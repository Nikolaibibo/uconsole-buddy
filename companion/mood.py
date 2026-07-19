"""State → gezeichnetes Gesicht (Brauen/Augen/Mund), Farbe, Akzent-Hinweis.
Das sichtbare Status-Wort kommt aus i18n (word_for); hier nur sprachneutrale Optik.

Brauen tragen die Emotion (hoch = wach/froh, gerade = neutral, schräg-runter = böse).
Box-Diagonalen ╲ ╱ statt ASCII \\ / — ein Backslash am Zeilenende würde sonst
Textual-Markup ([...]) zerschießen."""

_FACES = {
    "idle":         {"brows": "‾     ‾", "eyes": "─     ─", "mouth": " ‿ ",   "color": "#8a8a8a", "hint": "z z z"},
    "thinking":     {"brows": "˘     ˘", "eyes": "◔     ◔", "mouth": " ~~~ ",  "color": "#5aa9e6", "hint": "?"},
    "running":      {"brows": "‾     ‾", "eyes": "●     ●", "mouth": "╲___╱",  "color": "#4caf50", "hint": ""},
    "waiting":      {"brows": "˘     ˘", "eyes": "◕     ◕", "mouth": " (O) ",  "color": "#ffb300", "hint": ""},
    "done":         {"brows": "˘     ˘", "eyes": "^     ^", "mouth": "╲___╱",  "color": "#8bc34a", "hint": ""},
    "error":        {"brows": "╲     ╱", "eyes": "×     ×", "mouth": "╱‾‾‾╲",  "color": "#e53935", "hint": "!"},
    "offline":      {"brows": "‾     ‾", "eyes": "·     ·", "mouth": " ─── ",  "color": "#6b6b6b", "hint": ""},
    "disconnected": {"brows": "‾     ‾", "eyes": "·     ·", "mouth": " ─── ",  "color": "#6b6b6b", "hint": ""},
}
_FALLBACK = {"brows": "‾     ‾", "eyes": "·     ·", "mouth": " ─── ", "color": "#8a8a8a", "hint": ""}

HEAD_W = 15         # innere Breite des Kopfes
CLOSED_EYES = "─     ─"  # zum Blinzeln (gleiche Breite wie offene Augen)


def mood_for(state: str) -> dict:
    return _FACES.get(state, _FALLBACK)


def _row(s: str) -> str:
    return "│" + s.center(HEAD_W) + "│"


def face_box(state: str, eyes: str | None = None) -> str:
    """Fünfzeiliges Gesicht: Rahmen · Brauen · Augen · Mund · Rahmen.
    `eyes` überschreibt die Augen (fürs Blinzeln)."""
    m = mood_for(state)
    top = "╭" + "─" * HEAD_W + "╮"
    bot = "╰" + "─" * HEAD_W + "╯"
    return "\n".join([top, _row(m["brows"]), _row(eyes or m["eyes"]), _row(m["mouth"]), bot])
