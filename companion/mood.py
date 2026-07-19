"""State → gezeichnetes Gesicht, Status-Wort, Farbe. Hier lebt der Charakter."""

# Pro Zustand: Augen + Mund (im Kopf-Rahmen zentriert), Status-Wort, Farbe, kleiner Hinweis.
_FACES = {
    "idle":         {"eyes": "-     -", "mouth": " ‿ ", "word": "schläft",     "color": "grey50",  "hint": "z z z"},
    "thinking":     {"eyes": "◔     ◔", "mouth": " ~ ", "word": "denke nach",  "color": "#5aa9e6", "hint": "?"},
    "running":      {"eyes": "●     ●", "mouth": " ◡ ", "word": "arbeite",     "color": "#4caf50", "hint": ""},
    "waiting":      {"eyes": "◕     ◕", "mouth": " o ", "word": "brauch dich!","color": "#ffb300", "hint": ""},
    "done":         {"eyes": "^     ^", "mouth": " ◡ ", "word": "fertig!",     "color": "#8bc34a", "hint": ""},
    "error":        {"eyes": "×     ×", "mouth": " o ", "word": "autsch",      "color": "#e53935", "hint": "!"},
    "offline":      {"eyes": "·     ·", "mouth": "...", "word": "offline",     "color": "grey37",  "hint": ""},
    "disconnected": {"eyes": "·     ·", "mouth": "...", "word": "offline",     "color": "grey37",  "hint": ""},
}
_FALLBACK = {"eyes": "·     ·", "mouth": " . ", "word": "…", "color": "grey50", "hint": ""}

HEAD_W = 13  # innere Breite des Kopfes


def mood_for(state: str) -> dict:
    return _FACES.get(state, _FALLBACK)


def face_box(state: str) -> str:
    """Vierzeiliges gezeichnetes Gesicht; Augen/Mund je Zustand, Rahmen konstant."""
    m = mood_for(state)
    top = "╭" + "─" * HEAD_W + "╮"
    eyes = "│" + m["eyes"].center(HEAD_W) + "│"
    mouth = "│" + m["mouth"].center(HEAD_W) + "│"
    bot = "╰" + "─" * HEAD_W + "╯"
    return "\n".join([top, eyes, mouth, bot])
