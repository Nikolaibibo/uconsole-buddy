# companion/usage_cards.py
"""Usage-Vollbild im Karten-Look, nachgebaut nach Claude Codes eigenem /usage-Screen:
grosse Prozentzahl fuers 5h-Fenster, darunter WEEKLY und die beiden Pacing-Karten.

Gezeigt wird **verbraucht** (wie im Vorbild), nicht verbleibend. Fehlt ein Wert,
steht `--%` — nie eine erfundene Zahl.

⚠️ Die Pacing-Zahl ist **abgeleitet, nicht dokumentiert.** Claude Codes /usage nennt
seine Formel nirgends; sie wurde aus zwei Datenpunkten (07.09.2026) rekonstruiert:
`verbraucht% − abgelaufen%` in Prozentpunkten, und der Marker im Balken sitzt bei
`abgelaufen%`. Beide Beispiele passen auf 1 Punkt genau (Rundung). Das ist eine
begruendete Vermutung, kein gesicherter Wert — wer sie zitiert, sagt das dazu."""
from datetime import datetime, timezone

GREEN = "#4ade80"
GREEN_DIM = "#22c55e"
LABEL = "#6b7280"
TRACK = "#374151"
AMBER = "#fbbf24"
RED = "#ef4444"

WARN_AT = 85
FIVE_HOUR_H = 5
SEVEN_DAY_H = 24 * 7


def _parse(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:
        return None


def elapsed_pct(reset_iso: str, window_hours: float, now_utc: datetime) -> float | None:
    """Wieviel Prozent des Fensters sind durch? Leitet sich aus dem Reset-Zeitpunkt ab:
    was nicht mehr uebrig ist, ist abgelaufen."""
    t = _parse(reset_iso)
    if t is None or window_hours <= 0:
        return None
    remaining_h = (t - now_utc).total_seconds() / 3600.0
    return max(0.0, min(100.0, (window_hours - remaining_h) / window_hours * 100.0))


def pacing(used, elapsed) -> int | None:
    """Verbraucht minus abgelaufen, in Prozentpunkten. Negativ = entspannter als linear."""
    if not isinstance(used, (int, float)) or not isinstance(elapsed, (int, float)):
        return None
    return round(used - elapsed)


def pacing_label(p, weekly: bool = False) -> tuple[str, str]:
    """(Kurzlabel, Fliesstext) — Schwellen selbst gesetzt, das Vorbild nennt keine."""
    if p is None:
        return "--", ""
    if p <= -30:
        return "Chill", "Easy week" if weekly else "Time to spare"
    if p <= 10:
        return "On track", "Steady"
    return "Hot", "Burning fast"


def _color(used) -> str:
    if not isinstance(used, (int, float)):
        return LABEL
    if used > WARN_AT:
        return RED
    if used > 60:
        return AMBER
    return GREEN


def border_color(hud: dict | None) -> str:
    """Rahmenfarbe: gruen normal, gelb/rot sobald ein Kontingent knapp wird."""
    if not hud:
        return LABEL
    worst = LABEL
    for key in ("usage_5h", "usage_7d"):
        c = _color(hud.get(key))
        if c == RED:
            return RED
        if c == AMBER:
            worst = AMBER
        elif worst is LABEL and c == GREEN:
            worst = GREEN
    return worst


def _pct(v) -> str:
    return f"{round(v)}%" if isinstance(v, (int, float)) else "--%"


def _countdown(reset_iso: str, now_utc: datetime) -> str | None:
    t = _parse(reset_iso)
    if t is None:
        return None
    secs = (t - now_utc).total_seconds()
    if secs <= 0:
        return None
    d, rem = int(secs // 86400), secs % 86400
    h, m = int(rem // 3600), int(rem % 3600 // 60)
    if d:
        return f"{d}d{h:02d}h"
    return f"{h}h{m:02d}" if h else f"{m}m"


def _local(reset_iso: str) -> str:
    t = _parse(reset_iso)
    return t.astimezone().strftime("%H:%M") if t else ""


def _bar(fill, marker=None, cells: int = 20, color: str = GREEN) -> str:
    """Balken: Fuellung = Verbrauch, senkrechter Strich = wo man bei linearem Tempo waere."""
    f = 0 if not isinstance(fill, (int, float)) else max(0, min(cells, round(fill / 100 * cells)))
    m = None if not isinstance(marker, (int, float)) else max(0, min(cells - 1, round(marker / 100 * cells)))
    out = []
    for i in range(cells):
        if m is not None and i == m:
            out.append(f"[{LABEL}]┃[/]")
        elif i < f:
            out.append(f"[{color}]━[/]")
        else:
            out.append(f"[{TRACK}]╌[/]")
    return "".join(out)


def _plain_len(s: str) -> int:
    import re
    return len(re.sub(r"\[/?[^\]]*\]", "", s))


def _card(title: str, rows: list[str], width: int) -> list[str]:
    """Rahmenkarte fester Breite. rows sind Markup-Zeilen ohne Rand."""
    inner = width - 4
    # Kopfzeile muss exakt so breit werden wie die Koerperzeilen ("│ " + inner + " │"),
    # sonst steht der Rahmen rechts offen: 2 Zeichen Praefix, 1 Fuellzeichen, 1 Ecke.
    fill = max(0, width - 4 - len(title) - 1)
    head = f"╭─ [{LABEL}]{title}[/] " + "─" * fill + "╮"
    out = [head]
    for r in rows:
        pad = max(0, inner - _plain_len(r))
        out.append(f"│ {r}{' ' * pad} │")
    out.append("╰" + "─" * (width - 2) + "╯")
    return out


def _big(text: str, width: int) -> list[str]:
    """Grosse Zahl per figlet; faellt auf Klartext zurueck, wenn es nicht passt."""
    try:
        from pyfiglet import Figlet
        raw = Figlet(font="banner").renderText(text).splitlines()
        # banner malt mit '#'; als Vollblock liest sich die Zahl wie im Vorbild.
        art = [l.rstrip().replace("#", "█") for l in raw if l.strip()]
        if art and max(len(l) for l in art) <= width:
            return art
    except Exception:
        pass
    return [text]


def _side_by_side(left: list[str], right: list[str], gap: int = 1) -> list[str]:
    n = max(len(left), len(right))
    left += [""] * (n - len(left))
    right += [""] * (n - len(right))
    lw = max((_plain_len(l) for l in left), default=0)
    return [l + " " * (lw - _plain_len(l) + gap) + r for l, r in zip(left, right)]


def cards_art(hud: dict | None, now_utc: datetime | None = None,
              width: int = 120, height: int = 24, frame: int = 0) -> str:
    now_utc = now_utc or datetime.now(timezone.utc)
    hud = hud or {}
    width = max(60, width)

    u5, u7 = hud.get("usage_5h"), hud.get("usage_7d")
    e5 = elapsed_pct(hud.get("reset_5h_iso", ""), FIVE_HOUR_H, now_utc)
    e7 = elapsed_pct(hud.get("reset_7d_iso", ""), SEVEN_DAY_H, now_utc)
    c5, c7 = _color(u5), _color(u7)

    # --- Karte 1: SESSION, volle Breite, grosse Zahl ---
    big = _big(_pct(u5), width - 6)
    rows = [f"[bold {c5}]{l}[/]" for l in big]
    cd5, at5 = _countdown(hud.get("reset_5h_iso", ""), now_utc), _local(hud.get("reset_5h_iso", ""))
    when = f"{cd5} · {at5}" if cd5 and at5 else (cd5 or "--")
    rows.append(f"[{LABEL}]RESETS IN[/] [{GREEN_DIM}]{when}[/]")
    session = _card("SESSION · 5H WINDOW", rows, width)

    # --- Karte 2: WEEKLY, volle Breite ---
    cd7, at7 = _countdown(hud.get("reset_7d_iso", ""), now_utc), _local(hud.get("reset_7d_iso", ""))
    when7 = f"{cd7} · {at7}" if cd7 and at7 else (cd7 or "--")
    weekly = _card("WEEKLY", [
        f"[bold {c7}]{_pct(u7)}[/]",
        _bar(u7, None, cells=max(10, width - 12), color=c7),
        f"[{LABEL}]RESETS IN[/] [{GREEN_DIM}]{when7}[/]",
    ], width)

    # --- Karten 3+4: Pacing nebeneinander ---
    half = (width - 1) // 2
    pace_cards = []
    for title, used, elapsed, weekly_flag in (
            ("SESSION PACING", u5, e5, False), ("WEEKLY PACING", u7, e7, True)):
        p = pacing(used, elapsed)
        short, long = pacing_label(p, weekly_flag)
        val = f"{p:+d}%" if p is not None else "--%"
        head = f"[{GREEN}]{short}[/]"
        pad = max(1, half - 4 - len(short) - len(val))
        pace_cards.append(_card(title, [
            head + " " * pad + f"[bold {GREEN}]{val}[/]",
            _bar(used, elapsed, cells=max(8, half - 6)),
            f"[{LABEL}]{long}[/]",
        ], half))

    blocks = [session, [""], weekly, [""], _side_by_side(pace_cards[0], pace_cards[1])]
    lines: list[str] = []
    for b in blocks:
        lines.extend(b)
    # Deko-Leerzeilen fliegen zuerst, danach die Pacing-Karten — die Zahlen oben bleiben.
    while len(lines) > height:
        if "" in lines:
            lines.remove("")
        else:
            lines = lines[:height]
    return "\n".join(lines)
