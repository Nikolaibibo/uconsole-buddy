"""E2E test for the TCP transport: multi-session aggregation + queued approvals."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion.net_server import NetTransport


async def _line(reader):
    raw = await asyncio.wait_for(reader.readline(), timeout=5)
    return json.loads(raw.decode())


async def run():
    snaps = []
    t = NetTransport(on_snapshot=lambda l: snaps.append(json.loads(l)), host="127.0.0.1", port=0)
    t._server = await asyncio.start_server(t._handle, "127.0.0.1", 0)
    port = t._server.sockets[0].getsockname()[1]

    fails = 0

    def check(cond, label):
        nonlocal fails
        print(("ok:   " if cond else "FAIL: ") + label)
        if not cond:
            fails += 1

    async def status(**kw):
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write((json.dumps({"type": "status", **kw}) + "\n").encode())
        await w.drain()
        await _line(r)
        w.close()

    # --- two sessions: A running(+feed), B thinking ---
    await status(sid="A", label="alpha", state="running", entry="npm test")
    await status(sid="B", label="beta", state="thinking")
    await asyncio.sleep(0.05)
    last = snaps[-1]
    check(last["total"] == 2, f"total=2 ({last['total']})")
    check(last["running"] == 2, f"running counts thinking too ({last['running']})")
    check(last["state"] == "running", f"agg state=running ({last['state']})")
    check(any("alpha▸npm test" in e for e in last["entries"]), "feed tagged with label")

    # --- B goes waiting -> aggregate must escalate to waiting ---
    await status(sid="B", label="beta", state="waiting")
    await asyncio.sleep(0.05)
    last = snaps[-1]
    check(last["state"] == "waiting", f"waiting wins priority ({last['state']})")
    check(last["waiting"] == 1 and last["total"] == 2, "counts: 1 waiting / 2 total")

    # --- queued approvals: A then B; one overlay at a time ---
    ra, wa = await asyncio.open_connection("127.0.0.1", port)
    wa.write((json.dumps({"type": "approve", "id": "a1", "sid": "A", "label": "alpha",
                          "tool": "bash", "hint": "rm a"}) + "\n").encode())
    await wa.drain()
    await asyncio.sleep(0.05)
    p1 = snaps[-1].get("prompt")
    check(bool(p1) and p1["id"] == "a1" and "alpha▸" in p1["hint"], "first approval shown with label")

    rb, wb = await asyncio.open_connection("127.0.0.1", port)
    wb.write((json.dumps({"type": "approve", "id": "b1", "sid": "B", "label": "beta",
                          "tool": "bash", "hint": "rm b"}) + "\n").encode())
    await wb.drain()
    await asyncio.sleep(0.05)
    check(snaps[-1].get("prompt", {}).get("id") == "a1", "second approval queued (still showing a1)")

    # decide a1 -> allow, then b1 should surface
    t.on_device_line(json.dumps({"cmd": "permission", "id": "a1", "decision": "once"}))
    check((await _line(ra)).get("decision") == "allow", "a1 -> allow")
    await asyncio.sleep(0.05)
    check(snaps[-1].get("prompt", {}).get("id") == "b1", "b1 surfaces after a1 resolved")

    # decide b1 -> deny, then back to aggregate face
    t.on_device_line(json.dumps({"cmd": "permission", "id": "b1", "decision": "deny"}))
    check((await _line(rb)).get("decision") == "deny", "b1 -> deny")
    await asyncio.sleep(0.05)
    check(snaps[-1].get("prompt") is None, "overlay cleared after queue drains")

    wa.close(); wb.close()
    t._server.close()
    print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)"))
    return fails


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(run()) else 0)
