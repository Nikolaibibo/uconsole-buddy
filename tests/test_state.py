from companion.state import AppState


def snap(**kw):
    base = {"total": 0, "running": 0, "waiting": 0}
    base.update(kw)
    return base


def test_apply_snapshot_updates_sessions():
    s = AppState()
    s.apply_snapshot(snap(total=3, running=1, waiting=1), now=100.0)
    assert (s.total, s.running, s.waiting) == (3, 1, 1)


def test_new_prompt_arms_and_resets_response():
    s = AppState()
    s.apply_snapshot(snap(waiting=1, prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    assert s.in_prompt() is True
    assert s.prompt_id() == "req1"


def test_record_decision_latches_and_counts():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("once", now=11.0)
    assert s.in_prompt() is False       # geantwortet → nicht mehr aktiv
    assert s.appr == 1 and s.deny == 0


def test_same_prompt_persists_does_not_rearm_response():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("once", now=11.0)
    # gleicher Prompt kommt im nächsten Snapshot nochmal (Entscheidung noch nicht verarbeitet)
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=12.0)
    assert s.in_prompt() is False       # response_sent bleibt, kein Doppel-Senden


def test_new_prompt_id_rearms():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("deny", now=11.0)
    s.apply_snapshot(snap(prompt={"id": "req2", "tool": "Write", "hint": "x"}), now=12.0)
    assert s.in_prompt() is True and s.deny == 1


def test_should_rearm_after_timeout():
    s = AppState()
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=10.0)
    s.record_decision("once", now=11.0)
    s.apply_snapshot(snap(prompt={"id": "req1", "tool": "Bash", "hint": "ls"}), now=12.0)
    assert s.should_rearm(now=14.0, timeout=4.0) is False   # 3s seit Entscheidung
    assert s.should_rearm(now=15.5, timeout=4.0) is True    # 4.5s → re-armen
    s.rearm()
    assert s.in_prompt() is True


def test_connection_state_disconnected_without_snapshot():
    s = AppState()
    assert s.connection_state(now=0.0) == "disconnected"


def test_connection_state_timeout():
    s = AppState()
    s.apply_snapshot(snap(total=1, running=1), now=100.0)
    assert s.connection_state(now=120.0) == "running"
    assert s.connection_state(now=131.0) == "disconnected"   # >30s ohne Snapshot


def test_connection_state_waiting_beats_running():
    s = AppState()
    s.apply_snapshot(snap(total=2, running=1, waiting=1,
                          prompt={"id": "r", "tool": "Bash", "hint": "x"}), now=100.0)
    assert s.connection_state(now=101.0) == "waiting"


def test_connection_state_idle_when_empty():
    s = AppState()
    s.apply_snapshot(snap(total=0, running=0, waiting=0), now=100.0)
    assert s.connection_state(now=101.0) == "idle"


def test_apply_snapshot_reads_state():
    s = AppState()
    s.apply_snapshot({"total": 1, "state": "waiting"}, now=100.0)
    assert s.claude_state == "waiting"
    assert s.mood_state(now=100.0) == "waiting"


def test_mood_state_falls_back_to_connection_state():
    s = AppState()
    s.apply_snapshot({"total": 1, "running": 1}, now=100.0)  # kein state-Feld
    assert s.claude_state == ""
    assert s.mood_state(now=100.0) == "running"  # aus connection_state abgeleitet
