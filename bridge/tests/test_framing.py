from bridge.framing import LineReassembler, chunk_for_mtu

def test_reassembler_joins_split_line():
    r = LineReassembler()
    assert r.feed(b'{"a":') == []
    assert r.feed(b'1}\n') == ['{"a":1}']

def test_reassembler_multiple_lines():
    r = LineReassembler()
    assert r.feed(b'{"a":1}\n{"b":2}\n') == ['{"a":1}', '{"b":2}']

def test_reassembler_drops_overlong():
    r = LineReassembler(max_len=16)
    assert r.feed(b'x'*32) == []
    assert r.feed(b'{"a":1}\n') == ['{"a":1}']

def test_chunk_caps_at_180():
    chunks = chunk_for_mtu(b'z'*400, mtu=185)
    assert all(len(c) <= 180 for c in chunks)
    assert b''.join(chunks) == b'z'*400

def test_chunk_tiny_mtu():
    chunks = chunk_for_mtu(b'z'*50, mtu=23)
    assert max(len(c) for c in chunks) == 20
    assert b''.join(chunks) == b'z'*50
