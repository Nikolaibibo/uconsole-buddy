import json
from bridge.protocol import (
    build_snapshot, build_prompt_snapshot, build_cleared_snapshot,
    parse_permission, decision_to_hook, hook_pretooluse_output,
)

def test_build_snapshot_defaults():
    m = json.loads(build_snapshot())
    assert m["total"] == 1 and m["waiting"] == 0 and m["prompt"] is None

def test_build_prompt_snapshot():
    m = json.loads(build_prompt_snapshot("req1", "Bash", "ls /tmp"))
    assert m["waiting"] == 1
    assert m["prompt"] == {"id": "req1", "tool": "Bash", "hint": "ls /tmp"}
    assert m["msg"] == "approve: Bash"

def test_build_cleared():
    m = json.loads(build_cleared_snapshot())
    assert m["waiting"] == 0 and m["prompt"] is None

def test_snapshot_newline_terminated():
    assert build_snapshot().endswith("\n")

def test_parse_permission_valid():
    assert parse_permission('{"cmd":"permission","id":"r1","decision":"once"}') == {"id": "r1", "decision": "once"}

def test_parse_permission_ignores_other():
    assert parse_permission('{"cmd":"status"}') is None
    assert parse_permission("garbage") is None

def test_decision_mapping():
    assert decision_to_hook("once") == "allow"
    assert decision_to_hook("deny") == "deny"
    assert decision_to_hook(None) == "ask"
    assert decision_to_hook("weird") == "ask"

def test_hook_output_shape():
    m = json.loads(hook_pretooluse_output("allow", "ok"))
    assert m["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert m["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert m["hookSpecificOutput"]["permissionDecisionReason"] == "ok"
