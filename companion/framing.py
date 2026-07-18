"""Byte-Framing für Nordic-UART-Serial-over-BLE. Reine Logik, keine BLE-Deps."""


class LineReassembler:
    """Puffert eingehende Bytes und gibt vollständige `\n`-terminierte UTF-8-Zeilen zurück."""

    def __init__(self, max_len: int = 8192) -> None:
        self._buf = bytearray()
        self.max_len = max_len

    def feed(self, data: bytes) -> list[str]:
        self._buf.extend(data)
        lines: list[str] = []
        while True:
            i = self._buf.find(b"\n")
            if i < 0:
                break
            raw = bytes(self._buf[:i])
            del self._buf[: i + 1]
            try:
                lines.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                pass  # kaputte Zeile verwerfen, weitermachen
        if len(self._buf) > self.max_len:
            self._buf.clear()  # Müll ohne Zeilenende → droppen, beim nächsten \n resyncen
        return lines


def chunk_for_mtu(data: bytes, mtu: int) -> list[bytes]:
    """Splittet `data` in Notify-taugliche Chunks (ATT-Payload = MTU-3, gedeckelt bei 180)."""
    size = mtu - 3 if mtu > 3 else 20
    if size > 180:
        size = 180
    return [data[i : i + size] for i in range(0, len(data), size)]
