# GJC (Gajae Code) integration

Make **Gerald** react to [GJC](https://github.com/gajae-code) / `pi` coding
sessions, not just Claude Code. This is a single extension that speaks the same
unix-socket protocol as the Claude hooks in `../bridge/hooks/`, so the **bridge
daemon and the uConsole device stay unchanged** — only the agent-facing layer
differs.

```
GJC (extension events)                   Mac / Linux              uConsole (BLE peripheral)
 session_start / before_agent_start
 tool_call(bash) / tool_execution_*  -->  bridge daemon    --BLE-->  Textual kiosk UI
 agent_end / session_shutdown             (bleak central,           (bluez-peripheral, NUS)
                                           unix socket)
```

## What it maps

| GJC event | Gerald state |
|-----------|--------------|
| `session_start` | `thinking` ("session start") |
| `before_agent_start` (prompt submitted) | `thinking` |
| `agent_start` | `running` |
| `tool_execution_start` | `running` + live feed line |
| `tool_execution_end` (failed) | `error` |
| `tool_call` (bash) | approval overlay → `Y`/`N` on device → `allow`/`deny` |
| `agent_end` | `done` → decays to `idle` |
| `session_shutdown` | `idle` |
| `model_select` | HUD model name |

The `error` state — dead in the Claude path because no hook emitted it — is
now driven by real failed tool calls.

## Setup

1. **Run the bridge daemon** (same as the Claude flow — see [`../../docs/SETUP.md`](../../docs/SETUP.md#2-bridge-host-bridge)):

   ```bash
   cd bridge
   .venv/bin/python -m bridge.daemon
   ```

2. **Install the extension** into GJC's extension directory:

   ```bash
   ./install.sh          # links into ~/.gjc/agent/extensions/
   ./install.sh --pi     # or into ~/.pi/agent/extensions/
   ```

   Or load it ad-hoc for one session:

   ```bash
   gjc -e /absolute/path/to/uconsole-buddy/bridge/gjc/uconsole-buddy.ts
   ```

3. **Run `gjc`.** Gerald reacts. Bash commands pop the approval overlay; press
   `Y`/`N` on the device.

## Configuration (env vars)

| Variable | Default | Meaning |
|----------|---------|---------|
| `UCONSOLE_BRIDGE_SOCK` | — | Explicit socket path (overrides everything). |
| `UCONSOLE_BRIDGE_HOME` | `~/.uconsole-buddy` | Base dir; socket is `<home>/run/bridge.sock`. |
| `UCONSOLE_BRIDGE_APPROVE` | `bash` | `bash` (gate Bash only), `all` (gate every tool), or `off` (mood/feed only, no permission gating). |
| `GERALD_LANG` | `en` | `en` or `de` for the short status words. |

The daemon and the Python hooks resolve the socket path with the **same rules**
(`bridge/bridge/paths.py`), so all sides agree without editing source. Set
`UCONSOLE_BRIDGE_SOCK`/`UCONSOLE_BRIDGE_HOME` once (e.g. in your shell rc) if you
want a non-default location.

## Fail-safe behaviour

- If the daemon isn't running, every status push is a silent no-op and GJC runs
  normally.
- If an approval round-trip times out or errors, it resolves to `ask` — GJC's
  normal permission flow takes over; the device never blocks your session.

## Notes / limitations

- HUD currently carries the model id only (GJC has no Claude-style statusline
  usage feed). Context-window / usage fields are left empty.
- Only one BLE central at a time — see the device troubleshooting in
  [`../../docs/SETUP.md`](../../docs/SETUP.md#troubleshooting).
