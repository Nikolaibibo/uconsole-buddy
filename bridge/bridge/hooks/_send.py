# bridge/hooks/_send.py — shared fire-and-forget status sender. NOT a hook itself.
import json, os, socket, sys

SOCK = os.path.expanduser("~/opt/uconsole-companion-bridge/.run/bridge.sock")
# Windows has no asyncio unix-socket server, so the daemon listens on loopback TCP there.
TCP_ADDR = ("127.0.0.1", int(os.environ.get("GERALD_PORT", "47821")))

# The BLE link (Nordic UART) is neither paired nor encrypted: anyone within radio range
# can read it. By default only categories leave the machine (tool name, fixed messages);
# commands, file names, MCP server names and notification texts stay local.
# GERALD_FULL_FEED=1 restores the verbose feed for trusted surroundings.
FULL_FEED = os.environ.get("GERALD_FULL_FEED") == "1"


def connect_bridge(timeout):
    """Open a client socket to the bridge daemon (loopback TCP on Windows, unix socket elsewhere)."""
    if sys.platform == "win32":
        return socket.create_connection(TCP_ADDR, timeout=timeout)
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
        with connect_bridge(3) as s:
            s.sendall((json.dumps(payload) + "\n").encode())
    except Exception:
        pass
    sys.exit(0)
