# companion/main.py  (PHASE 0 -- wird in Task 1.4 ersetzt)
import asyncio
import logging

from .ble_nus import NusPeripheral

logging.basicConfig(
    filename="companion.log", level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger("companion")


def on_line(line: str) -> None:
    log.info("RX %s", line)
    print("RX", line)


async def _run() -> None:
    ble = NusPeripheral("Claude-uConsole", on_line)
    await ble.start()
    log.info("advertising as Claude-uConsole")
    print("advertising as Claude-uConsole — im Hardware Buddy verbinden")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(_run())
