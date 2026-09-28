# A third graphics card, and AMD/Intel support - research (2026-09-27)

Research and design only. Nothing in the repository was changed for this
report. Part 1 is read straight from the real source (`backend/jarvis_second_card.py`,
`backend/jarvis_hardware.py`, `backend/rebuilt/jarvis-framework.toml`,
`docs/SECOND-CARD.md`, `docs/MODEL-TOPOLOGY.md`) at HEAD `d68f7b24`
(2026-09-27), line numbers given so it can be checked. Part 2 is web research,
clearly marked - `ollama.com` and its docs subdomain are blocked from this
environment (the same limit `jarvis_second_card.py`'s own comments already
note about `ollama.com`/`huggingface.co`), so it comes from search-result
summaries, not a page I read myself, and is not verified against this repo.

---

## Part 1: a third graphics card

### 1.1 How today's design actually works (verified against the source)

**A card is identified by its `nvidia-smi` id (`GPU-...`), never a number.**
The module docstring explains why (CUDA's own device order can differ from
`nvidia-smi`'s), and `lane_env()` enforces it: the uuid argument is checked
against `re.fullmatch(r"GPU-[0-9A-Fa-f-]{8,64}", ...)` (line 1065) and a
non-matching value raises `ValueError`.

**Ollama is told which card runs which model with `CUDA_VISIBLE_DEVICES`,
one separate `ollama serve` process per lane - not `OLLAMA_SCHED_SPARE`.**
That env var does not appear anywhere in this file. The real mechanism
(`lane_env()`, lines 1041-1112):

- a second, independent `ollama serve` is started, listening on its own
  loopback port (11435 for the feature lane, a different one for
  "combined");
- `CUDA_VISIBLE_DEVICES=<uuid>` (or, for "combined", a comma-joined list of
  uuids - see below) plus `CUDA_DEVICE_ORDER=PCI_BUS_ID` pin that process to
  exactly the card(s) named;
- `OLLAMA_VULKAN=0` is set too, because Ollama's Vulkan route is on by
  default and **ignores** `CUDA_VISIBLE_DEVICES` (the module docstring cites
  `envconfig/config.go:234`, `EnableVulkan` default `true`) - without it the
  pin would not actually be a pin.

**The "pin" the owner runs by hand** (`pin_command()`, lines 1845-1860) is a
*different* pin: it sets the same two variables, but for the owner's Windows
user account, so the **everyday** Ollama (the one running `jarvis-primary`
chat) only ever sees the primary card. Jarvis's own second-card process is
never affected by it - it gets its environment from `lane_env()`, not from
the user's persistent settings.

**The UI presents exactly two named roles - `detected.primary` and
`detected.second` - as singular JSON keys, not a list.** `status()`
(line 2009) does:

```python
detected = {k: det[k] for k in ("capable", "why", "primary", "second", "cards")}
```

`detected["cards"]` *is* already a list (every card nvidia-smi/the registry
found, each with a `role` string) - see 1.2. But every consumer that
actually places a model reads the singular `det["primary"]` / `det["second"]`
/ `det["_second"]`, not that list.

### 1.2 Two cards, hardcoded - or N cards capped by the UI/toml? Checked against the real code

**Verdict: the low-level plumbing is closer to N-ready than the role model
and the settings/API shape are.** Three different layers, three different
answers:

1. **The settings file (`jarvis-framework.toml`) is a single scalar block,
   not list-shaped at all** - not even "a fixed pair of keys per card". The
   `[second_card]` section (`backend/rebuilt/jarvis-framework.toml:646-657`)
   has exactly `port`, `keep_alive`, `flash_attention` - one instance,
   for the one lane process this module ever starts. There is no per-card
   table today; card *selection* happens entirely at runtime, by detection
   (`[compute] primary_gpu`, or "whichever card the monitor is on", or "the
   first `nvidia-smi` lists" - `docs/SECOND-CARD.md` lines 26-30), not by
   naming cards in the toml. Adding a third lane's own settings (its own
   port, its own `flash_attention` override) needs this to become an
   array-of-tables.

2. **Detection already builds a full list of every card, each with a `role`
   string** (`_detect()`, lines 807-856) - but the *policy* picks exactly
   one "second" candidate and discards the rest:

   ```python
   if candidates:
       second = sorted(candidates, key=lambda d: (-d.total_mb, d.index))[0]
   ...
   elif c in candidates:
       role, why = "unused", f"capable, but the {second.name} has more memory"
   ```

   A third Turing-or-newer, 10 GB+ card sitting in the PC today is already
   *detected* and already correctly labelled "capable" - and then thrown
   away with "capable, but the [other] card has more memory." This is the
   real shape of "two cards, hardcoded": not a literal `2` anywhere, but a
   policy of "primary, plus at most one lane" baked into the sort-and-take-
   first line above.

3. **The low-level env-var plumbing already tolerates more than one id.**
   `lane_env()`'s `uuid` parameter is explicitly documented as "a single card
   id ... or a sequence of them" (lines 1049-1053), used today by "combined"
   mode: `CUDA_VISIBLE_DEVICES = ",".join(ids)` (line 1080) already
   comma-joins an arbitrary number of ids, and `OLLAMA_SCHED_SPREAD=1`
   (`spread=True`, lines 1098-1104) already tells Ollama's own scheduler to
   use every id listed rather than guessing. **This part would not need to
   change for a third card.**

**Where the code literally assumes exactly two**, confirmed by reading it:

- `_combined_rows()` (lines 950-957) returns a 2-tuple, `(primary row,
  second row)`, found by `next(r for r in rows if r["role"] == "primary")`
  and the same for `"second"` - there is no third role to find.
- `_combined_capable()` and `_reconcile_combined()` destructure that pair
  directly - e.g. `ids = (prim["uuid"], second["uuid"])` (line 1514) - and
  `COMBINED_MIN_TOTAL_MB` (line 337) is arithmetic over the **sum of
  exactly two** `total_mb` fields (the comment at lines 307-324 adds "room,
  2080 Super" + "room, 2060" as two named terms, not a loop).
- Exactly two module-level singleton state machines exist - `_LANE` and
  `_COMBINED_LANE` (lines 1420-1421) - each a `_LaneProcess` with its own
  `state`/`uuid`/`port`. There is no data structure for "however many lanes
  exist"; a third, independent lane needs a third singleton, or the two
  rewritten as a dict/list.
- Every feature's `"what"` string (`FEATURES`, lines 277-296) says "the
  second card" as a fixed phrase, and `_what()` (lines 1933-1938) only ever
  substitutes it for "beside chat, on the same card" (the single-card preset
  case) - there is no third phrasing.
- The "combined" mode's own name, **"One bigger model on both cards"**, is
  two-card by name as well as by the arithmetic above.

**One thing worth correcting, plainly, because it is the example the brief
itself suggested as the biggest risk:** `pin_command()` is *not* actually
two-card-shaped. It takes one `primary_uuid` and emits one
`CUDA_VISIBLE_DEVICES=<that id>` - its job is "keep the everyday Ollama off
every card Jarvis wants for lanes," which already holds for any number of
extra cards without changing a single line. The real risk is elsewhere (1.4).

### 1.3 A concrete design for a third card

**Settings file** - `[second_card]` becomes an array-of-tables, one entry
per lane the owner has actually assigned a role to, e.g.:

```toml
[[second_card.lane]]
role = "second"
port = 11435
keep_alive = "30m"
flash_attention = "auto"

[[second_card.lane]]
role = "third"
port = 11436
keep_alive = "30m"
flash_attention = "auto"
```

The per-owner switches file (`second-card.json`) needs a matching change:
today `features: {feature_id: bool}` says only *whether* a feature is on;
with more than one lane it has to say **which lane**, e.g.
`features: {feature_id: {"enabled": bool, "lane": "second" | "third" | null}}`.
That is a new, real decision, not a formatting change - see 1.4.

**`GET /api/second-card`'s JSON** - `detected.primary` / `detected.second`
(singular) becomes `detected.primary` / `detected.lanes: [...]`, a list of
however many capable extra cards exist (0, 1 or 2 today; more later if the
PC ever has more). `detected.cards` already carries every card with a role
string (1.2), so this is a matter of *stopping at* that list instead of
collapsing it back down to one name - every call site that currently reads
`det["second"]` or `det["_second"]` (roughly a dozen, by function name:
`_wanted`, `_feature_active`, `_reconcile`, `lane_for`, `main_pin`, the
`status()` body itself, `_detect_preset`'s mirror of all of these) needs to
either loop over `lanes` or take the specific one a feature was assigned to.

**Approval-card wording** - this is the part that most directly matters for
this project's "no approve-all" rule. With one extra card, "Turn on
'Longer conversations'" is unambiguous: there is only one place it could
run. With two, the *same* switch is ambiguous unless the card names the
physical GPU - so turning a feature on has to become a genuine two-part
decision: **which card**, then **turn it on there** - never a default
("the biggest one" or "the first one found") standing in for a choice the
owner has to make once. That reads naturally as one approval card that
lists the feature, the chosen card's name, its memory and the model, in
the same style `_combined_status()`'s `why` sentences already write
(e.g. "Working: qwen3:8b split across the RTX 2080 Super and the RTX 2060
12 GB, with room for 32,768 tokens") - just with a real choice behind it
instead of an assumed one.

**"Combined" with three cards** is a separate, smaller question: the
env-var plumbing (`lane_env`'s sequence-of-ids, `OLLAMA_SCHED_SPREAD`)
already generalises to three, so "one bigger model split across all three
cards" is mostly `_combined_rows()`/`_combined_capable()`/
`COMBINED_MIN_TOTAL_MB` becoming a loop over a list instead of a 2-tuple,
plus renaming the feature ("...on both cards" no longer fits). That part
alone would be an **M**, not an **L** - it rides on plumbing that is
already there.

### 1.4 Size and biggest risk

**Size: L.** Not because any one function is hard, but because the
singular-primary/singular-second pattern (1.2's third bullet list) is
repeated across the settings file, the switches file, the status JSON, a
dozen call sites in `jarvis_second_card.py`, `jarvis_hardware.py`'s own
mirror of "primary/lane" detection, **both** apps' Settings/Brain screens
(which today render exactly one main switch plus five feature switches,
with no card picker anywhere), the approval-card copy, `docs/SECOND-CARD.md`
and `docs/JARVIS-API.md`, and this project's own required feature audit
(bug audit + `tools/check_parity.py` + docs) that CLAUDE.md asks for every
new feature. Each piece is small; there are a lot of pieces, and they all
have to agree on the same new shape.

**Biggest risk - not the one the brief itself guessed.** The pin command
(1.2, last paragraph) is not the danger. The real risk is the **auto-pick
policy in `_detect()`**: it already silently discards a second capable card
today (line 836's "capable, but the [other] card has more memory"), and
if that policy is simply *loosened* rather than *replaced with an owner
choice* - e.g. "pick the two biggest candidates automatically" - Jarvis
would be choosing which physical card runs which feature without the owner
ever naming it, which is exactly the kind of default this project's own
rules forbid ("no approve-all"; "naming a specific card for a specific role
is a decision, not a default," as the brief itself put it). The safe design
is more approval cards, not a smarter auto-pick - which is more UI and more
wording, which is most of why this is an **L**, not a quick constant change.

---

## Part 2: AMD and Intel GPU support ("as best as you can")

**Everything in this part is external research, not read from
`ollama.com`'s own pages (blocked from this environment) and not verified
against this repository beyond the codebase's own detection strings quoted
in 2.2. Treat it as a starting point, not a confirmed fact.**

### 2.1 Does Ollama itself support AMD and Intel today?

**AMD: yes, in mainline Ollama, via its ROCm backend, and Windows is
described as officially supported (not merely a preview) as of the ROCm
v7/HIP7 driver stack.** Search results describe RDNA3 (RX 7000-series,
`gfx1100`/`gfx1101`/`gfx1102`) and AMD's Instinct data-centre cards
(MI200/MI300) as well supported, RDNA4 (RX 9000-series) as newly supported
with ROCm 7.2 (reported March 2026, "the first release with official RDNA4
... support and out-of-the-box Ollama/LM Studio/llama.cpp/vLLM parity,
shipped as one installer for both Windows and Linux"), and older
RDNA1/2 and even some GCN-generation cards (`gfx1010`...`gfx1153`) as
listed but needing more manual setup (an unofficial override,
`HSA_OVERRIDE_GFX_VERSION`, is a common community workaround for a card
whose exact chip ROCm does not explicitly list, not an official guarantee).
Multiple AMD GPUs are handled with `HIP_VISIBLE_DEVICES` or
`ROCR_VISIBLE_DEVICES` (the ROCm analogues of `CUDA_VISIBLE_DEVICES`), and
per-GPU generation overrides use a **1-indexed** suffix,
`HSA_OVERRIDE_GFX_VERSION_1`, `_2`, ... (not 0-indexed like the device-list
variables - a real gotcha if this is ever wired up, worth writing down
before anyone copies the pattern from `CUDA_VISIBLE_DEVICES`).

**Intel: no, not in mainline Ollama, and not close, as of this research.**
Every attempt found is a long-open, unmerged pull request or a standing
feature request against `ollama/ollama`: issue #8414 ("Support Intel
GPUs"), issue #10244 and #16930 (both proposing a SYCL/oneAPI backend),
and pull requests #11160 and the newer #17621 - the search result on #11160
specifically reports it as `mergeable=false` with conflicts across
`discover/types.go`, `envconfig/config.go` and others, i.e. stalled, not
merged. What exists and works today is **Intel's own separate build**:
`intel/ipex-llm`'s "Ollama Portable ZIP", a pre-compiled binary Intel ships
itself with its IPEX-LLM/oneAPI stack baked in - a different program that
happens to share Ollama's name and command-line shape, not a code path in
the project everyone means by "Ollama." Community forks
(`ollama-intel-arc`, `ollama-intel-sycl`) exist for the same reason: there
is nowhere upstream to send the fix.

### 2.2 What this codebase would need to change for a mixed rig

Every one of these is a real, cited call site, not a guess:

- **Detection is NVIDIA-only, by tool choice.** `_cards()`/`_primary()`
  (`jarvis_second_card.py` lines 453-466) delegate to
  `jarvis_compute.query_cards`/`compute.primary`, and `_smi_apps()`
  (line 469) calls `compute._run_smi([...])` directly - `nvidia-smi`, named
  in the module's own docstring throughout. AMD's equivalent tool is
  `rocm-smi` (or `amd-smi` on newer ROCm); nothing in this file calls either.
- **The capability floor is a CUDA-only number.** `MIN_COMPUTE = 7.5`
  (line 222) is a CUDA "compute capability" - a number AMD and Intel cards
  do not have at all (AMD uses `gfx####` architecture codes; Intel uses its
  own Xe/Arc generation naming). `_not_capable()`'s first branch, "this
  driver does not report which generation it is, so it is treated as not
  capable" (lines 763-764, triggered when `cc is None`), is exactly what
  would fire for every AMD or Intel card today - not a bug, just proof
  there is no code path for them.
- **The id format check is NVIDIA's own id shape.** `lane_env()`'s
  `re.fullmatch(r"GPU-[0-9A-Fa-f-]{8,64}", ...)` (line 1065) is the
  `nvidia-smi` `GPU-<uuid>` format specifically. A ROCm device id or an
  Intel Level-Zero id would not match this pattern, so `lane_env()` would
  raise `ValueError` for one today, by construction - it is not merely
  untested, it is actively refused.
- **The env vars set are CUDA's.** `CUDA_VISIBLE_DEVICES` /
  `CUDA_DEVICE_ORDER` (lines 1080-1081) only steer Ollama's CUDA route.
  Telling: `lane_env()` already **strips** `HIP_VISIBLE_DEVICES`,
  `ROCR_VISIBLE_DEVICES` and `GPU_DEVICE_ORDINAL` from anything inherited
  (lines 1074-1076), on purpose, so a stray AMD setting on the PC cannot
  quietly leak into Jarvis's own NVIDIA-only lane. That is correct for a
  CUDA-only lane, and it also confirms there is no partial AMD path
  anywhere in this file to build on - it is actively scrubbed, not merely
  absent.
- **`OLLAMA_VULKAN=0`'s reasoning is NVIDIA-specific too.** It exists
  because Ollama's Vulkan route ignores `CUDA_VISIBLE_DEVICES` (module
  docstring, lines 133-141: "The second card is always an NVIDIA card ...
  so CUDA is the route it uses"). If the second card is AMD or Intel and
  Ollama's ROCm/SYCL route is what actually reaches it, this line's
  premise does not hold - it would need its own, separately-reasoned
  vendor-routing logic, not a copy-paste of this one.
- **One module already sees vendor - but only to label it, not to use it.**
  `jarvis_hardware.py` (a newer, separate module) already tells AMD and
  Intel cards apart by name/device-id (`_vendor()`, lines 260-268: checks
  for `"AMD"`/`"RADEON"`/`VEN_1002` and `"INTEL"`/`VEN_8086`/`" ARC"`) and
  already parses Ollama's own log for why it dropped a ROCm device or an
  old AMD/Intel driver (`_DROPPED`, lines 92-101: "Ollama dropped it: its
  AMD (ROCm) build has no support for this card's chip", etc.). That is
  read-only, informational groundwork for the "Hardware and models" status
  page to explain *why* a card is not used - it does not place a model on
  one. **Not verified here:** whether `jarvis_profiles.py`'s model-fit
  arithmetic (VRAM/KV-cache budgeting) branches on vendor at all, or
  assumes CUDA numbers throughout once a card reaches that stage - I did
  not read that file for this report, and the one line I did see
  (`route=row["route"] or "CUDA"`, `jarvis_hardware.py` `_detect`) defaults
  an unlabelled route to `"CUDA"`, which is worth checking before assuming
  the planning layer is vendor-safe just because the detection layer is
  vendor-aware.

### 2.3 The honest verdict

**Not a small, wording-level change for either vendor - and the two vendors
are not even the same size of problem.**

**AMD is a genuinely large rewrite of the hardware-detection and lane
layer, but the target is real and stable to build against.** It needs: a
second detection path (`rocm-smi`/`amd-smi`, parsed the way `nvidia-smi` is
parsed today), a parallel capability floor (which RDNA/GCN generations
give the fast, quantised llama.cpp kernel path AMD's driver stack cares
about - not the same arithmetic as Turing's `compute_cap >= 7.5`, and not
researched here at all), a parallel id-format check, a parallel
`lane_env()`-equivalent using `HIP_VISIBLE_DEVICES`/`ROCR_VISIBLE_DEVICES`
(mind the 1-indexed `HSA_OVERRIDE_GFX_VERSION_N` gotcha, 2.1), and - this is
the part `docs/MODEL-TOPOLOGY.md` shows the scale of - **an entirely new
round of the same VRAM/KV-cache/flash-attention research this project
already did once for Turing**, because none of that research's numbers
(the `q8_0`-needs-flash-attention finding, the per-token KV byte counts,
the empty-gap figures) are known to hold on AMD's ROCm build of llama.cpp.
Skipping that research and just wiring the env var would repeat exactly the
mistake `MODEL-TOPOLOGY.md`'s own history warns about ("Everything anyone
has planned on this machine about context has been theory").

**Intel is not really "support Ollama on Intel GPUs" today - it is
"point the owner at a different program Intel ships."** With no backend
merged upstream (2.1), building against Intel means building against
`intel/ipex-llm`'s own fork, whose command surface, update cadence and
compatibility with this project's `/api/*` assumptions are controlled by
Intel, not by Ollama's maintainers or by this project. That is a materially
bigger commitment than "AMD support," and arguably not "Ollama support" at
all in the sense the rest of this codebase means it.

### 2.4 Rules check

**Rule 1 (local-first) holds regardless of vendor.** ROCm and Intel's
oneAPI/SYCL/Level-Zero are both on-device compute backends, exactly like
CUDA - nothing about running an 8B model through a different vendor's
kernels sends anything off the PC. Nothing here has anything to do with
where a model's weights or the conversation go.

**One thing worth telling the owner, flagged plainly rather than
overclaimed:** installing AMD's or Intel's own graphics driver package
(separate from ROCm/oneAPI/Ollama itself) commonly bundles that vendor's
own control-panel app (AMD Software: Adrenalin; Intel Graphics Software),
which - like NVIDIA's own GeForce Experience - typically offers an optional
telemetry/account sign-in step during setup. This is not verified against
either vendor's current installer for this report, and it is not something
this codebase would cause or control either way - but it is the same kind
of thing the owner already has to decline on NVIDIA's installer today, and
worth a plain heads-up before buying a second card from a different vendor
on the strength of this document alone.

**Rules 2 and 4 are unaffected by vendor** - the design in Part 1 (an
explicit, named-card approval card for every feature and every lane) is
exactly as easy or as hard to keep on an AMD or Intel lane as on an NVIDIA
one; nothing about a different vendor's env vars changes who is asked or
when.

---

## Recommendations

1. **Do the settings/status data-model change first, on its own** (the
   singular `primary`/`second` -> a list of assigned "lanes", 1.3) -
   **S.** Every later change (a third NVIDIA card, AMD, Intel) repeats the
   same singular-key pattern in a dozen places today; deciding the new
   shape once, and moving the *existing* two-card design onto it before
   adding a third card, means the third card's own work is additive
   instead of another rewrite of the same spots.

2. **Build the third NVIDIA card** on top of that shape - **L** (1.4),
   with the per-feature "which card" approval card (1.3) as the one piece
   that must not be skipped or defaulted. The "combined" mode's own
   extension to three cards can ship separately and later, as an **M**
   (1.3, last paragraph) - its plumbing is already closer to ready.

3. **AMD (ROCm) support - only as a full research-then-build project, not
   a quick env-var change** - **L**, and the research half (2.3's "new
   round of the Turing-style investigation") should be sized and scheduled
   like `docs/MODEL-TOPOLOGY.md`'s own history, not folded into the coding
   estimate. Do not wire `HIP_VISIBLE_DEVICES` before that research exists;
   it would ship numbers nobody has checked, exactly the mistake this
   project has already written down once as a lesson learned.

4. **Intel - do not build a lane for it now.** The cheapest honest step is
   near-free: let `jarvis_hardware.py`'s already-working vendor detection
   (2.2) say so plainly on the "Hardware and models" screen ("Jarvis sees
   an Intel Arc card here; Ollama cannot use it yet") instead of the card
   silently showing as unused with no reason - **XS**, since the detection
   and the wording pattern for "why a card is not used" already exist.
   Revisit building anything further only if Ollama merges a real SYCL
   backend upstream (2.1); until then, the alternative is depending on a
   different vendor's own fork of Ollama, which is a bigger and different
   decision than "supporting Intel," and should be named to the owner as
   exactly that if it ever comes up again.
