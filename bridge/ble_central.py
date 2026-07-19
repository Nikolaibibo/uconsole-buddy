"""BLE-Central (bleak): verbindet sich mit dem uConsole-Peripheral, NUS-Serial."""
import asyncio
from typing import Callable
from bleak import BleakScanner, BleakClient
from .framing import LineReassembler, chunk_for_mtu

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"  # zum Auffinden (Name unzuverlässig)
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # WRITE (Central → Gerät)
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # NOTIFY (Gerät → Central)


class BleCentral:
    def __init__(self, on_line: Callable[[str], None], device_name: str = "Claude-uConsole"):
        self._on_line = on_line
        self._name = device_name
        self._reasm = LineReassembler()
        self._client: BleakClient | None = None

    async def connect(self) -> None:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: NUS_SERVICE.lower() in [u.lower() for u in (ad.service_uuids or [])],
            timeout=15.0)
        if dev is None:
            raise RuntimeError(f"kein Gerät mit NUS-Service {NUS_SERVICE} gefunden")
        self._client = BleakClient(dev)
        await self._client.connect()

        def _rx(_char, data: bytearray):
            for line in self._reasm.feed(bytes(data)):
                self._on_line(line)

        await self._client.start_notify(NUS_TX, _rx)

    async def send_line(self, line: str) -> None:
        assert self._client is not None
        data = line.encode("utf-8")
        mtu = getattr(self._client, "mtu_size", 23) or 23
        for chunk in chunk_for_mtu(data, mtu):
            await self._client.write_gatt_char(NUS_RX, chunk, response=False)
            await asyncio.sleep(0.01)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
