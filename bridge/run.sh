#!/usr/bin/env bash
cd "$HOME/Documents/web/uconsole-companion-bridge"
source .venv/bin/activate
exec python -m bridge.daemon
