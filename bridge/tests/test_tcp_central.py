"""TCP-Transport auf der Bridge-Seite — Gegenstück zu device/companion/tcp_nus.py.

Getestet wird gegen einen echten asyncio-Server auf 127.0.0.1, nicht gegen einen
Mock: der Fehler, den diese Schicht fangen muss (Strecke tot, aber „verbunden"
gemeldet — der Phantom-Connect vom 07.09.), sitzt genau in der Socket-Schicht.
Ein Mock würde ihn wegdefinieren.
"""
import asyncio
import json

from bridge.tcp_central import TcpCentral


def run(coro):
    return asyncio.run(coro)


class FakeDevice:
    """Echter TCP-Server, der sich wie `companion/tcp_nus.TcpPeripheral` verhält.

    `answer_probe=False` stellt ein Gerät dar, das die Verbindung annimmt, aber
    nicht antwortet — die Phantom-Verbindung.
    """

    def __init__(self, answer_probe: bool = True) -> None:
        self.answer_probe = answer_probe
        self.lines: list[str] = []
        self._server = None
        self._writer = None
        self.connections = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]

    async def _handle(self, reader, writer) -> None:
        self.connections += 1
        self._writer = writer
        buf = b""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8")
                    self.lines.append(line)
                    await self._maybe_ack(line, writer)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            # Seit Python 3.12 wartet Server.wait_closed() wirklich auf offene
            # Verbindungen. Ohne dieses close() haengt stop() fuer immer.
            writer.close()

    async def _maybe_ack(self, line: str, writer) -> None:
        if not self.answer_probe:
            return
        try:
            is_probe = json.loads(line).get("cmd") == "status"
        except (ValueError, AttributeError):
            return
        if is_probe:
            writer.write(b'{"ack": "status"}\n')
            await writer.drain()

    async def drop(self) -> None:
        """Gerät schließt die Verbindung — Absturz, Neustart, WLAN weg."""
        if self._writer is not None:
            self._writer.close()

    async def send(self, line: str) -> None:
        self._writer.write((line + "\n").encode("utf-8"))
        await self._writer.drain()

    async def stop(self) -> None:
        self._server.close()
        await self._server.wait_closed()


def test_sends_auth_line_first():
    """Ohne die auth-Zeile trennt das Gerät — sie muss vor allem anderen raus."""
    dev = FakeDevice()

    async def scenario():
        port = await dev.start()
        central = TcpCentral(lambda _line: None, host="127.0.0.1", port=port,
                             secret="s3cr3t")
        await central.connect()
        await central.disconnect()
        await dev.stop()

    run(scenario())

    assert dev.lines, "Gerät hat keine einzige Zeile gesehen"
    assert json.loads(dev.lines[0]) == {"auth": "s3cr3t"}


def test_connect_refuses_a_link_that_never_answers():
    """Der Phantom-Connect vom 07.09.: der Socket steht, aber nichts fließt.

    Über TCP ist das seltener als über CoreBluetooth, aber nicht unmöglich —
    ein hängendes Gerät nimmt die Verbindung an und antwortet nie. Wer sich
    dann als verbunden meldet, läuft stumm weiter und reconnected nie.
    """
    dev = FakeDevice(answer_probe=False)
    failed = []

    async def scenario():
        port = await dev.start()
        central = TcpCentral(lambda _line: None, host="127.0.0.1", port=port,
                             secret="x", probe_timeout=0.2)
        try:
            await central.connect()
        except RuntimeError as exc:
            failed.append(str(exc))
        assert not central.is_connected
        await central.disconnect()
        await dev.stop()

    run(scenario())

    assert failed, "connect() hätte ohne Ack scheitern müssen"


def test_connect_succeeds_when_device_acks():
    """Die Gegenprobe: antwortet das Gerät, gilt die Strecke als verbunden."""
    dev = FakeDevice(answer_probe=True)

    async def scenario():
        port = await dev.start()
        central = TcpCentral(lambda _line: None, host="127.0.0.1", port=port,
                             secret="x", probe_timeout=2.0)
        await central.connect()
        assert central.is_connected
        await central.disconnect()
        await dev.stop()

    run(scenario())

    probes = [l for l in dev.lines if json.loads(l).get("cmd") == "status"]
    assert probes, "connect() hat nie eine status-Probe geschickt"


def test_send_line_reaches_the_device():
    dev = FakeDevice()

    async def scenario():
        port = await dev.start()
        central = TcpCentral(lambda _line: None, host="127.0.0.1", port=port,
                             secret="x", probe_timeout=2.0)
        await central.connect()
        await central.send_line('{"type": "snapshot", "state": "thinking"}')
        await asyncio.sleep(0.05)
        await central.disconnect()
        await dev.stop()

    run(scenario())

    snapshots = [l for l in dev.lines if json.loads(l).get("type") == "snapshot"]
    assert snapshots == ['{"type": "snapshot", "state": "thinking"}']


def test_send_line_is_dropped_while_disconnected():
    """Snapshots sind fire-and-forget. Ohne Strecke werden sie verworfen, nicht
    gepuffert und nicht geworfen — sonst reißt ein toter Link den Daemon mit."""
    central = TcpCentral(lambda _line: None, host="127.0.0.1", port=1, secret="x")

    async def scenario():
        await central.send_line('{"type": "snapshot"}')   # darf nicht werfen

    run(scenario())

    assert not central.is_connected


def test_device_lines_reach_on_line():
    """Die Gegenrichtung: was das Gerät schickt, muss beim Daemon ankommen."""
    dev = FakeDevice()
    seen: list[str] = []

    async def scenario():
        port = await dev.start()
        central = TcpCentral(seen.append, host="127.0.0.1", port=port,
                             secret="x", probe_timeout=2.0)
        await central.connect()
        await dev.send('{"decision": "allow", "id": "42"}')
        await asyncio.sleep(0.05)
        await central.disconnect()
        await dev.stop()

    run(scenario())

    assert '{"decision": "allow", "id": "42"}' in seen


def test_reports_and_reconnects_when_the_device_drops():
    """Bricht die Strecke weg, muss beides passieren: der Daemon erfährt es
    (wartende Freigaben verfallen) und die Bridge kommt von selbst zurück."""
    dev = FakeDevice()
    dropped: list[int] = []

    async def scenario():
        port = await dev.start()
        central = TcpCentral(lambda _line: None, host="127.0.0.1", port=port,
                             secret="x", probe_timeout=2.0,
                             on_disconnect=lambda: dropped.append(1),
                             reconnect_backoff=(0.05,))
        await central.connect()
        assert dev.connections == 1

        await dev.drop()
        await asyncio.sleep(0.5)

        assert dropped, "on_disconnect wurde nie gerufen"
        assert dev.connections >= 2, "kein Reconnect versucht"
        assert central.is_connected, "Reconnect hat die Strecke nicht wieder aufgebaut"

        await central.disconnect()
        await dev.stop()

    run(scenario())


def test_intentional_disconnect_does_not_reconnect():
    """Sonst kämpft ein gewolltes disconnect() gegen die eigene Reconnect-Schleife."""
    dev = FakeDevice()

    async def scenario():
        port = await dev.start()
        central = TcpCentral(lambda _line: None, host="127.0.0.1", port=port,
                             secret="x", probe_timeout=2.0,
                             reconnect_backoff=(0.05,))
        await central.connect()
        await central.disconnect()
        await asyncio.sleep(0.3)
        assert dev.connections == 1, "disconnect() hat einen Reconnect ausgelöst"
        assert not central.is_connected
        await dev.stop()

    run(scenario())
