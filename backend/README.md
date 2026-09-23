# Backend patches

> Architecture, invariants and the permission model every capability must use:
> [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Read that first; this file
> is the detail.


Thirty-one patches against the Jarvis backend, each with an executable test.
The last four of the older ones - `ui-control-wiring.patch`, `ollama-direct.patch`,
`tool-calling-wiring.patch` and `loopback-too.patch` - sit outside the ordered
stack below: each only touches its own few lines, shared with no other patch
here. Two ordering constraints remain: tool-calling needs ollama-direct (a
logical one), and loopback-too needs token-file (a textual one - its context
is token-file's output). See their own sections, after the table.

Added 2026-09-23, from the learning research, five more at the very end, in
this order: `feedback.patch`, `memory-intake.patch`, `skill-suggest.patch`,
`documents-owned.patch`, `speed-record.patch`. They are *in* the stack, not
beside it - each quotes the output of older patches above it. One order among
them matters: **`feedback.patch` must come before `memory-intake.patch`**,
because memory-intake rewrites a line that feedback's context ends on (see
memory-intake's own section). The other three touch lines none of the others
touch. The five were checked together, in that order, with `git apply` on a
rebuilt `jarvis_hud.py` and `jarvis_extract.py` - and backwards, back to the
starting text byte for byte. `test_learning_integration.py` checks the order
and the one place two of them meet on the same card. Four of them need a new
module copied into the backend folder too: `jarvis_feedback.py`,
`jarvis_intake.py`, `jarvis_skill_discovery.py`, and `jarvis_speed.py` with
`jarvis_owned_tables.py`. Each section says how.

Added later on 2026-09-23, one more at the very end: **`voice-enroll.patch`**
("Train my voice" on the phone). It needs `voice-503.patch` and `appearance.patch` before it (its context is their output).
It comes with a new module, `jarvis_voice_enroll.py`, and with updated copies
of `jarvis_speech.py` and `rebuilt\jarvis_voice.py`; the script copies all
three in. Its own section, near the end of this file, also has the steps
to install the better voice check.

And after that, no patch but a new module: **`jarvis_wakeword.py`** ("hey
Jarvis"), with a new `jarvis_speech.py` that finally has speech-to-text, a
voice and Silero VAD to run. The last section of this file, "Voice that
works", has the one-line installs for the models and what was measured.

**Order.** This is a *stack*, not a set. The table order is the only order that
works, and the script applies exactly it.

The first thirteen would commute on their own — several touch `jarvis_hud.py`,
but in well-separated regions. They are still in this order because
`memory-safety` must land before anything makes the extractor run. That one is
a *semantic* constraint, not a textual one: without it, the first accepted
proposal retires a roughly-matching unrelated fact, permanently, and `retire()`
has no way back.

From `bitemporal.patch` down, the dependencies are **textual** — each of those
patches has context lines that are an earlier patch's output, so it simply will
not apply without it. That is why a "dry-run every patch against the untouched
tree first" check is impossible here and the script rehearses the whole stack
on a throwaway copy instead.

| patch | file it changes | what it is for |
|---|---|---|
| `memory-safety.patch` | `jarvis_memory.py`, `jarvis_extract.py` | Five ways the memory store destroyed or refused data. Apply first. |
| `events-pump.patch` | `jarvis_hud.py` | Starts the event pump, which nothing was starting. One line and a comment. |
| `appearance.patch` | `jarvis_hud.py` | `GET`/`POST /api/appearance`, so the phone and the desktop can agree on a face. |
| `gate-push.patch` | `jarvis_gate.py` | Stops the approval gate posting unredacted private content to a public broker. Apply this one whether or not you use ntfy. |
| `skill-notes.patch` | `jarvis_skills.py` | Gates and surfaces the skill notes, which steer answers, are written without approval, and appear on no screen. |
| `documents-honesty.patch` | `jarvis_hud.py` | The brain map reports a document store that has never existed. Makes the status line true. |
| `memory-prefix.patch` | `jarvis_hud.py` | Recalled facts were the first thing in every request: it dropped the persona invariants and threw away the KV cache for the whole conversation, every turn. |
| `extraction-wiring.patch` | `jarvis_hud.py`, `jarvis_events.py` | `propose()` had zero call sites. Gives the learning loop a trigger, and the review queue a doorbell. |
| `voice-503.patch` | `jarvis_hud.py` | Four voice routes answered a missing speech module in four different shapes, two of them a 500 for something that did not break. |
| `degrade-filter.patch` | `jarvis_hud.py` | **A cloud turn that stepped down to local and back out again went upstream unfiltered.** The worst thing in this directory. |
| `vram-estimate.patch` | `jarvis_models.py` | The estimator that advises on model choice was wrong in both directions at once. |
| `memory-pane.patch` | `jarvis_hud.py` | Routes to read, edit, forget, backdate and export what Jarvis has learned. Gives `retire()` its first caller. Needs `extraction-wiring` for the learning switch. |
| `token-file.patch` | `jarvis_hud.py` | Makes a token on first run. **The phone has never been pairable without this.** |
| `bitemporal.patch` | `jarvis_memory.py`, `jarvis_hud.py` | The second time axis. Adds `retired_at` — when we stopped believing a fact, as distinct from when it stopped being true. Needs `memory-safety` and `memory-pane`. |
| `embedding-guard.patch` | `jarvis_memory.py` | A NaN or all-zero embedding was stored without complaint and the row was then unreachable forever. Needs `memory-safety`. |
| `gpu-offload.patch` | `jarvis_models.py`, `jarvis_hud.py` | Says when the model is running on the CPU instead of the graphics card. Nothing did, and the only symptom was that everything got slow. |
| `gate-outcome.patch` | `jarvis_gate.py` | A timeout was indistinguishable from a refusal. Adds `Verdict.outcome`, which fails closed by default. A real denial now proposes a standing constraint through `jarvis_extract.propose()` — never applies one. |
| `no-auto-approve.patch` | `jarvis_gate.py` | **`confirm_auto()` granted every `ask` action with nobody asked.** An approve-all, inside the module that forbids one. |
| `memory-noise.patch` | `jarvis_extract.py`, `jarvis_hud.py` | A discarded proposal came straight back, and recalled facts carried no date. |
| `decide-once.patch` | `jarvis_extract.py` | Found during a self-improvement audit: `decide()` was a plain check-then-act, so two concurrent accepts on one proposal could both win. A full queue also dropped proposals with no record. Needs `memory-noise`. |
| `event-allowlist.patch` | `jarvis_events.py` | The approval doorbell shipped `raised` — which quotes hostile outside text — to every subscriber, including a phone lock screen. |
| `approval-notice.patch` | `jarvis_gate.py`, `jarvis_events.py` | A waiting approval reached a phone as "fields: args, tool". Adds `notice_for()` — a readable title and reason built only from this module's own tables, so it is safe on a lock screen by construction. Needs `event-allowlist`. |
| `ui-control-wiring.patch` | `jarvis_gate.py` | Registers the three new capabilities below with the gate's own `_RISK`/`_TOOL_ACTIONS` tables. Textually independent of everything above it — see its own section. |
| `ollama-direct.patch` | `jarvis_hud.py` | `/api/chat`'s local lane called an OpenJarvis instance that was never actually running. Points it at Ollama directly instead — see its own section. |
| `tool-calling-wiring.patch` | `jarvis_hud.py` | Wires `jarvis_agent.py`'s tool-using loop into the local lane, and only the local lane. Needs `ollama-direct.patch` first (not textually, but a tool-enabled local turn is pointless before the local lane actually reaches Ollama) — see its own section. |
| `loopback-too.patch` | `jarvis_hud.py` | **Pairing the phone unplugged the desktop.** `JARVIS_HUD_BIND` moved the one socket off `127.0.0.1` instead of adding one, and the desktop's HUD may only talk to loopback. Also serves `127.0.0.1` when bound elsewhere. Needs `token-file.patch` — see its own section. |
| `feedback.patch` | `jarvis_hud.py`, `jarvis_extract.py` | **There was no way to tell Jarvis an answer was wrong.** Gives every answer an id, a route to mark it right or wrong, and — through `jarvis_feedback.py` — helpful/harmful counts per fact. A fact that keeps turning up in wrong answers raises one "retire this?" card in the normal review queue; nothing retires by itself. Goes before `memory-intake.patch` — see its own section. |
| `memory-intake.patch` | `jarvis_extract.py`, `jarvis_hud.py` | Seven memory items from the 2026-09-23 learning research: "Remember:", near-duplicate proposals, corrections by number, a "both are true" answer, real dates, a warning on planted instructions, and never learning from turns the backend started. Needs `backend/jarvis_intake.py` copied in. After `feedback.patch` (its hunk rewrites a line feedback's context ends on) - see its own section. |
| `skill-suggest.patch` | `jarvis_hud.py` | `GET /api/skills/suggestions`: a read-only view of the routines Jarvis has noticed and the skill offers it made. Needs `appearance.patch` (textual) and `jarvis_skill_discovery.py` copied beside `jarvis_hud.py` — see its own section at the end. |
| `documents-owned.patch` | `jarvis_hud.py` | **If you ever ran the OpenJarvis copy you downloaded, what it indexed would reach Jarvis's prompts.** Its indexer makes a `documents` table in the same `memory.db`. Now only a table Epic-Jarvis recorded creating is read. Needs `documents-honesty.patch` and `jarvis_owned_tables.py` — see its own section. |
| `speed-record.patch` | `jarvis_hud.py` | Records how fast each answer was — numbers only, to a file on this PC — and shows it on the Models screen. Needs `gpu-offload.patch`, `tool-calling-wiring.patch` and `jarvis_speed.py` — see its own section. |
| `voice-enroll.patch` | `jarvis_hud.py` | **"Train my voice" from the phone.** `POST /api/voice/enroll` takes the owner's recorded sentences, holds them in memory and raises ONE approval card. Only approving it replaces the voice print; the recordings are deleted either way. Needs `voice-503.patch` and `appearance.patch` (textual), and `jarvis_voice_enroll.py` — see its own section at the end. |
| `cloud-one-turn.patch` | `jarvis_hud.py` | The phone and quickbar now send the conversation so far with each question. This makes sure a **cloud** lane still gets only the newest question, never an earlier one. Needs `ollama-direct.patch` (textual) — see its own section at the end. |
| `task-control.patch` | `jarvis_hud.py` | **The Pause, Resume, Stop and note buttons on both apps went nowhere.** Adds the routes they call. Resume raises an approval card; nothing else here approves anything. Needs `jarvis_task_control.py` and the updated `jarvis_agent.py` — see its own section, at the end. |
| `note-capture.patch` | `jarvis_hud.py`, `jarvis_gate.py` | **`#log`, `#joplin` and the quick note never filed anything** — they asked the model for tools that did not exist. Adds a route that files the owner's own words in Logseq or Joplin through the gate, and says honestly whether it landed. Needs `task-control.patch` (textual) and `jarvis_note_capture.py` — see its own section, at the end. |
| `power-mode.patch` | `jarvis_hud.py` | **Nothing could change the power mode.** Adds `POST /api/power` (Active / Quiet / Standby) through the gate as `power_manage`. Needs `note-capture.patch` (textual) and `jarvis_power_switch.py` — see its own section, at the end. |

## Twenty of the twenty-two actually apply, and that is correct

Ten backend modules were lost and rebuilt from scratch (`backend/rebuilt/` —
see the header of any file in there). The rebuild was written against the
*patched* behaviour, because the patches were the specification: their `+`
lines were often the only surviving copy of the original code.

So six of the twenty-two patches are already half-applied by the rebuild:

| patch | half in `rebuilt/` | half still applied, from `rebuilt-patches/` |
|---|---|---|
| `memory-safety.patch` | `jarvis_memory.py` | `jarvis_extract.py` |
| `extraction-wiring.patch` | `jarvis_events.py` | `jarvis_hud.py` |
| `bitemporal.patch` | `jarvis_memory.py` | `jarvis_hud.py` |
| `approval-notice.patch` | `jarvis_events.py` | `jarvis_gate.py` |
| `embedding-guard.patch` | `jarvis_memory.py` | *(nothing — skipped entirely)* |
| `event-allowlist.patch` | `jarvis_events.py` | *(nothing — skipped entirely)* |

`apply-patches.ps1` detects the rebuilt modules by a marker in their header and
substitutes the split versions, which is why a clean run reports **19**.

**The hazard this creates, and it has already bitten once.** "The rebuild
contains that half" is an assumption, not a fact, and nothing checked it. Four
of those six halves were missing or wrong in the first rebuild: the whole
second time axis (`retired_at`, `known_at`, `retire(valid_to=)`), the
`_usable_vector` guard and its counter, the `Embedder` base class two suites
subclass, and the framing method's recovered name. The patches were skipped on
the assumption, the tests that would have caught it could not run, and the
backend shipped without features the README said it had.

The tests here are the only thing that closes that gap, and they only run
against a real backend — so run them.

## Run the tests

They live here; the modules they test live in your backend folder. Point them
at it:

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Get-ChildItem backend\test_*.py | ForEach-Object { Write-Host $_.Name -NoNewline; python $_.FullName > $null 2>&1; if ($?) { Write-Host "  ok" -ForegroundColor Green } else { Write-Host "  FAIL" -ForegroundColor Red } }
```

`apply-patches.ps1` sets that variable for you. Without it the suites look in
their own folder, which is right in the dev container — the modules are
symlinked in there — and wrong everywhere else.

## Apply them

One command:

```powershell
.\scripts\apply-patches.ps1
```

Point it somewhere else with
`-BackendPath "D:\your\path"`, undo with `-Revert`, and skip the test run
with `-SkipTests`.

It backs up every file it is about to touch into a timestamped folder, then
**applies the whole stack to a throwaway copy first** — so a patch that will
not apply stops the run before your real files are touched, rather than
leaving you half-applied. Only if the rehearsal succeeds does it patch the
backend for real and run the suites. Running it twice is safe: it checks
whether the whole stack is already applied and says so instead of failing.

**If an earlier run already put some of the patches on** (the usual case:
your backend got the list as it was on 2026-09-16, and patches have been
added since, one of them in the middle), the script now handles that too. It
finds which patches are already on, takes those off newest first, and puts
the whole list back on in the right order - rehearsed on a copy first, like
everything else. Before 2026-09-23 it could not do this: it stopped with "N
patch(es) will not apply. NOTHING HAS BEEN CHANGED" even though no patch was
broken. If you have an older copy of the script, this one line does the same
job by hand (take everything off, then put everything on):

```powershell
.\scripts\apply-patches.ps1 -Revert; .\scripts\apply-patches.ps1
```

**It also copies in the new modules the patches call** - `jarvis_intake.py`,
`jarvis_feedback.py`, `jarvis_skill_discovery.py`, `jarvis_speed.py`,
`jarvis_owned_tables.py`, the updated `jarvis_agent.py`,
`jarvis_browser_control.py` (which stays switched off until `[tools].enabled`
names `"browser_control"`), and, since "Train my voice",
`jarvis_voice_enroll.py`, `jarvis_speech.py` and `rebuilt\jarvis_voice.py`, and since "hey Jarvis", `jarvis_wakeword.py`. Each patch only adds a call into one of these, and the call quietly does nothing when the
file is missing, so a backend without them would pass every test with the
new features switched off. The script compares each file with the one in
this repository's `backend\` folder; if yours is missing or different, it
backs the old one up into the same `_jarvis-backup-...` folder and copies
the new one in. `-Revert` leaves them where they are (nothing calls them
once the patches are off). And when the tests run against your backend
(`JARVIS_BACKEND` set), a suite for one of these modules now FAILS with
"copy backend\<name> into the backend folder" if your copy is missing or
out of date, instead of quietly testing this repository's copy.

If a patch will not apply, it prints the reason and changes nothing. That
output is worth sending back: it almost always means the backend file has
moved on since the patch was written, and the patch gets regenerated.

### By hand, if you would rather

The order below matters — see **Order** above. Back up `jarvis_hud.py`,
`jarvis_memory.py` and `jarvis_extract.py` first, and add `--check` to see
whether a patch will apply without changing anything.

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
git apply --verbose path\to\memory-safety.patch
git apply --verbose path\to\events-pump.patch
... and so on, in table order
```

No git? `patch -p1 --forward -i <name>.patch` does the same, with `--dry-run`
for the check.

---

# `memory-safety.patch` — apply this one first

Five defects, each found by executing the code rather than reading it, each
with a reproduction in `test_memory_safety.py`. Together they are the reason
this patch has to land before extraction is ever wired up: the current code
does not learn anything, and the moment it starts learning it begins
destroying facts it already has.

### 1. A correction retired a random unrelated fact

`jarvis_extract._accept` took the model's free-text `replaces` string, ran
`store.search(..., k=1)`, and retired whatever came back. `search` has no
relevance floor, so it always came back with something. Measured: accepting
*"Mario drives a 1998 Volvo"* retired *"Mario prefers tabs over spaces in
Go"*. A `replaces` reading *"Mario's allergy"* retired the note about Vim. The
accept reply was `{"ok": true}` either way — the retirement was invisible, and
`retire()` has no route back.

Now `MemoryStore.find_one()` resolves it, requires at least two overlapping
content words and 50% containment, and returns **None** rather than a guess.
None means "store the new fact, retire nothing": two facts that disagree can be
sorted out later, a deleted allergy cannot. The target is also resolved when
the proposal is **queued**, not when it is accepted, and stored on the row — so
the approval card can say which fact this will retire before you agree to it.

### 2. Installing the embedding model bricked every future write

First run without `fastembed` creates `facts_vec` as `float[256]`, the hash
stand-in's width. `CREATE VIRTUAL TABLE IF NOT EXISTS` never rebuilds it, so
when the real 384-dimension model finished downloading, every `add_fact` raised
`Dimension mismatch` — permanently, on a store that had been working.

Worse, `add_fact`'s `INSERT` commits before the vector write (the connection is
`isolation_level=None`), so the failure was reported for a fact that had in
fact been stored, and every retry of the "failed" accept wrote another copy.

Now the table is **dropped** when the embedder changes so it rebuilds at the
new width, and `_embed_rows` swallows its own failures and returns a count
instead of raising past a committed row.

### 3. `backfill_embeddings()` had no caller, and looped forever if called

The module docstring promises that *"the moment the model appears the
embeddings are backfilled"*. Nothing called it. And its `while True` only broke
on an empty batch — a throwing embedder left `embedded=0` on the same rows, so
the next `SELECT` returned them again, forever. It now stops when a batch
writes nothing.

### 4. Five facts entered every prompt, related or not

`MemoryStore.search` had no relevance floor anywhere: the vector arm is a k-NN
scan that returns its nearest rows for *any* query, and the FTS arm built its
`OR` query from every word including `the` and `is`. So it returned a full five
facts for anything. Measured, asked *"why is the sky blue"*, it injected the
NAS, the car's MOT and the owner's diet; the same store also held their
medication and bank details.

That also made `jarvis_recall.select_facts` dead code, because
`jarvis_hud.py` only falls through to it when the store returns nothing —
and `select_facts`, whose comment reads *"Misleading context is more expensive
than missing context"*, correctly returns nothing for those questions.

Now: content words only in the FTS query, a distance cutoff on the vector arm,
and **no vote at all for a non-semantic embedder**. The hash stand-in measured
AUC 0.73 where chance is 0.50 — giving it an equal vote is what guaranteed a
full five results. On a machine with no model, search is now genuinely
lexical-only, and returns nothing when nothing matches.

### 5. The pre-queue filter discarded statements, not questions

`jarvis_extract` dropped anything under three words or opening with an
auxiliary. Measured against realistic extractor output it threw away
*"Can't eat gluten"*, *"Does not drink alcohol"*, *"Is vegetarian"*,
*"Wife: Dana"*, *"Do not suggest Docker, ever"* and *"Should always use metric
units"* — a coeliac diagnosis and four standing instructions — while keeping
*"Whose birthday is 3 March"*. It was matching the shape of a question word
rather than a question. An auxiliary is only interrogative when a subject
follows it; a wh-word almost never opens a durable fact.

### And the auto-accept branch is gone

`propose()` contained `if _cfg("auto_accept", False) and _cfg("setup_complete",
False) and conf >= 0.8: _accept(...)` — a path that wrote facts with no human
decision, two config lines from live. Combined with defect 1 it would have
silently deleted facts with nobody in the loop. Nothing in Jarvis approves on
the owner's behalf, and a queue whose contents can retire existing facts is the
last place to make an exception. `setup_status()` now reports `auto_accept:
false` unconditionally, because that is now true, and adds `queue_full` so a
client can say when the review queue has stopped accepting work.

### Test it

```
python3 backend/test_memory_safety.py
```

Fifty checks, run against real sqlite stores in a temp dir. Roughly a third are
**controls** — that a genuine correction still supersedes, that on-topic
retrieval still returns the right fact, that an accepted proposal is still
written, that no facts are lost in the embedder swap. Those are the ones that
fail if a fix is reverted or over-applied.

---

# `events-pump.patch`

`jarvis_events.Pump` existed. `POLLERS` listed `_poll_approvals`,
`_poll_power` and `_poll_persona`. The class docstring said *"Started by the
proxy"*. `jarvis_hud.py` is the proxy, and it never constructed one — so the
only event kinds ever published were `activity` and `model`, and `approval`,
which `JARVIS-API.md` documents with a worked example and both clients handle,
had never fired.

The cost is not cosmetic. An event is how a client learns that a gate was
raised or settled. Without it the desktop refreshes only on connect, on a
renumbered resume, or when the owner presses Retry — and the stream lives for
an hour with keepalives, so nothing ever times out. So a gate raised while the
desktop sat idle produced no toast and no tray badge for up to an hour, and an
approval settled on the phone left a live, clickable card on the desktop for
the same hour. The 409 on the second decision is what kept that safe; it should
never have been load-bearing.

The patch is one `Pump(engine=_ENGINE).start()` and a comment explaining why it
is there, plus a boot line so its absence is visible next time.

### Test it

```
python3 backend/test_events_pump.py
```

Ten checks: that a changed queue publishes exactly one event and an unchanged
one publishes none, that the payload truncates its items at ten (which is why
treating `approval` as a doorbell and re-reading `/api/pending` is correct
rather than wasteful), and — the control — that `jarvis_hud.py` still contains
a `Pump(...)` call that is started. That last one fails if the line is ever
removed again.

Run it from a directory holding `jarvis_events.py` and `jarvis_hud.py`.

---

# `appearance.patch`

`appearance.patch` adds the two routes the Faces window already speaks, so a
face chosen on the desktop is the face the phone wears. Without it the picker
still works and saves — it just says, every time, that the choice stayed on
this machine.

## Apply it

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
copy jarvis_hud.py jarvis_hud.py.bak
git apply --verbose path\to\appearance.patch
... and so on, in table order
```

No git in that folder? `patch -p1 < appearance.patch`, or apply the four edits
by hand — the patch is 200 lines and three of the four are one-liners.

Then restart the backend and press **save** in Faces. The line under the
buttons should change from *"saved on this machine only"* to *"saved to Jarvis
— the phone sees this too"*.

## What it adds

| | |
|---|---|
| `GET /api/appearance` | The stored document. Joins the existing desktop-only surfaces, so it carries the same origin and token checks as `/api/models` and `/api/config`. |
| `POST /api/appearance` | Writes it. Joins the existing gated-action tuple and dispatches through `_desktop_action`, like every other write. |
| `~/.openjarvis/appearance.json` | Where it lives — beside `config.toml`, not inside it. |
| an `appearance` event | Published on save, so a client that is already open repaints. Clients that do not know the kind ignore it. |

It does not touch anything else. No existing route changes behaviour.

## Why it is shaped this way

**It is cosmetic, so it is not gated.** The document decides how Jarvis looks.
It approves nothing, starts nothing and reveals nothing, so it needs no
approval and should never grow one. If a field would ever change *behaviour*
rather than appearance, it belongs on a different route.

**It rejects rather than clamps.** An unknown pattern or colour comes back 400
naming the offender. Silently dropping a bad binding would leave the picker
showing a choice that is in effect nowhere, which is worse than refusing and
worse than storing something odd.

**A machine without the spec stores anyway, and says so.** The server never
needed `jarvis-visual-spec.json` before, so it may not have one. Refusing every
write in that case would brick the feature the route exists to enable; instead
the reply carries `"note": "stored without checking it against the visual
spec"`. To get validation, drop a copy of the spec next to `jarvis_hud.py` or
in `~/.openjarvis/`.

**The server stamps `updated`, not the client.** Two devices with two clocks
are the case that field exists to arbitrate, so the one machine both of them
talk to owns it. Last write wins — there is one owner here, and a merge
strategy would be machinery for a conflict that does not happen.

**The write is atomic.** Written to a temporary file and renamed, because a
half-written file here means the owner's face silently reverting.

**`/api/config` was the obvious home and is not one.** It is a deliberate 501:
that file decides what Jarvis may do unattended, and the refusal explains why a
half-built editor for it would be worse than none. Appearance has no such
weight and should not sit behind that review.

## Test it

```
python3 backend/test_appearance.py "path/to/patched/jarvis_hud.py"
```

Fourteen checks against the real `jarvis-visual-spec.json`: that all fifty
colours are found, that an unknown colour is refused rather than dropped, that
`banked` is accepted, that a refused save leaves the stored document untouched,
that a save publishes an event, that a machine without the spec says so, and
that a corrupt file reports itself instead of taking the surface down.

Two of those exist because `python -m py_compile` passed while the patch was
broken twice: `time` was never imported, so every save would have raised
`NameError`; and the palette walk looked for `families[].shades[]`, which does
not exist — the fifty colours are a flat `palette.colors` — so colour checking
was silently finding nothing and passing everything.


---

# `gate-push.patch` — the one to read even if you never set a token

`jarvis_gate._redact` exists for a reason its own docstring states plainly:

> the gate "is handed exactly the sensitive part - the recipient of the email,
> the path of the file, the body of the shell command - so writing `detail`
> verbatim would turn the audit trail into the leak it exists to detect."

The local audit log honoured that. The **push did not**. 130 lines below that
docstring, `_push` sent the identical dict verbatim to
`https://ntfy.sh/<your-topic>`:

```
LOCAL AUDIT:  {"command":"<redacted 35 chars>","recipient":"<redacted 24 chars>"}
SENT TO ntfy: {"command":"grep -r 'password' /home/mario/.env",
               "recipient":"dr.okafor@clinic.example"}
```

An ntfy.sh topic is a URL with no authentication. The topic name is the only
secret, it travels in the path, and anyone who knows or guesses it subscribes
to everything. On tier `notify` this fires with **no human in the loop at
all** — the whole point of that tier is that it does not ask.

It also quietly falsifies the published contract: `risk_for` labels
`read_joplin_note`, `read_files_readonly` and `delete_file` as
`reach: "local"`, which both `JARVIS-API.md` and `JARVIS-FRAMEWORK.md` define
as *"nothing leaves this machine"*. Every one of them pushed outbound once it
reached `notify` or `ask`.

**Mitigating:** it is opt-in — nothing is sent unless `JARVIS_NTFY_TOPIC` is
set. **Aggravating:** ntfy appears in none of the three spec documents, so an
owner who sets that variable to get phone alerts has no way to learn what it
sends.

The patch does three things:

1. **Both call sites redact before sending.** The redactor already existed and
   already keeps enough shape to make a useful alert — you still learn that a
   `send_email` is waiting and how long the body was.
2. **No push at all while the conversation is latched local.** The taint latch
   exists precisely because private content is in play; a push is egress to a
   third party, which is the thing the latch is refusing. It fails closed:
   `taint_active()` returns true when it cannot read its own database.
3. **The `prompt` fallback is gone.** It was the wider of the two leaks —
   prose rather than a dict of keys. The notification is now a doorbell: what
   is waiting, its id, and "open Jarvis to read it". Same rule the SSE
   approval event already follows.

### Test it

```
python3 backend/test_gate_push.py
```

Ten checks against a stubbed network and a stubbed framework — nothing is sent
and no approvals database is touched. Four are controls: that `_redact` still
keeps the keys so the alert means something, that a redacted body reaches the
broker unchanged, and (parsing the source) that **neither** call site passes
raw `detail` or falls back to `prompt`. That last pair is what fails if someone
later "simplifies" the call sites back.


---

# `skill-notes.patch`

`jarvis_skills.refine(name, note)` appends free-text notes to a skill's index
row. Three facts about it, each true in the current code:

- **It is not gated.** `write_skill()` twenty lines above calls
  `_gate("modify_own_code", ...)`. `refine()` calls nothing.
- **Its notes reach the model.** `load()` returns `"notes": row.get("notes")`
  *alongside the body*, so they go into the prompt every time the skill is
  used, and they change what it does.
- **They appear on no surface.** `cards()` — what `GET /api/skills` serves, and
  the only place anything lists skills — returns name, description, trust and
  uses. Not notes.

So: a store of self-authored heuristics, written with no approval, injected
into prompts, invisible to the owner. That is the exact shape this product's
rules exist to forbid, sitting inside the module that otherwise enforces them
best — the one that scans skill bodies on raw bytes before a model sees them
and refuses outright at block severity rather than asking.

**Nothing calls `refine()` today**, which is why it has gone unnoticed. It is a
loaded gun, not a fired one. The patch is here so that stays true when
something does call it — and something will, because "let the assistant record
what it learned" is the single most requested feature in this class.

Two changes: `refine()` goes through `_gate("modify_own_code", ...)` like its
neighbour, with a prompt that shows the owner the note and says it will be read
every time the skill runs; and `cards()` returns `notes`, so anything steering
an answer is on a screen the owner can reach.

That screen is the Brain window's Faculties view: each skill's notes are
listed under it as "Jarvis's note: ..." (`brain.js` `renderSkills`, since
2026-09-23 - before that, the notes were sent and nothing drew them).

This is worth knowing before adopting anything from the self-improving-agent
literature. ExpeL's "Insight Pool" is this, with a research paper behind it. The
delta between a skill bank and an ungated one is approval, not storage — and we
already have the storage.

---

# `documents-honesty.patch`

Two readers, no writer, and a status line that said everything was fine.

`SELECT ... FROM documents` runs twice in `jarvis_hud.py` — in
`collect_documents()`, which builds the document half of the brain map, and in
`retrieval_corpus()`, which builds the text the retrieval trace matches
against. Nothing creates that table. `grep -rn "CREATE TABLE documents"` over
the whole backend returns nothing, and `MemoryStore._init` creates `facts`,
`facts_fts` and `facts_vec` and stops there.

So both queries have always raised `no such table: documents`, and both catch
`sqlite3.Error` and return empty. That is a reasonable thing to do when a
store is merely not set up yet — except that it makes *missing* and *empty*
the same silence, and the one surface that could have distinguished them said
the opposite:

```python
"sources": {
    "documents": DOCS_DB.exists(),     # <- true on every boot
```

`DOCS_DB` is `~/.openjarvis/memory.db`. The memory store creates that file for
its own tables the first time it runs, so `.exists()` has been true since the
first boot of the program and has never once been about documents. The brain
map's source list — the place you would look to find out whether a source is
wired up — reported a working document store on a machine that has never had
one.

## What it changes

A `_has_table(db_path, name)` helper beside `_ro_sqlite`, and three call sites
that ask it instead of asking the filesystem:

| site | was | is |
|---|---|---|
| `collect_documents()` | `if not DOCS_DB.exists()` | `if not _has_table(DOCS_DB, "documents")` |
| `retrieval_corpus()` | `if DOCS_DB.exists()` | `if _has_table(DOCS_DB, "documents")` |
| `build_graph()` sources | `DOCS_DB.exists()` | `_has_table(DOCS_DB, "documents")` |

and the two bare `except sqlite3.Error` returns now print. They were only
defensible while a missing table was the expected case; once the missing table
is ruled out above them, a read that still fails is a real fault and should
say so, the way `build_graph()`'s own per-source handler already does.

## What it does not change

It does not create the table. Nothing writes documents, so an empty table
would be the same nothing with a more convincing shape — and a document
corpus is a decision about what gets indexed and therefore about what a
resembling query can pull into a prompt, which is the owner's call and not a
patch's. The point of this one is that the status line now tells the truth
until that decision is made, so `documents: false` is what you see, and it is
correct.

## Test it

```powershell
python test_documents_honesty.py
```

Sixteen checks. `_has_table` is lifted out of `jarvis_hud.py` with `ast` and
executed against real SQLite files rather than paraphrased in the test, so
what runs is the shipped function: a `memory.db` holding a `facts` table and
no `documents` reads as absent, an empty `documents` table reads as present,
a view does not read as a table, and a corrupt file answers no instead of
raising. Against the unpatched file all sixteen fail.

---

# `memory-prefix.patch`

The recalled-facts block was the first thing in the request.

```python
messages = [{"role": "system", "content": "Things you know about the user..."}] + messages
```

The facts in that block are chosen per question, so the first token of the
request differed on every single turn. llama.cpp — and therefore Ollama —
reuses a cached KV prefix only up to the first token that differs. A changing
token 0 matches nothing, so the **entire conversation** was re-prefilled every
turn: on a 6,000-token history at the ~1,700 tok/s an RTX 2080 Super prefills
an 8B Q4 at, that is several seconds of GPU time per turn, spent re-reading
text the model read a moment ago, and it grows as you talk.

Nothing was wrong with the facts or the injection. It was the position.

## What it changes

The block is inserted immediately before the final user turn instead:

```python
messages = messages[:-1] + [recalled, messages[-1]] if messages else [recalled]
```

Every earlier turn is now byte-identical from one turn to the next, so the
cache matches up to the final question and only the tail is prefilled. The
facts also end up adjacent to the question they were recalled for, which is
where they do the most good.

There is a comment at the call site saying so, because this is the kind of
thing that gets undone by a well-meaning edit: **if delimiters are ever added
around recalled facts, they go on the `recalled` message**. Wrapping the whole
list, or putting a marker at position 0, puts the invalidation straight back.

## And `k=5` becomes `MEMORY_K`

`search(query, k=5)` was a token budget written where nobody would look for
one. Five facts is 100–150 tokens on every local prompt whether or not the
fifth had anything to do with the question. It is now `MEMORY_K`, from
`JARVIS_MEMORY_K`, defaulting to 5 — so nothing changes until you change it.

With `memory-safety.patch` applied the store's search has a distance floor, so
a lower `k` costs nothing on a query that genuinely has less to recall; it only
stops the tail being padded out to five near-misses. Try 3.

## And it puts the persona invariants back

This is the more serious half, and it is not about speed at all.

`ollama/server/routes.go`:

```go
msgs := append(m.Messages, req.Messages...)
if req.Messages[0].Role != "system" && m.System != "" {
    msgs = append([]api.Message{{Role: "system", Content: m.System}}, msgs...)
}
```

**A system message at index 0 suppresses the Modelfile's own `SYSTEM` block.**
Prepending the recalled facts put one there, so `jarvis_persona`'s
`INVARIANT_PROMPT` — *"say what is a guess and what is verified"*, *"never
claim an action was taken that was not"* — was dropped on every local turn
where recall fired, **and only those turns**. The invariants went missing at
exactly the moment the model was holding the user's private facts, and came
back the moment it was not. Nothing surfaced it: the answer just came back
slightly more confident than it should have.

With the block moved off index 0 the Modelfile `SYSTEM` is inserted again —
and it is now a *stable* position 0, which is exactly what a prefix cache
wants. The two fixes are the same edit.

Truncation does not undo it. `chatPrompt` re-collects system messages only
from the region it **skips** (`for j := range i`, `ollama/server/prompt.go`),
and this block is at the tail, in the kept region. The one exception is a
conversation truncated to its final message alone, where there is no prefix
left to preserve anyway.

**One thing to check on the machine**, because it cannot be checked from here:
the HUD posts to `JARVIS_URL/v1/chat/completions`, not to Ollama directly. All
of the above is Ollama's behaviour. If the Jarvis backend normalises the
message list by hoisting system messages to the front before forwarding, it
would undo both halves of this. Worth one look at how it builds its Ollama
request.

## Test it

```powershell
python test_memory_prefix.py
```

Sixteen checks. The ordering expression is lifted out of `jarvis_hud.py` with
`ast` and evaluated, rather than paraphrased in the test, so what runs is the
shipped line. The check that matters serialises two turns that recall
*different* facts over the same history and asserts the prefixes are
identical — with a control that runs the old prepend through the same
assertion and confirms it fails, so the property is known to discriminate.
Against the unpatched file all sixteen fail.

---

# `extraction-wiring.patch`

**`jarvis_extract.propose()` has never been called.**

Grep the tree. Zero call sites. Every other piece of the learning loop works:
the prompt, the `proposals` table, `pending()`, `decide()`, the accept path
that supersedes the fact it replaces, the HTTP routes the HUD already serves.
The banner has been printing `extraction SCAFFOLD — proposals queue for
review` on every boot since it was written, about a queue that could not fill.
The memory store has only ever held what was typed into it by hand.

Apply `memory-safety.patch` first. It is not optional here: the moment
extraction starts producing proposals, the unpatched `_accept` retires a
roughly-matching fact chosen by an unfloored `search(replaces, k=1)`.

## The trigger

A `_Learner` on one background thread, offered the transcript in the chat
handler's `finally`. Three constraints shape it:

**It must not slow the answer down.** Extraction is another full generation on
the same 8B that is answering, on one GPU. Inline it would double the wait for
every turn; concurrent it would halve the speed of both.

**It must not be able to break a turn.** Its own thread, and the `offer()` call
is inside a `try` — a learning pass must never be the reason an answered turn
reports an error.

**Every turn is the wrong cadence.** A conversation is cumulative, so the same
text would be re-read again and again for facts the queue already holds. A
pass runs after **45 seconds of quiet** (`JARVIS_EXTRACT_IDLE`), and then not
again for **5 minutes** (`JARVIS_EXTRACT_MIN_GAP`). `JARVIS_EXTRACT=0` turns
the whole thing off and the banner says so.

There is no clock in the implementation. The idle wait is an `Event` with a
timeout, so a turn arriving restarts it by construction rather than by
comparing timestamps — the version that cannot drift and cannot be confused by
the system clock moving.

## What it reads — user turns only

This is the load-bearing decision, and it is the same cut the cloud lane
already makes twenty lines above, for the same reason the comment there gives:
**the assistant turn is a carrier.** It restates injected memory. It quotes
tool output. A Joplin read comes back through it — and the vault is
deliberately kept out of the retrieval corpus, with a comment saying so,
precisely so that something merely *resembling* it cannot pull it into a
prompt. Extracting durable facts out of a vault read and filing them in memory
would undo that separation quietly and permanently, one accepted proposal at a
time.

So the learner sees what you typed and nothing else. It also means the taint
latch does not need consulting: there is nothing in the transcript it reads
that the latch protects.

The cost is honest and small: a fact the assistant stated and you confirmed
with "yes" is not learned. That is the right side to err on.

## The doorbell

`_poll_proposals` joins `POLLERS`, publishing `kind: "proposal"` with a count
when the queue changes. Without it the queue now fills on its own, having
asked nobody, and the only way to find out is to open the memory pane and
look — so the review queue grows unseen and the learning loop looks broken
from every surface at once.

It carries the **count and the ids, never the text**. A proposal quotes
whatever was said to produce it, and this bus reaches every connected client,
including a phone showing notifications on a lock screen. Same rule as the
approval doorbell.

Clients: `proposal` is a new event kind. A client that does not know it should
ignore it, which every `switch` on `kind` in both clients already does.

## Test it

```powershell
python test_extraction_wiring.py
```

Twenty-two checks. `_Learner` is lifted out of `jarvis_hud.py` with `ast` and
executed with millisecond timings against a fake extractor, so the shipped
class is what runs: a burst of four turns produces one pass and not four, an
unchanged transcript is not sent to the model twice, a transcript containing
nothing you typed does not wake the model at all, and a pass that raises does
not stop the next thing you say being learned from. The transcript assertions
check both directions — your words present, the assistant's Joplin quote and
the recalled-facts block absent. Against the unpatched files all of it fails.

---

# `voice-503.patch`

`jarvis_speech.py` does not exist — not unfinished, absent — so every
`/api/voice/*` route is on its failure path on every request today. They
disagreed about what that looks like:

| route | today |
|---|---|
| `/api/voice/status` | `200` `{"available": false, "error": "ModuleNotFoundError: ..."}` |
| `/api/voice/utterance` | `500` `{"error": "ModuleNotFoundError"}` |
| `/api/voice/say` | `500` `{"error": "ModuleNotFoundError"}` |
| `/api/voice/wake` | the `ImportError` was not caught at all |

A client asking "is the voice path up?" had to recognise four shapes. And the
two 500s are the wrong answer: a 500 says the server broke, and nothing broke
— the module was never installed. That is a 503, which is the code the `say`
route's own no-engine branch already used.

## `client_fallback_ok` is the point

All four now go through one `_no_speech()` helper returning the same body —
but `client_fallback_ok` is set **per route**, because the two directions are
not alike:

| route | code | `client_fallback_ok` | why |
|---|---|---|---|
| `say` | 503 | **true** | speaking text the client already holds reveals nothing and skips no check |
| `utterance` | 503 | **false** | client-side speech-to-text moves the privacy boundary and disarms the owner-voice gate |
| `wake` | 503 | false | there is nothing to switch on |
| `status` | 200 | false | same body; still 200, because "can you speak?" is a question this route *can* answer |

The `utterance` reason says it in words the client author will read:

> do NOT recognise this yourself. Local speech-to-text on the client moves the
> privacy boundary and disarms the owner-voice gate; show that dictation is
> unavailable instead.

## And the `say` permission was too broad

The old reason read *"speak it with your own synthesiser; the text is already
yours, so nothing is revealed"*. True of a synthesiser **on the device**. Not
true of one that ships the text to a vendor to be spoken — which is what
stock Android does by default, and what the sibling client is doing right now.
So the sentence the server sends is narrowed to say on-device, name network
synthesis as egress, and state that the 503 is not permission for it.

Details for the client half are in `docs/ANDROID-VOICE-FALLBACK.md`. **This
patch does not close that hole** — the 503 path *is* the hole. It makes the
contract honest and machine-readable so the client fix has something to read.

## Test it

```powershell
python test_voice_503.py
```

Nineteen checks. `_no_speech` and `_SAY_FALLBACK` are lifted out of the source
with `ast` and executed, so the shipped helper is what runs; the rest walk the
tree and assert that exactly one of the four call sites allows a client
fallback and three refuse it, and that nothing reaches a 500 for a module that
was simply never installed.

---

# `jarvis_speech.py` — the module `voice-503.patch` was answering the absence of

Ships as a whole file, not a patch, the same way `jarvis_research.py` does:
`jarvis_speech.py` does not exist anywhere handed over, so there is nothing to
patch against. It implements exactly the interface the four `/api/voice/*`
routes already expect — `status()`, `hear(raw, source=...)`, `say(text)`,
`set_wake_enabled(enabled)` — using sherpa-onnx, per
`docs/ARCHITECTURE.md`'s "Decisions already taken" table.

**Worth flagging rather than quietly overriding:** `backend/.gitignore` lists
`jarvis_speech.py` alongside `jarvis_hud.py`, `jarvis_memory.py` and
`jarvis_gate.py` — modules confirmed to genuinely exist on the owner's
machine — under the rule "the backend sources themselves live on the owner's
machine, not here... a stale copy in git would be worse than no copy." That
placement, read alone, would suggest a real `jarvis_speech.py` might already
be sitting on the owner's machine, unlike the ten modules rebuilt into
`backend/rebuilt/` because they were confirmed to exist nowhere. Against
that: `docs/ARCHITECTURE.md` §10, "Things that do not exist," states flatly
"`jarvis_speech.py` — absent" with no hedge — contrast the very next line,
about five *other* modules, which says "present nowhere in anything handed
over. **Some may exist on the owner's machine**," a qualifier `jarvis_speech`
pointedly does not get. Read together, the more likely explanation is that
the `.gitignore` entry is prophylactic boilerplate for every known backend
module name rather than a claim that this one currently exists — but this
file is committed with `git add -f` specifically *because* that is a
judgment call on evidence that disagrees with itself, not a settled fact.
**If a real `jarvis_speech.py` does turn out to already exist on your
machine: do not let this one overwrite it.** Diff the two first — this one
was written to the interface the patches already expect, so if the real file
implements the same four functions, keeping yours and discarding this one
loses nothing.

**Changed 2026-09-23:** `apply-patches.ps1` now copies this file in (after
backing up whatever copy is there, into the `_jarvis-backup-...` folder). The
phone's talk button depends on this version - see the `voice-enroll.patch`
section at the end, "the phone never showed its talk button". If you do have
a different, real `jarvis_speech.py`, the backup folder has it.

## Order matters, and it is the one thing this file exists to protect

`hear()` runs the owner-voice check (`jarvis_voice.verify()`, rebuilt in an
earlier pass) **before** it ever runs speech-to-text. A voice that is not the
owner's is never turned into words — refusing after transcribing would leave
a stranger's speech in memory on the way to saying no. `test_speech.py` proves
this with real code, not a comment: it patches the transcription function to
raise `AssertionError` if it is ever called, then drives `hear()` with a clip
that matches no enrolled profile. If the ordering were ever reversed, that
test fails instead of merely reading wrong.

## A disagreement recorded rather than silently resolved

`jarvis-framework.toml`'s own `[voice]` section — the real, checked-in
config — reads `stt_engine = "faster-whisper"` / `stt_model = "small.en"`,
naming a different engine than this file implements, and its own comment
names `openWakeWord` as the wake-word engine. Neither `faster_whisper` nor
`openwakeword` is installed anywhere this was written or tested; only
`sherpa_onnx` is. Rather than overwrite those keys — silently breaking
whatever already reads them — this file adds its own (`sherpa_stt_model`,
`sherpa_stt_tokens`, `tts_model`, `tts_voices`, `tts_tokens`, `tts_data_dir`,
…) and only engages sherpa-onnx STT when `stt_engine = "sherpa-onnx"` is set
explicitly. Until that line is added, `status()` says so in its `note` field
rather than pretending to be the active engine. TTS has no such conflict —
the TOML has no TTS section — so `tts_engine` defaults to `"sherpa-onnx"`.

*Resolved 2026-09-23:* nothing reads the faster-whisper keys, and leaving
them made speech-to-text impossible. The default is now `"sherpa-onnx"` in the
code and the shipped TOML, the model is found by its files, and "Voice that
works" (end of this file) has the line that changes your own TOML.

## What is not here

Model files. No STT model, no Kokoro voice, no Silero VAD weight ships in
this repository or was available anywhere this was built — they are tens to
hundreds of megabytes of binary ONNX assets that belong on the owner's own
machine. Every engine is constructed lazily, on first real use, from paths
read out of `[voice]`; verified against the real, installed `sherpa_onnx`
package that pointing any of its three model configs at a nonexistent path
raises `RuntimeError` — not a hang, not a process abort — so a missing or
corrupt model degrades to an honest "not available" rather than a crash.
`status()` reports `stt_available`/`tts_available` from a cheap file-existence
check, not by constructing the model, so polling it never pays for a load.

**Not done in this pass, and why:** wiring the desktop's mic button to this
module instead of the disabled Web Speech API (`hud_bootstrap.js` §2b, "when
the local pipeline lands, this block is what to delete"). `jarvis_hud.html`'s
actual mic-button JavaScript — what it calls on `start()`, what shape it
expects back — is vendored from the backend and not visible anywhere in this
repository, the same category of gap as `jarvis_gate.py`'s real interface.
Building a replacement without seeing what it replaces would be guessing at
an invisible contract, which is exactly what this project's own rules exist
to prevent. What is real and ready for that wiring: the four routes above,
backed by real code, reachable the moment `stt_engine`/`tts_engine` name
`sherpa-onnx` and the model paths point at real files.

**Also not done:** routing `set_wake_enabled()` through an approval gate.
The route's own comment says turning on the wake word "is gated as
`change_own_config`, because widening where Jarvis listens is a change to
its exposure" — but `jarvis_gate.py`'s real `check()`/`decide()` signature is
not visible anywhere in this repository either, so `set_wake_enabled()` here
takes effect immediately, in its own small state file
(`~/.openjarvis/voice/wake_override.json`), deliberately not the framework
TOML. Wiring a real gate check in front of it is left for whoever holds
`jarvis_gate.py`'s actual source, the same shape of gap already recorded
above for the secret-scan and denial-constraint features. *Resolved
2026-09-23:* turning it ON now raises one card through `jarvis_gate.check()`,
the call `jarvis_voice_enroll.py` already makes; OFF stays immediate.

## Test it

```powershell
python test_speech.py
```

Twenty-two checks, against the real `sherpa_onnx` package and the real
`jarvis_voice` gate — no mocks for either. A synthesised WAV clip is encoded,
decoded and compared sample-for-sample; a real spectral voice profile is
enrolled and then matched against the same clip and refused against a
different one; engine construction is pointed at files that do not exist and
confirmed to degrade rather than raise or hang; and `status()` is proven not
to construct an engine just to report on one.

---

# `degrade-filter.patch` — read this one first

**A cloud turn that stepped down to the local model and back out again sent
the whole transcript upstream, unfiltered.**

The cloud-lane control is one comprehension near the top of the chat handler:
on a cloud decision, keep only `role == "user"` messages. Its comment explains
why at length and the reasoning is right — the assistant turn is a carrier, it
restates injected memory, so only what you typed goes out.

It runs once. `is_cloud` is computed once, above the degrade loop, and never
re-evaluated. The loop then has a branch that, on landing at the local model,
restores the **raw client transcript**:

```python
if lane == local_model and not decision.inject_memory:
    messages = body.get("messages") or []
    decision.inject_memory = True
```

and nothing ever put the filter back. The loop is sized `len(lanes) + 2`
*precisely because* it expects hops after that one. Reproduced by executing the
real loop:

```
cloud -> 429 -> local -> 503 -> back out to cloud
  jarvis-escalate  roles=['user','user']
  qwen3:8b         roles=['user','assistant','user']
  jarvis-critic    roles=['user','assistant','user']   <- LEAK
```

The other direction needed no rebuild at all. A **local** turn carrying the
recalled-facts block had no guard whatsoever against `degrade()` returning a
cloud lane, and the facts went with it.

The loop's own comment says *"downward only, never back into the lane that
just said no"*. That is a contract with `jarvis_router`, and the loop never
checked it. The fix does not need the contract to hold: it re-derives the
filter from the lane it is **about to call**, on every hop, and clears the
route header's memory claims when it does. Stripping the recalled-facts block
is free, because that block is a system message.

## Step events for Brain -> Live (`jarvis_agent.py`, 2026-09-23)

While it answers with tools switched on, `jarvis_agent.run_local_turn` now
publishes a `step` event on the one bus for each step: asking the model,
each tool starting, finishing or being refused, and writing the answer.
Brain -> Live on the desktop shows them. A step carries only names from
Jarvis's own tool table and a yes/no - never a tool's arguments or result,
and never the model's own reasoning, because the bus also reaches the
phone's lock screen. `apply-patches.ps1` already copies `jarvis_agent.py`
in, so there is nothing extra to do. Tests: the four `t_*step*` tests in
`test_agent.py`.

## A picture stays local, always (`choose()`, 2026-09-23)

A screen capture (Alt+Shift+S on the desktop) can show anything that was on
screen - an email, a file, a password manager - and none of the text checks
in `choose()` can read a picture. `choose()` used to escalate a turn with a
picture like any other long question, and even picked a cloud lane with
"vision" in its name. It now pins any turn with `has_image` to the local
lane, gate `"image"`, right after the taint gate (`rebuilt/jarvis_router.py`,
edited in place like the gate below). Test:
`test_rebuilt.Router.test_a_picture_never_goes_to_a_cloud_lane`, which fails
on the old router.

The catch, said plainly: the local model today (`qwen3:8b`) cannot see
pictures. The desktop now checks that with Ollama before sending one and
offers to send the words alone (`jarvis-desktop/src-tauri/src/vision.rs`).
A picture-capable local model, such as `qwen2.5vl`, would need more graphics
memory than the current card has spare; the planned second card is the place
for it (`docs/MODEL-TOPOLOGY.md`).

To take this change, copy the rebuilt router over the one in your backend
folder (it is not one of the files `apply-patches.ps1` copies for you), then
restart the backend. One line, in PowerShell:

```powershell
Copy-Item -LiteralPath "C:\Users\pcadmin\Epic-Jarvis\backend\rebuilt\jarvis_router.py" -Destination "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\" -Force; Write-Host "Copied jarvis_router.py into the backend folder. Restart the backend to use it."
```

## The other gate in `choose()`, added since: a pasted secret, not just the word for one

`jarvis_router.is_private()` catches a *topic word* — "what's my api key" —
and nothing ever scanned for the secret **itself**: a `.env` line, a stack
trace, a token pasted with no matching word nearby. `choose()` now has a
sixth gate, `looks_like_a_secret()` (`jarvis_router.py`, not a patch — it is
a rebuilt module, edited in place), checked right after `is_private()` and
before complexity: a private key block, an AWS/GitHub/Slack token, a JWT, a
bearer header, or a labelled `key: <value>` assignment pins the turn local
the same unconditional way `is_private`/taint already do. The reason string
names *what kind* of secret it looked like and shows four characters plus a
length — never the value itself, so the confirmation that protection fired
cannot become a second place the secret is readable in full.

Deliberately narrow: known, low-ambiguity shapes rather than a generic
high-entropy heuristic. A false negative here still has to clear
`is_private`, taint, complexity and budget; a false positive on this gate
only costs answer quality (local instead of cloud), never privacy — which is
the right side to be wrong on, so the patterns lean toward specific shapes
that explain themselves rather than a broad net that flags everything and
means nothing. Five new tests in `test_rebuilt.py`'s `Router` class (which
had nine already, for `is_private`/taint/degrade): every listed shape is
caught, ordinary text and a bare hash are not, the secret never appears
verbatim in the reason, and a message with the shape but no matching keyword
is still caught (`is_private` must not be what is doing the work in that
one).

**Not built, and worth saying plainly rather than leaving quiet:** this
downgrades silently, the same as `is_private`/taint already do — it does not
pause and ask via the approval queue (`jarvis_gate`). That queue's own
`check()`/`decide()` functions are not visible anywhere in this repository —
every patch that touches `jarvis_gate.py` does so through narrow, pre-existing
diff context, none of which happens to include the function signature — so
wiring a genuine "confirmation card" through it would mean guessing at an
API this session cannot verify, which is worse than not building it. What
ships is the part that matters most and is fully verified: the secret never
reaches a cloud lane. Turning the after-the-fact notice into an actual card
on a client is future work for whoever has `jarvis_gate.py` open.

## Test it

```powershell
python test_degrade_filter.py
```

Eleven checks. The degrade loop is lifted out of `jarvis_hud.py` with `ast` and
executed against a stub router that deliberately **breaks** the downward-only
contract, because that is the case the code was trusting. Two controls: the
local-rebuild branch beside the fix must still restore the full transcript, and
a cloud turn that never degrades must be untouched. Against the unpatched file,
five of the eleven fail — including both leaks.

---

# `vram-estimate.patch`

`jarvis_models.estimate_vram_mb` is what advises on model choice, and it was
wrong in both directions at once, which is presumably why nobody noticed.

- **`cache_bits: int = 8`** — a `q8_0` cache — while nothing in the tree sets
  `OLLAMA_KV_CACHE_TYPE`, so Ollama was running `f16` and every estimate was
  ~47% light on the KV term. Now read from the environment, defaulting to 16.
  And `q8_0` is not 8 bits: llama.cpp stores 32 values in 34 bytes, so it is
  **8.5**. (Ollama's own estimator rounds this to 8 and under-counts by ~6%.)
- **The batch surcharge was not modelled at all.** `server/sched.go` adds a
  flat **768 MiB at `num_batch >= 1024`** and **2 GiB at `>= 2048`**, and
  Ollama's auto-batch reaches for those when it thinks there is headroom. An
  estimate could say a model fits and then Ollama would spill it.
- **`assume_context` capped at 8192**, so a model you intend to deploy at 16K
  was judged as if it were at 8K and `fits_with_margin` waved it through. Now
  16384.
- **`RUNTIME_OVERHEAD_MB = 1500`** is left at 1500 and made overridable rather
  than "corrected". The measured parts are the CUDA context (~330 MiB) and the
  compute buffer (~250–350 MiB at `num_batch 512`), so ~650 MiB — but this
  estimate is deliberately a floor, and the cost of being wrong downward is a
  model that spills and runs at a fifth of the speed. Named and overridable
  beats silently optimistic.

See `docs/MODEL-TOPOLOGY.md` for what to do with the corrected numbers.

---

# `memory-pane.patch`

Extraction fills a review queue on its own now. Before these routes there was
no way to read that queue, no way to see what had already been accepted, and
**`MemoryStore.retire()` had no caller anywhere in the tree** — so a fact, once
in, was in.

| route | |
|---|---|
| `GET /api/memory/facts?limit=` | every fact, newest first, **retired ones included**, each marked `current` |
| `GET /api/memory/export` | the whole store as JSON, for a copy that does not depend on this program continuing to work |
| `POST /api/memory/forget` | `{id, valid_to?}` → `retire()`. Its first caller. |
| `POST /api/memory/edit` | `{id, text, valid_to?}` → supersede |
| `POST /api/memory/learning` | `{enabled}` → the switch |
| `POST /api/memory/sleep_time` | `{enabled?}` and/or `{remind?}` → the overnight-offer card's own "enable" / "stop asking" actions |

## Four things it deliberately does

**Forgetting retires; it does not delete.** The row stays and stops being
current. A bi-temporal store whose interface deletes rows is not bi-temporal,
and the reply says so in words: *"retired, not deleted — it stops being
recalled and stays in the history. There is no undo for this."*

**Editing supersedes.** `add_fact(text, supersedes=id)`, never `UPDATE facts`.
Overwriting the text in place would throw away *when the old wording was
true*, which is the one thing this store exists to keep. An edit that changes
nothing returns `unchanged` rather than writing a new row.

**Retired facts are shown, not hidden.** A pane listing only current facts
makes a superseded fact look deleted when it is not.

**One integer id per write, no list form.** Same rule as
`/api/memory/decide`. Forgetting is irreversible, so a list form would be an
approve-all with another name.

**A correction can be backdated.** `bitemporal.patch` gave `retire()` a
`valid_to` parameter and `add()` a documented workflow for using it — "call
retire() with the real date before adding" — the moment this store learned
"I moved in January" told in March. Nothing called either with a date until
now: both routes always retired at "now", so the one case bitemporal.patch
was built for was unreachable from any real UI. Both `forget` and `edit`
now accept an optional `valid_to` (a unix timestamp) and pass it straight to
`retire()` — `edit` calling it *before* `add_fact(supersedes=id)`, which is
the order `add()`'s own same-fact fallback needs to backdate correctly
rather than silently retiring at "now" regardless of what was sent. Omit it
and both behave exactly as before.

## The overnight-memory offer

`GET /api/memory/pending` now carries `setup.sleep_time_offer`:
`jarvis_sleep.reminder_card()`, unedited, since a client that reads `setup`
for one thing should not need a second route for a related one. The card is
`null` most of the time — it is once-a-day, server-side, and null whenever
the pass is already on, reminders are off, or today already offered it once.

**Only a client that shows the card gets it - `?sleep_offer=1`** (changed
2026-09-23). `reminder_card()` marks the day's offer as made the moment it
is *called*. It used to be called on every read of this route, and the HUD
page reads the route at load, on every `proposal` event and every 30
seconds - without ever showing the card. So the HUD usually used up the
day's card before the Brain window or the phone looked. Now the route calls
`reminder_card()` only when the request says `sleep_offer=1` (exactly `1`);
the Brain window and the phone send it, the HUD does not. Of those two,
whichever asks first on a given day still gets the card and the other does
not, until tomorrow - the same once-a-day contract `jarvis_sleep.py` always
had. The line lives in this patch; `feedback.patch` quotes it as context.

**What the card says is now true.** The pass it offers is not built
(`jarvis_sleep.status()` says `"implemented": false`), and the card used to
say it would "merge duplicates and retire facts that newer ones replaced" -
which, if it were ever built that way, would retire facts with nobody
deciding each one. The rebuilt `jarvis_sleep.py` card now says it is not
built, that switching it on only records the wish, and that no fact is ever
changed or retired without the owner's yes on that one fact. That file is
now copied in by `apply-patches.ps1` (`$SHIPPED`), because the owner's copy
carries the old words.

`POST /api/memory/sleep_time` answers the card's own three actions. "enable"
and "stop asking" are one write each — `jarvis_sleep.set_enabled()` /
`set_remind()`, added alongside this route, in the same `CONFIG_DIR` JSON
sidecar `extraction-wiring.patch`'s `learning.json` already uses for the same
reason: the TOML is the owner's own hand-edited file, and neither switch was
ever going to rewrite it from an HTTP handler. "not now" sends nothing at
all — the card already tracks "already offered today" itself, so a dismiss
with no write still does not return until tomorrow.

## The learning switch, and its floor

`learning_enabled()` reads `CONFIG_DIR/learning.json`, so the pane can turn
extraction off without an environment variable and a restart. **`JARVIS_EXTRACT`
is a floor it cannot lift** — an environment variable is the owner speaking
before the process started, and a switch in a window must not override that.
Setting it on while the floor is down returns `enabled: false` and says why,
rather than reporting a success it did not achieve.

A missing file reads as **on**, matching the shipped default. Inventing "off"
from an absent file would silently disable a feature the boot banner says is
running.

**Switching it on starts the learner** (fixed 2026-09-23, in
`extraction-wiring.patch`'s `set_learning()`). The learner thread is started
at boot only when learning is already on, and the switch used to write
`learning.json` and nothing else - so on a backend that booted with learning
off, "Start learning" said "Learning is on." and nothing ran until a
restart. Now `set_learning(True)` also calls `LEARNER.start()`, which does
nothing if it is already running. And **switching it off drops a pass that
was already waiting** for the conversation to go quiet: `_pass()` reads the
switch again before it asks the model. `backend/test_memory_honesty.py`
proves both, on the learner as the patch stack writes it.

## Ordering

This is the one patch with a real dependency: `extraction-wiring` defines
`learning_enabled()` and `set_learning()`. Apply that first. The other eleven
still commute.

## Test it

```powershell
python test_memory_pane.py
```

Forty-one checks. The switch and the query-string clamp are lifted out of
the source with `ast` and executed — including that a corrupt switch file reads
as on rather than raising, and that `limit=all`, `limit=-1` and
`limit=99999999` reach a `LIMIT` clause as the default, 1 and 5000 rather than
as a traceback. The rest are controls on shape: that no write route grows a
list form, that `forget` calls `retire()` and not a `DELETE`, that `edit` never
emits an `UPDATE`, that both new read routes are actually in the whitelist
— because a route nothing can call is the defect this project keeps producing
— and that `valid_to` actually reaches `retire()` on both routes, rejects a
non-numeric value, and is applied *before* `edit` supersedes rather than
after, which is the one ordering that makes a backdated correction land as a
correction rather than as "now" regardless of what was sent.

---

# `token-file.patch`

**The Android client has never been pairable, on any install, since it was
written.**

It authenticates by token alone — it sends no `Origin`, so the origin check
cannot help it — and nothing in this project has ever generated a token.
`docs/INSTALL.md` already lists that as an unbuilt piece. A secret nobody
creates is not a default, it is a missing feature.

The same fix closes a smaller hole: with no token, every process on this
machine can `GET /api/events` and read the doorbell — what is waiting and how
much of it. Not catastrophic on a single-owner workstation, since anything
that could subscribe could also read `~/.openjarvis` directly, but it costs
nothing to shut.

## What it does

`HUD_TOKEN` in the environment still wins, unchanged — someone who set it
meant it, and nothing is written in that case. Otherwise the server reads
`~/.openjarvis/token`, and writes a `secrets.token_urlsafe(32)` if it is not
there. Written beside and renamed, then `chmod 600` on a best effort: a
half-written token is a token that does not match, which looks exactly like an
attacker to every client at once.

The boot banner prints **the path, never the token** — a token echoed to a
terminal is a token in a scrollback buffer.

**It degrades rather than dying.** A config directory it cannot write returns
empty and falls back to the old tokenless loopback behaviour. A read-only
folder should cost the phone its pairing, not cost the owner their assistant.
The non-loopback refusal still fires in that case, and now explains that a
token is normally made for you, so reaching that message means a permissions
problem rather than a missing step.

## The desktop half

`commands.rs` gains a third fallback in `jarvis_token_for`: settings store →
environment → `~/.openjarvis/token`. Without it the desktop would be locked
out of its own backend by a secret generated on its behalf. It honours
`OPENJARVIS_CONFIG_DIR` because the backend does — reading a different
directory from the one the server wrote to is the whole failure this avoids.

`app.path().home_dir()` rather than the `dirs` crate. Tauri already resolves
this and `windows.rs` uses the same API for `widget.json`; a new top-level
crate for one lookup is a new thing to audit and pin.

## Test it

```powershell
python test_token_file.py
```

Seventeen checks against the real `_resolve_token`, lifted with `ast`. A second
call returns the *same* token, because regenerating on every boot would unpair
the phone on every boot. An all-whitespace `HUD_TOKEN` falls through instead of
disabling authentication — `$env:HUD_TOKEN=""` in PowerShell sets it empty
rather than unsetting it. And the unwritable-directory case patches
`Path.write_text` to raise rather than using `chmod`, because root ignores
directory permissions and Windows ignores the mode bits entirely — the chmod
version would have passed for the wrong reason on both.


---

# `bitemporal.patch` — the second time axis

Apply last. Needs `memory-safety` and `memory-pane`.

## The case it exists for

*"I moved in January. I'm telling you in March."*

Before this patch that sentence is unstorable. `retire()` stamped `valid_to`
with `time.time()`, so you got one of two wrong answers:

- retire in March → the store says Mario lived in Lisbon until March, which is
  false about the world, and "where did I live in February" answers wrong.
- backdate to January → the store says it knew in January, which is false
  about Jarvis, and cannot explain the Lisbon answer it gave in February.

Both matter. The first is what a person asks about. The second is what
explains an answer Jarvis already gave — and with the review queue it is not a
corner case, because a proposal accepted three weeks late is *exactly* this
shape.

## What changed

`facts` gains one column:

```
valid_from, valid_to   when the fact was TRUE          (valid time)
created,    retired_at when WE believed it             (transaction time)
```

`retire(id, replaced_by=None, valid_to=None)` now stamps both. `retired_at` is
always now, because that is when we learned. `valid_to` defaults to now and is
the parameter to pass when you know better.

`MemoryStore.known_at(when)` is the query the column buys: what this machine
believed at a past moment, right or wrong. A fact entered on Tuesday and
retired on Friday is in Wednesday's answer and not in today's.

## The migration, and what it cannot recover

Existing stores are altered in place — `ALTER TABLE facts ADD COLUMN
retired_at REAL`, guarded by a `PRAGMA table_info` read rather than a
try/except, so a real failure is not swallowed as "already there". Rows
retired before the column existed are backfilled `retired_at = valid_to`.

**That backfill is a guess and the patch says so in the code.** Back then the
two axes were the same number, so every historical retirement now reads as
"we learned the moment it stopped being true". That is often false and there
is no way to recover the truth. Only new retirements record both honestly.

## A control the patch also fixes

Three places computed "is this fact current". One of them said
`f["valid_to"] is None`, directly below a line that said
`valid_to is None or valid_to > at`. Unreachable while `retire()` could only
stamp `now`; reachable the moment it takes a date. A lease that ends in
December is true today, and all three places now agree about that.

## Where it is visible

Not a column nobody reads:

- `GET /api/memory/facts?known_at=<epoch>` answers from `known_at()` and
  labels itself read-only.
- A `brain_memory_as_of` command — its own command, not a `brain_read`
  section, because that table maps a name to a fixed path with no parameters
  on purpose, and letting a window append a query string to an allowlisted
  path would widen the grant.
- A **What did you know on…** button in the Brain's Memory tab. While a past
  date is showing, every editing control is gone and `memoryWrite` refuses,
  because a Forget button acting on today's store while the owner looks at
  last June is a trap.
- Each row shows `learned N ago` and `true until X, noticed Y` **only when the
  two dates differ by more than a day** — otherwise it would be noise on
  every row.

`test_bitemporal.py`: 32 checks. Twelve of them fail on the unpatched tree.


---

# `embedding-guard.patch` — a broken embedder must not write invisible rows

Needs `memory-safety`. Independent of everything else.

`_pack` is `struct.pack(f"{n}f", *v)`. It accepts NaN and infinity silently,
and `FastEmbedder.embed` was:

```python
def embed(self, texts):
    return [list(map(float, v)) for v in self._m.embed(list(texts))]
```

No finite check, no zero check, no width check. A NaN reaching `facts_vec` is
not a row that ranks badly — **every distance comparison against NaN is false,
so the row can never be returned, and nothing anywhere says so.** The fact
looks stored, `embedded` reads 1, and it is gone from semantic recall for good.

All-zero is the other shape of the same bug, and it is the one Jan documents in
`readiness.ts`: cosine divides by the norm, so a zero vector makes every score
NaN rather than merely inaccurate.

`_usable_vector(v, dim)` now gates both call sites.

- **Writing:** a bad vector is skipped and the row is left `embedded=0`,
  exactly as a failed INSERT already was — so the fact is still found by
  keyword and the backfill retries it when the model is working again. Storing
  it anyway would be a row that can never be returned and never be noticed.
- **Reading:** a bad *query* vector is worse than a bad stored one, because it
  does not fail. It ranks the whole table by distance-from-nonsense, and RRF
  then lets that noise outrank the real keyword hits. The vector vote is
  dropped and FTS5 answers alone — the same thing that happens on a machine
  with no embedding model.
- **Saying so:** `status()` grows `bad_vectors` and a sentence explaining it,
  **only when the count is non-zero**, because a permanent `bad_vectors: 0`
  would be noise on every screen that renders status.

Rejected: NaN, ±inf, all-zero, near-zero (float error means exact zero is not
the only route to garbage), the wrong width, a non-list, a string inside, and
`True` — which is an `int` subclass and would otherwise pack as `1.0`.

Borrowed from `evaluateEmbeddingVector` in janhq/jan,
`extensions/llamacpp-extension/src/readiness.ts`, Apache-2.0. See
`docs/COMPARISON.md` §3.

`test_embedding_guard.py`: 24 checks, 7 of which fail on the unpatched tree.


---

# `gpu-offload.patch` — say when the model fell off the graphics card

Independent of the others.

llama.cpp fits as many layers as it thinks will fit and silently runs the rest
on the CPU. **Ollama reports the model loaded and healthy either way.** Nothing
errors, nothing warns, and the only symptom is that answers take fifteen
seconds instead of two — at which point the owner blames the assistant rather
than the fit.

`MM.offload_status()` reads `/api/ps`, which carries `size` and `size_vram`
per loaded model, so the split is a subtraction:

| reading | status | what it means |
|---|---|---|
| `size_vram == size` | `gpu` | what you want; says nothing |
| `size_vram == 0` | `cpu` | none of it is on the card |
| in between | `partial` | some layers spilled; this is the common one |
| no models | `idle` | Ollama unloads after a few minutes; normal |

Jan's equivalent compares a hardware GPU count against the engine's device
count, which catches only the all-CPU case. The subtraction catches partial
spill too, and partial spill is the commoner failure.

Surfaced in `_models_view()` — the one screen that says which model is running
is the screen that has to say whether it is really on the card — and as a
banner in the Brain's Models pane, **shown only when the answer is bad**. A
banner on the healthy path is noise on every visit.

Never raises, never blocks: a four-second budget on loopback, and every
failure reports `unknown` rather than inventing a number. A `size` of zero,
which happens while a model is still loading, is not a divide-by-zero and is
not called a failure.

`test_gpu_offload.py`: 26 checks, 15 of which fail on the unpatched tree. It
also asserts that the only URL the check ever touches is loopback.

Idea from janhq/jan `extensions/llamacpp-extension/src/readiness.ts`
(Apache-2.0). See `docs/COMPARISON.md` §3.


---

# `gate-outcome.patch` — a timeout is not a refusal

The database always knew the difference: `approvals.state` is
`pending|approved|denied|expired`. `Verdict` did not. By the time a caller saw
the answer, "a person said no" and "nobody was there" differed only in the
wording of a sentence, so telling them apart meant matching prose.

They need different handling. **A denial is an answer** — do not retry, the
person decided. **A timeout is the absence of one** — worth asking again when
the owner is back, worth counting (a run of them means notifications are
broken, not that the owner is refusing things), and it should read differently
on a screen.

`Verdict` gains `outcome`, one of `auto` / `notify` / `approved` / `denied` /
`timed_out` / `refused`, plus a `timed_out` property.

Two things make it safe rather than decorative, both from codex by way of
`docs/PEERS.md`:

- **The default is `refused`, never anything permissive.** codex's
  `impl Default for ReviewDecision` returns `Denied` for the same reason: a
  new construction site that forgets the field must fail closed.
- **`__post_init__` enforces the invariant**: only `auto`, `notify` and
  `approved` may carry `allowed=True`, and an unrecognised outcome is coerced
  to `refused` rather than raising — because this runs on the path that
  decides whether a tool may act, and an exception there looks like a crash
  rather than a refusal.

`gate_tool` now says something different on a timeout. That string goes back
to the **model** as the tool result, and "denied" tells it to find another way
— which, for a tool the owner would have approved, means routing around a gate
nobody answered.

## Added since: a denial can teach a standing rule — but only as a proposal

A prior audit found the gap and the raw material for closing it in the same
pass: every `check()`/`decide()` branch already calls `_audit(...)`, so a
structured, queryable record of every denial (`approvals.state`, the action,
who decided) has existed since this patch landed — nothing had ever read it
back to learn anything from it. "The owner said no to this once" just stayed
a line in a log.

`Verdict.outcome == "denied"` now calls `_propose_constraint_from_denial(action,
detail)` — added to both places a denial is returned (the on-time path and the
late-poll path; `timed_out` calls it from neither, on purpose: nobody decided
anything there, and seeding a rule from silence would teach Jarvis something
that never happened). It builds one plain-language sentence — *"Remember
this: I do not want Jarvis to `<action>` without asking me first. I just said
no when it asked."* — and hands it to `jarvis_extract.propose()` tagged
`source="gate_denial"`.

**Why `propose()` and not a direct write.** It is the one choke point every
fact this project learns already goes through — `memory-safety.patch` removed
the single auto-accept branch that used to live inside it, specifically so
nothing writes to memory without a human deciding. A denial calling
`store.add_fact()` directly would be a second, parallel door into the same
room: the exact shape `no-auto-approve.patch` (next section) found and fixed
one gate up. So a denial only ever *proposes* — the candidate lands in the
same review queue as every extracted fact, "Keep" or "Discard" in the Brain
window's Memory tab, one at a time, same as always. Best-effort: a failed or
missing `jarvis_extract` import is swallowed, because a completed denial must
never become an error the owner has to do something about.

Two new tests in `test_gate_outcome.py`, stubbing `jarvis_extract` the same
way the rest of the file stubs `jarvis_framework`: a real denial (the same
thread-and-poll setup `t_a_real_denial_is_denied` already uses) calls
`propose()` exactly once, tagged correctly, naming the denied action; a real
timeout calls it zero times. The function itself was also run directly
against a stub outside the full gate loop — normal call, a missing
`jarvis_extract` module, a `propose()` that raises, and an empty action name
all verified not to leak an exception past the function's own boundary.

**Not built:** a "confirmation card" surfacing this on a client. That would
mean this becoming its own gated, tier-`ask` action through
`jarvis_gate.check()`/`decide()` — but neither function's signature is visible
anywhere in this repository (every patch touching `jarvis_gate.py` does so
through narrow, pre-existing diff context that never happens to include the
function definitions themselves), so calling into either from here would be
guessing at an interface this session cannot verify. What ships instead
already satisfies the invariant that matters: nothing is written to memory
without a human decision, via the exact same review queue every other
learned fact already goes through — silently proposed, not silently applied.

---

# `no-auto-approve.patch` — there was an approve-all in the gate

Found by `test_gate_outcome.t_there_is_still_no_approve_all` on its first run.

`confirm_auto()` returned `True` for tiers `auto`, `notify` **and `ask`**,
refusing only `never`. `ask` means a human decides one action at a time. This
granted every future, unnamed `ask` action for the life of the process on the
strength of one CLI flag typed once.

`docs/ARCHITECTURE.md` invariant 3 reads: *"No auto-approve anywhere, and no
approve-all control anywhere. One action, one decision. Do not build one."*
This was one, and it sat inside the module that enforces the rule, with a
docstring explaining why it was fine.

It had **zero callers**, which is the only reason it never granted anything.
That is not a defence: the next person to wire up `--auto-approve` would have
found it here looking intended.

Now it delegates to `confirm`. The symbol still resolves, so anything on the
owner's machine that wired it keeps working — it just asks. The flag becomes a
no-op rather than a bypass and says so on stderr once per process, because a
flag that silently stopped working is its own kind of lie.

**The old docstring's objection is answered, not ignored.** It argued that
gating the flag "would silently redefine a documented flag". True. The flag's
documentation is not the authority; the invariant is. A tool that asks when
you told it not to is a nuisance. A tool that acts when you would have said no
is the thing the gate exists to prevent.

`test_gate_outcome.py`: 30 checks, 11 of which fail across the unpatched pair.
The load-bearing one is *"an ask-tier action is NOT granted by the flag"* —
it fails on the unpatched tree, which is what makes the finding real rather
than theoretical.


---

# `memory-noise.patch` — a discarded fact must stay discarded

Two refinements taken from projects that hit the problem first.

## 1. Discarding did not work

`propose()` deduped against `state='pending'` only. The learner re-reads the
**whole** conversation on each pass, and the transcript grows every turn, so
the "nothing new was said" guard does not stop it. You discard *"Mario drives
a 1998 Volvo"*, the same sentence is still in the transcript, the model
proposes it again, and it is back in the queue within the minute.

A review queue that re-asks what you just declined trains you to stop reading
it — which costs more than the feature is worth, and is how you end up at Open
WebUI's #18603, where users ask to switch memory off entirely.

Now `state IN ('pending','rejected')`.

**`accepted` is deliberately not in that list.** An accepted proposal became a
fact, and `propose()` already checks the current facts; adding it would
wrongly suppress a re-propose after the owner *retires* that fact and
genuinely wants it back. There is a test for exactly that.

## 2. Recalled facts carried no date

Khoj injects memories as `- [{friendly_dt}]: {raw}` — the one small thing in
that project worth copying outright. Undated, a fact is asserted flatly: the
model cannot know *"Mario lives in Lisbon"* was true eighteen months ago and
says it as though it were checked this morning.

It is worth more here than to Khoj, because this store retires rather than
deletes and now carries two time axes. `created` is printed — when **this
machine was told** — because that is what the owner can check against their
own memory of the conversation; `valid_from` would be when the fact became
true in the world, which for most facts is the extractor's guess. The prompt
says which of the two it is, because an unexplained date invites the model to
read it as the other one.

`chosen_facts` had to start carrying `created`: it was built as
`{"text", "id"}` and dropped every other column, which is why the first
version of the helper printed no date on the path that supplies almost every
fact.

A fact with no usable date prints without one rather than with a wrong one —
`- text`, exactly what the model saw before. Tested against a missing key,
`None`, a string, zero and a negative.

`test_memory_noise.py`: 17 checks, 6 of which fail on the unpatched tree.


---

# `decide-once.patch` — one human decision, at most one fact

Found reading `decide()` during a self-improvement audit — not reported by
any test, because none existed for this file's concurrency.

## 1. `decide(id, True)` was a plain check-then-act

```python
row = c.execute("SELECT * FROM proposals WHERE id=? AND state='pending'", ...).fetchone()
if not row:
    return None
if accept:
    return _accept(c, store, dict(row))
```

Nothing sits between the `SELECT` and the `UPDATE` `_accept()` eventually
issues. Two concurrent calls for the same id — a double-tap, a retried
request, two devices open on the same review card — can both read
`state='pending'` before either commits, and both then call `_accept()`.
`store.add_fact()` already serialises its own writers, so nothing crashes and
nothing corrupts; it just quietly writes the same fact twice for one decision
the owner made exactly once.

Reproduced with a `threading.Barrier` forcing simultaneous release rather than
`Thread.start()`'s natural stagger, which is wide enough on a fast local
sqlite file that the race often does not show up on its own: twelve threads,
released together, twelve accepted results, twelve fact rows, from one
proposal.

Fixed by making the `UPDATE` the claim, not the consequence: `SET
state='accepting' WHERE id=? AND state='pending'`, checked by `rowcount`
before anything else runs. The loser sees exactly what an already-decided
proposal looks like — `None` — instead of a race. A rejection is the same
shape: `UPDATE ... WHERE state='pending'`, `rowcount` decides the return
value, no separate read at all.

## 2. A full queue dropped proposals with nothing to show for it

```python
if text.lower() in known or text.lower() in have or pending_n >= cap:
    continue
```

Three different reasons to skip a proposal, folded into one `continue`. Once
the queue hit its cap, every further proposal that extraction pass produced
went on the floor — `queue_full` stayed a boolean, and a client watching it
could not tell "nothing new to learn" from "still learning things, and losing
all of them".

Split apart now, and the cap branch counts: `setup_status()["dropped_full"]`,
a running total for the process's life, present only once something has
actually been dropped — a permanent `dropped_full: 0` line would be noise on
every screen that renders this, the same rule `jarvis_memory`'s `bad_vectors`
counter already follows.

## Ordering

Needs `memory-noise`: its context is that patch's `state IN
('pending','rejected')` dedupe query.

## Test it

```powershell
python test_decide_once.py
```

Fourteen checks. The concurrency one is real, not simulated — real threads,
a real sqlite file, released together by a barrier — and it fails three ways
on the unpatched tree: more than one winner, fewer `None`s than losers, and
more than one fact actually written.


---

# `event-allowlist.patch` — a denylist ships whatever nobody remembered

Found by `test_gate_egress.py`, which exists because `docs/PEERS.md` said to
enumerate every place the gate is consulted and put a test on each.

The SSE approval event filtered its payload like this:

```python
{k: v for k, v in item.items() if k not in ("detail", "prompt")}
```

Correct when it was written — those were the only two fields carrying text.
`raised` was added to the row **later**, and shipped itself.

`raised` is not an incidental field. It is the explanation of why an item is
on the card when the tier table said otherwise, and the desktop client's own
comments in `jarvis-link.js` name what is in it:

```js
quote:   "The attacker's words."
context: "Text from the page or the document being judged, so it is
          never shown until the user asks for it."
```

So the one field whose entire purpose is quoting hostile outside text was
being pushed, unasked, to every subscriber — including the phone's foreground
service, which surfaces approvals **on a lock screen**, where "never shown
until the user asks" is not something the notification tray knows about.

This is the third instance of one bug: the rule stated in one place and not
enforced at the next. The other two were `gate-push.patch` (the audit log
honoured `_redact`, the ntfy push sent the same dict verbatim) and
`events-pump.patch` itself.

Now an allowlist — `id`, `action`, `tier`, `created` — plus `raised` reduced
to a **boolean**, because the invariant *"an item carrying `raised` never
belongs in a group that can be actioned quickly"* has to survive out here, and
a client can apply it from the flag without the attacker's words.

**A denylist fails silently: a new column ships itself. An allowlist fails
visibly: a new field is missing until someone adds it, and the person who
added the column is the person who notices.**

`jarvis_content_risk.chip_from()` builds that dict and is **not in this
repository**, so its contents were confirmed from the client that reads them
rather than the code that writes them. Said here because it is a weaker kind
of evidence and the difference should not be invisible.

`test_gate_egress.py`: 23 checks over all six sites where approval content can
leave. Two of them are permanent CONTROLS that run the old denylist expression
against a fixture row and show it leaking — so a reader can see the bug rather
than take this file's word for it.


---

# `approval-notice.patch` — a notification you can act on, that still cannot leak

The owner asked for this in plain words: *"I want approval for certain actions
(especially ones with a lot of weight) to be a notification on Android and or
the desktop program that I can read the details in a simple manner and approve
or disapprove."*

## What was actually arriving

Two of the three previous patches in this stack shut leaks by **removing**
text. `gate-push.patch` replaced the pushed detail with `_safe_detail`, which
prints the field *names* and nothing else:

```
Jarvis wants to: send_email
fields: args, tool
(id 41) - open Jarvis to read it
```

That is safe, and it is useless. Nobody can decide anything from it, so the
notification stopped being a decision point and became a nag that says "come
and look". The gap between "safe" and "worth reading" was the whole request.

## The move: generate, do not redact

`notice_for(item)` reads exactly two things off an approval row: `action`, and
whether `raised` is truthy. It reads **no** `detail`, **no** `prompt`, and
nothing from inside `raised`. Every word it returns comes out of `_RISK` and
out of the action name — tables in `jarvis_gate.py`, written by us.

```python
{"title":  "Jarvis wants to send email",
 "body":   "it leaves this machine and cannot be taken back. nothing has "
           "happened yet.",
 "weight": "heavy",
 "deny_ok": True,
 "approve_ok": False}
```

This is the difference that matters. A redaction is safe **because a reviewer
remembered**; three leaks in this project happened at the next call site along,
where nobody did. A function that never touches the payload cannot join that
list — there is no field you could add to an approval row tomorrow that would
start appearing on a lock screen.

## `weight`, and why it is three named reasons rather than a score

`heavy` means *interrupt them*. It is earned by any one of:

- the action cannot be undone (`reversible == "no"`), or
- it leaves this machine (`reach != "local"`), or
- outside text pushed the tier up (`raised`).

Deliberately not a number. A person can argue with "it leaves the machine";
nobody can argue with 0.73.

## `deny_ok: True`, `approve_ok: False`

The two buttons are not symmetric and the backend says so once, here, rather
than each client deciding for itself.

Refusing something you have not fully read costs a retry. Approving something
you have not fully read **is the exact failure this module exists to prevent** —
and a notification is the worst possible place to do it: glanceable, often on a
lock screen, one thumb, no context.

So: **Deny is a notification button. Approve is not.** Approving requires
opening Jarvis and seeing the detail, the source, and the `raised` quote in
quotation marks next to where it came from.

That is also the honest answer to "approve or disapprove" in the request: half
of it is being given, and this section is why the other half is not. It is not
an approve-all — that still does not exist and is not being built — it is the
weaker point that a one-tap approve on a lock screen is, on its own, worth
refusing.

## `raised` is still a boolean

The owner chose the same summary on both clients, having been told the phone
shows it on a lock screen. That is their call and it is honoured.

But `raised.quote` is not "the summary". It is text an attacker wrote to make
a reader hurry. Its home is inside the app, in quotation marks, beside its
source, where the point is to **slow the reader down** — putting it on a lock
screen defeats the feature it belongs to. The notice therefore *says* that
something tried to rush you, and never quotes it. That something tried is the
fact that changes your decision; its words are not.

## The desktop side, and a limitation worth writing down

`jarvis-desktop/src-tauri/src/stream.rs` now reads `notice.title` and
`notice.body` off the doorbell, with a fallback to the old wording so an
unpatched backend still produces a sensible toast.

**There is no Deny button on the Windows toast, and not by choice.**
`tauri-plugin-notification`'s builder accepts `action_type_id`, which reads as
though actions work everywhere. They do not: the desktop implementation
(`notify_rust`, `win7_notifications`) never reads that field — actions are a
mobile-only feature of that plugin. Verified in
`tauri-plugin-notification-2.4.0/src/desktop.rs`. So the Deny button the
contract permits is buildable on Android and is not, today, on Windows. The
toast is a prompt to open the app.

`test_approval_notice.py`: 37 checks. The central one feeds a row stuffed with
private strings and attacker text and asserts that none of them appear in the
notice, end to end through the doorbell.

---

# `ui-control-wiring.patch` — the gate now knows these three capabilities exist

`jarvis_research.py` gained authenticated GitHub search. `jarvis_ui_control.py`
and `jarvis_android_control.py` are new - a `microsoft/UFO`-style way to click
inside other Windows programs, and a `Genymobile/scrcpy`-style way to tap the
paired phone, both built to the shape `docs/UFO-SAFETY-DESIGN.md` specifies
rather than by taking either project as a dependency. All three ship as whole
files, the same way `jarvis_research.py` and `jarvis_speech.py` already do -
there is nothing on the owner's machine to patch for something new.

This section was rewritten once the owner sent over the real `jarvis_hud.py`
and `jarvis_gate.py` - the first draft, written without them, guessed wrong
about where the missing piece lives. Real ground:

**`jarvis_hud.py` needs NO changes.** `GET /api/pending` already just calls
`jarvis_gate.pending()`/`.history()` - generic over every action name there
is, including three that did not exist an hour ago. Once `jarvis_gate` knows
about an action, anything that reaches `jarvis_gate.check()` for it shows up
correctly, formatted by `notice_for()`, with zero HUD-side code.

**`jarvis_gate.py` needed real entries, and now has them** -
`ui-control-wiring.patch`, verified with `git apply --check` AND `patch
--dry-run` against the owner's actual file, not written blind:

- `_RISK["control_phone"]` and `_RISK["research_authenticated"]` - two new
  entries; `control_computer` already existed and is reused as-is for native
  UI control, exactly as it already covers `browser_click`/`browser_type`.
- `_TOOL_ACTIONS` gains `jarvis_ui_control_plan`/`_run`,
  `jarvis_android_control_plan`/`_run`, `jarvis_research_plan`,
  `jarvis_research_run`, and `jarvis_research_run_authenticated` - each
  `_plan` tool is `auto` (matches the read-only bucket `model_list` and
  `browser_axtree` are already in - nothing is sent), each `_run` tool maps
  to a real `_RISK` action.
- The owner's real `jarvis-framework.toml` already has `control_computer =
  "ask"` (confirmed against the sample in `backend/rebuilt/`) - so
  `jarvis_ui_control_run` needs **no TOML change at all**. `control_phone`
  and `research_authenticated` are new action names; absent from
  `[autonomy.tiers]` they fail closed to `ask` via `unknown_action_tier`
  (already `"ask"` by default), so this is *safe* without a TOML edit too -
  but add explicit lines for both, the same way every other real action has
  one, rather than relying on the fallback silently:
  ```toml
  control_phone         = "ask"
  research_authenticated = "ask"
  ```

**What is still genuinely missing, and where it actually lives - this was
the wrong guess in the first draft of this section:** `jarvis_gate.py`
answers "may this run"; something else has to actually CALL
`jarvis_ui_control.plan()`/`run()` (and the other two) as a real, LLM-callable
tool in the first place, and wire its `announce` callback to
`jarvis_events.set_activity`. `jarvis_gate.py`'s own docstring names that
something: **OpenJarvis**, a separate process (port 8000) with its own tool
registry - `_TOOL_ACTIONS` maps its ~50 existing tool names to actions, but
does not define the tools themselves. OpenJarvis is not in this repository,
was not mentioned as a separate component in `docs/ARCHITECTURE.md` or
anywhere else handed over so far, and this session has never seen its source.
**Registering these three capabilities as real tools OpenJarvis can call
happens there, not in this repo, and not in `jarvis_hud.py`.** If you want
that written as a real, verified patch too, the same way this one was: find
wherever your existing tools - `shell_exec`, `web_search`, `browser_click` -
are actually defined and dispatched (likely near something called
`ToolExecutor` or a tool registry, per `jarvis_gate.gate_tool()`'s own
docstring), and send that over the same way.

### `jarvis_research.py`'s new part needs nothing beyond the patch above

`JARVIS_GITHUB_TOKEN` in the environment authenticates every request; unset,
behaviour is exactly what it was before. `Plan.authenticated` is captured at
`plan()` time and `run()` refuses if the live state has since changed -
described under "AUTHENTICATED REQUESTS" in the module's own docstring.

### A line-ending discovery worth checking against the other twenty-two

The owner's real `jarvis_gate.py`, as sent, is CRLF on essentially every
line. `ui-control-wiring.patch`, like the other twenty-two, is stored LF -
this project's own convention, and what `apply-patches.ps1`'s line-ending
section always forces every patch to before applying, regardless of what
target it is going against. Verified directly: an LF patch applies cleanly
against an LF copy of the real file, and fails outright (`patch does not
apply`) against the real CRLF one, unmodified - not a guess, a real `git
apply --check` run against both. If the *other* twenty-two have never
actually been run against this exact backend copy, this is worth ruling out
before assuming a failure is about anything else. Fix once, for all
twenty-three, by normalizing the backend `.py` files to LF - safe, because
Python treats `\r\n` and `\n` identically (`compile()` and every parser in
CPython read both as a newline), so this changes nothing about how the code
runs:

```
$dir = if ($env:JARVIS_BACKEND) { $env:JARVIS_BACKEND } else { "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program" }; $backup = "$dir-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"; Copy-Item -Recurse -LiteralPath $dir -Destination $backup; Get-ChildItem -LiteralPath $dir -Filter *.py | ForEach-Object { $text = [IO.File]::ReadAllText($_.FullName) -replace "`r`n", "`n"; [IO.File]::WriteAllText($_.FullName, $text) }; Write-Host "Backed up to $backup and converted every .py file in $dir to LF."
```

### What has and has not been verified

All three modules' own logic is tested here and now, on this machine -
`python3 test_research.py`, `test_ui_control.py`, `test_android_control.py` -
covering exactly the properties that matter: `plan()` performs no real
action (proven by making the real reader/actor/process-spawner raise if
reached at all, the same technique `test_research.py` uses on `socket`),
`run()` refuses without `approved=True`, and each `run()` re-verifies its
target is still what was planned before every step and stops rather than
guessing when it is not.

**None of the three has run against a real Windows desktop, a real paired
phone, or a real GitHub token.** `jarvis_ui_control.py`'s default reader/actor
need the `uiautomation` package and an actual window to point at;
`jarvis_android_control.py`'s need a real `adb` binary and a real device;
`jarvis_research.py`'s authenticated path needs a real token. All three were
written so the injectable seam (`read`/`act`, `run_adb`, `fetch`) is the ONLY
place real I/O happens, specifically so the logic above the seam is provable
without any of that - but "provable without it" is not "tried with it." The
first real run of each is the owner's to do, on their own machine, and is
worth doing once deliberately before it is wired into anything the owner
would trust unattended.

---

# `ollama-direct.patch` — the local lane was calling a program that was never running

`jarvis_hud.py`'s own `/api/chat` route always sent the local lane's completion
request to `{JARVIS_URL}/v1/chat/completions` (`JARVIS_URL` defaults to
`http://127.0.0.1:8000`) — the port and API shape of `open-jarvis/OpenJarvis`,
a separate agent framework. Its docstring at the top of the file even says so
outright: `"/api/chat - a same-origin proxy to jarvis serve on :8000"`, and the
error path on a failed request said `"Start it with uv run jarvis serve"` -
`jarvis serve` being OpenJarvis's own CLI.

**OpenJarvis was never actually part of this setup.** The owner downloaded it
once, separately, to look at it - it was never installed as this project's
completion backend. So every local chat turn was silently doomed to a 503 the
moment it reached `_open()`, unless OpenJarvis happened to be running, which
it never was. This is worth stating plainly rather than routing around
quietly: the desktop app the owner has been building this whole session could
never have actually held a conversation, because the one thing it depends on
to answer was assumed into existence and never verified.

The fix is narrow on purpose, because everything AROUND `_open()` - lane
selection, the privacy filter that strips non-user turns before a cloud hop,
the recalled-facts injection and its careful positioning for the KV cache, the
downward-only degrade chain - is real, load-bearing, and each piece has its
own history of a subtle bug already found and fixed once (see
`degrade-filter.patch`). None of it needed to change. Only the URL the local
lane's completion request goes to: Ollama already speaks the exact
OpenAI-compatible shape this code was already sending, at
`{OLLAMA_URL}/v1/chat/completions` - no new dependency, no new format, one
new small function (`_completions_url`) deciding which lane goes where. A
non-local (cloud) lane still goes to `JARVIS_URL`, unchanged - not because
that's believed to work, but because there is no other cloud-lane transport
in this codebase yet to redirect it to, and pretending otherwise would trade
one silent failure for a different one. In practice this doesn't affect the
owner today: `_lane_names()` reads cloud lane names from `PROXY_FILE`
(`litellm-proxy.yaml`), which does not exist on this machine, so `lanes` is
always empty and every turn is already local-only. The moment a real
cloud-lane transport exists, `_completions_url` is the one place that needs
to learn about it.

**Tool-calling is a separate, deliberately un-bundled next step.** This patch
only fixes the local lane's completion transport - the model does not yet
have any tools to call at all (`/api/chat` never sends a `tools` field to the
completion request). Wiring in `jarvis_ui_control.py`, `jarvis_android_control.py`,
`jarvis_research.py`'s authenticated search, and a small set of tools ported
from OpenJarvis's own catalogue is real, additional work on top of a working
chat loop, not folded into this patch - each is independently reviewable and
neither risks the other.

### What was deliberately NOT ported from OpenJarvis, and why

The owner asked to pull useful tools from OpenJarvis "all" of them. That is
not a safe instruction to follow literally - several of OpenJarvis's ~50
built-in tools either need something this project has already rejected as a
dependency, or need a setup decision only the owner can make:

- **Browser automation** (`browser_click`, `browser_axtree`, etc.) needs a
  real headless-browser dependency (Playwright, in OpenJarvis's case).
  `docs/ARCHITECTURE.md`'s "Decisions already taken" table already rejected
  `browser-use` by name ("dies at 8k context by step 2-3"). Not ported.
- **`code_interpreter_docker` / `docker_shell_exec`** need Docker.
  `docs/ARCHITECTURE.md` already decided "Git worktrees, not Docker" for
  sandboxing. Not ported. Plain `shell_exec` (no Docker, tier `ask` already
  in `jarvis-framework.toml`) is a candidate for the next patch instead.
- **Connectors** (Gmail, Calendar, Slack, Notion, ...) need OAuth setup per
  service, and OpenJarvis's own version stores the resulting tokens as
  plain, unencrypted JSON files (permission-restricted, not encrypted) -
  looser than this project should copy without asking first. Not ported
  until the owner picks specific services and a storage approach.
- **General web search** needs a real search API and, in practice, a key.
  Rather than fake one with an unreliable scrape, this is left out until the
  owner wants to pick a provider.
- **Model management, image/audio generation, OpenJarvis's own eight
  agent modes** (scheduled digests, continuous monitoring, etc.) all need
  either a file this session does not have (`jarvis_models.py`'s real API)
  or a scope decision bigger than "add a tool." Not ported.

What's actually in `jarvis_agent.py` now, because each one reuses
`jarvis_gate.py`'s existing, already-tiered action names with nothing new to
configure: `calculator` (auto), `memory_search` (auto, read-only, over the
real `jarvis_memory.py`), `file_read` (`read_files_readonly`), `shell_exec`
(`run_shell_on_host`, tier `ask`), and one tool each for the three modules
built earlier this session - `control_computer` (native UI control, resolves
to the `jarvis_ui_control_run` action added by `ui-control-wiring.patch`),
`control_phone` (adb, resolves to `jarvis_android_control_run`, added by the
same patch), and `github_search` (wraps `jarvis_research.py`, resolving to
`jarvis_research_run` or `jarvis_research_run_authenticated` depending on
whether a token is configured *at the moment the call actually runs* - not
decided by the model). These three model-facing names deliberately differ
from the actual `jarvis_gate` action keys - see `Tool.gate_lookup_name` in
`jarvis_agent.py`'s own docstring for why a static match on `name` was not
enough, and `test_agent.py`'s
`t_every_tool_resolves_to_a_real_jarvis_gate_action` for the regression test
that guards it: `action_for_tool()` does not raise on a name it does not
recognise, it silently falls through to `"unclassified_tool"`, so a mismatch
here would not have failed loudly on its own. Deliberately
**not** included: a `memory_store`/`memory_manage`-style tool that would let
the model write directly to `facts`. This project's memory system exists
specifically so nothing reaches `facts` without a human accepting it through
the review queue (`memory-safety.patch`, `memory-pane.patch`) - a chat-time
tool that wrote around that queue would reopen the exact hole those patches
closed. Remembering something new stays the extractor's job, not a tool the
model calls directly.

### Test it

```powershell
python test_ollama_direct.py
```

Structural checks, over the source, that the endpoint fix is what it claims
to be and touches nothing else: `_completions_url` returns the Ollama URL for
the local lane and the JARVIS_URL for any other lane, the error message names
the right service for each case, and the surrounding routing/privacy/degrade
code - `is_cloud`, the recalled-facts block, `jarvis_router.degrade` - is
byte-for-byte unchanged by this patch. Cannot start a real HTTP server here to
prove Ollama actually answers; that part is the owner's own machine to try.

---

# `tool-calling-wiring.patch` — the model can finally use a tool, on the local lane only

`jarvis_agent.py` (new file, ships whole like `jarvis_research.py`) is the
actual tool-using loop: it hands Ollama a `tools` list, and when the model
asks for one, gates it through `jarvis_gate.check()` - the same module, the
same four-step shape, as everything else - before it ever runs. Without this
patch that module has no caller at all; `/api/chat` never sent a `tools`
field to anything.

**Where it plugs in, precisely.** Right after `lane = decision.lane`, one new
line: `use_tools = lane == local_model and bool((cfg.get("tools") or
{}).get("enabled"))` - the exact `[tools].enabled` list `collect_tools()` and
`/api/status` already read, so there is no new switch to learn, only the one
that already existed actually doing something. When `use_tools` is true, the
degrade loop is skipped entirely (`jarvis_agent.run_local_turn` makes its own
request to Ollama; running the loop too would mean two live completions for
one turn) and the response-streaming section gets an `if use_tools: ... else:
<the original with-upstream relay, unedited>` - so a cloud lane, or a local
lane with no tools enabled, takes the exact path it always did.

**Local only, enforced twice, not once.** `use_tools` requires
`lane == local_model` before tools are even considered - a cloud lane never
reaches `jarvis_agent` at all. Separately, `run_local_turn`'s own
`enabled_tools` parameter is the *specific* whitelist from `[tools].enabled`,
not "on or off": a tool call for something not in that list is refused with
"no such tool", the same as a name the model invented outright, and never
reaches the real tool's code. Two independent checks, so a bug in either one
does not silently become "every tool, everywhere."

**Six tools only run after a person says yes, whatever the config says.**
`github_search`, `browser_control`, `control_computer`, `control_phone`,
`shell_exec` and `home_control` (`NEEDS_A_PERSON` in `jarvis_agent.py`)
each send something off this computer or act on the real world. The gate
answers "allowed" on tier `auto` (nobody was asked) and `notify` (you are
told afterwards) as well as on an approved card, and the loop used to check
only "allowed". So `github_search` - whose action is `web_research`, which
is `"auto"` in the shipped `jarvis-framework.toml` - sent a search term to
GitHub with nobody asked. Now the loop also checks that the gate's answer
was a person approving (`outcome == "approved"`), and otherwise refuses
without running anything and tells the model which line to change.

What that means for you: **`github_search` is refused until you set
`web_research = "ask"`** (and `research_authenticated = "ask"`, if you use
a GitHub token) in `jarvis-framework.toml`'s `[autonomy.tiers]`. Be aware
that `web_research` may also govern other web tools you have, which will
then ask too. The reads you chose to leave at `"auto"` (calendar, email,
notes, home state) and the two note writes are not affected.
`test_agent.py` proves it against the shipped config: every one of the six,
at `auto` or `notify`, never runs.

**What's genuinely rough about this first pass, said plainly rather than
smoothed over:** a tool-enabled turn is one extra non-streamed round trip
slower than a plain one (the model is asked once, without streaming, purely
to find out if it wants a tool; only the final answer streams) - and it does
not retry or step down the way the plain-relay path does, since
`jarvis_router.degrade()`'s whole reason for existing is negotiating between
*lanes*, and a tool-enabled turn never leaves the local one. Neither of these
is a correctness bug; both are the kind of thing worth knowing about before
relying on this for anything time-sensitive.

**A failure after headers are sent still reaches the client.** The tool
branch sends its `200` and sets `_headers_sent = True` *before*
`jarvis_agent.run_local_turn(...)` makes its own request(s) to Ollama - unlike
the plain-relay branch, where a downed Ollama is caught by the degrade loop
before any header goes out. The first version of this patch only caught the
socket-drop exceptions (`BrokenPipeError`, `ConnectionResetError`, etc.)
around that call; anything else - Ollama refusing the connection, a bug in
the tool loop itself - fell through to the generic `except Exception` far
below, which tries to `_send(503, ...)` a friendly message that never
arrives, because `_send()` sees `_headers_sent` and just cuts the connection
instead. The client learned nothing happened. Fixed by adding a second,
broader `except Exception` around the `run_local_turn` call that writes one
`{"error": "..."}` line straight to `self.wfile` - the exact shape
`main.js`'s own `consumeLine`/`routeFromPayload` handling already renders via
`showError()` (`if (chunk.error) showError(...)`), so no client change was
needed to make use of it.

**Four more findings from a self-run audit of this whole session's work,**
fixed in `jarvis_agent.py` itself rather than in this patch:

- A tool call is now built once, at the moment the approval card is shown,
  not re-derived at execution time. `control_computer`/`control_phone`/
  `github_search` each read live, mutable state to build their `Plan` (a
  window's current controls, a phone's current screen, whether a token is
  configured) - re-reading that state a second time at execute() could let
  the steps that actually run differ from the ones a human approved, which
  is exactly what `docs/ARCHITECTURE.md`'s "run() executes an approved plan"
  contract exists to prevent. Fixed by splitting each `Tool` into
  `prepare(args) -> (state, description_text)`, run once before the gate
  decision, and `execute(args, state, **kwargs)`, which receives that same
  `state` back rather than recomputing it.
- `github_search`'s approval card used to show a generic
  `"Search GitHub about: {...}"` line instead of `jarvis_research.describe()`
  - the same disclosure every other capability's card gets (auth state,
    licence risk, what will actually run). Fixed as part of the same
  restructure above.
- `_gate_check` only wrapped the `import jarvis_gate` line in try/except; a
  raise from `jarvis_gate.check()` itself would have propagated instead of
  failing closed. Fixed by wrapping the whole call.
- `_safe_eval` (the calculator's expression walker) had no bound on `Pow` -
  `9**9**9**9**9` is a valid AST with no name and no call, so "no names, no
  calls" alone did not make it safe, and `calculator` is tier `auto`: no
  human ever sees a card for it before it runs. Fixed with
  `_MAX_POW_EXPONENT`/`_MAX_POW_BASE` bounds that reject anything past them
  before the exponentiation runs.

All of `test_agent.py`, `test_research.py`, `test_ui_control.py`,
`test_android_control.py`, `test_ollama_direct.py`, and
`test_tool_calling_wiring.py` pass after these fixes (145 checks across the
six files, run both standalone and, where a `JARVIS_BACKEND` copy of the real
files was available, against the real patched source).

**A second, independent audit pass found five more, all fixed:**

- The final streaming call in `run_local_turn` still offered `tools`, even
  though the round just above already decided this turn needs none (a round
  came back with no `tool_calls`, or `max_rounds` cut it off). Nothing here
  reads `tool_calls` out of a *streamed* response - so a nondeterministic
  model (no `temperature`/`seed` is pinned in either request) could change
  its mind on that second, independent completion and request a tool
  anyway, and its raw tool-call delta JSON would stream straight to the
  client, ungated and unexecuted, as a garbled or empty answer. Fixed by
  dropping `tools` from the final `stream_body` entirely - once the loop
  above has decided, this call can only ever answer in prose.
- Tool-call argument parsing only caught `json.JSONDecodeError`. Some
  OpenAI-compatible backends (including some Ollama versions/models) hand
  back `function.arguments` already parsed into an object rather than a
  JSON string; `json.loads()` on a dict raises `TypeError`, which escaped
  `run_local_turn` entirely and was reported to the owner as "Ollama is not
  answering" - a real bug in this parsing step, misdiagnosed as Ollama being
  down. Fixed to use a dict's `arguments` directly and only fall back to
  `json.loads()` for a string, catching `TypeError` alongside
  `JSONDecodeError`.
- `tool-calling-wiring.patch`'s broad `except Exception` (added in the fix
  just above this section) unconditionally told the owner "Ollama is not
  answering... start it with `ollama serve`" - but its own comment already
  admits it also catches "a bug in the tool loop itself." A `TypeError`
  from the point above, or any other bug in `jarvis_agent.py`, would send a
  beginner developer to restart a service that was never the problem.
  Fixed to name the real exception first and offer the Ollama-restart step
  as one possibility, not the diagnosis.
- `_run_file_read` opened in text mode and capped with `.read(N)`, which
  caps *characters*, while `_MAX_FILE_READ_BYTES` and the tool's own
  contract both claim bytes. A file that is mostly multi-byte UTF-8 (CJK
  text, emoji) could return up to ~4x the stated budget, and a file with
  few characters but many bytes could wrongly report `truncated: false`
  entirely. Fixed to read in binary, cap by the actual bytes read, and
  decode afterward (`errors="replace"` on a boundary cut mid-character).
- `jarvis_android_control.py`'s `run()` docstring said the device is
  re-verified "before the FIRST command, and again... after a screenshot,"
  but the code actually checks before *every* step - a stale docstring
  describing behavior the code no longer has (it's safer than documented,
  not less safe). Fixed the docstring to match.

All six backend test files still pass after these fixes (151 checks total),
with three new regression tests added: the final call really omits `tools`,
a dict-shaped `arguments` value doesn't crash the loop, and a multi-byte-
heavy file is truncated by real byte count rather than reported whole
because it has few characters.

**A third pass - a review from a different model (Gemini), verified line by
line against the real source before touching anything - found 9 more real
findings and 3 that did not hold up. Said plainly, both directions:**

Confirmed and fixed:

- **Android shell injection, the serious one.** `adb shell <args...>` joins
  every argument after `shell` with a space and runs the result as ONE
  command line on the DEVICE's own `/system/bin/sh -c` - a `"text"` step's
  `value` of `"hello; reboot"` became the literal remote command
  `input text hello; reboot`, which the phone's shell splits on `;` and
  runs both halves. `subprocess.run(argv)` on the host was never the
  exposure (no `shell=True`, nothing here is interpreted locally) - the
  remote shell was. Fixed by checking `value` (for `"text"`) and the
  resolved keycode (for `"key"`) against a plain-text allowlist before
  they're ever turned into a command, rejecting anything else as an
  unmatched request rather than trying to escape it - getting a remote
  shell's own quoting exactly right, on a device this code cannot inspect,
  is a worse bet than just not sending the characters that matter.
- **A screenshot crashed the whole turn.** `A.run()`'s `"screenshot"` step
  put raw PNG bytes into the result dict, which `run_local_turn` then hands
  to `json.dumps()` - which cannot serialize bytes at all, and this was
  uncaught at that specific call site. Fixed by base64-encoding the
  screenshot before it leaves `jarvis_android_control.py`.
- **A null coordinate crashed `plan()` entirely.** `int(r["x"])` on
  `{"x": null}` raises `TypeError`, not `ValueError` - `plan()`'s own
  `except (KeyError, ValueError)` didn't catch it, so a malformed request
  escaped `plan()` instead of landing in `rejected` like every other one.
  Fixed by catching `TypeError` too.
- **`ctrl.Select(step.value or "")` was calling a method that doesn't
  exist.** Checked against the real `uiautomation` library source (fetched
  and read directly, not guessed from memory): `.Control(...)` **does**
  exist as an instance method - that specific claim in the review was
  wrong - but the plain `Control` object it returns has no `.Select()`
  method at all; that only exists on specific typed subclasses like
  `ComboBoxControl`, none of which this module ever creates. Fixed to use
  `ctrl.GetPattern(PatternId.SelectionItemPattern).Select()`, which works
  on any control and matches what a "select" step already means here -
  choose the named control itself, not a separate dropdown-plus-item-name.
- **The `"read"` action was a no-op.** `elif step.action == "read": pass` -
  offered to the model as a real action in the tool's own schema, it always
  "succeeded" and reported nothing, because nothing here fetched a value
  and there was nowhere to put one even if it had. Fixed on both ends: the
  actor now returns `GetPattern(ValuePattern).Value` (or the control's
  `Name` if it has no value pattern), and `run()` folds that into the
  step's own `value` before it's reported done.
- **`_default_read` only ever saw a window's direct children.** Real
  Windows apps nest their actual controls several levels inside panes and
  group boxes; every one of them was reported "not found" at `plan()` time,
  not because it wasn't on screen but because this never looked past depth
  1. Fixed with a bounded recursive walk (depth 8 - deep enough for a real
  app, finite so a very large or virtualized tree can't run away).
- **A JSON-literal scalar in `arguments` still crashed a tool.** The
  previous audit's dict-vs-string fix didn't cover a third case: `"123"` is
  valid JSON and parses to the int `123`, not a dict, and every tool calls
  `args.get(...)`. Fixed with an explicit `isinstance(args, dict)` check
  after parsing.
- **`json.dumps(result)[:8000]` could hand the model broken JSON.**
  Slicing a serialized string can cut off mid-quote or mid-brace - not
  hypothetical, since `file_read` alone can return up to 200,000
  characters. Fixed with `_tool_content()`: serialize once, and if it's
  over budget, replace it with a small, always-valid JSON note saying so,
  rather than a byte-slice of the real one.
- **Windows reserved device names in `file_read` could hang a worker.**
  Opening `"CON"` for reading opens the console and blocks waiting for a
  keypress that will never come from a headless service. Not a sandbox
  issue (this tool is a whole-filesystem read, gated like `shell_exec` is,
  by design) - just a path that resolves to a device instead of a file.
  Fixed by rejecting `CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`, anywhere in
  the path, with or without an extension.

Checked and rejected, with the evidence, because the review didn't have
`jarvis_gate.py` and reasoned from an incorrect model of how it works:

- **"Heavy/irreversible tier stripped before the gate."** The claim was
  that `run_local_turn` needed to pass `weight`/`heavy` inside `detail` so
  `jarvis_gate.check()` could raise the tier for a dangerous plan. Read
  directly against the real file: `notice_for()`'s own docstring says
  outright it "does NOT read `detail`... every word it returns comes from
  `_RISK` and from the action name," and `check()`'s tier lookup is
  `tiers.get(action, UNKNOWN_TIER)` - keyed only by the action string,
  never by the payload. This is deliberate, not an oversight: letting a
  model-controlled payload declare its own risk tier is exactly the kind
  of self-graded permission this project's gate exists to prevent. The
  suggested fix would have added dead keys to `detail` with zero effect.
- **"`github_search` downgrades to `unclassified_tool`."** The claim was
  that passing `"jarvis_research_run_authenticated"` into
  `action_for_tool()` misses the lookup. Read directly against the real
  `_TOOL_ACTIONS` dict: that exact string **is** a registered key (mapping
  to `"research_authenticated"`) - added for precisely this path in an
  earlier patch, with its own regression test
  (`t_every_tool_resolves_to_a_real_jarvis_gate_action`) that still passes
  against the real file today.
- **A syntax bug in `_safe_eval`'s unary-operator branch.** The claim
  described `isinstance(node.UnaryOp)` - a one-argument call with no such
  attribute. The actual line already reads
  `isinstance(node, ast.UnaryOp)`, correctly, and always has.

### Test it

```powershell
python test_agent.py
python test_tool_calling_wiring.py
```

`test_agent.py` runs the real loop end to end against a scripted fake model
and a fake gate - no real Ollama, no real jarvis_gate, no real tool ever
executes. It proves: a denied tool call never runs the real function, an
approved one does and its actual result (not a guess) is what the model sees
next, an unregistered or *disabled* tool name is refused rather than
silently allowed through, the calculator cannot reach a name or a call
(`__import__`, `open(...)`, bare `os.system` all rejected), and a model that
keeps asking for tools forever is cut off at `max_rounds` rather than
looping. `test_tool_calling_wiring.py` is the structural half, over the real
patched source: `use_tools` genuinely requires both the local lane and a
non-empty `[tools].enabled` (an `and`, checked as an `and` in the AST, not
just as a string that happens to appear), the plain-relay `else` branch is
still there and reachable, the tool branch actually passes `enabled_tools`
and wires `announce` to the same `_activity()` doorbell everything else in
this project already uses, and the `run_local_turn` call sits inside a `try`
whose broad handler actually writes to the client rather than just
returning - the specific regression described just above.

---

# `loopback-too.patch` — binding for the phone must not unplug the desktop

`main()` opens one socket: `ThreadingHTTPServer((bind, HUD_PORT), Handler)`.
`JARVIS_HUD_BIND` (and the desktop's own "Let my phone reach this" setting,
which sets it) therefore *moved* the listener off `127.0.0.1` rather than
adding a second address. `docs/INSTALL.md` §2.5 tells the owner to leave the
desktop's Base URL at `http://127.0.0.1:4719`, and the HUD page's
Content-Security-Policy only allows `127.0.0.1` and `localhost` - so the
moment the phone could reach Jarvis, the desktop could not.

Found on the owner's machine, not in review: with the backend bound to a
NordVPN Meshnet address the phone answered, while Edge on the same PC was
refused at `http://localhost:4719`. Pointing the desktop at the mesh address
instead "fixed" its event stream (that runs in Rust, outside any CSP) and
broke the HUD window completely, because every request the page made was then
refused by its own policy.

The patch adds `_loopback_companion(bind, port, handler)`: when the main bind
is not already loopback (or a wildcard, which covers it), it starts a second
`ThreadingHTTPServer` on `127.0.0.1:port` with **the same `Handler`** in a
daemon thread, and says so on the banner. Same handler means the same token
and origin checks, and loopback is this server's default bind anyway, so this
opens nothing the default setup does not. If `127.0.0.1:port` is already taken
it prints why and carries on - the phone still works, which is better than
refusing to boot over the desktop's half.

Two things it does not change, both worth knowing:

- **A backend started by hand still needs `JARVIS_HUD_ORIGINS`.** The HUD page
  is served from `http://tauri.localhost`, which the server's allowlist cannot
  guess. The desktop passes it when it starts the backend itself
  (`sidecar.rs`); from a terminal, set
  `$env:JARVIS_HUD_ORIGINS = "http://tauri.localhost"` before `jarvis_hud.py`.
- **`/api/shutdown` arriving on the loopback listener** may only stop that
  listener, depending on how `_install_shutdown` reaches the server. The
  desktop's supervised stop already kills the process tree when the backend
  is still there after asking, and Ctrl+C in a terminal stops the main
  listener, which ends the process and its daemon thread.

`test_loopback_too.py` runs the real function against real sockets - lifted
from the installed `jarvis_hud.py`, or from this patch's own `+` lines when
none is installed - with `127.0.0.2` standing in for the mesh address: no
second listener for loopback or wildcard binds, both addresses answering
through the same handler for a mesh bind, a warning instead of a crash when
`127.0.0.1` is taken, and (installed file only) `main()` calling it before the
main socket opens.

---

# `browser-control-wiring` — Jarvis can drive a browser, but the switch stays off

The request behind this one, in plain words: "control a chat for me on
customer service or something." `docs/ARCHITECTURE.md`'s "Decisions already
taken" table had already rejected `browser-use` by name for exactly that job
- "dies at 8k context by step 2-3" - and this project's own `jarvis_ui_control.py`
had already worked out the right shape for "click inside something else" that
doesn't have that problem: read once, freeze concrete steps, re-verify
before each one, never a live loop. `jarvis_browser_control.py` (new file,
ships whole like `jarvis_ui_control.py` and `jarvis_android_control.py`) is
that same shape, aimed at a browser tab instead of a native window.

**What it is.** `plan(goal, session, requests)` reads the current page
(through Chrome's DevTools Protocol since 2026-09-23 - see "What was ported
from browser-use" below; capped at 300 elements) and binds each requested
step to exactly one `(role, name)` element actually on that page - a
`navigate` request is checked
against an `http`/`https`-only scheme filter and an optional
`allowed_domains` list instead, since there is no page yet to search.
`run(plan, approved=True)` executes only the enumerated steps, re-reading
the page and re-checking the target before each one (`navigate` excepted -
it has nothing to re-check). Any mismatch stops the run at that step and
reports it; that is a new `plan()` and a new decision, never a retry.

**Why this is not the same mistake twice.** The actual fix for "dies at 8k
context by step 2-3" is `_MAX_READ_VALUE_CHARS` (700 characters): a `read`
step's value - a chat transcript, an input's current text - is capped in
`run()` itself, on every single step, not left to `jarvis_agent._tool_content()`'s
existing 8000-character whole-result cutoff, which only fires once the total
is already too big and then throws the whole thing away. Capping per step
instead of per turn is what lets a five-step conversation with a support
widget cost roughly five times one step, not blow the budget by step three.

**Wired into `jarvis_agent.py` as `"browser_control"`,** the same pattern as
`control_computer`/`control_phone`: a `_prepare_browser_control`/
`_run_browser_control` pair, `needs_announce=True`, and
`gate_lookup_name=lambda args: "jarvis_browser_control_run"` - a new action
name, because no existing `jarvis_gate` tier fits a browser step. It needs:

- A new `_RISK["control_browser"]` entry in `jarvis_gate.py`, same shape as
  the `control_phone` entry `ui-control-wiring.patch` already added.
- `_TOOL_ACTIONS["jarvis_browser_control_run"] = "control_browser"`.
- `jarvis-framework.toml`'s `[autonomy.tiers]`:
  ```toml
  control_browser = "ask"
  ```
  Absent from the TOML this already fails closed to `"ask"` via
  `unknown_action_tier` (the same safety net `control_phone` relied on before
  its own line existed) - add the explicit line anyway, for the same reason
  every other real action has one rather than leaning on the fallback
  silently. **Never `"auto"`** - every step here either sends a message to a
  real person on the other end or navigates to a page nobody has looked at
  yet; those are exactly what `jarvis_ui_control.py`'s own `heavy` flag and
  this project's `no-auto-approve.patch` exist to keep out of the automatic
  bucket.

**Ships disabled, and stays that way until you decide otherwise.** Two
reasons, both real, neither a formality:

1. **A new dependency this project has never taken before.** Nothing here
   imports Playwright at module load time (same lazy-import discipline as
   `jarvis_ui_control.py`'s `uiautomation`), but the real `read`/`act` do need
   it actually installed and a Chromium build present:
   ```powershell
   pip install playwright; playwright install chromium
   ```
2. **Context budget.** `docs/MODEL-TOPOLOGY.md`'s primary lane is an 8B model
   at 16K context, arithmetic'd out in `jarvis-primary.Modelfile` to
   6.48 of 6.90 GiB - sized tight on purpose, with nothing to spare for
   several rounds of page-plus-history. This tool belongs on the second,
   larger-context lane - planned as the RTX 2060 12 GB second graphics
   card - once that lane is actually running and has been measured with
   real page reads, not when the card is merely installed.

**Do not add `"browser_control"` to `[tools].enabled` until both of those are
actually true on your machine.** Nothing else in this patch turns it on by
itself - `enabled_tools` is the same opt-in-only whitelist
`tool-calling-wiring.patch` already established, so a tool absent from that
list is simply never offered to the model, the same way `control_phone`
shipped inert until it was added deliberately.

### `read_new` — following a conversation that never stops

The follow-up ask this answers, in the owner's words: "I want Jarvis to be
able to say anything and continue a conversation extremely long once I set
up my GTX 2060 12GB." The "say anything" half needed nothing new - `type`
and `click` never inspected or filtered message content; the human deciding
per message already IS the only constraint, by design. "Extremely long" was
a real gap: re-reading a whole transcript to find out if there's anything
new is the same failure shape as "dies at 8k context by step 2-3," just
spread across many turns of one conversation instead of many steps of one
task.

`read_new` reads a **container** (a chat log, a message list - named by
`role`/`name` same as any other step) rather than one element, because a
message bubble rarely has its own accessible name for `(role, name)`
matching to find. `value` carries the cursor: the highest message index
already seen. Only messages after it come back, capped at
`_MAX_NEW_MESSAGES` (15) and `_MAX_MESSAGE_CHARS` (300) each - and when the
cap actually bites, the result says so in a trailing line naming how many
were left out and the cursor to ask for them with, rather than silently
dropping anything. `_format_new_messages` is the pure function this all
runs through, independent of Playwright, specifically so the "capped, and
says so" property is checked directly rather than trusted.

The result: turn 40 of an hour-long conversation costs the same as turn 2 -
the size of what's new, never the size of everything said so far.

### What was ported from browser-use (2026-09-23)

**First, a bug this fixed.** The page reader used Playwright's
`page.accessibility.snapshot()`. That function no longer exists: on
Playwright 1.63.0, `'accessibility' in dir(playwright.sync_api.Page)` is
`False`, and calling it on a real page raises `AttributeError: 'Page' object
has no attribute 'accessibility'`. So on any current Playwright, the old
`plan()` could never have read a page at all.

`browser-use` (MIT licence) is still rejected as a framework - its
"look, decide, click, repeat" loop is the thing this project never does. But
several of its parts make ONE approved step safer, and those were copied or
adapted into `jarvis_browser_control.py` (each piece says which browser-use
file it came from; the licence is in `THIRD-PARTY-NOTICES.txt`). browser-use
itself is **not** a dependency.

- **A better page reader.** It asks Chrome directly (the DevTools Protocol,
  the same way browser-use does) and keeps only elements a person could
  actually see: not hidden, not see-through, and not covered by something
  drawn on top - a cookie banner or a pop-up's dark backdrop. Each element
  also says whether it can be clicked or typed into, whether it is a
  password/payment field, and which named section it sits in.
- **Never click a guess.** If two elements have the same role and name (two
  "Reply" buttons), the request is reported as ambiguous instead of picking
  the first. Adding `"within": "Order 2"` (the name of the section it is in)
  says which one; the card prints it and `run()` re-checks it.
- **A fence on every move, not only `navigate`.** If a click, a redirect, or
  a new tab takes the page to a site outside `allowed_domains` - or, when
  that is not given, outside the sites the plan itself names - the run
  stops and says where. Where the browser allows it, the move is blocked
  before the other site even loads.
- **Dialogs, pop-ups, downloads, crashes.** A pop-up question
  (`confirm`/`prompt`) is **always answered Cancel, never OK**, and the run
  stops and shows the question. (browser-use answers OK - that would be
  Jarvis approving something for you.) A plain `alert` with only an OK
  button is closed and noted. Downloads are always blocked. A new tab, a
  crash or a frozen page stops the run.
- **Waiting for the page to settle** after each click or navigation, with a
  time limit, so the next step sees the page as it ended up.
- **`read_page`** - a new action that returns the page's main text as tidy
  plain text, 1500 characters at a time, with a line saying how much is left
  and where to continue. Never raw HTML, never a screenshot.
- **Secrets the model never sees.** A `type` step may say
  `<secret>shop_password</secret>` instead of a password. The real value is
  fetched only at the moment of typing and is never on the card, in the
  result, or in any log. A password field refuses a typed-out password.
  **There is no secret store in this project yet**, so today such a step
  simply stops and types nothing (`jarvis_agent.py` passes none) - a store
  is a separate decision.

Not ported: the agent loop, AI-provider code, cloud, telemetry, video
recording, MCP server, and screenshots to the model.

**Known gaps.** Elements inside an iframe are not read - and many
third-party chat widgets live in an iframe, so for those this cannot target
anything yet. An element only *partly* covered (say, half under a cookie
banner) is still offered. Playwright's documentation says its click first
checks that nothing covers the exact point it will click, and waits (here,
at most 8 seconds) and then fails rather than clicking the cover - that
case has not been tested here.

### Test it

```powershell
python test_browser_control.py
python test_browser_control_live.py
```

`test_browser_control.py`: forty-nine scenarios, 185 checks, no real browser,
no network - `read`/`act`/`observe`/`secrets` injected, the real
Playwright-backed defaults proven unreachable via `NoRealAction`, and the
page reader and page-to-text converter tested on hand-built data. Beyond the
original checks (no input during `plan()`, no run without `approved=True`,
stop on any mismatch, capped reads) it proves: an ambiguous element never
becomes a step; a step that lands off the fence - or passes through a
foreign site on the way - stops the run; a confirm dialog stops it and the
real dialog handler only ever dismisses; downloads, pop-ups and crashes stop
it; a secret's real value reaches `act()` and nowhere else, and fails closed
with no store; `read_page` is capped and says so.

`test_browser_control_live.py`: nineteen scenarios, 66 checks, against a real
headless Chromium on small pages served from this machine only (two names
for the same local server stand in for "our site" and "a foreign site").
**It skips cleanly** (and counts as passing) when Playwright or its Chromium
is not installed, which is the normal state on your PC today.

**Where this has and has not run.** Both suites passed in the Linux dev
container with Playwright 1.63.0 and Chromium 141, headless. Not yet run on
Windows, not with the visible browser window the module really uses, and
not against a real customer-service widget. The first real session - on a
page you control, with `allowed_domains` set, watching the actual browser
window it opens - is still worth doing once, deliberately, before this is
ever added to `[tools].enabled`.

---

# `keyless-integrations-wiring` — calendar, email, notes, and home, no cloud key

`docs/ANDROID-FEATURE-AUDIT.md` §2 named these four directly: "Calendar
(CalDAV), notes (Obsidian/Joplin local REST), home (Home Assistant's MCP
server) - read-only first, no cloud keys." This adds email (IMAP) to the
same list, for the same reason - it is the other open, self-hosted protocol
this project can speak with nothing but a username and password the owner
already has. Four new files, one per integration
(`jarvis_calendar.py`, `jarvis_email.py`, `jarvis_notes.py`,
`jarvis_home.py`), each self-contained and each following the exact
`plan()`/`describe()`/`run()` shape `jarvis_research.py` set out and
`jarvis_browser_control.py` already reused - see each module's own
docstring for what makes it different from the other three (the ICS
line-folding parser in `jarvis_calendar.py`, the plain-text-only preview in
`jarvis_email.py`, the token-free URL in `jarvis_notes.py`, the read/act
split in `jarvis_home.py`).

**Wired into `jarvis_agent.py` as five tools** (`calendar_read`,
`email_check`, `notes_search`, `home_read`, `home_control` - `jarvis_home.py`
gets two because reading state and calling a service are different
consequences and different tiers), each a `_prepare_*`/`_run_*` pair
following `control_computer`/`browser_control`'s own pattern. None of the
five needs `needs_announce=True` - each is one request or one small batch of
identically-shaped requests, not a multi-step plan like
`control_computer`/`control_phone`/`browser_control`, so there is no
step-by-step progress worth narrating.

**What each one needs in `jarvis_gate.py` and `jarvis-framework.toml`,**
the same ceremony `browser-control-wiring`'s own section above walked
through:

- Five new `_RISK` entries: `calendar_read`, `email_read`, `notes_search`,
  `home_read`, `home_control`.
- `_TOOL_ACTIONS` gains `jarvis_calendar_read_run -> calendar_read`,
  `jarvis_email_read_run -> email_read`,
  `jarvis_notes_search_run -> notes_search`,
  `jarvis_home_read_run -> home_read`,
  `jarvis_home_control_run -> home_control`.
- `jarvis-framework.toml`'s `[autonomy.tiers]`:
  ```toml
  calendar_read  = "auto"
  email_read     = "auto"
  notes_search   = "auto"
  home_read      = "auto"
  home_control   = "ask"
  ```
  **The four reads are `"auto"` where `browser_control` is `"ask"` - a
  judgment call, stated as one so it can be argued with.** Every step
  `jarvis_browser_control.py` takes either sends something to a real person
  or lands on an unread page, so it can never default to unattended; reading
  the owner's own calendar, inbox, notes, or Home Assistant entity state
  changes nothing and sends nothing to anyone, on infrastructure the owner
  runs for themselves with no cloud account involved - the same "nothing is
  sent, nothing acts" reasoning that already makes `jarvis_gate`'s `_plan`
  actions (including `jarvis_research.plan()`'s own) `auto` rather than
  `ask`. `home_control` is never `"auto"`: it is the one of the five that
  acts on the real, physical world, same reasoning as `control_browser`'s
  own "never auto" line above. If `"auto"` is wrong for a given owner's
  threat model, one line per action overrides it - these tools do not
  decide their own tier, `jarvis_gate.py` does, same as always. Absent from
  the TOML, all five fail closed to `"ask"` via `unknown_action_tier`
  regardless - add the explicit lines anyway, for the same reason every
  other real action has one.

**`home_control` marks a lock, alarm, or cover action `heavy`** inside
`jarvis_home.py` itself (`_is_heavy_service`), the same signal
`jarvis_ui_control.Step.heavy` already carries for the native-UI tool -
"the front door is now unlocked" is a materially bigger consequence than
"the kitchen light is now on", even though both are one API call to the
same server.

**Ship disabled, for a different, simpler reason than `browser_control`.**
Nothing here needs a new dependency (`jarvis_calendar.py`'s ICS parsing and
CalDAV REPORT, `jarvis_email.py`'s IMAP, and `jarvis_home.py`'s REST calls
are all stdlib `urllib`/`imaplib`/`email`; `jarvis_notes.py` is the same
`urllib`) and none needs a second, larger-context lane - the real reason is
that each one needs the owner's own credentials configured in the
environment before it can do anything at all:

| integration | environment variables |
|---|---|
| calendar | `JARVIS_CALDAV_URL`, `JARVIS_CALDAV_USER`, `JARVIS_CALDAV_PASSWORD` |
| email | `JARVIS_IMAP_HOST`, `JARVIS_IMAP_PORT` (default 993), `JARVIS_IMAP_USER`, `JARVIS_IMAP_PASSWORD`, `JARVIS_IMAP_MAILBOX` (default `INBOX`) |
| notes | `JARVIS_NOTES_BACKEND` (`"joplin"` or `"obsidian"`, optional - inferred from which token is set), `JARVIS_JOPLIN_URL`/`JARVIS_JOPLIN_TOKEN`, `JARVIS_OBSIDIAN_URL`/`JARVIS_OBSIDIAN_API_KEY` |
| home | `JARVIS_HOME_URL`, `JARVIS_HOME_TOKEN` |

Turning one on with nothing configured is safe - `plan()`/`plan_states()`/
`plan_service()` all notice and return a plan that only ever explains why it
has nothing to read or nowhere to send, proven in each module's own test
(`"describe() says why, sends nothing"`) - but it is also useless, so add a
tool to `[tools].enabled` only once its own row above is actually filled in
on your machine.

### Test it

```powershell
python test_calendar.py; python test_email.py; python test_notes.py; python test_home_control.py; python test_integrations_wiring.py
```

One hundred and seventy-three checks across five files, no real CalDAV
server, IMAP account, Joplin/Obsidian instance, or Home Assistant, and no
network - `fetch`/`fetch_messages` injected the same way
`jarvis_research.py` and `jarvis_browser_control.py` inject their own I/O,
with a `NoNetwork` guard proving `plan()`/`plan_states()`/`plan_service()`
truly open no socket. `test_integrations_wiring.py` is the fifth file and
checks the seam the other four cannot: that `jarvis_agent.py`'s
`_prepare_*`/`_run_*` pairs actually call each module with the right
arguments and the right `gate_lookup_name`, and fail honestly - never with
a raised exception - when nothing is configured.

**Not run against a real calendar, inbox, notes app, or smart home.** Same
caveat every wiring section above gives for its own modules: the injectable
seam is the only place real I/O happens, specifically so the logic above it
is provable without any of that - but proof without it is not a real run.
Point each one at a real account deliberately, read what `describe()` prints
before approving anything, and watch the first real result before adding it
to `[tools].enabled`.

---

# `memory-intake.patch` + `jarvis_intake.py` — what may enter the review queue, and in what form

Seven of the fifteen items in `docs/LEARNING-RESEARCH-2026-09-23.md` (2, 3,
4, 5, 6, 9 and 10). All seven are about the same moment: something is about
to become a card in the memory review queue. None of them writes a fact.
Every card still needs your one decision, one card at a time.

**Two parts, and you need both.**

- `jarvis_intake.py` is a new file. It holds all the logic. Copy it into
  your backend folder (the one with `jarvis_hud.py` in it):

  ```powershell
  Copy-Item -LiteralPath "C:\Users\pcadmin\Epic-Jarvis\backend\jarvis_intake.py" -Destination "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\"; Write-Host "Copied jarvis_intake.py into the backend folder."
  ```

- `memory-intake.patch` adds small hooks to `jarvis_extract.py` and
  `jarvis_hud.py` that call into it. `apply-patches.ps1` applies it with
  the rest.

If the patch is applied but the file is missing, every hook falls back to
what the backend did before, and the one rule that matters most - item 10,
below - still holds, because that check is written into the learner itself.

**Why the logic is a separate file.** `jarvis_extract.py` exists only on
your PC. This repository knows about two thirds of its text, from the
patches that changed it. The learner's *prompt* is in the third nobody
quoted. A patch has to quote the lines around each change exactly, so the
patch only touches lines whose text is known, and everything else lives in
the new file.

## What each item does, in plain words

**2. "Remember: …"** — start a message with `Remember:` (or `Remember,`)
and the rest goes straight to the review queue in your own words. No model
rewords it. It happens at the end of that turn, not 45 seconds later. It
only looks at your newest message, so if an app ever re-sends earlier turns,
an old "Remember:" is not queued again. `Remember this:` does NOT trigger it - the
approval gate writes that phrase itself when you say no to something.
One change is made to your words: a relative date gets the real date added
in brackets, "I started yesterday (2026-09-22)". If learning is switched
off in the Memory tab, this is off too. *Not checked:* whether your
speech-to-text writes the colon or comma. If it does not, a spoken
"remember …" goes to the normal learner instead.

**3. Near-duplicate cards are not queued.** A new card is compared with the
facts you keep and the cards waiting or discarded. It is dropped only if
it says the same words in the same order once case, punctuation, "a/the",
plurals and "the user/owner" are set aside; every number, date word and
negation ("not", "no longer", "was" vs "is") matches; it is not a
correction; and the embedder (the part that turns text into comparable
numbers) agrees they mean the same. Until the real embedder has
downloaded, this check does not run at all. Every drop is counted:
`setup_status()` shows `near_duplicates_dropped`.
**This is narrower than the research asked for, on purpose.** Comparing by
meaning alone puts "allergic to peanuts" next to "allergic to shellfish",
and "Mario likes hiking" next to "Mario's sister likes hiking". Dropping
either loses a real fact before you see it. So meaning can only stop a
drop, never cause one. The price: a card reworded with a synonym ("enjoys"
for "likes") still reaches you, to discard by hand.

**4. Corrections point at the old fact by number.** The learner's prompt now
lists the closest stored facts, numbered 0, 1, 2 …, and asks for the number
of the fact a correction replaces. The number is turned back into that exact
fact in code the model cannot reach. A number that is not on the list means
"no match", so nothing is retired. If the model writes words instead, the
old matching runs, exactly as before.

**5. "Both are true."** A third answer on a correction card: keep the new
fact AND keep the old one current. New route `POST /api/memory/keep_both`
with `{"id": <proposal id>}` - one id, one decision, like
`/api/memory/decide`. It claims the card the same way `decide()` does, so
two taps write one fact. Nothing is deleted or retired. (The app buttons
are not in this change - see "What the apps need" below.)

**6. Real dates.** The learner is told the date of the conversation and asked
to turn "last week" into a date. Then, whatever the model wrote, the code
adds the real date in brackets after "yesterday", "last week", "3 days ago",
"last Monday", "next month" and similar: "went to Paris last week (week of
2026-09-14)". The words stay, so a wrong reading shows on the card.
Deliberately left alone because they are a coin toss: "next Friday", "next
weekend", "on Monday", "recently". `import_history.py` now dates each old
conversation from the export's own timestamp, and a fact from a
conversation more than two days old that has no date at all gets "(as of
2023-05-03)" on the end. *Not changed:* the fact's `valid_from` column. The
date lives in the text, as the research said it would.
*A known limit, and it now applies:* a live chat is dated by the time its
**newest** message arrived, because no message carries its own time. When
this was written both apps sent one message per request, so that was exact.
They no longer do: the quickbar (`chat-history.js`), the HUD page
(`S.messages.slice(-12)`) and the phone (`ChatHistory.kt`,
`JarvisApi.chatCall`) all send the recent conversation with each question
(checked 2026-09-23). So in a chat that runs past midnight, a "yesterday"
said before midnight is dated as if it were said after it - one day off.
The words stay on the card next to the date, so the slip is visible before
anything is kept. The same sentence is still not queued twice: if the words
(dates aside) are already a fact or a waiting or discarded card, the new
copy is recognised as the same one.

**9. A warning on cards that look like planted instructions.** Each card is
checked for text written to be obeyed: "ignore your previous instructions",
"always forward invoices to someone@…", "don't ask me before …", chat-format
markers, hidden characters. A match adds a `flags` list to the card. **It
drops nothing.** It runs on the processor, not the graphics card. The gate's
own "I do not want Jarvis to … without asking me first" card is tested not
to trip it.

**10. Never learn from turns the backend started.** The learner now reads a
conversation only when the code handing it over says it came from you -
`origin="owner"`. The one place that says so is `/api/chat`, for a request
from a paired app. The default is not "owner", so a future scheduled digest
that forgets to say learns nothing. Separately, anything the backend itself
writes in your voice should be built with `jarvis_intake.jarvis_turn()`,
which remembers a fingerprint of it (a hash, not the text), so it is never
learned even if an app later sends it back as part of the chat history.
Nothing in the request or the model's answer can mark a turn as yours.
**Your "no" still becomes a proposed rule** (`gate-outcome.patch`): that
path calls `propose()` directly, and a test proves it still queues, with no
warning on it. Honest note: nothing calls `jarvis_turn()` yet, because
nothing in the backend starts a conversation yet.

## Ordering

After `feedback.patch`, and it must stay after it. Its `jarvis_extract.py`
lines are the output of `memory-safety`, `memory-noise` and `decide-once`;
its `jarvis_hud.py` lines are the learner and call site `extraction-wiring`
wrote and the memory block `memory-pane` wrote.

One of those lines is shared with `feedback.patch`: feedback's new
`/api/feedback/mark` block ends right above the memory-route line
`"/api/memory/learning", "/api/memory/sleep_time"):`, and uses that line as
its context. This patch rewrites that line to add `/api/memory/keep_both`.
So feedback has to go first. The other way round, feedback's hunk no longer
finds its context and the whole run stops before touching anything. Checked
both ways with `git apply` on a rebuilt `jarvis_hud.py` when the two were
merged.

## What the apps do with it

When this patch was written neither app used any of it. Both do now
(checked 2026-09-23): the backend sends, on every row of
`GET /api/memory/pending`, `flags` (a list of `{"code", "why"}`),
`flags_checked`, `keep_both_ok` and `verbatim`. The Brain window's Memory
tab (`brain.js` `proposalRow`) and the phone (`Learning.kt`
`MemoryCards.from`) show each `why` as a warning when `flags` is not empty,
show a third button, "Both are true", only when `keep_both_ok` is true
(posting to `/api/memory/keep_both`), and label a `verbatim` card "your own
words". `setup` in the same response may carry `near_duplicates_dropped` +
`near_duplicates_note`, `near_duplicate_check`, and `remember_last` (how the
last "Remember:" went, with a plain-words `note`); both apps show the two
notes. The HUD page does not decide memory cards at all - it says how many
are waiting and points at the Brain. `docs/JARVIS-API.md` has the full
shapes.

**"Remember:" works with learning switched off** (2026-09-23). It used to
be dropped silently when the learning switch was off, because `offer()`
checked the switch first. It is the owner asking, and it uses no model, so
it is now handled before the switch is read; the switch stops Jarvis
*reading conversations for facts*, not the owner telling it one. It still
only makes a card to keep or discard.

**propose() refuses a model that is not on this machine** (2026-09-23).
This patch also appends a check to the end of `jarvis_extract.py` that
re-binds `propose` so it returns `[]` and sends nothing unless `OLLAMA`
(from the `OLLAMA_URL` environment variable) is loopback. Before, only the
live learner checked; `import_history.py` (a whole chat history) and the
gate's "your no becomes a proposed rule" did not. Every caller reaches
`propose()` as `jarvis_extract.propose`, looked up when called, so all of
them get the checked version. `backend/test_memory_honesty.py` runs that
code and reads every call site.

## How it was proven

The real `jarvis_extract.py` and `jarvis_hud.py` are not in this
repository, so the patch was checked two ways in the dev container:

1. `git apply --check` against a reconstruction that holds ONLY lines some
   patch in this directory quotes, at their real positions, with every
   other line a placeholder that cannot match. A hunk whose context was
   guessed would fail here.
2. The test suites against a runnable stand-in: those same quoted lines,
   plus the smallest inferred glue to make them run (marked INFERRED). The
   patch applies to it, `test_memory_intake.py` passes against it, and the
   existing suites that touch the same code (`test_decide_once`,
   `test_extraction_wiring`, `test_import_history`) pass the same before and
   after.

Your PC is the first place it meets the real files. Run the tests there.

## Found while doing this, and NOT fixed here

**The learner only ever reads the last message before you go quiet.**
`_Learner.offer()` keeps one transcript and replaces it on every turn
("latest wins"), which assumed each request carries the whole
conversation. It does not: both apps send one new message per request
(`main.js:2196-2203`, `JarvisApi.kt:686`). So if you send five messages and
then stop, only the fifth is read. This predates memory-intake and is not
changed by it; fixing it means the learner keeping the turns since its last
pass instead of replacing them. Worth doing, as its own change, with its
own test.

## Test it

```powershell
python test_memory_intake.py
```

Part A (the new module on its own) runs anywhere. Part B needs
`jarvis_extract.py` with the patch applied; Part C needs `jarvis_hud.py`
with the patch applied. Each part says "skip" and why, rather than failing,
when its file is not there. `test_extraction_wiring.py` was updated too:
every `offer()` call now says `origin="owner"`, and it checks the call site
does.

---

# Standalone tools

Not patches - scripts you run once, on demand, that call the patched backend
rather than change it. `grade-peers.py` and `jarvis_research.py` are the
other two in this directory; this is the third.

## `import_history.py` — feed an old Claude or Gemini export into the review queue

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; python "C:\Users\pcadmin\Epic-Jarvis\backend\import_history.py" --claude "C:\path\to\claude-export.zip" --gemini "C:\path\to\takeout.zip"
```

(One or both of `--claude`/`--gemini`. Run it from the backend folder, or
set `$env:JARVIS_BACKEND` first, the same as the test suites.)

This does not add anything to memory by itself. It calls the exact same
`jarvis_extract.propose()` a live conversation triggers once it goes quiet -
once per historical conversation found in the export - so every guarantee
that function already has keeps holding for free: the model call is
whatever `_local_llm` is (Ollama at `OLLAMA_URL`), and nothing becomes a
fact without a human accepting it in the Brain window.

**"On this machine" is checked, not assumed** (2026-09-23). `OLLAMA_URL` is
an environment variable; pointed at another computer, it would have sent
your whole history there, and nothing here used to check. Now the script
refuses to start - before reading the export or marking anything done -
unless `OLLAMA_URL` is this machine (`127.0.0.1`, `localhost` or `::1`), and
tells you what to set. `memory-intake.patch` makes `propose()` itself refuse
too, for every caller.

**There is deliberately no bulk-approve here, and there will not be one.**
Two full histories can be thousands of conversations, which is exactly the
amount of data that tempts a shortcut around "no approve-all anywhere in
Jarvis" - the rule holds anyway. Every proposal this produces gets exactly
one decision, the same as a proposal from yesterday's conversation would.
Practically, that means importing a big history is reviewed over several
sittings, not in one pass: when the review queue fills (`review_queue_max`,
default 200), the script stops on its own, tells you to go clear some of it,
and picks up exactly where it left off when you run it again - it remembers
which conversations it has already offered, in `<config dir>/import-history-
progress.json`, so re-running never re-asks the local model about the same
conversation twice.

**Claude's export format is the one this project has actually seen.**
`scripts/recover_from_claude_export.py`, built and run against a real
export earlier in this project's history, found the shape this parser uses:
many JSON files, not one (`conversations.json` is an index with no message
text; the real conversations are one file each), `chat_messages`, a
`sender` of `human`/`assistant`, text as a bare string or as content blocks.

**Gemini's export format is not verified against a real file.** It is
written against Google Takeout's documented "Gemini Apps" activity export
shape. Takeout's activity log has historically captured the *prompt* you
sent more reliably than the *response* you got back, so a Gemini import may
end up mostly one-sided. If the field names in your real export don't match
what `gemini_conversations()` looks for, it says "0 conversations found in
this file" rather than guessing or crashing - open the JSON, check the real
key names, and the handful of `.get(...)` calls in that one function are
what to adjust.

### Test it

```powershell
python test_import_history.py
```

Eighteen checks, against synthetic export files - no real conversation data,
no network, no model. The ones that matter most: importing only ever adds a
*proposal*, never a fact; a full queue stops the run rather than dropping
anything silently; and resuming after a pause calls the local model exactly
once more, for the one conversation that had not been offered yet, not once
for every conversation from the start again.

---

# `jarvis_task_control.py` — the pause/stop/inject checkpoint, half of it

Ships as a whole file, not a patch, the same reason `jarvis_speech.py` and
`jarvis_research.py` do: there is nothing to patch against for the half of
this that lives in `jarvis_gate.py`/`jarvis_hud.py`.

`docs/AUTONOMY-PROPOSALS.md` section 3d designed this: a pause/stop/inject
control on a running plan, checked at the re-verification point that
`jarvis_ui_control.run()`, `jarvis_android_control.run()` and
`jarvis_browser_control.run()` already have, "no new architecture, one
more read at a point that already exists in all three loops." That
section also recorded, honestly, that the desktop widget's Pause button
had shipped ahead of any backend to answer it - clicking it would send a
request into an empty room, and `link.activity` would never actually say
`"paused"` because nothing was there yet to say it.

## What this closes, verified

- **`jarvis_task_control.py`** - a small, thread-safe, in-memory signal
  store: `request(task_id, "pause"|"stop")`, `checkpoint(task_id)`,
  `clear(task_id)`, and `inject_note(task_id, note)` /
  `pending_note(task_id)` for the free-text half of section 3d. Tested
  directly, no mocks needed - it is a plain dict behind a lock.
- **All three `run()` functions gain a `checkpoint` parameter**, injected
  exactly the way `announce` already is - a plain callback, never an
  import. None of `jarvis_ui_control.py`, `jarvis_android_control.py` or
  `jarvis_browser_control.py` has ever imported a sibling `jarvis_*`
  module, and this does not start now: a caller wires
  `checkpoint=lambda: jarvis_task_control.checkpoint(task_id)` itself.
  Read right where `announce` already fires, once per step, before the
  existing re-verification. `"stop"` ends the run exactly like a failed
  re-verification does, reason `"stopped by request"`. `"pause"` ends it
  the same way but adds `"paused": True` to the result, and the steps
  not yet run stay listed - ready for one explicit "continue" decision to
  become a fresh, approved `run()`, never resumed on their own. Omitting
  `checkpoint` (every existing caller, `jarvis_agent.py` included) is
  unchanged - a control with no injected checkpoint behaves exactly as it
  did before this patch, which every affected test suite's own control
  case now proves.

## What this does NOT close, and why

> **Closed since, 2026-09-23:** `task-control.patch` (its own section, at the
> end of this file) adds the routes and the `activity: "paused"` report. The
> names it uses are the ones both clients call (`/api/task/*`), not the
> `/api/pending/<id>/control` guessed below. What follows is kept as the
> record of why it waited.

Nothing here gives a client a way to actually call `request()` or
`inject_note()`, and nothing here broadcasts `activity: "paused"` back
out over `GET /api/events`. Both live entirely inside
`jarvis_gate.py`/`jarvis_hud.py`, neither of which is visible anywhere in
this repository - the same category of gap `degrade-filter.patch`'s
`looks_like_a_secret()` section and `jarvis_speech.py`'s wake-word gate
both already recorded rather than guessed past. Writing a new Flask route
against a file this session has never read and cannot run a test against
is precisely the "guessing blind" mistake `ui-control-wiring.patch`'s own
section made once and had to rewrite.

**What to add, once `jarvis_gate.py`/`jarvis_hud.py` are open on the real
machine** - the exact shape section 3d already specifies:

- A route - `POST /api/pending/<id>/control` fits the existing
  `/api/pending/<id>/...` family best, but confirm the real name against
  the file rather than assuming this one - taking `{"action": "pause" |
  "stop"}`, calling `jarvis_task_control.request(id, action)`.
- Wherever `run()` is actually invoked for a plan, pass
  `checkpoint=lambda: jarvis_task_control.checkpoint(id)` - this is the
  one line that turns the signal store into a live control.
- After a `run()` call returns, if the result carries `"paused": True`,
  publish it the same way `approval-resolved` already is - the doc's own
  words: "broadcast the same way `approval-resolved` already is today...
  no new transport, the existing fan-out `GET /api/events` already does
  this." `link.activity` becomes `"paused"` only from that real event,
  never optimistically from the click handler succeeding - section 3d's
  own point, made while this was still entirely unbuilt.
- `POST /api/pending/<id>/amend` with `{"note": "..."}` →
  `jarvis_task_control.inject_note(id, note)`; whatever builds the next
  proposal reads it back with `pending_note(id)`.
- Call `jarvis_task_control.clear(id)` once a task's id stops meaning
  anything - finished, stopped, or superseded by a fresh plan - so a
  stale signal can never attach itself to an unrelated later task that
  happens to reuse the id space.

## Test it

```powershell
python test_task_control.py
python test_ui_control.py
python test_android_control.py
python test_browser_control.py
```

Fourteen checks for the new module, plus three new cases in each of the
three control-module suites (stop, pause, and a control proving that
omitting `checkpoint` entirely still runs exactly as it did before this
was written). Against the pre-patch `run()` in any of the three, the new
`checkpoint`-passing cases fail with a `TypeError` for an unexpected
keyword - which is the correct failure for a parameter that does not
exist yet, not a false pass.


---

# `feedback.patch` and `jarvis_feedback.py` — "that answer was wrong"

Items 1 and 8 of `docs/LEARNING-RESEARCH-2026-09-23.md`, which the owner
approved on 2026-09-23.

**What was missing.** Jarvis learns what you tell it, but it never found out
whether its own answers were any good. There was no way to say "that was
wrong", so nothing could ever learn from it.

**What this adds, in plain words.**

1. Every answer from `/api/chat` gets an ID number, sent back in the
   `X-Jarvis-Route` header as `turn_id`. The backend quietly notes which
   remembered facts went into that answer — their ID numbers only.
2. A new route, `POST /api/feedback/mark`, lets a button on that one answer
   say `right` or `wrong` (or take the mark back).
3. For each fact, Jarvis counts how many answers it was used in that you
   marked right ("helpful") and marked wrong ("harmful"). Only your marks
   move these counts. Nothing else can: they are counted from your marks
   every time, not stored as a number something could change.
4. If a fact keeps showing up in wrong answers — **at least 5 wrong, and at
   least 3 times as many wrong as right** — Jarvis puts **one** card in the
   normal memory review queue: "Stop using this fact?". Nothing happens
   unless you accept it. Accepting **retires** the fact (it gets an end
   date and stays in the history; it is not deleted). Discarding it leaves
   the fact exactly as it was, and you will not be asked about it again
   until it has been in 5 more wrong answers.

## What it never stores, and where it lives

`jarvis_feedback.py` is a new module, shipped as a file like
`jarvis_research.py` — copy it into the backend folder. It keeps its own
small database, `feedback.db`, next to `memory.db` in the same config folder.
Its own file, not new tables in `memory.db`, so it cannot get in the way of
the memory store or anything that migrates it.

It stores **no text from any conversation**: no question, no answer, no fact
wording. Only a random answer ID, a time, fact IDs (`mem:12`), and marks. It
opens no network connection. The test checks every column of every table,
and fails if one could hold text.

Old marks are never overwritten. Changing your mind adds a new row, and only
the newest mark on an answer counts.

The counter format (an ID with helpful/harmful counts) is an idea from the
ACE project's playbook (`ace-agent/ace`, Apache-2.0). Only the idea — no ACE
code was copied, so there is no `THIRD-PARTY-NOTICES.txt` entry for it.

## Why the card goes through the review queue

`docs/ARCHITECTURE.md` says a feature that needs its own approval flow is a
design mistake, so the "retire this?" card uses the one that already exists
for memory: `jarvis_extract`'s proposals, one card, one decision,
`/api/memory/decide`. The patch adds `propose_retire()` to `jarvis_extract.py`
and one branch at the top of `_accept()`: a card whose `source` is
`feedback_retire` retires the fact it names and **adds nothing**. Without that
branch, accepting it would have stored the card's own sentence as a new fact.

The approval gate (`jarvis_gate`) was the other candidate, and it is the
wrong one here: it waits on a thread for an answer, and a "no" on it
proposes a standing rule ("do not do this without asking") — the wrong lesson
from "keep this fact".

**Hidden from any app that has not been changed for it.** Today both apps
label every review card "Keep" / "Discard", and the desktop says "Kept.
Jarvis can recall it now." after Keep. On a retire card, "Keep" (accept)
*retires* the fact - the button would say the opposite of what it does. So
`GET /api/memory/pending` leaves retire cards out, unless the app asks for
them with `?retire_cards=1`. An app sends that only once it labels the two
buttons "Retire it" (accept) and "Keep using it" (discard). Until then the
card simply waits in the queue, undecided: nothing is retired and nothing is
thrown away. (Chosen over a settings switch because it is per app: the
desktop and the phone can each start showing the card when each is ready,
and neither can show it with the wrong button.) Two places still count a
hidden card: the queue size in `setup.pending`, and the `proposal` event on
the event stream. So an unchanged app may briefly say "1 waiting" and then
show an empty list. That is the price of keeping it safe, and it goes away
when the app asks for the cards.

## Why the bar is so high

With one user, the counts are small, and a fact that was part of a wrong
answer did not necessarily cause the mistake. So one or two bad answers must
never be enough. The numbers are `RETIRE_MIN_WRONG = 5` and `RETIRE_RATIO =
3` at the top of `jarvis_feedback.py`.

## What the patch changes in `jarvis_hud.py`

Three small additions and one changed line:

- `/api/chat`: right after the step-down (degrade) loop, one call to
  `jarvis_feedback.record_turn(route_header["injected_ids"])`, which adds
  `turn_id` to the `X-Jarvis-Route` header. It sits after the loop on
  purpose: `degrade-filter.patch` empties `injected_ids` when a turn leaves
  the local model, so the facts recorded are the ones really used. It is
  inside its own `try`, so it can never be the reason an answer fails.
- `POST /api/feedback/mark` — `{"turn_id": "<32 hex>", "mark":
  "right" | "wrong" | "none"}`. One ID. A list is refused with a 400: a
  "mark all" would move every counter at once on one tap.
- `GET /api/feedback/counts` and `GET /api/feedback/mark?turn_id=…`.
- `GET /api/memory/pending`: the one existing line that changes. The list it
  returns leaves out retire cards unless the request says `?retire_cards=1`
  (above). This hunk's context is `memory-pane.patch`'s own output.

All three new routes check the token and the origin exactly like the memory
routes beside them. No new event kind: a new retire card rings the existing
`proposal` doorbell, because it is an ordinary proposal.

## Skill notes: counted, but nothing feeds them yet

The counters accept skill-note IDs too (`note:<skill>:<hash>`, from
`jarvis_feedback.note_id()`). But nothing records which skill notes went into
an answer yet — that happens inside `jarvis_skills.load()`, which is on the
owner's machine and not in this repository. Until something passes
`notes=[...]` to `record_turn()`, skill-note counts stay empty. Skill notes
never raise a retire card: removing a note is a change to the skill, which
already has its own gate (`skill-notes.patch`).

## Ordering

**Before `memory-intake.patch`** (see that section's Ordering: it rewrites a
line this patch's hunk ends on), after everything else it was written
against. Its context lines are other patches' output:
`memory-safety`'s `_accept()` and the end of `propose()` (with `memory-noise`
and `decide-once` above them), `memory-pane`'s memory routes, and
`tool-calling-wiring`'s `if use_tools:` split. Needs `jarvis_feedback.py`
copied into the backend folder as well; without it, the chat hook does
nothing and the two routes answer 503.

## How it was checked, and what was not

The real `jarvis_hud.py` and `jarvis_extract.py` are not in this repository,
so the patch was checked against **reconstructions**: every line inside the
regions it touches was taken verbatim from the patches listed above, and
`git apply --check` passes against them (forward and in reverse). That
proves the patch matches what those patches wrote. It cannot prove nothing
else on the owner's machine differs — `apply-patches.ps1` rehearses on a copy
first, so if it does differ, the run stops and changes nothing.

Not verified: that `route_header` always holds an `injected_ids` key. It is
set by code this repository has never seen; `degrade-filter.patch` and
`test_degrade_filter.py` both treat it as always there. If it is missing,
the answer still gets a `turn_id`, with no facts recorded.

## Test it

```powershell
python test_feedback.py
```

74 checks with the patched backend present. Without a backend folder, the 48
that test `jarvis_feedback.py` itself still run, and the two halves that
need `jarvis_extract.py` and `jarvis_hud.py` say SKIP. With those files
present but unpatched, both halves FAIL rather than skip.

---

# `jarvis_skill_discovery.py` and `skill-suggest.patch` — Jarvis offers a routine as a skill, once, and only writes it if you say yes

Item 7 of `docs/LEARNING-RESEARCH-2026-09-23.md`. When you keep asking Jarvis
for the same chain of tools (for example: search notes, then read the
calendar), it now notices, and offers to save that chain as a skill. The
offer is an ordinary approval card. Nothing is written until you tap yes.

**In plain words, what happens:**

1. At the end of every chat turn that used a tool, `jarvis_agent.py` writes
   **one line** to the audit log Jarvis already keeps
   (`~/.openjarvis/logs/jarvis-<date>.jsonl`): a random turn id and the tool
   names in order, each with "did it run" and "did it work". No arguments, no
   results, no words from the conversation. There is no field for them.
2. `jarvis_skill_discovery.py` counts chains of 2 to 4 tools that ran in
   several separate turns. Tools that ran **without asking** (tiers `auto`
   and `notify`, which is every read-only tool) count, the same as approved
   ones. Denied, timed-out, refused and failed steps do not.
3. When one chain has run in **3 separate turns in 30 days**, it raises
   **one** card through the approval Jarvis already needs to change itself
   (`modify_own_code`, the same gate `jarvis_skills.write_skill()` uses). The
   card shows the whole file it would write and where.
4. **Yes** writes that one file. **No** writes nothing, and that routine (and
   any piece of it) is never offered again. **Nobody answering** writes
   nothing, and it can be offered again another day. At most one card a day,
   one routine per card. There is no "save all".

## What was checked first, and why a new log line was needed

The research doc listed this as unknown: does the approval log record which
turn each action belonged to? **It does not.** Checked against the files in
this repo:

- `approvals.db` (`SELECT id,action,tier,detail,prompt,created,raised FROM
  approvals`, quoted in `test_gate_egress.py`) only gets a row for `ask`-tier
  actions, so the read-only tools never appear in it, and it has no turn
  column.
- The audit log's gate lines are `{"t", "iso", "event", "detail"}`
  (`rebuilt/jarvis_framework.py`, `audit_log`) with `detail` =
  `{"action", "detail"}` or `{"id", "action", "by"}` (`gate-outcome.patch`).
  A time and an action name. No turn.

Guessing turns from timestamps would merge two turns a minute apart. The tool
loop is the only code that knows where a turn starts and ends, so it writes
the record - one `agent.chain` line per tool-using turn, into the **same**
audit log, through the same writer. Still one log.

## Rules it keeps (each has a test)

- Counting only. Nothing in the module opens a network connection; the test
  replaces `socket.connect` with an error for the whole run.
- The skill text is built from tool **names** and the tool descriptions in
  `jarvis_agent.TOOLS`, which this project wrote. None of your messages are
  copied into it (OpenJarvis's version copies your past questions in as
  examples; that part was deliberately not taken).
- A skill is only written after a **person** said yes: the gate's tier must
  be `ask` and its outcome `approved`. If `modify_own_code` is ever set to
  `auto` or `notify`, the gate would say "allowed" with nobody asked - so no
  card is raised and nothing is written (the same rule as
  `skill-notes.patch`).
- `run()` needs `approved=True` spelled out, writes exactly the text that was
  on the card to exactly the path that was on the card, and never writes over
  an existing folder.
- Nothing is deleted. Every offer and every answer is appended, with its
  date, to `~/.openjarvis/skill-offers.json`. If that file cannot be read,
  offers stop - not knowing what you declined must not become asking again -
  and the file is left untouched.
- The model decides nothing: not which chain, not the name, not the text,
  not the tier, and not where a turn came from. A record can carry an
  `origin` set by the backend; a turn whose origin is anything other than
  `"owner"` is not counted, so a future scheduled job cannot teach itself a
  routine. (Nothing sets `origin` yet - item 10 is where that belongs.)

## What is NOT verified, said plainly

- **Where `jarvis_skills.py` loads skills from.** That module is not in this
  repo. The file is written to `JARVIS_SKILLS_DIR` if you set it, otherwise
  `~/.openjarvis/skills/<name>/SKILL.md`. Right after writing, the module asks
  `jarvis_skills.cards()` whether the new skill is listed and records the
  answer as `listed` (true / false / null if it could not ask). If
  `/api/skills/suggestions` shows `"listed": false` on a written offer, set
  `JARVIS_SKILLS_DIR` to the folder `jarvis_skills` reads.
- **`write_skill()` is not called**, on purpose: its signature is not in this
  repo, and it raises its own `modify_own_code` card, so you would be asked
  twice about one file. Its scanner still runs when the skill is loaded
  (`jarvis-framework.toml` section 12 says the scanner runs on the raw bytes
  before any skill reaches the model).
- **Saying no also proposes a memory rule.** `gate-outcome.patch` turns every
  denial into a memory proposal - here, "I do not want Jarvis to modify own
  code without asking me first". That is the gate's own behaviour. It is only
  a proposal in the review queue; Discard it if you only meant "not this
  skill".
- `notice_for()` words the card's lock-screen line from `jarvis_gate._RISK`.
  Whether `_RISK` has an entry for `modify_own_code` is not visible here; if
  it does not, the notice uses the unknown-action wording.
- `[self_modification].required_checks` (shadow copy, critic review) are not
  built (`pipeline_implemented = false` in the config). A skill is a text file
  of instructions, not code, and goes through the same card `write_skill()`
  uses today.

## Settings (all optional, in `[skills]` of `jarvis-framework.toml`)

| key | default | meaning |
|---|---|---|
| `suggest_skills` | `true` | `false` turns offers off. `enabled = false` does too. |
| `suggest_after_repeats` | `3` | separate turns before an offer. Never below 2. |
| `suggest_window_days` | `30` | how far back to count (1-90). |
| `suggest_every_hours` | `24` | at most one card per this many hours. |

Setting `modify_own_code = "never"` under `[autonomy.tiers]` also stops
offers - and every other self-change - outright. If `[logging] enabled =
false`, nothing is recorded, so nothing is ever offered.

## `skill-suggest.patch` — the read-only route

Adds `GET /api/skills/suggestions` next to `GET /api/skills`, inside the same
branch and therefore behind the same checks (that branch's origin/token lines
are not visible in this repo, so "the same checks as `/api/skills`" is the
exact claim). It returns `jarvis_skill_discovery.view()`: which chains are
counted, their status, the offer history, and why offers are off if they are.
It cannot approve, write or trigger anything. If the module is missing it
answers `{"available": false, "reason": ...}` instead of failing.

**Ordering:** needs `appearance.patch` - both hunks sit inside lines that
patch wrote (the `/api/visual-spec` entry in the GET list and the end of that
branch). Nothing else touches them. Listed last in `apply-patches.ps1`.

**Install:** copy `backend/jarvis_skill_discovery.py` beside `jarvis_hud.py`,
the same as `jarvis_agent.py`, then run `apply-patches.ps1` as usual. The
updated `jarvis_agent.py` must be copied too - it is what writes the
`agent.chain` line.

## Test it

```
python3 backend/test_skill_discovery.py
python3 backend/test_skill_suggest.py
python3 backend/test_agent.py
```

`test_skill_discovery.py` (108 checks) writes through the real
`rebuilt/jarvis_framework.audit_log` into a temp folder and uses a fake gate,
so no real log, approval or skills folder is touched. Ten deliberate
mutations of the module (drop the tier check, count failed steps, count per
appearance instead of per turn, overwrite folders, accept `approved=1`, skip
the cooldown, ...) each made it fail before this was committed.
`test_skill_suggest.py` checks every context line of the patch against
`appearance.patch`'s own output, and, once `jarvis_hud.py` is present, that
the route is wired and only reads. `test_agent.py` gained five tests: the
record holds tool names and nothing else, a turn with no tool records
nothing, a failing recorder never costs the answer, and the record is still
written when the answer fails to stream.

---

# Two new modules to copy first: `jarvis_speed.py` and `jarvis_owned_tables.py`

The two patches below call two new modules. Like `jarvis_research.py`, they
ship as whole files, because there is nothing on your PC to patch for them.
Copy both into the backend folder before running `apply-patches.ps1`. From
the folder you cloned this repository into:

```powershell
Copy-Item .\backend\jarvis_speed.py, .\backend\jarvis_owned_tables.py "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\"; Write-Host "Copied both into the backend folder."
```

If you forget, nothing breaks. Every call into them is wrapped. Without
`jarvis_speed.py` nothing gets timed. Without `jarvis_owned_tables.py` the
documents table is never read, which is the safe side.

---

# `documents-owned.patch` — another program's table must not reach your prompts

Apply after `documents-honesty.patch`. It must come after it, because its
context lines are that patch's output. `apply-patches.ps1` lists it last.

**The problem.** Epic-Jarvis keeps its memory in `~/.openjarvis\memory.db`.
That is OpenJarvis's folder and OpenJarvis's file name, left over from when
Jarvis was designed to sit in front of OpenJarvis. OpenJarvis was never part
of this setup, but you did download a copy once. If that copy is ever run, its
document indexer creates a table called `documents` in that same file
(OpenJarvis `rust/crates/openjarvis-tools/src/storage/sqlite.rs:58-67`).
`jarvis_hud.py` reads a table with exactly that name in three places: the
brain map, the status line, and the text that retrieval puts in front of the
model. So whatever OpenJarvis indexed would start reaching Jarvis's prompts,
and nobody would have decided that.

**The fix.** All three readers now ask a second question. It is not only
"is there a `documents` table?" but also "did Epic-Jarvis record creating
it?" (`_documents_are_ours()`). The record is one row in
`epic_jarvis_created_tables`, kept by `jarvis_owned_tables.py`. A table with
the right name and no record is left completely alone: never read, never
changed, never deleted.

**What you will notice: nothing.** Nothing in Epic-Jarvis creates a
`documents` table today, so the documents were never read before this patch
and are still not read after it. The difference is that this now stays true
if another program adds one. The brain map's `sources` gains one field,
`documents_not_ours`. It is `true` when a `documents` table is there that
Epic-Jarvis did not make, so the screen can say so rather than show a quiet
`documents: false`.

**For a future feature that really does index documents.** It must create
the table with `jarvis_owned_tables.create_owned_table(con, "documents", ddl)`.
That writes the table and its record in one transaction. It refuses when
a table with that name is already there. It also refuses
`CREATE TABLE IF NOT EXISTS`, which would quietly adopt someone else's table.

## Test it

```powershell
python test_documents_owned.py
```

Twenty checks in the container, and four more on your PC once the patch is
applied. Real SQLite files: a table made the way OpenJarvis makes it is "not
ours", and its rows are still all there afterwards. Epic-Jarvis refuses to
create over it. A table made through `create_owned_table` is "ours" (the
control). A create that fails half-way leaves no record behind.
It also rehearses the patch against the text `documents-honesty.patch` wrote,
using `git apply` on a stand-in file (`_skeleton.py`). **That proves the
context matches the earlier patch's output. It does not prove the rest of your
real file matches.** Only `apply-patches.ps1`'s rehearsal against your real
files can prove that. On your PC, where the patched `jarvis_hud.py` exists,
the test also lifts the real `_documents_are_ours` out of it and runs it.
Against an unpatched `jarvis_hud.py` that part fails, which is correct.

---

# `speed-record.patch` and `jarvis_speed.py` — how fast was each answer?

Apply after `gpu-offload.patch` and `tool-calling-wiring.patch`. It must come
after both, because its context lines are their output. `apply-patches.ps1`
lists it last.

**The problem.** "Jarvis got slow" had no answer except a feeling. An Ollama
update, a game holding video memory, or a model that no longer fits on the
graphics card can each make every answer take three times as long. Nothing
recorded it. The only timings anywhere were one-off measurements typed into
`docs/MODEL-TOPOLOGY.md`.

**What it records.** One row per answer, in `speed.jsonl` in the Jarvis
settings folder (`%USERPROFILE%\.openjarvis\` unless you moved it):

- which model answered
- how long until the first word
- how long the whole answer took
- words per second and tokens per second
- how much of the model was on the graphics card
- whether tools were used

**What it never records: any words of the conversation.** Not the question,
not the answer, not a summary. That is enforced in code: every row goes
through a filter (`_clean()`). It keeps only a fixed list of field names, and
only numbers, true/false values and a model name. A text field passed in by
mistake is dropped, not written. The stream is read as it passes through, to
count words and time them. The text is never kept.

**It stays on this PC.** There is no upload, no leaderboard and no
analytics. OpenJarvis has all three, and they are exactly the part not
copied. The file is only ever added to. At about 250 bytes a row, a hundred
answers a day comes to about 9 MB a year. Reading only looks at the end of
the file, so its size never slows anything down.

**Where it hooks in.** A few small hooks in `jarvis_hud.py`, each wrapped so
that timing can never be the reason an answer fails:

- A stopwatch starts before the request goes to Ollama.
- Both answer paths (plain, and with tools) show each chunk to the meter
  *after* it has been sent to you.
- A finished answer is recorded. An answer cut off because the phone dropped
  out is never recorded, since half an answer's speed is not a speed.
- `GET /api/models` gains a `speed` block, next to the `offload` block from
  `gpu-offload.patch`.

The graphics-card share comes from `jarvis_models.offload_status()`. It is
looked up after the answer, on a background thread, so it never holds an
answer open.

**Tool answers are marked.** When tools are on, the time to the first word
includes the tool calls, and any wait for you to approve one. So those
answers are left out of the "first word" figure on the screen, and counted
everywhere else.

**The slowdown warning.** When the last 10 answers on a model are 30% or
more slower than the 20 before them, the `speed.note` says so in words. It
stays silent until there are 30 answers, because a verdict from three answers
would be noise.

**Not verified:**

- Whether Ollama's OpenAI-style stream reports token counts. The meter
  handles all three cases: exact counts from Ollama's own timings when they
  are present, `usage` when that is sent, and counting stream pieces when
  neither is. Each row says which one it used (`token_source`).
- Power readings on the 2080 Super. They were not attempted.

## Test it

```powershell
python test_speed_record.py
```

Sixty-three checks with no network (opening a socket fails the test) and a
fake clock. The main one: an answer full of a distinctive secret sentence is
timed, then every word of it is searched for in the file, and none is found.
Also checked:

- a word split across two stream pieces counts once;
- all three stream shapes are handled;
- a broken or unwritable file never raises;
- the slowdown warning, with a control where nothing changed;
- the patch rehearsed against what `gpu-offload.patch` and
  `tool-calling-wiring.patch` wrote.

The same limit applies as above: the rehearsal proves the context matches
those patches, not the rest of your real file. On your PC it also reads the
patched `jarvis_hud.py` and checks that both answer paths feed and finish
the meter, and that no `finish` sits inside an error handler.

---

# The Tripwire speed check — a function, and the hook still to add

**Tripwire is not in this repository.** `jarvis_tripwire.py` exists only on
your PC. The only trace of it here is its name in `selftest.py` and its
settings in `jarvis-framework.toml` §21. So this could not be wired in and
tested for real. What exists is the part Tripwire calls, in `jarvis_speed.py`,
tested on its own.

`jarvis-framework.toml` §21 says Tripwire already runs a few fixed test
prompts ("probes") on the old model before a swap and on the new one after
it. Ollama's own replies carry exact timings, so the hook is small. In
`jarvis_tripwire.py`, wherever it runs its probes:

```python
import jarvis_speed
speed = jarvis_speed.SwitchSpeed(old_model, new_model)
# before the swap, for each probe reply:   speed.add("old", reply)
# after the swap, for each probe reply:    speed.add("new", reply)
result["speed"] = speed.finish()
```

`finish()` returns the comparison, with a sentence ready to show ("Old: 41
tokens/s. New: 20 tokens/s. The new model is about 51% slower."). It always
adds, in these words: "This measures speed only. It cannot tell you whether
the new model's answers are better or worse." It also writes a `switch` row
to `speed.jsonl`, so the Models screen shows the last switch even if
Tripwire's own result screen is closed.

Two things to know:

- **If the probes go through the OpenAI-style endpoint**, their replies
  carry no timings. Wrap each call with `speed.timed("old", lambda: ...)`
  instead. You then get a first-word time from the wall clock but no speed
  figure.
- **Never measure the old model after the swap.** Running a prompt on it
  loads it again, and on an 8 GB card that pushes the new model off the card.
  So `measure(model)` (three fixed prompts of its own, for when Tripwire's
  probes cannot be timed) is for the new model, or for the old one *before*
  the swap and only when `is_loaded(old)` says it is already in memory. If
  the old model was not measured, `finish()` falls back to the last stored
  measurement of it, then to its recent real answers. The sentence says which
  one it used.

`measure()` talks only to Ollama on this PC and refuses any other address
before sending anything. It sends only the three fixed prompts in
`FIXED_PROMPTS`, which are about nothing in particular. It never sends
`num_ctx`, because a different context size would make Ollama reload the
model. It is covered by `test_speed_record.py` (the switch and measure
sections).

---

# `selftest.py` step 7 — the doctor: is the model ready, and on the card?

**The problem.** The self-test never mentioned Ollama. The most common way
Jarvis goes wrong could pass every check it had. That is when part of the
model spills off the graphics card onto the CPU: every answer gets several
times slower, and no error appears anywhere.

**What it checks now**, at the end of every run, even when backend files
are missing:

| check | fails when | how to fix it, as printed |
|---|---|---|
| Ollama answers | nothing is listening | start the Ollama app, or `ollama serve` |
| the configured model is downloaded | it is not in Ollama's list | `ollama pull <name>`, or for `jarvis-primary` the `ollama create` line |
| it is fully on the graphics card | any of it is on the CPU, with the percentage | close what is holding video memory, restart Ollama |
| context size | *warning only*, when Ollama gave the model under 8192 tokens | `docs/MODEL-TOPOLOGY.md` |
| `OLLAMA_KV_CACHE_TYPE` | *warning only*, when it is not `q8_0` in this window | `docs/MODEL-TOPOLOGY.md`, "Setup" |

**Read-only, and it loads nothing.** It sends three GET requests to Ollama:
`/api/version`, `/api/tags` and `/api/ps`. None of them loads a model. So when
no model is loaded, the graphics-card check says **skip**, with "Ask Jarvis
anything, then run this again". It does not load a model to find out. When a
different model is loaded, that is a warning, not a failure. When Ollama's
address is not this PC, nothing is sent there at all and it says so.

The two cache checks can only ever warn. The right numbers depend on the card
and the model. A smaller cache means a shorter memory of the conversation,
not something broken. The `OLLAMA_KV_CACHE_TYPE` check can only see the
settings of the window the self-test runs in, not Ollama's own, and it says
that too.

The configured model comes from `jarvis_models.current_model()`, the same
call the Models screen makes, or from `JARVIS_MODEL` when that is set.

## Test it

```powershell
python test_selftest_doctor.py
```

Thirty-six checks with a fake Ollama that records every URL. It checks that
only the three read-only paths are ever asked, all GET with no body, and never
`/api/generate`, `/api/chat`, `/api/pull` or `/api/show`. It also checks:

- no loaded model is a skip, not a failure;
- a 65% spill fails with "65%" in the message;
- the cache checks never produce a failure, with a control where nothing
  warns;
- another machine's address is never contacted;
- strange replies never crash it.

---

# The memory audit's fixes — `test_memory_honesty.py`

From the 2026-09-23 memory audit. Each check feeds the real thing that
produces a value into the real thing that reads it:

- **"Start learning" starts the learner** and "Stop learning" drops a pass
  already waiting - on `_Learner`/`set_learning()` as `extraction-wiring`,
  `memory-pane` and `memory-intake` together write them.
- **"Remember:" makes a card with learning switched off.**
- **Nothing reads a conversation with a model that is not on this
  machine** - the check `memory-intake.patch` appends to `jarvis_extract.py`
  is run; `import_history.py` refuses before reading anything; and every
  `propose()` call in the repository is read to prove it goes through the
  checked function.
- **The overnight-tidy card**: the HUD's plain read of
  `/api/memory/pending` no longer uses it up (only `?sleep_offer=1` does,
  which the Brain window and the phone send), and the card's words say the
  feature is not built and nothing is retired without a yes on that fact.
- **Field names**: the real `MemoryStore.status()`, fact rows and
  `jarvis_intake.annotate()` rows against every field `brain.js` and the
  phone's `Learning.kt` read - and against the desktop UI tests' own
  fixture, so it cannot invent fields again.
- **The same typed date means the same moment on both apps**: the numbers
  the phone's `MemoryDatesTest.kt` pins are fed to the desktop's own
  `asOfSeconds` under node, in the same time zones.

```powershell
python backend\test_memory_honesty.py
```

Needs `git` for the learner checks and `node` for the date check; without
either, those parts say SKIP rather than pass.

---

# Where the 2026-09-23 learning jobs meet — `test_learning_integration.py`

The four learning jobs (memory intake, feedback, skill suggestions, and
speed/doctor/documents) were built at the same time, each on its own. When
they were merged, three things turned up that none of them could see alone.

**1. `feedback.patch` has to go before `memory-intake.patch`.** Both were
written as "last in the stack". Feedback's new `/api/feedback/mark` block ends
on the memory-route line `"/api/memory/learning", "/api/memory/sleep_time"):`
and memory-intake rewrites that exact line to add `/api/memory/keep_both`.
With memory-intake first, feedback cannot find its context and the whole run
stops before changing anything. With feedback first, both apply. Checked both
ways with `git apply` on a rebuilt `jarvis_hud.py`.

**2. The "retire this?" card was offered a "Both are true" button.** It
should not be, and now is not. Feedback's retire card names the fact it asks
about in `replaces_id`, the same field a correction card uses. Memory intake
offered "Both are true" on any card with that field set. Pressing it on a
retire card marked the card accepted and retired nothing - the same effect as
"Keep using it", but written down as something else. Fixed in two places:

- `jarvis_intake.annotate()` (and the patch's fallback copy of it) now sets
  `keep_both_ok: false` on a card whose `source` is `feedback_retire`;
- `decide_keep_both()` in `memory-intake.patch` refuses such a card with
  `409 {"ok": false, "reason": "not_a_correction"}` and leaves it waiting.

The test proves it both ways: it failed 5 checks before the fix, on a
stand-in `jarvis_extract.py` carrying both patches, and passes after.

**3. `apply-patches.ps1` stopped every run with three files "missing" that
were not missing.** This one is older than the learning work. Three patches
(`ui-control-wiring`, `ollama-direct`, `tool-calling-wiring`) have a date
after a tab on their `+++ b/` line, which is normal for `diff -u`. The
script's missing-file check read the name up to the end of the line, so it
looked for a file called `jarvis_hud.py<TAB>2026-09-18 ...`, did not find it,
and stopped - with every real file present. It now reads the name up to the
tab. Checked with PowerShell 7 against a folder holding every backend file
name: before the fix it stopped with the three "missing" files; after it,
the run went on to the rehearsal. **If you ever saw "jarvis_hud.py 2026-09-18
... is not in your backend folder", this was why.**

## Test it

```
python backend\test_learning_integration.py
```

22 checks without a backend folder (the stack order, the retire card's
wording, and `jarvis_intake` on its own). With `JARVIS_BACKEND` pointing at a
backend carrying both patches, 7 more run through the real
`jarvis_extract.py`: the retire card has no "Both are true", the keep-both
route refuses it and leaves it waiting, and accepting it still retires the
fact.

---

# `voice-enroll.patch` — "Train my voice"

**What it is.** Jarvis only obeys your voice. It learns what you sound like
from a few recorded sentences. Until 2026-09-23 nothing could do that
learning: `jarvis_voice.enroll()` existed, but no route, screen or script
called it. So in the default "owner" mode every voice was refused, yours
included.

**How to use it.** On the phone: open **Checks** (the platform checks
screen), find the **Your voice** card, tap **Train my voice**. Read the five
sentences one at a time (tap Record, read, tap Stop - each clip's length is
shown and you can redo any of them), then tap **Send to your PC**. An
approval card appears, on the PC and on the phone. Approve it. That is the
moment Jarvis learns your voice - not before.

## Why there is a card

Your voice print decides who Jarvis obeys. Replacing it is a change to
Jarvis's own settings, action `change_own_config`, which is tier `"ask"` in
`jarvis-framework.toml`. The card is also what stops someone who picks up
your unlocked phone from recording their own voice and becoming "you" in one
tap: the card says "If you did not just do this on your phone, say no".

## What the PC does

| | |
|---|---|
| `POST /api/voice/enroll` | Body `{"clips": ["<base64 WAV>", ...]}`. Checks the clips, keeps them **in memory only**, raises **one** card, answers `202` at once. Enrols nothing. |
| approve the card | `jarvis_voice.enroll()` builds the voice print from the clips, then the clips are deleted. |
| deny, or nobody answers in 3 minutes | Nothing changes. The clips are deleted. |
| a second training while a card waits | `409` - "approve or deny that card first", with the seconds left. It does not replace the first: that card would still be on screen, and approving it would then enrol the wrong clips or nothing. |
| `change_own_config` not `"ask"` | `409` before any card, saying to set it back to `"ask"`. A card that no person answers must not replace your voice. |
| limits | 3 to 8 clips, each 1 to 10 seconds, 16 kHz 16-bit mono WAV, not silent. Anything else is a `400` naming the clip: "clip 3 is too short (0.6 s) - read the whole sentence". Eight clips of ten seconds fit inside the backend's 4 MB request limit. |
| `/api/voice/status` | `gate.enrolled`, `gate.samples`, `gate.embedder`, `gate.speaker_model`, `gate.needs_retraining`, and `gate.training` (a card waiting, and how the last one ended). |

The card is raised through `jarvis_gate.check()` on a background thread,
the same way `jarvis_skill_discovery.offer()` raises its "make this a
skill?" card (the check blocks until someone answers). The tier is checked
before the card and again on the answer: `allowed` is also `True` on tiers
`auto` and `notify`, where nobody was asked.

Nothing logs audio or the token. The audit log gets two lines per training,
with counts and seconds only. The card shows the number of clips and their
total length, nothing else. `test_voice_enroll.py` checks all of that,
including that `jarvis_voice_enroll.py` has no print, logging or file-write
call in it at all.

## Found while building it - read these

**1. The phone never showed its talk button.** The phone reads
`/api/voice/status` as `listening`, `stt`, `tts`, `audio_in` and `gate`
blocks, and shows the talk button only when `listening.push_to_talk` is
true. `jarvis_speech.status()` sent none of those - only flat keys - so the
button could never appear, whatever else worked. The utterance answer had the
same gap: the phone reads `ok` and `owner`, the module sent `is_owner`, so
even a real transcript would have read as "didn't catch that". Fixed in
`jarvis_speech.py`: it now sends both shapes (the flat keys stay, for the
desktop). `test_voice_contract.py` reads the phone's own `VoiceModels.kt`
and the desktop's `voice.rs` and fails if a field either of them reads goes
missing again. One thing not checked: that `jarvis_hud.py`'s utterance route
sends `Heard.as_dict()` as it is. The route's reply line is not in this
repository. The desktop's `voice.rs` assumes the same thing.

**2. The talk button now shows only when talking can actually work:** your
voice is trained (or voice is set to `"broad"`), **and** the PC has
speech-to-text set up. The shipped config said `stt_engine =
"faster-whisper"`, which `jarvis_speech.py` does not speak, so on your PC the
button stays hidden after training until speech-to-text is set up. The
Checks screen says so in words ("Talk button on Home: hidden. The PC has no
speech-to-text set up yet"). That is the honest answer - a button that can
only ever say "no engine" is worse than none. *Since fixed:* see "Voice that
works" at the end of this file for the install.

**3. The basic voice check does not keep strangers out.** Without a speaker
model the PC uses a "spectral" check: how loud each band of pitch is. Tried
on four different synthesised voices here, it scored every one of them above
0.9 against the others, and the bar is 0.35 - so every voice passed as every
other. That is expected from how it works (those numbers are never negative,
so any two voices look alike). It stops silence and noise, not a person. The
phone says "Using the basic voice check, which cannot reliably tell two
people apart" until the better one is installed. **Install it (below).**

**4. The precedent in the brief was not what the code does.** The brief said
`POST /api/voice/wake` raises an approval card, and `docs/JARVIS-API.md` says
the same. This repository's `jarvis_speech.set_wake_enabled()` applies the
change at once with no card - its own docstring says so, because
`jarvis_gate.py`'s interface was not visible when it was written. So "Train
my voice" does not copy wake. It calls `jarvis_gate.check()` directly, the
way `jarvis_skill_discovery.py` and `jarvis_agent.py` already do. *Since
fixed:* `set_wake_enabled(True)` now raises its card the same way (see "Voice
that works" at the end of this file).

**5. The desktop's microphone records at its own rate** (often 48 kHz) and
sends that. The speaker model is now told the real rate and copes. The basic
spectral check is not, and a voice trained at 16 kHz on the phone may score
differently from the desktop's microphone. One more reason for the better
check.

## Install the better voice check (recommended)

The better check is a speaker model: a 30 MB file that turns a voice into
numbers that really do differ between people. It runs on the processor, not
the graphics card, through `sherpa-onnx` - the same engine the rest of
Jarvis's voice uses. No PyTorch needed.

Paste each line into PowerShell, one at a time.

**1. Install sherpa-onnx** into the Python that runs Jarvis:

```powershell
python -m pip install --upgrade sherpa-onnx; python -c "import sherpa_onnx; print('sherpa-onnx', sherpa_onnx.__version__, 'is installed')"
```

**2. Download the speaker model.** It lands in the `voice-models\speaker`
folder inside Jarvis's settings folder (normally
`C:\Users\pcadmin\.openjarvis\voice-models\speaker\model.onnx`), and the
line checks it is the right file:

```powershell
$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $base = if ($env:OPENJARVIS_CONFIG_DIR) { $env:OPENJARVIS_CONFIG_DIR } elseif ($env:JARVIS_CONFIG_DIR) { $env:JARVIS_CONFIG_DIR } else { "$env:USERPROFILE\.openjarvis" }; $d = Join-Path $base 'voice-models\speaker'; New-Item -ItemType Directory -Force -Path $d | Out-Null; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx' -OutFile (Join-Path $d 'model.onnx'); if ((Get-FileHash (Join-Path $d 'model.onnx') -Algorithm SHA256).Hash -eq '357A834F702B80161E5B981182C038E18553C1F2CA752ED6CEC2052365D4129B') { Write-Host "OK - the speaker model is at $d\model.onnx" -ForegroundColor Green } else { Write-Host "That is not the expected file. Delete $d\model.onnx and run this line again." -ForegroundColor Red }
```

(`speaker-recongition` is misspelled in the real address. Leave it.)

**3. Put the new code on the PC.** From this repository's folder, run the
patch script. It applies `voice-enroll.patch` and copies in
`jarvis_voice_enroll.py`, `jarvis_speech.py` and `jarvis_voice.py`, backing
up any older copies first:

```powershell
.\scripts\apply-patches.ps1
```

**4. Check the PC sees the model.** This prints the voice check's status.
Look for `embedder  sherpa-onnx:357a834f702b` and `speaker_model  True`:

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; python jarvis_voice.py
```

If it still says `spectral-v1`, the `note` line says why (for example "the
sherpa-onnx package is not installed").

**5. Restart Jarvis, then train your voice on the phone** (Checks → Your
voice → Train my voice) and approve the card. If you trained with the basic
check before installing the model, train again: a voice print made with one
check cannot be used by the other, and the phone will say "Your PC's voice
check changed since you trained it".

To use a different model file instead, set `speaker_model = "C:/path/to/file.onnx"`
under `[voice]` in `jarvis-framework.toml`.

**What was checked, and what was not.** Checked in the dev container: the
download address works (29,596,978 bytes, the SHA-256 above), `sherpa-onnx`
1.13.8 installs with pip and loads the model, and a voice trained through
the real enrolment code with this model passes `jarvis_speech.hear()`
(`JARVIS_TEST_SPEAKER_MODEL=<file> python backend/test_voice_enroll.py`).
**Not checked:** the Windows `pip` install, these PowerShell lines on
Windows (PowerShell could not be run by the session that wrote them), and how
well the model tells real people apart - there was no recording of several
real people to try it on. Its bar is still the config's `threshold = 0.35`;
after training, it is worth having someone else try the talk button once.

## Test it

```powershell
python backend\test_voice_enroll.py; python backend\test_voice_contract.py
```

`test_voice_enroll.py`: staging never enrols; approving enrols and deletes
the clips; denying, a timeout, a refusal or a wrong tier deletes them and
enrols nothing; every limit is a `400` naming the clip; a second training is
a `409`; no audio or token in the audit, the card, stdout or the status; the
patch applies to what `voice-503` and `appearance` wrote (GNU `patch`, the script's fallback, was also tried by hand: no fuzz) and leaves `test_voice_503.py`'s
four `_no_speech` call sites at four. `test_voice_contract.py`: the status
and utterance JSON against the phone's and the desktop's own field lists.

---

# `cloud-one-turn.patch` — a cloud lane gets your newest question, alone

**What changed around it.** The phone and the desktop quickbar used to send
only your newest question to `/api/chat`, so every follow-up ("and on
Tuesday?") reached the model with nothing before it. They now send the
conversation so far too - at most 10 earlier questions and answers and
18,000 characters, kept in memory only (`net/ChatHistory.kt`,
`src/chat-history.js`, and `docs/JARVIS-API.md` §4 for the numbers). The HUD
page always sent its own.

**Why this patch.** The cloud cut in `/api/chat` keeps every `role ==
"user"` message. With a conversation attached, that means your *earlier*
questions too. If a question like "my salary is ..." was kept local when you
asked it, it must not ride along later on a question that happened to go to
a cloud lane. Whether `jarvis_router.choose()` is shown the whole
conversation or only the newest question is decided in `jarvis_hud.py`,
which is not in this repository, so this was not checked - the patch makes
it not matter.

**What it does.** Inside `_open`, which every attempt of the degrade loop
goes through with the lane it is about to call: if that lane is not the
local model, the request is cut down to the newest user message. Nothing
else goes - not earlier questions, not answers, not the recalled-facts
block. A screenshot turn goes whole. The local model is untouched and still
gets the whole conversation.

**The cost.** A cloud answer to a follow-up does not see the conversation.
`ollama-direct.patch`'s own note says no machine has had a cloud lane set up
so far; if that is still true, this changes nothing you can see today. It is
here for the day one is.

**Order.** After `ollama-direct.patch`, whose `_completions_url(lane),` line
is its context. Listed last in `apply-patches.ps1`.

---

<!-- ===== task controls, notes, power (2026-09-23) - begin ===== -->

# `task-control.patch` — Pause, Resume, Stop, and notes, for real

**What was wrong.** Both apps have had Pause, Resume, Stop and "add a note"
buttons for days. Every one of them sent a request to an address the PC did
not have, so every press failed (or, worse, looked like it might have worked).
The note field on approval cards was the same.

**What this adds, in plain words.** Five addresses on the PC, using exactly
the names both apps were already calling, so neither app had to change where
it sends:

| button | what happens now | approval card? |
|---|---|---|
| **Stop** | The running task stops before its next step. Steps already done stay done. If a task is paused, Stop forgets it. | No — stopping is the safe direction, like Deny. |
| **Pause** | The running task stops before its next step, and the PC remembers the steps that did not run. Both apps then show "paused" and a Resume button — only once the PC says so, never on the click. | No. |
| **Resume** | Nothing runs yet. The PC shows **one approval card** listing every step that is left, in full. The task continues only if you approve it. Each step is checked against the screen again before it runs. | **Yes**, through the normal gate, under the same rule (tier) as the original task. |
| **Note for what runs next** | Kept with the running (or paused) task. Jarvis reads it when the current step finishes. It changes no step you already approved. | No — it approves nothing. |
| **Note on an approval card** | Kept with that one card. The card does not change. When you answer the card (yes or no), Jarvis reads your note together with your answer. To have Jarvis plan something different, deny the card. | No — it approves and denies nothing. |

Every press is written to the audit log (`task.stop`, `task.pause`,
`task.resume_asked`, `task.note`, `task.amend` ...) with which device it came
from. The audit line records a note's **length, never its words**.

**One thing the design document said differently, on purpose.** The design
(`docs/AUTONOMY-PROPOSALS.md` §3b) imagined that a note on a card would make
Jarvis re-plan and replace the card's options. Jarvis cannot do that today —
the gate waits on a card and there is nothing that rewrites a waiting card —
and inventing it would mean a card whose contents change after you started
reading it. So the note travels with your answer instead, and **Deny is how
you ask for a different plan.** Both apps now say exactly that.

**Which tasks can be paused.** The three multi-step tools:
`control_computer`, `control_phone` and `browser_control`. They already check
before every step; `jarvis_agent.py` now hands them the pause/stop check too
(the `checkpoint` that `jarvis_task_control.py` was written for and nothing was
passing). A plain answer, a calculator call or a one-shot tool has no steps to
pause between.

**Rule 4 (stale link).** Stop, Pause and notes work even on a stale link: the
moment you most need Stop is when the link is misbehaving. **Resume** is held
on a stale link, on both apps, because it is the one that makes work go again.

**Limits, said plainly.**
- One paused task at a time. A second pause replaces the first.
- A paused task is forgotten after an hour — its picture of the screen is too
  old by then. Ask Jarvis again instead.
- Nothing here survives restarting the backend. A paused task is lost on a
  restart (the Resume button disappears; nothing runs).
- After a resumed task finishes, the chat that started it is already over, so
  Jarvis does not tell you in chat. `GET /api/task` shows what it did.
- Notes are cut at 1,000 characters; at most 64 card notes are kept.

## What it changes

- `jarvis_hud.py` (the patch): the routes `POST /api/task/pause`,
  `/api/task/resume`, `/api/task/stop`, `/api/task/note`,
  `/api/pending/<id>/amend`, and `GET /api/task`. All behind the same origin
  check and token as every other private route. They only check who is asking
  and pass the request on — every rule lives in `jarvis_task_control.py`.
  It also puts a small wrapper in front of `_activity()`: while a task is
  paused, "idle" is reported as "paused", which is what makes the Resume
  button appear.
- `jarvis_task_control.py` (copy it in; the script does): the rules above.
- `jarvis_agent.py` (copy it in; the script does): registers each running
  multi-step task, passes the pause/stop check, keeps the rest of a paused
  plan, and hands notes to the model.

**Where it goes in the stack:** last, after `speed-record.patch`. Its context
lines are `extraction-wiring`'s (`_activity`), `feedback`'s (the end of the
`/api/feedback/mark` block) and `memory-intake`'s (the memory-route tuple).

**Not checked against your real `jarvis_hud.py`** — nobody here has it. The
patch was checked with `git apply` (on, off, and back to the same bytes) on a
stand-in built from what the earlier patches wrote. `apply-patches.ps1`'s
rehearsal on a copy of your real files is the real test, and it changes
nothing if the patch does not fit.

## Test it

```
python backend\test_cloud_one_turn.py
```

Runs the patch's own lines on a request carrying a private earlier question
(only the newest question comes out), checks the local lane is untouched,
rehearses the patch with `git apply` against what the earlier patches wrote,
and - with `JARVIS_BACKEND` set - checks `_open` in your real file.
python backend\test_task_control.py
```

103 checks, no network and no real gate: a fake plan module and a fake gate
stand in. The ones that matter most: Resume runs **nothing** until the gate
allows it, and then runs exactly the steps that were left, from the original
plan object; a denied, timed-out or broken gate runs nothing; a Stop pressed
while the resume card waits beats approving it; a card note reaches the model
whether the card was approved or denied; and the audit log never holds a
note's words.


---

# `note-capture.patch` and `jarvis_note_capture.py` — notes that really get saved

**What was wrong.** On the desktop, `#log`, `#joplin`, Alt+Shift+N and the
widget's #log / #jop capture all asked the *model* to call two tools,
`append_logseq_journal` and `create_joplin_note`. Neither tool existed
anywhere. So **no note was ever filed** — and the widget could only say
"Sent", because it had no way to know.

**What this adds, in plain words.**

1. **A route for your own words:** `POST /api/notes/capture` with
   `{"target": "logseq" | "joplin", "text": "..."}`. No model is involved at
   all — you typed it, so it is filed as you typed it. The desktop's #log /
   #joplin / quick note / widget capture now use this.
2. **The two tools, for real,** in `jarvis_agent.py`, for when you ask Jarvis
   in chat ("add to my journal that ..."). Same code, same checks. Like every
   tool they are only offered if `[tools].enabled` in your config names them.
3. **Honest answers.** The desktop now says one of: *Filed in Logseq,
   journals/2026_09_23.md* (only after the PC read the note back), *Waiting
   for your approval…*, or *Not filed* and why (you said no, nobody answered,
   no Logseq folder, no Joplin token, Joplin not running...).

**Permission, the project's one way.** Every write goes through
`jarvis_gate` under the action names **your own `jarvis-framework.toml`
already lists**: `append_logseq_journal` and `create_joplin_note`. That file
decides whether you see a card first. **As shipped, it says `auto` for the
Logseq journal and `notify` for a new Joplin note — so, as shipped, no card
is shown for either.** That is your file's existing choice ("An agent that
must ask permission to write its own log will not keep a log"), not
something this patch decided. To be asked every time, change those two lines
to `"ask"`. Nothing here is a standing grant of its own.

**What it will never do.**
- **Overwrite.** Logseq: your journal file is only ever *added to* at the end
  (opened in append mode — it cannot remove anything), and made only if it is
  not there yet. Joplin: always a *new* note; no note is edited; a notebook is
  looked up by name and never created.
- **Leave this PC.** Logseq is a file on your disk. Joplin is its own service
  on this PC; if the address is anything but this PC, it refuses.
- **Show or save your Joplin token.** It is read from the environment only at
  the moment it is sent, only to Joplin on this PC, and it is scrubbed out of
  every error message.

**Where things are.**
- Logseq graph folder: `JARVIS_LOGSEQ_GRAPH`, else `[notes.logseq]
  graph_directory` in jarvis-framework.toml, else `<config dir>\notes`. The
  folder must already exist and look like a Logseq graph. Today's page is
  `journals\YYYY_MM_DD.md` — Logseq's default. If you changed Logseq's journal
  file name format, this will not follow it (say so and it can learn to).
- Joplin token: `JARVIS_JOPLIN_TOKEN` (the same one note search uses), else
  the variable named by `[notes.joplin] token_env`. Address:
  `JARVIS_JOPLIN_URL`, else `http://127.0.0.1:<port from the config, 41184>`.

## A token leak, fixed in `jarvis_notes.py` too

The 2026-09-23 audit reproduced it: with `JARVIS_JOPLIN_URL` set without its
`http://`, every note search failed with an error that **contained the Joplin
token** (urllib quotes the whole address, and Joplin's token is part of the
address). That error went back to the model, onto the screen and into logs.
`jarvis_notes.py` now scrubs the token and the Obsidian key out of every error,
in every spelling. The script now copies `jarvis_notes.py` in too, so the fix
reaches your backend.

## What it changes

- `jarvis_hud.py`: `POST /api/notes/capture` and `GET /api/notes/capture?id=`,
  right after `task-control.patch`'s routes (that is its context, so it goes
  after it). Same origin check and token as every private route.
- `jarvis_gate.py`: the risk lines for the two actions (both "stays on this
  PC", both undoable by deleting what was added), and the two tool names in
  `_TOOL_ACTIONS`. Context: `ui-control-wiring.patch`'s lines.
- `jarvis_note_capture.py`, `jarvis_notes.py`, `jarvis_agent.py`: copy them in
  (the script does).

**Not checked against your real files** — nobody here has them, and there
is no Logseq or Joplin here either. Logseq was tested against a folder shaped
like a graph; Joplin against a stand-in that answers like Joplin's documented
API. The first real run is the real test.

## Test it

```
python backend\test_note_capture.py
```

70 checks. The ones that matter most: nothing is written without an allowed
verdict (denied, timed out and a broken gate all write nothing and say why);
the earlier text of a journal is byte-for-byte intact after an append; only
`POST /notes` is ever sent to Joplin; the token is in no plan, card, result or
error — including the exact `ValueError` the audit found in `jarvis_notes.py`.


---

# `power-mode.patch` and `jarvis_power_switch.py` — the Active / Quiet / Standby switch

**What was wrong.** Both apps showed the power mode, and the desktop's FAQ
explained Quiet and Standby — but nothing anywhere could change it. The phone
tile and the desktop tray both said so in their own comments.
`jarvis_power.set_mode()` existed with no route to it.

**What this adds.** `POST /api/power` with `{"mode": "active" | "quiet" |
"standby"}`. The desktop tray gets a **Change power mode** submenu; the
phone's **Mind** screen gets Active / Quiet / Standby buttons under the Power
line.

- **Quiet**: Jarvis still answers you, but starts nothing on its own.
- **Standby**: also unloads the model from the graphics card (what the FAQ
  already promised), so the next answer takes 5–15 seconds. Refused while a
  multi-step task is running — stop it first.
- **Active**: back to normal.

**Does it ask first?** It goes through the gate as `power_manage`, and your
`jarvis-framework.toml` sets that to `auto`, with its own reason: "Putting
Jarvis into quiet/standby, or waking it, is the safe direction either way, so
it does not interrupt you for a yes." So by default, no card — both
directions, because your file says both are safe. Set it to `"ask"` there and
a card appears. Waking (Active) is held on a stale link on both apps (rule 4);
going quieter is not. The rules that put Jarvis under by themselves (quiet
hours, the idle timer) are **not** reachable from here.

**The mode on screen only changes when the PC says so** (the `power` event),
never on the click.

**Not checked against your real files.** The route was rehearsed on a
stand-in `jarvis_hud.py`; the test uses this repo's rebuilt `jarvis_power.py`.
Unloading uses `jarvis_models.resident_models()` / `unload()` if your copy has
them — if not, the answer says the model stayed loaded.

## Test it

```
python backend\test_power_switch.py
```

26 checks: the mode changes only on an allowed verdict; denied, timed out and a
broken gate change nothing; standby unloads and says which model; standby is
refused while a task runs; only the three modes are accepted; the patch applies
after `note-capture.patch` and reverts.

<!-- ===== task controls, notes, power (2026-09-23) - end ===== -->

# Voice that works: speech-to-text, a spoken voice, and "hey Jarvis"

Added 2026-09-23. **What was wrong, in plain words:**

1. **Push-to-talk could never be turned into words.** The shipped settings
   file said `stt_engine = "faster-whisper"`, an engine Jarvis has no code
   for. `jarvis_speech.py` only speaks sherpa-onnx, so it refused every clip
   and the phone's talk button stayed hidden. The default is now
   `"sherpa-onnx"`, and step 3 below changes that line in your own settings
   file for you.
2. **Jarvis had no voice.** No model files were on the PC.
3. **Turning on "hey Jarvis" happened with no approval card**, although
   `docs/JARVIS-API.md` said it raised one. It now raises one.
4. **The desktop's "automatic listening" sent everything it heard to be
   transcribed**, cut up by a plain loudness trigger, not the Silero VAD the
   architecture names. It now listens for "hey Jarvis" only, and the PC runs
   Silero VAD on every clip.
5. **Nothing listened for "hey Jarvis" anywhere.** Now the phone and the
   desktop both can - off by default, and only after you approve a card.

## Install the voice models (one time)

Paste each line into PowerShell, one at a time, in this order. Each download
is checked against a SHA-256 measured from the real file; a wrong file is
deleted and nothing is installed. Everything lands in the `voice-models`
folder inside Jarvis's settings folder (normally
`C:\Users\pcadmin\.openjarvis\voice-models`). **About 850 MB in all.** None of
it uses the graphics card.

**1. The two Python packages** (sherpa-onnx runs speech-to-text, the voice
and Silero VAD; onnxruntime runs the wake word):

```powershell
python -m pip install --upgrade sherpa-onnx onnxruntime; python -c "import sherpa_onnx, onnxruntime; print('OK - sherpa-onnx', sherpa_onnx.__version__, 'and onnxruntime', onnxruntime.__version__, 'are installed')"
```

**2. Speech-to-text** - NVIDIA's Parakeet TDT 0.6B v2 (English, with
punctuation), 480 MB, into `voice-models\stt`:

```powershell
$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $base = if ($env:OPENJARVIS_CONFIG_DIR) { $env:OPENJARVIS_CONFIG_DIR } elseif ($env:JARVIS_CONFIG_DIR) { $env:JARVIS_CONFIG_DIR } else { "$env:USERPROFILE\.openjarvis" }; $m = Join-Path $base 'voice-models'; New-Item -ItemType Directory -Force -Path $m | Out-Null; $f = Join-Path $env:TEMP 'jarvis-stt.tar.bz2'; Write-Host 'Downloading speech-to-text (480 MB)...'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2' -OutFile $f; if ((Get-FileHash $f -Algorithm SHA256).Hash -ne '157C157BC51155E03E37D2466522A3A737DD9C72BB25F36EB18912964161E1AD') { Remove-Item $f; Write-Host 'That is not the expected file, so nothing was installed. Run this line again.' -ForegroundColor Red } else { tar -xjf $f -C $m; Remove-Item $f; $d = Join-Path $m 'stt'; if (Test-Path $d) { Rename-Item $d ('stt-old-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }; Rename-Item (Join-Path $m 'sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8') 'stt'; Write-Host "OK - speech-to-text is in $d" -ForegroundColor Green }
```

**3. Tell Jarvis to use it.** This changes the one `stt_engine` line in your
`jarvis-framework.toml` from `"faster-whisper"` to `"sherpa-onnx"`, keeping a
copy of the old file beside it (`jarvis-framework.toml.before-voice`):

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $t = python -c "import jarvis_framework as f; print(f.config_path() or '')"; if (-not $t) { Write-Host 'Could not find jarvis-framework.toml (or jarvis_framework.py is not in this folder). Nothing was changed.' -ForegroundColor Red } else { $s = [IO.File]::ReadAllText($t); $rx = [regex]'(?m)^([ \t]*)stt_engine[ \t]*=[^\r\n]*'; if ($s -match '(?m)^[ \t]*stt_engine[ \t]*=[ \t]*"sherpa-onnx"') { Write-Host "Already set: $t says stt_engine = sherpa-onnx" -ForegroundColor Green } elseif ($rx.IsMatch($s)) { Copy-Item $t "$t.before-voice" -Force; $s = $rx.Replace($s, '${1}stt_engine = "sherpa-onnx"', 1); [IO.File]::WriteAllText($t, $s, (New-Object Text.UTF8Encoding $false)); Write-Host "OK - $t now says stt_engine = sherpa-onnx (the old copy is $t.before-voice)" -ForegroundColor Green } else { Write-Host "$t has no stt_engine line. Add stt_engine = `"sherpa-onnx`" under [voice]." -ForegroundColor Yellow } }
```

**4. Jarvis's voice** - Kokoro v0.19 (English, 11 voices), 320 MB, into
`voice-models\tts`:

```powershell
$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $base = if ($env:OPENJARVIS_CONFIG_DIR) { $env:OPENJARVIS_CONFIG_DIR } elseif ($env:JARVIS_CONFIG_DIR) { $env:JARVIS_CONFIG_DIR } else { "$env:USERPROFILE\.openjarvis" }; $m = Join-Path $base 'voice-models'; New-Item -ItemType Directory -Force -Path $m | Out-Null; $f = Join-Path $env:TEMP 'jarvis-tts.tar.bz2'; Write-Host 'Downloading the voice (320 MB)...'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-en-v0_19.tar.bz2' -OutFile $f; if ((Get-FileHash $f -Algorithm SHA256).Hash -ne '912804855A04745FA77A30BE545B3F9A5D15C4D66DB00B88CBCD4921DF605AC7') { Remove-Item $f; Write-Host 'That is not the expected file, so nothing was installed. Run this line again.' -ForegroundColor Red } else { tar -xjf $f -C $m; Remove-Item $f; $d = Join-Path $m 'tts'; if (Test-Path $d) { Rename-Item $d ('tts-old-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }; Rename-Item (Join-Path $m 'kokoro-en-v0_19') 'tts'; Write-Host "OK - the voice is in $d" -ForegroundColor Green }
```

**5. The speech detector (Silero VAD) and the "hey Jarvis" model** - four
small files, 4 MB, into `voice-models\vad` and `voice-models\wakeword`:

```powershell
$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $base = if ($env:OPENJARVIS_CONFIG_DIR) { $env:OPENJARVIS_CONFIG_DIR } elseif ($env:JARVIS_CONFIG_DIR) { $env:JARVIS_CONFIG_DIR } else { "$env:USERPROFILE\.openjarvis" }; $ow = 'https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/'; $files = @( @('vad', 'silero_vad.onnx', 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx', '9E2449E1087496D8D4CABA907F23E0BD3F78D91FA552479BB9C23AC09CBB1FD6'), @('wakeword', 'melspectrogram.onnx', ($ow + 'melspectrogram.onnx'), 'BA2B0E0F8B7B875369A2C89CB13360FF53BAC436F2895CCED9F479FA65EB176F'), @('wakeword', 'embedding_model.onnx', ($ow + 'embedding_model.onnx'), '70D164290C1D095D1D4EE149BC5E00543250A7316B59F31D056CFF7BD3075C1F'), @('wakeword', 'hey_jarvis_v0.1.onnx', ($ow + 'hey_jarvis_v0.1.onnx'), '94A13CFE60075B132F6A472E7E462E8123EE70861BC3FB58434A73712EE0D2CB') ); $ok = $true; foreach ($x in $files) { $d = Join-Path (Join-Path $base 'voice-models') $x[0]; New-Item -ItemType Directory -Force -Path $d | Out-Null; $p = Join-Path $d $x[1]; Invoke-WebRequest -UseBasicParsing -Uri $x[2] -OutFile $p; if ((Get-FileHash $p -Algorithm SHA256).Hash -ne $x[3]) { Remove-Item $p; $ok = $false; Write-Host "$($x[1]) is not the expected file - deleted it." -ForegroundColor Red } }; if ($ok) { Write-Host "OK - the speech detector and the wake word are in $base\voice-models" -ForegroundColor Green } else { Write-Host 'Run this line again.' -ForegroundColor Red }
```

**6. Put the new code on the PC**, from this repository's folder. It copies
in `jarvis_speech.py` and the new `jarvis_wakeword.py` (backing up older
copies first):

```powershell
.\scripts\apply-patches.ps1
```

**7. Check it works.** Jarvis speaks a sentence with its new voice, listens
for "hey Jarvis" in it, and writes down what it heard. It saves the sentence
it spoke to `C:\Users\pcadmin\.openjarvis\voice\self-test.wav` so you can
play it. Nothing is sent anywhere:

```powershell
cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; python jarvis_speech.py --test
```

Look for `Wake word: HEARD` and `heard 'Hey Jarvis, what is the weather like
tomorrow?'`. Then **restart Jarvis**. The phone's talk button appears once
your voice is trained (Checks -> Your voice) - it was hidden only because
speech-to-text was missing.

*Optional:* Jarvis's voice defaults to an American female voice (number 0).
For a British male voice add `tts_speaker_id = 9` under `[voice]` in
`jarvis-framework.toml` (10 is another; 5 and 6 are American male).

## "Hey Jarvis"

**How to turn it on.** Two steps, on purpose:

1. **Allow it on the PC.** On the phone: Checks -> *Wake word* -> **Turn on
   "hey Jarvis"**. Or on the desktop: the round button next to the microphone
   in the Jarvis bar. Either one raises **one approval card**. Nothing changes
   until you approve it (tier `ask` for `change_own_config`; checked before
   the card and again on your answer).
2. **Switch listening on where you want it.** On the phone: **Listen on this
   phone** (same card). On the desktop: the same round button again, after
   approving. Each stays on until you turn it off; the phone's also stops when
   the phone restarts or Android closes Jarvis. Turning the wake word OFF is
   immediate, never a card.

**What happens, and where.**

| | where it runs | what it sends, and where |
|---|---|---|
| waiting for "hey Jarvis" (phone) | on the phone: openWakeWord's "hey jarvis" model through ONNX Runtime | **nothing**. The microphone is open; Android shows its microphone dot and a notification the whole time |
| waiting for "hey Jarvis" (desktop) | the desktop app cuts the room's sound into sentences by loudness; the Jarvis server **on the same PC** runs the model on each | each sentence goes to the PC's own Jarvis over loopback (`127.0.0.1`) and is dropped there unless it holds "hey Jarvis" - not voice-checked, not transcribed, not kept. The desktop refuses to listen at all if its server address is not this PC |
| it heard "hey Jarvis" | | the phone sends that sentence (from 2 s before the phrase to your pause) to your PC over Tailscale. **Never anywhere else** |
| on the PC | `jarvis_speech.hear()`: Silero VAD -> "hey Jarvis" checked again -> your voice checked -> speech-to-text -> the sentence must start with "hey Jarvis" | the words go to Jarvis like typed text. "Hey Jarvis." on its own opens an 8-second window for the next sentence |

No company's servers are involved at any point, and no API key is needed.

**Why openWakeWord, not Porcupine or sherpa-onnx's keyword spotter.**
`jarvis-framework.toml` had already named openWakeWord and its `hey_jarvis`
model (`wake_phrase`, `wake_threshold = 0.5`), and said why Picovoice's
Porcupine was out: its free tier ended in June 2026 and it checks its licence
key over the internet. `docs/WAKE-WORD.md` had also chosen it. It has a
model trained for exactly "hey jarvis", and it runs on ONNX Runtime, which
the phone can get from Maven Central (the only place its build fetches from)
and the PC from pip. sherpa-onnx's open-vocabulary keyword spotter was
measured on the same clips (below): fewer false alarms, more misses - but
there is no sherpa-onnx library for Android on Maven Central or Google's
repository, so the phone could not use it without committing a 40 MB binary.
The models are CC BY-NC-SA 4.0 (non-commercial; recorded in
`THIRD-PARTY-NOTICES.txt`), which rule 5 already allows for.

## What was measured here, and what was not

Checked in the dev container (Linux, 4 CPU cores, no GPU), with sherpa-onnx
1.13.8 and onnxruntime 1.30.0, against the real downloads above. The test
speech was **synthesised by Kokoro** in its 11 voices - there is no recording
of a real person here. Ten sentences per voice, 110 clips: four start with
"hey Jarvis", six do not (including "Hey Jason, ...", "Put the jar of jam
...", and "... the computer was called Jarvis").

- **Speech-to-text** (Parakeet, 2 threads): 109 of the 110 sentences came
  back word for word, all 44 "hey Jarvis" ones included (`'Hey Jarvis, what
  time is it?'`); the one miss was "shelf" heard as "shell". About 0.09x real
  time: 0.3 s for a 3 s clip. SenseVoice and Moonshine were also tried:
  faster, but they wrote "Javis", "Pig Jarvis" and "Hage-Arvis".
- **Voice** (Kokoro fp32, 2 threads): `say()` produced a 24 kHz WAV, 3.4 s of
  speech in about 1.2-3 s. (The int8 Kokoro was about 2.5x slower on this CPU,
  so the full one is the recommended download.)
- **Wake word**, openWakeWord at the shipped threshold 0.5: **44 of 44** "hey
  Jarvis" clips heard, **8 of 66** others wrongly heard - all eight are "...
  the computer was called Jarvis". Each of those is then dropped on the PC,
  because the transcript does not start with "hey Jarvis". The phone's Kotlin
  spotter, run on a desktop JVM with the same models, scored within 0.0005 of
  the PC's on every clip. sherpa-onnx's spotter for comparison: 39 of 44
  heard, 0 of 66 wrong.
- **End to end**, the phone's real `WakeWordService` + `VoiceSession` +
  `JarvisApi` on a desktop JVM with a fake microphone, talking over HTTP to
  the real `jarvis_speech.hear()`: "hey Jarvis, what time is it?" reached the
  chat as `what time is it?`; "Hey Jason ..." and "Put the jar of jam ..."
  sent nothing; "hey Jarvis." + a pause + a sentence reached the chat as the
  sentence; the "called Jarvis" false alarm was sent to the PC and dropped
  there.

**Found, and worth knowing: the voice check let other synthetic voices
through.** With a voice print made from three clips of one Kokoro voice, the
other ten Kokoro voices passed the owner check on 30-70% of their clips
(threshold 0.35). Kokoro's voices all come from one model and are more alike
than real people, so this is probably pessimistic - but it has not been tried
with a second real person. Please have someone else try the talk button once
after training; if they get through, raise `threshold` under `[voice]` (0.5
is a reasonable next step) and train again.

**Not checked:** anything on Windows or a phone - these PowerShell lines
(PowerShell could not be run by the session that wrote them; Windows 10/11's
built-in `tar` is assumed to unpack `.tar.bz2`), the pip install on Windows,
a real microphone, the phone's battery use while listening, and how often
"hey Jarvis" fires by mistake over hours of real conversation or TV
(openWakeWord's authors report under 0.5 per hour for their models). Also
not visible here: the route in `jarvis_hud.py` that calls
`set_wake_enabled()`. For ON it now receives `{"ok": true, "pending": true}`
(a card is up) where it used to get `{"ok": true, "enabled": true}`, and it
is assumed to pass that on as before.

## Test it

```powershell
python backend\test_wakeword.py; python backend\test_speech.py; python backend\test_voice_contract.py
```

`test_wakeword.py`: the order in `hear()` (each later step made to fail if it
is reached), the follow-up window, every way the approval card can end, the
transcript check, 48 kHz audio, and that the spotter module writes and logs
nothing. To also run the real models once they are installed, set
`$env:JARVIS_TEST_VOICE_MODELS = "$env:USERPROFILE\.openjarvis\voice-models"`
first.
