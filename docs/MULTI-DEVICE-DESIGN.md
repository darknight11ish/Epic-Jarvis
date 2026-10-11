# Multi-device: one PC as the host, several devices on the mesh

**What the owner asked for (his own words, 2026-10-09):** *"one computer with
a capable setup (one or more gpus) is the main jarvis host, and i can connect
multiple devices (whether that is multiple phones, or a laptop or other
computers) to it? and in the settings I can label each device, change specific
settings, and remove or add more devices? They would all have to be on the
meshnet of course or tailscale."*

This note says what he already has, what each missing piece costs, and the
questions only he can answer. It is checked against the code, file by file.

---

## 1. The inventory: what exists today

Read from the owner's live backend
(`...\Claude\Open jarvis files\Desktop program\jarvis_devices.py`, 2,394 lines
before this work, byte-for-byte the same as `backend/jarvis_devices.py`), the
desktop (`jarvis-desktop/src/devices.js`, `src-tauri/src/devices.rs`) and the
phone (`jarvis-client/.../net/Devices.kt`, `ui/screens/DevicesPlate.kt`).

### Several devices paired at once, each with its own key — **EXISTS**

* `jarvis_devices.py:27` — the registry is `<settings folder>/devices/registry.json`,
  a list of rows, one per device. A sentence in the module's own docstring
  says it plainly: *"a key per device, listed in both apps with its own
  Remove"* (`jarvis_devices.py:17`).
* `jarvis_devices.py:1649` `_mint()` — a new row per pairing, with its own
  `jdk1.<id>.<secret>` key. **Only the key's SHA-256 is written** (`:1661`).
* `jarvis_devices.py:968` `check_device_key()` — a device key is checked
  against the registry and **never** falls through to the old shared key
  (`:1143` `wrap_token_ok`).
* `test_devices.py` pairs two devices in one test (`t_the_device_list`) and
  proves each key works independently.
* The **old shared key** is a bootstrap, not a fallback: it works from another
  device only until the first device holds a key of its own
  (`jarvis_devices.py:949` `_first_pairing`).

**So: the owner's "connect multiple devices" half is built.** What is not
built is the third device's *experience* — see the questions in §4.

### Removing a device — **EXISTS**

* `jarvis_devices.py:1783` `remove()`, route `POST /api/devices/remove`.
  **Immediate, no card, one device** — it only takes access away.
* A removed device's open event stream is cut within one keepalive, by
  `_StreamGuard` (`jarvis_devices.py:1067`).
* Its signing key goes too (`:1802`), and — added by this work — so does its
  label (`:1822`).
* The Devices card is on both apps and is **never hideable**: desktop
  `settings.html` `<section class="card" id="devices">` (no `hidden`
  attribute, and `settings.js` has no way to hide a card); phone
  `SettingsScreen`'s own `item(key = "devices")`.

### Labelling a device — **MISSING** (this work builds it)

* **What a device calls itself today is its phone model.** At pairing the
  phone sends `name` (`jarvis_devices.py:1555` `claim`), the phone builds it
  from `Build.MODEL`-style text (`jarvis-client/.../net/Pairing.kt:259`
  `suggestedName(model)`, "Pixel 9", falling back to "My phone"), and the PC
  stores it as the row's `name` (`:1660`).
* **That name cannot be rewritten.** It is part of the pairing transcript and
  therefore part of the HMAC sums (`jarvis_devices.py:602` `transcript`), so
  changing it after the fact would break the proof the card was approved
  against.
* Until this work, **no route, no command and no button anywhere renamed a
  device** — `grep` for `rename|label` across `backend/`, `jarvis-desktop/`
  and `jarvis-client/` found nothing for devices (the matches are topics,
  tags, decks, chats, voices).

### Per-device settings — **PARTLY EXISTS, two of them**

* `CLAUDE.md` (2026-09-28): *"sharpness and frame rate stay per device"*;
  every other look-and-behaviour option is shared between the PC and the
  phone, "one request changes both".
* `jarvis_animal.py:194` — the `DEVICE_TITLE = "Sharpness and frame rate"`
  block says why: *"Each device keeps its own: what one graphics chip can draw
  says nothing about another's."* The value is stored on the device itself
  (`jarvis_animal.step_device`), and `jarvis_settings_registry.py:94` records
  that asking the PC to change them "changes nothing" because they are
  per-device.
* Nothing else is per-device: `settings_view` returns one shared picture of
  every setting, and the PC's own Settings page has no "for this device"
  concept outside the animal tuning.

### A non-phone client (a laptop or another PC) — **MISSING, and it is a new client**

Said plainly, because this is the largest item in the request:

* **The backend would accept one.** A device key is a key: `/api/devices`,
  chat, approvals and every other route are keyed on the header, with no
  notion of "phone" anywhere in `jarvis_devices.py`. `kind` is stored per row
  (`:1660`, `"phone"`) and shown as a word, and would need to become real
  (`"laptop"`, `"pc"`).
* **Nothing else would.** There is no desktop-as-client mode: the desktop app
  *is* the host — it starts the backend, holds the shared key, answers
  Windows Hello, and reads the backend at `127.0.0.1`. Letting a second PC in
  means a second copy of `jarvis-desktop` running in a client mode that does
  not exist: a pairing screen (the phone's UI, in Rust/JS), a stored device
  key in the Windows credential store, a "connect to another PC" address
  field, and a rule for what a client may do (it cannot approve risky cards —
  there is no Windows Hello on *that* machine for *this* host).
* **Also on the mesh.** The address rule already exists and is reusable:
  `jarvis_devices.PHONE_SUFFIXES` (`.ts.net`, `.nord`) plus
  `jarvis_local_http._own_network`, and `jarvis-client/.../PhoneAddress.kt`
  refuses anything else with the same sentence.
* **Honest estimate:** this is a project of its own, not a settings change.
  The pieces that exist (per-device keys, the registry, the list, Remove, the
  address rule) are about a third of it.

### The phone half of the risky-approval chip — **PARTLY EXISTS (backend done, phone missing)**

`CLAUDE.md`, 2026-09-25: *"the phone half (a Keystore key that needs a fresh
fingerprint per risky approval) comes with 'more devices'"*. That work
landed early in the backend:

* `jarvis_devices.py:2108` `register_key()` — `POST /api/devices/approval-key`,
  a device-sends-its-public-key route, ONE `register_approval_key` card on the
  PC with Windows Hello, and a **swap** card if the device already had a key
  (`KEY_REPLACE_CARD_TEXT`, `:328`).
* `:2173` `challenge()` — `POST /api/approve/challenge`, a 120-second,
  single-use nonce per card per device.
* `:2213` `check_signed_approval()` — what `jarvis_owner_check.approve_check`
  asks before accepting a risky card from a device. It signs the card id, the
  action, the nonce and a SHA-256 of the words the phone *showed*.
* `docs/JARVIS-API.md` §91; `docs/PAIRING-DESIGN.md` §11.

**What is missing is the phone side being finished and trusted**: the key
lives in the phone's Keystore (`SignedApproval`, `JarvisRuntime.approvalKeyLocal`),
and the app can turn it on and off, but the last mile — a fresh fingerprint
per risky approval, and the four words matched against the card — is the part
that has never been proved on a real phone. Nothing about this work changes
that; it is written down here so the two are not confused.

---

## 2. The safety shape (not negotiable, and already the code's shape)

These are not new rules; they are what the code already does, written down so
no future piece of this feature can quietly break one.

1. **Every device has its own key.** `jdk1.<id>.<secret>`, minted per pairing,
   stored as a SHA-256, checked before anything else
   (`jarvis_devices.py:968`, `:1143`).
2. **A new device is approved ON THE PC, WITH WINDOWS HELLO.** `pair_device`
   is in `jarvis_owner_check.PC_ONLY_ACTIONS` (with `unretire_shared_key` and
   `register_approval_key`), and the card can only be approved at tier `ask`
   (`_verdict`, `:1321`).
3. **A device can never approve another device.** No device key can raise,
   answer or approve a `pair_device` card: `start`/`session_view`/`cancel` are
   `403 pc_only` from anywhere but the PC (`:1412`, `:1446`, `:1460`), and the
   card itself is a person's yes on the PC. The new label route cannot raise
   any card at all.
4. **The phone connects ONLY over Tailscale or NordVPN Meshnet.** `claim` and
   `collect` refuse anything that is not a mesh peer (`mesh_peer`, `:775`;
   `_mesh_refusal`, `:1520`), and the address in the QR code must end
   `.ts.net` or `.nord` (`phone_host`, `:662`). Never plain home Wi-Fi — the
   owner replaced that choice on 2026-09-28 for exactly this reason.
5. **Removing a device revokes its key immediately, and says so.** It is
   card-free *because* it narrows: the row's hash is emptied, its signing key
   dropped, its open streams cut, and the answer — "… was removed. It can no
   longer reach Jarvis." — names the device by the name the owner was looking
   at.
6. **Never log the token or any device key.** `jarvis_scrub` knows the key's
   shape (`jdk1.d<8 hex>.<43>`); `_hide()` registers each secret; audit lines
   carry ids and states only (`:546` `_audit`). This work's own audit line
   carries an id and whether a label was cleared — **never the label**.
7. **A label grants and revokes nothing.** It changes what a device is
   *called*, never what it *may do*: it cannot approve, cannot pair, cannot
   loosen. That is why it needs no card, and why it is refused, never
   cleaned, when it breaks the name rule (a label appears on the device list
   in both apps and inside a pairing card, so it must not be able to fake a
   card's words).

---

## 3. What was built as the first slice (2026-10-09)

**Labelling a device.** The smallest genuinely useful step: it is the one part
of the request that is entirely missing, it is visible on both apps, and it
changes nothing about who may do what.

* **The PC**: `POST /api/devices/label {"id", "label"}` in
  `backend/jarvis_devices.py`. A `label` field beside the key's hash in the
  same registry row — **absent means no label**, so every row written before
  this reads exactly as before. `row_shown()` is the one rule for what to
  show: the label, else the name the phone sent, else the id. `devices_view`
  now sends `label`, `name` and `shown` per row. Removing a device drops its
  label with the key. The label's own audit line is `{"id", "cleared"}` only.
* **The desktop**: `devices_label` in `src-tauri/src/devices.rs`, wired the
  whole way (`build.rs`, `permissions/surfaces.toml`,
  `permissions/autogenerated/devices_label.toml`, `lib.rs`), and a **Name this
  device...** button on each device's row in Settings → Devices. The box
  starts at the name the device has now, Cancel sends nothing, an unchanged
  name sends nothing, and an empty box clears the label.
* **The phone**: the same button and box on Settings → Devices, the label
  shown wherever the name was, and "The phone calls itself Pixel 9." under it
  when the two differ — so the owner can always see what clearing the label
  goes back to.
* **Shared words**: the three sentences live in `DEVICES_WORDS`
  (`jarvis_devices.py`), are exported into
  `contract/pairing-cases.json` for both apps by `tools/gen_pairing_cases.py`,
  and `backend/test_devices.py` checks each app's own copy word for word.

**What this deliberately does NOT do:** no per-device settings beyond
sharpness and frame rate (that is a question for the owner, §4); no non-phone
client; no change to pairing, to the mesh rule, or to `PC_ONLY_ACTIONS`.

---

## 4. The questions only the owner can answer

Asked as multiple choice, short, with the recommendation first.

**Q1. How does a device get its name?**

Today the phone sends its own model at pairing ("Pixel 9", or "My phone"),
and that name is part of the pairing sums, so it can never be rewritten — a
label is a second name kept beside it.

* **A suggested name, which he can change** (recommended — what is built: the
  phone sends "Pixel 9", the owner types "Garden phone" in Settings, Devices)
* **Always typed by the owner** (one more thing to type at pairing, and a
  phone paired in a hurry has no name until he is at the PC)
* **The model only, never named** (nothing to label; two identical phones
  read as "Pixel 9" and "Pixel 9")

**Q2. Can a NEW device ever be approved from another device, or only on the PC?**

* **Only on the PC, with Windows Hello** (recommended — what is built, and in
  `PC_ONLY_ACTIONS`)
* **Also from a device that already has a signed-approvals key** (handier when
  he is not at the PC; it weakens the rule that a device can never approve a
  device, and it needs the phone half of §1 finished first)

**Q3. What per-device settings should exist, beyond sharpness and frame rate?**

* **Nothing else yet** (recommended: these two are the only ones with a real
  reason — what one graphics chip can draw says nothing about another's)
* **Also: which notifications this device gets, and whether it is read aloud
  there** (a second device would otherwise get the same alerts as the phone in
  his pocket)
* **Also: a "quiet this device" switch** (silences alerts on one device
  without touching the others)

**Q4. How many devices is "enough"?**

`NONCES_PER_DEVICE = 6` and one pairing at a time are the only limits today;
the list has no cap.

* **No cap, as today** (recommended — each device is a row and a hash; a
  person does not pair a hundred devices by accident)
* **A cap with a plain message** (say 10: past that, the PC says to remove one
  first, so a runaway script cannot fill the registry)
* **A cap that warns but does not refuse** (the list says "that is a lot of
  devices" and carries on)

**Q5. What happens to a label when the same physical phone re-pairs?**

Today: removing the device drops its label with its key, and pairing again
mints a **new id**, so the label is gone and the phone is back to "Pixel 9"
(and the phone's key is different — a re-pair is a new device as far as the
PC is concerned).

* **A fresh start, exactly as today** (recommended — a label belongs to a key,
  and there is no way to tell "the same phone" from "a phone that copied its
  model name")
* **Remember the last label for a model name** ("Pixel 9" was "Garden phone",
  so offer it back at pairing) — convenient, but a *different* Pixel 9 would
  then be offered a name that was never its own
* **Ask on the PC during pairing** (the pairing card already waits for a yes;
  a second line could ask for a name there too)

---

## 5. What this costs, and in what order

| Piece | Size | Notes |
|---|---|---|
| Labelling a device | **built** | backend + both apps + tests |
| Per-device settings (one more) | small | one registry entry, both screens; the shape is already there for sharpness/frame rate |
| The phone half of signed approvals | medium, phone-only | backend is done (§1); it needs a real phone and a fingerprint to prove |
| A laptop/other-PC client | **large** | a client mode in the desktop app, a second credential store, its own pairing screen |
| A device cap or a device name list | small | a rule in `jarvis_devices.py` plus words in both apps |

Suggested order: answer Q1–Q5 → per-device settings (Q3) → the phone half of
signed approvals → anything else. The non-phone client should wait for the
owner's answer to Q2, because a client that cannot approve risky cards is a
different thing from one that can.
