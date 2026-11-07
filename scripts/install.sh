#!/bin/sh
# Install Qasida (2.0.0) for the current user.
# Usage, from a checkout of RED-MOON-:
#   sh scripts/install.sh
# Usage, without cloning first (needs git):
#   git clone https://github.com/harshhdubeyyyy/RED-MOON- && cd RED-MOON- && sh scripts/install.sh
# What it does:
#   1. Checks python3 and a C compiler (cc) are present.
#   2. Symlinks bin/qasida into ~/.local/bin/qasida.
#   3. Verifies: qasida --version and qasida run examples/qasida_demo.fg
# It does NOT need root, and it does NOT change your system Python.
set -e
if ! command -v python3 >/dev/null 2>&1; then
    echo "install: python3 not found — install Python 3 from python.org, then run this again." >&2
    exit 1
fi
if ! command -v cc >/dev/null 2>&1; then
    echo "install: no C compiler (cc) found — install gcc / Xcode Command Line Tools / Build Tools, then run this again." >&2
    exit 1
fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
if [ ! -f "$REPO_DIR/forge.py" ]; then
    echo "install: forge.py not found in $REPO_DIR — run this script from a RED-MOON- checkout." >&2
    exit 1
fi
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO_DIR/bin/qasida" "$HOME/.local/bin/qasida"
chmod +x "$REPO_DIR/bin/qasida"
export PATH="$HOME/.local/bin:$PATH"
echo "installed: $HOME/.local/bin/qasida"
"$HOME/.local/bin/qasida" --version
"$HOME/.local/bin/qasida" run "$REPO_DIR/examples/qasida_demo.fg"
echo ""
echo "Done. If 'qasida' is not found in a new terminal, add this line to your shell profile:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
