#!/usr/bin/env bash
# Symlink the GJC uConsole-buddy extension into GJC's extension directory.
#
#   ~/.gjc/agent/extensions/uconsole-buddy.ts  ->  this repo's copy
#
# Honours $GJC_CODING_AGENT_DIR (default ~/.gjc/agent). Re-run any time to
# refresh the link. Use `--pi` to target a pi install (~/.pi/agent) instead.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/uconsole-buddy.ts"

AGENT_DIR="${GJC_CODING_AGENT_DIR:-$HOME/.gjc/agent}"
if [ "${1:-}" = "--pi" ]; then
  AGENT_DIR="$HOME/.pi/agent"
fi

EXT_DIR="$AGENT_DIR/extensions"
mkdir -p "$EXT_DIR"
ln -sf "$SRC" "$EXT_DIR/uconsole-buddy.ts"

echo "linked: $EXT_DIR/uconsole-buddy.ts -> $SRC"
echo "Start the bridge daemon, then run gjc. Approvals gate: ${UCONSOLE_BRIDGE_APPROVE:-bash}"
