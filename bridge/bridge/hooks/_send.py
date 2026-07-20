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
# TCP transport for remote/overlay (e.g. Tailscale) setups: "host:port".
ADDR = os.environ.get("UCONSOLE_BRIDGE_ADDR")


def open_conn(timeout=3):
    """Connected socket to the bridge — TCP if UCONSOLE_BRIDGE_ADDR is set, else unix."""
    if ADDR:
        host, _, port = ADDR.rpartition(":")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host or "127.0.0.1", int(port)))
        return s
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    return s


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
        s = open_conn(3)
        s.sendall((json.dumps(payload) + "\n").encode())
    except Exception:
        pass
    sys.exit(0)
