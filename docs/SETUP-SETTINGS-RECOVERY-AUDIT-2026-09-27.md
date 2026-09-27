# Setup, settings and recovery audit - 2026-09-27

**The question (`docs/handoff-2026-09-27/HANDOFF.md` §4, the second of three
combined passes):** look at the whole settings surface and the whole
first-run and recovery experience with fresh eyes - as the owner setting
Jarvis up for the first time, or trying to get out of trouble - and find
what is confusing, missing, inconsistent or would leave a beginner stuck.
Four parts: the settings audit, the install walkthrough, failure and
recovery, and a design for the "first ten minutes".

**How it was done.** One reviewer, reading the code at `c92f90ed`
(`claude/jarvis-continuation-03kls1`): `jarvis-desktop/src/settings.html`
and its scripts, `onboarding.html`, the phone's `SettingsScreen.kt`,
`BrainScreen.kt`, `ReadinessScreen.kt` ("Platform checks") and
`PairingScreen.kt`, `docs/INSTALL.md` cover to cover, `scripts/apply-patches.ps1`,
the watchdog in `sidecar.rs`, the backup module and panel, and the shared
error words (`tools/gen_plain_error_cases.py`).

**What could NOT be checked, said plainly:**
- **The desktop app was not run on Windows**, and the phone app was not run
  at all (no Android build here). Pages were drawn in headless Chromium on
  Linux with test data, the same way `jarvis-desktop/tests/` draw them.
- **`apply-patches.ps1` was not run.** The PowerShell 7 copy CLAUDE.md
  describes was gone from `/opt/pwsh`; a fresh copy was downloaded, but this
  session's sandbox refused to run it (the script calls `git`, and the
  sandbox blocks anything it cannot prove stays out of `git`). Everything
  said about the script below is from reading it. For the same reason **no
  change was made to the script** - see §4.3.

Each finding is **CONFIRMED** (checked against the file, quoted) or
**PLAUSIBLE** (reasoned, not fully verified). File references are to
`c92f90ed` unless marked "now".

---

## 1. Summary

The owner's most likely ways to get stuck, most likely first:

1. **After a crash, the recovery instructions pointed at a button that is
   not there** (CONFIRMED, fixed). When Jarvis crashed 3 times the
   notification said "start it again from the tray" - but the tray then
   shows **"Stop the backend (pid ...)"**, not Start, and Settings says Jarvis
   "has been running for 5m". Now the notification and INSTALL.md say
   exactly which two rows to press. The Settings status line is still wrong
   after a crash: a code change, proposed in §4.1.
2. **After a restore, the message said to use "the tray icon's Restart"**,
   which does not exist (CONFIRMED, fixed). It also did not say to write
   down the safety backup's code first - a code that is lost when Jarvis
   restarts.
3. **Every backup has its own recovery code, and nothing said so**
   (CONFIRMED, fixed). A beginner would reasonably treat the first code
   like a password for all of them. The code box now says which backup it
   opens, by date.
4. **The briefing sends you to "Settings, News feeds", which does not exist
   in either app** (CONFIRMED, fixed). Feeds are added by saying "add this
   feed: <address>"; the briefing now says those words.
5. **INSTALL.md was stale in six places** (CONFIRMED, all fixed): the
   `[tools]` section (following it could break the settings file), the
   first-launch screens, the hotkeys (it said five; there are six,
   Stop everything included), Windows Hello (not mentioned, yet risky approvals are refused
   without it), what happens when Jarvis crashes, and backups.
6. **The phone's settings live in three places** - Settings, Platform checks
   and Brain - and the desktop's in one (CONFIRMED, owner's call, §2.2).
7. **"Let my phone reach this" works only when the app starts Jarvis for
   you, and that switch is in a closed box at the bottom of the page**
   (CONFIRMED, owner's call, §2.1).
8. **When the phone gets "Jarvis isn't running on your PC." but Jarvis IS
   running**, nothing on the phone says the likely cause (Jarvis listening
   to the PC only) (CONFIRMED, proposed fix in §4.2).
9. **There is no single "start here" or "what's new" place.** About a dozen
   features added this session each have their own corner of Settings, the
   Brain or a voice command, and nothing lists them (CONFIRMED). A small
   design is in §5 - **proposed, not built**.

**Fixed directly in this pass:** 16 small things (§6). **Needs the owner:**
6 decisions (§7). **Two tests were already failing on the branch** before
this pass and now pass (§6, items 15-16).

---

## 2. The settings audit

### 2.1 Desktop Settings (`settings.html`, 21 cards)

**S1 - Three FAQ answers pointed "above" at cards that are below.**
CONFIRMED, fixed. The FAQ is the second card, near the top, yet it said
`"What Jarvis can reach" (above)` (line 217), `Open Shortcuts above`
(253) and `see Updates above` (350). All three cards come later. Now "further
down this page".

**S2 - The jump list left out two cards.** CONFIRMED, fixed. `#backup`
("Backups", line 1300) and `#tool-updates` ("Check for tool updates", 1401)
had no link in "Jump to:" (lines 50-83). Added under "Rare".

**S3 - A group called "Read-only" holds switches.** CONFIRMED, fixed. The
heading (lines 76, 1539) covers "What asks first", whose own note says
"'Ask me first' makes one ask every time" - real switches that change what
Jarvis does. Renamed "What Jarvis does" (the jump list and the heading).

**S4 - "Starting Jarvis for you" did not say it restarts a crashed Jarvis.**
CONFIRMED, fixed. The watchdog (feasibility I98, `sidecar.rs`) restarts a
Jarvis this app started, at most 3 times in 10 minutes. The card never said
so, so the one notification when it gives up came out of nowhere. One
sentence added, with what to do.

**S5 - The switch most first-time owners need is the hardest to find.**
CONFIRMED, owner's call. "Let Jarvis Desktop start and stop Jarvis" is in
the closed "More options" box at the end of "Rare" (line 1419). Without it:
Jarvis is off after every reboot, the watchdog does nothing, and "Let my
phone reach this" (Connection, the FIRST card) silently does nothing -
its note admits: "It works only when this app starts Jarvis for you
(Settings, More options, ...)" (lines 162-165). The ease-of-use audit
flagged the same pair (its step 19-21). Suggestion in §5 (the "Start here"
card) rather than moving cards again.

**S6 - Jargon in the refusal sentences of the Connection card.** CONFIRMED,
not fixed (Rust strings with a shared test table; left for a wording pass).
When the phone-address box is refused, the red line quotes `commands.rs`
directly: "the bind address must not include a port — the backend already
knows its port from JARVIS_HUD_PORT" (line 779), "the bind address must be a
bare host — no path, query, fragment or credentials" (772), and for the
address box "the base URL must be an origin only — no path, query or
fragment" (1060). The box is labelled "Let my phone reach this", not "bind
address"; "origin", "fragment" and `JARVIS_HUD_PORT` are unexplained.
Suggested words: "Type only the address, like 100.64.1.5 - no :4719 and
nothing after it."

**S7 - Jargon in two notes.** CONFIRMED, fixed. "Setting SearXNG up (Docker,
and switching on its JSON output) is in backend/README.md" (line 974) - now
says what SearXNG and Docker are. "Check for tool updates" said it means
"reaching PyPI, crates.io and GitHub" - now "the websites that publish them
(PyPI for Python, crates.io for Rust, and GitHub)", in both the PC's words
(`jarvis_tool_updates.DETAIL`) and the app's fallback copy.

**S8 - Two stale code comments.** CONFIRMED, fixed. The top comment said
"there is no 'More options' section" (lines 36-38); there is (1419). Two
comments still said "the phone's Mind", renamed "Brain" on 2026-09-26, and
those sections have since moved to the phone's Settings.

**S9 - The recovery code has a Copy button; the pairing token deliberately
does not.** CONFIRMED, owner's call - and **the security pass may also look
at this.** The token's reason (settings.html lines 138-145, "Windows keeps
what you copy in its clipboard history, and can send it to your other
devices with cloud clipboard") applies equally to a recovery code, which
opens a copy of everything Jarvis knows. `bk-code-copy` (line 1324) uses
`navigator.clipboard.writeText`. The "Private copy" feature (I114,
`clipboard_privacy.rs`) already keeps a copy out of Clipboard History and
cloud sync - the Copy button could use that, or be removed.

### 2.2 The phone

**S10 - The phone's settings are in three places.** CONFIRMED, owner's call.
- **Settings** (`SettingsScreen.kt`): links to voice training, the voice
  check and Jarvis's voice; Security; Appearance; How Jarvis talks; web
  search; What asks first; What Jarvis can reach; Sending email; Folders;
  Backups; the smartwatch switch.
- **Platform checks** (`ReadinessScreen.kt`): "Interrupt Jarvis while it
  talks" (line 632), "Say 'One moment'" (668), the "I heard you" sound,
  the "Hey Jarvis" switch, Security again, and "Check for new versions"
  (973).
- **Brain**: the morning briefing's setup (line 424), learning and chat
  history, Coming up, the standby schedule, models, hardware, second card.

On the desktop, the three voice-flow switches are in **Settings → Voice**;
on the phone they are not in Settings at all - Settings' "Voice" section
only links elsewhere. The briefing's setup is in the desktop's **Settings**
("Everyday") but the phone's **Brain**. The screen's own comment says the
ease audit's rename of Platform checks to "Checks and setup" "has not
actually landed" (SettingsScreen.kt lines 27-29). Suggestion: move the three
voice-flow switches into Settings → Voice on the phone, and give the phone's
Settings a "Morning briefing" link to the Brain section. Not done here: it
is Kotlin that can only be compiled on GitHub, and it is a layout choice.

**S11 - The phone's refusal of a home-network address is helpful.**
CONFIRMED - this is the one the brief asked about. It says what to type
instead, not just "refused" (`PhoneAddress.kt` line 56): "Jarvis's address
{address} is on your own network, but this phone can only reach your PC by
its Tailscale name (ending in .ts.net) or its NordVPN Meshnet name (ending
in .nord) ... type the name the Tailscale or NordVPN app shows for your
PC." The pairing box says the same before anything is typed.

**S12 - CLAUDE.md still says the opposite.** CONFIRMED, tell the owner.
CLAUDE.md's 2026-09-27 list says "**Phone: allow home-network addresses**
(private addresses and `.local`)". The handoff (§3, item 1) and
`PhoneAddress.kt` record that this was investigated, found impossible as
things stand (the PC's Jarvis never listens on the home Wi-Fi), and that
the owner chose to keep using the Tailscale/Meshnet name. The binding spec
and the code now disagree; this pass did not edit CLAUDE.md. **The owner (or
the main session, with the owner's OK) should reword that line.**

### 2.3 One-sided on purpose (`ARCHITECTURE.md` §8)

**S13 - Every asymmetry found is written down**, except layout (S10), which
is placement rather than a missing feature. CONFIRMED: Accounts, Backups,
Check for tool updates, the watchdog and crash notes, data health, App-icon
shortcuts, Private copy, the smartwatch switch and the walkthrough all have
rows. `tools/check_parity.py`: "No undecided drift." News feeds and music
control have **no screen in either app** (voice only, `jarvis_news.py` lines
17-23, `jarvis_media.py`), so there is no asymmetry to record.

**S14 - The walkthrough had two rows that disagreed.** CONFIRMED, fixed.
Line 1504 described it correctly; line 1513 called it "three screens over
the tray icon, the shortcut and a first message" - it is the tray icon,
approval cards and memory. Merged into one row. Also: blank lines between
rows had split the "On the desktop" table into seven fragments, which
GitHub shows as loose text with pipes; rejoined into one table (no words
changed).

---

## 3. The install walkthrough (`docs/INSTALL.md`)

All six fixed. Doc claim first, then what the code does.

**I1 - The settings file's `[tools]` section.** CONFIRMED, fixed.
- Doc (line 192): "This repository's copy of the file has **no** `[tools]`
  section, so a PC set up from it starts with every tool off. To turn one
  on, add a section like this ... `[tools]` / `enabled = ["calculator"]`".
- Code: `backend/rebuilt/jarvis-framework.toml` ends with `[tools]` /
  `enabled = ["web_search"]` (added when "web search ships switched on").
- Why it matters: a new owner following the doc adds a **second** `[tools]`
  heading, and a TOML file with the same heading twice cannot be read at
  all. The doc now says to add names inside the existing list, that an
  older settings file has no `[tools]` at all, and that the four reading
  tools can be switched on from Settings → What asks first.

**I2 - The first launch.** CONFIRMED, fixed.
- Doc (line 352): the HUD "will say 'demo · not connected' ... ignore it —
  that page is the backend's own browser page and does not know the
  desktop app exists."
- Code: since 2026-09-25 the HUD's requests go through the desktop app
  (`hud_proxy.rs`), so "demo · not connected" now means the app could not
  reach Jarvis - not something to ignore. The doc also never mentioned the
  **Welcome** window (`onboarding.html`, opened by `lib.rs` line 1230 on
  first run).

**I3 - The hotkeys.** CONFIRMED, fixed.
- Doc (line 359): "Five are registered at startup"; "`Alt+Shift+S/N/W`
  clash with the Windows keyboard-layout switch".
- Code (`hotkeys.rs` `ACTIONS`): six, including `Alt+Shift+X`, **Stop
  everything** - the one a beginner most needs to know about. Now a table
  of all six.

**I4 - Windows Hello.** CONFIRMED, fixed. The doc never mentioned it. The
backend refuses a risky approval on a PC without it
(`jarvis_owner_check.NOT_SET_UP`: "risky approvals are refused until it is.
Set up Windows Hello in Windows Settings (Accounts, Sign-in options) ... a
PIN is enough"). New step 2.6 says so before the owner meets the refusal.

**I5 - What happens when Jarvis crashes.** CONFIRMED, fixed. Nothing in the
doc described the watchdog or "Hang and crash notes". Step 2.5 and "When
something goes wrong" now do, including the two-row tray dance (F1).

**I6 - Backups.** CONFIRMED, fixed. Not mentioned anywhere. A new short
section "Backups" (before "Updating everything") says: one code per backup,
a lost code means a useless backup, keys are not in it, "Erase the words"
cannot reach an older backup, and backups happen only when you press the
button. "Uninstalling" now says backup files stay in their folder. Also
added: "Find it for me" (step 2.5), and a note under "Updating everything"
that "Check for tool updates" is not how you update Jarvis.

**I7 - `OLLAMA_NO_CLOUD=1` is not in step 1.7.** CONFIRMED, **not fixed -
check on the PC first.** CLAUDE.md lists it as "a second lock behind rule
1". Only the Hardware and models setups' one-line command sets it
(`jarvis_profiles.py` line 844); an owner who follows INSTALL 1.7 and never
opens that card never gets it. The handoff (§5) says installing a model
from the phone is "not yet verified to still work" with it on, so adding it
to 1.7 should wait for that check.

**Checked and still true:** the order and wording of steps 1.1-1.10, the
Credential Manager table in "Uninstalling" (all 11 names match the code),
the "When it fails" error sentences (they match
`tools/gen_plain_error_cases.py` word for word), the Brain tab names, the
tray row names.

---

## 4. Failure and recovery

### 4.1 Jarvis will not start, or keeps crashing

**F1 - The give-up notification sent the owner to a row that is not there.**
CONFIRMED, fixed (the words; the status line is §7, D3).
- Was (`sidecar.rs` line 917): "The backend crashed 3 times in the last 10
  minutes, so Jarvis stopped restarting it automatically. Check
  backend.log, then start it again from the tray."
- After a crash, the app still holds the dead process (`snapshot()` never
  drops it, lines 191-209), so `supervisor_status().owned` stays true.
  The tray therefore shows **"Stop the backend (pid N)"** (`tray.rs` line
  915), Settings' Start button is greyed (`settings.js` line 361), and
  Settings says "Jarvis Desktop started Jarvis, and it has been running for
  Nm" (line 370) - about a Jarvis that crashed.
- Now: "Jarvis crashed 3 times in 10 minutes, so Jarvis Desktop stopped
  restarting it. Why: the end of backend.log (Settings, More options, Open
  the log folder). To start it again: tray icon, Stop the backend if it is
  shown, then Start the backend." It says "Jarvis", like every other
  screen, not "the backend".

**F2 - Once it gives up, it stays given up until the app is restarted.**
CONFIRMED, now documented; fixing it is §7, D3. `gave_up` is set once
(line 819) and never cleared, so after the owner starts Jarvis again by
hand, a second crash is not restarted automatically. INSTALL.md now says so.

**F3 - The HUD's "demo" banner only checks once.** CONFIRMED. The status is
read when the HUD page loads (`jarvis_hud.html` line ~1987); its banner
says "then reload", but the desktop HUD has no reload control and closing
it only hides it. INSTALL 2.3 now says to quit and reopen the app.

### 4.2 The phone cannot reach the PC

**F4 - "Jarvis isn't running on your PC." when it is.** CONFIRMED, proposed
(not fixed). The most common first phone failure is a Jarvis that runs but
listens to the PC only (no "Let my phone reach this", or a Jarvis started by
hand without `JARVIS_HUD_BIND`). From the phone that looks exactly like
"nothing listening", and the shared fix sentence
(`tools/gen_plain_error_cases.py` line 87) says only "The PC is on, but
Jarvis is not started ... press Start". The owner checks, sees Jarvis
running, and is stuck. INSTALL 3.4 explains it; the phone does not.
Proposed: the phone's copy adds "Already running? It may be listening to
the PC only: in Jarvis Desktop's Settings, Connection, fill in 'Let my phone
reach this'." Not fixed here because the same sentence is shared with the
desktop (where it would confuse), lives in four files including Kotlin, and
needs a phone-only variant - a small builder task.

**F5 - The phone's refusal words are good** (S11).

### 4.3 A patch fails to apply (`apply-patches.ps1`)

Read, not run (see the top). The script is careful - it rehearses on a copy
and says "NOTHING HAS BEEN CHANGED" truthfully - but three messages stop
short of the next step. **Not changed in this pass**: the script could not
be run here, CLAUDE.md records three bugs shipped by untested edits to it,
and **the security/dependencies pass is likely to edit this same file** (the
hash-locked install). Proposed words, for whoever next edits it with
`/opt/pwsh` working:

**F6 - "Stopped part-way."** CONFIRMED (lines ~1496-1521). "Copy them back,
or run with -Revert." A beginner does not know how to "run with -Revert".
Proposed: print the exact one-line command, filled in with their path:
`powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1
-BackendPath "<their path>" -Revert`.

**F7 - "Send the block above back."** CONFIRMED (lines ~1436-1441 and
~1823). Back to whom, and how? Proposed: "... - it is also saved in the log
file named on the 'Log' line at the top. Your Jarvis is unchanged and still
starts as before." (That last sentence is true only for the rehearsal
failure, where nothing was touched.)

**F8 - After failing tests, nothing says whether Jarvis still works.**
CONFIRMED (lines ~1818-1837). The patches are already on at that point.
Proposed: "The patches are on. Jarvis will usually still start; if it does
not, this one line takes every patch off again: <the -Revert line>."

### 4.4 Backups and the recovery code

**F9 - The lost-code warning IS shown at the moment of the code.**
CONFIRMED - the brief's question. `backup-settings.js` shows
`LOST_CODE_WARN` in the code box, and the backend's own message repeats it
("Backed up. Write this down or save it somewhere safe now ... If it is
lost, this backup can never be opened again"). The folder card says it too.

**F10 - But not that each backup has its own code.** CONFIRMED, fixed.
`jarvis_backup.backup_now` makes a fresh code every time (line 600,
`made_code = code or generate_code()`), and 5 backups are kept - so up to
5 codes. The code box showed a title and the code, with no date. It now
adds "This code opens only the backup made <date>. Every backup has its own
code, so write the date down next to it." The panel's opening note now also
says backups happen only when you press the button.

**F11 - The restore's last message named a "Restart" the tray does not
have.** CONFIRMED, fixed. Was (`jarvis_backup.py` line 869): "Restored.
Restart Jarvis now (the tray icon's Restart, or close and reopen the app)".
The tray has no Restart row, and closing the app's windows only hides them.
And the safety backup's code - shown once - is kept only in the running
Jarvis's memory (`take_restore_result`), so restarting before reading it
loses it. Now: write down the safety code first ("Your data just before the
restore", in Settings, Backups), then tray icon, Stop the backend, then
Start the backend (or close and restart the PowerShell window).

**F12 - No reminder to back up.** CONFIRMED, owner's call (§7, D5). Backups
are made only by "Back up now" - no timer, no nudge. The phone shows "Last
backup: 3 days ago", which helps; nothing prompts a first backup.

### 4.5 Other recovery traps

**F13 - "Check for tool updates" hands a beginner commands that can trip
the next update.** PLAUSIBLE, and **the dependencies pass may also look at
this.** It shows `cd jarvis-desktop\src-tauri; cargo update -p <name>`
(`jarvis_tool_updates.py` line ~582). That edits `Cargo.lock` in the
owner's copy of this repository, and the next `git pull` in "Updating
everything" can then stop with "Your local changes ... would be
overwritten". Not reproduced here. INSTALL now says those commands are
untested and not needed to update Jarvis.

---

## 5. The first ten minutes - a proposal, NOT built

**What exists today.** CONFIRMED: a 3-screen Welcome (tray icon, approval
cards, memory) on the desktop's first launch; one picture and one sentence
above the phone's pairing form; FAQs in both apps; "What can I say?". There
is **no** place that says "here is what's new" or "here is what to set up
next". A returning owner after this session would have to know to look
for: Backups, Accounts, Check for tool updates, the Humour switch, "Between
us", news feeds ("add this feed:"), music control ("pause", "next song"),
Stop everything (Alt+Shift+X), the slower Approve on risky cards, the crash
restarts, and the phone's app-icon shortcuts. Most of these are off by
default or voice-only.

Two small pieces, reusing what is there. No new settings, no new cards, no
new backend routes.

### 5.1 "Start here" - a checklist card at the top of desktop Settings

Five rows, each ticked from facts the page already reads, each with one
button that jumps to the existing card:

| Row | Ticked when | Button goes to |
|---|---|---|
| Jarvis is connected | the link is live | Connection |
| Jarvis starts by itself | "Let Jarvis Desktop start and stop Jarvis" and "Start Jarvis Desktop when Windows starts" are both on | More options (opened) |
| Windows Hello is set up | Security's check says so | Security |
| A backup folder is chosen | `get_backup` has a folder | Backups |
| Your phone (optional) | "Let my phone reach this" is filled in | Connection |

A "Hide this" link, remembered on this PC. It answers S5 and I4 without
moving any card. **Size: small** (one card, one script, reads only).

### 5.2 "What's new" - one extra Welcome screen, only when there is news

The Welcome window already comes back when `ONBOARDING_VERSION`
(`commands.rs` line 601) is raised. Add a fourth screen, "New since you
last looked", shown only to someone who has seen an older version: 4-6
lines, each "what it is - where it is - on or off", for example:

- **Backups** - Settings, Backups. Off until you choose a folder.
- **Stop everything** - Alt+Shift+X, or the tray. Stops Jarvis at once.
- **News in the briefing** - say "add this feed:" and an address.
- **Music control** - say "pause" or "next song".
- **Humour** - Settings, How Jarvis talks. Off.

The builder of each future feature adds one line and raises the version.
The phone gets the same list as a dismissible note at the top of its
Settings, once per list. **Size: small-medium.** Raising the version also
shows the two corrected Welcome sentences (§6, item 9) to owners who
already closed the Welcome once - this pass did not raise it, so that
choice stays with the owner.

**Recommendation: build 5.1 first** - it helps on day one and every time
something breaks; 5.2 matters once features keep landing.

---

## 6. Fixed in this pass

1. INSTALL 1.6: the `[tools]` section, and how to add a tool safely (I1).
2. INSTALL 2.3: the Welcome window; what "demo · not connected" means now (I2, F3).
3. INSTALL 2.4: all six hotkeys, Stop everything included (I3).
4. INSTALL 2.5: "Find it for me"; what the app does when Jarvis crashes (I5).
5. INSTALL 2.6 (new): set up Windows Hello (I4).
6. INSTALL "Backups" (new), "Uninstalling", "Updating everything", "When something goes wrong" (I6, F1, F2, F13).
7. `sidecar.rs`: the give-up notification names the log's place and the right tray rows (F1).
8. `jarvis_backup.py`: the restore's last message - real restart steps, safety code first (F11).
9. `onboarding.html`: screen 1 says to look under the `^` arrow (the ease audit's finding); screen 2 no longer says "There is no setting anywhere that makes Jarvis stop asking" (untrue since "What asks first" and "Lights, plugs and fans"). Same length as before (checked by drawing it).
10. `backup-settings.js`: the code box says which backup the code opens; the note says one code per backup and no timer (F10).
11. `jarvis_briefing.py`: "Settings, News feeds" replaced by the words that add a feed, in both places it appeared.
12. `settings.html`: the three wrong "above"s; Backups and Check for tool updates in the jump list; "Read-only" renamed; the watchdog sentence; the SearXNG note; two stale comments (S1-S4, S7, S8).
13. `jarvis_tool_updates.py` and `tool-updates-settings.js`: "PyPI, crates.io" explained (S7).
14. `ARCHITECTURE.md` §8: the two walkthrough rows merged; the split table rejoined (S14).
15. `tests/briefing.mjs` **was failing before this pass**: it expected the PC to say "No news provider has been chosen", which the news-feeds change had replaced. Now expects the PC's current words, and no longer requires the PC to repeat the apps' copy of the older-PC line (`jarvis_briefing.OUTSIDE_LINE`'s own comment says the apps keep that copy on purpose).
16. `tests/plain-errors.mjs` **was failing before this pass** ("the page never talks about a card"): a code comment in `manner-settings.js` said "no card either way". Reworded; no behaviour change.

No file needing a `.patch` was touched: `jarvis_briefing.py`,
`jarvis_backup.py` and `jarvis_tool_updates.py` are in `apply-patches.ps1`'s
`$SHIPPED` list (copied whole), and `backend/patch-history` is up to date.

## 7. For the owner to decide

Each is short on purpose; the reasons are in the sections above.

- **D1 - Phone settings in one place?** Move the phone's three voice
  switches from Platform checks into Settings → Voice, and link the
  briefing from Settings (S10). *Recommended.*
- **D2 - The "Start here" card** (§5.1). *Recommended.*
- **D3 - After a crash, Settings says Jarvis "has been running".** Fix the
  status line to say it stopped, and let a manual Start switch automatic
  restarts back on (F1, F2). *Recommended*; a small Rust change.
- **D4 - The recovery code's Copy button** (S9): keep it but copy the
  private way (kept out of clipboard history), or remove it like the
  token's. *Recommended: the private way.*
- **D5 - A backup reminder?** For example, "No backup yet" or "Last backup:
  30 days ago" on the Brain (F12). Or leave it manual.
- **D6 - CLAUDE.md's "Phone: allow home-network addresses" line** no longer
  matches what you chose (S12). Reword it?

## 8. Overlap with the other two passes

- `scripts/apply-patches.ps1`: **not edited here**; the security/dependencies
  pass (hash-locked install) is the likely editor. Proposed wording in §4.3.
- The recovery code's Copy button (S9) and the tool-update commands (F13)
  touch the security/dependencies pass's area.
- The two previously failing desktop tests (§6, 15-16) may also be spotted
  by the quality pass; both are fixed here.

## 9. Verification

- `python3 backend/run_suites.py`: 128 passed, 0 failed, 19 skipped (need
  the owner's PC files). `test_backup.py` 73/0, `test_tool_updates.py` 56/0
  on their own.
- `python3 tools/build_patch_history.py --check`: up to date.
- `python3 tools/check_parity.py`: no undecided drift.
- `python3 tools/gen_notices.py --check`: up to date.
- Rust: `cargo fmt --check`, `cargo clean -p jarvis-desktop` then `cargo
  check` and `cargo clippy -D warnings`, all `--target
  x86_64-pc-windows-msvc`: clean.
- Desktop UI tests (headless Chromium): `briefing.mjs`, `plain-errors.mjs`,
  `faq.mjs`, `auto-learn.mjs`, `continuity.mjs`, `sayable.mjs`,
  `web-search.mjs` - all pass.
- The Welcome window drawn at its real size (480x560): screen 1 fits with
  the added sentence. **Screen 2 was already tight before this pass**: in
  headless Chromium the third example ends about 26 px into the footer row
  (PLAUSIBLE on Windows - fonts render slightly differently there). The
  edit kept its length the same; shortening it is a small UI item.
- **Not run:** `apply-patches.ps1` (sandbox refused PowerShell), `cargo
  test` (needs Windows), the phone app (needs GitHub Actions).
