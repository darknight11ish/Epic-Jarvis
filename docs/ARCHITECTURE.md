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
Android companion reached over a private network (Tailscale, or NordVPN
Meshnet). A Python HTTP server does the work;
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
2. **No public tunnel, ever.** Reachability is a private, encrypted
   device-to-device network: Tailscale, or NordVPN Meshnet. Both give each
   device an address in `100.64.0.0/10` that only the owner's own devices
   can reach, and neither is a public tunnel. The desktop's bind-address
   check accepts exactly that range (`validate_bind_address`, commands.rs),
   and the phone allows plain HTTP only to loopback, `*.ts.net` and `*.nord`
   names (`network_security_config.xml`). A non-loopback bind with no
   `HUD_TOKEN` refuses to start — `SystemExit(2)`, not a warning.

   **The other end too: both apps talk only to a Jarvis on the owner's own
   networks** (the owner's decision, 2026-09-26, after a Gemini audit
   finding). Until then the desktop's Settings checked only the SHAPE of the
   Jarvis address (`validate_base`), and the phone checked nothing, so
   `https://abc.ngrok-free.app` was accepted and the pairing token went
   through a public tunnel with every request. Now an address is accepted
   only on this PC, the home network, Tailscale or NordVPN Meshnet, **by the
   backend's own rule** - `jarvis_local_http._own_network`, the one that
   already limits plain http:// to Home Assistant and the calendar - and
   refused otherwise, https:// included (this is about where the token goes,
   not whether the line is scrambled):

   | allowed | refused |
   |---|---|
   | this PC: `localhost`, 127.x.x.x, `::1` | anything else, e.g. `8.8.8.8`, `0.0.0.0` |
   | home network: 10.x, 172.16-31.x, 192.168.x, IPv6 `fc00::/7`, names ending `.local`, `.lan`, `.home.arpa`, and a single word with no dot (`nas`) | link-local 169.254.x.x and `fe80::` (not on the backend's list either) |
   | Tailscale and NordVPN Meshnet: 100.64.0.0 to 100.127.255.255, `fd7a:115c:a1e0::/48`, names ending `.ts.net` or `.nord` | 100.63.x and 100.128.x (outside that block), 172.15.x and 172.32.x, any other name: `*.ngrok-free.app`, `*.trycloudflare.com`, `localhost.evil.com`, `10.0.0.1.nip.io` |

   Judged by spelling alone, no DNS. A number written the old way
   (`3232235777`) is judged as the address it dials, and both the address as
   written and the host each app's own HTTP library parses must pass, so a
   user name in the address (`http://127.0.0.1@evil.com`) cannot fool it.
   Refused in one sentence, the same on both apps: *"Jarvis's address X is
   not on your own networks, so this app will not send your pairing key
   there: use this PC (localhost), your home network (...), Tailscale (...)
   or NordVPN Meshnet (...)."* An address saved before the rule (or set in
   `JARVIS_HUD_BASE`) is not used, and nothing is used in its place (owner,
   2026-09-26): the desktop does nothing over the network - no chat, no
   reads, no requests to this PC instead, no backend started - until an
   allowed address is entered. Every request to Jarvis is refused with that
   sentence (`jarvis_headers` asks `require_base_allowed` first; the base is
   empty, so a request cannot be built either), the event stream stays
   offline with it as the reason, and Settings shows it in red
   (`jarvis_base`/`base_from`, `base_problem`, `stream.rs`); the phone treats it as no address at all, opens the pairing
   screen with the sentence, and says it wherever it would say any other
   connection failure (`OwnNetwork.kt`, `ClientSettings.baseUrl`). One case
   table, `tools/gen_own_network_cases.py`, made from the backend's real
   code, is read by the Rust tests, `tests/own-network.mjs` and
   `OwnNetworkTest`; `backend/test_own_network_cases.py` fails when it is
   stale. Debatable things the backend allows, kept for parity: single-word
   names (a home router answers them, but a DNS search domain could too),
   `.lan` and `.home.arpa`, and the whole 100.64.0.0/10 block (also used by
   some mobile carriers' own networks, not only Tailscale and Meshnet).
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

The smart-home card is the same test, applied (the owner's decision of
2026-09-25, after the creativity audit): "turn off the kitchen, hall and
bedroom lights" is ONE card that lists every device and its exact request -
at most ten, never cut - and a yes sends exactly those and nothing else
(`jarvis_home.plan_services`; the plan carries a digest of its requests and
`run()` sends nothing if they changed). It grants nothing for later. Locks,
alarms, doors, covers and the other entities in `jarvis_home._stands_alone`
are never part of such a set: each still gets a card of its own.

**A standing setting the owner chose, for one named kind of thing, is not an
approve-all either - the same test as the Obsidian daily note at `auto`**
(the owner's decisions of 2026-09-26, after the approvals audit). Two such
settings exist, each off unless the owner turns it on with a card, each
immediate to turn off, and neither raises a card that something else answers:
- **"Lights, plugs and fans without a card"** (`jarvis_asks_first.py`,
  JARVIS-API §33): only `light`, `switch` and `fan` on, off or toggle; only
  devices the owner's own newest words named; never in a turn shaped by
  outside text; never a lock, door, alarm, cover, gate, valve, camera,
  scene, script or button (`jarvis_home.everyday_problem`). `home_control`
  stays in `NEEDS_A_PERSON`; everything else is its card as before.
- **Loosening one line of "What asks first"** (JARVIS-API §32): only seven
  actions (reading the owner's own calendar, email, notes and home status;
  the three note writes), on the PC only, one card plus Windows Hello each.
  The backend refuses anything else - NEEDS_A_PERSON's actions and the
  hard-limit list included.
No approval card is ever answered for the owner, and no control approves
more than one card.

It also means Jarvis never drives its own approval surfaces. "Control the
computer" refuses every window of Jarvis's own, and "control the phone"
stops before any tap while a Jarvis app is in front (security audit M3,
2026-09-25): one card approving a click on another card's Approve button
would be an approve-all by the back door. `backend/README.md`, "The PC-side
security audit's fixes".

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
outside text - a reading tool ran, the conversation is tainted, the
newest message was not typed or said by the owner (pasted, shared, from the
clipboard, a picture's caption, or with no tag at all - only `typed` and
`voice` are the owner's own words), or the app sent a `system` message of
its own (security audit M1, 2026-09-25) - a note write
(Obsidian, Logseq, Joplin) is put to the same gate as
`write_notes_after_outside_text`, tier `ask`, and runs only on a person's
yes, like `NEEDS_A_PERSON`. Not a second approval path: the same gate, the
same card, one more line on it saying why. `backend/README.md`, "Outside
text in the tool loop". "Tainted" survives a backend restart (security
review G1, 2026-09-26): a conversation the backend has not met since it
started counts as tainted when the request carries earlier turns, unless
the chat history database holds all of them and none read outside text
(`jarvis_chat_log._seed`). It fails closed: an error, history off, or a gap
means tainted.

One answer raises at most five cards (`jarvis_agent.CARDS_PER_TURN`; the owner confirmed five,
2026-09-25). A card for several smart-home devices (section 2) counts once. After that, a call that would ask is refused before it is
put to anyone, and the answer says so. A flood of cards is how a planted
instruction tries to wear a person into pressing Approve without reading.
The limit is a refusal, never a grant. `backend/README.md`, "The approval
gate, tightened".

**What changed on 2026-09-26** (the approvals audit,
`docs/APPROVALS-AUDIT-2026-09-26.md`; the owner's four decisions): a plain
repeating alarm, reminder or standby schedule has no card (the briefing and
"tell me when" keep `schedule_repeat`); a light, plug or fan the owner named
can run with no card when the owner's lights setting is on (above,
`jarvis_agent` LIGHTS_WITHOUT_CARD); an everyday fact about someone the owner
mentions saves without a memory card, and once saved it is a normal fact
everywhere - it may be read aloud and does not make a web search ask
(section 5, `jarvis_sensitive.topic()`); and the "What asks first"
page in both apps shows every action's tier, makes one stricter at once, and
- on the PC only - loosens one of seven with a card that needs Windows Hello
(`jarvis_owner_check.PC_ONLY_ACTIONS`). Each one is a place where no card is
RAISED, by the owner's choice; none is a card answered for them.

**Stopping is never gated.** Stop, Pause and "Stop everything"
(`/api/task/stop`, `/api/task/pause`, `/api/stop_all`) need no card and are
never held on a stale event stream or by a waiting card: rule 4 blocks
ACTING on a stale stream, and these only make Jarvis do less. The desktop's
Stop everything hotkey also works while App lock is on.
None of them approves, denies, resumes or starts anything - Resume is the
one task control that raises a card. "Stop everything" also refuses every
further tool call of the answer being written, even one whose card is
approved after the press: a stop wins over an approval of the earlier
question.

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

### A known limit: a program already on the PC

Written down 2026-09-25 (the Muse audit, `docs/COMPETITORS-MUSE-2026-09-25.md`).
The Windows Hello check before a risky approval ("Windows Hello for
approvals", `jarvis-desktop/src-tauri/src/lock.rs`) is made by the desktop
app. The backend's `POST /api/approve` asks only for the pairing token, and
any program running as the owner can read that token from Credential
Manager (`backend/README.md`, the token store). So a harmful program already
on the PC could approve a card without meeting Windows Hello.

Corrected 2026-09-25, while designing the fix (`docs/APPROVAL-GAP-DESIGN.md`).
This paragraph used to say the phone was "not affected in the same way".
That was wrong in two ways:
- **The phone uses the same pairing token as the PC.** There is only one
  (`jarvis_token_store.py show` prints it for typing into the phone). So a
  program on the PC can approve while pretending to be the phone. The
  phone's fingerprint check is made inside the phone app, and the backend
  never sees it, just like the desktop's.
- **`/api/approve` is not the only way in.** The gate waits for its row in
  `approvals.db` (in `~/.openjarvis/`) to say "approved"
  (`gate-outcome.patch`), and a program running as the owner can write that
  file directly.

A program written specifically to attack Jarvis, running as the owner, can
also change Jarvis's own files. No fix inside the owner's Windows account
can stop that. The design says what a fix can and cannot stop.

**Step 1 is built (2026-09-25, the owner's decisions; `owner-check.patch`,
`backend/jarvis_owner_check.py`, `backend/README.md` "The approval gap,
step 1").** What it closes:
- **A risky approval from this PC needs Windows Hello at the backend.**
  `POST /api/approve` asks Windows Hello itself - the prompt shows the
  card's own title - before it accepts a risky card (the phone's rule, one
  definition in three places, `tools/gen_risky_approval_cases.py`) that
  comes from this PC: loopback, the PC's own addresses, or anything that
  cannot be placed. So reading the token and posting `/api/approve`, or
  pretending to be the phone through the PC's own Tailscale address, meets
  a prompt nobody asked for. A PC with no Windows Hello refuses risky
  approvals ("no lock, no risky approval").
- **An "approved" row counts only with the running backend's stamp.** The
  gate believes "approved" only when this backend process accepted the
  approval through its own `/api/approve` and stamped it with a secret kept
  only in its memory. Writing "approved" into `approvals.db`, or calling
  `jarvis_gate.decide()` from another program, is refused.
- **The desktop asks once, not twice**: when `/api/version` says
  `capabilities.owner_check: "backend"` and the desktop talks to the
  backend on loopback, it leaves the risky cards to the backend's prompt.

What is **still open**, said plainly:
- A card that is **not risky** (local, undoable, not rushed) can still be
  approved by a program holding the token - the "Risky only" rule.
- **Another device** on the owner's Tailscale or Meshnet network holding a
  stolen token is taken for the phone and not asked on the PC. Step 2 (a
  phone key per risky approval, with "more devices") closes that.
- **A program written to attack Jarvis** can still edit its files or take
  over its running process (above). Nothing inside the owner's Windows
  account can stop that.
- The Windows side is **untested on Windows** until the half-day test in
  `backend/README.md`: that the backend's prompt comes to the front, that
  the PC calling its own Tailscale address counts as "this PC", and that
  the gate's wait runs in the same process as the web server. Each fails
  closed if wrong (risky approvals from the PC are refused).

### The notification contract — `notice`

A waiting approval has to be readable on a phone without any of the payload
leaving the machine's control. That is not done by redacting the row. It is
done by **generating** the text from tables we wrote.

`jarvis_gate.notice_for(item)` reads exactly two things off an approval row —
`action`, and whether `raised` is truthy. It reads no `detail`, no `prompt`,
and nothing inside `raised`. Every word it returns comes from `_RISK` and from
`jarvis_card_words.TITLES` (a table of plain phrases, one per action, written
by us - `backend/jarvis_card_words.py`). It is attached to every
`/api/pending` row as `notice`, and allowed through the SSE doorbell by name.

```
title        "Jarvis wants to send an email"   from jarvis_card_words.TITLES;
             an action with no phrase: 'Jarvis wants your OK for "<name>"'
body         why it matters, that something tried to hurry you if `raised`
             is set, and that nothing has happened yet
weight       "heavy" | "normal"
deny_ok      true    — always
approve_ok   false   — always
```

**Three rules for any client reading this.**

1. **`weight: "heavy"` interrupts; `"normal"` arrives quietly.** Heavy is
   earned by any one of three things: the action cannot be undone, it leaves
   this machine, or outside text pushed the tier up. Three named reasons a
   person can argue with, not a score nobody can. Both weights get a
   notification on both apps - heavy with a sound, normal silently (the
   phone's quiet channel; a Windows toast with `<audio silent="true"/>`).
   Until 2026-09-25 the PC showed none at all for a normal card, which then
   sat unseen and ran out of time (the creativity audit).

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

### One card on every screen

Decided 2026-09-25 after the creativity audit (`docs/CREATIVITY-AUDIT-2026-09-25.md`,
items 2, 4 and 8), which found the card speaking three dialects: the Jarvis
bar showed the code name (`switch_model`), the widget "APPROVAL REQUIRED",
the phone "Jarvis wants to learning enable", and Approve and Deny swapped
places between screens. Presentation only - no approval logic changed.

- **The same words everywhere.** The title is always `notice.title`
  (`jarvis_card_words.TITLES`, above), under the label "Needs your OK". The
  Jarvis bar, the widget, the HUD page, the phone's card, its home-screen
  widget, both apps' notifications and the fingerprint prompt all show it.
  `tools/gen_card_words_cases.py` writes the words into one file that
  `backend/test_card_words.py`, the desktop's `tests/card-words.mjs`, the
  Rust `stream.rs` tests and the phone's `CardWordsContractTest` all read.
- **The same button order everywhere: Deny on the left, Approve on the
  right.** Why this order: Android's own dialogs put the confirming button
  on the right; the phone's card already approves with a swipe to the right
  and denies with one to the left, so the buttons now sit where the gesture
  goes; the Jarvis bar, the desktop's main card, already had it; and the
  first button the keyboard's Tab reaches is the safe one. Notifications are
  unchanged: Deny only, never Approve (rule 2 above).
- **"Open the card"** wherever a button raises one. Settings and the Brain on
  the PC, and every phone screen but Home, show one line while any card
  waits, with a button that goes to it (the Jarvis bar on the PC, behind App
  lock; Home on the phone). One line per window rather than a link under each
  button, so a button added later cannot miss it. It decides nothing.
- **Voice says a card is waiting, and what happened.** A spoken question that
  waits on a card hears "I need your OK for that. There's a card on your
  screen.", then "Approved. Carrying on.", "OK, I won't do that." or "That
  card timed out, so nothing was done." - from `: jarvis-status` lines the PC
  sends (JARVIS-API §4). Fixed words, never the card's. **Never
  approve-by-voice**: the voice check cannot tell a recording from the owner,
  so a spoken "yes" answers nothing. For the same reason no sentence says
  "until you say yes" any more ("until you approve the card").

---

## 4. The egress boundary

These lanes leave the machine. Nothing else may.

| lane | what may go | enforced by |
|---|---|---|
| **cloud model** | user-role turns only - and, with `cloud-one-turn.patch`, only the **newest** one, because the clients now send the conversation so far | a role filter, re-derived on **every** hop of the degrade loop; the newest-turn cut in `_open` |
| **ntfy push** | text generated from our own tables, never payload, never while tainted | `notice_for` (`_safe_detail` where there is no action name) + `taint_active()` |
| **research** | enumerated search terms, per approved plan | `jarvis_research.plan/run` |
| **the owner's own accounts** - calendar, email, Home Assistant, each only when its settings are filled in on the PC | one request (or one small batch) per plan: to the calendar the owner set up - their CalDAV server with the time range, **or, since 2026-09-25, Google (`calendar.google.com`) through the calendar's private link**, which asks for the whole calendar and has the days picked out on the PC; to their IMAP server; to their Home Assistant. The password, token or private link goes only to the host it belongs to; the private link is also kept off every card, result, error and the log (`test_calendar_link.py`) | each module's `plan()`/`run()` through the gate (`jarvis_calendar`, `jarvis_email`, `jarvis_home`); `jarvis_local_http.plain_http_problem` (plain `http://` only inside the owner's own networks); each module's redirect handler (`_RefuseRedirect`, and for the private link `_FeedRedirect`: https on the same host or between Google's calendar hosts only) |
| **sending email** (2026-09-25, the owner's decision after the Muse audit) | ONE plain-text email per approval card, from the owner's own account (the address email reading uses), to at most 10 people in To and Cc (no Bcc), with the subject and text the card showed word for word - at most 2,500 characters, no attachments - and the owner's password, to their own sending server only (`smtp.X` for `imap.X`, e.g. `smtp.gmail.com`, or `JARVIS_SMTP_HOST`), inside SSL/TLS or STARTTLS with the certificate checked; unencrypted only to this PC or the owner's own networks. Written by the model on this PC only (rule 1) | `jarvis_email_send.plan/run` (no socket in `plan`; addresses, caps and invisible characters checked; a plan whose fingerprint or settings changed after its card is refused; never retried; the password never in a plan, card, result, error, event or the log) + `jarvis_agent._one_call` (`send_email` in `NEEDS_A_PERSON`: only a person's yes sends; no card unless the tier is `ask` and the turn's model is on this PC; the card says at the top when outside text shaped the turn; `CARDS_PER_TURN`) |
| **web search** (2026-09-25) | ONE search's words (at most 300 characters), to the ONE provider the owner chose - SearXNG on the owner's own machine (which asks other engines), DuckDuckGo, Exa, Tavily or Brave - and, for the last three, the owner's key to that service only. Never words that look like a password or key. A card with the exact words whenever the conversation has read email, files, notes, saved memories or other outside text, or the owner chose "Ask before every web search" | `jarvis_search.plan/run` (no socket in `plan`, secret refusal, one provider, no fallback, redirects refused, answers capped) + `jarvis_agent._web_search_call` (when it asks; only a person's yes after that) |

**Sending email, in one sentence each** (the owner's decision of 2026-09-25,
`CLAUDE.md`; docs/JARVIS-API.md section 26). What it sends: one email, exactly
as its card showed it - From, To, Cc, Subject and every word - and nothing
else of the owner's. Where: to the owner's own sending server, logged in with
the account email reading already uses. When it asks: always - every email is
its own card under gate action `send_email` (tier `ask`, and nothing is sent
on any other tier), there is no "always allow", and a card raised after
outside text starts by saying so ("This conversation read outside text ...
check that sending it was your idea"). Rule 1 holds because the email can
only be written in a turn answered by the model on this PC: the tool is never
offered to a cloud lane, and `_one_call` refuses it again, before any card,
when the turn's model is not on this PC. The desktop's widget never approves
an email - its Approve opens the Jarvis bar, where the whole email is shown
word for word (never as Markdown) - and every lock screen, notification and
the widget under App lock show only the notice, "Jarvis wants to send an email".
**"Tell me when" uses this row, not a new one** (2026-09-25,
`jarvis_tellme.py`, JARVIS-API §30): once its ONE card is approved, it
looks every 5 minutes at the From line of new mail (with PEEK) or every
minute at ONE named Home Assistant device, each look through the gate as
`email_read` / `home_read` at tier `auto` only. The name it watches for
stays on this PC (it is matched here, never sent to the mail server), and
a match only rings the owner's own apps over the existing link, with words
built from the owner's own - no telephone call, no outside notification
service. **Since 2026-09-26 it is instant, still on this row**: while an
email watch is on, ONE connection to the same IMAP server stays open and
the server says when mail arrives (IMAP IDLE; LOGIN, CAPABILITY, EXAMINE,
IDLE, DONE and LOGOUT only - nothing is fetched over it). A nudge runs the
ordinary look above, through the gate. The connection is itself put to the
gate as `email_read` each time it opens, closes on Standby and on Stop
everything, and falls back to the 5-minute looks when it drops. "Tell me if
Alex hasn't replied by Friday" is the same look, told when nothing matched.
**Every connection to the owner's mail server checks its certificate and
name since 2026-09-26** (`jarvis_email.tls_context`): Python's `imaplib`
did neither by default, so the email reads and the watch's looks
encrypted to whoever answered. A mail program on this PC itself (a bridge
such as Proton Mail Bridge, with a home-made certificate) is the one
exception; its traffic never leaves the PC.

**"Folders Jarvis may look in" adds no lane** (2026-09-26,
`jarvis_documents.py`, JARVIS-API §35): finding, searching and reading the
owner's own files in the folders listed on the PC, and bringing in a Notion
export, all stay on this PC. PDF and Word files are turned into text by
MarkItDown's document parts only (never its audio part, which sends sound to
Google, or its YouTube part), in a separate program with no passwords in its
environment; the text goes only to the model on this PC.

The owner's-own-accounts row was not in this table until 2026-09-25, although those reads
already left the machine; it was written down when the Google Calendar link
was added. Their settings are environment variables on the PC, and neither
app has a screen to enter them. For the private calendar link that is on
purpose (2026-09-25): a link typed on the phone would be one more place to
keep a password safe. Only the morning briefing's settings line says which
calendar is read ("your Google Calendar (private link)"), in both apps.

**Which of these lanes is on right now is listed by code, in both apps**
(the Muse audit, 2026-09-25): "What Jarvis can reach" (`GET /api/reach`,
`backend/jarvis_reach.py`, JARVIS-API.md section 24) is written from the
same settings this table's code reads - `[tools].enabled`, the tiers, the
accounts' environment variables, the web search settings, the cloud lanes -
never by the model, and names hosts only, never a key or a link. "What can
you reach?" is answered from it without the model (`jarvis_quick.py`).

**Email text has its one-time codes and sign-in links hidden** before the
model, the apps, the briefing or a log see it (`backend/jarvis_mail_mask.py`,
JARVIS-API.md section 25): the most valuable thing a planted instruction
could try to get into a web search's words. A pattern list, so not
everything is caught; what it misses is written down there.

**Web search, in one sentence each** (the owner's decisions of 2026-09-25,
`CLAUDE.md`; docs/JARVIS-API.md section 23). What it sends: the search words
the model chose, and nothing else of the owner's. Where: to the provider
chosen in Settings (SearXNG at `http://127.0.0.1:8888` by default, reached
with no proxy; its address may only be this PC or the owner's own networks)
- never to another one quietly: when the chosen one is down, the answer says
so and offers to switch. When it asks: a search straight from the owner's
own typed or said question, in a conversation that has read nothing from
outside, runs without a card - and since the owner's decision after the
creativity audit (2026-09-25) that is still true when a pinned or recalled
saved fact is in the turn, unless the fact is sensitive or the search words
repeat it; any other search is a card showing its exact words (gate action
`search_the_web`, `ask`), and the results themselves are outside text that
marks the rest of the conversation. Rule 1 holds because private text can
only reach the search words after it has been read - from then on every
search is a card - with one bounded exception the owner chose: a saved fact
that is not sensitive reaches the words unasked only if it is REWORDED
(its words, numbers and names are checked; "vegetarian" saved and
"meat-free" searched is not caught). Sensitive facts always ask.

The cloud filter deserves a note because it was broken in the least obvious
way: it ran once, above the degrade loop, and the loop could go cloud → local
→ cloud. It now re-derives from the lane it is **about to call**. The loop's
comment claims "downward only" — that is a contract with `jarvis_router` which
the loop never checked, so the fix does not depend on it holding.

The **local model is also egress** if `OLLAMA_URL` does not point at this
machine, or if the "local" model is one of Ollama's cloud models (`-cloud` /
`:cloud`: reached through the Ollama on this PC, answered on ollama.com). The
learner checks both before it runs, and since 2026-09-25 (security audit H1)
so does the chat path: `jarvis_agent.run_local_turn` sends such a model
nothing and says why, and `jarvis_router.choose` gives it the gate
`cloud_model` instead of "stays on this machine". Anything else that talks to
Ollama must do the same. Not yet: the model switch and install routes (the
owner's `jarvis_models.py`) do not refuse a cloud model's name.

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

**"Always keep in mind": a few pinned facts, read with every question**
(the owner's decision, 2026-09-24; `memory-profile.patch`,
`rebuilt/jarvis_memory.py` `pin()` / `profile()` / `with_profile()`,
docs/JARVIS-API.md §4 and §6 `/api/memory/profile`). Search only finds facts
that share words or meaning with the question, so "the owner is
vegetarian" was missing from "what should I cook tonight?". The owner can
pin facts; every local chat turn then starts the quoted FACTS block with
them, under their own heading, before the searched facts, and a pinned fact
the search also found is not repeated.

```
profile     fact_id INTEGER PRIMARY KEY, added REAL, how TEXT ("tap")
            IDS ONLY. The words are read from `facts`, word for word -
            never copied, summarised or rewritten (see the rule below
            about compressing facts). Joined to the CURRENT facts, not
            erased: a pinned fact that is forgotten, corrected, reworded
            (which supersedes it), runs out or is erased leaves the list by
            itself. Unpin deletes the pin row, never the fact.
```

- **A hard cap: the pinned facts' words may add up to 1,200 characters**
  (`PROFILE_LIMIT`, about 300 tokens - some 7% of the 4,096-token context
  the primary model runs with today, re-read every turn). A pin that would
  pass it is refused in words: "That would make the list too long - unpin
  something first". The check and the write are one transaction.
- **Only the owner's own tap pins** - a fact they can see, no approval card
  (like Forget), no confirm, held on a stale link in both apps. That is also
  the only way a SENSITIVE fact gets on the list; nothing suggests or adds
  one. Sensitive pinned facts still count in `injected_sensitive`, so the
  answer stays on screen as for any other.
- **Recall rules unchanged around it:** `JARVIS_MEMORY_K=0` is no memory at
  all, pinned facts included; a turn that leaves the local lane drops the
  whole block; `keep_rules_first` keeps the Jarvis rules at position 0 on a
  first question. A pinned fact never gets a "retire this?" card from
  answer marks - it is in every answer, so its marks say nothing about it.
- The idea is Letta's, MIRIX's and MemoryOS's "core memory"
  (docs/RESEARCH-2026-09-24.md §3 item 2), without their rewriting: no
  model can add to, merge or summarise the list.

**"Who is my sister?": the entity layer** (memory wave 3, 2026-09-25;
`rebuilt/jarvis_memory.py` "The entity layer", `memory-entities.patch`,
`jarvis_entities.py`, docs/JARVIS-API.md §6 `/api/memory/entities`). Words
and meaning cannot connect "my sister's wedding" to "Priya's wedding is in
Lisbon"; a saved fact can - "Owner's sister is called Priya". So every saved
fact is linked to the people, pets, places and things it names, and the word
the owner uses for one ("sister") becomes an alias of that name.

```
entities          id, name, kind, created, merged_into   (a merge is a pointer)
entity_aliases    alias, entity_id, fact_id   (fact_id = the fact that taught it;
                                               NULL = the name itself)
fact_entities     fact_id, entity_id
entity_merge_asks a, b, proposal_id, state    ("are these the same?", once per pair)
```

The rules, each one enforced where the rows are written:

- **Links come from SAVED facts only** - `add()` and `edit()`, after every
  check the fact already passed - never from the conversation. Nothing else
  writes them, so the layer adds no new way to poison memory.
- **A link can only ADD a candidate to recall.** Nothing in the layer
  retires, edits, hides or reorders a fact.
- **Grounded or dropped.** Every name and alias is in its fact word for
  word, whoever found it. An alias is kept only with a name from the SAME
  fact, and records that fact's id. Forget and a correction take the fact's
  links and the aliases it taught; **Erase** also deletes every name no
  other fact still says, and wipes (and turns down) any "are these the
  same?" card that showed one - inside the erase's own transaction, so the
  file scrub zeroes those bytes too.
- **Merging is the owner's call, one pair at a time.** Only an exact match
  after normalising is one entry by itself. A likely typo (Graphiti's
  thresholds: both names specific enough, 90% of three-letter chunks
  shared) raises ONE card per pair, ever, in the ordinary review queue
  (`source: "entity_merge"`); yes joins the pair with a pointer, no is
  remembered and never asked again. There is no list form.
- **Found without a model**, on every save: capitalised names, and "my
  sister is called Priya" / "my brother Arjun" / "Mario is my manager" -
  the relation words are English only. An optional local-model pass
  (`jarvis_entities.py`, one call per learner pass, loopback and not-cloud
  checks) is **off** by default and unmeasured.
- **Recall** (`jarvis_past.recall` -> `search(entities=True)`): the
  question's words are looked up in the alias table ("sister's" folds to
  "sister"), the full names are added to the question for word and meaning
  search, and the facts linked to them are a third list in the RRF fusion.
  No model call; `k` and both floors unchanged; an alias that names more
  than two entries says nothing and is ignored. A temporary chat still
  recalls nothing, and the pinned list is unchanged. `JARVIS_MEMORY_ENTITIES=0`
  turns it off.
- **The apps:** the desktop shows the names under each fact, "About
  <name>" (that entry's facts, word for word - no summary) and the merge
  card; the phone shows none of it (§8).

**A temporary chat uses and makes no memory** (the owner's decision,
2026-09-25; `temporary-chat.patch`, docs/JARVIS-API.md §4 and §18.1). A
request with `"temporary": true` recalls nothing - no search, no pinned
list, not even the older word list; the FACTS block is replaced by one
fixed line telling the model it is a temporary chat - is never offered to
the learner (no proposal, no "Remember:", no automatic save), and is not
kept in the chat history. Everything else about the turn is unchanged:
tools, the gate and its cards, local-first routing. It needs no card, on or
off, because it can only make a turn stricter; it is offered only when the
running server says it has it (`capabilities.temporary_chat`), and
`X-Jarvis-Route` says `"temporary": true` so an app never has to assume.
Its live message still goes in the chat log's in-memory registry - a hash,
never the words - so the "read outside text" mark keeps working, under the
provenance `"temporary"`, which automatic learning always turns into a card.

**"Used in this answer" reads facts by id, and only when asked** (2026-09-25,
`GET /api/memory/used`, `rebuilt/jarvis_memory.py` `used_view()`). The
route header and the `memory_saved` event stay ids only (§6: every event is
a doorbell); an app reads the words of those few facts behind the pairing
token when the owner opens "Used 2 memories" or "Jarvis remembered 2
things", hidden like every memory list, with Forget (and on the desktop
"Erase the words") one fact at a time.

**"Current" is `valid_to IS NULL OR valid_to > now`, never `valid_to IS
NULL`.** A lease that ends in December is true today. Three places computed
this and one of them got it wrong, directly below a line that got it right.
The writers had it wrong too until 2026-09-26: `retire()`,
`add(supersedes=...)` and `edit()` matched `valid_to IS NULL` only, so a
fact that ends later could never be forgotten, corrected, reworded or
retired by a "stop using this fact?" card (`test_memory_true_from.py`, the
checks marked "the bug"). One copy of the old rule is still in the owner's
own `jarvis_extract._accept` (memory-safety.patch): a correction CARD
aimed at a fact that ends later is saved without retiring it - a later
patch to that file, not done here.

**Memory ideas 1-4** (the owner's decision of 2026-09-26, after
docs/MEMORY-RESEARCH-2026-09-26.md; backend/README.md "Memory ideas 1-4"
has the self-test numbers; docs/JARVIS-API.md §34):

```
fact_repeats  fact_id, said_at, how ("typed" | "voice")   "said again" - NO WORDS
```

- **The re-ranker** (idea 1). Chat recall only (`jarvis_past.recall` ->
  `search(rerank=True)`): the top 20 facts that pass every filter are
  re-ordered by a small cross-encoder on the processor
  (`Xenova/ms-marco-MiniLM-L-6-v2` through fastembed, Apache-2.0, English
  only) before the first `k` go to the model. It only re-orders - no fact
  added, `k` and both floors unchanged - and never touches `find_one()`,
  corrections or anything that writes. **Off by default** (2026-09-26: a
  memory change is kept only once the PC's self-test shows it helps);
  `JARVIS_MEMORY_RERANK=1` turns it on, and `eval_memory.py` measures it
  whatever the setting. When on: loaded on a background thread; each chat's
  recall waits for it up to 1.5 s; until it is ready, if it cannot load, or
  if one question takes longer than 1.5 s, recall is exactly what it was
  (said once, in the audit log and `status()["reranker"]`). Its gain is
  measured only on the PC: the model cannot download in the container.
- **"Said again"** (idea 3). When the owner says a fact Jarvis already
  keeps, the learner's proposal is still dropped, and one row is kept: the
  fact's id, when the PC saw the turn arrive, typed or voice. Only from the
  owner's own live words, by automatic learning's own checks (typed or
  strictly checked voice, seen live, no outside text read, every word said
  and no "not" dropped), only after the fact was saved, one row per turn
  however often the learner re-reads it. Nothing reads the count to decide
  anything, so it can never make a fact harder to forget, correct or erase;
  Erase keeps the rows (ids and dates, like the fact's own dates). Shown as
  "said again 3 times" in both apps' "Saved automatically" list (the one
  list both apps read from a shipped module; the full memory list is the
  owner's `jarvis_hud` route and does not carry it yet).
- **Real "true from" dates** (idea 4). `add()` sets `valid_from` from the
  owner's own words when they say when something changed ("I moved to Leeds
  in January", told in March -> 1 January; `true_from()`: fixed English
  rules, one date only, a change word, nothing that points at the future,
  NEVER a future date), marked `meta.true_from = "said"`. A correction
  with such a date ends the old fact on that date. **Older news never
  replaces newer news** (Graphiti's rule): when both facts' dates come from
  the owner's words and the correction's is earlier, the old fact stays in
  use and the correction is stored as history, true until the newer one
  began, linked to it by `retired_by` (so its history and Erase reach it);
  the correction card says so first ("It sounds older than what Jarvis
  knows..."), in the reason line both apps already show. Corrections still
  always get a card; no model is involved.

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
lists in eight languages, number and token shapes, anything private about
another person - since 2026-09-26 an everyday fact about someone ("my sister
likes jazz") is not a card on its own: the local model decides it, and only
its clear "not sensitive" saves it - then the learner's own local model; its
"unsure" or no answer is a card too; and passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses are a card even when
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
- **Deep questions are not kept at all** (`jarvis_big_model.py`, security
  audit L2, 2026-09-25): they live in memory until the backend stops. They
  used to be written to `deep-questions.jsonl` in plain text, outside this
  switch and its encryption.
- **Turning it back on is a card; off is immediate. No delete-all.**
  One conversation per delete, and both apps hold deleting and shortening
  the keep period on a stale link.
- **A temporary chat is never kept** (2026-09-25): nothing of it reaches
  `chat-history.db`, whether history is on or off (§5, "A temporary chat
  uses and makes no memory").

---

## 6. Events — one bus

`jarvis_events.Pump` runs the pollers on one thread; every client learns state
changes from it and from nowhere else. Kinds: `approval`, `proposal`,
`finding`, `power`, `persona`, `model`, `activity`, `appearance`, `step`,
`deep`, `memory_saved`, `schedule`, `focus`, `hello`. (`step` is the tool loop saying what it is doing - asking the model,
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
shows the same line on the phone's Brain screen and re-reads the list
(`JarvisRuntime.onMemorySaved`) - never a notification. Since 2026-09-25
the line opens those facts, their words read by id from
`/api/memory/used` only then. JARVIS-API §19.
`schedule` is a timer, an alarm or a reminder going off, or Coming up
changing, `{"id", "kind", "state", "late"?}` only - `jarvis_schedule.py`;
added 2026-09-25. Both apps handle it: the desktop's Rust reads the job by
id and shows a Windows toast (`brain/schedule.rs` `toast_fired`) and the
Brain reads Coming up again; the phone reads Coming up again and shows a
notification (`JarvisRuntime.onScheduleEvent`). The words are read by id,
never carried; a locked screen gets only the kind. A kind that tells nobody
- the standby schedule going off at 01:00 - adds `"notify": false`, and then
neither app shows a toast or a notification. Since 2026-09-25 it also says
`"ready"` for a morning briefing that has been put together
(`jarvis_briefing.py`); both apps notify a briefing on `ready`, not `fired`,
with only "Jarvis: your morning briefing is ready.", and read the briefing
itself from `GET /api/briefing`. JARVIS-API §21 and §22. And, since
2026-09-25, `"matched"` for a "tell me when" that happened, `{"id", "kind":
"tellme", "state": "matched", "urgent"}` (`jarvis_tellme.py`); its looks
every few minutes ring no doorbell at all. Both apps read its `alert` by
id - words the PC built from the owner's own, never the email's - and ring
until seen when it is urgent (desktop `brain/schedule.rs` `toast_matched`,
phone `JarvisRuntime.onTellMeMatched`). JARVIS-API §30.
`focus` is a focus session starting, changing or ending, `{"state"}`, or a
line waiting to be said, `{"state": "callout", "seq"}` - never what was in
front on the PC - `jarvis_focus.py`; added 2026-09-25. Both apps read `GET
/api/focus` again on it; on `callout` only the desktop's Rust fetches the
line, as sound, from the PC itself (the phone is refused it). JARVIS-API
§31.)

**Every event is a doorbell.** Count, ids, and what is needed to route —
never content. That includes `activity`'s sentence: while Jarvis drives a
browser, a window or the phone it is a step number and a fixed word ("Step
2/3: a click in another program's window"), never an address, a window
title, a control's name or typed text (security audit L4, 2026-09-25). This bus reaches a phone that surfaces notifications with the
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
- **The rules block always goes first; everything added to a turn goes after
  it.** The spoken-style note, the "you were interrupted" note and the owner's
  manner line (warm or plain, `jarvis_manner.py`, 2026-09-25) are system lines
  placed just before the newest question, and `keep_rules_first` puts the
  rules in front whenever anything else would be first. Manner is wording
  only: its line says every rule still applies, it changes no tier, card,
  memory or egress, and it is never sent to a cloud lane.

---

## 8. The clients

**Desktop** (`jarvis-desktop/`): Tauri 2, seven windows (quickbar, widget,
HUD, Brain, Faces, onboarding, Settings - one capability file each in
`src-tauri/capabilities/`), per-window ACL capabilities. The Rust commands are the real API — buttons are a courtesy, and
any window holding the capability can call them, so a check that lives only in
the webview is not a check. `decide_approval` consults link staleness in Rust
for exactly that reason.

No desktop page holds the pairing token. The HUD page (vendored from the
backend) used to be given it; since the apps security audit (M2,
2026-09-25) its requests go through Rust (`hud_proxy.rs`: a fixed list of
reads, its chat, the right/wrong mark), and approvals are not answered in
the HUD at all - only in the Jarvis bar and the widget, through
`decide_approval`. No window may `emit` events to the others either (M1).

**Android** (`jarvis-client/`): Kotlin, native, over Tailscale or NordVPN
Meshnet. It is a
remote, not a second brain. It renders, it decides one thing at a time, it
does not hold its own copy of state.

### App lock: what it covers on each app

Both apps have an App lock (off by default) that asks the owner's own check -
Windows Hello on the PC, the fingerprint or phone PIN on the phone - before
Jarvis opens, and again after "Lock again after". What it covers, since the
apps security audit (M3 and L5, the owner's decisions of 2026-09-25):

- **Desktop:** the Jarvis bar, the Brain, Settings **and the HUD window**
  (`lock.rs` `Covered`; every way the HUD is shown - the tray, a second
  launch, a normal start - goes through `lock::may_open`). The widget stays
  on the desktop, but while App lock is on its approval card shows only the
  notice's title, and its Approve opens the Jarvis bar to approve there;
  `decide_approval` refuses an Approve from the widget in Rust as well. Deny
  works from the widget, as from the phone's. An email's card (`send_email`,
  2026-09-25) is approved in the Jarvis bar only, lock or not: the widget
  shows one line of a card, and an email is approved after reading all of it
  (`commands.rs` `waiting_email`, `widget.js`). **Notes too** (the
  owner's decision of 2026-09-26): with App lock on, the widget offers no
  note to a running task or a card, and `inject_task_note` and
  `amend_approval` refuse the widget in Rust - notes are added in the
  Jarvis bar, which asks Windows Hello first. Stop everything (the hotkey
  and the tray row) is never behind App lock.
- **Phone:** the whole app - including Home's "Stop everything" button,
  which is behind App lock like the rest of the app (JARVIS-API §28); the
  PC's hotkey and tray row are not. The home-screen widget only ever shows the
  `notice` text and offers Deny only, lock or not.
- **Watches and other bridged devices (phone, 2026-09-26):** every
  notification Jarvis posts - approvals, timers, alarms, reminders, "tell me
  when", the link and wake-word status - is local only
  (`setLocalOnly(true)`; `NotificationsStayLocalTest` checks every builder),
  so Android does not copy it to a paired smartwatch. Still open: whether
  Android 16's lock-screen widgets can show the home-screen widgets (both
  declare `widgetCategory="home_screen"` only, not `keyguard`); not checked
  on a real phone.
- **Screenshots (phone):** while App lock or "Hide memory lists and chat
  history" is on, Jarvis cannot be screenshotted, screen-recorded or cast
  (`FLAG_SECURE`, `SecurityRules.blockScreenCapture`). Phone only for now -
  see "One-sided on purpose" below.
- **No lock, no risky approval (both apps, the owner's decision of
  2026-09-25):** a risky approval is refused on a PC without Windows Hello
  or a phone without a screen lock, whatever the lock settings say, with
  the same words in both apps - each led by "Nothing was approved." (the
  desktop adds it before the backend's own sentence, `not_approved_words`) (`lock/rules.rs` `NO_HELLO_NO_RISKY`,
  `SecurityRules.NO_SCREEN_LOCK`) and, on the phone, a button that opens
  Android's screen-lock settings. It used to go through unchecked when no
  lock was on. On the PC the backend refuses too (§3, "A known limit").
- **Who asks on the PC:** since the approval gap's step 1, the backend
  asks Windows Hello itself for a risky approval from the PC, and the
  desktop does not ask as well (`lock::check_approval`,
  `approval_needs_local_check`); "Every approval" still asks in the desktop
  for the other cards. The phone still asks its own fingerprint.

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
| People and things (`/api/memory/entities`): the names under each fact, "About <name>", and the "are these the same?" card (memory wave 3, 2026-09-25) | The same rule: linking facts to the people and things they name, and joining two entries, is the memory graph, which stays off the phone (`CLAUDE.md`). The phone shows no names and never asks for the merge card (its pending list leaves out `?merge_cards=1`, so the card waits for the desktop). What the layer is for reaches the phone anyway: chat recall runs on the PC, so "where is my sister getting married?" finds Priya's wedding from either app. |
| Rewording a stored fact (`/api/memory/edit`), and forgetting one from a list of every fact | Deep memory editing. It stays on the desktop's Brain → Memory tab. Forget (`/api/memory/forget`) itself is no longer desktop-only: since 2026-09-24 the phone calls it for facts in the "Saved automatically" list (JARVIS-API §19), and since 2026-09-25 for a fact shown under "Used in this answer" or "Jarvis remembered N things" - one the owner just saw Jarvis use or save, not a browse of the whole store. |
| "Erase the words" beside Forget under "Used in this answer" and "Jarvis remembered N things" | The phone offers Erase in one place only, Brain → Saved automatically, for facts saved automatically that are still in use (the row below). A fact an answer used may be any fact, forgotten ones included (a question about the past recalls them), and erasing any fact at all is deep memory editing. On the phone those two lists offer Forget; the desktop offers both, as it does on every fact. |
| "Erase the words" (`/api/memory/erase`) on a fact that was already forgotten, or was never saved automatically | The same line as Forget, above: the phone lists only facts saved automatically that are still in use, and a list of every fact, forgotten ones included, is deep memory editing. The phone offers Erase wherever it offers Forget (Brain → Saved automatically), so the route itself is on both apps. |
| Pinning a fact on "Always keep in mind" (`/api/memory/profile`) that was not saved automatically | The same line as Forget, above (2026-09-24): the phone's only list of current facts is "Saved automatically", so it pins from there, and a list of every fact is deep memory editing. The route and the "Always keep in mind" section - the pinned facts, "N of 1,200 characters used", Unpin on each - are on both apps, so a fact pinned on the desktop can be unpinned from the phone. |
| Exporting all memory (`/api/memory/export`) | A copy of everything Jarvis knows does not belong on a phone that can be lost. |
| Shutting the backend down (`/api/shutdown`) | The phone would then have nothing to reach and no way to undo it. |
| Deep config editing (`/api/config`) | Out of scope on the phone (`CLAUDE.md`). The desktop does not use it either today: it is only in the Brain window's read allow-list, and no window asks for it. |
| Fetching the look spec (`/api/visual-spec`) | The phone ships its own copy and checks it in a unit test (`SpecDriftTest`); `JARVIS-API.md` says the phone never fetches it. |
| "Finished, or only paused?" (`/api/voice/turn`) | The phone runs the same Smart Turn model itself (`voice/SmartTurn.kt`), so its audio never leaves it just to ask. The desktop asks its own PC over loopback. |
| Screen capture | Nothing earlier wrote a reason down; this one is written 2026-09-24 from the code. The phone attaches a picture through Android's photo picker (`MainActivity.kt`, `PickVisualMedia`), which already offers the phone's own screenshots - one picture, chosen by the owner. Capturing the screen live on Android needs a separate system permission every session and shows a "casting" icon, for no gain over the picker. |
| Global hotkeys (`hotkeys.rs`) | Keyboard shortcuts for a PC. A phone has no equivalent. |
| The "Stop everything" hotkey (Alt+Shift+X, `hotkeys.rs`) | Written with the feature, 2026-09-25. A key on a PC's keyboard; a phone has no global keys. The phone has the same control as a button - Home's "Stop everything", shown whenever Jarvis is busy - calling the same route (`/api/stop_all`, `ported` in `tools/check_parity.py`) with the same words. Each app stops only its OWN speech: pressing it on the phone does not silence the PC, or the other way round (JARVIS-API §28). |
| The tray icon (`tray.rs`) | Part of Windows' taskbar. |
| Starting and stopping the backend (`sidecar.rs`) | The backend runs on the PC, next to the desktop app. The phone cannot run it, and stopping it from the phone is the `/api/shutdown` problem above. |
| On the Hardware screen: the memory bars, the "Details" arithmetic, Copy for the one PowerShell line, and the "exactly what is made" Modelfile (desktop Settings, Hardware and models) | The phone shows the cards (names and memory), what runs now, the three setups in the PC's words, their steps, Measure, and the line itself to read (the phone's Brain, Hardware - the design's section 4.6 asks for that much and no more). The line runs on the PC, so Copy belongs there; the bars and the arithmetic are the design's "Details", which a phone screen does not need to choose a setup. Every route is on both apps (JARVIS-API §20). |
| The Faces window's "Portable output" (`faces.html`) | Code for building a client (the look spec as JSON, Kotlin, TypeScript). It is a developer's tool, and the phone already ships its own copy of the spec. |
| A temporary chat in the HUD window (`jarvis_hud.html`) | The HUD window shows the backend's own page, which sends its own chat requests and has no temporary-chat control; the desktop's temporary chat is in the quickbar, where its chat is. Both apps have the feature (JARVIS-API §4). |
| Who set the power mode, on the tray's Power row ("· set by hand", "· quiet hours", "· idle timer", and since 2026-09-25 "· standby schedule") | Written 2026-09-25, when the standby schedule added a fourth. The phone's Power field has only ever shown the mode itself; the reason is a tray detail. What the standby schedule did is on both apps anyway: its row in Coming up says how its last end went ("Went on standby at 01:00."). |
| Entering an Exa, Tavily or Brave key for web search (Settings -> Web search, `save_search_key`) | Written 2026-09-25, with the feature. A key is "sent only to the one service it authenticates against" (`CLAUDE.md` rule 3). Typed on the phone, it would have to travel over the link to the PC first - somewhere other than its one service. So the desktop writes it straight into Credential Manager on the PC (never over HTTP), or the owner runs `py -3 jarvis_search.py key exa` (or `key tavily`, `key brave`) there; the backend has no route that takes a key. Everything else about web search is on both apps (JARVIS-API §23): choosing the provider, the SearXNG address, "Ask before every web search", Test search - and the phone shows whether a key is saved and where to add one. |
| The backend's own Windows Hello check before a risky approval (`owner-check.patch`, the approval gap's step 1, 2026-09-25) | Written with the feature. It checks approvals that come FROM the PC, where the desktop is; the phone keeps checking its own fingerprint in the app, as before, and the backend lets a phone approval through without a PC prompt. The phone's half - a key in the phone's Keystore that needs a fresh fingerprint for every risky approval, checked by the backend - is step 2, built with "more devices" (`docs/APPROVAL-GAP-DESIGN.md`). Both apps share the stamp (every approval) and "no lock, no risky approval". |
| Saying a timer aloud when it goes off ("Your timer is done.", while "Hey Jarvis" listening is on in the Jarvis bar; 2026-09-25) | The owner asked for it on the desktop ("say timers aloud on the desktop when voice is on"). The phone's timer notification rings, and its voice is only switched on for a conversation - a phone in a pocket speaking on its own was not asked for. Alarms and urgent "tell me when"s ring until seen on both apps (JARVIS-API §30.5). |
| Focus sessions: watching which app or site is in front, and saying a drift out loud (`GET /api/focus/callout`), and the widget's "Lock on" (the owner's decision of 2026-09-25: "Jarvis watches which app/site is in front ON THE PC ONLY ... Nothing leaves the PC") | Written with the feature. The watching happens in the backend, on the PC, and is about the PC's screen: a phone has nothing to watch, and the spoken line names what was in front, so it stays on the PC - the backend refuses `/api/focus/callout` to any address but loopback, and the desktop's Rust fetches it as sound (JARVIS-API §26). "Lock on" is about the PC's screen too. Everything else is on both apps: starting a session (minutes, "on what"), the countdown, on or off target, the drift count, Pause / Resume, +10 minutes, Stop and the report card (the phone's Brain, Focus session; the desktop's Brain -> Work and the widget), and every voice command ("snooze", "I'm doing research", "lock on this") works when said or typed to Jarvis from either app. |
| Loosening a line on "What asks first" (`POST /api/asks_first/tier` with `"ask": false`; the owner's decision of 2026-09-26: "On the PC only, the owner may also loosen a short safe list - one card plus Windows Hello per change") | Written with the feature. The phone shows the same page in the same words, and its "Ask me first" switches turn ON only (stricter, at once) - once a row asks, the phone's line says to loosen it on the PC. Loosening is one card that must meet Windows Hello, and Windows Hello is the PC's: the backend refuses the request from any device but the PC, and `jarvis_owner_check.PC_ONLY_ACTIONS` refuses the card's approval from any other device too, so a stolen token used from elsewhere cannot loosen anything. The phone shows that card with Deny only ("Approve this one on the PC - it needs Windows Hello there."). "Lights, plugs and fans without a card" is on both apps (ON one card, OFF at once). |

| Adding a folder to "Folders Jarvis may look in" (`POST /api/folders/add`) and bringing in a Notion export (`POST /api/folders/import`) (the owner's decisions of 2026-09-26; the feasibility audit's guardrail 1: "one folder list, PC only, empty by default") | Written with the feature. Both are about files on the PC: the desktop opens the Windows folder picker (or the file picker, for the export's `.zip`) in Rust, and only the path the owner chose is sent; adding then raises ONE approval card (`change_own_config`). A phone has no view of the PC's folders to pick from, and a path typed on the phone would be a guess. The backend refuses both routes from any device but the PC (`jarvis_owner_check.from_this_pc`), not only the apps. Everything else is on both apps: the list in the PC's words and Remove on each folder (at once, never held on a stale link - it only lets Jarvis see less; `/api/folders` and `/api/folders/remove`, `ported` in `tools/check_parity.py`), and asking about the files, which is ordinary chat from either app (the `my_files` tool runs on the PC, with the model on the PC). |

**On the phone, kept off the desktop:**

| what | why |
|---|---|
| The phone's own layout settings (`AppearanceStore.kt`, `Look`: the face's share of Home, the tabs row, glow, motion, compact spacing, corners, text size, panel edges, and the "make room" switches) | They describe a phone screen. They are saved per device and never synced (`toSyncDocument` leaves them out), so they cannot change the desktop. |
| **Blocking screenshots while a lock is on** (`FLAG_SECURE`, `SecurityRules.blockScreenCapture`) | **Undecided on the desktop - the owner's call.** The owner decided it for the phone (apps security audit L5, 2026-09-25), where screenshots, screen recording and casting are all a tap away. Windows could do the same for Jarvis's windows (Tauri's `set_content_protected`, which keeps a window out of screenshots, recordings and screen sharing), but it was not part of that decision and is not built. |

**The voice flow is in both apps since 2026-09-25** (`docs/JARVIS-API.md`
§17 part 5; it was backend-only until then): interrupting Jarvis by talking
(`?source=barge_in`, pause first and decide second), "One moment." when a
tool starts (`GET /api/voice/moment`, `ported` in `tools/check_parity.py`),
`&waited_ms=`, the "I heard you" sound (with its own switch in both apps,
"Play a short sound when I finish speaking", off by default), keeping
listening after a question (part 6) and telling the model it was
interrupted (part 7). Two small
differences, on purpose, each for a reason written in §17: the desktop
plays "I heard you" for a "hey Jarvis" sentence only once the PC says the
phrase was heard (its listener cuts every sound in the room; the phone's
own spotter already heard the phrase), and only the phone opens its
microphone by itself after a question (the desktop's listener is always
listening). Still in neither app: the "Voice delay" panel (`flow.summary`)
- the one-line command in `backend/README.md` prints it.

**One card on every screen is in both apps since 2026-09-25** (§3): the
same title and label, Deny left and Approve right, "Open the card", a
notification for every card, and the spoken card lines. One small
difference, on purpose: "Open the card" sits in Settings and the Brain on
the PC (the Jarvis bar, the widget and the HUD show the card itself) and on
every screen but Home on the phone (Home shows the cards). Both name the
last card in the queue as read. The phone's home-screen widget has no
Approve at all - "Review" opens the app - and sits where Approve sits
elsewhere, on the right.

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

Fifty-three patches (counted in `scripts/apply-patches.ps1`'s list on
2026-09-24, after `chat-history.patch`, `auto-learn.patch`, `memory-erase.patch`, `past-recall.patch` and `memory-profile.patch`), applied in that list's order. The order matters: many patches
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
  and so does the phone (Brain). Both read `/api/memory/pending`
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
  and the phone's Brain (`SecondCardPlate.kt`). Not measured on real cards.
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
  apps have a Wiki plate (the desktop's Brain → Memory, the phone's Brain).
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
  memory until the backend stops, with their measured speed - never on disk
  (security audit L2, 2026-09-25).
  `GET`/`POST /api/big-model`, `GET /api/deep`, `POST /api/deep/ask`
  (`big-model.patch`). Both apps have its screens: the three switches in the
  desktop's Settings ("Big model (slow)", `settings.js`) and the phone's Brain
  (`BigModelPlate.kt`), and deep questions in the desktop's Brain → Memory
  (`deep.js`) and the phone's Brain (`DeepQuestionsSection`, same file). Not
  run against a real colibri or on the owner's PC; none of colibri's speed
  claims checked there. [`BIG-MODEL.md`](BIG-MODEL.md) is the owner's guide.

- **Presets for any graphics card** (added 2026-09-25). Jarvis finds the
  cards (Ollama's log, `nvidia-smi`, the registry) and works out three
  setups for them - Fastest answers, Smartest answers, Most features - with
  the owner's 0.75 GB gap (`jarvis_hardware.py`, `jarvis_profiles.py`,
  `hardware.patch`: `GET /api/hardware`, `POST /api/hardware/apply`,
  `/create`, `/measure`). **Nothing changes until the owner chooses one**,
  and choosing only lists the steps: each is its own existing approval card
  (download, switch, the second-card switches) or the new one, `models_create`
  (the same four steps as section 3), asked for one at a time from the app;
  what Ollama reads at start-up is one PowerShell line the owner runs. With a
  setup chosen, the second card's lanes follow it - on one big card, inside
  the everyday Ollama. Both apps: the desktop's Settings ("Hardware and
  models") and the phone's Brain ("Hardware"). Not run on a real card.
  [`HARDWARE-PROFILES.md`](HARDWARE-PROFILES.md) is the design.

- **Timers, alarms, reminders and the to-do list, with ONE scheduler**
  (added 2026-09-25, the owner's decisions of that day).
  `jarvis_schedule.py` is the one clock: jobs of a kind (timer, alarm,
  reminder, to-do, the standby schedule below - and `register_kind` for the
  briefing and the overnight tidy still to come) in `schedule.db`, the PC's local time with
  both clock changes handled, a job missed while the PC was off going off
  once, late. A one-off needs no card; since 2026-09-26 (the approvals
  audit) neither does a plain repeating alarm or reminder - it is set up at
  once and the answer says its next three times. A repeat that reads (the
  briefing, "tell me when") is ONE card (`schedule_repeat`, the same four
  steps as section 3, listing the next three times). Stopping or deleting is immediate, one job at a time; there
  is no delete-all (the one bulk change is clearing a NAMED list, below). `jarvis_quick.py` answers the plain sentences ("set a
  timer for 10 minutes", "remind me at 6 to call Mum") WITHOUT the model, so
  they work when it is slow, unloaded or asleep - English only; anything
  else goes to the model as before. A reminder's words stay on the PC and
  are not learned as a fact. `GET /api/schedule`, `POST /api/schedule/add`
  and `/act` (`schedule.patch`). Both apps: the desktop's Brain -> Work ->
  Coming up with a toast when a job goes off, and the phone's Brain -> Coming
  up with a notification. The PC is the clock: the phone hears of a job
  going off only while it is connected. The initiative engine could not
  host it (a 30-minute heartbeat, findings kept in memory only, off with
  `[initiative] enabled = false`), so it is left as it was; the digest is in
  the owner's `jarvis_arbiter.py`, not here. Not run on the owner's PC.
  JARVIS-API §21.

- **Sleep mode, as the standby schedule** (added 2026-09-25, task #55).
  Not a second standby: Standby (`jarvis_power_switch.py`, both apps'
  existing Standby control) on a timetable - "on standby from 01:00, awake
  at 07:00, every day" - named after it so the owner sees one thing.
  `jarvis_standby_schedule.py` registers kind `standby` on the one
  scheduler: a window job that goes off at both ends, one at a time, set up
  at once with no card since 2026-09-26 (until then ONE `schedule_repeat`
  card listing the next three nights); Pause and Delete are immediate and
  do not wake Jarvis. Each end is
  `jarvis_power_switch.set_mode` through `power_manage`, like the buttons;
  which end it is comes from the clock, so a night the PC was off agrees. A
  start is skipped while a task runs. The end wakes Jarvis only if the
  schedule put it on standby (the owner's decision of 2026-09-25): it reads
  who set the mode from `jarvis_power`'s `why`, so a Standby chosen by hand
  - before or during the hours - stays until the owner chooses Active. Standby itself now unloads EVERY
  model the everyday Ollama holds (asked directly, this PC only) and says
  what is still loaded, and waking loads the chat model again at once
  (never a cloud model). Timers and reminders still go off on standby; a
  question is answered after the model loads, and Jarvis stays on standby.
  Both apps: Coming up gets a "Standby schedule" part (the desktop's Brain
  -> Work, the phone's Brain); its going-off shows no toast or notification
  (`"notify": false`). No new route or patch. Not run on the owner's PC;
  Ollama was a stand-in. JARVIS-API §11 and §21.8.
- **The morning briefing** (added 2026-09-25), the first later kind on the
  one scheduler (`jarvis_briefing.py`, `register_kind` with `repeatable`).
  A short list of the day put together in code - no model sees it: today's
  calendar (only when set up, and only when its read runs without a card),
  today's alarms, reminders and timers, the to-do list, the approval count,
  and (only when email is set up) how many unread emails and who the newest
  five are from - the From line only, read with `BODY.PEEK` so nothing is
  marked read (the owner's decision of 2026-09-25). "Show who new emails are
  from" is a setting on the PC, on by default, in both apps: off at once,
  on through ONE `change_own_config` card, like the voice settings that show
  more. The names are outside text: lines, hidden with the private lists,
  and a chat answer that shows them marks the conversation as having read
  outside text, as calendar titles do. Weather and news say they are not
  available. A repeat is the scheduler's own
  `schedule_repeat` card, a one-off none; each run only reads, each read
  that leaves the PC going through the gate as its own action. Kept in
  memory only. Both apps: the desktop's Brain -> Work and Settings, the
  phone's Brain; the notification says only "Jarvis: your morning briefing
  is ready." `GET /api/briefing`, `POST /api/briefing/now`,
  `POST /api/briefing/senders` (`briefing.patch`). Not run on the owner's
  PC. JARVIS-API §22.
- **Snooze, "cancel that", named lists and "What did I miss?"** (added
  2026-09-25, the creativity audit's everyday quick wins). All on the one
  scheduler and the fast path, no new route or patch, no card. Snooze makes
  a one-off copy of a timer, alarm or reminder that went off (a repeat keeps
  its times) - from "Just went off" in both apps' Coming up, the phone's
  notification, the Windows toast (the same foreground activation as the
  approval toast's Deny, not watched on a real PC), or by saying "snooze".
  "Cancel that" takes back only the last thing the fast path set in the same
  conversation, within two minutes, once. Named lists ("add milk to the
  shopping list") are to-do items with a list name; a whole named list is
  cleared only in the apps, after "are you sure?", with the count the app
  showed - never the to-do list, never by voice. "What did I miss?" is the
  briefing's builder since the owner's previous message (one time for the
  PC, in memory): what went off, cards waiting, unread email as the
  briefing reads it, and what is next - private, not kept. JARVIS-API
  §21.9 and §22.9.
- **The back-off for offers** (added 2026-09-25, `jarvis_backoff.py`): at
  most three offers waiting, none within two minutes of a chat message, and
  each "no" quiet for 1, then 7, then 30 days by a fingerprint of what is
  offered - and, since 2026-09-25 (a bug the creativity audit found), none
  in Quiet or Standby: the offer is kept for when Jarvis is Active again,
  never counted as a "no". Applied to the overnight-tidy card and the skill
  offer. It never approves or acts, and nothing the owner asks for consults
  it. JARVIS-API §22.6.

- **Web search, with a choice of five providers** (added 2026-09-25, the
  owner's decisions of that day). `jarvis_search.py` (shipped whole):
  SearXNG on this PC (the default, in Docker), DuckDuckGo (`ddgs`, its
  DuckDuckGo engine only), Exa and Tavily (free keys, no payment card)
  and Brave (a key and a payment card, charged past its free monthly
  credit - removed and added back the same day by the owner; its "why"
  line says it can cost money), keys in Credential Manager, Whoogle left
  out with its reason,
  behind one `plan()`/`run()` - the same four steps as section 3 when it
  asks. The model tool `web_search` (offered only when `[tools].enabled`
  names it), `GET /api/search`, `POST /api/search/settings` and `/test`
  (`web-search.patch`), gate actions `search_the_web` and
  `stop_asking_before_every_web_search`. When it asks, and the egress lane:
  section 4. Both apps: the desktop's Settings ("Web search",
  `web-search-settings.js`) and the phone's Brain ("Web search",
  `WebSearchPlate.kt`); the key box is desktop-only (section 8). "Which
  search should I use?" is answered without the model (`jarvis_quick.py`).
  Nothing has reached a real SearXNG, DuckDuckGo, Exa, Tavily or Brave yet: the
  tests use local stand-ins. The briefing's "weather and news: not
  available" line is unchanged - weather is a separate decision.
  Since the creativity audit (2026-09-25), saved memories make a search ask
  only when a fact in the turn is sensitive or the search words repeat one
  (section 4; JARVIS-API §23.3).
- **Several smart-home devices on one card** (added 2026-09-25, the
  owner's decision after the creativity audit): `home_control`'s
  `entity_ids`, `jarvis_home.plan_services` - at most ten devices, every one
  listed with its exact request; never a lock, alarm, door, cover, camera,
  script, scene or button (section 2). No app change: both apps show the
  card's text as sent. Nothing has reached a real Home Assistant.

- **Stop everything** (added 2026-09-25, the owner's decision after the
  prompt-pack review). `POST /api/stop_all` (`jarvis_stop_all.py`, shipped
  whole; `stop-all.patch` installs it round the server's POST handler):
  the task Stop, then every tool call of the answer being written refused
  before the gate (and one approved after the press not run), then every
  stopper registered with `jarvis_stop_all.register()` - focus sessions
  register one, which pauses a running session. Never a card, never held on a stale link: stopping
  only makes Jarvis do less (section 3). Desktop: the Alt+Shift+X hotkey,
  which stops the desktop's speech first, and the same "Stop everything"
  row in the tray menu (2026-09-26); phone: Home's "Stop everything"
  button, which stops the phone's. Both say the same sentences
  (`STOP_SPEECH`, `STOP_PC_SILENT`, `STOP_NOT_REACHED` = `StopEverything.kt`),
  and a PC that did not answer is said in the plain words. A step already under way finishes; the
  stop lands before the next one. JARVIS-API §28.

- **A live preflight** (added 2026-09-25, the same review):
  `selftest.py --preflight` asks the RUNNING Jarvis every question a live
  chain depends on - token, handshake, model, a chat round trip, every
  patch and shipped module really in place, the settings file kept off the
  web, the gate, Stop everything, the scheduler, the event stream, voice,
  calendar/email/search, Credential Manager - and prints PASS / FAIL / WARN
  and "N pass, N fail, N warn". Read-only (it approves, sends, unloads and
  changes nothing). One new check per real incident. `backend/README.md`,
  "The preflight"; JARVIS-API §29.

**Still missing:**

- **Obsidian daily notes in every date format.** Only formats that can be
  written out exactly are followed (YYYY, YY, MM, M, DD, D, bracketed words,
  `/` folders). A format with month or weekday names, or week numbers, is
  refused with the reason, and so is a vault where the Periodic Notes plugin
  may be naming the daily note. Nothing guesses a file name.

- **Overnight memory tidying.** `jarvis_sleep.py` only offers it, at most
  once a day and under the back-off (a "not now" is quiet for 1, then 7,
  then 30 days), and the card says it is not built; switching it on records the wish
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
| Reachability | Tailscale or NordVPN Meshnet, properly. Never a public tunnel. |
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
   Does it happen at a time, or on its own - a briefing, a nudge, a nightly
   job? Then it is a KIND of job on the one scheduler
   (`jarvis_schedule.register_kind`), with its own `on_fire`: the same
   clock, the same missed-while-off rule, the same `schedule` event and the
   same Coming up list in both apps. Not a timer thread of its own. And
   anything that repeats is set up by one card, like `schedule_repeat` -
   unless the owner decided otherwise for that kind: since 2026-09-26 plain
   alarms, reminders and the standby schedule have none
   (`register_kind(plain_repeat=True)`; a new kind asks by default).
   A kind that must look more often than hourly ("tell me when",
   `jarvis_tellme.py`) brings its own rule check (`register_kind(check=)`)
   with its own floor and an end date; the shared check keeps the hourly
   floor for everything else. A kind whose runs are not news is `silent`
   (no doorbell per run) and publishes its own event when there is some.
   Does it OFFER something nobody asked for - a card, a suggestion, a nudge?
   Then it asks `jarvis_backoff.may_offer()` first and reports every "no"
   with `declined()`: a few at most, never mid-conversation, never in Quiet
   or Standby, and a "no" is heard for 1, then 7, then 30 days. The back-off only decides whether to
   ask; it never approves, and the owner's own requests never consult it.
   And an offer never asks for more (rule 4, the Muse audit, 2026-09-25):
   no offer Jarvis makes on its own may ask for more access, a new
   connection, a key, a password, a payment method, an identity document,
   or to turn on a setting that shows or trusts more. That is checked by the
   offer's KIND, in code: declare the new kind in `jarvis_backoff.OFFERS`
   with what it asks for, and pass `kind=` to `may_offer()` - a kind that is
   not declared, or asks for anything in `NEVER_ASKS`, is refused and the
   refusal logged (`backend/test_backoff_rule.py` fails on a `may_offer()`
   call without `kind=`).
   Does it reach something outside Jarvis? Then it gets a row in
   `jarvis_reach.KINDS` ("What Jarvis can reach", JARVIS-API.md section 24),
   so both apps and "what can you reach?" say so - from the settings, never
   from the model.
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
