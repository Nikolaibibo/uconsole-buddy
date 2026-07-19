# tests/conftest.py — hook scripts do `from _send import send_status` (they rely on
# Claude Code invoking them by absolute path, which puts the script's own dir on
# sys.path[0]). When tests load a hook module directly via importlib, that dir isn't
# on sys.path yet, so add bridge/hooks here once for the whole test session.
import pathlib
import sys

HOOKS_DIR = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
