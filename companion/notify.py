"""Sound-Notification: Entscheidungslogik (rein) + Wiedergabe (I/O-Rand)."""
import subprocess

_CHANNELS = {"waiting": "waiting", "done": "done", "error": "error"}


class NotifyDecider:
    def __init__(self, debounce: float = 2.0) -> None:
        self._debounce = debounce
        self._last_state: str | None = None
        self._last_fire = float("-inf")
        self.muted = False

    def decide(self, state: str, now: float) -> str | None:
        prev, self._last_state = self._last_state, state
        if self.muted or state == prev:
            return None
        channel = _CHANNELS.get(state)
        if channel is None:
            return None
        if now - self._last_fire < self._debounce:
            return None
        self._last_fire = now
        return channel


def play(channel: str, assets_dir: str) -> None:
    """Fire-and-forget WAV-Wiedergabe; Fehler still schlucken (nie Loop blockieren)."""
    try:
        subprocess.Popen(
            ["paplay", f"{assets_dir}/{channel}.wav"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
