#!/usr/bin/env python3
import json, os, sys
from datetime import datetime
from _send import send_status, FULL_FEED

MAXLEN = 60


def feed_line(tool, tool_input, hhmm, full=None):
    if full is None:
        full = FULL_FEED
    if not full:
        # Category only: "mcp__hubspot__search" would already name the system in use.
        category = "MCP" if tool.startswith("mcp__") else tool
        return f"{hhmm} {category}"[:MAXLEN]
    ti = tool_input or {}
    if tool == "Bash":
        hint = ti.get("command", "")
    elif tool in ("Edit", "Write", "Read"):
        hint = os.path.basename(ti.get("file_path", "") or "")
    else:
        hint = json.dumps(ti)
    line = f"{hhmm} {tool}: {hint}"
    return line[:MAXLEN]


def main():
    try:
        try:
            ev = json.load(sys.stdin)
        except Exception:
            ev = {}
        if not isinstance(ev, dict):
            ev = {}
        tool = ev.get("tool_name", "?")
        hhmm = datetime.now().strftime("%H:%M")
        entry = feed_line(tool, ev.get("tool_input", {}), hhmm)
        send_status(state="running", entry=entry)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
