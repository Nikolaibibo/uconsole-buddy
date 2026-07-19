"""Central-seitiges JSON-Protokoll: Snapshots bauen, permission parsen, Hook-Output. Rein."""
import json


def build_snapshot(*, total=1, running=0, waiting=0, msg="", prompt=None,
                   tokens=0, tokens_today=0, entries=None) -> str:
    return json.dumps({
        "total": total, "running": running, "waiting": waiting, "msg": msg,
        "entries": entries or [], "tokens": tokens, "tokens_today": tokens_today,
        "prompt": prompt,
    }) + "\n"


def build_prompt_snapshot(prompt_id: str, tool: str, hint: str) -> str:
    return build_snapshot(total=1, running=0, waiting=1, msg=f"approve: {tool}",
                          prompt={"id": prompt_id, "tool": tool, "hint": hint})


def build_cleared_snapshot() -> str:
    return build_snapshot(total=1, running=0, waiting=0, msg="idle", prompt=None)


def parse_permission(line: str) -> dict | None:
    try:
        m = json.loads(line)
    except (ValueError, TypeError):
        return None
    if isinstance(m, dict) and m.get("cmd") == "permission" and "id" in m and "decision" in m:
        return {"id": m["id"], "decision": m["decision"]}
    return None


def decision_to_hook(decision: str | None) -> str:
    return {"once": "allow", "deny": "deny"}.get(decision, "ask")


def hook_pretooluse_output(permission_decision: str, reason: str = "") -> str:
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": permission_decision,
        "permissionDecisionReason": reason,
    }})
