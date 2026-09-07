from datetime import datetime, timezone

from companion.usage_cards import cards_art, elapsed_pct, pacing, pacing_label

# 18:40 CEST am 07.09. — der Stand aus Nikolais /usage-Screenshot
NOW = datetime(2026, 9, 7, 16, 40, 0, tzinfo=timezone.utc)
FULL = {"usage_5h": 5, "usage_7d": 5,
        "reset_5h_iso": "2026-09-07T18:39:59.811Z",   # in 1h59
        "reset_7d_iso": "2026-09-09T05:59:59.811Z",   # in 1d13h
        "plan": "Team", "model": "Opus 5", "project": "marvin"}


def test_elapsed_pct_of_the_five_hour_window():
    """1h59 Rest von 5h heisst 60 % des Fensters sind durch."""
    assert round(elapsed_pct(FULL["reset_5h_iso"], 5, NOW)) == 60


def test_elapsed_pct_of_the_seven_day_window():
    assert round(elapsed_pct(FULL["reset_7d_iso"], 24 * 7, NOW)) == 78


def test_elapsed_pct_is_none_without_a_usable_timestamp():
    assert elapsed_pct("", 5, NOW) is None
    assert elapsed_pct("kaputt", 5, NOW) is None


def test_pacing_is_the_difference_in_percentage_points():
    """Abgeleitet aus zwei Datenpunkten: verbraucht minus abgelaufen."""
    assert pacing(5, 60) == -55
    assert pacing(5, 78) == -73
    assert pacing(90, 50) == 40
    assert pacing(None, 60) is None
    assert pacing(5, None) is None


def test_pacing_label_buckets():
    assert pacing_label(-55)[0] == "Chill"
    assert pacing_label(0)[0] == "On track"
    assert pacing_label(40)[0] == "Hot"
    assert pacing_label(None)[0] == "--"


def test_shows_consumed_not_remaining():
    """Vorbild ist der /usage-Screen: 5 % verbraucht, nicht 95 % frei."""
    art = cards_art(FULL, NOW, width=120, height=24)
    assert "5%" in art
    assert "95%" not in art
    assert "REMAINING" not in art


def test_has_both_reset_countdowns():
    art = cards_art(FULL, NOW, width=120, height=24)
    assert "1h59" in art
    assert "1d13h" in art or "1d 13h" in art


def test_pacing_appears_on_screen():
    art = cards_art(FULL, NOW, width=120, height=24)
    assert "-55%" in art or "−55%" in art
    assert "Chill" in art


def test_missing_data_renders_dashes_never_a_number():
    art = cards_art(None, NOW, width=120, height=24)
    assert "--%" in art
    assert "0%" not in art


def test_respects_width_and_height():
    import re
    for w, h in ((80, 18), (120, 24), (158, 24)):
        art = cards_art(FULL, NOW, width=w, height=h)
        lines = art.splitlines()
        assert len(lines) <= h, (w, h, len(lines))
        for line in lines:
            assert len(re.sub(r"\[/?[^\]]*\]", "", line)) <= w, (w, line)


def _plain(s):
    import re
    return re.sub(r"\[/?[^\]]*\]", "", s)


def test_card_borders_are_flush():
    """Kopfzeile und Koerper einer Karte muessen exakt gleich breit sein,
    sonst steht der Rahmen rechts offen."""
    from companion.usage_cards import _card
    for width in (40, 61, 80):
        lines = _card("TITEL", ["a", "laengerer inhalt"], width)
        widths = {len(_plain(l)) for l in lines}
        assert widths == {width}, (width, widths)


def test_big_number_uses_blocks_not_hashes():
    # Markup erst strippen -- die Farbcodes sind selbst Rauten (#4ade80).
    art = _plain(cards_art(FULL, NOW, width=120, height=24))
    assert "#" not in art
    assert chr(9608) in art
