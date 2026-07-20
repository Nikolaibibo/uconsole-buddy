#!/usr/bin/env bash
# Launch the bridge daemon from wherever this repo is checked out.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../bridge/bridge
BRIDGE_DIR="$(dirname "$HERE")"                         # .../bridge
cd "$BRIDGE_DIR"
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
exec python -m bridge.daemon
