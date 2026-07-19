---
tags: [projekt, uconsole, claude, ble, maker, claude-code, hooks, buddy, mood, notify]
status: bereit-zur-umsetzung
created: 2026-07-19
updated: 2026-07-19
source: marvin-session
hardware: uConsole (Raspberry Pi CM4) + Mac
sprache: Python
bridge-spec: "[[Claude Companion Bridge (Terminal) - Spec]]"
device-spec: "[[Claude Companion uConsole - Spec]]"
---

# Claude Companion Buddy (Mood & Notify) — Spec

> Erweitert das bestehende uConsole-Companion von einem reinen **Freigabe-Terminal** zu einem echten **Buddy**, der auf CC-Sessions reagiert: Ambient-Mood (was macht Claude gerade), Live-Aktivitätsfeed, physisches Ping (Sound) wenn Claude auf dich wartet, und Charakter (Gesichter/Sprüche). **Baut auf der schon funktionierenden Pipeline auf — keine neue Architektur, nur an jeder Ebene dranstecken + anreichern.**

## 1. Ausgangslage / Warum

Nach dem 19.07.-Bau steht die volle Kette **live**: `CC-Hook → Unix-Socket → BLE-Daemon (Mac) → BLE-Snapshot → Device-State → Textual-UI`. Verifiziert:

- **Bridge (Mac, `~/Documents/web/uconsole-companion-bridge/`):** `pretooluse.py` registriert + live (Bash-Approval-Overlay). `session.py`/`stop.py`/`notify.py` **existieren als Gerüst, sind aber NICHT in `settings-snippet.json` registriert** → Claude Code ruft sie nie auf. `daemon.push_status()` funktioniert, ist aber **verlustbehaftet** (plättet auf `running`-bool + `msg`, der echte `state`-String geht verloren).
- **Gerät (uConsole, `~/Documents/web/uconsole-companion/`):** `ui.py` rendert **jetzt schon** `entries[:3]`, `tokens`/`tokens_today`, `appr`/`deny`, und `state.connection_state()` leitet `idle/running/waiting/disconnected` ab. Es fehlt nur: Nichts füllt `entries`, kein prominentes Gesicht, keine Notification.
- **Hardware (verifiziert, alle Kanäle ohne sudo beschreibbar — User in `video`/`input`/`audio`):** 🔊 Speaker (`paplay`/`aplay`, bcm2835) · 💡 Backlight `backlight@0` (0–9) · 🔴 LEDs (ACT/PWR/Capslock). **Keine Vibration/Buzzer** (CM4-Handheld).

Fazit: „reagiert auf CC-Sessions" ist zu ~50 % gebaut. Diese Spec verdrahtet + reichert den Rest an.

## 2. Ziele (vom User gewählt)

1. **Ambient Mood/Status** — Gerät zeigt dauerhaft, was Claude tut: idle / thinking / running / waiting / done / error.
2. **Aktive Benachrichtigung (Sound)** — deutlicher Chime bei `waiting` (Claude braucht dich), sanfter Ton bei `done`, eigener Klang bei `error`. Edge-triggered, debounced, Quiet-Toggle am Gerät.
3. **Live-Aktivitätsfeed** — rollende Anzeige, welches Tool/Command gerade lief (nicht nur Bash-Approvals) + Token-Zähler.
4. **Persönlichkeit/Charakter** — Gesichtsausdrücke + Sprüche je Zustand.

## 3. Nicht-Ziele (YAGNI)

- Keine Vibration (Hardware kann's nicht).
- Kein Backlight/LED als Notification-Default (Sound gewählt) — Licht bleibt optionaler, später aktivierbarer Kanal, wird aber **nicht** im ersten Wurf verdrahtet.
- Keine Bridge-seitige Präsentationslogik (Faces/Sprüche/Notification-Entscheidung leben am Gerät).
- Keine Multi-Session-/Multi-Owner-Verwaltung über das Bestehende hinaus.

## 4. Architektur — Ansatz A: „Snapshot anreichern, Gerät rendert Mood"

Gewählt gegen B (Bridge entscheidet alles) und C (nur Minimal-Wiring). **Bridge = Fakten, Gerät = Charakter.** Respektiert den bestehenden Split, hält Persönlichkeit geräteseitig frei iterierbar, und Notification-Hardware ist ohnehin geräteseitig.

```
CC-Hooks ──push event──▶ Daemon (hält state+entries) ──enriched snapshot──▶ Gerät
 Session/Prompt/                                                         ├─ mood.py  → Gesicht+Spruch
 PostToolUse/Notify/Stop                                                 ├─ ui.py    → Feed + Face
 (+ PreToolUse=Approval, unverändert)                                    └─ notify.py→ Sound bei Übergang
```

### 4.1 Protokoll (additiv, abwärtskompatibel)

Der Snapshot (`protocol.build_snapshot`) bekommt **ein neues Feld** und ein **schon vorhandenes wird endlich gefüllt**:

- **`state`** (neu): `"idle" | "thinking" | "running" | "waiting" | "done" | "error"`. Explizit statt aus Zählern geraten. Alte Gerät-Versionen ignorieren unbekannte Felder → abwärtskompatibel; das Gerät fällt auf `connection_state()` zurück, wenn `state` fehlt.
- **`entries`** (vorhanden, bislang leer): Bridge hängt pro Tool-Call **eine Zeile** an, Format `"HH:MM Tool: kurzhint"` (z. B. `"14:23 Bash: npm test"`, `"14:23 Edit: ui.py"`). Ring-Puffer, letzte N (z. B. 8) im Daemon; Gerät zeigt `entries[:3]`.
- `tokens`/`tokens_today`: falls das Hook-JSON Usage liefert, durchreichen; sonst unverändert lassen (kein Regressionsrisiko).

### 4.2 Bridge (Mac) — Änderungen

**a) Hooks registrieren** (`settings-snippet.json`, additiv zum bestehenden PreToolUse/Bash):

| Hook | Matcher | Wirkung |
|------|---------|---------|
| `SessionStart` | — | `state=thinking`, Feed „session start" |
| `UserPromptSubmit` | — | `state=thinking` |
| `PreToolUse` | `Bash` | **unverändert** — Approval-Overlay (hat Vorrang) |
| `PostToolUse` | `*` | Feed-Zeile anhängen + `state=running` |
| `Notification` | — | `state=waiting` (Claude braucht Input/Freigabe) |
| `Stop` | — | `state=done` → Auto-Zerfall zu `idle` nach ~5 s |
| `SessionEnd` | — | `state=idle` |

**b) Daemon** (`bridge/daemon.py`):
- Kleiner In-Memory-Zustand: aktueller `state` + `entries`-deque(maxlen=8).
- `push_status` → **`push_event(event, state=None, entry=None)`**: aktualisiert internen Zustand, baut **vollen angereicherten Snapshot** (`state` + `entries` + counts), pusht ihn. Nicht mehr verlustbehaftet.
- **Approval-Vorrang bleibt:** solange `self._pending` ein offener Prompt ist, überschreibt kein Event den Overlay-Snapshot (bestehendes `if self._pending: return`-Muster beibehalten, aber Zustand intern trotzdem mitführen, damit nach dem Prompt der korrekte Mood zurückkommt).
- **Done→idle-Zerfall:** ein einzelner asyncio-Timer; `Stop` setzt `done` + plant nach 5 s einen `idle`-Push (wird gecancelt, wenn vorher ein neues Event kommt).
- Socket-Handler: `type:"status"` → `push_event`; neuer optionaler `entry`-Payload wird angehängt.

**c) Hook-Skripte** (`bridge/hooks/*.py`): dünn/fire-and-forget bleiben; `_send.py` sendet zusätzlich `state` + optional `entry`. Neue Skripte für die noch fehlenden Events (`posttooluse.py`, `userprompt.py`, `sessionend.py`) analog zu den bestehenden.

### 4.3 Gerät (uConsole) — Änderungen

- **Neu `companion/mood.py`** (reine Logik, testbar): `mood_for(state) -> (face, spruch)`.
  - `idle` 😴 „warte auf dich" · `thinking` 🤔 „denke nach…" · `running` ⚙️ „arbeite…" · `waiting` 🙋 „brauch dich!" · `done` ✅ „fertig!" · `error` 💥 „autsch". (Sprüche = Charakter, frei iterierbar; Emojis fallen bei fehlender Font-Unterstützung auf ASCII-Marker zurück.)
- **`companion/state.py`**: `apply_snapshot` liest neues `state`-Feld (Fallback auf `connection_state()` wenn fehlt). Kleine Hilfsmethode `mood_state(now)`.
- **`companion/ui.py`**: Gesicht + Spruch **prominent oben** (eigener `#face`-Static); Status/Feed-Panel bleibt; Feed füllt sich echt aus `entries`. Overlay unverändert.
- **Neu `companion/notify.py`** (I/O-Rand dünn, Entscheidungslogik rein+testbar):
  - **Edge-triggered:** feuert nur bei **State-Übergang** (z. B. `running→waiting`, `*→done`, `*→error`), nie bei jedem Snapshot.
  - **Debounce:** min. Abstand (z. B. 2 s) zwischen zwei Sounds; `done` unmittelbar nach `waiting`-Antwort unterdrückbar.
  - **Kanäle (gewählt: Sound):** `waiting` → deutlicher Chime · `done` → sanfter Ton · `error` → eigener Klang. Wiedergabe via `paplay <wav>` (kleine WAVs im Repo, z. B. `assets/waiting.wav` etc.).
  - **Quiet-Toggle:** Taste am Gerät (z. B. `m` = mute) schaltet Sounds stumm; Zustand in der UI sichtbar (🔇).
  - Licht-Kanäle (Backlight-Puls/LED) als **auskommentierte/geflaggte Option** vorbereitet, aber nicht default-aktiv.

## 5. Datenfluss (Beispiel: du gehst Kaffee holen)

1. Du schickst Prompt → `UserPromptSubmit` → `thinking` 🤔.
2. Claude ruft Tools → `PostToolUse` je Call → `running` ⚙️ + Feed-Zeilen.
3. Claude braucht eine Nicht-Bash-Freigabe/Input → `Notification` → `waiting` 🙋 → **Chime** (du hörst es aus der Küche).
4. Du kommst zurück, antwortest → `running`.
5. Claude fertig → `Stop` → `done` ✅ → **sanfter Ton** → nach 5 s `idle` 😴.

(Bash-Freigaben laufen weiter über das bestehende Approval-Overlay + Y/N-Knopf, unangetastet.)

## 6. Fehlerbehandlung

- **Kein Daemon / Socket weg:** Hooks sind fire-and-forget mit Timeout → CC läuft normal weiter (bestehendes Verhalten).
- **BLE-Disconnect:** bestehender Fail-safe (`fail_pending`→`ask`) + Auto-Reconnect bleibt. Bei Reconnect pusht der Daemon den zuletzt bekannten `state` neu.
- **Snapshot ohne `state`:** Gerät nutzt `connection_state()` (abwärtskompatibel).
- **Sound-Wiedergabe schlägt fehl** (`paplay`-Fehler): still schlucken, nie die UI/State-Loop blockieren (wie `_send.py` heute Exceptions schluckt).
- **Notification-Sturm:** Debounce + Edge-Trigger verhindern Dauerfeuer.

## 7. Testing

- **Off-Hardware (wie bestehende Suite):** `mood_for` (alle States), `notify`-Entscheidungslogik (Edge-Trigger, Debounce, Quiet), Feed-Zeilen-Format, `apply_snapshot` mit/ohne `state`-Feld, Daemon `push_event` + Done→idle-Timer. Ziel: alle neuen reinen Funktionen abgedeckt, Gesamt-Suite bleibt grün.
- **Am Gerät (smoke):** jeder Sound-Kanal einmal hörbar; Quiet-Toggle; voller Session-Durchlauf (thinking→running→waiting→done) mit echtem `claude` im Terminal; Approval-Overlay weiterhin funktionsfähig.

## 8. Inkrementeller Bau (Reihenfolge)

1. **C-Increment zuerst:** Protokoll `state` + Daemon `push_event` nicht-verlustbehaftet + die 3 schlafenden Hooks registrieren → grobes idle/running/waiting/done live. (Kleiner, sofort testbarer Gewinn.)
2. Feed: `PostToolUse`-Hook + `entries`-Füllung + UI-Feed.
3. Mood: `mood.py` + `#face` in der UI.
4. Notify: `notify.py` + WAV-Assets + Quiet-Toggle.

## 9. Offene Punkte / später

- Liefert das Hook-JSON verlässliche Token-Usage? (Beim Bau prüfen; sonst Token-Feld unverändert lassen.)
- WAV-Sounds: eigene erzeugen vs. System-Sounds — beim Bauen entscheiden.
- Light-Notify-Kanal (Backlight-Puls/LED) als Opt-in nachrüsten, falls Sound mal stört.
- `PreToolUse` nur `Bash` — andere Tools bewusst kein Approval (Scope-Grenze aus Bridge-Spec).
