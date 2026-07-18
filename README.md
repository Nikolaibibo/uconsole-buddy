# uConsole Claude Companion

Physisches Freigabe-/Status-Terminal für Claude Desktop "Hardware Buddy" über BLE (Nordic UART).
Läuft auf der uConsole (CM4, hci0). Spec + Plan: Obsidian Vault `Privat/Projekte/Uconsole/`.

## Dev
    source .venv/bin/activate
    pytest -q                 # Pure-Logic-Tests
    python -m companion.main  # App starten (Phase 1+)

## Protokoll
Vertrag: github.com/anthropics/claude-desktop-buddy/REFERENCE.md
