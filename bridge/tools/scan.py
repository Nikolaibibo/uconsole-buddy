"""Diagnose: listet ALLE BLE-Geräte, die bleak sieht (Name + Service-UUIDs + RSSI)."""
import asyncio
from bleak import BleakScanner


async def main():
    print("scanne 10s ...")
    devs = await BleakScanner.discover(timeout=10.0, return_adv=True)
    print(f"\n{len(devs)} Geräte gefunden:")
    for addr, (d, adv) in devs.items():
        name = d.name or (adv.local_name if adv else None)
        print(f"  {addr}  name={name!r}  rssi={getattr(adv,'rssi',None)}")
        if adv and adv.service_uuids:
            print(f"        uuids={adv.service_uuids}")
    if len(devs) == 0:
        print("\n⚠ 0 Geräte = wahrscheinlich fehlende Bluetooth-Freigabe fürs Terminal "
              "(Systemeinstellungen → Datenschutz → Bluetooth).")


asyncio.run(main())
