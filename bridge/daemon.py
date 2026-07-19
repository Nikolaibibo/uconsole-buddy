# bridge/daemon.py  (Bridge-Kern; Socket-Server folgt in Task 1.2)
import asyncio
from typing import Awaitable, Callable
from .protocol import (
    build_cleared_snapshot,
    build_prompt_snapshot,
    build_snapshot,
    decision_to_hook,
    parse_permission,
)


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

    async def push_status(self, state: str, msg: str = "") -> None:
        """Status-Snapshot pushen (P2) — nur wenn kein Approval-Prompt aktiv ist,
        damit ein Session/Stop/Notify-Event nie einen laufenden Overlay-Prompt überschreibt."""
        if self._pending:
            return
        await self._send(build_snapshot(
            total=1, running=1 if state == "running" else 0, waiting=0, msg=msg))

    def fail_pending(self) -> None:
        """Bei BLE-Disconnect: alle offenen Approvals fail-safe auf 'ask' auflösen (P3)."""
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result("ask")
        self._pending.clear()


# ---- Daemon-Außenschale: Unix-Socket-Server + BLE-Verdrahtung (Task 1.2) ----
import json, logging, os
from pathlib import Path
from .ble_central import BleCentral

APPROVE_TIMEOUT = 100.0
SOCK = Path(os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock"))
logging.basicConfig(filename="bridge.log", level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bridge")


def _make_handler(bridge: "Bridge"):
    async def handle(reader, writer):
        try:
            raw = await reader.readline()
            req = json.loads(raw.decode("utf-8"))
            if req.get("type") == "approve":
                decision = await bridge.request_approval(
                    req["id"], req.get("tool", "?"), req.get("hint", ""), APPROVE_TIMEOUT)
            elif req.get("type") == "status":
                await bridge.push_status(req.get("state", "idle"), req.get("msg", ""))
                decision = "ask"   # kein Approval — Antwort wird vom fire-and-forget-Hook ignoriert
            else:
                decision = "ask"   # unbekannter Typ — kein Approval
            writer.write((json.dumps({"decision": decision}) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as e:
            log.info("handler error: %s", e)
            try:
                writer.write(b'{"decision":"ask"}\n')
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
    return handle


async def _serve(bridge: "Bridge"):
    SOCK.parent.mkdir(parents=True, exist_ok=True)
    if SOCK.exists():
        SOCK.unlink()
    server = await asyncio.start_unix_server(_make_handler(bridge), path=str(SOCK))
    os.chmod(SOCK, 0o600)
    log.info("socket listening at %s", SOCK)
    print(f"socket listening at {SOCK}")
    async with server:
        await server.serve_forever()


async def _main():
    # bridge und ble referenzieren sich gegenseitig (ble braucht bridge.fail_pending als
    # on_disconnect-Callback, bridge braucht ble.send_line als send_snapshot). Auflösung über
    # dasselbe bridge_ref-Indirektions-Pattern, das on_line schon fuer on_ble_line nutzt.
    bridge_ref: dict = {}

    def on_line(line: str):
        log.info("BLE< %s", line)
        if "bridge" in bridge_ref:
            bridge_ref["bridge"].on_ble_line(line)

    def on_disconnect():
        log.info("BLE disconnected — failing pending approvals")
        if "bridge" in bridge_ref:
            bridge_ref["bridge"].fail_pending()

    ble = BleCentral(on_line, on_disconnect=on_disconnect)
    print("verbinde mit uConsole (NUS) ...")
    await ble.connect()
    log.info("BLE connected to uConsole")
    print("BLE verbunden.")
    bridge = Bridge(lambda s: ble.send_line(s))
    bridge_ref["bridge"] = bridge
    await _serve(bridge)


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
