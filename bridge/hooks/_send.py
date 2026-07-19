# bridge/hooks/_send.py — shared fire-and-forget status sender. NOT a hook itself.
import json, os, socket, sys

SOCK = os.path.expanduser("~/Documents/web/uconsole-companion-bridge/.run/bridge.sock")


def send_status(state=None, msg="", entry=None):
    payload = {"type": "status", "msg": msg}
    if state is not None:
        payload["state"] = state
    if entry is not None:
        payload["entry"] = entry
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(SOCK)
        s.sendall((json.dumps(payload) + "\n").encode())
    except Exception:
        pass
    sys.exit(0)
