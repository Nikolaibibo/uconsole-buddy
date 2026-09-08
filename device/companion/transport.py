# companion/transport.py
"""Wählt den Transport: BLE (Default) oder TCP im WLAN.

BLE bleibt Default, damit der bestehende Mac-Betrieb unverändert weiterläuft.
Der PC-Betrieb setzt `COMPANION_TRANSPORT=tcp`.
"""
import os
from typing import Callable, Mapping, Optional

from .ble_nus import NusPeripheral
from .tcp_nus import TcpPeripheral, DEFAULT_PORT

DEVICE_NAME = "Claude-uConsole"


def build_transport(on_line: Callable[[str], None],
                    env: Optional[Mapping[str, str]] = None):
    env = os.environ if env is None else env
    kind = env.get("COMPANION_TRANSPORT", "ble").strip().lower()

    if kind == "ble":
        return NusPeripheral(DEVICE_NAME, on_line)

    if kind == "tcp":
        secret = env.get("COMPANION_TCP_SECRET", "")
        if not secret:
            # Ohne Geheimnis waere der Port im ganzen WLAN offen. Das ist ein
            # Konfigurationsfehler, kein Betriebsmodus -- deshalb laut.
            raise ValueError(
                "COMPANION_TRANSPORT=tcp erfordert COMPANION_TCP_SECRET "
                "(sonst kann jeder im Netz Snapshots schicken)"
            )
        return TcpPeripheral(
            DEVICE_NAME, on_line,
            host=env.get("COMPANION_TCP_HOST", "0.0.0.0"),
            port=int(env.get("COMPANION_TCP_PORT", DEFAULT_PORT)),
            secret=secret,
        )

    raise ValueError(f"unbekannter COMPANION_TRANSPORT: {kind!r} (erlaubt: ble, tcp)")
