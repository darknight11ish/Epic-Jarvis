# The prompt coach: audit, and the settings it now has

**Date:** 2026-10-09 · **Branch:** `feat/prompt-coach-settings` · **Scope:** the
"Coach this" prompt coach in all three parts of Jarvis - the Python backend
(`backend/jarvis_prompt_coach.py`), the Windows desktop
(`jarvis-desktop/src/`, `src-tauri/src/prompt_coach.rs`) and the Android app
(`jarvis-client/.../net/PromptCoach.kt` and the two plates that draw it).

**The one-line answer to the owner's verdict.** *"Make sure it's effective and
has multiple settings, including an enable and disable"*: it had exactly one
setting (an on/off switch, off by default) and no settings surface beyond a
single toggle. It now has **four more settings beside that switch**, every one
of them defaulting to the behaviour it already had, and a **per-AI awareness**
of which model or service a prompt is headed for, with a visible date and a
file that keeps it current.

**Is it effective?** As an advisor, yes for what it claims and no for what it
does not claim. Every fence the design makes in words is held by a test that
reads the module's own source: it never sends, never approves, never leaves the
PC, keeps nothing. **Nothing in this repository measures whether coaching
HELPS** - only that it fires, refuses properly, and (now) that the four settings
change what it says. That is written down in §4 and in `JARVIS-API.md` §120.9
rather than left implied.

---

## 1. What it does, and whether it ever touches the owner's prompt

**It advises. It never changes the prompt and never sends anything.**

- The module's one entry point returns text: `coach()` builds a prompt, calls
  the local model once and returns a dict (`jarvis_prompt_coach.py:1168`), and
  `handle_post` turns that into `{"ok": true, "coach": {...}}` or a plain-sentence
  refusal (`:1230`). There is no send, no tool, no file and no card anywhere on
  the path.
- The promise is kept by a test that reads the source with docstrings and
  comments stripped and forbids the words entirely:
  `backend/test_prompt_coach.py`'s `t_it_approves_nothing_and_keeps_nothing`
  asserts no match for `jarvis_gate|owner_check|approve|deny`, no
  `subprocess|os.system|popen|eval(|exec(`, no `jarvis_memory|jarvis_auto_learn|
  jarvis_chat_log|remember|save_fact`, no logging, and that the only HTTP is
  `jarvis_local_http.urlopen` to the model on this PC.
- **The owner's words are never rewritten.** `coach()` reads `text`; the
  critique comes back with a separate `suggestion`. On the phone the two
  buttons are the only things that send, and they send what the owner picked:
  `PromptCoachBar.kt:214` (`onSendMine` → `sendMine()`, the box unchanged) and
  `:218` (`onSendSuggestion` → `sendSuggestion(pick)`). On the desktop the same
  two buttons call `sendMine`/`sendSuggestion` handed in by `main.js`
  (`prompt-coach-panel.js`'s `mine`/`send` click handlers).
- **It is not an interceptor.** Nothing in a chat turn or an approval path
  imports the module: `grep -n "prompt_coach" backend/*.py` finds only the
  module itself, its test, `jarvis_settings_registry.py` (the switch) and
  `_where.py` (the shipped-file list). The only route that reaches it is
  `/api/prompt/coach` (`backend/prompt-coach.patch`), and on both apps that is
  reached only by pressing **Coach this**.
- **The score is not a gate.** A 1 out of 10 is shown and both buttons stay
  live - `PromptCoach.parseCritique` clamps but never compares, and the desktop's
  `readCritique` does the same (`prompt-coach-panel.js:102-133`).

**One thing it does read that is not the box:** the last few turns, capped at 6
(`MAX_TURNS`, `:199`), so "it" and "that" have an antecedent. That was the
owner's own answer of 2026-10-08.

## 2. Does "disable" truly disable? Yes - and the answer is worth its evidence

| Where | What stops | Evidence |
|---|---|---|
| The module refuses every call | `coach()` raises `Refused(OFF_LINE)` before anything else is looked at | `:1168-1180`; `OFF_LINE` at `:114` |
| A damaged/missing setting file | `enabled()` fails to **off**; a non-`bool` `enabled` fails to off | `setting()` `:804`, `enabled()` `:840`; tests `t_off_by_default_and_fails_closed` |
| The POST route | `{"enabled": false}` is instant, no card | `handle_setting` `:1245`; `set_enabled` `:873` |
| The desktop bar | The "Coach this" button is **not drawn at all**, and any open panel is wiped | `prompt-coach-panel.js`'s `paintButton()` (hidden unless `on()`) and `wipe()` |
| The desktop Settings card | Shows the switch off after a re-read; neither direction is held on a stale link | `prompt-coach-settings.js`; `prompt_coach.rs` (no `StreamState`) |
| The phone | The bar shows no button when the PC says off; the settings switch is greyed only while the link is down | `PromptCoachBar.kt`, `PromptCoachPlate.kt:47+` |

**"At once, in both apps":** yes. Both apps' switches go to
`POST /api/prompt/coach/setting`, which writes one JSON file; there is no cache
on either side, and the desktop bar and the phone bar each re-read the switch on
every show/focus (`prompt-coach-panel.js`'s `refresh()` on `visibilitychange`
and `focus`; `MainActivity.kt:1553` re-reads).

**The two honest gaps, both checked rather than assumed:**

1. **A critique already in flight is not cancelled by turning the switch off.**
   The off check happens at the start of `coach()`, so a press that is already
   running finishes and shows its advice. It cannot send anything - the panel's
   two buttons are the only senders, and they go down the chat's own path. The
   next press is refused with the PC's own sentence.
2. **Nothing else calls it.** A disabled coach on the phone still leaves the
   *settings* rows visible (so the owner can turn it back on) and greys the
   controls while the link is stale; that is the intended shape, and the desktop
   has no stale-link gate on this card at all, by design, because this feature
   takes no action.

## 3. What settings existed today (before this change)

**One**, and no settings surface of its own:

- `enabled`, a boolean, off by default, in `prompt-coach.json` in the PC's
  settings folder (`SETTINGS_NAME`, `:62`; written by `set_enabled`, `:873`).
- Registered as a `BoolSetting("prompt_coach")` with `Section("prompt-coach")`
  in `backend/jarvis_settings_registry.py:670` / `:211`, so it is reachable by
  voice ("turn on the prompt coach") as well as by both apps' switches.
- Classified `ported` in `tools/check_parity.py:103-104`, which is why the
  phone must keep reading its words from the PC
  (`PromptCoachPlate.kt`, `net/PromptCoach.kt`).
- **No generated settings row.** `tools/gen_settings_cases.py` is **not on
  `main`** (checked: `tools/` has 60 `gen_*.py` files and that is not one of
  them), so the claim that `settings.html`'s toggle rows are spliced between
  markers does not hold in this checkout yet. The prompt-coach card in
  `jarvis-desktop/src/settings.html:904` is **hand-written markup**, and this
  change edited it by hand - which is why the four rows are drawn at runtime
  from the PC's own data instead of being written into the HTML (see §5).

## 4. Is it effective? What the tests prove, and what nothing measures

**What is proven.** `backend/test_prompt_coach.py` runs with **no model at all**
(`ask=` is an injectable seam) and covers, in its own words:

- the switch fails to off for a missing file, a damaged file and a non-boolean
  value (`t_off_by_default_and_fails_closed`);
- the local-address check happens **before** the request is built, asserted from
  the source's own order and again in behaviour, with the model never asked
  (`t_the_local_check_comes_first`);
- a critique comes back whole, including the last few turns and the schema
  (`t_a_critique_comes_back_whole`);
- **"nothing to say" is a real answer**, and a model that claims `clear` while
  listing gaps is not believed (`t_nothing_to_say_is_a_valid_answer`,
  `t_clear_is_not_taken_at_its_word`);
- five kinds of malformed answer are refusals, never a half-filled card
  (`t_a_bad_answer_is_a_refusal_never_half_a_card`);
- the fences of §1 (`t_it_approves_nothing_and_keeps_nothing`);
- both routes (`t_the_routes_own_half`).
- **New in this change:** the four settings default to today's behaviour and
  fall back to it when damaged; one moves without touching the others; an
  unknown key or value is refused in words naming the real ones; `speaks_up:
  weak` really holds advice back (and says so, in the PC's own sentence, rather
  than showing an empty list); `platform: quieter_phone` really trims; `bluntness`
  and `coaches_on` really reach the model's own instructions; `status()` carries
  every choice's name and line for both screens; every AI the chatbot driver
  offers has a row; an unknown AI is reported, never guessed at; an owner's own
  `prompt-coach-targets.json` can correct one field or add a whole target, and a
  row older than 180 days says so.

**What nothing measures - said plainly.** There is **no test that coaching
helps**. Nothing compares a prompt with its answer before and after coaching,
and no feedback signal is wired to the coach: the thumbs-up/down buttons mark a
chat turn (`feedback.patch`), not a critique, and the coach contributes no count
to anything. `docs/PROMPT-COACH-DESIGN.md` already said the 8B model is a
mediocre prompt critic; that stands, and the app's own `DETAIL` line says so on
screen. **Nobody has run this against the real model on the owner's PC**, so
neither the quality of the advice nor its latency is measured.

**The failure modes, each checked:**

| Failure mode | What happens | Evidence |
|---|---|---|
| Coaching during an approval card | **Can happen, on purpose, and is harmless.** The coach reads nothing about the approval queue and raises no card. `PROMPT-COACH-DESIGN.md` choice B says why: it opens no way out of the PC and acts on nothing. It cannot delay, answer or repeat a card | design §B; `prompt-coach.patch` never touches the gate |
| A crisis message | **Not excluded, and not harmful.** The coach is not in a chat turn and its output is never compared with the wellbeing path; the critique goes nowhere and is kept nowhere, so nothing about a crisis turn is stored, counted or logged. It is reachable only by pressing the button on words the owner typed | `t_it_approves_nothing_and_keeps_nothing`; `wellbeing.patch` untouched |
| An error turn | The coach never sees an answer - only the box and the last few turns | `coach()`'s `history` argument |
| Repeating itself | **Two different answers.** Pressing **Coach it** twice with the same words is two model calls and can give two different critiques (temperature 0.1, not 0) - only the on-screen copy is replaced. The *advice panel* never repeats on its own: it is redrawn only by a press or a re-read of the switch | `_ask`'s `temperature: 0.1`; `refresh()` |
| Delaying a turn | **It delays itself, never a turn.** It is off the send path: the words go to the chat whether or not a critique is on screen. But a press holds the button and keeps the panel open for up to 120 s (PC, `TIMEOUT_SECONDS`) / 150 s (desktop, `COACH_TIMEOUT`) while the model loads | `:203`, `prompt_coach.rs` `COACH_TIMEOUT` |
| Firing when the prompt was already good | **This was the real one, and it is now a setting.** Before this change the coach always answered a press with whatever it could find, and `PROMPT-COACH-DESIGN.md` admits the 8B model will confidently "improve" a fine prompt. `speaks_up: weak` now holds the advice back for anything the model itself scored 7 or more, and the screen says which happened | `parse()` `:997`, `WEAK_BELOW` `:187`, `NOTHING_WEAK` `:189` |

## 5. What was built

### 5.1 The four settings

Declared in **one place**, `jarvis_prompt_coach.SETTINGS`
(`backend/jarvis_prompt_coach.py:133`), each as
`(key, names, default, {value: (word, line)})`, and handed to both apps by
`status()` → `settings_rows()` (`:1281`, `:1300`). **Neither app holds a copy of
any setting's name or explanation**: the desktop draws what it was sent into
`#coach-groups` (`jarvis-desktop/src/prompt-coach-settings.js`), and the phone
draws the same rows in `PromptCoachSection`
(`jarvis-client/.../ui/screens/PromptCoachPlate.kt`). A new choice therefore
appears in both apps by changing one Python tuple.

| # | Setting | Values | Default | What it changes | Where it is applied |
|---|---|---|---|---|---|
| 0 | `enabled` (the master switch) | on / off | **off** | Whether there is a Coach this button at all | `enabled()` `:840`; `coach()` `:1168` |
| 1 | **When it speaks up** (`speaks_up`) | `any` = "Whenever it has something to say" · `weak` = "Only when the prompt is weak" | `any` | On `weak`, a prompt the model itself scored 7 or more is passed with no advice, `advice_given: false` and the PC's own sentence | `parse()` `:997`; `WEAK_BELOW = 7` `:187` |
| 2 | **How blunt it is** (`bluntness`) | `gentle` = "A gentle nudge" · `direct` = "Direct about what is wrong" | `gentle` | The words the local model is told to use | `prompt_for()` `:1101` |
| 3 | **What it coaches on** (`coaches_on`) | `shape` = "Shape only - length and clarity" · `content` = "Content too - missing details and the wrong task" | `shape` | Whether the model also judges the task and what was left out | `prompt_for()` `:1101` |
| 4 | **Per-platform behaviour** (`platform`) | `same` = "The phone behaves the same as the PC" · `quieter_phone` = "Quieter on the phone" | `same` | On `quieter_phone`, at most 2 gaps and 2 questions are shown | `parse()` `:997`; `MAX_ISSUES_QUIET`/`MAX_MISSING_QUIET` `:192` |

**Every default is today's behaviour**, so a switch the owner already had keeps
meaning what it meant. They live in the **same file** as the switch
(`prompt-coach.json`), so `jarvis_backup.py` already picks them up; a key that
is missing, or holds a value that is not one of its own choices, falls back to
its own default — never to a guess. `set_choice()` (`:884`) refuses an unknown
key or value with a 409 naming the real ones.

**Where they are declared, and the two collisions that were live:**

- **`jarvis_prompt_coach.SETTINGS` is the table.** Not
  `jarvis_settings_registry.py`'s `BOOL_SETTINGS`, because these are not
  booleans and the registry's setter contract is one `on: bool`.
- **`settings.html` rows are not generated in this checkout**:
  `tools/gen_settings_cases.py` is **not on `main`** (see §3), so there are no
  markers to splice between. The card's markup was edited by hand **to add one
  empty container**, and every word inside it comes from the PC at runtime. When
  that generator lands, the card's markup should move under it; the
  *declaration* is already in the one right place.
- **No new phone settings place was needed.** `MenuPlaces.SETTINGS`
  (`MenuPlaces.kt:26`), `OpenPlace` (`:57`), `SettingsJump` (`:35`) and
  `SETTINGS_ITEM_INDEX` (`SettingsScreen.kt:109`) already declare
  `prompt-coach`, so the four rows live inside the existing row and none of the
  four unit tests that guard those maps was relaxed.
- **No new route, and no new Tauri command.** The route stays
  `/api/prompt/coach/setting` (which the phone already calls, so
  `tools/check_parity.py` is untouched), and the desktop's one command
  `set_prompt_coach` now takes a single `CoachChange { enabled, key, value }`
  (`src-tauri/src/prompt_coach.rs`). One route, one command, one permission
  pair, no `DYNAMIC_BELOW` entry.

### 5.2 Which AI the prompt is headed for

The owner: *"make sure it is aware of what model of cloud AI I am using because
each kind has their own intricacies and make sure this can stay up to date."*

- **Where the notes live.** `jarvis_prompt_coach.DEFAULT_TARGETS`
  (`:274`), one row per AI, each with `name`, `kind`, `context`, `quirks`,
  `style`, `checked` (the date it was last verified) and `source`. There are
  **16 rows**: the local Ollama model, the six API services the chatbot driver
  can use (read from `jarvis_chatbot_api.PRESETS` — OpenAI's `gpt-5-mini`,
  DeepSeek, Mistral, Grok/xAI, OpenRouter, Groq) and the nine website adapters
  (`jarvis_chatbot.ADAPTERS` — Gemini, ChatGPT, Claude, Copilot, Perplexity,
  DeepSeek's site, Grok's site, Le Chat, Meta AI).
- **How a new model is added.** Three ways: (1) a service or website with no
  row is listed by `unknown_targets()` (`:687`) and **`test_prompt_coach.py`
  fails while that list is not empty**, so a new AI cannot arrive unnoticed;
  (2) a row in `DEFAULT_TARGETS`; (3)
  **`prompt-coach-targets.json`** in the Jarvis settings folder — the owner's
  own rows, laid over the shipped ones **field by field** (so one quirk can be
  corrected without retyping the row, and the shipped `source` and date survive
  unless the owner gives their own), or a brand-new target, which needs a name
  and gets today's date. `from_file()` (`:513`) reports every reason a row was
  refused rather than half-reading one, and a file that cannot be read is one
  plain sentence while the shipped table still answers.
- **How it stays up to date.** Every row carries its own `checked` date. A row
  older than `STALE_DAYS` (180, `:270`) says *"may be out of date"* in the app
  and to the model. A date that cannot be read counts as stale — an undated
  claim is not a fresh one.
- **What happens when Jarvis does not know the target — the part that must not
  drift: it SAYS SO.** `advice_for()` (`:651`) returns `known: false`, an empty
  quirk/style list and a plain sentence naming the thing the owner named; the
  critique carries it; and the local model's own instructions say, in as many
  words, that Jarvis does not know this AI and **must not guess, describe how it
  behaves, or invent a claim about it**. There is no nearest-name match and no
  fallback to the local model's notes. `resolve_target()` (`:602`) matches a
  chatbot id, an adapter id, the short name typed at a terminal (read from each
  preset's own `short` field), an alias, or the row's own display name —
  normalised for case, punctuation and underscores.
- **Nothing about a target changes where the critique runs.** Still this PC's
  model, still `jarvis_auto_learn.check_local_model()` **before** the request is
  built, still nothing sent anywhere. A cloud model never receives the prompt:
  the notes about it are instructions to the local critic.

### 5.3 The phone's half

- `net/PromptCoach.kt`: `Group`/`Choice` types and `groups()`, which reads the
  PC's rows and **drops** a row with no key, no choices or a value that is not
  one of its own choices (half a row is a picker nothing is selected in);
  `choiceBody(key, value)`; `saidChoice(...)`; and `Critique` extended with
  `adviceGiven`, `said` and `target` (a `Target` with `known` and `stale`).
- `ui/screens/PromptCoachPlate.kt`: draws one group per row and one radio row
  per choice, all words the PC's.
- `ui/screens/PromptCoachBar.kt`: the "nothing to say" line is now the PC's own
  sentence when the advice was **held back** (`advice_given: false`), which is a
  different thing from finding nothing; and a footer under the critique names
  the AI and what Jarvis knows about it, in the PC's words, with the heading
  chosen by the PC's own `known`.
- `JarvisApi.setPromptCoachChoice` and `JarvisRuntime.setPromptCoachChoice`
  mirror the switch's path, including the stale-link gate.

### 5.4 Tests added or extended (each fails without its change)

- `backend/test_prompt_coach.py` — 18 new checks in 12 new test functions (§4).
- `jarvis-desktop/tests/prompt-coach.mjs` — **new**, and picked up
  automatically by CI's "every desktop test suite" loop (`for f in tests/*.mjs`).
- `jarvis-client/.../PromptCoachTest.kt` — **new**, 9 tests.
- `jarvis-desktop/src-tauri/src/prompt_coach.rs` — one new `#[test]`,
  `the_four_settings_ride_on_the_calls_that_already_existed`.
- `backend/test_base_matches_repo.py` was **already failing on `origin/main`**
  before this branch: `jarvis-backend/jarvis_prompt_coach.py` was the 479-line
  published copy while `backend/`'s was the 1,679-line one. Copying the module
  across (which is what that suite's own message asks for) turns its 12 passed,
  1 failed into **13 passed, 0 failed**.

**One red herring, recorded so nobody chases it.** The only odd-looking output
this branch produced was `check_claims.py` reading a Gradle lock file while a
Kotlin build held it. Section 5.5 explains it, with the clean re-run.

### 5.5 Verification actually run (real output)

```
py -3 tools/check_parity.py            -> "No undecided drift."                          exit 0
py -3 tools/check_invoke_grants.py     -> "318 command(s) invoked from 11 page(s); every one is granted"   exit 0
py -3 tools/check_command_acl.py       -> "357 commands, generate_handler! and build.rs agree."             exit 0
py -3 tools/gen_menu_cases.py --check  -> "menu-cases.json (both copies), MenuCatalog.kt and menu-catalog.js match"  exit 0
py -3 tools/check_feature_list.py      -> "122 entries in 9 groups; 5 passed, 0 failed"                     exit 0
py -3 tools/check_claims.py            -> "125 claim(s) checked against the code: 93 built, 25 still open,
                                           7 unverifiable ... Every `built` claim still holds"              exit 0
py -3 backend/test_prompt_coach.py     -> "all checks passed"                               exit 0
py -3 backend/test_base_matches_repo.py-> "13 passed, 0 failed"                             exit 0
py -3 backend/test_shipped_modules.py  -> "594 passed, 0 failed"                            exit 0
py -3 backend/test_settings_registry.py-> "114 passed, 0 failed"                            exit 0
py -3 backend/test_referee.py          -> "105 passed, 0 skipped, 0 failed"                 exit 0
py -3 backend/test_devices.py          -> "275 passed, 0 skipped, 0 failed"                 exit 0
py -3 backend/test_gate_risk_rows.py   -> "11 passed, 0 failed"                             exit 0
node tests/prompt-coach.mjs            -> 10 checks, all ok                                 exit 0
cd src-tauri && cargo test prompt_coach -> 7 passed, 0 failed                               exit 0
cd jarvis-client && gradlew testDebugUnitTest -> BUILD SUCCESSFUL, 1981 tests, 0 failures, 0 skipped
```

**The whole sweep was attempted and abandoned on time, not on a failure.**
`py -3 backend/run_suites.py` runs every suite that can run without the owner's
PC and took far longer than the work allowed; it was stopped, and instead every
suite this change can reach was run on its own - the fourteen above. Nothing
that failed is unlisted, and the two known non-failures are named below.

**Two commands that fail for reasons unrelated to this change, both checked.**

1. `py -3 backend/test_settings_registry.py` **exits 1 with `JARVIS_BACKEND`
   set**, printing *"Not run: this suite would have tested this repository's
   copy instead of the one your backend uses."* That is `_where.py`'s
   `require_shipped` (`:564-597`) doing its job: this session's environment
   points `JARVIS_BACKEND` at the owner's real backend folder, whose
   `jarvis_prompt_coach.py` is an older copy. **With it cleared the suite is
   114 passed, 0 failed.** It is the trap the brief warned about, and it is not
   a code failure.
2. `py -3 tools/check_claims.py` failed once with a Gradle lock file
   (`jarvis-client/.gradle/9.6.0/checksums/checksums.lock could not be read
   ([Errno 13] Permission denied)`) while a Kotlin build held it. Re-run with no
   build running: exit 0.

**Baseline for the Kotlin**, measured on `origin/main` at `facba013` in this
same worktree before any change: **1,972 tests, 0 failures, 0 skipped**. After
this change: **1,981** — the 9 new `PromptCoachTest` tests, and **none
regressed**. The task's "1,974 currently pass" was 2 higher than this checkout's
own measurement; the important numbers are the ones taken here.

## 6. What is still blocked or not done

1. **`tools/gen_settings_cases.py` is not on `main`.** A generated toggle row is
   what the brief described; this checkout has none, so the prompt-coach card's
   markup is hand-written and was edited by hand (one empty container, no words
   of its own). Nothing was invented to look generated.
2. **No voice control for the four.** `jarvis_quick.py`'s grammar covers the
   `BoolSetting` `prompt_coach` and none of the four, so
   `jarvis_settings_registry.py` is unchanged and nothing claims otherwise.
3. **No measurement of whether coaching helps.** See §4.
4. **Nothing has run against the real 8B model.** Every suite here uses the
   `ask=` seam; the advice's quality and latency are the owner's to judge.
5. **The desktop settings card is not covered by a screenshot test**, though its
   rows are covered by headless-browser assertions in `tests/prompt-coach.mjs`.

## 7. The risk

- **The four settings change what the coach says, and one of them changes what
  the owner SEES.** `speaks_up: weak` can make a press produce "nothing was weak
  enough to flag" instead of a list. It is off by default (the default is
  `any`), so nothing changes until the owner chooses it, and both apps say which
  happened rather than showing an empty panel.
- **The per-AI notes are written from this repository's own evidence and are
  dated, not verified against each company today.** A wrong quirk is a wrong
  instruction to an 8B critic. That is why every row carries its date and its
  source, why a row older than 180 days warns on screen and to the model, and why
  an unknown target is reported rather than guessed.
- **`set_prompt_coach`'s argument shape changed** from `{ enabled }` to
  `{ change: { enabled } }`. The page and the command ship together in the same
  app, so there is no mixed-version window; but a *third party* calling the
  command by name would need the new shape, and the Rust test and
  `tests/prompt-coach.mjs` both pin it.
- **The one real behavioural discovery of this work**: Tauri binds a page's
  arguments to a command's parameters **positionally**, so three loose `Option`s
  turned `{key, value}` into `enabled = <the key>`. It was caught by
  `tests/prompt-coach.mjs` before it could ship, and fixed by taking one struct.
  Anyone adding a field to this command must keep it inside `CoachChange`.
