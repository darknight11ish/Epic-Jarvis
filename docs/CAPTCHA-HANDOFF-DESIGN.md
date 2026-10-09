# Handing a captcha to the owner's phone ("Solve it here") - design

**Read this with:** `docs/JARVIS-API.md` section 87.8 (the wire format, field
by field), `docs/CHATBOT-DRIVER-DESIGN.md` (the driver that pauses),
`docs/ARCHITECTURE.md` section 4 ("Not a way out: Solve it here") and section
8 (the clients). This note is the *why* and the *end-to-end flow*; 87.8 is the
*what the routes say*. Where the two differ, 87.8 is right - it is checked
against the code.

**Status: the backend half is already built on `main`** (commit `547efadf`,
"Solve it here, backend", 2026-09-28; `backend/jarvis_handoff.py`,
`backend/test_handoff.py`, the routes in `backend/jarvis_chatbot_routes.py`).
This pass did **not** rewrite it. It wrote this note, checked the built
backend against every rule below, and added the three promise tests
`test_handoff.py` was missing (§6). **Nothing here has run against a real
captcha, a real phone or a real Android build**: there is no captcha service,
no phone and no Android SDK in this checkout. That is said again, plainly, in
§9.

For the owner's decision of 2026-09-28 (`CLAUDE.md`, "A captcha can be handed
to the owner's phone"). Anything marked **unverified** has not been tried on a
real machine.

**THE OWNER'S DECISION OF 2026-10-08** (his own words: *"make this a setting for
both options with 1 as the default"*; `CLAUDE.md`, added the same day): how long
the hand-off stays on offer is no longer two constants chosen by hand. It is a
setting with **two choices, defaulting to the quick cut-off**:

1. **"Stop early" - THE DEFAULT.** About a minute (60 s) of no interaction, then
   the hand-off ends **and the PC says plainly that Jarvis is stuck on a puzzle
   in that window, naming it**, leaving the window for the owner to solve there.
2. **"Keep offering it".** The live picture stays on offer for the full
   15-minute ceiling, so the owner can pick their phone up late.

Keeping a window of the owner's on offer fifteen times longer is *more*
exposure, so choice 2 is **one approval card, decided on the PC with Windows
Hello**; choice 1 is immediate from either app. Section 5 has the whole shape;
both apps show it in the same words. This answers **Q1**; section 8 takes it out
of its open list below (Q5 and Q10 follow on 2026-10-09).

**THE OWNER'S DECISIONS OF 2026-10-09.** Three more questions were answered, and
section 8 records each one as answered rather than deleting it, so the list of
what is still open stays checkable against the list of what was asked:

1. **Q1 - how long the hand-off stays on offer. ANSWERED.** The owner chose **a
   setting with both options, and the quick cut-off as the default** - what
   section 5 already describes. It is **built and merged** (PR #134):
   `stop_early` = "Stop early" (about 60 s of no interaction, then the hand-off
   ends and the PC says which window is stuck) and `keep_offering` = "Keep
   offering it" (up to the 900 s ceiling).
2. **Q5 - whether starting a hand-off needs an approval card on the PC.
   ANSWERED: no card.** In the owner's own words, *"your tap is the yes"* - he
   tapped "Solve it here" on his own phone after Jarvis paused, and that tap is
   the decision. This confirms the no-card rule the flow was built with (§2 step
   5); it is not a change to it.
3. **Q10 - whether a customer-support window's page may ever be shown on the
   phone. ANSWERED: it may.** From three options the owner chose **"Send it -
   it's my phone, my mesh"**: a support window may be pictured to the phone like
   any other window. He did **not** choose "never send a support page", and did
   **not** choose "ask me on the PC first, each session". §3 carries the cost in
   its own "what is *not* protected" list; section 8 has the full statement.

**In one paragraph:** when the visible browser window Jarvis is driving stops
on a captcha, a sign-in page or an "unusual activity" page, Jarvis stops
there and tells the phone. The owner taps "Solve it here" and sees a live
picture of *that one window*, which travels only from the PC to the owner's
own phone over Tailscale or NordVPN Meshnet, is never written down anywhere, and
is thrown away with the answer. Their taps and typing go back to *that one
window*, and only while Jarvis is still paused on that page. Jarvis never
solves the captcha, never guesses where to tap, and never keeps a picture or
a typed character. Solving it in the window on the PC still works just as it
did, and is the fallback when a captcha refuses taps that came this way.

## 1. What the existing captcha code already does (read before building)

Three separate pieces already existed before this feature, and this feature
was built **on** them, not beside them:

1. **`jarvis_browser_engine.py`** (the headless browser, Obscura) already
   detects a captcha or a sign-in page and stops the run. `wants_a_person()`
   returns the word `"captcha"` (a challenge phrase, or a weaker one in the
   title and the first part of the text) or `"signin"` (a password box plus
   "sign in"/"log in" in the title or the address - or, for the email-first
   kind with no password box yet, the same words plus a box for a username or
   email), and the run stops with a plain sentence naming which and handing the
   job to the visible browser. It reads a page's title and its first part and
   nothing else; it has no window the owner can touch, so it can never be
   handed over this way - and it does not need to be: it hands over by telling
   the owner to ask again with the visible browser.
2. **`jarvis_chatbot_web.py`** (the visible browser every chatbot site and the
   support widget is built on) decides, on every step, whether the page wants
   a person. `_status_here()` returns `CB.Status("needs_owner", <code>)` with
   the code `"captcha"` (a captcha frame/selector), `"unusual"` (an "unusual
   traffic/activity" warning page, or Google's `/sorry/...` address) or
   `"login"` (a sign-in host, a sign-in address shape, a sign-in form or
   signed-out marker, or a sign-in phrase in a heading). The driver turns any
   `needs_owner` into a **pause** and keeps the window open. That pause is the
   only thing that can start a hand-off.
3. **`jarvis_browser_control.py`** already refuses to drive a captcha or a
   sign-in with the headless engine, and its help text already promises the
   owner that Jarvis "never types a password with it and never solves a
   captcha". It is not part of the hand-off: a browser-control *run* has no
   session the owner can take over, so a captcha there stops the run in words.

So: **detection was already there; what this feature adds is the hand-over.**
It does not add a second captcha detector, does not classify pages itself, and
does not touch the headless engine's rules.

## 2. The flow, end to end

Every step names the real call, so a reader can check this against the code.

1. **Detect.** The visible window's adapter sees the page
   (`jarvis_chatbot_web._status_here`) and returns `needs_owner` with
   `captcha`, `login` or `unusual`. The driver pauses the conversation or the
   support chat with that code. The browser window stays open and untouched.
2. **Offer.** `jarvis_handoff.offer()` (read by both apps on
   `GET /api/chatbot/status`, key `handoff`) says whether a page is waiting,
   for which site, and why - in words, never a picture and never a word from
   the page. It publishes one `handoff` event on the bus, once per
   target+reason, so the phone can raise an alert without polling blind.
3. **Pause Jarvis.** Nothing else happens on its own. Jarvis sends nothing
   more to that site, reads nothing from it, and does not retry the step.
   On the PC the Brain shows the same alert and points at the window.
4. **Alert the phone.** The phone's own notification channel (kept on the
   phone, `setLocalOnly(true)`) says "{site} needs you"; with App lock or
   "Hide memory lists and chat history" on, only "A website Jarvis is using
   needs you", and the lock screen never says more. Tapping "Solve it here"
   opens the screen.
5. **Open the hand-off.** `POST /api/chatbot/handoff/start {"kind","id"}`
   (`jarvis_handoff.start`). **No approval card**: nothing leaves the owner's
   own devices and nothing is done but what the owner does themselves. The
   hosts the window may show from now on are frozen: the site's own hosts, its
   sign-in hosts, and the host it is on at this moment. One hand-off at a time;
   a new one ends the old. It refuses with 409 and a plain sentence when
   nothing is waiting.
6. **Live view.** `GET /api/chatbot/handoff/frame?h=` (`frame()`), at most
   twice a second. It is Playwright's own `page.screenshot(type="jpeg",
   quality=60, scale="css")` of **that one page** - never the desktop, never
   another window, never another tab the site opened - returned base64 in the
   answer with its pixel size and a sequence number. Is it a stream or a still
   refreshed at a rate? **A still, refreshed on demand** (the phone asks about
   once a second while the screen is in front). See owner question Q2.
7. **Taps and keys.** `POST /api/chatbot/handoff/input {"h","type",...}`
   (`send_input()`), one input per call: `tap` (x,y as fractions of the last
   picture), `text` (1-200 characters, no control characters), `key` (one of
   ten named keys - Enter, Backspace, Delete, Tab, Escape, Space, the four
   arrows), or `scroll` (capped at 1500 page pixels). `_relay()` passes exactly
   that to `page.mouse.click` / `page.keyboard.type` / `page.keyboard.press` /
   `page.mouse.wheel`. Jarvis adds nothing, clicks nothing by itself, and never
   reads what the owner types.
8. **Still paused? Check again.** *Every* picture and *every* input first
   re-checks that the session is still paused at the same code with the same
   window, and - on the window's own thread, in `_on_window()` - that the page
   is alive and showing one of the frozen hosts, and checks the host **again
   after** an input (an input can drive the page elsewhere). Any failure ends
   the hand-off immediately with a reason and a sentence.
9. **Resume.** The owner presses the driver's **Resume** (which still asks
   with its card, as always) or "End" on the hand-off screen. Ending never
   asks: it only makes Jarvis do less. `POST /api/chatbot/handoff/end {"h"}`,
   or any of the enders in §5. The conversation carries on from where it
   paused; the window is left exactly where the owner left it.

## 3. The security shape: what crosses, and what is never kept

**What crosses the boundary (PC -> the owner's own phone, and back).**

- Only **one JPEG of one browser page**, PC to phone, on request.
- Only the **owner's own input** - their tap coordinates, the characters they
  typed, the key they pressed, their scroll - phone to PC.
- Only **fixed sentences and counts**: the site's name, the reason code, and
  the reasons a hand-off ended. No page text, no page title, no address bar,
  never a word the site said.

**What never crosses.** Nothing else on the PC: not the desktop, not other
windows or tabs, not the clipboard, not memory, not email, not files, not
credentials. Rule 1 holds because the only destination is the owner's own
paired phone over their private mesh (Tailscale or NordVPN Meshnet); **no
public tunnel is opened or reachable** (rule 2), no proxy exists in this path,
and no spoofing code is added to the visible browser. Jarvis itself never
solves, skips, anticipates or clicks a captcha, and never claims to be human.

**Where the "never saved" promise is kept, in the code.** Three places, and a
test for each (§6):

- **No file, no temp file, no cache.** `frame()` returns the JPEG bytes in the
  HTTP answer and keeps no path, no temp file and no on-disk cache anywhere;
  the module contains no file write or open call at all (checked by reading its
  own source), and the picture exists as bytes for the length of the answer and
  is then gone. (The only thing this module records anywhere is an audit line,
  and that carries no picture - see the next point.)
- **No log line, no audit of content.** `_audit()` writes only counts and the
  *name* of a special key: `start` (kind, reason, host count), `input` (type,
  and `key` for a named key), `end` (why, frames, inputs, seconds). Typed text
  never reaches it - `test_handoff.py` types "hunter two" and asserts the word
  is in no audit record. This pass added the matching test for the picture: no
  frame's base64, and no hand-off token, appears in any audit line.
- **No chat history, no memory, no learner, no event.** The picture is not a
  chat message, is never learned from, is never put on the event bus, and is
  never handed to a model. An input's contents are not kept after the call
  either.

**The pairing token** is never logged by this path (rule 3, and the standing
rule "never log the token"): the hand-off routes are answered by the chatbot
route installer, which checks the token and passes the request on; the token
value is never copied into a body, an audit line, an event or a sentence this
module writes. A test asserts it (§6).

**What is *not* protected, said plainly.** The typed characters (a password,
a one-time code) travel live over the owner's mesh link and sit in the PC's
memory for that one input; they are never logged or kept, but they are not
encrypted end-to-end beyond what Tailscale/Meshnet themselves provide. A
captcha may recognise a tap that arrived this way and refuse it - the apps
say so in words (`WORDS["may_refuse"]`). A site that opens a **new window or
tab** for its sign-in is finished on the PC: only the first window is passed
on. Anyone who can already drive the owner's PC can take a picture of that
window directly; this feature does not defend against a program already on the
PC (that is `ARCHITECTURE.md` section 3's known limit, not a new one here).
**A customer-support window is pictured to the phone like any other window**
(the owner's decision of 2026-10-09, Q10 below, in his own words: *"Send it -
it's my phone, my mesh"*). That is real and is not softened: a support session
can show **order numbers, addresses and account details**, and this decision
means those can appear on the phone whenever the hand-off is offered on that
window. It is survivable only because every protection above is unchanged and
still holds - the picture is **never saved**, it goes **only to the owner's own
paired phone over Tailscale/Meshnet**, it is shown **only while the memory
lists are not hidden** (the PC blanks that route in that state), cards are
still decided by tapping, and **solving it on the PC still works**.

## 4. The rate and size limits

| Thing | Limit | Where |
|---|---|---|
| Pictures | at most **2 a second**; a faster ask gets 429 with `retry_ms` | `FRAMES_PER_S = 2.0` |
| Picture size | a JPEG at quality 60, in CSS (page) pixels - a page-sized picture, not a screen-sized one; no resize cap beyond the page itself | `JPEG_QUALITY = 60` |
| One typed run | at most **200 characters**, and no control characters (use the named keys) | `TEXT_MOST = 200` |
| Inputs | at most **30 in any 3 seconds**, else 429 "Slow down a little." | `INPUTS_MOST`, `INPUT_WINDOW_S` |
| One scroll | at most **1500 page pixels** either way | `SCROLL_MOST` |
| Keys | ten named keys only; no function keys, no `Ctrl`/`Alt` shortcuts, nothing that reaches the browser's own chrome | `KEYS` |
| Hosts | fixed at `start()`: the site's own, its sign-in hosts, the host showing then. Anything else ends it | `hosts` |
| Hand-offs | one at a time, globally - starting a new one **ends the old** | `_CURRENT` |

## 5. How the owner stops it, and what times out

Every ender writes one sentence into `jarvis_handoff.ENDED`, which both apps
show; the routes answer **410** with `ended` and that sentence afterwards.

| Enders | `ended` | Meaning |
|---|---|---|
| The owner's **End** button, or a repeated End (never refused, never a card) | `owner` | "You ended it." |
| **Resume** on the conversation, or the session running again | `resumed` | "The page is no longer waiting for you..." |
| **Stop** on the conversation | `stopped` | "The conversation stopped." |
| The window **going to another site** | `left` | "...Nothing more is passed on - look at the window on the PC." |
| The window **closing** | `closed` | "The browser window closed." |
| **Nobody looking**: no picture asked for the owner's idle time | `idle` | "Nobody was looking at the picture for a while..." |
| **However it went**: 15 minutes | `time` | "The hand-off ended after 15 minutes." |
| **Stop everything** (the global hotkey) | `stop_all` | "Stop everything ended it." |
| A **new hand-off** starting | `replaced` | "A new hand-off started." |

Timeout is therefore two clocks, both fail-closed: **nobody looking** and the
**15-minute ceiling**. Both are refreshed by pictures *and* by inputs, so an
owner typing slowly on a sign-in form is not cut off mid-way. Nothing about
ending a hand-off asks for approval: it only makes Jarvis do less, so it is
never held on a stale link (rule 4 holds it the other way - input *is* held when
the link is stale, ending never is).

**How long "nobody looking" is, is now the OWNER'S SETTING** (his decision of
2026-10-08, in his own words: *"make this a setting for both options with 1 as
the default"*; `backend/jarvis_handoff_mode.py`). This answers Q1 below. The
ceiling is **15 minutes for both choices**: the setting moves the idle clock,
not the ceiling, which is exactly what the owner was promised.

| The choice | Idle clock | What happens | Gated? |
|---|---|---|---|
| **"Stop early"** (THE DEFAULT, and the stricter one) | **60 s** | The hand-off ends (`idle`) **and the PC says plainly which window Jarvis is stuck on** (`STUCK`: "{site} is waiting on this PC"), naming it, leaving the window for the owner to solve there. The window on the PC is the fallback this feature already promises, so the owner is never left without a way through | **No** - it is the default, it is the narrower choice, and going back to it is immediate from either app, never held on a stale link |
| **"Keep offering it"** | the full **900 s** | The live picture stays on offer for the whole ceiling, so the owner can pick their phone up late | **ONE approval card** (`handoff_keep_offering`, tier "ask"), **and on `jarvis_owner_check.PC_ONLY_ACTIONS`**: decided on the PC, with Windows Hello, and refused from any other device |

**Why the longer offer is gated, and the shorter one is not** (the repo's own
rule for a setting that increases exposure - `ARCHITECTURE.md` section 3, one
permission model, one place approval cards come from; the same shape as
`jarvis_voice`'s `live_end` and `jarvis_watch_notify.py`): a live picture of one
of the owner's own browser windows - which may show their own account details,
or a support chat's order page - staying on offer for fifteen minutes instead of
one is *more* exposure, never less. Going back to "Stop early" narrows what may
be seen, so it needs no card.

**Fail closed.** No settings file at all is the owner's default ("Stop early").
A file that is unreadable, is not JSON, or holds anything but the two names
reads as "Stop early" too, with a plain `why` - a damaged file must never quietly
leave a window on offer for fifteen minutes. Nothing about it is stored except
one word and the time it changed.

**Where both apps show it** (`docs/JARVIS-API.md` section 87.8; one id,
`settings.handoff`): desktop Settings, "When the phone does not answer"
(`handoff-mode.js`, `handoff-mode-rules.js`, `src-tauri/src/handoff.rs`
`handoff_mode`); the phone's Settings, the same row (`net/HandoffMode.kt`,
`ui/screens/HandoffModePlate.kt`, `JarvisRuntime.setHandoffMode`). Both read the
same words from the PC, and `tools/gen_handoff_cases.py` carries them into both
apps' contract file so neither can drift.

**The route is a sibling, never one of the hand-off's own.**
`GET`/`POST /api/chatbot/handoff_mode` carries one word and no picture, no page
and no tap. It is deliberately **not** under `/api/chatbot/handoff/`: the
desktop must never name one of those routes (`jarvis-desktop/tests/handoff.mjs`
checks it), because it has the real window and pictures nothing.

## 6. The tests, and what each one proves

`backend/test_handoff.py` (104 checks pass here, including the three below;
the real-browser half is skipped without Playwright):

- **In code (AST):** one `screenshot` call and it is in `frame()`; the owner's
  `click`/`type`/`press`/`wheel` are reached only in `_relay()`; `_on_window`
  is called only from `frame()` and `send_input()`; `_mine()` (the
  still-paused check) comes **before** the window is touched in both; no
  `goto`/`evaluate`/`fill`/`launch` anywhere; no proxy, captcha-solving or
  spoofing word from the chatbot sites' own FORBIDDEN list; no other chatbot
  file pictures a page or moves a mouse.
- **In behaviour:** nothing is offered, pictured or passed on while a session
  is running, paused for another reason, part of a comparison, or has no
  window; refused starts touch no page; a tap before any picture is refused;
  a tap outside the picture, a 201-character text, a control character, `F5`,
  `Control+L`, an unknown type and another hand-off's id are all refused - and
  the page saw nothing; every ender above ends it and the page sees nothing
  after.
- **The three promise tests added this pass** (they were the gap):
  1. **The picture is not written to disk.** During a frame and an input, every
     write, open, move, copy or delete that could reach a file is trapped
     (`Path.write_bytes`, `os.replace`, `shutil.copy`, `tempfile`, and the
     builtin `open` itself); the check fails if any is attempted. This trap was
     itself probed: with the trap armed, a save added to `frame()` is caught -
     and a first version of the trap that only wrapped `Path` let a bare
     `open(path, "wb")` through, which is why the builtin is wrapped too. A
     second code-level check reads the module's own source (docstrings and
     comments removed) for a list of write and open names, so a save that the
     trap somehow cannot see still has to get past a reader.
  2. **The picture and the token are never logged.** A frame is taken with a
     known token in play, and the audit lines are searched for the picture's
     own base64 and for the token: neither may appear. Fails if a frame's bytes
     are put in the audit detail, or the token is.
  3. **The routes are gated like every other route.** The chatbot routes are
     installed into a stand-in handler and the hand-off frame/input/end routes
     are asked for with a bad origin (403) and with a bad or missing token
     (401) before any hand-off exists. Fails if a hand-off route is added to
     the answered list without going through the installer's own `_allowed()`.

Run it with `python backend\test_handoff.py`, or through
`python backend\run_suites.py` with everything else.

**The setting's own suite** (`backend/test_handoff_mode.py`, added 2026-10-08
with the owner's decision). Each check fails without its fix:

- **The default is the quick cut-off, and the two values are what the owner was
  promised**: no settings file reads as "Stop early"; the two names are exactly
  `stop_early` and `keep_offering`; the default's idle clock is 60 s; both
  choices share the 900 s ceiling; "Keep offering it" makes the idle clock the
  ceiling itself; a file that is unreadable, is not JSON, or holds anything but
  the two names reads as "Stop early" with a plain `why`.
- **Under the default, an idle hand-off ends at about a minute AND the PC
  message names the stuck window**: a real pause, a real start, 59 s of nobody
  looking - still on offer; a minute - it ends `idle`, and `offer()` carries
  `STUCK`'s own two sentences with the site's name in them ("Gemini is waiting
  on this PC"), while a hand-off that ended another way carries none.
- **Under the patient value, it stays on offer past a minute and up to the
  ceiling**: 61 s - still offering; six minutes - still offering, and a picture
  still comes back; then every 30 s until the 900 s ceiling ends it `time`.
- **The gates and the words**: "Keep offering it" waits for one card under
  `handoff_keep_offering`, applies only on a person's `approved` at tier "ask",
  and is refused outright at any other tier; "Stop early" is immediate, never a
  card, and withdraws a waiting card; a bad value is refused; the idempotent
  cases and the OFF-during-an-approved-card race (the one
  `jarvis_learning_switch.py` was fixed for) are covered; the action is on
  `jarvis_owner_check.PC_ONLY_ACTIONS`, has a plain card title, and the shipped
  tier table says "ask"; the route rides the chatbot routes' own `install()` and
  is never one of the hand-off's picture or input routes; and this module's own
  audit lines carry an outcome word - no picture, no page, no token.

Also checked, in both apps' own suites (`jarvis-desktop/tests/handoff.mjs`,
`jarvis-desktop/tests/handoff-mode.mjs`, the phone's `HandoffTest.kt`): the two
values, the default and **every sentence** are the PC's own, held to the
generated contract file word for word; and the desktop still names none of the
hand-off's own routes.

## 7. What the phone will need (the next step - not built in this pass)

The phone calls these routes and nothing else; it never runs a browser, never
sees another window, and holds no state of its own about what is on the PC.

1. **A notification channel of its own**, kept on the phone
   (`setLocalOnly(true)`), raised from the `handoff` event: "{site} needs
   you", or "A website Jarvis is using needs you" while App lock or "Hide
   memory lists and chat history" is on. The lock screen never says the site.
2. **A screen behind App lock** showing the picture, with the fixed sentences
   from `WORDS` (`tools/gen_handoff_cases.py` writes both apps'
   `handoff-cases.json` from the real module, so the words cannot drift).
3. **The picture loop**: ask `frame` about once a second, and **only while
   that screen is in front and the app is unlocked** (not composed behind the
   lock screen), hold it in memory for the screen only, drop it when the
   screen goes, and block screenshots of Jarvis while it shows. The picture is
   never put in saved state (`onSaveInstanceState`), never cached to disk,
   never logged, and never sent anywhere else.
4. **Taps as fractions** of the picture; a tap on the margin goes nowhere.
   **Typing masked on a sign-in page**, held in memory for the input only,
   never in the app's saved state. The ten named keys offered as buttons.
5. **Stale-link handling**: hold `input` while the link is stale, with
   `WORDS["held_stale"]`; **End and "Solve it on the PC instead" are never
   held** (rule 4).
6. **The plain warning** (`WORDS["may_refuse"]`) on the screen, not behind a
   link: some captchas refuse taps passed on this way, and the PC window is
   the fallback.
7. **The 410 handling**: when a route answers 410 with `ended`, show the
   sentence and close the screen; do not retry the picture.

The desktop half is deliberately **one-sided**: the window is right there, so
the Brain shows the same alert and points at it, and the desktop never calls
the picture or input routes (`tests/handoff.mjs` checks). Note for the next
pass: **both of these already exist on `main`** (`jarvis-client`'s
`net/Handoff.kt`, `ui/screens/HandoffScreen.kt`, `service/HandoffNotifier.kt`;
`jarvis-desktop/src/handoff.js`). They have never run on a real phone or a
real captcha (§9). This pass changed nothing about them.

## 8. Questions only the owner can answer

This section used to say "listed, not answered". Three of the ten have since
been answered by the owner and are kept below in §8.1, each **in the words it
was asked in**, so a narrower or easier question was never quietly put in its
place. The rest, in §8.2, are still **listed, not answered**: each is a
decision, and the design deliberately does not guess.

**Q1 was answered on 2026-10-08, and Q5 and Q10 on 2026-10-09** - see the
block at the top of this note, and section 5: *"make this a setting for both
options with 1 as the default"*, *"your tap is the yes"*, and *"Send it - it's
my phone, my mesh"*.

### 8.1 Answered, kept here so the asking stays checkable

**Q1 was answered on 2026-10-08, Q5 and Q10 on 2026-10-09** (the block at the
top of this note, and section 5):

- **Q1 - How long before it gives up?** **Answered by the owner on
  2026-10-08, and confirmed 2026-10-09** (see section 5): it is now a setting
  with two choices - "Stop early" (about a minute, THE DEFAULT, which ends the
  hand-off and makes the PC name the stuck window) and "Keep offering it" (the
  full 15-minute ceiling, one approval card on the PC with Windows Hello). The
  ceiling is 15 minutes for both. He chose **a setting with both options, and
  the quick cut-off as the default**, and it is **built and merged** (PR #134;
  `stop_early`, `keep_offering`). What is left of this question is a
  *measurement*, not a decision: nobody has watched a real captcha hand-off
  run, so the two numbers are still chosen rather than measured (section 9).
- **Q5 - Does "Solve it here" need a card?** Today: **no card**, on the
  grounds that nothing leaves the owner's own devices and nothing is done but
  what the owner does by hand (this matches `ARCHITECTURE.md` section 4's "Not
  a way out"). Keep it card-free, or put one card on the *first* hand-off per
  session so the owner always consciously starts one?
  **Answered by the owner on 2026-10-09: it stays card-free.** In his own
  words, *"your tap is the yes"* - he tapped "Solve it here" on his own phone
  after Jarvis paused, and that tap is the only yes this needs. No card is put
  on the first hand-off of a session either; that option was not chosen. This
  confirms what is built (§2 step 5) rather than changing it. What it commits
  to: a hand-off still only ever starts because the owner tapped, on his own
  paired phone, and the card-free start still does nothing but what he does by
  hand. What it costs: nothing here gates the *decision* to open a live picture
  of one of his own windows, so the protection is App lock and the frozen hosts
  (§2 steps 5-6), not a card. How long that picture stays on offer is still the
  owner's own setting (Q1, section 5), and the longer choice, "Keep offering
  it", still carries its own approval card.
- **Q10 - May a support chat's hand-off ever show the company's real page to
  the phone?** Today: yes, it is the same one-window picture, and the widget's
  page may contain the owner's own order details. Is that acceptable on a
  phone screen (behind App lock), or should support-chat hand-offs be
  PC-only?
  **Answered by the owner on 2026-10-09: yes, it may.** From three options he
  chose **"Send it - it's my phone, my mesh"**: a support window may be
  pictured to the phone like any other window, with no separate rule for
  support. He did **not** choose "never send a support page" (support
  hand-offs PC-only) and did **not** choose "ask me on the PC first, each
  session". What it commits to: a support chat's paused page - the company's
  real page, not a copy - is offered to the phone on exactly the same terms as
  every other window: one JPEG, only over Tailscale/Meshnet, only while the
  hand-off is on offer, thrown away with the answer.
  **What it costs, plainly.** A support session can show **order numbers,
  addresses and account details**, and this decision means those can appear on
  the phone whenever the hand-off is offered on that window. That is real, and
  the note does not soften it; it is survivable only because the protections
  that were already there are unchanged and still hold: the picture is
  **never saved** (no file, no temp file, no cache, no log, no chat, no memory
  - §3 and §6's three promise tests), it goes **only to the owner's own paired
  phone over Tailscale/Meshnet** and never over a public tunnel, it is shown
  **only while the memory lists are not hidden** (with App lock or "Hide memory
  lists and chat history" on, the PC blanks that route and the lock screen
  never names the site - §2 step 4), cards are still decided by **tapping**,
  and **solving it on the PC still works** - the window itself is the fallback
  and there is no rule that support must go through the phone. §3's "what is
  *not* protected" list carries the same line.

### 8.2 Still open - listed, not answered

Each is a decision, and the design deliberately does not guess. (Q2 and Q5 were
the ones most likely to change what is already built; Q5 is answered above, and
Q2 is still open.) **Seven questions remain open**, each left in the words it
was asked in:

- **Q2 - A stream, or a still refreshed?** Today: a still, asked for about
  once a second, because it is simple, cheap, and nothing is sent when nobody
  is looking. A captcha whose picture itself rotates or animates (an audio
  challenge, a moving slider) may want a faster rate or a real stream. Which
  does the owner want - and if a stream, what stops it from being a live feed
  of a window the owner forgot about?
- **Q3 - What if the phone never answers?** Today: the conversation stays
  paused, the window stays open, and the offer stays on `GET
  /api/chatbot/status` until the 15 minutes pass or the owner deals with it on
  the PC. Should Jarvis instead nudge again after a while, ring the phone,
  give up after N minutes and stop the conversation, or stay paused
  indefinitely until the owner acts? (Stopping on a timer risks losing a
  half-typed sign-in; staying forever holds a browser window open.)
- **Q4 - Is the window brought to the front?** Today: **no**. The hand-off
  never calls focus, raise or activate; the window stays wherever the owner
  left it, which is why the PC alert says "on this PC" and points at it. Bring
  it to the front when the phone taps "Solve it here", or when the hand-off
  starts? (Fronting a browser window takes focus away from whatever the owner
  is doing, and this project has been bitten by focus-stealing before.)
- **Q6 - How much of the picture may the phone keep while the screen is
  open?** Today: the latest frame only, in memory, dropped with the screen -
  so a brief network stall shows `WORDS["waiting"]` rather than a stale
  picture. Keep one previous frame to smooth a bad link (and say on screen that
  it is a moment old), or never show anything but the latest?
- **Q7 - May the owner also type a whole password at once, or must it go
  character by character?** Today: up to 200 characters in one input, which
  suits a password manager paste on the phone. If the owner would rather the
  app never hold more than one character at a time, that is a different
  screen and a different limit - and it would make long passwords painful.
- **Q8 - What happens to the alert after the hand-off ends?** Today: the offer
  disappears from `status` and `end` is reported; the phone's notification is
  the phone's own to clear. Should the notification clear itself the moment
  the hand-off ends (`closed`, `time`, `resumed`), or stay until the owner
  dismisses it so they know something happened while they were away?
- **Q9 - Is the PC's copy of the alert enough?** Today the PC shows a line on
  the Brain and points at the window; it does not ring, flash or front the
  window. If the owner is not looking at the PC when a captcha appears, is
  that enough, or should the PC also make a sound / raise the window (see Q4)?

## 9. What is NOT verified, and the risk

- **No real captcha has ever been met.** Every check in `test_handoff.py` runs
  against a stand-in window that records calls, plus (when Playwright is
  present) a fake page in a real Chromium. Whether a real reCAPTCHA/hCaptcha
  frame accepts a passed-on tap is **unknown**, and the project says so in the
  app's own words. It may simply refuse.
- **No phone, no Android SDK, no emulator here.** The phone half is on `main`
  but has never been built or run against this backend from this checkout. Its
  behaviour - notification, App lock, the picture loop, masked typing, and the
  new Settings row for how long the offer lasts - is unverified **in this pass
  and, as far as this note can tell, in general**. The 2026-10-08 change is the
  first time this feature's phone half has been edited since it was built, so
  **CI's Gradle build is its first compile.**
- **No end-to-end run.** PC -> mesh -> phone -> tap -> PC has never been
  exercised here, and cannot be: there is no second device, no mesh link and
  no captcha in this environment.
- **The picture quality is unmeasured.** JPEG quality 60 at a page's own size
  may be too blurry to read a captcha's grid on a phone, or larger than the
  link wants. `FRAMES_PER_S = 2`, `JPEG_QUALITY = 60` and **both of the
  setting's numbers** (`STOP_AFTER_S = 60`, `CEILING_S = 900`) are chosen
  numbers, not measured ones: nobody has watched a real hand-off run, so the
  owner's setting chooses between two guesses rather than between two measured
  values (the rest of Q1 in section 8).
- **The setting's own new surface is unverified in the same way as the rest of
  the phone half.** The phone's Settings row, its read of
  `GET /api/chatbot/handoff_mode` and its "Use this" have never been built or
  run: there is no Android SDK here (below). The desktop's card has been checked
  by its own offline suites (`tests/handoff-mode.mjs`), not by opening the page
  in a browser.
- **The risk, plainly.** (a) A captcha may reject passed-on input, which is
  why the PC window is kept as the fallback and the app says so. (b) The
  picture shows a real page that may contain the owner's own account details
  (a support chat's order page), so it must stay behind App lock and never on
  a lock screen. **This is now the owner's decision, not an assumption**
  (2026-10-09, Q10): a support window's page may be pictured to the phone, and
  he accepted that **order numbers, addresses and account details** can appear
  there whenever the hand-off is offered on that window - §3 and Q10 carry the
  cost and the protections that make it survivable. (c) A typed password lives
  in the PC's memory for one input
  and on the mesh link; it is never logged, which is a promise kept in code
  and tested, but it is not extra-encrypted by this feature. (d) This feature
  does **not** narrow `ARCHITECTURE.md` section 3's known gap: a program
  already running on the PC can call these routes with the token like any
  other. (e) The feature adds a new way for the owner's own screen content to
  reach their phone, which is why every limit in §4 exists.
