#!/usr/bin/env bash
cd "$HOME/Documents/web/uconsole-companion"
export GERALD_LANG=de
# Lokale Konfiguration (Transport, TCP-Secret). Fehlt die Datei, bleibt BLE aktiv
# -- das ist der Rueckweg: .env.local weg, launch-display.sh, fertig.
if [ -f .env.local ]; then set -a; . ./.env.local; set +a; fi
source .venv/bin/activate
while true; do
  # BlueZ frisch: verwaiste GATT-Registrierung (SIGKILL/Crash-Reste) + Controller-Reset (#1)
  if [ "${COMPANION_TRANSPORT:-ble}" = "ble" ]; then
    sudo systemctl restart bluetooth 2>/dev/null
    sleep 4
  fi
  python -m companion.main
  code=$?
  [ "$code" -eq 0 ] && break        # sauberes Quit (q) -> nicht neu starten
  echo "[companion crash (exit $code) - Neustart in 3s]"
  sleep 3
done
