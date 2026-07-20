#!/usr/bin/env bash
# Open Gerald in a titled lxterminal window (for labwc autostart / kiosk).
# Honors GERALD_LANG (en|de|ko) and UCONSOLE_LISTEN from the environment.
# The window title "Gerald" lets a labwc <windowRule> full-screen just this one.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec lxterminal --title=Gerald -e "$HERE/launch-tcp.sh"
