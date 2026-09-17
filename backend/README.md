# Backend patches

> Architecture, invariants and the permission model every capability must use:
> [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Read that first; this file
> is the detail.


Twenty-two patches against the Jarvis backend, each with an executable test.

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
above for the secret-scan and denial-constraint features.

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

**That "once" is per process, not per client.** `reminder_card()` marks
itself seen the moment it is *called*, and now two clients call it: whichever
of the desktop or the phone polls `/api/memory/pending` first on a given day
gets the card, and the other does not, until tomorrow. Accepted rather than
rewriting `jarvis_sleep.py`'s own tested once-a-day contract for two callers
it was never asked to serve.

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
whatever `_local_llm` is (Ollama, on this machine, never a cloud lane), and
nothing becomes a fact without a human accepting it in the Brain window.

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
