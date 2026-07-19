---
tags: [projekt, uconsole, claude, ble, maker, claude-code, hooks, buddy, mood, notify, plan]
status: bereit-zur-umsetzung
created: 2026-07-19
updated: 2026-07-19
source: marvin-session
hardware: uConsole (Raspberry Pi CM4) + Mac
sprache: Python
spec: "[[Claude Companion Buddy (Mood & Notify) - Spec]]"
---

# Claude Companion Buddy (Mood & Notify) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erweitert das uConsole-Companion vom Freigabe-Terminal zum Buddy, der auf CC-Sessions reagiert: Ambient-Mood, Live-Feed, Sound-Ping bei `waiting`, Charakter.

**Architecture:** Ansatz A — Bridge (Mac) liefert Fakten (echter `state`-String + Feed-Zeilen im Snapshot), Gerät (uConsole) rendert Mood/Feed und feuert Sound bei State-Übergängen. Baut auf der bestehenden Pipeline `CC-Hook → Socket → Daemon → BLE → Device-State → UI` auf; nichts an der Bash-Approval-Kette ändert sich.

**Tech Stack:** Python 3.11, asyncio; Bridge: `bleak`; Gerät: `textual` + `bluez-peripheral`; Tests: `pytest` (pure-logic, off-hardware). Repos: Bridge `~/Documents/web/uconsole-companion-bridge/` (Mac), Device `~/Documents/web/uconsole-companion/` (uConsole, via `ssh uconsole`).

## Global Constraints

- **Zwei Repos, zwei Maschinen.** Bridge-Tasks (1–4) laufen auf dem Mac. Device-Tasks (5–8) laufen auf der uConsole (`ssh uconsole`, User `nikolai`, Repo `~/Documents/web/uconsole-companion/`).
- **Abwärtskompatibel:** neue Snapshot-Felder additiv; ältere Gerät-Version ignoriert `state` und fällt auf `connection_state()` zurück.
- **Approval-Vorrang unantastbar:** solange ein Prompt in `Bridge._pending` offen ist, überschreibt kein Status-Event den Overlay-Snapshot.
- **Hooks bleiben fire-and-forget:** jeder Statushook schluckt Exceptions und beendet mit `sys.exit(0)`; nie CC blockieren.
- **Sound-Wiedergabe darf nie die State/Render-Loop blockieren** — Fehler still schlucken.
- **Test-Konvention Bridge:** `asyncio.run`-Wrapper `def run(coro)`, Helper `make_bridge()` (siehe `tests/test_daemon.py`). Test-Konvention Gerät: plain `pytest`, `pythonpath=["."]`.
- **Commit-Stil:** kleine Commits pro Task, `feat:`/`test:`/`chore:`-Präfix.

---

## Task 1: Snapshot bekommt `state`-Feld (Bridge)

**Files:**
- Modify: `~/Documents/web/uconsole-companion-bridge/bridge/protocol.py` (`build_snapshot`)
- Test: `~/Documents/web/uconsole-companion-bridge/tests/test_protocol.py`

**Interfaces:**
- Produces: `build_snapshot(*, state="idle", total=1, running=0, waiting=0, msg="", prompt=None, tokens=0, tokens_today=0, entries=None) -> str` — JSON-Zeile enthält jetzt `"state"`.

- [ ] **Step 1: Failing test** — in `tests/test_protocol.py` anhängen:

```python
def test_build_snapshot_has_state():
    m = json.loads(build_snapshot(state="waiting"))
    assert m["state"] == "waiting"

def test_build_snapshot_default_state_idle():
    m = json.loads(build_snapshot())
    assert m["state"] == "idle"
```

- [ ] **Step 2: Run — verify fail**

Run: `cd ~/Documents/web/uconsole-companion-bridge && pytest tests/test_protocol.py -q`
Expected: FAIL (`KeyError: 'state'`)

- [ ] **Step 3: Implement** — `build_snapshot` in `bridge/protocol.py` anpassen:

```python
def build_snapshot(*, state="idle", total=1, running=0, waiting=0, msg="", prompt=None,
                   tokens=0, tokens_today=0, entries=None) -> str:
    return json.dumps({
        "state": state,
        "total": total, "running": running, "waiting": waiting, "msg": msg,
        "entries": entries or [], "tokens": tokens, "tokens_today": tokens_today,
        "prompt": prompt,
    }) + "\n"
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_protocol.py -q`
Expected: PASS (alle, inkl. bestehende — `state` ist additiv)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/web/uconsole-companion-bridge
git add bridge/protocol.py tests/test_protocol.py
git commit -m "feat(protocol): snapshot carries explicit state field"
```

---

## Task 2: Daemon führt Zustand + Feed, `push_event` (Bridge)

**Files:**
- Modify: `~/Documents/web/uconsole-companion-bridge/bridge/daemon.py` (`Bridge`-Klasse)
- Test: `~/Documents/web/uconsole-companion-bridge/tests/test_daemon.py`

**Interfaces:**
- Consumes: `build_snapshot(state=..., entries=...)` aus Task 1.
- Produces:
  - `Bridge.push_event(self, state=None, msg=None, entry=None) -> awaitable` — aktualisiert internen Zustand (`_state`, `_msg`, `_entries` deque maxlen 8), pusht angereicherten Snapshot; überspringt Push (aber merkt sich den Zustand), wenn `_pending` aktiv.
  - `Bridge.push_status(self, state, msg="")` bleibt als dünner Wrapper → `push_event(state=state, msg=msg)` (bestehende Tests + Hooks brechen nicht).

- [ ] **Step 1: Failing test** — in `tests/test_daemon.py` anhängen:

```python
import json

def test_push_event_sets_state_and_entry():
    async def scenario():
        b, sent = make_bridge()
        await b.push_event(state="running", msg="arbeite", entry="14:23 Bash: ls")
        m = json.loads(sent[-1])
        assert m["state"] == "running"
        assert m["entries"] == ["14:23 Bash: ls"]
        assert m["msg"] == "arbeite"
    run(scenario())

def test_push_event_entries_ring_keeps_last_8():
    async def scenario():
        b, sent = make_bridge()
        for i in range(10):
            await b.push_event(state="running", entry=f"e{i}")
        m = json.loads(sent[-1])
        assert m["entries"] == [f"e{i}" for i in range(2, 10)]  # nur letzte 8
    run(scenario())

def test_push_event_skips_send_during_approval_but_keeps_state():
    async def scenario():
        b, sent = make_bridge()
        task = asyncio.create_task(b.request_approval("rA", "Bash", "x", timeout=5))
        await asyncio.sleep(0)
        before = len(sent)
        await b.push_event(state="running", entry="hidden")
        assert len(sent) == before                      # kein Push während Approval
        b.on_ble_line('{"cmd":"permission","id":"rA","decision":"once"}')
        await task
        await b.push_event(state="done")                # jetzt frei
        m = json.loads(sent[-1])
        assert m["state"] == "done"
        assert "hidden" in m["entries"]                 # während Approval gemerkte Zeile ist da
    run(scenario())
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_daemon.py -q`
Expected: FAIL (`AttributeError: 'Bridge' object has no attribute 'push_event'`)

- [ ] **Step 3: Implement** — in `bridge/daemon.py`: oben `from collections import deque` ergänzen; `Bridge.__init__` erweitern und `push_status` ersetzen:

```python
    def __init__(self, send_snapshot: Callable[[str], Awaitable[None]]):
        self._send = send_snapshot
        self._pending: dict[str, asyncio.Future] = {}
        self._state = "idle"
        self._msg = "idle"
        self._entries: deque[str] = deque(maxlen=8)

    def _build_state_snapshot(self) -> str:
        return build_snapshot(
            state=self._state,
            total=1,
            running=1 if self._state in ("running", "thinking") else 0,
            waiting=1 if self._state == "waiting" else 0,
            msg=self._msg,
            entries=list(self._entries),
        )

    async def push_event(self, state: str | None = None, msg: str | None = None,
                         entry: str | None = None) -> None:
        if entry:
            self._entries.append(entry)
        if state is not None:
            self._state = state
        if msg is not None:
            self._msg = msg
        if self._pending:          # aktiver Approval-Overlay hat Vorrang
            return
        await self._send(self._build_state_snapshot())

    async def push_status(self, state: str, msg: str = "") -> None:
        """Rückwärtskompatibler Wrapper (alte Hooks + Tests)."""
        await self.push_event(state=state, msg=msg)
```

(Der Import `build_snapshot` ist in `daemon.py` bereits vorhanden.)

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_daemon.py -q`
Expected: PASS (neue + bestehende, inkl. `test_push_status_*`)

- [ ] **Step 5: Commit**

```bash
git add bridge/daemon.py tests/test_daemon.py
git commit -m "feat(daemon): stateful push_event with rolling entries feed"
```

---

## Task 3: Done→idle-Zerfall (Bridge)

**Files:**
- Modify: `~/Documents/web/uconsole-companion-bridge/bridge/daemon.py` (`Bridge`)
- Test: `~/Documents/web/uconsole-companion-bridge/tests/test_daemon.py`

**Interfaces:**
- Produces: nach `push_event(state="done")` plant der Daemon einen Übergang auf `idle` nach `decay`-Sekunden (Default 5.0); jedes weitere Event canceled den Timer. Parameter `decay` an `push_event` für Testbarkeit.

- [ ] **Step 1: Failing test** — anhängen:

```python
def test_done_decays_to_idle():
    async def scenario():
        b, sent = make_bridge()
        await b.push_event(state="done", decay=0.05)
        assert json.loads(sent[-1])["state"] == "done"
        await asyncio.sleep(0.12)
        assert json.loads(sent[-1])["state"] == "idle"   # automatisch zerfallen
    run(scenario())

def test_new_event_cancels_decay():
    async def scenario():
        b, sent = make_bridge()
        await b.push_event(state="done", decay=0.10)
        await b.push_event(state="running")              # canceled Zerfall
        await asyncio.sleep(0.15)
        assert json.loads(sent[-1])["state"] == "running"
    run(scenario())
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_daemon.py -k decay -q`
Expected: FAIL (`push_event() got an unexpected keyword argument 'decay'`)

- [ ] **Step 3: Implement** — `__init__` um `self._idle_task = None` ergänzen; `push_event`-Signatur + Timer-Logik:

```python
    async def push_event(self, state: str | None = None, msg: str | None = None,
                         entry: str | None = None, decay: float = 5.0) -> None:
        if entry:
            self._entries.append(entry)
        if state is not None:
            self._state = state
            self._cancel_decay()
            if state == "done":
                self._idle_task = asyncio.ensure_future(self._decay_to_idle(decay))
        if msg is not None:
            self._msg = msg
        if self._pending:
            return
        await self._send(self._build_state_snapshot())

    def _cancel_decay(self) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    async def _decay_to_idle(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._state = "idle"
        self._msg = "idle"
        if not self._pending:
            await self._send(self._build_state_snapshot())
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_daemon.py -q`
Expected: PASS (alle)

- [ ] **Step 5: Commit**

```bash
git add bridge/daemon.py tests/test_daemon.py
git commit -m "feat(daemon): done state auto-decays to idle after 5s"
```

---

## Task 4: Hooks pushen Events + Registrierung (Bridge)

**Files:**
- Modify: `~/Documents/web/uconsole-companion-bridge/bridge/hooks/_send.py`
- Modify: `bridge/hooks/session.py`, `bridge/hooks/stop.py`, `bridge/hooks/notify.py`
- Create: `bridge/hooks/userprompt.py`, `bridge/hooks/posttooluse.py`, `bridge/hooks/sessionend.py`
- Modify: `settings-snippet.json`
- Modify: `bridge/daemon.py` (Socket-Handler `type:"status"` → `push_event` mit `entry`)
- Test: `~/Documents/web/uconsole-companion-bridge/tests/test_hooks.py` (neu, pure-logic)

**Interfaces:**
- Consumes: Unix-Socket-Protokoll `{"type":"status","state":?,"msg":?,"entry":?}`.
- Produces:
  - `_send.send_status(state=None, msg="", entry=None)` — sendet erweitertes Status-JSON, fire-and-forget.
  - `posttooluse.feed_line(tool, tool_input, hhmm) -> str` — pure Formatter für Feed-Zeilen (getestet).

- [ ] **Step 1: Failing test** — `tests/test_hooks.py` anlegen:

```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "posttooluse", pathlib.Path("bridge/hooks/posttooluse.py"))
ptu = importlib.util.module_from_spec(spec); spec.loader.exec_module(ptu)

def test_feed_line_bash():
    assert ptu.feed_line("Bash", {"command": "npm test"}, "14:23") == "14:23 Bash: npm test"

def test_feed_line_edit_uses_file_path():
    assert ptu.feed_line("Edit", {"file_path": "/a/b/ui.py"}, "09:01") == "09:01 Edit: ui.py"

def test_feed_line_truncates():
    line = ptu.feed_line("Bash", {"command": "x" * 200}, "00:00")
    assert len(line) <= 60
```

- [ ] **Step 2: Run — verify fail**

Run: `cd ~/Documents/web/uconsole-companion-bridge && pytest tests/test_hooks.py -q`
Expected: FAIL (Datei `bridge/hooks/posttooluse.py` fehlt)

- [ ] **Step 3: Implement**

`bridge/hooks/_send.py` ersetzen:

```python
# bridge/hooks/_send.py — shared fire-and-forget status sender. NOT a hook itself.
import json, os, socket, sys

SOCK = os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock")


def send_status(state=None, msg="", entry=None):
    payload = {"type": "status", "msg": msg}
    if state is not None:
        payload["state"] = state
    if entry is not None:
        payload["entry"] = entry
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(SOCK)
        s.sendall((json.dumps(payload) + "\n").encode())
    except Exception:
        pass
    sys.exit(0)
```

`bridge/hooks/session.py`:

```python
#!/usr/bin/env python3
import sys
from _send import send_status
if __name__ == "__main__":
    sys.stdin.read()
    send_status(state="thinking", msg="session start")
```

`bridge/hooks/stop.py`:

```python
#!/usr/bin/env python3
import sys
from _send import send_status
if __name__ == "__main__":
    sys.stdin.read()
    send_status(state="done", msg="fertig")
```

`bridge/hooks/notify.py`:

```python
#!/usr/bin/env python3
import json, sys
from _send import send_status
if __name__ == "__main__":
    try:
        ev = json.load(sys.stdin)
    except Exception:
        ev = {}
    if (ev.get("notification_type") or "") == "permission_prompt":
        send_status(state="waiting", msg="brauch dich")
    else:
        send_status(state="waiting", msg=ev.get("message", "brauch dich"))
```

`bridge/hooks/userprompt.py` (neu):

```python
#!/usr/bin/env python3
import sys
from _send import send_status
if __name__ == "__main__":
    sys.stdin.read()
    send_status(state="thinking", msg="denke nach")
```

`bridge/hooks/sessionend.py` (neu):

```python
#!/usr/bin/env python3
import sys
from _send import send_status
if __name__ == "__main__":
    sys.stdin.read()
    send_status(state="idle", msg="idle")
```

`bridge/hooks/posttooluse.py` (neu):

```python
#!/usr/bin/env python3
import json, os, sys
from datetime import datetime
from _send import send_status

MAXLEN = 60


def feed_line(tool, tool_input, hhmm):
    ti = tool_input or {}
    if tool == "Bash":
        hint = ti.get("command", "")
    elif tool in ("Edit", "Write", "Read"):
        hint = os.path.basename(ti.get("file_path", "") or "")
    else:
        hint = json.dumps(ti)
    line = f"{hhmm} {tool}: {hint}"
    return line[:MAXLEN]


def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        ev = {}
    tool = ev.get("tool_name", "?")
    hhmm = datetime.now().strftime("%H:%M")
    entry = feed_line(tool, ev.get("tool_input", {}), hhmm)
    send_status(state="running", entry=entry)


if __name__ == "__main__":
    main()
```

Chmod ausführbar:

```bash
chmod +x bridge/hooks/userprompt.py bridge/hooks/posttooluse.py bridge/hooks/sessionend.py
```

Daemon-Socket-Handler in `bridge/daemon.py` (`_make_handler`) den `status`-Zweig erweitern:

```python
            elif req.get("type") == "status":
                await bridge.push_event(state=req.get("state"),
                                        msg=req.get("msg") if "msg" in req else None,
                                        entry=req.get("entry"))
                decision = "ask"
```

`settings-snippet.json` ersetzen (PreToolUse/Bash bleibt, Rest additiv — Pfade absolut):

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/pretooluse.py", "timeout": 120 } ] }
    ],
    "PostToolUse": [
      { "matcher": "*", "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/posttooluse.py", "timeout": 10 } ] }
    ],
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/userprompt.py", "timeout": 10 } ] }
    ],
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/session.py", "timeout": 10 } ] }
    ],
    "Notification": [
      { "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/notify.py", "timeout": 10 } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/stop.py", "timeout": 10 } ] }
    ],
    "SessionEnd": [
      { "hooks": [ { "type": "command", "command": "/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/bridge/hooks/sessionend.py", "timeout": 10 } ] }
    ]
  }
}
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_hooks.py -q && pytest -q`
Expected: PASS (Feed-Formatter + gesamte Bridge-Suite grün)

- [ ] **Step 5: Manuell verdrahten + Smoke** (nicht-automatisiert)

`settings-snippet.json`-Inhalt in die aktiv genutzte `.claude/settings.json` des Test-Projekts (`~/uconsole-hook-test/.claude/settings.json`) übernehmen. Daemon starten (`python -m bridge.daemon`), `claude` im Testprojekt starten, einen Prompt + Tool-Call auslösen → im `bridge.log` `BLE< ...` bzw. Snapshot mit `"state"` sehen.

- [ ] **Step 6: Commit**

```bash
git add bridge/hooks/ settings-snippet.json bridge/daemon.py tests/test_hooks.py
git commit -m "feat(hooks): session/prompt/posttooluse/notify/stop/end push buddy events"
```

---

## Task 5: `mood.py` — Gesicht + Spruch (Gerät)

**Files:**
- Create: `~/Documents/web/uconsole-companion/companion/mood.py`
- Test: `~/Documents/web/uconsole-companion/tests/test_mood.py`

**Interfaces:**
- Produces: `mood_for(state: str) -> tuple[str, str]` — `(face, spruch)`; unbekannter/leerer State → `("😐", "…")`.

- [ ] **Step 1: Failing test** — `tests/test_mood.py`:

```python
from companion.mood import mood_for

def test_known_states_have_face_and_spruch():
    for st in ["idle", "thinking", "running", "waiting", "done", "error"]:
        face, spruch = mood_for(st)
        assert face and spruch

def test_waiting_is_distinct():
    assert mood_for("waiting") != mood_for("running")

def test_unknown_state_fallback():
    assert mood_for("bogus") == ("😐", "…")
```

- [ ] **Step 2: Run — verify fail**

Run: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest tests/test_mood.py -q'`
Expected: FAIL (`ModuleNotFoundError: companion.mood`)

- [ ] **Step 3: Implement** — `companion/mood.py`:

```python
"""State → Gesicht + Spruch. Reine Logik, hier lebt der Charakter."""

_MOODS = {
    "idle":     ("😴", "warte auf dich"),
    "thinking": ("🤔", "denke nach…"),
    "running":  ("⚙️", "arbeite…"),
    "waiting":  ("🙋", "brauch dich!"),
    "done":     ("✅", "fertig!"),
    "error":    ("💥", "autsch"),
}


def mood_for(state: str) -> tuple[str, str]:
    return _MOODS.get(state, ("😐", "…"))
```

- [ ] **Step 4: Run — verify pass**

Run: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest tests/test_mood.py -q'`
Expected: PASS

- [ ] **Step 5: Commit** (auf dem Gerät)

```bash
ssh uconsole 'cd ~/Documents/web/uconsole-companion && git add companion/mood.py tests/test_mood.py && git commit -m "feat(mood): state to face+spruch mapping"'
```

---

## Task 6: State liest `state`-Feld, UI zeigt Gesicht (Gerät)

**Files:**
- Modify: `~/Documents/web/uconsole-companion/companion/state.py` (`AppState`)
- Modify: `~/Documents/web/uconsole-companion/companion/ui.py` (`CompanionApp`)
- Test: `~/Documents/web/uconsole-companion/tests/test_state.py`

**Interfaces:**
- Consumes: `mood_for` (Task 5).
- Produces:
  - `AppState.claude_state: str` (aus Snapshot-Feld `state`, Default `""`).
  - `AppState.mood_state(now: float) -> str` — liefert `claude_state`, sonst Fallback `connection_state(now)`.

- [ ] **Step 1: Failing test** — in `tests/test_state.py` anhängen:

```python
from companion.state import AppState

def test_apply_snapshot_reads_state():
    s = AppState()
    s.apply_snapshot({"total": 1, "state": "waiting"}, now=100.0)
    assert s.claude_state == "waiting"
    assert s.mood_state(now=100.0) == "waiting"

def test_mood_state_falls_back_to_connection_state():
    s = AppState()
    s.apply_snapshot({"total": 1, "running": 1}, now=100.0)  # kein state-Feld
    assert s.claude_state == ""
    assert s.mood_state(now=100.0) == "running"  # aus connection_state abgeleitet
```

- [ ] **Step 2: Run — verify fail**

Run: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest tests/test_state.py -q'`
Expected: FAIL (`AttributeError: 'AppState' object has no attribute 'claude_state'`)

- [ ] **Step 3: Implement**

In `companion/state.py`: in `__init__` `self.claude_state = ""` ergänzen; in `apply_snapshot` nach den anderen Feldern `self.claude_state = msg.get("state", "")`; neue Methode:

```python
    def mood_state(self, now: float) -> str:
        return self.claude_state or self.connection_state(now)
```

In `companion/ui.py`: `from .mood import mood_for` ergänzen; `#face` ins Layout + Styling; `compose` und `render_from_state` erweitern:

```python
    CSS = """
    #face { padding: 1; text-style: bold; }
    #overlay { display: none; border: heavy $warning; padding: 1; }
    #overlay.active { display: block; }
    #status { padding: 1; }
    """
```

```python
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="face")
            yield Static("", id="status")
            yield Static("", id="overlay")
```

Am Anfang von `render_from_state` (nach `self._state = state`):

```python
        face, spruch = mood_for(state.mood_state(now))
        self.query_one("#face", Static).update(f"{face}  {spruch}")
```

- [ ] **Step 4: Run — verify pass**

Run: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest tests/test_state.py -q'`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ssh uconsole 'cd ~/Documents/web/uconsole-companion && git add companion/state.py companion/ui.py tests/test_state.py && git commit -m "feat(ui): render mood face from explicit state"'
```

---

## Task 7: `notify.py` — Sound-Entscheidungslogik (Gerät)

**Files:**
- Create: `~/Documents/web/uconsole-companion/companion/notify.py`
- Test: `~/Documents/web/uconsole-companion/tests/test_notify.py`

**Interfaces:**
- Produces: `NotifyDecider(debounce=2.0)` mit `.decide(state: str, now: float) -> str | None` (Kanal `"waiting"|"done"|"error"` oder `None`), edge-triggered (nur bei State-Wechsel), debounced (min. Abstand), `.muted: bool`.

- [ ] **Step 1: Failing test** — `tests/test_notify.py`:

```python
from companion.notify import NotifyDecider

def test_fires_on_transition_to_waiting():
    d = NotifyDecider()
    assert d.decide("running", now=0.0) is None      # kein Kanal für running
    assert d.decide("waiting", now=1.0) == "waiting"  # Übergang → feuert

def test_no_refire_same_state():
    d = NotifyDecider()
    assert d.decide("waiting", now=0.0) == "waiting"
    assert d.decide("waiting", now=5.0) is None       # gleicher State → still

def test_debounce_blocks_rapid_fires():
    d = NotifyDecider(debounce=2.0)
    assert d.decide("waiting", now=0.0) == "waiting"
    assert d.decide("done", now=0.5) is None          # zu schnell nach letztem Feuer
    assert d.decide("waiting", now=3.0) == "waiting"   # nach Debounce wieder frei

def test_muted_never_fires():
    d = NotifyDecider(); d.muted = True
    assert d.decide("waiting", now=0.0) is None
```

- [ ] **Step 2: Run — verify fail**

Run: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest tests/test_notify.py -q'`
Expected: FAIL (`ModuleNotFoundError: companion.notify`)

- [ ] **Step 3: Implement** — `companion/notify.py`:

```python
"""Sound-Notification: Entscheidungslogik (rein) + Wiedergabe (I/O-Rand)."""
import subprocess

_CHANNELS = {"waiting": "waiting", "done": "done", "error": "error"}


class NotifyDecider:
    def __init__(self, debounce: float = 2.0) -> None:
        self._debounce = debounce
        self._last_state: str | None = None
        self._last_fire = float("-inf")
        self.muted = False

    def decide(self, state: str, now: float) -> str | None:
        prev, self._last_state = self._last_state, state
        if self.muted or state == prev:
            return None
        channel = _CHANNELS.get(state)
        if channel is None:
            return None
        if now - self._last_fire < self._debounce:
            return None
        self._last_fire = now
        return channel


def play(channel: str, assets_dir: str) -> None:
    """Fire-and-forget WAV-Wiedergabe; Fehler still schlucken (nie Loop blockieren)."""
    try:
        subprocess.Popen(
            ["paplay", f"{assets_dir}/{channel}.wav"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
```

- [ ] **Step 4: Run — verify pass**

Run: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest tests/test_notify.py -q'`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
ssh uconsole 'cd ~/Documents/web/uconsole-companion && git add companion/notify.py tests/test_notify.py && git commit -m "feat(notify): edge-triggered debounced sound decider"'
```

---

## Task 8: Sound-Assets + Verdrahtung + Mute-Toggle (Gerät)

**Files:**
- Create: `~/Documents/web/uconsole-companion/companion/assets/waiting.wav`, `done.wav`, `error.wav` (per Generator-Skript)
- Create: `~/Documents/web/uconsole-companion/tools/gen_sounds.py`
- Modify: `~/Documents/web/uconsole-companion/companion/main.py` (Notifier verdrahten)
- Modify: `~/Documents/web/uconsole-companion/companion/ui.py` (Mute-Taste `m`)

**Interfaces:**
- Consumes: `NotifyDecider`, `play` (Task 7); `AppState.mood_state` (Task 6).

- [ ] **Step 1: Sound-Generator schreiben** — `tools/gen_sounds.py` (stdlib `wave`+`math`, keine Extra-Deps):

```python
"""Erzeugt kleine WAV-Töne in companion/assets/. Aufruf: python tools/gen_sounds.py"""
import math, os, struct, wave

OUT = os.path.join(os.path.dirname(__file__), "..", "companion", "assets")
RATE = 22050


def tone(path, freqs, dur=0.18, vol=0.4):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames = bytearray()
    per = int(RATE * dur)
    for f in freqs:                       # Sequenz kurzer Töne = Chime
        for i in range(per):
            env = min(1.0, i / 400) * min(1.0, (per - i) / 400)   # weiche Flanken
            s = int(vol * env * 32767 * math.sin(2 * math.pi * f * i / RATE))
            frames += struct.pack("<h", s)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(frames))


if __name__ == "__main__":
    tone(os.path.join(OUT, "waiting.wav"), [880, 1175])   # deutlicher Zwei-Ton-Chime
    tone(os.path.join(OUT, "done.wav"), [660], dur=0.15, vol=0.25)  # sanft
    tone(os.path.join(OUT, "error.wav"), [300, 220], dur=0.14)      # tiefer Fehlerton
    print("wrote waiting.wav done.wav error.wav")
```

- [ ] **Step 2: Sounds erzeugen + hörbar prüfen** (am Gerät)

```bash
ssh uconsole 'cd ~/Documents/web/uconsole-companion && python tools/gen_sounds.py && for w in waiting done error; do paplay companion/assets/$w.wav; done'
```

Expected: Datei-Ausgabe + drei hörbare Töne (Chime / sanft / tief).

- [ ] **Step 3: Notifier in `main.py` verdrahten**

In `companion/main.py`: Imports ergänzen `import os` und `from .notify import NotifyDecider, play`; in `Companion.__init__` `self.notifier = NotifyDecider()` und `self._assets = os.path.join(os.path.dirname(__file__), "assets")`; im `_on_line`-Snapshot-Zweig:

```python
        if "total" in msg:                      # Heartbeat-Snapshot
            now = time.monotonic()
            self.state.apply_snapshot(msg, now=now)
            channel = self.notifier.decide(self.state.mood_state(now), now)
            if channel:
                play(channel, self._assets)
            self._rerender()
```

`CompanionApp` (in `ui.py`) um Mute-Toggle erweitern — Konstruktor nimmt optionalen `on_mute`-Callback; Binding + Action:

```python
    BINDINGS = [
        ("y", "approve", "erlauben"),
        ("enter", "approve", "erlauben"),
        ("n", "deny", "ablehnen"),
        ("escape", "deny", "ablehnen"),
        ("m", "mute", "stumm"),
        ("q", "quit", "beenden"),
    ]

    def __init__(self, on_decision, on_mute=None):
        super().__init__()
        self._on_decision = on_decision
        self._on_mute = on_mute
        self._state = None

    def action_mute(self) -> None:
        if self._on_mute:
            self._on_mute()
```

In `main.py` den Callback übergeben und Mute-Status spiegeln:

```python
        self.app = CompanionApp(on_decision=self._on_decision, on_mute=self._toggle_mute)
```

```python
    def _toggle_mute(self) -> None:
        self.notifier.muted = not self.notifier.muted
        self._rerender()
```

Mute-Indikator in `render_from_state` (im `body`-String der `#status`-Zeile, z. B. am Ende): `{" 🔇" if getattr(self, "_muted", False) else ""}` — dafür setzt `main._toggle_mute` zusätzlich `self.app._muted = self.notifier.muted` vor `_rerender`.

- [ ] **Step 4: Voller Smoke-Test am Gerät** (nicht-automatisiert)

Bridge-Daemon auf dem Mac starten, `claude` im Testprojekt, einen Prompt abschicken:
- Gesicht wechselt 🤔→⚙️→(bei Input-Bedarf)🙋 mit Chime → nach Abschluss ✅ mit sanftem Ton → nach 5 s 😴.
- `m` am Gerät schaltet stumm (🔇), Töne bleiben aus.
- Bash-Freigabe-Overlay + Y/N funktioniert weiterhin.

Regressions-Check: `ssh uconsole 'cd ~/Documents/web/uconsole-companion && pytest -q'` → alle grün.

- [ ] **Step 5: Commit**

```bash
ssh uconsole 'cd ~/Documents/web/uconsole-companion && git add companion/main.py companion/ui.py companion/assets tools/gen_sounds.py && git commit -m "feat(buddy): wire sound notifier + mute toggle into live loop"'
```

---

## Self-Review (Autor)

**Spec-Coverage:** Ambient-Mood → T1/T2/T5/T6 · Sound-Notify → T7/T8 · Live-Feed → T2 (entries) + T4 (posttooluse) + T6 (UI zeigt entries schon) · Charakter → T5 (mood.py) · Bridge nicht-verlustbehaftet → T2 · Done→idle → T3 · Approval unangetastet → Global Constraints + T2-Test. Alle 4 Spec-Ziele abgedeckt.

**Increment-Grenzen:** C-Increment (grober State live) = T1–T4; Feed = T2+T4; Mood = T5+T6; Notify = T7+T8. Jeder Task endet mit eigenständig testbarem Deliverable.

**Typkonsistenz:** `state`-Strings identisch über Bridge (`push_event`) und Gerät (`mood_for`/`NotifyDecider`): `idle/thinking/running/waiting/done/error`. `feed_line`/`entries` Format konsistent (`"HH:MM Tool: hint"`). `mood_state(now)` einheitlich in T6 definiert + T8 konsumiert.

**Offen (Spec §9, bewusst später):** Token-Usage aus Hook-JSON, echte statt synthetische WAVs, Light-Notify-Kanal.
