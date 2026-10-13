# HANDOFF — the Android half

Written 2026-10-09 so a **second conversation** can own the Android app end to end
while the first owns the desktop and the merge pipeline. The split is **by
surface, not by task list**, because today proved what happens otherwise: a
settings search box was built twice by two sessions, and two agents fought over
one handset until neither result was trustworthy.

**Your surface: `jarvis-client/` (the Android app) and the attached phone.**
Do not touch `jarvis-desktop/`, `src-tauri/`, the desktop tests, or the merge
pipeline — the other conversation is there right now.

Repo: `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`. Read
`CLAUDE.md` at the repo root (it is 2,000 lines of the owner's decisions, and it
is the source of truth for what a setting must do).

## The phone

```
f0a5b32b   OnePlus CPH2419 (ColorOS)   Android 15 / API 35   arm64-v8a
1080x2412 @ 480 dpi   dark mode ON   notification permission FALSE
```
`adb` is at `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` — **not on PATH**.
For Kotlin: `$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"`, then
`cd jarvis-client; .\gradlew.bat testDebugUnitTest` (**~1,989 tests pass; none may
regress**). The app compiles locally now — **compile before you push**; the prompt
coach once burned three ~1-hour CI round-trips on Kotlin errors invisible locally.

**The phone is the owner's, and the rules about it are not negotiable:** the app
is sideloaded, never Play; the phone reaches the PC over **Tailscale or NordVPN
Meshnet only** (never plain home Wi-Fi, never a public tunnel); **a client never
does speech-to-text** — the words are worked out on the PC.

**Two hard-won operating notes:**
* **Keep adb swipe start points above y≈1900.** A stray swipe from lower down
  trips a ColorOS gesture, changes density/rotation, and another app comes
  forward. An agent hit this and had to prove its revert.
* **Turning App lock or "Hide memory lists" ON is instant; turning it OFF asks
  for the fingerprint.** So you cannot do it and put it back — leave that test to
  the owner (the procedure is in `docs/ANDROID-TOUR-2026-10-09.md`).

## What is already merged (do not redo)

Android 15 + screen-size compatibility (edge-to-edge **cutout bug fixed** — real,
screenshot-measured), the second Android audit, the device audit, the watch
screen's false-all-clear fix, the local APK signing runbook. SearXNG and Docker
work on the PC; `docker ps` answers.

## Your queue, roughly in value order

1. **The device tour's three dead ends** (real, in `docs/ANDROID-TOUR-2026-10-09.md`):
   * **"Set Jarvis as the assistant app" is a dead button** — `MainActivity.kt:3817-3822`
     returns silently on **both** failure paths; no role request reaches `logcat`.
     Worse than a usual dead control because **"Look at this" is gated on that
     role**: the owner is told they need it and given a button that does nothing.
   * **"Start link" gives no feedback** — the card reads the same before and after.
   * **Help points at a button that is not there** — `FaqScreen.kt:109` says "tap
     Train my voice on the Your voice card"; unpaired, that control is hidden
     (`ReadinessScreen.kt:127`).
2. **The notification link row** the owner chose: one row on the phone that opens
   **Android's own per-app notification settings** — *not* a second copy of the
   PC's four switches. Decided 2026-10-09; see the CLAUDE.md entry.
3. **The 12 of 16 screens that need pairing.** The device tour reached only
   `CHECKS`, `FAQ`, `SECURITY`, `SETTINGS`. Everything else — HOME, BRAIN, INBOX,
   APPEARANCE, VOICE, LIVE, HISTORY, HANDOFF, APPROVALS, FEATURES — needs the
   phone paired, and **pairing needs the owner's Windows Hello tap on the PC**.
   Read `docs/RULE-FLEXIBILITY.md` and `docs/CAR-MODE-DESIGN.md` before proposing
   anything that changes a stored decision.
4. **The second audit's remaining findings** (N2, N3, N4 — N1 is fixed).
5. **Refresh-rate follow-up**: `feat/refresh-rate` (PR #167) is in review. The
   phone offers 60/90/120 and is **running at 60 Hz on a 120 Hz panel** because
   the owner's own `peak_refresh_rate` is 60. An app cannot change it (needs
   `WRITE_SECURE_SETTINGS`), and **this phone ignores per-window requests**
   (`mIgnorePreferredRefreshRate: true`). Do not promise otherwise.

## Traps that cost real time today

* **CI only triggers on pull requests.** A bare branch push runs nothing — a
  draft PR is enough to start checks. **Auto-merge is not allowed here**; the
  first conversation merges by hand.
* **`frontend` takes ~57 minutes** and `main` moves several times an hour. Re-check
  mergeability immediately before merging, and expect "green but not mergeable".
* **`JARVIS_BACKEND` is set in the shell** and makes some suites fail with a scary
  *"this would have tested the repository's copy"* message. **That is not a code
  failure** — and an assertion *about the live backend* must run **with** it set,
  or it is not tested at all.
* **PowerShell has no heredocs.** Use `git commit -F <file>`, never
  `git commit -m` (a multi-line `-m` silently loses the commit).
* **Use a fresh GUID-suffixed temp directory.** `Copy-Item -Recurse` into an
  existing folder **nests** instead of replacing, producing confidently wrong
  results — that caused a completely false failure report today.
* `git checkout --` reverts uncommitted work. `py -3`, not `python`.
  `$env:PYTHONIOENCODING="utf-8"`.
* **`settings.html`'s toggle rows ARE NOW GENERATED** — PR #163 **merged** on
  2026-10-09 (`main` = `58f93e86`), so the desktop rows come from the table in
  `backend/jarvis_settings_registry.py`. For you that matters in one way: **a new
  phone setting's desktop counterpart is declared in that table, never written by
  hand.** A row with no real setter in the backend is a row Jarvis cannot change
  by asking — say so in the table rather than implying it can. (Only 6 of the 26
  desktop toggles had a working setter before this work; that is the gap.)
* A new settings place on the phone needs `MenuPlaces`, `OpenPlace`,
  `SettingsJump` and `SETTINGS_ITEM_INDEX` declared, or **four unit tests fail**.
  **Declare it; never relax those tests.** `SETTINGS_ITEM_INDEX` must match the
  real row order — that is what caught a stale number today.
* **Never log the pairing token.** It is UTF-8 (43 chars, **not** UTF-16), read
  via `CredRead` from Windows Credential Manager as `Jarvis Backend/pairing token`,
  and the header is **`X-Jarvis-Token`**, not `Authorization: Bearer`. Both
  mistakes cost a 401 today.

## Rules that do not move

Never auto-approve; acting stays blocked on a stale event stream. Nothing private
leaves the PC. No public tunnel. A client never does speech-to-text.
Non-commercial, sideloaded, never Play. No bulk approval. **Jarvis never sends a
text message — auto-send is forbidden and is not built** (`docs/RULE-FLEXIBILITY.md`
entry 002); car mode reading texts aloud is the only SMS exception, and it is
entry 001. If something seems to need a rule relaxed, **that is a finding to
report to the owner, not a change to make.**

## How the owner wants to be asked

Multiple choice, **one or two questions at a time**, two or three options, one or
two sentences each, **recommendation first and labelled as yours**. Plain words —
they are a beginner developer. Put the reasoning in your reply or a file, never
inside the options. Then **do the work**; do not ask them to approve each step.

## Reporting back

The other conversation will not see your messages. When you finish something,
**push it and open a PR** — finished work with no PR number is indistinguishable
from work that was never done, which is how seven finished branches sat invisible
for hours today.
