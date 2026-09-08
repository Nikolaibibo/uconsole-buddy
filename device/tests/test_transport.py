"""Transport-Auswahl per Umgebungsvariable.

BLE bleibt der Default, damit der Mac bis zur Abgabe unverändert weiterläuft;
der PC-Betrieb schaltet per `COMPANION_TRANSPORT=tcp` um.
"""
from companion.transport import build_transport
from companion.tcp_nus import TcpPeripheral
from companion.ble_nus import NusPeripheral


def _noop(_line: str) -> None:
    pass


def test_defaults_to_ble_when_unset():
    link = build_transport(_noop, env={})
    assert isinstance(link, NusPeripheral)


def test_selects_tcp_when_requested():
    link = build_transport(_noop, env={"COMPANION_TRANSPORT": "tcp",
                                       "COMPANION_TCP_SECRET": "s3cret"})
    assert isinstance(link, TcpPeripheral)


def test_tcp_takes_port_and_secret_from_env():
    link = build_transport(_noop, env={
        "COMPANION_TRANSPORT": "tcp",
        "COMPANION_TCP_PORT": "9999",
        "COMPANION_TCP_SECRET": "hunter2",
    })
    assert link.port == 9999
    assert link._secret == "hunter2"


def test_tcp_without_secret_is_refused():
    """Ein offener Port im WLAN ohne Geheimnis ist ein Konfigurationsfehler,
    kein zulaessiger Betriebsmodus -- lieber laut scheitern als still offen sein."""
    try:
        build_transport(_noop, env={"COMPANION_TRANSPORT": "tcp"})
    except ValueError:
        return
    # kein raise: nur zulaessig, wenn ausdruecklich erlaubt
    raise AssertionError("erwartet: ValueError ohne COMPANION_TCP_SECRET")
