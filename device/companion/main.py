# companion/main.py
import asyncio
import logging
import os
import time

# NusPeripheral is imported lazily in _build_transport so TCP mode works
# without bluez installed.
from .notify import NotifyDecider, play
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
        self.transport = self._build_transport()
        self.notifier = NotifyDecider()
        self._assets = os.path.join(os.path.dirname(__file__), "assets")
        self.app = CompanionApp(on_decision=self._on_decision, on_mute=self._toggle_mute)
        self._send_q: asyncio.Queue[str] = asyncio.Queue()

    def _build_transport(self):
        """Pick transport from $UCONSOLE_TRANSPORT (default 'ble').

        tcp: direct TCP server on $UCONSOLE_LISTEN (default 0.0.0.0:8765) — for
             remote/overlay (e.g. Tailscale) setups; no BLE, no bridge daemon.
        ble: Nordic-UART BLE peripheral (original desk-companion mode).
        """
        transport = os.environ.get("UCONSOLE_TRANSPORT", "ble").lower()
        if transport == "tcp":
            from .net_server import NetTransport
            listen = os.environ.get("UCONSOLE_LISTEN", "0.0.0.0:8765")
            host, _, port = listen.rpartition(":")
            self._transport_kind = "tcp"
            self._listen = listen
            return NetTransport(self._on_line, host=host or "0.0.0.0", port=int(port))
        from .ble_nus import NusPeripheral
        self._transport_kind = "ble"
        return NusPeripheral("Claude-uConsole", self._on_line)

    # ---- RX ----
    def _on_line(self, line: str) -> None:
        log.info("RX %s", line)
        msg = parse_message(line)
        if msg is None:
            return
        if "total" in msg:                      # Heartbeat-Snapshot
            now = time.monotonic()
            self.state.apply_snapshot(msg, now=now)
            channel = self.notifier.decide(self.state.mood_state(now), now)
            if channel:
                play(channel, self._assets)
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

    def _toggle_mute(self) -> None:
        self.notifier.muted = not self.notifier.muted
        self.app._muted = self.notifier.muted
        self._rerender()

    # ---- Loops ----
    async def _tx_loop(self) -> None:
        while True:
            line = await self._send_q.get()
            await self.transport.send_line(line)
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
        await self.transport.start()
        if self._transport_kind == "tcp":
            log.info("listening for agents on %s", self._listen)
        else:
            log.info("advertising as Claude-uConsole")
        asyncio.create_task(self._tx_loop())
        asyncio.create_task(self._tick_loop())
        await self.app.run_async()


def main() -> None:
    asyncio.run(Companion().run())


if __name__ == "__main__":
    main()
