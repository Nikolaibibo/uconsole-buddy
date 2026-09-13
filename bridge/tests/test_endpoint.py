"""Der Control-Endpunkt zwischen Hooks und Daemon — eine Quelle für beide Seiten.

Vorher stand er zweimal hartkodiert: `daemon.py` auf `~/opt/...`, `hooks/_send.py`
auf `~/Documents/web/...`. Die beiden sind auseinandergelaufen und niemand hat es
gemerkt, weil diese Schicht keinen Test hatte. Dieselbe Klasse Fehler wie der
`statusline_tee.py`-Drift vom 07.09. Deshalb: eine Funktion, beide importieren sie.

TCP auf dem Loopback statt Unix-Socket, weil `asyncio.start_unix_server` unter
Windows nicht existiert und zwei Codepfade zwei Fehlerquellen wären.
"""
import pytest

from bridge.endpoint import control_endpoint


def test_defaults_to_loopback():
    """Nur Loopback — der Endpunkt darf nie im Netz hängen, er hat keine Auth."""
    host, port = control_endpoint(env={})
    assert host == "127.0.0.1"
    assert isinstance(port, int)


def test_env_overrides_host_and_port():
    assert control_endpoint(env={"BRIDGE_CONTROL_ADDR": "127.0.0.1:9999"}) == ("127.0.0.1", 9999)


def test_rejects_a_non_loopback_address():
    """Ein Tippfehler wie 0.0.0.0 würde den Endpunkt lautlos im WLAN öffnen."""
    with pytest.raises(ValueError, match="Loopback"):
        control_endpoint(env={"BRIDGE_CONTROL_ADDR": "0.0.0.0:8767"})


def test_rejects_a_malformed_address():
    with pytest.raises(ValueError):
        control_endpoint(env={"BRIDGE_CONTROL_ADDR": "keinport"})
