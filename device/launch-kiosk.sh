#!/usr/bin/env bash
# Open Gerald in a titled lxterminal window (for labwc autostart / desktop icon).
# Honors GERALD_LANG (en|de|ko) and UCONSOLE_LISTEN from the environment.
# The window title "Gerald" lets a labwc <windowRule> full-screen just this one.
#
# Idempotent: drops any previous Gerald instance first, so clicking the desktop
# shortcut again just relaunches a fresh window (no port-in-use clash on 8765).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pkill -f "companion\.main" 2>/dev/null || true
pkill -f "lxterminal --title=Gerald" 2>/dev/null || true
sleep 1
exec lxterminal --title=Gerald -e "$HERE/launch-tcp.sh"
