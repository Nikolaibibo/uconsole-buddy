import json
from companion.logfmt import summarize_rx

SNAP = json.dumps({"state": "running", "total": 1, "running": 1, "waiting": 0,
                   "msg": "denke nach", "entries": ["21:41 Bash: net use", "21:43 Bash: ls //nas"],
                   "prompt": None, "hud": {"project": "marvin"}})


def test_snapshot_keeps_shape_drops_content():
    out = summarize_rx(SNAP, debug=False)
    assert out == "snapshot state=running running=1 waiting=0 entries=2 hud=yes"
    assert "net use" not in out and "marvin" not in out and "denke" not in out


def test_pending_prompt_is_flagged_without_its_text():
    out = summarize_rx(json.dumps({"total": 1, "state": "waiting",
                                   "prompt": {"id": "r1", "hint": "rm -rf secret"}}), debug=False)
    assert "prompt=yes" in out and "secret" not in out


def test_command_is_logged_by_name():
    assert summarize_rx('{"cmd": "status"}', debug=False) == "cmd=status"


def test_unknown_shape_never_logs_values():
    out = summarize_rx('{"auth": "hunter2"}', debug=False)
    assert out == "keys=auth" and "hunter2" not in out


def test_garbage_is_described_not_echoed():
    assert summarize_rx("not json at all", debug=False) == "<unparseable, 15 chars>"


def test_debug_mode_logs_verbatim():
    assert summarize_rx(SNAP, debug=True) == SNAP
