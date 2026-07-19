"""Lokalisierung — alle sichtbaren Strings pro Sprache.

Sprache über Env-Var `GERALD_LANG` (`en` | `de`, Default `en`). Auf Nikolais Gerät
setzt run-debug.sh `GERALD_LANG=de`; öffentliche Klone starten englisch."""
import os

_STRINGS = {
    "en": {
        # Mood-Wörter (großes Status-Wort)
        "idle": "asleep", "thinking": "thinking", "running": "working",
        "waiting": "need you", "done": "done", "error": "ouch",
        "offline": "offline", "disconnected": "offline", "_fallback": "...",
        # Fußzeile
        "connected": "connected", "disc": "disconnected",
        "sound_on": "sound on", "muted": "muted",
        # Approval-Overlay
        "may_i": "may i?", "yes": "yes", "no": "no",
    },
    "de": {
        "idle": "schläft", "thinking": "denke nach", "running": "arbeite",
        "waiting": "brauch dich", "done": "fertig", "error": "autsch",
        "offline": "offline", "disconnected": "offline", "_fallback": "…",
        "connected": "verbunden", "disc": "getrennt",
        "sound_on": "Ton an", "muted": "stumm",
        "may_i": "darf ich?", "yes": "klar", "no": "nö",
    },
}

_MOOD_STATES = {"idle", "thinking", "running", "waiting", "done", "error",
                "offline", "disconnected"}

LANG = os.environ.get("GERALD_LANG", "en").lower()
if LANG not in _STRINGS:
    LANG = "en"


def t(key: str) -> str:
    """Übersetzten String holen; Fallback auf Englisch, dann auf den Key selbst."""
    return _STRINGS.get(LANG, _STRINGS["en"]).get(key, _STRINGS["en"].get(key, key))


def word_for(state: str) -> str:
    """Lokalisiertes Status-Wort für einen Mood-State (unbekannt → Fallback)."""
    return t(state) if state in _MOOD_STATES else t("_fallback")
