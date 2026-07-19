"""State → gezeichnetes Gesicht, Status-Wort, Farbe. Hier lebt der Charakter."""

# Pro Zustand: Augen + Mund (im Kopf zentriert), Status-Wort, Farbe, kleiner Hinweis.
# Augen mit weitem Abstand, damit das große Gesicht Präsenz hat.
_FACES = {
    "idle":         {"eyes": "─         ─", "mouth": " ‿ ", "word": "schläft",      "color": "grey50",  "hint": "z z z"},
    "thinking":     {"eyes": "◔         ◔", "mouth": " ~ ", "word": "denke nach",   "color": "#5aa9e6", "hint": "?"},
    "running":      {"eyes": "●         ●", "mouth": "◡ ◡", "word": "arbeite",      "color": "#4caf50", "hint": ""},
    "waiting":      {"eyes": "◕         ◕", "mouth": " O ", "word": "brauch dich!", "color": "#ffb300", "hint": ""},
    "done":         {"eyes": "^         ^", "mouth": "‿ ‿", "word": "fertig!",      "color": "#8bc34a", "hint": ""},
    "error":        {"eyes": "×         ×", "mouth": " o ", "word": "autsch",       "color": "#e53935", "hint": "!"},
    "offline":      {"eyes": "·         ·", "mouth": " ⁀ ", "word": "offline",      "color": "grey37",  "hint": ""},
    "disconnected": {"eyes": "·         ·", "mouth": " ⁀ ", "word": "offline",      "color": "grey37",  "hint": ""},
}
_FALLBACK = {"eyes": "·         ·", "mouth": " . ", "word": "…", "color": "grey50", "hint": ""}

HEAD_W = 17  # innere Breite des Kopfes


def mood_for(state: str) -> dict:
    return _FACES.get(state, _FALLBACK)


def face_box(state: str) -> str:
    """Großes, siebenzeiliges Gesicht mit Luft; Augen/Mund je Zustand, Rahmen konstant."""
    m = mood_for(state)
    w = HEAD_W
    top = "╭" + "─" * w + "╮"
    bot = "╰" + "─" * w + "╯"
    pad = "│" + " " * w + "│"
    eyes = "│" + m["eyes"].center(w) + "│"
    mouth = "│" + m["mouth"].center(w) + "│"
    return "\n".join([top, pad, eyes, pad, mouth, pad, bot])
