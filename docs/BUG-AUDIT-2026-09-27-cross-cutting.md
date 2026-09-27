# Cross-cutting audit, 2026-09-27: parity and fit

Scope: the checks that sit *between* the backend, the desktop app and the
phone app, for the features added most recently (JARVIS-API §54-§58:
"Who are you?", "Where this came from", Floating Jarvis on the phone, the
floating face on the desktop, and "open"/"adjust" any setting by voice or
chat), plus the repo-wide consistency tools. This is not a line-by-line bug
hunt; the four sibling audits (`BUG-AUDIT-2026-09-27-backend.md`,
`-desktop-rust.md`, `-desktop-js.md`, `-phone.md`) do that. Audited at
`959bd719` (Merge: Open or adjust any setting by voice or chat). Nothing was
fixed; this is a report only.

## In plain words

**What I checked.** I ran every automatic consistency check myself
(the parity checker, all 19 shared-wording fixture generators, the full
backend test suite and the patch-history check). I read both "floating
Jarvis" implementations, phone and desktop, side by side. I checked the new
"open a setting" / "adjust a setting" feature against the approval rules.
I also checked that the docs describe what the code actually does.

**What held up.**
- All the automatic checks are clean:
  - 131 backend tests pass, 0 fail (19 skipped because they need files that
    live only on your PC).
  - Every shared wording file is up to date.
  - The parity checker reports no unexplained differences between the two
    apps.
  - The patch history is up to date.
- The "adjust a setting by voice" feature does what it promises. Every
  setting it can change goes through the same function, and the same
  approval card, as the switch in the app. The two settings that must be
  approved on the PC with Windows Hello still are. Pasted or shared text
  cannot trigger any of it. I found no setting that should ask first but
  doesn't.
- The list of "PC-only" approvals really has the three entries the docs say
  it has.
- The section numbers in `JARVIS-API.md` run 1 to 58 with no gaps or repeats.

**What is wrong.**
1. **One real bug, which the phone audit also found on its own.** On the
   phone, "open web search" scrolls to the wrong setting (How Jarvis talks),
   and so does every section below it in the list: each lands one row too
   early. Here is how it happened:
   - Two pieces of work landed at the same time.
   - Floating Jarvis added a new row to the phone's Settings screen.
   - "Open a setting" added a list of where each row sits.
   - Each was correct on its own branch. Merging them put everything below
     the new row one place off.
   - The test that was meant to catch this doesn't really check the phone
     side at all.
2. **The docs around that feature are wrong in the same area.** Several
   places say Voice, Security, Appearance and Backups can't be jumped to on
   the phone. They can.
3. **The note saying both floating features work "by a tap" is only half
   true.** On the phone, tapping the floating avatar opens the chat. On the
   PC, the floating face is deliberately not clickable, so you have to say
   or type "open a chat". That paragraph is also missing a blank line, so on
   GitHub it shows up as broken table rows.
4. **The phone's own write-up (§56) still carries its "the PC version may
   not exist" hedge.** The ARCHITECTURE note was corrected once both
   versions merged, but these hedges were not.
5. **Smaller things:**
   - the two apps use different lists of phrases that count as
     "open a chat";
   - while App lock is on, the two floating features follow opposite rules
     (your call which is right);
   - four cross-references point to the wrong section;
   - six notes in the parity checker still say "Brain" for settings that
     moved to the phone's Settings screen;
   - a code comment names a patch file (`settings.patch`) that doesn't
     exist.

None of these break a safety rule. #1 is the only one you would notice
when using the app.

## Findings

| # | Severity | Where | One-line issue | Fix size |
|---|---|---|---|---|
| 1 | Medium | `jarvis-client/.../ui/screens/SettingsScreen.kt` 65-77; `backend/test_settings_registry.py` 106-131 | The phone's "open <section>" scroll map is off by one for 8 sections since merge `959bd719`, and the registry test's phone-side check cannot catch it (same bug as the phone audit's #3; the cause and the test gap are the cross-cutting part) | Small |
| 2 | Low | `docs/ARCHITECTURE.md` 1539; `SettingsScreen.kt` 113-116; `test_settings_registry.py` 122-128; `docs/JARVIS-API.md` 8654-8658; `jarvis_settings_registry.py` 40-45, 121-140 | The docs and comments disagree with the code about which sections the phone can jump to (Voice/Security/Appearance/Backups can), and the registry's `app` field is wrong for `backup`, `account-secrets`, `shortcuts` and `hardware` | Small |
| 3 | Low | `docs/ARCHITECTURE.md` 1561-1566 | "Both expand ... on 'open a chat' ... or a tap": the desktop floating face is deliberately not clickable; the "honest hedge" claim is true in substance but not as worded | Trivial |
| 4 | Low | `docs/ARCHITECTURE.md` 1551-1552 | The picture-in-picture paragraph directly follows a table row with no blank line, so GitHub renders it as one-cell rows of the "On the phone" table | Trivial |
| 5 | Low | `docs/JARVIS-API.md` 8353-8355, 8455-8468, 8472-8480 | §56 still carries the phone session's pre-merge hedges ("Phone only for now", "a concurrent piece of work may add ...", "sending the turn on to the model as usual") that the merge corrected in ARCHITECTURE and §57.3 but not here | Small |
| 6 | Low | `jarvis-client/.../net/OpenChatPhrase.kt` 27-44 vs `backend/jarvis_quick.py` 1792-1799 | The phone and the backend recognise different "open a chat" phrase lists, and no shared fixture ties them together | Small (or owner's call) |
| 7 | Low (owner's call) | `data/FloatingAvatar.kt` 60 vs `windows.rs` 1015-1022 and `jarvis-link.js` 457-465 | App lock: the phone's avatar goes neutral, while the desktop face keeps showing approval, error and offline states; the phone's rule is also missing from ARCHITECTURE §8's App-lock section | Trivial (doc) / owner's call (behaviour) |
| 8 | Low | `docs/JARVIS-API.md` 8689, 7179, 7513, 8414 | Four cross-references point at the wrong subsection or at one that does not exist (§32 for §43, 41.2 for 43.2, 44.4 for 46.4, and "§3.1(2)") | Trivial |
| 9 | Low | `tools/check_parity.py` 112, 113, 115, 116, 120, 124 | Six notes still say "Phone: Brain, ..." for sections that moved to the phone's Settings screen (ease-of-use row 16) | Trivial |
| 10 | Low | `docs/JARVIS-API.md` 8703-8705; `backend/schedule.patch` 102; `backend/briefing.patch` 121 | §58.2 says peer/local are "never defaulted to 'this PC'", but the code's own rule is that an address it cannot place counts as this PC; two patch comments name a `settings.patch` that does not exist | Trivial |

## Details

### 1. The phone's scroll map is off by one after the merge (Medium)

The phone audit found this independently (`BUG-AUDIT-2026-09-27-phone.md`
#3). This section adds the cross-boundary cause and the test gap.

The evidence, from a script that reads the actual `item(key = ...)` order
and the actual map in `SettingsScreen.kt`, for every id in
`jarvis_settings_registry.SECTIONS`:

```
phone LazyColumn order: 0 voice, 1 security, 2 appearance, 3 floating-avatar,
  4 manner, 5 web-search, 6 asks-first, 7 reach, 8 email-sending, 9 folders,
  10 backup, 11 watch-notify, 12 tail
manner         phone_map=3  -> lands on floating-avatar
web-search     phone_map=4  -> lands on manner
asks-first     phone_map=5  -> lands on web-search
reach          phone_map=6  -> lands on asks-first
email-sending  phone_map=7  -> lands on reach
folders        phone_map=8  -> lands on email-sending
backup         phone_map=9  -> lands on folders
watch-notify   phone_map=10 -> lands on backup
```

How it happened:

- `git log` shows `31d0588e` (Floating Jarvis) added
  `item(key = "floating-avatar")` at position 3.
- `344c9408` ("Open or adjust any setting") was branched from before that
  commit. In its own tree, `git show 344c9408:.../SettingsScreen.kt` has no
  floating row (`grep -c floating` gives 0), so its map was correct there.
- The merge `959bd719` combined the two, and nothing re-checked the map.
- The map's own doc comment promised this would not happen silently: "kept
  as one small map rather than computed, so a reordering of the items below
  is a visible two-line diff here too". In a three-way merge, that diff
  never had to be visible.

Why no test caught it. `test_settings_registry.py` line 120-121:

```python
phone_missing = [s.id for s in R.SECTIONS if s.app in ("both", "phone")
                 and s.id not in phone_keys and s.id not in desktop_ids]
```

The desktop check just above it already requires every "both" id to be a
desktop id. The extra `and s.id not in desktop_ids` therefore excludes every
"both" section from the phone check. Only `app="phone"` ids (today only
`watch-notify`) are ever compared against the phone's item keys. Nothing
compares `SETTINGS_ITEM_INDEX`'s numbers to the item order at all.

JARVIS-API §58.1 (line 8607-8611) describes the test as checking SECTIONS
"against ... `SettingsScreen.kt`'s own `item(key = "...")` rows". For the
phone half, that overstates it.

Fix, for whoever owns it:
- shift the map (or compute it from the keys);
- add a test that parses both the item order and the map and checks they
  agree;
- drop the `not in desktop_ids` escape from the phone check (or restrict it
  to a named allow-list).

### 2. Which sections the phone can jump to: the docs disagree with the code (Low)

The code: `SETTINGS_ITEM_INDEX` holds `"voice" to 0`, `"security" to 1`,
`"appearance-card" to 2` and `"backup" to 9`, and `item(key = "backup")`
exists (line 234, `BackupSection()`).

Each claim, set against that code:

- **`docs/ARCHITECTURE.md` line 1539** says two things:
  - "saying 'open backups' from the phone answers with the plain sentence
    naming the place, since `SettingsScreen.kt` has no screen there to jump
    to". There is a backup row, and a map entry for it.
  - "Voice, Security and Appearance ... just not through an `item(key=...)`
    ... jumping there opens the Settings screen and names the place in
    words, rather than scrolling to a row". All three are `item(key=...)`
    rows and are scrolled to.

  The same row also lists "Hardware and models" among sections that are
  "already desktop-only". ARCHITECTURE line 1514 says the phone has Hardware
  (in Brain), and every Hardware route is `ported`.
- **`SettingsScreen.kt` 113-116** (KDoc of `initialSection`) says "an id
  this screen has no row for (the three linked screens above, and every
  desktop-only section) is a harmless no-op". The three linked screens *do*
  have rows and map entries.
- **`test_settings_registry.py` 122-128** says "Security, Appearance and
  Voice on SettingsScreen.kt are their own linked screens, not
  `item(key=...)` rows". `item(key = "voice")` (line 140) and
  `item(key = "security")` (line 178) are literal keys. Only the *wire* id
  `appearance-card` differs from the phone key `appearance`.
- **`JARVIS-API.md` §58.1**:
  - Lines 8650-8652 say the map covers "the seven moved sections, `"voice"`,
    `"security"` and `"appearance"`". That matches the code, apart from also
    holding `backup`.
  - Lines 8654-8656, in the same paragraph, say "the three linked screens
    are reachable by their OWN screen, not a scroll target on this one". The
    paragraph contradicts itself.
- **The registry's `app` field** (`jarvis_settings_registry.py` 121-153):
  - `backup` is `app="desktop"`, but the phone has a backup row.
  - `account-secrets` and `shortcuts` are `"both"`, but ARCHITECTURE §8
    lines 1519 and 1510 record both as desktop-only.
  - `hardware` is `"both"`, while ARCHITECTURE 1539 calls it desktop-only.

  I checked who reads `app`: only `test_settings_registry.py` 116/120 (and
  the unused `sections_for()`). The answer sentence is identical for both
  apps. So this is doc accuracy, not behaviour.

### 3. The picture-in-picture paragraph overclaims the tap, and the hedge history is imprecise (Low)

`docs/ARCHITECTURE.md` 1561-1563: "Both are voice only, both expand into the
real chat surface on 'open a chat' (or a close phrasing) **or a tap**".

- **Phone (true).** `AvatarOverlayService.kt` line 295 and
  `WakeWordService.kt` line 618 both use `MainActivity.ACTION_START_VOICE` as
  the tap target.
- **Desktop (not true).** The floating face is deliberately untappable:
  - `floating.html`: "nothing here is clickable";
  - the iframe is `pointer-events: none`, and the whole page is only a
    `data-tauri-drag-region`;
  - `capabilities/floating.json`: "this window has no button to act with at
    all";
  - `windows.rs` 1061-1064: "there is nothing in it to type into or click a
    button on";
  - `floating.js` registers no click handler.

  Only the spoken or typed "open a chat" opens the bar (`commands.rs`
  2105-2117). JARVIS-API §57's own intro claims only "says or types", which
  is accurate.

"Both went through this row's own honest hedge while only one side
existed": I traced it.

- The phone session (`31d0588e`) wrote a hedge *in this ARCHITECTURE row*:
  "Not claimed as one-sided by decision ... If that work has landed, this
  row is stale the moment the two are merged".
- The desktop session (`a06b7ad4`) wrote its hedge in its own JARVIS-API
  section, then numbered §56.3: "an Android floating face (if built) is a
  separate piece of work". It did not write one in this row.
- The merge (`24ca2172`) replaced the phone row with this paragraph, and
  rewrote §56.3 (now §57.3) to cite §56.4.

So both sides did hedge and both were corrected in the places the paragraph
covers. The claim holds in substance; "this row's own hedge" is only
literally true of the phone side. See #5 for the hedges the merge missed.

The claim "not one shared mechanism, because neither platform's way of
drawing on top of other apps has an equivalent on the other" is accurate:

- the phone uses `Notification.BubbleMetadata` (`WakeWordService.kt`
  607-622, `setAllowBubbles(true)` at 797) or a `TYPE_APPLICATION_OVERLAY`
  window (`AvatarOverlayService.kt`, `FLAG_NOT_FOCUSABLE` at 178);
- the desktop uses an always-on-top borderless Tauri window
  (`windows.rs` 1037-1085).

"Neither reuses a backend route" is also accurate:

- the phone matches `Heard.text` locally (`OpenChatPhrase.kt`);
- the desktop reads `quick == "open_chat"` off the existing
  `X-Jarvis-Route` header.

### 4. The paragraph renders as table rows on GitHub (Low)

`sed -n '1551,1552p' docs/ARCHITECTURE.md | cat -A` shows line 1551 ending
the "Findings" table row and line 1552 starting
`**The picture-in-picture idea ...` with no blank line between them. In
GitHub-flavoured Markdown, a table continues until a blank line. Each
following line becomes a one-cell row of the "On the phone, kept off the
desktop" table. The paragraph after it (1573, "The voice flow is in both
apps") is preceded by a blank line, so it is fine.

### 5. §56 still carries the pre-merge hedges (Low)

`docs/JARVIS-API.md`:

- **8353-8355.** "Phone only for now - see `docs/ARCHITECTURE.md` §8,
  'One-sided on purpose': the Windows half, if any, is a separate piece of
  work". The Windows half exists (§57), and the ARCHITECTURE row this points
  at was replaced at the merge by the paragraph in #3.
- **8464-8468.** "(A concurrent piece of work may add a comparable phrase to
  `jarvis_quick.py` for the Windows side ...)". It did: `_OPEN_CHAT`,
  `jarvis_quick.py` 1792.
- **8455-8461.** "IN ADDITION to sending the turn on to the model as usual".
  Since `_OPEN_CHAT` landed, "open a chat", "open the chat", "show me the
  chat" and "bring up the chat" are answered by the fast path ("Here you
  go.", §57.2), not by the model. The phone still sends the turn, so the
  safety point (nothing is suppressed) holds, but "to the model" is no
  longer accurate for those phrases.
- **8472-8480.** §56.5 compares the avatar to the desktop's HUD window. It
  does not mention the desktop floating face, which is the real counterpart
  and follows a different App-lock rule (#7).

### 6. Two different "open a chat" phrase lists (Low)

- Phone only (`OpenChatPhrase.kt` 27-44): "open chat", "open the chat
  screen", "show me the chat screen", "open jarvis", "open the jarvis app",
  "open the app", "let's chat", "lets chat".
- Backend only (`jarvis_quick.py` 1792-1799): "open/show/bring up the Jarvis
  bar", "show me a chat", "open a chat window" (both have some window forms).

Result: on the phone, "let's chat" brings the app forward and the *model*
answers it. "Open a chat" brings the app forward and the *fast path* answers
it. On the desktop, "let's chat" does nothing special. The Kotlin comment
explains why it does not copy the backend's normaliser, which is reasonable.

Every other wording contract shared across the two apps goes through a
`tools/gen_*_cases.py` fixture; this one does not. Owner's call: either
align the lists (a shared fixture), or write down that they differ on
purpose.

Also noted, not a defect: the desktop acts on `open_chat` whether or not the
floating face is on (`commands.rs` 2105-2117 has no floating check), while
the phone acts only when `floatingAvatar != OFF`.

### 7. App lock: opposite rules for the same idea (Low, owner's call)

- **Phone.** `floatingAvatarShowsContent(appLockOn) = !appLockOn`
  (`FloatingAvatar.kt` 60). Under App lock, the link badge goes neutral:
  "shows nothing content-bearing while it is locked" (§56.5).
- **Desktop.** The face is "NOT behind the app lock" (`windows.rs`
  1015-1022). `surfaceState` (`jarvis-link.js` 457-465) returns `"error"`,
  `"approval"` (a card is waiting), link and standby states regardless of
  lock.

Each side's reasoning is consistent with its own app: the desktop widget and
tray already show this much while locked. But the same feature now reveals
"a card is waiting" on the PC and hides link status on the phone.
ARCHITECTURE §8's "App lock: what it covers on each app" (1351-1411)
mentions only the desktop face (line 1372); the phone avatar's rule is
written only in JARVIS-API §56.5. Whether the two should match is the
owner's call. The missing ARCHITECTURE line is a doc fix.

### 8. Four stale or dangling cross-references (Low)

- **Line 8689 (§58.2 table).** The reading-tool row cites "(§32)" for
  `jarvis_asks_first.handle_tools()`. The route is written up in §43
  ("Offering a reading tool to the AI model, from the PC"); §32 is "What
  asks first".
- **Line 7179 (§43.1 table).** "action `enable_reading_tool` (41.2)". §41.2
  is "Things you can say - The route"; the card is §43.2.
- **Line 7513 (§46.1).** "(44.4)". There is no §44.4 (§44 ends at 44.3); the
  meant section is §46.4 "In the briefing, and 'read me the news'".
- **Line 8414 (§56.3).** "see §3.1(2) for why specialUse over dataSync".
  JARVIS-API.md has no §3.1. The label is a convention used in
  `AndroidManifest.xml` line 15 and `res/values/strings.xml` line 28, where
  the reasoning actually lives.

These were found by a script that scans every `(NN.N)` / `§NN.N` from §38
onward against the real `### NN.N` headings. Every §54-§58 reference
elsewhere in the repo (Kotlin, Rust, JS, Python, READMEs) points at a
section that exists and says what the reference claims.

### 9. check_parity.py notes still say "Brain" on the phone (Low)

These notes in `tools/check_parity.py` still say "Phone: Brain, <name>":
- line 112, `/api/search`
- line 113, `/api/email/sending`
- line 115, `/api/reach`
- line 116, `/api/asks_first`
- line 120, `/api/folders`
- line 124, `/api/manner`

`SettingsScreen.kt`'s own doc comment (30-40) says these sections were
"Moved HERE, in full, from Brain's old 'Settings' group". `BrainScreen.kt`
no longer calls `MannerSection`, `WebSearchSection` and the others (grep: no
matches; line 730 says "moved all seven, whole").

The classifications themselves (ported/deliberate) are still correct. Only
the "where" text is stale.

### 10. The "never defaulted to this PC" wording, and a patch that doesn't exist (Low)

**The wording.** JARVIS-API §58.2 (8703-8705) says peer/local are "read off
the live TCP connection ... never invented, never defaulted to 'this PC'".
The code says the opposite:

- `schedule.patch` line 105 reads
  `(getattr(self, "client_address", None) or ("",))[0]`;
- `jarvis_owner_check.from_this_pc` (218-232) says "Anything that cannot be
  placed counts as this PC";
- `jarvis_quick.answer_turn`'s own docstring (2834-2840) says so plainly:
  "the SAME 'cannot be placed counts as this PC' rule".

The practical risk is nil:
- a real socket always has `client_address`;
- the approval itself is separately checked at `/api/approve`
  (`jarvis_owner_check` 629-632: PC-only, plus Windows Hello).

So this is an overstatement in the doc, not a hole.

**The missing patch.** `schedule.patch` line 102 (and the same context line
in `briefing.patch` line 121) say "settings.patch's 'open'/'adjust'". There
is no `backend/settings.patch`; the registry is "shipped whole, no patch of
its own".

## The six focus areas: verdicts

1. **JARVIS-API.md accuracy (§54-§58, ARCHITECTURE §3/§8).**
   *Found problems (minor).*
   - Top-level numbering 1-58 is sequential with no gap or duplicate.
   - All §54-§58 references across the repo resolve.
   - ARCHITECTURE §3's "second door, never a second gate" paragraph
     (308-321) matches the code.
   - But: §58.1 contradicts itself and the code about which phone sections
     can be jumped to (#2); ARCHITECTURE 1539 is wrong about
     Voice/Security/Appearance/Backups/Hardware (#2); four nearby
     cross-references are stale (#8).
2. **The "two different mechanisms, both hedged then corrected" claim.**
   *Confirmed in substance, with one overclaim.*
   - The two mechanisms really are independent and platform-specific.
   - Both sessions did hedge, and the merge corrected ARCHITECTURE and §57.3.
   - But "or a tap" is false for the desktop (#3), the paragraph renders
     broken (#4), and §56's own hedges were never corrected (#5).
3. **`tools/check_parity.py` coverage.** *Confirmed accurate (output).*
   - Output: 128 desktop / 108 phone / 107 ported / 18 not porting / 1 still
     to port (`/api/retrieve`) / 1 phone-only (`/api/notifications/watch`) /
     "No undecided drift".
   - The phone-only watch route, and the deliberate `/api/asks_first/tools`,
     `/api/tool_updates`, `/api/focus/callout` (backend `handle_callout`
     refuses a non-PC peer, `jarvis_focus.py` 1626) and backup/folders
     routes (`from_this_pc` in `jarvis_backup.py`/`jarvis_documents.py`)
     match the code: grep finds no phone call to the first two and no
     desktop call to the watch route.
   - Six notes carry a stale "Brain" location (#9).
4. **Generated fixture staleness.** *Confirmed accurate.* All 19
   `tools/gen_*_cases.py --check` runs report up to date, exit 0.
5. **Approval-model consistency.** *Confirmed accurate.*
   - `PC_ONLY_ACTIONS = frozenset({"loosen_what_asks_first",
     "enable_reading_tool", "restore_backup"})` (`jarvis_owner_check.py`
     118), exactly as the registry, ARCHITECTURE §3 and JARVIS-API §58.2
     say.
   - `maybe_suggest_combined` reuses `_request_change_combined` and the
     existing `second_card_combined_enable` card (`jarvis_second_card.py`
     302, 2684); it makes no PC-only claim. Its "suggest" switches exist in
     both apps (`settings.js` 1910-1922; `SecondCardPlate.kt`).
   - Every "adjust" setter calls the same `handle_*`/`request_*` as its REST
     route. Each "ON" that should raise a card does: learning, sensitive,
     lights, briefing senders, smartwatch, and "ask before every search"
     OFF (`jarvis_search.py` 1495-1499).
   - The fast path only reads the owner's own words: `newest_own_words`
     refuses shared, clipboard or system-tagged turns (`jarvis_quick.py`
     2787-2794).
   - No adjustable setting was found that CLAUDE.md says should ask first
     but does not.
6. **`run_suites.py` and `build_patch_history.py --check`.** *Confirmed
   clean.*
   - "131 passed, 0 failed, 19 skipped (they need files that live only on
     the owner's PC)".
   - "backend/patch-history is up to date." It also printed a note that an
     old `wellbeing.patch` version from `31ad726` is left out as corrupt;
     that is the tool's own expected handling, not a failure.
