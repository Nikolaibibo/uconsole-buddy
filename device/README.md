# uConsole Claude Companion

Physisches Freigabe-/Status-Terminal für Claude Desktop "Hardware Buddy" über BLE (Nordic UART).
Läuft auf der uConsole (CM4, hci0). Spec + Plan: Obsidian Vault `Privat/Projekte/Uconsole/`.

## Dev
    source .venv/bin/activate
    pytest -q                 # Pure-Logic-Tests
    python -m companion.main  # App starten (BLE, Phase 1+)

## Transport
- **BLE** (default): `python -m companion.main` — Nordic-UART peripheral on hci0.
- **TCP** (remote / Tailscale, no BLE): the device hosts the aggregator itself.

      UCONSOLE_TRANSPORT=tcp UCONSOLE_LISTEN=0.0.0.0:8765 python -m companion.main

  The agent connects with `UCONSOLE_BRIDGE_ADDR=<this-host>:8765`. See
  `../bridge/gjc/README.md`.

## Protokoll
Vertrag: github.com/anthropics/claude-desktop-buddy/REFERENCE.md
