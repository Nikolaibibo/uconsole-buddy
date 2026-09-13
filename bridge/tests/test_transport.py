"""Die Weiche zwischen BLE und TCP — Spiegelbild von device/companion/transport.py.

Absichtlich dieselben Env-Namen wie auf der Geräteseite: wer den Betrieb
umstellt, fasst beide Enden an und soll dabei nicht zwei Vokabulare lernen.
BLE bleibt Default, damit ein vorhandenes Setup sich nicht von selbst ändert.
"""
import pytest

from bridge.ble_central import BleCentral
from bridge.tcp_central import TcpCentral
from bridge.transport import build_transport


def noop(_line: str) -> None:
    pass


def test_defaults_to_ble_when_nothing_is_configured():
    link = build_transport(noop, env={})
    assert isinstance(link, BleCentral)


def test_tcp_refuses_to_start_without_a_secret():
    """Ohne Geheimnis stünde der Port im ganzen WLAN offen. Das ist ein
    Konfigurationsfehler, kein Betriebsmodus — deshalb laut."""
    with pytest.raises(ValueError, match="COMPANION_TCP_SECRET"):
        build_transport(noop, env={
            "COMPANION_TRANSPORT": "tcp",
            "COMPANION_TCP_HOST": "192.168.178.146",
        })


def test_tcp_refuses_to_start_without_a_host():
    """Anders als das Gerät (das lauscht) muss die Bridge wissen, wohin —
    einen sinnvollen Default gibt es dafür nicht."""
    with pytest.raises(ValueError, match="COMPANION_TCP_HOST"):
        build_transport(noop, env={
            "COMPANION_TRANSPORT": "tcp",
            "COMPANION_TCP_SECRET": "s3cr3t",
        })


def test_tcp_takes_host_port_and_secret_from_env():
    link = build_transport(noop, env={
        "COMPANION_TRANSPORT": "tcp",
        "COMPANION_TCP_HOST": "192.168.178.146",
        "COMPANION_TCP_PORT": "9001",
        "COMPANION_TCP_SECRET": "s3cr3t",
    })
    assert isinstance(link, TcpCentral)
    assert link._host == "192.168.178.146"
    assert link._port == 9001
    assert link._secret == "s3cr3t"


def test_unknown_transport_is_rejected():
    with pytest.raises(ValueError, match="zigbee"):
        build_transport(noop, env={"COMPANION_TRANSPORT": "zigbee"})


def test_on_disconnect_is_passed_through():
    """Der Daemon hängt seine fail_pending-Logik daran — geht das verloren,
    bleiben wartende Freigaben nach einem Abbruch für immer stehen."""
    calls: list[int] = []
    link = build_transport(noop, on_disconnect=lambda: calls.append(1), env={
        "COMPANION_TRANSPORT": "tcp",
        "COMPANION_TCP_HOST": "192.168.178.146",
        "COMPANION_TCP_SECRET": "s3cr3t",
    })
    link._on_disconnect()
    assert calls == [1]
