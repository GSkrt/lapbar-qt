"""First-run setup: a QWizard walking a non-technical user through creating their own Strava API app,
pasting its Client ID/Secret, and signing in. The GUI equivalent of `lapbar setup` (backend's setup.py),
reusing its real validation regexes, storage calls and auth.authorize() rather than re-implementing them --
setup.py's own flow is written around blocking terminal I/O (input()/print()), which a GUI can't reuse
directly, so this rebuilds the same three steps as wizard pages instead.
"""
import html
import webbrowser

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWizard, QWizardPage

from lapbar import auth, config, setup, vault


def _link(url: str, text: str | None = None) -> QLabel:
    """A QLabel that renders `url` as a real, clickable hyperlink opened in the system browser."""
    label = QLabel(f'<a href="{html.escape(url)}">{html.escape(text or url)}</a>')
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    label.setWordWrap(True)
    return label


class IntroPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Set up lapbar-qt")
        layout = QVBoxLayout(self)
        text = QLabel(
            "lapbar-qt reads your activities straight from Strava. For that, Strava requires every app to use "
            "its own API credentials, so you'll register a small private app under your own account — "
            "there is no shared key, and your data never passes through anyone else. It takes about two "
            "minutes.\n\n"
            "You'll need:\n"
            "  • a Strava account\n"
            "  • an active Strava subscription (Strava requires one to create API apps — see:)\n"
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addWidget(_link(setup.DOCS_URL))
        more = QLabel("  • to sign in with the same account that owns the app\n\n"
                       "You can cancel this at any time and run it again later from the tray menu.")
        more.setWordWrap(True)
        layout.addWidget(more)


class CreateAppPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 1 of 3 — create your Strava API app")
        layout = QVBoxLayout(self)

        step1 = QLabel(f'1. Open the Strava API settings page: <a href="{html.escape(setup.API_SETTINGS_URL)}">'
                        f'{html.escape(setup.API_SETTINGS_URL)}</a>')
        step1.setTextFormat(Qt.TextFormat.RichText)
        step1.setOpenExternalLinks(True)
        step1.setWordWrap(True)
        layout.addWidget(step1)

        open_button = QPushButton("Open Strava API settings in browser")
        open_button.clicked.connect(lambda: webbrowser.open(setup.API_SETTINGS_URL))
        layout.addWidget(open_button)

        text = QLabel(
            "2. Fill in the form exactly like this:\n\n"
            "     Application Name ............ lapbar-qt   (anything you like)\n"
            "     Category ..................... Visualizer\n"
            "     Club .......................... leave empty\n"
            "     Website ....................... http://localhost\n"
            "     Application Description ...... Personal status tray app\n"
            "     Authorization Callback Domain   localhost   ← must be exactly this\n"
            "     Icon .......................... Strava asks for an image; any picture works\n\n"
            "3. Click Create. Strava then shows your Client ID and Client Secret (click ‘Show’)."
        )
        text.setWordWrap(True)
        layout.addWidget(text)


class CredentialsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 2 of 3 — paste your credentials")
        layout = QFormLayout(self)

        hint = QLabel(
            "Client ID is the number near the top of the page.\n"
            "Client Secret is the long code under it (click ‘Show’).\n\n"
            "Take the Client Secret, not the Access Token or Refresh Token further down — those only have "
            "read access and cannot see your activities."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)

        self.client_id_edit = QLineEdit()
        self.client_id_edit.setPlaceholderText("e.g. 123456")
        self.client_id_edit.textChanged.connect(self.completeChanged)
        layout.addRow("Client ID:", self.client_id_edit)

        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret_edit.setPlaceholderText("40 characters, hidden")
        self.client_secret_edit.textChanged.connect(self.completeChanged)
        layout.addRow("Client Secret:", self.client_secret_edit)

        self.registerField("client_id*", self.client_id_edit)
        self.registerField("client_secret*", self.client_secret_edit)

    def isComplete(self) -> bool:
        return (setup.valid_client_id(self.client_id_edit.text().strip())
                and setup.valid_client_secret(self.client_secret_edit.text().strip()))

    def validatePage(self) -> bool:
        client_id = self.client_id_edit.text().strip()
        client_secret = self.client_secret_edit.text().strip()
        config.write_env_file(config.user_env_path(), {"STRAVA_CLIENT_ID": client_id})
        try:
            vault.set("client_secret", client_secret)
        except vault.VaultUnavailable as e:
            QMessageBox.warning(self, "Keyring unavailable", str(e))
            return False
        return True


class _AuthWorker(QObject):
    finished = pyqtSignal(bool, str)  # ok, error message
    urlReady = pyqtSignal(str)        # the authorize URL, as soon as auth.authorize() has built it

    def __init__(self, client_id: str, client_secret: str):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret

    def _out(self, message: str):
        # auth.authorize() reports its progress through this callback, one line at a time; the only line
        # worth surfacing back to the wizard is the authorize URL itself, as a fallback link in case the
        # automatic browser-open silently fails (e.g. no default browser configured).
        text = message.strip()
        if text.startswith("http"):
            self.urlReady.emit(text)

    @pyqtSlot()
    def run(self):
        try:
            auth.authorize(self.client_id, self.client_secret, open_browser=True, out=self._out)
        except Exception as e:  # noqa: BLE001 - reported back to the wizard page, never raised into the thread
            self.finished.emit(False, str(e))
            return
        self.finished.emit(True, "")


class SignInPage(QWizardPage):
    """Runs auth.authorize() on a background QThread (it blocks on a local HTTP server waiting for Strava's
    redirect) and only reports the page complete once that finishes -- the same QThread-worker pattern
    verified in PLAN.md for the periodic fetch, reused here so opening the browser never freezes the wizard.
    """

    def __init__(self):
        super().__init__()
        self.setTitle("Step 3 of 3 — sign in with Strava")
        self.setFinalPage(True)
        self._ok = False
        self._thread: QThread | None = None
        self._worker: _AuthWorker | None = None
        layout = QVBoxLayout(self)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.link = QLabel("")
        self.link.setTextFormat(Qt.TextFormat.RichText)
        self.link.setOpenExternalLinks(True)
        self.link.setWordWrap(True)
        self.link.hide()
        layout.addWidget(self.link)

    def initializePage(self):
        self._ok = False
        self.link.hide()
        self.status.setText(
            "Opening Strava's authorization page in your browser. Click Authorize and leave every permission "
            "ticked — lapbar-qt needs to read your activities.\n\nWaiting…"
        )
        self._thread = QThread()
        self._worker = _AuthWorker(self.field("client_id"), self.field("client_secret"))
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_finished)
        self._worker.urlReady.connect(self._on_url)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_url(self, url: str):
        self.link.setText(f'If nothing opened automatically, click: <a href="{html.escape(url)}">{html.escape(url)}</a>')
        self.link.show()

    def _on_finished(self, ok: bool, message: str):
        self._thread.quit()
        self._thread.wait()
        self.link.hide()
        if ok:
            self._ok = True
            try:
                self.status.setText(f"All set! Signed in as {setup.athlete_name()}.")
            except Exception:  # noqa: BLE001 - the sign-in itself already succeeded; this is cosmetic only
                self.status.setText("All set! (Could not read your name from Strava just now, which is harmless.)")
        else:
            self._ok = False
            self.status.setText(
                f"Sign-in failed: {message}\n\nGo back and check your Client ID and Client Secret, then try again.")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._ok


class SetupWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("lapbar-qt setup")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.addPage(IntroPage())
        self.addPage(CreateAppPage())
        self.addPage(CredentialsPage())
        self.addPage(SignInPage())


def run_setup_wizard(parent=None) -> bool:
    return SetupWizard(parent).exec() == QWizard.DialogCode.Accepted
