---
tags: [projekt, uconsole, claude, ble, maker, claude-code, hooks, plan]
status: bereit
created: 2026-07-19
source: marvin-session
sprache: Python
spec: "[[Claude Companion Bridge (Terminal) - Spec]]"
device-repo: "~/Documents/web/uconsole-companion (auf dem Gerät)"
---

# Claude Companion Bridge (Terminal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mac-seitige Bridge, die den Terminal-`claude` (Claude Code CLI) über einen `PreToolUse`-Hook + persistenten BLE-Daemon ans uConsole-Companion-Gerät anschließt: Tool-Freigaben erscheinen als Overlay auf der uConsole und werden per Y/N-Knopf entschieden.

**Architecture:** Dünne Hook-Scripts (zustandslos) reden über einen Unix-Domain-Socket mit einem langlaufenden Daemon (Python + bleak, BLE-**Central**), der die Verbindung zum uConsole-**Peripheral** hält. Reine Logik (Framing, Snapshot/permission-Protokoll, Approval-Arbitrierung) ist BLE-frei und unit-getestet; BLE + Hooks werden gegen echte Hardware verifiziert. Die uConsole-Firmware bleibt unverändert.

**Tech Stack:** Python 3.11+ (Mac hat 3.14), asyncio, `bleak` (BLE-Central), `pytest`. Ziel: macOS.

## Global Constraints

- **uConsole-Firmware NICHT anfassen.** Nur Mac-Seite. Gerät = Peripheral `Claude-uConsole`, hci0 `2C:CF:67:FE:1E:1D`.
- **NUS-UUIDs verbatim:** Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`; aus **Central-Sicht**: **RX = `6e400002-…` → hier WRITE** (Snapshot an Gerät), **TX = `6e400003-…` → hier SUBSCRIBE/NOTIFY** (permission vom Gerät).
- **Framing:** UTF-8 JSON, ein Objekt pro Zeile, `\n`-terminiert. RX-Writes chunken auf `min(mtu-3, 180)`.
- **Permission-Mapping:** Gerät sendet `decision: "once"|"deny"`. Bridge mappt `once→allow`, `deny→deny`, alles andere/nichts → **`ask`**.
- **Fail-safe = `ask`:** Daemon nicht erreichbar / BLE tot / Timeout ~100s → Hook gibt `permissionDecision: "ask"` (nativer Terminal-Prompt), **nie** stilles `allow`.
- **PreToolUse-stdout-Contract (Claude Code v2.1.210+):** `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"|"deny"|"ask","permissionDecisionReason":"…"}}`, Exit 0.
- **v1-Matcher = nur `Bash`.** Hook-`timeout` in settings.json = **120**.
- **Repo:** `~/Documents/web/uconsole-companion-bridge/` (getrennt vom Device-Repo).
- **Socket:** Unix-Domain-Socket unter `$HOME/Documents/web/uconsole-companion-bridge/.run/bridge.sock`, Dir `0700`.

---

## File Structure

```
uconsole-companion-bridge/
├── README.md
├── requirements.txt
├── pyproject.toml
├── settings-snippet.json
├── bridge/
│   ├── __init__.py
│   ├── framing.py        # LineReassembler + chunk_for_mtu (Kopie vom Device, pur)
│   ├── protocol.py       # build_snapshot/prompt/cleared, parse_permission, decision-mapping, hook-output — pur
│   ├── ble_central.py    # bleak-Central: connect/subscribe/send_line, reconnect
│   ├── daemon.py         # Bridge-Kern (arbitrierung) + Unix-Socket-Server + BLE-Verdrahtung
│   └── hooks/
│       ├── pretooluse.py # dünn: stdin→daemon→PreToolUse-JSON, fail-safe ask
│       ├── notify.py     # dünn: status-event (P2)
│       ├── session.py    # dünn: status-event (P2)
│       └── stop.py       # dünn: status-event (P2)
└── tests/
    ├── test_framing.py
    ├── test_protocol.py
    └── test_daemon.py
```

---

# PHASE 0 — Daemon-BLE-Kern (produktive fake_central)

### Task 0.1: Repo + Environment-Scaffold (Mac)

**Files:**
- Create: `~/Documents/web/uconsole-companion-bridge/{README.md,requirements.txt,pyproject.toml,.gitignore}`
- Create: `bridge/__init__.py`, `bridge/hooks/__init__.py`

**Interfaces:**
- Produces: Repo mit venv, in dem `bleak` + `pytest` importierbar sind; bare `pytest` findet das Repo-Root.

- [ ] **Step 1: Repo + venv**
```bash
mkdir -p ~/Documents/web/uconsole-companion-bridge/{bridge/hooks,tests,.run}
cd ~/Documents/web/uconsole-companion-bridge
chmod 700 .run
git init
python3 -m venv .venv
source .venv/bin/activate
python --version   # >= 3.11 (Mac: 3.14)
```

- [ ] **Step 2: `requirements.txt`**
```
bleak>=0.22
pytest>=8.0
```

- [ ] **Step 3: `pyproject.toml`**
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 4: `.gitignore`**
```
.venv/
__pycache__/
*.pyc
.run/
bridge.log
```

- [ ] **Step 5: leere `__init__.py`**
```bash
: > bridge/__init__.py; : > bridge/hooks/__init__.py
```

- [ ] **Step 6: Install + Verify**
```bash
pip install -r requirements.txt
python -c "import bleak; print('bleak OK')"
```
Expected: `bleak OK`.

- [ ] **Step 7: `README.md`**
```markdown
# uConsole Claude Companion — Bridge (Terminal)

Verbindet Claude Code (Terminal) via PreToolUse-Hook + BLE-Daemon mit der uConsole.
Gerät = Peripheral `Claude-uConsole`. Spec/Plan: Vault `Privat/Projekte/Uconsole/`.

## Start
    source .venv/bin/activate
    python -m bridge.daemon        # Daemon (hält BLE + Socket)
    pytest -q                      # Pure-Logic-Tests
```

- [ ] **Step 8: Commit**
```bash
git add -A && git commit -m "chore: scaffold bridge repo + deps"
```

---

### Task 0.2: `framing.py` (TDD)

**Files:** Create `bridge/framing.py`; Test `tests/test_framing.py`

**Interfaces:**
- `class LineReassembler(max_len=8192)` → `feed(data: bytes) -> list[str]`
- `def chunk_for_mtu(data: bytes, mtu: int) -> list[bytes]` (Chunk = `min(mtu-3,180)`, 20 wenn `mtu<=3`)

- [ ] **Step 1: Failing test**
```python
# tests/test_framing.py
from bridge.framing import LineReassembler, chunk_for_mtu

def test_reassembler_joins_split_line():
    r = LineReassembler()
    assert r.feed(b'{"a":') == []
    assert r.feed(b'1}\n') == ['{"a":1}']

def test_reassembler_multiple_lines():
    r = LineReassembler()
    assert r.feed(b'{"a":1}\n{"b":2}\n') == ['{"a":1}', '{"b":2}']

def test_reassembler_drops_overlong():
    r = LineReassembler(max_len=16)
    assert r.feed(b'x'*32) == []
    assert r.feed(b'{"a":1}\n') == ['{"a":1}']

def test_chunk_caps_at_180():
    chunks = chunk_for_mtu(b'z'*400, mtu=185)
    assert all(len(c) <= 180 for c in chunks)
    assert b''.join(chunks) == b'z'*400

def test_chunk_tiny_mtu():
    chunks = chunk_for_mtu(b'z'*50, mtu=23)
    assert max(len(c) for c in chunks) == 20
    assert b''.join(chunks) == b'z'*50
```

- [ ] **Step 2: Run → FAIL** — `pytest tests/test_framing.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement**
```python
# bridge/framing.py
"""Byte-Framing für Nordic-UART. Reine Logik, keine BLE-Deps. (Kopie vom Device-Repo.)"""

class LineReassembler:
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
                pass
        if len(self._buf) > self.max_len:
            self._buf.clear()
        return lines


def chunk_for_mtu(data: bytes, mtu: int) -> list[bytes]:
    size = mtu - 3 if mtu > 3 else 20
    if size > 180:
        size = 180
    return [data[i : i + size] for i in range(0, len(data), size)]
```

- [ ] **Step 4: Run → PASS** — `pytest tests/test_framing.py -v` → 5 passed.

- [ ] **Step 5: Commit**
```bash
git add bridge/framing.py tests/test_framing.py && git commit -m "feat: framing (reassembler + chunker) with tests"
```

---

### Task 0.3: `protocol.py` (TDD)

**Files:** Create `bridge/protocol.py`; Test `tests/test_protocol.py`

**Interfaces:**
- `def build_snapshot(*, total=1, running=0, waiting=0, msg="", prompt=None, tokens=0, tokens_today=0, entries=None) -> str` — JSON-Zeile + `\n`; `prompt` = None oder `{"id","tool","hint"}`.
- `def build_prompt_snapshot(prompt_id, tool, hint) -> str` — `waiting=1` + prompt, `msg=f"approve: {tool}"`.
- `def build_cleared_snapshot() -> str` — `waiting=0`, kein prompt, `msg="idle"`.
- `def parse_permission(line: str) -> dict | None` — `{"id","decision"}` oder None.
- `def decision_to_hook(decision: str | None) -> str` — `once→allow`, `deny→deny`, sonst `ask`.
- `def hook_pretooluse_output(permission_decision: str, reason: str = "") -> str` — PreToolUse-stdout-JSON (ohne Newline).

- [ ] **Step 1: Failing test**
```python
# tests/test_protocol.py
import json
from bridge.protocol import (
    build_snapshot, build_prompt_snapshot, build_cleared_snapshot,
    parse_permission, decision_to_hook, hook_pretooluse_output,
)

def test_build_snapshot_defaults():
    m = json.loads(build_snapshot())
    assert m["total"] == 1 and m["waiting"] == 0 and m["prompt"] is None

def test_build_prompt_snapshot():
    m = json.loads(build_prompt_snapshot("req1", "Bash", "ls /tmp"))
    assert m["waiting"] == 1
    assert m["prompt"] == {"id": "req1", "tool": "Bash", "hint": "ls /tmp"}
    assert m["msg"] == "approve: Bash"

def test_build_cleared():
    m = json.loads(build_cleared_snapshot())
    assert m["waiting"] == 0 and m["prompt"] is None

def test_snapshot_newline_terminated():
    assert build_snapshot().endswith("\n")

def test_parse_permission_valid():
    assert parse_permission('{"cmd":"permission","id":"r1","decision":"once"}') == {"id": "r1", "decision": "once"}

def test_parse_permission_ignores_other():
    assert parse_permission('{"cmd":"status"}') is None
    assert parse_permission("garbage") is None

def test_decision_mapping():
    assert decision_to_hook("once") == "allow"
    assert decision_to_hook("deny") == "deny"
    assert decision_to_hook(None) == "ask"
    assert decision_to_hook("weird") == "ask"

def test_hook_output_shape():
    m = json.loads(hook_pretooluse_output("allow", "ok"))
    assert m["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert m["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert m["hookSpecificOutput"]["permissionDecisionReason"] == "ok"
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement**
```python
# bridge/protocol.py
"""Central-seitiges JSON-Protokoll: Snapshots bauen, permission parsen, Hook-Output. Rein."""
import json


def build_snapshot(*, total=1, running=0, waiting=0, msg="", prompt=None,
                   tokens=0, tokens_today=0, entries=None) -> str:
    return json.dumps({
        "total": total, "running": running, "waiting": waiting, "msg": msg,
        "entries": entries or [], "tokens": tokens, "tokens_today": tokens_today,
        "prompt": prompt,
    }) + "\n"


def build_prompt_snapshot(prompt_id: str, tool: str, hint: str) -> str:
    return build_snapshot(total=1, running=0, waiting=1, msg=f"approve: {tool}",
                          prompt={"id": prompt_id, "tool": tool, "hint": hint})


def build_cleared_snapshot() -> str:
    return build_snapshot(total=1, running=0, waiting=0, msg="idle", prompt=None)


def parse_permission(line: str) -> dict | None:
    try:
        m = json.loads(line)
    except (ValueError, TypeError):
        return None
    if isinstance(m, dict) and m.get("cmd") == "permission" and "id" in m and "decision" in m:
        return {"id": m["id"], "decision": m["decision"]}
    return None


def decision_to_hook(decision: str | None) -> str:
    return {"once": "allow", "deny": "deny"}.get(decision, "ask")


def hook_pretooluse_output(permission_decision: str, reason: str = "") -> str:
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": permission_decision,
        "permissionDecisionReason": reason,
    }})
```

- [ ] **Step 4: Run → PASS** — 8 passed.

- [ ] **Step 5: Commit**
```bash
git add bridge/protocol.py tests/test_protocol.py && git commit -m "feat: central protocol (snapshots, permission parse, hook output) with tests"
```

---

### Task 0.4: `ble_central.py` + fake_central-PoC (Hardware-Verify)

> **✅ P0 BEWIESEN 19.07.** Voller Loop lief: PoC → Prompt an uConsole → Y gedrückt → Mac empfing `{"decision":"once"}`. Zwei Korrekturen gegenüber dem Plan-Code unten:
> 1. **Auffinden per NUS-Service-UUID, nicht per Name.** Das Gerät wirbt als `uconsole` (Adapter-Alias), nicht `Claude-uConsole` (Advertisement-LocalName wird geräteseitig nicht gesetzt). Filter jetzt: `NUS_SERVICE.lower() in [u.lower() for u in (ad.service_uuids or [])]`.
> 2. **PoC-Teardown:** nach `build_cleared_snapshot()` ein `await asyncio.sleep(0.8)` vor `disconnect()`, sonst kommt der cleared-Snapshot nicht mehr durch → auf dem Gerät bleibt der Prompt stehen und das **Rearm-Sicherheitsnetz** re-aktiviert ihn alle ~4s.
> 3. 🔧 **Device-seitiger Follow-up (Device-Repo, nicht Bridge):** Bei BLE-**Disconnect** sollte die uConsole ihren pending `prompt` clearen — sonst hängt ein Overlay + Rearm-Loop, wenn ein Central mit offenem Prompt weggeht. (Trifft den produktiven Daemon kaum — der bleibt verbunden + sendet cleared —, aber sauber wär's.)

**Files:** Create `bridge/ble_central.py`; Create throwaway `tools/poc_send_prompt.py` (nicht committen)

**Interfaces:**
- `class BleCentral(on_line: Callable[[str], None], device_name="Claude-uConsole")`
  - `async def connect(self) -> None` — nach `device_name` scannen, verbinden, TX (`6e…0003`) subscriben → Bytes → `LineReassembler` → `on_line(line)`.
  - `async def send_line(self, line: str) -> None` — an RX (`6e…0002`) schreiben, via `chunk_for_mtu` (MTU aus `client.mtu_size`, sonst 23).
  - `async def disconnect(self) -> None`

- [ ] **Step 1: Implement `ble_central.py`**
```python
# bridge/ble_central.py
"""BLE-Central (bleak): verbindet sich mit dem uConsole-Peripheral, NUS-Serial."""
import asyncio
from typing import Callable
from bleak import BleakScanner, BleakClient
from .framing import LineReassembler, chunk_for_mtu

NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # WRITE (Central → Gerät)
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # NOTIFY (Gerät → Central)


class BleCentral:
    def __init__(self, on_line: Callable[[str], None], device_name: str = "Claude-uConsole"):
        self._on_line = on_line
        self._name = device_name
        self._reasm = LineReassembler()
        self._client: BleakClient | None = None

    async def connect(self) -> None:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: (d.name or "").startswith(self._name), timeout=15.0)
        if dev is None:
            raise RuntimeError(f"{self._name} nicht gefunden")
        self._client = BleakClient(dev)
        await self._client.connect()

        def _rx(_char, data: bytearray):
            for line in self._reasm.feed(bytes(data)):
                self._on_line(line)

        await self._client.start_notify(NUS_TX, _rx)

    async def send_line(self, line: str) -> None:
        assert self._client is not None
        data = line.encode("utf-8")
        mtu = getattr(self._client, "mtu_size", 23) or 23
        for chunk in chunk_for_mtu(data, mtu):
            await self._client.write_gatt_char(NUS_RX, chunk, response=False)
            await asyncio.sleep(0.01)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
```

- [ ] **Step 2: Throwaway PoC-Script**
```python
# tools/poc_send_prompt.py  (NICHT committen)
import asyncio
from bridge.ble_central import BleCentral
from bridge.protocol import build_prompt_snapshot, build_cleared_snapshot, parse_permission

got = asyncio.Event(); result = {}

def on_line(line):
    print("FROM DEVICE:", line)
    p = parse_permission(line)
    if p:
        result.update(p); got.set()

async def main():
    ble = BleCentral(on_line)
    await ble.connect()
    print("verbunden — sende prompt")
    await ble.send_line(build_prompt_snapshot("poc1", "Bash", "rm -rf /tmp/foo"))
    print("Overlay sollte JETZT auf der uConsole sein — druecke Y oder N")
    await asyncio.wait_for(got.wait(), timeout=120)
    print("ENTSCHEIDUNG:", result)
    await ble.send_line(build_cleared_snapshot())
    await ble.disconnect()

asyncio.run(main())
```

- [ ] **Step 3: Hardware-Verify — der PoC**
1. **Hardware Buddy am Mac trennen** (nur ein Central gleichzeitig): im Hardware-Buddy-Fenster „Disconnect".
2. Sicherstellen, dass die uConsole-App läuft + advertised (`Claude-uConsole`).
3. Am Mac:
```bash
cd ~/Documents/web/uconsole-companion-bridge && source .venv/bin/activate
python tools/poc_send_prompt.py
```
4. Erwartet: macOS fragt ggf. **einmalig** nach Bluetooth-Freigabe fürs Terminal (erlauben — Systemeinstellungen → Datenschutz → Bluetooth). Dann: **⚠-Overlay klappt auf der uConsole auf** („Tool: Bash / rm -rf /tmp/foo"). **Y** drücken → Script druckt `ENTSCHEIDUNG: {'id':'poc1','decision':'once'}`. Mit **N** → `'deny'`.

Expected: der volle BLE-Loop (Prompt hin, Knopfdruck zurück) läuft — **P0-Beweis**.

- [ ] **Step 4: Commit** (nur die Lib, nicht den PoC)
```bash
git add bridge/ble_central.py && git commit -m "feat(ble): bleak central (connect/subscribe/send) — P0 proven"
```

---

# PHASE 1 — Approval end-to-end (funktionsfähig)

### Task 1.1: Bridge-Kern (Arbitrierung, TDD)

**Files:** Create `bridge/daemon.py` (nur die `Bridge`-Klasse in diesem Task); Test `tests/test_daemon.py`

**Interfaces:**
- `class Bridge(send_snapshot: Callable[[str], Awaitable[None]])`
  - `async def request_approval(self, req_id: str, tool: str, hint: str, timeout: float) -> str` — sendet Prompt-Snapshot via `send_snapshot`, registriert Future unter `req_id`, wartet; gibt `"allow"|"deny"|"ask"` (ask bei Timeout); sendet danach cleared-Snapshot.
  - `def on_ble_line(self, line: str) -> None` — bei passender `permission` (id matcht pending) → Future mit `decision_to_hook(decision)` auflösen.

- [ ] **Step 1: Failing test (async)**
```python
# tests/test_daemon.py
import asyncio
from bridge.daemon import Bridge
from bridge.protocol import parse_permission  # noqa

def run(coro): return asyncio.run(coro)

def make_bridge():
    sent = []
    async def send_snapshot(line): sent.append(line)
    return Bridge(send_snapshot), sent

def test_approval_allow():
    async def scenario():
        b, sent = make_bridge()
        task = asyncio.create_task(b.request_approval("r1", "Bash", "ls", timeout=5))
        await asyncio.sleep(0)  # request_approval sendet Prompt + registriert Future
        b.on_ble_line('{"cmd":"permission","id":"r1","decision":"once"}')
        res = await task
        assert res == "allow"
        assert any('"prompt"' in s and '"r1"' in s for s in sent)   # Prompt gesendet
        assert any('"waiting": 0' in s for s in sent)               # cleared danach
        return res
    assert run(scenario()) == "allow"

def test_approval_deny():
    async def scenario():
        b, _ = make_bridge()
        task = asyncio.create_task(b.request_approval("r2", "Bash", "x", timeout=5))
        await asyncio.sleep(0)
        b.on_ble_line('{"cmd":"permission","id":"r2","decision":"deny"}')
        return await task
    assert run(scenario()) == "deny"

def test_approval_timeout_asks():
    async def scenario():
        b, _ = make_bridge()
        return await b.request_approval("r3", "Bash", "x", timeout=0.05)  # keine Antwort
    assert run(scenario()) == "ask"

def test_stale_permission_ignored():
    async def scenario():
        b, _ = make_bridge()
        task = asyncio.create_task(b.request_approval("r4", "Bash", "x", timeout=0.2))
        await asyncio.sleep(0)
        b.on_ble_line('{"cmd":"permission","id":"OTHER","decision":"once"}')  # falsche id
        return await task
    assert run(scenario()) == "ask"   # nur die falsche id kam → Timeout → ask
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement `Bridge` in `daemon.py`**
```python
# bridge/daemon.py  (Bridge-Kern; Socket-Server folgt in Task 1.2)
import asyncio
from typing import Awaitable, Callable
from .protocol import build_prompt_snapshot, build_cleared_snapshot, parse_permission, decision_to_hook


class Bridge:
    def __init__(self, send_snapshot: Callable[[str], Awaitable[None]]):
        self._send = send_snapshot
        self._pending: dict[str, asyncio.Future] = {}

    async def request_approval(self, req_id: str, tool: str, hint: str, timeout: float) -> str:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        try:
            await self._send(build_prompt_snapshot(req_id, tool, hint))
            try:
                return await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                return "ask"
        finally:
            self._pending.pop(req_id, None)
            try:
                await self._send(build_cleared_snapshot())
            except Exception:
                pass

    def on_ble_line(self, line: str) -> None:
        p = parse_permission(line)
        if not p:
            return
        fut = self._pending.get(p["id"])
        if fut and not fut.done():
            fut.set_result(decision_to_hook(p["decision"]))
```

- [ ] **Step 4: Run → PASS** — 4 passed.

- [ ] **Step 5: Commit**
```bash
git add bridge/daemon.py tests/test_daemon.py && git commit -m "feat: bridge arbitration core (approval/timeout/stale) with async tests"
```

---

### Task 1.2: Daemon-Außenschale (Unix-Socket + BLE-Verdrahtung)

**Files:** Modify `bridge/daemon.py` (Socket-Server + `main()` ergänzen)

**Interfaces:**
- Consumes: `Bridge`, `BleCentral`.
- Produces: `python -m bridge.daemon` → hält BLE-Link, lauscht auf `$HOME/…/.run/bridge.sock`. Socket-Nachricht (eine JSON-Zeile) `{"type":"approve","id","tool","hint"}` → `bridge.request_approval(...)` → antwortet `{"decision":"allow|deny|ask"}\n`. `{"type":"status",...}` (P2) wird angenommen, in P1 noch ignoriert/geloggt.

- [ ] **Step 1: Socket-Server + main ergänzen**
```python
# bridge/daemon.py  (ans Ende anhängen)
import json, logging, os
from pathlib import Path
from .ble_central import BleCentral

APPROVE_TIMEOUT = 100.0
SOCK = Path(os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock"))
logging.basicConfig(filename="bridge.log", level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bridge")


async def _serve(bridge: "Bridge"):
    if SOCK.exists():
        SOCK.unlink()
    server = await asyncio.start_unix_server(_make_handler(bridge), path=str(SOCK))
    os.chmod(SOCK, 0o600)
    log.info("socket listening at %s", SOCK)
    async with server:
        await server.serve_forever()


def _make_handler(bridge: "Bridge"):
    async def handle(reader, writer):
        try:
            raw = await reader.readline()
            req = json.loads(raw.decode("utf-8"))
            if req.get("type") == "approve":
                decision = await bridge.request_approval(
                    req["id"], req.get("tool", "?"), req.get("hint", ""), APPROVE_TIMEOUT)
            else:
                decision = "ask"   # status u.a. (P2) — kein Approval
            writer.write((json.dumps({"decision": decision}) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as e:
            log.info("handler error: %s", e)
            try:
                writer.write(b'{"decision":"ask"}\n'); await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
    return handle


async def _main():
    bridge_ref: dict = {}
    def on_line(line: str):
        log.info("BLE< %s", line)
        if "bridge" in bridge_ref:
            bridge_ref["bridge"].on_ble_line(line)
    ble = BleCentral(on_line)
    await ble.connect()
    log.info("BLE connected to Claude-uConsole")
    bridge = Bridge(lambda s: ble.send_line(s))
    bridge_ref["bridge"] = bridge
    await _serve(bridge)


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Regressions-Check** — `pytest -q` → alle Tests (framing+protocol+daemon) grün (Import von `bridge.daemon` zieht jetzt `bleak` — muss installiert sein).

- [ ] **Step 3: Hardware-Verify — Daemon + Fake-Socket-Client**
1. Hardware Buddy trennen; uConsole-App läuft.
2. `python -m bridge.daemon` (verbindet BLE, „socket listening" im `bridge.log`).
3. Zweites Terminal — Fake-Request:
```bash
python - <<'PY'
import socket, os, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock"))
s.sendall((json.dumps({"type":"approve","id":"t1","tool":"Bash","hint":"echo hi"})+"\n").encode())
print("DAEMON:", s.recv(200).decode())   # blockt bis Knopfdruck
PY
```
4. Erwartet: Overlay auf uConsole → **Y** → Client druckt `{"decision":"allow"}`; **N** → `{"decision":"deny"}`; nichts drücken (~100s) → `{"decision":"ask"}`.

- [ ] **Step 4: Commit**
```bash
git add bridge/daemon.py && git commit -m "feat: daemon unix-socket server + BLE wiring"
```

---

### Task 1.3: `pretooluse.py`-Hook + settings.json (echt, end-to-end)

**Files:** Create `bridge/hooks/pretooluse.py`; Create `settings-snippet.json`

**Interfaces:**
- Consumes: Daemon-Socket, `protocol.hook_pretooluse_output`/`decision_to_hook`.
- Produces: ausführbares Hook-Script; gibt PreToolUse-JSON auf stdout, Exit 0. **Fail-safe → `ask`.**

- [ ] **Step 1: `pretooluse.py` implementieren**
```python
#!/usr/bin/env python3
# bridge/hooks/pretooluse.py — dünn, zustandslos, fail-safe ask
import json, os, socket, sys

SOCK = os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock")
HINT_MAX = 120

def hint_from(tool_name, tool_input):
    if tool_name == "Bash":
        return (tool_input.get("command", "") or "")[:HINT_MAX]
    return json.dumps(tool_input)[:HINT_MAX]

def out(decision, reason=""):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)

def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        out("ask", "hook: bad stdin")
    tool = ev.get("tool_name", "?")
    req_id = f"{ev.get('session_id','s')}#{os.getpid()}"
    hint = hint_from(tool, ev.get("tool_input", {}) or {})
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(115)
        s.connect(SOCK)
        s.sendall((json.dumps({"type": "approve", "id": req_id, "tool": tool, "hint": hint}) + "\n").encode())
        reply = json.loads(s.recv(400).decode())
        decision = reply.get("decision", "ask")
        if decision not in ("allow", "deny"):
            decision = "ask"
        out(decision, f"uConsole: {decision}")
    except Exception as e:
        out("ask", f"bridge unavailable: {e}")   # Daemon aus / BLE weg / Timeout → nativer Prompt

if __name__ == "__main__":
    main()
```
```bash
chmod +x bridge/hooks/pretooluse.py
```

- [ ] **Step 2: `settings-snippet.json`**
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [ { "type": "command",
                     "command": "$HOME/Documents/web/uconsole-companion-bridge/bridge/hooks/pretooluse.py",
                     "timeout": 120 } ] }
    ]
  }
}
```

- [ ] **Step 3: Fail-safe-Verify (ohne Daemon)** — Daemon NICHT laufen lassen:
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"echo hi"},"session_id":"s1"}' | ./bridge/hooks/pretooluse.py
```
Expected: `{"hookSpecificOutput": {..., "permissionDecision": "ask", ...}}` (Bridge unavailable → ask). Exit 0.

- [ ] **Step 4: settings.json einpflegen** — den `PreToolUse`-Block aus `settings-snippet.json` in `~/.claude/settings.json` mergen (`$HOME` real ausschreiben, falls Claude Code es nicht expandiert).

- [ ] **Step 5: Hardware-Integrationstest — der echte Loop**
1. Hardware Buddy trennen; uConsole-App läuft; `python -m bridge.daemon` läuft.
2. In einem **neuen** Terminal `claude` starten (damit die settings.json-Hooks greifen), einen Bash-Command auslösen (z.B. „lauf `ls /tmp`").
3. Erwartet: **⚠-Overlay auf der uConsole** (Tool: Bash / ls /tmp). **Y** → Claude Code führt aus. **N** → Claude Code meldet Ablehnung. Ohne Knopfdruck ~100s → nativer Terminal-Prompt (ask).
4. `bridge.log`: `BLE<` permission-Zeile + Socket-Handling sichtbar.

Expected: **Der Terminal-`claude` wird per uConsole-Knopf gesteuert. Spec P1 erreicht — funktionsfähig.**

- [ ] **Step 6: Commit**
```bash
git add bridge/hooks/pretooluse.py settings-snippet.json && git commit -m "feat: PreToolUse hook + settings; terminal approve/deny live"
```

---

# PHASE 2 — Status-Hooks

### Task 2.1: `notify.py`/`session.py`/`stop.py` + Daemon-Status

**Files:** Create `bridge/hooks/{notify,session,stop}.py`; Modify `bridge/daemon.py` (Status-Handling + Snapshot-Push)

**Interfaces:**
- Status-Hooks (dünn, fire-and-forget, kurzer Socket-Timeout): senden `{"type":"status","state":"running|idle|waiting","msg":...}`; ignorieren die Antwort.
- Daemon: bei `type==status` den gehaltenen Snapshot-Zustand aktualisieren und (wenn kein Approval aktiv) einen Snapshot pushen.

- [ ] **Step 1: gemeinsamer dünner Sender**
```python
# bridge/hooks/_send.py
import json, os, socket, sys
SOCK = os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock")
def send_status(state, msg=""):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
        s.connect(SOCK)
        s.sendall((json.dumps({"type":"status","state":state,"msg":msg})+"\n").encode())
    except Exception:
        pass
    sys.exit(0)
```
```python
# bridge/hooks/session.py
#!/usr/bin/env python3
import sys; from _send import send_status  # noqa
if __name__ == "__main__": send_status("running", "session start")
```
(analog `stop.py` → `send_status("idle","done")`; `notify.py` liest stdin `notification_type` → `waiting` bei `permission_prompt`, sonst `idle`.)

- [ ] **Step 2: Daemon-Status-Handling** — im `_make_handler` `type=="status"` behandeln: Zustand merken; wenn gerade kein `_pending`-Approval, `send_snapshot(build_snapshot(running=..., waiting=..., msg=...))`. Antwort `{"decision":"ask"}` (Status braucht keine Entscheidung, Feld wird ignoriert).

- [ ] **Step 3: Hardware-Verify** — Hooks in settings.json ergänzen (Notification/SessionStart/Stop), `claude`-Session starten: uConsole zeigt `● running` bei Start, `waiting` bei Prompt, `idle` bei Stop.

- [ ] **Step 4: Commit**
```bash
git add bridge/hooks/ && git commit -m "feat(status): notification/session/stop hooks + daemon status push"
```

---

# PHASE 3 — Härten & Autostart

### Task 3.1: launchd-Keepalive + Reconnect + Docs

**Files:** Create `bridge/run.sh`, `com.uconsole.bridge.plist`; Modify `bridge/ble_central.py` (Reconnect); Modify `README.md`

- [ ] **Step 1: `run.sh`**
```bash
#!/usr/bin/env bash
cd "$HOME/Documents/web/uconsole-companion-bridge"
source .venv/bin/activate
exec python -m bridge.daemon
```
```bash
chmod +x bridge/run.sh
```

- [ ] **Step 2: Reconnect in `ble_central.py`** — bei Disconnect-Callback (`BleakClient(..., disconnected_callback=...)`) neu scannen+verbinden mit Backoff; `_pending`-Futures beim Drop auf `ask` auflösen.

- [ ] **Step 3: `com.uconsole.bridge.plist` (launchd User-Agent)**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.uconsole.bridge</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-lc</string>
    <string>$HOME/Documents/web/uconsole-companion-bridge/bridge/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
```

- [ ] **Step 4: Installieren + Verify**
```bash
cp com.uconsole.bridge.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.uconsole.bridge.plist
launchctl list | grep uconsole   # läuft?
```
> ⚠️ launchd-Kontext braucht evtl. separat Bluetooth-TCC-Freigabe (offener Punkt Spec §9). Beim ersten Lauf `bridge.log` prüfen; wenn BLE-Permission fehlt, Daemon vorerst manuell aus einem freigegebenen Terminal starten.

- [ ] **Step 5: README-Setup-Doku** — Ein-/Ausschalten, „Hardware Buddy trennen"-Hinweis, Troubleshooting (BT-TCC, Daemon vor `claude` starten).

- [ ] **Step 6: Commit**
```bash
git add bridge/run.sh com.uconsole.bridge.plist bridge/ble_central.py README.md
git commit -m "feat: launchd keepalive + BLE reconnect + docs"
```

---

## Self-Review (gegen den Spec)

- **Spec §2 Architektur / §3 Komponenten** → File-Structure + Tasks 0.1–1.2, 2.1. ✅
- **Spec §4.1 Approval-Fluss** → Task 1.1 (Arbitrierung) + 1.2 (Socket/BLE) + 1.3 (Hook). ✅
- **Spec §4.2 Status** → Task 2.1. ✅
- **Spec §5 Fail-safe = ask** → Task 1.1 (Timeout→ask), 1.2 (Handler-Fehler→ask), 1.3 (Hook alle Fehlerpfade→ask) + Test `test_approval_timeout_asks`, Fail-safe-Verify 1.3 Step 3. ✅
- **Spec §6 settings.json / PreToolUse-Contract** → Task 1.3 (settings-snippet + hook_pretooluse_output-Schema, getestet in test_protocol). ✅
- **Spec §7 Entscheidungen** (Matcher=Bash, getrenntes Repo, ask, B=v2) → Global Constraints + Task 1.3 Matcher. ✅
- **Spec §8 Phasen** → P0–P3. ✅
- **Spec §9 offene Punkte** (BT-TCC, Contention, MTU, Hook-Latenz, permission_mode) → Task 0.4 Step 3 (TCC + Contention), 0.4 (MTU via chunk_for_mtu), 3.1 Step 4 (launchd-TCC); permission_mode bewusst v1-out (Spec §9). ✅
- **NUS-Rollen-Inversion** (Central: WRITE RX / SUBSCRIBE TX) → Task 0.4 explizit. ✅

Kein Platzhalter. Typkonsistenz: `request_approval`/`on_ble_line`/`send_snapshot`/`decision_to_hook`/`hook_pretooluse_output`/`build_prompt_snapshot` durchgängig gleich benannt über Tasks 0.3–1.3.
