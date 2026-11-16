# Design: one plan card per job, and trusted mode

**Status: DESIGN ONLY. Nothing in this document is built.** It records two
decisions the owner made on 2026-11-15 and 2026-11-16, and seven further
rulings from his review of 2026-11-16, and it designs them. This is now the
build brief: the pull request that carries it changes no code, no test and no
behaviour, and the feature that follows it is built from this document.

**Every number here was measured in this worktree on 2026-11-15, and the file
and line are given so it can be checked again.** Everything the apps will say is
**designed**, not built, and is marked where it appears. A line marked
**Settled** is one of the owner's rulings, with the reason he gave.

The two decisions, in one breath each:

1. **One plan card per job.** Today each GitHub write raises its own card. The
   owner answers ONE card that names the whole job - every write, every file,
   every target, and for a merge the exact commit - and the job then runs. If
   anything turns out different from what the card said, no write happens and a
   new card is raised instead.
2. **Trusted mode, engaged by chat.** The owner says "go trusted for an hour",
   answers ONE card with Windows Hello, and for sixty minutes Jarvis does GitHub
   work without asking each time. It covers GitHub only, it ends by itself, it
   never survives a restart, and every action it takes is still listed.

Both are **a grant**: a small record that says "this one yes covers these
actions, on these targets, until this time". Jarvis already has that machinery,
in miniature, for web search - `grant_made()` / `granted()` / `grant_ended()` at
`jarvis-backend/jarvis_gate.py:1939-1960`, a time-boxed, audited,
per-conversation grant for ONE action that ends on four conditions, one of them
the process restarting. **This document widens that existing grant; it does not
build a second approval path around the gate,** and that sentence is the whole
architecture.

## The words this document uses

Read this once and the rest is plain.

| word | what it means here |
|---|---|
| **tool** | One ability the AI model can call, such as `github_merge_pr`. The model asks for it by name, with arguments. |
| **action** | The gate's own name for a kind of change. One tool can have more than one: `github_fix_and_push` decides under `github_fix_and_push` for its prepare and push stages and under `github_fix_write` for its write stage (`backend/jarvis_agent.py:5909-5916`). |
| **the gate** | `jarvis-backend/jarvis_gate.py`, the single checkpoint every tool call passes through. It reads the owner's tier table ("auto" = do it, "ask" = raise a card, "never" = refuse) and allows, asks, or refuses. |
| **approval card** | The one-question form Jarvis shows before a change. On the PC it needs Windows Hello; on the phone it needs that phone's fingerprint or PIN over a one-use challenge (`jarvis-backend/jarvis_owner_check.py:166-168`). |
| **grant** | The small in-memory record above. It is data a person's yes wrote, not a mood of the model's. |
| **target** | What a write would touch: the repository, the pull request number, the branch, the file path, and, for a merge, the exact commit. |
| **stale event stream** | The live feed both apps listen to. When a client has fallen behind, the server tells it (`hello.stale`, `jarvis-backend/jarvis_events.py:60-63`), and the apps then hold Approve rather than let a person approve what they cannot see. |
| **job** | One thing the owner asked for, in one chat, such as "fix the failing checks and merge it". A job may need several writes. |

## 1. The problem, measured

**The switch: the model has to be offered the tool at all.** `[tools].enabled`
must name it. That is done one of two ways. ONE master card offers all twenty -
its title is "Offer ALL TWENTY GitHub and review tools to the AI model?"
(`jarvis-backend/jarvis_asks_first.py:760`) and approving it writes twenty names
in one atomic write (`set_tools_enabled_many`, `jarvis_asks_first.py:2626-2644`)
- or one card per tool, twenty times. The row's own sentence names the split:
"the eighteen GitHub tools (the library search, five card-free reads and twelve
carded writes) and both local review gates"
(`jarvis_asks_first.py:755-758`).

**The card: every write raises its own approval, every time.** The twelve writes
each have their own action, all shipped at "ask", and none can be loosened:
`backend/jarvis_agent.py:850-871` names them, and the settings page carries a
row for each because "the page promises every action a card can name"
(`jarvis_asks_first.py:1000-1042`). No switch turns that off.

**And the reads do not raise anything.** Six card-free reads, in the module's own
words: "The reads are CARD-FREE ... a read changes nothing, so the gate runs it
at 'auto' and it is NOT in NEEDS_A_PERSON. Every WRITE above still asks its own
card" - then "There are SIX, and `github_search` is the sixth: it is
deliberately NOT in `GITHUB_READ_TOOLS` above" (`jarvis_agent.py:874-885`). The
six are the five in `GITHUB_READ_TOOLS` (`jarvis_agent.py:842-849`) plus
`github_search`, named together as `GITHUB_CARD_FREE_READS` (line 885). The
twelve are `GITHUB_ACTION_TOOLS` (lines 850-871). **6 reads free, 12 writes
carded, by the owner's own decisions.**

One stale comment, noted rather than fixed here: the module header still says
"the four reads, the six carded writes and the small operational details around
them" (`backend/jarvis_github.py:604-605`). Measured, that tuple holds five
reads and the write list holds twelve. The comment is wrong; this document does
not touch it.

### "Fix the failing checks and merge it" is four cards

Not three. The count, from the tree:

| # | card | why it is separate |
|---|---|---|
| 1 | fix-and-push, **prepare** | `github_fix_and_push` is at "ask" and in `NEEDS_A_PERSON` (`jarvis_agent.py:7299`); prepare copies the pull request into a scratch folder on this PC. |
| 2 | fix-and-push, **write** | The write stage is its own action, `github_fix_write` (`jarvis_agent.py:7317`), decided by the tool's `gate_lookup_name` (`jarvis_agent.py:5913-5916`). |
| 3 | fix-and-push, **push** | The push is a separate call under `github_fix_and_push` again: "push the fix to its own branch ... shows the exact commits, files and command" (`jarvis_agent.py:5884-5892`). |
| 4 | **merge** | `github_merge_pr`, at "ask" and in `NEEDS_A_PERSON` (`jarvis_agent.py:7297`). |

One answer may raise **five** cards (`CARDS_PER_TURN = 5`,
`jarvis_agent.py:8182`). The job fits - just - and the limit is per answer, so a
second file or a re-run does not fit at all and the model asks for the rest in
another turn.

### Why this is not just annoying

The repository already tells the truth about the bans in one sentence
(`backend/jarvis_github.py:596-602`):

> Jarvis can never force-push, squash-merge or rebase, use an admin bypass, turn
> on auto-merge, bypass required checks, push directly to main, approve a pull
> request in your name, edit a comment, dispatch a workflow, use a gist, close or
> reopen more than one issue at a time, or delete/close repositories or branches;
> every merge, push, edit, review, label change or issue close requires its own
> approval card.

That last clause is the problem stated as a promise, and §5 is about it.

The urgency is measured outside this repository. In a browser game built to look
like Claude Code's permission prompts - 60 seconds, approve or deny, scored both
ways - humans **approved about one third of the malicious commands**, and the
boring one, `npm run analyze`, was approved 65% of the time
([IANS, *Approval Fatigue*](https://www.ians.com/news/approval-fatigue-the-hidden-risk-of-human-oversight-of-ai-agents)).
The article's conclusion is the one that matters: human review "should be the
final safeguard, not the primary one".

**A card is only worth something while the person reading it is still reading.**
Four cards for one job is not four times safer than one. Past a certain number it
is less safe, because the fourth is answered by someone who has already said yes
three times. More cards is not more safety past that point - which is the whole
argument for one card that means something.

## 2. Decision 1 - one plan card per job

### What it is, and the one action behind it

A **plan card** is one approval card that names every write the job will make,
drawn before any of them happens. The card is the permission; the list on it is
the exact list of what may run.

**Settled:** the plan card gets its **own gate action, `github_plan`, at tier
`ask`**, listed in `NEEDS_A_PERSON` and in `_NO_RULE_FROM_DENIAL`
(`jarvis_agent.py`; `jarvis-backend/jarvis_gate.py`). The reason is that it is
the **single auditable boundary**: one action name covers the whole job, so the
approval log has one line to read for "who allowed this job" rather than four.
It takes the four decisions of the edit button below - approve, edit, reject,
respond - and it **mints a scoped `PlanGrant`** whose `describe()` renders every
named write, repository, pull request or branch, file, and pinned `head_sha`.

**Individual writes keep their own gate actions** (`github_merge_pr` and the
rest) for calls made outside a plan. Nothing is removed and no tool is
re-classified; the plan is a second way to say yes, narrower than the first.

### What it names

Per write: the **repository**, the **pull request number** where there is one,
the **branch**, the **files** it may write, and for a merge the **exact commit**
it is pinned to - the same pin the merge card already has: "refused with nothing
sent if that commit has moved" (`jarvis-backend/jarvis_gate.py:3171`). A sketch
of one, for the example job:

```
Job: fix the failing checks on #1295 and merge it
Repository:      darknight11ish/Epic-Jarvis
Pull request:    #1295 - "Make the gate read the whole arguments"
Branch:          fix/gate-arguments-2026-11-15
Files it writes: backend/jarvis_gate.py       (ONE file, inside the scratch copy)
Then:            push to that branch, then merge #1295 - pinned to abc1234
                 - only if abc1234 is still its head and every required check passes
Cards inside:   4  (prepare, one file, push, merge) - rendered by PlanGrant.describe()
```

### Any divergence raises a new card

The plan is a promise about the world as it was when the card was drawn. If the
world has moved, the card no longer describes it, so it no longer covers it:

- **the head moved** - the merge is pinned to `abc1234`; if the branch now ends
  elsewhere, merging is a new card (already true of a single merge card,
  `jarvis_github.py:1516-1525`);
- **a required check went red** - a card drawn when a check was green does not
  approve a red one;
- **a file the card did not name** - the fix turns out to need a second file;
- and by the same rule, a different repository, pull request number or branch,
  or a re-run that was not on the card.

The write does not happen and the owner is asked again. **That refusal is the
feature**: a plan card that could stretch to a second file would be a card that
approved a category, and a category is not something a person can read.

One caveat in the check this depends on, recorded here and not fixed here: on
the path where a repository has no check runs at all, the sentence is
unconditional - `backend/jarvis_github.py:6492-6494` prints "More than one CI
run is on the head commit" whatever the number of runs actually is, so a single
red run with no check runs prints a false sentence by construction. The plan
card's merge must read **the required checks' own conclusions**, never a count of
runs.

### The three rules

Written as rules so a later reader cannot treat them as suggestions.

> **Rule A - named actions only.** A plan card may never approve a queue, a
> pending list, or a set of items you have not seen. Every write it allows is
> named on the card, one by one.

> **Rule B - no silent expansion.** A write the card did not name is always a
> new card. It is never covered by the card being close, by the job being nearly
> finished, or by the earlier card having said yes to something similar.

> **Rule C - a stale event stream still blocks it, exactly as it blocks a single
> action.** If the app cannot show the owner what has happened, it does not let
> them approve what happens next. The plan card is not exempt.

Rule C is not a turn of phrase: both apps already hold Approve while the stream
is stale - "both apps ask 'are you sure?' first and hold it while the event
stream is stale" (`jarvis-backend/jarvis_hud.py:4491-4492`), and the server tells
a client it has fallen behind with `hello.stale` (`jarvis_events.py:60-63`). A
plan card is a card, so it waits the same way.

### The button that is missing today: edit

Today a card is yes or no. LangChain's human-in-the-loop has **four** answers to
a paused tool call - `approve`, `edit`, `reject`, `respond`
([LangChain, Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)):
approve runs the call as proposed, **edit** changes an argument first, reject
skips it and tells the model why, and respond answers in place of the tool. The
plan card borrows the button today's cards do not have, `edit`; `respond` is not
needed, because no GitHub write is a question to the owner.

**Settled:** edit may change **non-target fields only** - the commit message,
the comment text, the pull request title and body. Changing the **repository, the
pull request number, the branch or the `head_sha` raises a NEW `github_plan`
card**. The reason is the point of the whole design: *a target can never be
swapped silently under an existing yes*. An edited card is recorded in the log
with both texts and the field that changed, so a card that was edited is never
presented later as a card approved as drawn.

## 3. Decision 2 - trusted mode, engaged by chat

### What it is

A **window the owner opens by talking to Jarvis**, during which GitHub work runs
without a card for each write. It is not a setting, it is not remembered, and it
is not a mode of the model. It is the `grant_made` / `granted` / `grant_ended`
grant of `jarvis-backend/jarvis_gate.py:1939-1960` widened: same three audit
events, same death on restart, same "the owner said stop" path, wider scope and
shorter life.

**The opening card, verbatim, as designed with the owner.** This is the exact
text shown on the PC. Designed, not built.

> Trusted for one hour? While it is on, Jarvis does GitHub work without asking
> each time: merging a pull request, pushing to a pull request's branch,
> comments, new issues, re-runs, reviews, labels, PR titles, closing one issue,
> creating an empty repo. GitHub only — nothing else on this PC. It never
> approves anything already waiting for you, it ends by itself in 60 minutes or
> if Jarvis restarts, and it ends the moment you say 'trusted mode off'. Every
> action is still listed as it happens. Approve with Windows Hello.

### The states

| state | what is true | what the owner sees |
|---|---|---|
| **off** (default) | No grant. Every write raises its own card, as now. | Nothing. No bar. |
| **card up** | Jarvis has asked. Nothing is allowed yet. | One card, with the text above, waiting for Windows Hello on this PC. |
| **on** | The grant is live until its expiry or its action cap. Covered GitHub writes run with no card. | The bar, in both apps. |
| **ended** | The grant is gone; covered writes raise cards again. | The end summary once, then nothing. |

Four reasons end it, and the summary always names which: **the hour was up**,
**Jarvis restarted**, **the owner said "trusted mode off"**, or **a stale event
stream voided it**.

### The sentences

**How it is opened and asked about.** Five phrases, in chat and in Jarvis Live.
Designed, not built.

| the owner says | what happens |
|---|---|
| `go trusted for an hour` | Raises the opening card. Nothing is on until it is answered. |
| `trusted mode on` | The same card. Saying it twice does not open two windows; the second gets "it is already on, until 21:58". |
| `trusted mode off` | Ends it at once, from either app, with no card - it only takes permission away, the same shape as the web-search revoke (`backend/jarvis_agent.py:4864-4865`). |
| `is trusted mode on?` | One sentence from the record: "Yes - until 21:58, 3 GitHub actions taken" or "No, trusted mode is off." |
| `how long has trusted mode got?` | "31 minutes, until 21:58." |

**The bar, in both apps.** One line, visible while the mode is on, read from the
record and never summarised by the model. Designed, not built.

> Trusted until 21:58 · 3 GitHub actions taken · say 'trusted mode off'

**The per-action line, as each action happens** - not collected at the end.
Designed, not built.

> Merged #1295 (abc1234) — trusted mode.

**The end summary, once,** at the moment the window closes, for whatever reason.
Designed, not built.

> Trusted mode ended at 21:58 (hour up). Five actions:
>
> - Merged #1295 (abc1234)
> - Pushed 2 commits to fix/gate-arguments-2026-11-15 (#1295)
> - Commented on #1295
> - Re-ran the failing check on #1295
> - Added the label `merge-ready` to #1295

The list is the audit log's own rows for this grant, not a reconstruction. If the
log cannot be read, the summary says so and names the count it cannot account
for; it never guesses.

### The five invariants

**Settled:** these are enforced **in code**, not in the prompt and not in the
card's wording. A mode that needs good behaviour from the model is not a mode.

1. **GitHub only, from a closed allowlist.** The actions trusted mode may cover
   are: comments, new issues, re-runs, creating an empty repository, a merge
   **pinned to passing checks**, fix-and-push, opening a pull request, labels,
   editing a pull request (title and body), a review that is **not** a formal
   APPROVE, and closing one issue. **Never** email, files, credentials or
   spending. **Never** auto-merge, squash, rebase, force-push, admin bypass,
   workflow dispatch, a formal APPROVE, or deleting a branch or a release.
2. **It never approves a card that was already pending, and never drains a
   queue.** A card that was up before the window opened still needs its own
   answer, and a list of them is a list (Rule A).
3. **A stale event stream voids the window immediately.** Not "blocks the next
   card": the window itself ends, so a client that has lost the feed cannot be
   trusted to be showing the owner what the window is doing.
4. **In memory only.** It is never written to disk, so no restart can resurrect
   it and there is no file to keep secret - the same reason the web-search grant
   gives (`backend/jarvis_agent.py:11989-11991`).
5. **The rule-4 amendment - `CLAUDE.md` and `docs/ARCHITECTURE.md` - ships in
   the same pull request as the feature** (§5).

**Settled, the cap:** `MAX_TRUSTED_ACTIONS = 20` by default, with a **hard
ceiling of 30**. The clock alone is not enough: an hour is long enough to fire
fifty writes, and the twentieth is where a person stops counting. The cap is in
code, so it is true whatever the card says.

**Settled, waking it up:** opening is **PC-only**, with Windows Hello, until
`jarvis_owner_check.py`'s shared-key hole is closed - the old pairing key that
every paired device shares, so a "yes" carrying it cannot prove *which* device
said it (`jarvis_owner_check.py:1814-1822`); the phone may open it once
device-bound keys are enforced. Closing - "trusted mode off" - works instantly
from anywhere with no card. The reason is the one the card states: *a mode that
switches itself on by voice alone is a hole*, and until the phone can prove it is
that phone, its "yes" is not strong enough for a window.

**Settled, the record:** every trusted action is shown in chat **and** appended
to the persistent local audit log, readable in **Brain → Activity**
(`jarvis-backend/jarvis_menus.py:850`, both apps), so the record outlives the 60
minutes and a restart. The grant dies; the list does not.

### What it does not cover: GitHub only

Stated as an exclusion list, because a window is only safe if its edge is
written down. None of these is covered, and opening the window again cannot
cover them: **email** (sending, drafting, tidying, reading), **files** (any write,
move, delete or read on this PC outside the scratch copy the fix flow already
uses - which is why the fix flow's local `write` stage stays carded while its
prepare and push stages are covered), **credentials** (the GitHub token, any API
key, the pairing token, any password), **spending** (anything that costs money,
including a raise to a money limit), and **everything else**.

### Why sixty minutes

A GitHub App's installation access token is valid for **exactly one hour**, then
must be minted again - GitHub's own community forum is full of people meeting
that boundary:
["GitHub App works for about an hour, then every API call returns 401 'Bad
credentials'"](https://github.com/orgs/community/discussions/211715). If GitHub
will not trust an automated installation for longer than an hour, sixty minutes
is defensible for Jarvis. It is also long enough for the job that motivated it:
four writes on one pull request with a CI run in the middle does not fit in five
minutes.

## 4. How it works inside the gate

### In plain words

A grant is a **small record**, not a state the model is in. It says: this one yes
covers these actions, on these targets, until this time, and here is what ends
it. It lives in memory, and it is written only after a person answered a card.

The gate holds it and checks **every tool call** against it before that call
runs. Four yes-or-no questions:

1. Is the action this call would take in the grant's allowed writes?
2. Is the target in the grant's targets - this repository, this pull request,
   this branch, this file, this commit?
3. Is the grant still in date, and under its action cap?
4. Is nothing on its "this would end it" list true right now - has the head
   moved, has a required check gone red, is the event stream stale?

Four yeses: the call runs with no card, and the gate writes one line saying a
grant covered it. Anything else: the grant does not let it run, the call falls
through to the ordinary path, and the ordinary path raises the usual card. That
is Rule B, enforced in one place instead of in every caller.

The gate can only ever **narrow** what would otherwise happen. A grant can never
name an action the risk table does not know, because such an action is forced to
"ask" whatever the settings file says
(`jarvis-backend/jarvis_gate.py:2224-2267`), and a grant can never lift a
"never".

### The engine, and the grant as data

**Settled:** the grant engine lives in its **own module, `jarvis_grants.py`**,
which `jarvis_gate.py` consults **before raising a card**. `jarvis_gate.py` stays
clean: it is 3,380 lines in this tree and every patch in the stack is sensitive
to its exact text, so the logic that decides "a grant covers this" gets a module
of its own and the gate gains one call, not a subsystem.

The shape, in the repository's own terms. `grant_id`, `issued_at` and
`expires_at` are the shipped web-search grant's own fields
(`backend/jarvis_agent.py:12063-12064`); the rest are new.

```
{
  "grant_id":       one random id - the one the audit log records,
  "kind":           "plan" | "trusted",
  "job_id":         the job this window belongs to,
  "allowed_writes": [the exact action names the card named],
  "targets":        [repo, PR number, branch, files, and for a merge the pinned head_sha],
  "void_if":        [head moved, required check red, an unnamed file, stale stream,
                     a restart, "trusted mode off"],
  "issued_at":      when the card was answered,
  "expires_at":     when it dies by itself,
  "actions_taken":  0,                              # counted against max_actions
  "max_actions":    MAX_TRUSTED_ACTIONS             # 20 by default, 30 is the ceiling
}
```

| field | why it is there |
|---|---|
| `grant_id` | The name the three audit events already take (`grant_made` / `granted` / `grant_ended`, `jarvis_gate.py:1939-1960`), so every line they write points back at this record. |
| `kind` | A plan names its writes one by one; trusted mode names a class. They are checked and logged differently, so they are different kinds. |
| `job_id` | Every action logged under it traces back to the one card that allowed it, months later. |
| `allowed_writes` | The list is closed. A write not on it is not covered, ever - Rules A and B in one field. |
| `targets` | The same write on a different target is a different write: `github_comment` on #1295 is not `github_comment` on #1300. |
| `void_if` | The events that end it, stored with the grant so the gate reads one record, not two. |
| `issued_at`, `expires_at` | A grant always expires. `expires_at` is the only way it ends without a person doing something. |
| `actions_taken`, `max_actions` | The cap, in code. The clock is not the only bound (§3). |

`PlanGrant.describe()` is the other half: it renders the card from this record,
so the card and the permission cannot disagree - the same reason the web-search
grant reads its own store to tell the prompt what is in force
(`backend/jarvis_agent.py:12091-12111`).

### Where new rows go, and the ruling that says so

The gate's three tables are `_RISK` (what a thing can do to you),
`_TOOL_ACTIONS` (which action a tool name decides under) and
`_NO_RULE_FROM_DENIAL` (a denial about one item, not a standing rule). They sit
at `jarvis-backend/jarvis_gate.py:269`, `1166` and `1714`.

**There is no `backend/jarvis_gate.py`** - checked in this worktree: the only
copy is the published base. So a new row cannot be added "beside the feature".

**The owner's ruling of 2026-11-14, measured the expensive way**
(`CLAUDE.md:321-348`): the row belongs in the published base,
`jarvis-backend/jarvis_gate.py`, inside a `<table>.update({...})` block at the
**end of the file** - the one region no earlier patch's hunk claims - and it
reaches the owner's own PC through `tools/repair_live_backend_gaps.py`, the same
route the Android app builder's `_RISK` rows took on 2026-10-30. **Never a new
patch.** The last block in the file is the shape to copy:

```python
_NO_RULE_FROM_DENIAL = _NO_RULE_FROM_DENIAL | {
    "send_file_to_phone",
}
```
(`jarvis-backend/jarvis_gate.py:3378-3380`, the last three lines of the file.)

Two consequences worth carrying, because they cost cycles on 2026-11-14. A new
patch that writes `jarvis_gate.py` disturbs six suites and the `audit` job:
`unknown-risk-approvable.patch` must stay the last patch that writes the file,
`handsfree.patch` and `web-search-grant.patch` must stay immediately before it,
and five more suites keep their own "patches written after me" lists. And
`backend/test_gate_tool_actions.py` and `backend/test_def068_entry.py` fold
`<table>.update({...})` at module level, so **a suite that only greps the literal
reports the row missing on a tree where the gate answers correctly**.

So trusted mode and the plan card need, at the end of the base file: a
`_TOOL_ACTIONS` row and a `_RISK` row for `github_plan` and for each new card
action (what it touches, whether it can be undone, one sentence of plain words),
and a `_NO_RULE_FROM_DENIAL` row where a denial is about that one window rather
than a standing rule.

### What this touches

| where | what changes there |
|---|---|
| `jarvis-backend/jarvis_gate.py` (base, the only copy) | One call to the grant engine, before the card; three rows at the end of the file; the three grant audit events reused as they are. |
| `jarvis_grants.py` (new module, both copies, and in `backend/_where.py`'s `SHIPPED` list) | The grant record, `PlanGrant`, `describe()`, the cap, the expiry, the void conditions. |
| `backend/jarvis_agent.py` + `jarvis-backend/` twin | The `github_plan` tool and the tools that open and close a trusted window; card and sentence words; `NEEDS_A_PERSON`; the `github_plan` action wiring. |
| `backend/jarvis_github.py` + twin | What each write's target is, so the gate can compare it; the merge pin; the last clause of `NEVER_WORDS` (§5). |
| `backend/jarvis_asks_first.py` + twin | A row on the settings page for each new card action, because the page promises every action a card can name. |
| `backend/jarvis_hud.py`, `docs/JARVIS-API.md` | Only if the bar needs a read; the cleaner source is one event on the existing stream, which both apps already listen to (`jarvis_events.py:60-63`). |
| `jarvis-desktop/src`, `jarvis-client/` | The bar in both apps, the edit button on the plan card, the per-action chat line. |
| `tools/repair_live_backend_gaps.py` | How the new base rows reach the owner's own PC. |
| `CLAUDE.md` and `docs/ARCHITECTURE.md` | The rule-4 amendment, in the same pull request as the feature - §5. |

Both `.py` copies matter: `backend/<file>` and `jarvis-backend/<file>` are kept
equal, and `test_base_matches_repo.py`, `test_base_regeneration.py` and
`tools/check_stale_twins.py` must all run before the push.

### Why this is safe by design, not by luck

The property borrowed here is old and specific: **the thing that decides what is
allowed is not the thing that was talked into wanting it.**

| system | its idea | what this design takes, and refuses |
|---|---|---|
| **CaMeL** (Google DeepMind, *Defeating Prompt Injections by Design*) | The model turns the request into a **plan as inert data**, and a separate privileged interpreter executes it, with **capabilities that travel with the data** ([plain-English write-up](https://simonwillison.net/2025/Apr/11/camel/)). | The plan card is the inert data, the gate is the interpreter, the grant is the capability. The model's words are never the permission: a model that says "I am trusted" changes nothing. Refused: running a write the card did not name. |
| **OpenHands** | Pluggable analyzers score each action, four risk levels (low, medium, high, unknown), a confirmation policy decides when a score means "ask", and the decision goes in the event history ([OpenHands, Security](https://docs.openhands.dev/sdk/arch/security)). | The audit trail, and "a policy maps what is known to whether to ask". Refused: letting the model rate the risk of its own action - ours comes from a fixed table a person wrote. |
| **Progent** | Privilege control as **per-call policies** over tool names and arguments, enforced deterministically at the tool-call level, with a check that a policy change only narrows ([Progent, arXiv 2504.11703](https://browse-export.arxiv.org/pdf/2504.11703)). | The per-call, deterministic check, and "an update may only narrow" - a second card can cut a grant short, and nothing can widen it. |

The one sentence to keep: **the permission is data a person wrote, and the check
is code that reads it.** Everything in this section is that sentence, spelled
out.

## 5. The rule that changes, written out

The old rule is written in **two** files, and it has to be amended in **both, in
the same pull request as the feature**. `CLAUDE.md:112-113`:

> 4. The app never auto-approves anything, and blocks acting when the event
>    stream is stale.

And `docs/ARCHITECTURE.md:188-189`:

> 3. **No auto-approve anywhere, and no approve-all control anywhere.** One
>    action, one decision. Do not build one.

That invariant has teeth because it was broken once, in the gate itself:
`confirm_auto()` "returned True for tier `ask` with nobody asked, behind a
`--auto-approve` flag", fixed by `no-auto-approve.patch` and now asserted by
`test_gate_outcome.t_there_is_still_no_approve_all` - a test written to catch the
**shape**, not the flag (`docs/ARCHITECTURE.md:191-199`). A one-hour window of
unnamed `ask` writes is that shape at a smaller scale, so the amendment cannot be
slipped past the invariant: it has to be written into it.

The replacement for `CLAUDE.md` rule 4, in the same voice (two lines, the same
shape, the stale clause kept because it is still true):

> 4. The app never acts without the owner's yes. A yes may cover a window the
>    owner opened - one named job, or trusted mode for one hour - and a window
>    always expires, dies when Jarvis restarts, and lists every action it took.
>    Acting is blocked when the event stream is stale.

The replacement for `docs/ARCHITECTURE.md` invariant 3, in the same voice:

> 3. **No auto-approve anywhere, and no approve-all control anywhere.** One
>    action, one decision - except a yes the owner gave for a window they
>    opened. That is a grant, not an auto-approve: a person answered a card to
>    write it, it names what it covers, it expires, it dies on restart, and it
>    lists every action it took. A queue, a pending list, or a set of items the
>    owner has not seen is never covered, and there is still no control that
>    approves in bulk. Do not build one.

Four things the sentences do that "never auto-approves anything" no longer can:
they allow a yes to be a window, they bound the window, they give it two deaths
that cannot be argued with, and they keep the list. What they never allow is a
yes with no person behind it.

### Three more sentences that would become untrue

Rule 4 is not the only place the old rule is written down. Trusted mode makes
three more sentences false. All three change in the **feature's** pull request,
never in this one, and one is pinned word for word by a test:

1. **`NEVER_WORDS`' last clause** - "every merge, push, edit, review, label
   change or issue close requires its own approval card"
   (`backend/jarvis_github.py:596-602`), pinned word for word by
   `backend/test_github_tools.py:909-917`, so the test changes with the
   sentence. The honest replacement keeps the list and changes the mechanism:
   "every merge, push, edit, review, label change or issue close needs your yes
   - its own card, or a window you opened."
2. **`capabilities_line()`** - "every write ships [off] ... and raises its own
   one-shot card, and a stale event stream holds Approve"
   (`backend/jarvis_github.py:1505-1510`). The second half stays true; the
   "one-shot card" half does not.
3. **The settings page's group row** - "every use is still decided by 'Ask me
   first' as its own row says" (`backend/jarvis_asks_first.py:755-758`). A page
   that says a thing is always carded while a window is open is a page that lies
   to the person reading it.

The merge and push cards' own refusal text (`jarvis_github.py:1516-1525`) is
correct and stays: a pinned merge that refuses a moved head is exactly what makes
a plan card safe.

## 6. What is out of scope, and why

Trusted mode is not a lifting of the owner's standing bans, and neither is a plan
card. The bans are the list they were on 2026-11-10 (`backend/jarvis_github.py:584-589`;
in plain words, `docs/JARVIS-API.md:36197`), and none of the six below is
reachable by any card, plan or window:

- **No auto-merge.** It acts after the owner has stopped watching, which is the
  one thing a window may never become. In the `NEVER` set by name.
- **No squash, no rebase, no force-push.** All three rewrite commits other people
  may already have pulled; the merge method is `"merge"` and only `"merge"`
  (`jarvis_github.py:368`). A pushed commit cannot be taken back.
- **No admin bypass and no bypassing a required check.** A merge past a red check
  is the failure this document exists to prevent, not a speed setting.
- **No workflow dispatch.** Arbitrary remote execution with model-chosen inputs -
  the reason it is a permanently banned verb with no action, card or tool.
- **No formal APPROVE on a pull request.** A real APPROVE satisfies
  branch-protection required-reviewer rules, so it would hand the owner's own
  sign-off authority to the assistant. A review that is not an APPROVE is
  allowed in the window; the APPROVE never is.
- **No branch or release delete.** There is no release tool at all - `release/`
  appears only as a branch prefix the push refuses to touch
  (`jarvis_github.py:393`) - and the never-list in §3 names a release delete
  anyway; deleting a branch destroys work with no undo.

Also unchanged, for the same reason: **no gists** (public by default), **no
editing a comment**, **no closing or reopening more than one issue at a time**.
The whole `NEVER` set stays where it is.

This section exists so a reader a year from now cannot mistake "trusted mode" for
"the bans were relaxed". The mode relaxes the **asking**, never the **allowing**.

## 7. Risks, and the proof required before this ships

### The counter-evidence the owner should see

The strongest finding in the research memo is not the game. It is **Anthropic's
own telemetry**: "Our telemetry showed users approved roughly 93% of permission
prompts. The more approvals a user sees, the less attention they pay to each",
and **their fix was fewer prompts bought by a tighter boundary**, not skipped
approvals - an OS-level sandbox ("network is denied by default") produced "an
84% reduction in permission prompts", and only then did they relax the
oversight: "A tight perimeter also means you can relax oversight"
([Anthropic, How we contain Claude](https://www.anthropic.com/research/how-we-contain-claude)).

So every source that relaxes approval does it in one order: **tighten what the
agent can reach, then stop asking.** This ruling puts merges and pushes - the
two irreversible, outward-facing writes - inside the window **first**, which is
the opposite order: merge and push are exactly the writes the same sources say
should go **last**.

**That is recorded here as the owner's decision, and it is not softened.** The
honest statement of the risk is: trusted mode buys the fatigue benefit without
paying the containment price, and the price that is not paid is the one that
makes the benefit safe.

Three mitigations, each of which costs nothing and is already in the design:
the **per-action cap in code** (20, hard ceiling 30), the **persistent audit
log** in Brain → Activity, and the **merge row naming which checks were green**
so the one irreversible write in the window is the one that shows its evidence.
If the owner wants the order changed later, the cheapest change is to take merge
and push out of the window first - not to lengthen the window.

### The proof required before this ships

**Settled:** an **AgentDojo-style red-team harness** is part of this wave, and it
is **dev/test only** - it goes in `requirements-dev.txt` or a standalone
benchmark script, never in runtime `requirements.lock`. **Shipping the wave
needs that proof first.** The reason: a window is the one feature whose failures
are silent by construction, so it is measured before it is trusted, not after.

## 8. Open questions for the owner

Four left, each answerable with yes or no, or with a number.

1. Does Lockdown stop trusted mode while it is on - the same rule the web-search
   grant already has (`backend/jarvis_agent.py:4870-4873`)?
2. How many pull requests may one plan card name - exactly one, or up to a
   number?
3. When a divergence raises a new card mid-job, does the rest of the job stop
   until it is answered, or do the writes still inside the plan carry on?
4. Should trusted mode keep running while this PC is locked?
