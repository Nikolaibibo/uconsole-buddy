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
        # Tastenkuerzel-Leiste
        "k_usage": "usage", "k_synth": "synthwave", "k_back": "back",
        "k_mute": "mute", "k_unmute": "sound", "k_quit": "quit",
    },
    "de": {
        "idle": "schläft", "thinking": "denke nach", "running": "arbeite",
        "waiting": "brauch dich", "done": "fertig", "error": "autsch",
        "offline": "offline", "disconnected": "offline", "_fallback": "…",
        "connected": "verbunden", "disc": "getrennt",
        "sound_on": "Ton an", "muted": "stumm",
        "may_i": "darf ich?", "yes": "klar", "no": "nö",
        "k_usage": "usage", "k_synth": "synthwave", "k_back": "zurück",
        "k_mute": "stumm", "k_unmute": "Ton an", "k_quit": "beenden",
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


def hints(screen: str | None = None, in_prompt: bool = False,
          muted: bool = False) -> str:
    """Tastenkuerzel-Leiste für die Fußzeile, als Klartext (Farbe macht die UI).

    Kontextabhängig: während einer Freigabe zählen nur y/n — die Screen-Tasten
    sind dort wirkungslos (das Overlay hat Vorrang) und würden nur in die Irre
    führen. Ist ein Screen offen, schließt dieselbe Taste ihn wieder."""
    if in_prompt:
        pairs = [("y", t("yes")), ("n", t("no"))]
    else:
        pairs = [
            ("u", t("k_back") if screen == "cards" else t("k_usage")),
            ("s", t("k_back") if screen == "synth" else t("k_synth")),
            ("m", t("k_unmute") if muted else t("k_mute")),
            ("q", t("k_quit")),
        ]
    return "   ".join(f"[{k}] {label}" for k, label in pairs)
