from companion.mood import mood_for, face_box


def test_all_states_have_fields():
    for st in ["idle", "thinking", "running", "waiting", "done", "error"]:
        m = mood_for(st)
        assert m["word"] and m["eyes"] and m["mouth"] and m["color"]


def test_face_box_is_four_lines_and_framed():
    box = face_box("running")
    lines = box.split("\n")
    assert len(lines) == 4
    assert lines[0].startswith("╭") and lines[0].endswith("╮")
    assert lines[-1].startswith("╰") and lines[-1].endswith("╯")


def test_waiting_distinct_from_running():
    assert mood_for("waiting")["eyes"] != mood_for("running")["eyes"]


def test_unknown_state_fallback():
    assert mood_for("bogus")["word"] == "…"
    assert len(face_box("bogus").split("\n")) == 4
