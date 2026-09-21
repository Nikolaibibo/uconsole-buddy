# companion/tcp_nus.py
"""TCP-Peripheral im WLAN — gleicher Vertrag wie `NusPeripheral`, ohne BLE.

Warum: Host und Gerät hängen im selben Netz. BLE löst damit ein Problem, das
nicht mehr existiert, kostet aber Pairing-Zicken und einen fest gepinnten
Adapter. Das Zeilenprotokoll (`framing.LineReassembler`) ist transportneutral
und bleibt unverändert — getauscht wird nur die Röhre.

Sicherheit: das WLAN ersetzt das BLE-Pairing nicht. Wer im Netz ist, könnte
sonst Snapshots schicken. Deshalb muss die erste Zeile `{"auth": "<secret>"}`
sein; ohne `secret=` (None) entfällt die Prüfung.
"""
import asyncio
import json
import logging
from typing import Callable, Optional

from .framing import LineReassembler

log = logging.getLogger("companion.tcp")

DEFAULT_PORT = 8766


class TcpPeripheral:
    def __init__(self, device_name: str, on_line: Callable[[str], None],
                 host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 secret: Optional[str] = None) -> None:
        self.device_name = device_name
        self._on_line = on_line
        self._host = host
        self._requested_port = port
        self.port = port
        self._secret = secret
        self._server: Optional[asyncio.AbstractServer] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self._host, self._requested_port)
        # Bei Port 0 vergibt das OS den Port — der echte Wert steht erst jetzt fest.
        self.port = self._server.sockets[0].getsockname()[1]
        log.info("listening on %s:%s", self._host, self.port)

    def _accepts(self, line: str) -> bool:
        try:
            return json.loads(line).get("auth") == self._secret
        except (ValueError, AttributeError):
            return False

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        reasm = LineReassembler()
        authed = self._secret is None
        if authed:
            self._adopt(writer)
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                for line in reasm.feed(data):
                    if not authed:
                        if not self._accepts(line):
                            log.warning("rejecting %s: bad auth", peer)
                            return
                        authed = True
                        self._adopt(writer)
                        continue
                    self._on_line(line)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            if self._writer is writer:
                self._writer = None
                log.info("client %s disconnected", peer)
            writer.close()

    def _adopt(self, writer: asyncio.StreamWriter) -> None:
        """Übernimmt den neuen Client. Wie bei BLE gilt: genau ein Central."""
        old = self._writer
        if old is not None and old is not writer:
            old.close()
        self._writer = writer
        log.info("client %s connected", writer.get_extra_info("peername"))

    async def send_line(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        writer = self._writer
        if writer is None:
            return
        try:
            writer.write(line.encode("utf-8"))
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self._writer = None

    def is_connected(self) -> bool:
        return self._writer is not None

    async def stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
