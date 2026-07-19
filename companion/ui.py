# companion/ui.py
"""Textual-Fenster-App: Status-Panels + Freigabe-Overlay. Layout aus Spec §7."""
from typing import Callable

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical

from .state import AppState
from .mood import mood_for


class CompanionApp(App):
    CSS = """
    #face { padding: 1; text-style: bold; }
    #overlay { display: none; border: heavy $warning; padding: 1; }
    #overlay.active { display: block; }
    #status { padding: 1; }
    """
    BINDINGS = [
        ("y", "approve", "erlauben"),
        ("enter", "approve", "erlauben"),
        ("n", "deny", "ablehnen"),
        ("escape", "deny", "ablehnen"),
        ("q", "quit", "beenden"),
    ]

    def __init__(self, on_decision: Callable[[str], None]):
        super().__init__()
        self._on_decision = on_decision
        self._state: AppState | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="face")
            yield Static("", id="status")
            yield Static("", id="overlay")

    def render_from_state(self, state: AppState, now: float) -> None:
        self._state = state
        face, spruch = mood_for(state.mood_state(now))
        self.query_one("#face", Static).update(f"{face}  {spruch}")
        conn = state.connection_state(now)
        lock = "🔒" if state.secure else ""
        lines = state.entries[:3]
        body = (
            f"● {conn} {lock}   Owner: {state.owner or '—'}\n"
            f"Sessions: total {state.total}  running {state.running}  waiting {state.waiting}\n"
            f"» {state.msg}\n"
            f"— letzte Zeilen —\n" + "\n".join(lines) + "\n"
            f"session {state.tokens/1000:.1f}k  today {state.tokens_today/1000:.1f}k  "
            f"✓{state.appr} ✗{state.deny}"
        )
        self.query_one("#status", Static).update(body)

        overlay = self.query_one("#overlay", Static)
        if state.in_prompt() and state.prompt:
            overlay.update(
                f"⚠ FREIGABE\nTool: {state.prompt.get('tool','')}\n"
                f"{state.prompt.get('hint','')}\n\n[Y] einmal erlauben   [N] ablehnen"
            )
            overlay.add_class("active")
        else:
            overlay.remove_class("active")

    def action_approve(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("once")

    def action_deny(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("deny")
