from companion.mood import mood_for

def test_known_states_have_face_and_spruch():
    for st in ["idle", "thinking", "running", "waiting", "done", "error"]:
        face, spruch = mood_for(st)
        assert face and spruch

def test_waiting_is_distinct():
    assert mood_for("waiting") != mood_for("running")

def test_unknown_state_fallback():
    assert mood_for("bogus") == ("😐", "…")
