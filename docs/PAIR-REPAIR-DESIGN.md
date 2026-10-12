# Pairing a phone again, after a reinstall (design)

> Written 2026-10-11, after the owner asked for it in their own words: after a
> reinstall, or on a phone that was paired before, **only the PC-side approval
> should be needed - no code, no scanning**.
>
> **This is a design, not a built thing.** It is the dangerous half of the
> day's work: a re-installed app has lost the key in the phone's Keystore, so
> "this is the phone I know" can no longer rest on a device secret. What it
> would rest on instead is weaker, and a loosening is the owner's decision,
> not a quiet build. Nothing here is built until they answer section 4.
>
> The other half of the same request - the PC finding its own mesh name so the
> typed address almost never appears - is built: `pair_phone_address` in
> `jarvis-desktop/src-tauri/src/devices.rs`.

## The short answer

- **Today, a phone is known because it holds a key only this PC gave it**
  (`jdk1.<id>.<secret>`, docs/PAIRING-DESIGN.md section 5.1), handed over
  after ONE card on the PC, approved with Windows Hello.
- **A re-installed app has none of that.** Android's Keystore does not survive
  a reinstall, and it is deliberately not backed up: the key it wrapped is
  gone. The approval-signing key is gone with it. So the phone really is a
  stranger again, and saying "it is the same phone" would be a claim, not a
  proof.
- **The recommended way** (section 3, option 1) keeps a human in the loop: the
  PC remembers that *a* device was paired before, offers ONE card naming it,
  and the owner approves with Windows Hello. No code, no scanning - and the
  card says plainly that Jarvis cannot prove the caller is that phone.
- **What must never happen**, whichever option is chosen, is section 3:
  nothing gets a key without a person approving it, and nothing about risky
  approvals or the old shared key changes.

## 1. What proves a device is known today

| Thing | Where it lives | What it proves |
|---|---|---|
| The device key `jdk1.<id>.<secret>` | The phone (Keystore-wrapped), never in the clear; the PC keeps only a SHA-256 fingerprint | Every request: `X-Jarvis-Token` carries it, and `jarvis_devices.wrap_token_ok` matches the fingerprint. The old shared key is a first-pairing bootstrap only (docs/PAIRING-DESIGN.md section "The short answer", narrowed 2026-10-05). |
| The approval-signing key | The phone's Keystore; its PUBLIC half is registered on the PC by ONE card plus Windows Hello (`/api/devices/approval-key`) | A risky approval from the phone: a signature over a one-use challenge (`/api/approve/challenge`), checked by the backend. |
| The pairing secret | The QR code's text, on the PC's screen for minutes | The phone's first ask: it proves whoever scanned the PC's screen was there. One use, 10 minutes, 3 tries. |

**The gap the owner is asking to close:** after a reinstall, both keys are
gone. The phone can still reach the PC, and the owner still has to walk the
whole first-pairing flow again - a QR on the PC's screen, a scan, and a card.

## 2. What each option would rest on

| Option | What proves the caller | Who has to do what |
|---|---|---|
| 1. "Pair this phone again?" card (recommended) | A record on the PC ("a device called *Pixel 8* was paired on 2026-09-30, last seen at 100.75.x.x") **plus the owner reading the card** plus Windows Hello | The phone asks; the owner reads one card on the PC and approves it |
| 2. Keep the scan, drop the typed code | The pairing secret in the QR (as today), plus the card | The phone photographs the PC's screen; the owner approves the card |
| 3. Hand a key back with no card at all | Nothing | Nobody - and that is the whole problem |

### Option 1 - a "Pair this phone again?" card (recommended)

The PC keeps a small record per device it has paired: the name the phone gave,
the mesh address it was last seen at, and when. A re-installed phone asks to
pair; the PC matches the ask against that record and offers ONE card naming
the device. Approved with Windows Hello, the PC issues a **new** key, exactly
as a first pairing does, and the old record is replaced.

- **What it makes weaker, in plain words:** the card is a claim, not a proof.
  Any program that can reach this PC over the owner's mesh network and says
  "I am Pixel 8" can raise the same card. If the owner approves without
  reading it, that program gets a key and can then do everything the phone
  could. The only things standing in the way are the owner's eyes, the
  Windows Hello check, and the card naming the device and the address it is
  asking from.
- **What makes it as tight as it can be:** one card, one use, a short expiry
  (2 minutes), never an "always allow", refused on a stale event stream, and
  the card's own words say Jarvis cannot prove the caller is that phone. It
  hands out a **new** key; the old one is already gone.
- **What it does not touch:** risky approvals. A re-paired phone starts with
  no approval-signing key, so it cannot approve a risky card until the owner
  turns signed approvals on for it, with its own card plus Windows Hello -
  the same as any new phone.

### Option 2 - keep the scan, drop the typed code

This is today's flow with the typing taken out: the phone still scans the PC's
QR, and the PC still raises its card.

- **What it makes weaker:** nothing. The scan proves the phone was pointed at
  the PC's screen, which is what it proves now.
- **What it costs:** the owner still has to open Settings, Devices, Pair a
  phone, and point the camera - so it is *not* what they asked for. It is
  listed because it is the honest fallback: if option 1's claim-not-proof is
  too loose, this is the strongest thing that still removes the typing.

### Option 3 - hand a key back with no card (do not build)

- **What it makes weaker:** everything. After a reinstall the phone holds
  nothing, so this is "anyone who can reach this PC and claim the name gets a
  key", with no person asked and no Windows Hello. A device on the owner's
  mesh network - a borrowed laptop, a compromised machine - could pair itself
  and read the owner's chat history, memory and files.
- **Verdict:** not recommended, and written down so the trade-off is visible
  rather than implied.

### Option 4 - the PC shows a fresh code, the owner types it on the phone

- **What it makes weaker:** nothing, and it still needs the owner to type
  something on the phone - which is the thing being removed. It is also no
  proof of the phone. Not recommended.

## 3. What must NOT be possible, whichever is chosen

1. **No risky approval from an unproven device.** A re-paired phone gets no
   approval-signing key. It cannot approve a risky card until the owner turns
   signed approvals on for it - one card, Windows Hello - exactly as any new
   phone does today.
2. **The old shared key's rule is unchanged.** It stays a first-pairing
   bootstrap, accepted from another device only while no device holds a key
   of its own. Re-pairing never reopens it.
3. **No path hands a key to something that never proved anything and was never
   approved by a person.** Every option that issues a key ends in ONE approval
   card, decided on the PC, with Windows Hello. There is no automatic
   reissue, no "always allow", and no reissue from a stale event stream.
4. **Removing a device is final unless the owner says otherwise.** If the
   owner removes the phone from Settings, Devices, the record that option 1
   rests on goes with it, so it must pair the full way again. (This is
   question 2 below - the owner may want the record kept instead, but the
   default has to be the safe way round.)
5. **The card says what it cannot prove.** Its words state that Jarvis cannot
   tell this phone from a program claiming to be it, and name the address the
   ask came from - the same discipline as the voice check, which says plainly
   that it cannot tell a recording from the real voice.

## 4. Questions for the owner

Two, both short. Everything else follows from decisions already made.

**1. After a reinstall, how should the PC decide it is your phone?**

- **A "Pair this phone again?" card on the PC, approved with Windows Hello**
  (recommended) - no code, no scanning. Weaker: a program that can reach your
  PC and claim the same name could raise that card, and approving it by
  mistake would give that program a key.
- **Keep the scan** - the phone must still photograph your PC's screen. No
  weaker than today, but you still walk to the PC and open the pairing panel.

**2. If you remove the phone from Devices, should "pair again" still work?**

- **No - removing forgets it** (recommended), so it must scan the QR again.
- **Yes - the record stays**, so it can pair again with just the card.

## 5. What is not built, and what it would take

Nothing in this document is built. If the owner picks option 1, the pieces are:

- A record per device in the PC's device list (the name and the last address
  are already kept for the list, so this is small).
- A re-pair request route, mesh only, with its own one-use window.
- ONE card whose words say what it cannot prove (section 3.5), and the
  Windows Hello check every risky card already gets.
- A test per rule in section 3, in the shape `backend/test_devices.py` and
  `jarvis-desktop/tests/devices.mjs` already use - including one that fails if
  a re-paired phone can approve a risky card without registering an approval
  key, and one that fails if the old shared key becomes reachable again.
