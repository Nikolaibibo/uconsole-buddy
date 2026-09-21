# companion/logfmt.py — what incoming lines look like in companion.log.
"""The log is the ground truth when Gerald shows offline, so connection events stay in.
Payloads do not: a snapshot carries the session feed (commands, paths, notification
texts), and companion.log used to collect all of it unrotated. By default an incoming
line is reduced to its shape; COMPANION_DEBUG=1 logs it verbatim again."""
import json
import os

DEBUG = os.environ.get("COMPANION_DEBUG") == "1"


def summarize_rx(line: str, debug: bool | None = None) -> str:
    if debug is None:
        debug = DEBUG
    if debug:
        return line
    try:
        msg = json.loads(line)
    except (ValueError, TypeError):
        return f"<unparseable, {len(line)} chars>"
    if not isinstance(msg, dict):
        return f"<{type(msg).__name__}>"
    if "cmd" in msg:
        return f"cmd={msg['cmd']}"
    if "total" in msg:
        parts = [f"state={msg.get('state', '?')}",
                 f"running={msg.get('running', 0)}",
                 f"waiting={msg.get('waiting', 0)}",
                 f"entries={len(msg.get('entries') or [])}"]
        if msg.get("prompt"):
            parts.append("prompt=yes")
        if msg.get("hud"):
            parts.append("hud=yes")
        return "snapshot " + " ".join(parts)
    # Unknown shape: key names only, never values (a TCP auth line would carry the secret).
    return "keys=" + ",".join(sorted(msg))
