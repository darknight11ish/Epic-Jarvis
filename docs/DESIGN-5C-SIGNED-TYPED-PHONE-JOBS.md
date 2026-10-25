# Design 5C - signed typed phone jobs

**STATUS: THIS IS A DESIGN. NOTHING IN IT IS BUILT.** No module, no patch, no
route, no test. Part 5C does not exist in this repository, on `main` or on any
branch I read. Read every sentence below as "would", not "does".

**Read from `origin/main` `d6364f52`**, in a fresh worktree of that commit
(`C:\Users\pcadmin\AppData\Local\Temp\wt-5c`). Every claim about existing code
below was read with `git show`/`git grep` **at that commit** - a worktree is a
second copy on another branch, so where a claim is about `main` the command that
produced it is named. Nothing here was read from the owner's PC.

---

## The answer first

**5C CAN be built without loosening rule 2 or rule 4 — but NOT as "an extension
of 5A/5B", because 5A/5B are not in this tree.** Two findings, and the second is
the one that changes the plan:

1. **Rule 4 already holds, and it is provable from the tables.** A typed job's
   run action resolves to the risk action `control_phone`, whose tier in the
   shipped config is **`ask`** — one approval card, every time. The one thing
   that must not happen (a job that acts with no card) is prevented by the
   existing tier chain, not by anything new. See §3.
2. **The foundation the brief says to extend is not on `main`.** The brief
   describes `backend/jarvis_android_control.py` as ~1000 lines with
   `inspect_ui()`, `resolve_node_to_tap()`, `long_press`, `open_app`, `ui_dump`
   and `annotate_screenshot_with_nodes()`. **Measured: that file is 378 lines,
   and five of those six names appear nowhere in the repository at all** (see
   §8). `open_app` exists, but in `backend/jarvis_open.py` and
   `backend/jarvis_quick.py`, not there. So 5C cannot be an extension of a UI
   inspector that does not exist: **5A/5B must land first, or 5C must be built
   as its own first slice.**

**Nothing here needs a public tunnel or an auto-approval.** If a later
implementation finds it needs either, that implementation is wrong, not this
design — rule 2 and rule 4 are not negotiable and nothing below bends them.

---

## 1. What a "typed job" is

A typed job is **a request from the owner's phone asking the PC to perform one
device action**, in a fixed, closed vocabulary. "Typed" means the vocabulary is
enumerated in code and every parameter is validated against its type — there is
no free-text field anywhere on the wire.

### The shape

    job = {
      "type":   one of JOB_TYPES,          # an enum, not a string the caller invents
      "params": {...},                     # keys depend on `type`, nothing else allowed
      "device": "<paired device id>",      # who is asking
      "app":    "<package name>",          # optional, validated as a package name
      "target": {...},                     # optional, a UI match, not coordinates
      "text":   "<bounded string>",        # optional, length-capped
    }

### What a job can ask for

The types are deliberately few, and each maps to one action the gate already
knows:

| type | does | maps to |
|---|---|---|
| `open_app` | bring one named package to the front | the existing open-app path |
| `tap_label` | tap the control whose visible text matches | a UI match |
| `long_press_label` | long-press that control | a UI match |
| `type_text` | type a bounded string into the focused field | a text entry |
| `read_screen` | return the screen's **text** | a read |
| `screenshot` | return one picture of the current screen | a read |

### What a job explicitly CANNOT do — and how that is prevented

- **It cannot name a shell command, a binary, or a path.** The wire format has
  no field a command could travel in: the only free-text field is `text`, it is
  length-capped, and it is only ever handed to the phone's own text-entry as
  keystrokes. The server maps `type` through a fixed table to the existing step
  builders, never to a process.
- **It cannot name an arbitrary intent, URI or URL.** No field carries one.
- **It cannot touch the PC's filesystem, install anything, change a setting, or
  approve anything.** Those are different actions with their own tiers.
- **It cannot run without a card** — §3.
- **It cannot be replayed** — §6.

**If this could not be prevented, this document would say so and stop.** It can:
the prevention is structural (a closed enum plus a fixed mapping), not a filter
over free text, which is the only kind of prevention that survives a reader
trying to be clever.

---

## 2. What is signed, and with what key

**Reuse the existing per-device approval key. Do not invent a second key, a
second store, or a second verification path.**

Everything below already exists in `backend/jarvis_devices.py` for approving a
card from a device that holds its own key:

| what | where |
|---|---|
| the device's public key | `approval_key_of()` — `backend/jarvis_devices.py:2238` |
| its state | `approval_key_state()` — `:2251` |
| the challenge that issues a nonce | `challenge()` — `:2409`, route `POST /api/approve/challenge` (`:2483`) |
| the nonce is single-use | `_take_nonce()` — `:2441` |
| the signed message | `sign_message()` — `:2229` |
| verifying it | `signature_ok()` — `:2167` |
| the whole check | `check_signed_approval()` — `:2449` |

### What is signed

The signature must cover **the exact thing the owner was shown**, or a signature
proves nothing about the card. The existing path already does this: the message
is built from the card id, the action, the nonce **and a hash of the card's own
words** (`check_signed_approval`, `:2468`, via `words_sha256(row)`).

A typed job inherits that shape:

    message = sign_message(job_type, canonical(params), device_id, nonce,
                           words_sha256(card))

`canonical(params)` is a deterministic serialisation (sorted keys, no
whitespace) so two encodings of the same job cannot produce two signatures. The
**nonce comes from the PC** (`challenge()`, `:2409`), never from the phone, and
the phone cannot choose it: a self-chosen nonce would make replay trivial.

### Key lifetime and storage

The key is created on the phone, its **public** half registered with one
`register_approval_key` card approved on the PC (that path and its card already
exist), and the private half stays in the phone's Keystore. That is unchanged by
this design — 5C adds no new secret material and no new place for it to live.

### What happens when the signature fails — fail closed, always

`check_signed_approval()` (`:2449`) is the model, and every branch refuses:

| condition | answer | nothing runs |
|---|---|---|
| the device holds no approval key | 403 `no_approval_key` (`:2459`) | yes |
| no `signature` object on the request | 403 `no_signature` (`:2462`) | yes |
| nonce unknown, expired, another device's, or already burnt | 403 `bad_signature` (`:2466`) | yes |
| **the check itself cannot run** | **503 `cannot_check` (`:2471`)** | **yes** |
| signature does not verify | 403 `bad_signature` (`:2473`) | yes |

The nonce is **burnt whether the signature was good or not** (`_take_nonce`,
`:2441`, called at `:2465`) — so a failed attempt cannot be retried with the same
nonce, and a stolen nonce is worth one try, not many. The `cannot_check` branch
is the one that matters most: an error verifying is a refusal, never a pass.

---

## 3. How rule 4 holds — and whether any path acts without a card

**No path may act without a card. Here is the chain that enforces it, and the
check that would catch a break in it.**

### The chain, read from the shipped tables

1. `action_for_tool("jarvis_android_control_run")` reads
   `_TOOL_ACTIONS` → `"control_phone"` — `jarvis-backend/jarvis_gate.py:795`.
2. `"control_phone"` is not a tier word, so it stays an action name —
   `action_for_tool()`, `jarvis-backend/jarvis_gate.py:1098-1122`.
3. `[autonomy.tiers]` in the shipped config sets it: **`control_phone = "ask"`**
   — `jarvis-backend/jarvis-framework.toml:256`.
4. That tier is in `_RANK = {"auto": 0, "notify": 1, "ask": 2, "never": 3}` —
   `jarvis-backend/jarvis_gate.py:740`.

So a RUN gets **tier `ask`: one approval card, shown to a person, every time.**
The sibling `jarvis_android_control_plan` maps to the tier literal `"auto"`
(`jarvis_gate.py:795`, kept in `_SYNTH_TIERS` at `:1119`) and **that is safe
only because planning performs no device action** — `plan()` builds steps
(`backend/jarvis_android_control.py:161`) and `run()` is what taps
(`:306`). If planning ever gained a side effect, this design's tier for it would
be wrong; that is an invariant to test, not an assumption to keep.

Its risk classification agrees: `_RISK["control_phone"]` is
`("no", "outbound", "tapping the phone can send a message or complete a
purchase")` — `jarvis-backend/jarvis_gate.py:300`. "no" there means **no undo**,
not "no card" (see `risk_for()`, `:639`).

### The check that would catch a card-less action

**Two, and the second is the one the brief asks for:**

1. **Every unrecognised or misspelled tier resolves to the STRICTEST, not the
   loosest.** `_tiers()` validates every string in `[autonomy.tiers]` against
   `_VALID_TIERS` and rewrites anything else to `"never"` —
   `jarvis-backend/jarvis_gate.py:1140-1153`: *"a typo in a security policy
   should lock, not unlock."* And an action nobody classified resolves to
   `UNKNOWN_TIER = "ask"` (`:72`, used at `:1502`), so **removing the
   `control_phone = "ask"` line makes the action ask, never auto-run.**
2. **The route must reach the gate, and only the gate may call `run()`.**
   `jarvis_gate.check()` (`jarvis-backend/jarvis_gate.py:1489`) is the only thing
   that produces an approval; a test must assert that nothing else calls
   `jarvis_android_control.run()` (`backend/jarvis_android_control.py:306`)
   except through it. **That test does not exist today** — there is no job route
   to guard yet. It is a requirement of 5C, not a property 5C inherits.

**The honest gap:** today the only caller of the android-control `run()` is
whatever invokes it directly; nothing in the tree routes a phone job. So 5C must
*add* the gate call, and the two checks above are what stop a future edit from
adding a second, card-less door.

---

## 4. How rule 2 holds — and the exact check for a public bind

**The transport is unchanged: Tailscale or NordVPN Meshnet, private
device-to-device, never a public tunnel.** 5C adds no listener, no port and no
address — it is a new route on the server that already exists, reached over the
network that already exists.

### The check that catches a public bind — it exists today

`bind-wildcard.patch` adds `_binds_every_interface` (which asks the same
resolver `socket.bind` uses, rather than matching strings) and
`_refuse_every_interface`, and **`main()` calls it before anything listens**.
The suite that proves it is `backend/test_bind_wildcard.py`, and its method is
the strong part: it **binds a real socket** to every `every_interface` entry in
`jarvis-desktop/tests/bind-address-cases.json` first, so the table is proven
against the operating system rather than against itself, and only then asks the
patched functions. Its own docstring records why: the desktop used to refuse
only the literal `"0.0.0.0"` and `"::"`, while `"0"`, `"0x0"`, `"0.0"` and
`"000.000.000.000"` all bind every interface.

**So yes — a check exists.** A 5C change that widened the bind, or added a
listener of its own, fails `backend/test_bind_wildcard.py`.

Three more existing refusals sit alongside it:

- `_RISK["open_public_tunnel"] = ("no", "outbound", "exposes this machine;
  permanently forbidden")` — `jarvis-backend/jarvis_gate.py:289`; the tier table
  elsewhere sets it to `never`, so the gate refuses it outright rather than
  asking.
- `action_for_tool()` rewrites a shell blob mentioning `ngrok|cloudflared|
  localtunnel|bore|funnel|serveo|ssh -R|socat` to `open_public_tunnel` —
  `jarvis-backend/jarvis_gate.py:1123-1129`.
- The apps refuse a server address that is not loopback, the home network,
  Tailscale or Meshnet (the owner's decision of 2026-09-26).

**What is NOT checked, and 5C must add:** nothing today proves a given *job*
arrived over the mesh rather than being POSTed to the PC from somewhere else.
The defence is the existing one — the server's bind plus the paired-device
token — so 5C must require the job route to be **refused without a paired
device's token**, the same as every other authenticated route. A job route added
to `KEYLESS` in `backend/jarvis_devices.py:2485` (currently only
`/api/pair/claim` and `/api/pair/collect`, which exist because the phone has no
key yet) would be a defect; a check should assert 5C's route is never in that
tuple.

---

## 5. What "stale" means for a typed job

Rule 4 says: block when the event stream is stale. For a typed job, "stale"
must be defined by something the PC controls, not by the phone's own clock, or
a phone with a wrong clock decides for itself whether it may act.

**Stale, for a job, means any of:**

1. **The card has expired.** Approvals carry a window — the phone-side contract
   reads `expires_in`, and `599` seconds (ten minutes) is what the live build
   offers (the matrix's third-pass T2/T3 rows). Past it, the card is refused.
2. **The nonce has expired or been used.** `_take_nonce()`
   (`backend/jarvis_devices.py:2441-2446`) refuses a nonce older than
   `NONCE_SECONDS`, one issued to another device, one for another card, or one
   already burnt.
3. **The thing the card described has changed.** The signature covers
   `words_sha256(row)` (`:2468`). If the job's target or words no longer hash to
   what was signed, the check fails — a card signed for one action cannot be
   spent on a different one.

**When the PC has not answered, what the phone sees:** "not answered yet" while
the window is open, and then a definite **"the PC did not answer — nothing was
done"** once the window closes. It must never show "done", and it must never
show a spinner for ever. The phone's own SSE watchdog exists for the same
reason in the other direction: it distinguishes a quiet-but-alive desktop from a
dead one, and its own contract test records the bug where a keepalive was
swallowed and a **perfectly answering desktop was declared stale**
(`jarvis-client/app/src/androidTest/java/com/jarvis/client/EventStreamContractTest.kt:109-117`).
A job's staleness must not repeat that mistake.

**The honest gap:** I found **no server-side staleness gate for a job** in the
tree — the mechanism I can point to is the client's SSE watchdog and the card's
own expiry. So 5C must **inherit the card window and the nonce TTL rather than
invent a second clock**, and it must state which of the three conditions above
it checked. A design that says only "we handle staleness" is not this one.

---

## 6. Failure modes

| what happens | what must happen |
|---|---|
| **The PC is asleep or off** | The job never starts. No wake, no queue, no retry. The phone shows pending, then a definite "the PC did not answer"; the nonce ages out. |
| **The network drops mid-job** | The job is **not** resumed and is **not** re-sent. Its outcome is recorded as **unknown**, and the phone says **"I don't know whether it ran"** — never "it failed" and never "it worked". This project already has that vocabulary for a send interrupted mid-flight (`outcome_unknown`, not a failure to retry). |
| **The phone sends the same job twice (same nonce)** | **Refused.** `_take_nonce()` burns the nonce on first use (`backend/jarvis_devices.py:2441`), so the replay answers `bad_signature` and nothing runs. This is why the nonce must come from the PC. |
| **The phone sends the same job twice (a fresh nonce each)** | Two cards, two decisions by the owner. That is correct and is not idempotency: the harm is a job that runs twice **from one approval**, and a fresh card is a fresh approval. |
| **The job's target is gone** | The tap finds no match. It must **refuse and say so**, never fall back to tapping coordinates. A stale screenshot plus blind coordinates is how a phone job taps "Send" on something the owner never saw. |
| **Two devices send at once** | Each job is bound to its own device id and its own nonce; one device cannot spend another's. |
| **The PC restarts between challenge and approval** | The nonce lives **in memory only** (`challenge()`'s own words, `:2411`), so it is gone: the job fails closed and the owner is asked again. |

**Idempotency, said plainly:** one approval spends one nonce and produces at
most one run. There is deliberately no "retry the job" path — a job that did not
finish is a job whose effect on the phone's screen is unknown, and the only safe
next step is a person looking at the phone.

---

## 7. What is NOT built

**Everything in this document.** Specifically, none of the following exists on
`main` at `d6364f52`:

- No `JOB_TYPES` enum, no job request shape, no canonicalisation function.
- No job route of any kind, and no gate action name for one.
- No job signing, and no reuse of the approval-key path for jobs.
- No server-side staleness gate for a job.
- No idempotency beyond the nonce that already exists for card approvals.
- No test asserting the job route cannot act without a card.
- No test asserting the job route is not in `KEYLESS`.

And §8 records the larger gap: **the UI-inspection groundwork 5C was said to
extend is not in this tree.**

---

## 8. What I could not confirm — including things in the brief that are wrong

Every claim below was measured at `origin/main` `d6364f52`, in a worktree of
that commit.

1. **"`backend/jarvis_android_control.py` grown to ~1000 lines" — it is 378
   lines** (21,233 bytes). Its functions are `_build_step:117`, `plan:161`,
   `describe:195`, `adb_env:223`, `_real_adb:232`, `foreground_packages:255`,
   `jarvis_in_front:268`, `_current_serials:294`, `run:306`.
2. **Five of the six named functions do not exist anywhere in the repository.**
   `git grep -w` over the whole tree returns **zero** files for `inspect_ui`,
   `resolve_node_to_tap`, `long_press`, `ui_dump` and
   `annotate_screenshot_with_nodes`. **`open_app` exists in 12 files**
   (`backend/jarvis_open.py`, `backend/jarvis_quick.py`,
   `backend/test_jarvis_open.py`, …) **but not in
   `jarvis_android_control.py`.** So "5A and 5B already built" is **not true of
   this tree**, and 5C cannot extend them here.
3. **`jarvis_gate.py` is not in `backend/`.** `backend/jarvis_gate.py` does not
   exist; the file is **`jarvis-backend/jarvis_gate.py`** (the published base,
   which the patches in `backend/` edit). Every `jarvis_gate.py` line number
   above is that file.
4. **The tier claims are correct**, verified rather than trusted:
   `jarvis_android_control_plan` → `"auto"` and `jarvis_android_control_run` →
   `"control_phone"` at `jarvis-backend/jarvis_gate.py:795`;
   `modify_own_code` → `("hard", "local", …)` at `:278`. **And the tier that
   matters is not in that file at all** — it is
   `control_phone = "ask"` in `jarvis-backend/jarvis-framework.toml:256`, which
   the brief did not mention and which is what actually makes the card happen.
5. **I could not find a server-side staleness gate for a job**, nor a general
   one — the word appears in the client's SSE watchdog and in per-feature
   settings caches. §5 says what 5C must therefore define itself.
6. **No behavioural testing was possible**, and none is claimed: there is no
   Ollama, no phone and no PC here, and this is a design. The five non-negotiables
   were applied as constraints on the design, not verified by running anything.

## 9. The five non-negotiables, applied

| rule | how this design keeps it |
|---|---|
| 1 — email, files, credentials, memory stay local | A job's vocabulary has no field that can carry them, and `read_screen`/`screenshot` return what is on the phone's own screen to the phone — nothing leaves the owner's devices, and no job touches the PC's files. |
| 2 — never a public tunnel | No new listener; the existing bind refusal (`_refuse_every_interface`, `main()`) and `open_public_tunnel` = `never` stand unchanged. The private mesh is the only transport. |
| 3 — API keys never logged, never plain text | 5C introduces no key: it reuses the device approval key, whose private half stays in the phone's Keystore and whose public half is registered by an existing card. |
| 4 — never auto-approve; block on a stale stream | The run action is tier **`ask`** — one card, every time (§3); the card window and the single-use nonce define "stale" (§5); a job that cannot be verified is refused (§2). |
| 5 — non-commercial, sideloaded | Nothing here publishes, lists or phones home. |
