# bridge/hooks/_send.py — shared fire-and-forget status sender. NOT a hook itself.
import json, pathlib, socket, sys

# Claude Code ruft die Hooks per absolutem Pfad auf; sys.path[0] ist dann dieses
# Verzeichnis, nicht die Repo-Wurzel. Ohne das hier waere `bridge.endpoint` nicht
# importierbar und der Endpunkt muesste ein zweites Mal hartkodiert werden --
# genau der Drift, der zwischen daemon.py und dieser Datei schon passiert ist.
_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bridge.endpoint import control_endpoint  # noqa: E402


def build_status_payload(state=None, msg=None, entry=None):
    payload = {"type": "status"}
    if state is not None:
        payload["state"] = state
    if msg is not None:
        payload["msg"] = msg
    if entry is not None:
        payload["entry"] = entry
    return payload


def deliver(payload, addr=None):
    """Zustellen, ohne je zu scheitern.

    Hooks sind kurzlebige Prozesse im kritischen Pfad von Claude Code: laeuft der
    Daemon nicht, muss das folgenlos bleiben. Deshalb wird jede Ausnahme
    geschluckt -- ein stummer Gerald ist harmlos, ein blockierter Hook nicht.
    """
    host, port = addr if addr is not None else control_endpoint()
    try:
        with socket.create_connection((host, port), timeout=3) as s:
            s.sendall((json.dumps(payload) + "\n").encode())
    except Exception:
        pass


def send_status(state=None, msg=None, entry=None):
    deliver(build_status_payload(state, msg, entry))
    sys.exit(0)
