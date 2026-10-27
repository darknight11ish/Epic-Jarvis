# Field test: cloud escalation, 2026-10-14

**What this is.** A field test of cloud escalation on the owner's own PC and his
own Android phone, driven through the live backend on `127.0.0.1:4719` and the
live desktop app, with the owner's authorisation to make real DeepSeek calls.

**The two questions the owner asked, answered up front.**

> *Does cloud escalation work well, on both the Android phone and the desktop?*

**No — not well, and the reason is specific.** The plumbing is sound: the router
offers the lane, the lane resolves to DeepSeek, the key is present and reaches
the request, the call succeeds (`HTTP 200`) and the spend is recorded. But every
escalated answer in this test came back **with no visible text at all**:
`finish_reason: "length"`, `content` empty, the whole token budget spent on
DeepSeek's hidden reasoning. Escalation returns a blank answer for exactly the
questions it exists to answer. See "The defect" below.

> *And can Jarvis **recommend** cloud escalation if it detects that the task is
> too complicated — or if it would really be helpful?*

**Yes, it recommends — and it recommends rather than silently escalating.** It
says so in `X-Jarvis-Route` (`gate: "offer"`, `offer: "jarvis-escalate"`) and
both apps turn that into a visible strip: *"A cloud model could give this one a
second look."* with a **Try the cloud model** button and **Not now**. The phone
strip was seen on the owner's real phone. And it does **not** fire on easy
questions. Both answers carry literal evidence below.

---

## 1. The mechanism, as it actually is

The decision is made by **`jarvis_router.choose()`** — the live backend's
`jarvis_router.py`, whose repository copy is `backend/rebuilt/jarvis_router.py`
(published base: `jarvis-backend/jarvis_router.py`). It is **a rule, not the local
model, and not the owner** who decides *that an offer is worth making*; the owner
decides *whether to accept it*.

Nine gates, in order, and each can only push the answer **downward** toward local
(`choose()`, the gate table in its docstring, and the code at the end of the
function):

| # | gate | what it does |
|---|---|---|
| -1 | `cloud_model` | the configured "local" model is itself an Ollama `:cloud` model |
| 0 | `unavailable` | no cloud lane was offered at all |
| 0b | `lockdown` | Lockdown is on — local, and **no offer either** |
| 1 | `taint` | the conversation has read outside text — local, unconditionally |
| 1b | `image` / `screen` | the turn carries a picture or words read off the screen |
| 2 | `private` | `is_private(query)` — the keyword backstop |
| 3 | `secret` | a secret-*shaped* value pasted into the message |
| 4 | `complexity` | `complexity < 0.40` — ordinary question, stays local |
| 5 | `budget` | the minute/day request budget is spent |
| 6 | `offer` | **complex enough, nothing private: name a lane but do NOT use it** |
| — | `escalate` | only when `owner_said_yes is True` **and** gates 0–5 already passed |

**Gate 6 is the answer to the owner's second question, and its default is "no".**

```python
lane = lanes[0]
if owner_said_yes is not True:
    d = local_decision(
        "offer", f"complexity {c}: {lane} could answer this, but the cloud is used "
                 f"only when you say yes for this question")
    d.offer = lane
    return d
return Decision(lane, "... and you said yes for this question", "escalate", c,
                inject_memory=False, tainted=conversation_tainted)
```

**What carries the owner's yes for one question.** `cloud_yes: true` in the
`/api/chat` body — `backend/cloud-say-yes.patch`, applied in the live
`jarvis_hud.py` as `owner_said_yes=bool(body.get("cloud_yes"))`. A yes can only
ever turn gate 6 from `offer` into `escalate`; it cannot pull a private, tainted,
picture or screen turn out, because those gates run first.

**Which lanes exist, and who serves them.** `jarvis_hud._lane_names()` reads the
`model_name:` entries out of `~/.openjarvis/litellm-proxy.yaml`. The owner's file
gives exactly three lanes: `jarvis-escalate`, `jarvis-critic`, `jarvis-bulk`.

That YAML talks about OpenRouter and a LiteLLM proxy on port 4000, **and that is
not what serves these lanes today.** `jarvis_chatbot_api.CLOUD_LANES` maps all
three lane names onto the **DeepSeek** service (the owner's decision of
2026-10-06, quoted in that file):

```python
CLOUD_LANES = {
    "jarvis-escalate": ("deepseek_api", "deepseek-flash"),
    "jarvis-bulk":     ("deepseek_api", "deepseek-flash"),
    "jarvis-critic":   ("deepseek_api", "deepseek-v4-pro"),
}
DEFAULT_LANE = ("deepseek_api", "deepseek-flash")
```

**How the request is built and where the key comes from.**
`jarvis_hud._completions_url(lane, body)` calls
`jarvis_chatbot_api.lane_state(lane)`, which resolves `url`, `model`, `cap` and
`key` and stores them **per thread**; `jarvis_hud._auth_headers()` then reads that
back with `last_lane_state().get("key")` and sets `Authorization: Bearer …`. The
key comes from Windows Credential Manager under
`Jarvis Backend/DeepSeek API key`, through `jarvis_token_store`. It is never a
name in `jarvis_hud.py`, never logged, and never written to disk.

**The privacy cuts on a cloud turn.** `backend/cloud-one-turn.patch` reduces the
payload to **only the newest `role == "user"` message**, whatever the client sent;
`inject_memory` is computed from the lane, so a cloud lane is never handed stored
memory; and a cloud lane is never the "local" fallback.

**The settings that gate all of it** (live values, read from
`C:\Users\pcadmin\.openjarvis\config.toml` and the live backend folder's
`jarvis-framework.toml`):

| setting | live value | effect |
|---|---|---|
| `[routing] complexity_threshold` | `0.40` | below this, gate 4 keeps it local and no offer is made |
| `[budget] requests_per_minute` / `requests_per_day` | `15` / `800` | counted on disk in `~/.openjarvis/budget.json` |
| `[budget] degrade_chain` | `["jarvis-escalate","jarvis-bulk","jarvis-critic"]` | the step-down chain on a 429/5xx |
| `[privacy] never_leaves_device` | 15 entries | read live by `jarvis_router._PrivateMatcher` |
| `[agent] context_from_memory` | `false` | **if true, escalation is off entirely** (lanes are passed as `[]`) |
| monthly money limit | `deepseek_api: $10.00` | `~/.openjarvis/chatbot/api-money.json`; no limit = the lane is not usable |

**Lockdown** was off, and the **taint latch** was clear, at the time of the test
(`jarvis_gate.taint_active() == False`, `jarvis_router.lockdown_on() == False`).

---

## 2. Is the lane wired to the Credential Manager key? Yes — established, not assumed

An earlier field-test pass measured `HTTP 401` with the key reported absent. **That
is not reproducible now, and the key is present.** Asked of the live code, with
`JARVIS_BACKEND` unset, in the live backend folder:

```
key_saved(deepseek_api) = True
ready_for('deepseek_api') = ''
lane_status(): jarvis-escalate -> deepseek_api / deepseek-flash / ready: true
               jarvis-bulk     -> deepseek_api / deepseek-flash / ready: true
               jarvis-critic   -> deepseek_api / deepseek-v4-pro   / ready: true
lane_state('jarvis-escalate'): url=https://api.deepseek.com/chat/completions
                               model=deepseek-flash  cap=8000  problem=''  key=35 chars
```

`cmdkey /list` shows the entry: `LegacyGeneric:target=Jarvis Backend/DeepSeek API key`.

And a real call through that resolved state succeeded:

```
HTTP      : 200
content   : 'LANE-OK'
usage     : {"prompt_tokens": 38, "completion_tokens": 18, "total_tokens": 56}
```

**So the lane is wired to the key, and the key works.** Whatever the earlier pass
saw, this pass could not reproduce it; the honest reading is that the key reaches
the backend today (the twin facts — entry present, `key_saved` True, `HTTP 200`
with a real answer — are all from this pass).

---

## 3. Does escalation work at all? The literal request and response

Driven through the real route, `POST http://127.0.0.1:4719/api/chat`, with
`X-Jarvis-Client: hud` and the pairing token read from Credential Manager as
UTF-8 bytes (never UTF-16) through `jarvis_token_store.default_store().read()`.

**Literal request** (`stream: false`):

```json
{"messages":[{"role":"user","content":"Compare three approaches to deduplicating a stream of events in real time, explain the trade-offs between exact hashing and probabilistic sketches, and design a step by step plan for choosing between them when memory is limited and latency matters."}],
 "auto":true,"stream":false,"cloud_yes":true}
```

**Route header returned:**

```
lane       : jarvis-escalate
where      : cloud
gate       : escalate
reason     : complexity 0.775, budget available, and you said yes for this question
complexity : 0.775
inject_memory : False
memory_side   : none
```

**Response body (from DeepSeek, `model: "deepseek-flash"`):**

```json
{"id":"7a305c34-2ed6-47aa-b09c-cbc4d038866b","object":"chat.completion",
 "model":"deepseek-flash",
 "choices":[{"index":0,"message":{"role":"assistant",
   "content":"",
   "reasoning_content":"We need answer. User asks: \"Compare three approaches ...\""},
   "finish_reason":"length"}]}
```

So the route, the key, the model and the reply all work — and **`content` is
empty**.

---

## 4. Question 1 — can Jarvis *recommend* escalation when a task is too hard?

**Yes. It recommends, and it does not silently escalate.**

**Literal evidence — the same hard question, without `cloud_yes`:**

```
gate       : offer
offer      : jarvis-escalate
where      : local
lane       : qwen3.5:9b
reason     : complexity 0.775: jarvis-escalate could answer this, but the cloud
             is used only when you say yes for this question
complexity : 0.775
ANSWER     : "Here are the three approaches to deduplication in a streaming
             context, followed by their trade-offs and a practical selection
             plan. ### The Three Approaches 1. **Exact Hashing ..."
```

The local model answered; the cloud lane was named but **not used**; and the
backend's own audit line agrees:

```json
{"iso":"2026-10-14T16:01:18Z","event":"route","detail":{"lane":"qwen3.5:9b",
 "gate":"offer","reason":"complexity 0.775: jarvis-escalate could answer this,
 but the cloud is used only when you say yes for this question","complexity":0.775}}
```

**And the offer is actually shown to the owner.** On his real phone
(`CPH2419`, `com.jarvis.client` `0.2.1445`, `MainActivity` in the foreground), the
question was typed into the app and sent; the app answered locally and then the
view tree contained:

```
TEXT="A cloud model could give this one a second look."
TEXT="Try the cloud model"      bounds=[90,20][506,164]
TEXT="Not now"                  bounds=[518,20][728,164]
```

and the backend logged the phone's own turn as `gate: "offer", complexity 0.558`
at `16:05:47Z`. The distinction the owner asked about is therefore settled:
**recommends** (a named lane in `offer` + a visible button), not *silently does
it* and not *does not notice*.

On the desktop the same turn was driven through the app's own window and produced
`gate: "offer", complexity 0.558` at `16:11:59Z` (section 7 has the desktop's own
caveat).

---

## 5. Question 2 — does it recommend only when it would *really* help?

**Yes. It stays quiet on an easy question.**

```
QUESTION   : Tell me the capital of France in one short sentence.
gate       : complexity
offer      : (empty)
lane       : qwen3.5:9b
where      : local
reason     : complexity 0.083 is under the threshold
complexity : 0.083
ANSWER     : "The capital of France is Paris."
```

No offer, no button, no cloud. A recommender that fired on everything would be
worse than none; this one did not.

**And the rule-1 boundary holds.** A private-ish question sent *with*
`cloud_yes: true` still stayed local and carried **no offer**:

```
QUESTION   : Summarise my inbox from this morning    (cloud_yes: true)
gate       : taint
offer      : (empty)
where      : local
reason     : this conversation has read outside text, so it stays on this machine
```

One honest detail about the *label*, not the behaviour: for a fresh single-turn
private question, `route.gate` reads `"taint"`, not `"private"`. Gate 1
(`_history_tainted`, which scans the same private list over every message in the
payload) runs before gate 2 (`is_private(query)`), so the same words are caught
one gate earlier. The turn stays local either way — but a reader expecting
`gate: "private"` on a first private question will not see it.

---

## 6. The defect: an escalated answer comes back blank

This is the finding that decides "does it work well", and it reproduced on
**every** escalated call.

| call | question | complexity | `finish_reason` | `len(content)` | `reasoning_tokens` | visible to the app |
|---|---|---|---|---|---|---|
| 1 | the long dedup question (`stream: false`) | 0.775 | `length` | 0 | 2048 | **nothing** |
| 2 | the same question (`stream: false`) | 0.775 | `length` | 0 | 2048 | **nothing** |
| 3 | the same question (`stream: true`) | 0.775 | `length` | 0 | 2048 | **nothing** |
| 4 | `"Explain how to compare two designs, and design a plan; which trade-offs matter most?"` (`stream: true`) | 0.467 | `length` | 0 | 2048 | **nothing** |

The streamed case is the one that matters, because that is what the apps use.
Reading the live SSE stream back:

```
route.lane : jarvis-escalate | gate: escalate | where: cloud
chunks with visible content : 0
chunks with reasoning only  : 2048
total reasoning chars       : 9412
finish_reason               : length
usage                       : {"completion_tokens": 2048,
                               "completion_tokens_details": {"reasoning_tokens": 2048}}
VISIBLE TEXT                : ''
```

**Why.** Three facts, each checked:

1. **DeepSeek's thinking mode is on by default.** The live
   `jarvis_chatbot_api.py` says so in its own words: *"DeepSeek's thinking mode is
   ON BY DEFAULT ("The default effort is high")"*.
2. **The request's cap is small and the reasoning is billed inside it.**
   `jarvis_hud._build_payload()` sends `max_tokens` straight from the request
   body, defaulting to **2048** (`int(_num(body.get("max_tokens", 2048), 2048, 1, 32768))`).
   DeepSeek put all 2048 into `reasoning_tokens`, hit the cap, and stopped before
   writing any answer — `finish_reason: "length"`.
3. **Nothing anywhere reads `reasoning_content`.** `git grep -n 'reasoning_content'`
   over `origin/main` returns **no matches**, and the same search over the live
   backend folder returns **no matches** either. So the reasoning text is dropped
   and the empty `content` is all the app receives.

**The consequence for the owner:** on the hardest questions — the only ones that
earn an offer — pressing **Try the cloud model** buys a blank answer. In this test
that cost **$0.0099** for four blank answers.

**What this is not.** It is not a routing bug, a key bug, or a privacy bug: the
route is right, the key reaches DeepSeek, gates 0–5 hold, memory is not attached,
and only the newest user turn is sent. It is a **response-shape** bug on the cloud
path.

---

## 7. Both apps

Both apps have the offer, with **identical wording**, and both send `cloud_yes`:

| | desktop | phone |
|---|---|---|
| label | `index.html`: *"A cloud model could give this one a second look."* | `CloudOffer.LABEL` — the same string |
| button | `id="cloud-offer-try"` → **Try the cloud model** | `CloudOffer.BUTTON` — the same string |
| dismiss | `id="cloud-offer-dismiss"` → **Not now** | **Not now** |
| reads the route | `main.js` `cloudOfferFromRoute()` requires `gate === "offer"` and a non-blank `offer` | `CloudOffer.laneFromHeader()` — the same two conditions |
| shows it | `main.js` `paintCloudOffer()`, gated on `state.phase === "done"` | `HomeScreen.kt` |
| sends the yes | `commands.rs` puts `cloud_yes: true` in the body | `ChatSession.tryCloudForLast()` → `cloud_yes: true` |

`docs/ARCHITECTURE.md` §8 already records this row, and it is **not** a one-sided
feature: *"it IS on both real chat surfaces: the desktop's main window
(`index.html`/`main.js`) and the phone's Home screen (`HomeScreen.kt`,
`net/CloudOffer.kt`). Left off the desktop's own separate
`widget.html`/`widget.js`"* — with its reason. **No §8 entry was needed for this
work, and none was added.** `tools/check_parity.py` is clean (section 9).

**Phone — driven on the device.** The offer strip appeared with the exact wording
above, on the owner's phone, in a **Temporary chat** (so nothing from that test
was kept or learned). **PASS for the recommendation.**

**Phone — the "Try the cloud model" press: NOT-TESTABLE by this pass.** Synthetic
taps injected with `adb shell input tap` were not received anywhere inside the
button's own reported bounds (`[90,20][506,164]`, probed at y = 92, 135, 160, 190
and 220), including on the adjacent **Not now** button, which costs nothing and
would have dismissed the strip. The app draws a full-screen GPU face surface,
which is also why `adb shell screencap` returns a black image for the app's area
while the status bar is drawn normally. **I did not press it on the phone.** The
wiring is verified by reading the code and the phone's own unit tests, not by a
tap.

**Desktop — driven on the machine, PARTIAL.** The app (`jarvis-desktop.exe`, pid
12904) was brought forward, a hard question was typed into its own input box and
sent, and the app answered locally while the backend logged `gate: "offer",
complexity 0.558` for that turn. **But the offer strip itself was not observed on
screen:** `paintCloudOffer()` shows it only when `state.phase === "done"`, and the
app stayed in the **`speaking`** phase (reading the long answer aloud) for the
whole observation window — still `SPEAKING` after a further 130 seconds, across
four captures. So the desktop row is **PARTIAL**: the route and the offer are
proven on the real app, the strip's own render is not.

**A separate desktop finding, on real hardware.** When first brought forward, the
desktop app was in **Demo mode** and could not answer at all:

> *"Demo — The local model is not answering — open the Ollama app (or run ollama
> serve), then reload."*
> *"SAMPLE REPLY — NOT FROM JARVIS … Jarvis is not connected … nothing you type
> here reaches it."*
> Chip: `QWEN3.5:9B` · `OFFLINE`

The app had started at `08:52:43`, about a minute **before** the everyday lane
came up (`…\JarvisOllama\logs\main.log`, first line `2026-10-14T08:53:45.660-07:00`;
the coding lane's own log is stamped `08:53:46`), and it never re-checked: it
needed the reload its own banner asks for. After a reload (`F5`) it read
`STANDING BY` / *"Systems online, sir. Local model loaded and the brain map is
current."* — and then it answered. Worth saying plainly: **the desktop could not
have shown a cloud offer at all in that state**, because it was not connected to
anything.

**The cloud lane's own status surface.** The desktop probes
`/api/chatbot/money` as its "Cloud model" service
(`jarvis-desktop/src-tauri/src/lib.rs`, `CLOUD_LANE_STATUS_PATH`), and treats it as
**optional** — "not answering is fine unless you use a cloud model" — so a working
cloud lane does not read as a broken install, and a broken one does not read as a
broken install either.

---

## 8. Does it record what it spends? Yes

A cloud lane that hides its cost would be a defect. This one does not hide it.

**Before this test** — `~/.openjarvis/chatbot/api-money.json` held
`"months": {}` (nothing ever recorded), and `~/.openjarvis/budget.json` **did not
exist** at all. So no cloud lane had ever been served through this HUD before.

**After four escalated turns:**

```json
{"limits": {"deepseek_api": 10.0},
 "months": {"2026-10": {"deepseek_api": {
   "completion_tokens": 8192, "dollars": 0.0099141,
   "prompt_tokens": 279, "requests": 4}}},
 "prices": {}, "version": 1}
```

and `budget.json` was created with **one entry per served turn** in both the
`minute` and `day` arrays (4 entries each) — the same counter gates 5 enforces.

Two separate mechanisms, both working:

- **the request count** — `jarvis_hud.py` calls `budget.spend()` after the degrade
  loop, *against the lane that actually served the turn* (`if ROUTING and budget is
  not None and lane in lanes`);
- **the money** — `jarvis_speed.Meter.finish()` calls
  `jarvis_chatbot_api.note_answer_spend(row)`, which reads the resolved lane state
  and writes the estimate. Its own docstring records why it lives there and not in
  the HUD: *"the cloud-lane transport never recorded what it spent, so the monthly
  limit `money_check()` enforces could never advance"* (audit finding E3), and the
  HUD's streaming loop sits inside patch-stack hunks.

**What the owner spent, exactly:** **$0.0099141** (four escalated turns, 279 prompt
+ 8192 completion tokens, at the file's own worst-case DeepSeek prices). The one
out-of-band probe I made directly against DeepSeek — to prove the key works,
outside Jarvis's own path — added about **$0.00003** and was, correctly, **not**
recorded, because it never went through the app. **Total real spend this pass:
about $0.01.**

The month's limit is $10.00, so this pass used about **0.1%** of it.

---

## 9. Everything that is BLOCKED, NOT-TESTABLE or PARTIAL

Per the project rule — **BLOCKED and NOT-TESTABLE are never counted as passes** —
these are the rows that are not PASS, each with its reason.

| row | result | reason |
|---|---|---|
| Phone: press **Try the cloud model** | **NOT-TESTABLE** | Synthetic `adb` taps are not received anywhere inside the button's reported bounds (probed at five y positions, including the free **Not now** button). The app's full-screen GPU face surface appears to swallow them; `adb shell screencap` returns a black app area for the same reason. Not pressed on the phone. |
| Desktop: the offer strip rendered on screen | **PARTIAL** | The turn and its `gate: "offer"` are proven on the real app, but `paintCloudOffer()` only shows the strip when `state.phase === "done"`, and the app stayed in `speaking` for the whole observation window (still `SPEAKING` after 130 s). |
| Desktop: the offer strip's **Try the cloud model** button | **NOT-TESTABLE** | Follows from the row above — the strip never rendered, so there was nothing to press. |
| Desktop: cloud escalation end to end through the app's own UI | **NOT-TESTABLE** | Same reason. The escalation itself was driven and proven through the live route (section 3); the desktop *button* was not. |
| Anything needing the owner's fingerprint, PIN, Windows Hello, his voice, his accounts, a watch or the camera | **BLOCKED** | Not touched; no such step was reached or attempted in this test. |
| The phone's talk/voice path for this feature | **BLOCKED** | Needs the owner's voice. |
| A screen or picture turn escalated to the cloud | **NOT-TESTABLE as a positive test** | Correctly refused by gates `image`/`screen`; there is no "pass" to record for sending one, and sending one would be a defect, not a feature. |
| Sending email, files, credentials or stored memory to the cloud | **NOT TESTED, ON PURPOSE** | Rule 1 says such a turn stays local. It is a defect if it ever escapes, so it is not exercised. The private-question check in section 5 is the safe form of this test, and it stayed local with no offer. |
| A real `jarvis-critic` (`deepseek-v4-pro`) call | **NOT-TESTABLE** | The critic lane is reached only by the self-modification review pipeline (`[self_modification] pipeline_implemented = false`), which does not exist. Its readiness was read, not exercised. |

---

## 10. What I changed, and how it was restored

**Changed and restored:**

| what | before | after | restored |
|---|---|---|---|
| The desktop window's position and size | `-5,0,810,691` (815×691) | moved to `1920,30,2560,721` so it could be captured, then set to the wrong size by the first restore | **Yes** — set back to `-5,0,810,691` (815×691) and re-read three times to confirm |
| The desktop app's connection state | stuck in Demo / `OFFLINE` | connected after an `F5` reload | **Left connected on purpose** — the reload is what the app's own banner instructs, and it is what a working desktop needs. It is a UI reload; nothing was written to disk. |

**Changed and NOT restored, said plainly:**

| what | detail |
|---|---|
| The PC's encrypted chat history | The desktop test turn is stored: conversation `ef7580f5-05ae-4e8d-b455-8daf37f7556a`, turns `idx 0` (user, `device: "hud"`, `provenance: "typed"`) and `idx 1` (assistant), text encrypted as always. I did **not** edit the database to remove them: the backend holds it open, and deleting encrypted rows from a live store risks more than the harmless test text costs. The phone test used **Temporary chat**, so it kept nothing. |
| `~/.openjarvis/chatbot/api-money.json` | Now records the 4 test turns and **$0.0099141**. Left as it is, because that record is the point of the feature and is real money actually spent. |
| `~/.openjarvis/budget.json` | Created by the test (4 entries per window). Left as it is; it prunes itself within a day. |
| The audit log | Four `route` lines and the phone's/desktop's lines were appended to `~/.openjarvis/logs/jarvis-2026-10-14.jsonl`. Append-only by design; left alone. |

**Not touched at all:** other `.dsh-scratch` worktrees; `scripts/apply-patches.ps1`
(never run); `.github/workflows/ci.yml`; `C:\Users\pcadmin\.openjarvis\config.toml`;
the live backend folder (only read, never written — all scripts ran from
`%TEMP%`); no approval card was approved (none was raised); no privacy setting was
loosened; the pairing token and the DeepSeek key were never written to any file,
log or output.

---

## 11. The checks, and what each returned

Run from this branch's worktree with **`JARVIS_BACKEND` cleared**, as `python -B`:

| check | result | its own last words |
|---|---|---|
| `tools/check_docs_map.py` | **exit 0** | `docs map OK: 383 documents, … bytes, and README.md agrees` |
| `tools/check_feature_list.py` | **exit 0** | `6 passed, 0 failed` |
| `tools/check_claims.py` | **exit 0** | `129 claim(s) checked against the code: 99 built, 22 still open, 8 unverifiable`, `Every 'built' claim still holds` |
| `tools/check_vacuous_checks.py` | **exit 0** | `322 suite file(s) read, 21882 check() call(s) looked at: no check is a fake skip` |
| `tools/check_parity.py` | **exit 0** | `No undecided drift.` |

`check_parity.py` prints three `::warning::` lines about `/api/work`,
`/api/work/choose` and `/api/work/recommend`. They are **not** about this
feature and not new here: `/api/work/recommend` is `'planned'` and called by
neither app, and the other two are the phone-only work routes. It still exits 0
with "No undecided drift."

## 12. What the owner should be told, in one paragraph

Cloud escalation is **wired correctly and honestly accounted** — the router offers
a lane instead of taking it, the phone and the desktop both show the same
"Try the cloud model" strip in the same words, it stays quiet on easy questions
and on anything private, and it records both the request and the money
($0.0099 for this pass). It just **does not yet produce an answer**: every
escalated call in this test returned an empty reply because DeepSeek's on-by-default
thinking mode used up the whole 2048-token cap and nothing reads
`reasoning_content`. Fix that one thing — raise the cap for a cloud lane, or turn
thinking off for `deepseek-flash`, or read `reasoning_content` when `content` is
empty — and the feature is worth using. Until then it is a feature that charges
for a blank screen.

---

**Closing line, added 2026-10-27 (the findings above are kept exactly as
written).** The three lanes this record measured (`jarvis-escalate`,
`jarvis-critic`, `jarvis-bulk`) became ONE on 2026-10-27 (`docs/DECISIONS.md`
that date, `docs/JARVIS-API.md` section 145.1): all three mapped to DeepSeek, so
the difference between them was a label and a model name and never a route, and
`_lane_names()` no longer reads `litellm-proxy.yaml` at all. The blank-screen
finding above is unchanged and is why an AUTOMATIC cloud turn - one nobody
clicked for - is now answered on this PC under one honest line instead of
showing the working-out. The measured cause (thinking billed inside the cap)
was not fixed; it was routed around.