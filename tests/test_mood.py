from companion.mood import mood_for, face_box, CLOSED_EYES


def test_all_states_have_fields():
    for st in ["idle", "thinking", "running", "waiting", "done", "error"]:
        m = mood_for(st)
        assert m["brows"] and m["eyes"] and m["mouth"] and m["color"]


def test_face_box_is_five_lines_and_framed():
    box = face_box("running")
    lines = box.split("\n")
    assert len(lines) == 5
    assert lines[0].startswith("╭") and lines[0].endswith("╮")
    assert lines[-1].startswith("╰") and lines[-1].endswith("╯")


def test_blink_overrides_eyes():
    normal = face_box("running")
    blinked = face_box("running", eyes=CLOSED_EYES)
    assert normal != blinked
    assert CLOSED_EYES.strip() in blinked


def test_error_has_distinct_brows():
    assert mood_for("error")["brows"] != mood_for("running")["brows"]


def test_unknown_state_fallback():
    assert len(face_box("bogus").split("\n")) == 5


def test_no_trailing_backslash_in_faces():
    # Ein Backslash am Zeilenende würde Textual-Markup [.../] zerschießen.
    for st in ["idle", "thinking", "running", "waiting", "done", "error", "offline"]:
        m = mood_for(st)
        for part in ("brows", "eyes", "mouth"):
            assert not m[part].rstrip().endswith("\\"), f"{st}/{part} endet auf backslash"
