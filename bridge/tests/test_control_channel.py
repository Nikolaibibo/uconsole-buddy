"""Die Strecke Hook → Daemon, end to end.

Bisher ungetestet — und genau deshalb ist niemandem aufgefallen, dass
`daemon.py` und `hooks/_send.py` auf zwei verschiedene Sockets zeigten.
Der Test fährt einen echten Server hoch und schickt mit demselben Code,
den die Hooks benutzen.
"""
import asyncio

import _send
from bridge.daemon import Bridge, start_control_server


def run(coro):
    return asyncio.run(coro)


def make_bridge():
    sent: list[str] = []

    async def send_snapshot(line):
        sent.append(line)

    return Bridge(send_snapshot), sent


def test_status_from_a_hook_reaches_the_bridge():
    result = {}

    async def scenario():
        bridge, sent = make_bridge()
        server = await start_control_server(bridge, ("127.0.0.1", 0))
        port = server.sockets[0].getsockname()[1]

        # _send ist blockierend (die Hooks sind kurzlebige Prozesse) — deshalb
        # in einen Thread, statt den Loop anzuhalten.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _send.deliver(
            {"type": "status", "state": "thinking", "msg": "denkt nach"},
            ("127.0.0.1", port)))

        await asyncio.sleep(0.1)
        server.close()
        await server.wait_closed()
        result["sent"] = sent

    run(scenario())

    assert any('"thinking"' in s for s in result["sent"]), \
        f"Zustand kam nicht in der Bridge an: {result['sent']}"


def test_deliver_survives_a_dead_daemon():
    """Hooks sind fire-and-forget. Läuft der Daemon nicht, darf der Hook
    trotzdem nicht scheitern — sonst blockiert er Claude Code."""
    _send.deliver({"type": "status", "state": "idle"}, ("127.0.0.1", 1))
