import json
from companion.protocol import (
    parse_message, build_permission, build_ack, build_status_ack,
)


def test_parse_valid():
    assert parse_message('{"total":3}') == {"total": 3}


def test_parse_invalid_returns_none():
    assert parse_message("not json") is None


def test_build_permission_once():
    m = json.loads(build_permission("req_abc", "once"))
    assert m == {"cmd": "permission", "id": "req_abc", "decision": "once"}


def test_build_permission_rejects_bad_decision():
    import pytest
    with pytest.raises(ValueError):
        build_permission("req_abc", "always")


def test_build_permission_terminated_by_newline():
    assert build_permission("x", "deny").endswith("\n")


def test_build_ack_omits_unset_fields():
    assert json.loads(build_ack("name")) == {"ack": "name", "ok": True}


def test_build_ack_includes_n_and_error():
    m = json.loads(build_ack("chunk", ok=False, n=12, error="boom"))
    assert m == {"ack": "chunk", "ok": False, "n": 12, "error": "boom"}


def test_build_status_ack_shape():
    m = json.loads(build_status_ack("Claude-uConsole", True, 8054, 42, 3))
    assert m["ack"] == "status" and m["ok"] is True
    assert m["data"]["name"] == "Claude-uConsole"
    assert m["data"]["sec"] is True
    assert m["data"]["sys"]["up"] == 8054
    assert m["data"]["stats"] == {"appr": 42, "deny": 3}
