# companion/ui.py
"""Big-Buddy-Vollbild: gezeichnetes Gesicht + Blockschrift-Wort (figlet), Mood-Rahmen,
lebendige Animationen (Blinzeln, Spinner, Denk-Punkte, zzz). Approval im Buddy-Stil."""
import time
from typing import Callable, Optional

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Container

from .mood import mood_for, face_box, CLOSED_EYES
from .i18n import t, word_for
from .state import AppState

try:
    from pyfiglet import Figlet
    _FIG = Figlet(font="small")
except Exception:  # pragma: no cover - Fallback wenn pyfiglet fehlt
    _FIG = None

_FOLD = {"Ä": "AE", "Ö": "OE", "Ü": "UE", "ß": "SS", "ä": "AE", "ö": "OE", "ü": "UE"}
_fig_cache: dict = {}


def _ascii(s: str) -> str:
    for k, v in _FOLD.items():
        s = s.replace(k, v)
    return s


def big_word(word: str) -> str:
    """Status-Wort als große ASCII-Blockschrift (figlet), gecacht. Fallback = gespreizte Caps."""
    token = _ascii(word).upper().replace("!", "").strip()
    if token in _fig_cache:
        return _fig_cache[token]
    if _FIG is None:
        art = " ".join(token)
    else:
        art = "\n".join(l.rstrip() for l in _FIG.renderText(token).splitlines() if l.strip())
    _fig_cache[token] = art
    return art


def _clip(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class CompanionApp(App):
    CSS = """
    Screen { align: center middle; }
    #root  { width: 100%; height: 100%; border: round #4caf50; align: center middle; }
    #name  { dock: top; width: 100%; text-align: center; padding: 1 0 0 0; text-style: bold; }
    #stack { height: auto; width: 100%; align: center middle; }
    #face  { width: 100%; text-align: center; }
    #word  { width: 100%; text-align: center; padding: 1 0 0 0; }
    #anim  { width: 100%; text-align: center; }
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
        self._frame = 0

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            yield Static("", id="name")
            yield Static("", id="foot")
            with Vertical(id="stack"):
                yield Static("", id="face")
                yield Static("", id="word")
                yield Static("", id="anim")
                yield Static("", id="ctx")
            yield Static("", id="overlay")

    def on_mount(self) -> None:
        # Animations-Herzschlag (unabhängig von State-Pushes)
        self.set_interval(0.4, self._tick_anim)

    def _tick_anim(self) -> None:
        self._frame += 1
        if self._state is not None:
            self._repaint()

    # ---- Animations-Bausteine ----
    def _animated_face(self, st: str, m: dict) -> str:
        # Blinzeln: kurz die Augen schließen (nicht bei waiting/error — die bleiben wach)
        blink = st in ("idle", "thinking", "running", "done") and self._frame % 14 == 0
        return face_box(st, eyes=CLOSED_EYES if blink else None)

    def _bar(self, width: int = 13, win: int = 3) -> str:
        """Großer Lauf-Balken: ein gefülltes Fenster wandert durch die Zellen (wrap)."""
        pos = self._frame % width
        cells = ["▰" if (i - pos) % width < win else "▱" for i in range(width)]
        return " ".join(cells)   # gespreizt = optisch groß

    def _accent(self, st: str) -> str:
        f = self._frame
        if st in ("running", "thinking"):
            return self._bar()
        if st == "idle":
            return "  ".join(["z"] * ((f // 2) % 3 + 1))
        if st == "waiting":
            return "▼  ▼  ▼" if f % 2 else "         "
        if st == "done":
            return "✓ ✓ ✓"
        if st == "error":
            return "✕ ✕ ✕"
        return ""

    def _repaint(self) -> None:
        state = self._state
        if state is None:
            return
        now = time.monotonic()
        st = state.mood_state(now)
        m = mood_for(st)
        color = m["color"]

        root = self.query_one("#root", Container)
        root.styles.border = ("round", color)
        self.query_one("#name", Static).update(f"[{color}]◦ Gerald ◦[/]")

        overlay = self.query_one("#overlay", Static)
        stack = self.query_one("#stack", Vertical)

        if state.in_prompt() and state.prompt:
            tool = state.prompt.get("tool", "")
            hint = _clip(state.prompt.get("hint", ""), 46)
            root.styles.border = ("round", "#ffb300")
            overlay.update(
                f"[#ffb300]{face_box('waiting')}[/]\n\n"
                f"[bold #ffb300]{big_word(t('may_i'))}[/]\n\n"
                f"[grey85]{tool} · {hint}[/]\n\n"
                f"[bold]\\[Y] {t('yes')}     \\[N] {t('no')}[/]"
            )
            overlay.add_class("active")
            stack.display = False
        else:
            overlay.remove_class("active")
            stack.display = True
            self.query_one("#face", Static).update(f"[{color}]{self._animated_face(st, m)}[/]")
            self.query_one("#word", Static).update(f"[bold {color}]{big_word(word_for(st))}[/]")
            self.query_one("#anim", Static).update(f"[{color}]{self._accent(st)}[/]")
            ctx = state.entries[-1] if state.entries else ""
            self.query_one("#ctx", Static).update(_clip(ctx, 52))

        conn = state.connection_state(now)
        conn_txt = f"○ {t('disc')}" if conn == "disconnected" else f"● {t('connected')}"
        mute_txt = f"✕ {t('muted')}" if getattr(self, "_muted", False) else f"♪ {t('sound_on')}"
        self.query_one("#foot", Static).update(f"{conn_txt}     {mute_txt}")

    def render_from_state(self, state: AppState, now: float) -> None:
        self._state = state
        self._repaint()

    def action_approve(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("once")

    def action_deny(self) -> None:
        if self._state and self._state.in_prompt():
            self._on_decision("deny")

    def action_mute(self) -> None:
        if self._on_mute:
            self._on_mute()
