# Pairing a phone by QR code, with a key per device (design)

> Written 2026-09-28, after the owner said "build QR-code pairing now"
> (CLAUDE.md, commit `dfff89ce`). Checked against the code at that commit.
> Every claim about existing code names the file and line it was read at.
> This is a design: **nothing here is built yet.**
>
> Two phases, in one document, so the first can ship alone:
> - **Phase 1 - pairing and a key per device** (feasibility I102). Sections 1-10.
> - **Phase 2 - a fingerprint-signed yes for risky cards from the phone**
>   (feasibility I103, the approval gap's step 2). Section 11. It needs
>   phase 1 and changes nothing in it.

## The short answer

- **On the PC**, Settings has a new "Devices" section with **Pair a phone**.
  It shows a QR code (a square barcode a camera can read) and, under it, an
  8-letter code such as `K7QM-4TXD` for when the camera cannot be used. Both
  stop working after 10 minutes, after one use, or after 3 wrong tries.
- **On the phone**, the pairing screen gets **Scan the code on your PC** and
  **Type the code instead**. The phone shows four short words, for example
  `tulip · anchor · mellow · crane`.
- **On the PC an approval card appears**: "Connect a new device to Jarvis?",
  with the phone's name and the same four words. It always needs Windows
  Hello, and it can only be approved on the PC. If the words match, approve.
  Only then does the phone get its own key.
- **Every device has its own key**, listed in both apps with a **Remove**
  button. Removing one cuts it off within seconds; the others carry on.
- **The old shared key keeps working** until the owner presses **Retire**.
  Retiring stops other devices using it; this PC's own apps keep using it,
  so the owner can never be locked out of the PC. Nothing is retired
  automatically.
- **Keys are never logged and the PC stores only a fingerprint of each key**
  (a SHA-256 hash - a one-way scramble that cannot be turned back into the
  key).
- **The phone still connects only over Tailscale or NordVPN Meshnet**, and
  pairing itself is refused over anything else.

What it does not fix, said plainly: a program already running as the owner
on the PC can still read the PC's own key and edit Jarvis's files
(ARCHITECTURE §3, "A known limit"). Pairing does not change that. What it
does change: a copied phone key can be removed on its own, the old shared
key stops working from other devices once retired, and phase 2 then makes
a stolen key on another device unable to approve anything risky.

---

## 1. What exists today (checked)

- **One shared key for everything.** The backend's key ("pairing token") is
  kept in Windows Credential Manager under `"Jarvis Backend/pairing token"`
  (`backend/jarvis_token_store.py:89`). `HUD_TOKEN` in the environment wins
  over it (`jarvis_token_store.py:32-34`, docstring step 2). The desktop's
  own copy lives under `"Jarvis Desktop/pairing token"`
  (`jarvis-desktop/src-tauri/src/token_store.rs:35`), and the desktop hands
  it to the backend it starts as `HUD_TOKEN` (`jarvis_token_store.py:32-34` and `:54-59`).
- **The phone is given that same key by hand.** Settings on the PC has "Show
  the token for my phone" (`jarvis-desktop/src/settings.html:132`,
  `commands.rs:693-704` `reveal_pairing_token`). The owner types 43
  characters into the phone (`PairingScreen.kt`'s token field and its "Show
  token" note). `JARVIS-API.md` §1 says it plainly: "the server cannot tell
  the laptop from the phone".
- **Every request carries it in `X-Jarvis-Token`**, plus
  `X-Jarvis-Client: hud` (phone: `net/JarvisApi.kt:299-303` `authed()`,
  names at `JarvisApi.kt:2350-2351`; desktop: `commands.rs:49`
  `JARVIS_CLIENT`, applied at `commands.rs:1642`).
- **The backend's check is `_token_ok(self)`, in the owner's
  `jarvis_hud.py`, which is not in this repository.** Its body has never
  been read here. What is known: every route patch calls it as
  `_token_ok(self)` and answers `401 {"error": "bad or missing
  X-Jarvis-Token"}` when it says no (e.g. `backend/feedback.patch:110-111`);
  it admits any loopback request when no token is set at all
  (`docs/API-DISAGREEMENTS.md:112`); and 22 hunks hand it to a module's
  `install(..., token_ok=_token_ok, ...)` at start-up, the **first** of them
  owner-check's, right after `_refuse_every_interface(bind)` at
  `jarvis_hud.py` line ~2408 (`backend/owner-check.patch`, hunk
  `@@ -2408,6 +2408,20 @@`). This matters for section 5.2.
- **"From this PC" is already decided in one place**:
  `jarvis_owner_check.from_this_pc(peer, local, own)`
  (`backend/jarvis_owner_check.py:218-240`): loopback, the address the
  connection arrived at, or one of the PC's own addresses; anything that
  cannot be placed counts as this PC.
- **Some cards can only be approved on the PC, always with Windows Hello**:
  `PC_ONLY_ACTIONS` (`jarvis_owner_check.py:118`), enforced in
  `approve_check` (`jarvis_owner_check.py:598-661`).
- **The phone keeps the key encrypted** with an AES key that never leaves
  the Android Keystore (`data/TokenStore.kt:35-169`); the Keystore key is
  deliberately usable without a fingerprint, so the background event stream
  can reconnect with the screen off (`TokenStore.kt:112-117`).
- **The phone's re-pair never loses a working key**: a new address and key
  are tried, and the old ones put back if the handshake fails
  (`MainActivity.kt:1383-1476`).
- **The phone's fingerprint check proves nothing to the PC**:
  `prompt.authenticate(builder.build())` has no `CryptoObject`
  (`ui/approval/BiometricGate.kt:189`).
- **Addresses**: the backend listens only on loopback and a mesh address
  (`validate_bind_address`, `commands.rs:760`); the mesh ranges are
  `100.64.0.0/10` and `fd7a:115c:a1e0::/48`
  (`backend/jarvis_local_http.py:99-100`); the phone may use plain
  `http://` only to `*.ts.net` and `*.nord` names
  (`data/PhoneAddress.kt:44-46`, ARCHITECTURE §2 line 92 onward).
- **No QR code or camera code exists anywhere.** Searched `jarvis-client`,
  `jarvis-android` and `jarvis-desktop` for CameraX, ZXing, ML Kit,
  barcode and QR: nothing. The phone's manifest has no `CAMERA` permission.
  `Cargo.toml` and `package.json` have no QR crate or package.
- **The desktop windows load nothing from outside**: the page policy is
  `default-src 'self'` with `img-src 'self' data: blob:`
  (`src-tauri/tauri.conf.json:67`). A QR image must be made locally.
- **Backups copy every `*.json` directly in the settings folder, never a
  subfolder** (`backend/jarvis_backup.py:47-49`, `:508`). Section 4 relies
  on that.
- **`cryptography` is optional on the backend** ("Without it NOTHING is
  kept", `backend/requirements.txt`, chat history line). Phase 1 is
  designed to need only Python's standard library; phase 2 needs
  `cryptography`.

## 2. Where this design departs from the outline, and why

`docs/CUTTING-EDGE-2026-09-26-round2-trust.md` item 6 sketched: a PC key
fingerprint in the QR code, a phone key made in the Keystore with key
attestation checked on the PC, and words "made from both keys and fresh
randomness". Three changes, each on purpose:

1. **No long-lived PC key, and no long-lived phone key, in phase 1.** The
   one-time 128-bit secret in the QR code already proves each side to the
   other: the phone proves it saw the code (`claim_proof`), and the PC
   proves it made the code (`pc_proof`, which the phone checks). The link
   itself is already scrambled by Tailscale or Meshnet. A long-lived key
   pair on each side would add storage, rotation and a new package
   (`cryptography`, optional today) without stopping any attack the secret
   does not already stop. The four words are made from **the pairing secret
   (the PC's side), the phone's own fresh random number, the PC's fresh
   random number, and the phone's name** - both sides and fresh randomness,
   which is what KDE Connect's 2025 advisory was about (a short code from
   long-lived keys alone could be brute-forced). The one key pair that
   actually earns its place - a phone key that needs a fingerprint for
   every use - comes in phase 2.
2. **Key attestation is deferred** (section 9 says why).
3. **The old shared key is not killed by "Retire" - it becomes this PC's
   key.** Retiring stops other devices using it. The desktop app and the
   backend on the same PC keep using it, because any program on the PC can
   read any key kept there anyway (ARCHITECTURE §3), so a separate desktop
   key would protect nothing - and keeping it means the owner cannot lock
   themselves out of the PC.

## 3. The flow, step by step

```
PC (desktop app)            backend                         phone
----------------            -------                         -----
"Pair a phone" ---------->  POST /api/pair/start
                            makes pair_id, secret, code,
QR + code + 10:00 <-------  expiry, pc_nonce
                                                            scans QR (or types code)
                                                            checks address is .ts.net/.nord
                                                            "Connect to jarvis-pc.x.ts.net?"  [Connect]
                            POST /api/pair/claim  <-------  phone_nonce, name, claim_proof
                            checks proof, peer is a mesh
                            device (not this PC), tries left
                            raises card pair_device --------------------------------+
                            202 {words, pc_nonce, pc_proof} ---------------------> checks pc_proof,
                                                            works out the words itself,
                                                            refuses if they differ;
card on PC:                                                 shows the 4 words
"Connect a new device?"                                     "Approve on your PC if they match"
name + the 4 words
Approve -> Windows Hello
                            POST /api/pair/collect <-------  every 2 s: pair_id, collect_proof
                            200 {device_id, token} ------->  saves token (TokenStore)
                            (once; session ends)            handshake with the new key
                                                            only then drops the old key
```

States of one pairing session (`GET /api/pair/session`, PC only):
`waiting_for_phone` -> `waiting_for_card` -> `approved` -> `done`, or it
ends as `denied`, `timed_out` (the card ran out), `expired` (10 minutes),
`burnt` (3 wrong tries), `cancelled` (the owner pressed Cancel or started a
new one), `refused` (the gate refused - wrong tier, gate failure).

There is **at most one session at a time**. Starting a new one cancels the
old one; a card still waiting for the old one is withdrawn (section 6.3).

## 4. What is stored

**Backend: `<Jarvis settings folder>/devices/registry.json`** (the settings
folder is `~/.openjarvis/`). In a **subfolder on purpose**: backups copy
only `*.json` directly in the settings folder (`jarvis_backup.py:47-49`),
so a restore can never bring back a removed device's key.
`test_devices.py` checks this against the real backup code.

```json
{
  "version": 1,
  "devices": [
    {
      "id": "d3f9a1c2e",
      "name": "Pixel 9",
      "kind": "phone",
      "token_sha256": "c26fc74e5d2065cd3d11bbb8fcae3193d54290ba5b86accdc0ae32af9e56f008",
      "created": 1790000000,
      "last_seen": 1790003600,
      "removed": null,
      "approval_key": null
    }
  ],
  "shared": {
    "retired": false,
    "retired_at": null,
    "last_other_seen": 1790003000,
    "last_other_address": "100.101.2.3"
  }
}
```

- `id`: `d` + 8 lowercase hex characters, random. Safe to show and log.
- `name`: 1-40 characters, the phone's model by default ("Pixel 9"),
  editable on the phone before it asks. **Allowed characters only**:
  letters and digits (any script), space, and `- _ . ' ( )`. No control
  characters, no right-to-left override characters, no line breaks - the
  name appears on an approval card, so it must not be able to fake card
  text. A name outside the rule is refused (400), never quietly cleaned,
  because it is part of the words' input (section 6.2) and the two sides
  must agree on it exactly. The rule is in the shared cases file.
- `token_sha256`: SHA-256 of the whole key text, as lowercase hex. A plain
  hash is enough: the key is 256 random bits, so nothing can guess it; a
  slow hash (Argon2, bcrypt) exists to protect guessable passwords, which
  this is not. The key itself is never written anywhere on the PC.
- `last_seen`: seconds since 1970, rounded to the minute, kept in memory and
  written at most once a minute per device (not on every request).
- `removed`: when it was removed. The row stays (so a past approval can
  still say which device it came from), with `token_sha256` set to `""`.
- `approval_key`: phase 2 (section 11). Always `null` in phase 1.
- `shared.last_other_seen` / `last_other_address`: when the old shared key
  was last used from **another device**, and from where. This is what lets
  the Retire button warn "something still uses it" (section 7.3).

Written by one lock-protected function, to a temporary file then renamed
over the old one (so a crash never leaves half a file).

**A file that cannot be read fails closed for other devices, never for the
PC**: every device key is refused and the shared key is treated as retired
for other devices - but requests from this PC still work, so the desktop's
Devices page can say what is wrong and offer **Start fresh** (which moves
the bad file aside as `registry.json.broken-<time>` and makes an empty one;
every phone then pairs again). Said on the page in those words.

**Phone**: the device key goes into the existing `TokenStore`
(`TokenStore.kt:71` `setToken`) - same Keystore-encrypted storage, no new
store. The phone can tell a device key from the old shared key by its
shape (section 5.1).

**Desktop**: nothing new is secret. The phone address to put in the QR code
(section 8.1) is remembered in the ordinary settings store; it is not a
secret.

## 5. How every request is checked after the change

### 5.1 The key's shape

`jdk1.<id>.<secret>` - for example `jdk1.d3f9a1c2e.<43 characters>`.
`<secret>` is `secrets.token_urlsafe(32)` (43 characters of `A-Z a-z 0-9 -
_`). Total 58 characters. The prefix does three jobs: the backend knows at
once which path to take, the device id lets it find the row without trying
every one, and the log scrubbers can recognise one even out of context
(today's key "is 43 random characters with no prefix", `jarvis_scrub.py:48`).
Regex, used by all three scrubbers and the fixture:
`jdk1\.d[0-9a-f]{8}\.[A-Za-z0-9_-]{43}`.

It still travels in `X-Jarvis-Token`. **Neither app's request code
changes**: `authed()` and `jarvis_headers()` send whatever key is stored.

### 5.2 The check (`backend/jarvis_devices.py`, `wrap_token_ok`)

```
key = X-Jarvis-Token header, trimmed
if key starts with "jdk1.":
    parse id; no such row, removed, or hash differs (hmac.compare_digest)
        -> refused, reason "device_removed"
    else -> allowed; remember this request's device (self._jarvis_device = id);
            note last_seen; guard the response stream (5.4)
    (a device key NEVER falls through to the shared-key check)
else:
    ok = the original _token_ok(self)          # unchanged: today's rule
    if ok and shared is retired and not from_this_pc(peer, local):
        -> refused, reason "shared_retired"
    if ok and not from_this_pc(peer, local): note shared.last_other_seen/address
    -> ok; self._jarvis_device = "pc" if from_this_pc else "shared"
```

`from_this_pc` is `jarvis_owner_check.from_this_pc` - the one rule, reused.

**Where it is wired in (`backend/devices.patch`, one hunk in
`jarvis_hud.py`).** `_token_ok` is a module-level function the route code
looks up by name when it runs, so replacing the name reaches every inline
check. But 22 modules are handed `token_ok=_token_ok` once at start-up and
keep the function they were given. So the replacement must happen **before
the first of them** - immediately before owner-check's hunk, after
`_refuse_every_interface(bind)` and the `_SCRUBBING_LOG` lines that
`owner-check.patch` shows as context:

```python
    # devices.patch (docs/PAIRING-DESIGN.md): a key per device. Before every
    # install() below, because each keeps the _token_ok it is handed.
    try:
        import jarvis_devices
        globals()["_token_ok"] = jarvis_devices.wrap_token_ok(_token_ok)
        print(jarvis_devices.install(Handler, origin_ok=_origin_ok,
                                     token_ok=_token_ok, read_body=_read_body))
    except Exception as exc:
        print(f"  devices    NOT ON ({type(exc).__name__}) - only the shared key works")
```

Failing safe here means **today's behaviour**: without the module, only
the shared key works, exactly as now. A device key is then refused, which
the phone reports (5.3). `test_devices.py` checks, on the stacked file
(`backend/_stack.py`), that this hunk comes before every
`token_ok=_token_ok` in `jarvis_hud.py`. The builder must stack it and read
the result, as the plan-card wiring was checked
(CLAUDE.md, 2026-09-28 plan-card entry); `tools/build_patch_history.py`
after (and `git fetch --unshallow origin` first - CLAUDE.md).

### 5.3 Saying why a key was refused

The route code writes the 401 itself (`{"error": "bad or missing
X-Jarvis-Token"}`), so the wrapper cannot change the body directly. It
wraps `self._send` for that one request: when the answer is 401 and the
wrapper refused the key, it adds `"key": "device_removed"` or
`"key": "shared_retired"` to the body. An app reads it if present and
otherwise falls back to today's words. Both apps' sentences:

- `device_removed`: "This phone's key was removed on your PC, so Jarvis no
  longer answers it. Pair again with the QR code in Settings, Devices, on
  your PC."
- `shared_retired`: "This phone was using the old shared key, which has
  been retired on your PC. Pair it with the QR code in Settings, Devices,
  on your PC."

### 5.4 Removing a device cuts off its open connections too

A removed phone may still have the event stream (`/api/events`) open, or an
answer streaming. The route code for those is in `jarvis_hud.py` (not in
this repository), so the wrapper does not touch it: instead, for a request
made with a device key, it replaces `self.wfile` with a thin guard whose
`write()` first asks `jarvis_devices.is_live(id)` and raises
`BrokenPipeError` when the device was removed. The event stream sends a
keepalive at least every 10 seconds (`JarvisApi.kt`'s read-timeout note,
around line 220), so a removed phone is cut off within about 10 seconds.
Tested with a fake handler; to be confirmed once on the real PC (section
10, "half-hour test").

### 5.5 What each app learns about itself

`GET /api/devices` (6.4) marks the caller's own row `"this_device": true`,
and says `"you": "pc" | "shared" | "<device id>"`. `GET /api/version`
gains `capabilities.pairing: {"version": 1}` (absent or `false` on an older
PC); both apps show pairing and Devices only when it is there.

## 6. The routes (frozen for the three builders)

All answers are JSON. Every route passes the server's origin check as
today, so every request sends `X-Jarvis-Client: hud`. "PC only" means
`from_this_pc` is true, else `403 {"ok": false, "pc_only": true, "error":
"This can only be done on the PC itself."}`. "Mesh only" means the
connection comes from `100.64.0.0/10` or `fd7a:115c:a1e0::/48` **and not
from this PC**, else `403 {"ok": false, "reason": "not_mesh", "error": ...}`
(words in 6.2). A missing `jarvis_devices.py` answers 404 (route not there),
which both apps read as "this PC does not have pairing yet".

### 6.1 Starting and watching a pairing (PC only, key required)

**`POST /api/pair/start`** - body `{"address": "jarvis-pc.tail1234.ts.net",
"port": 4719}` (`port` optional, default the backend's own port).

- `address` must pass the phone's own rule: the shared own-networks rule
  AND a name ending `.ts.net` or `.nord` (the phone cannot use anything
  else, `PhoneAddress.kt:44-46`). Else `400 {"ok": false, "reason":
  "address", "error": "<the phone's own sentence, PhoneAddress.MESSAGE>"}`.
- `200`:
  ```json
  {"ok": true, "pair_id": "00112233445566ff",
   "qr": "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
   "code": "K7QM-4TXD", "expires_in": 600, "tries_left": 3}
  ```
  The `qr` text and the `code` are in **this answer only** - never in
  `GET /api/pair/session`, never logged, never in an event. The desktop
  turns `qr` into a picture in Rust (8.2) and throws the text away.
- Starting again cancels the previous session (and withdraws its card).
- `503 {"ok": false, "error": ...}` if the registry cannot be read (4).

**`GET /api/pair/session`** - `200 {"state", "expires_in", "tries_left",
"device_name" | null, "words" | null, "wrong_tries_from": ["100.x.y.z"],
"message"}`, or `{"state": "none"}`. `words` appears from
`waiting_for_card` on. `wrong_tries_from` lists the addresses wrong tries
came from, so something odd is visible. `message` is the plain sentence for
the state (both apps' words come from here, e.g. burnt: "Three wrong tries
- this code no longer works. Start again.").

**`POST /api/pair/cancel`** - `{}`. `200 {"ok": true, "was": "<state>"}`.
Withdraws a waiting card.

### 6.2 The phone's half (no key needed, mesh only)

These two routes are the only ones in Jarvis that take no key: the phone
has none yet. The QR secret or the typed code is what proves the phone may
ask.

**`POST /api/pair/claim`**

```json
{"method": "qr", "pair_id": "00112233445566ff",
 "phone_nonce": "EBESExQVFhcYGRobHB0eHw", "name": "Pixel 9",
 "proof": "H0lGV2Jnwf0UFy1oAmBO4EZNtAWRnoyX8RjVNFIqq9c"}
```
(`method: "code"` leaves out `pair_id`: there is only ever one session.)

| Answer | Body | Means / phone says |
|---|---|---|
| `202` | `{"state": "waiting_for_card", "pair_id", "pc_nonce", "pc_proof", "words": ["...", "...", "...", "..."], "expires_in"}` | The card is up. The phone checks `pc_proof`, works the words out itself, and refuses if they differ ("The PC answered with different words. Do not approve the card on your PC."). |
| `403` | `{"reason": "wrong_proof", "tries_left": 2}` | "That code is not right. 2 tries left." At 0 the session is burnt. |
| `403` | `{"reason": "not_mesh"}` | "Pairing only works over Tailscale or NordVPN Meshnet. Turn one on, on this phone and on your PC." Also for a request from the PC itself: "Pairing is for another device - this PC already has its own key." |
| `410` | `{"reason": "gone", "state": "expired" \| "burnt" \| "cancelled" \| "used" \| "none"}` | "This code no longer works. On your PC, press Pair a phone again." |
| `400` | `{"reason": "name" \| "bad_request"}` | "Use a shorter name, with letters and numbers only." / a plain error. |
| `503` | `{"reason": "card"}` | "Your PC could not show the approval card. Try again." |

A wrong `proof` for either method counts toward the 3 tries. So does a
`claim` for a session already claimed. `phone_nonce` must be 16 random
bytes, base64url without padding (22 characters).

**`POST /api/pair/collect`** - `{"pair_id", "proof"}`. The phone asks every
2 seconds while the card waits.

| Answer | Body | Phone does |
|---|---|---|
| `202` | `{"state": "waiting_for_card", "expires_in"}` | keeps waiting |
| `200` | `{"state": "approved", "device_id": "d3f9a1c2e", "token": "jdk1.d3f9a1c2e...."}` | saves the key, then shakes hands with it (7.2). Given **once**; the session ends. |
| `403` | `{"state": "denied"}` | "You said no on your PC. Nothing changed on this phone." |
| `410` | `{"state": "timed_out" \| "expired" \| "cancelled" \| "refused" \| "used" \| "none"}` | "The card on your PC ran out of time / was cancelled. Start again on the PC." |
| `403` | `{"reason": "wrong_proof"}` | counts toward the 3 tries |

**The exact sums** (all HMAC-SHA256; `b64u` = base64url, no padding; `||` =
joined; `\0` = a zero byte; text is UTF-8):

```
K        = the 16 secret bytes from the QR code                (method "qr")
         = SHA256("jarvis-pair-code-v1" \0 CODE)               (method "code";
           CODE = the 8 characters, normalised, no dash)
ref      = pair_id (method "qr") or "-" (method "code")
T        = "jarvis-pair-v1" \0 method \0 ref \0 phone_nonce \0 name
proof    = b64u(HMAC(K, "claim" \0 T))
pc_proof = b64u(HMAC(K, "pc" \0 T \0 pc_nonce))
words    = D = HMAC(K, "words" \0 T \0 pc_nonce);
           word i (i = 0..3) = WORDS[ (D[2i]*256 + D[2i+1]) mod 1296 ]
collect  = b64u(HMAC(K, "collect" \0 pair_id \0 phone_nonce))
```

Why HMAC and not the secret itself: the secret and the code **never travel
over the network**, so no log, crash note or proxy ever holds them; and
`pc_proof` lets the phone tell the real PC from anything else answering at
that name.

Test vectors, computed for this document with Python's `hmac` (secret bytes
`00 01 .. 0f`, pair_id `00112233445566ff`, phone_nonce bytes `10 .. 1f`,
pc_nonce bytes `20 .. 2f`, name `Pixel 9`):

| | method `qr` | method `code` (`K7QM4TXD`) |
|---|---|---|
| secret / K | `AAECAwQFBgcICQoLDA0ODw` | `e898e958c53b4f306488422d76cbdd30ba929057ac21bc70fb8ffbaeadff5c2e` (hex) |
| phone_nonce | `EBESExQVFhcYGRobHB0eHw` | same |
| pc_nonce | `ICEiIyQlJicoKSorLC0uLw` | same |
| proof | `H0lGV2Jnwf0UFy1oAmBO4EZNtAWRnoyX8RjVNFIqq9c` | `5cbB9b5oknDpoMN3xu_fPdO5q_GvgR5BwN19a2eXxQ4` |
| pc_proof | `HkPzmveXlM4XdYo_7TECbY7y3HF1Q4mIXmSxVXxDM80` | `WM3nmfZziLG4yNxam4xdbLkbCmz34-67h9-Vig0ZdUo` |
| word numbers | `330, 679, 1036, 970` | `1164, 578, 141, 383` |
| collect | `xqsJqE1r6hkgKSjlXeofy2K_C65PQiTjkZgEtpuTCEg` | `vGv4Z06RSHN36fZ3dWXisIq7S6ALIBm_EsRAgf7xeqE` |

These go into `tools/gen_pairing_cases.py`, which writes the shared cases
file both apps' tests read (section 10). Word **numbers** are in the
vectors so the tests do not depend on the word list; the word list itself
is one file, `contract/pair-words.txt`, copied into both apps.

**The word list**: the EFF "short word list 2" (1,296 words, each with a
unique first three letters, chosen to be easy to read aloud). Its licence
is Creative Commons Attribution 3.0 US according to EFF - **to be re-read
on EFF's page before copying**, then credited in
`THIRD-PARTY-NOTICES.txt` and the phone's `NOTICES.txt`. 4 words give about
41 bits; the small bias from `mod 1296` does not matter for this job.

### 6.3 The approval card

A new gate action, **`pair_device`**, tier `ask`:
- added to `jarvis_owner_check.PC_ONLY_ACTIONS` (`jarvis_owner_check.py:118`)
  - so it **always** asks Windows Hello and is **refused from any other
  device** (a stolen key cannot approve a new device); on a PC without
  Windows Hello it is refused with `NOT_SET_UP` - the owner's "no lock, no
  risky approval". Pairing then is not possible until Windows Hello is set
  up; the old shared key still works meanwhile.
- in the gate's "acts only on tier ask" set and `_RISK` table, like
  `phone_notifications_read` (`backend/phone-notifications.patch:5,17`):
  `("yes", "local", "gives <name> its own key to talk to Jarvis; you can
  remove it any time in Settings, Devices")`.
- raised on a background thread, exactly like
  `jarvis_phone_notifications._decide` (`jarvis_phone_notifications.py:
  231-300`): refused unless the gate answered at tier `ask` and the
  configured tier is `ask`; a session cancelled while it waits is
  "withdrawn", and no key is made.
- The key is made **only after** the gate says approved (and stamped, per
  owner-check) - never before, never held in advance.

Its words (`jarvis_card_words.TITLES` and the card text):

> **Jarvis wants to connect a new device**
>
> "Pixel 9" is asking for its own key to talk to Jarvis.
> Check that phone shows these four words: **tulip · anchor · mellow · crane**
>
> Approve only if you are pairing that phone right now, on this PC. If you
> did not press "Pair a phone", deny this. You can remove the device any
> time in Settings, Devices.

The Windows Hello prompt shows the title, as every PC-only card does
(`approval_message`, `jarvis_owner_check.py:167`).

The card lives the usual `approval_timeout_seconds` (180 s shipped); the
10-minute session covers the scanning before it.

### 6.4 The device list (any key)

**`GET /api/devices`**

```json
{"you": "d3f9a1c2e",
 "devices": [
   {"id": "pc", "name": "This PC", "kind": "pc", "removable": false},
   {"id": "d3f9a1c2e", "name": "Pixel 9", "kind": "phone",
    "created": 1790000000, "last_seen": 1790003600,
    "this_device": true, "removable": true, "approval_key": false}],
 "shared": {"retired": false, "retired_at": null,
            "last_other_seen": 1790003000, "last_other_address": "100.101.2.3",
            "can_bring_back_here": false},
 "pairing": {"available": true, "why_not": null}}
```

Never a key, never a hash. Removed devices are not listed. `pairing.why_not`
is a sentence when pairing cannot work ("Windows Hello is not set up on this
PC...", "The device list cannot be read..."). `can_bring_back_here` is true
only for a request from this PC.

**`POST /api/devices/remove`** - `{"id": "d3f9a1c2e"}` and nothing else.
Immediate, **no card** (it only takes access away, like Forget). `200
{"ok": true, "id", "name", "was_this_device": bool}`; `404 {"reason":
"no_such_device"}`; `400` for anything else (a list is refused: no "remove
all"); `"pc"` cannot be removed (`400 {"reason": "not_removable"}`). Audit
line `devices.removed` with the id only. Sends a `devices` event (`{}` -
nothing else) so the other app re-reads the list.

**`POST /api/devices/shared`** - `{"retired": true}` or `{"retired": false}`.
- `true` (stricter): **immediate**, no card. **Refused (409, reason
  `uses_it_yourself`) when the request itself used the shared key from
  another device** - "This phone is still using the old shared key. Pair it
  with the QR code first, or it would cut itself off." This is the rule
  that makes "retire" unable to lock the owner out.
- `false` (looser, bringing it back for other devices): **PC only**, one
  card `unretire_shared_key` (tier ask, in `PC_ONLY_ACTIONS`, so Windows
  Hello), `202 {"waiting": true}`; refused with `409` while Lockdown is on,
  like every loosening (JARVIS-API §75.2).

### 6.5 Changes to existing routes

- `GET /api/version`: `capabilities.pairing` (5.5).
- Audit lines and the past-approvals list (the owner's 2026-09-27 answer,
  "which device") can use `self._jarvis_device` (`pc`, `shared`, or an id).
- Nothing else changes. `X-Jarvis-Token` stays the header.

## 7. The owner's side, in both apps

### 7.1 Desktop: Settings, Devices (new section, settings window only)

- **Pair a phone** (a normal button). First time only: one field, "Your
  phone reaches this PC at", pre-filled if the desktop can find the PC's
  Tailscale name (8.1), else typed once; remembered.
- The panel then shows: the QR code; under it "Can't scan? Type this code
  on the phone: **K7QM-4TXD**"; "Works for 9:41 more"; and one status line
  from `GET /api/pair/session`, read every 2 s while open ("Waiting for
  your phone...", "Your phone asked. Check the card - the words must
  match: tulip · anchor · mellow · crane", "Pixel 9 is connected.",
  or the ending's sentence). **Cancel** ends it.
- **While the panel is open, the settings window is hidden from screen
  capture** (`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`,
  Windows 10 2004 and newer; `Win32_UI_WindowsAndMessaging` is already an
  enabled feature in `Cargo.toml`). A screenshot, a screen recording or a
  meeting's screen share shows a black box instead of the code; so does
  Jarvis's own "Look at this". Put back when the panel closes. It is a
  cheap guard against the easiest copy of the code, not a wall (a program
  running as the owner has other ways in; ARCHITECTURE §3).
- Behind App lock like the rest of Settings.
- **The device list**: This PC (no Remove), then each device - name, kind,
  "paired 3 Sep", "last used 2 minutes ago" - each with **Remove**, which
  asks "Remove Pixel 9? It stops reaching Jarvis at once. To use it again,
  pair it again with the QR code." (Cancel / Remove).
- **The old shared key** row: "Old shared key - used by this PC, and by
  devices paired before per-device keys." Then one of:
  - not retired, and used from another device in the last 30 days: "Last
    used from another device (100.101.2.3) 2 hours ago. Pair that device
    first." with **Retire for other devices** still offered, behind a
    confirm naming that address;
  - not retired, unused elsewhere: "No other device has used it since
    <date>." **Retire for other devices**;
  - retired: "Retired on 28 Sep - it now works on this PC only."
    **Bring it back** (card + Windows Hello).
- "Show the token for my phone" (`settings.html:132`) moves under this row
  as "Show the old shared key (not needed with QR pairing)" while it is not
  retired, and is hidden once it is.

### 7.2 Phone: pairing screen, and Settings, Devices

**Pairing screen** (`PairingScreen.kt`), new at the top, shown when the
PC has `capabilities.pairing` or when nothing is paired yet:
- **Scan the code on your PC** (the one filled button). Asks for the
  camera the first time, with one sentence first: "Jarvis uses the camera
  only to read the code on your PC. Nothing is recorded or sent." Refused
  camera: says so, and offers the typed code.
- **Type the code instead**: two fields - "Your PC's Tailscale or Meshnet
  name" (the existing address field and its rule) and "Code (8 letters)".
- The old address + token form moves under "Use the old shared key
  instead", collapsed.
- After a scan: "Connect to **jarvis-pc.tail1234.ts.net**?" with a
  **Name for this phone** field (the model name, editable) and **Connect**.
  This question is always asked, so a code someone else printed cannot
  quietly point the phone at a different PC.
- Then the four words, large, with "Approve the card on your PC if it
  shows these same words." and **Cancel**. Screenshots blocked on this
  screen (the same `FLAG_SECURE` rule as "Show token", `PairingScreen.kt`'s
  `onKeyShownChange`).
- On `200 approved`: the key is saved, the handshake runs with it, and
  **only if the handshake answers** is the old key dropped - the same
  put-back rule as `MainActivity.kt:1383-1476` today. A failed handshake
  keeps the phone on its old key and says so.
- **No link or other app can start pairing**: no intent filter for
  `jarvis-pair:`. The code is only read by the app's own scanner or typed.

**Settings, Devices** (new `DevicesPlate.kt`): the same list, same words,
same Remove confirm. "This phone" tagged. Removing this phone itself says
"This phone will stop reaching Jarvis at once and go back to the pairing
screen." **Retire for other devices** is offered only when this phone uses
its own key (the backend refuses it otherwise anyway, 6.4). **Bring it
back** is not offered on the phone - one-sided on purpose (section 12).

## 8. The pieces each app needs

### 8.1 The address in the QR code

The backend cannot reliably know the PC's Tailscale or Meshnet **name**
(it listens on a number, `validate_bind_address`, `commands.rs:760`), and
the phone can only use a name (ARCHITECTURE §2, line 92 onward). So the
desktop supplies it:
1. pre-filled from `tailscale status --json` (its `Self.DNSName`, trailing
   dot removed) **if** the Tailscale command answers within 2 s - a local
   read-only command, nothing sent anywhere. **Unverified on Windows**: the
   half-hour test (section 10) checks the command's name and output there.
   Meshnet has no equivalent checked here, so a Meshnet owner types it once;
2. otherwise typed once by the owner, checked by the shared rule, and
   remembered.

### 8.2 Drawing the QR code on the PC

**Recommended: the `qrcodegen` crate** (Project Nayuki's QR Code generator,
MIT licence, no dependencies of its own), in Rust. `pair_start` gets the
`qr` text from the backend, makes the picture as an SVG in Rust, and sends
only the SVG to the page (allowed by the page policy's `img-src data:`,
`tauri.conf.json:67`); the text itself never reaches the page's scripts.
Error correction level M; the text is about 110 characters, so a version 6
or 7 code - easy for any phone camera at arm's length. Credit it in
`THIRD-PARTY-NOTICES.txt` (`npm run notices` / `tools/gen_notices.py`).
Alternatives, not chosen: the `qrcode` crate (MIT/Apache-2.0; its default
features pull image code, fine but larger); a JavaScript QR library copied
into `src/` (also possible - but then the secret text sits in the page).
**Version and licence to be confirmed on crates.io when it is added** - not
checkable from here.

### 8.3 Reading the QR code on the phone

**Recommended: CameraX + ZXing's core library.**
- CameraX (`androidx.camera:camera-camera2`, `-lifecycle`, `-view`;
  Apache-2.0): the standard AndroidX camera library. It talks to the
  phone's own camera; it does not need Google Play Services, so it fits
  the GrapheneOS plan (`docs/GRAPHENEOS.md`).
- ZXing core (`com.google.zxing:core`, Apache-2.0): plain Java, bundled in
  the app, decodes QR codes from CameraX's `ImageAnalysis` frames. Nothing
  online.
- Only QR codes are looked for (`DecodeHintType.POSSIBLE_FORMATS` = QR
  only), and a code is accepted only if it matches the payload rule exactly
  (8.4).
- Manifest: `CAMERA` permission, plus
  `<uses-feature android:name="android.hardware.camera" android:required="false"/>`
  so a phone without a camera can still install it (and type the code).
- R8 (the tool that shrinks the app): ZXing core needs no keep rules that
  are known here; **check the release build scans**, since the emulator
  smoke job is the first place it runs.
- Size: CameraX adds a few MB; ZXing core about 0.5 MB. Jarvis Live's camera
  (`docs/LIVE-DESIGN.md`) will want CameraX later anyway.

Not chosen, and why:
- **ML Kit barcode scanning**: its code is not open, it comes under
  Google's own ML Kit terms, and it is Google's library in an app that has
  avoided every Google service so far (`docs/GRAPHENEOS.md`, "no Firebase or
  Google Play Services dependency of any kind"). Whether its bundled version
  sends usage data was not checked here; not needing to find out is part of
  the reason.
- **Google code scanner**: needs Google Play Services.
- **zxing-android-embedded** (Apache-2.0): wraps Android's old camera API
  and is no longer actively developed.

### 8.4 The QR text

```
jarvis-pair:1/<host>/<port>/<pair_id>/<secret>/<expires>
```

| field | rule |
|---|---|
| `1` | the format version; anything else: "This code is from a newer Jarvis - update the app." |
| `host` | lower case, `[a-z0-9.-]`, 1-253 characters, ending `.ts.net` or `.nord`, and passing the phone's own-networks rule |
| `port` | 1-65535, digits only, no leading zero |
| `pair_id` | 16 lowercase hex characters |
| `secret` | 22 characters of `A-Z a-z 0-9 - _` (16 bytes, base64url, no padding) |
| `expires` | seconds since 1970, 10 digits. Shown as a countdown only; the PC decides (clocks may differ). |

Exactly six `/`-separated parts after `jarvis-pair:`; nothing before or
after; no spaces. Anything else is "That is not a Jarvis pairing code."
The strict shape is on purpose: one parser, the same cases in Python,
Kotlin and Rust, no URL library guessing at an odd string.

### 8.5 The typed code

- 8 characters from Crockford's alphabet (`0-9` and `A-Z` without `I L O
  U`), shown as `K7QM-4TXD`. 40 bits.
- The phone normalises before use: upper case; spaces and `-` removed; `O`
  becomes `0`; `I` and `L` become `1`. Then exactly 8 characters from the
  alphabet, else "The code is 8 letters and numbers, like K7QM-4TXD."
- **3 wrong tries, from anywhere, burn the session** (QR and code alike).
  With 40 bits and 3 tries, guessing is hopeless (3 in about a trillion).
- **Only over the mesh**: `claim` and `collect` are refused from anything
  but a Tailscale/Meshnet address (6.2). The phone already only uses
  `.ts.net`/`.nord` names. So the short code never travels over plain home
  Wi-Fi.
- The honest limit: someone who could **record** the scrambled traffic and
  also break the mesh's encryption could try all codes offline. Inside
  Tailscale or Meshnet that is not a realistic worry, and the session is
  used up within seconds anyway. A PAKE (a way to make a short code safe
  even from a listener: SPAKE2, RFC 9382) is the upgrade if Jarvis ever
  allows pairing outside the mesh. Not needed now.

### 8.6 Scrubbers

The new key shape (5.1) is added to: `backend/jarvis_scrub.py`'s patterns,
the phone's `platform/CrashLog.kt` (today it catches the header form only,
`CrashLog.kt:30-32`), and the desktop's log file scrubber. Each gets a test
case from the shared file.

## 9. Key attestation: recommended to defer

Key attestation lets the PC check that a key really lives in a phone's
security chip, for the real Jarvis app. **Recommendation: not in phase 1,
and in phase 2 only if it is built "record, do not refuse".** Reasons,
weighed plainly:

- **It stops little here.** The attack it answers - a program that copied
  the QR code pairing from another device - already meets the mesh (the
  other device must be one of the owner's own), the PC-only card, Windows
  Hello, and the four words. And the Jarvis APK is public on the
  `client-latest` release, so an attacker with their own Android phone
  passes attestation with the real app anyway.
- **It is the part most likely to lock the owner out.** A GrapheneOS phone
  (the owner may switch, `docs/GRAPHENEOS.md`) reports its boot state as
  "self-signed", not "verified", so a strict check refuses it unless it
  knows GrapheneOS's key. Google moved to a new attestation root in 2026
  (a summary, per the trust research), so a check must carry both roots.
  Checking whether a leaked key has been revoked needs Google's online list,
  which is a new way out of the PC; offline, a leaked factory key cannot be
  spotted.
- **It is real code to get right**: parsing the attestation record (an
  ASN.1 structure) in Python needs a new package or hand parsing, on the
  one path that decides who gets a key.
- Phase 2 makes a new phone key anyway (11.1). If attestation is wanted
  later, that is where to collect it - stored with the device, shown in the
  list ("security chip: checked / not checked"), never a reason to refuse.

## 10. Tests, and the half-hour test on the PC

**Shared cases**: `tools/gen_pairing_cases.py` (backend agent, first thing)
writes one file from the backend's own code, read by all three:
`jarvis-client/app/src/test/resources/contract/pairing-cases.json` and
`jarvis-desktop/tests/fixtures/pairing-cases.json`. It holds: QR text cases
(valid and invalid, from 8.4), code normalisation cases, name-rule cases,
the proof/`pc_proof`/word-number/collect vectors (6.2), the key shape and
scrubber cases, and every sentence the apps show. `backend/
test_pairing_cases.py` fails when the file is stale (like
`test_own_network_cases.py`).

**Backend** - `backend/test_devices.py` (new):
- The key: shape, randomness length, only its hash is written (the file
  and every audit line searched for the key text).
- `wrap_token_ok`: a device key works; a removed or unknown one is refused
  and never falls back to the shared check; the shared key works before
  Retire; after Retire it is refused from a mesh address and still works
  from loopback and from the PC's own address; an unreadable registry
  refuses device keys and treats shared as retired - except from this PC;
  the 401 gets its `key` reason; `last_seen` is written at most once a
  minute.
- The stream guard: a write after Remove raises `BrokenPipeError`.
- Ordering: on the stacked `jarvis_hud.py`, the devices hunk comes before
  every `token_ok=_token_ok`.
- Pairing: `start` is PC only; its address rule uses the shared cases;
  `qr` round-trips through the parser; `session` never contains the code or
  secret; `claim` from a non-mesh address, and from this PC, is refused; 3
  wrong proofs burn it (and a 4th right one is refused); `expires` is
  enforced with a fake clock; a valid claim raises exactly one `pair_device`
  card with the name and words in its text; wrong tier -> refused; denied,
  timed out, cancelled while waiting -> no key made; approved -> `collect`
  gives the key once, a second `collect` is `410`; a new `start` withdraws
  the old card.
- Remove, Retire (including the `uses_it_yourself` refusal), Bring back
  (card, PC only, 409 under Lockdown).
- `devices/registry.json` is **not** in a backup (runs `jarvis_backup`'s
  own collection on a temp folder).
- Tables that must know the new actions: `test_card_words.py`,
  `test_asks_first.py`, `test_gate_risk_words.py`, `test_reach.py` (a "What
  asks first" row for `pair_device`), `test_owner_check.py`
  (`PC_ONLY_ACTIONS`), `test_patch_history.py` - re-running
  `tools/gen_card_words_cases.py`, `gen_asks_first_cases.py`,
  `gen_reach_cases.py`, `build_patch_history.py` as each requires.
- `tools/check_parity.py`: the new routes classified - `/api/devices`,
  `/api/devices/remove`, `/api/devices/shared` `ported`; `/api/pair/start`,
  `/session`, `/cancel` desktop-only; `/api/pair/claim`, `/collect`
  phone-only - each with its reason.

**Desktop**:
- Rust unit tests (compiled by `cargo check/clippy --target
  x86_64-pc-windows-msvc --all-targets`, run on Windows CI): the SVG is
  made, is well-formed, and holds a code of version 10 or less for the
  longest valid text; the settings-store field for the address; the command
  list in `permissions/surfaces.toml` (settings window only).
- `tests/devices.mjs` (new, Playwright): the list, Remove's confirm, the
  shared-key row's three states and its warning, the pairing panel's
  states from a fake `pair_session`, words shown as given. **Note:**
  Playwright's browser download is blocked in this container (CLAUDE.md,
  third-card entry), so these run in CI only.
- `tests/pairing-cases.mjs` (plain node): the page's copy of any rule
  (the code's display grouping) against the shared file.

**Phone** (unit tests under `src/test`, confirmed only once CI compiles
them - no local Android build, CLAUDE.md):
- `PairPayloadTest.kt` (QR text rule), `PairCodeTest.kt` (normalising),
  `PairNameTest.kt`, `PairProofTest.kt` (the vectors - `javax.crypto.Mac`,
  no new library), `DevicesTest.kt` (parsing `/api/devices`, the `key`
  reason sentences), `PairFlowTest.kt` (the state machine against a fake
  API: words mismatch refuses; a failed handshake keeps the old key; a
  `403 denied` changes nothing).
- An instrumented test with the existing `mockwebserver` dependency
  (`build.gradle.kts:381`) for claim/collect over real OkHttp.
- The emulator smoke job: the scan screen opens without a crash (the
  emulator's fake camera is enough for that).

**The half-hour test on the owner's PC** (before switching Retire on for
real; each step fails safe if wrong):
1. `tailscale status --json` exists on Windows and gives `Self.DNSName`.
2. A removed phone's event stream really stops within ~10 s (5.4).
3. The pairing card's Windows Hello prompt comes to the front (the same
   question owner-check's own half-day test asks).
4. A phone connecting through Tailscale arrives from its 100.x address
   (so "mesh only" lets it in and "from this PC" does not).

## 11. Phase 2: a fingerprint-signed yes from the phone

Built after phase 1 ships. It closes the last open row of the approval-gap
table: "Someone who stole the token uses it from another device on your
Tailscale network - still works" (`docs/APPROVAL-GAP-DESIGN.md` §3).

### 11.1 The approval key

- Made on the phone, in the Android Keystore: EC P-256, purpose SIGN,
  `setUserAuthenticationParameters(0, AUTH_BIOMETRIC_STRONG or
  AUTH_DEVICE_CREDENTIAL)` - **a fresh fingerprint or PIN for every single
  use** - and `setIsStrongBoxBacked(true)` when the phone has StrongBox,
  else the normal secure area. Invalidated by Android when a new
  fingerprint is added or the screen lock removed - then it must be
  registered again.
- Android makes such a key only when the phone has a screen lock - which
  matches "no lock, no risky approval" (`SecurityRules.afterApprovalCheck`,
  `data/Security.kt:178`).
- Face unlock on many phones is "Class 2" and cannot unlock it; the PIN
  always can. `BiometricGate`'s current allowed methods already exclude
  weak biometrics (`BiometricGate.kt`, `allowed()`).
- **"Fingerprint only"** (the phone's stricter setting) is kept by asking
  the prompt for `BIOMETRIC_STRONG` alone; the key itself allows both, so
  changing the setting needs no new key.

### 11.2 Registering it (a card, PC only)

**`POST /api/devices/approval-key`** (device key required) - `{"public_key":
"<SPKI DER, base64url>"}`. Raises card `register_approval_key` (tier ask,
in `PC_ONLY_ACTIONS`: Windows Hello, PC only): "Let Pixel 9 approve risky
actions with its fingerprint or PIN?" `202 {"waiting": true}`; the state is
read back as `approval_key: "waiting" | true | false` in `GET
/api/devices`. The key is stored in the device's row. Needs
`cryptography` on the PC; without it `503` ("risky approvals from the phone
need the cryptography package on your PC").

### 11.3 Signing one approval

1. The phone asks **`POST /api/approve/challenge`** `{"id": "<card id>"}` ->
   `200 {"nonce": "<22 characters>", "words_sha256": "<hex>",
   "expires_in"}`. The nonce is made fresh, kept in the backend's memory
   only, tied to that card and that device, and used at most once.
2. The phone works out `words_sha256` itself from what it **showed**:
   SHA-256 of `id \x1f action \x1f title \x1f text`, where `title` is the
   card title it displayed (`notice.title` or the shared fallback) and
   `text` is `detail.text` (or `detail` when it is plain text, or `""`).
   If it differs from the PC's, it refuses: "The card changed on your PC.
   Look at it again." The canonical rule is a shared cases file made from
   `contract/pending-rows.json`.
3. The phone shows the fingerprint prompt **with a `CryptoObject(Signature)`**
   (replacing the plain `prompt.authenticate(...)` at `BiometricGate.kt:189`),
   and signs `"jarvis-approve-v1" \0 id \0 action \0 nonce \0 words_sha256`
   (ECDSA, SHA-256).
4. `POST /api/approve` gains `"signature": {"device": "d3f9a1c2e",
   "nonce", "sig": "<DER, base64url>"}`.

### 11.4 What the backend then requires

In `jarvis_owner_check.approve_check`, for a **risky** card (the same one
rule, `is_risky`) approved **not from this PC**:
- a request made with a device key that has an approval key: needs a valid
  signature from that key over that card, nonce unused and unexpired; else
  `403 {"owner_check": "no_signature" | "bad_signature"}`;
- a request made with the **shared** key from another device: refused once
  the shared key is retired (phase 1 already does that); **while it is not
  retired, allowed as today** - so installing phase 2 never stops an
  unpaired phone from working. The Devices page says "Risky approvals from
  <phone> are not yet signed - pair it and turn on signed approvals."
- a device with a key but **no approval key yet**: its risky approvals are
  refused with "Turn on signed approvals for this phone first" and a button
  that starts 11.2. This is a real change for the owner, so it is
  switched on together with the owner's go-ahead at phase 2's start, not
  silently.
- Cards that are not risky, Deny, and approvals from this PC: unchanged.

Tests: `test_owner_check.py` gains signature cases (valid, wrong card,
reused nonce, changed words, removed device, shared key before/after
retire); phone `ApprovalSignTest.kt` for the words hash; a Keystore
instrumented test for key creation parameters.

## 12. Fit with what exists (the standing audit, done in advance)

- **One permission model**: two new gate actions (`pair_device`,
  `unretire_shared_key`; phase 2 `register_approval_key`), ordinary cards,
  ordinary `/api/approve`. No second approval path. Nothing auto-approved.
- **Stricter at once, looser with a card** - the settings pattern used
  everywhere: Remove and Retire are immediate; pairing and Bring back are
  cards with Windows Hello.
- **Rule 1**: nothing leaves the owner's devices. Rule 2: pairing refused
  outside the mesh. Rule 3: keys never logged, hashed on the PC,
  Keystore-encrypted on the phone. Rule 4: nothing auto-approved; the
  phone's pairing screen needs no live event stream (it has none yet), but
  Remove and Retire are not held on a stale link either, because they only
  take access away. Rule 5: unaffected.
- **Lockdown**: pairing is not a way out of the PC, so Lockdown does not
  stop it; Bring back is a loosening, refused under Lockdown.
- **Backups**: the registry is kept out of backups by where it lives (4).
- **One-sided on purpose** (rows for ARCHITECTURE §8): starting a pairing,
  the QR code and Bring back are on the PC only (the code and the card live
  there; Bring back is a loosening done with Windows Hello); scanning and
  typing the code are on the phone only (the desktop is on the PC and
  needs no pairing).
- **Docs to update when built**: `JARVIS-API.md` §1 (the key may be a
  device key; `X-Jarvis-Client` is still not identity, but the key now is)
  and a new section (§90) with section 6 of this document;
  `ARCHITECTURE.md` §2 (pairing only over the mesh), §3 (the known limit:
  what per-device keys close and what they do not), §8 (the rows above);
  `backend/README.md` (the patch); `docs/INSTALL.md` (pairing by QR code
  replaces typing the key); `THIRD-PARTY-NOTICES.txt` (qrcodegen, ZXing,
  CameraX, the EFF word list).

## 13. Build order: three builders against the frozen API

Section 6 is the contract. Each builder may start at once; only the shared
cases file is a hand-off, and the vectors in 6.2 let the other two write
their tests before it lands.

**Backend (M)** - `backend/jarvis_devices.py` (whole module, standard
library only in phase 1), `backend/devices.patch` (the one hunk in 5.2, plus
the gate lines for the two actions), `jarvis_owner_check.py`
(`PC_ONLY_ACTIONS`), `jarvis_card_words.py` titles, `jarvis_reach.py` row,
`jarvis_scrub.py` pattern, `tools/gen_pairing_cases.py` (first),
`test_devices.py`, `test_pairing_cases.py`, `tools/check_parity.py`
classifications, `apply-patches.ps1` list entry (last in the list).

**Desktop (M)** - `src-tauri/src/devices.rs` (commands `pair_start`,
`pair_session`, `pair_cancel`, `devices_list`, `devices_remove`,
`devices_shared`; `qrcodegen` for the SVG; the capture exclusion; the
Tailscale name lookup), `permissions/surfaces.toml` (settings window only),
`src/settings.html` / `settings.js` / a new `devices.js` (the section),
the "Show the old shared key" move, `tests/devices.mjs`,
`tests/pairing-cases.mjs`, Rust tests, notices.

**Phone (L)** - `net/Pairing.kt` (payload parse, code normalising, proofs,
words, `claim`/`collect` calls), `data/PairWords.kt` + `assets/
pair-words.txt`, `ui/screens/QrScanScreen.kt` (CameraX + ZXing),
`PairingScreen.kt` (the new top half; old form collapsed),
`MainActivity.kt` (the swap-after-handshake, reusing the put-back),
`ui/screens/DevicesPlate.kt`, `net/JarvisApi.kt` (`/api/devices` calls; the
401 `key` reason), `platform/CrashLog.kt` pattern, manifest (`CAMERA`,
`uses-feature`), `build.gradle.kts` (CameraX, ZXing core), notices, the
tests in section 10.

**Then, together**: the feature audit CLAUDE.md requires (bugs, both apps,
fit), the half-hour test on the PC, and the docs in section 12. Phase 2
follows as its own piece of work.

## 14. Risks, said plainly

- **`_token_ok` has never been read here.** The wrapping in 5.2 is
  designed not to need its body, but the patch's placement must be checked
  on the stacked file, and the first real start on the PC is the real test.
  If the wrap fails, the fallback is today's behaviour, not a lock-out.
- **A program already on the PC** can still read this PC's key, start a
  pairing, and edit `registry.json` to add a key of its own. It cannot pass
  the card's Windows Hello, and adding a key only gives it what it already
  had (it is already on the PC). ARCHITECTURE §3's limit stands.
- **A device on the owner's mesh can burn a pairing session** with 3 wrong
  tries. Nuisance only; the desktop shows where they came from.
- **Anyone with a paired device's key can remove other devices.** Nuisance
  only (re-pairing fixes it); a key thief has bigger powers anyway until
  phase 2.
- **The PC with no Windows Hello cannot pair by QR** (the owner's own rule).
  The shared key keeps working there.
- **Untested pieces**: `tailscale status` on Windows, the stream guard on
  the real server, the phone's scanner on a real camera, the capture
  exclusion. Each is in the half-hour test or CI, and each fails safe.

## 15. Questions for the owner

One only - everything else here follows from decisions already made.

**After phase 2, a paired phone without signed approvals switched on cannot
approve risky cards.** Turning signed approvals on is one card on the PC,
once per phone.

- **Ask on the phone the first time it tries a risky approval** - one
  button, "Turn on signed approvals" (recommended)
- **Turn it on as part of pairing**, so the pairing card also covers it
  (one card fewer, but that card then means two things)
