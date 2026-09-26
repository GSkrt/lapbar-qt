#!/usr/bin/env bash
# Switch between the two LapBar builds so only one runs at a time:
#   omarchy - the Quickshell bar-widget plugin (io.github.gskrt.lapbar)
#   qt      - this repo's own standalone PyQt6 tray app
#
# Path is relative to this script, not hardcoded, so it works from wherever the repo is cloned.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="io.github.gskrt.lapbar"
QT_ENTRY_POINT="$ROOT/app/bin/lapbar-qt"

usage() {
  echo "Usage: $(basename "$0") omarchy|qt|off|status" >&2
  exit 1
}

status() {
  omarchy-plugin-list | awk -v id="$PLUGIN_ID" '$1 == id { print "omarchy plugin: " $2 }'
  pgrep -f "$QT_ENTRY_POINT" >/dev/null 2>&1 && echo "qt app: running" || echo "qt app: not running"
}

[[ $# -eq 1 ]] || usage

case "$1" in
  omarchy)
    pkill -f "$QT_ENTRY_POINT" 2>/dev/null || true
    omarchy-plugin-enable "$PLUGIN_ID"
    ;;
  qt)
    omarchy-plugin-disable "$PLUGIN_ID"
    setsid nohup "$QT_ENTRY_POINT" >/dev/null 2>&1 &
    ;;
  off)
    omarchy-plugin-disable "$PLUGIN_ID"
    pkill -f "$QT_ENTRY_POINT" 2>/dev/null || true
    ;;
  status)
    status
    ;;
  *)
    usage
    ;;
esac
