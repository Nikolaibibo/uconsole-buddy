"""Direct TCP transport for the companion — no BLE, no separate bridge daemon.

For remote setups (agent on one host, uConsole on another, linked over a private
overlay such as Tailscale) the BLE central/peripheral split does not work: BLE is
short-range and needs a machine next to the device. This module collapses the
former host-side bridge daemon INTO the device app: it runs the same event
aggregator (`Bridge`) plus an asyncio TCP server, so an agent extension/hook can
connect directly and speak the exact same JSON protocol as the unix socket.

Wire protocol (newline-delimited JSON), identical to bridge/bridge/protocol.py:
  agent -> device : {"type":"status", state?, msg?, entry?, hud?}
                    {"type":"approve", id, tool, hint}
  device -> agent : {"decision": "allow"|"deny"|"ask"}   (reply to approve)

Snapshots produced by the aggregator are injected into the UI via the
`on_snapshot(line)` callback (the same line format the BLE path receives).
Device Y/N decisions are fed back in via `on_device_line(line)`.
"""
import asyncio
import json
import logging
from collections import deque
from typing import Awaitable, Callable

log = logging.getLogger("companion.net")

APPROVE_TIMEOUT = 100.0
HEARTBEAT_S = 15.0  # keep the "connected" face alive between events


# ---- Snapshot / permission builders (mirror of bridge/bridge/protocol.py) ----
def build_snapshot(*, state="idle", total=1, running=0, waiting=0, msg="",
                   prompt=None, tokens=0, tokens_today=0, entries=None, hud=None) -> str:
    return json.dumps({
        "state": state, "total": total, "running": running, "waiting": waiting,
        "msg": msg, "entries": entries or [], "tokens": tokens,
        "tokens_today": tokens_today, "prompt": prompt, "hud": hud,
    }) + "\n"


def build_prompt_snapshot(prompt_id: str, tool: str, hint: str) -> str:
    return build_snapshot(state="waiting", total=1, running=0, waiting=1,
                          msg=f"approve: {tool}",
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


# ---- Aggregator (mirror of bridge/bridge/daemon.py Bridge) --------------------
class Bridge:
    def __init__(self, send_snapshot: Callable[[str], Awaitable[None]]):
        self._send = send_snapshot
        self._pending: dict[str, asyncio.Future] = {}
        self._state = "idle"
        self._msg = "idle"
        self._entries: deque[str] = deque(maxlen=8)
        self._hud: dict | None = None
        self._idle_task = None

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

    def on_device_line(self, line: str) -> None:
        """A device Y/N decision (build_permission line) resolves a pending approval."""
        p = parse_permission(line)
        if not p:
            return
        fut = self._pending.get(p["id"])
        if fut and not fut.done():
            fut.set_result(decision_to_hook(p["decision"]))

    def _build_state_snapshot(self) -> str:
        return build_snapshot(
            state=self._state, total=1,
            running=1 if self._state in ("running", "thinking") else 0,
            waiting=1 if self._state == "waiting" else 0,
            msg=self._msg, entries=list(self._entries), hud=self._hud,
        )

    async def push_event(self, state=None, msg=None, entry=None, decay=5.0, hud=None) -> None:
        if hud:
            self._hud = hud
        if entry:
            self._entries.append(entry)
        if state is not None:
            self._state = state
            self._cancel_decay()
            if state == "done":
                self._idle_task = asyncio.ensure_future(self._decay_to_idle(decay))
        if msg is not None:
            self._msg = msg
        if self._pending:  # active approval overlay wins
            return
        await self._send(self._build_state_snapshot())

    async def heartbeat(self) -> None:
        if not self._pending:
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

    def fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result("ask")
        self._pending.clear()


# ---- TCP transport shell ------------------------------------------------------
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
        # Bridge is async; the UI callback is sync.
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
                        req.get("id", "?"), req.get("tool", "?"), req.get("hint", ""), APPROVE_TIMEOUT)
                    writer.write((json.dumps({"decision": decision}) + "\n").encode("utf-8"))
                    await writer.drain()
                elif t == "status":
                    await self.bridge.push_event(
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
            self.bridge.fail_pending()
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

    # Symmetry with NusPeripheral.send_line so main.py can treat both the same.
    async def send_line(self, line: str) -> None:
        self.on_device_line(line)
