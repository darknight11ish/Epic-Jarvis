# Desktop ↔ phone pairing: how far I got, and why the card is not waiting

**Date:** 2026-10-09 · **Worktree:** `.dsh-scratch/pairing` (branch `test/desktop-phone-pairing` off `origin/main` @ `2f925c11`)
**Verdict:** **I did not reach the approval card.** Not because the flow is broken at the card — because **the phone is locked** and the phone's half of pairing cannot run at all from a locked device. **No pairing was approved, no device key exists, and I approved nothing.**

---

## 1. What is running (verified)

| Thing | State | How I know |
|---|---|---|
| Backend on `127.0.0.1:4719` | **Up** | `GET /` → 401, `/api/version`, `/api/pending`, `/api/models` → 401 (`bad or missing X-Jarvis-Token`). 401 means alive and token-gated, not down. |
| Backend bind | `100.75.21.228` (NordLynx) + `127.0.0.1` | Backend banner, log line 1727: `bind 100.75.21.228 - REACHABLE OFF THIS MACHINE (token required)` |
| Desktop app | `jarvis-desktop` pid 30240, "Jarvis" 750×80 bar visible | Window enumeration |
| Desktop ↔ backend | **Connected** | Established TCP `127.0.0.1:61193 → 127.0.0.1:4719`, owned by pid 30240 |
| Paired devices | **0** | Backend startup banner: `devices 0 paired device(s), pairing by QR code on ; old shared key still open for a first device` |
| Phone `f0a5b32b` | OnePlus CPH2419, Android 15 / API 35, arm64-v8a, `user/release-keys` | `getprop` |
| App on phone | `com.jarvis.client` **versionName 0.2.0** (versionCode 1, targetSdk 36) | `dumpsys package` |
| `adb reverse` | `tcp:4719 tcp:4719` present | `adb reverse --list` |

So: **step 6 is not applicable.** No device key exists, so there was nothing to test.

## 2. The flow, from the code (routes and where the card comes from)

Setup is `docs/PAIRING-DESIGN.md`; the implementation is `backend/jarvis_devices.py` (mirrored at `jarvis-backend/jarvis_devices.py`).

1. **The PC starts a session** — `POST /api/pair/start` `{"address": "...nord"}` (`jarvis_devices.py:1410`). PC-only (`403 pc_only` elsewhere). Returns `{pair_id, qr, code, expires_in: 600, tries_left: 3}`. The desktop button is **Settings → Devices → "Pair a phone"** (`jarvis-desktop/src/settings.html:373`, `#dv-pair`; driver `jarvis-desktop/src/devices.js:408` `pairPhone()` → Tauri `pair_start`).
   * The **short code** is `show_code(s.code)`; the **QR** is the Rust-drawn picture of `qr_text()` (`:691`) = `jarvis-pair:v1/<host>/<port>/<pair_id>/<secret>/<expires>`. The secret and code are **never** in `GET /api/pair/session`.
   * **The code was never produced this run**, because a session only starts when the PC asks for one, and I stopped before that (see §4).
2. **The phone asks for its own key** — `POST /api/pair/claim` `{method, pair_id|code, phone_nonce, name, proof}` (`:1529`). **No token at all** (`KEYLESS`, `:2249`); guarded by two things:
   * `mesh_peer(peer, local, own)` must answer **`"mesh"`** (`:775`), and
   * the phone must prove knowledge of the code/QR secret (`claim_proof`, HMAC over `jarvis-pair-v1\0method\0ref\0phone_nonce\0name`).
   On success the state becomes `waiting_for_card` and the route **returns the four words** — the shared secret the owner compares on both screens.
3. **The card is raised here** — `claim()` spawns `_decide()` (`:1583`), whose whole body is `gate(ACTION, {...}, text)` with `ACTION = "pair_device"` (`:128`). That call is what puts the approval card on the PC. Its words are `card_text()` (`:1290`), verbatim:

   > `"<name>" is asking for its own key to talk to Jarvis.`
   > `Check that phone shows these four words: <w1> · <w2> · <w3> · <w4>`
   >
   > `Approve only if you are pairing that phone right now, on this PC. If you did not press "Pair a phone", deny this. You can remove the device any time in Settings, Devices.`

4. **The phone collects the key** — `POST /api/pair/collect` `{pair_id, proof}`, polled every 2 s (`:1609`). Only after the card is **approved** does `_mint()` (`:1649`) create the device row and hand the token over **once**; only the token's SHA-256 is stored.

**The card is PC-only, and that is enforced twice:**
* `pair_device` is in `PC_ONLY_ACTIONS` (`backend/jarvis_owner_check.py:143`), so approving it **must** happen on the PC with **Windows Hello** — `PC_ONLY = "This card can only be approved on the PC, with Windows Hello, so nothing was approved"`.
* `why_not()` (`:1302`) refuses to start a session at all unless the tier is `"ask"` **and** the owner-check is armed; the phone half additionally cannot complete without the owner's yes.

This is the rule I was told matters most, and the code makes it structural rather than a matter of my restraint: **there is no route that completes pairing.** The key is minted only inside `collect()`, gated on `s.state == "approved"`, and that state is only ever set by a person's yes through `gate()`. Writing a device key by hand is likewise not a route — the registry stores only hashes.

## 3. Two concrete technical findings

**(a) Pairing cannot work over `adb reverse` — and that is by design.**
The phone reaches `127.0.0.1:4719` through the USB reverse tunnel, but the backend then sees the connection as *loopback*, and `from_this_pc()` (`:761`) treats loopback as "this PC". I proved this with a keyless probe:

```
POST http://127.0.0.1:4719/api/pair/claim   -> 403 {"reason":"not_mesh",
    "error":"Pairing is for another device - this PC already has its own key."}
POST http://100.75.21.228:4719/api/pair/claim -> 403 {"reason":"not_mesh", ...same...}
```

The second line is the important one: **connecting to the PC's own Meshnet address is also judged "this PC"**, because `mesh_peer` checks `from_this_pc(peer, local)` *before* the mesh ranges. A genuine second device has its own 100.x address, so it passes — but the `adb reverse` shortcut does not, and can never make pairing work. Pairing goes over **Meshnet or Tailscale**, exactly as the owner decided on 2026-09-28.

**(b) The pairing name resolves, so the mesh path is live.**
`jarvis-desktop.json` holds `"pair_phone_address": "marioirelan11-alps.nord"` and `"bind_address": "100.75.21.228"`. That name resolves from this PC to `100.75.21.228` (via a hosts-file entry: `100.75.21.228 marioirelan11-alps.nord`), and it pings. The phone is on Meshnet at `tun0 = 100.124.30.77`.

## 4. Where it stopped, and why

**The phone is locked.** `dumpsys window` reports `isKeyguardShowing=true`, `mDreamingLockscreen=true`, focus on `NotificationShade`. Screenshots show the lock screen — *"Emergency calls only", "Friday 1:24", "Charging 78%"* — with the fingerprint prompt (`OnScreenFingerprintIcon`, `OnScreenFingerprintDimLayer`). Evidence: `evidence/04-phone-locked.png`.

Consequences, each observed rather than assumed:
* **`uiautomator dump` fails** on the locked device — no `/sdcard/uiN.xml` is produced ("failed to stat remote object"). So I could not find or confirm the pairing fields, and step 3's UI-dump/drive loop cannot run.
* I did **not** unlock it, swipe it, or try a PIN. That is the owner's security boundary.
* I deliberately did **not** call `POST /api/pair/start`. A session with no phone to claim it only expires after 600 s, and starting one *cancels any session already live* (`jarvis_devices.py:1428-1429`), so starting one would have destroyed another agent's session for no gain. (I also could not read `GET /api/pair/session` to check whether one was already live: it is token-gated and I have no token. So I cannot state from observation that the state is `none` — only that **I** started nothing, and that no card was on screen when I captured the screen repeatedly between 13:26 and 13:33.)

**A second, softer blocker on the PC side:** I could reach the desktop's Settings window through its own command palette (Jarvis bar → `/` → type `devices` → the row *"Devices — Every paired device with its own key"*) — that part worked, and the app created the window: `cls='Tauri Window' title='Jarvis Desktop — Settings' [695x737 at 127,0]`. But it stays **`visible=False`**, and `ShowWindow`/`MoveWindow` from outside are ignored, because the app holds it hidden (it is built `.visible(false)` and shown by its own `window_memory` restore path). So I could not read or click the Devices panel, and could not press "Pair a phone" myself. Everything past §2 therefore comes from the code, not from the running UI.

## 5. The owner action needed

**None right now — there is no card waiting.** The single blocking action is earlier in the flow:

> **Unlock the phone** (`f0a5b32b`), leave it on the home screen, and have the PC's Settings → Devices open. Then the phone must be driven to *Pair with your desktop → Type the code instead*, and the code typed there. Only after that does the card appear.

If a card does appear later, what it asks for is: **a Windows Hello check (fingerprint/PIN) plus a tap on Approve on the PC** — it cannot be approved from the phone or by any route, by design. Its exact words are quoted verbatim in §2.3.

## 6. What I could not test

* The phone half of pairing, end to end (locked device).
* Whether the card actually appears — **I never saw a card**, because no phone claimed a session.
* Everything in the brief's step 6: connected state on the phone, the phone in the desktop's Devices list, a phone chat message answered by the backend, a PC approval card reaching the phone, and survival of an `adb reverse` hiccup. None could be attempted: **no device key exists** (`0 paired device(s)`).

## 7. Evidence kept (not committed)

`evidence/` — `00`/`03` splash + current screen, `04-phone-locked.png` (the lock screen), `10`/`13`/`22` PC screens, `11` main window, `23` the Jarvis bar, `25`–`29` command palette → *Devices* row, `15` tray overflow with the Jarvis icon (its own tooltip reads *"Jarvis — connecting…"*). Helper scripts `focus-win.ps1`, `click.ps1`, `reveal-settings.ps1`, `tray-list.ps1`, `overflow-list.ps1`. No token, code or key appears in any of them.

## 8. Notes and loose ends

* The desktop's main window reads **"DEMO · NOT CONNECTED"** and the tray icon reads **"connecting…"**, yet the app holds a live TCP connection to the backend (pid 30240). That looks like a stale status, and it is worth a separate look — it is not what stopped this task.
* The backend has crashed and been watchdog-restarted repeatedly (`jarvis-desktop.log`: restarts at 23:32, 23:36, 00:40, 20:15, 20:20 today), most recently at 20:20:51. The backend has written **nothing** to `backend.log` since (its mtime is frozen at 20:20:51) even though it is serving requests, so the log is not currently useful for watching requests.
* `jarvis-desktop.exe` is version 0.2.0; phone app 0.2.0.
