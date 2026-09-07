# companion/usage_screen.py
"""Usage-Vollbild im Synthwave-Look: Sonnenuntergang über Perspektiv-Grid, darunter
SESSION- und WEEKLY-Balken. Reine Renderlogik (Rich-Markup als String) — Zeit und
Breite werden injiziert, damit das Ganze ohne Gerät testbar bleibt.

Wichtig: die HUD-Felder `usage_5h`/`usage_7d` sind **verbraucht**, der Screen zeigt
**verbleibend**. Fehlt ein Wert, steht dort `--%` — nie eine erfundene Zahl."""
from datetime import datetime, timezone

from .hud import _countdown

PINK = "#ff5fa2"
CYAN = "#3fd8ff"
VIOLET = "#a04ce0"
SUN_HOT = "#ffb347"
SUN_MID = "#ff7a59"
SUN_LOW = "#ff3d8b"
DIM = "#6b5f8a"
WARN = "#e53935"

WARN_AT = 85  # ab so viel *verbraucht* wird der Rahmen rot

_SUN = [
    ("▄▄▄███████▄▄▄", SUN_HOT),
    ("███████████████████", SUN_HOT),
    ("▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀", VIOLET),
    ("███████████████████", SUN_MID),
    ("▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀", VIOLET),
    ("█████████████████", SUN_LOW),
    ("▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀", VIOLET),
    ("███████████", SUN_LOW),
]

_SUN_SMALL = [
    ("▄▄▄█████▄▄▄", SUN_HOT),
    ("███████████████", SUN_HOT),
    ("▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀", VIOLET),
    ("█████████████", SUN_LOW),
    ("▀▀▀▀▀▀▀▀▀▀▀▀▀", VIOLET),
]

_GRID = [
    "╲     ╲    ╲   │   ╱    ╱     ╱",
    " ╲    ╲   ╲   │   ╱   ╱    ╱",
]

_STAR_SEEDS = (3, 11, 19, 28, 37, 46, 58, 67, 79, 88)


def remaining_pct(used) -> int | None:
    """Verbraucht → verbleibend. None bleibt None (kein Wert ist keine 100 %)."""
    if not isinstance(used, (int, float)):
        return None
    return max(0, min(100, 100 - round(used)))


def remaining_bar(pct, cells: int = 20) -> str:
    """Balken über `cells` Zellen. Ohne Wert: komplett leer, aber volle Länge."""
    if not isinstance(pct, (int, float)):
        return "▱" * cells
    filled = max(0, min(cells, round(pct / 100 * cells)))
    return "▰" * filled + "▱" * (cells - filled)


def border_color(hud: dict | None) -> str:
    """Rahmenfarbe: violett normal, rot sobald ein Kontingent knapp wird."""
    if not hud:
        return VIOLET
    for key in ("usage_5h", "usage_7d"):
        v = hud.get(key)
        if isinstance(v, (int, float)) and v > WARN_AT:
            return WARN
    return VIOLET


def _title_lines(width: int) -> list[str]:
    """CLAUDE / USAGE als Blockschrift; fällt auf Klartext zurück, wenn es nicht passt."""
    try:
        from pyfiglet import Figlet
        fig = Figlet(font="small")
        out: list[str] = []
        for word in ("CLAUDE", "USAGE"):
            art = [l.rstrip() for l in fig.renderText(word).splitlines() if l.strip()]
            if not art or max(len(l) for l in art) > width:
                raise ValueError
            out.extend(art)
        return out
    except Exception:
        return ["CLAUDE", "USAGE"]


def _center(s: str, width: int) -> str:
    s = s[:width]
    return " " * ((width - len(s)) // 2) + s


def _starfield(width: int, frame: int) -> str:
    """Deterministisches Sternenband; einzelne Sterne blinken über den UI-Tick."""
    row = [" "] * width
    for i, seed in enumerate(_STAR_SEEDS):
        pos = (seed * 7) % max(1, width)
        row[pos] = "·" if (frame // 3 + i) % 4 else "✦"
    return "".join(row)


def _metric_rows(label: str, used, color: str, width: int,
                 countdown: str | None = None) -> list[str]:
    pct = remaining_pct(used)
    cells = max(6, min(48, width - 20))
    shown = f"{pct}%" if pct is not None else "--%"
    head = f"  [{color}]{label}[/]"
    pad = width - 2 - len(label) - len(shown) - 2
    rows = [head + " " * max(1, pad) + f"[bold {color}]{shown}[/]"]
    bar = remaining_bar(pct, cells)
    tail = "REMAINING"
    gap = width - 2 - cells - len(tail) - 2
    rows.append(f"  [{color}]{bar}[/]" + " " * max(1, gap) + f"[{DIM}]{tail}[/]")
    if countdown:
        rows.append(f"  [{DIM}]↺ {countdown}[/]")
    return rows


def usage_art(hud: dict | None, now_utc: datetime | None = None,
              width: int = 80, height: int = 24, frame: int = 0) -> str:
    """Kompletter Screen als Rich-Markup-String.

    Die Metriken sind der Zweck des Screens und werden **nie** gekürzt. Passt die Deko
    nicht in `height`, fällt sie in Prioritätsreihenfolge weg (Grid vor Sonne vor Titel)
    — auf dem 720p-Panel bleiben nur ~24 Zeilen, das reicht nicht für alles."""
    now_utc = now_utc or datetime.now(timezone.utc)
    hud = hud or {}
    width = max(40, width)

    session = _metric_rows("SESSION", hud.get("usage_5h"), PINK, width,
                           _countdown(hud.get("reset_5h_iso", ""), now_utc))
    weekly = _metric_rows("WEEKLY", hud.get("usage_7d"), CYAN, width)
    must = session + [""] + weekly

    budget = max(0, height - len(must))
    plan = {"rule": False, "sun": 0, "title": "none", "grid": 0, "stars": False, "gap": 0}

    def take(n: int) -> bool:
        nonlocal budget
        if budget >= n:
            budget -= n
            return True
        return False

    # Reihenfolge = Wichtigkeit. Erst jede Deko einmal klein, dann die Upgrades.
    plan["rule"] = take(1)
    if take(len(_SUN_SMALL)):
        plan["sun"] = len(_SUN_SMALL)
    if take(1):
        plan["title"] = "plain"
    if take(1):
        plan["grid"] = 1
    plan["stars"] = take(1)
    if take(1):
        plan["gap"] = 1
    if plan["sun"] and take(len(_SUN) - len(_SUN_SMALL)):
        plan["sun"] = len(_SUN)
    if plan["title"] == "plain":
        fig = _title_lines(width)
        if len(fig) > 1 and take(len(fig) - 1):
            plan["title"] = "fig"
    if plan["grid"] and take(1):
        plan["grid"] = 2
    if plan["gap"] and take(1):
        plan["gap"] = 2

    lines: list[str] = []
    if plan["stars"]:
        lines.append(f"[{DIM}]{_starfield(width, frame)}[/]")
    if plan["title"] == "fig":
        for l in _title_lines(width):
            lines.append(f"[bold {PINK}]{_center(l, width)}[/]")
    elif plan["title"] == "plain":
        lines.append(f"[bold {PINK}]{_center('C L A U D E   U S A G E', width)}[/]")
    if plan["gap"] >= 1:
        lines.append("")
    sun = _SUN if plan["sun"] == len(_SUN) else _SUN_SMALL
    for art, color in (sun if plan["sun"] else []):
        lines.append(f"[{color}]{_center(art, width)}[/]")
    for g in _GRID[:plan["grid"]]:
        lines.append(f"[{VIOLET}]{_center(g, width)}[/]")
    if plan["rule"]:
        lines.append(f"[{VIOLET}]{'─' * width}[/]")
    if plan["gap"] >= 2:
        lines.append("")
    lines.extend(must)
    return "\n".join(lines)
