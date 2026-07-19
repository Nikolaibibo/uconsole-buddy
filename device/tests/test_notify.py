from companion.notify import NotifyDecider


def test_fires_on_transition_to_waiting():
    d = NotifyDecider()
    assert d.decide("running", now=0.0) is None      # kein Kanal fuer running
    assert d.decide("waiting", now=1.0) == "waiting"  # Uebergang -> feuert


def test_no_refire_same_state():
    d = NotifyDecider()
    assert d.decide("waiting", now=0.0) == "waiting"
    assert d.decide("waiting", now=5.0) is None       # gleicher State -> still


def test_debounce_blocks_rapid_fires():
    d = NotifyDecider(debounce=2.0)
    assert d.decide("waiting", now=0.0) == "waiting"
    assert d.decide("done", now=0.5) is None          # zu schnell nach letztem Feuer
    assert d.decide("waiting", now=3.0) == "waiting"   # nach Debounce wieder frei


def test_muted_never_fires():
    d = NotifyDecider()
    d.muted = True
    assert d.decide("waiting", now=0.0) is None
