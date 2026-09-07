"""Der Daemon hat am 07.09. mehrfach 'BLE connected' gemeldet, während das Gerät
null Verbindungen hatte: connect() und start_notify() liefen durch, es floss nur
nie etwas. Diese Tests halten fest, dass eine Verbindung erst zählt, wenn das
Gerät geantwortet hat — und dass eine verstummte Strecke bemerkt wird."""
import asyncio

from bridge.ble_central import BleCentral


def run(coro):
    return asyncio.run(coro)


class FakeClient:
    """Verhält sich wie ein bleak-Client. `answers` ist der ganze Unterschied
    zwischen einer echten und einer Phantom-Verbindung."""

    def __init__(self, answers=True):
        self.answers = answers
        self.connected = False
        self.disconnect_calls = 0
        self.written = []
        self._cb = None

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False
        self.disconnect_calls += 1

    async def start_notify(self, uuid, cb):
        self._cb = cb

    async def write_gatt_char(self, uuid, data, response=False):
        self.written.append(bytes(data))
        if self.answers and self._cb:
            self._cb(uuid, bytearray(b'{"ack":"status","ok":true}\n'))

    @property
    def is_connected(self):
        return self.connected


def make(answers=True, on_disconnect=None, heartbeat=None):
    lines = []
    client = FakeClient(answers=answers)

    async def finder():
        return object()

    c = BleCentral(lines.append, on_disconnect=on_disconnect,
                   finder=finder,
                   client_factory=lambda dev, disconnected_callback=None: client,
                   probe_timeout=0.15, heartbeat_s=heartbeat)
    return c, client, lines


def test_connect_probes_the_device_and_succeeds_on_an_ack():
    async def scenario():
        c, client, _ = make(answers=True)
        await c.connect()
        assert c.is_connected
        assert any(b'"cmd": "status"' in w or b'"cmd":"status"' in w
                   for w in client.written), client.written
    run(scenario())


def test_connect_fails_when_the_device_never_answers():
    """Das ist der Phantom-Connect: alles laeuft durch, nur antwortet niemand."""
    async def scenario():
        c, client, _ = make(answers=False)
        try:
            await c.connect()
        except Exception as e:
            assert "ack" in str(e).lower() or "antwort" in str(e).lower(), e
        else:
            raise AssertionError("connect() haette scheitern muessen")
        assert not c.is_connected
        assert client.disconnect_calls >= 1, "toter Client muss losgelassen werden"
    run(scenario())


def test_a_gone_quiet_link_triggers_a_reconnect():
    """Watchdog: die Strecke steht laut bleak, das Geraet antwortet aber nicht mehr."""
    async def scenario():
        fired = []
        c, client, _ = make(answers=True, on_disconnect=lambda: fired.append(1),
                            heartbeat=0.05)
        await c.connect()
        client.answers = False          # Geraet verstummt
        await asyncio.sleep(0.6)
        assert fired, "kein Reconnect ausgeloest, obwohl die Probe unbeantwortet blieb"
        assert not c.is_connected
        c.stop()
    run(scenario())
