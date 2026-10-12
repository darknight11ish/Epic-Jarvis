# A cloud brain, and the second opinion: design only

**Status: DESIGN. No code, no patch, nothing switched on.** Written 2026-10-11 against
`origin/main` `4c604e87`; every line number below was read with
`git show origin/main:<path>`, not from the working tree.

The owner asked for a cloud model to run Jarvis's brain, "on a version that specifically
excludes private information", and chose **two shapes to be designed together**: the
carded one-question-at-a-time second opinion (Shape A), and the filtered cloud brain
(Shape B).

---

## 1. The rule-1 finding, first, because it is the whole document

Rule 1 of `CLAUDE.md` says, in the owner's own words:

> Anything touching email, files, credentials or stored memory stays on the local model.
> The app sends none of it anywhere.

**A cloud model running the brain sends some of that.** Not as a side effect - as the
point of the feature. The brain is what reads the memory, drafts from the email, writes
the note and decides which tool to call. If a cloud model does that, then memory text,
email text and file text reach a service that is not this PC.

`docs/RULE-FLEXIBILITY.md:41` and `:53` are explicit about what to do with that:

> These are not "hard to relax": they are the floor, and a feature that needs one of
> them is a finding to report - **not** a reason to edit the list.

So this is a finding, and the change it would need is stated plainly:

- **Shape A does not need rule 1 changed.** It is the carded, per-question exception the
  project already has in two other places, and it keeps memory, email, files and
  credentials local by construction.
- **Shape B does need rule 1 changed**, for the owner's own words and whatever the turn
  legitimately reads. Section 4 says why a filter cannot carry that weight, and section 3
  says what Shape B would have to promise instead.

Nothing here edits the list, and nothing here assumes the owner has agreed to it.

---

## 2. Shape A - the carded second opinion (his option 1)

**The shape.** The local model keeps everything: memory, email, files, credentials and
the tools. When a turn is hard, the owner asks for a second opinion and **one card lists
the exact words that would leave** - the question itself, and nothing else. The cloud
answers that one turn. No memory is injected, no tool output rides along, and nothing is
stored on the cloud side by this app.

**What is already built** (so this is mostly wiring and words, not new machinery):

- **The rule is already enforced at the router**, and it is worth quoting, because it is
  the strongest privacy sentence in the codebase (`backend/rebuilt/jarvis_router.py:17-23`):

  > "cloud turns get your raw question and nothing else. Local turns get your question
  > plus whatever stored facts are actually relevant to it. There is no third option
  > where a cloud model quietly receives your memory."
  >
  > So `inject_memory` is FALSE on every cloud lane, computed from the lane rather than
  > passed in - a caller cannot ask for memory on a cloud turn, because the bug that
  > started all this (`context_from_memory = true` injecting memory into every request,
  > before routing even ran) was exactly a caller being trusted.

- **A carded escalate already exists**: `backend/cloud-one-turn.patch` and
  `backend/cloud-say-yes.patch`, with the HUD's **`escalate CLOUD`** and
  **`critic CLOUD`** buttons.
- **The precedent for a card that lists what leaves, per request**, is
  `quiz_cloud_grade` (`backend/quiz-cloud.patch:7`): *"acts only on tier `ask`: ONE card
  per 'grade this better' request"*, and its risk row is `("no", "outbound", "makes this
  PC contact ...")` - an outbound action, one card, plain words. Shape A should copy that
  shape exactly rather than invent a new one.
- **The key handling already follows rule 3** (`backend/ollama-direct.patch:7-10`): the
  `Authorization` header is built in one place, the lane's key is read back from
  `jarvis_chatbot_api` and is *"never logged, never on disk"*, and a lane this PC cannot
  pay for *"comes back with no address"* (`:29-40`) - so a paid cloud lane fails closed
  rather than sending to a guessed address.

**What is missing** (the work, if the owner says go):

1. The card's words. The card must show **the exact question text that will be sent**,
   with a line saying plainly that no memory, no email, no file and no tool output goes
   with it. Whether today's card already does that has to be read on the PC - see
   section 7.
2. A named place in the app for the second opinion (the buttons exist; the settings row
   and its wording do not).
3. **Two things only the owner can do**, and they are his actions, not the app's:
   - **supply a key** for the service (rule 3: never logged, sent only to that service,
     never in plain text on disk); and
   - **set a monthly spend cap** (section 6). Without both, Shape A cannot be turned on.

**What Shape A still cannot promise.** The cloud sees the question. A question can
itself contain a secret - "what does this chest X-ray finding mean", "draft a reply to
the offer on Elm Street", "is 4111 1111 1111 1111 a valid card". The card shows the owner
what leaves, so he can stop it, but the app cannot know for him. That is honest and
acceptable *for one question he chose to ask*; it is not acceptable as a standing default,
which is exactly why the card is per request.

---

## 3. Shape B - the filtered cloud brain (his option 3)

**What it is.** The cloud runs the conversation. A filter runs over everything on its way
out and removes private material. His words: "a version that specifically excludes
private information".

### 3.1 The failure mode, designed first

**When the filter is unsure, the turn stays local.** Fail-closed. Never "cleaned and sent
anyway".

That is not caution for its own sake - it is the rule this repository already wrote down
about its own scrubber. `backend/jarvis_scrub.py:29-32`, from its section *"WHAT THIS IS
NOT FOR - READ BEFORE ADDING A CALL SITE"*:

> NOT the cloud lane: a message holding a secret is sent LOCAL by `jarvis_router` gate 3,
> never "cleaned and sent anyway". A scrubbed string is NOT safe to send anywhere: a
> pattern list never recognises everything.

**I agree with the Lead's recommendation, and I would go one step further.** A
card-on-unsure (offer the owner the choice when the filter cannot decide) is worse than it
looks:

- It makes the owner the filter, one prompt at a time, for exactly the cases a pattern
  list could not judge - and he is being asked to judge them **without seeing what the
  filter saw**. The cost is not the tap; it is that the tap looks like consent while the
  decision has been handed to the person with the least information.
- It trains the answer. After the twentieth "yes, send it", the card stops being read.
- It leaves the risk with the wrong party: the app knows a pattern did not match; only
  the owner is asked to know whether a diagnosis matters.

So: **unsure means local, and the owner is told it happened** (section 5). If he wants the
cloud for that turn, he can ask again in words that carry nothing private - he is in the
conversation and knows what he said.

### 3.2 What this means for rule 1, said plainly in this section rather than in a caveat

**Shape B cannot be built without changing rule 1, and I would not build it even then.**
The reason is not the filter's quality; it is that a brain needs what rule 1 protects: to
answer "did I already reply to Sarah about the offer", it must read the email; to answer
"remind me what the doctor said", it must read the memory. A filter placed after that read
is the only thing between the owner's private life and a third party, and section 4 is
about why that filter cannot be a guarantee. Any version of Shape B that quietly keeps the
email local is not Shape B - it is Shape A.

If the owner still wants it, the honest form is narrower than "cloud brain": a cloud
**drafting** model that never reads memory or email (the local model fetches and passes a
redacted excerpt, one card per excerpt), which is Shape A with a bigger card. That is a
real, buildable feature, and it is the version I would recommend if he wants more cloud
than Shape A.

---

## 4. What a filter provably cannot do

This is the section that must not let a reader believe the filter is a guarantee. A
pattern list can recognise **shapes**:

- API keys and tokens (`_SECRET_PATTERNS` in `jarvis_router`; `looks_like_a_secret`),
- card numbers, IBANs, long digit runs,
- private keys and "BEGIN ... PRIVATE KEY" blocks,
- obvious password lines (`password: ...`, `hunter2`-after-a-colon),
- the owner's own known identifiers *if a list of them is maintained*.

It **cannot** recognise, and no pattern list will:

- **"my sister has been diagnosed with MS"** - a diagnosis has no shape;
- **"we accepted the offer on the house"** - an offer has no shape;
- **the contents of an email** - prose is prose; the private part is the meaning;
- **the name of someone he knows** - names are ordinary words ("Mark", "Grace") and
  appear in every text;
- an address, a school, a workplace, a routine ("I'm out Thursday 2-4"), a debt, a
  relationship, a plan, a medical appointment, a legal matter;
- **anything whose privacy is a fact about the world**, not a fact about the string.

And the asymmetry is already written into the router
(`backend/rebuilt/jarvis_router.py:251`): a false positive sends a turn local, *"which
costs quality, not privacy"* - the two errors are not equal, which is why every uncertain
answer must fall the same way.

**Honest conclusion, so it cannot be read past: a filter that catches 60% is not "60%
safe".** The 40% it misses is exactly the material the owner asked to protect, and it is
missed silently - which is the same disease as the checks this project spent a day
finding, with a privacy consequence instead of a wasted cycle.

---

## 5. The switch, the card, and the off-ramp

These apply to **both** shapes, and they follow the project's existing switch shape
(off by default; on raises one card; off is immediate - as at
`backend/jarvis_scrub.py:36`, *"NO OFF SWITCH, ON PURPOSE"*, which is about a *redactor*
never being switchable off, not about this).

- **Off by default.** A fresh install has no cloud lane and no key. Nothing leaves.
- **Turning it on raises ONE approval card** that names, in plain words, what would leave
  the PC for that shape (Shape A: the question text, one turn at a time. Shape B: the
  conversation, which is why Shape B's card must also say it cannot exclude everything).
  The card is a **risky approval**: Windows Hello on the PC, the screen lock on the phone,
  the same as `quiz_cloud_grade` and every other outbound action.
- **Turning it off is immediate.** No card, like every other "make it stricter" switch.
- **When a turn would have gone to the cloud and did not, the owner is told.** Silence is
  not acceptable, and it is the difference between a privacy feature and a mystery:
  - Shape A, card declined or lane unreachable: the answer comes from the local model and
    says so in one line - *"Answered on this PC: the cloud lane is off / was not
    approved."*
  - Shape B, filter unsure: the turn stays local and the app says, in one line,
    *"Answered on this PC: it could not be checked well enough to send it."* If the reason
    can be named without repeating the private text ("a card number", "a password"), name
    the KIND, never the value.
- **Nothing is retried in the background.** A turn that stayed local is not queued for
  when the owner is not looking.

---

## 6. The spend cap

A cloud brain is metered, and the owner's decision of 2026-09-28 already set the shape for
this in the chatbot driver: **a monthly amount per service, set on the PC; Jarvis stops
that service when the amount is reached, and the card says how much is left.**

For these shapes:

- **Per service, never pooled.** Each cloud lane's cap is its own number; one lane running
  out must not silently move the spend to another.
- **Set on the PC only.** No app can raise it, because raising it is the direction that
  spends money.
- **The card shows the estimate and says "about".** Prices change; the number is an
  estimate from a price list the owner can see and correct.
- **Stops, does not warn and continue.** At the cap the lane is unavailable and the answer
  is the local one, with the one-line note from section 5.
- **Both owner actions from section 2 are prerequisites**: a key, and a cap. A lane with a
  key and no cap is not switched on.

---

## 7. What I could not determine

Stated plainly rather than guessed:

1. **Whether today's `escalate CLOUD` / `critic CLOUD` card already lists the exact words
   that leave.** The patches (`backend/cloud-one-turn.patch`,
   `backend/cloud-say-yes.patch`) exist in the repo, but the card's final wording is
   assembled on the PC. Until that is read there, Shape A's "the card shows the question
   itself" is a requirement, not a verified fact.
2. **Whether every path to the cloud lane passes the router's `inject_memory = False`
   guard.** The guard is computed from the lane rather than passed in
   (`jarvis_router.py:22-23`), which is the right shape, but I did not trace every caller
   in `backend/ollama-direct.patch` and `backend/cloud-one-turn.patch` on the live PC.
3. **How much of a conversation Shape B would actually send.** Without that number its
   cost - and its privacy surface - cannot be stated in tokens or in money.
4. **No recall figure for any filter.** I have not measured a filter on this owner's own
   text, and section 4 deliberately contains no percentage I cannot back. A number here
   would be the most dangerous sentence in the document.
5. **Nothing in this document was run.** There is no code, no test and no measurement
   behind any of it; it is a design, written from the sources above, for the owner to
   decide on.
