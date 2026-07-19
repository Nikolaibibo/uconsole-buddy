#!/usr/bin/env python3
# bridge/hooks/notify.py — dünn, zustandslos, fire-and-forget status push (P2)
import json
import sys

from _send import send_status

if __name__ == "__main__":
    try:
        ev = json.load(sys.stdin)
    except Exception:
        ev = {}
    notification_type = ev.get("notification_type") or "idle"
    if notification_type == "permission_prompt":
        send_status("waiting", "permission")
    else:
        send_status("idle", notification_type)
