"""TCP-Central: verbindet sich über WLAN mit dem uConsole-Peripheral.

Gegenstück zu `device/companion/tcp_nus.py`. Gleicher Vertrag wie `BleCentral`,
damit `daemon.py` nicht merkt, welche Röhre dranhängt. Das Zeilenprotokoll ist
transportneutral und bleibt unverändert — getauscht wird nur der Transport.
"""
import asyncio
import json
import logging
from typing import Callable

from .framing import LineReassembler

DEFAULT_PORT = 8766
PROBE_TIMEOUT = 3.0   # so lange darf das Gerät für den status-Ack brauchen
PROBE = '{"cmd": "status"}'  # das Gerät antwortet darauf mit {"ack":"status"}
RECONNECT_BACKOFF = (2.0, 4.0, 8.0, 15.0)  # Sekunden; letzter Wert wird wiederholt (Cap)

log = logging.getLogger("bridge.tcp")


class TcpCentral:
    def __init__(
        self,
        on_line: Callable[[str], None],
        host: str,
        port: int = DEFAULT_PORT,
        secret: str = "",
        on_disconnect: Callable[[], None] | None = None,
        probe_timeout: float = PROBE_TIMEOUT,
        reconnect_backoff: tuple[float, ...] = RECONNECT_BACKOFF,
    ):
        self._backoff = reconnect_backoff
        self._reconnect_task: asyncio.Task | None = None
        self._closing = False
        self._on_line = on_line
        self._on_disconnect = on_disconnect
        self._host = host
        self._port = port
        self._secret = secret
        self._probe_timeout = probe_timeout
        self._reasm = LineReassembler()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._rx_task: asyncio.Task | None = None
        self._connected = False
        self._answered = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._closing = False
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        # Die auth-Zeile muss vor allem anderen raus — sonst trennt das Gerät.
        await self._send_raw(json.dumps({"auth": self._secret}))
        self._rx_task = asyncio.ensure_future(self._rx_loop())
        if not await self._probe():
            # Nicht als verbunden markieren — sonst läuft der Daemon stumm weiter
            # und die Reconnect-Schleife startet nie.
            await self._teardown()
            raise RuntimeError("kein status-Ack — Verbindung meldet sich nicht")
        self._connected = True

    async def _probe(self) -> bool:
        """status schicken und auf irgendeine Antwort warten.

        Der eigentliche Test der Strecke: ein offener Socket beweist nur, dass
        jemand `accept()` gerufen hat. Erst eine Antwort beweist, dass die
        Gegenseite lebt und das Protokoll spricht."""
        self._answered.clear()
        try:
            await self._send_raw(PROBE)
            await asyncio.wait_for(self._answered.wait(), self._probe_timeout)
            return True
        except Exception:
            return False

    async def _rx_loop(self) -> None:
        try:
            while True:
                data = await self._reader.read(4096)
                if not data:
                    break
                self._answered.set()   # irgendetwas kam an -> die Strecke lebt
                for line in self._reasm.feed(data):
                    self._on_line(line)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        # Hier angekommen heißt: die Strecke ist zu. War es Absicht, hat
        # disconnect() den Task ohnehin abgebrochen und wir stehen nicht hier.
        if not self._closing:
            self._trigger_reconnect()

    def _trigger_reconnect(self) -> None:
        if self._connected:
            self._connected = False
            if self._on_disconnect is not None:
                self._on_disconnect()
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        for delay in self._delays():
            await asyncio.sleep(delay)
            if self._closing:
                return
            try:
                await self.connect()
                log.info("reconnected to %s:%s", self._host, self._port)
                return
            except Exception as e:
                log.info("reconnect failed (%s) — retrying", e)

    def _delays(self):
        yield from self._backoff
        while True:              # letzter Wert ist der Cap, nicht das Ende
            yield self._backoff[-1]

    async def send_line(self, line: str) -> None:
        if self._writer is None or not self._connected:
            return  # nicht verbunden — Snapshot verwerfen statt crashen
        try:
            await self._send_raw(line)
        except Exception as e:
            # Ein toter Link scheitert oft beim Senden, bevor die Lese-Schleife
            # das EOF sieht. Selbst als Abbruch behandeln statt zu warten.
            log.info("send failed (%s) — treating as disconnect", e)
            self._trigger_reconnect()

    async def _send_raw(self, line: str) -> None:
        self._writer.write((line + "\n").encode("utf-8"))
        await self._writer.drain()

    async def _teardown(self) -> None:
        self._connected = False
        if self._rx_task is not None:
            self._rx_task.cancel()
            self._rx_task = None
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass
            self._writer = None

    async def disconnect(self) -> None:
        self._closing = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        await self._teardown()
