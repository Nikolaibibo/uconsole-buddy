#!/usr/bin/env python3
# bridge/hooks/session.py — dünn, zustandslos, fire-and-forget status push (P2)
import sys

from _send import send_status

if __name__ == "__main__":
    sys.stdin.read()  # stdin lesen + ignorieren (Claude Code liefert Session-JSON)
    send_status("running", "session start")
