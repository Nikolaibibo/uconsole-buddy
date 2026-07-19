import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "posttooluse", pathlib.Path("bridge/hooks/posttooluse.py"))
ptu = importlib.util.module_from_spec(spec); spec.loader.exec_module(ptu)

import _send

def test_feed_line_bash():
    assert ptu.feed_line("Bash", {"command": "npm test"}, "14:23") == "14:23 Bash: npm test"

def test_feed_line_edit_uses_file_path():
    assert ptu.feed_line("Edit", {"file_path": "/a/b/ui.py"}, "09:01") == "09:01 Edit: ui.py"

def test_feed_line_truncates():
    line = ptu.feed_line("Bash", {"command": "x" * 200}, "00:00")
    assert len(line) <= 60

def test_payload_omits_msg_when_not_passed():
    p = _send.build_status_payload(state="running", entry="14:23 Bash: ls")
    assert "msg" not in p
    assert p == {"type": "status", "state": "running", "entry": "14:23 Bash: ls"}

def test_payload_includes_msg_when_passed():
    p = _send.build_status_payload(state="thinking", msg="denke nach")
    assert p["msg"] == "denke nach"
