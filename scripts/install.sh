#!/usr/bin/env bash
# DeepDict macOS / Linux CLI Installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/huweisoog/deepdict/main/scripts/install.sh | bash
# Or install from a local clone:
#   bash ./scripts/install.sh .

set -euo pipefail

DEFAULT_REPO="git+https://github.com/huweisoog/deepdict.git"
SOURCE="${1:-${DEEPDICT_SOURCE:-}}"

if [ -z "$SOURCE" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
    SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"
  else
    SOURCE="$DEFAULT_REPO"
  fi
fi

INSTALL_ROOT="${HOME}/.local/share/deepdict"
VENV_DIR="${INSTALL_ROOT}/venv"
BIN_DIR="${HOME}/.local/bin"

echo "==> DeepDict Installer (macOS / Linux)"
echo "    Source : ${SOURCE}"
echo "    Target : ${INSTALL_ROOT}"

PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Error: Python 3.10+ is required." >&2
  echo "macOS users can install it via Homebrew: brew install python@3.12" >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "==> Creating isolated virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "==> Upgrading pip and installing DeepDict..."
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install --upgrade "$SOURCE"

ln -sf "${VENV_DIR}/bin/deepdict" "${BIN_DIR}/deepdict"

APP_BUNDLE_MSG=""
if [ "$(uname -s)" = "Darwin" ] && [ "${DEEPDICT_NO_APP:-0}" != "1" ]; then
  echo "==> Creating macOS application bundle (DeepDict.app)..."
  if APP_OUT="$(QT_QPA_PLATFORM=offscreen "${VENV_DIR}/bin/python" -m deepdict --install-app 2>&1)"; then
    APP_BUNDLE_MSG="$APP_OUT"
    echo "    ${APP_OUT}"
  else
    echo "    (Skipped macOS app bundle: ${APP_OUT})"
  fi
fi

echo ""
echo "DeepDict installed successfully!"
if [ -n "$APP_BUNDLE_MSG" ]; then
  echo "  Open App   : Finder -> 应用程序 / Launchpad / Spotlight -> DeepDict"
fi
echo "  Run GUI    : deepdict"
echo "  Demo mode  : deepdict --demo"
echo "  Self check : deepdict --selftest"

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    echo ""
    echo "Note: ${BIN_DIR} is not in your PATH yet. Add this to your ~/.zshrc or ~/.bashrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

if [ "$(uname -s)" = "Darwin" ]; then
  echo ""
  echo "macOS Tip: For global hotkeys and selection bubbles, grant Accessibility permission to"
  echo "DeepDict (or your Terminal / Python) in: System Settings -> Privacy & Security -> Accessibility."
fi
