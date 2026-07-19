---
tags: [projekt, uconsole, claude, ble, maker, claude-code, hooks]
status: bereit-zur-umsetzung
created: 2026-07-19
updated: 2026-07-19
source: marvin-session
hardware: uConsole (Raspberry Pi CM4) + Mac
sprache: Python
device-spec: "[[Claude Companion uConsole - Spec]]"
---

# Claude Companion Bridge (Terminal) — Spec

> Mac-seitige Bridge, die den **Terminal-`claude` (Claude Code CLI)** ans uConsole-Companion-Gerät anschließt. Ersetzt den Hardware Buddy (der nur Desktop/Cowork-Sessions brückt) für die Terminal-Nutzung. **Die uConsole-Firmware bleibt unverändert** — sie spricht schon das Snapshot/`permission`-JSON-Protokoll; hier entsteht nur ein neuer „Sender" auf dem Mac.

## 1. Ausgangslage / Warum

Der offizielle **Hardware Buddy** brückt nur Sessions, die die Claude-**Desktop/Cowork**-App trackt — empirisch bewiesen (19.07.): eine lose Terminal-`claude`-Session erzeugt **nie** einen `prompt` im BLE-Snapshot (`waiting` bleibt 0). Der Terminal-`claude` hat aber einen **eigenen, besseren** Integrationspunkt: **Claude Code Hooks**.

Verifiziert gegen die aktuelle Doku (Claude Code v2.1.210+, 19.07.):
- **`PreToolUse`-Hook blockiert synchron** und gibt per stdout-JSON `permissionDecision: "allow" | "deny" | "ask" | "defer"` zurück (das alte `decision: approve/block` ist für PreToolUse **nicht** mehr gültig).
- **Timeout pro Hook konfigurierbar** (Command-Hook Default 600s) → `"timeout": 120` fürs Warten auf den Knopfdruck ist unkritisch. PreToolUse-Timeout → Tool wird **geblockt**.
- Offiziell empfohlene Form: **dünner Hook + persistenter Daemon** (Daemon hält die Geräte-Verbindung, Hook ist zustandslos).

Quellen: `code.claude.com/docs/en/hooks.md`, `.../settings.md`, `.../agent-sdk/hooks.md`.

## 2. Architektur

```
Claude Code (Terminal)
  │  Hooks: PreToolUse / Notification / SessionStart / Stop  (dünne Scripts)
  │  ↕ lokaler Unix-Domain-Socket (JSON, eine Zeile pro Nachricht)
Mac-Daemon  (Python + bleak, BLE-CENTRAL)
  │  ↕ BLE Nordic UART  (verbindet sich mit dem uConsole-Peripheral)
uConsole    (UNVERÄNDERT: bluez-peripheral + Textual, Snapshot/permission-JSON)
```

- **Rollen:** Mac-Daemon = BLE **Central** (verbindet sich, sendet Snapshots, empfängt `permission`). uConsole = BLE **Peripheral** (wie gehabt). Das ist die produktive Form der `fake_central`, die schon prototypisiert wurde.
- **Single-Central-Constraint:** Es kann immer nur **ein** Central mit dem Peripheral verbunden sein. Daemon (Terminal-Weg) und Hardware Buddy (Desktop-Weg) sind daher **wechselseitig exklusiv** — für Terminal-Arbeit hält der Daemon den Link, der Hardware Buddy ist dann getrennt. Kein Problem, nur eine Tatsache.

## 3. Komponenten (alle neu, alle Mac-seitig)

- `bridge/protocol.py` — Snapshot **bauen** (Central-Sicht) + `permission` **parsen**. Spiegel des Geräte-Protokolls (Contract aus dem Device-Repo kopiert). Rein, testbar.
- `bridge/ble_central.py` — bleak-Central: mit `Claude-uConsole` verbinden, Snapshot auf RX schreiben (gechunkt), TX subscriben, `permission` empfangen; Reconnect bei Drop.
- `bridge/daemon.py` — Langläufer: hält BLE-Link, lauscht auf Unix-Socket, übersetzt Hook-Requests ↔ BLE. Hält den „aktuellen Snapshot"-Zustand (running/waiting/prompt), pusht bei Änderung.
- `bridge/hooks/pretooluse.py` — **dünn**: liest stdin-JSON (`tool_name`,`tool_input`,`session_id`), fragt Daemon über Socket, blockt ≤~100s auf Entscheidung, gibt PreToolUse-JSON aus. **Fail-safe: jede Unsicherheit → `ask`.**
- `bridge/hooks/notify.py`, `session.py`, `stop.py` — **dünn**, fire-and-forget: Status-Events an den Daemon (kurzer Timeout).
- `settings-snippet.json` — Hook-Registrierung (siehe §6), zum Einpflegen in `~/.claude/settings.json`.
- `bridge/run.sh` + (P3) launchd-User-Agent für Keepalive.

## 4. Protokoll-Fluss

### 4.1 Approval (Kern)
1. Claude will ein gematchtes Tool laufen lassen → `PreToolUse`-Hook feuert, stdin = `{tool_name, tool_input, session_id, cwd, …}`.
2. Hook → Daemon (Socket): `{"type":"approve","id":"<session_id>#<n>","tool":"Bash","hint":"<cmd/args gekürzt>"}`.
3. Daemon → uConsole (BLE): Snapshot `{"total":1,"running":0,"waiting":1,"msg":"approve: Bash","prompt":{"id":…,"tool":"Bash","hint":…}}`.
4. uConsole zeigt ⚠-Overlay → Nutzer drückt **Y/N** → uConsole → `{"cmd":"permission","id":…,"decision":"once"|"deny"}` auf TX.
5. Daemon empfängt, mappt `once→allow` / `deny→deny`, antwortet dem Hook über den Socket.
6. Hook gibt aus:
   ```json
   {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"approved on uConsole"}}
   ```
7. Daemon pusht „cleared"-Snapshot (`waiting:0`, kein `prompt`).

### 4.2 Status (P2)
- `SessionStart` → Daemon setzt „session on", pusht `running`-Zustand.
- `Notification` (`notification_type` `permission_prompt`/`idle_prompt`) → Zustand „waiting"/„idle" aufs Gerät.
- `Stop` → „idle/done".

## 5. Fail-safe-Semantik (nicht verhandelbar)

**Jede Unsicherheit → `ask`** (normaler Terminal-Prompt), niemals stilles `allow`:
- Daemon nicht erreichbar (nicht gestartet) → Hook gibt sofort `ask`.
- Daemon erreicht, aber BLE tot / uConsole weg → `ask`.
- Kein Knopfdruck in ~100s (Hook-interner Timeout, < settings-`timeout` 120) → `ask`.
- Nur ein *expliziter* Knopfdruck erzeugt `allow`/`deny`. Alles andere degradiert sauber auf den nativen Prompt.

## 6. Hooks-Registrierung (`~/.claude/settings.json`)

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [ { "type": "command",
                     "command": "$HOME/Documents/web/uconsole-companion-bridge/bridge/hooks/pretooluse.py",
                     "timeout": 120 } ] }
    ],
    "Notification": [
      { "matcher": "permission_prompt|idle_prompt",
        "hooks": [ { "type": "command",
                     "command": "$HOME/Documents/web/uconsole-companion-bridge/bridge/hooks/notify.py",
                     "timeout": 5 } ] }
    ],
    "SessionStart": [ { "hooks": [ { "type": "command", "command": "…/hooks/session.py", "timeout": 5 } ] } ],
    "Stop":         [ { "hooks": [ { "type": "command", "command": "…/hooks/stop.py",    "timeout": 5 } ] } ]
  }
}
```
- **v1-Matcher: nur `Bash`** (Entscheidung 19.07.). Später `Bash|Edit|Write|mcp__.*` erweiterbar. Trade-off: breiter = mehr Kontrolle, aber jeder gematchte Call will einen Knopfdruck.
- `PreToolUse` stdout-Contract exakt wie §4.1/6; Exit 0 + JSON. (Exit 2 = hart blocken mit stderr-Reason — nutzen wir nicht, wir nutzen `permissionDecision`.)

## 7. Entscheidungen (gelockt 19.07.)
- **Matcher v1 = nur `Bash`.**
- **Getrenntes Mac-Repo** `~/Documents/web/uconsole-companion-bridge/` (anderes Deploy-Ziel als das Device-Repo; Protokoll-Contract wird kopiert, nicht geteilt).
- **Fail-safe = `ask`** bei jeder Unsicherheit.
- **B/Dashboard (Token/Multi-Session) = v2**, nicht jetzt. Das Snapshot-Schema kann die Felder schon → keine Firmware-/Protokolländerung nötig, nur der Daemon-Snapshot-Builder wird später erweitert.

## 8. Phasen (rückwärts vom Ziel)
- **P0 — Daemon-BLE-Kern:** `ble_central.py` + `protocol.py` → Daemon verbindet sich mit `Claude-uConsole`, schickt einen Snapshot mit `prompt`, empfängt die `permission`-Antwort. Beweis: Overlay auf dem Gerät + Knopfdruck kommt am Mac an. (= produktive `fake_central`.)
- **P1 — Approval end-to-end:** Unix-Socket im Daemon + `pretooluse.py` + settings.json → echter Terminal-`claude` → Bash-Command → Knopf → allow/deny. Fail-safe `ask` verdrahtet. **→ funktionsfähig.**
- **P2 — Status:** `notify.py`/`session.py`/`stop.py` → running/idle/waiting aufs Gerät.
- **P3 — Härten & Autostart:** launchd-User-Agent (Daemon-Keepalive), Reconnect-Robustheit, Docs.
- **Out of scope (v1):** Token-/Multi-Session-Dashboard (v2), Verschlüsselung des Socket (lokal, `0700`-Dir reicht).

## 9. Offene Punkte (beim Bau prüfen)
- **macOS Bluetooth-Permission (TCC):** bleak-Central braucht BT-Zugriff für den ausführenden Prozess (Terminal/launchd). Beim ersten Lauf verifizieren; ggf. Terminal/den launchd-Kontext in Systemeinstellungen → Datenschutz → Bluetooth freigeben.
- **BLE-Contention:** Vor dem Daemon-Test den Hardware Buddy trennen (nur ein Central gleichzeitig).
- **bleak-MTU/Chunking:** RX-Writes ggf. auf `write_without_response` + Chunk ≤ (MTU-3); analog zur Geräteseite.
- **Hook-Latenz:** BLE-Verbindung muss beim Daemon **stehen**, bevor der erste Hook feuert — sonst erster Call → `ask`. Daemon vor der `claude`-Session starten (P3 löst das via Autostart).
- **`permission_mode`:** Der Hook feuert auch in `acceptEdits`/`bypassPermissions`. v1 ignoriert das (routet `Bash` immer zum Gerät); ggf. in v1.1 den Mode auswerten, um in Bypass-Modi `ask`/durchzuwinken.
