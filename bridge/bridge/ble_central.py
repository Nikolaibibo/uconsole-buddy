"""BLE-Central (bleak): verbindet sich mit dem uConsole-Peripheral, NUS-Serial."""
import asyncio
import logging
from typing import Callable
from bleak import BleakScanner, BleakClient
from .framing import LineReassembler, chunk_for_mtu

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # zum Auffinden (Name unzuverlässig)
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # WRITE (Central → Gerät)
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # NOTIFY (Gerät → Central)

RECONNECT_BACKOFF = (2.0, 4.0, 8.0, 15.0)  # Sekunden; letzter Wert wird wiederholt (Cap)
PROBE_TIMEOUT = 3.0   # so lange darf das Geraet fuer den status-Ack brauchen
HEARTBEAT_S = 60.0    # Abstand der Lebendkontrolle auf einer stehenden Strecke
PROBE = b'{"cmd": "status"}\n'  # das Geraet antwortet darauf mit {"ack":"status"}

log = logging.getLogger("bridge.ble")


class BleCentral:
    def __init__(
        self,
        on_line: Callable[[str], None],
        device_name: str = "Claude-uConsole",
        on_disconnect: Callable[[], None] | None = None,
        finder=None,
        client_factory=None,
        probe_timeout: float = PROBE_TIMEOUT,
        heartbeat_s: float | None = HEARTBEAT_S,
    ):
        self._on_line = on_line
        self._on_disconnect = on_disconnect
        self._name = device_name
        self._reasm = LineReassembler()
        self._client: BleakClient | None = None
        self._connected = False
        self._reconnect_task: asyncio.Task | None = None
        # Einspeisbar, damit die Verbindungslogik ohne Hardware testbar ist.
        self._finder = finder or self._find_device
        self._client_factory = client_factory or BleakClient
        self._probe_timeout = probe_timeout
        self._heartbeat_s = heartbeat_s
        self._heartbeat_task: asyncio.Task | None = None
        self._answered = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    async def _find_device():
        return await BleakScanner.find_device_by_filter(
            lambda d, ad: NUS_SERVICE.lower() in [u.lower() for u in (ad.service_uuids or [])],
            timeout=15.0)

    async def _probe(self) -> bool:
        """status an das Geraet schicken und auf irgendeine Antwort warten.

        Der eigentliche Test der Strecke: `connect()` und `start_notify()` koennen
        auf macOS erfolgreich zurueckkehren, ohne dass eine Verbindung existiert
        (beobachtet 07.09.2026, das Geraet meldete dabei null Connections). Erst
        eine Antwort beweist, dass wirklich etwas fliesst."""
        self._answered.clear()
        try:
            await self._client.write_gatt_char(NUS_RX, PROBE, response=False)
            await asyncio.wait_for(self._answered.wait(), self._probe_timeout)
            return True
        except Exception:
            return False

    async def connect(self) -> None:
        # Alten Client sauber loslassen, sonst hält macOS/CoreBluetooth ein stale Handle,
        # das den Reconnect in einen TimeoutError laufen lässt.
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
        dev = await self._finder()
        if dev is None:
            raise RuntimeError(f"kein Gerät mit NUS-Service {NUS_SERVICE} gefunden")
        self._client = self._client_factory(dev, disconnected_callback=self._on_disc)
        await self._client.connect()
        await self._client.start_notify(NUS_TX, self._rx)
        if not await self._probe():
            # Nicht als verbunden markieren — sonst laeuft der Daemon stumm weiter
            # und die Reconnect-Schleife startet nie.
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            raise RuntimeError("kein status-Ack — Verbindung meldet sich nicht")
        self._connected = True
        self._start_heartbeat()

    def _rx(self, _char, data: bytearray) -> None:
        self._answered.set()   # irgendetwas kam an -> die Strecke lebt
        for line in self._reasm.feed(bytes(data)):
            self._on_line(line)

    def _start_heartbeat(self) -> None:
        if self._heartbeat_s and (self._heartbeat_task is None
                                  or self._heartbeat_task.done()):
            self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Lebendkontrolle auf einer stehenden Strecke. Zwei unbeantwortete Proben
        hintereinander gelten als tot — eine einzelne kann an Funk oder Last liegen."""
        misses = 0
        while self._connected:
            await asyncio.sleep(self._heartbeat_s)
            if not self._connected:
                return
            if await self._probe():
                misses = 0
                continue
            misses += 1
            log.info("Lebendkontrolle ohne Antwort (%d)", misses)
            if misses >= 2:
                log.info("BLE stumm — erzwinge Reconnect")
                self._trigger_reconnect()
                return

    def stop(self) -> None:
        """Heartbeat und Reconnect beenden (Tests, sauberes Herunterfahren)."""
        self._connected = False
        for t in (self._heartbeat_task, self._reconnect_task):
            if t is not None and not t.done():
                t.cancel()

    def _trigger_reconnect(self) -> None:
        """Als getrennt markieren + Reconnect-Loop starten (idempotent). Von _on_disc UND
        vom Send-Fehler-Pfad genutzt — falls bleaks disconnected_callback mal nicht feuert."""
        self._connected = False
        if self._on_disconnect is not None:
            self._on_disconnect()
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    def _on_disc(self, _client: BleakClient) -> None:
        """bleak-Callback bei ungeplantem Verbindungsverlust. Synchron — keine awaits hier."""
        log.info("BLE disconnected")
        self._trigger_reconnect()

    async def _reconnect_loop(self) -> None:
        attempt = 0
        while not self._connected:
            delay = RECONNECT_BACKOFF[min(attempt, len(RECONNECT_BACKOFF) - 1)]
            log.info("reconnect attempt %d in %.0fs", attempt + 1, delay)
            await asyncio.sleep(delay)
            try:
                await self.connect()
                log.info("BLE reconnected")
            except Exception as e:
                log.info("reconnect failed: %s", e)
                attempt += 1

    async def send_line(self, line: str) -> None:
        if self._client is None or not self._connected:
            return  # nicht verbunden — Reconnect läuft; Snapshot verwerfen statt crashen
        data = line.encode("utf-8")
        mtu = getattr(self._client, "mtu_size", 23) or 23
        try:
            for chunk in chunk_for_mtu(data, mtu):
                await self._client.write_gatt_char(NUS_RX, chunk, response=False)
                await asyncio.sleep(0.01)
        except Exception as e:
            # Toter Link: Send scheitert oft, BEVOR bleaks disconnected_callback feuert.
            # Selbst als Disconnect behandeln → Reconnect-Loop anwerfen.
            log.info("send failed (%s) — treating as disconnect", e)
            self._trigger_reconnect()

    async def disconnect(self) -> None:
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
        if self._client:
            await self._client.disconnect()
