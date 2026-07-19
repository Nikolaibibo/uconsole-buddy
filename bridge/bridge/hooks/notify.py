#!/usr/bin/env python3
import json, sys
from _send import send_status
if __name__ == "__main__":
    try:
        ev = json.load(sys.stdin)
    except Exception:
        ev = {}
    if (ev.get("notification_type") or "") == "permission_prompt":
        send_status(state="waiting", msg="brauch dich")
    else:
        send_status(state="waiting", msg=ev.get("message", "brauch dich"))
