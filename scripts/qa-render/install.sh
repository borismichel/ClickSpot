#!/usr/bin/env bash
#
# Install / refresh the shared qa-render harness onto this host so every agent
# (any company, any workspace) uses the same wrapper. Safe to re-run.
#
#   ./scripts/qa-render/install.sh
#
# Installs:
#   ~/.local/share/qa-render/qa-render     (the wrapper)
#   ~/.local/share/qa-render/launch.cjs    (the JS launch helper)
#   ~/.local/bin/qa-render  ->  ../share/qa-render/qa-render   (symlink, on PATH)
#
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/qa-render"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$SHARE_DIR" "$BIN_DIR"
install -m 0755 "$SRC_DIR/qa-render" "$SHARE_DIR/qa-render"
install -m 0644 "$SRC_DIR/launch.cjs" "$SHARE_DIR/launch.cjs"

ln -sfn "$SHARE_DIR/qa-render" "$BIN_DIR/qa-render"

echo "Installed:"
echo "  $SHARE_DIR/qa-render"
echo "  $SHARE_DIR/launch.cjs"
echo "  $BIN_DIR/qa-render -> $SHARE_DIR/qa-render"
echo
if command -v qa-render >/dev/null 2>&1; then
  echo "qa-render is on PATH: $(command -v qa-render)"
else
  echo "NOTE: $BIN_DIR is not on PATH. Add it:  export PATH=\"$BIN_DIR:\$PATH\""
fi
echo "Helper for require(): $SHARE_DIR/launch.cjs"
