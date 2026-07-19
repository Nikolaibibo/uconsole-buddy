#!/usr/bin/env bash
cd "$HOME/Documents/web/uconsole-companion"
# BlueZ komplett frisch machen: entfernt verwaiste GATT-Registrierungen (SIGKILL-Reste)
# UND resettet den Controller — das ist, was bisher nur ein Reboot löste (#1).
sudo systemctl restart bluetooth 2>/dev/null
sleep 4
source .venv/bin/activate
python -m companion.main
echo
echo "[companion beendet — Enter zum Schliessen]"
read
