# bridge/hooks/_send.py — shared fire-and-forget status sender. NOT a hook itself.
import json, os, socket, sys

def _socket_path():
    env = os.environ.get("UCONSOLE_BRIDGE_SOCK")
    if env:
        return os.path.expanduser(env)
    home = os.environ.get("UCONSOLE_BRIDGE_HOME")
    base = os.path.expanduser(home) if home else os.path.expanduser("~/.uconsole-buddy")
    return os.path.join(base, "run", "bridge.sock")


SOCK = _socket_path()


def build_status_payload(state=None, msg=None, entry=None):
    payload = {"type": "status"}
    if state is not None:
        payload["state"] = state
    if msg is not None:
        payload["msg"] = msg
    if entry is not None:
        payload["entry"] = entry
    return payload


def send_status(state=None, msg=None, entry=None):
    payload = build_status_payload(state, msg, entry)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(SOCK)
        s.sendall((json.dumps(payload) + "\n").encode())
    except Exception:
        pass
    sys.exit(0)
