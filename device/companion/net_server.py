"""Direct TCP transport for the companion — no BLE, no separate bridge daemon.

For remote setups (agent on one host, uConsole on another, linked over a private
overlay such as Tailscale) the BLE central/peripheral split does not work: BLE is
short-range and needs a machine next to the device. This module collapses the
former host-side bridge daemon INTO the device app: it runs a session-aware event
aggregator (`Bridge`) plus an asyncio TCP server, so multiple agent sessions can
connect at once and speak the same newline-JSON protocol as the unix socket.

Multi-session (e.g. several tmux windows each running gjc/claude):
  Each agent tags its events with `sid` (stable per process) and `label` (project
  name). The aggregator keeps per-session state and emits ONE aggregate snapshot:
    - mood     = highest-priority state across sessions (waiting > error > running
                 > thinking > done > idle)
    - total/running/waiting = live session counts (shown on the device)
    - feed     = merged recent tool lines, tagged "label▸…"
  Approvals are queued: one overlay at a time, labelled with its session.

Wire protocol (newline-delimited JSON):
  agent -> device : {"type":"status", sid?, label?, state?, msg?, entry?, hud?}
                    {"type":"approve", id, sid?, label?, tool, hint}
  device -> agent : {"decision": "allow"|"deny"|"ask"}   (reply to approve)
"""
import asyncio
import json
import logging
import time
from collections import deque
from typing import Awaitable, Callable

log = logging.getLogger("companion.net")

APPROVE_TIMEOUT = 100.0
HEARTBEAT_S = 15.0        # keep the "connected" face alive + prune stale sessions
SESSION_TTL = 120.0       # drop a session with no events for this long
DONE_DECAY_S = 5.0        # a finished session falls back to idle after this

_PRIORITY = {"waiting": 0, "error": 1, "running": 2, "thinking": 3,
             "done": 4, "idle": 5, "offline": 6, "disconnected": 6}


def _snapshot(*, state, total, running, waiting, msg, prompt, entries, hud) -> str:
    return json.dumps({
        "state": state, "total": total, "running": running, "waiting": waiting,
        "msg": msg, "entries": list(entries), "tokens": 0, "tokens_today": 0,
        "prompt": prompt, "hud": hud,
    }) + "\n"


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


class Bridge:
    def __init__(self, send_snapshot: Callable[[str], Awaitable[None]]):
        self._send = send_snapshot
        self._sessions: dict[str, dict] = {}   # sid -> {state,label,ts}
        self._feed: deque[str] = deque(maxlen=8)
        self._hud: dict | None = None
        # approval queue
        self._pending: dict[str, asyncio.Future] = {}   # id -> future
        self._prompts: dict[str, dict] = {}             # id -> {tool,hint,label}
        self._queue: deque[str] = deque()               # ids waiting to be shown
        self._active: str | None = None                 # id currently on screen

    # ---- session state ----
    def _touch(self, sid: str, label: str | None, state: str | None, now: float) -> None:
        s = self._sessions.setdefault(sid, {"state": "idle", "label": "", "ts": now})
        if label:
            s["label"] = label
        if state is not None:
            s["state"] = state
        s["ts"] = now

    def _prune(self, now: float) -> None:
        stale = [sid for sid, s in self._sessions.items() if now - s["ts"] > SESSION_TTL]
        for sid in stale:
            del self._sessions[sid]

    def _agg_state(self) -> str:
        if not self._sessions:
            return "idle"
        return min((s["state"] for s in self._sessions.values()),
                   key=lambda st: _PRIORITY.get(st, 5))

    def _counts(self) -> tuple[int, int, int]:
        total = len(self._sessions)
        running = sum(1 for s in self._sessions.values() if s["state"] in ("running", "thinking"))
        waiting = sum(1 for s in self._sessions.values() if s["state"] == "waiting")
        return total, running, waiting

    def _state_snapshot(self) -> str:
        total, running, waiting = self._counts()
        st = self._agg_state()
        return _snapshot(state=st, total=max(total, 1), running=running, waiting=waiting,
                         msg=f"{total} sessions" if total > 1 else st,
                         prompt=None, entries=self._feed, hud=self._hud)

    async def _emit(self) -> None:
        if self._active is not None:          # an approval overlay is showing
            return
        await self._send(self._state_snapshot())

    async def push_event(self, sid=None, label=None, state=None, msg=None,
                         entry=None, hud=None) -> None:
        now = time.monotonic()
        if hud:
            self._hud = hud
        if entry:
            self._feed.append(f"{label}▸{entry}" if label else entry)
        key = sid or "_"
        self._touch(key, label, state, now)
        if state == "done":
            asyncio.ensure_future(self._decay(key))
        self._prune(now)
        await self._emit()

    async def _decay(self, sid: str) -> None:
        try:
            await asyncio.sleep(DONE_DECAY_S)
        except asyncio.CancelledError:
            return
        s = self._sessions.get(sid)
        if s and s["state"] == "done":
            s["state"] = "idle"
            await self._emit()

    # ---- approvals (queued, one overlay at a time) ----
    async def _show_prompt(self, pid: str) -> None:
        p = self._prompts[pid]
        hint = f"{p['label']}▸{p['hint']}" if p.get("label") else p["hint"]
        await self._send(_snapshot(state="waiting", total=max(len(self._sessions), 1),
                                   running=0, waiting=1, msg=f"approve: {p['tool']}",
                                   prompt={"id": pid, "tool": p["tool"], "hint": hint},
                                   entries=self._feed, hud=self._hud))

    async def _advance(self) -> None:
        while self._queue:
            nxt = self._queue[0]
            if nxt in self._pending:
                self._active = nxt
                await self._show_prompt(nxt)
                return
            self._queue.popleft()
        self._active = None
        await self._emit()   # no more prompts → back to aggregate face

    async def request_approval(self, req_id, tool, hint, timeout, sid=None, label=None) -> str:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut
        self._prompts[req_id] = {"tool": tool, "hint": hint, "label": label or ""}
        self._queue.append(req_id)
        if self._active is None:
            await self._advance()
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return "ask"
        finally:
            self._pending.pop(req_id, None)
            self._prompts.pop(req_id, None)
            try:
                self._queue.remove(req_id)
            except ValueError:
                pass
            if self._active == req_id:
                await self._advance()

    def on_device_line(self, line: str) -> None:
        """A device Y/N decision resolves the currently-shown approval."""
        p = parse_permission(line)
        if not p:
            return
        fut = self._pending.get(p["id"])
        if fut and not fut.done():
            fut.set_result(decision_to_hook(p["decision"]))

    async def heartbeat(self) -> None:
        self._prune(time.monotonic())
        await self._emit()

    def fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result("ask")


class NetTransport:
    """Owns a Bridge and an asyncio TCP server. `on_snapshot` injects snapshot
    lines into the UI; device decisions come back via `on_device_line`."""

    def __init__(self, on_snapshot: Callable[[str], None], host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self._on_snapshot = on_snapshot
        self.bridge = Bridge(self._send_snapshot)
        self._server: asyncio.AbstractServer | None = None

    async def _send_snapshot(self, line: str) -> None:
        self._on_snapshot(line.rstrip("\n"))

    def on_device_line(self, line: str) -> None:
        self.bridge.on_device_line(line)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("agent connected: %s", peer)
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                try:
                    req = json.loads(raw.decode("utf-8"))
                except (ValueError, TypeError):
                    continue
                t = req.get("type")
                if t == "approve":
                    decision = await self.bridge.request_approval(
                        req.get("id", "?"), req.get("tool", "?"), req.get("hint", ""),
                        APPROVE_TIMEOUT, sid=req.get("sid"), label=req.get("label"))
                    writer.write((json.dumps({"decision": decision}) + "\n").encode("utf-8"))
                    await writer.drain()
                elif t == "status":
                    await self.bridge.push_event(
                        sid=req.get("sid"), label=req.get("label"),
                        state=req.get("state"),
                        msg=req.get("msg") if "msg" in req else None,
                        entry=req.get("entry"), hud=req.get("hud"))
                    writer.write(b'{"decision":"ask"}\n')
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception as e:  # noqa: BLE001 — never kill the UI on a bad client
            log.info("handler error: %s", e)
        finally:
            try:
                writer.close()
            except Exception:
                pass
            log.info("agent disconnected: %s", peer)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info("listening on %s:%s", self.host, self.port)
        asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            try:
                await self.bridge.heartbeat()
            except Exception:
                pass

    async def send_line(self, line: str) -> None:
        self.on_device_line(line)
