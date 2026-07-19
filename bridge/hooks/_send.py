# bridge/hooks/_send.py — shared fire-and-forget status sender. NOT a hook itself.
import json
import os
import socket
import sys

SOCK = os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock")


def send_status(state, msg=""):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(SOCK)
        s.sendall((json.dumps({"type": "status", "state": state, "msg": msg}) + "\n").encode())
    except Exception:
        pass
    sys.exit(0)
