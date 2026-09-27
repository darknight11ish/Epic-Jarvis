# Quality audit, 2026-09-27: one card or two, clashes, gaps, words, battery, tests, CI, memory

The third of the three combined passes the owner asked for
(`docs/handoff-2026-09-27/HANDOFF.md` section 4). The other two (security,
privacy and dependencies; setup, settings and recovery) ran separately.

**How far to trust it.** Every finding is marked:

- **CONFIRMED** - I read the file, or ran the code or the test, and quote
  what I found.
- **PLAUSIBLE** - reasoned from the code and the docs' own numbers, but not
  run, usually because it needs the real graphics cards or the real model.
  Each one says what is missing.

Checked at commit `c92f90ed` (branch `claude/jarvis-continuation-03kls1`).
Nothing here ran on a real graphics card, a real Ollama, a real phone, or a
real Windows desktop. Section 10 lists everything I could not check.

---

## In plain words (for the owner)

1. **The humour switch does not really switch humour off.** Jarvis's
   always-on character rules already say "a light, dry touch" of humour is
   fine. The switch only adds MORE permission when on; "off" takes nothing
   away. And with "Plain" and humour both on, Jarvis is told two opposite
   things. This is your call (question 1).
2. **Two word lists the apps check themselves against had gone stale**,
   the second time in one day. The cause: five of these lists had no
   automatic check at all. **Fixed:** refreshed the stale one, and every
   list now has a check that fails the tests the moment it goes stale.
3. **"One bigger model on both cards" is probably too big to fit while
   everyday chat is loaded.** Its memory sums count your 2080 Super as
   empty, but everyday chat stays on that card all the time. Nothing uses
   this mode for answers yet, so nothing breaks today. It needs fixing
   before anything does (finding 3).
4. **"Erase the words" says "from your PC for good".** Since backups
   exist, an older backup can still hold the words. You decided the apps
   must say so. The Backups screen says it, but the Erase question does
   not (finding 4).
5. **Nothing from this branch reaches your phone or your desktop app yet.**
   The phone app and the desktop installer are only published from `main`
   and from the old branch name. Merging the pull request fixes it
   (question 2).
6. **With one graphics card, which is what you have today, everything
   second-card related stays safely off.** I ran every switch on a
   pretend one-card PC: nothing starts, nothing crashes, and each refusal
   says why in plain words.
7. Smaller things, most fixed: a lock-screen line that left out web-page
   watches (fixed), a stale memory scoreboard (fixed), three "Now" ideas
   from the feasibility audit that are still not built, and one FAQ answer
   that is out of date.

---

## 1. One card or two

### 1a. One card (today): everything degrades cleanly - CONFIRMED

I drove `backend/jarvis_second_card.py` through its own test world
(`tools/gen_second_card_cases.py`'s `World`, which replays `nvidia-smi`
lines) with the one-card line the tests use (a 2080 Super, 8 GB):

| What I did | What happened |
|---|---|
| `status()`, every switch off | `capable: False`, "only one graphics card found (the NVIDIA GeForce RTX 2080 SUPER)" |
| `lane_for()` for all five features, and `combined_lane()` | all `None` |
| Turn each switch on (`request_change`) | 503 each, e.g. `"Longer conversations" cannot be turned on: only one graphics card found (...)`; combined: `needs two graphics cards; only one is here` |
| Switches left ON from an earlier two-card PC, card now gone | `lane_for` all `None`, no Ollama started, no crash |
| "One bigger model" left ON, card gone | `combined_lane()` `None`; every other switch refused 409 "turn that off first" |
| Programs started, in every case above | 0 |

`lane_for` reads the switch file and returns before anything else when the
switches are off (`jarvis_second_card.py:1490-1491`), so a one-card PC pays
one small file read per chat turn. The docs' claim - "nothing here does
anything on a PC with one card" (`jarvis_second_card.py:12`,
`docs/SECOND-CARD.md:4-6`) - holds.

### 1b. "One bigger model on both cards" counts the 2080 Super as empty - PLAUSIBLE, high impact once it is used

The budget (`jarvis_second_card.py:273-285`) gives the 2080 Super 5.57 GiB
of room for its share of `qwen3:14b`:

    room, 2080 Super (monitor)   8.00 - 1.10 desktop - 0.33 CUDA - 1.00 fit  =  5.57 GiB

That is the room on an **empty** card. But everyday chat lives on that card
all the time: `OLLAMA_KEEP_ALIVE=-1` (`docs/MODEL-TOPOLOGY.md:130`, "deliberate"),
and Ollama predicts 6.92 GiB for `jarvis-primary` (`docs/HARDWARE-PROFILES.md:242`).
Nothing in the combined mode unloads it - I searched `jarvis_second_card.py`
for `unload`, `keep_alive` and `jarvis-primary`: no code does. Ollama splits
by **free** memory (the module's own finding), so with chat loaded almost
all of the 12.28 GiB would have to go on the 2060, which has 10.07 GiB of
room. It does not fit; llama.cpp would then put the rest in the PC's own
memory (much slower) or refuse to load.

Why nothing breaks today: nothing calls `combined_lane()` yet
(`jarvis_second_card.py:46-48`, confirmed by grep). Also, the approval card
says the mode "uses both cards for the one model" (`_describe_combined`),
which is not true while chat is on one of them.

**What is missing to confirm it:** the second card. **Heads-up for the
builder working on the combined lane right now:** whatever starts sending
answers to this lane has to decide what happens to everyday chat first
(unload it, or budget around it). I did not change this file.

### 1c. A wrong reason when the second card is under 10 GB - CONFIRMED, low

`_combined_rows` (`jarvis_second_card.py:772-779`) only accepts a card whose
role is `"second"`, and a card only gets that role if it passes the
10 GB floor for the per-card features. So a pair that the combined mode
itself would accept (its floor is 18 GB **together**) is refused with a
false reason. I ran it: a 12 GB card with the monitor plus an 8 GB card
(20 GB together) gives

    "One bigger model on both cards" cannot be turned on: needs two graphics cards; only one is here.

The realistic way to hit this with your own cards: plugging the monitor
into the 2060 by mistake. The 2060 then becomes the main card and the
2080 Super "the second", which fails the 10 GB floor. The docs already say
to plug the monitors into the 2080 Super. I did not fix it: this file is
being changed by the in-flight builder. The fix is to take any other card
in `_combined_rows`, not only a "second" one, since `_combined_capable`
already checks each card itself.

### 1d. Doc slip - CONFIRMED

`docs/SECOND-CARD.md:55` calls "One bigger model on both cards" "a sixth
switch", and `:281` calls the better voice "A sixth use of the second
card". Left for the in-flight builder, who is likely editing that page.

---

## 2. Feature clashes

### Finding 1. Humour: "off" is not off, and Plain + humour contradict - CONFIRMED

- The character block is sent on **every** turn, word for word, in all
  three copies: `backend/jarvis-primary.Modelfile:173`,
  `jarvis_agent.py:3530` (`LANE_SYSTEM`), `jarvis_profiles.py:913`:
  "- Humour: a light, dry touch at most, and never about mistakes, health,
  money or safety, never when the owner is upset, never in a refusal."
- The humour switch only ever **adds** a note:
  `return NOTE[m] + (HUMOR_NOTE if h else "")` (`jarvis_manner.py:216`).
  With the switch off, nothing tells the model not to use humour, and the
  character block tells it a little is fine.
- Your decision (CLAUDE.md, 2026-09-27): "Humour: a switch in 'How Jarvis
  talks', **off to start**." With the switch off, the model is still told
  light humour is allowed.
- **Plain + humour on:** Plain says "be neutral and businesslike ... no
  small talk ... do not bring up shared jokes" (`jarvis_manner.py`,
  `NOTE[PLAIN]`), and then the humour note says "You may add a little
  light, gentle humour". Both are sent in the same system message. The
  apps allow this combination on purpose ("it can be on with either warm
  or plain", `jarvis_manner.py:205`), and `test_manner.py` tests that it
  saves, but not what the model is told.
- `docs/PERSONA-MODES-CHECK-2026-09-27.md` said humour was "Later - not
  part of this batch" and found "no live conflict". The setting had been
  built the day before (`1e90874f`). I added a dated correction there.

Two builders made these a day apart (the switch in `1e90874f`, the
character block in `f2ad15f4`). Neither one changed the other's text.
**Question 1** below.

### Finding 4. "Erase the words" vs backups - CONFIRMED

- Both apps ask: "Erase the words of this fact from your PC for good? ...
  This cannot be undone." (`jarvis-desktop/src/auto-learn.js:208-210`,
  `jarvis-client/.../net/MemoryErase.kt:58-60`).
- Backups (built 2026-09-26) keep the last 5 locked files
  (`jarvis_backup.py:183`, `KEEP = 5`), possibly in a cloud-synced folder.
  The module knows: `ERASE_LIMIT` ("'Erase the words' cannot reach into an
  older backup...", `jarvis_backup.py:216-218`). But that sentence is shown
  only on the Backups screen and the restore card. The Erase question
  itself, where the promise "for good" is made, never mentions it.
- Your decision: "the app must say plainly ... that erased facts stay in
  older backups until they age out". The feasibility audit's guardrail for
  backups (I96) was "Erase warns about old backups".

Not fixed here: the words live in both apps, and neither app's tests can
run in this container. **Recommended fix** (no decision needed; it carries
out one you already made): when a backup folder is set, add one sentence
to the Erase question in both apps, for example "Your backups made before
now still hold these words until they are replaced (Jarvis keeps the last
5)." Also apply it to "Also delete the chat it came from".

### Finding 6. The lock-screen line for "tell me when" left out web pages - CONFIRMED, **fixed**

A "tell me when this page changes" (built 2026-09-26) is set up with the
same card as the others (`schedule_repeat`; `test_tellme.py:1233`). The
card itself is honest: "Each look is a request to that one address on the
internet" (`jarvis_tellme.py`, `card()`). But the gate's line for that
action - the words on the approval notice and the lock screen - still
said "a 'tell me when', which looks at your own mail server or Home
Assistant each time" (`asks-first.patch:97`). **Fixed:** it now adds "or at
one web page you named". Every existing check on that line still passes
(`test_approval_contract.py`, `test_asks_first.py`, `test_schedule.py`,
`test_briefing.py`, `test_tellme.py`).

Left as it is, and worth a look: the same line calls the action `"local"`,
and "local" decides that the notice waits quietly to be found, while
"outbound" makes it interrupt (`approval-notice.patch`, `notice_for`). A
page watch fetches an internet address every 30 minutes. Changing this
would make every briefing card interrupt as well, so I left it alone.

### What I checked and found consistent - CONFIRMED

- **Action names.** The whole patch stack's `_RISK` table (28 entries, built
  with `backend/_stack.py`'s stand-in) has no duplicate key. Every
  action-name constant in `backend/*.py` resolves to one name each.
  `_NO_RULE_FROM_DENIAL` has no duplicates.
  `jarvis_asks_first.py`'s `HARD_LIMITS`, `MUST_ASK`, `LOOSE` and `GROUPS`
  agree with each other and with the shipped `jarvis-framework.toml`.
- **`web_research` ships `"auto"` but is on `MUST_ASK`.** The "What asks
  first" page shows it as "Refused - it only runs on your yes"
  (`jarvis_asks_first.py:157`), which is what the tool loop does
  (`jarvis_agent.py:5016-5031`). `backend/README.md:2472` says the same.
  Two places said "asks" instead of "is refused":
  `docs/APPROVALS-AUDIT-2026-09-26.md:111` (a dated record, left as it is)
  and a comment in `test_asks_first.py` (**fixed**).
- **Briefer during focus + manner + humour + the crisis note** are four
  separate system lines, in a fixed order. The crisis note is nearest the
  question (`jarvis_agent.py:4467-4484`). None of them replaces another.
  One gap, PLAUSIBLE, low: on a crisis turn the humour note is still sent.
  Its own words say "never about ... crisis", so the model is told not to
  joke, but the code does not drop the note. Worth folding into question
  1's fix: on a crisis turn, send no humour note at all.
- **One umbrella action, many meanings** (PLAUSIBLE, low):
  `change_own_config` guards adding a news feed, choosing a backup folder
  (which may be cloud-synced), the lights setting, adding a folder, wake
  settings and more. Each card's own text is specific. The lock-screen
  title is one generic line, "change one of its settings"
  (`jarvis_card_words.py:107`). Its risk line lives in your own
  `jarvis_gate.py`, which I cannot see. One effect to know about: setting
  it to `"never"` switches all of these off at once.

---

## 3. Gap audit: feasibility "Now" ideas still not built - CONFIRMED

I checked all 46 "Now" rows of `docs/FEASIBILITY-AUDIT-2026-09-26.md`
section 2 against the commit log and the code. Built this session or
earlier: I03, I05, I06, I07, I12, I14, I15, I16, I28, I40, N1, I42, I53,
I68, I69, I75, I81, I93, I95 (the harness; the run is yours), I96, I97,
I98, I99, I110, I111 (pinning half), I114, I115, I116, I125, I129, I131,
I132, I133, I134, I135, I144, I145, I151, I152, I154. The step 0 fixes
are in (taint survives a restart: `jarvis_chat_log.py:24`; the
`file_read` refusal list: `jarvis_agent.py:251-274`).

**Still not built:**

| Id | Idea | Evidence it is not built |
|---|---|---|
| I09 | Model shortlist test ("test only") | No hit for "shortlist" outside the research docs |
| I39 | "Where's that file?" (Everything / `es.exe`) | `jarvis_tool_updates.py:76-80`: "Everything (`es.exe`) is NOT integrated into Jarvis at all" |
| I82 | "Someone at the door" (docs and a phrase) | No hit in `backend/`, `docs/` or `jarvis_quick.py` |

**Waiting on something else, as planned:** I37 (the overnight tidy) waits
for your memory self-test run on the PC. I102 and I103 (QR pairing and
per-device keys) are queued after the security audit (section 3, step 6).

The table itself is now partly out of date. The owner turned several "No"
and "Later" rows into decisions: I142 "Between us" (No, now built), I146
games in a temporary chat (No, now built), I137 humour, I140 "From now
on", I49, I67 and I91 (all Later, now built). The table was a snapshot, so
I left it alone. The handoff's "All work is on branch
`claude/admiring-ritchie-5urg5h`" (`HANDOFF.md:9`) is also out of date:
this session works on `claude/jarvis-continuation-03kls1`.

---

## 4. Accessibility and plain words

**Desktop HTML** - CONFIRMED, from the source. I parsed every
`jarvis-desktop/src/*.html` for images without `alt`, form fields without
a label, buttons with no name, and a page without `lang`:

- `brain.html`, `settings.html`, `onboarding.html`: nothing found.
- Five text boxes are named only by their grey hint text (`placeholder`):
  `index.html` `#task-note`, `#approval-note`; `widget.html` `#task-note`,
  `#appr-note`, `#capture-input`. Chromium, which WebView2 uses, reads the
  hint text as the box's name when there is nothing else, so a screen
  reader is not left with nothing. A real `aria-label` is still the norm.
  Low.
- `jarvis_hud.html` (`#input`, `#gsearch`) the same, and it and
  `faces.html` have no `<html lang>`. Low.
- Four buttons are empty in the HTML and filled in by script (`#attention-mute`,
  `#problem-action`, `#answer-used-line`, `#answer-sources-line`). Fine if
  the script always fills them; I could not render to check.
- **Contrast** has its own desktop tests (`tests/tokens.mjs`,
  `themecheck.mjs`). They need Playwright, which is not installed in this
  container, so **I could not run them** or look at a rendered page.

**Phone** - CONFIRMED: no `IconButton` in the app has
`contentDescription = null`, and no text size below 11 sp in `ui/`. Most
new screens show words served by the PC, which `test_manner.py`'s style
check already covers.

**Plain words** - CONFIRMED:
- Settings' FAQ, "Does anything I say to Jarvis leave this computer?"
  (`settings.html:206`), lists web search, calendar, email and Home
  Assistant. Since then, four more ways out were built: news feeds, "tell
  me when this page changes", saving email drafts to your mail provider,
  and "Check for tool updates". The answer should name them, or point to
  "What Jarvis can reach". Not fixed: the settings pass may be editing this
  page.
- "Check for tool updates" (`jarvis_tool_updates.py:157-162`) says "Python
  packages, the Rust building blocks ... PyPI, crates.io" without saying
  what PyPI and crates.io are (the public download sites for Python and
  Rust parts). CLAUDE.md: say what a thing is before its name. Low.
- The humour switch's fallback words in both apps (`manner.js:43`,
  `Manner.kt:53`) leave out the backend's first sentence ("Occasional light
  humour in answers, when it fits."). They are shown only when the PC does
  not send its own words, and neither app's tests compare them with the PC's.
  Low.

---

## 5. Performance and battery (the phone)

**Nothing built this session polls in the background on the phone** -
CONFIRMED. Every new repeating loop I found in `jarvis-client` is inside a
screen (`LaunchedEffect`), so it stops when you leave that screen:
Hardware (every 5 s), the big model (every 20 s), Brain's auto-refresh.
The app's background parts are the same as before: the event-stream
service (`service/EventService.kt`), the "Hey Jarvis" service (only if you
switch it on), and the runtime's 10-second watchdog
(`JarvisRuntime.kt:4099`).

The three things the brief named all run **on the PC, not the phone**, and
their limits are enforced in code - CONFIRMED:

| Feature | The limit in code | Where |
|---|---|---|
| "Tell me when this page changes" | at most every 30 minutes (`PAGE_MINUTES = 30`), at least daily; refused otherwise | `jarvis_tellme.py:205-206`, `check_rule` `:486-498` |
| Instant email (IMAP IDLE) | renewed every 9 minutes, retry waits 30 s up to 30 min, closed on standby and "Stop everything", 5-minute looks as the fallback | `jarvis_tellme.py:196`, `:225`, `:231`, `:1653-1702` |
| News headlines | fetched only when a briefing runs or you ask; no timer. 10 feeds at most, 10-second timeout, size cap | `jarvis_news.py:107-111`, `:268`, `:373` |

Not checked: how often the PC's event stream sends its keep-alive to the
phone. That lives in your own `jarvis_hud.py`.

---

## 6. Test quality

**The real numbers** - CONFIRMED, run here: `python3 backend/run_suites.py`
gives **128 passed, 0 failed, 19 skipped** before my changes, in 4 min
46 s. All 19 skips are named, and each needs a file that exists only on
your PC (`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_extract.py`,
`jarvis_models.py`).

**Thin suites?** The smallest suites for this session's features are
`test_paste_guard.py` (14 checks), `test_focus_brief.py` (15),
`test_identity.py` (18) and `test_character.py` (20). I read
`test_paste_guard.py` in full: its 14 `check(` lines run over 17 "must
hide" and 20 "must keep" sentences, plus a real check of what reaches the
encrypted chat database. That is real behaviour, not a trivial assert.
The larger siblings (`test_email_draft.py` 108, `test_tellme.py` 173)
test similar things in similar depth. I found no suite that only asserts
that something exists.

**Finding 2: shared word lists going stale without anything failing** -
CONFIRMED, **fixed**.

- `tools/gen_plain_error_cases.py --check` **failed** at the start of this
  audit. Both apps' copies of `plain-error-cases.json` lacked the humour
  switch's four fields (`humor`, `humor_default`, `humor_detail`,
  `humor_title`), stale since `1e90874f`. This is the second one this
  session: `c92f90ed` had just fixed `email-sending-cases.json` the same way.
- The cause: five of the 19 `gen_*_cases.py` producers had **no** automatic
  check anywhere (`plain_error`, `email_sending`, `focus`, `web_search`,
  `reach`). `run_suites.py` and CI never ran their `--check`. The other 14
  are each checked by a backend suite.
- **Fixed:** refreshed the fixture, and added one check to each matching
  suite, the same shape as `test_asks_first.py`'s
  `t_both_apps_read_the_current_contract`: `test_manner.py`,
  `test_email_send.py`, `test_focus.py`, `test_web_search.py`,
  `test_reach.py`. **I tested the test:** with the old stale fixture put
  back, `test_manner.py` fails, naming the file and the command to run.
- **Also fixed, a bug in the producer itself:**
  `gen_plain_error_cases.py` used `os.environ.setdefault(
  "OPENJARVIS_CONFIG_DIR", ...)`, so it read the caller's settings folder
  when one was set. With a `manner.json` containing `"humor": true` there,
  `--check` failed on a correct fixture. I ran that to prove it. Its four
  siblings always use a fresh folder; now it does too.

**The other checks, all clean** - CONFIRMED: every other
`tools/gen_*_cases.py --check`, `tools/check_parity.py` ("No undecided
drift"), `tools/build_patch_history.py --check`, `tools/gen_notices.py
--check`, and `tools/check_python_advisories.py` ("77 pinned releases,
every one with a hash"; "0 problem(s)").

---

## 7. CI and release

Read in full: `.github/workflows/ci.yml`, `jarvis-client.yml`,
`desktop-release.yml`, `android-apk.yml`, `verify-toolchain.yml`.

**Coverage** - CONFIRMED. New backend files and patches are covered:
`ci.yml` runs all of `run_suites.py` and `check_parity.py`, with full git
history so the patch-history check runs. New Rust files are covered:
`cargo fmt --check`, `clippy --all-targets -D warnings` and `cargo test`
on Windows. New desktop pages are covered: every `tests/*.mjs` under
Playwright, plus a parse check of every `src/*.js`. New Kotlin files are
covered: `jarvis-client.yml` runs on changes to `jarvis-client/**`,
`backend/**`, desktop `src/**` and the shared fixtures. Before my fix, the
five word-list checks above were the one real hole; now they run in CI
through the backend suites.

**Nothing skips silently.** I read every `|| true` and every
`continue-on-error`. The `|| true` lines are all log-collection or
clean-up. The two `continue-on-error` jobs say why: publishing the release
(a failure prints a warning with the fix) and the face-photo job (it never
gates anything).

**Finding 7: nothing from this branch is published** - CONFIRMED.
- The phone app is published to `client-latest` only when `github.ref ==
  'refs/heads/main' || github.ref == 'refs/heads/claude/admiring-ritchie-5urg5h'`
  (`jarvis-client.yml:975`).
- The desktop release workflow runs only on
  `branches: [main, "claude/admiring-ritchie-5urg5h"]` (`desktop-release.yml:44`, `:100`).
- This session's work is on `claude/jarvis-continuation-03kls1`. So the
  CI checks run, but the APK on your phone and the desktop installer do
  not change until this branch is merged into `main`. This was decided on
  purpose (the DEPS audit, B-20: one working branch only). Only the branch
  name is out of date. **Question 2.**

---

## 8. Memory effectiveness

**Only your PC can measure it for real**, with the meaning search, the real
re-ranker and the real learner model. What I could do:

- **Re-ran the build machine's words-only self-test** (`python3
  backend/eval_memory.py --words-only`, 97 s) - CONFIRMED: recall@5 80.9%
  at 71 facts (77.7% at 10,071 same-topic), two-fact questions 7/10, time
  questions 10/10 with 0 wrong versions, learner cases 80/80
  (5+4+8+37+14+12). **Identical to the scoreboard's last row**, so nothing
  measurable here got worse after the later changes.
- **Changes that touched learning and were not on the scoreboard** -
  CONFIRMED: I154 ("passing moods are not facts" added to the learner's
  instructions, `jarvis_intake.mood_rule`, commit `dbcdef38`) and I151
  (crisis messages never learned, `31ad7269`). Your rule is that every
  learning change is measured and written on the scoreboard. **Fixed:**
  added a dated row with the re-run above. It says plainly that the build
  machine **cannot** see I154's effect: that change is in the words the
  real model reads, and here the learner is a stand-in.
- **"Between us"** leaves shared facts out of recall in a Plain-manner turn
  (`jarvis_agent.py:197`, `without_shared_in_plain`). The self-test does
  not run with a manner, so this is not measured. It only ever removes
  facts you tagged, in Plain turns, so the risk is small. PLAUSIBLE, low.
- **"Where this came from" and the quote check** (`jarvis_sources.py`) only
  read back what a tool already returned. They do not change which facts
  are found. CONFIRMED by reading the module and the commit message.
- **The one-line command** (`docs/MEMORY-SCOREBOARD.md`) is correct and
  current. `eval_memory.py` takes `--learner-model`, writes to
  `%USERPROFILE%\jarvis-memory-eval` (`eval_memory.py:1060`), and runs the
  learner test in the same run (`:720-723`). **One gap, fixed:** it
  measures the memory code in **your Jarvis folder**, not this
  repository's: when `JARVIS_BACKEND` holds a `jarvis_memory.py`, that copy
  is imported first (`eval_memory.py:141-146`). An out-of-date install would
  give old numbers. The page now says to run `apply-patches.ps1` first.

---

## 9. What I changed

| File | Change |
|---|---|
| `jarvis-desktop/tests/fixtures/plain-error-cases.json`, `jarvis-client/app/src/test/resources/contract/plain-error-cases.json` | Refreshed (the humour fields) |
| `tools/gen_plain_error_cases.py` | Always a fresh settings folder, never the caller's |
| `backend/test_manner.py`, `test_email_send.py`, `test_focus.py`, `test_web_search.py`, `test_reach.py` | One freshness check each, the existing `test_asks_first.py` shape |
| `backend/asks-first.patch` (+ `backend/patch-history/`, regenerated) | The lock-screen line for "tell me when" names web-page watches |
| `backend/test_asks_first.py` | A comment said github_search "asks" at `auto`; it is refused |
| `docs/MEMORY-SCOREBOARD.md` | "Run apply-patches first"; a dated row for the later learning changes |
| `docs/PERSONA-MODES-CHECK-2026-09-27.md` | A dated correction: the humour setting existed, and it does conflict |

**Overlap with the other passes, said plainly:** `asks-first.patch` holds
a `jarvis_gate.py` risk line, and the security pass may also be editing
the gate's lines. The edit is one line, and the line count did not change.
I **proposed but did not make** changes in three places other work is
touching: `jarvis-desktop/src/settings.html` (the FAQ; the settings pass),
and `backend/jarvis_second_card.py` and `docs/SECOND-CARD.md` (findings
1b-1d; the builder working on the combined lane).

---

## 10. What I could not check, and why

- **Anything on a real graphics card:** real `nvidia-smi` output, whether
  the 14B fits beside chat (1b), real speed. The second card is not
  installed, and this container has no GPU.
- **Anything with the real model:** the memory self-test with the meaning
  search and the re-ranker (`fastembed` is not installed here), the real
  learner, whether the humour lines change what Jarvis actually says.
- **The phone:** no Android build here (`dl.google.com` is blocked), so
  none of the phone's own tests ran. I read their Kotlin: the refreshed
  fixture keeps `PlainErrorsTest.kt`'s manner test valid (it reads named
  keys and adds `manner`/`available`, which the fixture does not have).
- **The desktop pages in a browser:** Playwright is not installed here, so
  no `tests/*.mjs` ran, and nothing was rendered (contrast, layout, the
  script-filled buttons). The desktop's plain-errors test reads named keys
  only, so the four new fields should not break it. CI will say for sure.
- **`cargo test`:** needs Windows. No Rust was changed, so no Rust check
  was needed.
- **Your own files:** `jarvis_gate.py` (the risk line for
  `change_own_config`), `jarvis_hud.py` (the event stream's keep-alive).
- **The combined-lane feature being built right now:** left alone, as
  asked. Findings 1b and 1c are about the version already committed.

---

## 11. Questions for you

**Question 1 - Humour.** Today, Jarvis's always-on character rules already
allow "a light, dry touch" of humour, so the humour switch being off does
not stop it. And "Plain" plus humour tells Jarvis two opposite things.

- **Off means no humour at all, and Plain wins over humour** (recommended).
  Jarvis gets "no humour" when the switch is off. With Plain chosen, the
  humour switch does nothing. (It would be greyed out in both apps, with a
  line saying why.)
- **Leave it as it is.** A little dry humour stays possible even with the
  switch off.

Either way, the memory self-test is not affected. The recommended way
changes the words the model reads, so the behaviour test on the PC
(`tools/tool_eval`, the character cases) should be run again after it.

**Question 2 - Getting this work onto your phone and PC.** The phone app
and the desktop installer are only published from `main` and from the old
branch name, so nothing built on this branch reaches you until it is
merged.

- **Merge this branch's pull request when the audits are done**
  (recommended). Nothing else changes.
- **Also publish from this branch now.** One line in each of two workflow
  files. The branch name would need changing again next session.
