"""Where secrets live: the system keyring when there is one, otherwise a private file.

Two items are stored: "client_secret" (your Strava app's secret) and "tokens" (JSON with the access and
refresh tokens). Nothing secret is ever written to the cache, to logs or to the plain-text config file
(which only holds the non-secret Client ID).

Order of lookup: the keyring, then the private file, then legacy plain-text files from older versions
(which are migrated into the keyring the first time it is reachable and then deleted).
"""
import json
import os
import subprocess

from . import config, platforms, system

SERVICE = "lapbar"
TIMEOUT = 8  # seconds; a locked keyring can wait for an unlock prompt


class VaultUnavailable(RuntimeError):
    """The keyring could not be reached (locked, no session bus, secret-tool missing)."""


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    if os.environ.get("LAPBAR_NO_KEYRING"):  # opt out: use the private file instead
        raise FileNotFoundError("keyring disabled by LAPBAR_NO_KEYRING")
    # secret-tool handles the Strava client secret and the sign-in tokens, so it is resolved to Omarchy's own
    # copy rather than trusting whatever a $PATH search would find first (see system.py).
    return subprocess.run([system.tool("secret-tool"), *args], input=stdin, capture_output=True, text=True,
                          timeout=TIMEOUT)


class Keyring:
    def _call(self, args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        try:
            return _run(args, stdin)
        except FileNotFoundError:
            raise VaultUnavailable("secret-tool is not installed (package libsecret)") from None
        except subprocess.TimeoutExpired:
            raise VaultUnavailable("the keyring did not answer in time; it may be locked") from None

    def get(self, name: str) -> str | None:
        done = self._call(["lookup", "service", SERVICE, "key", name])
        if done.returncode == 0:
            return done.stdout or None
        if done.stderr.strip():  # a plain "not found" is silent; anything said means a real problem
            raise VaultUnavailable(done.stderr.strip())
        return None

    def set(self, name: str, value: str) -> None:
        done = self._call(["store", "--label", f"lapbar {name}", "service", SERVICE, "key", name], value)
        if done.returncode != 0:
            raise VaultUnavailable(done.stderr.strip() or "could not write to the keyring")

    def delete(self, name: str) -> None:
        self._call(["clear", "service", SERVICE, "key", name])


class NoKeyring:
    """A system without a keyring LapBar can use safely: nothing is ever found, and every write is refused, so
    vault.set() falls back to the private file. Used on macOS, whose built-in `security` tool takes the secret
    as a command-line argument (readable by every local account in `ps`)."""

    def get(self, name: str) -> str | None:
        return None

    def set(self, name: str, value: str) -> None:
        raise VaultUnavailable("no keyring on this system")

    def delete(self, name: str) -> None:
        pass


class WindowsCredentials:
    """Windows Credential Manager (generic credentials), called in-process through advapi32: the secret never
    leaves this process except into the Credential Manager, which encrypts it for the signed-in user."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168
    MAX_BLOB = 5 * 512                     # CRED_MAX_CREDENTIAL_BLOB_SIZE

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self.ctypes = ctypes
        self.CREDENTIAL = CREDENTIAL
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        api.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(CREDENTIAL)))
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = (ctypes.POINTER(CREDENTIAL), wintypes.DWORD)
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = (ctypes.c_void_p,)
        self.api = api

    @staticmethod
    def _target(name: str) -> str:
        return f"{SERVICE}:{name}"

    def _failed(self, what: str):
        code = self.ctypes.get_last_error()
        raise VaultUnavailable(f"Windows Credential Manager could not {what} (error {code})")

    def get(self, name: str) -> str | None:
        ctypes = self.ctypes
        found = ctypes.POINTER(self.CREDENTIAL)()
        if not self.api.CredReadW(self._target(name), self.CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == self.ERROR_NOT_FOUND:
                return None
            self._failed("read a secret")
        try:
            cred = found.contents
            return ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode("utf-8") or None
        finally:
            self.api.CredFree(found)

    def set(self, name: str, value: str) -> None:
        ctypes = self.ctypes
        blob = value.encode("utf-8")
        if len(blob) > self.MAX_BLOB:
            raise VaultUnavailable("the secret is too large for Windows Credential Manager")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = self.CREDENTIAL()
        cred.Type = self.CRED_TYPE_GENERIC
        cred.TargetName = self._target(name)
        cred.Comment = f"lapbar {name}"
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = SERVICE
        if not self.api.CredWriteW(ctypes.byref(cred), 0):
            self._failed("store a secret")

    def delete(self, name: str) -> None:
        if not self.api.CredDeleteW(self._target(name), self.CRED_TYPE_GENERIC, 0) \
                and self.ctypes.get_last_error() != self.ERROR_NOT_FOUND:
            self._failed("remove a secret")


def _keyring():
    """The keyring for this system. LAPBAR_KEYRING (secret-tool, windows or none) overrides the choice."""
    choice = os.environ.get("LAPBAR_KEYRING") or ("windows" if platforms.IS_WINDOWS else
                                                  "none" if platforms.IS_MAC else "secret-tool")
    if choice == "windows":
        try:
            return WindowsCredentials()
        except (OSError, AttributeError):        # not on Windows after all
            return NoKeyring()
    return NoKeyring() if choice == "none" else Keyring()


class PrivateFile:
    """Fallback when there is no keyring: one JSON file that only the current user can read."""

    @property
    def path(self):
        return config.state_dir() / "secrets.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        config.private_dir(self.path.parent)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # 0600 from the first byte
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(self.path)

    def get(self, name: str) -> str | None:
        return self._load().get(name) or None

    def set(self, name: str, value: str) -> None:
        data = self._load()
        data[name] = value
        self._save(data)

    def delete(self, name: str) -> None:
        data = self._load()
        if data.pop(name, None) is not None:
            if data:
                self._save(data)
            else:
                self.path.unlink(missing_ok=True)


def _legacy(name: str) -> str | None:
    """Plain-text locations used by earlier versions (read-only fallback)."""
    if name == "tokens":
        try:
            return (config.state_dir() / "tokens.json").read_text(encoding="utf-8") or None
        except FileNotFoundError:
            return None
    if name == "client_secret":
        return config.get("STRAVA_CLIENT_SECRET") or None
    return None


def get(name: str) -> str | None:
    problem = None
    try:
        value = _keyring().get(name)
        if value:
            return value
    except VaultUnavailable as e:
        problem = e
    value = PrivateFile().get(name) or _legacy(name)
    if value:
        return value
    if problem:
        raise problem
    return None


def set(name: str, value: str) -> str:  # noqa: A001 - mirrors get/delete
    """Store a secret; returns where it went: "keyring" or "file"."""
    try:
        _keyring().set(name, value)
        PrivateFile().delete(name)
        return "keyring"
    except VaultUnavailable:
        PrivateFile().set(name, value)
        return "file"


def delete(name: str) -> None:
    try:
        _keyring().delete(name)
    except VaultUnavailable:
        pass
    PrivateFile().delete(name)


def keyring_available() -> bool:
    ring = _keyring()
    if isinstance(ring, NoKeyring):
        return False
    try:
        ring.get("probe")
        return True
    except VaultUnavailable:
        return False


def client_secret() -> str | None:
    return os.environ.get("STRAVA_CLIENT_SECRET") or get("client_secret")


def migrate_legacy() -> list[str]:
    """Move plain-text secrets from older versions into the keyring, then delete them.

    Only runs when the keyring is reachable, so a locked keyring never causes secrets to be
    parked somewhere weaker.
    """
    tokens_file = config.state_dir() / "tokens.json"
    env_file = config.user_env_path()
    has_old_secret = "STRAVA_CLIENT_SECRET" in config.read_env_file(env_file)
    if not (tokens_file.exists() or has_old_secret) or not keyring_available():
        return []
    moved = []
    if tokens_file.exists():
        if _copy_verified("tokens", tokens_file.read_text(encoding="utf-8")):
            tokens_file.unlink()
            moved.append("tokens")
    if has_old_secret:
        secret = config.read_env_file(env_file)["STRAVA_CLIENT_SECRET"]
        if not secret or _copy_verified("client_secret", secret):
            config.write_env_file(env_file, {}, remove=["STRAVA_CLIENT_SECRET"])
            moved.append("client_secret")
    return moved


def _copy_verified(name: str, value: str) -> bool:
    """Put `value` in the keyring unless it already holds something, and confirm by reading back.

    Returns True only when the keyring holds a value for `name`, so the caller may then delete the
    plain-text original. An existing keyring value is never overwritten.
    """
    ring = _keyring()
    if ring.get(name) is None:
        ring.set(name, value)
    return ring.get(name) is not None
