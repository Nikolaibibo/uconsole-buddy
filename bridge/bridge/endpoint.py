"""Der Control-Endpunkt zwischen Hooks und Daemon — eine Quelle für beide Seiten.

Vorher stand er zweimal hartkodiert (`daemon.py` auf `~/opt/...`, `hooks/_send.py`
auf `~/Documents/web/...`) und war auseinandergelaufen. Wer ihn ändern will,
ändert ihn ab jetzt hier oder per `BRIDGE_CONTROL_ADDR`.

TCP auf dem Loopback statt Unix-Socket: `asyncio.start_unix_server` gibt es unter
Windows nicht, und zwei Codepfade wären zwei Fehlerquellen. Der Preis ist das
`chmod 0600` des Unix-Sockets — dafür ist der Endpunkt hart auf Loopback
begrenzt, damit ein Tippfehler ihn nicht ins WLAN hängt.
"""
import os
from typing import Mapping, Optional, Tuple

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767

_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def control_endpoint(env: Optional[Mapping[str, str]] = None) -> Tuple[str, int]:
    env = os.environ if env is None else env
    raw = env.get("BRIDGE_CONTROL_ADDR", "").strip()
    if not raw:
        return DEFAULT_HOST, DEFAULT_PORT

    host, sep, port = raw.rpartition(":")
    if not sep or not port.isdigit():
        raise ValueError(f"BRIDGE_CONTROL_ADDR muss host:port sein, nicht {raw!r}")
    if host not in _LOOPBACK:
        raise ValueError(
            f"BRIDGE_CONTROL_ADDR muss auf Loopback zeigen, nicht {host!r} — "
            "der Endpunkt hat keine Authentifizierung"
        )
    return host, int(port)
