# companion/ui.py
"""Big-Buddy-Vollbild: großes gezeichnetes Gesicht + Status-Wort, minimaler Kontext.
Approval-Overlay im selben Buddy-Stil. Layout-Richtung: Charakter über Info."""
from typing import Callable, Optional

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical

from .mood import mood_for, face_box
from .state import AppState


def _spaced(word: str) -> str:
    """Status-Wort 'groß' setzen durch Buchstaben-Spreizung."""
    return " ".join(word.upper())


def _clip(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class CompanionApp(App):
    CSS = """
    Screen { align: center middle; }
    #stack { height: auto; width: 100%; align: center middle; }
    #face  { width: 100%; text-align: center; }
    #word  { width: 100%; text-align: center; text-style: bold; padding: 1 0 0 0; }
    #ctx   { width: 100%; text-align: center; color: #9e9e9e; padding: 1 0 0 0; }
    #foot  { dock: bottom; width: 100%; text-align: center; color: #6b6b6b; }
    #overlay { display: none; }
    #overlay.active { display: block; width: 100%; height: 100%; align: center middle; }
    """

    BINDINGS = [
        ("y", "approve", "erlauben"),
        ("enter", "approve", "erlauben"),
        ("n", "deny", "ablehnen"),
        ("escape", "deny", "ablehnen"),
        ("m", "mute", "stumm"),
        ("q", "quit", "beenden"),
    ]

    def __init__(self, on_decision: Callable[[str], None],
                 on_mute: Optional[Callable[[], None]] = None):
        super().__init__()
        self._on_decision = on_decision
        self._on_mute = on_mute
        self._state: Optional[AppState] = None
        self._muted = False

    def compose(self) -> ComposeResult:
        yield Static("", id="foot")
        with Vertical(id="stack"):
            yield Static("", id="face")
            yield Static("", id="word")
            yield Static("", id="ctx")
        yield Static("", id="overlay")

    def render_from_state(self, state: AppState, now: float) -> None:
        self._state = state
        st = state.mood_state(now)
        m = mood_for(st)
        color = m["color"]

        overlay = self.query_one("#overlay", Static)
        stack = self.query_one("#stack", Vertical)

        if state.in_prompt() and state.prompt:
            # Approval hat Vorrang: erwartungsvolles Gesicht nimmt den Screen über
            tool = state.prompt.get("tool", "")
            hint = _clip(state.prompt.get("hint", ""), 46)
            box = face_box("waiting")
            overlay.update(
                f"[#ffb300]{box}[/]\n\n"
                f"[bold #ffb300]{_spaced('darf ich?')}[/]\n\n"
                f"[grey85]{tool} · {hint}[/]\n\n"
                f"[bold]\\[Y] klar     \\[N] nö[/]"
            )
            overlay.add_class("active")
            stack.display = False
        else:
            overlay.remove_class("active")
            stack.display = True
            self.query_one("#face", Static).update(f"[{color}]{face_box(st)}[/]")
            word = _spaced(m["word"])
            if m.get("hint"):
                word = f"{word}    [{color}]{m['hint']}[/]"
            self.query_one("#word", Static).update(f"[bold {color}]{word}[/]")
            ctx = state.entries[-1] if state.entries else state.msg
            self.query_one("#ctx", Static).update(_clip(ctx, 52))

        conn = state.connection_state(now)
        conn_txt = "○ getrennt" if conn == "disconnected" else "● verbunden"
        mute_txt = "✕ stumm" if getattr(self, "_muted", False) else "♪ Ton an"
        self.query_one("#foot", Static).update(f"{conn_txt}     {mute_txt}")

    def action_approve(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("once")

    def action_deny(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("deny")

    def action_mute(self) -> None:
        if self._on_mute:
            self._on_mute()
