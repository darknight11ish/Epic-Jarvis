# F5 field-test matrix - 2026-11-03

**Wave:** F5, "explain and adjust any feature, function or setting", plus the read-a-link chat path.
**Repo:** `Epic-Jarvis-main`. **Harness:** [`probe_f5.py`](probe_f5.py) in this folder.
**BEFORE evidence:** [`post-f5-probe.txt`](post-f5-probe.txt), captured **2026-11-03 09:41:26 -08:00**
against the **live F3 build**.

## What "BEFORE" means, in this build's own words

The capture carries its own identity, so it does not have to be taken on trust:

- `/api/version` says `server=jarvis-hud api=1`, and its `started` stamp is
  **2026-11-02T14:10:10 -08:00** - that is the running process, not a rebuild;
- the **F4** habits route answers `404 {"error": "not found"}`, so this capture is before the F4
  deploy as well as before F5 (the harness prints that line as `wave`);
- the F5 routes do not exist at all - **there are none to exist**: the plan's own §8 says *"F5 adds
  no route"*, and the worktree's diff confirms it (no new `PATH`, no new `handle_get`).

So **every A verdict in this file is an F3 verdict**, and every A cell has to be re-run after the F5
deploy. Nothing here is a claim about F5.

## How to read a row

Every feature is **two rows**, graded differently on purpose - the same split as
[`MATRIX.md`](MATRIX.md):

- **Sub-Row A - automated live probe.** A `GET` against the live backend on this PC. It can be
  **PASS**. What it proves is narrow and it is written on the row: the route exists, the answer is
  well-formed, and the value in it is true of this PC.
- **Sub-Row B - needs the owner's voice or thumb.** Saying the sentence, reading the spoken line,
  answering a card, hearing Live pause. Nobody but the owner can drive it, and he is not at the
  machine today, so every B row is **BLOCKED-owner-away**. **BLOCKED is never counted as a pass**
  (`docs/FIELD-TEST-MATRIX-2026-10-11.md`).

Row ids are one number per feature (`F5-01` ... `F5-10`) with the letter for the sub-row
(`F5-01A` / `F5-01B`), the same convention as the F4 matrix.

## The F5 wave

| Row | Feature (the owner's words) | Sub-Row A: the automated live probe | A verdict on live F3 | Sub-Row B: what only the owner can do | B verdict |
|---|---|---|---|---|---|
| **F5-01** | **Explain a setting** - what it is, where it lives, its current value, the exact phrase that changes it | **F5-01A** - `explain-door`: there is **no GET door**. `GET /api/chat` answers `404`, and an answer is only produced by `POST /api/chat`; the supporting read `feature-guide-tool` shows the read-only explaining tool is offered (`feature_guide_offered=True`, 11 tools) | **BLOCKED** - the sentence can only be produced by `POST /api/chat`; a GET never reaches the intent matcher | **F5-01B** - ask *"where do I change the weather source, and what is it set to?"* and judge the four facts in the words | **BLOCKED-owner-away** |
| **F5-02** | **The fourth fact has a live reader** - the current value is read from the module that owns it | **F5-02A** - six value probes, all `200`: `value-antislop` (`mode=during enabled=False`), `value-personality` (`warm_peer`, one of 10 published presets), `value-focus-preset` (`general`, one of 9), `value-sky-show` (`show=True`, a real bool), `value-weather-source` (`off`, one of `off/home_assistant/open_meteo`), `value-animal-switches` (7 switches, 7 bool values, in step) | **PASS** (read only) - the readers exist and answer truly of this PC. **A PASS is the reader, not the sentence** | **F5-02B** - ask for each value by voice and hear whether it matches what the Settings page shows | **BLOCKED-owner-away** |
| **F5-03** | **Every** setting's value - the 35 bools, `small_approvals`, voice speed and speaker, `live_idle_seconds` | **F5-03A** - **no probe, and no invented route.** There is no route that lists setting values (`/api/settings`, `/api/explain`, `/api/feature_guide` all answered `404` when checked at 09:37); the 35 bools are read inside an answer through `jarvis_feature_guide.read_state`, and the three named values have no GET route at all | **BLOCKED** - not in this build, and not reachable read-only in any build: the only door is `POST /api/chat` | **F5-03B** - pick three settings at random on the Settings page, ask about each, compare | **BLOCKED-owner-away** |
| **F5-04** | **Never a default dressed up as the value** - *"I could not read its current value on this PC, so I will not guess."* | **F5-04A** - `value-never-a-default`: the sentence only ever appears inside an answer, and provoking it means making a reader fail - a write to this PC. No GET can force it | **BLOCKED** - only `backend/test_setting_explain.py` (local) can force an unreadable reader; pretending a live probe proved it would be inventing evidence | **F5-04B** - with a module stopped, ask by voice and hear the honest sentence instead of a number | **BLOCKED-owner-away** |
| **F5-05** | **A cardless change leaves one undo receipt** - change it, then say "undo" | **F5-05A** - `receipts-read` (`200`: `count=20`, `undo_action=undo_action`, `undo_tier=ask`, per-row `undone`/`undone_at`, the "already undone" words) then `settings-receipt-undoable`. The list happens to hold **20 `change_setting` receipts and none is `undoable`** - i.e. **this build holds no settings restorer and cannot put a setting back** | **BLOCKED** - a change is a `POST /api/chat` turn, and the receipt half is honestly absent from this build | **F5-05B** - say "turn off the Anti-Slop filter", then "undo", then look at what changed | **BLOCKED-owner-away** |
| **F5-06** | **Undo applies once** - a second undo refuses and changes nothing | **F5-06A** - `undo-applies-once`: the guard's *state* is readable (`undone` + `undone_at` on every row, and the `"already"` words are in the payload), but applying it is `POST /api/receipts/<id>/undo` and "once" needs it applied twice | **BLOCKED** - two POSTs are the only proof; this harness never sends one | **F5-06B** - say "undo" twice and check the second answer and that nothing moved | **BLOCKED-owner-away** |
| **F5-07** | **A carded setting change** - one card, Live pauses, one calm spoken line, no spoken approval | **F5-07A** - **no probe, by design.** A card exists only when a change raises one: `POST /api/chat` (or `/api/approve` to answer it). The read side (`/api/pending`) is already covered by the F4 harness's `approvals-read`, **PASS** on F3 | **BLOCKED** - raising a card needs a POST; answering one changes state | **F5-07B** - ask for a carded change in Live and watch: one card, Live paused, one calm line, no spoken yes | **BLOCKED-owner-away** |
| **F5-08** | **Read a link in chat** - "read this link / this YouTube video", one card per link, a non-link refused | **F5-08A** - `read-link-reader-carded` (`200`: the YouTube caption row is `state=on`, `asks=Yes, every time`, `where=youtube.com` - the reader the intent hands a link to, proven **without fetching anything**), then `read-link-intent`. The `read_link` intent lives inside the chat matcher; a non-link refusal and one-card-per-link can only be provoked by `POST /api/chat` | **BLOCKED** - the intent has no GET surface in any build; only the reader's own registration is provable here | **F5-08B** - paste a real link by voice and by typing, and decline the card once | **BLOCKED-owner-away** |
| **F5-09** | **THE OWNER'S DECISION, 2026-11-03: the page-reading tool stays unswitchable** | **F5-09A** - two independent surfaces, both `200`: `page-reader-not-switchable` (`/api/asks_first`: `read_web_page` is in `not_offered.tier_c`, **not** in `switchable`, **not** in the app's `tools.items`; `switchable_tools=12`) and `page-reader-reach-line` (`/api/reach`: its own row is `state=off`, `offered_to_model=False`, and its sentence still names the settings file) | **PASS** - the boundary is intact. **This probe's PASS bar is the decision**, so if F5 ever makes the page reader offerable, this row turns **FAIL** - that is the decision being violated, not a harness fault | **F5-09B** - open Settings > "What asks first" on the PC and the phone and confirm no switch for the page reader appears | **BLOCKED-owner-away** |
| **F5-10** | **The only write path is the settings registry behind `change_setting`** (never a free-form settings-file edit) | **F5-10A** - `settings-write-tool` (`200`: `change_setting_offered=True`, 11 tools). **Narrow on purpose:** it proves the registry door is the offered one. The "no module writes `jarvis-framework.toml`" half is a **code-suite** fact (`backend/test_settings_registry.py`), not a live one | **PASS** (narrow, as worded) | **F5-10B** - ask for a setting that is not in the registry and hear the honest refusal, with no card | **BLOCKED-owner-away** |

Supporting reads that are not features of their own but show the harness was talking to a healthy
backend, both **PASS** on F3: `build-identity` (`server=jarvis-hud api=1 capabilities=18`) and
`data-health` (`checks=6 warn=0`).

## Counts on live F3, from `post-f5-probe.txt`

| verdict | probes (19) | sub-rows A (10) | sub-rows B (10) |
|---|---|---|---|
| PASS | 14 | 3 (F5-02, F5-09, F5-10 - all "read only") | 0 |
| FAIL | 0 | 0 | 0 |
| BLOCKED | 5 | 7 | 10 (all BLOCKED-owner-away) |

The 19 probes are not 1:1 with the 20 sub-rows: two probes are the capture's own health/identity
reads, one A row has two probes (F5-09), one has none by design (F5-07), and one has a supporting
read behind a BLOCKED row (F5-01).

## The decision pinned in F5-09, and why it is pinned at all

`F5-PLAN-2026-11-03.md` §5.3 and its commit 5 proposed the opposite: move `read_web_page` from
`TIER_C` into `TIER_A` so a Settings switch could offer it. **The owner decided on 2026-11-03 that it
stays unswitchable**, and the F5 tree carries that decision: `backend/jarvis_asks_first.py:419` still
has `read_web_page` in `TIER_C`, `:426` still has `TOOLS_SWITCHABLE = TIER_A + TIER_B`, and
`_TOOL_TARGETS` (`backend/jarvis_settings_registry.py:1371-1376`) still names only four tools - none
of them the page reader. `backend/jarvis_reach.py:590` (`_tool_switchable`) and `:660` (`_off_line`)
therefore still say "settings file only".

That is exactly why F5-09A is written as a **decision pin**: a PASS means "the boundary is intact",
and a FAIL after the deploy is the signal that the decision was quietly reversed. It is the F5
counterpart of the F4 matrix's `def028-live-words` row, whose PASS bar is the fix rather than the wire.

## Where the row names come from (so they can be checked)

There are no new route names to check - F5 adds none. The behaviour behind each row was read out of
the **F5 build worktree**, `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\F5-2026-11-03\wt`,
at **HEAD `ee9d5105e`** with the F5 edits **uncommitted** (it was mid-edit by two other agents while
this matrix was written; it is a moving target, so these are content claims about that tree at
09:35-09:40, not about `main`):

| What the row relies on | Read from |
|---|---|
| the fixed honest sentence | `backend/jarvis_settings_registry.py:4120` (`UNREADABLE_VALUE_WORDS`), used by `_now_phrase` (`:4327`) |
| one reader per setting kind | `:4279` `current_value`, `:4140` `_choice_now`, `:4227` `_number_now`, `:4244` `_animal_now`, `:4255` `_sky_show_now`, `:4264` `_weather_source_now` |
| the explain door itself | `:4450` `find_explain_setting`, `:4538` `explain_setting_words` |
| the read-a-link intent and its refusals | `backend/jarvis_quick.py:3482` `_read_link_intent`, `:13577` `READ_LINK_NO`, `:13589` `READ_LINK_NO_URL`, `:13726` `_run_read_link` |
| the settings receipt and its restorer | `jarvis_quick.py:14598` `_restore_settings_change`, `:14684` `_settings_receipt`, `:14716` `RC.register_restorer(SETTINGS_RECEIPT_TOOL, ...)`; `:16526` `_run_settings_undo` |
| the undo's once-only guard | `backend/jarvis_receipts.py:713` `is_undoable`, `:738` `_claim` (one conditional `UPDATE ... WHERE undone_at IS NULL`), `:233` `WORDS["already"]`, `:227` `LIST_PATH` |
| the page reader's tier | `backend/jarvis_asks_first.py:419` (`TIER_C`), `:426` (`TOOLS_SWITCHABLE`); `backend/jarvis_reach.py:1495` `_read_web_page`, `:590` `_tool_switchable`, `:660` `_off_line` |
| the suites that prove the halves live cannot | `backend/test_setting_explain.py`, `backend/test_read_link.py` (both new in that worktree), plus the extended `test_settings_registry.py`, `test_settings_tool.py`, `test_live.py`, `test_live_parity.py` |

**The one detail that changes what "after the deploy" means.** `register_restorer` is called **inside
the change path** (`jarvis_quick.py:14716`), immediately before the receipt is written - **not at
import**. So F5-05A cannot turn PASS from the deploy alone: the live process learns the settings
restorer only when one cardless setting change has run in it. Until then `undoable` stays `false` and
this row stays BLOCKED - honestly, not as a fault.

## What this matrix does NOT say

- **No B row is a pass.** The owner is away; every row that needs his voice, his thumb or his ears is
  BLOCKED-owner-away and stays that way until he is at the machine.
- **No A row is a claim about F5.** Every A verdict above was measured on **F3**. Seven of the ten A
  cells are BLOCKED, and five of those are BLOCKED because **the only door is a POST** - not because
  a route is missing.
- **A PASS on F5-02 is the reader, not the sentence.** `/api/antislop` answering `mode=during` says
  the value is readable; it says nothing about whether the sentence Jarvis speaks about it is right.
- **The receipts in the list are context, not evidence.** At capture time the list held 20
  `change_setting` receipts stamped **09:37:13 - 09:41:14**, i.e. **another process on this PC was
  writing them while this was being read** (this harness only reads; it cannot write a receipt).
  They name real setting keys (`antislop_mode`, `face`, `voice_speaker`, `small_approvals`,
  `todo_carryover`, `one_moment`, `lights_without_card`, `second_card_*`), and at least one of them
  did **not** take effect on the live build: the receipt says `antislop_mode` went `during -> after`,
  while `/api/antislop` still answered `mode=during` at 09:42. They are recorded as exactly what they
  are - test output that landed in the owner's real receipts store - and are **never** counted as
  proof that the live build can put a setting back. The live build's own answer says it cannot
  (`0 undoable`).
- **That other process is worth a look after the deploy.** The F5 suites are supposed to point at a
  temporary folder before they import anything (`backend/test_setting_explain.py` does exactly that),
  so a run that wrote into the owner's own receipts store is either a suite that missed that step or
  a run with the config folder pointed at the live install. It moved no setting this harness can
  read, but the rows it left are real rows in the owner's list.
- **F5-09A is a decision pin, not a defect detector.** A FAIL there means "the page reader became
  switchable", which is the owner's decision being violated - not a harness fault.

## After the F5 deploy

1. Run the harness again, from the repository root:

   ```powershell
   python .dsh-scratch\FIELD-TEST-2026-11-03\probe_f5.py | Tee-Object .dsh-scratch\FIELD-TEST-2026-11-03\post-f5-deploy-probe.txt
   ```

2. Copy the new verdicts into the A cells, leaving each `was ...` note in place so the F3 reading
   stays visible (the older matrices' convention). Re-check the `live build` and `wave` lines first:
   if `wave` still says F3, the run is a BEFORE run again, whatever the date.
3. **What should flip, and what cannot:**
   - `settings-receipt-undoable` may flip to **PASS**, but only after one cardless setting change has
     run in the live process (see the `register_restorer` note above).
   - `explain-door`, `value-never-a-default`, `read-link-intent` and `undo-applies-once` **stay
     BLOCKED** after any deploy: they need a POST. That is the honest shape, not a gap to close.
   - `page-reader-*` must **stay PASS**. A FAIL there is the decision being reversed.
   - The six `value-*` probes should stay PASS. If one turns FAIL, a module's reader changed or broke
     and that is a real finding.
4. Fill a B row only when the owner has actually driven it. Until then it is **BLOCKED-owner-away** -
   never "probably fine".

## Not probed, and why

- **`POST /api/chat`** - the explain sentence, the "could not read it" sentence, and the `read_link`
  intent with its refusal of a non-link. One POST each; the harness is GET-only by construction, and
  the capture prints these doors in a `NOT PROBED READ-ONLY, BY DESIGN` block.
- **`POST /api/receipts/<id>/undo`** - applying an undo, and refusing the second. Two POSTs.
- **`POST /api/approve` / `/api/deny`** - answering a setting's card. The card is the feature;
  answering it changes state.
- **`GET /api/youtube`** - deliberately not called. It is the Quiz page's async route and its `start`
  path fetches captions; a probe must not fetch anything, and the reader's registration is provable
  from `/api/reach` without it.
- **`GET /api/chat`** - it is probed, but only to prove the door is POST-only. It answers `404`.
- **Anything that writes.** No card approved or denied, no setting changed, no undo applied, no link
  fetched, no Live session started, no pairing. The five request paths all go through
  `probe.call()`, which is `method="GET"` and nothing else.

## AGENT-DRIVEN EVIDENCE — 2026-11-03 evening (never counted as an owner PASS)

**Provenance.** The owner delegated the field-test driving to the paired DeepSeek session. Every row below was driven against the live Jarvis backend on this PC through the same `POST /api/chat` the HUD uses - header `X-Jarvis-Client: hud`, `stream: true`, and the newest user turn carrying `"provenance": "typed"` - on 2026-11-03 evening. The full answers and the raw logs are in `AGENT-DRIVEN-RESULTS.md` and the `agent-drive*.log` / `agent-drive*.json` files in this folder.

**The grading rule, in plain words.** These rows are graded **AGENT-DRIVEN (AGENT-PASS)**. They are evidence, **NOT** owner field PASSes, and they must never be added to any owner-PASS count or tally - every table and count above stays exactly as it is. The project rule says a probe PASS is not a field PASS, and an agent is not the owner (`docs/FIELD-TEST-MATRIX-2026-10-11.md`). The agent typed the sentences and read the answers back; that is not the owner speaking them, hearing them, or judging them by ear or eye. Every owner-only row remains **BLOCKED** exactly as it was.

**Words used here.** A *card* is the approval card Jarvis shows before a change. A *receipt* is the little record that lets `undo` put a change back.

**Live state.** The run put back what it touched. The sun-and-moon switch was turned off and then back on; the final read is `/api/sky` -> `{"show": true}`, which is where it started, and the `undo` inside the chat set the same value back. Anti-Slop was turned on by an early attempt and turned back off; `/api/antislop` -> `{"enabled": false}`. No approval card was raised by any row (`pending: []` before and after each row), and no card was ever approved or denied. This is as recorded in `AGENT-DRIVEN-RESULTS.md`; this section does not re-read the live backend.

**The F5 B rows recorded in this section.**

| Row | What was driven | Result (AGENT-PASS / AGENT-PARTIAL) | One-line evidence | Owner PASS? |
|---|---|---|---|---|
| **F5-01B** | Asked `how do i change the weather source` - the phrasing the fast path accepts (the page's own compound question does not; see open finding 1 below). | **AGENT-PASS** | Four facts in the answer: what the setting is ("Weather behind the face", a choice in Settings), where it lives, its current value **Off**, and the exact sentences `set the weather source to off` / `... home assistant` / `... open meteo`; turning Open-Meteo on asks on a card. The earlier read-only probe `value-weather-source` (F5-02A above) read `off` as well. | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F5-02B** | Asked for three settings in one row: `what is the anti-slop filter set to`, `how do i change the personality`, `how do i change the sun and moon`. | **AGENT-PASS** | Each answer cross-checked against the module that owns it: anti-slop **off** matches `/api/antislop` (`enabled=false`); personality **Warm Collaborator** matches `/api/manner` (`manner=warm`); sun and moon **on** matches `/api/sky` (`show=true`). | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F5-03B** | Asked `how do i change the jarvis live timeout`. | **AGENT-PASS** | The answer gives the current value (**1 minute and 30 seconds**), the range (**30 seconds to 10 minutes**), and the sentence `set the jarvis live timeout to 3 minutes`. No GET route re-read this value; it is recorded as the answer stated it, as written in `AGENT-DRIVEN-RESULTS.md`. | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F5-05B** | Said `turn off the sun and moon` (a cardless, receipted setting), then `undo`. | **AGENT-PASS** | Change: "The sun and moon are no longer shown." with no card; undo: "The sun and moon now show behind the face."; `/api/sky` went `true` -> `false` -> `true`. The row above names the Anti-Slop filter instead, and that setting writes no receipt - that is open finding 2 below. | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F5-06B** | Said `undo` a second time. | **AGENT-PASS** | The second undo answers "I already put the sun and moon back in this chat, so there is nothing left to undo." - it refuses, and `/api/sky` stays `true`, so nothing moved. | **No** - still BLOCKED-owner-away, because an agent is not the owner. |
| **F5-09B** | Driven twice: the live tool lists, then the phone's Settings screen. | **AGENT-PASS** (screen + API) - moved up from AGENT-PARTIAL when the phone lane drove the screen. | API: `read_web_page` is in `not_offered.tier_c`, absent from `switchable`, and absent from the app's `tools.items`. Screen (phone build 0.2.3635): Settings > "What asks first" shows the page-reader row as text only - "Read a web page out loud - Asks you first, every time" plus "Always asks. This cannot be changed from an app." - a TextView with `checkable=false`, `clickable=false`, and no toggle anywhere near it; 149 labels were saved in order. Evidence: `PHONE-DRIVE.md` and the `phone/` dumps. | **No** - still not an owner PASS, because an agent is not the owner. |
| **F5-10B** | Asked `change the warp drive calibration to nine`. | **AGENT-PASS** | "I don't recognize 'warp drive calibration' as a setting I have on this PC..." - an honest refusal, and no card was raised (`card_raised=False`, `pending: []`). | **No** - still BLOCKED-owner-away, because an agent is not the owner. |

**Not recorded here.** F5-04B, F5-07B and F5-08B were not driven - they stay BLOCKED exactly as written above. Nothing in this section changes any count in this file.

### Open findings from this run

Both findings below are **NOT FIXED** and **NOT filed in the defect register yet**. They are follow-up material from this agent-driven run, and neither of them blocks the accounts PR.

1. **Page sentences the fast path rejects fall through to the local model, which then answers wrongly or invents capabilities.** - **NOT FIXED, and NOT filed in the defect register yet.** Four sentences from the click-through page were seen failing (the full transcript is in `AGENT-DRIVEN-RESULTS.md`):
   - "which model is answering me, and why that one?" - the model answered about itself and **invented a card offer** for a cloud model.
   - "where do I change the weather source, and what is it set to?" - the model sent the owner to Home Assistant's `configuration.yaml`, **wrong on both facts**: Jarvis's weather source is `off/home_assistant/open_meteo` in its own settings file, and it is set to **Off**.
   - "list my plugins" - the model said it had no plugin-list function, while the plugin list is a real chat tool.
   - "which apps on my phone may you open?" - the model **invented capabilities** (email, calendar, reminders, contacts, photo access); the real answer is that the allow-list is empty.
   The accepted phrasings are in `AGENT-DRIVEN-RESULTS.md`; the page itself needs correcting.
2. **The Anti-Slop toggle is a cardless change that writes no settings receipt, so a following "undo" cannot take it back.** - **NOT FIXED, and NOT filed in the defect register yet.** `turn on the anti-slop filter` really does change the setting (`/api/antislop` `enabled=true`; raw log `agent-drive-undo.log`), but no settings receipt is written, so the next `undo` answers "There is nothing here for me to take back." The F5 claim that a cardless change leaves one receipt is therefore **false for this one setting**. The receipted path that does work is the registry/animal path, which the sun-and-moon row above exercises.
