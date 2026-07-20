from datetime import datetime, timezone
from companion.hud import hud_line, _bar, _color, _countdown

NOW = datetime(2026, 7, 20, 8, 0, 0, tzinfo=timezone.utc)
FULL = {"model": "Fable 5", "ctx_pct": 12, "project": "marvin",
        "usage_5h": 5, "usage_7d": 23,
        "reset_5h_iso": "2026-07-20T10:29:59.955Z", "plan": "Team"}


def test_empty_hud_renders_empty():
    assert hud_line(None) == ""
    assert hud_line({}) == ""


def test_full_line_has_all_segments():
    line = hud_line(FULL, NOW)
    for frag in ("marvin", "Fable 5", "ctx", "12%", "5h 5%", "↺ 2h29m", "7d 23%"):
        assert frag in line


def test_partial_hud_skips_missing_segments():
    line = hud_line({"ctx_pct": 90}, NOW)
    assert "ctx" in line and "#e53935" in line          # rot >85
    assert "5h" not in line and "·" not in line


def test_bar_and_color():
    assert _bar(0) == "▱▱▱▱▱"
    assert _bar(12) == "▰▱▱▱▱"
    assert _bar(100) == "▰▰▰▰▰"
    assert _color(60) == "#4caf50" and _color(61) == "#ffb300" and _color(86) == "#e53935"


def test_countdown_past_or_garbage_is_none():
    assert _countdown("2026-07-20T07:00:00Z", NOW) is None      # Vergangenheit
    assert _countdown("kaputt", NOW) is None
    assert _countdown("2026-07-20T08:45:00Z", NOW) == "45m"
