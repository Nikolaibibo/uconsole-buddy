---
tags: [projekt, uconsole, claude, ble, maker]
status: bereit-zur-umsetzung
created: 2026-07-19
updated: 2026-07-19
hardware: uConsole (Raspberry Pi CM4)
sprache: Python
---

# Claude Companion (uConsole) — Spec

> Planungsdokument. Erst Spec, dann Code (Python). Ziel: schlank, keine Zusatzdienste.

## 0. Umsetzungs-Schärfung (2026-07-19)

> Erarbeitet mit MARVIN. Protokoll Feld-für-Feld gegen Anthropics offizielle Referenz `anthropics/claude-desktop-buddy` (`REFERENCE.md`) geprüft — **stimmt vollständig überein, kein Protokoll-Bug im Ur-Spec.** Es gibt eine funktionierende Referenz-Firmware (M5StickC Plus, ESP32); ihr Verhalten spiegeln wir in Python statt es zu erraten.

### Hardware-Gate: bestanden ✅ (Console live per SSH, `192.168.178.146` / `.37`)
- **Zwei BT-Controller.** Wir nehmen **hci0 = onboard Cypress BCM4345C0** (`2C:CF:67:FE:1E:1D`, UART): `Powered: yes`, `UP RUNNING`, nicht blockiert, hat `GattManager1` + `LEAdvertisingManager1`, `current settings: … le secure-conn`. → Advertising + GATT-Peripheral + verschlüsselte Characteristics (Bonding) hardwareseitig abgedeckt.
- **hci1 = USB-Realtek RTL8821C** (`90:DE:80:D4:12:DE`, DOWN, soft-blocked) ist fälschlich bluetoothctl-`[default]`. → **App muss hci0 explizit pinnen**, sonst wirbt sie auf dem toten Adapter. hci1 sonst ignorieren.
- BlueZ **5.66**, Debian 12 Bookworm, Python **3.11.2**, `venv` + pip da. Kein Dongle nötig. (`hciuart` inactive ist ok — hci0 ist trotzdem oben.)

### Gelockte Entscheidungen
- **Code-Repo:** `~/Documents/web/uconsole-companion/`.
- **Test-Loop = echt (a):** Dev-Mode an, echte Claude-Code/Cowork-Session; Prompt on-demand auslösen = **nicht-allowlisteter Command** (z.B. Bash) → Prompt **parkt unbegrenzt**, läuft beim Testen nicht weg. Notnagel (dokumentiert, nicht gebaut): `tools/test_serial.py`-Muster auf einen `bleak`-Central umschreiben.
- **TUI = Textual, Fenster-App auf dem Desktop** (nicht curses, nicht Boot-TTY). Autostart via `~/.config/autostart/*.desktop`. Fällt Textual-Perf auf dem CM4 durch → curses-Fallback.

### Protokoll-Deltas aus der Referenz-Firmware (verbindlich)
- **TX-Chunking:** Notifications in `MTU-3` splitten, **cap 180 Byte**, ~4 ms Yield zwischen Chunks (BLE-Stack flushen lassen). macOS handelt MTU ~185 aus; Peer mit 23-Byte-Default nicht abschneiden.
- **RX-Reassembly:** Bytes puffern bis `\n`, dann Zeile parsen (`json.loads`). Ring/Puffer voll → droppen (Upstream soll mithalten).
- **Reconnect:** `onDisconnect` → **sofort Advertising neu starten** + `secure`/`passkey` zurücksetzen. (Ergänzt §8.)
- **Permission-State-Machine (Kern):** `last_prompt_id` tracken; ändert sich `prompt.id` → `response_sent=False`, Ankunftszeit stempeln, Alert (Ton/LED/Wecken). `in_prompt = prompt_id and not response_sent`. `Y`→`once`, `N`→`deny`, danach `response_sent=True`.
- **Security (Phase 3):** DisplayOnly-IO-Capability, `SC + MITM + Bond`, Keysize 16, NUS-Characteristics **inkl. CCCD** encrypted-only, Passkey wird **am Gerät angezeigt** / am Mac getippt, Auth-Fail → disconnect. Auf BlueZ = eigener **Agent** (Capability `DisplayOnly`, implementiert `DisplayPasskey` → Passkey in die TUI). `bluez-peripheral`s eingebauter Agent reicht dafür vermutlich nicht → rohes `dbus-fast` einplanen (offener Punkt #2 bestätigt).

### Verbesserung ggü. der Referenz — Permission-Delivery-Sicherheitsnetz
Die geräte-initiierte `permission`-Nachricht wird vom Mac **nicht geackt**. Die Firmware latcht `response_sent` blind → geht die Notify verloren, hängt sie fest (zeigt „beantwortet", Buttons tot). **Wir machen es robuster:** nach dem Senden Status „gesendet ✓ — warte auf Bestätigung"; der **nächste Snapshot** mit gewechselter/leerer `prompt.id` = Bestätigung; bleibt dieselbe `prompt.id` >~4 s stehen → Buttons **re-armen** (Neu-Senden möglich). → gehört in §8.

### Scope-Trims (YAGNI)
- **Raus:** GIF-Pets/Characters, Folder-Push (`char_begin` bewusst nicht acken → Mac-Timeout), Pet-Gamification-Stats `vel`/`nap`/`lvl`, `bat`-Feld (v1). Status-Ack meldet nur **`appr`/`deny`** + `sec` + `sys.up` + `name`.

### Referenz-Artefakte
- Repo: `github.com/anthropics/claude-desktop-buddy` — `REFERENCE.md` (Protokoll-Vertrag), `src/ble_bridge.cpp` (NUS/Framing/Chunking/Security), `src/main.cpp` ~Z.1023–1139 (Permission-State-Machine), `tools/test_serial.py` (Python-Protokoll-Muster).

## 1. Ziel (Desired Result)

Die uConsole wird ein physisches **Freigabe- und Status-Terminal** für Claude Desktop, das auf dem Mac läuft. Sie zeigt an, was Claude gerade tut (Sessions, letzte Zeilen, Tokens) und erlaubt es, wartende Tool-Freigaben mit einem Tastendruck zu **erlauben (`once`)** oder **abzulehnen (`deny`)**. Genau diese Permission-Antworten sind die „Kontroll-Signale".

Kein separater Dienst, kein Cloud-Anteil: der Mac spricht direkt per BLE mit der uConsole.

## 2. Architektur (Überblick)

```
┌──────────────────────┐        BLE (Nordic UART)        ┌───────────────────────┐
│  Mac                  │  ── Snapshots / Prompts ──▶     │  uConsole (CM4, Linux) │
│  Claude Desktop       │                                 │  Python: BLE-Peripheral│
│  Dev-Mode → Hardware  │  ◀── permission once/deny ──    │  + TUI (approve/deny)  │
│  Buddy = BLE Central  │  ◀── acks / status ──           │                        │
└──────────────────────┘                                 └───────────────────────┘
```

- **Mac** = BLE **Central** (scannt, verbindet). **uConsole** = BLE **Peripheral** (advertised, GATT-Server).
- **Ein** Python-Prozess auf der uConsole. Asyncio durchgehend, keine Threads.

## 3. Voraussetzungen

- CM4 muss die **Wireless-Variante** sein (Onboard-BT). Falls nicht: USB-BLE-Dongle. → Check: `bluetoothctl show` zeigt einen Controller.
- Aktuelles **BlueZ** (`sudo apt install bluez`), muss `LEAdvertisingManager1` + `GattManager1` unterstützen (Pi OS tut das).
- Mac-seitig einmalig: **Help → Troubleshooting → Enable Developer Mode**, dann **Developer → Open Hardware Buddy… → Connect**, uConsole aus der Liste wählen, BT-Freigabe erteilen. Danach reconnectet der Bridge automatisch.

## 4. BLE-Transport

Nordic UART Service (serial-over-BLE). Die uConsole advertised einen Namen, der mit `Claude` beginnt (ein paar Bytes der BT-MAC anhängen, damit mehrere Geräte im Picker unterscheidbar sind).

| Rolle | UUID |
| --- | --- |
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| RX (Mac → Gerät, write) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| TX (Gerät → Mac, notify) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

**Framing:** UTF-8 JSON, ein Objekt pro Zeile, mit `\n` terminiert. RX über MTU-Grenzen hinweg zusammensetzen (Bytes puffern bis `\n`, dann parsen). TX-Notifications einfach in Häppchen senden, der Mac setzt zusammen.

**Timeout:** kommt >30 s kein Snapshot, gilt die Verbindung als tot → in der TUI „disconnected" zeigen.

## 5. Nachrichten

### 5.1 Mac → Gerät (empfangen & parsen)

**Heartbeat-Snapshot** (bei jeder Änderung + Keepalive alle 10 s):

| Feld | Bedeutung |
| --- | --- |
| `total` | Anzahl aller Sessions |
| `running` | aktiv generierende Sessions |
| `waiting` | Sessions, die auf eine Freigabe warten |
| `msg` | Einzeiler für kleines Display |
| `entries` | letzte Transkriptzeilen, neueste zuerst (wenige) |
| `tokens` | kumulierte Output-Tokens seit App-Start |
| `tokens_today` | Output-Tokens seit lokaler Mitternacht |
| `prompt` | **nur wenn eine Entscheidung ansteht**: `{id, tool, hint}` |

Abgeleitete Signale: `waiting > 0` → Freigabe blockiert (TUI-Alarm), `running > 0` → arbeitet, `total == 0` → nichts offen.

**Turn-Events** (optional): `{"evt":"turn","role":"assistant","content":[…]}`. Enthält das rohe SDK-Content-Array; >4 KB werden verworfen. → kann für „letzte Antwort"-Zeile genutzt werden, nicht kritisch.

**One-shot beim Connect:**
- `{"time":[<epoch>, <tz_offset_sec>]}` → lokale Zeit setzen (kein Ack).
- `{"cmd":"owner","name":"Nikolai"}` → Besitzername (Ack, siehe unten).

### 5.2 Gerät → Mac (senden)

**Freigabe-Entscheidung (die Kontroll-Signale):**
```json
{"cmd":"permission","id":"req_abc123","decision":"once"}
{"cmd":"permission","id":"req_abc123","decision":"deny"}
```
`id` muss exakt `prompt.id` entsprechen. `once` = Tool erlauben, `deny` = ablehnen.

**Acks** — jede Nachricht mit `cmd`-Feld erwartet ein Ack:
```json
{"ack":"<cmd>","ok":true,"n":0}
```

| Kommando | Aktion | Ack |
| --- | --- | --- |
| `{"cmd":"status"}` | Statusabfrage (Mac pollt ~alle 2 s) | Status-Ack (s.u.) |
| `{"cmd":"name","name":"…"}` | Anzeigename setzen | `{"ack":"name","ok":true}` |
| `{"cmd":"owner","name":"…"}` | Besitzer setzen | `{"ack":"owner","ok":true}` |
| `{"cmd":"unpair"}` | gespeicherte Bonds löschen | `{"ack":"unpair","ok":true}` |
| Folder-Push (`char_begin`…) | **nicht** unterstützen → nicht acken, Mac läuft nach paar Sekunden in Timeout | — |

**Status-Ack** (Mac füllt damit sein Stats-Panel):
```json
{"ack":"status","ok":true,"data":{
  "name":"Claude-uConsole",
  "sec":true,
  "sys":{"up":<sek>},
  "stats":{"appr":42,"deny":3}
}}
```
Nicht vorhandene Felder einfach weglassen (`bat` z. B. brauchen wir nicht). `sec:true` nur, wenn die Verbindung verschlüsselt ist (→ Phase 2).

## 6. Funktionsumfang (voll)

1. **Control** — approve/deny wartender Prompts. *(Kern)*
2. **Status + letzte Zeilen** — `running`/`waiting`/`msg` + `entries`.
3. **Tokens + Stats-Panel** — `tokens` / `tokens_today` anzeigen; Gerät zählt `appr`/`deny` lokal, zeigt sie und meldet sie im Status-Ack zurück.

## 7. TUI-Layout

```
┌ Claude Companion ───────────────── ● verbunden 🔒 ┐
│ Owner: Nikolai            up 2h14m                 │
├───────────────────────────────────────────────────┤
│ Sessions:  total 3   running 1   waiting 1         │
│ » approve: Bash                                    │  ← msg
├─ letzte Zeilen ───────────────────────────────────┤
│ 10:42  git push                                    │
│ 10:41  yarn test                                   │
│ 10:39  reading file...                             │
├─ tokens ──────────────── stats ───────────────────┤
│ session 184.5k   today 31.2k   ✓42  ✗3            │
└───────────────────────────────────────────────────┘

  ⚠ FREIGABE (nur wenn prompt aktiv):
  ┌───────────────────────────────────────────────┐
  │ Tool: Bash                                     │
  │ rm -rf /tmp/foo                                │  ← hint
  │                                                │
  │   [Y] einmal erlauben     [N] ablehnen         │
  └───────────────────────────────────────────────┘
```

**Tasten:** `Y`/Enter = `once`, `N`/Esc = `deny`, `Q` = beenden. (Freigabe-Overlay fängt Tasten, solange `prompt` aktiv ist.)

## 8. Zustände

`disconnected` (kein Snapshot >30 s) → `idle` (`total==0`) → `running` (`running>0`) → `waiting` (`prompt` gesetzt → Overlay + optional LED/Ton). Nach gesendeter Entscheidung zurück, bis der nächste Snapshot kommt.

**Delivery-Sicherheitsnetz (Schärfung 2026-07-19):** Entscheidung ist geräte-initiiert und wird nicht geackt. Nach dem Senden → `sent`-Zustand („gesendet ✓ — warte auf Bestätigung"). Bestätigung = nächster Snapshot mit gewechselter/leerer `prompt.id`. Bleibt dieselbe `prompt.id` >~4 s → Buttons **re-armen** (Neu-Senden möglich), statt fest zu hängen. Bei Disconnect sofort Advertising neu starten + `secure`/`passkey` reset.

## 9. Stack & Module

- **Python 3.11+**, komplett `asyncio`.
- **`bluez-peripheral`** — Advertising + GATT-Server + Agent fürs Pairing.
  - Fallback, falls Bonding mehr Kontrolle braucht: rohes `dbus-fast` nach dem Muster von BlueZ' `example-gatt-server`.
- **TUI: Textual** (async, Panels/Overlays sauber) — Alternative `curses`, wenn maximal minimal.

Thin modules (keine Redundanz):
- `ble_nus.py` — Peripheral, NUS-Characteristics, Line-Reassembler, TX-Queue
- `protocol.py` — Snapshot/Turn/Cmd parsen; permission/ack/status bauen
- `state.py` — App-State + Zähler (`appr`/`deny`), Uhr/Owner
- `ui.py` — Textual-App, Keybindings, Overlay
- `main.py` — verdrahtet alles in einer Event-Loop

## 10. Phasen (rückwärts vom Ziel)

- **Phase 0 — Link beweisen:** NUS-Peripheral advertised, Mac sieht `Claude-uConsole`, verbindet, rohes JSON wird geloggt.
- **Phase 1 — Kern-Companion:** Snapshot parsen → Status/Prompt in TUI; `Y`/`N` sendet `permission`; Acks für `status`/`name`/`owner`/`unpair` + `time`/`owner` verarbeiten. **→ funktionsfähig.**
- **Phase 2 — Voll:** Tokens + Stats-Panel + letzte Zeilen; `appr`/`deny` lokal zählen und im Status-Ack melden.
- **Phase 3 — Härten & Autostart:** LE Secure Connections **Bonding** (verschlüsselte Characteristics, DisplayOnly-IO, 6-stelliger Passkey, `sec:true`, `unpair` behandeln); `systemd --user`-Service für Autostart beim Boot.
- **Out of scope:** Folder-Push, GIF-Pets.

## 11. Sicherheit (Phase 3, aber wichtig)

Über die Verbindung fließen Transkript-Schnipsel und Tool-Hints → unverschlüsselt in Funkreichweite mitlesbar. Für den Dauerbetrieb daher **Bonding aktivieren**: NUS-Characteristics als encrypted-only markieren, DisplayOnly-IO advertisen → erste GATT-Nutzung löst OS-Pairing aus (Mac fragt nach dem Passkey, den die uConsole anzeigt), danach AES-CCM-verschlüsselt. Phase 1 darf zum schnellen Anlaufen unverschlüsselt sein.

## 12. Offene Punkte (beim Bau prüfen)

- ~~CM4 wirklich Wireless-Variante? BT onboard aktiv?~~ ✅ **Gelöst 19.07.:** hci0 Cypress onboard, `Powered: yes`, LE + secure-conn. hci0 pinnen, hci1 ignorieren (siehe §0).
- `bluez-peripheral`: reicht der eingebaute Agent für LE-Secure-Bonding, oder braucht es rohes dbus? → **Erwartung: rohes `dbus-fast` für DisplayOnly-Agent** (siehe §0 Security). Beim Bau Phase 3 verifizieren.
- Textual-Performance auf der uConsole ok? (sonst `curses`) → **In Phase 1 live messen** (Entscheidung: Textual, Fenster-App).
- ~~Autostart als `systemd --user` inkl. BT-Rechten.~~ → **Entschieden: `~/.config/autostart/*.desktop`** (Fenster-App, kein TTY/systemd).
