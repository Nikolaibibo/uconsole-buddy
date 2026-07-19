# Gerald — uConsole Claude Buddy

**Gerald** is a physical desk companion that reacts to your [Claude Code](https://claude.com/claude-code) sessions. A handheld terminal (a [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole), Raspberry Pi CM4) sits next to you and shows — as a big drawn face — what Claude is doing right now: thinking, working, waiting for you, done. It plays a chime when Claude needs your input, streams a live feed of the tool calls, and lets you approve/deny shell commands with a physical key press.

It started as a client for Anthropic's official **Hardware Buddy** (BLE) reference and grew into a full terminal-driven buddy via Claude Code hooks.

```
        ◦ Gerald ◦

     ╭───────────────╮
     │   ‾       ‾   │        <- brows carry the emotion
     │   ●       ●   │
     │     ╲___╱     │        <- mouth + eyes morph per state
     ╰───────────────╯

        A R B E I T E         <- big figlet status word (mood-coloured)
      ▱ ▱ ▱ ▱ ▰ ▰ ▰ ▱ ▱       <- running activity bar
      14:23 Bash: npm test    <- live tool feed

     ● connected      ♪ sound on
```

## What it does

- **Ambient mood** — a drawn face (eyebrows + eyes + mouth) morphs and re-colours per state: `idle` · `thinking` · `running` · `waiting` · `done` · `error`.
- **Live activity feed** — the last few tool calls (`Bash: npm test`, `Edit: ui.py`, …).
- **Sound notifications** — a bright chime when Claude needs you (`waiting`), a soft tone when it's `done`, a distinct tone on `error`. Mute with `m`.
- **Physical approvals** — a `Bash` command awaiting permission takes over the screen; press `Y`/`N` on the device to allow/deny the real session.
- **Full-screen kiosk** with a mood-coloured border and small animations (blinking, running bar, drifting `z z z`).
- **Multilingual** — English (default) and German UI, switch with the `GERALD_LANG` env var.

## How it works

```
Claude Code (hooks)                      Mac / Linux              uConsole (BLE peripheral)
 SessionStart / UserPromptSubmit
 PreToolUse(Bash) / PostToolUse(*)  -->  bridge daemon    --BLE-->  Textual kiosk UI
 Notification / Stop / SessionEnd        (bleak central,           (bluez-peripheral,
                                          unix socket)              Nordic UART / NUS)
```

Claude Code hooks fire on session events and send a tiny JSON line to the daemon's unix socket (fire-and-forget). The daemon holds one BLE connection to the device and pushes JSON snapshots (`state`, rolling `entries`, …) over **Nordic UART (NUS)**, one JSON object per line — the same protocol as [`anthropics/claude-desktop-buddy`](https://github.com/anthropics/claude-desktop-buddy). `PreToolUse(Bash)` round-trips: the device sends back a `permission` (`once`/`deny`) that becomes the hook's `allow`/`deny`.

## Repo layout

| Path | What |
|------|------|
| **`bridge/`** | Mac/Linux side: Claude Code hook scripts + the BLE daemon (central). |
| **`device/`** | uConsole side: the Textual kiosk UI + BLE peripheral. |
| **`docs/`** | `SETUP.md` (getting started) + the original German design specs & plans. |

Both parts keep their own git history (imported via `git subtree`).

## Requirements

- **Bridge host** (where you run Claude Code): macOS or Linux, Python 3, Bluetooth LE. Depends on `bleak`.
- **Device**: a Linux box with BlueZ + a BLE adapter (built on a uConsole / Raspberry Pi CM4, Python 3.11). Depends on `bluez-peripheral`, `dbus-fast`, `textual`, `pyfiglet`. A Wayland compositor (labwc) for the kiosk look, but any terminal works for testing.
- **Claude Code** ≥ v2.1.210 (hook `permissionDecision` contract).

## Quick start

See **[docs/SETUP.md](docs/SETUP.md)** for the full walkthrough (device + bridge + wiring the hooks + kiosk + troubleshooting).

> ⚠️ **Heads-up:** the socket path and the hook command paths are currently **hardcoded** to the author's home directory (`~/Documents/web/uconsole-companion-bridge/…`). You'll need to adjust them — SETUP.md lists exactly where.

## Credits

Built on Anthropic's [`claude-desktop-buddy`](https://github.com/anthropics/claude-desktop-buddy) protocol (reference firmware: M5StickC Plus). This project adds a uConsole peripheral, a Claude-Code-hooks bridge for terminal sessions, and the Gerald kiosk UI. Design specs & implementation plans (German) live in `docs/`.
