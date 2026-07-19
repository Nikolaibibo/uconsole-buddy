---
tags: [projekt, uconsole, claude, ble, maker, plan]
status: bereit
created: 2026-07-19
source: marvin-session
hardware: uConsole (Raspberry Pi CM4)
sprache: Python
spec: "[[Claude Companion uConsole - Spec]]"
---

# Claude Companion (uConsole) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein physisches Freigabe-/Status-Terminal auf der uConsole, das per BLE (Nordic UART) mit Claude Desktops "Hardware Buddy" spricht: zeigt Sessions/Status/Tokens, erlaubt Tool-Freigaben per Tastendruck (`once`/`deny`).

**Architecture:** Ein Python-asyncio-Prozess. Reine Logik (Byte-Framing, JSON-Protokoll, App-State/State-Machine) ist BlueZ-frei und voll unit-getestet; `ble_nus.py` ist dünner `bluez-peripheral`-Glue auf **hci0**; `ui.py` ist eine Textual-Fenster-App; `main.py` verdrahtet alles in einer Event-Loop. Protokoll ist 1:1 der Vertrag aus `anthropics/claude-desktop-buddy` `REFERENCE.md`; das Verhalten spiegelt die Referenz-Firmware, mit einem Delivery-Sicherheitsnetz obendrauf.

**Tech Stack:** Python 3.11, asyncio, `bluez-peripheral` (+ `dbus-fast` für den Pairing-Agent in Phase 3), `textual`, `pytest`. Ziel-OS: Debian 12 Bookworm auf CM4, BlueZ 5.66.

## Global Constraints

- **Python 3.11+**, komplett `asyncio`, keine Threads.
- **BLE-Adapter hart auf hci0 pinnen** (`2C:CF:67:FE:1E:1D`, onboard Cypress). hci1 (USB-Realtek `90:DE:80:D4:12:DE`) ignorieren.
- **NUS-UUIDs verbatim:** Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`, RX (write) `6e400002-…`, TX (notify) `6e400003-…`.
- **Framing:** UTF-8 JSON, ein Objekt pro Zeile, `\n`-terminiert. RX bis `\n` puffern, dann parsen. TX chunken auf `min(mtu-3, 180)` Byte, ~4 ms Yield zwischen Chunks.
- **Advertising-Name** beginnt mit `Claude`; ein paar Bytes der BT-MAC anhängen (`Claude-uConsole`).
- **Permission-`decision`** nur `"once"` (erlauben) oder `"deny"` (ablehnen). `id` muss `prompt.id` exakt matchen.
- **Timeout:** kein Snapshot >30 s → Verbindung tot (`disconnected`).
- **Keepalive:** Mac schickt Snapshots bei Änderung + alle 10 s; Mac pollt `status` ~alle 2 s.
- **Folder-Push NICHT unterstützen:** `char_begin`/`file`/`chunk`/… **nicht** acken → Mac läuft in Timeout.
- **Sicherheit:** Phase 1 darf unverschlüsselt sein. Phase 3 = LE Secure Connections Bonding, DisplayOnly-IO, Passkey am Gerät anzeigen, NUS-Chars + CCCD encrypted-only, `sec:true` nur bei verschlüsseltem Link.
- **Scope-Trims (nicht bauen):** GIF-Pets, Folder-Push, Stats `vel`/`nap`/`lvl`, `bat`-Feld.
- **Repo:** `~/Documents/web/uconsole-companion/`. Entwickeln/Testen läuft **auf der uConsole** (per SSH `nikolai@192.168.178.146`).

---

## File Structure

```
uconsole-companion/
├── README.md
├── requirements.txt
├── companion/
│   ├── __init__.py
│   ├── framing.py     # LineReassembler (bytes→lines) + chunk_for_mtu — pure, dep-frei
│   ├── protocol.py    # parse_message + build_permission/build_ack/build_status_ack — pure
│   ├── state.py       # AppState: Snapshot anwenden, Prompt-State-Machine + Rearm, connection_state, Zähler
│   ├── ble_nus.py     # bluez-peripheral NUS-Peripheral auf hci0: Advertising, GATT-Chars, RX→Reassembler, TX-Queue→Chunker, Reconnect
│   ├── agent.py       # (Phase 3) dbus-fast DisplayOnly Pairing-Agent
│   ├── ui.py          # Textual-App: Panels + Freigabe-Overlay + Keybindings
│   └── main.py        # asyncio-Verdrahtung: RX-Routing, One-Shots, Acks, Keys→permission, Tick
├── tools/
│   └── fake_central.py  # OPTIONAL Fallback-Dev-Harness (bleak-Central), NICHT Teil des Kerns
└── tests/
    ├── test_framing.py
    ├── test_protocol.py
    └── test_state.py
```

**Warum eine kleine Abweichung vom Ur-Spec:** Der Spec legte den Line-Reassembler in `ble_nus.py`. Wir ziehen Reassembler **und** TX-Chunker in ein dep-freies `framing.py`, damit die Tests laufen, ohne den BlueZ-Stack zu importieren. `ble_nus.py` importiert `framing`. Sonst bleibt die Modulaufteilung wie im Spec.

---

# PHASE 0 — Link beweisen + Environment

### Task 0.1: Repo + Environment-Scaffold

**Files:**
- Create: `~/Documents/web/uconsole-companion/README.md`
- Create: `~/Documents/web/uconsole-companion/requirements.txt`
- Create: `~/Documents/web/uconsole-companion/companion/__init__.py`
- Create: `~/Documents/web/uconsole-companion/.gitignore`

**Interfaces:**
- Produces: ein Repo mit aktivem venv, in dem `bluez_peripheral`, `dbus_fast`, `textual`, `pytest` importierbar sind.

- [ ] **Step 1: Repo + venv anlegen (auf der uConsole)**

```bash
ssh nikolai@192.168.178.146
mkdir -p ~/Documents/web/uconsole-companion/{companion,tests,tools}
cd ~/Documents/web/uconsole-companion
git init
python3 -m venv .venv
source .venv/bin/activate
python --version   # erwartet: Python 3.11.x
```

- [ ] **Step 2: `requirements.txt` schreiben**

```
bluez-peripheral>=0.1.7
dbus-fast>=2.21
textual>=0.60
pytest>=8.0
```

> **Korrektur (Basis-Build 19.07.):** `bluez-peripheral==0.2.0` existiert nicht auf PyPI (nur Alphas) → Pin auf `>=0.1.7` (stable). Zusätzlich `pyproject.toml` mit `[tool.pytest.ini_options] pythonpath=["."]` angelegt, damit bare `pytest` das Repo-Root findet.
>
> **Korrektur (Task 0.3 gebaut + verifiziert 19.07.):** `bluez-peripheral` 0.1.7 hängt an **`dbus_next`, NICHT `dbus_fast`**. Real umgesetzt in `ble_nus.py`: `from bluez_peripheral.util import get_message_bus, Adapter` (statt roher `dbus_fast`-MessageBus). Adapter-Wahl **explizit per Adresse** über `Adapter.get_all()` + Match auf `2C:CF:67:FE:1E:1D` (nicht `get_first()` — der erwischt den falschen hci1). Advertising auf hci0 live bewiesen (`LEAdvertisingManager1.ActiveInstances: 1`). **Folge für Task 3.1:** `agent.py` gegen **`dbus_next`** schreiben, nicht `dbus_fast` (siehe Korrektur-Banner dort).

- [ ] **Step 3: `.gitignore` schreiben**

```
.venv/
__pycache__/
*.pyc
companion.log
```

- [ ] **Step 4: `companion/__init__.py` schreiben (leer)**

```python
```

- [ ] **Step 5: Dependencies installieren + Import verifizieren**

Run:
```bash
pip install -r requirements.txt
python -c "import bluez_peripheral, dbus_fast, textual, pytest; print('deps OK')"
```
Expected: `deps OK` (kein ImportError). Falls `bluez-peripheral` beim Build zickt: `pip install dbus-fast` zuerst, dann erneut.

- [ ] **Step 6: `README.md` schreiben**

```markdown
# uConsole Claude Companion

Physisches Freigabe-/Status-Terminal für Claude Desktop "Hardware Buddy" über BLE (Nordic UART).
Läuft auf der uConsole (CM4, hci0). Spec + Plan: Obsidian Vault `Privat/Projekte/Uconsole/`.

## Dev
    source .venv/bin/activate
    pytest -q                 # Pure-Logic-Tests
    python -m companion.main  # App starten (Phase 1+)

## Protokoll
Vertrag: github.com/anthropics/claude-desktop-buddy/REFERENCE.md
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold uconsole-companion repo + deps"
```

---

### Task 0.2: `framing.py` — LineReassembler + chunk_for_mtu (TDD)

**Files:**
- Create: `companion/framing.py`
- Test: `tests/test_framing.py`

**Interfaces:**
- Produces:
  - `class LineReassembler(max_len: int = 8192)` mit `feed(self, data: bytes) -> list[str]` — hängt Bytes an, gibt vollständige UTF-8-Zeilen (ohne `\n`) zurück; übervoller Puffer wird verworfen.
  - `def chunk_for_mtu(data: bytes, mtu: int) -> list[bytes]` — splittet in Chunks der Größe `min(mtu-3, 180)` (bzw. 20 wenn `mtu<=3`).

- [ ] **Step 1: Failing test schreiben**

```python
# tests/test_framing.py
from companion.framing import LineReassembler, chunk_for_mtu


def test_reassembler_joins_split_line():
    r = LineReassembler()
    assert r.feed(b'{"a":') == []
    assert r.feed(b'1}\n') == ['{"a":1}']


def test_reassembler_multiple_lines_one_feed():
    r = LineReassembler()
    assert r.feed(b'{"a":1}\n{"b":2}\n') == ['{"a":1}', '{"b":2}']


def test_reassembler_keeps_remainder():
    r = LineReassembler()
    assert r.feed(b'{"a":1}\n{"b"') == ['{"a":1}']
    assert r.feed(b':2}\n') == ['{"b":2}']


def test_reassembler_drops_overlong_garbage():
    r = LineReassembler(max_len=16)
    assert r.feed(b'x' * 32) == []          # no newline, exceeds max_len → dropped
    assert r.feed(b'{"a":1}\n') == ['{"a":1}']  # resyncs after next newline


def test_chunk_for_mtu_caps_at_180():
    data = b'z' * 400
    chunks = chunk_for_mtu(data, mtu=185)   # 185-3=182 → cap 180
    assert all(len(c) <= 180 for c in chunks)
    assert b''.join(chunks) == data


def test_chunk_for_mtu_tiny_mtu_uses_20():
    data = b'z' * 50
    chunks = chunk_for_mtu(data, mtu=23)    # 23-3=20
    assert max(len(c) for c in chunks) == 20
    assert b''.join(chunks) == data
```

- [ ] **Step 2: Run → FAIL**

Run: `pytest tests/test_framing.py -v`
Expected: FAIL (`ModuleNotFoundError: companion.framing`).

- [ ] **Step 3: `framing.py` implementieren**

```python
# companion/framing.py
"""Byte-Framing für Nordic-UART-Serial-over-BLE. Reine Logik, keine BLE-Deps."""


class LineReassembler:
    """Puffert eingehende Bytes und gibt vollständige `\\n`-terminierte UTF-8-Zeilen zurück."""

    def __init__(self, max_len: int = 8192) -> None:
        self._buf = bytearray()
        self.max_len = max_len

    def feed(self, data: bytes) -> list[str]:
        self._buf.extend(data)
        lines: list[str] = []
        while True:
            i = self._buf.find(b"\n")
            if i < 0:
                break
            raw = bytes(self._buf[:i])
            del self._buf[: i + 1]
            try:
                lines.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                pass  # kaputte Zeile verwerfen, weitermachen
        if len(self._buf) > self.max_len:
            self._buf.clear()  # Müll ohne Zeilenende → droppen, beim nächsten \n resyncen
        return lines


def chunk_for_mtu(data: bytes, mtu: int) -> list[bytes]:
    """Splittet `data` in Notify-taugliche Chunks (ATT-Payload = MTU-3, gedeckelt bei 180)."""
    size = mtu - 3 if mtu > 3 else 20
    if size > 180:
        size = 180
    return [data[i : i + size] for i in range(0, len(data), size)]
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/test_framing.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add companion/framing.py tests/test_framing.py
git commit -m "feat: line reassembler + mtu chunker with tests"
```

---

### Task 0.3: `ble_nus.py` minimal — Advertising + RX-Logging auf hci0

**Files:**
- Create: `companion/ble_nus.py`
- Create: `companion/main.py` (Phase-0-Minimalversion; wird in Task 1.4 ersetzt)

**Interfaces:**
- Produces:
  - `class NusPeripheral(device_name: str, on_line: Callable[[str], None], adapter_addr: str = "2C:CF:67:FE:1E:1D")`
  - `async def start(self) -> None` — Adapter hci0 wählen, NUS-Service + RX/TX-Chars registrieren, Advertising starten. RX-Writes → `LineReassembler` → `on_line(line)` je Zeile.
  - `async def send_line(self, line: str) -> None` — String (inkl. `\n`) über TX notifien, via `chunk_for_mtu` gechunkt.
  - `def is_connected(self) -> bool`
  - Bei Disconnect: Advertising automatisch neu starten.

- [ ] **Step 1: `ble_nus.py` implementieren**

> Hinweis: `bluez-peripheral`s API kann je Version leicht abweichen. Referenzmuster: das mitgelieferte `nus`-Beispiel des Pakets. Kern: `Adapter` per Adresse holen, `Service`/`Characteristic` mit den 3 NUS-UUIDs, RX = `write`-Flag mit Write-Handler, TX = `notify`-Flag. Falls die installierte Version andere Klassennamen nutzt → an dieses Muster anpassen, Verhalten bleibt gleich.

```python
# companion/ble_nus.py
"""Nordic-UART BLE-Peripheral auf hci0 (bluez-peripheral / BlueZ D-Bus)."""
import asyncio
from typing import Callable

from bluez_peripheral.gatt.service import Service
from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags as Flags
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.util import Adapter
from dbus_fast.aio import MessageBus
from dbus_fast import BusType

from .framing import LineReassembler, chunk_for_mtu

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Mac → Gerät (write)
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Gerät → Mac (notify)
ADAPTER_ADDR = "2C:CF:67:FE:1E:1D"  # hci0 onboard Cypress — HART gepinnt


class _NusService(Service):
    def __init__(self, on_line: Callable[[str], None]):
        self._on_line = on_line
        self._reasm = LineReassembler()
        self._tx_value = bytearray()
        self._mtu = 185  # macOS-typisch; keine dynamische MTU-Abfrage in Phase 0
        super().__init__(NUS_SERVICE, True)

    @characteristic(NUS_TX, Flags.NOTIFY)
    def tx(self, options):
        return bytes(self._tx_value)

    @characteristic(NUS_RX, Flags.WRITE | Flags.WRITE_WITHOUT_RESPONSE)
    def rx(self, options):
        return b""

    @rx.setter
    def rx(self, value, options):
        for line in self._reasm.feed(bytes(value)):
            self._on_line(line)

    def notify_line(self, line: str) -> None:
        data = line.encode("utf-8")
        for chunk in chunk_for_mtu(data, self._mtu):
            self._tx_value = bytearray(chunk)
            self.tx.changed(bytes(chunk))  # sendet Notify an subscribte Clients


class NusPeripheral:
    def __init__(self, device_name: str, on_line: Callable[[str], None],
                 adapter_addr: str = ADAPTER_ADDR):
        self.device_name = device_name
        self.adapter_addr = adapter_addr
        self._svc = _NusService(on_line)
        self._bus: MessageBus | None = None
        self._adapter: Adapter | None = None
        self._advert: Advertisement | None = None
        self._connected = False

    async def start(self) -> None:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._adapter = await Adapter.get_first(self._bus)  # hci0-Pinning: siehe Hinweis
        await self._svc.register(self._bus, adapter=self._adapter)
        self._advert = Advertisement(self.device_name, [NUS_SERVICE], 0, 0)
        await self._advert.register(self._bus, self._adapter)

    async def send_line(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        self._svc.notify_line(line)

    def is_connected(self) -> bool:
        return self._connected
```

> **hci0-Pinning:** `Adapter.get_first` nimmt den ersten Adapter. Weil hci1 soft-blocked/DOWN ist, ist hci0 praktisch der einzig nutzbare — aber **verlass dich nicht drauf**. Beim ersten Lauf in Task 0.3 verifizieren, dass wirklich `2C:CF:67:…` advertised (siehe Step 3). Falls nicht: `Adapter` per Adresse selektieren (über `bus`-Introspektion `/org/bluez/hci0`) statt `get_first`. Das ist der eine Ort, wo das Pinning hart werden muss.

- [ ] **Step 2: Phase-0-`main.py` (nur Logging) schreiben**

```python
# companion/main.py  (PHASE 0 — wird in Task 1.4 ersetzt)
import asyncio
import logging

from .ble_nus import NusPeripheral

logging.basicConfig(
    filename="companion.log", level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger("companion")


def on_line(line: str) -> None:
    log.info("RX %s", line)
    print("RX", line)


async def _run() -> None:
    ble = NusPeripheral("Claude-uConsole", on_line)
    await ble.start()
    log.info("advertising as Claude-uConsole")
    print("advertising as Claude-uConsole — im Hardware Buddy verbinden")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(_run())
```

- [ ] **Step 3: Hardware-Verifikation — Link beweisen**

Auf der uConsole:
```bash
source .venv/bin/activate
python -m companion.main
```
Prüfen (BlueZ-seitig, zweites SSH-Fenster):
```bash
bluetoothctl show 2C:CF:67:FE:1E:1D | grep -i Discoverable   # sollte advertisen
```
Auf dem **Mac**: Claude Desktop → Help → Troubleshooting → Enable Developer Mode → Developer → Open Hardware Buddy… → Connect → **`Claude-uConsole`** in der Liste → verbinden, BT-Freigabe erteilen.

Expected: In `companion.log` / stdout tauchen `RX {…}`-Zeilen auf (Heartbeat-Snapshots, mind. alle 10 s). Damit ist die Kette Mac→BLE→hci0→Reassembler→Zeile bewiesen.

- [ ] **Step 4: Commit**

```bash
git add companion/ble_nus.py companion/main.py
git commit -m "feat(ble): NUS advertising on hci0 + raw RX line logging"
```

---

# PHASE 1 — Kern-Companion (funktionsfähig)

### Task 1.1: `protocol.py` — parse + build (TDD)

**Files:**
- Create: `companion/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces:
  - `def parse_message(line: str) -> dict | None` — `json.loads`, `None` bei Parse-Fehler.
  - `def build_permission(prompt_id: str, decision: str) -> str` — `{"cmd":"permission","id":…,"decision":…}\n`; `decision` ∈ {`"once"`,`"deny"`}, sonst `ValueError`.
  - `def build_ack(cmd: str, ok: bool = True, n: int | None = None, error: str | None = None) -> str` — nicht gesetzte Felder weglassen.
  - `def build_status_ack(name: str, sec: bool, up: int, appr: int, deny: int) -> str` — Status-Ack mit `data.name/sec/sys.up/stats.{appr,deny}`.

- [ ] **Step 1: Failing test schreiben**

```python
# tests/test_protocol.py
import json
from companion.protocol import (
    parse_message, build_permission, build_ack, build_status_ack,
)


def test_parse_valid():
    assert parse_message('{"total":3}') == {"total": 3}


def test_parse_invalid_returns_none():
    assert parse_message("not json") is None


def test_build_permission_once():
    m = json.loads(build_permission("req_abc", "once"))
    assert m == {"cmd": "permission", "id": "req_abc", "decision": "once"}


def test_build_permission_rejects_bad_decision():
    import pytest
    with pytest.raises(ValueError):
        build_permission("req_abc", "always")


def test_build_permission_terminated_by_newline():
    assert build_permission("x", "deny").endswith("\n")


def test_build_ack_omits_unset_fields():
    assert json.loads(build_ack("name")) == {"ack": "name", "ok": True}


def test_build_ack_includes_n_and_error():
    m = json.loads(build_ack("chunk", ok=False, n=12, error="boom"))
    assert m == {"ack": "chunk", "ok": False, "n": 12, "error": "boom"}


def test_build_status_ack_shape():
    m = json.loads(build_status_ack("Claude-uConsole", True, 8054, 42, 3))
    assert m["ack"] == "status" and m["ok"] is True
    assert m["data"]["name"] == "Claude-uConsole"
    assert m["data"]["sec"] is True
    assert m["data"]["sys"]["up"] == 8054
    assert m["data"]["stats"] == {"appr": 42, "deny": 3}
```

- [ ] **Step 2: Run → FAIL**

Run: `pytest tests/test_protocol.py -v`
Expected: FAIL (`ModuleNotFoundError: companion.protocol`).

- [ ] **Step 3: `protocol.py` implementieren**

```python
# companion/protocol.py
"""JSON-Protokoll für Hardware-Buddy NUS. Reine Logik, keine BLE-Deps."""
import json


def parse_message(line: str) -> dict | None:
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def build_permission(prompt_id: str, decision: str) -> str:
    if decision not in ("once", "deny"):
        raise ValueError(f"decision must be 'once' or 'deny', got {decision!r}")
    return json.dumps({"cmd": "permission", "id": prompt_id, "decision": decision}) + "\n"


def build_ack(cmd: str, ok: bool = True, n: int | None = None,
              error: str | None = None) -> str:
    m: dict = {"ack": cmd, "ok": ok}
    if n is not None:
        m["n"] = n
    if error is not None:
        m["error"] = error
    return json.dumps(m) + "\n"


def build_status_ack(name: str, sec: bool, up: int, appr: int, deny: int) -> str:
    data = {"name": name, "sec": sec, "sys": {"up": up},
            "stats": {"appr": appr, "deny": deny}}
    return json.dumps({"ack": "status", "ok": True, "data": data}) + "\n"
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/test_protocol.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add companion/protocol.py tests/test_protocol.py
git commit -m "feat: protocol parse + permission/ack/status builders with tests"
```

---

### Task 1.2: `state.py` — AppState + Prompt-State-Machine + Rearm (TDD)

**Files:**
- Create: `companion/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces `class AppState` mit Feldern `total, running, waiting, msg, entries, tokens, tokens_today, prompt (dict|None), owner, name, appr, deny, connected, secure` und Methoden:
  - `apply_snapshot(self, msg: dict, now: float) -> None`
  - `record_decision(self, decision: str, now: float) -> None`  (`"once"`→`appr+=1`, `"deny"`→`deny+=1`, setzt `response_sent`)
  - `in_prompt(self) -> bool`  (Prompt vorhanden UND noch nicht beantwortet)
  - `should_rearm(self, now: float, timeout: float = 4.0) -> bool`
  - `rearm(self) -> None`  (setzt `response_sent=False`)
  - `connection_state(self, now: float) -> str`  (`"disconnected"|"waiting"|"running"|"idle"`)
  - `set_owner(self, name: str) -> None`, `set_name(self, name: str) -> None`
  - `prompt_id(self) -> str`

- [ ] **Step 1: Failing test schreiben**

```python
# tests/test_state.py
from companion.state import AppState


def snap(**kw):
    base = {"total": 0, "running": 0, "waiting": 0}
    base.update(kw)
    return base


def test_apply_snapshot_updates_sessions():
    s = AppState()
    s.apply_snapshot(snap(total=3, running=1, waiting=1), now=100.0)
    assert (s.total, s.running, s.waiting) == (3, 1, 1)


def test_new_prompt_arms_and_resets_response():
    s = AppState()
    s.apply_snapshot(snap(waiting=1, prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    assert s.in_prompt() is True
    assert s.prompt_id() == "req1"


def test_record_decision_latches_and_counts():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("once", now=11.0)
    assert s.in_prompt() is False       # geantwortet → nicht mehr aktiv
    assert s.appr == 1 and s.deny == 0


def test_same_prompt_persists_does_not_rearm_response():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("once", now=11.0)
    # gleicher Prompt kommt im nächsten Snapshot nochmal (Entscheidung noch nicht verarbeitet)
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=12.0)
    assert s.in_prompt() is False       # response_sent bleibt, kein Doppel-Senden


def test_new_prompt_id_rearms():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("deny", now=11.0)
    s.apply_snapshot(snap(prompt={"id": "req2", "tool": "Write", "hint": "x"}), now=12.0)
    assert s.in_prompt() is True and s.deny == 1


def test_should_rearm_after_timeout():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("once", now=11.0)
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=12.0)
    assert s.should_rearm(now=14.0, timeout=4.0) is False   # 3s seit Entscheidung
    assert s.should_rearm(now=15.5, timeout=4.0) is True    # 4.5s → re-armen
    s.rearm()
    assert s.in_prompt() is True


def test_connection_state_disconnected_without_snapshot():
    s = AppState()
    assert s.connection_state(now=0.0) == "disconnected"


def test_connection_state_timeout():
    s = AppState()
    s.apply_snapshot(snap(total=1, running=1), now=100.0)
    assert s.connection_state(now=120.0) == "running"
    assert s.connection_state(now=131.0) == "disconnected"   # >30s ohne Snapshot


def test_connection_state_waiting_beats_running():
    s = AppState()
    s.apply_snapshot(snap(total=2, running=1, waiting=1,
                          prompt={"id": "r", "tool": "Bash", "hint": "x"}), now=100.0)
    assert s.connection_state(now=101.0) == "waiting"


def test_connection_state_idle_when_empty():
    s = AppState()
    s.apply_snapshot(snap(total=0, running=0, waiting=0), now=100.0)
    assert s.connection_state(now=101.0) == "idle"
```

- [ ] **Step 2: Run → FAIL**

Run: `pytest tests/test_state.py -v`
Expected: FAIL (`ModuleNotFoundError: companion.state`).

- [ ] **Step 3: `state.py` implementieren**

```python
# companion/state.py
"""App-State + Prompt-State-Machine. Reine Logik; Zeit wird als `now` (float s) injiziert."""

TIMEOUT_S = 30.0  # kein Snapshot länger → disconnected


class AppState:
    def __init__(self) -> None:
        self.total = 0
        self.running = 0
        self.waiting = 0
        self.msg = ""
        self.entries: list[str] = []
        self.tokens = 0
        self.tokens_today = 0
        self.prompt: dict | None = None
        self.owner = ""
        self.name = "Claude-uConsole"
        self.appr = 0
        self.deny = 0
        self.connected = False
        self.secure = False
        # interne State-Machine
        self._last_prompt_id = ""
        self._response_sent = False
        self._prompt_arrived = 0.0
        self._decision_sent = 0.0
        self._last_snapshot: float | None = None

    def apply_snapshot(self, msg: dict, now: float) -> None:
        self.total = msg.get("total", 0)
        self.running = msg.get("running", 0)
        self.waiting = msg.get("waiting", 0)
        self.msg = msg.get("msg", "")
        self.entries = msg.get("entries", [])
        self.tokens = msg.get("tokens", self.tokens)
        self.tokens_today = msg.get("tokens_today", self.tokens_today)
        self.prompt = msg.get("prompt")  # dict oder None
        new_id = self.prompt["id"] if self.prompt else ""
        if new_id != self._last_prompt_id:
            self._last_prompt_id = new_id
            self._response_sent = False
            if new_id:
                self._prompt_arrived = now
        self._last_snapshot = now

    def record_decision(self, decision: str, now: float) -> None:
        self._response_sent = True
        self._decision_sent = now
        if decision == "once":
            self.appr += 1
        elif decision == "deny":
            self.deny += 1

    def in_prompt(self) -> bool:
        return bool(self.prompt) and not self._response_sent

    def should_rearm(self, now: float, timeout: float = 4.0) -> bool:
        return (self._response_sent and bool(self.prompt)
                and (now - self._decision_sent) > timeout)

    def rearm(self) -> None:
        self._response_sent = False

    def connection_state(self, now: float) -> str:
        if self._last_snapshot is None or (now - self._last_snapshot) > TIMEOUT_S:
            return "disconnected"
        if self.prompt:
            return "waiting"
        if self.running > 0:
            return "running"
        return "idle"

    def set_owner(self, name: str) -> None:
        self.owner = name

    def set_name(self, name: str) -> None:
        self.name = name

    def prompt_id(self) -> str:
        return self.prompt["id"] if self.prompt else ""
```

- [ ] **Step 4: Run → PASS**

Run: `pytest tests/test_state.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add companion/state.py tests/test_state.py
git commit -m "feat: AppState with prompt state machine, rearm safety net, connection state"
```

---

### Task 1.3: `ui.py` — Textual-Skeleton (Status-Panel + Freigabe-Overlay)

**Files:**
- Create: `companion/ui.py`

**Interfaces:**
- Consumes: `AppState` (liest Felder + `connection_state`, `in_prompt`, `prompt`).
- Produces:
  - `class CompanionApp(App)` (Textual) mit `render_from_state(self, state: AppState, now: float) -> None` das die Panels aktualisiert.
  - Keybindings: `y`/`enter` → ruft `self.on_decision("once")`, `n`/`escape` → `self.on_decision("deny")`, `q` → beenden. `on_decision` ist ein injizierter Callback `Callable[[str], None]` (von `main.py` gesetzt).
  - Freigabe-Overlay ist nur sichtbar, wenn `state.in_prompt()`.

- [ ] **Step 1: `ui.py` implementieren**

```python
# companion/ui.py
"""Textual-Fenster-App: Status-Panels + Freigabe-Overlay. Layout aus Spec §7."""
from typing import Callable

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical

from .state import AppState


class CompanionApp(App):
    CSS = """
    #overlay { display: none; border: heavy $warning; padding: 1; }
    #overlay.active { display: block; }
    #status { padding: 1; }
    """
    BINDINGS = [
        ("y,enter", "approve", "erlauben"),
        ("n,escape", "deny", "ablehnen"),
        ("q", "quit", "beenden"),
    ]

    def __init__(self, on_decision: Callable[[str], None]):
        super().__init__()
        self._on_decision = on_decision
        self._state: AppState | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="status")
            yield Static("", id="overlay")

    def render_from_state(self, state: AppState, now: float) -> None:
        self._state = state
        conn = state.connection_state(now)
        lock = "🔒" if state.secure else ""
        lines = state.entries[:3]
        body = (
            f"● {conn} {lock}   Owner: {state.owner or '—'}\n"
            f"Sessions: total {state.total}  running {state.running}  waiting {state.waiting}\n"
            f"» {state.msg}\n"
            f"— letzte Zeilen —\n" + "\n".join(lines) + "\n"
            f"session {state.tokens/1000:.1f}k  today {state.tokens_today/1000:.1f}k  "
            f"✓{state.appr} ✗{state.deny}"
        )
        self.query_one("#status", Static).update(body)

        overlay = self.query_one("#overlay", Static)
        if state.in_prompt() and state.prompt:
            overlay.update(
                f"⚠ FREIGABE\nTool: {state.prompt.get('tool','')}\n"
                f"{state.prompt.get('hint','')}\n\n[Y] einmal erlauben   [N] ablehnen"
            )
            overlay.add_class("active")
        else:
            overlay.remove_class("active")

    def action_approve(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("once")

    def action_deny(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("deny")
```

- [ ] **Step 2: Visuelle Rauch-Prüfung (ohne BLE)**

Temporär ein Mini-Skript zum Rendern mit Fake-State (nicht committen):
```bash
python - <<'PY'
import asyncio
from companion.ui import CompanionApp
from companion.state import AppState
s = AppState()
s.apply_snapshot({"total":3,"running":1,"waiting":1,"msg":"approve: Bash",
                  "entries":["10:42 git push","10:41 yarn test"],"tokens":184500,
                  "tokens_today":31200,
                  "prompt":{"id":"r1","tool":"Bash","hint":"rm -rf /tmp/foo"}}, now=100.0)
app = CompanionApp(on_decision=lambda d: print("decision", d))
async def drive():
    async with app.run_test() as pilot:
        app.render_from_state(s, now=101.0)
        await pilot.pause()
        assert app.query_one("#overlay").has_class("active")
        print("overlay active OK")
asyncio.run(drive())
PY
```
Expected: `overlay active OK` (Textual `run_test`-Harness bestätigt, dass das Overlay bei aktivem Prompt sichtbar ist). Danach einmal echt starten (`python -m companion.ui` ist noch nicht verdrahtet — das kommt in 1.4).

- [ ] **Step 3: Commit**

```bash
git add companion/ui.py
git commit -m "feat(ui): textual status panel + approval overlay + keybindings"
```

---

### Task 1.4: `main.py` — Verdrahtung (→ funktionsfähig)

**Files:**
- Modify: `companion/main.py` (Phase-0-Version komplett ersetzen)

**Interfaces:**
- Consumes: `NusPeripheral`, `AppState`, `CompanionApp`, `protocol.*`.
- Produces: lauffähige App. RX-Zeile → `parse_message` → Routing:
  - Snapshot (hat `total`) → `state.apply_snapshot` → UI neu rendern.
  - `evt=="turn"` → optional letzte Antwort in UI (nicht kritisch; hier ignorieren, >4KB verwerfen macht der Mac).
  - `{"time":[epoch,off]}` → Uhr setzen (kein Ack).
  - `{"cmd":"owner","name":…}` → `state.set_owner` + `build_ack("owner")`.
  - `{"cmd":"name","name":…}` → `state.set_name` + `build_ack("name")`.
  - `{"cmd":"status"}` → `build_status_ack(name, secure, up, appr, deny)`.
  - `{"cmd":"unpair"}` → (Phase 1: Bonds gibt's noch nicht) `build_ack("unpair")`.
  - `char_begin`/`file`/`chunk`/… → **nicht** acken (Folder-Push).
  - Tastendruck Y/N → `build_permission` senden + `state.record_decision`.
  - Periodischer Tick (1 Hz): `should_rearm` prüfen → `rearm()`; UI mit aktueller `now` neu rendern (für Disconnect-Timeout-Anzeige).

- [ ] **Step 1: `main.py` neu schreiben**

```python
# companion/main.py
import asyncio
import logging
import time

from .ble_nus import NusPeripheral
from .state import AppState
from .ui import CompanionApp
from .protocol import parse_message, build_permission, build_ack, build_status_ack

logging.basicConfig(filename="companion.log", level=logging.INFO,
                    format="%(asctime)s %(message)s")
log = logging.getLogger("companion")

BOOT = time.monotonic()


class Companion:
    def __init__(self) -> None:
        self.state = AppState()
        self.ble = NusPeripheral("Claude-uConsole", self._on_line)
        self.app = CompanionApp(on_decision=self._on_decision)
        self._send_q: asyncio.Queue[str] = asyncio.Queue()

    # ---- RX ----
    def _on_line(self, line: str) -> None:
        log.info("RX %s", line)
        msg = parse_message(line)
        if msg is None:
            return
        if "total" in msg:                      # Heartbeat-Snapshot
            self.state.apply_snapshot(msg, now=time.monotonic())
            self._rerender()
        elif msg.get("evt") == "turn":
            pass                                # nicht kritisch
        elif "time" in msg:
            pass                                # Uhr: OS-Zeit reicht in Phase 1
        elif msg.get("cmd") == "owner":
            self.state.set_owner(msg.get("name", "")); self._reply(build_ack("owner"))
        elif msg.get("cmd") == "name":
            self.state.set_name(msg.get("name", "")); self._reply(build_ack("name"))
        elif msg.get("cmd") == "status":
            up = int(time.monotonic() - BOOT)
            self._reply(build_status_ack(self.state.name, self.state.secure, up,
                                         self.state.appr, self.state.deny))
        elif msg.get("cmd") == "unpair":
            self._reply(build_ack("unpair"))
        # Folder-Push (char_begin/file/chunk/file_end/char_end): bewusst NICHT acken.

    # ---- TX ----
    def _reply(self, line: str) -> None:
        self._send_q.put_nowait(line)

    def _on_decision(self, decision: str) -> None:
        pid = self.state.prompt_id()
        if not pid:
            return
        self._reply(build_permission(pid, decision))
        self.state.record_decision(decision, now=time.monotonic())
        log.info("TX permission %s %s", pid, decision)
        self._rerender()

    def _rerender(self) -> None:
        self.app.render_from_state(self.state, now=time.monotonic())

    # ---- Loops ----
    async def _tx_loop(self) -> None:
        while True:
            line = await self._send_q.get()
            await self.ble.send_line(line)
            log.info("TX %s", line.strip())

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            if self.state.should_rearm(now):
                self.state.rearm()
                log.info("rearm: keine Bestätigung, Buttons wieder scharf")
            self._rerender()

    async def run(self) -> None:
        await self.ble.start()
        log.info("advertising as Claude-uConsole")
        asyncio.create_task(self._tx_loop())
        asyncio.create_task(self._tick_loop())
        await self.app.run_async()


def main() -> None:
    asyncio.run(Companion().run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Regressions-Check — alle Unit-Tests grün**

Run: `pytest -q`
Expected: alle Tests (framing + protocol + state) passed.

- [ ] **Step 3: Hardware-Integrationstest — der echte Loop**

1. uConsole: `python -m companion.main` (Textual-Fenster geht auf).
2. Mac: Hardware Buddy → Connect → `Claude-uConsole`. Status-Panel sollte sich mit `● running/idle` füllen, Owner erscheint nach Owner-One-Shot.
3. Mac: eine **Claude-Code-Session** starten und einen **nicht-allowlisteten** Befehl auslösen, z.B. Claude bitten `ls /tmp` per Bash zu laufen → Freigabe-Prompt entsteht und **parkt**.
4. uConsole-TUI: Overlay „⚠ FREIGABE — Tool: Bash" erscheint. **`Y` drücken** → Claude Code fährt fort (Befehl läuft). **Gegenprobe:** neuen Prompt auslösen, **`N`** → Claude Code meldet Ablehnung.
5. `companion.log` prüfen: `TX permission req_… once/deny` steht drin, danach Snapshot ohne `prompt`.
6. **Sicherheitsnetz testen:** während ein Prompt aktiv ist, kurz BLE stören (Mac-BT aus/an) direkt nach `Y` → nach ~4 s sollte das Log `rearm: …` zeigen und die Buttons wieder scharf sein.

Expected: approve/deny steuern echte Claude-Freigaben. **Ab hier ist die App funktionsfähig (Spec Phase 1 erreicht).**

- [ ] **Step 4: Commit**

```bash
git add companion/main.py
git commit -m "feat: wire BLE+state+UI into working companion (approve/deny live)"
```

---

# PHASE 2 — Voll (Tokens, Stats, letzte Zeilen)

### Task 2.1: Tokens + `appr`/`deny`-Stats + letzte Zeilen ausbauen

**Files:**
- Modify: `companion/ui.py` (Token-/Stats-/Zeilen-Panel schärfen)
- (State + Status-Ack tragen `appr`/`deny` bereits — nur UI-Feinschliff.)

**Interfaces:**
- Consumes: `AppState.tokens`, `tokens_today`, `appr`, `deny`, `entries`.
- Produces: klar lesbares Token-/Stats-Panel; letzte Zeilen mit Zeitstempel wie im Spec §7.

- [ ] **Step 1: Token-Formatierung als testbare Pure-Funktion auslagern**

In `companion/ui.py` oben ergänzen:
```python
def fmt_tokens(v: int) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1000:.1f}k"
    return str(v)
```

- [ ] **Step 2: Failing test für `fmt_tokens`**

```python
# tests/test_protocol.py  (ans Ende anhängen)
from companion.ui import fmt_tokens

def test_fmt_tokens():
    assert fmt_tokens(950) == "950"
    assert fmt_tokens(31200) == "31.2k"
    assert fmt_tokens(1_840_000) == "1.8M"
```

- [ ] **Step 3: Run → PASS**

Run: `pytest tests/test_protocol.py::test_fmt_tokens -v`
Expected: PASS.

- [ ] **Step 4: `render_from_state` auf `fmt_tokens` umstellen**

In `render_from_state` die Token-Zeile ersetzen:
```python
            f"session {fmt_tokens(state.tokens)}  today {fmt_tokens(state.tokens_today)}  "
            f"✓{state.appr} ✗{state.deny}"
```

- [ ] **Step 5: Hardware-Verifikation**

Mit laufender Session prüfen: Tokens steigen, `✓/✗` zählen bei jedem approve/deny hoch. Mac-Stats-Panel im Hardware Buddy zeigt `appr`/`deny` (kommt aus unserem Status-Ack).

Expected: Zahlen plausibel + Status-Ack liefert Stats an den Mac.

- [ ] **Step 6: Commit**

```bash
git add companion/ui.py tests/test_protocol.py
git commit -m "feat(ui): token/stats formatting + last lines panel"
```

---

# PHASE 3 — Härten & Autostart

### Task 3.1: `agent.py` — LE-Secure-Bonding (DisplayOnly-Passkey)

**Files:**
- Create: `companion/agent.py`
- Modify: `companion/ble_nus.py` (NUS-Chars + CCCD encrypted-only markieren; `secure`-Flag setzen)
- Modify: `companion/main.py` (Passkey in UI zeigen; `unpair` löscht echte Bonds)

**Interfaces:**
- Produces:
  - `class PairingAgent` (dbus-fast) mit Capability `DisplayOnly`, implementiert `DisplayPasskey(device, passkey, entered)` → ruft injizierten Callback `on_passkey(passkey: int)`; `RequestConfirmation`/`AuthorizeService` auto-akzeptieren.
  - `async def register_agent(bus, on_passkey) -> None` — Agent bei `org.bluez.AgentManager1` registrieren (`RequestDefaultAgent`).

> **Korrektur 19.07. — `dbus_next` statt `dbus_fast`:** `bluez-peripheral` 0.1.7 nutzt `dbus_next`. Damit der Agent auf DEMSELBEN System-Bus wie das NUS-Peripheral läuft, `agent.py` gegen `dbus_next` schreiben (`from dbus_next.service import ServiceInterface, method`, `from dbus_next.aio import MessageBus`) und den Bus über `bluez_peripheral.util.get_message_bus()` teilen — NICHT einen zweiten `dbus_fast`-Bus aufmachen. Der Code unten ist das Muster; Import-Zeilen entsprechend auf `dbus_next` umstellen und beim Bau gegen die installierte `dbus_next`-API verifizieren (Methoden-Signaturen/Typannotationen `"o"`/`"u"`/`"q"`/`"s"` sind in beiden Libs gleich).

- [ ] **Step 1: `agent.py` implementieren**

```python
# companion/agent.py
"""BlueZ-Pairing-Agent (DisplayOnly) via dbus_next. Zeigt 6-stelligen Passkey an."""
from typing import Callable
from dbus_next.service import ServiceInterface, method
from dbus_next.aio import MessageBus

AGENT_PATH = "/com/uconsole/agent"


class PairingAgent(ServiceInterface):
    def __init__(self, on_passkey: Callable[[int], None]):
        super().__init__("org.bluez.Agent1")
        self._on_passkey = on_passkey

    @method()
    def Release(self):  # noqa: N802
        pass

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: N802,F821
        self._on_passkey(int(passkey))

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: N802,F821
        return  # akzeptieren

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: N802,F821
        return  # akzeptieren

    @method()
    def Cancel(self):  # noqa: N802
        pass


async def register_agent(bus: MessageBus, on_passkey: Callable[[int], None]) -> None:
    agent = PairingAgent(on_passkey)
    bus.export(AGENT_PATH, agent)
    introspection = await bus.introspect("org.bluez", "/org/bluez")
    obj = bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
    mgr = obj.get_interface("org.bluez.AgentManager1")
    await mgr.call_register_agent(AGENT_PATH, "DisplayOnly")
    await mgr.call_request_default_agent(AGENT_PATH)
```

- [ ] **Step 2: `ble_nus.py` — Characteristics encrypted-only + secure-Flag**

Die NUS-Char-Flags um Encryption erweitern (RX/TX + CCCD):
```python
    @characteristic(NUS_TX, Flags.NOTIFY | Flags.ENCRYPT_READ)
    ...
    @characteristic(NUS_RX, Flags.WRITE | Flags.ENCRYPT_WRITE)
```
und eine `secure`-Property, die `main` lesen kann (in Phase 1 immer False). Bei erfolgreichem Pairing (Agent-Callback in `main`) `state.secure = True` setzen.

> Falls die installierte `bluez-peripheral`-Version keine `ENCRYPT_*`-Flags kennt: Characteristics über rohes `dbus-fast` mit Flags `encrypt-read`/`encrypt-write`/`encrypt-notify` registrieren (BlueZ-`example-gatt-server`-Muster). Dies ist der im Spec §12 markierte Verifikationspunkt.

- [ ] **Step 3: `main.py` — Passkey anzeigen + Agent registrieren**

In `Companion.run()` vor `self.app.run_async()`:
```python
        from .agent import register_agent
        await register_agent(self.ble._bus, self._on_passkey)
```
und Methode:
```python
    def _on_passkey(self, passkey: int) -> None:
        log.info("passkey %06d", passkey)
        self.app.query_one("#status").update(f"🔒 PAIRING — Passkey am Mac eingeben:\n\n    {passkey:06d}")
```

- [ ] **Step 4: Hardware-Verifikation — echtes Pairing**

1. Bestehende Bonds beidseitig löschen (uConsole `bluetoothctl remove <MacAddr>`; Mac: Hardware Buddy „Forget").
2. `python -m companion.main`, am Mac neu verbinden.
3. Erwartet: uConsole zeigt 6-stelligen Passkey, macOS fragt danach → eingeben → Link wird verschlüsselt.
4. Status-Ack sollte jetzt `sec:true` melden (im `companion.log` nach `status`-Poll sichtbar); TUI zeigt 🔒.
5. `unpair`-Pfad testen: Mac „Forget" → prüfen, dass Reconnect erneut Pairing verlangt.

Expected: verschlüsselter Link, `sec:true`, Passkey-Flow funktioniert.

- [ ] **Step 5: Commit**

```bash
git add companion/agent.py companion/ble_nus.py companion/main.py
git commit -m "feat(security): LE Secure Connections bonding with DisplayOnly passkey"
```

---

### Task 3.2: Autostart als Desktop-App

**Files:**
- Create: `~/.config/autostart/claude-companion.desktop`
- Create: `~/Documents/web/uconsole-companion/run.sh`

**Interfaces:**
- Produces: App startet beim Desktop-Login automatisch in einem Terminal-Fenster.

- [ ] **Step 1: `run.sh` schreiben**

```bash
#!/usr/bin/env bash
cd "$HOME/Documents/web/uconsole-companion"
source .venv/bin/activate
exec python -m companion.main
```
```bash
chmod +x ~/Documents/web/uconsole-companion/run.sh
```

- [ ] **Step 2: Terminal-Emulator prüfen**

```bash
which lxterminal xterm x-terminal-emulator 2>/dev/null
```
Erwartet: mindestens einer existiert. Den vorhandenen im nächsten Step verwenden (Beispiel nutzt `lxterminal`).

- [ ] **Step 3: `.desktop`-Autostart schreiben**

```ini
# ~/.config/autostart/claude-companion.desktop
[Desktop Entry]
Type=Application
Name=Claude Companion
Exec=lxterminal -e /home/nikolai/Documents/web/uconsole-companion/run.sh
X-GNOME-Autostart-enabled=true
Terminal=false
```

- [ ] **Step 4: Verifikation — Reboot**

```bash
sudo reboot
```
Nach dem Hochfahren: Terminal-Fenster mit laufender Companion-App ist offen, advertised `Claude-uConsole`. Mac reconnectet automatisch (LTK wiederverwendet, kein erneutes Pairing).

Expected: App läuft nach Boot ohne manuelles Eingreifen.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/web/uconsole-companion
cp ~/.config/autostart/claude-companion.desktop ./claude-companion.desktop  # Kopie ins Repo (Doku)
git add run.sh claude-companion.desktop
git commit -m "feat: desktop autostart entry"
```

---

## Self-Review (gegen den Spec)

- **Spec §4 BLE-Transport** → Task 0.3 (UUIDs, Framing), Global Constraints. ✅
- **Spec §5.1 Mac→Gerät** (Snapshot, turn, time, owner) → Task 1.2 (apply_snapshot), Task 1.4 (Routing). ✅
- **Spec §5.2 Gerät→Mac** (permission, acks, status-ack) → Task 1.1 (builder), Task 1.4 (Dispatch). ✅
- **Spec §6 Funktionsumfang** (Control / Status / Tokens+Stats) → Task 1.3/1.4 (Control+Status), Task 2.1 (Tokens+Stats). ✅
- **Spec §7 TUI-Layout** → Task 1.3, 2.1. ✅
- **Spec §8 Zustände + Delivery-Sicherheitsnetz** → Task 1.2 (connection_state, should_rearm/rearm), Task 1.4 (tick). ✅
- **Spec §10 Phasen** → Phase 0/1/2/3 dieses Plans. ✅
- **Spec §11 Sicherheit** → Task 3.1. ✅
- **Spec §12 offene Punkte** → hci0-Pinning (0.3 Hinweis), bluez-peripheral-Agent-Risiko (3.1 Hinweis auf dbus-fast), Textual-Perf (1.3 Rauch-Prüfung + 1.4 echt), Autostart (3.2). ✅
- **Folder-Push nicht acken** → Global Constraints + Task 1.4. ✅
- **Scope-Trims** → keine Tasks für GIF/vel-nap-lvl/bat/Folder-Push (bewusst). ✅

Kein Platzhalter, keine offenen TODOs. Typkonsistenz: `on_decision`/`record_decision`/`build_permission`/`prompt_id`/`should_rearm`/`rearm` durchgängig gleich benannt in Tasks 1.1–1.4.
