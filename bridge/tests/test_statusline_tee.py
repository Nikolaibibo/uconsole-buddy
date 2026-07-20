import io
import sys
from types import SimpleNamespace
from bridge.statusline_tee import extract_hud, should_send, main

STDIN = {
    "model": {"id": "claude-fable-5", "display_name": "Fable 5"},
    "workspace": {"current_dir": "/Users/n/marvin", "project_dir": "/Users/n/marvin"},
    "context_window": {"context_window_size": 1000000, "used_percentage": 12.4},
}
CACHE = {
    "data": {"planName": "Team", "fiveHour": 5, "sevenDay": 23,
             "fiveHourResetAt": "2026-07-20T10:29:59.955Z",
             "sevenDayResetAt": "2026-07-22T05:59:59.955Z"},
    "timestamp": 1784527182650,
    "lastGoodData": {"planName": "Team", "fiveHour": 5, "sevenDay": 23,
                     "fiveHourResetAt": "2026-07-20T10:29:59.955Z"},
}


def test_extract_full():
    hud = extract_hud(STDIN, CACHE)
    assert hud == {"model": "Fable 5", "ctx_pct": 12, "project": "marvin",
                   "usage_5h": 5, "usage_7d": 23,
                   "reset_5h_iso": "2026-07-20T10:29:59.955Z", "plan": "Team"}


def test_extract_partial_no_cache_no_ctx():
    hud = extract_hud({"model": {"display_name": "Fable 5"}}, None)
    assert hud == {"model": "Fable 5"}
    assert "ctx_pct" not in hud and "usage_5h" not in hud


def test_extract_uses_last_good_data_when_data_null():
    hud = extract_hud(STDIN, {"data": None, "lastGoodData": CACHE["lastGoodData"]})
    assert hud["usage_5h"] == 5


def test_should_send_on_change_and_heartbeat():
    hud = {"ctx_pct": 12}
    assert should_send(None, hud, 1000.0)                                   # kein State → senden
    assert not should_send({"sent_at": 990.0, "hud": hud}, hud, 1000.0)     # unverändert, <30s
    assert should_send({"sent_at": 990.0, "hud": {"ctx_pct": 11}}, hud, 1000.0)  # geändert
    assert should_send({"sent_at": 960.0, "hud": hud}, hud, 1000.0)         # Heartbeat >30s
    assert not should_send(None, {}, 1000.0)                                # leeres hud → nie


def test_main_fail_safe_subprocess_not_found(tmp_path, monkeypatch):
    """subprocess.run() FileNotFoundError (BUN missing) → main() returns 0, not traceback."""
    # Create a real plugin directory so _latest_plugin_dir() returns non-None
    plugin_dir = tmp_path / "1.0.0"
    plugin_dir.mkdir()
    (plugin_dir / "src").mkdir()
    (plugin_dir / "src" / "index.ts").write_text("// dummy plugin")

    # Monkeypatch paths so subprocess.run() is reached with missing BUN
    monkeypatch.setattr("bridge.statusline_tee.BUN", str(tmp_path / "no-such-bun"))
    monkeypatch.setattr("bridge.statusline_tee.PLUGIN_GLOB", str(tmp_path / "*/"))
    monkeypatch.setattr("bridge.statusline_tee.STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr("bridge.statusline_tee.SOCK", str(tmp_path / "bridge.sock"))

    # Create stdin mock with .buffer attribute (to avoid AttributeError on .buffer.read())
    stdin_mock = SimpleNamespace(buffer=io.BytesIO(b"\xff\xfe not json"))
    monkeypatch.setattr("sys.stdin", stdin_mock)

    # main() should return 0 without raising FileNotFoundError from subprocess.run()
    result = main()
    assert result == 0
