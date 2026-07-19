#!/usr/bin/env python3
import sys
from _send import send_status
if __name__ == "__main__":
    sys.stdin.read()
    send_status(state="thinking", msg="session start")
