"""Transport-Tests für den TCP-Peripheral (Ersatz für BLE im WLAN-Betrieb).

Kein Netzwerkgerät nötig: Server bindet auf 127.0.0.1 mit Port 0 (ephemer).
"""
import asyncio

from companion.tcp_nus import TcpPeripheral

SECRET = "s3cret"


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5))


async def _connect(peripheral, secret=SECRET):
    reader, writer = await asyncio.open_connection("127.0.0.1", peripheral.port)
    if secret is not None:
        writer.write(('{"auth":"%s"}\n' % secret).encode())
        await writer.drain()
    return reader, writer


def test_received_line_is_passed_to_callback():
    received: list[str] = []

    async def scenario():
        p = TcpPeripheral("test", received.append, host="127.0.0.1", port=0, secret=SECRET)
        await p.start()
        _, writer = await _connect(p)
        writer.write(b'{"cmd":"status"}\n')
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.close()
        await p.stop()

    _run(scenario())
    assert received == ['{"cmd":"status"}']


def test_send_line_reaches_connected_client():
    async def scenario():
        p = TcpPeripheral("test", lambda _l: None, host="127.0.0.1", port=0, secret=SECRET)
        await p.start()
        reader, writer = await _connect(p)
        await asyncio.sleep(0.1)
        await p.send_line('{"ack":"status"}')
        line = await reader.readline()
        writer.close()
        await p.stop()
        return line

    assert _run(scenario()) == b'{"ack":"status"}\n'


def test_client_with_wrong_secret_is_rejected():
    received: list[str] = []

    async def scenario():
        p = TcpPeripheral("test", received.append, host="127.0.0.1", port=0, secret=SECRET)
        await p.start()
        _, writer = await _connect(p, secret="falsch")
        writer.write(b'{"cmd":"status"}\n')
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        await asyncio.sleep(0.1)
        connected = p.is_connected()
        writer.close()
        await p.stop()
        return connected

    assert _run(scenario()) is False
    assert received == []


def test_line_split_across_packets_is_reassembled():
    received: list[str] = []

    async def scenario():
        p = TcpPeripheral("test", received.append, host="127.0.0.1", port=0, secret=SECRET)
        await p.start()
        _, writer = await _connect(p)
        writer.write(b'{"cmd":')
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.write(b'"status"}\n')
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.close()
        await p.stop()

    _run(scenario())
    assert received == ['{"cmd":"status"}']


def test_is_connected_false_before_any_client():
    async def scenario():
        p = TcpPeripheral("test", lambda _l: None, host="127.0.0.1", port=0, secret=SECRET)
        await p.start()
        connected = p.is_connected()
        await p.stop()
        return connected

    assert _run(scenario()) is False
