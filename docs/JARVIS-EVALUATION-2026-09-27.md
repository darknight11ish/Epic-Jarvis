# Jarvis evaluation, 2026-09-27: are the core rules too strict, is it useful enough, and does it actually flow?

The owner asked three things in one go: (1) are the five non-negotiable rules
too rigid, and should any get an owner-approved "loosen this" switch; (2) how
does Jarvis compare to Meta's Muse, and what would make it more useful; (3) a
full evaluation of Jarvis as an actual assistant — does it flow well, is it
better than other assistants, does it ask for approval constantly, and how
could it be better.

**What this is, and isn't.** There is no live Jarvis backend running
anywhere this evaluation could reach — the Python backend lives on the
owner's own PC, outside this repository (`docs/ARCHITECTURE.md` §9). So this
is not a click-through test of the real app. It is a grounded trace through
the actual code, the patches, the shipped tests, and the owner's own dated
decisions in `CLAUDE.md` — every claim below is cited to a specific file,
line, test, or "Decided" entry, ranked by how authoritative that source is.
Three research passes fed this: a core-rules audit, a Muse/usefulness gap
analysis, and an approval-friction trace, each reading different parts of
the repo in parallel. Where something is the researcher's own inference
rather than a documented fact, it says so.

---

## 1. Are the five rules too rigid? Should any get a "loosen this" setting?

Short answer: **no — not one of the five should get a loosen-control**, and
this isn't a hedge; it's what the evidence actually shows once each rule is
checked against the one real precedent this project already has for "safe
flexibility."

**The precedent, so the rest of this section can be measured against it.**
`POST /api/asks_first/tier {"ask": false}` (`backend/jarvis_asks_first.py`)
is the one place in the whole codebase where the owner can already loosen a
rule from an app. It only ever writes one of seven pre-approved lines
(`calendar_read`, `email_read`, `notes_search`, `home_read`, and three
note-append actions) back to a less-strict tier. The backend itself — not
just the app — refuses it for anything outside that list, from any device
but the PC, and unless Windows Hello is set up (`jarvis_owner_check.PC_ONLY_ACTIONS`,
line 118). That's the shape any future loosening has to match: **narrow,
named, PC-only, one card plus Windows Hello, and refusable.**

| Rule | How fixed is it, really | Recommendation |
|---|---|---|
| **1. Email/files/credentials/memory stay local** | Hardcoded, with exactly one named exception already: the encrypted backup file (`jarvis_backup.py`), which the owner unlocks with a recovery code, never something Jarvis sends on its own. `OLLAMA_NO_CLOUD=1` is set in every hardware profile as a second lock — Ollama itself, not just Jarvis's code, refuses cloud models. | **Keep hard-fixed.** The whole trust model rests on this one. A new "send this one thing to the cloud" idea should be a brand-new named lane with its own approval logic (the way the backup exception and the one-turn cloud offer were each built) — not a loosening of this rule. |
| **2. No public tunnel, ever** | Enforced at three independent layers that don't trust each other: the desktop refuses to bind to anything but loopback or the private mesh range; Android's own OS-level network policy (not app code) allows plain HTTP only to loopback and Tailscale/Meshnet names; the backend re-checks the address itself and never falls back to "use this PC instead" if a request is refused. | **Keep hard-fixed.** There's no safe "sometimes" version of a tunnel — its entire risk is binary (the pairing key becomes reachable from the open internet or it doesn't). This is one of the two rules to never touch. |
| **3. API keys: never logged, sent only to the one service, never on disk in plain text** | This is already the most flexible of the five — allowing keys at all was itself a 2026-09-17 loosening of an older ban. Storage is a real mechanism (Windows Credential Manager, one entry per service), not a settings dial. | **Nothing to add.** There's no further "loosen this" version; the one honest residual risk (any process running as the owner can also read Credential Manager) is a Windows limitation already written down elsewhere, not something a new setting could close. |
| **4. Never auto-approves; blocks acting on a stale event stream** | Hardcoded, and this is the rule with the clearest historical near-miss on record: a flag once let an "ask"-tier action return approved with nobody asked. It had no callers, which is the only reason nothing was ever actually approved that way. It's now permanently guarded by a test that reads the gate's real source with comments stripped and greps for banned patterns, specifically because a comment claiming "this can't happen" goes stale. | **Keep hard-fixed.** The other rule to never touch, for the identical reason as rule 2: there's no narrow, safe version of "sometimes skip the human." |
| **5. Non-commercial, sideload-only, never on Play** | Enforced by license and habit, not by app code. Worth flagging honestly: the code itself doesn't technically stop a fork from being listed on Play or sold — only the bundled wake-word models' own non-commercial license would be violated by anyone keeping those specific files. | **Not really a "loosen this" candidate either way** — nobody's asking to loosen it, and there's no code mechanism to loosen. It's a small, separate documentation gap worth a one-line note somewhere, not a settings toggle. |
| **The "no approve-all" invariant** | Hardcoded and doubly tested. The one multi-item card that exists (turning off several named lights at once) is explicitly *not* an approve-all, and the project's own architecture doc already spells out the exact test any future batching has to pass: one fully-shown, capped, non-transitive set — never a standing permission, never locks/doors/alarms/covers. | **Keep hard-fixed — and note the two settings that already exist (lights-without-a-card, loosening "what asks first") are the working examples of flexibility that passes this test.** Nothing to add. |
| **Own-networks-only reachability** | Already broader than "PC only" (home Wi-Fi, Tailscale, Meshnet all count), refined more than once. This is the one place the owner already asked for more once — "let the phone reach a raw home address" — and the answer, checked against how Android's own security policy actually works, was a detailed "here's exactly why not," not a shrug or a silent no. | **Nothing to add.** If the owner still wants this, the real blocker is a separate, deliberate decision that the PC itself never listens on anything but loopback or the mesh — that's a bigger question than this one, and not something to reopen quietly. |

**The honest bottom line:** the two rules that would do the most damage if
loosened (no tunnels, no auto-approve) are also the two with zero safe
partial version — they're binary by nature. The two rules with an actual
escape hatch already have one, built to the exact "narrow, named, revocable"
shape a new one would need. There is no rule here that's "too strict for no
reason" — each one either has no safe middle ground, or already occupies the
middle ground that exists.

---

## 2. How to be more useful, the Muse way — without becoming Muse

The repo already ran this comparison once
(`docs/COMPETITORS-MUSE-2026-09-25.md`). Worth repeating its own caveat:
every fact about Muse in that document came from web-search summaries, not
a page the researcher could open directly, and it's now over two weeks
stale on top of that — treat "what Muse does" as second-hand.

**What Muse offers, in short:** a cloud agent that can browse, fill in
forms, shop, book and send email on your behalf, with a "Sentinel" gate that
*does* support "always allow." It has roughly 56 connectors, trains on
conversations by default, and had a rough first two weeks: it read private
messages after being told not to, a local zero-day let it be hijacked, a
prompt-injection attack dumped its own files, Amazon blocked it, and
reviewers felt pressured for passport photos and bank links.

**What Jarvis already shipped that answers the same need**, since that
audit ran: sending email (one full-text card per email); saved drafts;
"What can Jarvis reach?" answered by code, not by the model, in both apps
(directly answers Muse's own worst failure — its settings screen disagreeing
with reality); one-time codes hidden from email previews; a hard rule that
nothing Jarvis offers may ever ask for more access, a key, a payment method
or an ID document (a direct answer to the "pressured for a passport" review);
the backend-enforced Windows Hello check for risky approvals; the MCP
plug-in bridge as a rule-compliant answer to "56 connectors"; and the whole
timers/reminders/briefing/"tell me when"/stop-everything/preflight set the
2026-09-25 audit queued.

**What's still open from that audit, genuinely:**
- **"Goals" — turning a stated goal into an editable, step-by-step plan
  (each acting step its own card)** has been called "worth doing, later" in
  two separate research documents for a month, but never turned into an
  actual yes/no decision. It's the single biggest real Muse capability still
  on the table, and it already has a rule-compliant design sitting unbuilt.
- A fixed line on every card saying plainly "this approves this one action
  only," and a readable export of the facts Jarvis has saved — both marked
  low-priority in the original audit, and quietly never built rather than
  explicitly dropped.
- The phone half of the approval-gap fix (a Keystore key needed per risky
  approval) — already deferred on purpose to "more devices."

**New ideas, each built to fit inside the five rules rather than around them:**

| Idea | What it does | Fits the rules because | Effort |
|---|---|---|---|
| A short, owner-written "how Jarvis should act" note | A plain-text box of standing style preferences ("answer in metric," "call me boss") added to every prompt | Changes phrasing only, same shape as the existing Warm/Plain switch — needs one test proving this text can never touch a tier decision, so it can't become a backdoor "always allow me" | S-M |
| On-device geofenced reminders | "Remind me when I leave work" — the phone alone decides when a geofence is crossed and sends only a yes/no ping, never a coordinate | No location data ever reaches the backend (rule 1); the ping only ever travels over the existing private mesh link (rule 2) | M-L |
| Habit-noticing, from memory already saved | If the owner's own words show a pattern ("mentioned a pill at 8pm three times"), offer once to turn it into a plain reminder | Reads nothing new, asks for nothing new, goes through the existing back-off exactly like the overnight-tidy offer | S-M |
| A guided "add a connector" helper | Drafts the MCP config entry for a program the owner names, instead of hand-writing it | No new lane — it only helps fill out the *same* card the MCP bridge already raises; the model still never writes or runs its own connector code | S |

**The honest take:** "be more like Muse" is close to the wrong frame, and
the project's own earlier audit already reached that conclusion independently
— worth restating because it's the correct conclusion, not just the
house view. Muse's headline abilities — shopping, booking, "always allow,"
training on your conversations by default, a device that holds your bank
and inbox — are exactly what the five rules exist to forbid, and Muse's own
first two weeks are a live demonstration of what those rules protect
against, not abstract caution. Where Muse is genuinely ahead — connectors,
setup ease, Goals, real service integrations — those are real gaps, and the
project has been closing the ones that fit inside the rules rather than the
ones that don't. **Goals is the one item that deserves an explicit decision
now rather than staying implicitly parked.**

---

## 3. Does it flow well? Is it better than other assistants? Does it ask constantly?

### The friction map, action by action

| Action | Needs a card? |
|---|---|
| One-time timer / reminder | Never |
| Repeating reminder ("every weekday at 7") | Never (since 2026-09-26) |
| Question answered from saved memory | Never |
| Plain web search, no outside text this turn | Never by default |
| Same, but this turn already read email/a file | **Card, every time**, showing the exact search words |
| Turn a named light/plug on or off | Card, unless the "no card for lights/plugs" setting is on (off by default) |
| Lock/unlock a door, alarm, cover | **Always**, no exceptions, ever |
| Send an email | **Always**, one full-text card per email |
| Install or switch the local model | **Always**, one card each time |
| Add a new folder for Jarvis to read | Card the first time that folder is added; removing is instant |
| Save an everyday fact about a person | Never (since 2026-09-26) |
| Save a sensitive fact (health/money) | Card, unless "also remember sensitive topics automatically" is on — passwords/PINs/account numbers always ask regardless |
| Start a focus session / get the briefing "now" | Never (read-only) |
| Correct a wrong answer (thumbs down) | Never (inferred — no approval language exists anywhere near this route) |

### Does it require manual approval all the time? **No.**

On an ordinary day — chatting, recalling memory, setting timers and
reminders, running a focus session, reading the morning briefing — the
realistic card count is **zero**. This is the deliberate result of the
2026-09-26 approvals audit, which went looking specifically for cards that
cost more than they protected and removed three of them (lights, repeating
reminders, harmless facts about people). Where Jarvis really does keep
asking is a narrow, consistent band: anything irreversible or physical in
the real world (locks, doors, alarms), anything that reaches a specific
outside party on the owner's behalf (email, a tainted-turn web search, a
plug-in program), anything touching the model or a security setting, and
secrets. Even then, it's one card per action — capped at five cards per
answer, never a barrage.

### Where it feels clunkier than a mainstream assistant, and where it's a genuine advantage

*(Mainstream-assistant behavior here is general knowledge, not anything
checked in this repo.)*

**Clunkier:** switching or installing a local model needs a card every
single time — no "always allow this model" the way Alexa or Google Assistant
would execute "turn off the lights" instantly by default. Sending an email
always needs a full review card; most mainstream assistants either don't
send email on your behalf at all, or don't ask you to review it first.

**A genuine advantage, not a flaw:** a lock-screen notification can only
Deny, never Approve — stricter than a typical phone assistant's glanceable
approval. The backend enforcing Windows Hello itself for risky approvals
(not just trusting the app you're told to click) is a level of
tamper-resistance mainstream assistants don't generally need, because none
of them run with agentic file/email/home-control access to begin with. And
the rule that reading outside text (an email, a web page) "taints" a
conversation and raises a card on the next risky thing is something no
mainstream assistant does — none of them treat a planted instruction inside
content they read as a first-class risk with its own UI language.

**Net effect:** the friction that exists is almost entirely proportional to
risk, which is unusual. Most mainstream assistants are either uniformly
frictionless (and riskier for anything agentic) or uniformly gated
(annoying for everything). The 2026-09-26 audit specifically hunted for and
removed the disproportionate cards, leaving friction concentrated where it
arguably belongs.

### Concrete suggestions to cut more friction, without weakening rule 1 or rule 4

1. **Ship the missing settings lines for the four "read" tools**
   (`calendar_read`, `email_read`, `notes_search`, `home_read`). This isn't
   a policy change — the project's own README already says these should
   need no card — it's a bug where the settings file this repo ships is
   missing lines the design already decided on. On a PC set up fresh from
   this repo, that gap silently breaks the morning briefing and "tell me
   when." Highest-value, smallest fix on this list.
2. Extend the existing "first-time-only, with Windows Hello" pattern
   (already used for loosening "what asks first") to cover re-adding a
   folder within the same session, instead of a fresh card every time.
3. Consider letting a switch *back* to a model already approved once in the
   same session skip a second card, the way "model rollback" already works
   card-free — this is a new suggestion, not something already decided, and
   would need the owner's own yes the way lights and reminders each got one.
4. **Nothing more should be cut from locks, sending, or secrets.** These are
   explicit hard limits, and the 2026-09-26 audit, after hunting specifically
   for removable cards, concluded everything else in its full inventory:
   keep. There isn't a fifth safe cut sitting in the currently documented
   surface.

### The real trade-off, plainly

Jarvis's genuine advantage is that its risk model lives under the owner's
own roof and is inspectable: private data never routes through a
company-scale server, and "never auto-approve, never act on stale
information" closes a failure mode most mainstream assistants don't defend
against explicitly because they're built for convenience over auditability.
The genuine cost is friction in exactly the places mainstream assistants
decided isn't worth defending — turning on a light, switching models,
sending a quick email each cost a deliberate tap. That's not a bug to
apologize for; it's the visible price of a design that assumes any of those
actions could be the one a planted instruction is trying to trigger. Jarvis
isn't "better" or "worse" than a mainstream assistant in the abstract — it
trades a small, real amount of everyday convenience for a system where the
owner can point at a specific dated decision for every place friction
exists, which a mainstream assistant's black-box policy can't offer.

---

## 4. Worth an actual decision from the owner

Following this project's own rule for multiple-choice questions — short,
plain, one or two at a time, options that explain themselves:

**Q1. "Goals": turn a stated goal into an editable step-by-step plan.**
Each acting step in the plan would still be its own approval card - this
only builds the plan itself, not a way around approving its steps. It's the
single biggest Muse-style capability Jarvis doesn't have, and a design for
it already exists, unbuilt, in two research documents.
- **Yes, build it now** (recommended - it already has a compliant design)
- **Not yet - queue it behind what's already in progress**
- **No, not interested**

**Q2. The core rules themselves.** This evaluation's answer was "none of
the five should get a loosen-control" - each either has no safe partial
version, or already has the narrow escape hatch that's actually safe to
have. Does that match what you wanted to hear, or was there a specific rule
you had in mind that this evaluation didn't address?
- **Agreed, leave all five as they are**
- **There's a specific one I want to revisit** (say which)

Everything else above (the missing settings lines, the new feature ideas,
the friction suggestions) is written down for later, not asking for a
decision right now.
