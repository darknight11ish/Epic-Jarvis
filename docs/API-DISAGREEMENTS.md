# Where the docs and the code disagree

The desktop update order asks for this list: *"Where the docs and `jarvis_hud.py`
disagree, the code wins — and tell me, because that is a doc bug on my side."*

Everything below was found while building A1–A3 against the 14 Sep backend
drop. Each entry names the document, what the code actually does, and what the
desktop was built to. **The desktop follows the code in every case.**

Checked against: `jarvis_hud.py`, `jarvis_arbiter.py`, `jarvis_gate.py`,
`jarvis_content_risk.py`, `jarvis_events.py`, `jarvis-visual-spec.json`,
`jarvis-reactor-kit.html`.

---

## 1. `face_state` is not served anywhere — every client must compose it

**JARVIS-API §5, "The `banked` state":**

> `jarvis_arbiter.face_state(activity)` does that resolution server-side; a
> client that re-derives it will disagree with the server the first time the
> two drift.

**The code:** `face_state()` is called by nothing. Not by a route in
`jarvis_hud.py`, not by `_publish_state`, not by any other module — its only
caller in the whole drop is `test_arbiter.py`. `/api/attention` returns
`banked` as a boolean, the `attention` event carries `banked` as a boolean, and
the activity arrives separately on the `activity` event and in
`GET /api/version`. There is no wire format that carries the composed answer.

So the warning cannot be followed as written: composing it client-side is the
only option. This is the most consequential item on the list, because a client
author reading §5 would go looking for a route that does not exist.

**What the desktop does:** composes it in exactly two places — `face_state()`
in `src-tauri/src/attention/state.rs` for the tray, `faceState()` in
`src/jarvis-link.js` for the windows — both line-for-line copies of the Python:

```python
if activity in ("idle",) and banked(now):
    return "banked"
return activity
```

`banked` is taken from the wire and **never** recomputed from
`remaining == 0 && pending > 0`. If a route ever serves the resolved state,
those two functions are the only things to delete.

**Suggested doc fix:** either add the composed state to `/api/attention` and the
`attention` event, or change §5 to say that clients compose it from `activity`
and `banked` and must not re-derive `banked` itself.

---

## 2. §3's event list omits three kinds that are published

**JARVIS-API §3:**

> **Event kinds:** `hello`, `approval`, `finding`, `power`, `persona`, `model`,
> `voice`.

**The code publishes three more:** `activity` (documented later in §4),
`attention` (documented later in §4, and central to A1), and `job` (published by
`jarvis_jobs`). A client that built its dispatch table from §3 alone would drop
the attention event on the floor and never light the badge.

**What the desktop does:** handles `hello`, `approval`, `activity`, `attention`,
and fans every other kind out verbatim.

---

## 3. §3's `hello` does not carry the activity §4 says it does

**JARVIS-API §4, "The `activity` event":**

> `hello` carries the current value, because a client that connects mid-turn has
> no other way to learn it.

**The code** — `jarvis_events.stream()`:

```python
hello = Event(id=bus.latest_id(), kind="hello",
              data={"resumed_from": last_id, "stale": stale, ...})
```

Four keys: `resumed_from`, `stale`, `latest`, `retry_ms`. No activity. The
§3 sample frame is correct; the §4 sentence is not.

**What the desktop does:** reads `GET /api/version`, which *does* carry
`activity` (`jarvis_events.hello()`), on connect and on any power change.

---

## 4. §4 says `/api/chat` is "not SSE"; with `stream: true` it is

**JARVIS-API §4:**

> **Streams** the reply as a chunked body — not SSE, just a chunked HTTP
> response.

**The code** copies the upstream `Content-Type` verbatim, so an upstream that
streams SSE produces `data:`-framed chunks on this route too.

**What the desktop does:** the chat pump handles both framings.

---

## 5. §4's "All require `X-Jarvis-Token`" is conditional

**JARVIS-API §4:** "All require `X-Jarvis-Token`."

**The code** — `_token_ok` admits any loopback peer when `HUD_TOKEN` is unset,
which `jarvis_events.hello()` reports honestly as
`auth.token_required: false`. The header is required only when a token is
configured.

**What the desktop does:** sends the token on every request when it has one.
This is a doc-tightening note rather than a client problem.

---

## 6. §4's `raised` sample omits `count_today`, which the prose then relies on

The JSON block in §4 lists `code`, `text`, `quote`, `context`, `source`,
`from_tier`, `to_tier`. The paragraph underneath says "`count_today` above 1 is
worth showing as it comes". `jarvis_content_risk.chip_from()` does emit
`count_today`, and it also **folds the ordinal into `text`** ("(4th time
today)"), so a client that rendered both would say it twice.

**What the desktop does:** renders `text` as it arrives and counts nothing.

---

## 7. Spec: `sweep` and `hue_sweep`

`jarvis-visual-spec.json` gives `thinking` the pattern id `sweep`, whose `kind`
is `hue_sweep`. Both renderers resolve on `kind`, so this is correct — noting it
only because a port that switched on the pattern *id* would silently fall
through to the first pattern in the list.

---

## 8. `jarvis_hud.html` fetches fonts from Google, and is blocked doing it

**The page** carries its own `<meta>` CSP allowing `fonts.googleapis.com` and
`fonts.gstatic.com`, and three `<link>`s pulling Chakra Petch and IBM Plex from
there.

**The code:** Tauri serves the app's `app.security.csp` as a response **header**
on every `.html` asset, and both policies are enforced. The header has no https
origin at all, so the request was blocked and the HUD was silently rendering in
system fonts — while also, on any build where it *did* work, leaking the user's
IP to Google on every window open, which is the exact thing `fonts/fonts.css`
was written to stop.

**Fixed in the desktop's bundled copy** (`src/jarvis_hud.html` now links
`fonts/fonts.css`, and the two remote origins are gone from its meta CSP). The
backend's own copy of this file has the same three lines and needs the same
change, or the fix is lost the next time the page is re-synced.

---

## 9. Nothing serves an audio level, and nothing plays the audio

**Read:** `jarvis-visual-spec.json` → `speech`; `DESKTOP-UPDATE-PROMPT.md` § B.

The spec's contract is that the client feeds `setSpeechLevel(0..1)` "per audio
frame with the level of the TTS audio **you are playing**". On Android that is
true: the app owns the `AudioTrack`. On this desktop it is not. The backend
speaks out of process — there is no `<audio>` element in any window, no route
serves a level, and `/api/events` carries no `speaking` amplitude — so there is
nothing here to put an `AnalyserNode` on.

What the desktop does instead is the spec's own answer to this: `speech.fallback`
("Speaking is never frozen, even before TTS is wired"). `src/voice.js` runs the
synthetic envelope whenever the composed face state is `speaking` and no level
has arrived for 500ms, which on this build is always. `attachSpeechSource()` and
`attachMicSource()` are the real path, written and wired but with nothing to
attach to yet; the day the backend hands the client the audio, or a route
publishes a level, one call replaces the fallback.

**Not a doc bug** — the spec anticipated this exactly. Recorded because "section
B is done" would otherwise imply real audio is being analysed, and it is not.
