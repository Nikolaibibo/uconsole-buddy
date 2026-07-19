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
