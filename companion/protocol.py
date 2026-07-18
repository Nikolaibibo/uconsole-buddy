"""JSON-Protokoll für Hardware-Buddy NUS. Reine Logik, keine BLE-Deps."""
import json


def parse_message(line: str) -> dict | None:
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def build_permission(prompt_id: str, decision: str) -> str:
    if decision not in ("once", "deny"):
        raise ValueError(f"decision must be 'once' or 'deny', got {decision!r}")
    return json.dumps({"cmd": "permission", "id": prompt_id, "decision": decision}) + "\n"


def build_ack(cmd: str, ok: bool = True, n: int | None = None,
              error: str | None = None) -> str:
    m: dict = {"ack": cmd, "ok": ok}
    if n is not None:
        m["n"] = n
    if error is not None:
        m["error"] = error
    return json.dumps(m) + "\n"


def build_status_ack(name: str, sec: bool, up: int, appr: int, deny: int) -> str:
    data = {"name": name, "sec": sec, "sys": {"up": up},
            "stats": {"appr": appr, "deny": deny}}
    return json.dumps({"ack": "status", "ok": True, "data": data}) + "\n"
