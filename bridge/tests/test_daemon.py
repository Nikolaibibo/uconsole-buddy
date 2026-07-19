import asyncio
from bridge.daemon import Bridge
from bridge.protocol import parse_permission  # noqa

def run(coro): return asyncio.run(coro)

def make_bridge():
    sent = []
    async def send_snapshot(line): sent.append(line)
    return Bridge(send_snapshot), sent

def test_approval_allow():
    async def scenario():
        b, sent = make_bridge()
        task = asyncio.create_task(b.request_approval("r1", "Bash", "ls", timeout=5))
        await asyncio.sleep(0)  # request_approval sendet Prompt + registriert Future
        b.on_ble_line('{"cmd":"permission","id":"r1","decision":"once"}')
        res = await task
        assert res == "allow"
        assert any('"prompt"' in s and '"r1"' in s for s in sent)   # Prompt gesendet
        assert any('"waiting": 0' in s for s in sent)               # cleared danach
        return res
    assert run(scenario()) == "allow"

def test_approval_deny():
    async def scenario():
        b, _ = make_bridge()
        task = asyncio.create_task(b.request_approval("r2", "Bash", "x", timeout=5))
        await asyncio.sleep(0)
        b.on_ble_line('{"cmd":"permission","id":"r2","decision":"deny"}')
        return await task
    assert run(scenario()) == "deny"

def test_approval_timeout_asks():
    async def scenario():
        b, _ = make_bridge()
        return await b.request_approval("r3", "Bash", "x", timeout=0.05)  # keine Antwort
    assert run(scenario()) == "ask"

def test_stale_permission_ignored():
    async def scenario():
        b, _ = make_bridge()
        task = asyncio.create_task(b.request_approval("r4", "Bash", "x", timeout=0.2))
        await asyncio.sleep(0)
        b.on_ble_line('{"cmd":"permission","id":"OTHER","decision":"once"}')  # falsche id
        return await task
    assert run(scenario()) == "ask"   # nur die falsche id kam → Timeout → ask


def test_push_status_sends_when_idle():
    async def scenario():
        b, sent = make_bridge()
        await b.push_status("running", "x")
        assert any('"running": 1' in s for s in sent)
        return sent
    run(scenario())


def test_push_status_skips_during_approval():
    async def scenario():
        b, sent = make_bridge()
        task = asyncio.create_task(b.request_approval("r5", "Bash", "x", timeout=5))
        await asyncio.sleep(0)  # Prompt-Snapshot gesendet, Future pending
        before = len(sent)
        await b.push_status("running", "x")
        assert len(sent) == before  # kein zusätzlicher Status-Snapshot während Approval aktiv
        b.on_ble_line('{"cmd":"permission","id":"r5","decision":"once"}')  # aufräumen
        await task
    run(scenario())


import json

def test_push_event_sets_state_and_entry():
    async def scenario():
        b, sent = make_bridge()
        await b.push_event(state="running", msg="arbeite", entry="14:23 Bash: ls")
        m = json.loads(sent[-1])
        assert m["state"] == "running"
        assert m["entries"] == ["14:23 Bash: ls"]
        assert m["msg"] == "arbeite"
    run(scenario())

def test_push_event_entries_ring_keeps_last_8():
    async def scenario():
        b, sent = make_bridge()
        for i in range(10):
            await b.push_event(state="running", entry=f"e{i}")
        m = json.loads(sent[-1])
        assert m["entries"] == [f"e{i}" for i in range(2, 10)]  # nur letzte 8
    run(scenario())

def test_push_event_skips_send_during_approval_but_keeps_state():
    async def scenario():
        b, sent = make_bridge()
        task = asyncio.create_task(b.request_approval("rA", "Bash", "x", timeout=5))
        await asyncio.sleep(0)
        before = len(sent)
        await b.push_event(state="running", entry="hidden")
        assert len(sent) == before                      # kein Push während Approval
        b.on_ble_line('{"cmd":"permission","id":"rA","decision":"once"}')
        await task
        await b.push_event(state="done")                # jetzt frei
        m = json.loads(sent[-1])
        assert m["state"] == "done"
        assert "hidden" in m["entries"]                 # während Approval gemerkte Zeile ist da
    run(scenario())


def test_done_decays_to_idle():
    async def scenario():
        b, sent = make_bridge()
        await b.push_event(state="done", decay=0.05)
        assert json.loads(sent[-1])["state"] == "done"
        await asyncio.sleep(0.12)
        assert json.loads(sent[-1])["state"] == "idle"   # automatisch zerfallen
    run(scenario())

def test_new_event_cancels_decay():
    async def scenario():
        b, sent = make_bridge()
        await b.push_event(state="done", decay=0.10)
        await b.push_event(state="running")              # canceled Zerfall
        await asyncio.sleep(0.15)
        assert json.loads(sent[-1])["state"] == "running"
    run(scenario())
