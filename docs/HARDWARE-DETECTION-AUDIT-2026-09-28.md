# Hardware detection, adaptation and communication audit, 2026-09-28

Read-only audit. No code was changed. The owner's request, verbatim: "Can
you run an audit that checks for how well Jarvis can detect hardware and
how well it can actually adapt settings and preferences and let the user
know these things?" Answered as three linked questions - **detection**,
**adaptation**, **communication** - for every hardware-detection mechanism
found in the codebase, not only graphics cards.

**A note on timing.** A separate, in-flight piece of work is extending the
second-card system to a third graphics card, touching
`backend/jarvis_second_card.py`, `backend/jarvis_hardware.py`,
`jarvis-desktop/src/hardware-panel.js` and the phone's second-card screen
while this audit was being written. Those four files were read as they
stand right now, for this report, and not edited. Where this audit
describes "exactly two card roles" as a limit, that is a snapshot of
today's shipped behaviour, not a permanent gap - `jarvis_second_card.py`'s
own module docstring (2026-09-28) already says a third card's detection
data is being built underneath the unchanged two-role API, and
`docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` already has the full design for
finishing it. This audit does not re-litigate that decision; it notes one
small, real wording bug in the *current* two-role code that the in-flight
work should be aware doesn't fix itself for free (finding H1, below).

Every claim below is checked against the real file at the line quoted, or
by actually running the test named, not by memory of the pattern. Where a
test could not be run for an environment reason (a module that lives on the
owner's PC, not in this repository), that is said plainly rather than
skipped silently.

## In short

1. **Detection: solid.** Every mechanism found - graphics cards, Windows
   Hello, the phone's microphone/notification/battery/assistant-role state,
   RAM and disk space, Home Assistant's own configuration - degrades to a
   named, honest "could not tell" or "not there" state instead of guessing
   or crashing. `jarvis_compute.plan()`'s `simulated` field and
   `jarvis_second_card.py`'s `_not_capable()` are the clearest examples;
   see mechanisms 1-2 below.
2. **Adaptation: solid, with one small false claim found (H1).** Every
   switch that turns hardware-dependent behaviour on re-checks the hardware
   is *still* there, fresh, at the moment of approval - not just when the
   card was first raised - in both `jarvis_second_card.py` and
   `jarvis_big_model.py`. `jarvis_hardware.py` goes further and tracks a
   **fingerprint** of the cards a preset was chosen for, so a hardware
   change after the choice is detected and surfaced, not silently kept.
   This is exactly the discipline CLAUDE.md's hardware paragraph asks for.
   The one bug found is a wording bug, not a behaviour bug: two identically-
   sized capable cards produce a false "has more memory" sentence (H1).
3. **Communication: strong on the PC and the phone's own "Checks" screen,
   uneven where a technical vendor-support gap has no owner-facing
   sentence yet (H2).** The approval-card and status text for every
   mechanism read is written in plain, concrete language that meets
   CLAUDE.md's "explain things simply" bar - `docs/GPU-SUPPORT-RESEARCH-
   2026-09-27.md` section 2.2 already found that an AMD or Intel card
   silently shows as "unused" with no owner-facing reason, which is a real
   communication gap, just not a new one.
4. **`tools/check_parity.py` is clean for everything hardware-adjacent**:
   "No undecided drift" (run fresh for this audit, below).
5. **Tests actually run for this audit**: `test_second_card.py` 273/273,
   `test_hardware.py` 147/147, `test_second_card_suggest.py` 143/143,
   `test_phone_second_card_contract.py` 29/29 - all passing.
   `test_gpu_offload.py` could not be run: it imports `jarvis_models`,
   which is one of the modules that live on the owner's real PC and is not
   in this repository (`docs/ARCHITECTURE.md` §9) - an environment limit,
   not a finding against the code.

## Mechanism 1: the base graphics-card reading - `backend/jarvis_compute.py`

**Detection.** `query_cards()` shells out to `nvidia-smi`, trying three
field sets in order (`FIELDS_FULL`, `FIELDS_OLD`, `FIELDS_OLDEST`) because
an older driver's `nvidia-smi` refuses the *whole* query for one field it
does not recognise (`compute_cap`):

> "`compute_cap` only exists in newer drivers' nvidia-smi (an older one
> refuses the WHOLE query, saying the field is not a valid field to query),
> so a refusal is retried without it, and the generation is then looked up
> by name (COMPUTE_BY_NAME) or left unknown." (`jarvis_compute.py:135-138`)

When even the oldest field set fails, or `nvidia-smi` is not on the PATH,
`_run_smi()` returns `None` and is never allowed to raise
(`jarvis_compute.py:159-172`); `query_cards()` then returns `[]`, and
`plan()` reports it honestly:

> `Plan(... simulated=True, ..., why="no GPU could be interrogated; this
> layout is a guess")` (`jarvis_compute.py:344-347`)

This is the clearest positive finding in the whole audit: `simulated` is a
named, checkable field specifically so nothing downstream can mistake a
guess for a measurement. The module docstring says why in as many words:

> "`simulated` is the honest field. ... it says so, rather than reporting a
> confident layout for hardware nobody looked at." (`jarvis_compute.py:36-39`)

For a driver that reports no compute capability at all, `compute_from_name()`
falls back to a marketing-name lookup table (`COMPUTE_BY_NAME`,
`jarvis_compute.py:147-153`) and returns `None` - never a guessed number -
for anything outside it, which `jarvis_second_card._not_capable()` then
treats as "not capable" rather than silently assuming Turing-or-newer
(`jarvis_second_card.py:832-834`, quoted under mechanism 2).

**Adaptation.** `plan()` decides which card is "primary" by one explicit,
documented rule (`[compute] primary_gpu` in the toml, else the card with a
monitor plugged in, else nvidia-smi's card 0 -
`jarvis_compute.py:259-286`), replacing an older rule ("most free memory")
that put everyday chat on the wrong card once a second GPU existed
(`jarvis_compute.py:19-24`). `Plan.total_mb` is a property, not a stored
field, specifically because an earlier version of `jarvis_models.py` read a
missing attribute inside a swallowed `except Exception: pass` and silently
scored every machine against a fabricated 8192 MB default
(`jarvis_compute.py:83-96`) - a real stale-data bug, already fixed, and
kept as a comment so it cannot be reintroduced by accident. The same
docstring also closes a related hole: a corrupted or injected negative
`total_mb` used to be trusted as a genuine positive measurement because
`0` was the only value treated as "not measured" (`jarvis_compute.py:104-109`).

**Communication.** This module has no UI of its own - `primary()` returns
"the everyday card AND the sentence saying which rule chose it, so a
screen can say why rather than just what" (`jarvis_compute.py:33-34`) - and
every consumer (`jarvis_second_card.py`, `jarvis_hardware.py`) does exactly
that, discussed below.

## Mechanism 2: the second-card feature switches - `backend/jarvis_second_card.py`

**Detection.** `_detect()` builds one row per card with an explicit role
(`primary`/`second`/`unused`) and an explicit, plain-language reason for
every row, never just a boolean. A card that cannot be the second card
says exactly why:

> `"Jarvis could not tell which generation the {name} is (this driver does
> not report it), so it is treated as not capable"` (`jarvis_second_card.py:832-834`)

> `"the {name} is older than Turing (the RTX 20 generation, compute
> capability 7.5), which the second-card features need"`
> (`jarvis_second_card.py:840-842`, with a specific added sentence for the
> Tesla P100 case)

> `"the {name} has {size}, which is not enough: the second-card features
> need at least 10 GB"` (`jarvis_second_card.py:843-845`)

> `"nvidia-smi did not give the {name}'s id, and Jarvis only points work at
> a card by its id"` (`jarvis_second_card.py:846-848`)

**Adaptation - the stale-hardware discipline CLAUDE.md's hardware
paragraph asks for is genuinely followed here, not just claimed.** Turning
a feature on is checked for capability THREE separate times, at three
different moments, not once at card-raise time and then trusted:

1. When the switch is first flipped, `request_change()` calls
   `det = detect(fresh=True)` and refuses outright if not capable
   (`jarvis_second_card.py:2938-2940`) - bypassing the normal 30-second
   cache specifically because this decision must not run on stale data.
2. When the person approves the card, `_decide()` checks again that the
   main switch and every prerequisite feature are *still* on
   (`jarvis_second_card.py:2502-2515`), that "combined" was not turned on
   in the meantime (a real bug the code's own comment says was found and
   fixed on 2026-09-27, `jarvis_second_card.py:2494-2501`), and re-detects
   with `fresh=True` one more time before writing the switch:
   > `if not detect(fresh=True).get("capable"): return _finish(feature, pid,
   > "refused", "the second card is not there any more", rid)`
   > (`jarvis_second_card.py:2516-2517`)
3. `lane_for()`, called on every chat turn that might use the feature,
   re-detects and re-reconciles every single time
   (`jarvis_second_card.py:1794-1795`) rather than trusting a value cached
   from when the switch was turned on.

This means a card physically removed between "switch on" and "the card
approved thirty seconds later" is caught, and a card removed after that is
caught on the very next turn. That is the opposite of the failure pattern
CLAUDE.md's hardware paragraph is warning against.

**Communication.** Every "why" sentence shown to the owner is generated
from the same detection data the code just acted on, never a separate
hand-written string that could drift from it - `_feature_row()`
(`jarvis_second_card.py:2059-2108`) builds one sentence per feature that
covers every real state ("Off. A card to turn it on is waiting for your
answer.", "On, but the main second-card switch is off.", "On, but ... is
not installed yet. Install it (Brain, Models, or 'ollama pull {model}' in a
terminal) and it starts working.") The approval card itself
(`describe_on`/`_describe_combined`) always states what refusing costs
(`jarvis_second_card.py:2536-2559`), per `docs/ARCHITECTURE.md` §3's
`describe()` contract. This all meets CLAUDE.md's "say what to actually
do, concretely" bar directly.

### Finding H1 (real bug, small): a false "has more memory" claim when two capable cards tie

`_detect()` picks exactly one "second" card from however many capable
extra cards exist, sorted `(-total_mb, index)` - biggest memory first, then
lowest index (`jarvis_second_card.py:934-935`). Every OTHER capable card is
then given this fixed reason:

```python
elif c in candidates:
    role, why = "unused", f"capable, but the {second.name} has more memory"
```
(`jarvis_second_card.py:944-945`)

This is unconditionally true only when `second` really does have strictly
more memory than the discarded card. With **two identical capable cards**
(the same model, e.g. two RTX 2060 12 GB, or any tie in `total_mb`), the
sort picks one by index alone, and the discarded twin is told it is unused
because the chosen one "has more memory" - which is false; they are equal.
This is a small thing (it never changes which card is picked, and it is
the internal `_detect()`/`extra_lanes()` groundwork the 2026-09-28
third-card work is explicitly building on top of, per the module's own
"A THIRD CARD" section, `jarvis_second_card.py:165-234`), but it is exactly
the kind of claim `docs/ARCHITECTURE.md` §2 rule 6 forbids: "Nothing is
claimed that is not true." Worth fixing in the same pass that gives a
third card its own real role, since that pass already has to touch this
exact sentence to say something for a genuinely-third card too.

## Mechanism 3: the hardware-preset system - `backend/jarvis_hardware.py`

**Detection**, in the documented trust order (module docstring,
`jarvis_hardware.py:17-31`): Ollama's own `server.log` first (which cards
Ollama itself will actually use, and *why* it dropped one -
`_DROPPED`, `jarvis_hardware.py:92-102`, covering AMD/ROCm drops, old
NVIDIA/AMD drivers, and integrated GPUs it ignores by default); then
`nvidia-smi` for live free memory and the id; then the Windows registry's
64-bit `HardwareInformation.qwMemorySize` for a card's real total memory
regardless of vendor - explicitly NOT `Win32_VideoController`, "whose
memory field stops at 4 GB" (`jarvis_hardware.py:26-27`). The three sources
are joined by name-and-size matching (`_norm`, `_close`,
`jarvis_hardware.py:634-641`), and every card's row says exactly which
sources found it (`"sources": [...]`), so a discrepancy between what
nvidia-smi sees and what Ollama's log says is visible, not merged away
silently.

Vendor detection (`_vendor()`, `jarvis_hardware.py:260-268`) already tells
AMD and Intel cards apart from NVIDIA by name/device-id, purely for
labelling - it does not place a model on either, since (per
`docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` section 2.2, verified against
this same file) `MIN_COMPUTE`, the id-format check and the CUDA env vars
are all NVIDIA-specific.

**Adaptation - the same "do not act on hardware that has moved" discipline
as mechanism 2, expressed as an explicit fingerprint.**
`cards_fingerprint()` hashes the chosen preset's cards by name+size
(`jarvis_hardware.py:877-880`), and `_status()` compares it against the
CURRENT fingerprint on every poll:

```python
stale = bool(ch.get("preset") and ch.get("fingerprint") != fp)
...
"chosen": ch.get("preset") if not stale else None,
"chosen_stale": ("Your cards have changed since you chose a preset, so it is no "
                 "longer used. Choose again." if stale else None),
```
(`jarvis_hardware.py:1280`, `1333-1335`)

The same fingerprint check runs again, independently, at the moment a
tuned model is actually created (`_chosen_role()`,
`jarvis_hardware.py:1474-1488`: `"your cards have changed since the preset
was chosen; choose again"`) - so a hardware change between "choose a
preset" and "press the create-model button" is caught a second time, not
assumed still valid because it was valid once. When the owner picks a
DIFFERENT preset (or clears one) that moves the extra features to a
different card, the second-card master switch is turned back OFF
automatically, on the reasoning that "the owner's yes was for the old
place" (`_master_off_if_moved()`, `jarvis_hardware.py:1403-1420`) - a
concrete example of adaptation erring toward re-asking rather than
carrying an old yes onto new hardware.

**Communication.** `_card_words()` (`jarvis_hardware.py:1163-1177`)
generates one plain sentence per card ("RTX 2080 Super, 8 GB; used by
Ollama through CUDA; a monitor is plugged into it.", "Not used: Ollama's
log does not list it, so Ollama does not use it."), and `_now()`
(`jarvis_hardware.py:1180-1236`) explains what is running right now in the
same style, including a concrete corrective when a model has spilled onto
the processor: "calculated about 0.3 GB over the card, so part of it is
probably on the processor. Press Measure to check." This is a direct,
checked example of CLAUDE.md's "say what to actually do, concretely" bar -
it names the button.

## Mechanism 4: Windows Hello / screen-lock detection - `jarvis-desktop/src-tauri/src/lock.rs`, `jarvis_owner_check.py`

**Detection.** `hello::availability()` asks Windows'
`UserConsentVerifier::CheckAvailabilityAsync` and maps its five-value
result to four owner-facing states - `"ready"`, `"not-set-up"`,
`"blocked"` (switched off by policy), `"busy"` - with a `None` (asking
itself failed) mapped to `"busy"`, never to `"ready"`
(`lock.rs:282-293, 311-319`: "Asking failed: report 'busy' (temporary),
never 'ready'."). `verify()` retries up to twice for transient failures
only - "a person dismissing the prompt is an answer and is never asked
again" (`lock.rs:322-323`) - and falls back from a window-owned prompt to a
plain one if Windows refuses the window-owned form
(`lock.rs:348-372`). On a non-Windows build, `hello::availability()`
returns `None` unconditionally and says so in the comment: "There is no
Windows Hello, so the check is 'unavailable'" (`lock.rs:398-399`). This is
a real, gate-relevant hardware/OS-capability check - `docs/ARCHITECTURE.md`
§3's "no lock, no risky approval" rule depends on it being right, not
optimistic.

**Adaptation.** A PC reported as `"not-set-up"` or `"blocked"` refuses
risky approvals outright rather than falling back to "ask anyway" -
exactly the CLAUDE.md-mandated fail-closed behaviour, and, per
`docs/APPROVAL-GAP-DESIGN.md`/`docs/ARCHITECTURE.md` §3 ("Step 1 is
built"), the check moved to the BACKEND itself in 2026-09-25 so a program
bypassing the desktop app cannot skip it either.

**Communication.** `security-settings.js`'s `helloLine()` turns the four
states into full sentences, each naming the concrete consequence and the
fix:

> `"Windows Hello is not set up on this PC, and a lock is on, so risky
> approvals here are refused and locked windows will not open."` + a link
> to set it up (`security-settings.js:99-103`)

> `"Windows Hello is a Windows feature, and this copy of Jarvis is not
> running on Windows."` (`security-settings.js:110-111`)

This is a strong example of CLAUDE.md's "say what a thing is before using
its name" bar (naming the consequence - "risky approvals ... are refused"
- before or alongside the jargon term "Windows Hello").

## Mechanism 5: the phone's own capability check - `jarvis-client/.../platform/PlatformReadiness.kt`

This is the phone-side analogue of the desktop's preflight self-test, and
it is the strongest single piece of writing found in this audit. Its own
doc comment states the design goal directly:

> "Three of them fail silently and look like something else: cleartext
> looks like a network outage, a denied notification looks like the
> service not running, and Doze looks like the backend going away. Step 0
> exists so those are visible on the device before anything talks to the
> network." (`PlatformReadiness.kt:18-21`)

**Detection** is real platform API calls, never assumption: microphone via
`ContextCompat.checkSelfPermission(..., RECORD_AUDIO)`
(`PlatformReadiness.kt:126-128`), notifications via
`POST_NOTIFICATIONS` gated correctly by SDK version (`Build.VERSION_CODES.
TIRAMISU`, `PlatformReadiness.kt:130-136`), battery-optimisation exemption
via `PowerManager.isIgnoringBatteryOptimizations`
(`PlatformReadiness.kt:120-124`), and the "digital assistant" role via
`RoleManager.isRoleHeld`/`isRoleAvailable`
(`PlatformReadiness.kt:149-160`) - each wrapped in `runCatching { }.
getOrDefault(false)` so a platform quirk cannot crash the one screen whose
job is explaining platform quirks.

**Adaptation** here is about what each finding is graded as, and the
grading is itself argued in the comments rather than asserted: a denied
microphone is `INFO`, not `WARN`, specifically because push-to-talk is
opt-in, "an app that nags for a microphone it is not using is the reason
people refuse the prompt that matters" (`PlatformReadiness.kt:214-219`); a
denied notification permission is `WARN` and counts and shows HOW MANY
approvals are sitting unannounced right now
(`PlatformReadiness.kt:242-251`), replacing an older, more technical
wording the comment quotes and explains was actually hiding the important
fact ("NOT ONE approval is announced", `PlatformReadiness.kt:235-241`).

**Communication** is the explicit two-tier design named in the class doc:
a plain sentence always shown, and the platform vocabulary
(`specialUse`, `POST_NOTIFICATIONS`, `RoleManager.ROLE_ASSISTANT`) moved to
a `technical` field "hidden behind a tap ... because the owner is not
expected to know what `specialUse` is" (`PlatformReadiness.kt:29-35,
163-169`). This is CLAUDE.md's "Explain things simply" section implemented
as a literal two-field data structure, not just a style choice applied
inconsistently.

## Mechanism 6: is the model actually on the graphics card? - `backend/selftest.py` `doctor()`

**Detection** is three read-only GET requests to Ollama
(`/api/version`, `/api/tags`, `/api/ps`) that load nothing
(`selftest.py:506-512`), so "is it on the card?" can be answered "skipped",
truthfully, rather than guessed, when no model happens to be loaded right
now:

> `(SKIP, "whether the model fits on the graphics card", "No model is
> loaded right now, and this test loads nothing. Ask Jarvis anything, then
> run this again to check it.")` (`selftest.py:653-656`)

**Adaptation** here is diagnostic only (this module does not itself change
any setting), but the check computes the real percentage of the model on
the card from Ollama's own `size`/`size_vram` fields
(`selftest.py:665-669`) and grades it PASS/FAIL/WARN with a real threshold
(99%/1%), not a boolean.

**Communication** names the concrete, non-obvious consequence and a
concrete fix rather than a code, e.g.:

> `"{model} is running on the CPU, not the graphics card" / "Every answer
> will be several times slower, and nothing else says so. Usually another
> program is holding video memory, or the model is too big for the card.
> Close games and video tools, restart Ollama, and run this again."`
> (`selftest.py:673-677`)

## Mechanism 7: RAM and disk detection for the optional "big model" lane - `backend/jarvis_big_model.py`

**Detection.** `_memory()` reads real total/available RAM via
`GlobalMemoryStatusEx` on Windows and `/proc/meminfo` on Linux (used for
development, not the shipped target), returning `(None, None)` rather than
raising on any failure (`jarvis_big_model.py:262-292`). `_disk_free()`
wraps `shutil.disk_usage` the same way (`jarvis_big_model.py:295-299`), and
`_drive_type()` best-effort classifies a drive as NVMe/SSD/HDD/USB via
PowerShell, capped at a few seconds, cached ten minutes, "unknown" for
anything it cannot place (`jarvis_big_model.py:306-314`).

**Adaptation** follows the exact same "re-check at decision time, not
just at first ask" pattern as mechanism 2: `request_change()` and
`_decide()` both call `detect(fresh=True)` immediately before acting
(`jarvis_big_model.py:1792, 1829, 1877`), bypassing the 30-second cache
(`jarvis_big_model.py:738-739, 745-746`) at exactly the moments that
matter. `_model_row()` computes whether a model can start **right now**
separately from whether it is merely configured and downloaded
(`can_start_now` vs `usable`, `jarvis_big_model.py:646-720`), so a
temporarily-busy machine is reported as "usable, but not now" rather than
either "ready" or "broken".

**Communication** states the exact numbers and the exact fix:

> `"it needs 24 GB of free memory to start and 18 GB is free. Close
> something big, or wait."` (paraphrased from the pattern at
> `jarvis_big_model.py:714-716`)

> `"{drive} is a SATA SSD drive. colibri reads most of a giant model from
> the disk for every word ..., and your own plan says giant models on the
> SATA drive are too slow: keep it on the NVMe drive."`
> (`jarvis_big_model.py:687-691`)

## Mechanism 8: disk space health - `backend/jarvis_data_health.py`

A small, focused check: free space where Jarvis writes chat history,
memory and the locked backup file, graded WARN below a named threshold and
OK above it, with the concrete stakes stated plainly - "Chat history,
memory and the locked backup file all live here. Free up space soon -
nothing here does it for you." (`jarvis_data_health.py:151-155`). The
module's own docstring commits to never reporting a FAIL for anything it
checks (a self-test guardrail, not covered further here since it is not
principally a hardware-detection module).

## Mechanism 9: Home Assistant - `backend/jarvis_home.py`

Worth stating precisely because "detection" means something narrower here
than for a graphics card: Jarvis does not scan the owner's network for
smart-home devices (that would be exactly the kind of device discovery
rule 2's "no public tunnel, ever" and the project's general no-scanning
posture would forbid). What it detects is whether Home Assistant's own
connection settings (a token, a URL) have been filled in on the PC at all:

> `{"state": "not_set_up", "why": "Home Assistant is not set up on this
> PC"}` (`jarvis_home.py:970`)

Once configured, the ONE weather device Jarvis reads for the morning
briefing and "what's the weather?" is named explicitly by the owner
(`JARVIS_HOME_WEATHER`) or Home Assistant's own default weather entity
(`jarvis_home.py:566, 583-594`) - never auto-picked from a scan of every
entity Home Assistant reports. This is a deliberate, narrower kind of
"detection" than the GPU mechanisms, and it is consistent with
`docs/ARCHITECTURE.md` §4's egress-boundary table, which already documents
Home Assistant reads as "two fixed read-only requests ... never a service
call through `home_control`".

## Desktop and phone UI wording, read directly

`jarvis-desktop/src/hardware-panel.js` (420 lines, read in full) renders
NOTHING of its own invention about the cards or presets - every sentence
comes from the backend's `words`/`why`/`summary`/`notes` fields
(module docstring, `hardware-panel.js:16-19`), and the only strings this
file itself owns are short shared UI labels ("Use this", "Measure",
"Waits for the step before it."), explicitly kept identical to the
phone's copy and checked by `backend/test_hardware.py`
(`hardware-panel.js:35-52`). The same pattern holds on the phone's
`SecondCardPlate.kt`: "All the words about each switch are the PC's own
(`name`, `what`, `why`)" (`SecondCardPlate.kt:39`). This single-source-of-
truth design is why the communication quality found mechanism-by-mechanism
above is not an accident of one screen - it is structural: there is
nowhere in either app for a second, drifted version of a hardware sentence
to be written.

## `tools/check_parity.py`, run fresh for this audit

```
desktop: 132 routes   phone: 112   ported: 111   not porting: 18
still to port: 1   not the backend's: 2   planned (backend first): 0
No undecided drift.
```

The one "still to port" route (`/api/retrieve`) and the one phone-only
route (`/api/notifications/watch`, the smartwatch setting) are both
unrelated to hardware detection and both already explained in
`docs/ARCHITECTURE.md` §8. Nothing hardware-adjacent is drifted between
the two apps.

## Verdict

**Detection: solid.** Every mechanism found fails to a named, honest state
rather than a guess or a crash, and the harder cases (an old driver that
refuses a whole nvidia-smi query, a PC with no Windows Hello, a phone with
notifications denied, a machine with no free RAM right now) are handled
explicitly, not left to an exception handler.

**Adaptation: solid, one small wording bug found (H1).** The specific
failure mode CLAUDE.md's hardware paragraph warns about - acting on
hardware information that is no longer true - is guarded against
deliberately and repeatedly (`detect(fresh=True)` at every decision point,
in two independent modules; an explicit cards-fingerprint staleness check
in a third) rather than merely claimed. The one bug found (H1) never
causes an unsafe action; it produces a false sentence in a tie case.

**Communication: strong, structurally so.** Both apps render the backend's
own words rather than inventing their own, so the writing quality found in
one place (the approval cards, the phone's Checks screen, the Windows
Hello lines) is representative of the whole surface rather than a good
screen next to a neglected one. The one communication gap worth naming
(H2) is already known and already scoped in `docs/GPU-SUPPORT-RESEARCH-
2026-09-27.md`, not a new finding.

## Prioritized findings, for the owner to decide on

1. **H1 (small, real bug).** `jarvis_second_card.py:944-945`: when two
   capable non-primary cards have exactly the same memory, the discarded
   one is told "capable, but the {second card} has more memory," which is
   false in a tie - they are equal. Fix: say "at least as much memory" (or
   name the actual tie-break, e.g. "was found first"), rather than
   asserting an inequality that may not hold. Natural to fold into the
   in-flight third-card work, since that work already has to give a
   genuinely-discarded third card its own honest sentence.
2. **H2 (communication gap, already scoped, not new).** An AMD or Intel
   card today shows as "unused" with a generic reason
   (`jarvis_hardware.py`'s `_unused_row()`) rather than the vendor-specific
   plain sentence `docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` recommendation
   4 already proposes ("Jarvis sees an Intel Arc card here; Ollama cannot
   use it yet"). Sized there as XS, since the vendor detection
   (`_vendor()`) already exists - only the sentence is missing.
3. **Not a bug, an honest known limit worth restating here:** every
   hardware mechanism that assumes a second card (`jarvis_second_card.py`,
   the `combined` mode, `jarvis_hardware.py`'s presets) is measured and
   tested only against a card that is not yet installed
   (`docs/MODEL-TOPOLOGY.md`'s own history, `jarvis_second_card.py:220-226`
   on "combined" specifically: "Real speed for splitting a model across
   even two cards is still unmeasured, because the second card is not
   installed"). Every approval card this audit read says this in words at
   the point of decision, so the limit is communicated, not hidden -
   listed here only so it is not mistaken for something this audit missed.
4. **Worth a look, not verified as a bug here:** this audit did not read
   `jarvis_profiles.py` (the VRAM/KV-cache arithmetic `jarvis_hardware.py`
   calls into) in full. `docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` section
   2.2 already flags one line there (`route=row["route"] or "CUDA"`) as
   worth checking for a silent CUDA-only assumption once a non-NVIDIA card
   ever reaches that stage - carried forward here rather than re-verified,
   since re-verifying it was out of this audit's scope.
