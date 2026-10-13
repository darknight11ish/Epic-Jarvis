# Jarvis UI research — the short version

**What this is:** a plain-language summary of everything in
[`UI-CUTTING-EDGE-2026-10-09.md`](UI-CUTTING-EDGE-2026-10-09.md). Same findings,
none of the detail. Five minutes to read.

**Date:** 2026-10-09.

---

## The five things that matter most

### 1. The desktop widget can approve a card you never read — fix this first

The little desktop widget has **one** pair of Approve/Deny buttons and **one** card
slot. If a card gets answered somewhere else — on your phone, or in the Jarvis bar —
the next card slides into the same slot, but the buttons stay exactly where they
were. So a click aimed at the card you were *reading* decides a card you have never
seen.

This is the most serious thing in the whole report, and **no in-flight branch fixes
it**. A written fix already exists but is sitting on an abandoned branch
(`approval-target.js`): it remembers *which* card the buttons belonged to at the
moment you pressed them, and refuses if that card has gone. Lift that file.

There is a second, smaller bug in the same widget: its detail text is cut to two
lines, so it can approve something (like sending an email) without ever showing you
all of it. Fix that with data the card already carries.

**About half a day's work for both. Do it before anything cosmetic.**

### 2. Nine PRs are open right now — and four things I first listed were already fixed

I re-checked every claim against `main` and found **six mistakes in my own first
draft**. Four of them were things the 2026-10-05 audit called broken that are
already fixed:

- `imePadding()` on the phone's root — **fixed**.
- The phone's Settings "jump to" list — **fixed**.
- The 48 dp minimum tap target — **fixed**.
- The chrome accent *is* already derived from your Idle colour — it has been since
  before the audit that said it wasn't.

Also: `settings.css` **does** have high-contrast handling; only `brain.css` lacks it.
So **don't redo any of those.** Part 14 of the full report has the whole list.

The nine open PRs are mostly one kind of work — turning a value that was decided in
code into something you choose (#151 new-chat timer, #157 voice-check bar, #152
captcha window). **That is the flexibility project already in flight.**

### 3. Your two apps share words but not colours — half a day fixes it forever

The desktop and the phone already agree on theme *names* (a test checks that). They
do **not** agree on the theme *values* — those are typed by hand twice, and three of
them had already drifted. Nothing can currently catch the next one.

**The fix:** generate the phone's theme file from the same source as the desktop's,
and add one test that fails when the two disagree. No new tooling, no bundler,
half a day. After that, a whole class of bug is gone permanently.

**If you only do one thing from this report, do this one.**

### 4. Flexibility: the machinery exists, and 15 new settings cost one card, not fifteen

The project already has a settings registry, an "asks first" registry, a limits
table, a menu catalogue and a features list — all with tests that check the two apps
agree. Adding a setting is a **known recipe** with three variants depending on where
the value lives, and three in-flight PRs are worked examples of it.

I found **~42 values still decided in code** — chat retention, approval timeout,
session lengths, poll intervals, list caps, screenshot quality and more. Fifteen of
them are worth adding, and because nine are the same shape they fit in **one "How
long things last" card with eleven rows**.

I also wrote down the **eight things that must never become settings** — the hard
limits, the must-ask list, the PC-only approvals, the never-hide list, the injection
detector's word lists, the event-stream numbers and the Android safety floor. Those
already have tests that fail the build if they change, which is exactly right.

**Bonus:** you already have a settings search box written in your working tree. Land
it — it is what makes the next fifteen settings cheap.

### 5. Text messages: **you have already decided this** (2026-10-09)

Your standing rule says **"Never text messages (SMS), and Jarvis never replies or
sends."** The phone enforces it in **three separate places**, including a
defence-in-depth check whose own comment quotes the rule.

**Since I wrote that, you decided three things, and they are now written down:**

- **Car mode may read texts aloud** — the one exception, recorded in
  [`RULE-FLEXIBILITY.md`](RULE-FLEXIBILITY.md) entry 001, with everything it keeps:
  never replies, never sends; codes hidden before the model *or* the speaker; every
  message is outside text; nothing leaves your devices; off by default.
- **Jarvis may draft a reply and speak it, and you may reply by voice** — "draft it,
  read it back, you say send" and "speak it, then confirm before sending". Entry 002
  makes clear this is **not** a rule relaxation: drafting is not sending.
- **Auto-send is forbidden for good.** Entry 002 says it is *"not a setting that is
  off by default — it is not built at all."* My earlier draft suggested auto-reply to
  named senders as the most defensible version of your request. **You chose
  otherwise, and I was wrong to recommend it.** Do not let a future session
  "helpfully" add it.

**`RULE-FLEXIBILITY.md` also answers a bigger question:** how a rule may be relaxed
at all. Three steps — a written entry naming what is kept, an approval card that
says *which rule* is being relaxed, and a line on "What asks first". Six things are
the floor and can never be relaxed. **Read that file before proposing anything that
touches a rule.**

**Still genuinely open:** reading your whole message history (`READ_SMS`) so threads
can be browsed and searched. It needs its own entry and your decision. My
recommendation is **not to** — it costs you every text you have ever sent or
received, and buys little that car mode and drafting do not already give.

**Also still worth an afternoon:** **KDE Connect** is the only genuinely private,
open-source phone↔PC SMS bridge, and its Windows half is *built* but unproven.

---

## Your Brain, compared to the outside world

**First, some good news.** Your Galaxy graph is better than I assumed. It is about
330 lines of hand-written canvas code, and it **already** does what a graph library
would be hired to do: a deterministic start, a bounded number of cooling steps,
efficient repulsion, redraws coalesced to the animation frame, cached theme colours,
and an 8 ms chunked settle when reduced motion is on.

And the research's clear conclusion: **at ~100 dots, no library beats what you
already have.** The two that look most attractive are traps:

- **tldraw** — its licence forbids production use without a licence key, requires a
  watermark, and says it may transmit usage data to tldraw. Three conflicts at once.
  (Its **accessibility documentation**, though, is the best free design spec in the
  field, and ideas are free.)
- **Neo4j NVL** — proprietary licence limited to Neo4j's own products, and it ships
  an analytics client.

### You already have a rule that decides a lot of this

Your rule is **"nothing is drawn only on the canvas."** That is a hard rule, and it
means a canvas-only graph can never be your main answer — it always needs a list
beside it.

Also: `brain.html` may have exactly **one** `<script src>` (a test enforces it), your
`package.json` has exactly **one** dependency (a build tool), and the CSP forbids
loading anything from the internet. So every option below is designed to need **no
library at all**.

### Ten directions you can choose from — all different, all no-library

**For the visual element (Galaxy):**

| | Direction | What changes | Cost | Best thing about it |
|---|---|---|---|---|
| **A** | **The Constellation** *(my pick)* | Galaxy becomes real DOM/SVG buttons pinned on a ring by kind | days | Makes your own accessibility rule **true by construction**. Keyboard, theming, high-contrast and zero motion all come free |
| **B** | **Frozen Atlas** | Compute the layout once, store the positions, draw instantly | medium (+ a schema change) | The map is **the same every time** — instant, calm, no CPU at rest. (Quartz's trick; fast 3D graph needed a Web Worker and WASM just to escape live physics) |
| **C** | **The Plex** | Never show the whole graph: one fact, its subject above, its siblings below | ~1 week | The known cure for the hairball, and it fits your data (a fact already has a subject, a kind, a date) |
| **D** | **The River** | A timeline: swim lanes by subject, a scrubber, "said again ×3" badges | days | Cheapest of all — uses the "true from" dates you already decided to build |
| **I** | **Matrix / table** | A plain HTML table of what relates to what | days | The **only** fully accessible surface. Unattractive, but this is what a screen reader will actually use |
| **J** | **Search-first Memory** | One box, live results, filter chips | ~1 week | Fastest lookup — but only for Memory, not all of Brain |

**For the other Brain tabs:**

| | Direction | What changes | Cost | Best thing about it |
|---|---|---|---|---|
| **E** | **Work as a waterfall** | Each turn becomes bars on a time axis; two runs side by side | medium | Shows the **approval wait** as a step of its own — the honest answer to "why was that slow?" |
| **F** | **Steps in the answer** | One collapsed line per answer: "What Jarvis did — 4 steps · 12s" | low | The calmest possible version. Nothing animates, nothing is on a canvas |
| **G** | **Calm glance Model tab** | Two plain rows and one sparkline | **low** | Copies `ollama ps` almost verbatim: which card, how much memory, **when it unloads** |
| **H** | **Ledger Trust tab** | One state word at the top, a sparkline of decisions per week, a filterable list | low–med | Turns paragraphs into something you can read in three seconds |

**They are not in competition.** Every mature app offers two or three views of the
same data, and the research's one clear finding is that no single view wins. The
mistake would be to pick one and delete the others.

### Four things that look good and are a bad idea

1. **A graph that animates while Jarvis works.** It fights your "calm, never busy"
   rule and reduced-motion in the same breath; it uses the graphics card the model
   needs; and it makes you read *position* as meaning when position is just an
   artefact of the maths.
2. **tldraw, NVL, or Cosmograph as a library** — licence, watermark, telemetry, or a
   cloud client in the dependency list.
3. **Running a Langfuse/Phoenix-style observability stack beside Jarvis.** It means a
   second server, a second database, and a second place your private text lives —
   outside the encrypted store. Also Phoenix is not open source and Langfuse is open
   core. Read their designs; don't run them.
4. **A single "risk score" for Trust.** Your trust state is several different things,
   and one number destroys the information you need to decide. It is also
   shame-adjacent, which you have already ruled out for streaks.

---

## What I would do, in order

1. **Fix the two widget approval bugs.** Half a day. Nothing else matters if a click
   can decide the wrong card.
2. **One source of truth for the theme colours** + the test that guards it. Half a
   day. Retires a whole class of bug.
3. **Pin Galaxy as DOM/SVG (A).** Days, no library, no rule change — and it turns
   your accessibility rule into a fact.
4. **Add the table view (I)** as a second way to see the same data.
5. **The calm Model tab (G).** Lowest risk, lowest cost, over data you already read.
6. **The trace (E + F)**, once you have span data.
7. **Merge the three flexibility PRs**, then land the search box and the one "How
   long things last" card.

---

## The decisions that are yours

**1. Brain's visual element.** Which to try first?

- **A — The DOM/SVG constellation** *(my pick)* — real buttons pinned by kind;
  keyboard, theming, high-contrast and zero motion all come free.
- **I — The plain table view** — the only fully accessible surface; unattractive,
  but it is what a screen reader will actually use.
- **D — The River (timeline)** — the quickest visible win; uses the "true from"
  dates you already decided to build.

**2. Your whole message history.** Should Jarvis be able to browse and search every
text you have ever sent or received?

- **No, leave it** *(recommended)* — car mode and drafting already cover reading and
  replying; this costs you the full history of every message for little gain.
- **Yes, and write the rule entry first** — it is a real reversal of the SMS rule and
  needs its own `RULE-FLEXIBILITY.md` entry plus your decision.

**3. Anything not in this report.** Say the word and I will research it.

*(The text-message question above is closed — you decided it on 2026-10-09. Auto-send
is forbidden and must not be built.)*

---

## Where the detail is

| Want | Read |
|---|---|
| The whole thing | [UI-CUTTING-EDGE-2026-10-09.md](UI-CUTTING-EDGE-2026-10-09.md) |
| What to do, in order | Part 13 (the plan) |
| The open PRs and my corrections | Part 14 |
| Adding flexibility | Part 15 |
| Text messages | Part 16 |
| Brain vs the outside world | Part 17 — rules in 17.2, the menu in 17.4 |
| How sure I am of each claim | Part 18 |
