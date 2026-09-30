# Report 46 (audit), agent ad9d7ce2, 2026-09-30T07:10Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first, then docs/PAIRING-DESIGN.md incl. section 11 phase 2, docs/APPROVAL-GAP-DESIGN.md, docs/ARCHITECTURE.md sections 3-4, JARVIS-API pairing/devices/approval routes; verify each claim with file:line + quote; 'not checked' honestly; change no files). AREA: PAIRING, PER-DEVICE KEYS, SIGNED APPROVALS (Keystore key needing a fresh fingerprint per risky approval; PC verifies signature), the PC-side Windows Hello check for risky approvals from the PC, the approval stamp so an 'approved' row written straight into the database does not count

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

**Pairing, per-device keys, signed approvals and the PC-side approval check: findings**

I found no critical hole in what is built. The main open item is the old-key downgrade (finding 1), which the docs already admit. I ran `test_pairing_cases.py`, `test_shipped_modules.py` (486 pass) and `tools/check_parity.py` (no undecided drift). `test_devices.py`, `test_owner_check.py` and `test_approval_sign.py` could not run here because this container's `cryptography` package panics, so the signature tests are not checked. I did not check the Windows behaviour, Kotlin compilation, or `jarvis_hud.py` (it is outside this repo).

**Findings, most serious first**

1. **Medium, open by design: the old shared key still approves risky cards from another device with no check.** `backend/jarvis_owner_check.py:613` returns None for `device in ("", "pc", "shared")`, so `approve_check` (line 662) lets the request through and `stamp()` runs at line 690. Anyone on the owner's mesh who holds the shared token can approve a risky card.
   - The docs say this plainly (`ARCHITECTURE.md:471-474`), so they are truthful.
   - Nothing pushes the owner to retire the old key. The phone's Retire button only shows when the phone uses its own key (`DevicesPlate.kt:228`).
   - Smallest fix: after the first phone turns on signed approvals, show a standing "Retire the old shared key" prompt on both apps.
   - Owner choice: (a) **Just show that prompt** (recommended); (b) refuse risky shared-key approvals from other devices as soon as any device is paired; (c) leave it as it is.

2. **Medium-low: nothing tells the owner whether an "approve risky actions with fingerprint" card is really from their phone.**
   - `jarvis_devices.py:1803` (`parse_public_key`) checks only that the key is P-256, with no Keystore attestation.
   - `key_card_text` shows only the device name.
   - A thief holding a stolen device key could raise the card, and an owner who approves it by mistake gives the thief a signing key with no fingerprint behind it. It is PC-only with Windows Hello, so it needs the owner to say yes.
   - Smallest fix: show the same four words (from `PairWords`) computed from the hash of the public key on both the card and the phone.

3. **Low: Remove is immediate for new requests, but open streams die on the next write.** `jarvis_devices.py:987-1003` (`_StreamGuard`) raises on the next write. The docs say "within one keepalive (about 10 s)" and are honest. I could not check the real keepalive interval because the server is not in the repo.

4. **Low: the phone blocks Deny on a stale link too.** `JarvisRuntime.kt:3323` (`decisionBlocker`) is used by `decide()` for both approve and deny. Rule 4 asks only that acting is blocked, and denying is the safe direction. This is stricter than needed, not a hole. Say if you want Deny let through on a stale link.

5. **Low: card expiry uses the wall clock.** `approval-expiry.patch` computes `expires_in` from `time.time()`, and `jarvis_owner_check.py:585-590,669,688` trusts it. A clock set backwards makes a card look like it has more time. The pairing session and signature nonces use `time.monotonic()` (`jarvis_devices.py:492`), which is correct. I did not check which clock the gate's own wait uses.

6. **Very low:**
   - If the response to a successful `collect` is lost, the key is gone for good but an orphan device row stays (`jarvis_devices.py:1548-1552`). Remove clears it.
   - A stamp made at `jarvis_owner_check.py:690` lives up to 15 minutes if the owner's handler then refuses.
   - The Windows Hello prompt is one at a time and re-checks that the card is still waiting (lines 670-689).

**Answers to your questions**

- **Code entropy, expiry and lockout.** The typed code is 8 characters from a 32-letter alphabet, about 40 bits (`jarvis_devices.py:1234`). A session lasts 10 minutes, is one-use, and burns after 3 wrong tries from anywhere (lines 1390-1397). Only an HMAC proof is sent, never the code or the QR secret. The 3-try limit is per session, not per source, so a mesh device can burn a session (a nuisance the design lists).
- **What the QR contains.** It holds host, port, a session id, a 16-byte secret and an expiry (lines 647-648). The secret is per-session and single-use, not long-lived.
- **Approval card before any key.** The `pair_device` card is PC-only with Windows Hello (`jarvis_owner_check.py:125`). A key is minted only at `collect` after approval (`jarvis_devices.py:1543`), once.
- **Race between two phones.** A second claim counts as a wrong try (lines 1463-1466).
- **Non-mesh pairing.** Claim and collect are refused unless the peer is in the mesh ranges (lines 1438-1440). The QR host must end in `.ts.net` or `.nord` (line 620).
- **Key storage.** The PC stores only the SHA-256 of each device key (line 1567) and compares with `hmac.compare_digest` (line 924). The registry is re-read whenever the file changes, so Remove takes effect on the next request. The phone stores the device key Keystore-encrypted (`TokenStore.kt`), and `allowBackup` is false.
- **Signed approvals.** The signature covers a fixed magic string, card id, action, a single-use nonce and a hash of the card id, action, title and text (`jarvis_devices.py:1887-1890`). The nonce is bound to card and device, burned on every attempt, and lives 120 seconds. The phone key is P-256, needs a fresh fingerprint or PIN for every use, and is invalidated on biometric enrolment (`ApprovalKey.kt:78-85`).
- **Stripping the signature.** A device with a key cannot fall back to the shared key: `no_signature` is returned (`jarvis_devices.py:2108-2110`), and a `jdk1.` key never falls through (lines 1073-1088).
- **No screen lock.** Android will not make the key, so no signed approval is possible.
- **Phone widget and notifications.** Deny only (`ApprovalWidget.kt`, `EventService.kt:297`).
- **Database stamp.** The stamp is held only in the backend's memory, and the gate refuses an unstamped "approved" row (`owner-check.patch`). The stamp key is not in any file an attacker could read. A card that is not risky can still be approved by any local program holding the token, and the docs say so (`ARCHITECTURE.md:454`). The registry file is also writable by a local program (`PAIRING-DESIGN.md` section 14).
- **App merges from the phone.** These go through the same signed path, and the card carries the exact words, refusing if too big (`jarvis_apps.py:268-273`). I did not verify that the phone shows the whole change before Approve is available.
- **Bulk approve.** I found no route for it.
- **Unauthenticated state-changing routes.** Only `/api/pair/claim` and `/api/pair/collect` take no key (`jarvis_devices.py:2132`), and both are mesh-only and proof-gated. I did not check other routes, because the server file is outside the repo. `POST /api/pending/<id>/amend` attaches a note to the model after an approval, needs only the token, and its text is not part of the signed hash; I did not check it further.
- **Owner checks.** `jarvis_card_words.py:147-154` has the titles, and `_where.py` and `apply-patches.ps1` list both modules. Parity is clean.

Key files:
- `/home/user/Epic-Jarvis/backend/jarvis_devices.py`
- `/home/user/Epic-Jarvis/backend/jarvis_owner_check.py`
- `/home/user/Epic-Jarvis/backend/owner-check.patch`
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt` (3130-3215)
- `/home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/platform/ApprovalKey.kt`
