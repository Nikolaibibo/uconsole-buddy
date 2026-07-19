# Setup — Gerald (uConsole Claude Buddy)

Get Gerald running end to end. Two machines are involved:

- **Device** — the BLE peripheral that shows the face (a uConsole / Raspberry Pi CM4, or any Linux box with BlueZ). Code in `device/`.
- **Bridge host** — where you run Claude Code (macOS or Linux). Runs the BLE daemon + the hook scripts. Code in `bridge/`.

> ⚠️ **Paths are hardcoded.** Several files pin the author's home path
> (`/Users/nikolaibockholt/Documents/web/uconsole-companion-bridge/…`). Before anything
> works on your machine, fix them (see [Adjust the paths](#adjust-the-paths)).

---

## 1. Device (`device/`)

On the uConsole / Linux device:

```bash
git clone https://github.com/Nikolaibibo/uconsole-buddy.git
cd uconsole-buddy/device
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # bluez-peripheral, dbus-fast, textual, pyfiglet
.venv/bin/python -m pytest -q                   # optional: pure-logic tests, no hardware needed
```

**Pick the right Bluetooth adapter.** The app advertises via BlueZ on the onboard
controller. On the uConsole that's `hci0` (onboard Cypress, UART); a USB dongle may show up
as `hci1` and hijack `bluetoothctl`'s default — pin the right one. Check with `hciconfig`.

**Run it:**

```bash
.venv/bin/python -m companion.main
```

It starts a Textual UI and advertises as `Claude-uConsole` over Nordic UART. With no bridge
connected it shows the `offline` face — that's expected until step 2 connects.

Tests live in `device/tests/` (`pytest`), the package is `device/companion/`.

---

## 2. Bridge host (`bridge/`)

On the machine where you run Claude Code:

```bash
cd uconsole-buddy/bridge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # bleak
.venv/bin/python -m pytest -q                   # optional
```

**Run the daemon** (it scans for the device by NUS service UUID, connects, and listens on a
unix socket):

```bash
.venv/bin/python -m bridge.daemon
```

- **macOS:** the first BLE access triggers a one-time Bluetooth permission prompt for the
  terminal (System Settings → Privacy & Security → Bluetooth). Grant it.
- Watch `bridge/bridge.log` for `BLE connected to uConsole`.

The daemon self-heals: if the device app restarts or the link drops, a failed send (or the
disconnect callback) triggers an automatic reconnect loop — no manual restart needed.

---

## 3. Wire up the Claude Code hooks

The buddy reacts to your sessions through Claude Code **hooks**. Merge the hooks from
`bridge/settings-snippet.json` into your project's `.claude/settings.json` (or your user
settings), **fixing the absolute paths** to where you cloned `bridge/`.

Hooks used:

| Hook | Effect |
|------|--------|
| `SessionStart` / `UserPromptSubmit` | `thinking` |
| `PostToolUse` (`*`) | `running` + appends a feed line |
| `PreToolUse` (`Bash`) | approval overlay → `Y`/`N` on the device → `allow`/`deny` |
| `Notification` | `waiting` (chime) |
| `Stop` | `done` → decays to `idle` after ~5 s |
| `SessionEnd` | `idle` |

The status hooks are fire-and-forget: if the daemon isn't running, they no-op and Claude Code
behaves normally. Start the daemon **before** `claude`.

> The `PreToolUse(Bash)` hook routes **every** Bash command through the device for approval.
> If you keep a large allow-list, consider omitting that one hook and using only the status
> hooks (mood/feed/sound) — those never touch your permissions.

---

## 4. Adjust the paths

The unix socket and the hook command paths are hardcoded. Change these to your clone:

- `bridge/bridge/daemon.py` — `SOCK = …/.run/bridge.sock`
- `bridge/bridge/hooks/_send.py` — `SOCK`
- `bridge/bridge/hooks/pretooluse.py` — `SOCK`
- `bridge/settings-snippet.json` — every `command` path

Keep the socket path identical in the daemon and all hook scripts (that's how they find each
other).

---

## 5. Kiosk & autostart (optional, uConsole/labwc)

To make it a full-screen appliance instead of a windowed terminal:

- **`device/run-debug.sh`** is a supervising wrapper: it runs `sudo systemctl restart bluetooth`
  (clears any orphaned GATT registration from a killed instance — see Troubleshooting), then
  loops the app, auto-restarting on crash and exiting cleanly on `q`.
- **`device/launch-display.sh`** kills any old instance (window + wrapper + app) and launches
  the wrapper in an `lxterminal`. Wire it into your compositor autostart
  (e.g. labwc `~/.config/labwc/autostart`).
- **lxterminal** (`~/.config/lxterminal/lxterminal.conf`): `hidemenubar=true`,
  `hidescrollbar=true`, `hidepointer=true`, and a larger `fontname` (e.g. `Monospace 18`) to
  make the face big.
- **labwc** (`~/.config/labwc/rc.xml`): a window rule to full-screen it and drop the titlebar:
  ```xml
  <windowRules>
    <windowRule identifier="lxterminal" serverDecoration="no" skipTaskbar="yes">
      <action name="ToggleFullscreen"/>
    </windowRule>
  </windowRules>
  ```
- **Volume**: set it once (`amixer sset Master 85% unmute`) and persist with `sudo alsactl store`.

These live under `~/.config` on the device, not in this repo.

---

## Troubleshooting

- **Only one BLE central at a time.** The device firmware holds a single connection. Disconnect
  Anthropic's Hardware Buddy (or any other connected app) before starting the daemon.
- **`connect()` times out / "Multiple Characteristics with this UUID".** A killed device app can
  leave an orphaned GATT registration in BlueZ, so the peripheral advertises but rejects new
  connects. Restarting `bluetooth` on the device clears it — the `run-debug.sh` wrapper does this
  on every launch.
- **Nothing renders / black screen.** Usually two app instances fighting over the display —
  make sure only one `companion.main` runs (`pgrep -f companion.main`); `launch-display.sh` kills
  old instances for you.
- **No sound.** Check the mixer isn't at a low volume (`amixer sget Master`) and that the default
  sink is your speaker, not HDMI (`pactl list short sinks`).
- **macOS launchd autostart fails with "Operation not permitted".** macOS TCC blocks launchd
  background jobs from `~/Documents`. Either move the daemon out of `~/Documents` (and the socket
  to `/tmp`), or grant the daemon's interpreter Full Disk Access. Running the daemon from a normal
  terminal works without this.

## Known limitations

- Paths hardcoded (see step 4).
- `error` state is defined but no hook emits it yet (dead path for now).
- Token counters are always `0` (Claude Code hook payloads aren't wired to real usage yet).
- Kiosk config lives under `~/.config` on the device, outside this repo.
