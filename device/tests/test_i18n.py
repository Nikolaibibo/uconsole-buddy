from companion import i18n


def test_word_for_all_mood_states_nonempty():
    for st in ["idle", "thinking", "running", "waiting", "done", "error", "offline"]:
        assert i18n.word_for(st)


def test_word_for_unknown_is_fallback():
    assert i18n.word_for("bogus") == i18n.t("_fallback")


def test_both_languages_cover_the_same_keys():
    en, de = i18n._STRINGS["en"], i18n._STRINGS["de"]
    assert set(en) == set(de)
    assert all(en[k] and de[k] for k in en)


def test_default_lang_is_english():
    # Ohne GERALD_LANG-Override ist Default 'en' (öffentliche Klone starten englisch).
    assert i18n._STRINGS["en"]["running"] == "working"
    assert i18n._STRINGS["de"]["running"] == "arbeite"


def test_hints_list_the_screen_keys():
    h = i18n.hints()
    for key in ("[u]", "[s]", "[m]", "[q]"):
        assert key in h, key


def test_hints_during_a_prompt_lead_with_the_decision_keys():
    h = i18n.hints(in_prompt=True)
    assert h.index("[y]") < h.index("[n]")
    # Waehrend einer Freigabe sind die Screen-Tasten wirkungslos -> nicht anbieten.
    assert "[u]" not in h and "[s]" not in h


def test_hints_label_changes_with_mute_state():
    assert i18n.hints(muted=True) != i18n.hints(muted=False)


def test_open_screen_is_labelled_as_a_way_back():
    """Ist ein Screen offen, schliesst dieselbe Taste ihn wieder — das soll dranstehen."""
    assert i18n.hints(screen="cards") != i18n.hints()
    assert i18n.t("k_back") in i18n.hints(screen="cards")
    assert i18n.t("k_back") in i18n.hints(screen="synth")


def test_hints_are_plain_text_and_need_escaping_by_the_ui():
    """Rich liest [u] als underline und [s] als strikethrough — genau die zwei
    Tasten, die wir anzeigen. hints() bleibt Klartext, die UI escaped."""
    from rich.markup import escape
    h = i18n.hints()
    assert "[u]" in h and "[s]" in h
    esc = escape(h)
    assert "\\[u]" in esc and "\\[s]" in esc
