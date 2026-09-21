from bridge.ble_central import NUS_SERVICE, matches_device

PIN = "2C:CF:67:FE:1E:1D"


def test_pinned_accepts_the_uconsole():
    assert matches_device("2c:cf:67:fe:1e:1d", [NUS_SERVICE.upper()], PIN)


def test_pinned_rejects_impostor_with_same_service():
    assert not matches_device("AA:BB:CC:DD:EE:FF", [NUS_SERVICE], PIN)


def test_requires_nus_service_even_with_matching_address():
    assert not matches_device(PIN, [], PIN)


def test_unpinned_accepts_any_nus_peripheral():
    assert matches_device("AA:BB:CC:DD:EE:FF", [NUS_SERVICE], None)
