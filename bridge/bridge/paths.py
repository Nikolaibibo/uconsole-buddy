"""Shared socket-path resolution for the bridge daemon.

Resolution order (first match wins):
  1. $UCONSOLE_BRIDGE_SOCK        — explicit socket path
  2. $UCONSOLE_BRIDGE_HOME/run/bridge.sock
  3. ~/.uconsole-buddy/run/bridge.sock   (default)

The exact same rules are mirrored in bridge/hooks/_send.py,
bridge/statusline_tee.py and gjc/uconsole-buddy.ts so every side of
the link agrees on where the unix socket lives.
"""
import os


def socket_path() -> str:
    env = os.environ.get("UCONSOLE_BRIDGE_SOCK")
    if env:
        return os.path.expanduser(env)
    home = os.environ.get("UCONSOLE_BRIDGE_HOME")
    base = os.path.expanduser(home) if home else os.path.expanduser("~/.uconsole-buddy")
    return os.path.join(base, "run", "bridge.sock")
