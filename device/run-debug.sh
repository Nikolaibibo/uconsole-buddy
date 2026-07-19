#!/usr/bin/env bash
cd "$HOME/Documents/web/uconsole-companion"
source .venv/bin/activate
while true; do
  # BlueZ frisch: verwaiste GATT-Registrierung (SIGKILL/Crash-Reste) + Controller-Reset (#1)
  sudo systemctl restart bluetooth 2>/dev/null
  sleep 4
  python -m companion.main
  code=$?
  [ "$code" -eq 0 ] && break        # sauberes Quit (q) -> nicht neu starten
  echo "[companion crash (exit $code) - Neustart in 3s]"
  sleep 3
done
