#!/usr/bin/env bash
# Launch the companion face UI in TCP mode (remote agent over Tailscale, no BLE).
# Run this ON the uConsole, in a terminal attached to its display.
#
#   UCONSOLE_LISTEN  bind address (default 0.0.0.0:8765)
#   GERALD_LANG      en | de (default en)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
[ -d .venv ] && source .venv/bin/activate
export UCONSOLE_TRANSPORT=tcp
export UCONSOLE_LISTEN="${UCONSOLE_LISTEN:-0.0.0.0:8765}"
echo "Gerald (TCP) listening on $UCONSOLE_LISTEN — agents connect with UCONSOLE_BRIDGE_ADDR=<this-host>:${UCONSOLE_LISTEN##*:}"
exec python -m companion.main
