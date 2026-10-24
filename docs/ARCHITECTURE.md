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

   **One narrow, named exception: the encrypted backup file**
   (`jarvis_backup.py`, `backup.patch`; the owner's decision of
   2026-09-27, CLAUDE.md - "This bends rule 1 for that one locked file
   only"). The owner may point "Back up now" at a folder a cloud-sync
   program (NordLocker, OneDrive, ...) uploads. Jarvis itself sends
   nothing anywhere: it only writes ONE file, encrypted before it ever
   touches a disk (AES-256-GCM, a key stretched by Argon2id from a
   recovery code only the owner ever holds), into a folder the owner
   picked - exactly what "Folders Jarvis may look in" already lets the
   owner do for reading. If that folder happens to be synced, the sync
   program uploads it, the same as anything else the owner puts there.
   That is the whole exception: one named file, always locked, never a
   general loosening of this invariant, and never anything Jarvis decides
   to send anywhere on its own. `docs/JARVIS-API.md` §45. What the file
   deliberately leaves out - the File Guardian's device-local store
   (`guardian/`: journal, pins and `blobs/`) and the two non-SQLite
   measurement/anchor files beside it - is recorded with a reason in
   `jarvis_backup.py`'s `NOT_BACKED_UP` / `NOT_BACKED_UP_PATHS` and its
   "EXPLICITLY NOT BACKED UP" section, and `test_backup.py` fails if a
   backend module names a `.jsonl` store that is neither carried nor
   written down.

   **A second named exception: support-chat details** (`jarvis_support.py`;
   the owner's decisions of 2026-09-28, "Customer-support chats"). In a
   chat with a company's customer support, Jarvis may give the details the
   owner listed on that chat's ONE approval card - an order number, an
   email address - word for word, to that company only, and nothing else.
   The last check before every message (`jarvis_support.support_check`)
   hides each listed value exactly as written and blocks anything else
   personal (an unlisted email, phone number, long number or address, a
   saved fact); payment card numbers, Social-Security-shaped numbers,
   passwords, keys and one-time codes block even when listed, and the card
   refuses them. Each value sent is audit-logged by its NAME only
   (`support.detail_sent`), never the value. Per chat, for the listed
   values only - like the backup file, never a general loosening.
   `docs/JARVIS-API.md` §65.
2. **No public tunnel, ever.** Reachability is a private, encrypted
   device-to-device network: Tailscale, or NordVPN Meshnet. Both give each
   device an address in `100.64.0.0/10` that only the owner's own devices
   can reach, and neither is a public tunnel. The desktop's bind-address
   check accepts exactly that range (`validate_bind_address`, commands.rs),
   and the phone allows plain HTTP only to loopback, `*.ts.net` and `*.nord`
   names (`network_security_config.xml`; why no more, below under "Which
   addresses the phone can use"). A non-loopback bind with no
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
   Refused in one sentence: *"Jarvis's address X is not on your own
   networks, so this app will not send your pairing key there: use this PC
   (localhost), your home network (...), Tailscale (...) or NordVPN Meshnet
   (...)."* on the desktop. The phone's sentence ends differently: *"...
   there: on this phone, use your PC's Tailscale name (ending in .ts.net)
   or its NordVPN Meshnet name (ending in .nord)."* (ease-of-use audit
   2026-09-27, #1e), because the phone can only connect in plain http:// to
   those names and to itself - `network_security_config.xml` allows no
   other cleartext host, and cannot list an address range.

   **Which addresses the phone can use** (2026-09-27). The phone applies
   the rule above AND Android's own list, and refuses up front, in one
   sentence, an address that passes the rule but not the list: *"Jarvis's
   address X is on your own network, but this phone can only reach your PC
   by its Tailscale name (ending in .ts.net) or its NordVPN Meshnet name
   (ending in .nord), not by a number or a home-network name: type the name
   the Tailscale or NordVPN app shows for your PC."* (`PhoneAddress.kt`,
   used by `ClientSettings.baseUrl`/`baseProblem`, so it is shown wherever
   the own-networks sentence is). Before this, such an address (192.168.x.x,
   10.x, `.local`, `jarvis-pc`, or a raw 100.x mesh number) was accepted,
   OkHttp then refused every request, and the owner was told "The
   connection to your PC dropped. Try again." - untrue, and retrying could
   never work. `PhoneAddressTest` reads the real XML file and fails if the
   app's copy of its list differs.

   Why Android's list is **not** widened to match the rule, although the
   owner's 2026-09-27 answer ("Phone: allow home-network addresses") asked
   for it - checked, not assumed:
   - *It cannot be widened for numbers.* Android's network security config
     matches a `<domain>` as plain text: the exact name, or, with
     `includeSubdomains`, a name ending in "." plus it (Android's own code:
     `ApplicationConfig.getConfigForHostname`). There are no ranges or
     wildcards, and the only method that changes the policy while the app
     runs (`NetworkSecurityPolicy.setCleartextTrafficPermitted`) is hidden
     from apps. The check is made inside OkHttp, against the URL's host
     text (`RealConnection.connect` calls
     `NetworkSecurityPolicy.isCleartextTrafficPermitted(url.host)`), so the
     only ways around it for a number are to replace OkHttp's internal
     platform object for the whole app, or to dial the number under a
     made-up allowed name through a custom name lookup. Both would turn
     Android's independent check into a rubber stamp for whatever this
     app's own code decided - the one thing the two layers exist to avoid.
   - *It would not reach Jarvis anyway.* Jarvis on the PC listens only on
     its Tailscale/Meshnet address (100.64-100.127) and on the PC itself:
     Jarvis Desktop refuses to save any other listening address, a home
     Wi-Fi one included, because that "would open Jarvis to everything on
     your Wi-Fi" (`validate_bind_address`, commands.rs; INSTALL.md). A
     192.168.x.x number, or a `.local`/`.lan` name (which points at the
     PC's Wi-Fi address), reaches nothing - set up the documented way. So
     the owner's answer cannot be delivered by the phone alone; it would
     first need the PC to listen on the home network, which is a separate
     decision the owner has not been asked.
   - *On a phone, names are safer than numbers.* The phone moves between
     networks and keeps its link open in the background. A number means
     whatever device holds it on the current Wi-Fi (or the mobile carrier's
     own network, for 100.x with the mesh off), and a `.local` name is
     asked of every device on the current Wi-Fi at once (multicast DNS) -
     any of them can answer - so the pairing key would go, unscrambled, to
     a stranger on a cafe's Wi-Fi. A `.ts.net` or `.nord` name is answered
     by the mesh app while it is on, with the traffic inside the mesh's
     encryption; with the mesh off it normally fails to resolve and nothing
     is sent.
   The raw 100.x number of the PC's mesh address is the one case that
   would reach Jarvis; its name does the same job, fails safe, and survives
   the number changing, so the sentence sends the owner to the name. The
   desktop needs none of this: Windows has no per-app list of hosts that
   may get plain http:// (§8, "One-sided on purpose"). An address saved before the rule (or set in
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

**A card waits 15 minutes and then refuses itself** (`approval_timeout_seconds`,
900 in the shipped config since 2026-10-13, and changeable in Settings), because
an unanswered request must not run. Four cards have no deadline at all, by the
owner's ruling of 2026-10-23 (Q1, `backend/no-expiry-cards.patch`): pairing a
device (`pair_device`, `unretire_shared_key`), registering a phone's approval
key (`register_approval_key`) and restoring a backup (`restore_backup`). Those
three ceremonies need the owner at the PC and can take longer than the window;
a card that lapsed half way through loses the work. Every other card keeps the
window, including "forget a time frame" and every switch that loosens a rule -
the rescued work behind this patch exempted 23 actions and the owner refused
that scope. **Waiting is not approving:** a never-expiring card still runs
nothing until a person answers it, is still answerable only while it is the live
card (a cancelled or replaced pairing is withdrawn), and a denial is still a
denial. The gate decides this from its own action ids only - there is no flow
argument and no caller-supplied value that can ask for it.

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
outside text - a reading tool ran (since 2026-09-26 that includes the PC
reading the words in a picture, JARVIS-API section 36), the conversation is tainted, the
newest message was not typed or said by the owner (pasted, shared, from the
clipboard, a picture's caption - since 2026-09-26 decided by the backend
from the picture itself, whatever the app's tag - or with no tag at all - only `typed` and
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

**The automatic restart of a dead model lane needs no card, and that is argued
rather than assumed** (2026-10-14: *"Also restart the lane automatically when it
dies"*; `jarvis_model_lanes.py`, `docs/JARVIS-API.md` §134.3). The rule that
governs a service start here is the one this project already wrote down for
Docker - *"starting a service gives Jarvis more, so it asks"*
(`docker_service_start = "ask"`) - and this is deliberately **not** that case.
What is started is not a new grant: it is the lane the chat is pointed at, the
one this PC already starts by itself at every logon, unattended, with no card and
nobody asked, so a card would be stricter than the machine's own behaviour. A
card also could not be answered when it is needed: the lane dies at 08:19 with
nobody at a screen, an `ask` card would sit for its 900-second timeout and
expire, the lane would stay dead, and the next attempt would raise another one -
the defect itself, plus a queue of expired cards. The act is bounded (three
automatic attempts per episode, then the plain warning), reversible (OFF is one
immediate press from either app) and said (every restart is spoken about in both
apps, in words written by the backend). **And nothing is auto-approved:** this
path raises no card and answers no card - rule 4 forbids *answering* a card, and
there is no card on this path to answer. It calls the same `start()` the owner's
own button calls, so it can reach no action his press could not, it starts only
the lane the chat is on and never both, and it clears no latch. So there is no
new tier line to loosen, in either direction of the switch: turning it back on is
the same action the button beside it takes in the same second, with no card of
its own.

**A second DOOR to the same gates, never a second gate** (`jarvis_settings_
registry.py`, the owner's decision of 2026-09-27, "open"/"adjust" any
setting by voice or chat): "turn on background learning" calls the exact
function `POST /api/memory/learning/auto` already calls; "stop asking
before my calendar" calls `jarvis_asks_first.request_tier` exactly as
`POST /api/asks_first/tier` does, `peer`/`local` included. `jarvis_owner_
check.PC_ONLY_ACTIONS` has three entries TODAY - `loosen_what_asks_first`,
`enable_reading_tool` and `restore_backup` - and this new path refuses the
first two exactly as their own REST routes do (still Windows Hello, still
refused from anywhere but this PC); the third is not offered as a spoken
"adjust" at all (`docs/JARVIS-API.md` §58.2). "Open a settings section" is
narrower still: it is read-only navigation, matched only against a fixed
list of real section ids, so it changes nothing by construction.
`docs/JARVIS-API.md` §58 has the whole design.

**One card for a whole time frame, never a bulk switch** ("Forget a time
frame", the owner's decision of 2026-09-28; `jarvis_forget_range.py`,
docs/JARVIS-API.md §64). The one place a single card forgets and deletes
many things at once - and it keeps the four steps: `preview()` lists every
fact and chat from the chosen days (touching nothing), the apps show each
one ticked and the owner unticks any to keep; `card_text()` lists EVERY
item still ticked in full - each fact word for word, each chat's title and
dates; the gate asks once (action `memory_forget_range`, tier `ask` only,
never loosened; risky, so Windows Hello or the phone's lock); `apply()`
runs only on a person's "approved", and only on ids re-checked against the
days. A spoken "yes" approves nothing. Undo (10 minutes, no card) only
puts back what that card removed.

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

**"Photo to reminder" (2026-09-28, JARVIS-API section 83) reads outside
text without a model turn at all.** `POST /api/photo/scan` reads the words
in a picture (`jarvis_ocr.py`) and finds a date with `jarvis_quick.py`'s own
parser - plain code. The words never reach the model, a tool, the gate or
the learner, and nothing is kept: the apps show a proposal in boxes, and
only the owner's tap adds ONE one-off reminder through the ordinary
`POST /api/schedule/add` (no card, like any one-off reminder the owner
sets; held on a stale link). A command printed on a flyer is at most a
suggested title the owner can see and change.
**"Solve it here" needs no card, and can only do what the owner does**
(`jarvis_handoff.py`, JARVIS-API §87.8, the owner's decision of 2026-09-28).
When a chatbot website or a support chat is paused at a captcha, a sign-in
page or an "unusual activity" page, the phone may be shown that ONE browser
window and pass the owner's own taps and typing to it. Nothing is decided
by Jarvis, nothing leaves the owner's own devices, and it never resumes the
conversation: Resume is still the task's own card. The routes refuse every
picture and every input unless the session is still paused at that very
page, in that window, on the site's own hosts; a Resume, a Stop, Stop
everything or the window going elsewhere ends it at once. Input is held on
a stale link (rule 4); ending never is.

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
across destinations with different threat models. **The screen is one more
destination** (2026-09-29, JARVIS-API 62.13): what Jarvis reads from a picture
of the screen is hidden by `jarvis_secrets.py` (gitleaks's and Presidio's
patterns, a much bigger table than `jarvis_router._SECRET_PATTERNS`, which
only decides whether a typed question may go to a cloud lane, or
`jarvis_scrub.py`, which cleans the log) and painted black in the picture;
a picture the owner attaches to a chat is cleaned the same way before any model sees it (`jarvis_chat_picture.py`, 2026-09-29: the
owner's "Yes, clean them too"), and one that cannot be checked is withheld;
like the others, a pattern list never recognises everything.

**A key is not in the string at all: the blind credential vault**
(2026-10-14, `jarvis_vault.py`, JARVIS-API §134). Every redactor above is a
filter on text that already holds the secret - they reduce what a leak costs,
they do not stop the secret being one `repr()` away. The vault changes the
shape instead: a caller writes a HANDLE, `{{vault:github}}`, where the value
goes, and `resolve()` puts the real value in exactly once, on the one line that
builds the outbound request, and **only for the host the value is bound to** -
so rule 3's "sent only to the one service it authenticates against" is the
function's own property, not something each caller has to remember. Anything
that comes back goes through `redact()`, which puts this turn's own values back
behind their handles and then runs `jarvis_scrub`. The values live in Windows
Credential Manager through `jarvis_token_store`, the same store the pairing
token and the search keys already use; `vault.json` holds the names, their host
binding and their times and never a value. The model, the card, the audit line
and the event carry the NAME. It is wired at one call site today - the Exa,
Tavily, Brave and DeepSeek search keys, whose destination host is fixed in code - and
deliberately **not** into `jarvis_browser_control`'s `secrets(name, host)` hook,
because a browsing turn can be pointed at any site (§3, above).

**The protected-file rule reads what an action TOUCHES, not the words on its
card** (2026-10-10, `gate-touches.patch`; `backend/README.md`, "The gate reads
what an action touches"). `check()`'s first rule - the one above the tier
table, holding *"if the policy and the gate are writable by an action the gate
itself approves, there is no gate"* - searches for `_PROTECTED`'s nine names
(`jarvis-framework.toml`, `jarvis_gate.py`, `jarvis_framework.py`,
`patch_openjarvis.py`, `jarvis_hud.py`, `jarvis_router.py`, `approvals.db`,
`hud-budget.json`, `.openjarvis-patch.json`). It used to search the whole
PROMPT it was handed, and **for a card raised by a route the prompt is the
card's own text** - so a card that merely *described* a protected file was
refused at tier `never` before any card existed: no card, no Windows Hello,
nobody asked, for anybody, ever. The owner's own log holds 45 of them
(2026-10-03 .. 2026-10-10): `enable_reading_tool` 21,
`loosen_what_asks_first` 21, `restore_backup` 3, the redaction lengths naming
jarvis-framework.toml (21 characters) and jarvis_hud.py (13). **What is
narrowed: only free-prose prompts.** The rule now reads the action's
`detail` (the parameters it was handed, minus the keys `_PROSE_KEYS` names -
`text`, `prompt`, `card` - which hold the card's own words) and the model's
own tool call (the JSON object inside the prompt; a prompt with no parseable
JSON in it is prose, and prose is not a target). **What is unchanged:**
everything that protects the tier table. An action whose **target** is a
protected file is still refused at `never`, before any card, with the same
plain reason, on every path a real caller uses - a path or command in
`detail`, OpenJarvis's confirm prompt quoting the tool call, jarvis_agent's
`tool <name> {json}`, a plan step, a tool name made from it, and even an
auto-tier action. Tiers, `Verdict.outcome`, the approval stamp, Windows
Hello, `notice_for` and the refusal wording are not touched at all. The
lesson worth keeping: **a rule that decides from free text decides from the
wrong thing** - it cannot tell a description from a target, and its false
positives are cards nobody can ever be shown. `backend/test_gate_touches.py`
holds both halves, including the three real cards raised end to end through
the real gate.

### The approval gap: what a program already on the PC can and cannot do

**State of it, 2026-10-08** (the heading above used to read "A known limit: a
program already on the PC", which its own lines below contradict - the limit was
narrowed twice and the risky half was built). The two cheap ways in, described
in the next paragraph, are **closed for risky approvals**: since 2026-09-25 the
backend asks Windows Hello itself before it accepts a risky approval from this
PC, and an "approved" row counts only with the running backend's own stamp
(step 1 - "Step 1 is built" below); since 2026-09-29 a paired phone must sign a
risky approval with a key in its own security chip (step 2). What is left is the
short list under "What is still open": a card that is **not risky**, a stolen
key used from **another device**, and a program written specifically to attack
Jarvis - which nothing inside the owner's Windows account can stop.

Written down 2026-09-25 (the Muse audit, `docs/COMPETITORS-MUSE-2026-09-25.md`),
when this was the whole story. The Windows Hello check before a risky approval
("Windows Hello for
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
  **Narrowed 2026-09-28 by QR-code pairing** (`docs/PAIRING-DESIGN.md`
  phase 1, `backend/jarvis_devices.py`, JARVIS-API section 90): each paired
  phone has a key of its own that can be removed on its own, and once the
  owner retires the old shared key it works on this PC only, so a copy of
  it is useless on another device. A stolen *device* key still works from
  another device until that device is removed - phase 2 (a fingerprint-
  signed yes per risky approval) is what closes that. **Built 2026-09-29
  (backend half; JARVIS-API section 91):** a paired phone that has turned
  on signed approvals (one `register_approval_key` card, PC only, Windows
  Hello) must sign every RISKY approval with a key locked in its security
  chip, made fresh by a fingerprint or PIN each time; the backend checks
  the signature (`jarvis_owner_check.approve_check`, a one-use 120-second
  challenge, the card's words re-hashed at that moment). A phone without
  it is refused risky cards ("Turn on signed approvals for this phone
  first") and an unpaired phone on the old shared key still works until
  the owner retires that key. A program that steals a device key alone can
  no longer approve a risky card from another device; a program that has
  the PHONE, or the phone's screen lock, still can - and a program on the
  PC is where it was (below).
  Pairing does NOT change the rest of this section: a program already on
  the PC can still read this PC's key and edit the device list (it cannot
  pass the pairing card's Windows Hello).
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

4. **A `weight: "heavy"` card's Approve stays disabled for a moment, and
   until the card has been read** (feasibility I110, 2026-09-27: "stops
   rubber-stamping"). Two conditions, both required: about two seconds have
   passed since the card appeared, AND the card's whole text has been in
   view - scrolled to the bottom of `#approval-preview` on the desktop
   (`jarvis-desktop/src/heavy-approve.js`), or, on the phone's collapsed
   `detail` (`ApprovalCard.kt`), opened at least once; a card with no hidden
   text to open satisfies that half immediately. **Stricter only**: a
   `"normal"` card, or a row with no `notice` at all (an older backend), is
   unaffected. Deny is never gated by this - refusing something unread costs
   a retry, approving it is the thing this whole rule exists to prevent. The
   desktop's widget, whose card clamps `detail` to two lines on purpose
   ("a decision surface, not a reading one"), cannot honestly satisfy "the
   whole card has been in view" at all, so a heavy card's Approve there
   redirects to the Jarvis bar instead of trying to gate a summary view - the
   same redirect App lock and an email already use, for a different reason
   each.

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
  waits, with a button that goes to it (the card in the HUD window on the PC,
  behind App lock; the Jarvis bar only when there is no HUD window; Home on
  the phone). One line per window rather than a link under each button, so a
  button added later cannot miss it. It decides nothing. The widget's own
  Approve is not this line: for an App-lock, email/tidy or heavy card it opens
  the card in the Jarvis bar, on purpose - the bar is where `heavy-approve.js`'s
  delay-and-scroll gate lives, and moving a button's destination must not
  remove a safety property.
- **The HUD page answers the card too, through the one decision path
  (2026-10-16).** The owner asked for it in his own words - *"i should also be
  able to approve any card from the jarvis hud directly on my desktop and not
  need the jarvis widget or jarvis bar to do so"* - so the page's own Approve
  and Deny are shown again and `hud_bootstrap.js` sends them through
  `decide_approval`, the same command the Jarvis bar and the widget call. It is
  the same permission path, not a second one: the stale-link refusal, the
  cut-off refusal, Windows Hello for the card the settings say needs it and the
  App-lock rule (`lock.rs` `Covered::Hud`) all apply, and the page's own POST
  to `/api/approve` is still refused by that bootstrap's fetch shim - so
  `hud-approvals` (one command) is the only way a decision leaves that window.
  Before this it was the one window the owner watches and could not act from,
  written down as item 8 of `docs/UI-AUDIT-2026-10-05.md`.
- **A card that arrives while the HUD is hidden raises it (2026-10-17).** The
  owner asked for it in his own words - *"i want an approval card to pull up
  fully with the option to click approve instead of the jarvis bar appearing
  and me typing approve."* - so an `approval` event brings the window up
  through `windows::show_hud_quietly`: `show` and no `set_focus` (the gentlest
  this API offers; whether Windows keeps the focus where it was is Windows'
  call), only when the window is hidden, and never while App lock is on. Only
  a card that has ARRIVED raises it: the event is a poller diffing the pending
  ids, so it also rings when a card is answered elsewhere, and a resolution
  must not pop the window up. The bar's own card is unchanged, and a card
  answered there still works there.
- **Voice says a card is waiting, and what happened.** A spoken question that
  waits on a card hears "I need your OK for that. There's a card on your
  screen.", then "Approved. Carrying on.", "OK, I won't do that." or "That
  card timed out, so nothing was done." - from `: jarvis-status` lines the PC
  sends (JARVIS-API §4). Fixed words, never the card's. **Never
  approve-by-voice**: the voice check cannot tell a recording from the owner,
  so a spoken "yes" answers nothing. For the same reason no sentence says
  "until you say yes" any more ("until you approve the card").
- **Two MECHANICAL guards against blind, stacked approvals (2026-10-20).**
  The owner's incident: one "approve all" click approved three backup
  restores, two imports and a device-key registration, because repeated
  requests had STACKED identical cards and muscle memory walked the queue.
  The review the owner accepted (ruling 8.2 of
  `FOR-GEMINI-COMPREHENSIVE-REVIEW-2026-10-20-LATE`) asked for two
  mechanical guards rather than advice, and neither weakens nor answers a
  card:
  1. **One card per identical request.** A request whose action AND target
     (a canonical digest of every input that changes what approving does)
     matches a card still in `state='pending'` reuses that card: the
     duplicate caller is told which card is already waiting and runs
     nothing, so one approved card is one action instead of three
     restores. Different actions or targets are never merged; a card that
     was answered, denied or expired is never reused; nothing is
     auto-approved. The SELECT and INSERT are one `BEGIN IMMEDIATE`
     transaction (`jarvis_gate.check()`, `backend/gate-touches.patch` - the
     file is patch-carried, not shipped whole).
  2. **State-replacing cards say so and take a second press.** The cards
     that REPLACE or delete what is already there - `restore_backup`,
     `register_approval_key`, `memory_forget_range`, and the
     voice-training clear (raised as the shared `change_own_config` and
     marked by its own module) - carry `replaces: true` on every waiting
     row (`jarvis_gate.pending()`), so both apps and the HUD get the same
     set from one place. Each draws a plain **"REPLACES CURRENT DATA"**
     heading (real words, never colour alone) and Approve takes TWO
     presses: the first arms it and says what the second will do, the
     second sends; the button's own label changes between them. A typed
     "approve", a right swipe and the desktop widget do not decide these
     cards (`quickActionable` refuses them; the widget opens the bar,
     where the two-press gate lives). Deny and a left swipe are never
     touched - refusing is always the safe direction. Ordinary cards are
     exactly as they were. `jarvis_gate.replaces_for()` is the backend
     table; `replace-confirm.js` (desktop, widget, bar) and
     `net/ReplaceConfirm.kt` (phone) are the client rule, with the three
     real action names as the fallback for a PC too old to send the field.
     **The HUD window is guarded by its own injected bootstrap.** The vendored
     page's `onclick` never runs inside the desktop HUD - `hud_bootstrap.js`
     captures every card press and sends through `decide_approval`, so a
     page-only rule cannot protect that window (the 2026-10-21 pre-merge audit
     found it could still approve a restore in one click). The bootstrap reads
     the PC's own `/api/pending` row, requires the explicit second press for a
     `replaces` row, arms ONE card id for 10 seconds and sends once; the page's
     two-press stays for a browser tab with no bootstrap. Only an EXPLICIT
     `replaces: false` is one click: an absent field, a missing row or a failed
     read is UNKNOWN and requires the second press, because treating doubt as
     "ordinary" is how this guard would re-open during its own deploy window.
     The pure rule is executed in `hud-replace-confirm.mjs`; the click wiring in
     the running window is executed by the Playwright case in `hud.mjs`.
     **THE SET WAS EXTENDED ON THE OWNER'S OWN INSTRUCTION (2026-10-21:
     "Extend the two-press guard to them")** to the other irreversible
     data-changing actions the pre-merge audit named: `delete_file`,
     `delete_joplin_note`, `delete_logseq_page`, `edit_joplin_note`,
     `edit_logseq_page`, `modify_own_code`, `app_merge_change` - every one is
     reversible "no" or "hard" in the gate's `_RISK` table. The desktop, page,
     HUD bootstrap and phone each carry the same ten-name FAIL-SAFE FLOOR: the
     PC's `replaces` field may ADD an action but a spoofed/`false` field can
     never SUBTRACT the second press, and an unknown card takes it. A single
     press only ARMS and sends nothing, so a cancelled card decides nothing.
     The backend table is `jarvis-backend/jarvis_gate.py`'s `_REPLACES_ACTIONS`
     (carried by `backend/gate-touches.patch`); this PR's own deploy-delta
     follow-up carries the extended table to the live PC.
     **THREE ACCURATE LABELS (review ruling 8.1, 2026-10-21):** the heading is
     not one generic sentence. The PC classifies each marked action -
     `deletes_data` (`delete_file`/`delete_joplin_note`/`delete_logseq_page`,
     `memory_forget_range`, and the detail-marked voice-training clear),
     `overwrites_note` (`edit_joplin_note`, `edit_logseq_page`) or
     `replaces_code_or_state` (`restore_backup`, `register_approval_key`,
     `modify_own_code`, `app_merge_change`) - and sends `replaces_kind`,
     `replaces_heading` and `replaces_note` on every waiting row, with the
     words owned by `jarvis_card_words.py` and drawn by every surface. A kept
     copy is promised only where one is really kept (the backup of current
     data before a restore, the app's git history, a device removable in
     Settings); the note edits and deletions say plainly that Jarvis keeps no
     copy. The backend suite asserts the exact words per action against the
     gate's `_RISK` why.

### Cardless by design, and why

The rule "the app never auto-approves anything" (rule 4) is not the same claim
as "every write raises a card": a cardless path here raises no card because it
answers none, and every one of them either only makes Jarvis do less or
records a preference the owner can change back in one press. This is the
complete list; a write that is not on it asks first. (The two-press cards and
the tiers themselves are section 3 above.)

| What is written | Why no card | What still guards it |
|---|---|---|
| **Appearance and layout** - the desktop's `theme` (`commands::set_theme`, the settings store's appearance class) and the big HUD's layout document (`hud_layout.rs` `set_hud_layout`) | Paint and arrangement only: no private material, no backend call, no outbound request, and changing it back is one press. | Rust's closed-world normaliser (`hud_layout::sanitise`) is the authority for the saved document and the page's normaliser is a second line; the layout write is its own appearance-class grant (`hud-layout-write`, owner-approved 2026-10-21, `capabilities/hud.json`), separate from the page's schedule grant, and the page holds no pairing token. |
| **One job on the schedule** - pause, resume, delete, done, add time or snooze on ONE job, plus a ONE-OFF reminder/alarm/timer add (`jarvis_schedule` `act()` / the add route) | "Stopping only makes things quieter": one job's state, or one new item. There is no list form and no delete-all - clearing a named list stays the Brain window's, by Ruling 15. | The stale-link hold blocks ACTING while the event stream is stale (rule 4); the audit line carries ids, kinds and outcomes only, never the item's words; and a REPEATING add does raise its one `schedule_repeat` card at tier `ask`. |
| **A ready-for-review marker** - Wave D-1's ready-for-review path (`Scheduler.propose_ready`, `jarvis_schedule.py`; JARVIS-API section 21) - the ruling calls this `suggest_done` | It completes nothing and changes no state: it only says "Jarvis's part is done - check it". | Only a to-do can be marked; the item stays `active`/`paused` until the owner's own `act("done")`, the one action that completes a task; the audit line is `schedule.ready` with ids, kind and a short reason only - never the item's words. |
| **The next message's lane** - the big HUD's ONE Cloud button (the same lane switch the bar always had; `jarvis_hud.html`'s rail) | It routes one message: it approves nothing, sends nothing, stores nothing, and it marks nothing until `/api/status` says the proxy is up. | The server's own rule-1 refusals still apply: a turn touching private material never runs on a cloud lane (`jarvis_agent.local_model_refusal`; `_one_call` refuses it again before any card - section 4). |
| **Actions that only reduce or refuse** - Stop, Stop everything, Pause, Cancel, Mute, Deny and Undo | "Stopping is never gated" (section 3 above): each makes Jarvis do less or refuses a request, so a card asking permission to stop would be a card that cannot be safely refused. | Stop everything also refuses the remaining tool calls of the answer being written, and works while App lock is on; Deny is always the safe direction; Undo only puts back what ONE card removed, inside 10 minutes; none of them approves, denies, starts or resumes anything (only Resume raises a card). |

**Wave D-1 (PR #722) is proactive, read-only and local-only, and its Rule-1
and Rule-4 position is recorded here before it ships.** Its proactive reads -
calendar travel/flight collisions and wrong-day anomalies
(`jarvis_calendar.detect_travel_and_flight_collisions`,
`detect_calendar_anomalies`), quiet email threads
(`jarvis_email.find_quiet_threads`), the 2-minute meeting prep cards and the
Daily Pulse / "where to look" strip (`jarvis_briefing.build`, `pulse_from`;
`jarvis_today` carries the pulse on the Today board) - add no socket of their
own, no model call and no card: they are built from reads the briefing already
makes, and a source nobody read is listed in `not_checked`, never shown as 0.
**Rule 1** holds because the calendar read latches outside text through
`jarvis_gate.latch_taint` (`jarvis_calendar`'s own read does this today), the
briefing is read-only and opens only the calendar and email reads their own
settings allow, everything it shows passes through its own `_clean` cap or is
already bounded by the read that produced it, and the sections that name
people are withheld by the same App-lock / hide-memory redaction as the
sections around them (the Today board's `pulse` is withheld entirely while the
private lists are hidden). **Rule 4** holds
because nothing here acts: the one write is the ready-for-review marker in the
row above, which never completes a task - only the owner's explicit
`act("done")` does. **Honest limit, stated by D-1's own docs:** the quiet-thread
list, the prep people/notes and the money/study/PC-health Pulse sources are
caller-supplied in v1, and no route or live mailbox read is wired yet; a source
nobody read is said so in `not_checked`, never invented.

---

## 4. The egress boundary

These lanes leave the machine. Nothing else may.

| lane | what may go | enforced by |
|---|---|---|
| **cloud model** | user-role turns only - and, with `cloud-one-turn.patch`, only the **newest** one, because the clients now send the conversation so far | a role filter, re-derived on **every** hop of the degrade loop; the newest-turn cut in `_open` |
| **ntfy push** | text generated from our own tables, never payload, never while tainted - and **nowhere at all unless the owner set BOTH `JARVIS_NTFY_TOPIC` and `JARVIS_NTFY_SERVER`**. The server used to default to the public `ntfy.sh`, so a topic on its own posted card titles to a broker nobody chose; the default destination is now nowhere (2026-10-05) | `notice_for` (`_safe_detail` where there is no action name) + `taint_active()` + `_push`'s own "both, or nothing" guard |
| **research** | enumerated search terms, per approved plan | `jarvis_research.plan/run` |
| **the owner's own accounts** - calendar, email, Home Assistant, each only when its settings are filled in on the PC | one request (or one small batch) per plan: to the calendar the owner set up - their CalDAV server with the time range, **or, since 2026-09-25, Google (`calendar.google.com`) through the calendar's private link**, which asks for the whole calendar and has the days picked out on the PC; to their IMAP server; to their Home Assistant (since 2026-09-26 also the forecast its weather device already has, for the briefing and "what's the weather?": two fixed read-only requests, `jarvis_home.plan_forecast`, never a service call through `home_control`). The password, token or private link goes only to the host it belongs to; the private link is also kept off every card, result, error and the log (`test_calendar_link.py`) | each module's `plan()`/`run()` through the gate (`jarvis_calendar`, `jarvis_email`, `jarvis_home`); `jarvis_local_http.plain_http_problem` (plain `http://` only inside the owner's own networks); each module's redirect handler (`_RefuseRedirect`, and for the private link `_FeedRedirect`: https on the same host or between Google's calendar hosts only) |
| **sending email** (2026-09-25, the owner's decision after the Muse audit) | ONE plain-text email per approval card, from the owner's own account (the address email reading uses), to at most 10 people in To and Cc (no Bcc), with the subject and text the card showed word for word - at most 2,500 characters, no attachments - and the owner's password, to their own sending server only (`smtp.X` for `imap.X`, e.g. `smtp.gmail.com`, or `JARVIS_SMTP_HOST`), inside SSL/TLS or STARTTLS with the certificate checked; unencrypted only to this PC or the owner's own networks. Written by the model on this PC only (rule 1) | `jarvis_email_send.plan/run` (no socket in `plan`; addresses, caps and invisible characters checked; a plan whose fingerprint or settings changed after its card is refused; never retried; the password never in a plan, card, result, error, event or the log) + `jarvis_agent._one_call` (`send_email` in `NEEDS_A_PERSON`: only a person's yes sends; no card unless the tier is `ask` and the turn's model is on this PC; the card says at the top when outside text shaped the turn; `CARDS_PER_TURN`) |
| **saving an email draft** (2026-09-27, the owner's decision, "a card every time, showing the full draft") | ONE plain-text draft per approval card, from the same account email reading and sending already use, to at most 10 people in To and Cc (no Bcc, and unlike sending, `to`/`cc` may both be empty), with the subject and text the card showed word for word - at most 2,500 characters, no attachments - saved by IMAP `APPEND`, with the standard `\Draft` flag, to the ONE mailbox that account's own server flags `\Drafts` (found by `LIST`, never a hard-coded name). Never sent: this module has no `smtplib` import at all. Written by the model on this PC only (rule 1) | `jarvis_email_draft.plan/run` (no socket in `plan`; addresses given ARE checked, caps and invisible characters checked, a completely empty draft refused; a plan whose fingerprint or settings changed after its card is refused; never retried; the password never in a plan, card, result, error, event or the log) + `jarvis_agent._one_call` (`draft_email` in `NEEDS_A_PERSON`: only a person's yes saves; no card unless the tier is `ask` and the turn's model is on this PC; the card says at the top when outside text shaped the turn; `CARDS_PER_TURN`) |
| **tidying the inbox** (2026-09-28, the owner's decision, "inbox tidy by voice"; JARVIS-API section 95) | Archive, star, mark as read, or move to Trash a checked list of emails - at most 30, every one named on ONE approval card (sender, subject, date) - in the one mailbox the account reads (`JARVIS_IMAP_MAILBOX`, the inbox unless set), on the owner's own IMAP server with the same password as reading (certificate checked). No permanent delete: "delete" only ever means Trash; no plain `EXPUNGE`, no `CLOSE` on a folder opened for changes. Only that mailbox and the account's own Archive and Trash folders (found by `LIST`'s special-use flag, never guessed; Gmail: labels). Written by the model on this PC only (rule 1) | `jarvis_inbox_tidy.plan/run/undo` (`plan` reads the emails read-only, `EXAMINE` and `BODY.PEEK`, to list them; nothing is changed before a yes; a plan whose fingerprint, account or folder numbers (UIDVALIDITY) changed after its card is refused; each email is checked again just before it is touched; Undo, 10 minutes, no card, restores exactly what changed and is in memory only - ids, never a sender or a subject; the password never in a plan, card, result, error, event or the log) + `jarvis_agent._one_call` (`tidy_inbox` in `NEEDS_A_PERSON`: only a person's yes changes anything; no card unless the tier is `ask`, `email_read` may look without a card, and the turn's model is on this PC; the card says at the top when outside text shaped the turn; `CARDS_PER_TURN`) |
| **plug-in programs (MCP)** (2026-09-26, the owner's "Smarter tools" choice; `jarvis_mcp.py`) | ONE tool call's arguments, exactly as its card showed them, over stdin to ONE program on this PC that the owner listed under `[mcp]` in `jarvis-framework.toml` and approved when it was added (and again whenever it changed). Nothing else: no web address, no network transport, no program fetched at start. **Said plainly:** the program runs as the owner and may use the network itself - Jarvis controls what it ASKS and what comes BACK, not what the program does; its start card says so. It gets no key of Jarvis's (only what the owner gave that one program, a key only from Credential Manager) | `jarvis_mcp` (stdio only; a full path, never `npx`/`uvx`; the environment from `jarvis_child_env.inherited()`; only read-only tools offered; the floor is `ask` for every call; `Bridge.run` needs a person's approval of THIS action, used once; the result cleaned, capped and marked untrusted) + `jarvis_agent._one_call` (`outside_program`: its own gate action `mcp__<server>__<tool>`, a person's yes only, `CARDS_PER_TURN`, `_TurnWatch.took_in` - so the result is outside text and marks the conversation) + reached only through `more_tools("plugins")` |
| **web search** (2026-09-25) | ONE search's words (at most 300 characters), to the ONE provider the owner chose - SearXNG on the owner's own machine (which asks other engines), DuckDuckGo, Exa, Tavily, Brave or DeepSeek - and, for the last four, the owner's key to that service only. Never words that look like a password or key. A card with the exact words whenever the conversation has read email, files, notes, saved memories or other outside text, or the owner chose "Ask before every web search" | `jarvis_search.plan/run` (no socket in `plan`, secret refusal, one provider, no fallback, redirects refused, answers capped) + `jarvis_agent._web_search_call` (when it asks; only a person's yes after that) + an on/off switch (2026-09-30, JARVIS-API 23.6): off at once from either app, back on through ONE card (`web_search_enable`), read by `plan()`/`run()` and `offered_tools()` at use time |
| **checking for tool updates** (2026-09-27, the owner's own request, made directly) - PC only, and never the AI model: `jarvis_tool_updates.py`, run only by a person pressing the desktop's own button | Package and crate NAMES only (checked 2026-09-27, security/privacy audit: each request is `pypi.org/pypi/<name>/json` or `crates.io/api/v1/crates/<name>` - the version the PC is on is compared here, never sent; the card says "NAME and the version number", which is more than is actually sent) - **with one honest correction, 2026-10-23**: for an OUTDATED Python package the update card's evidence needs PyPI's own advisory list for the version that is pinned, and that read is `pypi.org/pypi/<name>/<pinned-version>/json`, so that ONE request DOES carry the pinned version number (same `pypi.org` host; it is the number the report already shows the owner; it is sent only for packages that are outdated, nothing else is added, and the crates.io and GitHub reads are unchanged), with a User-Agent naming the tool, not the owner (it named the owner's GitHub address until 2026-09-27) - never a file path, a folder name, or anything about the owner - to PyPI (`pypi.org`), crates.io (`crates.io`) and, if a real hand-installed tool is ever added to the (empty today) GitHub list, `api.github.com`. Report only: nothing here ever writes a file, runs `pip install`, or runs `cargo update` - it only shows the owner the exact command to run themselves. ONE approval card, the very first time this is ever run, ever; every later run skips the card entirely | `jarvis_tool_updates.run_check` (no socket opened by anything but the fetch functions it calls, each with its own timeout and a small retry, never a fallback that swaps providers; plain `urllib.request.urlopen`, so a redirect IS followed and the system proxy is used - acceptable only because no key or anything of the owner's is in the request, https only); `request_check` (the plan/run split: `approved()` is checked, and the gate is asked, before any fetch; only "approved" writes `tool_updates.json`, and a damaged or missing file reads as not-yet-approved, never as approved). "Desktop only" is the apps' choice, not the backend's: the two routes take any paired device's token (unlike the backup routes, `from_this_pc`) |
| **an address the owner typed, meant to be on the open internet** (2026-09-27, feasibility I49/I67) - a news feed's own address (`jarvis_news.py`) or the one page "tell me when this page changes" watches (`jarvis_tellme.py`'s `page` source) | ONE plain GET of exactly that address, never a link found on it - a feed's headlines (titles only, never an article's own page) or a page's own words, reduced to a SHA-256 fingerprint with script/style/nav/footer/aside text, timestamps, view counts, CSRF/session nonces, utm_* parameters and the SecAlign chat/tool markers stripped (`strip_page_noise`; Pillar 26, 2026-10-17), plus the short structured facts the watch keeps (`extract_watch_signals`: every price as an integer whole cent, every version tag, a three-state stock state) - never the page's words, never a quote or a diff, and nothing sent to the AI model. A difference only in that noise is `[SILENT]`; a real change latches `jarvis_gate.latch_taint(why="page_watch")` because outside text was read. ONE approval card per address ADDED (a feed) or WATCHED (a page); reading it afterwards needs no further card, only the tier below. Refused - at add-time, and again immediately before every later fetch - if the address resolves, by a REAL DNS lookup (never spelling), to this PC or a private network address, so a public-looking name can never be used to make Jarvis fetch from its own machine or home network (DNS rebinding is checked for, not only assumed away) | `jarvis_local_http.private_fetch_problem` (real DNS, checked on every fetch, not only at setup; a redirect followed only where the same check allows it) + `jarvis_local_http.public_urlopen` (since 2026-09-27, the security/privacy audit: the connection itself looks the name up ONCE, refuses any private answer, and connects to exactly the address it checked - before this, urllib looked the name up a second time to connect, so an answer that changed within that moment got through) + `jarvis_news.request_add`/`read_feed` (gate action `news_read`, tier `auto`/`notify`; adding is `change_own_config`, tier `ask` only) + `jarvis_tellme.add`/`_look_page` (gate action `page_read`, tier `auto` only - stricter than news, since a look is every 30 minutes, not about once a day; adding is the scheduler's own `schedule_repeat`, tier `ask` only) |
| **a YouTube video's captions, for a quiz** (2026-09-30, the owner's "reading a YouTube video's captions is allowed, one card per link"; `jarvis_youtube.py`, `youtube.patch`, JARVIS-API §112, `docs/STUDY-FROM-TEXT-DESIGN.md` §5 and §14) - **BUILT ON THE PC, NOT YET TRIED AGAINST THE REAL SITE** (the network policy of the build container blocked it; YouTube often blocks data-centre addresses and changes its pages). **It breaks YouTube's terms and may be blocked**; the owner accepted that, and the card says it every time | The video's id, inside the requests the `youtube-transcript-api` package (MIT, pinned `==1.2.4`, no key, no sign-in, no cookies, no proxy service) makes to `youtube.com` for that video's CAPTION TEXT - the subtitles - and nothing else: never the video or its sound, never comments, never another link. The link itself tells YouTube which video the owner is studying, and the PC's address is visible to YouTube; the card says both. What comes back is cleaned and cut to 20,000 characters and handed to the ordinary quiz as OUTSIDE text (a quiz marked `provenance: "outside"`): never learned, never saved, kept in memory only | `jarvis_youtube.parse_link` (shape only, no network: one video on `youtube.com`/`www`/`m` or `youtu.be`; playlists, channels, other hosts, lookalike or non-ASCII hosts, ports, links with a name or password, non-web schemes and control characters refused BEFORE any card) + ONE card per link (gate action `youtube_captions_read`, tier `ask` only, a risky approval: Windows Hello on the PC, a screen lock on the phone; the exact canonical link on the card; a second link is a second card; nothing is fetched before a person's yes) + a 40-second limit on the library's requests + errors in plain words that never quote the link or an exception + `start(tainted=True)` refuses after a turn that read outside text + the link is never logged (the audit line holds outcomes only) + `jarvis_quiz` (fenced-data model calls, crisis check on every answer, no learner or memory import). No captions, no speech-to-text fallback, no other site |
| **a quiz sent to a cloud AI service to be marked better** (2026-09-30, the owner's "grading is local first, cloud on request"; `jarvis_quiz_cloud.py`, `quiz-cloud.patch`, JARVIS-API §113, `docs/STUDY-FROM-TEXT-DESIGN.md` §7 and §15) - **BUILT ON THE PC, NEVER RUN AGAINST A REAL PROVIDER** (the build container has no network; the tests use a stub transport). **It bends rule 1 for that one quiz**, the way the locked backup and the app builder's cloud-help offer do, and the card says so | ONE message, built once before the card and shown on it word for word: a fixed instruction, then for each ANSWERED question its question, its passage and the owner's typed answer. Not sent: the quiz title, the marks and comments the local model gave, unanswered questions, the rest of the source text, any other quiz, chats, memory, email, files, settings. It goes to ONE host - the API host of the cheapest service the chatbot driver has set up (`jarvis_chatbot_api.py`: a key saved on this PC AND a monthly money limit AND a price), or the one the owner named - with that service's own key in that request's header only. Never for a quiz that had a crisis answer, is marked private, is Spanish practice, was made from outside text other than YouTube captions (the card then says the passages are caption text), or whose questions, passages or answers look like money, health, credentials, ID or secrets (`jarvis_sensitive`, `jarvis_secrets`; fails closed) | ONE card per request (gate action `quiz_cloud_grade`, tier `ask` only, a risky approval: Windows Hello on the PC, a screen lock on the phone; never an "always allow", never by voice) showing the whole message, the service, host, model and what is left of its monthly limit + the SAME transport the chatbot driver uses (`jarvis_chatbot_api.ApiChatbot`: key read only there, host pinned, https only, no redirects, hard answer-length cap, money counted, unreadable-money-file fails closed) - reused, not copied + after a yes the quiz is read again and nothing is sent if it no longer gives the identical message + the reply is data: only one checked level and one sentence per question are used, all or nothing + nothing is written to disk here, the audit line holds outcomes only (never a word of the quiz, never a key) + `start(tainted=True)` refuses after a turn that read outside text |
| **customer-support chat (website)** (2026-09-28, the owner's "Customer-support chats"; `jarvis_support.py`, `jarvis_support_widget.py`, JARVIS-API §65) - **BUILT, NOT YET TRIED FOR REAL**: reachable from both apps through `/api/chatbot/support/*` once Playwright is installed on the PC. A browser window the owner can see, on its own profile (`chatbot/support-profile`, the owner signs in to their OWN account there by hand), opens ONLY the help page of the company on the card - Groupon's preset (`www.groupon.com`, address unverified) or a help page the owner types (https, a public name) - and never navigates anywhere else by itself. The company's chat widget usually sits in a frame served from its maker's own host; Jarvis reads and types in such a frame only when it is where that maker's widget sits AND its host is on that maker's list (Zendesk, Intercom, LivePerson, Gorgias, Freshchat, Salesforce; NOT VERIFIED), else it pauses. "What Jarvis can reach" has its row (`jarvis_reach._support_chat`); the gate's `_RISK` lines are `support-chat.patch` (outbound, cannot be undone) | Messages Jarvis writes in the owner's name (no opening "I'm an AI" line - the owner's choice), each through the support last check: only the details on the card, never a password, PIN, card number, security answer, ID number or code; a message saying it is a person never leaves. Fixed lines: the accepting reply "Yes, I accept that. Thank you." ONLY after that offer's own card; the owner's Decline line; "One moment please, I'm just checking that." while an offer card waits (at most every 2 minutes, 3 times); "Are you still there?" once; the request for a reference number and a written summary; thanks. A menu button in the chat is pressed only when the driver names its exact label, after the same check (one with offer words gets its own card) | `jarvis_support.plan/describe/run` (gate action `support_chat`, tier `ask` only, one card per chat listing every detail and the company's terms risk) + `support_offer` (one card per offer, showing the agent's words and the exact reply; a typed "yes" is refused) + `support_check` right before every send + plain-code detectors: "are you a bot?" and identity checks are handed to the owner (nothing sent), a detail not on the card is handed to the owner + `jarvis_task_control` Pause/Resume, Take over, Stop and `jarvis_stop_all`. Any company preset beyond Groupon needs the owner's OK first |
| **"tell me when" watches on a search, a price or GitHub** (2026-09-28, the owner's choice of the research audit's "Watches" group; `jarvis_tellme.py`, docs/JARVIS-API.md section 70) - three watches, each ONE approval card (`schedule_repeat`, tier `ask` only) and each only notifying | **A search:** the owner's own typed or said words (at most 200 characters), once a day by default (every 6 hours at the most often), to the ONE web search provider the owner chose - the **web search** lane above, through the same `jarvis_search.plan/run` (secret refusal, one provider, no fallback, redirects refused), never while "Ask before every web search" is on; only 16-character fingerprints of the result addresses are kept, never titles, text or the addresses. **A price:** the same one GET of one typed address as a page watch - the lane above - with one number read from it by plain code, never the AI model; nothing is bought or pressed. **GitHub (a new way out):** ONE read-only GET to `api.github.com` per look - a repository's workflow run list or one pull request, the repository, branch and number the owner named, nothing else - and, when `JARVIS_GITHUB_TOKEN` is set, that key (the one GitHub research already uses) in that request's header only; without it, public repositories only. Nothing on GitHub is changed | `jarvis_tellme._look_search` (through `jarvis_search`), `_look_price` (through `jarvis_local_http.private_fetch_problem`/`public_urlopen` and `_PageRedirect`, gate action `page_read`), `_look_github`/`_default_github_get` (gate action `github_read`, tier `auto` only; any address but `https://api.github.com/...` refused before sending; redirects refused, never followed; the key read fresh, registered with `jarvis_scrub` by value, never in a card, error, audit line, event or `schedule.db` - `test_tellme_watches.py` checks) |
| **chatbot conversation (website)** (2026-09-27/28, the owner's decisions; `docs/CHATBOT-DRIVER-DESIGN.md`) - **BUILT, NOT YET TRIED FOR REAL**: the core (`jarvis_chatbot.py`), its routes (`jarvis_chatbot_routes.py`, `chatbot-routes.patch`), both apps' screens, and the Gemini adapter (`jarvis_chatbot_gemini.py`, Playwright, a visible window, its own browser profile signed in once by hand) are built (2026-09-28); it reaches gemini.google.com only after the owner has installed Playwright and signed the window in. The routes take any chatbot id and both apps list every one, so each website below is likewise reachable from both apps once its own window is signed in (the sign-in helper leaves a small dated note in the profile folder only when the sign-in finishes; a folder without it is "not signed in yet"). The owner's one-off self-check (`py -3 jarvis_chatbot_gemini.py check`) sends one fixed question, "What is 2 plus 2?", to verify the selectors. **Eight more websites, the same visible window** ("the chatbot driver becomes versatile", 2026-09-28): one shared base (`jarvis_chatbot_web.py`) and a thin site file each, each its own named way out with its own spare account, profile folder and self-check - ChatGPT `chatgpt.com` (`jarvis_chatbot_chatgpt.py`), Claude `claude.ai` (`jarvis_chatbot_claude.py`), Microsoft Copilot `copilot.microsoft.com` (`jarvis_chatbot_copilot.py`), Perplexity `www.perplexity.ai` (`jarvis_chatbot_perplexity.py`; its listed sources are copied as text, never opened), DeepSeek `chat.deepseek.com` (`jarvis_chatbot_deepseek.py`), Grok `grok.com` (`jarvis_chatbot_grok.py`), Le Chat `chat.mistral.ai` (`jarvis_chatbot_lechat.py`) and Meta AI `www.meta.ai` (`jarvis_chatbot_metaai.py`). Each window opens only its own host by itself; the sign-in hosts its "Sign in with ..." buttons lead to (Google, Microsoft, Apple, X, Facebook, the sites' own `auth.` hosts) are reached only by the owner's click, and are a "needs you" pause. None of their selectors has been tried against the real site (`docs/JARVIS-API.md` 87.5). "What Jarvis can reach" has its row (`jarvis_reach._chatbot`); the gate's `_RISK` line is `chatbot.patch` (outbound, cannot be undone) | The owner's goal, word for word as its ONE card showed it, then Jarvis's own short follow-up questions, written on this PC by a model that is given only the goal and the conversation (no memory, email, notes, calendar, files or history, and no tools), to ONE chatbot website per adapter (Gemini first, `gemini.google.com`, typed into a visible browser window at a person's pace with the spare account used only by Jarvis; never a captcha solved - the owner's 2026-09-28 "driven openly, never hidden" rule was reversed on 2026-09-29, see CLAUDE.md "Stealth on for everything"). At most the card's messages and minutes. Never a message that fails the last check: a password- or key-shaped value, a one-time code or sign-in link, an email address, a phone or other long number, a street address or postcode, the owner's never-send words, a private topic (`jarvis_router.is_private`), or anything repeating a saved fact (`jarvis_search.repeated_facts`) | `jarvis_chatbot.plan/describe/run` (gate action `chatbot_session`, tier `ask` only, one card per conversation and a new one for any changed limit; `run` refuses a conversation whose goal, limits or version changed after its card) + `jarvis_chatbot.last_check` right before every `send()`, the goal included (one rewrite, then pause and ask; fails closed) + stops in code (limits, two refusals, circles, a question about the owner handed back, captcha/sign-in/"unusual activity" pauses) + `jarvis_task_control` Stop/Pause/Resume and `jarvis_stop_all`. Each new chatbot is a new adapter, and needs the owner's OK first (each company's terms differ) |
| **chatbot conversation (API, with a key)** (2026-09-28, the owner's "the chatbot driver becomes versatile"; `jarvis_chatbot_api.py`) - **BUILT, NOT YET TRIED FOR REAL**, like the row above: reachable from both apps through `/api/chatbot/*` once that service's key is saved on the PC; not yet tried against any real service. One named way out per service, each only once the owner has saved that service's key on the PC: **OpenAI** `api.openai.com`, **DeepSeek** `api.deepseek.com` (address unverified), **Mistral** `api.mistral.ai`, **xAI (Grok)** `api.x.ai` (host checked; path seen in xAI's own client, not its API reference), **OpenRouter** `openrouter.ai` (which passes each message on to the company that runs the chosen model), **Groq** `api.groq.com`. "What Jarvis can reach" has its row (`jarvis_reach._chatbot_api`, the hosts with a key saved) | The same words as the row above - the goal as its ONE card showed it, then Jarvis's own follow-ups, each through the same last check - plus that conversation's earlier messages and replies (the API keeps no memory, so each request carries the conversation so far), as a Chat Completions request `{"model", "messages"}` plus that service's answer-length cap (the money limit's hard stop, 2026-09-28: `max_completion_tokens` for OpenAI, Groq and OpenRouter, `max_tokens` for Mistral and xAI, none for DeepSeek, whose field is unverified; JARVIS-API §87.4.1), with no system message and nothing else. The service's key (Windows Credential Manager, `Jarvis Backend/<company> API key`, added on the PC only with `py -3 jarvis_chatbot_api.py key <service>`) goes in the Authorization header to that service's own host and nowhere else | `jarvis_chatbot` exactly as above (the same card, action `chatbot_session`, the last check before every send) + `jarvis_chatbot_api.endpoint_problem` (https, the preset's own host and port, no user name - checked at open and again before every request; the key is attached only after it passes) + `_RefuseRedirect` (a redirect is refused, never followed) + errors in plain words that never quote the service's own error text + at most ONE retry, only after a 429 whose Retry-After is at most 20 seconds. Nothing is logged; the key is registered with `jarvis_scrub`. **A monthly money limit per service** (the owner, 2026-09-28: "a money limit comes before API chatbots are used for real"): no limit set = the service is not used (`ready` false, before any card); spending is estimated from each answer's token counts and a price list the owner can correct (defaults UNVERIFIED), per calendar month, in `chatbot/api-money.json` (numbers only, never the key); a service at its limit is refused before any card, and `before_send` refuses any message whose worst case would pass what is left. The card shows "About $X of $Y left this month". Limits and prices are set on the PC's command line only (`py -3 jarvis_chatbot_api.py limit|price|spent`) - no route |
| **chatbot comparison ("Ask several and compare")** (2026-09-28, the owner's "the chatbot driver becomes versatile", point 4; `jarvis_chatbot_compare.py`, JARVIS-API §87.7) - **BUILT, NOT YET TRIED FOR REAL**, on both apps. **No new host**: it uses the two rows above (and "a second AI on this PC", which leaves nothing on the PC), 2 to 3 of them on one graphics card, 2 to 4 on two (proposed numbers, the owner may change them), one after another | Exactly what the rows above send, once per chatbot picked: the goal word for word as the ONE card showed it, then that conversation's own follow-ups. Each chatbot's conversation is separate - no chatbot's words are ever sent to another, and the summary written from all of them stays on the PC | ONE card (gate action `chatbot_session`, tier `ask` only, risky, no "always allow") listing every chatbot by name and address, the goal and the limits per chatbot and in all; each conversation is an ordinary `jarvis_chatbot.run()` with its own `last_check` before every send; a chatbot that cannot go on is left out (never a captcha solved; an API service whose next message could pass its monthly money limit is left out too, and the card shows each one's money left); Stop, the task Stop and Stop everything end all of them; one comparison OR one conversation at a time |
| **the weather for the animals' scene, from Open-Meteo** (2026-09-28, the owner's decision "Weather in the animals' scene") - off by default, and only when the owner chose "Open-Meteo (online)" | The owner's rough position - the latitude and longitude of the town typed on the PC, rounded to 0.1 degree (about 11 km) - and the names of four weather values, in ONE plain GET of one fixed address, `https://api.open-meteo.com/v1/forecast`, about every 20 minutes and only while an app is showing a face (the PC reads nothing on its own timer). No name, key, cookie or anything else of the owner's; no proxy; no redirect followed; the answer capped at 64 KB and turned into five numbers that are drawn, never given to the AI model. ONE approval card to switch it on, naming the exact numbers; the yes covers that position only (a new town switches it off); off is at once | `jarvis_sky.request_weather` (the card: `change_own_config`, tier `ask` only, `leaves_this_pc`) + `jarvis_sky.read_open_meteo` (refuses a position the card did not name, immediately before sending) + `_default_open_meteo_fetch` (refuses any other address before a socket opens; `jarvis_local_http.public_urlopen`) |
| **the headless browser, Obscura** (2026-09-29, the owner's decision, given several times after the ban risk was explained: "integrate Obscura fully, stealth on for everything it runs", as an option Jarvis can choose per task beside the visible browser; `jarvis_obscura.py`, `jarvis_browser_engine.py`, `browser-engine.patch`, JARVIS-API §97) - **BUILT, NOT YET TRIED FOR REAL**: the owner installs Obscura's Windows program with one pasted PowerShell line that downloads ONE NAMED release (`v0.2.3`, never "latest"), prints its checksums for the owner to compare and does NOT run it, then runs the second command the line prints (the backend never downloads it; `PINNED_DIGEST` is empty, so the first checked file's checksum is remembered and a later different file refused until the owner accepts it on purpose), then turns it on with ONE `obscura_enable` card (a risky approval: a new program on the PC and a new way onto the web); off is instant and stops it. Nothing of it was ever run where it was built | The SAME things a visible-browser plan sends and no more: a navigation to an address on that plan's card (never one that leads to this PC, the home network, Tailscale or Meshnet, which is refused before Obscura is asked and again by Obscura's own guard), a click, the words the card showed typed into a box - to the sites the plan named. **Rule 1, exactly:** a `<secret>` step, a typed value or web address (path, query, fragment) that looks like a password, key or token, and a typed value or address query that repeats a saved fact are refused at plan time, before any card; a password, payment, file or hidden box is refused when it is reached; a message list is refused. **Not stopped:** an ordinary word the model chose to type that came from an email or a file it read - the card shows every typed word in full and, after outside text, says to check it (JARVIS-API §97.3). `--stealth` is always on (an ordinary Chrome's TLS fingerprint and profile; it solves no captcha, a site can still block or ban it, and the card says so and that signing in to a real account could get it closed). No proxy setting exists; no cookie or file is ever saved (its own error output goes to a plain-text `obscura.log`); running the page's own script, cookies, storage, tabs, key presses and PDF are not reachable. It opens no network port: it is driven over standard input and output. What comes back is outside text, read with hidden markup left out but with a warning that text hidden by a style sheet, off screen or in the page's own colour may remain. A click is checked (from where the page says a link or form leads, read as a browser reads it) before it is made; a redirect or a page that moves itself is noticed only AFTER it has loaded | `jarvis_browser_control.plan/describe/run` (the same ONE plan card listing every step, gate action `control_browser`, each step re-read and re-checked, the fence on the plan's sites) with the engine named on the card's first line + `jarvis_browser_engine` (switch off by default, `obscura_enable` tier `ask` only; `choose()` picks the engine and refuses in words rather than quietly switching browser; the engine acts only inside an approved run; a captcha, an "are you human" page or a sign-in page stops the run and hands it to the visible browser) + `jarvis_obscura` (`ALLOWED_TOOLS` allow-list, one program at a time, started only while the switch is on, 10-minute and 3-minute-idle limits enforced by a watchdog, 15-page and per-call limits, allow-listed environment, no `--http`/`--host`/`--port`/`--proxy`/`--allow-private-network`/`--storage-dir`) + `jarvis_browser_engine.stop_all` on the switch and on Stop everything + `_TurnWatch.took_in` (outside text, never a fact) + `jarvis_task_control` Pause/Resume/Stop. The chatbot driver, the support chats and "Solve it here" do not use it (they need a window the owner can take over) |
| **the phone's "a newer version is available" check and in-app APK download** (built 2026-09-24; download+install 2026-10-11; documented here 2026-09-29, the owner's decision after the audit: keep it on, and write it down) - the PHONE only, never the PC or the AI model: `net/UpdateCheck.kt`, `platform/UpdateChecker.kt` | The CHECK is one plain GET to GitHub for the public `client-latest` release of this repository: no token, no Jarvis data, no header naming the phone, no redirects followed, and the answer is only compared with this build's own commit. **GitHub does see the phone's IP address**, and that something asked about this repository's release. At most once every 6 hours when the app opens and every 24 hours while it stays open. **On by default, with a "Check for new versions" switch that turns it off entirely.** The DOWNLOAD only exists after the owner presses Download: one file from this repository's own release asset - **https only, GitHub's own hosts only, every redirect hop re-checked** (`isReleaseDownload`/`isGithubHost`), into the app's private cache, and **the APK's signing certificate must match the SHA-256 pinned in the app** (`UpdateCheck.SIGNER_SHA256`) before the file reaches Android's installer; nothing is offered until that matches, and no file is ever installed by Jarvis itself (Android's own installer screen does it). The app's network security config **forbids cleartext** (except the owner's own mesh hostnames the backend uses) and **never trusts a user-installed CA**. | one fixed URL (`UpdateCheck.URL`), `followRedirects(false)` for the check, a 512 KB answer cap, the setting and the timer in `UpdateCheck.due`; the pinned certificate + `afterFetch` before `Download.Ready`; `install()` accepts ONLY `Ready`; `res/xml/network_security_config.xml` (`base-config cleartextTrafficPermitted="false"`, no user certificates) and the manifest's `networkSecurityConfig`; `UpdateCheckTest.kt` and `UpdateSecurityTest.kt` |
| **ONE web page the owner hands over, read out loud** (2026-10-05, the owner's own request: "does jarvis have the ability for me to post a webpage into jarvis and it can read the content out loud?"; `jarvis_readpage.py`, `readpage.patch`, JARVIS-API §115) - the model's `read_web_page` tool, which is **off until `"read_web_page"` is added to `[tools].enabled`** (`jarvis-framework.toml`), like every tool but `web_search` | ONE plain GET of exactly the address the card showed. Nothing of the owner's rides along: no memory, no email, no file, no credential (rule 1). Never a link found on the page, never a second page, no POST, no form, no download. A `<title>` and the words a reader would see come back, in a 1,500-character window with a trailer naming the offset to carry on from. What comes back is OUTSIDE text: it is never learned as a fact, never saved to disk, and the model is told in words that a tool's text is data, never instructions. **Where the address itself is written down, said plainly:** it is on the card, so it is also on the gate's own pending-approval row while the card waits (`jarvis_gate.check` stores the card's `prompt`, capped at 500 characters) - true of every tool in this project, and not new here; the audit log holds outcomes and counts rather than the prompt, the apps' Activity list keeps a title and a decision, and `jarvis_readpage.py` writes no file of its own | THREE, in order: `jarvis_readpage.check_url` (shape only, no network: `http`/`https`, no control characters, no name-and-password in the address) + `jarvis_local_http.private_fetch_problem` (a REAL DNS lookup, run at prepare - so a private address means NO card is raised - and again immediately before the fetch) + `jarvis_local_http.public_urlopen` and `_PageRedirect` (the connection checks the address it actually connects to, and a redirect is followed only where the same check allows it). Then ONE card per address (gate action `read_web_page`, tier `ask` only, a risky approval: Windows Hello on the PC, a screen lock on the phone; the address in full; never an "always allow"), and `jarvis_agent._one_call` refuses the run at any tier when nobody was asked (`read_web_page` is in `NEEDS_A_PERSON`). The answer may be READ ALOUD: `read_web_page` is on `tools/gen_private_aloud_cases.py`'s `READ_ALOUD_TOOLS` beside `web_search`, so a voice turn speaks it, with every earlier rule first (a sensitive saved fact, a private question, the router's private gate, a dropped event stream) |

**Not a way out, but written here because it is a way IN: pairing a phone**
(2026-09-28, `backend/jarvis_devices.py`, JARVIS-API section 90). Two
routes take no key at all - `POST /api/pair/claim` and `/api/pair/collect`,
because a phone being paired has none yet. They answer only a Tailscale or
NordVPN Meshnet address that is not this PC (403 `not_mesh` otherwise), only
while the owner has pressed "Pair a phone" on the PC (10 minutes, one use),
and only to a request that proves it saw the QR code or the typed code
without sending either (HMAC sums); 3 wrong tries, from anywhere, end it.
No key is made until the `pair_device` card is approved on the PC with
Windows Hello, and it is handed over once. Nothing leaves the PC for it.

**Lockdown: every lane above at once** (2026-09-28, the owner's choice of
the research audit's idea 10; `backend/jarvis_asks_first.py`, JARVIS-API
§75). One tap, from either app, makes every lane in this table ask first or
stop, with no card; undoing it is the PC-only loosening of §3 (ONE
`loosen_what_asks_first` card plus Windows Hello). It is not a second gate:
`rebuilt/jarvis_framework.action_tier()` returns "ask" for a way out whose
line says "auto" or "notify" while it is on, so the gate asks for a chat
tool, and everything that runs by itself - it accepts only "auto" - stops
("tell me when", news, the briefing's reads). The few lanes the tier table
does not decide are switched beside it: the cloud model (the router's gate
"lockdown": not even offered), web search (always a card), the lights
setting (off), plug-in programs (a card at every start) and tool-update
checks (the card again). **Not yet covered:** the ntfy push lane, which is
sent from the owner's `jarvis_gate.py` - text made from Jarvis's own tables,
never payload, but still a way out; it needs a patch to that file.

**Not a lane: a library's own reports** (2026-09-28, research audit section
1.3). ONNX Runtime, which runs the voice and memory-search models, has its
own trace events ON by default in Microsoft's builds (its `docs/Privacy.md`).
On Windows they go to ETW, and only reach Microsoft if a trace session is
collecting and the owner's Windows diagnostic-data setting allows it.
Jarvis switches them off before any model loads, wherever the backend loads
onnxruntime itself: `jarvis_wakeword.py`, `jarvis_turn.py`, and
`jarvis_memory.quiet_onnxruntime()` before the memory search loads its own
meaning model or re-ranker on ONNX Runtime directly
(`backend/test_ort_quiet.py`). **Known limit:** sherpa-onnx (speech-to-text,
Kokoro, the voice check) carries its own copy of ONNX Runtime with no switch
Jarvis can reach. For that copy, Windows' own setting (Settings → Privacy &
security → Diagnostics & feedback → "Send optional diagnostic data" off) is
the control. The Hugging Face download library's reports are off
(`HF_HUB_DISABLE_TELEMETRY`), and so are the shared "do not track" switch and
`ANONYMIZED_TELEMETRY` (2026-09-30): `jarvis_child_env.py` sets all three in
Jarvis's own process when it is imported, adds them to the environment of every
program Jarvis starts (`inherited`), and `docs/INSTALL.md`'s start line sets
them before any library loads. Only those three names: a library with a switch
of another name still reports.

**The sun, the moon and the weather behind the animals, in one sentence each**
(the owner's decisions of 2026-09-28, `CLAUDE.md`; docs/JARVIS-API.md section
89). The sun and moon add no lane at all: the town is turned into a rough
position from a list the PC carries (`jarvis_sky_places.py`, GeoNames' towns),
never by a geocoding service, and each app works the sky out itself from that
position. The weather from the owner's own Home Assistant adds no lane either:
it is the owner's-own-accounts row above - the briefing's weather device, one
GET through the gate as `home_read`, only at tier auto. Only
"Open-Meteo (online)" is a new way out, the row above: what it sends is the
position rounded to about 11 km and nothing else, where is one fixed address,
and when it asks is once, when it is switched on, for that position.

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

**Tidying the inbox earns its own row, though it too reaches no new
destination** (the owner's decision of 2026-09-28, "inbox tidy by voice";
`jarvis_inbox_tidy.py`, docs/JARVIS-API.md section 95). The same account,
the same IMAP server and password as reading, sending and drafting - but the
second WRITE to the mailbox, and the first to change mail that is already
there: archive, star, mark as read, or move to Trash, a list of emails at a
time. What it changes: exactly the emails on its card, named one by one
(sender, subject, date; at most 30, and never more than one card can show
whole - past that it says "too many at once, narrow it" and lists nothing);
nothing else in the mailbox and nothing of the owner's elsewhere. Where: the
one mailbox in `JARVIS_IMAP_MAILBOX` (the inbox unless set), and for a move
the account's own Archive or Trash folder, found by `LIST`'s special-use
flag (Gmail: its labels), never a guessed name. **There is no permanent
delete** - "delete" only ever means Trash, and the module has no plain
`EXPUNGE`, no `CLOSE` on a folder opened for changes (it silently expunges),
and sets `\Deleted` only on ONE message after the server confirmed its copy,
on a server that can `UID EXPUNGE` it; a server that can do neither `MOVE`
nor that is refused before anything is touched. When it asks: always - every
tidy is its own card under gate action `tidy_inbox` (tier `ask` only,
never loosened by What asks first), and it is a risky approval (Windows
Hello on the PC, the screen lock on the phone) because it changes a mailbox
on a server; the card says at the top, in plain words, when reading outside
text (an email, a page) shaped the request. The card is approved on screen
only - a spoken "yes" approves nothing. Rule 1: the emails are found and
listed by code on this PC and only the local model asks for the tidy; the
model is told counts ("Archived 12 emails"), never a sender or a subject.
Looking at the emails to list them is a read of the same kind as
`email_check`, made before the card exists, so tidying is offered only while
`email_read` may look without a card of its own. **Undo, 10 minutes, one
tap, no card**: exactly what changed is put back (a move is found again by
its Message-ID; a flag only where Jarvis set it), and an email the owner
moved or deleted meanwhile is left alone and counted; the record is in
memory only, holds ids and no words, and ends at ten minutes or when the
backend stops. The desktop's widget shows one line of a card, so a tidy's
Approve, like an email's, opens the Jarvis bar (`is_email`, `isEmailCard`).
**Written down, not guessed: it has not been tried against a real mail
server** - only against a stand-in that fails loudly when the code does what
it must never do; the half-hour test in `backend/README.md` ("Inbox tidy")
is the proof, and Gmail's label calls are the part most in need of it.

**Saving an email draft earns its own row, though it reaches no new
destination** (2026-09-27, `CLAUDE.md`; docs/JARVIS-API.md section 40).
Reading and sending email both already reach the owner's own IMAP server on
the same account and password, so a draft's `APPEND` is not a new place
Jarvis can reach - but it is the first WRITE to the mailbox itself, ever
(every read here uses `EXAMINE`/`BODY.PEEK` - "No STORE, COPY, MOVE",
`jarvis_email.py`'s own docstring), which is a materially different kind of
request even to a server already listed, the same reasoning `jarvis_email_send.py`'s
own docstring gives for why sending needed its own plan and its own card
rather than a quiet extension of a read-only tool. What it saves: one draft,
exactly as its card showed it - From, To (may be empty), Cc (may be empty),
Subject and every word - and nothing else of the owner's; never sent. Where:
to the ONE mailbox the account's own server calls Drafts, found by `LIST`'s
special-use flag, never a hard-coded name. When it asks: always - every
draft is its own card under gate action `draft_email` (tier `ask`, and
nothing is saved on any other tier), there is no "always allow". Rule 1 and
the desktop's widget behaviour are identical to sending's, above -
`email-sending.js`'s `isEmailCard` and `email_sending.rs`'s `is_email` treat
`draft_email` exactly as they already treated `send_email`, so a draft gets
the same never-Markdown, never-widget-approve card without a second code
path.

**"Folders Jarvis may look in" adds no lane** (2026-09-26,
`jarvis_documents.py`, JARVIS-API §35): finding, searching and reading the
owner's own files in the folders listed on the PC, and bringing in a Notion
export, all stay on this PC. PDF and Word files are turned into text by
MarkItDown's document parts only (never its audio part, which sends sound to
Google, or its YouTube part), in a separate program with no passwords in its
environment; the text goes only to the model on this PC.

The owner's-own-accounts row was not in this table until 2026-09-25, although those reads
already left the machine; it was written down when the Google Calendar link
was added. Their settings were environment variables on the PC only until
2026-09-27 (the ease-of-use audit's row 15, "Security G3"): the IMAP
username and password, the private calendar link, and the Home Assistant
token can now also be entered once in the desktop's Settings, "Accounts",
which writes each straight into Windows Credential Manager on this PC
(`backend/jarvis_token_store.resolve_secret`, JARVIS-API.md section 44) -
never over HTTP, never to the phone. An environment variable the owner
already set still wins, unchanged. **The phone still has no screen to enter
any of them** - that stays on purpose (2026-09-25): a value typed on the
phone would have to travel over the link to the PC first, one more place to
keep a password safe, the same reasoning §8 gives for the web search keys.
Only the morning briefing's settings line says which calendar is read
("your Google Calendar (private link)"), in both apps.

**Which of these lanes is on right now is listed by code, in both apps**
(the Muse audit, 2026-09-25): "What Jarvis can reach" (`GET /api/reach`,
`backend/jarvis_reach.py`, JARVIS-API.md section 24) is written from the
same settings this table's code reads - `[tools].enabled`, the tiers, the
accounts' credentials (an environment variable or Credential Manager, either
way), the web search settings, the cloud lanes -
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

**News feeds and "tell me when this page changes", in one sentence each**
(the owner's decision of 2026-09-27, `CLAUDE.md`; docs/JARVIS-API.md
sections 30.3.1 and 46). What each sends: nothing of the owner's at all -
only the address itself, which the owner typed. Where: exactly that
address, and nowhere it links to - there is no code in either module that
follows a link, so "never follows links elsewhere" is not a policy sitting
on top of the fetch, it is the whole of what the fetch can do. When it
asks: once, when the address is ADDED (a feed) or WATCHED (a page) - a card
naming the address in full, action `change_own_config` for a feed (the same
action every "let Jarvis reach one more thing" card uses) or the
scheduler's own `schedule_repeat` for a page; reading it afterwards needs no
further card, only its tier (`news_read`/`page_read`, both `auto` in the
shipped file). What makes this row different from every other one above:
the address is not the owner's own account, so the guard is the REVERSE of
`plain_http_problem`'s - here the owner's OWN networks are exactly what
must be refused, checked by a real DNS lookup (never spelling, since a
name gives no protection against pointing at 127.0.0.1 or the home network)
and re-checked immediately before every later fetch, not only when the
address was first approved, because a name's DNS answer can change after
that (DNS rebinding) - and, since 2026-09-27, checked on the connection
itself, against the very address it connects to (`public_urlopen`), so an
answer that changes between the check and the connect (fast rebinding)
cannot get through either. One thing does leave before the card: adding
an address looks its name up in DNS first, to refuse a private one before
asking - the owner's DNS server sees the name the owner typed, nothing
else. A headline or a changed-page notification is treated
as outside text exactly like a calendar title: never learned as a fact,
and it marks the conversation that reads it.

**"Where this came from" adds no lane** (feasibility I42/I132, 2026-09-27;
`jarvis_sources.py`, JARVIS-API §55). It reads back, by reference, exactly
what the four reading tools above (`notes_search`, `web_search`, `my_files`,
`file_read`) already fetched THIS turn - it opens no socket of its own,
follows no link, and never fetches a web page to preview it. A web source is
shown as text with its host only; the full address reaches the owner's real
browser only when they tap it, through the same `open_external_url`/
`data-external` path every other outside link in the desktop already uses
(never a fetch Jarvis makes). The quote check beside it (a quoted phrase in
the answer checked against what was read this turn) is a plain word match on
the PC (`jarvis_sources.py`), never a model call and never a fetch either;
both apps only ever display its already-computed result. GET
`/api/chat/sources` is itself a read of this PC, behind the pairing token
like every other memory-shaped route - not a new destination, and gated by
the exact "Hide memory lists and chat history" check `/api/memory/used`
already uses, not a second one.

The **local model is also egress** if `OLLAMA_URL` does not point at this
machine, or if the "local" model is one of Ollama's cloud models (`-cloud` /
`:cloud`: reached through the Ollama on this PC, answered on ollama.com). The
learner checks both before it runs, and since 2026-09-25 (security audit H1)
so does the chat path: `jarvis_agent.run_local_turn` sends such a model
nothing and says why, and `jarvis_router.choose` gives it the gate
`cloud_model` instead of "stays on this machine". Anything else that talks to
Ollama must do the same. Not yet: the model switch and install routes (the
owner's `jarvis_models.py`) do not refuse a cloud model's name.

**Not a way out: "Solve it here"** (`jarvis_handoff.py`, 2026-09-28). A
picture of the paused chatbot or support window goes from the PC to the
owner's phone over the same authenticated link every answer uses
(Tailscale or Meshnet), and the owner's taps and typing come back. It stays
on the owner's own devices, is never saved on either, and sends nothing to
the website that the owner did not type or tap there - so it adds no row to
the table above. The window's own host lock stays as it was: a hand-off ends
the moment the window shows any host but the site's own, its sign-in hosts
and the one it showed when the hand-off began.

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
**"Also delete the chat it came from"** (2026-09-27) is a second, separate
yes/no on the same confirm, off by default: this ONE fact's own
`conversation_id`, read from its meta the instant before erasing strips it
out, is deleted from chat history too (docs/JARVIS-API.md §6, §18.1) -
never the earlier wordings `erase()` cascades to alongside it, which may
have been said in a different chat.

**"Forget a time frame" forgets; it never erases** (the owner's decision
of 2026-09-28; `jarvis_forget_range.py`, docs/JARVIS-API.md §64). Each fact
on its ONE approved card is `retire()`d exactly as Forget retires it -
`forgotten_at` included, so the past-recall rule and "not learned again"
treat it like any Forget - picked by `created` (when Jarvis SAVED it), never
by `valid_from`. For 10 minutes one tap on Undo un-forgets it
(`MemoryStore.unforget()`, the only way back from a retirement, and only
for a row still exactly as that Forget left it: an erase in the meantime
wins). The chats on the card are taken out of `chat-history.db` at once and
held in memory only, still sealed, until Undo or the 10 minutes or a
restart, whichever comes first. Wiping words stays "Erase the words", one
fact at a time.

**"Between us" is a label, not a new door into `facts`** (the owner's
decision, 2026-09-27; `memory-shared.patch`). `meta.kind = "shared"`, the
owner's own tap, marks a fact that already exists as a shared joke or
nickname - the same shape as the "Always keep in mind" pin above, except
the label lives in the fact's own meta rather than a second table.
`ERASE_KEEPS_META` keeps it through "Erase the words" (a label, never
words), and a Plain-manner turn's recall drops a shared fact before the
model ever sees it (`without_shared_in_plain`) - Warm may use it. Never set
by auto-learning or the model; docs/JARVIS-API.md §48 has the rest.

**Three tables are welded to one local rowid.** `facts` is
`id INTEGER PRIMARY KEY`, `facts_fts` uses `content_rowid='id'`, and
`facts_vec` is `vec0(fact_id INTEGER PRIMARY KEY)`. Any proposal needing
globally-unique ids — sync, sharding, cross-device dedup — is a three-table
migration plus a full re-embed, and `vec0` is a virtual table most extensions
cannot touch. Cost it honestly or design around it.

**The distance floor is inert on first boot.** It sits behind
`self.embedder.semantic`, and until the meaning model finishes downloading
the embedder is `HashEmbedder` with `semantic=False`. Until 2026-09-24, on day
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
always got. A bare month ("remind me in June") is not a past cue. Since
the memory review of 2026-09-27: when the question names a time, a CURRENT
fact that only became true after it is labelled too - "(true since
<date>)" when the owner's words gave the date, "(known since <date>)" when
it is only the day Jarvis was told (B1) - and **a forgotten fact never
comes back**, not even for a question about the past: Forget (the route,
or a "stop using this fact?" card) marks `meta.forgotten_at`, and past
recall skips it (B15). A fact replaced by a correction, or that simply
ended, is history and still recalled, labelled. Jarvis's own
`memory_search` tool uses this same recall (B4).

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
**"From now on ..." in a temporary chat obeys the same rule** (2026-09-27):
`jarvis_manner.set_temporary(conversation_id, manner)` holds that one
conversation's own manner override in memory only, keyed by
`conversation_id`, never written to `manner.json` - gone with the process,
like every other per-conversation map here (`jarvis_agent._OPENED`).

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
checks marked "the bug"). The last copy of the old rule, in the owner's
own `jarvis_extract._accept` (memory-safety.patch), went with the memory
review of 2026-09-27 (B12): keeping a correction card aimed at a fact that
ends later now retires it, like every other writer.

**Memory ideas 1-4** (the owner's decision of 2026-09-26, after
docs/MEMORY-RESEARCH-2026-09-26.md; backend/README.md "Memory ideas 1-4"
has the self-test numbers; docs/JARVIS-API.md §34):

```
fact_repeats  fact_id, said_at, how ("typed" | "voice")   "said again" - NO WORDS
```

- **The re-ranker** (idea 1). Chat recall only (`jarvis_past.recall` ->
  `search(rerank=True)`): the top 20 facts that pass every filter are
  re-ordered by a small cross-encoder on the processor
  (`Xenova/ms-marco-MiniLM-L-6-v2` on ONNX Runtime directly, Apache-2.0,
  English only) before the first `k` go to the model. It only re-orders - no
  fact added, `k` and both floors unchanged - and never touches `find_one()`,
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
  however often the learner re-reads it. The count can never make a fact
  harder to forget, correct or erase, and the only thing that may read it
  to decide anything is the tie-break below (off by default); Erase keeps
  the rows (ids and dates, like the fact's own dates). Shown as
  "said again 3 times" in both apps' "Saved automatically" list (the one
  list both apps read from a shipped module; the full memory list is the
  owner's `jarvis_hud` route and does not carry it yet).
- **"Said again" as a tie-breaker** (milestone 12, 2026-09-28). Chat
  recall only (`jarvis_past.recall` -> `search(said_again=True)`): after
  the fusion, the re-ranker and the cut to `k`, facts NEXT TO EACH OTHER
  that tie exactly - the same RRF score, and the same re-ranker score if it
  ran - are put in "said again" order, most first. It is a permutation of
  the final list: no fact added, dropped, hidden or faded, `k` and both
  floors unchanged, and no fact moves past one that scored differently.
  Never `find_one()`, corrections or anything that writes; a failure is the
  old order. **Off by default** (kept only once the PC's self-test shows it
  helps); `JARVIS_MEMORY_SAID_AGAIN_TIEBREAK=1` turns it on, and
  `eval_memory.py` measures it on its own "said again" line whatever the
  setting. Words only, it changed nothing on the golden set (2026-09-28);
  ties are commoner with meaning search on, so only the PC's run can say.
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

**The memory review of 2026-09-27** (docs/MEMORY-REVIEW-2026-09-27.md;
backend/README.md "The memory review's fixes" has every number). Rules it
added, each measured by the self-test before it was kept:

- **A fact that would change a stored one is a card**, even when the
  learner's model did not mark it as a correction (B5): the same slot with
  a different value ("Owner lives in Leeds" / "... in York"), or a change
  word ("now", "no longer", "moved", "quit") and two shared words. The card
  names the fact it would replace (`replaces_id`), like any correction; it
  never retires anything by itself.
- **The learner's own-words check reads clauses and tense** (B6, B7): a
  fact about the owner taken from the half of a sentence about someone
  else ("Dana works at Google and I work at Apple"), or said only in the
  past tense ("I lived in Paris") and saved as true now, is a card. Number
  words and digits are the same number ("three cats" = "3 cats", I3).
- **A sensitive topic stays with the fact** (B13). A fact saved after a
  card held back for a sensitive topic, or under "Also remember sensitive
  topics automatically", keeps that topic (`meta.sensitive`, a label -
  never words); read-aloud and web search use it when the words alone look
  everyday (`jarvis_sensitive.fact_topic`). Everyday facts about people stay
  normal (the owner's decision of 2026-09-26) - nothing is kept with them.
- **Other words for the same person, on lookup only** (I1): "boss" also
  looks up "manager", "GP" "doctor", mum/mom/mother, dad/father,
  flatmate/roommate/housemate, neighbour/neighbor - never partner, husband
  or wife, and never when saving (an alias is always the owner's own word).
- **One step out from a person** (I13): for a question that asks WHO
  ("for whose wedding?"), the fact saying who the person in the top fact
  is, at most two extra facts.
- **"Said again" after Erase is a day, not a moment** (I12): an erased
  fact's said-again times are rounded down to the day, the count kept.
- **Both memory models live in Jarvis's own folder** (B17,
  `~/.openjarvis/models`; the `FASTEMBED_CACHE_PATH` setting still wins when
  set, its name kept from when fastembed owned the folder so a PC that
  already set it keeps working), not the temp folder a disk clean-up
  empties.

**Smarter memory dates, "Where did I put ...?" and the overnight tidy**
(the owner's choice of 2026-09-28, docs/RESEARCH-AUDIT-2026-09-28.md
sections 3 and 8.5; docs/JARVIS-API.md sections 77-79; backend/README.md
"Smarter memory dates"). Each measured by the memory self-test before it
was kept (docs/MEMORY-SCOREBOARD.md):

- **"True until" is a label, never a hide.** `add()` reads an end date from
  the owner's words ("until 12 October", "the lease ends in December") into
  `meta.true_until`, with fixed rules like `true_from`. `valid_to` is NOT
  set from the words: a fact is never hidden on its own, before or after
  the date. Recall shows "(until 12 Oct)" while the date is ahead; once it
  has passed, the overnight tidy asks "Still true?" and only the owner's
  yes ends the fact - on that date.
- **A thing that moved is not a correction card.** A fact that says where
  a thing is (`jarvis_places.place_of`, fixed rules) and names a thing
  Jarvis already keeps a place for, somewhere else, is saved without the
  correction card when every OTHER automatic-learning check passes (a
  sensitive hiding place still waits); the older place is then ended as
  history, replaced by the new one - older news, by the owner's own dates,
  is filed as history instead. "Where is my passport?" is answered by the
  fast path from the places in use, without the model, and says it used
  memory (`injected_ids`), so the usual on-screen rules apply. This is the
  one place automatic learning retires a fact; it is limited to the same
  thing's place, and the retired place stays in the history.
- **The overnight tidy raises cards and nothing else** (`jarvis_tidy.py`).
  It is off unless the owner's "Overnight memory tidying" switch is on; one
  job on the one scheduler, at most once a day, paced by the back-off, at
  most five cards a night. "Still true?" (an end date that passed) and
  "Which is true now?" (two facts that may clash, found with the learner's
  LOCAL model, which is given numbered facts and returns only numbers - the
  Graphiti `resolve_edge` pattern). Every card is the ordinary "stop using
  this fact?" card, one fact each. Accepting one ENDS the fact as history
  (on its said date, or replaced by the newer fact), not a Forget - the one
  place `retire()` reads which card is being accepted (`_tidy_ending`: the
  `tidy_cards` row of the proposal in state `accepting`). A Forget from a
  list stays a Forget.
- **"Facts this chat taught"** (`GET /api/memory/conversation-facts`): a
  read of the facts in use whose meta names that conversation, for
  History's Delete to offer forgetting them - none ticked, then the usual
  "are you sure?", then the ordinary Forget, one fact per call.

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
each clip started, `source`, with the transcript) - and so do its answers
about the screen, unless the owner turned on the voice setting
`hands_free_screen` (owner, 2026-09-28; one approval card to turn it on,
off at once; JARVIS-API §16 and §62.7). A Jarvis Live turn (`source=live`,
JARVIS-API §63) is trusted like the talk button by default however Live
was started; the voice setting `hands_free_live` gives it the "Hey Jarvis"
caution when Live was started by voice, or always (owner, 2026-09-28; a
stricter choice at once, a looser one a card). A Live turn the model marked
as side talk (`[not for me]`) is never learned from, never counted and not
kept in chat history at all (owner, 2026-09-28; `jarvis_intake.owner_turns`,
`jarvis_agent`, `jarvis_chat_log.record_turn`). An ordinary Live turn counts
toward "suggest the bigger model" like any turn; a crisis turn never does,
and after one Live quietly gets more time (it does not end until at least
30 minutes after the last crisis turn) and skips the "minutes left" warning
(owner, 2026-09-28; `jarvis_live.Engine.note_crisis`). **When Live ends on
a PC with App lock on** is the voice setting `live_end`: by default when App
lock would ask again (talking does not count as being at the PC), or, the
looser choice, only when Windows itself locks - that one raises an approval
card; going back is immediate (owner, 2026-09-28).

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
  nothing is recorded and the apps say why. There is no plain-text path -
  **with one named exception**, the owner's of 2026-09-28 ("Chats, after the
  chat audit": "Support chats: export stays"): a customer-support chat's
  "Export transcript" (docs/JARVIS-API.md §65.5, desktop only), the owner's
  own record of what a company agreed to. It is written only by the owner's
  tap, to a folder they pick with the Windows "Save as" dialog, never to the
  clipboard, and the button and the file both say plainly that the file is
  not encrypted. Nothing else of the chat history ever leaves it in plain
  text.
- **The PC records the live turn, with where its words came from.** Only
  the newest user message of each request (and shared text sent just
  before it), tagged typed / voice / shared / pasted / clipboard /
  picture_caption, `unknown` when untagged. `voice` only when this PC's own
  speech route made those exact words. A conversation that ran a tool is
  marked from that turn on. Automatic learning trusts this - through an
  in-memory registry of the same facts (hashes, never words) that is kept
  even while history is off - instead of the history an app re-sends (the
  memory-safety audit). **One loosening, the owner's (2026-09-28, after the
  second chat audit):** when the PC meets a conversation it already holds
  in its own encrypted record (after a restart, or "Continue this chat"),
  it re-registers that record's typed and spoken user messages that did not
  read outside text - read from the PC's own record, never from what the
  app sends, and never shared, pasted, chatbot, support, crisis or imported
  text - so a continued chat does not fall back to a card for every fact.
  A Forget or Erase on the conversation is remembered across a restart
  (a floor in the history database), so the words cannot come back.
- **Deep questions are not kept at all** (`jarvis_big_model.py`, security
  audit L2, 2026-09-25): they live in memory until the backend stops. They
  used to be written to `deep-questions.jsonl` in plain text, outside this
  switch and its encryption.
- **Turning it back on is a card; off is immediate. No delete-all.**
  One conversation per delete, and both apps hold deleting and shortening
  the keep period on a stale link. Since 2026-09-28 deleting one offers to
  forget the facts it taught (docs/JARVIS-API.md §79): none ticked, each
  ticked fact forgotten through the ordinary Forget, one per call. The one
  exception to "one at a time" is "Forget a time frame" (2026-09-28,
  docs/JARVIS-API.md §64): the chats from some days, on a list the owner
  checks, deleted only after ONE approval card listing every one, with 10
  minutes to Undo.
- **Tags label saved chats (2026-09-30; `docs/CHAT-TAGS-DESIGN.md`,
  docs/JARVIS-API.md §99).** One tag per chat, chosen only by the owner (or by
  Jarvis when asked; never on its own). The tag names are the owner's words, so
  they are one sealed value in `meta`; a chat carries only an opaque `tag_id`
  number. No card - nothing leaves the PC - and tagging an already-saved chat
  works while history is off, since it records nothing new; with no key
  nothing is read or written. Tag names never reach memory, the learner, a
  search index or a log. The apps keep only which sections are folded.
- **"Fork from here" copies a chat up to a message (2026-09-30;
  `docs/CHAT-TAGS-DESIGN.md` section 8, docs/JARVIS-API.md §110).** A new chat
  "Fork of <title>", each turn sealed again under the new id; it counts as new
  (`updated` = the fork's moment) and keeps the source's tag and outside-text
  marks. No card - nothing leaves the PC. It gets its own learning hush (with
  the source's Erase flag), so copied words are neither learned nor counted
  as "said again" twice. Never for a support, chatbot or comparison record, or
  a chat titled "A difficult moment".
- **A temporary chat is never kept** (2026-09-25): nothing of it reaches
  `chat-history.db`, whether history is on or off (§5, "A temporary chat
  uses and makes no memory"). Since 2026-09-27 a game or role-play the PC
  spots is a temporary chat by itself; since the chat audit (2026-09-28) it
  is really never kept (`games-temporary.patch` used to hand `record_turn`
  the body without the flag) and both apps say so under the answer.
- **Every conversation has a kind** (the chat audit, 2026-09-28; the
  owner's decisions "Chats, after the chat audit" and "History marks Live
  sessions"; docs/JARVIS-API.md §18.6): `chat`, `live`, `support`,
  `chatbot` or `compare`, one column set when it is first written, plus an
  empty `project` column for Projects step 4. What each kind means for the
  rules:
  - `chatbot` and `compare` - a conversation Jarvis had with another AI,
    and "Ask several and compare" - are **kept** since 2026-09-28 (they were
    memory-only), in the same encrypted store, as ONE record each, every row
    role `chatbot`: never `user`, so the learner never reads a word of it;
    outside text as a whole; never read aloud (History is on-screen only);
    read-only.
  - `support` records are never removed without the owner's own tap on
    that record: "Delete conversations older than" keeps them (and says
    so), "Forget a time frame" lists them unticked, and Delete asks once
    more, naming what it is.
  - A conversation that held a **crisis** turn is kept, titled "A difficult
    moment", never with the owner's words (the crisis turn itself is never
    learned from or counted, §38 of the API).
  - Main's "Bring in chats from ChatGPT, Claude, Gemini or DeepSeek"
    (§85) does not add those chats to History - it only proposes facts - so
    there is no `imported` kind.
- **"Continue this chat" re-sends kept words only by the owner's tap**
  (2026-09-28). It does not make History a memory: nothing kept is ever put
  in front of the model on its own. Only the owner, from an opened chat or
  Live session, carries it on - the SAME conversation id, so its "read
  outside text" mark carries over (the PC decides that from its own
  record) - and only the newest kept questions and answers that fit a chat's
  own re-send limit go back, each with the tag it was kept under; a
  question whose answer was not kept, a Live side remark, and a
  `support`/`chatbot`/`compare` row never do. A temporary chat is never in
  History, so it can never be continued. Jarvis Live's "Move it here" is
  the same, for the one Live chat moving between devices (the PC's Live
  status names its conversation id).
- **A conversation ends after 30 quiet minutes** (2026-09-28), in both apps:
  the next question starts a new one, with one quiet line saying so; the
  old one stays in History. Never in the middle of Jarvis Live.
- **Searching your own old chats is a client-side filter, not a search
  feature.** 2026-09-26 said plainly that "searching past chat words waits"
  - that decision was about a NEW capability: a backend index or route over
    `chat-history.db`'s words, callable from a chat turn or the model, which
    would be a new way memory-adjacent text reaches the model without the
    review queue's checks. The owner's answer of 2026-09-27, "A search box
    in History for the owner's own old chats is allowed now", is a narrower,
    already-approved carve-out of that rule, not a repeal of it: a plain
    text box over the History list an app has ALREADY LOADED from
    `GET /api/history`, filtering it in the app - `ChatLog.filtered()` on
    the phone, `paintHistoryList`'s `needle` on the desktop - by
    conversation title only. No new route, no new index, nothing written to
    disk, and the search words never reach a model or a tool.
- **Searching what was said, for the screen only** (the owner's choice of
  2026-09-28, "Brain upgrades"; docs/JARVIS-API.md §71). This changes the
  written rule just above, and says how far: `GET /api/history/search`
  (`jarvis_chat_log.ChatLog.search`, `brain-reads.patch`) searches the kept
  turns' WORDS for the apps' History search box. Three invariants hold it
  to the owner's own words of 2026-09-27, "shown on screen only; nothing
  saved, nothing handed to the AI":
  - **No index, ever.** Each search opens every kept turn with the key, in
    memory, compares it and drops it. An FTS5 table, a word list or a cache
    between searches would be a plain-text copy of the chats on disk,
    beside the encrypted one - the "encrypted or not kept" rule above
    forbids it. The search words are not written, logged or audited
    (`test_brain_reads.py` compares every byte of the history folder).
  - **Not a tool, not a chat turn.** Only the apps' History screens call
    it, behind the token and hidden with the chat history under "Windows
    Hello for memory lists and chat history" / "Hide memory lists and chat
    history". `jarvis_agent.py` offers nothing that reaches it, and nothing
    it returns is put in front of the model.
  - **What the list shows, no more.** A temporary chat was never kept, so it
    is never found; what the keep period deleted is gone.
  "Find in this chat" is in the apps, over a conversation already open.
  What still waits on the memory self-test is the other half of the
  2026-09-26 rule: a chat turn that can ask Jarvis to search its own past
  conversations. "Anything that hands past chat words to the model" is no
  longer a flat no: the one exception is the next bullet, and nothing else.
- **Overnight suggested tags: the ONE way past chat words reach a model, and
  it is the local model, for cards only** (the owner's decision of
  2026-09-30, "any rule can change if the change is worth it";
  `docs/OVERNIGHT-TAGS-DESIGN.md`, docs/JARVIS-API.md §104). This changes the
  rule "nothing hands past chat words to the model", and says how far. With
  "Suggest tags overnight" on (off by default; turning it on is ONE approval
  card), `jarvis_tag_suggest.py` may, once a night between 01:00 and 06:00,
  give **this PC's own model** (`jarvis_sensitive.learner_model()`, checked
  loopback and not an Ollama cloud model by `jarvis_auto_learn.check_local_model`;
  never a cloud lane, so rule 1 holds) the owner's OWN first six typed or
  spoken messages of up to five untagged chats, at most 1,500 characters
  in all per chat, with the tag names. Never Jarvis's answers, never another chat, never
  memory. Which chats may be read is decided in `ChatLog.suggest_candidates`,
  beside the key: not one that read outside text or holds shared, pasted or
  picture-caption words, not a crisis chat, not Live, support, chatbot or
  comparison, not one under a Forget/Erase hush or marked as bank spending,
  not one still in use (idle over 30 minutes), not a declined one. The model's
  reply can only PICK a tag name that already exists (checked exactly, by code);
  it can neither make a tag nor do anything else, and what it returns is
  never stored, logged or shown. The result is a card per suggestion
  (`chat_tag_suggest`, tier `ask`; at most three a night; a chat is filed
  only when a person taps Approve, through the same function the owner's own
  tap uses). Everything above about **no index, no summary, nothing kept
  beside the encrypted file** still stands: no embedding, no stored model
  output, no chat words in `meta` (only opaque chat ids, counts and dates).
  It is not a tool or a chat turn: only the scheduler's quiet hourly step
  (`tag_suggest`) reaches it. Searching the owner's own past chat words for a
  chat TURN still waits, as above.
- **"New section here" is a divider, not a fork in what Jarvis reads** (owner,
  2026-09-30, JARVIS-API §106): a sealed list of turn numbers in the `marks`
  table. View-only: Jarvis still reads the whole chat the same way, and a
  marker reaches no model, learner, memory or index.

### Money-sensitive conversations — a mark, not a taint

Once `my_spending` has been called in a conversation (bank spending added up from a
file the owner dropped in a folder, JARVIS-API section 100), **the conversation is
marked money-sensitive** (the owner's answer, 2026-09-30). It is the standing limit made
to hold across turns: money is never sent to a web search or a chatbot. The mark is kept
by `jarvis_chat_log` in its `meta` table (`money:<conversation id>`, no words), so it
survives a restart, "Continue this chat" and a fork (which copies it), and is set in
memory for a temporary chat. While it is set, a web search **asks first** (its card says the
conversation looked at bank spending) and `POST /api/chatbot/start` with that
`conversation_id` is refused. It is deliberately **not** the outside-text taint: every
other tool works as before, and `my_spending` is still left out of `tools_ran`, so the
memory-writing rules that read `tools_ran` do not change. Inside the turn itself the
model's words are held until code has checked them (with a table: the sentence rule; with
none: no amount of money may pass; JARVIS-API 100.5). Closed 2026-09-30: `my_spending` and
`retirement_whatif` are both refused, with a plain reason, while the Money topic is Off or
"Learn, but don't use" (`jarvis_topics.starter_use_blocked("money")`, checked in
`jarvis_agent._spending_refusal` / `_retirement_refusal`); no table is made, so the chat-table
route has nothing to serve. Project benchmark numbers are unchanged: they are already kept on
screen and never reach the model.

### Review decks — a third sealed store, kept apart from memory and from chat history

`study.db` (`jarvis_decks.py`, `decks.patch`, 2026-09-30, docs/JARVIS-API.md
§102, docs/QUIZ-DECKS-DESIGN.md) holds **the owner's own words on this PC**:
questions the owner chose to **Keep** from a finished quiz (the question, the
owner's answer in their own words, and the passage it came from, which may be
copied from anything the owner pasted). It is not memory and not chat history:
nothing in it is recalled into a chat, read by the learner, searched, sent to a
model or a cloud lane, and no model tool or voice command makes a deck or a
card - only an app's tap does. The invariants:

- **Sealed or not kept.** Deck names, fronts, backs and passages are
  AES-256-GCM (the chat-history scheme) under a key of their own in Credential
  Manager (`Jarvis Backend/study decks key`); deleting that key never touches
  chat history. No key, no `cryptography`, no `fsrs` (the schedule maths,
  py-fsrs 6.3.2, pinned) or a key that does not open the file: nothing is kept
  and the apps say why. Only ids, the card kind, the level tag, the paused flag
  and py-fsrs's numbers are plain, so "N cards ready" needs no key.
- **Spanish practice** is a mode of the quiz (`mode: "spanish"`), typed only
  (a client must not do speech-to-text). Fill-the-blank is cut and marked by code;
  translations and sentence endings are marked by the local model; a key the
  model wrote is labelled. Its crisis check is English only and every Spanish
  page and the Keep sheet say so.
- **Reviewing calls no model**: the owner rates each card. No streak, points or
  guilt words anywhere.
- **Backups (owner, 2026-09-30).** `study.db` is in the locked backup, under the
  same recovery code, and so is its key, carried the way the chat-history key
  is (JARVIS-API §45.1). A deleted card or deck is
  gone from the file at once (`secure_delete`, then `VACUUM`) but not from older
  backups, and the delete question says so: "Copies in older backups stay until
  they age out." "Forget a time frame" does not cover decks.
- **No approval card**: every write is the owner's own tap on the owner's own
  words on this PC; the apps hold every write on a stale link (rule 4) and hide
  the words under "Hide memory lists and chat history".

---

## 6. Events — one bus

`jarvis_events.Pump` runs the pollers on one thread; every client learns state
changes from it and from nowhere else. Kinds: `approval`, `proposal`,
`finding`, `power`, `persona`, `model`, `activity`, `appearance`, `step`,
`deep`, `memory_saved`, `schedule`, `focus`, `wellbeing`, `hello`. (`step` is the tool loop saying what it is doing - asking the model,
a tool starting, finishing or refused - with tool names from its own table
and nothing else; `jarvis_agent._step_event`. Brain → Now renders it (the
tab was called "Live" until 2026-09-28, renamed so it is not confused with
Jarvis Live).
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
§31.
`wellbeing` is the serious moment of a crisis answer, `{"serious": true |
false}` - one boolean, never a word - `jarvis_wellbeing.py`; added
2026-09-28 (the owner's "At serious moments the animals drop the cute
gestures"). The animal faces hold a neutral pose while it is true; the
PC's spoken sound turns plain by itself (no app change). The desktop reads it
and holds the serious pose (`noteWellbeing`, `jarvis-desktop/src/jarvis-link.js`);
the phone's side of it is still to build - JARVIS-API §38.1 says what each must read.)

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
  invariants live, for a model that has one. Both from one line. If delimiters
  are ever added around recalled facts, they go on that message, not around the
  list.
- **The rules block always goes first; everything added to a turn goes after
  it.** The spoken-style note, the "you were interrupted" note, the owner's
  manner line (warm or plain, `jarvis_manner.py`, 2026-09-25) and the crisis
  note (`jarvis_wellbeing.py`, 2026-09-27, nearest the question of all of
  them) are system lines placed just before the newest question, and
  `keep_rules_first` puts the rules in front whenever anything else would be
  first. Manner is wording only: its line says every rule still applies, it
  changes no tier, card, memory or egress, and it is never sent to a cloud
  lane. **Humour** (2026-09-27) is not a third line - it is a clause appended
  to the SAME manner line, only when the owner's own switch is on, and it
  says its own limit in words (never a card, an error, or a serious topic)
  rather than a code path enforcing one. The crisis note is stricter still: on a match, no tools are offered
  that turn at all, and the fixed help message (`jarvis_wellbeing.reply()`)
  is appended after the answer, or sent alone if the model fails - the one
  place in this codebase where the backend, not the model, adds words to a
  reply. Neither approves or acts (rule 4): both only change what is said.
- **The rules are SENT, not assumed, on every local turn (2026-10-14;
  `with_rules_first`, `backend/jarvis_agent.py`).** This is the correction to
  the line above: `keep_rules_first` only repairs a request in which something
  else would be first, and then trusts Ollama to prepend the Modelfile's
  `SYSTEM` block - which only happens for a model that HAS one. The owner's
  everyday model since 2026-10-10, `qwen3.5:9b`, is a plain library pull with
  no `SYSTEM` of its own, so on a fresh main-lane turn the request was the
  question and nothing else: the persona invariants, including "Never claim an
  action was taken that was not", were not in front of the model on the lane he
  actually uses. Every local turn is now sent `LANE_SYSTEM` as its first
  message, before trimming (the room `budget()` already reserved for it via
  `_TEMPLATE_TOKENS`), from ONE function that the main lane, the second card
  and the warm-up's `chat_prefix` all call - so a recalled-facts turn or an
  app's own leading system message cannot end up with two competing system
  turns. Cost, measured on his PC: +340 prompt tokens a turn. What it does NOT
  fix, measured: tool-call rates (35 of 35 calls both before and after, with
  `change_setting` offered) and, at this sample size, the rate of claimed-but-
  undone answers. `backend/test_lane_prompt.py`, `docs/JARVIS-API.md`
  ("The main lane hears the rules") and the PR that landed it have the numbers.
- **The character block** (feasibility I129, 2026-09-27,
  `docs/CUTTING-EDGE-2026-09-26-round4-character.md` section 1): a short,
  named-trait paragraph - "Who you are: Jarvis... Honest before agreeable...
  You are software... Humour: a light, dry touch at most..." - added to the
  END of the rules block, in all three copies word for word
  (`jarvis-primary.Modelfile`'s `SYSTEM`, `jarvis_agent.LANE_SYSTEM`,
  `jarvis_profiles.JARVIS_SYSTEM`; `test_agent.py`, `test_profiles.py` and
  the new `backend/test_character.py` hold them equal). It answers first,
  puts honesty ahead of agreement even when the owner is upset or pushing
  back, and rules out claimed feelings, a body, a past, or "sir" - short
  named traits, not a prose self-portrait, because a small model holds a
  named trait far more reliably (PAI-Bench, cited in the research doc). A
  humour clause in the SAME paragraph is a fixed limit in words (never on a
  mistake, health, money, safety, an upset owner, or a refusal) - separate
  from, and stricter than, the owner's own Humour switch
  (`jarvis_manner.py`), which can only turn casual chat humour on or off,
  never override this. **`_TEMPLATE_TOKENS`** (`jarvis_agent.py`), the room
  `budget()` leaves for the rules before trimming a long chat, is worked
  out from the rules' real length (`estimate_tokens(LANE_SYSTEM) + 100`),
  not a flat guess - a flat number happened to cover the old, shorter rules
  and would have quietly run over once the character block made them
  longer, and Ollama drops the oldest turns without saying so when a
  request runs over its context. **The character check** (I133/I134): the
  model-facing half is `tools/tool_eval/behaviour_cases.py`'s "behaviour"
  suite (run by `tools/tool_eval/ollama_tool_eval.py --models jarvis-primary`
  on the owner's PC, or `--selftest` here with no Ollama) - it already
  covers identity, "I don't know", holding a right answer under pushback,
  no fake actions or feelings, outside text unable to change who Jarvis is,
  spoken and Plain-manner answers, humour limits and ten-turn drift; the
  character block added two more cases (not the film's JARVIS, honesty
  under emotional pressure). `backend/test_character.py` is the no-model
  half: the block is in the rules, under a token cap, `_TEMPLATE_TOKENS`
  covers them, the key phrases are there, and no existing rule is weakened.
  `selftest.py`'s "model" preflight step reads `/api/show` for
  `jarvis-primary` and WARNs, with the exact `ollama create` line, when the
  model's own stored rules do not match `LANE_SYSTEM`. Since 2026-10-14 the
  rules are in EVERY local request (`with_rules_first`), so the mix this warns
  about is now two copies of the rules - Ollama's own collation keeps one
  system block - rather than the old block surviving on the turns
  `keep_rules_first` did not fire. The warning is kept: a model whose stored
  block is stale is still a model built from an older Modelfile, and the
  `/api/show` check is the one place that is visible. **It does not cover the
  owner's everyday model at all** - it is keyed on the name `jarvis-primary`,
  and `qwen3.5:9b` has no stored block to compare, which is exactly how the
  2026-10-14 fault went unseen.
- **Style rules for every fixed line** (feasibility I135, 2026-09-27): a
  card title, a quick answer (`jarvis_quick.py`, `jarvis_sayable.py`,
  `jarvis_reach.py`, `jarvis_identity.py`), a focus callout
  (`jarvis_focus.py`) and the JSON files both apps read those words from
  are none of them written by the model, so they hold to the SAME rules
  the manner line already does, checked by `test_manner.py`
  (`t_style_rules_for_every_fixed_line`): no emoji anywhere; no "!" on a
  card specifically (an error or a quick answer may still need one, in
  principle, though none does today); never more than one "sorry" in the
  same line; and no film phrases - "sir", "at your service", or the dotted
  "J.A.R.V.I.S." spelling. Warm and Plain must still carry the same facts
  in different words (the manner line's own rule, extended to every other
  place two wordings exist).
- **The older `[persona]` modes** (`jarvis-framework.toml:1032-1044`, eight
  built-in names in a comment, one shared fence for all of them - not eight
  individually fenced definitions, which corrects the character research
  doc's own description of this section) do not conflict with the
  character block where the toml is specific: its fence already protects
  "whether it tells you it is unsure" and "whether it is willing to
  disagree with you" by schema, agreeing with "Honest before agreeable".
  Humour and claimed feelings are not on either of the toml's lists - a
  named, open gap, not a live conflict; `jarvis_persona.py`, which would
  settle it, is not in this repository. Full write-up:
  `docs/PERSONA-MODES-CHECK-2026-09-27.md`.

---

## 8. The clients

**Desktop** (`jarvis-desktop/`): Tauri 2, nine windows (quickbar, widget,
HUD, Brain, Faces, onboarding, Settings, the floating face, the Jarvis Live
badge - one capability file each in `src-tauri/capabilities/`), per-window ACL capabilities. The Rust commands are the real API — buttons are a courtesy, and
any window holding the capability can call them, so a check that lives only in
the webview is not a check. `decide_approval` consults link staleness in Rust
for exactly that reason.

No desktop page holds the pairing token. The HUD page (vendored from the
backend) used to be given it; since the apps security audit (M2,
2026-09-25) its requests go through Rust (`hud_proxy.rs`: a fixed list of
reads, its chat, the right/wrong mark). Approvals **are** answered in the HUD
since 2026-10-16 (the owner's ask, §3), and they are answered through the same
`decide_approval` the Jarvis bar and the widget call - `capabilities/hud.json`
holds one command for it, `hud-approvals` -> `allow-decide-approval`, so
Windows Hello, the stale-link refusal, the cut-off refusal and the App-lock
rule apply there unchanged. What that page's own `fetch` still cannot do is
post a decision itself: `hud_bootstrap.js`'s shim refuses `/api/approve` and
`/api/deny` whatever the link is doing. **The same file also keeps a private
answer on screen there** (2026-10-16, the owner's decision *"Gate it - keep
sensitive answers on screen in the HUD too"*): that page is the one surface
which reads a TYPED answer aloud, and its `speechSynthesis.speak` is now
refused for an answer whose route says `injected_sensitive` above 0 or
`gate: "private"`, with the bar's own line ("It's on your screen.") drawn
under the answer instead - the rule of `docs/JARVIS-API.md` §16 step 3, read
off the route the page already has. It is a decision, not an oversight: the
step-3 exception that a typed question may be read aloud is removed in that
one window and nowhere else. No window may `emit` events to the
others either (M1).

**The HUD page draws only while it is being looked at** (2026-10-23, the
idle-power review). Its Galaxy map has one drawing loop, and it runs only while
the Brain map is the view on screen **and** the window is visible: leaving the
map or hiding the window stops it (the loop is not re-armed), and returning
re-measures the picture once and starts it again. A hidden window also pauses
the page's two endless animations - the answer caret and the pressed talk
button. The live paths are deliberately untouched: the event stream and its
reconnect, the approval reads, speech and audio, and the face window's own
lifecycle (the face was already unloaded when the Talk view ends). No route,
permission, approval card or new dependency is involved; the page is still
replaced whole by the normal shipped-file copy. The Brain window needs no such
guard: its constellation settles once and stops.

**A face never pretends Jarvis is there** (owner, 2026-09-28). When the
link is down or stale for longer than 12 seconds - the same grace on both
apps, long enough to cover the hourly reconnect - every face (widget,
floating face, HUD) shows **standby with a hollow ring** round it, the
tray icon's "nothing is coming through" shape, and says "Jarvis isn't
connected" to a screen reader. The approval face does not wait for the
grace: it goes the moment Approve is blocked (rule 4). Desktop:
`jarvis-link.js` `faceSignal` (`OFFLINE_GRACE_MS`), `faces.html`
`drawOfflineRing`; phone: `FaceView.kt` `drawOfflineRing`. The ring, the
same on both: a full circle at 0.4532 of the face's short side (just
outside the approval clock), a stroke of max(1.5 px, 0.008 of it), fully
opaque, in the colour bound to the state shown (standby's neutral grey
unless the owner chose another) dimmed toward the ground by that state's
own dim - a fixed colour, so it never breathes. (Until 2026-09-28 the
desktop drew the pattern's second colour of the moment at 60% opacity,
which breathed with standby's pattern and measured about 1.1:1 against the
ground; the phone already drew this one, about 1.6:1.) An animal shows no
sleeping Zs while the ring is up - "not connected" is not "asleep"
(docs/CRITTERS.md). The tray follows the same rule since 2026-09-28: a
dropped link paints the hollow icon in standby's colour, and a stale link
never paints the approval colour (`tray.rs` `spec_state`).

**The animal faces' display options** - the sleeping Zs, "Keep the animal
still", the serious moment and calm motion - are on both apps, drawn from
the same numbers (docs/CRITTERS.md, "How they move"). Since 2026-09-28
every animal option is in ONE place in each app, "Animal options"
(docs/JARVIS-API.md section 60): "Keep the animal still" and the behaviour
switches (listening nods, focus buddy, small acknowledgements, petting,
cute idle moments, seasonal touches - for every character face, the robot
included) are kept on the PC and shared by both apps
(`jarvis_animal.py`, `/api/animal`; the values also ride in
`/api/appearance`), like the sun, moon and weather (`/api/sky`); sharpness
and frame rate stay on each device. Jarvis changes any of them when asked,
with the same rules as the switch. No card for any of them - they only
change how the animal moves - except Open-Meteo weather, which keeps its
one card.

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
  launch, a normal start, and the quiet raise for an arriving card - goes
  through the App lock, either `lock::may_open` or
  `windows::show_hud_quietly`'s own refusal). The widget stays on the
  desktop, but while App lock is on its approval card shows only the notice's
  title, and its Approve opens the card in the Jarvis bar - behind the lock,
  where Windows Hello is asked first and `heavy-approve.js`'s delay-and-scroll
  gate applies; `decide_approval` refuses an Approve from the widget in Rust as
  well. Deny works from the widget, as from the phone's. An email's card
  (`send_email`, 2026-09-25) is approved in the Jarvis bar only, lock or not:
  the widget shows one line of a card, and an email is approved after reading
  all of it (`commands.rs` `waiting_email`, `widget.js`). **Notes too** (the
  owner's decision of 2026-09-26): with App lock on, the widget offers no
  note to a running task or a card, and `inject_task_note` and
  `amend_approval` refuse the widget in Rust - notes are added in the
  Jarvis bar, which asks Windows Hello first. **The widget's own tiles
  too** (the owner, 2026-09-28): with App lock on, Focus session, the
  10-minute timer and Play/pause open the Jarvis bar instead of acting,
  in `widget.js` and again in Rust (`brain/widgets.rs`). Stop everything
  (the hotkey, the tray row and the widget's tile) is never behind App
  lock. **The floating face**
  (2026-09-27) is not covered either, for a shorter reason than the
  widget's: it shows no approval card at all, ever - not even a title -
  only which of eight states Jarvis is in, the same information the tray
  icon already shows to anyone at the keyboard. **What it holds is wider
  than what it shows** (bug audit 2026-09-27, desktop-rust finding #4): its
  `jarvis-link` grant includes `get_pending_approvals`, and
  `core:event:allow-listen` lets it hear the full `jarvis-event` stream, so
  the window's own memory carries every waiting card in full - an email's
  whole text included - the same way the widget's does, for the same
  reason (both read the one shared link module, `jarvis-link.js`, rather
  than each keeping a separate connection). Release builds have no
  developer tools (`Cargo.toml`'s `devtools` feature), so nothing outside
  this app's own code can read that memory; `capabilities/floating.json`'s
  description says so.
- **Phone:** the whole app - including Home's "Stop everything" button,
  which is behind App lock like the rest of the app (JARVIS-API §28); the
  PC's hotkey and tray row are not. **Quick Settings tiles** (2026-09-28,
  JARVIS-API §81.2) sit outside the app: a "Stop everything" tile is not
  behind App lock either, like the PC's hotkey (it only stops things); a
  "Brief me" tile only opens the app, so App lock asks as usual; the timer,
  focus and PC play/pause tiles show nothing private and, with App lock on
  and the phone locked, ask for the phone's own unlock first. No tile can
  approve or deny. The "tap to turn \"Hey Jarvis\" back on" notice after a
  restart (§81.1) opens the app, and listening starts only after App lock. The home-screen widget only ever shows the
  `notice` text and offers Deny only, lock or not. **The floating avatar**
  ("Floating Jarvis", §56) is not covered either, for the same reason as the
  desktop's floating face: App lock does not change what it shows
  (`floatingAvatarShowsContent`, `data/FloatingAvatar.kt` - matched to the
  desktop by the owner's decision, 2026-09-27, cross-cutting audit finding
  #7, after the two apps were found to disagree). It shows only whether the
  PC is reachable and whether this phone is listening at all - never a word
  Jarvis heard, said or is about, and there is no button on it to act with.
- **Watches and other bridged devices (phone, 2026-09-26):** every
  notification Jarvis posts - approvals, timers, alarms, reminders, "tell me
  when", the link and wake-word status - is local only
  (`setLocalOnly(true)`; `NotificationsStayLocalTest` checks every builder),
  so Android does not copy it to a paired smartwatch. Still open: whether
  Android 16's lock-screen widgets can show the home-screen widgets (both
  declare `widgetCategory="home_screen"` only, not `keyguard`); not checked
  on a real phone.
- **Screenshots (both apps, the owner's decision of 2026-10-11 for the
  desktop):** while App lock or "Hide memory lists and chat history" is on,
  Jarvis cannot be screenshotted, screen-recorded or cast. On the phone that
  is `FLAG_SECURE` (`SecurityRules.blockScreenCapture`); on the PC it is
  `WDA_EXCLUDEFROMCAPTURE` on every window of the app
  (`Security::blocks_capture`, `lock.rs`). What the PC's half does and does
  not stop is in the one-sided table below.
- **No lock, no risky approval (both apps, the owner's decision of
  2026-09-25):** a risky approval is refused on a PC without Windows Hello
  or a phone without a screen lock, whatever the lock settings say, with
  the same words in both apps - each led by "Nothing was approved." (the
  desktop adds it before the backend's own sentence, `not_approved_words`) (`lock/rules.rs` `NO_HELLO_NO_RISKY`,
  `SecurityRules.NO_SCREEN_LOCK`) and, on the phone, a button that opens
  Android's screen-lock settings. It used to go through unchecked when no
  lock was on. On the PC the backend refuses too (§3, "The approval gap").
- **Inbox tidy's Undo strip (2026-09-28, JARVIS-API §95):** the tidy itself
  is an ordinary approval card (a draft's or an email's rules: shown
  verbatim, approved in the Jarvis bar only on the PC, risky on both). The
  Undo strip after it holds counts and the PC's words, never a sender or a
  subject. **Desktop:** while App lock has locked Jarvis, or "Windows Hello
  for memory lists and chat history" hides the lists, Rust takes the words
  out of the status (the strip says only "Your inbox was tidied. You can undo
  it for a few minutes.") and refuses Undo until the owner unlocks. **Phone:**
  the strip lives on Home, behind App lock like everything on it; while the
  lists are hidden it says the same short line and Undo waits for Show. Both
  apps hold Undo on a stale link (rule 4: it acts on a mailbox).
- **Private views on the server (2026-10-20, Q1):** the Guardian's journal and
  diff, the person dossier and the action-receipts list all accept
  `?app_locked=1` / `?hide_memory_lists=1` from the desktop, and a locked view
  answers the honest marker (`"Hidden while App lock is on."` / the hidden-lists
  sentence) with no names, diffs, summaries or rows - the store read is skipped
  entirely. The merge lives in `jarvis_private_view.py` and is fail-safe: it ORs
  the trusted in-process state with the request's flags, so a request can only
  ADD withholding and a `0`/`force_unlock` key can never unlock; only the
  trusted `note_state()` hook can clear it, and an absent hook means unlocked.
  **The live HUD must eventually pass its App lock / hidden-lists state** - that
  wiring is not in this slice, so until it lands each app's own hiding above is
  what protects the view. **Q2's `traces.db` retention cap is not a live-HUD
  delta and is no longer BLOCKED:** `traces.db` has no writer in this repository
  or on the live HUD, and this wave deliberately adds none. The cap ships in the
  shipped modules instead - `jarvis_sqlite.trim_table` / `idle_maintenance` caps
  any `traces.db`'s `traces` table at the newest 10,000 rows, and
  `jarvis_initiative.sqlite_maintenance` calls it from the 30-minute heartbeat -
  so deploy step 1 carries it. The live PC already has both modules (measured
  2026-10-23: byte-identical to `origin/main:backend/...`) and no `traces.db`;
  the reconcile tool's old `traces-retention` BLOCKED entry was retired on
  2026-10-23 (RA-5) and its dry run reports 0 blocked deltas. The cap acts only
  if a store from an older build or a backup restore appears.
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

### Who restarts a dead model lane, and what every client does about it

Added 2026-10-14, with the owner's decision *"Also restart the lane automatically
when it dies."* The BACKEND owns it (`backend/jarvis_model_lanes.py`, armed in
the install block `model-lanes.patch` adds): one daemon thread, one loopback
`/api/tags` probe of the lane the chat uses every 30 s, no model call, and a
restart through the same `start()` the button uses - the owner's own Windows
logon task, looked up on that PC by the stable half of its name, as argv, never a
shell. `docs/JARVIS-API.md` §137.3 has the route, the numbers and what happens at
the cap.

**Both apps, and nothing one-sided.** The Jarvis bar and the widget draw it from
one file (`jarvis-desktop/src/lane-auto.js`), through Rust
(`set_model_lane_auto`); the phone draws it on Home's status line (`net/ModelLane.kt`,
`JarvisRuntime.setLaneAuto`). All three read `/api/model-lanes` on the beat that
already reads `/api/status`, **whether or not the standing warning is drawn** -
the sentence is news about a lane that has come BACK, which is exactly when that
warning has cleared. The words are the backend's own (`auto_note`), drawn
verbatim: no client composes a sentence out of fields, so the three cannot come
to three ways of saying one fact. `tools/check_parity.py` carries
`/api/model-lanes/auto` as `ported`.

**The HUD window (`jarvis-desktop/src/jarvis_hud.html`) keeps only the standing
line** - no button, no automatic line, no switch - for the reason it already had
no button: it is vendored from the backend and runs under `hud_proxy.rs`, which
allows it exactly five reads and one `POST /api/chat`, and widening that
allow-list for routes that start a program on the PC or change a setting is a
separate decision. Both windows that carry the action are one keystroke away.

**THE RESIDUAL RISK, STATED PLAINLY.** An automatic restart cannot tell "it
crashed" from "I meant to turn it off": a dead process carries no intent, and
`schtasks` reports the same "Ready" either way. So with the switch ON - which is
the default, because that is what the owner asked for - **Jarvis will start a
lane that was stopped deliberately, and will say so in both apps.** The switch
(section 3 has the permission argument: no card, in either direction) is the only
honest answer, because he is the only one who can say which it was. Nothing is
hidden about this: it is in the module's own header, in `JARVIS-API.md` §137.3,
and in this paragraph.

### One-sided on purpose

The two apps are meant to do the same things. These are the exceptions, each
with its reason, so a gap is never mistaken for an oversight (or an
oversight for a decision). `tools/check_parity.py` checks the ones that are
backend routes, in both directions; the rest are listed here only.

**The microphone recovery is the desktop's, on purpose** (2026-10-21;
JARVIS-API §5.2, Slice D of the Live & Voice program). Only the desktop opens
THIS PC's input device (`jarvis-desktop/src-tauri/src/voice.rs`), so only it
can re-open that device when the first 400 ms of a recording are exact digital
zeros, and only it can hold a bounded 300 ms pre-roll in front of a
talk-to-type clip. The phone's equivalent is the phone's own capture: it
uploads a complete clip, and the PC's `hear()` still says the same sentence
(`silent: true`) for a clip whose opening is exact zeros, so a deaf phone
microphone is described in the same words. Nothing is added to the phone's
screens, no route changes, and `tools/check_parity.py` has nothing new to
classify.

**The `/api/presets` spelling is desktop-HUD-only, and that is a spelling
rather than a parity gap** (2026-10-21, the owner's request for the HUD's left
rail). `GET /api/presets` and `GET /api/work` are the same read route, answered
by the same function (`backend/jarvis_presets.py` `install()` / `live_status()`):
the phone reads the canonical `/api/work` (`net/FocusPresets.kt`), and the
desktop HUD reads `/api/presets` through its window's fixed read allowlist
(`hud_proxy.rs` `HUD_GET_PATHS`). The feature itself is in both apps; only one
surface spells the route this way. `tools/check_parity.py` records it as
`deliberate` for that reason.

**`/api/work/choose` is kept and `/api/work/recommend` is being removed, and
the difference is a caller, not a policy** (2026-10-22; coherence audit F11,
Gemini ruling Q9). `POST /api/work/recommend` is dead: neither app calls it -
the phone's only caller, `JarvisRuntime.offerWorkSetup`, is called by no Kotlin
file under `jarvis-client/app/src/main`, so the "Jarvis suggests a setup" panel
`HardwarePlate.kt` can draw is never populated - and the phone-side surface is
being deleted in Session B's coherence slice (`jarvis-client/` belongs to that
session, not this one). `POST /api/work/choose` is kept: it only remembers a
preference and changes no model (`docs/JARVIS-API.md` section 128), and it
belongs to the phone's Work setups section (`HardwarePlate.kt`'s "use" and
"stop" buttons call it). The desktop's carded equivalent is
`POST /api/work/apply` - one `switch_model` card, the one asked action
(JARVIS-API section 145), sent by the bar's, Settings' and the HUD rail's
`apply_focus_preset` - and the two routes are NOT unified: one remembers a
setup, the other asks for a carded model change. `tools/check_parity.py` names
both as `planned` until the phone PR lands (two warnings, exit 0); the
classification change that removes the last warning rides with that phone PR,
because a docs edit cannot reclassify a route. **Honest limit:** this paragraph
records the decision and the dead half; the checker's zero-warning state lands
with the phone files, not here.

**The editable HUD's layout presets are the desktop's, on purpose** (2026-10-21;
H1 of the editable-HUD design, Gemini rulings 23-28; `jarvis-desktop/src/hud-layout.js`,
`contract/hud-presets.json`, `src-tauri/src/hud_layout.rs`). The big HUD
window is a 1280x820 widescreen WebView2 cockpit whose named regions
(`header`, `left_rail`, `stage_top`, `stage_main`, `right_rail`) and card ids
exist only there. The seven built-in layouts - **Cockpit** (the default),
**Studio**, **Ambient**, **Quiet**, **Telemetry & Ops**, **Second Brain &
Planner** and **Minimal** - are therefore desktop-only data, mirrored in
`contract/hud-presets.json` for the desktop's own Rust and tests. **The phone
does not read this file and has no editable-HUD layouts: the Android home-HUD
presets (`A1`-`A4`) are planned and not yet built** (the plan lives in the
editable-HUD design, not in shipped code, and no phone source names this file
or the layout document). `tools/check_parity.py` has nothing to classify: no
backend route and no phone source names it. The choice is saved in the
desktop's appearance-class settings store (the same class as `theme`, no
approval card, no pairing token).

**H2 draws the editor: one reducer, every input (2026-10-22; H2 of the
editable-HUD design, rulings 23-27; `jarvis-desktop/src/hud-edit.js`, the HUD
page, `hud_layout.rs::open_hud_edit`).** The big HUD window's own header now
has **[Edit HUD]**: the panel cards (the six Bento inspector cards, the three
left-rail panels, the approvals queue and the Jarvis-bar button) are wrapped in
card shells and can move between the left rail, the stage top and the right
rail, resize S/M/L/Tall, fold and - except the four protected cards - hide.
**Drag, the card's own buttons, the keyboard and undo all call the SAME pure
`applyAction`**, which runs H1's `normalizeLayout` before anything is rendered
or saved, so protected cards are present and visible and save-then-load cannot
rewrite an edit. That is what makes the WCAG 2.2 SC 2.5.7 claim mechanical:
every drag has a click-only and a keyboard-only twin, and a Playwright gate
asserts the three save payloads are deep-equal. The pointer drag is one
delegated pointer-events handler (inside the ruling's 180-line budget, measured
by a test) and CSS Grid does every reflow - no vendored library, no new
dependency. Autosave is one 400 ms debounced `set_hud_layout` write plus an
immediate flush on `Done`/Escape; undo is session-only (50 actions) and
`Reset to preset` / `Discard changes` are one click each. The approvals card's
transient auto-expand stays DERIVED (`effectiveCollapsed(card, pendingCount)`),
never written. The unsafe-to-hide safety banners from the rulings
(outside-text/rush-latch, stale-link, App lock) are **H4's**, outside the
region grid, and H2 does not touch them.

**One write, owner-approved.** H1 gave the HUD window the layout READ only, for
the bootstrap; H2's in-window editor needs the page to save the layout it just
arranged, so `capabilities/hud.json` gains **exactly one grant,
`hud-layout-write`** (owner-approved 2026-10-21) and **no other write command**
- the existing capability test is flipped to assert precisely that, that the
read grant stays, and that the page still holds no pairing token.
`hud_layout.rs::sanitise` remains the authority for the saved document (the
page-side normalizer is a second line of defence). Settings -> "The big HUD
window" gains the door (`open_hud_edit`: show that window, ask it to edit -
navigation only, no card), and the header button does the same without it.
**Honest limits of H2, said in the PR:** the main stage (conversation, Galaxy,
composer, stage tabs) is fixed - its registry rows round-trip but H2 does not
reparent the live stage; there is no import/export (copy/paste JSON is H3), no
user-preset management (`Duplicate to My Presets` is H3), and touch/pen drag is
NOT-TESTABLE on real hardware here (keyboard/click paths are the guaranteed
alternatives). Desktop-only, like H1: the phone keeps its own home screen and
never reads this.

**H3 renders the preset, and the owner can keep their own (2026-10-22; H3 of
the editable-HUD design, Gemini ruling Q5, Rulings 9/27/28;
`jarvis-desktop/src/hud-layout.js`, `hud-presets.js`,
`src-tauri/src/hud_bootstrap.js`, `contract/hud-presets.json`, the HUD page).**
A preset's own `shell_template` (six shells), `density` (comfortable / compact /
spacious) and `default_stage_tab` are now drawn: the bootstrap puts
`data-hud-shell`/`data-hud-density` on the page and announces `jarvis:hud-shell`,
the page opens the mapped view or inspector tab, and the six shells are CSS
Grid/Flexbox variants with a way back from every rail a shell hides - a
slide-over drawer (Ambient `center-core`, `two-column-right`, `single-stage-bento`)
or the stage tabs (`split-stage`'s right rail, via Telemetry/Memory/Today) - so
no card becomes unreachable. Entering **Edit HUD** auto-reveals every hidden
rail, so the protected controls the HUD draws (`approvals`, the fixed Stop
everything button, the Jarvis-bar button and the mic) stay visible and reachable
while editing, and the layout document keeps all four `PROTECTED_IDS`
(`approvals`, `emergency_stop`, `voice_controls`, `bar_launcher`) forced
visible. **The fixed Stop everything control (owner-approved 2026-10-22):** the
stage bar carries a native `#hud-stop` button outside every card, region and the
layout document, so no preset, imported layout or Edit HUD can hide it. It
calls the same `screen_work::stop_everything` command as the PC hotkey
(`Alt+Shift+X`), the tray and the widget - stops speech and the running turn,
posts `/api/stop_all` with Rust's token, approves nothing, starts nothing, and is
never held on a stale link or App lock - and the HUD gains only the
least-privilege `hud-stop` capability (`allow-stop-everything`). H4 may later
move it into `#hud-safety`; there is exactly one stop control, never a duplicate.
The four-into-three `LOOKS` alias map, the
`data-hud-layout` look attribute and `lookForPreset` are **retired**; the only
survivor of the old road is a `jarvis.hud.preview` localStorage mirror holding
three facts purely so the FIRST frame is not the wrong shell (the store's answer
always wins). The colour `theme` is no longer part of a layout document at all
(Appearance owns colour), and the seven fixed cards carry no inert `col_span`/
`row_span` in the contract (68 dead values removed); a saved document that still
carries `theme` keeps loading with the key dropped, and `LAYOUT_VERSION` stays 1
so no owner layout is discarded. The seven presets are renamed where the
coherence slice renamed them: **Quiet** (silently migrated from the old
"focus"), and the registry label `lanes` is "Focus presets", matching the page.

**"My layouts", one document and one write.** The owner's own saved layouts
travel INSIDE the same layout document (`user_presets`, at most 20, each a
closed-world copy of cards plus its shell/density/tab) and are saved through the
**same existing `set_hud_layout` command** - no new capability, no new command,
no approval card, no backend, no phone. Rust `sanitise` bounds and validates the
library (ids, names, base presets, protected cards forced visible, 64 KB cap),
exactly as it does the active document. The window's header **Layout: <name>**
badge opens the **Layouts** menu: built-in layouts, My layouts, Duplicate to My
layouts (the first edit of a shipped layout becomes the owner's copy - Ruling
27), rename, delete, Reset to the shipped layout, and **Export / Import JSON** as
copy/paste text only (Ruling 9: no file picker, no `blob:`, no Tauri dialog
capability, CSP untouched). Settings lists the same library and adds a one-click
"Reset HUD to Cockpit" row. **Honest limits, in the PR:** the library is
per-computer (export/import is the manual move path; no sync), touch/pen and the
real monitor look are NOT-TESTABLE in CI, and H4's non-hideable safety rail
(outside-text/rush-latch, stale-link/catching-up with Deny kept live, App lock)
is still H4 - H3 does not draw it and makes no new guarantee about it.
Desktop-only, like H1/H2: the phone has its own home screen and no editable-HUD
layouts (A1-A4 planned, not built).

**The HUD Reminders tab is the desktop HUD's, on purpose** (2026-10-21; the
owner's dedicated Reminders menu). The HUD page (`jarvis_hud.html`, vendored
byte-for-byte in three copies: `jarvis-desktop/src/`, `backend/` and
`jarvis-backend/`) is a desktop window; the phone has its own Coming up
screens on the same backend route. Its new `GET /api/schedule` read goes
through `hud_proxy.rs`'s fixed list, and in Rust it gets the SAME word
redaction the Brain window uses (`brain::schedule::redact_list`): while App
lock or "Hide memory lists" is on, the words of reminders, to-do items and
named lists are blanked while kinds, times and counts stay, so a page script
cannot read round it. Its writes are two HUD-scoped commands,
`hud_schedule_add` and `hud_schedule_act` (`hud-schedule` in
`capabilities/hud.json`), held on a stale link like the Brain's, with no
approval card because they only add or quieten, and with **no list form and no
delete-all** (Ruling 15 keeps "clear named list" in the Brain window). Phase 1
is view, add, and the EXISTING one-job actions - snooze, add time, pause,
resume, done, delete. Editing an item's words/time/repeat, moving it between
lists and reordering are Phase 2: they need backend actions and a rank column,
so they need a later deploy, and they are not faked in the page. The phone is
not missing a control: its own app already reads and acts on the same
schedule. `tools/check_parity.py` has nothing new to classify, because no
backend route is added and the phone's read of `/api/schedule` is unchanged.

**Wave D-1's proactive surfaces are desktop-first in one place, and that is
written down rather than implied** (2026-10-22; PR #722; JARVIS-API sections 22
and 82). The briefing's new sections - Travel and next steps, 2-minute prep and
Quiet threads - travel on the existing briefing answer, which both apps already
show, and no backend route was added. Since B5-c (2026-10-23) the Pulse's
money / study / PC-health halves are read on this PC by
`jarvis_pulse_sources.pulse_sources()` (read-only, bounded, counts and titles
only, withheld under App lock / hidden memory lists) instead of waiting for a
caller; the quiet-thread list and the prep people/notes are still
caller-supplied. The Daily Pulse's `where_to_look` strip
reaches the desktop's Today board (`jarvis_today` carries `pulse`); the phone's
Today board does not exist yet - the phone's Today is unchanged in this slice,
and a phone Today board is the named follow-up in JARVIS-API section 82 - so
this is a recorded scope gap, not a parity pass. `tools/check_parity.py` has
nothing new to classify: no route, and the phone's existing reads are
unchanged. The Rule-1/Rule-4 position for the proactive reads and for the
ready-for-review marker (`suggest_done` in the ruling; `propose_ready` in the
code) is recorded in section 3's "Cardless by
design, and why" subsection before this wave merges; the short version is that
the reads are read-only, local-only and built from reads the briefing already
makes, and the marker never completes a task - only the owner's explicit
`act("done")` does.

**Not on the phone yet, and that is the scope of this slice rather than a
one-sided decision** (2026-10-19; extended by S3, 2026-10-20): **searchable
recordings and videos** (`backend/jarvis_media_index.py`,
`plugins/ready/media-index/`, JARVIS-API §149, F5 S2+S3). The owner's decision
keeps readable transcript text in a PC-side index, ON by default, with one
Delete; since S3 the same index also keeps a video's readable **on-screen
text**, read by the PC's own text reader from a capped number of frames (8 per
video, spread across the file; 2,000 characters per video; the per-run file cap
is unchanged, so one search OCRs at most 16 frames). The on-screen rows live in
the same table and the same file as the transcript, so the same disclosure,
backup exclusion and Delete cover both, and a search line says whether it was
said (`source: "speech"`) or shown (`source: "screen"`). The desktop has its
Settings card (disclosure, switch, counts, Delete) through the route; the
desktop card's status line counts recordings, and the route additionally
reports how many stored lines came from on-screen text. The phone's chat path
works - `my_files`'s `search_media` action (whose result says `on_screen`) and
the spoken switch ("turn off searchable recordings") are backend, so both
apps' chats can use it - but the phone has **no Settings card yet** for the
disclosure, counts, switch and Delete. That is the honest gap: the disclosure
is a promise the feature makes, and it must be on the phone too before this can
be called parity. S3 deliberately does not close it by adding a fake control:
the phone's own menu row for it (`settings.media-index`) is **desktop-only**,
and asking to open it already answers with the existing PC-only sentence
(`jarvis-client`'s `OpenPlace.PC_ONLY` lists `media-index`). **One thing is
PC-only rather than pending (2026-10-20 audit, Gemini Area 1A):**
`POST /api/media-index` (ON/OFF/Delete of the stored words) is refused `403`
from another device with the project's own `from_this_pc` rule, so a phone can
read the switch but never change or delete the index; the route is PC_ONLY and
a phone Settings card would only ever be able to READ it. When the card is
built it goes on the same route and the same card as the desktop, with the same
words; nothing about the permission model changes. `tools/check_parity.py`
cannot see it (the route is a drop-in folder, and no app source names it),
which is said plainly here rather than read as a clean pass it did not earn.
**Real OCR is not tested by the S3 suite** - it drives the read seams, so the
real frame decoder and text reader on the owner's PC remain NOT-TESTABLE until
field-tested; that is not a pass.

**The setup questionnaire is shared, and its APPLY step is the desktop's alone,
one-sided on purpose** (2026-10-20; JARVIS-API §147; `backend/jarvis_setup.py`,
`setup.patch`). Both apps read the same fourteen questions (`GET /api/setup`)
and both may ask the read-only plan (`POST /api/setup/plan`, which writes
nothing and raises no card): the desktop draws it in Settings → First-time
setup (`setup-questionnaire.js`, `setup-bridge.js`, `setup-settings.js`,
`src-tauri/src/setup_questionnaire.rs`) and the phone reads the same questions
on its own Settings card (`net/SetupQuestionnaire.kt`,
`ui/screens/SetupQuestionnairePlate.kt`), with the same prefill, the same
effects (instant / asks you on a card / blocked) and the same "would not
change" reasons. **Applying (`POST /api/setup/apply`) is the PC's alone**: it
calls the EXISTING setters in a fixed safest-first order, ONE at a time, and
every loosening change raises its OWN existing approval card and waits for it,
so one apply can take minutes and needs a person at the PC; several of those
changes are PC-only by rules that already exist (`jarvis_asks_first` refuses a
loosening request from any device but the PC, and fails closed when it cannot
tell). A phone button would either fail halfway or sit behind cards it cannot
answer, so the phone has no apply path at all and says the changes are made on
the PC. That is not a missing screen - the read-only half is built and tested,
the write is deliberately not. `tools/check_parity.py` classifies
`/api/setup/apply` `deliberate`, and nothing here invents a gate action, a tier
or a latch: every option maps to a setter the matching Settings control already
calls, and the preset answer is a recommendation that changes no model.

(`backend/jarvis_receipts.py`, `plugins/ready/receipts/`, JARVIS-API §132).
The store and its two routes are built: `GET /api/receipts` (the recent list)
and `POST /api/receipts/<receipt_id>/undo`, which raises ONE `undo_action`
card - the shipped `jarvis-framework.toml` gives that action "ask" of its own
(2026-10-16; before the line existed it took `unknown_action_tier`, which is
also "ask", so the card is the same one) - and the reversal runs only on
the gate's own answer. What neither app has yet is a screen - no receipts list
and no Undo button on the desktop's Jarvis bar or Brain, none on the phone.
That is one decision, not two: this slice is the backend half, and the change
the owner can already see is a tick on a goal's plan, which both apps' Goal
screens show. **When the screen is built it goes on BOTH apps, on the same
store and the same card**, and nothing about either app's permission model
changes - so nothing here is kept off one app on purpose. It is written in
this section because `CLAUDE.md` asks where a feature that is in no app is
recorded, and "not built yet" is not the same sentence as "kept off the
phone". `tools/check_parity.py` cannot see it at all - it scans the two apps'
own source, so a backend route no app calls is outside what it decides -,
which is said plainly here rather than read as a clean pass it did not earn.

**Cost advice is built, and it is in no app yet - and this one is a decision
about the permission model rather than a screen somebody forgot**
(2026-10-14): **the complexity/latency auto-router**
(`backend/jarvis_auto_router.py`, `plugins/ready/auto-router/`).
`evaluate_route()` estimates what a turn will cost on this PC - the measured
token rate `jarvis_speed.py` keeps, the size of the conversation, and the kind
of work `jarvis_work.match()` reads - and advises when a cloud lane would be
quicker. **It decides nothing.** `jarvis_router.choose()`
(`backend/rebuilt/jarvis_router.py:590`) stays the one authority on which lane
answers a turn; this module asks it directly and can only ever advise a lane
`choose()` would also permit, so it is strictly weaker than that authority and
cannot open a gate the authority keeps shut. Its own four gates are inputs to
the ADVICE, never a second permission: the mode switch (off by default in
general chat), the one taint latch this project has
(`jarvis_gate.taint_active()`) together with a project whose `shareable` flag
is not on, the on-disk cloud budget plus
`jarvis_chatbot_api.money_check()` (an exhausted OR unconfigured monthly cap is
a no), and `jarvis_scrub.scrub_text()`, whose absence is itself a refusal.
`plugins/ready/auto-router/plugin.json` sets `install: "none"`, so the folder
imports the module and prints one banner line and **adds no route at all**:
nothing new is reachable, and no app is handed an endpoint to call. That is
what keeps a second entry point into "should this go to the cloud?" from
becoming a second source of truth for a privacy decision - the failure
`jarvis_router.py:632-648` describes. `tools/check_parity.py` cannot see it -
it scans the two apps' own source, so a backend module with no route is
outside what it decides - which is said here rather than read as a clean pass
it did not earn. **When a caller is added it goes into BOTH apps on the same
advisory function**, and a cloud turn is still reached only when the owner says
yes for that one question.

**Not on either app yet, for the same reason and by the same decision**
(2026-10-14): **the blind credential vault** (`backend/jarvis_vault.py`,
`plugins/ready/vault/`, JARVIS-API §134). Its two routes are built -
`GET /api/vault/handles` (every name, the handle, the host it is bound to, when
it was last used and whether a value is really there - never a value, never a
masked prefix of one, never a length) and `POST /api/vault/put` (ONE secret,
after ONE card at tier `ask`) - and neither app calls either of them yet, and
neither holds a vault screen. That is one decision, not two: a value is typed on
the PC and the real key reaches its one service from the PC, so there is nothing
for a phone to carry. **When a screen is built it goes on BOTH apps**, and
`GET /api/vault/handles` is the route an app may read because it carries no
value; the value is never sent to an app at all. Nothing here is kept off one app
on purpose, and `tools/check_parity.py` cannot see either route - it scans the
two apps' own source, so a backend route no app calls is outside what it decides
-, which is said plainly here rather than read as a clean pass it did not earn.

**Not on either app yet either, and again that is the scope of the slice**
(2026-10-15): **"Write Like Me"** - Jarvis drafting in the owner's own voice
(`backend/jarvis_voiceprint.py`, `plugins/ready/voiceprint/`, JARVIS-API §133).
The store and its four routes are built: `GET /api/voiceprint` (the learned
samples, the voiceprint numbers and what the engine is doing),
`POST /api/voiceprint/sample`, `POST /api/voiceprint/learn_edit` (his final
version of a draft, as a gold sample) and `POST /api/voiceprint/forget`, which
refuses unless the body carries `"confirm": true`. Neither app has a screen
yet: no list and no Forget on the desktop or the phone. This is the same
decision as the receipts slice above and is recorded here for the same reason -
"not built yet" is not "kept off the phone". **When the screens are built they
go on BOTH apps, on the same store and the same confirm**, and
`tools/check_parity.py` cannot see any of it for the same structural reason: it
scans the two apps' own source, and a backend route no app calls is outside
what it decides. Said plainly rather than read as a clean pass it did not earn.

**The engine is `jarvis_voiceprint.py`, and `jarvis_style.py` is left exactly
as it is.** There was already an earlier version of this idea in
`jarvis-backend/jarvis_style.py` (`strip_entities`, `exemplars`,
`prompt_block`), and the owner's decision of 2026-10-15 was to build the engine
in a new module rather than in that file, because **that file is delivered to
nobody**: measured, the repository holds exactly one copy
(`jarvis-backend/jarvis_style.py`; there is no `backend/jarvis_style.py` and no
`backend/rebuilt/jarvis_style.py`), no patch the installer applies writes it,
and `$SHIPPED` does not carry it -
`python -B tools/check_unmanaged_files.py` classifies it **NEITHER**. An edit
there reaches no PC. Promoting it into `$SHIPPED` instead would make
`apply-patches.ps1` start **overwriting a file it has never managed**, on every
run, with no way to know whether the owner had edited it - so it was refused as
a change of behaviour that is his to approve, not a formality. Two consequences
are deliberate and recorded rather than left to be discovered:

  - the new module is **self-contained and never imports `jarvis_style`**. That
    is a rule, not tidiness: `jarvis_style.py` IS present on the owner's PC, so
    a `try: import jarvis_style` fallback would silently run the OLD code on
    the one machine that matters. `backend/test_voiceprint.py` asserts the
    module does not name it. The old file keeps its callsite-less career:
    `rebuilt/jarvis_events.py` reports it as the `persona` capability and
    `selftest.py` lists it, so an existing install still shows it. The new
    engine is reported separately as `voiceprint` (`jarvis_events.py`, beside
    `persona`), so the two can be told apart.
  - the earlier engine's stripping had real leaks - a slash-date left its day
    behind (`_PATH` ran before `_DATE`), a UK area code survived (`_PHONE`
    needed a 3-4 digit group first), and bare numbers, decimals, postcodes and
    times passed through untouched. The owner asked for all of them closed, and
    they are: `jarvis_voiceprint.strip_entities` ends with a pass that replaces
    any remaining run of digits, so **no digit survives** - asserted for every
    row of that module's own docstring table by its suite.
  - **One limitation, named:** the proper-noun walk keeps its inherited rule
    and does not replace a capitalised word that OPENS a sentence, because the
    first word is capitalised whether or not it is a name. So "Priya's number
    is ..." keeps the name. Numbers are unaffected. Changing it would delete
    the first word of every sentence from every exemplar, which is the shape of
    the writing the feature exists to preserve.

**On the desktop, kept off the phone:**

| what | why |
|---|---|
| Live voice-to-setting adjustment proof (2026-10-23) | **NOT-TESTABLE in this repository, one-sided by ownership:** the Live clip/answer path lives in the owner's HUD file, outside this repo. The repository proves the typed adjustment path and a hermetic rule that a card raised during Live pauses the Live engine before a transcript is answered; it cannot prove a Live voice sentence reaches a setting. Cards are tap-only by design. |
| The memory graph (`/api/graph`) | Out of scope on the phone (`CLAUDE.md`). Since 2026-09-28 only the desktop's HUD window reads it (the Brain's Galaxy is drawn from people and things instead, privacy finding B1, docs/JARVIS-API.md §71.3), and the HUD's copy loses its fact and person dots while the memory lists are hidden. |
| Galaxy, made of people and things (Brain -> Advanced, 2026-09-28) | The memory graph, which stays off the phone (`CLAUDE.md`). It reads `/api/memory/entities` (the row below), so no route of its own. |
| "History of this fact" (`/api/memory/fact-history`, 2026-09-28, docs/JARVIS-API.md §71.2) | The phone lists only facts saved automatically that are still in use ("Saved automatically"). Those are never corrections, so they almost never have an earlier wording, and a view that brings back the retired wordings of any fact is the deep memory editing that stays on the desktop (the rows below about Forget and Erase draw the same line). The phone's "What did I believe on this date?" still shows retired facts as they were on a date. |
| People and things (`/api/memory/entities`): the names under each fact, "About <name>", and the "are these the same?" card (memory wave 3, 2026-09-25) | The same rule: linking facts to the people and things they name, and joining two entries, is the memory graph, which stays off the phone (`CLAUDE.md`). The phone shows no names and never asks for the merge card (its pending list leaves out `?merge_cards=1`, so the card waits for the desktop). What the layer is for reaches the phone anyway: chat recall runs on the PC, so "where is my sister getting married?" finds Priya's wedding from either app. **Changed 2026-09-30 (owner, GALAXY-PANEL-DESIGN option B): the phone gets a list, not a map** - Brain -> "People and things", names grouped by kind with a fact count, tap one for the facts behind it (newest first, 20 at a time, read by id from `/api/memory/used`); no picture, no links, no merge card, read-only, hidden under "Hide memory lists and chat history", and it leaves out Off-topic facts. **Widened 2026-10-11 (owner): the phone shows the Galaxy's connections, still without the map.** The owner asked to see the Galaxy on his phone and chose a light, read-only version, so the same list now also says which other names appear in the same saved facts ("Shares facts with", `Entities.connections`) - the desktop's dot-to-dot edge, in words, worked out from the `/api/memory/entities` read already in hand by intersecting `fact_ids`. This is the standing rule narrowed for one screen and no further: the phone still has no canvas, no force layout, no dragging and **no write** - no Forget, Erase, Pin, merge or rename from this screen, where this app offers Forget a few plates away. **A1 (2026-10-21, owner + Gemini approved): the phone's list gains kind filter chips, a search over names, the shared-facts count on each row, and read-only as-of chips (Now / 7d / 30d / a picked date) that narrow each name to the facts active then through the existing `?known_at=` read, the retired ones shown muted - still no new route, no write, no card, no canvas, and still hidden under "Hide memory lists and chat history". The read-only Capabilities/Neural list mode was deferred because no `/api/galaxy/capabilities` route exists on the PC yet; the phone did not invent one. The map's own floating search box, hover and drag stay the desktop's. It reads no new route; `/api/graph` stays off the phone "by rule" (JARVIS-API section 6). The names under each fact, "About <name>" and the Galaxy's own picture stay the desktop's. |
| Rewording a stored fact (`/api/memory/edit`), and forgetting one from a list of every fact | Deep memory editing. It stays on the desktop's Brain → Memory tab. Forget (`/api/memory/forget`) itself is no longer desktop-only: since 2026-09-24 the phone calls it for facts in the "Saved automatically" list (JARVIS-API §19), and since 2026-09-25 for a fact shown under "Used in this answer" or "Jarvis remembered N things" - one the owner just saw Jarvis use or save, not a browse of the whole store. |
| "Erase the words" beside Forget under "Used in this answer" and "Jarvis remembered N things" | The phone offers Erase in one place only, Brain → Saved automatically, for facts saved automatically that are still in use (the row below). A fact an answer used may be any fact, history included (a question about the past recalls facts that were corrected or have ended - never forgotten ones, since the memory review of 2026-09-27, B15), and erasing any fact at all is deep memory editing. On the phone those two lists offer Forget; the desktop offers both, as it does on every fact. |
| "Erase the words" (`/api/memory/erase`) on a fact that was already forgotten, or was never saved automatically | The same line as Forget, above: the phone lists only facts saved automatically that are still in use, and a list of every fact, forgotten ones included, is deep memory editing. The phone offers Erase wherever it offers Forget (Brain → Saved automatically), so the route itself is on both apps. |
| Pinning a fact on "Always keep in mind" (`/api/memory/profile`) that was not saved automatically | The same line as Forget, above (2026-09-24): the phone's only list of current facts is "Saved automatically", so it pins from there, and a list of every fact is deep memory editing. The route and the "Always keep in mind" section - the pinned facts, "N of 1,200 characters used", Unpin on each - are on both apps, so a fact pinned on the desktop can be unpinned from the phone. |
| Exporting all memory (`/api/memory/export`) | A copy of everything Jarvis knows does not belong on a phone that can be lost. |
| The memory store's file path ("Store", `db` in `/api/memory/status`) on the memory counts | Written 2026-09-27, when the memory review put both apps' counts on one shared fixture (`contract/memory-words-cases.json`). It is a folder on the PC: nothing the owner can use on a phone. Every other row - including the re-ranker's state and "Said again" - is the same in both apps, word for word. |
| Shutting the backend down (`/api/shutdown`) | The phone would then have nothing to reach and no way to undo it. |
| Deep config editing (`/api/config`) | Out of scope on the phone (`CLAUDE.md`). The desktop does not use it either today: it is only in the Brain window's read allow-list, and no window asks for it. |
| Fetching the look spec (`/api/visual-spec`) | The phone ships its own copy and checks it in a unit test (`SpecDriftTest`); `JARVIS-API.md` says the phone never fetches it. |
| "Finished, or only paused?" (`/api/voice/turn`) | The phone runs the same Smart Turn model itself (`voice/SmartTurn.kt`), so its audio never leaves it just to ask. The desktop asks its own PC over loopback. **Fast path (2026-10-21):** the route also takes raw 16 kHz mono int16 PCM (sniffed; old WAV clients unchanged), and `jarvis_turn.predict_pcm()`/`TurnStream` answer in process with no WAV/base64/HTTP, building the log-mel picture incrementally (`MelStream`) over the 32 ms chunks against the unchanged `features()` reference (tested within a stated tolerance); the session was already cached, CPU only, no new dependencies. **The owner check's first window (same day, V1-Path A):** `hear()` asks the same `jarvis_voice.verify` on the clip's first ~1.2 s of voice (`_decide_owner`), decides only outside `[voice] early_verify_margin` (0.06) and re-checks the FULL clip inside the band; the verify-first privacy rule and the stated costs are unchanged (words made beside the check are discarded when it says no, and a refusal still waits for that worker, so timing does not reveal the distinction). `[voice] early_verify_window = 0` restores the old single full-clip call. Hardware latency is NOT-MEASURED. |
| Looking at the screen: the Alt+Shift+S "Look at this" key, the optional Alt+Shift+V "Watch with me" key, and the always-on-top "Jarvis is watching" badge (**rewritten 2026-09-28**) | **The old row is replaced.** It said (2026-09-24) that the phone should not capture the screen live, because Android's photo picker already offered its screenshots. The owner's decision of 2026-09-28 (`CLAUDE.md`, "Jarvis may look at the owner's screen, on the PC and the phone") replaces that: **both apps get both halves** (`docs/SCREEN-DESIGN.md` §6) - on the phone, "Look at this" through the assistant gesture and "Watch with me" through Android's own screen sharing, with Android's consent dialog every session, the phone's own "Never look at" list of apps, and the pictures sent only to the PC over Tailscale/Meshnet, never streamed. What stays on the desktop alone is the **keys and the badge**: keyboard shortcuts are PC things (like the hotkeys below), and the phone's sign is its persistent "Jarvis is watching · Stop" notification and Android's own status-bar icon instead of a floating window. Built 2026-09-29 (JARVIS-API §62, §96): the backend, the desktop and the phone. **One-sided on purpose, and why:** (a) **the Never look at list is per device**: the PC's holds programs and websites and is refused from any other device (`/api/screen/never-look`, `deliberate` in `tools/check_parity.py`); the phone's holds Android apps, on the phone (`data/ScreenNever.kt`), because neither side can see the other's programs; (b) **the keys, the badge and the tray row are the PC's**, like the other hotkeys; the phone's signs are a Home plate (for the PC's watching, with Stop) and its own ongoing notification (for its own Watch); the PC's watching has no phone notification yet; (c) **starting, asking and extending a PC watch is the PC's alone** - the PC refuses those from any other device, and the phone only reads the sign and can Stop it (stopping only makes Jarvis look less); (d) **the phone's own screen is looked at only on the phone**: the assistant gesture (Look at this) and Android's screen sharing (Watch this phone with me) have no PC equivalent, and their words or one picture travel only inside a chat question to the PC, over Tailscale or Meshnet; (e) **the phone's Watch needs Android's Usage access and its own consent dialog every time**, which the PC has no version of. **Screen safety (2026-09-29, API §62.13):** hiding anything that looks like a key, password or card number covers BOTH apps (the phone's screen text and screen picture are cleaned on the PC before anything uses them); **one-sided on purpose:** (f) **painting other windows black, the private-window pause and the streaming sites on the Never look at list are the PC's** - the phone has no windows behind the one in front to paint, Chrome's Incognito windows block screenshots by default and streaming apps use copy protection, so the assist gesture gets no text or picture from them (not tried on a real phone), and its own list already covers password managers and bank apps. (g) **the phone's Watch cannot pause on password boxes** (audit, 2026-09-29; the owner chose to write it down and keep Watch as it is): Android does not reliably say when a password box is in front, so the phone pauses only for apps on its Never look at list, bank and password-manager apps, a switched-off screen and a near-black picture. The PC still blacks out anything shaped like a key, password or card number, but a password shown with a "show" eye is not caught. Not tried on a real phone. **Picture mode (2026-09-29, API §96.1):** (2026-09-30: with the second/third card's "Pictures" lane running, a look uses that lane's picture model first and the processor reader is the fallback - the same cleaned picture, no new switch, this PC only) its model runs on the PC only - both apps show and set its switch (`/api/screen/picture`, `ported`), but neither reads a picture for it: the phone's screenshot goes to the PC as before and the PC's picture reader looks at it, after secrets are blacked out. |
| Starting a pairing, the QR code and the typed code, and watching or cancelling it (`/api/pair/start`, `/session`, `/cancel`; QR-code pairing, 2026-09-28, `docs/PAIRING-DESIGN.md` section 12) | The code is shown on the PC and the `pair_device` card is approved there with Windows Hello; the backend refuses these routes from any other device (403 `pc_only`). The phone is the device being paired, so it scans or types the code instead (the phone table below). |
| Turning on signed approvals and the signing challenge (`/api/devices/approval-key`, `/api/approve/challenge`; pairing phase 2, 2026-09-29, `docs/PAIRING-DESIGN.md` section 11) | The signing key lives in a phone's Keystore and the fingerprint or PIN is asked on the phone; the desktop IS the PC and its risky approvals are checked by Windows Hello on the PC itself, so it has no key to register and never signs. It only reads the result: the device list's `approval_key` (`false`, `"waiting"` or `true`) beside each phone. `tools/check_parity.py` lists both routes as phone-only. |
| "Bring it back" for the old shared key (`/api/devices/shared` with `{"retired": false}`) | A loosening: PC only, one `unretire_shared_key` card with Windows Hello, refused under Lockdown - the same rule as loosening "What asks first". The phone offers Retire (stricter, immediate), never Bring back; the backend refuses Bring back from any other device. |
| Making an app project, adding an app folder that has no project, and starting a task from the phone (`POST /api/projects` with an `app`, `POST /api/projects/{id}/app/tasks`; apps in Projects, 2026-09-29, `docs/APPS-IN-PROJECTS-DESIGN.md`, JARVIS-API §92) | Nothing on the phone can fill a task: pasting code is deep editing, which stays off the phone (next row), so an empty task there has nothing to offer. The backend would take both from either app (no card: an empty folder in Jarvis's own folder, nothing runs); the screens offer them on the desktop only, and the phone says "Set on your PC". The phone READS an app's versions and open tasks (they ride on the project itself), reads a task's whole change, and merges or discards it. Jarvis writing an app's files from chat is a later slice and will work from either app. |
| Pasting a change into a task (`POST /api/projects/{id}/app/tasks/{task}/files`, `<<<FILE>>>` blocks; 2026-09-29, JARVIS-API §92) | PC only - `403`, `"pc_only": true` from anywhere else: a paste of code is the owner's editing, not a setting, and the phone has no place to write it (`CLAUDE.md`, no deep config editing on the phone). It lands only in the task's own copy, inside Jarvis's apps folder, and nothing runs it; the merge card decides. |
| Approving the merge card (`app_merge_change`) is **on both apps** - written here so it is not read as PC only like `pair_device` (2026-09-29, the owner's answer: after the whole change has been shown) | Not one-sided. The card is risky (the gate's risk table says it cannot be undone yet), so the PC asks Windows Hello and the phone the screen lock or a signed approval; it is not in `PC_ONLY_ACTIONS` because a merge only writes text files into Jarvis's own folder and the owner reads every line first (the phone pages the whole change and opens Merge on the last page). **Never from the approval widget or a notification**: the card is "heavy", so a widget's Approve opens the full card instead of approving. |
| Global hotkeys (`hotkeys.rs`) | Keyboard shortcuts for a PC. A phone has no equivalent. |
| The big coding model's switch (`big_coder.rs`; Settings -> Big model -> "The big coding model (30B coder)") | **PC-only, and one-sided on purpose.** The 30B coder is sized for this PC's pair of graphics cards and pauses Jarvis's own model lanes while it works, so the switch lives where the hardware is (one `change_own_config` card on ON; OFF at once). The phone has no control for it in this slice, but can ask Jarvis to turn it on or off by typing or speaking it once the backend registry path exists; a phone Settings control is a named follow-up. The card itself is the ordinary queue card and can be decided on either device. `tools/check_parity.py` classifies `/api/big-coder` `deliberate` for this reason. |
| The "Stop everything" hotkey (Alt+Shift+X, `hotkeys.rs`) | Written with the feature, 2026-09-25. A key on a PC's keyboard; a phone has no global keys. The phone has the same control as a button - Home's "Stop everything", shown whenever Jarvis is busy - calling the same route (`/api/stop_all`, `ported` in `tools/check_parity.py`) with the same words. Each app stops only its OWN speech: pressing it on the phone does not silence the PC, or the other way round (JARVIS-API §28). |
| Talk-to-type (Settings, Voice, "Talk-to-type (this PC only)"; the Alt+Shift+T hotkey, `talk_type.rs`; `mode: talk_to_type` on `/api/voice/enroll` and `source=talk_to_type` on `/api/voice/utterance`, JARVIS-API §72; the owner's decision, 2026-09-27) | Written with the feature, 2026-09-28. It types into programs on the PC, pressing Ctrl+V there - a phone has no PC program in front to type into, and "a client must not do speech-to-text" rules out a phone version of its own (`CLAUDE.md`, and the owner's decision says "Not on the phone"). The switch lives on the PC with the other voice settings, and the phone does not show it: the phone's voice screen reads only the settings it offers (`VoiceStrict.kt`), so the new `talk_to_type` key in `/api/voice/status` is ignored there. No new route, so `tools/check_parity.py` has nothing new to classify. |
| "Better voice" (2026-09-28, JARVIS-API §80): the second "hey Jarvis" detector (microWakeWord) runs on the PC only; the phone's own listener stays openWakeWord alone | Written with the feature. The phone does run its own detector (`voice/WakeSpotter.kt`, in `WakeWordService`), but it only decides when to send a sentence to the PC; the PC then checks the phrase again (`jarvis_speech.hear()` step 3) - and, with "Two detectors must agree", runs the second detector too (step 3a) - before the voice check and before any word exists. So the setting covers the phone's "hey Jarvis" without a phone change. Running microWakeWord ON the phone would need TensorFlow Lite in the app beside ONNX Runtime: a second model runtime, its own licence and size, and a separate decision. The SETTING itself is on both apps (Settings -> Voice; the phone's Voice check screen), like the other voice settings. |
| Which speech detector (Silero VAD v4 or v6) the PC uses: a status line in Settings -> Voice, and the `vad_version` line under `[voice]` that chooses it (backend/README.md, "Better voice", step 8) | Written with the feature. It is a file on the PC chosen by a line in the PC's settings file after the PC's own bake-off, not an app switch - nobody can judge a speech detector by looking at it (the feasibility audit's "invisible upgrades get no switch"). The desktop shows which file is in use because that is where the owner runs the bake-off and the PowerShell line; the phone's clips go through the same PC detector, and its Voice check screen shows the voice settings only. |
| The tray icon (`tray.rs`) | Part of Windows' taskbar. |
| Windows remember their size and place (Brain, Settings, Faces and the HUD; `window_memory.rs`, tauri-plugin-window-state 2.5.0; the owner's choice of 2026-09-28, the research audit's idea 16) | Written with the feature. A phone app is always full-screen: there is no size or place to remember. Only size, place and maximised are kept - never whether a window was open, which would put the HUD on screen before Windows Hello with App lock on. The widget, the floating face and the Jarvis bar place themselves, as before. |
| "Jarvis is working on your screen, 0:42 - Stop" on the widget (`screen_work.rs`, `screen-work.js`, `GET /api/task`; the owner's choice of 2026-09-28, the research audit's idea 17) | Written with the feature. It is about the PC's own screen, seen by whoever sits at the PC while Jarvis moves its mouse and types there. Its Stop is the "Stop everything" key; the phone already has the same stop as Home's "Stop everything" button, and the task Pause/Stop, shown whenever Jarvis is busy. |
| Signing in to a chatbot's account for "Talk to a chatbot for me" (the spare Google account Jarvis uses for Gemini; `docs/CHATBOT-DRIVER-DESIGN.md`, JARVIS-API §87) | Written with the feature's screens, 2026-09-28. The chatbot is driven in a visible browser window ON THE PC, in a browser profile used only for this, so the sign-in happens there, by the owner's own hands - and when Gemini asks to sign in again mid-conversation, the conversation pauses and asks the owner to do it in that window, then press Resume. Neither app ever carries the account's password; there is no route for one. Everything else about a conversation - starting one (one approval card), watching it, Pause, Resume, Stop, new limits, the summary - is on both apps (`/api/chatbot/*`, `ported` in `tools/check_parity.py`). The words both apps show come from the PC's `jarvis_chatbot_routes.WORDS`, through one contract file. |
| Starting and stopping the backend (`sidecar.rs`) | The backend runs on the PC, next to the desktop app. The phone cannot run it, and stopping it from the phone is the `/api/shutdown` problem above. |
| On the Hardware screen: the memory bars, the "Details" arithmetic, Copy for the one PowerShell line, and the "exactly what is made" Modelfile (desktop Settings, Hardware and models) | The phone shows the cards (names and memory), what runs now, the three setups in the PC's words, their steps, Measure, and the line itself to read (the phone's Brain, Hardware - the design's section 4.6 asks for that much and no more). The line runs on the PC, so Copy belongs there; the bars and the arithmetic are the design's "Details", which a phone screen does not need to choose a setup. Every route is on both apps (JARVIS-API §20). |
| The Faces window's "Portable output" (`faces.html`) | Code for building a client (the look spec as JSON, Kotlin, TypeScript). It is a developer's tool, and the phone already ships its own copy of the spec. |
| The animal on the floating face: its sleeping Zs, "Keep the animal still", the serious pose (2026-09-28) and the sun, moon and weather behind it (2026-09-28) | Written with the features. The desktop's floating face draws the real animal (`faces.html` in display mode), so it gets all three, like every other desktop face. The phone's "Floating Jarvis" is the app's own icon with a status dot (`AvatarOverlayService.kt`), not the animal - there is no animal there to sleep, keep still or go serious, or to put a sky behind. On the phone the Zs and Still reach every place the animal is drawn (Home and the Appearance preview), and the serious pose reaches Home (the preview shows the state being edited, not what Jarvis is doing). The same holds for the animal behaviour switches of "Animal options" (2026-09-28; shared by both apps, `/api/animal`): they reach wherever each app draws the animal, which on the phone is not "Floating Jarvis". |
| The fade when switching faces to or from Tokamak or Membrane (the face switch's goodbye and hello, 2026-09-28) | Written 2026-09-28, after the animal-behaviours audit. On the desktop every face, the two mesh faces included, is drawn into the one canvas whose opacity carries the fade (`faces.html`, display mode's `switchFace`), so they fade like any face that is not a character. On the phone those two draw on their own GL surface (`GLFaceSurface`), which Compose's layer alpha cannot fade: leaving, a mesh face goes at once instead of sitting still for a second (`FaceView`'s switch skips its goodbye), and arriving it shows at once. Every other face - the animals and the robot included - says goodbye and hello the same way on both apps. |
| Typing the town for "Show the sun and moon behind the face" (`POST /api/sky {"place"}`; the owner's decision of 2026-09-28: "a town the owner types once on the PC (the phone gets it from the PC)") | Written with the feature. The backend refuses a town from any device but this PC (`jarvis_owner_check.from_this_pc`), so a stolen token cannot move where Jarvis thinks the owner lives. Everything else is on both apps, in the PC's words (`/api/sky`, `ported` in `tools/check_parity.py`): the switch, which town is set and today's rise and set times (each app's own maths), "Forget my town" (at once, from either), and the weather source (Open-Meteo's card answered on either). |
| A temporary chat in the HUD window (`jarvis_hud.html`) | The HUD window shows the backend's own page, which sends its own chat requests and has no temporary-chat control. The desktop's temporary chat is in the Jarvis bar, where its chat is. Both apps have the feature (JARVIS-API §4). Since the owner's decision of 2026-10-06 the HUD's own chat box is shown and usable again, and a button beside it still opens the Jarvis bar; the box's turns are their own conversation, filed in History as HUD. |
| The HUD's three layouts - Command Cockpit (default), Studio Split-Workspace, Ambient Voice Core - and the pickers for them (the owner's request of 2026-10-20, "i would also like to choose from 3 different UIs for the jarvis HUD in the settings... looking cutting edge while still being intuitive and effective"; `jarvis-desktop/src/jarvis_hud.html`, `hud-window.js`, `hud-window-settings.js`, the "The big HUD window" card in Settings) | **The desktop's only, because a phone has no HUD window** - the big always-on panel is a PC surface, and the phone's own look is its three themes (`Themes.kt`), shared with the desktop through `theme.css` and unchanged by this. The setting is cosmetic, like the theme: no approval card, no Rust command, no route. It is kept in the HUD origin's `localStorage` under `hud-window.js`'s `HUD_LAYOUT_KEY` (the same place and same road as the "Open the Jarvis bar" button switch above it), so the Settings card and the in-HUD picker write one key, and the open HUD obeys a change at once through the shared `storage` event. All three layouts are the one page switched by `document.body.dataset.hudLayout`; every DOM id stays in the document in every mode. `tools/check_parity.py` has nothing to classify: no route, no phone surface. **Fit (2026-10-21, field fix):** the HUD window's declared minimum is 960x640, and `window_memory.rs` (`MIN_INNER`, `clamp_restored_size`) now clamps a stale saved size back up to it on restore - Windows accepts a programmatic resize below the minimum, so the installed app once came back at 815x691 with its layout picker off-screen. The page itself also wraps its stage header and drops the Cockpit to one column at 720 CSS px, because the app's own Text-size / Ctrl+= zoom shrinks the CSS viewport without changing the window; no control is off-screen at any of those widths, and the right rail is the drawer the base stylesheet already provides below 1080px. |
| The HUD Galaxy's three lenses - Memory, Neural, Unified - and their picker (the owner-approved Galaxy v2 slice G1, 2026-10-21; `jarvis-desktop/src/jarvis_hud.html`, `docs/DECISIONS.md` 2026-10-21) | **The desktop HUD window's alone, because a phone has no HUD window and the memory graph is off the phone** (standing rule; `tools/check_parity.py` has nothing to classify: no route, no phone surface). It is a VIEW over the ONE graph the HUD already reads - `GET /api/graph`, through the shell's fixed allowlist - so it adds no route, no permission and no Rust: `Neural` draws the capability half the PC's own `build_graph()` computed (`collect_models` brains, `collect_tools` ability groups and abilities), `Memory` draws the memory half (facts, documents, knowledge/entities, projects, skills, personas) **exactly as the PC sent it, so it is already redacted by the PC's lock rules when the owner has hidden memory lists**, and `Unified` shows both with a counts line that says which half is which. Every dot is also a real focusable HTML `<button>` with a label - the canvas is the picture, not the only surface - and the counts are computed from the payload, never typed into the page. The honest limits: the Memory lens shows names and counts, not the per-entity facts list (`/api/memory/entities` is deliberately not reachable from this window; Brain keeps that list), and `/api/presets` is not reachable either, so a lens cannot mark an active lane. The chosen lens is a cosmetic preference in the HUD origin's `localStorage` (`jarvis.galaxy.lens`), no approval card, no setting in Settings. Tests: `jarvis-desktop/tests/hud.mjs` (three lenses over a stub graph, computed counts that follow the payload, keyboard focus + Enter opening the inspector in every lens, an empty Memory lens saying so honestly, and the lens surviving a reload). |
| "Chat history…" in the tray, and the Jarvis bar's "Esc: end chat" with "Chat ended. Kept chats are in Brain > History." (the chat audit, 2026-09-28) | A tray menu and an Esc key are the PC's. The phone's way to History is "Earlier chats" on Home (next to Temporary chat), which the bar has too; the phone's chat ends on New conversation, a temporary chat, Live, 30 quiet minutes or the app's process ending - it has no Esc. |
| Who set the power mode, on the tray's Power row ("· set by hand", "· quiet hours", "· idle timer", and since 2026-09-25 "· standby schedule") | Written 2026-09-25, when the standby schedule added a fourth. The phone's Power field has only ever shown the mode itself; the reason is a tray detail. What the standby schedule did is on both apps anyway: its row in Coming up says how its last end went ("Went on standby at 01:00."). |
| Entering an Exa, Tavily, Brave or DeepSeek key for web search (Settings -> Web search, `save_search_key`) | Written 2026-09-25, with the feature; DeepSeek added 2026-10-23. A key is "sent only to the one service it authenticates against" (`CLAUDE.md` rule 3). Typed on the phone, it would have to travel over the link to the PC first - somewhere other than its one service. So the desktop writes it straight into Credential Manager on the PC (never over HTTP), or the owner runs `py -3 jarvis_search.py key exa` (or `key tavily`, `key brave`, `key deepseek`) there; the backend has no route that takes a key. Everything else about web search is on both apps (JARVIS-API §23): choosing the provider, the SearXNG address, "Ask before every web search", Test search - and the phone shows whether a key is saved and where to add one. |
| "Accounts" (Settings -> Accounts, `save_account_secret`/`forget_account_secret`; ease-of-use audit row 15, 2026-09-27, JARVIS-API §44) | Same reasoning as the web search key row above, for the IMAP username and password, the private calendar link, and the Home Assistant token: each is "sent only to the one service it authenticates against" (`CLAUDE.md` rule 3), and CLAUDE.md's standing rule keeps deep config editing off the phone besides. The desktop writes each straight into Credential Manager on the PC - never over HTTP, no backend route takes one. An environment variable the owner already set still wins (`jarvis_token_store.resolve_secret`); this only adds a second place to set one, never a second source that could disagree once one is chosen. |
| The account ADDRESSES (Settings -> Accounts, `get_account_addresses`/`save_account_address`; the owner's decision of 2026-10-06, JARVIS-API section 116) | Written with the feature, and **not** one-sided in the way the row above is: an address is not a secret, so it goes to a backend route that keeps it in `accounts.json` beside `web-search.json` (`jarvis_accounts.py`, `backend/accounts.patch`) and hands it back to the page - the same shape section 23's SearXNG address already uses. **What keeps it on the PC is the standing rule**: deep config editing stays off the phone (`CLAUDE.md`), the phone is never asked for an account secret, and `jarvis-client`'s `OpenPlace.PC_ONLY` answers "only on your PC" for that card. Rule 3 is enforced by the whitelist rather than by convention: the route takes only the eight, refuses a key, a password, a token or the private calendar link with a plain 400, and the desktop's own command refuses a name outside the eight before a request is even built. `deliberate` in `tools/check_parity.py`. |
| The backend's own Windows Hello check before a risky approval (`owner-check.patch`, the approval gap's step 1, 2026-09-25) | Written with the feature. It checks approvals that come FROM the PC, where the desktop is; the phone keeps checking its own fingerprint in the app, as before, and the backend lets a phone approval through without a PC prompt. The phone's half - a key in the phone's Keystore that needs a fresh fingerprint for every risky approval, checked by the backend - is step 2, built with "more devices" (`docs/APPROVAL-GAP-DESIGN.md`). Both apps share the stamp (every approval) and "no lock, no risky approval". |
| Saying a timer aloud when it goes off ("Your timer is done.", while "Hey Jarvis" listening is on in the Jarvis bar; 2026-09-25) | The owner asked for it on the desktop ("say timers aloud on the desktop when voice is on"). The phone's timer notification rings, and its voice is only switched on for a conversation - a phone in a pocket speaking on its own was not asked for. Alarms and urgent "tell me when"s ring until seen on both apps (JARVIS-API §30.5). |
| Focus sessions: watching which app or site is in front, and saying a drift out loud (`GET /api/focus/callout`), and the widget's "Lock on" (the owner's decision of 2026-09-25: "Jarvis watches which app/site is in front ON THE PC ONLY ... Nothing leaves the PC") | Written with the feature. The watching happens in the backend, on the PC, and is about the PC's screen: a phone has nothing to watch, and the spoken line names what was in front, so it stays on the PC - the backend refuses `/api/focus/callout` to any address but loopback, and the desktop's Rust fetches it as sound (JARVIS-API §26). "Lock on" is about the PC's screen too. Everything else is on both apps: starting a session (minutes, "on what"), the countdown, on or off target, the drift count, Pause / Resume, +10 minutes, Stop and the report card (the phone's Brain, Focus session; the desktop's Brain -> Work and the widget), and every voice command ("snooze", "I'm doing research", "lock on this") works when said or typed to Jarvis from either app. |
| The voice upgrades' bake-off (`backend/jarvis_bakeoff.py`, 2026-09-26) | Written with it. It is a program the owner runs on the PC, not an app screen: it measures the PC's own voice engines, the PC's graphics-card memory and the room through the PC's microphone. Its verdict decides a later change that reaches both apps (the phone's wake-word file, the engine name both apps show). |
| Loosening a line on "What asks first" (`POST /api/asks_first/tier` with `"ask": false`; the owner's decision of 2026-09-26: "On the PC only, the owner may also loosen a short safe list - one card plus Windows Hello per change") | Written with the feature. The phone shows the same page in the same words, and its "Ask me first" switches turn ON only (stricter, at once) - once a row asks, the phone's line says to loosen it on the PC. Loosening is one card that must meet Windows Hello, and Windows Hello is the PC's: the backend refuses the request from any device but the PC, and `jarvis_owner_check.PC_ONLY_ACTIONS` refuses the card's approval from any other device too, so a stolen token used from elsewhere cannot loosen anything. The phone shows that card with Deny only ("Approve this one on the PC - it needs Windows Hello there."). "Lights, plugs and fans without a card" is on both apps (ON one card, OFF at once). |
| Offering a reading tool to the AI model at all (`POST /api/asks_first/tools`; the owner's answer of 2026-09-27, ease-of-use audit row 14: "Reading tools ... can be switched on from the PC app, each with a card plus Windows Hello; other tools stay in the settings file") | Written with the feature. Same shape as loosening a tier line, above, and the same reason: `enable_reading_tool` is one card that must meet Windows Hello, and the backend refuses the request, and the card's approval, from any device but the PC (`jarvis_owner_check.PC_ONLY_ACTIONS`). CLAUDE.md's standing rule against deep config editing on the phone also applies on its own: switching what the AI model may even be offered is config, not a card the owner answers about one action. The phone's "What asks first" page is unaffected - it reads the same route, but simply does not show the new "tools" key GET /api/asks_first now carries (`jarvis_reach.py`'s "What Jarvis can reach" already told the owner a tool was "off" for this reason; its wording now also says which four can be switched on, and that every other tool is file-only). `deliberate` in `tools/check_parity.py`. |
| "Show me where" under "Jarvis isn't running on your PC." (ease-of-use audit 2026-09-27, #2) | Written with the change. It opens the desktop's own Settings at "Starting Jarvis for you", with More options open. The phone has no Settings for the PC to open: it shows the same words (the shared plain-errors list), which name that place, and its "Try again". |
| A filter box on "What Jarvis knows about you" (ease-of-use audit #7) | That list - every fact, forgotten ones too - is on the desktop only (the Forget and Erase rows above), so its filter is too. |
| "I lost my phone. What do I do?" in the FAQ (ease-of-use audit #8h) | Everything it says is done on the PC and in Tailscale's or NordVPN's own pages, and the phone it is about is the one that is gone. docs/INSTALL.md, "If you lose your phone", has the steps. "How do I update Jarvis?" is in both FAQs. |
| The five-screen walkthrough (`onboarding.html`; ease-of-use audit #4, "3 examples on walkthrough screen 2") | The desktop has a first-run tour because it is a window that can sit empty with nothing to do until the tray icon, an approval card and memory are explained. The phone's first screen IS the point of contact - pairing - so there is no equivalent empty moment to fill with a tour; its own "What can I say?" line is in the FAQ (`Sayable.HELP_TITLE`/`HELP_BODY`, `FaqScreen.kt`) instead of a screen 2. `Sayable.WALKTHROUGH_EXAMPLES` still exists on the phone, held to the same contract fixture as the desktop's 3 examples, so a phone screen that wants them later does not have to invent its own three. The UI audit (2026-09-26, item 16) set the phone's whole onboarding budget at one picture and one sentence, and the phone has exactly that since the ease-of-use audit (#17, 2026-09-27): above the pairing form, on a genuine first pairing only (`PairingScreen.kt`; a re-pair, `onCancel` set, is a returning owner). The desktop's five screens are the tray icon, approval cards, memory, how to talk to it, and where the settings live. Both of its commands go through the shared invoke budget (`src/invoke-budget.js`), and the last button and Escape share one busy guard so the finish cannot be fired twice. |
| Adding a folder to "Folders Jarvis may look in" (`POST /api/folders/add`) and bringing in a Notion export (`POST /api/folders/import`) (the owner's decisions of 2026-09-26; the feasibility audit's guardrail 1: "one folder list, PC only, empty by default") | Written with the feature. Both are about files on the PC: the desktop opens the Windows folder picker (or the file picker, for the export's `.zip`) in Rust, and only the path the owner chose is sent; adding then raises ONE approval card (`change_own_config`). A phone has no view of the PC's folders to pick from, and a path typed on the phone would be a guess. The backend refuses both routes from any device but the PC (`jarvis_owner_check.from_this_pc`), not only the apps. Everything else is on both apps: the list in the PC's words and Remove on each folder (at once, never held on a stale link - it only lets Jarvis see less; `/api/folders` and `/api/folders/remove`, `ported` in `tools/check_parity.py`), and asking about the files, which is ordinary chat from either app (the `my_files` tool runs on the PC, with the model on the PC). |
| "Bring in chats from ChatGPT, Claude, Gemini or DeepSeek" (Brain -> Memory; `/api/memory/import_chats`, `/start`, `/cancel`; the owner's choice of 2026-09-28, JARVIS-API §85) | Written with the feature. The export is a file on the PC: the desktop opens the Windows file picker in Rust and sends only the path the owner chose, and the backend refuses `/start` from any device but the PC (`jarvis_owner_check.from_this_pc`). A phone has no view of the PC's files, and the file is usually hundreds of megabytes - uploading it from a phone would be a new way for a whole chat history to travel. What the import makes reaches the phone anyway: every possible fact is an ordinary card in the review queue ("Waiting for you"), which the phone shows and decides one at a time, like any other. The phone shows no progress line; the run is started and stopped on the PC. `deliberate` in `tools/check_parity.py`. |
| Backups: choosing the folder, "Back up now", listing, and restoring (`POST /api/backup/folder`, `/api/backup/now`, `GET /api/backup/list`, `POST /api/backup/restore/preview`, `/api/backup/restore`) (the owner's decision of 2026-09-27, CLAUDE.md; `docs/JARVIS-API.md` §45) | Written with the feature. The folder picker is the exact one "Folders Jarvis may look in" uses (Rust's `folders::picker`, reused not copied), so the same reasoning applies: a phone has no view of the PC's folders. Restoring replaces memory, chat history, settings and notes - and, from 2026-10-05, also puts the backup's copy of the backend's own top-level `*.py` files back into the folder `jarvis_backup.py` runs from (the code comes back with the data, section 4's own reasoning), so it is PC-only for the same reason `loosen_what_asks_first` and `enable_reading_tool` are: it always needs Windows Hello, which is the PC's (`jarvis_owner_check.PC_ONLY_ACTIONS`). The backend refuses every one of these five routes from any device but the PC (`jarvis_owner_check.from_this_pc`). **Rewritten 2026-10-13 for the phone's half, below: `GET /api/backup` itself IS on both apps, at two depths - `ported` in `tools/check_parity.py`: the desktop reads the full view (the folder, waiting cards, counts), and the phone reads it only for the one line it has always carried, `last_backup_at` (`net/Backup.kt`, `ui/screens/BackupPlate.kt`). The folder's own state now reaches the phone properly, through `/api/backup/status`.** Since 2026-10-24 the phone's finish tap WRITES the file on the PC (the next row), so the PC's own fallback for a run left waiting is a convenience rather than the only way to finish it. **The finish is BOUND to the phone that started the run or to this PC** (Gemini's Q-A asker guard, 2026-10-24): `prepare` records the asking device's identity - the same `_jarvis_device` identity `jarvis_devices` stamps on every request, never a new header - and `commit` from any OTHER paired device holding the same code is refused 403, writes nothing, and does not spend the run. The next row carries the fallback and its stated limits. |
| **What the phone MAY NOT do about backups: choose the folder, restore, list files, or delete older copies** (`POST /api/backup/folder`, `GET /api/backup/list`, `POST /api/backup/restore/preview`, `/api/backup/restore`, `/api/backup/delete-older`) - **and what it MAY do** (2026-10-13: `GET /api/backup/status` on any paired device; `POST /api/backup/prepare` from the phone; since 2026-10-24 `POST /api/backup/commit` from the phone too, with the run's one-time code) | Written with the phone's half of the feature, and this is the row that says why the line is where it is. What stays the PC's, unchanged in reason: the **folder** (a phone has no view of the PC's folders - the Windows picker is on the PC); the **file list** (`GET /api/backup/list` names files on the PC's disk, which is what row "the memory store's file path" above already keeps off a phone); **restoring** (replaces everything Jarvis knows and always needs Windows Hello, which is the PC's - `jarvis_owner_check.PC_ONLY_ACTIONS`); **deleting older copies** (a real deletion on the PC's disk). What the phone DOES is the state, the ask, and - since 2026-10-24 - the trigger: `/api/backup/status` is a read - the folder's LAST segment, how many are kept, when the last one was, and whether the newest file is complete and well formed - and it carries no recovery code and never a full path (**the whole path names the owner's Windows account, the same reason §8 keeps the memory store's own path off a phone**); `/api/backup/prepare` mints this run's one-time recovery code and **writes nothing at all**. **The one thing on this row that needed a decision rather than an inference:** the code that locks a backup travels to the phone, once, in the reply to `prepare` - because a run made from the phone whose code never reached the owner would not merely add a file nobody can open, it would push an older, still-openable backup out of the five kept. The write is a SECOND call, `/api/backup/commit`: **2026-10-13 said a phone may ask and only the PC may write; the owner relaxed that on 2026-10-24 to ONE TAP FROM THE PHONE** - after the code is shown and the owner ticks that he wrote it down somewhere safe, the phone's finish button may commit, and the one-time code it holds IS the authorisation. The write itself still physically happens on the PC, by the PC's backend, into the folder the owner chose there; only the trigger comes from the phone. The phone's screen will not make the call until that tick, says "Nothing has been written yet" while the run is open, and says "Your PC wrote the backup" only after the answer reports a file. A run that is abandoned writes nothing. **The residual risk, in plain words, accepted by the owner on 2026-10-24:** the tick is a promise by the phone app, not a check by the PC, so a modified or misused paired phone could make the PC write a backup whose recovery code was never kept - that file cannot be opened, and because making a backup deletes the oldest of the five kept, it pushes the oldest one out. The owner accepted that rather than leave a run the phone could never finish. **The finish is BOUND, not just coded (Gemini's Q-A asker guard, same day):** `prepare` records the asking device's identity (the same `_jarvis_device` `jarvis_devices` stamps on every request: "pc", "shared", or a paired device's id), and `commit` is accepted only from that device or from this PC; a different paired device holding the same code is refused 403, writes nothing and does not spend the run (the device is checked before the code, so the route is no code oracle). **Two stated limits, neither hidden:** a run minted with no recorded identity - a backend without `jarvis_devices`, or a direct in-process call - cannot be bound, so possession of the live code still decides there; and the legacy shared key is one identity (`shared`) for every holder until the first device is paired, after which `jarvis_devices` refuses the shared key from another device. The guard does NOT close the token-churn gap: a token holder can `prepare` and then `commit` as the device that minted its own run (`docs/JARVIS-API.md` §45.6). `tools/check_parity.py`: `status`/`prepare` are `phone-only`; `commit` is `ported` (the phone's finish press and the desktop's typed-code fallback both call it, and the backend binds the phone's call to the minting device or to the PC); the desktop does not need `prepare`/`status`, because it IS the PC: it already has the picker and its own one-call "Back up now", which can show the code on the screen that made it. **2026-10-20 (Gemini ruling 8.1, `docs/JARVIS-API.md` §45.4b):** a restore now FAILS CLOSED unless the safety backup is verified on disk first, the last restore's outcome is PERSISTED and readable by BOTH apps (`GET /api/backup`; the phone's copy carries no recovery code and no technical `why`, and reading it consumes nothing - the one-time code rule is unchanged), and the audit/receipt name every restored file. The explicit dismissal is `POST /api/backup/restore/dismiss`: any paired device may ask, BUT a device is refused 409 while this PC has not yet shown the restore's one-time recovery code - the code exists only in the PC's memory, so clearing the notice first would make the safety backup unopenable for ever (2026-10-21 audit, M2; the PC itself may always clear it, and after the PC's first read any device can); **neither app draws that button yet**, so the desktop panel shows the persisted outcome as before and the control is a named follow-up, not a changed rule. The 2026-10-21 audit's other fixes are in §45.4b point 4 of `docs/JARVIS-API.md`: the record file is excluded from backups, a failed record write leaves an honest fallback (never an older restore as current), a partial failure still names the files it had replaced, a verification crash is a clean refusal, and the safety backup is re-checked after the apply. |
| The short tool list (`[tools] short_list`) and the tool and behaviour test (`tools/tool_eval`, 2026-09-26) | Written with the feature. Neither is something an app shows: the short list changes which tool descriptions the PC sends to its own model (both apps' chats get it the same), and the test runs on the PC against the PC's model, with one PowerShell line. Nothing to port. |
| The warm-up with words (`[power] warm_prefix`, `jarvis_agent.warm_prefix`, 2026-09-28) | Written with the change. It is the PC's backend reading Jarvis's rules and tool list into its own model ahead of a question, after waking and after a learning pass; nothing in either app shows it or starts it, and both apps' questions get the same benefit. Switched off only in the PC's settings file, like the short list. Nothing to port. |
| Setting up a plug-in program (MCP): the `[mcp]` lines and `py -3 jarvis_mcp.py inspect` (2026-09-26) | Written with the feature. A plug-in program is a program ON the PC, listed by full path in the PC's settings file - deep config editing, which stays off the phone (`CLAUDE.md`), and the desktop has no screen for it either. Using one is the same from both apps' chats: its start card and every call's card reach both apps like any other card, and both apps show its row on "What Jarvis can reach" and its two rows on "What asks first". **F4 (2026-10-18):** the bridge is taint-safe - full-payload protected-target scanning on arguments AND results, SecAlign marker strip on what comes back, `latch_taint(why="mcp_tool")`, and the top-K tool diet. There is still NO app screen for setting one up: "`[mcp]` lines edited on the PC" is deliberate and one-sided (deep config editing), and neither app adds or removes a server; both only show the cards and the read-only reach rows. |
| "Data health in the preflight" (`GET /api/data-health`; feasibility I97, 2026-09-27) | Written with the feature. It exists for `backend/selftest.py --preflight`'s own PowerShell output, not for a screen in either app - a diagnostic the owner pastes back, the same audience as every other preflight check (JARVIS-API §49). Neither app calls the route today. |
| The restart-with-a-cap watchdog (`sidecar.rs`'s `spawn_watchdog`) and hang/crash notes (`crash_notes.rs`, Settings -> More options -> "Hang and crash notes"; feasibility I98/I99, 2026-09-27) | Both are about a process on the PC: the Rust desktop app supervising the Python backend it started, on this machine. There is nothing on a phone to watch or restart, and a panic in this process is this process's own. The phone has its own separate crash reporting question, not raised by this work. |
| "Private copy" (feasibility I114, 2026-09-27) - keeping a copied answer out of what each platform remembers or syncs on its own | Genuinely different mechanisms, not one file shared two ways: the desktop excludes the clip from Windows Clipboard History and Cloud Clipboard sync (`clipboard_privacy.rs`, two registered clipboard formats set to 0 in the same open/close sequence as the text); the phone marks the clip `ClipDescription.EXTRA_IS_SENSITIVE` so Android's own copy toast shows no preview (`PrivateClipboard.kt`) - Android has no clipboard history or cross-device sync feature to opt out of at all. `docs/JARVIS-API.md` §51 has both. |
| App-icon shortcuts (feasibility I125, `res/xml/shortcuts.xml`, 2026-09-27) | Phone only - a long press of an app's own icon on the home screen or app drawer is an Android launcher convention with no Windows equivalent this app has any reason to add (the desktop already has its own quickbar hotkeys, Settings -> Shortcuts). Talk and Note reuse the widget's own actions; "Brief me" and "What did I miss?" ask their fixed, read-only sentence on Home through the chat box's own send (`AppShortcuts.kt`, changed 2026-09-27) - no new backend route. `docs/JARVIS-API.md` §52. |
| "Check for tool updates" (`GET`/`POST /api/tool_updates`(`/check`); the owner's own request, made directly, 2026-09-27) | Written with the feature. Checking the versions of the Python packages, Rust building blocks and any pinned GitHub tool Jarvis is built from is developer/maintenance tooling, not something the owner does from their phone - the same reasoning that keeps the model catalogue and deep config editing off the phone (`CLAUDE.md`'s standing rule). Report only: it never installs or changes anything, on either app, ever - it only shows the exact command to run, which is itself a PC-side action (`py -3 -m pip install ...`, `cargo update ...`, run from a terminal on the PC, not from a phone). `deliberate` in `tools/check_parity.py`. |
| **Turning Lockdown OFF** (`POST /api/asks_first/tier {"action": "lockdown", "ask": false}`; the owner's choice of 2026-09-28, `docs/JARVIS-API.md` §75) | Written with the feature. Turning it ON is in both apps, at once. Turning it off loosens every way out of the PC at once, so it is the existing PC-only loosening - ONE `loosen_what_asks_first` card that needs Windows Hello, refused from any other device by the backend itself (`jarvis_owner_check.PC_ONLY_ACTIONS`). The phone shows where to do it instead of a button, exactly as for loosening one action. |
| "Open <a settings section>" by voice or chat (§3, `docs/JARVIS-API.md` §58.1) jumping to Hardware and models, the second graphics card, the big model, Updates, "Check for tool updates" or "More options" | No new route (this rides inside `/api/chat`), so nothing for `tools/check_parity.py` to check. Each of these sections is already desktop-only or Rare-and-desktop-only for its own reason, listed elsewhere in this table. Voice, Security, Appearance and Backups ARE reachable on the phone: each is a real `item(key = ...)` row in `SettingsScreen.kt`'s `LazyColumn`, with its own entry in `SETTINGS_ITEM_INDEX`, so "open voice", "open security", "open appearance" and "open backups" from the phone scroll to that row like any other section, the same as on the desktop. |
| "Try the cloud model" (the "yes" button, 2026-09-27; §4 "`offer` in `X-Jarvis-Route`", `docs/JARVIS-API.md` §18.1) - the widget only | No new route (it rides inside `/api/chat`, so nothing for `tools/check_parity.py` to check), and it IS on both real chat surfaces: the desktop's main window (`index.html`/`main.js`) and the phone's Home screen (`HomeScreen.kt`, `net/CloudOffer.kt`). Left off the desktop's own separate `widget.html`/`widget.js`, which never renders an answer's own text or route at all today - it shows only the quickbar's Talk/Note/status controls, nothing an offer could attach to. Nothing here is a decision to keep it off the widget forever; there is simply nothing on that screen yet for it to hang beside. |
| Inbox tidy's Undo strip (2026-09-28, `docs/JARVIS-API.md` §95) - the desktop's Jarvis bar and the phone's Home only | It IS on both real chat surfaces (the bar's strip under the input, `inbox-tidy.js`; Home's `InboxTidyPlate`), and both routes are checked by `tools/check_parity.py` as ported. Left off the desktop's separate `widget.html`/`widget.js` and the HUD window: the widget shows no chat, and the HUD window's own chat box (shown and usable again, 2026-10-06) shows no Undo strip - the widget's Approve for the tidy's own card opens the Jarvis bar, where the strip then is. Undo is held on a stale link in both apps, unlike "Forget a time frame"'s (which is never held, so its ten minutes cannot run out): tidying acts on a mailbox, so rule 4 holds it (a failed Undo can be tried again while its ten minutes last). |
| Projects: choosing a coding project's folder, and writing or changing a coding benchmark's command (`POST /api/projects` and `/api/projects/<id>` with `folder`, `/benchmarks` with `command`; `docs/JARVIS-API.md` §88, the owner's decision of 2026-09-28, `docs/PROJECTS-DESIGN.md` §6) | Written with the backend (build steps 1 and 2) and kept in both apps' screens (step 3, 2026-09-28): the desktop chooses the folder with the Windows folder picker and writes a command in Brain -> Projects; the phone shows both and says "Set on your PC", and creates life projects only. Project folders and benchmark commands are PC-only: folders already are ("Folders Jarvis may look in" is added on the PC alone, and a project's folder must already be on it), and a command's words decide what would run on the PC. The backend refuses both from any device but the PC (`jarvis_owner_check.from_this_pc`, `403` with `"pc_only": true`). Everything else about a project - creating a life project, instructions, notes, the Shareable switch, logging a number - is on both apps; clearing a folder is too, since it only lets Jarvis see less. |
| Setting up Jarvis's Gemini window: signing it in once (`py -3 jarvis_chatbot_gemini.py sign-in`) and the selector self-check (`py -3 jarvis_chatbot_gemini.py check`), 2026-09-28 | PowerShell commands on the PC, not app screens, in neither app: the browser window they open is on the PC, and the owner signs in to the spare Google account there, by hand. Whether it is set up reaches both apps anyway, as the "Chatbot conversations" row of "What Jarvis can reach" ("Not set up", with the line to run). |
| Signing in to the other chatbot websites (ChatGPT, Claude, Copilot, Perplexity, DeepSeek, Grok, Le Chat, Meta AI) and their self-checks: `py -3 jarvis_chatbot_<site>.py sign-in` / `check`, 2026-09-28 | **PC only**, the same reason as Gemini's: each website's window, and its browser profile holding that site's sign-in cookie, are on the PC, and the owner signs in to each spare account there, by hand - a phone cannot sign a PC's browser in, and Jarvis never types or keeps a password. Both apps still see which are set up, through the same "Chatbot conversations" row. |
| Customer-support chats: signing in to the owner's own account in the support window, opening the company's chat on its help page, answering an identity check or "are you a bot?", and the read-only check (`py -3 jarvis_support_widget.py sign-in|check groupon`, `forget-sign-ins`), 2026-09-28 | **PC only**: the support window, its browser profile holding the owner's REAL sign-ins, and the chat itself are on the PC; the owner signs in, opens the chat and answers what Jarvis hands over there, by hand (the owner's decisions: identity checks are "always handed to the owner in the window"). Both apps start, watch, take over, resume and stop the chat, and answer a waiting offer (Decline, Say something else). |
| "Export transcript" of a support chat (`GET /api/chatbot/support/export`), 2026-09-28 | **Desktop only**: the design's "the owner's tap on the PC, to a folder they pick". The file is plain text, NOT encrypted (the button says so), written where the owner picks with the Windows "Save as" dialog; a phone has no folder on the PC to put it in, and says "Export transcript is on the PC only." The encrypted chat history keeps the record on both apps' History. |
| Saving a chatbot API key (`py -3 jarvis_chatbot_api.py key <service>`) and choosing "a second AI on this PC" (`local_model` under `[chatbot]` in `jarvis-framework.toml`), 2026-09-28 | A key is entered on the PC only, like the web-search keys: sending it from the phone would send it somewhere other than its own service (rule 3). Neither app has a screen for entering a key or choosing the local model; once either is done on the PC, both apps' chatbot screens can start a conversation with it (`/api/chatbot/*`), and both apps see whether a key is saved, in "What Jarvis can reach" ("Chatbot conversations with a key (API)"). The local model is a settings-file line, as the other second-card settings are. |
| Setting an API chatbot's monthly money limit, or correcting its price (`py -3 jarvis_chatbot_api.py limit <service> <dollars>`, `price <service> <in> <out>`, `spent`), 2026-09-28 | Set on the PC only, the same place a key is added, as the owner decided ("a monthly amount per service, set on the PC"). Raising a limit or lowering a price is a loosening - more money can leave - and a person typing at the PC's own command line is how every other loosening of this feature is done (a key, the model line); there is no route for either, so no app, and nothing that holds the pairing token, can raise one. Both apps READ it: the chooser shows "About $X of $Y left this month for <company> (prices are estimates you can correct on the PC)" under each API service with a limit, and the approval card (written on the PC) says the same. Lowering is on the PC too, to keep ONE place for the numbers. |
| Jarvis Live's always-on-top badge, its tray row and the red mark on the tray icon, and ending Live when Windows locks (and pausing it when the lock cannot be read) | The badge is the PC's always-visible Live sign (docs/LIVE-DESIGN.md); the phone's sign is its Live screen, a strip on Home and an ongoing notification (the row in the phone table). Windows' lock is a PC thing; on the phone, App lock and the screen do that job. |
| Jarvis Live's "End Live when" as a PC voice setting (`live_end`: when App lock would ask again, or - looser, with an approval card - only when Windows locks) | The owner's decision of 2026-09-28 is about the PC, where Live can outlast App lock while the owner walks away from a desk. **The phone has its own "End Live when" since 2026-09-28 (the Jarvis Live extras)**, on its Security screen, saved on the phone: "When App lock would ask again" (default) or "Only when the phone's screen locks" (looser, so it asks for the fingerprint or PIN, like every loosening there - not a card, because the phone's lock settings never go to the PC). Each app keeps its own, because each app's App lock is its own. |
| The "Start or end Jarvis Live" hotkey (`hotkeys.rs` `toggle_live`, off until the owner picks a key; Alt+Shift+L suggested), 2026-09-28 | A key on a PC's keyboard. The phone's one-tap equivalents are its Quick Settings tile and the headset button (the phone table). |
| Jarvis Live noticing "another program is using the microphone" (Windows' own record) and muting itself | The PC's way of noticing a call (the owner's answer, 2026-09-28). The phone notices a call from Android's audio mode instead (the phone row). When Windows' record cannot be read, the PC's sign says "Jarvis can't tell when you're on a call - use Mute". |
| "This looks like a game, so nothing in it is kept or learned." strip under the Jarvis bar (the second chat audit, 2026-09-28) | The bar has a strip for the chat's own state ("Temporary chat: ..."); a game or role-play the PC made temporary by itself gets one too, so a chat that never reaches History says so. The phone has no such strip: it only avoids saying "the last one is in History" for a game (`ChatSession.game`), and "New conversation"/"After 30 quiet minutes" say the plain thing. |
| Spending summaries: the "Check these columns" box, the saved layouts and the categories editor (`/api/spending/profile`, `/profile/delete`, `/categories`, `/suggest`), 2026-09-30 | Bank files live on the PC and adding a folder is already PC-only; a phone screen is a poor place to map columns, and the standing rule is no deep config editing on the phone. **Both apps ask the same questions and draw the same table** (`/api/chat/table`, in the chat); the phone shows the categories read-only and says "Set up on the PC" when a file's columns have not been checked. The PC refuses these writes from any other device (`jarvis_owner_check.from_this_pc`). |
| Topic controls: Brain -> Memory -> Topics (**2026-09-30**, JARVIS-API §107) | **Both apps get the rows, the four-choice picker, the "Check these" list, Show them, and add / rename / delete.** **One-sided on purpose:** (a) **editing a topic's keywords is the PC's** (typing a long list of words is deep configuration; the phone shows the count only); (b) **the Galaxy is the desktop's alone** (standing rule: no memory graph on the phone), and it hides people linked only to an Off topic's facts; (c) **the fact words in the check list and in "Show them" are a memory list on both apps**: hidden under "Hide memory lists and chat history" and App lock, and topic **names** are hidden there too (rows read "Topic 1, 41 facts, mode"); (d) **turning a private topic back on is decided by tapping the card on either device** (tier ask; no Windows Hello - nothing leaves the PC), and every change is held on a stale link. |
| Chatbot money limits: the Raise control, the "Remove the limit" button and the price boxes (`POST /api/chatbot/money`; JARVIS-API §122) | **The READ is on both apps now; the WRITE is the desktop's alone for this step (2026-10-12).** The backend answers a paired phone as well as this PC (`jarvis_chatbot_limits.py`: a raise from a phone raises the same card and is answered with that phone's own fingerprint or PIN; a lowering, a removal and a price correction need no card and may come from either app), and the phone draws the whole page in the PC's own words - every service's limit, what is spent, what is left, its price with `yours`/`default` and the UNVERIFIED mark, and its answer-length cap (`net/Money.kt`, `ui/screens/MoneyPlate.kt`, Brain -> Money and time). What the phone does NOT have yet is the control: it sends no body to this route at all, so `Chatbot.WRITE_PATHS` gains no entry until the caller that uses one exists (CLAUDE.md, "a `WRITE_PATHS` entry must ship with its caller or not at all"), and the plate says plainly that changing a limit from the phone is not built yet. The API key itself stays the PC's on both apps, which is what the PC's own `pc_only` sentence says. `tools/check_parity.py`'s entry is `ported` - it names the read half and says the write half is still to come. |
| Which picture reader reads the words in a picture: Windows' own text recognition (the default) or RapidOCR (`jarvis_ocr.py`, 2026-10-13) | **The READ is on both apps; the CHOICE is the PC's alone.** `GET /api/second-card`'s `picture_text.engine` already names the reader in use and whether it works, and both apps read that route before a picture is sent - so the Hardware screen says which one answered, in words, on the phone too. What the phone does not have is the switch, and that is deliberate for the same reason as the speech-detector row above ("invisible upgrades get no switch"): the setting is a file on the PC, chosen by measurement, and **nobody can judge which picture reader is better by looking at a phone**. It is not a permission and not a loosening - both readers run locally and neither sends anything anywhere, so there is no card to approve and nothing an approval would decide (`jarvis_ocr.reader()`/`set_reader()`; `py -3 jarvis_ocr.py reader`). There is no new route, so `tools/check_parity.py` has nothing new to classify, and this row is here so the gap is not mistaken for an oversight. **The reader is OFF by default and is not measured as better** - `docs/MEASURED-2026-10-13-ocr-two-readers.md` has what the comparison actually said. |
| Personality presets, the four tuning dials and "My personalities" (Settings -> How Jarvis talks, 2026-10-23, Personality Presets Slice 2a) | **Desktop first, one-sided on purpose for now.** The panel - eight built-in presets, four tuning dials, the voice-sync switch and the owner's saved mixes - is the Windows Settings window's (`manner-settings.js`, `personalities.js`). The phone's Mind screen still offers only the older Warm/Plain choice and shows no preset cards, dials, saved mixes or Hear Sample. The data rides on the EXISTING `/api/manner` read and its one-field writes (`personality`, `dials`, `voice_sync`, `custom:{op}`); no route was added, so `tools/check_parity.py` has nothing to classify. The Android half is a later slice, not an invented phone caller: until it lands the phone keeps the behaviour it had before, and neither app claims otherwise. **Hear Sample today plays the preset's base voice only** - the PC's `/api/voice/voices/sample` accepts `{"voice"}` and nothing else, so the blended-voice preview waits for the Kokoro/Live voice slice; the page says so under the grid. |

| **"Update both halves"** — one button that patches the Python backend and then installs the signed Jarvis Desktop release (`update.rs`'s `update_both`, `backend_update.rs`, `backend_update_status`/`set_update_folders`, and the repo tool `tools/update_backend.py`; the owner's own request, made directly, 2026-10-13; three paces and a real progress bar added 2026-10-17) | Written with the feature. **A phone cannot patch a PC's backend.** The patch program (`scripts/apply-patches.ps1`), the repository it lives in, and the Python folder it writes into are all on the PC, and the work is `git apply`, then `pip`, then the test suites - none of which a phone can run, and none of which should sit behind a pairing token that can be used from anywhere on the private network. So there is deliberately **no route**: the phone is not offered a control that cannot work, and `tools/check_parity.py` has nothing to classify because nothing was added to the API. What the phone already does about a version gap stays as it was and is truthful: every route a newer backend grew answers 404 to an older app, and each app says so in the PC's own words (`jarvis-client`'s "Update the backend by running apply-patches.ps1"). The desktop's own half of this - the signed release check - is the desktop's alone for the same reason `install_update` is: it replaces the executable on the PC, which is a thing only the PC has. **The three paces are the same one-sided decision** (2026-10-17): `max_speed`, `responsive` (the default and the recommended one) and `safe` choose how many of the SAME suites `backend/run_suites.py` runs at once while the backend half is updated - 22, 14 and 1 workers on this PC's 24 threads. They are worked out by `tools/update_backend.py --modes-json`, read by `backend_update_status` and shown as a choice when "Update everything" is pressed; an unknown pace is refused before anything runs. There is no phone equivalent because there is no phone half of this feature at all, and the progress bar is painted only from the tool's own `JARVIS-EVENT` rows (`update_progress.rs` -> `backend-update-progress`): its fraction is completed work, never a timer, and on a fallback the bar starts a labelled second (safe) pass rather than pretending the first one is still going. |

| **A browser as a Jarvis client** (PWA slice 2, 2026-10-23: `jarvis-desktop/src/hud-web-bridge.js`, served with the HUD page; `POST /api/devices/web-session` / `web-logout`) | **Desktop only, one-sided on purpose:** the browser is a THIRD kind of client, not the phone. A tablet or laptop browser opens the same HUD page from the PC (over Tailscale/NordVPN Meshnet or on the PC itself), pairs with a key the owner printed for it at the PC's own terminal, keeps the PC's HttpOnly cookie, reads the live event stream through a `fetch()` reader, and keeps its OWN HUD layout in that browser's `localStorage` - never the PC's. The phone does not need any of it: it is already a paired device with its own key, its own screens and no cookie session, so neither route is ported there (`tools/check_parity.py`: both `deliberate`). No Tauri command was added (`capabilities/hud.json` untouched), and the browser has no client-side speech-to-text: the browser's cloud recogniser is removed from the page, and web voice waits for the HTTPS/AudioWorklet slice. The real iPad/PWA device rows remain NOT-TESTABLE until driven on a device. |

**On the phone, kept off the desktop:**

| what | why |
|---|---|
| "Temporary is on - this Live session will not be kept in History." shown BEFORE Live starts (the owner, 2026-09-29; `LiveScreen.kt`) | The phone's Live screen is a screen of its own with the Start button on it, so it can say so before Start. The desktop's Live strip exists only while Live is on here, so its line appears then; Temporary's own strip is already on the bar the rest of the time. |
| "This is the chat you are in on Home" line on an opened chat in History, and "Change" beside History's on/off line (the second chat audit, 2026-09-28) | The phone's History is a screen of its own, next to Home's chat, so it can name the one Home is in and put the switch's state at the top (the settings sit at the bottom of a long list). The desktop's Brain History is a separate window whose settings row is always on screen, and the bar tells the owner where a chat went when it ends. |
| Scanning the pairing QR code, or typing its code (`/api/pair/claim`, `/api/pair/collect`; QR-code pairing, 2026-09-28) | The phone is the device being paired. The desktop runs on the PC, which already has its own key (the old shared one, kept for this PC even after Retire), so it has nothing to pair. The backend refuses both routes from the PC itself. |
| The ongoing "Talking to Gemini, 3 of 5" notification with Stop, while Jarvis talks to a chatbot for the owner (`service/ChatbotNotifier.kt`; JARVIS-API §87) | Written with the feature, 2026-09-28. It is how a phone in a pocket shows that something is still going and offers Stop without opening the app. On the PC the same line heads the Brain's "Talk to a chatbot for me" card, the approval card arrives the usual way, and the "Stop everything" hotkey stops a conversation too - a Windows notification that stays up would only repeat what the Brain shows. The same holds for "Ask several and compare" (2026-09-28): the phone's line reads "Comparing 3 chatbots: asking ChatGPT, 2 of 3" and its Stop stops the whole comparison. |
| The phone's own layout settings (`AppearanceStore.kt`, `Look`: the face's share of Home, the tabs row, glow, motion, compact spacing, corners, text size, panel edges, and the "make room" switches) | They describe a phone screen. They are saved per device and never synced (`toSyncDocument` leaves them out), so they cannot change the desktop. |
| "Also on my phone" (the owner's decision of 2026-09-26; `net/AlsoOnPhone.kt`, a button on an alarm or reminder in Brain -> Coming up) | Written with the feature. It hands an alarm to the PHONE's own Clock app, or a reminder to its calendar, by the owner's tap, so it rings with the PC off - the gap it closes is the phone's alone (the PC is Jarvis's clock, and the phone hears of a job only while connected). On the desktop the PC already rings it; Windows' Clock app offers no way for another program to add an alarm; and putting an event into Google Calendar from the desktop would be a new way out of the PC (a link to Google carrying the event's words), which the creativity audit (usefulness #12) said needs the owner's OK first - not built. No route is involved, so `tools/check_parity.py` has nothing to check. |
| "Also on my phone" on a "Photo to reminder" proposal (the owner's choice of 2026-09-28; `net/PhotoReminder.kt` `calendarOffer`, `PhotoReminderDialog.kt`; JARVIS-API section 83) | Written with the feature. Both apps have "Photo to reminder" (the Jarvis bar's screen capture and the Brain's "Choose a picture..." on the PC; a picture shared to Jarvis on the phone), and both add a Jarvis reminder on the owner's tap. Only the phone's proposal also has "Also on my phone" - the same hand-over as the row above, to the phone's own calendar - for the same reasons: on the PC Jarvis's own reminder already rings, and putting the event into a calendar from the PC would be a new way out of the PC. The picture's words are outside text on both. |
| **"Swipe to approve or deny"** (the owner, 2026-09-28; Security on the phone, `SecurityRules.SWIPE_TITLE`, `Security.swipeDecides`) | The swipe exists only on the phone's approval card - the desktop decides cards with buttons and keys only, so there is nothing there to turn off. On by default (as before); off, no swipe decides any card, whatever `risk.swipe_ok` says. Turning it off is instant; turning it back on needs the fingerprint or PIN check, like every other loosening on that screen. Saved on the phone only. |
| **Blocking screenshots while a lock is on** (`FLAG_SECURE`, `SecurityRules.blockScreenCapture`) | **Decided and built, both apps.** The owner decided it for the phone (apps security audit L5, 2026-09-25), where screenshots, screen recording and casting are all a tap away, and then decided it for the desktop on 2026-10-11. On the PC, while App lock would ask for Windows Hello (the owner has gone) or while "Windows Hello for memory lists and chat history" is hiding the Brain's lists, every window of the app is marked `WDA_EXCLUDEFROMCAPTURE` through `SetWindowDisplayAffinity` (`src-tauri/src/lock.rs`; the rule is `Security::blocks_capture` in `lock/rules.rs`, the desktop's half of the phone's `SecurityRules.blockScreenCapture`). It follows those two existing settings - there is no switch of its own, the same as on the phone - and it is cleared the moment the owner passes Windows Hello, so a capture the owner takes themselves still works. **What it is worth, plainly:** on Windows 10 2004 and newer this keeps the app's own windows out of screenshots, screen recording and screen sharing taken through Windows' own capture APIs. It does **not** stop a camera pointed at the screen, and it does not promise anything about what sits *around* the window in a full-screen capture - Microsoft's own page for the function says it is not a security feature and gives no guarantee. It is the cheapest way to copy what is on screen that is closed, not a wall. Not Tauri's `set_content_protected`, which on Windows applies the same setting by rebuilding the window - that closed Settings the moment a pairing succeeded (the owner's report, 2026-10-07). |
| **Smartwatch notifications** (`GET`/`POST /api/notifications/watch`, `phone-only` in `tools/check_parity.py`; the owner's decision, 2026-09-25, reconfirmed 2026-09-27, Q17) | A smartwatch pairs with a phone, never with a Windows PC - there is nothing on the desktop for this to mean. The setting itself still lives on the PC, the same as every other approval-card switch (`docs/ARCHITECTURE.md` §3: one permission model, one place cards come from), so a stolen or borrowed phone cannot flip it on its own; only the phone ever reads it or acts on it (`.setLocalOnly(...)` on its own `NotificationCompat.Builder`s). Off by default - every notification stays on the phone; turning it on raises one card (`watch_notifications_enable`), turning it off is instant. There is no Jarvis watch app and none is built for this: Android's own, already-built-in notification bridging does the copying, to whatever companion device is paired, once this setting stops refusing it. |
| **"Playing on your PC" buttons** (`GET /api/media`, `POST /api/media/control`; the owner's choice of 2026-09-28, `docs/JARVIS-API.md` §74.2) | Written with the feature. **Since "Widgets you describe" (§86, 2026-09-28) the two routes are `ported`:** the desktop calls them ONLY for a widget's "Play/pause PC" button (`brain/widgets.rs`), with the phone tile's own play-or-pause rule; it still shows no "what's playing" of its own, for the reason below. The desktop IS the PC: Windows' own media keys and media flyout are already there, and "pause the music" said or typed to the Jarvis bar is answered without the model (§47.1). A Jarvis copy of those buttons on the PC would add a second control for the same thing. On the phone they are one tap on Home, greyed on a stale link (rule 4), no card. |
| **Ringing when "ring my phone" is said** (the `ring_phone` event; `docs/JARVIS-API.md` §74.1) | Written with the feature. The PC is the one being asked, never the one being found: the desktop ignores the event, and the phone rings on its alarm channel with Stop and a time-out. Saying it works from both apps (it is answered on the PC without the model). With one pairing key for every phone, every connected phone rings - the answer says so; per-device targeting waits for "more devices". |
| **"Hey Jarvis is off since the phone restarted - tap to turn it back on"** (`data/WakeResume.kt`, `service/WakeResumeNotifier.kt`; the owner's choice of 2026-09-28, `docs/JARVIS-API.md` §81.1) | Written with the feature. Only the phone has this gap: Android will not let an app open the microphone at boot, so the phone's "hey Jarvis" is off after every restart until the owner taps. The desktop's listener is part of the backend on the PC, which starts with the PC and needs no tap, so there is nothing for a notice to say there. No route, so no `tools/check_parity.py` entry. |
| **Widgets you describe: the home screen vs. the widget window** (`docs/JARVIS-API.md` §86; `widget/JarvisBoardWidget.kt`, `src/widget-board.js`) | Written with the feature. Both apps have the whole feature (describe, preview, Add, Delete, draw one). What differs is WHERE a widget is drawn: the phone offers three home-screen slots ("Jarvis widget 1-3"), like its three Quick Settings tile slots, because Android cannot add a widget type while the app runs; the PC draws ONE chosen widget inside the existing desktop widget window, in place of the face - not a new window, and not the Windows 11 widget board, which only takes widgets from a packaged (MSIX) app, and this app is not packaged that way. The phone cannot tell a paste from typing in its text box, so it always says "typed"; the desktop's box sends pasted words as pasted, which the PC refuses. |
| **Quick Settings tiles the owner chooses** (`data/QuickTiles.kt`, `service/QuickTileService.kt`; the owner's choice of 2026-09-28, `docs/JARVIS-API.md` §81.2) | Written with the feature. Quick Settings tiles are an Android panel; Windows has no equivalent a program can fill with its own buttons. The PC already has the same five things close at hand: the Stop everything hotkey and tray row, the Jarvis bar ("set a timer for 10 minutes", "brief me", "focus for 25 minutes", "pause the music" - all answered on the PC), and Windows' own media keys. Every tile calls a route the phone already called (`/api/focus/start`, `/api/schedule/add`, `/api/stop_all`, `/api/media`, `/api/media/control`), so `tools/check_parity.py` is unchanged. |
| **The Android 17 notes** (the assistant volume line in Settings -> Voice, and the "try Android's own Bubble" line under Floating Jarvis; `docs/JARVIS-API.md` §81.3-81.4) | Written with the feature. Both describe what Android 17 does for this app; Windows has neither an assistant volume slider nor app bubbles. |
| **A haptic tick on letting go of the talk button** (UI audit "do first" item 7, 2026-09-26) | A PC has no vibration motor. The desktop's own half of "Caught it" is a short reactor "inhale" instead - the same contraction-and-spring the moment gets on the phone (`jarvis-desktop/src/style.css` `reactor-inhale`, called from `main.js`'s `stopPushToTalk`, never on a cancel) - so both apps mark the same instant, each in the one channel its hardware actually has. |
| **Refusing a home-network desktop address up front** ("...this phone can only reach your PC by its Tailscale name ... or its NordVPN Meshnet name ...", `PhoneAddress.kt`; 2026-09-27) | Written with the change (§2, "Which addresses the phone can use"). It makes the phone's own judgment agree with Android's per-app list of names that may get plain http:// (`network_security_config.xml`), which Android enforces through OkHttp on every request. Windows has no such per-app list, and the desktop's requests to Jarvis are made by its Rust code (`reqwest`), which has none either - an address the shared rule accepts is one the desktop can actually use (usually Jarvis on the same PC) - so it keeps the shared own-networks rule alone, with the shared sentence. Both apps still apply that rule, from the one table (`tools/gen_own_network_cases.py`). |
| **Setup helps from the phone play test** (2026-09-28; walk-through N1, C8, C9): reconnecting at once when the phone's network changes, the "Tailscale (or Meshnet) is off on this phone" line, **Show token** on the pairing screen, and the one-time "Background restart" offer after the first pairing | Each fixes something only the phone has. The desktop normally talks to Jarvis on the same PC (`127.0.0.1`), so it has no network to change and no VPN to need; a token is normally never typed on the PC at all (Jarvis makes one and the desktop reads it from Windows Credential Manager), so its own masked Token box, for choosing your own token, got no Show button - a possible follow-up, not built; and Windows does not close a desktop program to save battery. No route is involved, so `tools/check_parity.py` has nothing to check. The PC's half of "can the phone reach Jarvis?" is the preflight check `phone` (`backend/selftest.py`), which the desktop's owner runs. |
| **"Findings" (Brain → Findings, `BrainScreen.kt`'s `Probed("Findings", brain.initiative, ...)`, "What Jarvis noticed on its own")** | Written down 2026-09-27, on the ease-of-use audit's parity check (#17). `GET /api/initiative` is read on both apps - the desktop's HUD window polls it too (`jarvis_hud.html`) - but only as transient cards the owner dismisses while the HUD happens to be open; the desktop's Brain window has no section that keeps them. The phone's Brain gives the same feed a persistent, browsable place instead, with the honest empty state from `initiativeNote()` ("Jarvis doesn't watch anything on its own yet") for when the initiative engine's check list is still empty. Nothing here is phone-only data; it is a phone-only place to read it back. |
| **Reading phone notifications** (`GET`/`POST /api/notifications/phone`, `phone-only` in `tools/check_parity.py`; the owner's decision, CLAUDE.md 2026-09-26; built 2026-09-28; docs/JARVIS-API.md §61) | A Windows desktop has no equivalent to "which app posted a notification, and what did it say" - `NotificationListenerService` is an Android concept with no PC surface this project has any reason to invent one for, the same reasoning §56 (Floating Jarvis) and the smartwatch row above already give for their own phone-only halves. The setting itself still lives on the PC, the same as every other approval-card switch (§3: one permission model, one place cards come from) - only the phone ever reads or acts on it. Everything else (which apps - empty by default, banking and SMS/Messages blocked outright; the one-time-code redaction; the local, capped store) is entirely on the phone and never reaches this backend module at all - it is a plain on/off switch, nothing more. |
| Jarvis Live's ongoing notification (End, Mute; kept on the phone) and the screen kept on while the Live screen shows | The phone's always-visible Live sign when the owner leaves the app; the PC's is the badge (the row in the desktop table). A PC screen does not sleep under a conversation the way a phone's does. |
| Jarvis Live noticing a phone or video call from Android's audio mode, and saying "I've lost the link to your PC." in the phone's own offline voice | Calls happen on the phone; the PC uses Windows' microphone record instead (the desktop row). The link line is the phone's because the PC's voice cannot reach it when the link is down; on the PC the sign says "Paused: link lost". |
| Jarvis Live's camera (built switched OFF, hidden in both apps until the 12 GB card passes the photo test) | The owner's answers of 2026-09-28: the phone's camera only - a PC webcam mostly sees the owner's face and room (docs/LIVE-DESIGN.md section 5). Taking the picture on the phone is not built yet; only the gate is. |
| **"Solve it here"**: a live picture of the PC's paused browser window and the owner's taps and typing passed back to it (`/api/chatbot/handoff/*`, `phone-only` in `tools/check_parity.py`; JARVIS-API §87.8), 2026-09-28 | The owner's decision is about the PHONE: "a captcha can be handed to the owner's phone". On the PC the browser window is right there, so the desktop shows the same alert on the Brain's Work tab ("Gemini needs you on this PC", from `/api/chatbot/status`'s `handoff`) and points at the window - it never calls the picture or input routes (`tests/handoff.mjs` checks). The phone's alert is its own channel and always stays on the phone. |
| The Jarvis Live Quick Settings tile, the headset button in Live, and the 10-minute "Live ended - Resume" notification (the Jarvis Live extras), 2026-09-28 | Phone things: a tile lives in Android's pulled-down shade, a headset button reaches a phone's media session, and a notification is how a phone in a pocket offers Resume. The PC has the tray row and the Live hotkey (the desktop table) and its badge shows "Resume Live" for 15 seconds, in the Jarvis bar until the 10 minutes are up. |
| Preferring a Bluetooth headset's microphone in Live, and saying which microphone is in use (the Jarvis Live extras), 2026-09-28 | On the phone Jarvis picks the microphone (Android's communication device; no Bluetooth permission). On the PC Windows picks it - Live opens the default microphone, both the plain and the echo-cancelled way (`aec.rs`) - so a Bluetooth headset is used when Windows makes it the default, and the Voice settings already say which microphone that is. Choosing a different microphone on the PC is a larger change to both capture paths, not made here. |
| "Talk about this in Live" in Android's Share sheet (the Jarvis Live extras), 2026-09-28 | A Share sheet is Android's. The text is outside text exactly as a share to Home is (`provenance: "shared"`, JARVIS-API §18); the PC's quickbar already takes clipboard text with its own "clipboard" tag, in Live as anywhere. |

**The fading-card radar and the "Mark my answer" button were phone-only in
slice 22B (2026-10-17) and are on BOTH apps since 2026-10-21.** The two PC
fields are additive and both apps read them from the one shared fixture
(`tools/gen_decks_cases.py`: `samples.decks.radar`, `samples.graded_reveal`).
The desktop draws the same radar rows under the deck list, sends the typed box's
words to the PC's deterministic grader only on the "Mark my answer" tap ("Show
answer" still sends nothing), and shows the grader's own sentence word for
word - the same sentence the phone shows. No route, key or word differs between
the apps. **A phone must not do speech-to-text** (`CLAUDE.md`), so there is no
microphone and nothing "spoken" here; the 22A voice-review receipt waits for a
slice that records a clip and lets the PC transcribe it.

**The picture-in-picture idea landed on both apps, on 2026-09-27, by two
different sessions working at the same time - not one shared mechanism,
because neither platform's own way of drawing something on top of other
apps has an equivalent on the other.** On the phone, "Floating Jarvis"
(Settings -> This app, `data/FloatingAvatar.kt`, `docs/JARVIS-API.md` §56)
is a three-state setting between Android's own chat-bubble notification
(`Notification.BubbleMetadata`, API 30+) and a `TYPE_APPLICATION_OVERLAY`
window. On the desktop, "the floating face" (Settings -> Appearance, the
tray, or `Alt+Shift+F`; `docs/JARVIS-API.md` §57) is a small always-on-top
Tauri window showing only the animated face. Both are voice only, and both
expand into the real chat surface on "open a chat" (or a close phrasing)
said or typed to Jarvis; on the phone a tap on the avatar does the same,
but the desktop's floating face is deliberately never clickable
(`floating.html`, `pointer-events: none`, `floating.js` registers no click
handler) - voice or typing is the only way in on the PC. Both went through
this row's own honest hedge while only one
side existed - correcting a claim once the other side's code could actually
be read, per this file's own "Talking to the other branch" section, rather
than trusting either session's guess about the other. Neither reuses a
backend route: the phone's phrase match runs entirely on words the desktop
already transcribes (`Heard.text`); the desktop's runs through the existing
`jarvis_quick.py` fast path and the `X-Jarvis-Route` header every fast-path
answer already carries. Not a `tools/check_parity.py` entry either way -
no route on either side for it to see.

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
the PC (the Jarvis bar, the widget and the HUD show the card itself, and the
button opens it in the HUD window) and on every screen but Home on the phone
(Home shows the cards). Both name the last card in the queue as read. The
phone's home-screen widget has no Approve at all - "Review" opens the app -
and sits where Approve sits elsewhere, on the right.

**PC help is in both apps since 2026-09-28** (`docs/JARVIS-API.md` §84):
the same five answers from `GET /api/pc/help`, and the same five questions
answered in chat by `jarvis_quick.py`. One small difference, on purpose:
the desktop shows it in Settings -> Hardware and models, the phone in Brain
under Hardware - in each app, where the graphics cards already are. Changing
Windows settings from it (Night light, dark mode, Do not disturb) is in
neither: nothing safe to build it on exists yet (§10).

**The headless browser (Obscura) runs on the PC only, and both apps only show and set it** (2026-09-29, JARVIS-API §97). The program runs in the PC's backend; the desktop (Settings, "Headless browser") and the phone (Settings, "Headless browser (Obscura)") read the same setting and switch it through `/api/browser/engine` with the same words (`contract/browser-engine-cases.json`), and neither ever runs a browser, sees a web page or holds a proxy or an address for it. **The chatbot driver, the customer-support chats and "Solve it here" keep using the visible browser on purpose**: each must hand a captcha, a sign-in or an "are you a bot?" question to the owner in a window, Obscura has no window, and their own rules say the window is a real, visible browser (Jarvis writes no fingerprint-spoofing for it; the old "driven openly" rule was reversed on 2026-09-29, the visible browser was kept). The headless engine cannot hand anything over: reaching a captcha or sign-in page there stops the run and tells the owner, in words, to ask again with the visible browser.

**The form picture is on the Jarvis bar's card and the phone's card only** (2026-09-30, JARVIS-API §98). The second card of a filled-in web form carries one picture of the form, and it is shown where the card is decided in full: the desktop's Jarvis bar and the phone's Home. The desktop's widget, its toasts and the HUD page, every notification and the phone's home-screen widget stay title-only, like every card - a picture of the owner's name, phone and email does not belong on a lock screen or a widget. It is hidden under App lock and under "Hide memory lists and chat history" on both apps. The desktop has no equivalent of the phone's screenshot block, so there is nothing to match there. **It is the one screen picture NOT run through `jarvis_screen.clean_picture`** (owner, 2026-09-30): the owner must read their own details to check them, and the picture never reaches a model, is held in memory only, and is dropped when the card is decided. Every other screen picture still passes that door. Not a new way out of the PC: the form's words go out through browser control's existing `control_browser` way out, to the site the plan named.

**"Start the local model" is on the Jarvis bar, the widget and the phone's Home, and deliberately NOT on the HUD window** (2026-10-13, JARVIS-API §137; the owner's decision after both of his Ollama lanes were dead for about five hours). The standing "the local model isn't running" line is drawn in all four places, and three of them now offer the one action that starts the lane the chat uses - by running **his own** Windows logon task, found on that PC by the half of its name a rename does not touch. **The HUD page is the one that keeps the line and offers no button**, and the reason is the proxy rather than the picture: `jarvis_hud.html` is vendored from the backend and runs under `hud_proxy.rs`, which allows it exactly five reads and one `POST /api/chat` precisely so that a script running in that page cannot call anything else. A route that starts a program on the PC is not something to add to that allow-list in passing - it is its own decision with its own review. Nothing is lost by it: the HUD's line still names the PC's own task, and the Jarvis bar (one summon away, and the window the owner chats in) carries the button. `tools/check_parity.py` is unaffected either way, because it reads the RUST commands and the JavaScript, and the bar's own `start_model_lane` is a desktop caller of both routes - so both are `ported`, and no other row in this section is needed for them.
**The skill library's four new doors are on the backend only, and that is the scope of this slice rather than a one-sided decision** (2026-10-15): `jarvis_skill_hub.py` (`plugins/ready/skill-hub/`) serves `GET /api/skills/hub/references`, `GET /api/skills/hub/projects`, `POST /api/skills/chain` and `POST /api/skills/learn`. No screen calls any of them yet - reading a skill's own reference manual, opening a message with `/skill`, looking in a trusted project's `.jarvis/skills`, and `/learn` are all things no app offers today. **This slice adds no route that already existed**: the list (`GET /api/skills`) and the removal (`POST /api/skills/decide`, with the "are you sure?" before it) are unchanged and are still on BOTH apps. `tools/check_parity.py` cannot see any of this - it scans the two apps' own source, so a backend route no app calls is outside what it decides - which is said plainly here rather than read as a clean pass it did not earn. **When a screen is built it goes on BOTH apps, on the same routes and the same card**: `/learn` saves only through `jarvis_skills.write_skill()`, which runs the scanner and raises the existing `modify_own_code` card itself, and it writes nothing at all when `jarvis_scrub` is absent.

**The file guardian's history is on this PC only, and that is one-sided on purpose** (2026-10-18, LM-2A; JARVIS-API §140). `GET /api/guardian/snapshots` and `GET /api/guardian/diff` expose the already-shipped guardian store (`backend/jarvis_file_guardian.py`): the owner's snapshot index, newest first and bounded to 200 rows a page, and the bounded unified diff the module already produces. **The phone cannot and must not show it**: the copies are files on the PC, and `jarvis_owner_check.from_this_pc` refuses a request from another device BEFORE the module is read, so the phone gets a 403 rather than a list of the PC's files. The desktop half (a history drawer in Projects/Receipts) is a later slice; **no app calls either route yet**, so `tools/check_parity.py` sees no drift - a backend route no app calls is outside what it decides. The one honest gap, until that drawer lands: the backend cannot see App lock or "Hide memory lists and chat history", both desktop-side state, so these routes cannot withhold themselves while either is on - the drawer must hide itself, and JARVIS-API §140 records that as a gap rather than a guarantee. The restore route is a SECOND slice (LM-2B, 2026-10-18; JARVIS-API §140.4): `POST /api/guardian/restore` - POST-only, this PC only, and the EXISTING `undo_action` card through the real `jarvis_gate.check()`, with no gate nameable over the wire - saves the version here now and a new receipt before it writes, so the existing Undo reverses it, and a denied/timed-out/unraisable card writes nothing. The desktop drawer IS built (LM-2C, 2026-10-18): Brain -> Projects -> File history (`guardian-panel.js`, `guardian.js`, `brain/guardian.rs`) lists the copies newest first, shows the module's bounded diff, and offers Restore behind the EXISTING `undo_action` card (the PC decides it; the page approves nothing). It hides WHOLE under App lock and "Hide memory lists and chat history" - `brain/guardian.rs` replaces the answer with one sentence and asks the PC for nothing while either is on, which is the desktop-side half of the gap the backend cannot see. `tools/check_parity.py` now carries all three guardian routes as `deliberate`; the phone still has no page for them, by design.
**The selection chip is on the PC's Jarvis bar only, and that is one-sided on purpose** (2026-10-18, Pillar 24-B; JARVIS-API §141). The owner's decision (Spotlight 6): he highlights text in another program and presses **Alt+Space**, and the bar shows one `📎 Attach selection from <program>` chip with the first ~40 scrubbed characters. **The phone cannot do this and must not try**: the route `GET /api/selection` reads the PC's own focused window and refuses a request from another device before anything is read (`jarvis_owner_check.from_this_pc`), because there is no phone-side selection to read and the answer is the PC's screen content. Everything else about it is shared safety: the screen's "Never look at" list, private browser windows, password boxes, the lock screen, and `jarvis_scrub` decide what - if anything - comes back, exactly as "Look at this" does. Two differences, both said plainly: the read happens BEFORE the bar takes focus (UI Automation reports the focused control, so a page-side ask after the bar is up would always be empty), and the window title is never carried anywhere - only the program's name and the already-scrubbed words. `tools/check_parity.py` classifies the route `deliberate`.

**The voice-training free-speech prompts are desktop-first, and that is one-sided for now** (2026-10-19; #605 backend plan, #616 desktop redesign, #618 phone four-condition plan, #630 the clip's prompt field). The PC's plan (`gate.training.training.free_speech`) carries three natural prompts in the owner's own words. `POST /api/voice/enroll` `mode: train` accepts an optional `free_speech` array naming, for each clip, which free-speech prompt it answers (null or "" means the sentence read aloud; absent means exactly the old body) - so a screen can record a prompt as the prompt it really is rather than as another audio clip in the round. The desktop redesign uses it; **the Android training screen deliberately records the balanced read phrases only for now**, says so in its intro, and sends nothing for the prompts. That is a one-sided gap for this slice, not a backend route: the phone follows in its own training-screen slice, and no client invents a free-speech control it cannot send. `tools/check_parity.py` sees no drift because the route is the already-ported `/api/voice/enroll`.
**App control's hands are on the phone only, and that is one-sided on purpose** (the owner's decision of 2026-10-19: "enable accessibility service with control by jarvis as an option in the android app"; the PC routes are `backend/app-control.patch`, the phone's half is `jarvis-client`'s `service/JarvisAccessibilityService.kt` + `data/AppControl.kt`). The capability is Android's AccessibilityService: only the phone can read another Android app's controls and perform a tap, swipe, type, Back or Home on it. The desktop has no equivalent job - its own control engine is `jarvis_ui_control.py` on Windows UI Automation, a separate engine with its own plan/verify/stop-on-change rules, and it does not drive a phone - so `POST /api/app-control/run`, `POST /api/app-control/plan` and `POST /api/app-control/step` are `phone-only` in `tools/check_parity.py`. **The PC is still the brain and the gate**: for `/run` the phone sends an allow-listed app, ONE atomic step and a MASKED snapshot; the PC raises ONE `change_own_config` card, and only after the owner approves does `/step` return the ONE step the phone performs, re-checked against a fresh snapshot. **The run starts on the phone** (the owner's decision of 2026-10-20): the owner types what they want in the phone's app control screen, and `/plan` sends those words plus the masked snapshot to THIS PC's local model - the Agentic + Vision preset's model on the main lane, never the fast lane by accident, never a cloud model - which proposes ONE step; that proposal goes through the same validation and refusal list before ONE card, and the card names the step and the local model that planned it. The phone never plans a step itself, never auto-approves, never retries a changed screen, never takes a second step without another tap and card, and never logs the screen's words or typed text - the PC's audit line is app + verb only. **It is not enabled by this slice**: the PC's `[app_control] enabled` is false by default (a settings file with no `[app_control]` table reads as off, and no route turns it on), the phone's own option is off by default with an EMPTY allow-list, and Android's own Accessibility switch must be turned on by hand. Neither app claims it works until a real phone has been driven - NOT-TESTABLE is not a pass.
---


**PC-ONLY, and no phone route is planned** (2026-10-20): the **Obsidian vault organizer** (`backend/jarvis_vault_organizer.py`, `plugins/ready/vault-organizer/`, JARVIS-API section 151). Its read-only plan reads the full text of the owner's own vault of notes on this PC, so every route is refused from another device (403 `not_this_pc`, the project's own `from_this_pc` rule) and the phone gets no Settings row, no card and no chat tool for it. This is a decision, not a gap to close later: a phone control could only ever ask the PC to read that vault, and the feature is OFF by default behind `[vault_organizer] enabled = false` until the owner turns it on with one card. Both halves are built on the backend (read-only plan, and the writer under ONE card with guardian snapshots and one-click Undo, on a COPY of the vault first - `docs/JARVIS-API.md` section 151's runbook). No app is waiting on it because nothing in either app calls these routes, and none will: the phone deliberately gets no organizer control, only the owner at the PC's own screen.

**The phone cannot read the PC's screen or selection out loud** (2026-10-21, task-39): a **Jarvis Live** session asks "what's on my screen?" or "read this selection" and gets one **read-only** look at this PC's screen through the existing `jarvis_screen.py` "Look at this" path, or the existing `jarvis_ui_control.read_selection()` - see JARVIS-API section 153. Only a session on the **PC** may do it: a session started on the phone gets a fixed line and **nothing is read**, because the screen is this PC's own screen and the phone cannot see it. If the device cannot be known, nothing is read. This is a decision, not a missing feature to port: the phone already has its own "show my phone to Jarvis" path (section 62) and that stays the phone's way to share what it sees. Actions that change a program are not part of the bridge either: they keep their existing ONE `control_computer` card, decided by a physical tap/click, and Live pauses while a card waits so a spoken "yes" cannot answer it.
**True barge-in with echo cancellation is a design phase, off and unwired, and
desktop-only on purpose** (2026-10-21; Voice Slice F, after the owner approved
the whole Live & Voice program). `backend/jarvis_barge_in.py` is a
reference-subtraction (NLMS) echo canceller over Jarvis's own outbound TTS PCM
plus a 350 ms speech decision, behind `[voice] aec_barge_in = false`; no live
module imports it and no route calls it, so the live voice path has no change
at all. System WASAPI loopback is explicitly NOT the reference (the combined
ruling of 2026-10-21); the residual is memory-only and zeroed, and the CAM++
owner gate stays verify-first. The phone cannot run this half - the canceller
needs the PC's own TTS PCM and the PC's CAM++ check - and it already keeps
Android's `AcousticEchoCanceler` in voice-call mode, so there is no phone gap
to close in this slice. Design, synthetic proof and the measurement plan:
`docs/DESIGN-VOICE-BARGE-IN.md`. Real open-speaker barge-in is NOT-MEASURED
until the owner's hardware.
**The flight price radar is backend-only and OFF, and it is NOT a booking
tool** (2026-10-21; the owner approved the full anti-surveillance price/flight
stack; slice F1). `backend/jarvis_price_radar.py` builds Google Flights' public
`tfs` query in pure Python, reads the public search page's inline payload,
and keeps a SQLite price history with last-known-good/stale semantics and an
outside-text diff behind `[price_radar] enabled = false`. It is read-only: no
cart, no seat hold, no checkout, no booking/PNR path, no cookies, no login, no
redirects, one host, one GET, one attempt (a 403/429 is recorded stale and
never retried), at least 300 s between checks with jitter. It adds **no app
surface at all** - no route, no card, no Settings row in either app - so
nothing here is on one app and missing from the other. The multi-source
product pages are F2's own module (`jarvis_price_sources.py`: local SearXNG
price mentions + the dual-persona steering probe); F1 installs its source
objects lazily from `enabled()` (`install_f2()`, nothing imported while the
switch is off), and F2 delegates to F1's disclosure constants so each
approved sentence exists once. Proxy exits (F3) are a later, separate slice.
Design, the disclosure wording and what is NOT measured (the endpoint
is unofficial and no live request is made in the suite):
`docs/DESIGN-PRICE-RADAR.md`.

**The `Alt+Space` startup race is now self-healing, and the honest limit is Windows itself** (R6, 2026-10-21; `hotkeys.rs`, `lib.rs`, `settings.js`). Registering a global hotkey at login competes with every other Run-key program, and Windows gives the loser no warning - before this, a machine where PowerToys Run or Copilot held `Alt+Space` simply had no spotlight and nothing in the app could say so or fix it (`autostart.rs` documented the race as deliberately unfixed; the startup code only printed the refusal). Now: the startup registration still reports every verdict, and **only the summon action** (`toggle_quickbar`, whose default is `Alt+Space`; watched by id, so an owner who moved the key is retried on the key they chose) gets up to **three bounded background retries at 2 s / 6 s / 15 s** on the existing Tauri async runtime when the OS refuses it. Each attempt asks the plugin's own live registry first and never re-registers a key this process already owns; it never unregisters or retouches the other shortcuts; and it never blocks setup - the tray's **Show or hide the Jarvis bar** remains the fallback, and Win+Shift+J and the rest are unchanged. The OS verdict + retry count + last reason live in managed state (`alt_space_status`); Settings -> Shortcuts shows an honest line ("alt+space is currently held by another program on this PC. Jarvis retried N times after logon.") and one **[Re-claim Alt+Space]** button (`reclaim_alt_space`) that makes exactly one more attempt and repaints what the OS answered - it never rebinds anything and never picks another key for the owner. **The honest limit**: if another program keeps the key, no amount of retrying can take it; the retries cover the logon rush only, the button works once that program lets go, and the tray is always there. The real boot race (two programs racing at login on the owner's PC) is owner-tested, not provable from a test suite; the unit tests drive the pure retry machine with an injected registration fn (fails twice then succeeds on the third - exactly three attempts; fails all four including the initial one - false + the last reason), and the Settings page + command seam is driven in the existing Playwright harness. One-sided on purpose: global hotkeys are a PC thing (the phone has no equivalent, like the other hotkey rows above).

**The HUD's safety rail is fixed and outside every editable region** (H4,
2026-10-22; A4, 2026-10-23; `src/hud-safety.js`). App lock / hidden memory
lists (through the already-granted `get_lock_flags`), the queue-scoped
rush/outside-text evidence from the pending queue's `raised` object, the two
persistent session latches' own words (read-only, from `/api/status`; see
below), and the catching-up state live in one
`#hud-safety` strip that is not a card, has no `data-hud-card` or
`data-hud-region`, is not in `CARD_REGISTRY` or the layout document, and is
painted from live truth only — so no preset, import, hand-edited settings file
or edit-mode action can hide or move it (a hostile import naming such cards is
dropped by `normalizeLayout`; a non-default preset and a hostile saved document
are tested at the page level and the strip survives both, stays visible in
edit mode with its "Always visible" line, and is click-through at 1280x820 and
1024x768 at DPR 1 and 900x600 at DPR 1.5, clear of the bar launcher, the
quickbar pills, the composer and the approvals buttons; reduced motion adds no
animation). While the link is stale, the card's
**Approve waits and Deny stays enabled** — matching `stale_answer_refusal`,
which holds only an approved decision — and the strip says why in words. Two
honest limits: the real fixed Stop everything control (#742, `#hud-stop`) is one
of the protected controls the geometry tests keep clear of the strip - and the
strip still has no controls of its own (nothing on it approves, decides or
clears anything). **Since A4 (2026-10-23) the two persistent session latches are
readable too**: the PC's own `/api/status` carries `taint_latched` /
`rush_latched`, read-only (true/false/null, where null is "the PC has not said" —
never "not latched" — and a taint read that fails answers true, the gate's own
fail-closed rule), so the strip can say "this session is staying on your PC" and
"something Jarvis read tried to rush you recently; approvals ask for one more
look" with no card waiting and across a backend restart. The queue-scoped banner
stays separate and never claims a latch from a card alone; none of this adds a
command, permission, card, route or grant (`/api/status` was already on the HUD's
fixed allowlist), and no control can clear either latch. The real locked-window
state is still Rust hiding the HUD, so there is no in-page locked overlay by
design. No new command, grant, capability, inline script or CSP change; the
phone's own stale-approval and App-lock rules are unchanged (this rail is the HUD
window's face of facts the phone already shows in its own surfaces).

**Reminders Phase 2 editing is on the desktop first, and that is one-sided on
purpose for now** (2026-10-22, backend #730). The PC's backend already offers
`edit`/`move`/`reorder` to every client, and the HUD's Reminders panel and the
Brain's Coming up draw them; the phone's Coming up stays a read surface, because
a phone-side row editor is its own slice (a small screen, a keyboard-free
picker, and the phone's own stale-link/App-lock handling), and building it
half-tested in this one would be worse than saying so. Nothing is faked on the
phone: it calls none of the three verbs, so `tools/check_parity.py` sees no
drift. The verbs are ready for it, and JARVIS-API section 21 documents the
shapes it will use.

**The Galaxy layout presets are the desktop's, on purpose** (2026-10-23; the
Galaxy rework's Phase G0: `jarvis-desktop/src/galaxy-presets.js`, `brain.js`).
The three flat views - **Star map**, **Clean tree** and **Zen ring** - and the
switcher that chooses them (chips in the Galaxy bar, hotkeys `6`/`7`/`8`, a
remembered choice) are the **desktop Brain window's alone** for now: the phone
deliberately has no memory graph (the standing rule recorded elsewhere in this
section), and the editable HUD stage keeps its own canvas renderer until Phase
G1 shares the same layout math with it. Nothing here reads or writes the PC: the
layouts are pure position maths, the choice is stored on this device only, in
the Brain window's own `localStorage` (`jarvis.galaxy.preset`); unlike the
theme, nothing about it is persisted on the PC and no route is involved. No
backend route or phone source names any of it - so `tools/check_parity.py` has
nothing to classify. The five rich 3D presets the blueprint also lists are shown
as disabled "not built yet" chips, never faked.

## 9. Where the backend lives

**The owner's live copies are not in this repo.** The owner keeps
`jarvis_hud.py`, `jarvis_memory.py`, `jarvis_gate.py` and the rest on their
machine. `backend/` holds **patches** against them plus the tests that prove
the patches do what they claim. `backend/.gitignore` refuses the sources,
because a stale copy in git is worse than no copy — the next reader would not
know which is real, and the patches are written against *that* folder.

**Since 2026-10-06 there is also a published copy: `jarvis-backend/`.** It is
a checked snapshot of the owner's folder, taken so that a stranger can clone
this repository and have a backend to run rather than a folder of patches
against a folder they do not have: 181 files, 10.59 MB, LF endings.
`jarvis-backend/README.md` has the rule that produced it and what it
deliberately leaves out; `docs/BACKEND-PUBLISH-INVENTORY-2026-10-06.md` has the
measurement behind it, file by file. `backend/test_base_matches_repo.py` keeps
the copy equal to
this repository's own modules, and says plainly what it cannot prove: **the
patch stack does not reverse off the base** — it stops at
`approval-notice.patch`, because `backend/rebuilt/jarvis_events.py` already
contains that patch's code — so the base is checked against `backend/`, never
against the stack.

**Five modules had no second copy anywhere until 2026-10-06.**
`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_extract.py`, `jarvis_models.py` and
`jarvis_skills.py` — 605 KB — existed only in the one folder on the owner's PC,
and `jarvis_backup.py`'s archive read his data and no `.py` file at all. Two of
their neighbours, `jarvis_memory.py` and `jarvis_events.py`, already had a
deliberate exception, in `backend/rebuilt/`. No public upstream has ever been
found for any of the twenty-six: the evidence is that the files were produced
in assistant conversations and saved to disk, which makes that chat history
their only origin. Those five are now in `jarvis-backend/`, and the archive
writes the backend's own `.py` files into a backup under `source/`.

`scripts/check-backend.ps1` lists what a folder is missing — run it before the
patches, because a patch failing against an absent file reports "patch does
not apply" and reads as a bad patch.

That asymmetry has narrowed, not gone: **this repo is version-controlled and the
folder the patches edit is still not.** A patch here can always be recovered.
The file it edits still cannot, on its own.

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

**The page's own files are a closed world, and they are carried like modules
(2026-10-23, PWA Slice 3a).** `GET /` has always answered with
`jarvis_hud.html`; a browser then asks for the stylesheet, the fonts and the
modules that page imports, and every one of them used to be a 404 — the page
loaded half-dressed and its shell modules never mounted. `jarvis_hud.py` now
serves them through `STATIC_ASSETS`, an explicit `url_path -> (file beside the
server, exact Content-Type)` dictionary: a URL is a key or it is a 404, and
the request never becomes part of a path (so there is no traversal, no
directory listing and no prefix match). The same page gate applies — the token
is required (a browser's `<link>`/`<script>` requests carry the SameSite=Strict
cookie; an Origin, when present, must pass `_origin_ok`) — and every answer
carries `X-Content-Type-Options: nosniff`. Files the later PWA slices will
write (`/hud-web-bridge.js`, `/manifest.webmanifest`, `/sw.js`, `/icons/*`) are
listed ahead of time: a request is an honest 404 until the file lands beside
the server. The files reach the owner's PC the way the page itself does:
`apply-patches.ps1`'s `$SHIPPED` list copies each one beside `jarvis_hud.py`,
`tools/reconcile_live_backend.py`'s shipped sync carries the same list to the
live folder, and `tools/gen_base_from_backend.py`'s `BESIDE`/`BESIDE_BINARY`
tables put them in the published base (the woff2 faces are copied as bytes).
`backend/test_hud_static.py` proves the whitelist is exactly what the page
loads, that the handler refuses traversal and everything else, and that every
served file is in those lists; the HUD-side code itself is a base-HUD change
carried live by two literal deltas in `tools/reconcile_live_backend.py`'s
`DELTA_TABLE` (`tools/hud-deltas/hud-static-*.txt`), because the live
`jarvis_hud.py` is never replaced.

**A local test run writes nothing into the owner's home folder - the audit log
included (2026-10-20).** `backend/run_suites.py` gives every run a throwaway
config folder, HOME and audit log, and `apply-patches.ps1` gets the same
variables from `--state-env`. The audit log needed its own switch:
`jarvis_framework.audit_log` obeys `[logging].log_directory`, and the config
shipped beside the modules names `~/.openjarvis/logs/`, so moving only the
config folder still pointed the log at the OWNER's real file. That is not a
theory: measured over 22:00-23:22 on 2026-10-20, local suite runs appended 191
`gate.asked`, 93 `gate.denied`, 180 `backup.restore.card`, 420
`media_index.deleted` and more to the owner's real audit log while approvals.db
and every live file were untouched - synthetic events in the forensic record.
So `jarvis_framework.log_dir()` now honours `JARVIS_LOG_DIR` over both the
config and `CONFIG_DIR/logs`, the runner sets it to a per-run temporary folder
for every suite, and the suites that test the logging machinery itself, or read
audit lines back from a log folder they choose (`LOG_MACHINERY_SUITES` in
`backend/run_suites.py`: `test_log_retention.py`, `test_rebuilt.py`,
`test_suite_state.py`, `test_skill_discovery.py`, `test_memory_erase.py`), are
the explicit, documented opt-out.
`backend/test_log_isolation.py` reproduces the hazard in a throwaway HOME and
proves the fix, the precedence, the default and the runner's own behaviour.

---

## 10. Things that do not exist

Say so rather than designing around imagined code. Every file this list names was
checked against the repository on 2026-10-16: each one exists where the text says
it does, and the two marked "only on the owner's PC" are still absent from
`backend/`. An item moves off this list only when the file that makes it true is
named.

**No longer missing** (this section used to list them, and was wrong once
they landed):

- `jarvis_speech.py` now exists, in `backend/`, with `jarvis_wakeword.py`,
  and `apply-patches.ps1` copies both in. It is what the four `/api/voice/*`
  routes call: speech check (Silero VAD), speaker check (with speech-to-text
  running beside it since 2026-10-20, its words used only where the check
  passed and discarded otherwise - `docs/JARVIS-API.md` section 5), and
  text-to-speech back, all on this machine. Its model files are NOT in the
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
  8 GB or more since 2026-09-30, 10 GB before; an 8 GB card runs three of the
  switches, see docs/SECOND-CARD.md), and seven switches - longer conversations, pictures,
  background learning, browser control, the wiki builder, and (2026-09-30,
  JARVIS-API section 108) the study helper and referee suggestions - each turned
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

- **The background job queue, and exactly what ticks it** (added 2026-10-15;
  the owner's decision of that day, "FINISH WHAT I ALREADY STARTED").
  `jarvis_jobs.py` is "Long Fuse" - the job list `features.json` ships as
  **Background jobs** and the Brain's Work pane reads at `GET /api/jobs`
  (cancel at `POST /api/jobs/cancel`). It is shipped whole (it is in this
  repository, in `backend/` and `jarvis-backend/`), and its rows live in
  `jobs.db` in the settings folder.

  **What ticks it, and how often.** `jarvis_initiative.Engine.start()` - the
  call jarvis_hud.py already makes on the owner's PC - registers
  `jarvis_jobs.tick()` on the initiative engine's own heartbeat. That
  heartbeat beats **once immediately** and then every
  **`[initiative] heartbeat_minutes`, 30 minutes as shipped**. So the queue
  rides the ONE heartbeat that exists: there is no thread, timer or
  `register_kind` of its own, and none may be added. A job due before the next
  beat waits for it. One switch is the consequence, and it is said here rather
  than left to be discovered: **`[initiative] enabled = false` stops the queue
  along with the checks.** `status()["checks"]` counts what the heartbeat
  runs: 1 (the events-pump watch) on a built engine, 2 once it is started,
  because the queue ticker is attached by `start()`.

  This is the fix for a real defect: until this landed `run_due()` - the
  function that runs every due job - had **zero production call sites**. The
  suites called it directly, which is the right way to test a function and
  exactly why the missing caller was invisible: every check passed and no
  queued job ever ran. `backend/test_jobs.py` tests the WIRING (the engine's
  beat runs a job, with nothing in the test calling `run_due()`), and it fails
  if the registration is removed. (The same missing-caller shape was found the
  same day in `jarvis_tasks.JobList.tick()`, which is a different feature and
  wants `jarvis_schedule.register_kind`, not this heartbeat. **Audited
  2026-10-18 and deliberately still unwired, with the reasons measured:** it is
  NOT a duplicate of `run_due()` - the two queues are drawn apart in
  `docs/AUDIT-JOB-LIST-2026-10-08.md` section 3 - but nothing in the program
  creates a job-list job (the plan card that would is switched off, and the HUD
  routes only list and steer), and there is no background step executor to hand
  `tick()`: it takes its executor and approver as arguments, and the only real
  one is built inside a chat turn. Attaching it to this heartbeat with a
  stand-in runner would move rows while no tool ran. `backend/test_tasks.py`
  pins the caller contract, proves nothing in the module starts itself, and
  proves two ticks - sequential or overlapping - cannot run a step twice; the
  module's own "WHO TICKS IT" docstring carries the same decision for the next
  reader.)

  **Which jobs may run while nobody is there, by name.** A call to
  `jarvis_jobs.create()` is an owner-present call, and the `caps` it writes on
  the row are frozen there for the job's whole life. So:

  * **runs to the end, unattended** - a job whose every step stays INSIDE that
    frozen set. That set is the owner's own yes, which is what "finish what I
    already started" means: a step at tier `ask` that was in the set at
    creation does not ask again, because the yes was already given. Reaching
    the end includes surviving a park and being claimed again on a later tick.
  * **parks and waits for him** - a step that needs an action the frozen set
    does NOT carry. `ctx.require()` records a one-shot `pending` grant, the
    job goes to `waiting_approval`, and it is claimed and asked again every
    `[jobs] approval_retry_seconds` (30 s) until a human answers; until then
    the step after the question is never reached. If nobody ever answers it
    waits for ever rather than proceeding.
  * **fails, and asks nobody** - a step on an action the framework sets to
    `never`. No grant can authorise it, so no card is raised for it at all.
  * **never starts** - a cancelled job (`cancel=0` guards every claim), and a
    job the owner never started, because the tick creates nothing.

  **Nothing here auto-approves.** The tick never creates a job, never widens a
  `caps` set and never decides a grant; only `decide_grant()` does, and that
  is a human's answer. A job body that raises fails that job and does not kill
  the tick, and the tick records what it did - counts and ids in the audit log,
  plus ONE receipt (`jarvis_receipts.record`, tool name `jobs.tick`) for a tick
  that ran something. The receipt carries no label, no param and no error text:
  those are the owner's words and the audit log is not private.

  **Said plainly, because it is a real gap:** there is no route that CREATES a
  job, and no route that answers a parked job's grant
  (`GET /api/jobs` lists, `POST /api/jobs/cancel` cancels, and nothing else).
  A job can therefore only be created by code that calls `create()`, and a
  parked job waits for ever until a route exists. Waiting is the safe
  direction - rule 4 is absolute - but it is not a finished feature, and the
  person who adds the route must pass the owner's own action through
  `create()`, which is what makes the frozen set his yes.

  **Two payload mismatches on `/api/initiative` were fixed the same day**, in
  the backend, and neither app changed: `jarvis_initiative.drain()` now mirrors
  `level`, `check` and `message` FLAT onto each row it hands out - which is
  where jarvis_hud.html:2591-2595 reads them, so a finding is drawn instead of
  served-and-invisible - while keeping the nested `finding` dict exactly as it
  was (`jarvis_hud.html` is vendored, so the shape is the backend's to fix);
  and the route now sends the `checks` count, which is what the phone's
  Findings note reads (BrainScreen.kt:2503-2509). The second half is
  `backend/initiative-payload.patch`, because `jarvis_hud.py` is NOT in
  `$SHIPPED` - it is one of the files the patch stack delivers, so an edit to
  the copy in this repository would never reach the owner's install.
  `backend/test_jobs.py` rehearses that patch against
  `jarvis-backend/jarvis_hud.py` (apply, reverse, byte-for-byte).
  `tools/check_parity.py` cannot see any of this: it scans the two apps' own
  source, so a payload key on an existing route is outside what it decides.

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
  PC, in memory): what went off, real "tell me when" matches, approval
  cards that timed out, facts saved automatically, cards waiting, unread
  email as the briefing reads it, and what is next (the last three added
  2026-09-27, ease-of-use audit row 12) - each its own labelled section,
  private, not kept. JARVIS-API §21.9 and §22.9.
- **The back-off for offers** (added 2026-09-25, `jarvis_backoff.py`): at
  most three offers waiting, none within two minutes of a chat message, and
  each "no" quiet for 1, then 7, then 30 days by a fingerprint of what is
  offered - and, since 2026-09-25 (a bug the creativity audit found), none
  in Quiet or Standby: the offer is kept for when Jarvis is Active again,
  never counted as a "no". Applied to the overnight-tidy card, the skill
  offer, and (added 2026-09-27) the second card's "would the bigger model
  help here?" suggestion - the one offer whose "yes" IS an existing
  approval card's "yes" (`second_card_combined_enable`), not a card of its
  own. Its counters never count a crisis turn (2026-09-27), and since
  2026-09-29 that includes a thumbs-down on a crisis-help answer: a bounded,
  in-memory list of crisis turn ids (ids only, never written anywhere) is
  what `note_correction` checks. It never approves or acts, and nothing the owner asks for consults
  it. JARVIS-API §22.6, §12.1.

- **Web search, with a choice of six providers** (added 2026-09-25, the
  owner's decisions of that day; DeepSeek added 2026-10-23 as an opt-in
  sixth). `jarvis_search.py` (shipped whole):
  SearXNG on this PC (the default, in Docker), DuckDuckGo (`ddgs`, its
  DuckDuckGo engine only), Exa and Tavily (free keys, no payment card),
  Brave (a key and a payment card, charged past its free monthly
  credit - removed and added back the same day by the owner; its "why"
  line says it can cost money) and DeepSeek (its own search service, a key,
  billed at $0.75 per 1,000 successful searches; a search that finds nothing
  is not billed), keys in Credential Manager, Whoogle left
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
  Nothing has reached a real SearXNG, DuckDuckGo, Exa, Tavily, Brave or
  DeepSeek yet: the
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

- **Looking at the screen ("Look at this", "Watch with me") - built
  2026-09-29, with limits.** Decided 2026-09-28 and designed
  (`docs/SCREEN-DESIGN.md`). Built: the rules (`jarvis_front.py`,
  `jarvis_screen.py`), the PC's Windows readers (`jarvis_screen_win.py`), the
  routes and the chat turn (`screen.patch`, `has_screen`, `read_screen`,
  JARVIS-API §62 and §96), the desktop (the Look at this key, the bar's Watch
  button and strip, the always-on-top badge, the tray row, the Never look at
  list) and the phone (the assistant gesture, "Watch this phone with me", the
  Security switch and Never look at list, the PC's sign with Stop on Home).
  **Still missing or unproven:** (1) the Windows readers and the badge's
  exclusion from capture have never run on Windows; (2) the phone's Kotlin
  compiles only in CI, and what Android really hands over (the screen's text
  on Android 14/15, GrapheneOS, Compose, Flutter and web content; whether a
  secure app draws black into screen sharing; Usage access's completeness;
  battery) is unmeasured; (3) **the picture path**: with one graphics card the
  everyday model is never shown a picture - a screen picture is read for its
  words and dropped - EXCEPT with the owner's slow **picture mode**
  (2026-09-29, `jarvis_screen_picture.py`, JARVIS-API §96.1): off by default,
  ON is one approval card, and a small model (MiniCPM-V 4.6) on the
  PROCESSOR, in its own copy of Ollama, also looks at the picture after
  secrets are blacked out and says what it saw as more outside text. Its tag,
  size and speed are unverified until the owner runs the measuring line;
  camera and Live pictures, and the two-card picture path, still wait for the
  12 GB card; (4) the phone's Watch cannot be asked from inside Jarvis, whose
  own screen is never looked at - ask by voice from another app; (5) no
  Recall-style always-on history, by the owner's decision.
- **Obsidian daily notes in every date format.** Only formats that can be
  written out exactly are followed (YYYY, YY, MM, M, DD, D, bracketed words,
  `/` folders). A format with month or weekday names, or week numbers, is
  refused with the reason, and so is a vault where the Periodic Notes plugin
  may be naming the daily note. Nothing guesses a file name.

- **Overnight memory tidying beyond two kinds of card.** Built on
  2026-09-28 (`jarvis_tidy.py`, section 5): "Still true?" and "Which is true
  now?" review cards only, off unless switched on. There is still no
  merging of repeats, no rewording and no summarising, and no fact is
  retired or changed without the owner's yes on that one fact. What the
  real local model gets right in "Which is true now?" is not measured yet
  (it needs the PC run).
- **A wake word measured on real speech.** "Hey Jarvis" is built (openWakeWord's
  model, on the phone and through the PC; turning it on is an approval card),
  but it has only been tested on synthesised voices: 44/44 heard, and the
  false alarms it produced were all dropped by the transcript check. Its
  false-alarm rate on real speech, TV, and battery use on the phone are not
  measured yet. The bake-off (2026-09-26, `jarvis_bakeoff.py`) is the tool
  that measures the first two on the owner's PC - the owner's own
  recordings and an hour of the room - for today's detector and its
  candidate side by side; until the owner runs it, they stay unmeasured.
- **A picture-capable local model, switched on.** The default model
  (`qwen3:8b`, via `jarvis-primary.Modelfile`) reads text only. A screenshot
  sent to it is not seen, so the quickbar asks Ollama first
  (`local_model_vision`) and offers to send the words without the picture.
  Since 2026-09-26 the PC itself reads the WORDS in such a picture
  (`jarvis_ocr.py`, Windows' own text recognition) and adds them as
  outside text (JARVIS-API section 36); then the quickbar sends the picture
  without asking. That is the words only - not what the picture shows.
  The fix is BUILT but off: the second card's "Pictures" switch sends a
  picture turn to `qwen2.5vl:7b` there (`jarvis_second_card.py`, below), and
  nothing changes until that card is installed and the switch approved. The
  desktop's check knows about it: `vision.rs` reads `GET /api/second-card`
  first, and says yes (naming that model) when the Pictures switch is on and
  its model is there; otherwise it asks Ollama about the everyday model, as
  before. Pictures never go to a cloud lane (`jarvis_router.choose()`
  keeps any turn with an image local, and the second card is on this PC).
- **A reasoning trace.** Brain → Now shows each tool Jarvis starts and
  finishes (the `step` event, from `jarvis_agent.py`, only when tools are
  switched on), but not the model's private reasoning: that text can quote
  email or files, and the event bus reaches a phone's lock screen (§6), so
  it is deliberately not published. **One exception, the owner's decision of
  2026-10-14:** a CLOUD lane's reply that carries no visible answer but does
  carry the model's working-out is shown - in the answer text only, under one
  line saying what it is (`jarvis_chatbot_api.CloudAnswer`; `docs/DECISIONS.md`,
  entry of 2026-10-14), because the alternative was the blank card the field
  test measured. It never reaches the event bus, and a cloud lane is never
  handed stored memory, email or files (rule 1), so nothing of the owner's can
  be in it.
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
- **Changing Windows settings from Jarvis** (Night light, dark mode, Focus
  Assist / Do not disturb). "PC help" (`jarvis_pc_help.py`, JARVIS-API §84)
  only reads. No safe way to change a Windows setting exists in this
  codebase yet (`jarvis_ui_control.py` clicks inside other programs'
  windows, which is not that), so none was built. When it is: one gate
  action per setting, tier `ask`, one card each, listed on "What asks
  first" and held by Lockdown.

**Present, but only on the owner's PC** (not missing, and not in this
repository either):

- `jarvis_undo` and `jarvis_hud`. Four of the six named here until
  2026-10-15 - `jarvis_jobs`, `jarvis_ledger`, `jarvis_content_risk` and
  `jarvis_watch` - are in this repository now, shipped whole in `backend/` and
  `jarvis-backend/`. These two are not: `jarvis_undo` is in the published base
  only, and `jarvis_hud.py` reaches the owner through the patch stack rather
  than through `$SHIPPED` (both halves are in `jarvis-backend/`, so what they
  serve can be read there). The owner checked their backend folder on
  2026-09-23 and all six files were there - checked by file presence only,
  so what is inside them, and the exact shape of the routes they serve, is
  unverified from here. The Brain's **Work** (`/api/jobs`, `/api/undo`),
  **Trust** (`/api/ledger`, `/api/content-risk`) and **Watch** (`/api/watch`)
  tabs read those routes; if a route does not answer, the pane says "Not on
  this backend." (`brain.js`, `unavailable()`).
- The rest of the backend (`jarvis_gate.py`, `jarvis_extract.py`,
  `jarvis_models`, `jarvis_arbiter`, ...) is in the same position (§9).
  One consequence, spelled out because it bit the "Activity" past-approvals
  list (JARVIS-API.md §41): `jarvis_gate.py`'s `history()` function is
  confirmed to exist and to never select `detail` or `prompt`
  (`backend/test_gate_egress.py` reads its source as text), but its exact
  column names beyond that - whether it sends `decided_by`, a `notice`
  object, `decided_at` - could not be read from this repository. Both apps'
  readers for it degrade to a plain, honest word (no device shown, "Not
  reported") rather than trust a guessed field name.
  `scripts/check-backend.ps1` is how to see what a folder holds.

---

## 11. Decisions already taken

Do not relitigate these without new evidence.

| | |
|---|---|
| Reachability | Tailscale or NordVPN Meshnet, properly. Never a public tunnel. |
| Face / appearance | Rendered locally on each device; the server is a sync channel only. |
| Voice | sherpa-onnx for STT (Parakeet TDT 0.6B v2), speaker verification, Kokoro TTS, Silero VAD. 0 GB VRAM. First audio is slow: from the owner finishing to Jarvis's first sound is roughly **2.5–4 s** today, with the voice on the processor. That is an estimate - the model's part (first word, first sentence) has not been measured; making the first sentence's sound alone takes about 1.3–1.6 s (measured in the dev container, not the owner's PC). The real figure is in `flow.timings` and `flow.summary` of `/api/voice/status` on the owner's PC (`backend/README.md`, "The voice flow"). Design a "thinking" state that survives several seconds of silence. Both apps make the next sentence's sound while the current one plays (one ahead), so there is no silence *between* sentences as long as making the next one takes less time than saying the current one (a simulation in the dev container: 3.5 s of mid-answer silence became 0 s; a short sentence followed by a long one can still leave a pause). Both apps also start speaking at the **first comma** of an answer once the phrase is long enough - the first piece only, the same rule on both (`jarvis-desktop/src/speech-pieces.js`, `SpeechText.kt`, one shared list of cases); in the dev container that moved the first sound from 2.04 s to 1.23 s, at the cost of one short pause after that first phrase. And a question **said** out loud is answered in a spoken style - a short first sentence, one to three sentences, no lists or markdown - by one line the PC adds for this PC's own model only (`jarvis_agent.SPOKEN_NOTE`, `JARVIS-API.md` section 17); typed questions are unchanged. The "One moment." clip's suggested 1000 ms (`JARVIS-API.md` section 17) would therefore fire on most spoken turns at today's speeds. **The wake word is the exception**: openWakeWord's `hey_jarvis` model on ONNX Runtime, on the phone and the PC alike - sherpa-onnx has no Android library on Maven Central/Google, and the TOML and `WAKE-WORD.md` had already chosen openWakeWord. Measured side by side in `backend/README.md`. **Custom voices** (2026-09-24, the owner's decision): ZipVoice via sherpa-onnx on the processor, and F5-TTS as an optional second-card "better voice" in its own process (on demand, stopped when idle and in standby); Kokoro stays the fallback. Adding a voice and switching to one are each a card; a voice that sounds like the owner's is refused (`backend/jarvis_voices.py`, `JARVIS-API.md` section 15). **Voice upgrades** (2026-09-26, the owner's choice, "each measured before it replaces anything"): a newer "hey Jarvis" detector (livekit-wakeword, trained once on the owner's PC) and Pocket TTS (a faster voice-copying engine on the processor) are built but **switched off**, with no switch in either app (the feasibility audit's "invisible upgrades get no switch"). `backend/jarvis_bakeoff.py` measures each against today's on the owner's PC and says "replace" or "keep what we have" by rules fixed beforehand (`backend/README.md`, "Voice upgrades: the bake-off"). A winner replaces the old part - never two detectors or three voice engines side by side. Every Pocket TTS file is hash-pinned and refused if it changed; the candidate detector is refused unless it matches the hash its training wrote down; the wake-word files the phone ships are pinned to the same hashes as the PC's (`test_voice_upgrades.py`). **How fast Jarvis speaks** (Slower / Normal / Faster) is in both apps: one number for every voice made on the PC, no card either way. **Which of Kokoro's own voices the built-in one uses** (2026-09-27, ease-of-use audit row 13) is the same shape, right next to it in both apps: no card either way, `[voice] tts_speaker_id` in the toml until a choice is made. **Kokoro v1.0, voices by name, "Hear it"** (2026-09-29, the owner's decision of 2026-09-28): the choice is saved as the voice's NAME (`bm_george`), not a number - a number means another voice in another pack - and the list is the voices the installed pack really has (`backend/jarvis_kokoro.py`: Kokoro v0.19's nine, or v1.0's eleven, best rated first, British ones asked for British English on v1.0). The old saved number is carried over once, unchanged. A **Hear it** button on every voice in both apps plays one fixed line in that voice and changes nothing (`POST /api/voice/voices/sample`, no card, never a recorded voice, `JARVIS-API.md` section 94). v1.0 is a 350 MB one-line install, checksum-pinned in one constant; nothing in the backend downloads it. **Ashby and Clara** (2026-09-29, the owner's decision): two blended Kokoro voices at the top of the built-in voice list in both apps - a butler-like British voice (70% George, 30% Michael, a little slower) and a warm woman's voice leaning British (60% Emma, 40% Heart) - made on the PC by one owner-run line (`py -3 jarvis_kokoro.py --make-blends`) into a checksum-pinned COPY of the pack's `voices.bin` beside it (sherpa-onnx refuses a voices file of any other size); the pack itself is never written, the copy is loaded only when it is exactly the pinned file, both get the same "not the owner's voice" check as a recorded voice (when chosen, heard and when the voice prints change), and no animal may use them (`JARVIS-API.md` section 94.7). **Voice follows the face** (2026-09-27, the owner's choice): with an animal face showing (red panda, pygmy owl, sea otter, monkey), the built-in voice becomes that animal's - one of the Kokoro voices already installed, its own pace and a small pitch rise (`jarvis_voices.FACE_VOICES`, not listened to yet). An on/off switch, off by default (the owner's 2026-09-28 decision; the sea otter no longer starts on Kokoro's "Sky" voice), under the built-in voice choice in both apps: no card either way (it changes how Jarvis sounds, never what it does), held on a stale link; a recorded custom voice still wins. **Each animal's voice** (2026-09-28, the owner's choice): under that switch in both apps, any of the built-in voices the pack offers (by name), a pitch from 3 steps deeper to 4 higher and a pace per animal, with Try it (one fixed line, changes nothing) and Reset - no card either way, held on a stale link; the mouth timing follows the chosen pitch and pace (`docs/LIPSYNC.md`). |
| Cloud / API keys | Allowed, **per use, with permission**. Jarvis works out what it genuinely needs the internet for, explains it, and asks. No standing grant. Enforced in `jarvis_router.choose()` since 2026-09-24 (the owner chose "ask each time"): without the owner's yes for that one question it answers locally and only names the cloud lane in `offer`; a yes never carries a private, tainted or picture turn out. Before that, the router escalated long questions by itself. **One exception, decided 2026-09-27**: a conversation with an AI chatbot website (`jarvis_chatbot.py`, section 4's "chatbot conversation (website)" row) follows up on its own within limits approved on one card; the core, its routes, both apps' screens and nine website adapters (Gemini first) are built; not yet tried against the real sites. The same exception covers the API adapters (section 4's "chatbot conversation (API, with a key)" row, `jarvis_chatbot_api.py`) and "a second AI on this PC" (`jarvis_chatbot_local.py`, which leaves nothing on the PC and so adds no row). |
| Structured output | Ollama's native `format: <schema>` — GBNF at the sampler. **Not** `outlines`, which cannot constrain Ollama. |
| Sandbox | Git worktrees, not Docker - for keeping the app builder's changes apart until a card approves them (`jarvis_app_workspace.py`, 2026-09-28; and since 2026-09-29 the merge card reaches it from Projects, `jarvis_apps.py`). A worktree is NOT a sandbox for running programs: `shell_exec` and any build command run with the owner's full permissions, which is why each one asks with the exact command (`docs/APP-BUILDER-DESIGN.md`). |
| Extraction | `ast-grep` — measured 54,490 → 1,088 bytes, 0 VRAM. |
| Bringing a Notion export into an Obsidian vault (2026-10-16, `/api/notion/preview` and `/api/notion/import`, `plugins/ready/notion-obsidian`) | **The backend is built; NEITHER app is wired yet, deliberately, in this pass.** The import needs two things chosen on the PC - the export file and the vault folder - and the phone has no view of the PC's folders at all (the same reason `/api/folders/add` is the PC alone, above); the desktop has the file picker that fits it and is not built here. So nothing reads the route from either app yet, `tools/check_parity.py` reports no drift, and the approval card is raised by the backend route itself. **Since 2026-10-21 both routes are PC only in the backend** (jarvis_owner_check.from_this_pc, the same rule /api/folders/import keeps; a phone gets 403 pc_only), and docs/JARVIS-API.md §152 documents the two routes, the hub note, 
ows_without_notes and the limits. The hub note and its .base are a PHASE-1 layout contract, and Ruling 8.4 (2026-10-21) settled the organizer's side: it moves only standalone pages, so a database's rows and its hub stay in the folder the .base filter names and that filter keeps resolving. |

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
   (`register_kind(plain_repeat=True)`; a new kind asks by default), and
   since 2026-09-28 Today cards (`jarvis_today.py`, JARVIS-API §82): the
   owner's own words shown back to them, reading nothing new.
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
