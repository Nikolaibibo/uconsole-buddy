"""State → Gesicht + Spruch. Reine Logik, hier lebt der Charakter."""

_MOODS = {
    "idle":     ("😴", "warte auf dich"),
    "thinking": ("🤔", "denke nach…"),
    "running":  ("⚙️", "arbeite…"),
    "waiting":  ("🙋", "brauch dich!"),
    "done":     ("✅", "fertig!"),
    "error":    ("💥", "autsch"),
}


def mood_for(state: str) -> tuple[str, str]:
    return _MOODS.get(state, ("😐", "…"))
