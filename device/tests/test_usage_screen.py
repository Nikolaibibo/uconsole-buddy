from datetime import datetime, timezone

from companion.usage_screen import usage_art, remaining_bar, remaining_pct

NOW = datetime(2026, 9, 7, 16, 0, 0, tzinfo=timezone.utc)
FULL = {"model": "Opus 5", "ctx_pct": 11, "project": "marvin",
        "usage_5h": 13, "usage_7d": 4,
        "reset_5h_iso": "2026-09-07T18:40:00.427Z", "plan": "Team"}


def test_percent_is_inverted_to_remaining():
    """Unsere Daten sind *used*, der Screen zeigt *remaining* — 13 used -> 87 frei."""
    assert remaining_pct(13) == 87
    assert remaining_pct(0) == 100
    assert remaining_pct(100) == 0


def test_missing_value_renders_dashes_not_a_number():
    """Daemon aus / Cache leer darf NIE als 100 % frei durchgehen."""
    assert remaining_pct(None) is None
    art = usage_art({"usage_5h": 13}, NOW, width=60)
    assert "87%" in art
    assert "--%" in art          # WEEKLY fehlt
    assert "100%" not in art


def test_bar_scales_with_width():
    assert remaining_bar(100, cells=10) == "▰" * 10
    assert remaining_bar(0, cells=10) == "▱" * 10
    assert remaining_bar(50, cells=10) == "▰" * 5 + "▱" * 5
    assert len(remaining_bar(None, cells=10)) == 10


def test_full_screen_has_title_labels_and_countdown():
    art = usage_art(FULL, NOW, width=80)
    for frag in ("SESSION", "WEEKLY", "REMAINING", "87%", "96%", "2h40m"):
        assert frag in art, frag


def test_empty_hud_still_renders_a_frame():
    """Ohne Daten kein leerer Screen — Rahmen + Platzhalter."""
    art = usage_art(None, NOW, width=60)
    assert "SESSION" in art and "--%" in art


def test_art_respects_width():
    for w in (48, 80, 120):
        art = usage_art(FULL, NOW, width=w)
        for line in art.splitlines():
            assert len(_strip_markup(line)) <= w, (w, line)


def _strip_markup(s: str) -> str:
    import re
    return re.sub(r"\[/?[^\]]*\]", "", s)


def test_metrics_survive_a_short_screen():
    """Die Zahlen sind der Zweck — bei wenig Hoehe fliegt Deko raus, nie SESSION/WEEKLY."""
    art = usage_art(FULL, NOW, width=80, height=14)
    lines = art.splitlines()
    assert len(lines) <= 14, len(lines)
    for frag in ("SESSION", "WEEKLY", "87%", "96%"):
        assert frag in art, frag


def test_decoration_grows_with_available_height():
    short = usage_art(FULL, NOW, width=80, height=14)
    tall = usage_art(FULL, NOW, width=80, height=30)
    assert len(tall.splitlines()) > len(short.splitlines())
    assert len(tall.splitlines()) <= 30
