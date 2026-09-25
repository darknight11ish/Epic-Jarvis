# Jarvis: how the pieces fit

This is the source of truth. Every other document in `docs/` is a detail of
something stated here; where they disagree, this wins and the other is stale.

Read this before adding anything. The characteristic defect of this codebase
has been capability with no call site — `propose()` with zero callers, a Pump
nothing constructed, a `retire()` nobody calls, an event kind no client
handles. Almost every one of those started as a good idea built beside the
system instead of into it.

---

## 1. What it is

A local-first assistant for one person, on one Windows 11 workstation, with an
Android companion reached over Tailscale. A Python HTTP server does the work;
a Tauri 2 shell (Rust + WebView2) is the desktop face; the model runs in Ollama
on the machine's own GPU.

Non-commercial. One owner. That shapes everything: there is no multi-tenancy,
no account system, no scale problem — and correspondingly no excuse for a
control that acts on more than one thing at a time.

---

## 2. The invariants

These are not preferences. Anything that violates one is wrong, however well
it works.

1. **Everything private stays on the local model.** Cloud lanes exist; what
   may reach them is bounded and enforced in code, not by convention.
2. **No public tunnel, ever.** Reachability is Tailscale. A non-loopback bind
   with no `HUD_TOKEN` refuses to start — `SystemExit(2)`, not a warning.
3. **No auto-approve anywhere, and no approve-all control anywhere.** One
   action, one decision. Do not build one.

   This invariant has been violated once, in the gate itself. `confirm_auto()`
   returned True for tier `ask` with nobody asked, behind a `--auto-approve`
   flag, with a docstring explaining why that was reasonable. It had no
   callers, which is the only reason it never granted anything. Fixed by
   `no-auto-approve.patch`, and now asserted by
   `test_gate_outcome.t_there_is_still_no_approve_all`, which reads the source
   with comments and docstrings stripped — **because this rule is a claim
   about code and a claim about code goes stale or is wrong from the start.**
   That one was wrong from the start.
4. **An item carrying `raised` never belongs in a group that can be actioned
   quickly**, whatever its `risk.swipe_ok` says.
5. **`POST /api/digest/seen` marks read and approves nothing.**
6. **Nothing is claimed that is not true.** A promise the product cannot keep
   is worse than no promise, because the owner stops checking. Several fixes
   in this repo are nothing but a sentence being made true.

### What "no approve-all" actually means

It forbids a control that grants permission for **future, unnamed** actions.

It does not forbid one decision about one bounded set of things, every one of
them shown in full. Approving a shell command with eight arguments is one
decision. Approving eight enumerated, printed search queries for one audit is
one decision. Approving "web access" as a standing setting is not — that is
the thing this rule exists to prevent.

---

## 3. The permission model — one mechanism, no exceptions

**Every capability that acts on the world or leaves the machine uses the same
four steps.** If a new feature needs its own approval flow, the design is
wrong.

```
plan()      Work out what would have to be done. Touch nothing. Open no
            socket. Return a plan object.

describe()  Render the plan for a person: every command, every URL, in FULL.
            No summarising — summarising a request on the card that
            authorises it defeats the card. Plus, always, what refusing
            costs. A permission request that omits that is a nudge, not a
            question.

<human>     jarvis_gate. One decision, recorded, with prompt and detail
            NULLed on decision so the queue does not become an unredacted
            twin of the audit log.

run()       Executes an approved plan. `approved` has no default of True.
            A module that can act must not be one call away from acting by
            accident.
```

`backend/jarvis_research.py` is the reference implementation. Its tests patch
`socket.connect` to raise, so "opens no socket" is a fact rather than a
comment. Copy that shape.

In the chat tool loop (`jarvis_agent.py`) a model's tool request is checked
against the tool's schema **before** `plan()`: a broken one never reaches a
card. Tool output is cleaned of chat markers and labelled as data before the
model reads it, and a card proposed after outside text says so under "What
shaped this request:" - which tools were read, and which values came from
that text, not the owner. The card still shows the plan in full; this only
adds to it. One thing there does change which tools ask (the owner's
decision of 2026-09-24, after the safety research): in a turn shaped by
outside text - a reading tool ran, the conversation is tainted, or the
newest message was pasted, shared or from the clipboard - a note write
(Obsidian, Logseq, Joplin) is put to the same gate as
`write_notes_after_outside_text`, tier `ask`, and runs only on a person's
yes, like `NEEDS_A_PERSON`. Not a second approval path: the same gate, the
same card, one more line on it saying why. `backend/README.md`, "Outside
text in the tool loop".

### Two rules that are easy to get wrong

**`allowed` is not "a human decided".** `jarvis_gate.check()` returns
`allowed=True` on tier `notify` — reason: *"tier is notify; you were told
after"* — and on `auto` with nobody in the loop. Anything that needs a person
must assert the tier is `ask` or `never`, not trust the boolean.
`skill-notes.patch` shows the pattern.

**Redaction is per-destination.** `jarvis_gate._redact` obeys
`[logging].redact_private_content_in_logs`, which is correct for an on-disk
log and wrong for anything that leaves. A push to a public broker gets
`_safe_detail` instead: keys only, unconditional. Do not reuse a redactor
across destinations with different threat models.

### The notification contract — `notice`

A waiting approval has to be readable on a phone without any of the payload
leaving the machine's control. That is not done by redacting the row. It is
done by **generating** the text from tables we wrote.

`jarvis_gate.notice_for(item)` reads exactly two things off an approval row —
`action`, and whether `raised` is truthy. It reads no `detail`, no `prompt`,
and nothing inside `raised`. Every word it returns comes from `_RISK` and from
the action name. It is attached to every `/api/pending` row as `notice`, and
allowed through the SSE doorbell by name.

```
title        "Jarvis wants to send email"   from the action name
body         why it matters, that something tried to hurry you if `raised`
             is set, and that nothing has happened yet
weight       "heavy" | "normal"
deny_ok      true    — always
approve_ok   false   — always
```

**Three rules for any client reading this.**

1. **`weight: "heavy"` interrupts; `"normal"` waits to be found.** Heavy is
   earned by any one of three things: the action cannot be undone, it leaves
   this machine, or outside text pushed the tier up. Three named reasons a
   person can argue with, not a score nobody can.

2. **`deny_ok` and `approve_ok` are not symmetric, and a client does not get
   to decide that for itself.** Refusing something you have not fully read
   costs a retry. Approving something you have not fully read is the failure
   this whole model exists to prevent — and a notification is the worst place
   for it: glanceable, often on a lock screen, one thumb, no context. So
   **Deny may be a notification action. Approve may not.** Approving means
   opening the app. This is not an approve-all — there is none and there will
   be none — it is the weaker point that a one-tap approve on a lock screen
   is, on its own, worth refusing.

3. **Do not build the notification text yourself.** The reason this function
   exists rather than each client assembling a string is that three separate
   leaks in this project happened at the next call site along, where the rule
   was stated in one place and not enforced in the other. A client that
   composes its own summary from `detail` has reopened the hole, on the one
   surface where it is least recoverable.

`raised` travels as a **boolean**, here as everywhere. `raised.quote` is text
an attacker wrote to make a reader hurry; its home is inside the app, in
quotation marks, next to its source, where the point is to slow the reader
down. The notice *says* something tried to rush you and never quotes it — that
it tried is the fact that changes the decision, its words are not.

*Known limitation, half-closed:* `tauri-plugin-notification` accepts
`action_type_id` on the desktop builder but never reads it — notification
actions are mobile-only in that plugin, so a Deny button could not go
through it. `jarvis-desktop/src-tauri/src/winrt_toast.rs` goes around the
plugin instead: a real WinRT toast, built and shown through
`windows::UI::Notifications` directly, with a Deny button whose click
relaunches the app (`activationType="foreground"`, not a background COM
activator — see that module's own doc for why) carrying the approval id,
answered through the same `decide_approval` the in-app card uses. Compiles
and passes `cargo clippy -D warnings` against the Windows target; **not
watched fire on a real Windows machine**, since this depends on an AUMID
association with the installer's own Start Menu shortcut that only a real
run can confirm. Until that is watched work, treat it as believed-correct,
not confirmed — and note the one real gap even once it does: unlike
Android's `decideDetached`, this still briefly activates the process on
click rather than never touching it, because a true background action
needs registry/COM plumbing this session could not add with confidence.

---

## 4. The egress boundary

Three lanes leave the machine. Nothing else may.

| lane | what may go | enforced by |
|---|---|---|
| **cloud model** | user-role turns only - and, with `cloud-one-turn.patch`, only the **newest** one, because the clients now send the conversation so far | a role filter, re-derived on **every** hop of the degrade loop; the newest-turn cut in `_open` |
| **ntfy push** | text generated from our own tables, never payload, never while tainted | `notice_for` (`_safe_detail` where there is no action name) + `taint_active()` |
| **research** | enumerated search terms, per approved plan | `jarvis_research.plan/run` |

The cloud filter deserves a note because it was broken in the least obvious
way: it ran once, above the degrade loop, and the loop could go cloud → local
→ cloud. It now re-derives from the lane it is **about to call**. The loop's
comment claims "downward only" — that is a contract with `jarvis_router` which
the loop never checked, so the fix does not depend on it holding.

The **local model is also egress** if `OLLAMA_URL` does not point at this
machine. The learner asserts loopback before it runs; anything else that talks
to Ollama in the background must do the same.

---

## 5. Memory — one model

```
facts (bi-temporal)  TWO axes, and they are not the same question.
                       valid_from / valid_to  when the fact was TRUE
                       created / retired_at   when WE believed it
                     Nothing is deleted; a superseded fact is retired and the
                     new one records what it replaced. "What is no longer
                     true" is load-bearing, and so is "what did you think you
                     knew in June" - a proposal accepted three weeks late has
                     both dates and one column cannot hold them.

facts_fts   FTS5, words
facts_vec   sqlite-vec, meaning
            fused by reciprocal rank fusion, with a vector distance floor
            and (2026-09-24) a word-share floor on the FTS list

proposals   the review queue. Extraction writes here. NOTHING reaches `facts`
            without decide(id, accept) or decide_keep_both(id) — one integer
            id, one decision. keep_both keeps the new fact AND leaves the old
            one current; it retires nothing. The one other door is
            accept_auto(id) (automatic learning, below): one id at a time,
            claimed like decide(), never a correction.
```

**The one exception to "nothing is deleted": "Erase the words"** (the
owner's decision, 2026-09-24; `MemoryStore.erase()`, `memory-erase.patch`,
docs/JARVIS-API.md §6 `/api/memory/erase`). It destroys the WORDS of one
fact and nothing else: `text` becomes the marker `[erased]`, its `facts_fts`
row and `facts_vec` row go, meta keeps only dates, ids and where it came
from, the copies of its words in `proposals` go, and the file is cleaned
(word index compacted, `secure_delete`, `memory.db-wal` checkpointed and
truncated) so the old bytes are really gone, not just unreachable. The row
stays - id, `created`, `valid_from`, `valid_to`, `retired_at`, `retired_by`,
`source` - with `erased_at` set, so the history and "what did you know in
June" still show that something was there. A current fact is retired as
Forget retires it; a forgotten one keeps its dates. No card (Forget has
none), a confirm in both apps, held on a stale link. Nothing may ever
recall, re-embed or show an erased fact's text: `backfill_embeddings()`
skips it, and the apps draw "Erased on <date>" from `erased_at`.

**Three tables are welded to one local rowid.** `facts` is
`id INTEGER PRIMARY KEY`, `facts_fts` uses `content_rowid='id'`, and
`facts_vec` is `vec0(fact_id INTEGER PRIMARY KEY)`. Any proposal needing
globally-unique ids — sync, sharding, cross-device dedup — is a three-table
migration plus a full re-embed, and `vec0` is a virtual table most extensions
cannot touch. Cost it honestly or design around it.

**The distance floor is inert on first boot.** It sits behind
`self.embedder.semantic`, and until fastembed finishes downloading the
embedder is `HashEmbedder` with `semantic=False`. Until 2026-09-24, on day
one the tail *was* padded to `k` on any shared content word ("what is my dog
called?" got the cat, on "called"). The word list now has its own floor:
a hit must match `JARVIS_MEMORY_MIN_WORD_SHARE` (default 0.1) of the
question's words, weighted by rarity, with framing words ("called", "name",
"before", "last year") not counted. `find_one()` - which picks what a
correction retires - passes `word_floor=0` and keeps its own stricter rule.
The default was chosen by `backend/eval_memory.py`, the memory self-test (a
made-up persona on a scratch store, never the owner's), on half its
questions and reported on the other half; `backend/README.md`, "Memory wave
1", has the numbers and the two right answers it costs with words alone.

**Recall can look into the past, and only when asked** (`past-recall.patch`,
`jarvis_past.py`). A chat question about the past - a fixed word check,
English plus the commonest forms in the seven other languages - also
recalls up to three retired facts that match, each labelled "(no longer
true since <date>)"; a date in the question ("in June", "last year") is read
by a fixed parser, never a model. "What did I tell you / believe ..." is
searched on the *transaction* axis (`search(known_at=t)`, the same rule as
`known_at()`); any other past question on the *valid* axis (true during
that window). Every other question gets exactly the current-only search it
always got. A bare month ("remind me in June") is not a past cue.

**"Current" is `valid_to IS NULL OR valid_to > now`, never `valid_to IS
NULL`.** A lease that ends in December is true today. Three places computed
this and one of them got it wrong, directly below a line that got it right.

**Never compress facts or transcripts** with a keep/drop token dropper
(LLMLingua and relatives). They are negation-blind, and this store is
bi-temporal precisely because negation matters. Retrieve less; do not compress
what you retrieve.

### The learner

Runs on one background thread, 45 s after the conversation goes quiet, then
not again for 5 minutes. It reads **user turns only** — the same cut the cloud
lane makes, for the same reason: the assistant turn is a carrier. It restates
injected memory, it quotes tool output, and a Joplin vault read comes back
through it. The vault is kept out of the retrieval corpus on purpose;
extracting facts out of a vault read would undo that one accepted proposal at
a time.

Consequence worth knowing: a turn whose `content` is a list — which is what
the client sends with a screenshot attached — is skipped whole. Safe
direction, deliberate, and the obvious "fix" of flattening content arrays
would immediately admit `tool_result` blocks.

**Who started the turn is the backend's call, never the model's**
(`memory-intake.patch`). `_Learner.offer()` learns only when its caller
passes `origin="owner"`, and the default is not that - so a background job
that forgets learns nothing. Anything the backend writes in the user role
goes through `jarvis_intake.jarvis_turn()`, which records a hash so the turn
is never learned even if a client sends it back as history. Nothing in a
request can mark a turn as the owner's; a marker can only remove one. The
gate's "your no becomes a proposed rule" path calls `propose()` directly and
is unaffected.

### Automatic learning — the owner's own words only

The owner decided on 2026-09-24 that Jarvis learns automatically by default
(`jarvis_auto_learn.py`, `auto-learn.patch`, docs/JARVIS-API.md §19). It is
not an approve-all: the learner still proposes every fact, and a proposal is
saved without a card only when a fixed list of checks passes - source
`conversation` or a colon "Remember:", every turn the learner read seen LIVE
by this PC as typed or very-strictly-verified voice in an untainted
conversation (the live-turn registry `jarvis_chat_log.record_turn()` writes
on every request, history on or off), no sign of pasted or hidden text, every
word of the fact in those turns - and no "not", "used to", "if", relation
word or he/she/they of theirs left out of the fact - never a correction,
nothing sensitive unless the owner allowed it (`jarvis_sensitive.py`: word
lists in eight languages, number and token shapes, any fact about another
person, then the learner's own local model - its "unsure" or no answer is a
card too; and passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses are a card even when
the owner allowed sensitive topics, by the patterns alone,
`jarvis_sensitive.always_asks`), and a local model by address AND name. Anything else is the same
card as before, with the reason on it. Saved facts are `source = "auto"` and
listed in both apps with Forget and "Erase the words"; the `memory_saved` event carries ids only.
Turning either switch ON is an approval card; OFF is immediate. An answer
that uses a sensitive saved fact is kept on screen, not read aloud, unless
the owner turned on the voice setting `sensitive_memory` (X-Jarvis-Route's
`injected_sensitive`, JARVIS-API §16). A "Hey Jarvis" voice turn is trusted
like the talk button by default; with the voice setting `hands_free:
button_only` it is never learned from without a card, and its memory,
sensitive and private answers stay on screen (the speech route records how
each clip started, `source`, with the transcript).

**Jarvis's own words are never the owner's.** Since 2026-09-25 an app sends
the last sentence of a spoken answer the owner cut off (`interrupted` on the
next question, JARVIS-API §17 part 7). It is not learned from: the PC tells
its model about it in a SYSTEM line added only to the request for this PC's
model (`jarvis_agent.with_cut_off_note`), never to the conversation the app
sent, which is all the learner (`jarvis_intake.owner_turns`: user messages,
their `content` only) and chat history read; and `chat-history.patch` takes
the field off before any model or the relay sees the conversation.

### Chat history — a second store, kept apart from memory

`chat-history.db` (`jarvis_chat_log.py`, `chat-history.patch`, 2026-09-24,
docs/JARVIS-API.md §18) keeps what was said to Jarvis, including voice
transcripts, **on by default** (the owner's decision). It is not memory:
nothing in it is recalled into a chat, and it is not a source the learner
reads from on its own. Three things about it are invariants:

- **Encrypted or not kept.** Every piece of text is AES-256-GCM with a key
  in Windows Credential Manager (`Jarvis Backend/chat history key`). No
  key, no `cryptography` package, or a key that does not open the file:
  nothing is recorded and the apps say why. There is no plain-text path.
- **The PC records the live turn, with where its words came from.** Only
  the newest user message of each request (and shared text sent just
  before it), tagged typed / voice / shared / pasted / clipboard /
  picture_caption, `unknown` when untagged. `voice` only when this PC's own
  speech route made those exact words. A conversation that ran a tool is
  marked from that turn on. Automatic learning trusts this - through an
  in-memory registry of the same facts (hashes, never words) that is kept
  even while history is off - instead of the history an app re-sends (the
  memory-safety audit).
- **Turning it back on is a card; off is immediate. No delete-all.**
  One conversation per delete, and both apps hold deleting and shortening
  the keep period on a stale link.

---

## 6. Events — one bus

`jarvis_events.Pump` runs the pollers on one thread; every client learns state
changes from it and from nowhere else. Kinds: `approval`, `proposal`,
`finding`, `power`, `persona`, `model`, `activity`, `appearance`, `step`,
`deep`, `memory_saved`, `hello`. (`step` is the tool loop saying what it is doing - asking the model,
a tool starting, finishing or refused - with tool names from its own table
and nothing else; `jarvis_agent._step_event`. Brain → Live renders it.
`deep` is a deep question finishing, `{"id", "state"}` only -
`jarvis_big_model.py`; added 2026-09-24. Both apps handle it: the desktop's
Brain reads `GET /api/deep` again (`brain.js`, Deep questions), and the
phone's `JarvisRuntime.onEvent` re-reads `/api/deep` and `/api/big-model`.
`memory_saved` is automatic learning saving facts, `{"ids": [...]}` only -
`jarvis_auto_learn.py`; added 2026-09-24. Both apps handle it: the desktop's
Brain shows the quiet "Jarvis remembered N things" line and re-reads the
auto list and `memory_facts` (`brain.js` `noteMemorySaved`), and the phone
shows the same line on Mind and re-reads the list
(`JarvisRuntime.onMemorySaved`) - never a notification. JARVIS-API §19.)

**Every event is a doorbell.** Count, ids, and what is needed to route —
never content. This bus reaches a phone that surfaces notifications with the
screen off. Clients fetch the authenticated route for the content.

If you add an event kind, add the client handler in the same change. A
doorbell that rings into an empty room is the defect this codebase keeps
producing.

---

## 7. The model

One 8B, resident, nothing else on the card. Full arithmetic, the Modelfile,
the verification step and the second-card analysis are in
[MODEL-TOPOLOGY.md](MODEL-TOPOLOGY.md). Two things belong here because they
are architectural rather than configuration:

- **`num_ctx` cannot be set from the HUD.** It posts to an OpenAI-compatible
  endpoint, which has no field for it. Context length lives on the model or in
  the environment. Left alone, Ollama picks 4096.
- **The recalled-facts block goes late, never at index 0.** At index 0 it
  invalidates the KV prefix cache for the whole conversation every turn, *and*
  suppresses the Modelfile's `SYSTEM` block — which is where the persona
  invariants live. Both from one line. If delimiters are ever added around
  recalled facts, they go on that message, not around the list.

---

## 8. The clients

**Desktop** (`jarvis-desktop/`): Tauri 2, seven windows (quickbar, widget,
HUD, Brain, Faces, onboarding, Settings - one capability file each in
`src-tauri/capabilities/`), per-window ACL capabilities. The Rust commands are the real API — buttons are a courtesy, and
any window holding the capability can call them, so a check that lives only in
the webview is not a check. `decide_approval` consults link staleness in Rust
for exactly that reason.

**Android** (`jarvis-client/`): Kotlin, native, over Tailscale. It is a
remote, not a second brain. It renders, it decides one thing at a time, it
does not hold its own copy of state.

`jarvis-android/` is the older app, kept for reference only: it speaks a
protocol the backend does not have, so it cannot talk to Jarvis. Its safe
parts (the approval widget, a quick-link widget) are already in
`jarvis-client`; see `CLAUDE.md` before copying anything else from it.

### Talking to the other branch — do this, it keeps going wrong

**Now that both apps live in this one repository** (`jarvis-desktop/` and
`jarvis-client/` on the same branch), the fetch commands below only matter
for old work still sitting on the two former branches. The lesson does not
expire: read the other side's code before claiming anything about it. The
history is kept because it is why that rule exists.

The two clients were worked by two sessions that **cannot message each other**.
Communication is a committed document. That much was already understood. What
was not: *each session only ever sees its own branch*, so a document written
as a message sits unread on the branch of whoever wrote it, and **silence
looks exactly like being ignored**.

That has now caused four separate misunderstandings in two days:

- The desktop's reply to `CROSS-CLIENT-CONTRACT.md` was written, committed and
  pushed — and recorded on the other side as never read.
- The Android session's `check_parity.py` was wrong about whether
  `/api/appearance` exists **in both directions inside 24 hours**, because it
  was reasoning about desktop source it had not fetched.
- The desktop told the Android session to fetch `/api/approvals`, a route that
  does not exist, from memory rather than from `jarvis_hud.py`.
- The Android session's `SpecDriftTest` compares against its *own* vendored
  copy of the visual spec, so it is structurally incapable of detecting drift
  from the desktop's copy.

Every one of them is the same mistake: making a claim about the other side's
code without fetching it. So:

```bash
# Before writing anything ABOUT the other client, or replying to it:
git fetch origin claude/android-apk-build-q435fi        # from the desktop
git fetch origin claude/jarvis-desktop-tauri-vey6bc     # from the client
git log --oneline origin/<other-branch> -10
git show origin/<other-branch>:docs/<the-doc>.md
```

**Read the other branch before claiming anything about it, and fetch before
concluding a message went unanswered.** A reply you cannot see is not absence
of a reply.

The cross-branch documents from that time (all in `docs/` now):

| on the desktop branch | on the client branch |
|---|---|
| `docs/CROSS-CLIENT-CONTRACT-REPLY.md` | `docs/CROSS-CLIENT-CONTRACT.md` |
| `docs/ANDROID-VOICE-FALLBACK.md` | `docs/ANDROID-REPLY-2026-09-15.md` |
| `docs/ARCHITECTURE.md` (this file) | `docs/HANDOFF.md`, `CLAUDE.md` |

One more thing the desktop session can do cheaply and the Android session
cannot: **read that branch's CI logs**. There is no local Android build, so
every check there costs a ~15 minute round trip, while the GitHub API is a
few seconds from here. Offer it rather than waiting to be asked.

**But relay the evidence, not a reading of it.** Fetching those logs resolved
a compile error whose five reported symptoms were all downstream of one
unclosed comment. It also produced the fifth misunderstanding, and this one
was pure relay damage: the desktop passed back a stack trace with the words
*"a timeout inside runBlocking — confirmed, not guessed"* on it. The frame
could not support that. `EventStreamContractTest.kt:103` is the `runBlocking`
line itself, so a timeout, a failed assertion and a thrown exception all
unwind through it identically — and the real cause turned out to be a
`ConcurrentModificationException`. The other session had written that
hypothesis in its own handoff, the desktop repeated it back with added
confidence, and it briefly became settled fact in two places at once.

A frame inside `runBlocking` says where a coroutine was blocked, not why it
failed. The general rule, which is the reason this is in the architecture
document rather than a commit message: **quote the log, and let the side that
owns the code do the diagnosing.** Fetching the other branch catches a stale
file. It does nothing about a claim that was never verified — and confidence
added in transit is indistinguishable, at the far end, from evidence.

### One-sided on purpose

The two apps are meant to do the same things. These are the exceptions, each
with its reason, so a gap is never mistaken for an oversight (or an
oversight for a decision). `tools/check_parity.py` checks the ones that are
backend routes, in both directions; the rest are listed here only.

**On the desktop, kept off the phone:**

| what | why |
|---|---|
| The memory graph (`/api/graph`) | Out of scope on the phone (`CLAUDE.md`). |
| Rewording a stored fact (`/api/memory/edit`), and forgetting one that was not saved automatically | Deep memory editing. It stays on the desktop's Brain → Memory tab. Forget (`/api/memory/forget`) itself is no longer desktop-only: since 2026-09-24 the phone calls it for facts in the "Saved automatically" list (JARVIS-API §19). |
| "Erase the words" (`/api/memory/erase`) on a fact that was already forgotten, or was never saved automatically | The same line as Forget, above: the phone lists only facts saved automatically that are still in use, and a list of every fact, forgotten ones included, is deep memory editing. The phone offers Erase wherever it offers Forget (Mind → Saved automatically), so the route itself is on both apps. |
| Exporting all memory (`/api/memory/export`) | A copy of everything Jarvis knows does not belong on a phone that can be lost. |
| Shutting the backend down (`/api/shutdown`) | The phone would then have nothing to reach and no way to undo it. |
| Deep config editing (`/api/config`) | Out of scope on the phone (`CLAUDE.md`). The desktop does not use it either today: it is only in the Brain window's read allow-list, and no window asks for it. |
| Fetching the look spec (`/api/visual-spec`) | The phone ships its own copy and checks it in a unit test (`SpecDriftTest`); `JARVIS-API.md` says the phone never fetches it. |
| "Finished, or only paused?" (`/api/voice/turn`) | The phone runs the same Smart Turn model itself (`voice/SmartTurn.kt`), so its audio never leaves it just to ask. The desktop asks its own PC over loopback. |
| Screen capture | Nothing earlier wrote a reason down; this one is written 2026-09-24 from the code. The phone attaches a picture through Android's photo picker (`MainActivity.kt`, `PickVisualMedia`), which already offers the phone's own screenshots - one picture, chosen by the owner. Capturing the screen live on Android needs a separate system permission every session and shows a "casting" icon, for no gain over the picker. |
| Global hotkeys (`hotkeys.rs`) | Keyboard shortcuts for a PC. A phone has no equivalent. |
| The tray icon (`tray.rs`) | Part of Windows' taskbar. |
| Starting and stopping the backend (`sidecar.rs`) | The backend runs on the PC, next to the desktop app. The phone cannot run it, and stopping it from the phone is the `/api/shutdown` problem above. |
| The Faces window's "Portable output" (`faces.html`) | Code for building a client (the look spec as JSON, Kotlin, TypeScript). It is a developer's tool, and the phone already ships its own copy of the spec. |
| **Update notice** | **Undecided - the owner's call.** The desktop checks GitHub for a newer version and says so in Settings (`update.rs`; it never installs on its own). The phone has no such notice: a new APK is published to the `client-latest` release and installed with adb. Whether the phone should say "a newer version exists" has not been decided. |

**On the phone, kept off the desktop:**

| what | why |
|---|---|
| The phone's own layout settings (`AppearanceStore.kt`, `Look`: the face's share of Home, the tabs row, glow, motion, compact spacing, corners, text size, panel edges, and the "make room" switches) | They describe a phone screen. They are saved per device and never synced (`toSyncDocument` leaves them out), so they cannot change the desktop. |

**The voice flow is in both apps since 2026-09-25** (`docs/JARVIS-API.md`
§17 part 5; it was backend-only until then): interrupting Jarvis by talking
(`?source=barge_in`, pause first and decide second), "One moment." when a
tool starts (`GET /api/voice/moment`, `ported` in `tools/check_parity.py`),
`&waited_ms=`, the "I heard you" sound, keeping listening after a question
(part 6) and telling the model it was interrupted (part 7). Two small
differences, on purpose, each for a reason written in §17: the desktop
plays "I heard you" for a "hey Jarvis" sentence only once the PC says the
phrase was heard (its listener cuts every sound in the room; the phone's
own spotter already heard the phrase), and only the phone opens its
microphone by itself after a question (the desktop's listener is always
listening). Still in neither app: the "Voice delay" panel (`flow.summary`)
- the one-line command in `backend/README.md` prints it.

---

## 9. Where the backend lives

**Not in this repo.** The owner keeps `jarvis_hud.py`, `jarvis_memory.py`,
`jarvis_gate.py` and the rest on their machine. `backend/` holds **patches**
against them plus the tests that prove the patches do what they claim.
`backend/.gitignore` refuses the sources, because a stale copy in git is worse
than no copy — the next reader would not know which is real.

**Twenty-six modules, and there is no second copy.** No public upstream has
been found; the evidence is that the files were produced in assistant
conversations and saved to disk, which makes that chat history the only
backup. `scripts/check-backend.ps1` lists what a folder is missing — run it
before the patches, because a patch failing against an absent file reports
"patch does not apply" and reads as a bad patch.

That asymmetry is worth stating once: **this repo is version-controlled and the
thing it patches is not.** A patch here can always be recovered. The file it
edits cannot.

Fifty-two patches (counted in `scripts/apply-patches.ps1`'s list on
2026-09-24, after `chat-history.patch`, `auto-learn.patch`, `memory-erase.patch` and `past-recall.patch`), applied in that list's order. The order matters: many patches
edit lines an earlier one wrote, and the list's comments say which. Above
all, `memory-safety` must land first: without it the first accepted proposal
retires a roughly-matching unrelated fact, permanently, and `retire()` has
no way back. `backend/README.md` has the table and a section per patch.

New capability that is a whole module — `jarvis_research.py` and most of the
newer ones, like `jarvis_second_card.py` and `jarvis_big_model.py` — ships
as a file, not a patch, because there is nothing on the owner's machine to
patch. `apply-patches.ps1` copies them in.

---

## 10. Things that do not exist

Say so rather than designing around imagined code. This list was last checked
against the repository on 2026-09-24; an item moves off it only when the file
that makes it true is named.

**No longer missing** (this section used to list them, and was wrong once
they landed):

- `jarvis_speech.py` now exists, in `backend/`, with `jarvis_wakeword.py`,
  and `apply-patches.ps1` copies both in. It is what the four `/api/voice/*`
  routes call: speech check (Silero VAD), speaker check, then speech-to-text,
  and text-to-speech back, all on this machine. Its model files are NOT in the
  repo: until the owner runs the installs in `backend/README.md` ("Voice that
  works"), those routes answer "not installed" honestly rather than working.
- `jarvis_framework.py`, `jarvis_router.py`, `jarvis_initiative.py`,
  `jarvis_compute.py` and `jarvis_sleep.py` exist as **rebuilds** in
  `backend/rebuilt/`, with `jarvis_events.py`, `jarvis_memory.py`,
  `jarvis_power.py`, `jarvis_recall.py` and `jarvis_voice.py`. The originals
  were confirmed gone; each rebuilt file's header says what was recovered and
  what was inferred. `backend/test_rebuilt.py` tests them.
- **The memory review pane.** The desktop has it (Brain → Memory: accept,
  reject, "both are true", edit, forget, and "what did you believe then?"),
  and so does the phone (Mind). Both read `/api/memory/pending`
  (`memory-pane.patch`). The HUD page decides no memory cards: it says how
  many are waiting and points at the Brain, and `hud_bootstrap.js` refuses
  any memory write from it.
- **Obsidian** (added 2026-09-24). `#obs` appends to today's daily note and
  the notes search reads the vault, both as a plain folder on this PC - no
  plugin, no key, no socket (`jarvis_note_capture.py`, `jarvis_notes.py`,
  gate action `append_obsidian_daily`, the same four steps as §3). Both apps
  show only the note targets the PC is set up for: `GET /api/notes/capture`
  with no id lists them by name. What the search finds reaches the local
  model only - `backend/test_obsidian_notes.py` puts its real output through
  the agent loop and the cloud cut to prove it.

- **The second graphics card** (added 2026-09-24), built and ALL OFF.
  `jarvis_second_card.py` detects a capable second card (Turing or newer,
  10 GB or more), and five switches - longer conversations, pictures,
  background learning, browser control, the wiki builder - each turned
  on by one approval card (`second_card_enable`, the same four steps as
  section 3) and only while that card is detected. When one is on, a second
  Ollama runs on `127.0.0.1:11435`, pinned to that card by its id; chat,
  pictures, the learner and browser control reach it only through
  `lane_for()`, which is None - "do what you did before" - in every other
  state. `GET`/`POST /api/second-card` (`second-card.patch`). Both apps have
  its screen: the desktop's Settings ("Second graphics card", `settings.js`)
  and the phone's Mind (`SecondCardPlate.kt`). Not measured on real cards.
  [`SECOND-CARD.md`](SECOND-CARD.md) is the owner's guide.

- **The wiki builder** (added 2026-09-24). Documents the owner puts in the
  vault's `Jarvis Wiki/Sources` become linked pages in `Jarvis Wiki/Pages`,
  written ONLY by the second card's model (`lane_for("wiki")`; None means
  nothing runs) - or, when the owner has switched the big model on for the
  wiki, ONLY by the big model (below), never by both and never by falling
  back from one to the other. `backend/jarvis_wiki.py` and `wiki.patch`: `GET /api/wiki`,
  `GET`/`POST /api/wiki/ingest`, gate action `wiki_update` (tier `ask` as
  shipped), the same four steps as section 3 - with one honest difference:
  its `plan()` opens a socket, to the lane on 127.0.0.1 only, because the
  model's answer IS the plan. Every page is validated before anything is
  written; the old copy of a changed page is kept in `.versions`. The card
  lists each page with a one-line summary rather than its full text. Both
  apps have a Wiki plate (the desktop's Brain → Memory, the phone's Mind).
  Not run against a real model yet.

- **The big model, slow** (added 2026-09-24), built and ALL OFF.
  `jarvis_big_model.py` runs a very large model with colibri (an Apache-2.0
  engine that streams most of the model from the SSD; Jarvis only talks to
  its HTTP API) for two background jobs: the wiki builder and "deep
  questions". Never chat, voice or approvals. Three switches (main, wiki,
  deep questions), each turned on by one approval card (`big_model_enable`,
  the same four steps as section 3), and only once colibri, Python 3, a
  downloaded model and enough memory and disk are found. colibri is started
  on demand on `127.0.0.1` with a key kept in Credential Manager, stopped
  when idle, and uses no graphics card unless the owner sets `cuda = "on"`,
  and then only the second card. Deep questions: no card per question (the
  switch was the approval; a question acts on nothing), answers kept in
  `deep-questions.jsonl` on the PC with their measured speed.
  `GET`/`POST /api/big-model`, `GET /api/deep`, `POST /api/deep/ask`
  (`big-model.patch`). Both apps have its screens: the three switches in the
  desktop's Settings ("Big model (slow)", `settings.js`) and the phone's Mind
  (`BigModelPlate.kt`), and deep questions in the desktop's Brain → Memory
  (`deep.js`) and the phone's Mind (`DeepQuestionsSection`, same file). Not
  run against a real colibri or on the owner's PC; none of colibri's speed
  claims checked there. [`BIG-MODEL.md`](BIG-MODEL.md) is the owner's guide.

**Still missing:**

- **Obsidian daily notes in every date format.** Only formats that can be
  written out exactly are followed (YYYY, YY, MM, M, DD, D, bracketed words,
  `/` folders). A format with month or weekday names, or week numbers, is
  refused with the reason, and so is a vault where the Periodic Notes plugin
  may be naming the daily note. Nothing guesses a file name.

- **Overnight memory tidying.** `jarvis_sleep.py` only offers it, once a
  day, and the card says it is not built; switching it on records the wish
  and runs nothing. If it is ever built it may only raise review cards: no
  stored fact is retired or changed without the owner's yes on that one
  fact.
- **A wake word measured on real speech.** "Hey Jarvis" is built (openWakeWord's
  model, on the phone and through the PC; turning it on is an approval card),
  but it has only been tested on synthesised voices: 44/44 heard, and the
  false alarms it produced were all dropped by the transcript check. Its
  false-alarm rate on real speech, TV, and battery use on the phone are not
  measured yet.
- **A picture-capable local model, switched on.** The default model
  (`qwen3:8b`, via `jarvis-primary.Modelfile`) reads text only. A screenshot
  sent to it is not seen, so the quickbar asks Ollama first
  (`local_model_vision`) and offers to send the words without the picture.
  The fix is BUILT but off: the second card's "Pictures" switch sends a
  picture turn to `qwen2.5vl:7b` there (`jarvis_second_card.py`, below), and
  nothing changes until that card is installed and the switch approved. The
  desktop's check knows about it: `vision.rs` reads `GET /api/second-card`
  first, and says yes (naming that model) when the Pictures switch is on and
  its model is there; otherwise it asks Ollama about the everyday model, as
  before. Pictures never go to a cloud lane (`jarvis_router.choose()`
  keeps any turn with an image local, and the second card is on this PC).
- **A reasoning trace.** Brain → Live shows each tool Jarvis starts and
  finishes (the `step` event, from `jarvis_agent.py`, only when tools are
  switched on), but not the model's private reasoning: that text can quote
  email or files, and the event bus reaches a phone's lock screen (§6), so
  it is deliberately not published.
- The `documents` table - read by two code paths, created by none. The status
  line says `documents: false`, which is correct. Since
  `documents-owned.patch`, a `documents` table is read only if Epic-Jarvis
  recorded creating it (`jarvis_owned_tables.py`): OpenJarvis's indexer
  makes one with that exact name in the same `memory.db`.
- **A published desktop update.** The updater is wired and the release
  workflow (`.github/workflows/desktop-release.yml`) is written, but nothing
  is published until the owner generates a signing key and adds it
  (`jarvis-desktop/README.md`, "Turning on updates"). Until then Settings
  says updates are not set up.

**Present, but only on the owner's PC** (not missing, and not in this
repository either):

- `jarvis_jobs`, `jarvis_undo`, `jarvis_ledger`, `jarvis_content_risk`,
  `jarvis_watch` and `jarvis_hud`. The owner checked their backend folder on
  2026-09-23 and all six files were there - checked by file presence only,
  so what is inside them, and the exact shape of the routes they serve, is
  unverified from here. The Brain's **Work** (`/api/jobs`, `/api/undo`),
  **Trust** (`/api/ledger`, `/api/content-risk`) and **Watch** (`/api/watch`)
  tabs read those routes; if a route does not answer, the pane says "Not on
  this backend." (`brain.js`, `unavailable()`).
- The rest of the backend (`jarvis_gate.py`, `jarvis_extract.py`,
  `jarvis_models`, `jarvis_arbiter`, ...) is in the same position (§9).
  `scripts/check-backend.ps1` is how to see what a folder holds.

---

## 11. Decisions already taken

Do not relitigate these without new evidence.

| | |
|---|---|
| Reachability | Tailscale, properly. Never a public tunnel. |
| Face / appearance | Rendered locally on each device; the server is a sync channel only. |
| Voice | sherpa-onnx for STT (Parakeet TDT 0.6B v2), speaker verification, Kokoro TTS, Silero VAD. 0 GB VRAM. First audio is slow: from the owner finishing to Jarvis's first sound is roughly **2.5–4 s** today, with the voice on the processor. That is an estimate - the model's part (first word, first sentence) has not been measured; making the first sentence's sound alone takes about 1.3–1.6 s (measured in the dev container, not the owner's PC). The real figure is in `flow.timings` and `flow.summary` of `/api/voice/status` on the owner's PC (`backend/README.md`, "The voice flow"). Design a "thinking" state that survives several seconds of silence. Both apps make the next sentence's sound while the current one plays (one ahead), so there is no silence *between* sentences as long as making the next one takes less time than saying the current one (a simulation in the dev container: 3.5 s of mid-answer silence became 0 s; a short sentence followed by a long one can still leave a pause). Both apps also start speaking at the **first comma** of an answer once the phrase is long enough - the first piece only, the same rule on both (`jarvis-desktop/src/speech-pieces.js`, `SpeechText.kt`, one shared list of cases); in the dev container that moved the first sound from 2.04 s to 1.23 s, at the cost of one short pause after that first phrase. And a question **said** out loud is answered in a spoken style - a short first sentence, one to three sentences, no lists or markdown - by one line the PC adds for this PC's own model only (`jarvis_agent.SPOKEN_NOTE`, `JARVIS-API.md` section 17); typed questions are unchanged. The "One moment." clip's suggested 1000 ms (`JARVIS-API.md` section 17) would therefore fire on most spoken turns at today's speeds. **The wake word is the exception**: openWakeWord's `hey_jarvis` model on ONNX Runtime, on the phone and the PC alike - sherpa-onnx has no Android library on Maven Central/Google, and the TOML and `WAKE-WORD.md` had already chosen openWakeWord. Measured side by side in `backend/README.md`. **Custom voices** (2026-09-24, the owner's decision): ZipVoice via sherpa-onnx on the processor, and F5-TTS as an optional second-card "better voice" in its own process (on demand, stopped when idle and in standby); Kokoro stays the fallback. Adding a voice and switching to one are each a card; a voice that sounds like the owner's is refused (`backend/jarvis_voices.py`, `JARVIS-API.md` section 15). |
| Cloud / API keys | Allowed, **per use, with permission**. Jarvis works out what it genuinely needs the internet for, explains it, and asks. No standing grant. Enforced in `jarvis_router.choose()` since 2026-09-24 (the owner chose "ask each time"): without the owner's yes for that one question it answers locally and only names the cloud lane in `offer`; a yes never carries a private, tainted or picture turn out. Before that, the router escalated long questions by itself. |
| Structured output | Ollama's native `format: <schema>` — GBNF at the sampler. **Not** `outlines`, which cannot constrain Ollama. |
| Sandbox | Git worktrees, not Docker. |
| Extraction | `ast-grep` — measured 54,490 → 1,088 bytes, 0 VRAM. |

**Rejected, with reasons, so they stay rejected:** screenpipe (relicensed,
captures keystrokes and the a11y tree, telemetry on by default) · moshi
(upstream says 8 GB cards cannot run it) · cr-sqlite (automatic merge breaks
the consent rule — demonstrated on the real binary) · llm-guard (archived
2026-07-09, models abandoned) · cognee and graphrag (~40 deps / three
mandatory Azure SDKs) · LLMLingua (negation-blind) · browser-use (dies at 8k
context by step 2–3; the framework and its loop stay rejected, though some
of its MIT code - page reading, watchdogs, secret placeholders - was adapted
into `jarvis_browser_control.py` on 2026-09-23, loop left out) · Phi-4-mini
(8B KV cost at 3.8B capability) · kokoro-onnx
the package, though Kokoro the model is adopted via sherpa-onnx.

---

## 12. Before you add anything

1. Does an existing mechanism already do this? The gate, the proposals queue
   and the event bus each get reinvented by roughly every external proposal
   that arrives. Connect to them.
2. Does it have a call site and a surface? If a person cannot see it happen
   and nothing invokes it, it is not finished.
3. Does it act, or leave the machine? Then it is `plan` / `describe` / gate /
   `run`, with the tier asserted.
4. Can you state, in one sentence, what it sends and where? If not, you do not
   know yet.
5. Does it need a test that fails on the unpatched tree? Yes. Every patch here
   has one, and several caught the fix being wrong.
6. Has someone already built it? [`PEERS.md`](PEERS.md) is what twenty
   comparable projects did about memory, approval gates, voice and packaging,
   read from their source, and [`COMPARISON.md`](COMPARISON.md) puts their
   files beside ours. Between them: what to copy, what to refuse, and where
   Jarvis is behind. Three of the most-recommended projects in this space are
   archived or retired, so check there before adopting a dependency — and
   check our own file before copying theirs, because twice now we already had
   the thing, and once ours was stricter.
