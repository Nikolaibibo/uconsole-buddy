"""PoC: verbindet sich mit Claude-uConsole, schickt einen prompt-Snapshot,
wartet auf die permission-Antwort vom Knopfdruck. NICHT committen."""
import asyncio
from bridge.ble_central import BleCentral
from bridge.protocol import build_prompt_snapshot, build_cleared_snapshot, parse_permission

got = asyncio.Event()
result = {}


def on_line(line):
    print("FROM DEVICE:", line)
    p = parse_permission(line)
    if p:
        result.update(p)
        got.set()


async def main():
    ble = BleCentral(on_line)
    print("scanne nach Claude-uConsole ...")
    await ble.connect()
    print("verbunden — sende prompt")
    await ble.send_line(build_prompt_snapshot("poc1", "Bash", "rm -rf /tmp/foo"))
    print(">>> Overlay sollte JETZT auf der uConsole sein — druecke Y oder N <<<")
    try:
        await asyncio.wait_for(got.wait(), timeout=120)
        print("ENTSCHEIDUNG:", result)
    except asyncio.TimeoutError:
        print("TIMEOUT — kein Knopfdruck in 120s")
    await ble.send_line(build_cleared_snapshot())
    await asyncio.sleep(0.8)  # cleared-Snapshot zustellen lassen, bevor wir trennen
    await ble.disconnect()


asyncio.run(main())
