"""End-to-end test for the TCP transport: raw client (agent) <-> NetTransport."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion.net_server import NetTransport


async def _read_json_line(reader):
    raw = await asyncio.wait_for(reader.readline(), timeout=5)
    return json.loads(raw.decode())


async def run():
    snapshots = []
    t = NetTransport(on_snapshot=lambda line: snapshots.append(json.loads(line)),
                     host="127.0.0.1", port=0)
    # bind to an ephemeral port
    t._server = await asyncio.start_server(t._handle, "127.0.0.1", 0)
    port = t._server.sockets[0].getsockname()[1]

    fails = 0

    def check(cond, label):
        nonlocal fails
        print(("ok:   " if cond else "FAIL: ") + label)
        if not cond:
            fails += 1

    # --- status event ---
    r, w = await asyncio.open_connection("127.0.0.1", port)
    w.write((json.dumps({"type": "status", "state": "running", "entry": "12:00 Bash: ls"}) + "\n").encode())
    await w.drain()
    ack = await _read_json_line(r)
    check(ack.get("decision") == "ask", "status ack returned")
    w.close()
    await asyncio.sleep(0.05)
    last = snapshots[-1]
    check(last["state"] == "running", "snapshot state=running")
    check("12:00 Bash: ls" in last["entries"], "feed entry propagated")

    # --- approval: agent asks, device says allow ---
    r2, w2 = await asyncio.open_connection("127.0.0.1", port)
    w2.write((json.dumps({"type": "approve", "id": "req1", "tool": "bash", "hint": "rm x"}) + "\n").encode())
    await w2.drain()
    await asyncio.sleep(0.05)
    prompt_snap = snapshots[-1]
    check(prompt_snap.get("prompt", {}) and prompt_snap["prompt"]["id"] == "req1", "prompt overlay snapshot emitted")
    # device UI decides 'once' -> feeds a permission line into the transport
    t.on_device_line(json.dumps({"cmd": "permission", "id": "req1", "decision": "once"}))
    reply = await _read_json_line(r2)
    check(reply.get("decision") == "allow", "device 'once' -> agent gets allow")
    w2.close()

    # --- approval: device denies ---
    r3, w3 = await asyncio.open_connection("127.0.0.1", port)
    w3.write((json.dumps({"type": "approve", "id": "req2", "tool": "bash", "hint": "sudo"}) + "\n").encode())
    await w3.drain()
    await asyncio.sleep(0.05)
    t.on_device_line(json.dumps({"cmd": "permission", "id": "req2", "decision": "deny"}))
    reply3 = await _read_json_line(r3)
    check(reply3.get("decision") == "deny", "device 'deny' -> agent gets deny")
    w3.close()

    t._server.close()
    print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)"))
    return fails


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(run()) else 0)
