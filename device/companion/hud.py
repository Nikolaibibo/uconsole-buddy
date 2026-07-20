# companion/hud.py
"""HUD-Leiste: rendert die Statusline-Daten der Mac-Session (model/ctx/usage) als eine
Rich-Markup-Zeile. Reine Logik — Zeit wird als now_utc injiziert (Countdown bleibt über
den UI-Tick frisch, ohne neue BLE-Pushes)."""
from datetime import datetime, timezone

GREEN, YELLOW, RED, DIM = "#4caf50", "#ffb300", "#e53935", "#9e9e9e"


def _color(pct: float) -> str:
    if pct > 85:
        return RED
    if pct > 60:
        return YELLOW
    return GREEN


def _bar(pct: float, cells: int = 5) -> str:
    filled = max(0, min(cells, round(pct / 100 * cells)))
    return "▰" * filled + "▱" * (cells - filled)


def _countdown(reset_iso: str, now_utc: datetime) -> str | None:
    """ISO-Zeitstempel → 'Xh YYm' Rest-Countdown; None bei Vergangenheit/Müll."""
    try:
        t = datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
        secs = (t - now_utc).total_seconds()
        if secs <= 0:
            return None
        h, m = int(secs // 3600), int(secs % 3600 // 60)
        return f"{h}h{m:02d}m" if h else f"{m}m"
    except Exception:
        return None


def hud_line(hud: dict | None, now_utc: datetime | None = None) -> str:
    if not hud:
        return ""
    now_utc = now_utc or datetime.now(timezone.utc)
    seg: list[str] = []
    if hud.get("project"):
        seg.append(f"[{DIM}]{hud['project']}[/]")
    if hud.get("model"):
        seg.append(f"[{DIM}]{hud['model']}[/]")
    if isinstance(hud.get("ctx_pct"), (int, float)):
        p = round(hud["ctx_pct"])
        seg.append(f"[{_color(p)}]ctx {_bar(p)} {p}%[/]")
    if isinstance(hud.get("usage_5h"), (int, float)):
        p = round(hud["usage_5h"])
        s = f"[{_color(p)}]5h {p}%[/]"
        cd = _countdown(hud.get("reset_5h_iso", ""), now_utc)
        if cd:
            s += f" [{DIM}]↺ {cd}[/]"
        seg.append(s)
    if isinstance(hud.get("usage_7d"), (int, float)):
        p = round(hud["usage_7d"])
        seg.append(f"[{_color(p)}]7d {p}%[/]")
    return " · ".join(seg)
