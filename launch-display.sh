#!/usr/bin/env bash
UID_N=$(id -u)
export XDG_RUNTIME_DIR=/run/user/$UID_N
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
for xa in /run/user/$UID_N/.mutter-Xwaylandauth.* "$HOME/.Xauthority"; do
  [ -f "$xa" ] && export XAUTHORITY="$xa"
done
# Alte Instanz KOMPLETT beenden: erst Fenster + Supervising-Wrapper, dann die App.
# (Sonst startet der Wrapper die App nach dem companion.main-kill sofort neu -> Doppel.)
pkill -f "lxterminal.*Claude-Companion" 2>/dev/null
pkill -f run-debug.sh 2>/dev/null
pkill -f companion.main 2>/dev/null
sleep 2
setsid lxterminal --title=Claude-Companion -e "$HOME/Documents/web/uconsole-companion/run-debug.sh" >/tmp/lxterm-launch.log 2>&1 &
disown
