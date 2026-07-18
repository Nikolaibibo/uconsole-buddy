from companion.framing import LineReassembler, chunk_for_mtu


def test_reassembler_joins_split_line():
    r = LineReassembler()
    assert r.feed(b'{"a":') == []
    assert r.feed(b'1}\n') == ['{"a":1}']


def test_reassembler_multiple_lines_one_feed():
    r = LineReassembler()
    assert r.feed(b'{"a":1}\n{"b":2}\n') == ['{"a":1}', '{"b":2}']


def test_reassembler_keeps_remainder():
    r = LineReassembler()
    assert r.feed(b'{"a":1}\n{"b"') == ['{"a":1}']
    assert r.feed(b':2}\n') == ['{"b":2}']


def test_reassembler_drops_overlong_garbage():
    r = LineReassembler(max_len=16)
    assert r.feed(b'x' * 32) == []          # no newline, exceeds max_len → dropped
    assert r.feed(b'{"a":1}\n') == ['{"a":1}']  # resyncs after next newline


def test_chunk_for_mtu_caps_at_180():
    data = b'z' * 400
    chunks = chunk_for_mtu(data, mtu=185)   # 185-3=182 → cap 180
    assert all(len(c) <= 180 for c in chunks)
    assert b''.join(chunks) == data


def test_chunk_for_mtu_tiny_mtu_uses_20():
    data = b'z' * 50
    chunks = chunk_for_mtu(data, mtu=23)    # 23-3=20
    assert max(len(c) for c in chunks) == 20
    assert b''.join(chunks) == data
