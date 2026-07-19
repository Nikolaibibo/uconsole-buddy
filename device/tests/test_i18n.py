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
