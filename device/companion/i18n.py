"""Lokalisierung — alle sichtbaren Strings pro Sprache.

Sprache über Env-Var `GERALD_LANG` (`en` | `de` | `ko`, Default `en`). Auf Nikolais
Gerät setzt run-debug.sh `GERALD_LANG=de`; öffentliche Klone starten englisch.

Hinweis: das große Status-Wort wird mit figlet (ASCII-Blockschrift) gerendert.
Für nicht-lateinische Sprachen (z.B. `ko`) fällt big_word() auf normalen Text
zurück — dafür muss die Terminal-Schrift die Glyphen haben (Hangul: fonts-nanum
/ Noto CJK)."""
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
    "ko": {
        "idle": "대기", "thinking": "생각 중", "running": "작업 중",
        "waiting": "확인 필요", "done": "완료", "error": "오류",
        "offline": "오프라인", "disconnected": "오프라인", "_fallback": "…",
        "connected": "연결됨", "disc": "끊김",
        "sound_on": "소리 켬", "muted": "음소거",
        "may_i": "허용?", "yes": "예", "no": "아니오",
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
