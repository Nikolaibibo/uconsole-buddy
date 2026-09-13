"""Wählt den Transport: BLE (Default) oder TCP im WLAN.

Spiegelbild von `device/companion/transport.py` — bewusst dieselben Env-Namen,
damit man beim Umstellen nicht zwei Vokabulare lernen muss. BLE bleibt Default,
damit ein vorhandenes Setup sich nicht von selbst ändert und der Rückweg eine
einzelne Variable ist.

Unterschied zur Geräteseite: dort ist `COMPANION_TCP_HOST` die Bind-Adresse
(Default `0.0.0.0`), hier ist es das Ziel. Dafür gibt es keinen sinnvollen
Default, also ist die Variable Pflicht.
"""
import os
from typing import Callable, Mapping, Optional

from .ble_central import BleCentral
from .tcp_central import TcpCentral, DEFAULT_PORT

DEVICE_NAME = "Claude-uConsole"


def build_transport(on_line: Callable[[str], None],
                    on_disconnect: Optional[Callable[[], None]] = None,
                    env: Optional[Mapping[str, str]] = None):
    env = os.environ if env is None else env
    kind = env.get("COMPANION_TRANSPORT", "ble").strip().lower()

    if kind == "ble":
        return BleCentral(on_line, device_name=DEVICE_NAME, on_disconnect=on_disconnect)

    if kind == "tcp":
        secret = env.get("COMPANION_TCP_SECRET", "")
        if not secret:
            raise ValueError(
                "COMPANION_TRANSPORT=tcp erfordert COMPANION_TCP_SECRET "
                "(sonst kann jeder im Netz Snapshots schicken)"
            )
        host = env.get("COMPANION_TCP_HOST", "")
        if not host:
            raise ValueError(
                "COMPANION_TRANSPORT=tcp erfordert COMPANION_TCP_HOST "
                "(die Adresse der uConsole, z. B. 192.168.178.146)"
            )
        return TcpCentral(
            on_line,
            host=host,
            port=int(env.get("COMPANION_TCP_PORT", DEFAULT_PORT)),
            secret=secret,
            on_disconnect=on_disconnect,
        )

    raise ValueError(f"unbekannter COMPANION_TRANSPORT: {kind!r} (erlaubt: ble, tcp)")
