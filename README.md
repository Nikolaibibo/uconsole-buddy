# uConsole Claude Companion — Bridge (Terminal)

Verbindet Claude Code (Terminal) via PreToolUse-Hook + BLE-Daemon mit der uConsole.
Gerät = Peripheral `Claude-uConsole`. Spec/Plan: Vault `Privat/Projekte/Uconsole/`.

## Start
    source .venv/bin/activate
    python -m bridge.daemon        # Daemon (hält BLE + Socket)
    pytest -q                      # Pure-Logic-Tests
