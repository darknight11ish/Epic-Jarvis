# Audit #1 (bugs, backend half) and #12a (Jarvis's own tools)

Tree: `scratchpad/integ` at deaca649 (`audit-integration`). Scope: the backend
Python files, `.patch` files and `scripts/apply-patches.ps1` changed in
`git diff 9cdb0567..HEAD` (193 files). Nothing in the repo was edited.

## In one paragraph

The backend suites have no new failures: the only real failures are the 4
already-known "is last in the list" ones. The biggest real problem is in the
plan card ("One card, several steps", switched off today). It does not do two
of the four things its own design promises. (1) The one plan card shows each
step's tool name and the model's reason, but **not the step's actual
arguments**, such as the note's text. (2) A step marked "risky" or "uses an
earlier result" says on the card that it "asks again on its own card", but for
any tool whose setting is `auto` it runs **without asking at all**. Also, a
"result-filled" step is never filled in from the earlier result, so the
feature cannot do what it says. Nothing can reach this today because the plan
card is switched off, but it must be fixed before the safety test turns it on.
One small new misfire: "call my mum's phone" rings the owner's own phone. Every
other model tool I checked is registered, goes through the approval gate,
marks outside text, and has a test.

## Test run

- `backend/run_suites.py` on a copy of the tree (venv at `scratchpad/venv`):
  **171 passed, 5 failed, 19 skipped.**
  - 4 of the 5 are the known combined-tree failures: `test_brain_reads`,
    `test_forget_range`, `test_history_import` and `test_photo_remind`. Each
    one fails only on "X.patch is last / install sits right before the main
    socket", because live/forget-range/sky now come after it.
  - The 5th, `test_patch_history`, failed only because my copy has no git
    history. **I re-ran it in the real integ tree: 24 passed, 0 failed.** It
    changed no files; `git status` was clean before and after.
- **No real failures beyond the known 4.** (The earlier `suites3.txt` run also
  showed `test_voice_contract` failing on stale fixtures. HEAD's "voice
  fixtures regenerated" commit fixed that, and it passes now.)

---

## Findings

### F1 - Plan card: the one card does not show the steps' arguments (medium; the feature is switched off) - checked in code
Branch: continuation-03kls1 (7e7d9253, 7675da4d).

- **What's wrong:** the plan card lists `tool - why` for each step. It never
  shows the step's arguments, so a "safe" step runs with values the owner never saw.
- **Evidence:** `backend/jarvis_plan.py:196`
  `lines.append(f"  {i}. {s.tool} - {s.why}{tag}")`. The file's own condition
  1 (line 24) says: "Every step is shown, in full, exactly as its own card
  would show it - `describe()` below, never a vaguer summary."
- **Why it matters:** an unmarked step whose tool is `auto` (for example
  `append_obsidian_daily`, `memory_search` or `calendar_read` in the shipped
  `rebuilt/jarvis-framework.toml`) runs with no card of its own. The owner
  approves "append_obsidian_daily - log it" without seeing the text that gets
  written.
- **Fix (code change):** in `describe()`, add each step's arguments in full,
  e.g. `json.dumps(s.args, ensure_ascii=False)`. Better still, add the text
  that tool's own `prepare()` produces; `_plan_step_dispatch` already builds
  that. The existing `_card_would_be_cut` check then refuses a plan whose card
  gets too long.

### F2 - Plan card: "risky" and "from_step" steps do not really ask for `auto` tools (medium-high once switched on) - checked in code
Branch: continuation-03kls1.

- **What's wrong:** the card promises "[asks again on its own card before it
  runs]" (`jarvis_plan.py:192-195`). But `_plan_step_dispatch` hands the step
  to `checker(action_name, ...)` at the tool's **own** tier
  (`jarvis_agent.py:919`). For an `auto` tool the gate says yes silently. The
  docstring admits it at `jarvis_agent.py:859`: "(or is silently
  auto-approved, for an auto-tier tool)". Only the `NEEDS_A_PERSON` tools are
  forced to ask.
- **Why it matters:** the card tells the owner something that is not true.
  Two examples from the shipped settings file:
  - A step "risky: true, append_obsidian_daily" is written with no card.
  - A `from_step` note write after an `email_check` step is also written with
    no card. That also breaks the 2026-09-24 rule that note writes after
    outside text wait for a yes. The direct tool path gets this right
    (`_one_call` escalates to `NOTE_AFTER_OUTSIDE_ACTION`), but the plan path
    does not apply `note_needs_a_person()` at all.
- **Test gap:** `test_agent_plan_wiring.py::_risky_or_from_step_case` only
  uses `home_control`, whose tier is `ask`, so this gap is not tested.
- **Fix (code change):** in `_resolve`, when `step.needs_own_card` is true
  (or when a reading step has already run in this plan), make it a real
  person's yes:
  - call the checker with a forced-ask action (the way `NOTE_AFTER_OUTSIDE_ACTION` does);
  - then require `_a_person_said_yes(verdict)`, as for `NEEDS_A_PERSON`;
  - add a test with an `auto` tool marked risky.

### F3 - Plan card: a "result-filled" step is never filled in (medium, functional) - checked in code
- **What's wrong:** `from_step` is only a flag. Nothing copies the earlier
  step's result into this step's arguments. `grep -n "\.args"` finds only
  `jarvis_agent.py:892` (`check_call(step.tool, step.args, ...)`). The step
  runs with whatever the model guessed when it wrote the plan.
- **Why it matters:** condition 2 in `jarvis_plan.py` promises the step is
  "asked again, individually, with the real value it would actually use". The
  step's own card shows the proposal-time guess instead. So the feature cannot
  do its main job, a step that depends on an earlier one.
- **Fix:** this is the owner's call on the design. Either
  - let the model fill in the step again after the earlier result, as a new
    tool round (then the step's own card is truthful), or
  - drop `from_step` and say plainly that a plan cannot use results.

### F4 - Plan steps bypass the per-step outside-text bookkeeping (low) - checked in code
- **What's wrong:** each plan step's result goes straight into the plan's
  result. Only the whole plan result goes through `watch.took_in("propose_plan", ...)`,
  at `jarvis_agent.py:6550`.
- **What this causes:**
  - "Where this came from" (`jarvis_sources.from_tool_result`) gets no sources
    for an email or a web page read inside a plan.
  - A later card's "Proposed after Jarvis read: ..." line says
    `propose_plan (once)` instead of "your email". `_READ_LABELS` has no label
    for it (line 4329).
- The taint itself does still happen, because `propose_plan` is not in
  `_NOT_READING`, so later tools in the turn do see outside text.
- **Fix:** call `watch.took_in(step.tool, out)` inside `run_step`.

### F5 - `propose_plan` is offered to the model even while it is switched off (low) - checked in code
- **What's wrong:** `offered_tools()` (`jarvis_agent.py:3630-3652`) hides
  `browser_control` and `my_files` when they cannot work. It does not hide
  `propose_plan` while `jarvis_plan.enabled()` is False.
- **Why it matters:** if `[tools].enabled` names it, every turn spends its
  description tokens (about 150) on a tool that always answers "refused: the
  multi-step safety test has not been run". An 8B model will sometimes try it
  instead of doing the steps one by one. Also, `jarvis_reach.py` has a label
  for it (line 118) but no `_NEEDS_A_PERSON` fallback entry (lines 139-141),
  unlike `jarvis_agent.NEEDS_A_PERSON`.
- **Fix:** add `if "propose_plan" in wanted and not jarvis_plan.enabled()[0]: wanted.discard("propose_plan")`
  to `offered_tools()`, and add `propose_plan` to the fallback set in
  `jarvis_reach.py`.

### F6 - "call my mum's phone" rings the OWNER's phone (low-medium) - checked in code (ran it)
Branch: audit-competitors-vyqpt1 (30bca340).

- **What's wrong:** `_RING` (`jarvis_quick.py:1562`) takes any name before
  "phone": `(?:ring|call|buzz|beep)\s+(?:my|the)\s+(?:(?P<name>[a-z][a-z' ]{0,20}?)\s+)?(?:phone|...)`.
  I ran `jarvis_quick.match()` on these sentences:
  - `"call my mum's phone"` gives `phone_ring`
  - `"call my work phone"` gives `phone_ring`
- **Why it matters:** the owner meant to call someone. Instead Jarvis rings
  the owner's own phone at full volume, on the alarm channel, through silent
  mode, with no model involved and no chance to say "no". The reply is
  "cannot tell your phones apart", which hides what really went wrong.
- **Fix (code change):** only take the name when it has no `'s`, and only
  from a short list of phone words (work, personal, other, old, new, own,
  android, second). Anything else goes to the model:
  `(?P<name>work|personal|other|old|new|own|second|android)`.

### F7 - New gate actions have no line in the shipped settings file (low) - checked in code
- **What's missing:** `phone_notifications_read`, `run_plan` and
  `propose_plan` have no line in `backend/rebuilt/jarvis-framework.toml`'s
  `[autonomy.tiers]`. `memory_forget_range`, `chatbot_session` and
  `github_read` were added.
- **Why it matters:** each missing one falls back to `unknown_action_tier = "ask"`, which is safe.
  - `jarvis_phone_notifications.request` insists on tier "ask" and works.
  - `run_plan` asks, which is correct.
  - `propose_plan` should be `auto` per `plan-gate.patch`. With no line it
    asks, so a proposal would raise an extra card when the feature is switched on.
  - The "What asks first" page lists what the file names, so these rows may be missing there. Unverified.
- **Fix:** add `phone_notifications_read = "ask"`, `run_plan = "ask"` and
  `propose_plan = "auto"`, each with a comment.

### Checked and found sound (no finding)
- **Warm-up with words** (`jarvis_agent.warm_prefix`, `_turn_begins`,
  `_send_warm`): the race between a warm-up and a question starting is handled
  under `_LIVE_LOCK` at every step. A turn that starts before the socket is
  handed over is caught by the `call.cancelled` check.
- **Big tool results cut shorter** (`_tool_content`, `_shorten_*`,
  `clear_old_tool_results`): the JSON always stays whole, and the outside-text
  label is never cut.
- **Crisis turns** (`note_crisis_turn` / `note_correction`): bounded, under
  a lock, and a "wrong" mark on a crisis turn is not counted. That closes the
  "written down, not fixed" item in CLAUDE.md.
- **"Remind me next time"** (`jarvis_next_time`): matches only the owner's
  own words, has a cooldown, 3 fires, 90 days, and a voice turn skips a
  sensitive one.
  - `set_extra` touches only jobs still on the list, and the lock is an RLock, so no deadlock through `fields()`.
- **Scheduler changes:**
  - `extra` column and `until_words` are fine.
  - `wall_at` checks the date.
  - The photo reminder's "already passed" refusal works.
  - The 10-minute-late rule (`LATE_RING = 600` in `jarvis_tellme.py`) is untouched by this diff.
- **Phone notifications** (`jarvis_phone_notifications.py`):
  - off by default; ON takes one card, OFF is instant;
  - it withdraws a waiting card, fails closed on a damaged file, and requires tier `ask`.
- **Price, page, search and GitHub watches:**
  - fetches go through `public_urlopen` / `private_fetch_problem`;
  - the GitHub token goes only in a header to `api.github.com`, with redirects refused (`_GitHubNoRedirect`).
- **Local chatbot:** refuses cloud models, including `-cloud` and `:cloud` tags, and only talks to this PC.
- **Chatbot replies:** marked as outside text, never learned from, and never read aloud.
- **Lockdown** now reaches the MCP start card, the tool-update check and web search. In each place, if Lockdown cannot be read, it asks.
- **apply-patches.ps1:** the new lines have no PowerShell-7-only syntax (`??`, `?.`, ternary). The patch order passes `test_patch_history` in the real tree.
- **SQL:** every `f"..."` query I found builds only column or table names from fixed lists (`_KEYS`, fixed `sets`). No owner text is put into SQL.

**Not covered in depth** (too large for one pass, so no claim either way):
`jarvis_chatbot*.py` (about 8k lines), `jarvis_live.py`, `jarvis_mouth.py`,
`jarvis_sky*.py`, `jarvis_speech.py`, `rebuilt/jarvis_memory.py`'s
tie-breaker, and `import_history.py`. I only grepped them for the usual kinds
of bug.

---

## #12a - Every tool Jarvis can use

**Tier** = the shipped `rebuilt/jarvis-framework.toml` line for the gate
action the tool resolves to. "person" means the tool is in `NEEDS_A_PERSON`:
it runs only after a real yes on a card, whatever the tier says.

**Taints** = its result goes through `_TurnWatch.took_in`, so it counts as
outside text for the rest of the turn. Every tool does, except
`calculator`/`send_email`/`draft_email` (`_NOT_READING`, line 3118) and the
scheduler tools, which return only the owner's own list.

**Phone** = can a chat from the phone reach it. Model tools run inside
`/api/chat` on the PC, so a phone chat reaches all of them.

**Test** = a suite that names it. I checked each with grep.

### Model tools (`jarvis_agent.TOOLS`, 26, plus `more_tools`)

| tool | tier (gate action) | taints? | PC | phone | test | problems |
|---|---|---|---|---|---|---|
| calculator | auto (no gate action) | no (result is worked out here) | yes | yes | test_agent | - |
| memory_search | auto | yes | yes | yes | test_injection_cases, test_private_aloud | - |
| file_read | auto (`read_files_readonly`) | yes | yes | yes | test_documents, test_gate_fixes | Overlaps `my_files` (older); the `instead` hints separate them |
| shell_exec | ask + person (`run_shell_on_host`) | yes | yes | yes | test_agent, test_gate_fixes | - |
| control_computer | ask + person (`jarvis_ui_control_run`) | yes | yes | yes | test_agent, test_approval_contract | - |
| control_phone | ask + person | yes | yes | yes | test_agent | - |
| browser_control | ask + person; offered only with the second card's lane | yes | yes | yes | test_gate_fixes, test_reach | - |
| github_search | person; action depends on token | yes | yes | yes | test_agent, test_tool_text | - |
| web_search | `search_the_web` ask; asks only when one of the reasons applies (`_web_search_call`) | yes | yes | yes | test_agent, test_asks_first, test_web_search | Inside a plan it always asks (stricter; see F2 for the plan path) |
| calendar_read | auto | yes | yes | yes | test_calendar_link, test_briefing | - |
| email_check | auto (`email_read`) | yes | yes | yes | test_briefing, test_email_draft | - |
| send_email | ask + person; refused before prepare off this PC / after outside text | no (its own confirmation) | yes | yes | test_email_send, test_approval_contract | - |
| draft_email | ask + person | no | yes | yes | test_email_draft | - |
| notes_search | auto | yes | yes | yes | test_integrations_wiring | - |
| my_files | auto (`file_read` → read_files_readonly); offered only while a folder is listed | yes | yes | yes | test_documents, test_sources | - |
| home_read | auto | yes | yes | yes | test_integrations_wiring | - |
| home_control | ask + person (lights-without-card setting is the one bypass) | yes | yes | yes | test_asks_first, test_card_words | Inside a plan it gets no lights bypass (stricter, documented) |
| append_logseq_journal | auto; escalated to `write_notes_after_outside_text` (ask) after outside text | yes | yes | yes | test_agent, test_injection_cases | Escalation missing on the plan path (F2) |
| append_obsidian_daily | auto; escalated likewise | yes | yes | yes | test_gate_denial_rule | same |
| create_joplin_note | notify; escalated likewise | yes | yes | yes | test_note_capture | same |
| **propose_plan** (NEW) | `run_plan` → unknown → ask; + person; refused unless `jarvis_plan.enabled()` and turn untainted | yes (as one lump, F4) | yes | yes | test_agent_plan_wiring, test_plan | **F1, F2, F3, F4, F5, F7** |
| set_timer | no card (SCHEDULE_TOOLS); refused after outside text | no | yes | yes | test_schedule, test_short_tool_list | - |
| set_reminder | no card; same | no | yes | yes | test_schedule, test_smarter_answers | - |
| todo_add / todo_done | no card; same | no | yes | yes | test_quick_wins, test_schedule | - |
| coming_up | no card, read-only | no | yes | yes | test_schedule, test_private_aloud | - |
| more_tools (short list, off by default) | none, opens a group; "opened after outside text" is noted on the next card | - | yes | yes | test_short_tool_list, test_mcp_wiring | - |
| plug-in (MCP) tools `mcp__<server>__<tool>` | own action, not known to the gate, so it asks; plus person (`OUTSIDE_PROGRAM_WHY`); a card to start the server, every start under Lockdown | yes | yes | yes | test_mcp_wiring | - |

**Checks on the list as a whole:**
- **Registered and reachable:** all 26 are in `TOOLS`, and every one is either
  in `CORE_TOOLS` or in exactly one `TOOL_GROUPS` group. `test_short_tool_list`
  enforces this.
- **No orphans:** every tool has both a `prepare` and an `execute`. The
  scheduler tools' dummy `execute` is never reached, because
  `_schedule_call` handles them first and they are excluded from plans.
- **No two tools doing the same job:** `file_read` and `my_files` overlap, but
  both are older, and the `instead` hints tell the model which to use.
- **Descriptions:** short and plain. `propose_plan`'s is the longest new one,
  at about 420 characters.
- **"Model cannot use tools" message:** `NO_TOOLS_NOTE` (line 2585) is only
  sent after Ollama's own `/api/show` capabilities list leaves out "tools",
  and the 400 error text says the same thing. Both are true.
- **Never learned as a fact:** tool output goes back to the model as `role:"tool"`
  with the outside-text label. The learner only learns from the owner's own
  turns (`jarvis_intake.owner_turns`).

### Not model tools: quick commands answered without the model (`jarvis_quick.py`)

These are new in this diff. They run only on the owner's own typed or spoken
newest message: `newest_own_words` accepts only `typed` or `voice`, and
refuses when there is a system message, a share or clipboard text, or a
picture.

| intent | card? | phone | test | notes |
|---|---|---|---|---|
| forget_range | never removes anything; fills in the Brain list, then ONE card (`memory_forget_range` ask) | yes | test_forget_range | - |
| lockdown_on / _off / _status | on: at once; off: this PC only, card + Windows Hello | yes (off refused from phone) | test_lockdown | "lock it down" also turns Lockdown on; harmless because it only makes things stricter |
| next_time_set / _list / _cancel | no card (owner decision) | yes | test_next_time | - |
| pc_help | read-only; marks program names as outside text | yes | test_pc_help | - |
| phone_ring / phone_stop | no card (owner decision) | yes | test_find_phone | **F6** |
| project_log | no card; health/money benchmark kept on screen | yes | test_projects | - |
| tellme_price / _search / _github | one card each (like other "tell me when") | yes | test_tellme_watches | - |
| today_set / _list / _remove | no card (owner decision) | yes | test_today | - |
| where_put | reads saved facts; `route_fields` marks memory and sensitive facts | yes | test_places | - |
| widget_make | calls the LOCAL learner model with a fixed menu; refused in a tainted chat | yes | test_widgets | The one quick command that uses a model (documented) |

**Other new abilities that are not tools the model can call (by design, and tested as such):**
- Chatbot talk / compare: `/api/chatbot/*`, one card per conversation or comparison.
- Projects and Goals: their own routes; Goals "never acts".
- Phone notifications: only a setting. Text reaches a chat as a `shared`
  message, which counts as outside text.
- Screen "Look at this" and the Live camera: `STEP_READS` names only. No route
  or tool exists yet.
- Photo to reminder: `test_photo_remind` checks "not a tool the model can call".
- Brain reads: `test_brain_reads` checks the same.
- History import and the app workspace.
