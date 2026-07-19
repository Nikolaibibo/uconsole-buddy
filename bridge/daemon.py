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
