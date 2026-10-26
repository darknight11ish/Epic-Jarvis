# Design: the owner-secret hand-off, and the 15-minute secret-page read taint

**Status: the rule engine is built and tested; the wiring is not built.** Nothing
imports `backend/jarvis_secret_handoff.py` yet. That is deliberate - same shape as the
price radar's F1 slice: the module (+ byte-identical `jarvis-backend/` twin) and its
suite land first, so the safety rules can be reviewed and tested without a half-wired
UI, and a backend without the module behaves exactly as before.

**Why this exists.** `jarvis_ui_control.py` refuses a password-masked control outright
(`code` `password_control`), and that refusal is right. It also means Jarvis cannot log
in anywhere for the owner. The owner-secret hand-off keeps the refusal for the MODEL
while adding the one flow that is safe: the owner types the secret into a card the HOST
draws, the host types it into the control the owner approved, and the value never enters
model context, a tool result, a database, a log line, the clipboard, or any file.

**Where the ideas come from.** `makecindy/cindy` (Apache-2.0), evaluated 2026-10-26:
`secretTaint.ts` and its input-hand-off product rules. No source line was copied - the
module is written against this project's own rules (one card, no auto-approval, outside
text, no CAPTCHA solving). The architect's ruling (the `for_deepseek_*rulings*` document
of 2026-10-26) supplied the three product answers; the owner reversed the build order so
the taint ships INSIDE the hand-off, because cindy's taint is triggered only by the
hand-off and stands inert without one.

## 1. The three questions, answered

### 1.1 Where the secret value is held

Nowhere. There is no store. The value exists in one function call:

1. the owner types it into the HUD card (host page, not model context);
2. `POST` to a host-only route carries it to the backend process (loopback; the route
   must suppress body logging and the request is never persisted);
3. `execute_owner_fill()` holds it as a parameter only, types it through an injected
   function, and returns a receipt that names the verified target and the taint
   duration - never the value.

No disk, no SQLite, no clipboard, no log, no model, no tool result. The module imports
no storage or logging library at all, and its suite proves that by reading its own AST.

### 1.2 What the card must show

Two clearly separated boxes, because the model's text is untrusted and the target is not:

| box | source | contents |
|---|---|---|
| host-verified target | read by the wiring layer from the OS (UIA) or the browser (`page.url`) at the moment the card is raised | page: exact scheme + host + port + path, with the registrable domain emphasised; a red `UNENCRYPTED HTTP` badge when the scheme is not https. window: executable name, PID, window title, control type and `IsPassword=True` |
| agent-claimed purpose | the tool-call argument, cleaned and capped at 120 chars | shown inside a muted, labelled box: `Jarvis's note (unverified): "..."` |

The owner types into a `type=password`, `autocomplete=off` input, then presses one
button - `[Type into <verified target>]` - or `[Cancel]`.

**Who measures the target.** In this slice the snapshot is *supplied by the caller* and the
engine compares it; the engine cannot itself read the OS. So the verification is exactly as
strong as the wiring that builds that snapshot - which is why the wiring slice in section 4
is not optional, and why this record says "compares" rather than "the host verifies".

### 1.3 What voids the step, and how the taint works

**Voided with ZERO characters typed** when, at submit time, the host re-reads the target
and finds: the page address or window changed; the kind changed; the focused control is
no longer the same one; the control is no longer password-masked; the card is older than
180 seconds; the card is answered from another machine (a caller that does not assert it is
this PC is refused, because `from_this_pc` has no safe default); the value is empty or only
whitespace or over 4096 characters; or the card was already used or cancelled.

**The taint.** `mark_secret_entered(target_key)` runs BEFORE the first character is
typed, so a typing failure halfway through still leaves the target read-locked. The
registry is in memory only: `SECRET_TAINT_TTL_S = 900` (15 minutes), at most
`SECRET_TAINT_MAX_KEYS = 32` targets, oldest evicted first, monotonic clock so a wall-clock
adjustment cannot shorten or extend it. Keys are canonicalised page addresses (scheme and
host lower-cased, a default `:80`/`:443` dropped, `.`/`..` path segments resolved, a
trailing slash dropped, query string, fragment and any `user:pass@` userinfo stripped) or
`pid:hwnd:window class`; a secret value is never part of a key. While a key is tainted, the wiring layer's read paths must call
`require_read_allowed(key)` and receive the honest refusal; once the browser navigates to
a different pathname, the new page is readable and the login page stays locked.

## 2. What is built, and what the suite proves

`backend/jarvis_secret_handoff.py` (+ twin) and `backend/test_secret_handoff.py`:
**93 checks, 0 skipped, 0 failed**, no GUI, no network, no sleeps.

- key normalisation (query/fragment/userinfo stripped, default ports dropped, `.`/`..`
  path segments resolved, lower-cased host, non-http refused, window class lower-cased and
  never silently dropped);
- the taint table (TTL, re-mark refreshes, bounded eviction, clear, status carries
  addresses and counts only);
- the card (only for a password-masked control, agent purpose cleaned and labelled
  untrusted, PC-only, 180 s, bounded pending cards, no secret field);
- the fill order (taint before typing, card consumed once, receipt has no secret);
- every void condition in 1.3, each asserting nothing was typed and no taint was set
  where it should not be;
- a typing failure: the injected exception is *replaced* by the module's own fixed
  sentence (so a third-party error string cannot echo the value it failed on), the target
  STILL taints, the card is spent;
- no persistence: the module never calls `open`, never prints, imports no sqlite/
  logging/network/clipboard library.

## 3. Honest limits

- **Python cannot wipe memory.** Strings are immutable, so overwriting a local variable
  in a `finally:` block does nothing. What the module actually promises is: the value
  lives for one call, is never copied into a structure the module owns, and is never
  written anywhere. It is not a secure enclave.
- **The taint table is memory only.** A backend restart clears it. That is intended: it
  is a session protection against reading a just-filled page back, not a durable record.
- **The origin check is only as strong as its caller.** `from_this_pc` has no safe default
  (a caller that omits it is refused), but the wiring must still prove the request came
  from this PC; the engine cannot see the network.
- **The keys are page addresses and window handles**, not secrets, so a future status
  page may show them; no reviewer or secret ever appears.
- **Nothing is measured live.** No real browser session, no real UIA window and no real
  card exists yet, so the wiring slice is the first measurement.

## 4. The wiring slice (next), in order

1. `jarvis_ui_control.py`: a `secret_handoff_snapshot()` that reads the live focused
   control (UIA), proves `IsPassword`, and builds a `VerifiedTargetSnapshot`; the read
   paths (`get_window_state`, `read_selection`) consult `require_read_allowed(key)` on
   the tainted window.
2. `jarvis_browser_control.py`: the same for a page - `page.url` for the key, the
   focused element for `control_id`, `locator.fill()` as the typing function; its
   `read_page` step consults the taint.
3. The route + card: a host-only `POST` pair (create/fill) that never logs its body, and
   a HUD card following the two-box layout in 1.2. Turning the feature on stays one
   approval card; nothing types until the owner does.
4. Docs: `docs/JARVIS-API.md` route section, `docs/ARCHITECTURE.md` §8 for the phone
   being deliberately out (the card is PC-only in slice 1).
