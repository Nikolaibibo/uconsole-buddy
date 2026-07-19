"""Byte-Framing für Nordic-UART. Reine Logik, keine BLE-Deps. (Kopie vom Device-Repo.)"""

class LineReassembler:
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
                pass
        if len(self._buf) > self.max_len:
            self._buf.clear()
        return lines


def chunk_for_mtu(data: bytes, mtu: int) -> list[bytes]:
    size = mtu - 3 if mtu > 3 else 20
    if size > 180:
        size = 180
    return [data[i : i + size] for i in range(0, len(data), size)]
