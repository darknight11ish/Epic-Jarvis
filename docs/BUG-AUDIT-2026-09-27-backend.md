# Bug audit of the Python backend - 2026-09-27

Scope: `backend/*.py` (the shipped modules), `backend/*.patch` and
`scripts/apply-patches.ps1`. Code that had never had a bug audit came first:
`jarvis_tool_updates.py`; `jarvis_second_card.py`'s "One bigger model on both
cards" mode and its new "suggest the bigger model" logic (with the counters in
`jarvis_agent.py`, `second-card-suggest.patch` and the new offer kind in
`jarvis_backoff.py`); `jarvis_settings_registry.py` and its wiring into
`jarvis_quick.py` ("open"/"turn on" a setting, and "open a chat"); and whether
`schedule.patch` and `briefing.patch`, which both edit the same `/api/chat` lines,
still build the right file. After that, a lighter sweep of the rest.

## In plain words (for the owner)

1. **I found no break of the five rules.** Nothing private leaves the PC by a new
   route, nothing is approved without a person, and the "only from this PC"
   check for loosening "What asks first" works the same from chat as from
   Settings.
2. **The new "suggest the bigger model" feature never actually suggests
   anything.** Jarvis only checks at the end of a chat answer, but the rule
   "never offer while the owner is chatting" was switched on at the start of
   that same answer. So the check is always told "not now", and nothing checks
   again later. The tests did not notice, because they skip the "you are
   chatting" step.
3. **The two "When to suggest the bigger model" switches in both apps cannot
   work.** The backend code for them exists, but no patch connects it to the
   server's web address (`/api/second-card/suggest`), so pressing either switch
   will get an error.
4. **"One bigger model on both cards" promises more than it does.** Its card
   says "Every answer then runs at roughly that card's pace", and the new
   suggestion says "A bigger model may do better with this". But nothing sends
   any chat to that bigger model yet (the code says so itself). Saying yes starts
   a copy of Ollama that sits unused.
5. **"Check for tool updates" ignores a later "never".** After your first yes,
   it never looks at your settings file again. If you later set it to "never",
   the "What asks first" page says it is switched off, but the button still
   contacts PyPI, crates.io and GitHub. It also tells you to run
   `cargo update -p <name>` for 61 Rust parts that cargo refuses to update by
   that name.
6. **Smaller problems:** two second-card switches can both end up on if their
   cards are approved in a certain order; the Hardware screen wrongly says "the
   everyday Ollama is using the second card" while the bigger-model mode runs;
   "show me what Jarvis can reach" now opens Settings instead of reading the list
   out; the "you corrected me" count can go up twice for one correction, or for
   a sentence that was not a correction; and a picture sent after a crisis
   message is marked for the calm crisis panel, even though that answer has no
   help line in it.
7. **The patch stack builds correctly.** `schedule.patch` and `briefing.patch`
   apply in order with nothing lost. All 131 test suites pass (19 skipped because
   they need files that are only on your PC). `apply-patches.ps1` has no syntax
   that only works in PowerShell 7. All six problems from yesterday's audit are
   fixed in the code.

## Findings

| # | Severity | Where | One-line bug | Fix size |
|---|---|---|---|---|
| 1 | Medium | `jarvis_second_card._maybe_suggest_combined` + `briefing.patch` (`note_conversation`) | The bigger-model offer is always refused as "conversation", because the quiet-after-chat clock was stamped at the start of the same turn; nothing checks again later | Small (move the check out of the turn, e.g. onto a timer after `QUIET_AFTER_CHAT`) |
| 2 | Medium | no patch routes `POST /api/second-card/suggest` | Both apps' two "When to suggest the bigger model" switches post to a route the server does not have | Small (one route block in a patch) |
| 3 | Medium | `jarvis_second_card._describe_combined`, `_combined_status`, `SUGGEST_WHY`/`_suggestion_reason` | The card and the offer say answers will run on the bigger model, but `combined_lane()` has no caller, so no answer ever does | Words: small. A real caller: larger |
| 4 | Low-medium | `jarvis_tool_updates.request_check` | After the one-time yes, the tier is never read again: `check_tool_updates = "never"` does not stop the check going out to the internet | One line |
| 5 | Low-medium | `jarvis_second_card._decide` | A feature (or main-switch) card approved after "combined" was turned on writes both on. That is the state the 409 refusal exists to prevent, and then neither runs | A few lines |
| 6 | Low | `jarvis_tool_updates._rust_group` | Suggests `cargo update -p <name>` for 61 crates that are in Cargo.lock at two or more versions; cargo refuses that command as ambiguous | Small |
| 7 | Low | `jarvis_second_card._main_pin` | While "combined" runs, the Hardware screen says "The everyday Ollama is using the <second card> right now" (the combined lane's own process is not excluded) | One line |
| 8 | Low | `jarvis_quick._match` (`_settings_open` before `_REACH`) | "show me what Jarvis can reach / access" now opens Settings instead of reading the reach list | Small |
| 9 | Low | `jarvis_agent.looks_like_correction` + `second-card-suggest.patch` | One correction can count twice (typed words and a "wrong" mark, or wrong, then none, then wrong again), and some ordinary sentences count as corrections. The card would then state a wrong number | Small |
| 10 | Low | `wellbeing.patch` | The crisis-panel header check skips a picture message and reads an OLDER message, so a picture turn after a crisis message is flagged "crisis" although `run_local_turn` does not treat it as one | One line |

---

### 1. The bigger-model offer can never be made (Medium, certain)

**Evidence.** `/api/chat` notes the conversation clock first, before anything
answers (the stand-in of `jarvis_hud.py` built from the whole stack shows this
order; `briefing.patch`):

```
briefing.patch:111  +        # briefing.patch: the owner is talking to Jarvis now, so no offer
briefing.patch:112  +        # nobody asked for is put to them for two minutes (jarvis_backoff.py).
briefing.patch:116  +            jarvis_backoff.note_conversation()
```

The offer is checked only at the very end of that same turn:

```
jarvis_agent.py:4920        broken_this_turn = sum(watch.bad.values())
jarvis_agent.py:4921        if broken_this_turn:
jarvis_agent.py:4922            note_struggle(conv_id, broken_this_turn)
jarvis_agent.py:4923        _maybe_suggest_bigger_model(conv_id)
```

and `may_offer` refuses while less than two minutes have passed since that stamp:

```
jarvis_backoff.py:91    QUIET_AFTER_CHAT = 120.0
jarvis_backoff.py:358            if self.quiet_for(now) > 0:
jarvis_backoff.py:359                return False, "conversation"
```

`_maybe_suggest_combined` treats that as "not now" and returns
(`jarvis_second_card.py:2673-2674`). Nothing else calls it: the grep for
`maybe_suggest_combined` finds only this call site and the tests. So an offer is
possible only on a turn whose answer took more than two minutes.

The suite's positive tests (`t_offers_and_the_card_is_the_real_one`,
`t_a_no_is_heard_like_every_other_offer`) never call `note_conversation()`.
The one test that does, `t_backoff_holds_it_back_mid_chat`, asserts "no card",
and in real use every turn looks like that test.

**Reproduction (run).** `repro_offer.py` plays the real order six times: stamp
the clock, answer for 20 s, count one broken tool call, then run the end-of-turn
check:

```
turn 3: struggle count 3, cards raised 0, backoff says (False, 'conversation')
turn 6: struggle count 6, cards raised 0, backoff says (False, 'conversation')
```

**Smallest fix.** Keep counting at the end of the turn, but make the offer later:
for example, a one-shot timer (or the scheduler) that tries again once
`quiet_for()` reaches 0. Add a test that stamps `note_conversation()` first, the
way `/api/chat` does.

---

### 2. `POST /api/second-card/suggest` is not routed (Medium, certain for the patches)

**Evidence.** The function exists:

```
jarvis_second_card.py:414  def handle_suggest_post(body) -> tuple:
jarvis_second_card.py:415      """POST /api/second-card/suggest {"signal": "struggle"|"correction",
```

Both apps post to it (`jarvis-desktop/src-tauri/src/commands.rs:3468`
`SECOND_CARD_SUGGEST_PATH`, `jarvis-client/.../net/SecondCard.kt:536`
`SUGGEST_PATH`), and `docs/JARVIS-API.md:1809` documents it. But nothing outside
the module and its test calls `handle_suggest_post` (grep over `backend/*.py`,
`*.patch`, `*.ps1`). The only second-card POST route in any patch matches the
path exactly:

```
second-card.patch:47  +        if route == "/api/second-card":
second-card.patch:67  +            code, out = jarvis_second_card.handle_post(body)
```

`second-card-suggest.patch` only touches `/api/feedback/mark`. In the stand-in of
`jarvis_hud.py` built from the whole stack, the only `second-card` routes are
`/api/second-card` (GET and POST).

**What goes wrong.** Turning either "When to suggest the bigger model" switch off
in either app fails. What the owner's server answers for a route it does not know
was not checked, because `jarvis_hud.py` is not in this repository. Most likely it
is a 404. Reading the settings works, because they come back inside
`GET /api/second-card`.

**Smallest fix.** Add an
`if route == "/api/second-card/suggest": ... jarvis_second_card.handle_suggest_post(body)`
block (origin check, token check, JSON body) to `second-card-suggest.patch`, and
a `t_the_patch` check that the stand-in has it.

---

### 3. Saying yes to "combined" changes no answer, but the words say it does (Medium, certain)

**Evidence.** The module says it plainly:

```
jarvis_second_card.py:51   answer to being asked directly). `combined_lane()` still has no automatic
jarvis_second_card.py:52   caller (the gap above is still real - nothing SWITCHES combined mode on by
```

and grep finds no call to `combined_lane()` anywhere in `backend/` except its own
definition and tests. Yet the card says:

```
jarvis_second_card.py:2409  f"Ollama splits the model by how much FREE memory each card has right now, not by "
jarvis_second_card.py:2410  f"how fast each card is - so most of the model can land on the bigger, slower card. "
jarvis_second_card.py:2411  f"Every answer then runs at roughly that card's pace. ...
```

the offer adds `" A bigger model may do better with this."` (line 2608), and once
it is on, the Hardware row says `f"Working: {model} split across the ..."`
(line 2065).

**What goes wrong.** The owner is told "a bigger model may do better with this",
says yes, and every answer still comes from the everyday model on the main card.
The only change is an idle copy of Ollama on both cards. That is a claim the code
does not back (ARCHITECTURE invariant 6, CLAUDE.md "do not claim more than the
evidence supports"). Finding 1 hides this today.

**Smallest fix.** Either give `combined_lane()` a real caller in
`jarvis_agent.choose_lane`, or, until then, change the card's, the offer's and the
row's words to say plainly that no answer uses it yet, and do not offer it at all
(`maybe_suggest_combined` should return early while nothing can use the lane).

---

### 4. Tool updates: "never" in the settings file is ignored after the first yes (Low-medium, certain)

**Evidence.** Once `tool_updates.json` says approved, `request_check` starts the
check without reading the tier:

```
jarvis_tool_updates.py:762      if approved():
...
jarvis_tool_updates.py:776              spawn(lambda: _run_in_background(run))
jarvis_tool_updates.py:782      t = tier_of(ACTION)          # only reached when NOT approved
```

But "What asks first" treats this action as one whose looser or "never" line
switches the feature off:

```
jarvis_asks_first.py:154      "never": "Never - your settings file switches it off",
jarvis_asks_first.py:157  SAYS_REFUSED = "Refused - it only runs on your yes, so its line must say \"ask\""
jarvis_asks_first.py:444          if tier in ("auto", "notify"):
jarvis_asks_first.py:445              row["says"] = SAYS_REFUSED
```

**What goes wrong.** The owner (or a later decision) sets
`check_tool_updates = "never"`. The page says "Never - your settings file
switches it off". Pressing the button still sends every package and crate name
to pypi.org and crates.io. Only package names and version numbers go out, so no
private data leaks, but a named way out of the PC does not obey the one place
the owner turns it off. Later runs also write no audit line (only `_decide`
audits).

**Reproduction (run).** `repro_tu.py`: approved file present,
`tier_of=lambda a: "never"`:

```
tier never, after one earlier yes: 202 True check ran: True
```

**Smallest fix.** In `request_check`, read `tier_of(ACTION)` first. Answer 503
(the same sentence as today's) for anything but `"ask"`, approved or not.

---

### 5. A feature card approved after "combined" is on turns both on (Low-medium, certain)

**Evidence.** Asking for a feature is refused while combined is on, but the
refusal is checked only when the card is raised:

```
jarvis_second_card.py:2718    if enabled and _read_switches().get("combined"):
jarvis_second_card.py:2719        return 409, {"error": (f"{label} cannot be turned on: \"{COMBINED_NAME}\" is on, and "
```

After approval, `_decide` checks the main switch, the "needs" list and the card,
but not `combined` (lines 2367-2382). `_decide_combined` does make the matching
check in the other direction (line 2469, `_combined_conflict(cur)`), but
`_combined_conflict` only sees features that are already ON, not a feature card
that is still waiting.

**What goes wrong.** The owner asks for "Longer conversations" (its card waits),
then asks for "One bigger model on both cards" and approves that. Then they
approve the first card. Both switches are on. `_wanted` refuses the feature lane
because `combined` is on (line 1423), and `_combined_wanted` refuses the combined
lane because of the conflict (line 1493). Two yeses, and neither runs. The same
thing can happen when the suggestion's card is the combined one.

**Reproduction (run).** `repro_both.py` (the suite's `G.World` harness):

```
after both yeses: combined = True  long_context = True  conflict = True
```

**Smallest fix.** In `_decide`, after the withdrawn check, refuse with "One bigger
model on both cards was turned on while the card waited" when
`_read_switches()["combined"]` is true, for features and for the main switch.

---

### 6. Tool updates: `cargo update -p <name>` is ambiguous for 61 crates (Low, certain)

**Evidence.** Every `[[package]]` row is reported separately, and an outdated one
gets the bare name:

```
jarvis_tool_updates.py:575    for name, version in sorted(pins):
jarvis_tool_updates.py:587        "command": (f"cd jarvis-desktop\\src-tauri; cargo update -p {name}"
```

Today's `Cargo.lock` has 576 crate names, and 61 of them appear at two or more
versions (base64 three times, bitflags twice, and so on; counted with `tomllib`).

**Reproduction (run, dry run, nothing written):**

```
$ cargo update -p base64 --dry-run --offline
error: There are multiple `base64` packages in your project, and the specification `base64` is ambiguous.
Please re-run this command with one of the following specifications:
  base64@0.21.7
  base64@0.22.1
  base64@0.23.1
```

The older copies are held back by the version ranges of the crates that use them.
`cargo update` usually cannot move them to the newest version at all, and it never
crosses a new major version. That second point comes from how cargo works; it was
not reproduced here. Either way, the report tells the owner to run commands that
fail or do nothing, and reports the same crates as "outdated" again every time.

**Smallest fix.** Use `-p {name}@{version}` when a name appears more than once.
Better: report only the newest locked copy of each name, and say "held back by
another part" for the older ones instead of giving a command.

---

### 7. False "everyday Ollama is on the second card" while combined runs (Low, certain)

**Evidence.**

```
jarvis_second_card.py:1879    ours = _LANE.pids()
jarvis_second_card.py:1892    if ("ollama" in pname or "llama" in pname) and gpu in others and pid not in ours:
jarvis_second_card.py:1893        return False, (f"The everyday Ollama is using the {others[gpu]} right now, so "
```

`_COMBINED_LANE`'s processes are not in `ours`, and the combined lane runs on the
second card by design.

**Reproduction (run).** `repro_pin.py`: a stand-in combined-lane process listed by
the fake nvidia-smi on the second card:

```
(False, 'The everyday Ollama is using the RTX 2060 right now, so it can take memory the second-card features need. Run the command below, then restart Ollama.')
```

**Smallest fix.** `ours = _LANE.pids() | _COMBINED_LANE.pids()`.

---

### 8. "Show me what Jarvis can reach" now opens Settings (Low, certain)

**Evidence.** `_settings_open` runs before `_REACH` (`jarvis_quick.py:790` vs
`:802`), and the "reach" section's aliases are exactly those words:

```
jarvis_settings_registry.py:147  Section("reach", ("what jarvis can reach", "what jarvis can access")),
```

`_REACH` still has the matching phrasing,
`(?:show|list|tell)\s+(?:me\s+)?what\s+(?:you|jarvis)\s+(?:can\s+(?:reach|access)|...)`,
but that pattern is never reached for these sentences.

**Reproduction (run).**

```
'show me what jarvis can reach'  -> ('settings_open', {'id': 'reach'})
'show me what jarvis can access' -> ('settings_open', {'id': 'reach'})
'what can jarvis reach'          -> ('reach_list', {})
```

`test_reach.py` uses "show me what **you** can reach", which still works, so the
suite did not catch it. On the floating face (voice only), the owner hears
"Opening what jarvis can reach in Settings." instead of the list.

**Smallest fix.** Try `_REACH` (and `_SAYABLE`) before `_settings_open`, or
drop the two sentence-shaped aliases from the "reach" section.

---

### 9. The correction count can overcount (Low, certain; masked by finding 1)

**Evidence.** Two separate places count, for the same answer:

```
jarvis_agent.py:4523    if watch.newest_own_words and looks_like_correction(watch.newest_own_words):
jarvis_agent.py:4524        note_correction(conv_id)
second-card-suggest.patch:20  +            if out.get("mark") == "wrong" and out.get("changed") \
```

`"changed"` is `before != value` (`jarvis_feedback.py:325`), so wrong, then none,
then wrong again on ONE answer counts twice. And the phrase check matches
sentences where the owner is describing something else (run):

```
'this is wrong, my code keeps crashing'          True
'my doctor says it is not true'                  True
"it's not right that my landlord did that"       True
```

**What goes wrong.** With `CORRECTION_THRESHOLD = 2`, one real correction (typing
"that's wrong" and tapping the wrong mark) or two such sentences would raise a
card saying "You have corrected Jarvis's answers 2 times in this conversation".
Today finding 1 stops the card, so nobody sees it yet.

Separately, not a backend bug: the phone's `Feedback.markBody` (`Learning.kt`)
never sends `conversation_id`, so a wrong mark counts only from the desktop.
ARCHITECTURE §8 does not list this as one-sided on purpose.

**Smallest fix.** Count at most one correction per answer (key the mark on the
turn id, and skip the phrase count when that turn was already marked). Tighten the
subject part of the regex so it requires the sentence to start with it, e.g.
`^(?:no[,.]?\s+)?(that'?s|...)`.

---

### 10. Crisis panel flag on a picture turn after a crisis message (Low, certain)

**Evidence.** The header check takes the newest user message whose content is a
string. A picture message's content is a list, so it is skipped, and the check
falls back to an earlier message:

```
wellbeing.patch:18  +            _wb_newest = next((m.get("content") for m in reversed(messages)
wellbeing.patch:19  +                               if isinstance(m, dict) and m.get("role") == "user"
wellbeing.patch:20  +                               and isinstance(m.get("content"), str)), "")
```

`run_local_turn`'s own check uses only the owner's newest words, and a picture
turn has none (`jarvis_agent.py:2888-2891`, `picture_caption`).

**Reproduction (run).** `repro_wb.py`: a crisis message, an answer, then a
picture with "what plant is this?":

```
header check reads: 'i want to kill myself' -> wellbeing=crisis: True
run_local_turn's own check (watch.crisis): False
```

Both apps then draw the calm crisis panel (large 988/911 styling) around a
plant answer that carries no help line.

**Smallest fix.** Read only the LAST message:
`m = messages[-1] if messages else {}`, and flag only when its content is a
string and `crisis()` matches.

---

## Possible, not verified

- **The combined budget ignores the everyday model.** `COMBINED_MODEL`'s
  arithmetic (`jarvis_second_card.py:310-322`) gives the 2080 Super 5.57 GiB of
  room. But the everyday Ollama keeps jarvis-primary loaded on that same card, and
  nothing stops it while combined is on. Ollama splits by FREE memory, so the 14B
  model may not fit at all. Not measured: there is no second card yet.
- **crates.io's crawler policy.** A real check sends 576 requests to crates.io
  back to back, with no pause between them (`_rust_group`). From memory, crates.io
  asks automated clients for at most one request per second. That policy page was
  not re-read here (the module's own comment says the same), so this may or may
  not risk a block of the owner's address.
- **A crisis turn is still counted as a correction**, and the offer check runs
  at the end of a crisis turn (`jarvis_agent.py:4523`, `:4923`, neither checks
  `watch.crisis`). Whether "never counted" (the owner's answer 10,
  2026-09-27) covers an in-memory counter like this is the owner's call. With
  finding 1 fixed, a "bigger model?" card could follow a crisis message.
- **News feeds follow a redirect to another public website.** `_FeedRedirect`
  (`jarvis_news.py:247-258`) refuses only private addresses, so a feed the owner
  approved can send Jarvis on to a different host the card never named. Whether
  that counts as "never follows links elsewhere" is a question for the owner.
- **Out-of-date doc.** `docs/JARVIS-API.md:6645-6647` says `wellbeing.patch` "is
  not in `scripts/apply-patches.ps1`'s `$PATCHES` list". It is
  (`apply-patches.ps1:485`).

## Areas read and found fine

- **The patch stack (`schedule.patch` and `briefing.patch`).** I rebuilt
  `jarvis_hud.py` from every patch, in `apply-patches.ps1`'s order, and logged
  each hunk. All five `briefing.patch` hunks and all four `schedule.patch` hunks
  applied directly, none materialised. The `/api/chat` block comes out in the
  right order: `note_conversation()`, then `answer_turn(body, peer=_peer,
  local=_local)`, then `tools_ran` from `_quick.read`. Nothing is lost.
  `briefing.patch`'s `@@ +2860` start does not add the earlier hunks' offset, but
  `git apply` (and GNU `patch`) search for the context lines, so it does no harm.
- **`jarvis_settings_registry.py`.** Each setter calls the same function, with the
  same arguments, as its REST route: `auto-learn.patch`, `asks-first.patch`,
  `tools-enable.patch`, `watch-notifications.patch`'s `install`, `briefing.patch`
  `/senders`, and `jarvis_search.handle_settings`. `peer`/`local` are threaded
  unchanged from `schedule.patch` through `answer_turn`, `answer`, `run` and
  `_run_settings_*` into `handle_tier` and `handle_tools`, whose `_here` falls back
  to `_from_this_pc`, which fails closed. "Open" is exact-alias only. "Adjust"
  covers only the listed settings. Loosening still needs this PC and Windows Hello.
- **`_OPEN_CHAT`.** Whole sentences only. "show the timer" still goes to timers,
  and "open the door" goes to the model.
- **`jarvis_backoff.py`'s new kind.** It is declared in `OFFERS`, it asks only
  `suggest_bigger_model` (in `MAY_ASK`, not in `NEVER_ASKS`), and
  `opened`/`closed`/`declined`/`accepted` are paired on every path of
  `_maybe_suggest_combined` and `_settle_suggestion`. `_SUGGEST_FP` is set only for
  a card that was really raised, and read once.
- **`jarvis_tool_updates.py`, other than findings 4 and 6.** `approved()` fails
  closed. Nothing goes out before a yes. The User-Agent names no person. The check
  runs off the request thread, and the "checking" flag is always cleared. There is
  no self-deadlock on `_C_LOCK`. Errors are shown as short sentences.
- **Earlier audit.** All six findings of `BUG-AUDIT-2026-09-26-backend.md` are
  fixed in the code. I checked this by reading the lines (`_INVISIBLE` has
  Zl/Zp; the IMAP timeouts; `fired_since` skips `k.silent`; tellme `look()`
  compares `ends`; focus deletes the captured `jid`; the briefing reads to
  `_today()`'s real end). The old reproductions were not re-run.
- **`scripts/apply-patches.ps1`.** It parses with 0 errors in PowerShell 7.4.6.
  An AST scan found no `??`, `?.`, `&&`/`||` pipeline chains or ternaries.
- **Suites.** `python3 backend/run_suites.py`: 131 passed, 0 failed, 19 skipped
  (they need the owner's own files).

The reproduction scripts (`repro_offer.py`, `repro_tu.py`, `repro_both.py`,
`repro_pin.py`, `repro_wb.py`, `probe_quick.py`, `stack_probe.py`) were run from
the session's scratch folder. They are not part of the repository, and each one
is described in its finding above.
