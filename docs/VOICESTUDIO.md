# VoiceStudio: a separate voice program Jarvis may call

**Built 2026-11-04.** The owner-approved Q3/Q4/Q5 (forwarded 2026-11-04) are
implemented here as a **client, a launcher, a measurement harness and this
page** - and nothing else yet:

- `backend/jarvis_voicestudio.py` - the client. Standard library only. It
  speaks HTTP to `127.0.0.1:11439` and never to anything else.
- `tools/voicestudio_sidecar.ps1` - the launcher: `-Start`, `-Stop`,
  `-Status`, pinned to the RTX 2080 SUPER, refusing to start while the card
  has less than a measured amount free.
- `tools/measure_voicestudio.py` - re-reports the measured facts and refuses
  to redo the heavy work.
- `backend/test_voicestudio.py` - 125 checks against a real `http.server` on
  an ephemeral loopback port.

**Not built yet, and said plainly:** Jarvis does not speak with VoiceStudio,
there is no Settings switch and no route. `jarvis_speech.py` does not import
the client. That wiring plus its one approval card is the **next slice**.
What exists today is the whole external side of the join, proved.

---

## 1. What this is, and the one rule that keeps the licence clean

VoiceStudio is an **AGPL-3.0** program by other people. Jarvis is MIT. The two
must never become one program:

| Arrangement | Verdict |
|---|---|
| VoiceStudio runs as a **separate, unmodified program** on this PC; Jarvis sends it HTTP requests on `127.0.0.1` and reads audio back | **Clean.** Nothing is conveyed and nothing is derived. AGPL SS2 explicitly permits running the unmodified program. |
| Its Python package imported **into** the Jarvis backend process | **Never.** That is one combined work; the whole of Jarvis would have to be AGPL-3.0. |
| Its source files copied into this repository | **Never.** Publishing them is conveying, and they cannot be labelled MIT. |

So this repository contains **no VoiceStudio code, binary or weight**, and
`backend/test_voicestudio.py` proves the client's only imports are the Python
standard library plus this repository's own `jarvis_local_http` and
`jarvis_framework`. `THIRD-PARTY-NOTICES.txt` names VoiceStudio as an external
program, not a bundled part.

**The rule in one line:** the program is the owner's, installed outside the
repository; Jarvis only ever has a socket to it.

---

## 2. Where it runs: the port and the card

| Thing | Value | Why |
|---|---|---|
| Address | **`127.0.0.1:11439`**, loopback only | Next free number in Jarvis's own local block (11434 everyday, 11435 second card, 11436 third card, 11437 picture reader). Not VoiceStudio's own `3900`, so the owner's own VoiceStudio window can run beside it. The measured backend listened on `127.0.0.1` only - no `0.0.0.0`, no LAN socket. |
| Card | **RTX 2080 SUPER, by UUID** | The RTX 2060 holds the everyday model and its lane must never be touched. `CUDA_VISIBLE_DEVICES` is set to the 2080's **UUID**, not an index, because indices can reorder. |
| The card's identity | `nvidia-smi -L` | `GPU 0: NVIDIA GeForce RTX 2060 (UUID: GPU-...)` / `GPU 1: NVIDIA GeForce RTX 2080 SUPER (UUID: GPU-...)`. The launcher reads this itself and refuses if it cannot find exactly one card whose name contains `2080`. It never falls back to the other card. |
| Free-memory floor | **5,200 MiB** | A measured floor, not a round guess - the arithmetic is in the launcher beside the constant. It refuses the state the measurement called contention and says which lane is in the way. |

### The contention verdict this design obeys

The measurement ran VoiceStudio **beside Jarvis's own two resident models**
(`qwen3:8b` on one card, `qwen3.5:4b` on the 2080). It worked, but only by
oversubscribing the 8 GB card:

- the 2080 had **2,245-2,335 MiB free** before the start and **382 MiB free at
  the box's peak**;
- Windows' driver **paged about 1.9 GB** of the model into system RAM
  (VoiceStudio's `cudaMemGetInfo` believes shared memory is free, so it loaded
  anyway);
- the process's private memory was **6,721 MB** with a model resident against
  **1,698 MB** idle.

**Verdict: CONTENTION.** So VoiceStudio is **demand-only and serialised**:
started when it is needed, never on boot, never kept resident beside Jarvis's
own models. The launcher enforces it with the floor above, and `-Stop` releases
the card again (VoiceStudio also has a 900 s idle unload by its own setting,
but that path was **not observed** during the measurement - `-Stop` is the one
that is proved).

---

## 3. The measured numbers

Every figure is from `VOICESTUDIO-EVAL/MEASURE/RESULTS.md` (2026-11-04, this
PC, after the deploy). The client carries the same numbers as constants, and
`tools/measure_voicestudio.py` prints them labelled `MEASURED`, so a report
never copies a number by hand.

| Fact | Measured | Note |
|---|---|---|
| First start -> `/health` 200 | **32.06 s** | cold database migrations |
| Later start -> `/health` 200 | **16.66 s** | database already migrated |
| Model preload after health | **8.92 s** | background load, after health |
| First ever speech call | **267.97 s** | includes **3.043 GB** of weights downloaded |
| Warm speech call | **1.70-1.98 s** for ~2.5 s of audio | real-time factor **0.66-0.79** |
| After a restart, first call | **27.41 s** | reload, no download |
| Resident VRAM | **1,945.3 MB** app-reported | nvidia-smi delta **~1,750-1,900 MiB** |
| Idle RAM (no model) | **546.2 MB** working set | 1,698 MB private |
| Resident RAM (model loaded) | **2,287 MB** working set | 6,721 MB private, incl. paged GPU memory |
| Weights on disk | **3.043 GB** | never shipped, never fetched by Jarvis |
| Egress observed | **Hugging Face only** | no telemetry, update or account calls seen |
| Disk for the measurement install | **11.61 GB** | deleting `MEASURE/` undoes it |

**Two start-up races the client handles, both measured:**

1. `/health` answers **503 with a step and a label** while it starts (usually
   `ml_imports`). `health()` reports "starting, step X" - never "failed".
2. A request fired **the instant** `/health` turns 200 can hit a half-imported
   `transformers` and answer **400 `cannot import name 'AutoFeatureExtractor'`**.
   The **next** request succeeds. `synthesize()` retries that one shape a
   bounded three times and says so in its words.

---

## 4. Licensing: what each engine and voice is

The client's dossiers carry one field, `license_class`, and it may only ever
hold **two** values:

| `license_class` | Meaning |
|---|---|
| `commercial_ok` | Apache-2.0 / MIT weights whose terms were **actually reviewed**. |
| `personal_non_commercial_only` | Everything else. Personal use only - this project's **Rule 5** (non-commercial build). |

**No engine is `commercial_ok` today, and that is on purpose.** VoiceStudio's
own inventory says *"No record currently makes that claim"* - its 70 model
records are labelled `unreviewed`, and model-card labels such as MIT and
Apache-2.0 "remain upstream metadata until the relevant weights, conversion and
component terms are checked". A client that called them commercial because the
label said MIT would be guessing with someone else's licence.

The two **model** licences that matter for speech, and that are accepted once
by the owner in VoiceStudio's own terms:

| Repository | Recorded terms | Class |
|---|---|---|
| `k2-fsa/OmniVoice` | CC-BY-NC (version unspecified); Higgs Audio 2; Meta Llama 3 | `personal_non_commercial_only` |
| `eustlb/higgs-audio-v2-tokenizer` | no licence found in its metadata (`NOASSERTION`) | `personal_non_commercial_only` |

**Weights are never shipped and never redistributed.** The AGPL does not cover
them: they have their own terms, and several forbid redistribution. Jarvis
neither ships them nor downloads them - the owner's VoiceStudio does, on its
first speech call, under the owner's own acceptance.

### The first run: the licence gate (403)

Until both are accepted, **every** speech request answers `403`
`model_licence_required`. `first_run_license_gate()` recognises it and returns
plain words naming both repositories, their terms, and the exact commands -
with the fingerprint **read from the server**, not typed:

```powershell
curl.exe -s "http://127.0.0.1:11439/models/licenses/acceptance/k2-fsa/OmniVoice"
curl.exe -s -X POST "http://127.0.0.1:11439/models/licenses/accept" -H "Content-Type: application/json" -d "{\"repo_id\": \"k2-fsa/OmniVoice\", \"fingerprint\": \"<from the first answer>\", \"accepted\": true}"
```

**The client never runs the second one.** Accepting a licence is the owner
saying yes to someone else's terms; a program that clicked it for him would be
the one thing this feature must not do. The test suite asserts the client never
posts to `/models/licenses/accept`.

---

## 5. The switch: off by default, and off for a reason

```toml
[voicestudio]
enabled = false
```

It ships `false` in `jarvis-framework.toml` (both this repository's template
and the published base). While it is false, `synthesize()` refuses and says the
switch's name; the **read-only** questions still answer, because asking is not
using.

Turning it on is a **hand edit for now**: there is no screen and no route in
this slice - the same first-slice position `[vault_organizer]` took. And
turning it on alone changes nothing you would hear, because nothing calls the
client yet. The next slice wires the voice and adds the one-card Settings
switch; only then does ON mean "Jarvis may speak with it".

---

## 6. How to run it (the owner's steps)

All four commands are **one line each**, ready to paste into PowerShell.

```powershell
# 1. Is it running, what does it hold, how much card is free? (read-only)
powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Status
```

```powershell
# 2. Start it. It pins the 2080 SUPER, refuses below 5,200 MiB free, and waits for /health.
powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Start
```

If it refuses for memory, it prints **one** command that unloads the 11435
lane's own model. **You** run that one; the launcher never unloads anything.
The 11436 lane (the RTX 2060) is never named in a command and never touched.

```powershell
# 3. Re-report the measured facts (read-only; never redownloads or reinstalls)
py -3 -B tools\measure_voicestudio.py
```

```powershell
# 4. Stop the process this script started, and release the card
powershell -NoProfile -ExecutionPolicy Bypass -File tools\voicestudio_sidecar.ps1 -Stop
```

Where things live: `-VoiceStudioPath` defaults to `D:\VoiceStudio` (the folder
holding `backend\main.py` and `.venv\Scripts\python.exe`); its data and its
weights default to `D:\VoiceStudio\data` and `D:\VoiceStudio\hf_cache`; the
start log is `data\voicestudio-start.log`. Everything is **outside this git
repository**, and the launcher refuses a path inside it.

The measured instance used for the numbers above is
`.dsh-scratch/VOICESTUDIO-EVAL/MEASURE` (11.61 GB, deletable). It is **not**
the product default, and it is not in the repository tree.

---

## 7. Measurement rules (so nobody repeats the expensive part)

The heavy measurement is **done**. It installed an 11.61 GB environment,
downloaded 3.043 GB of weights and spent 268 s on its first call. Repeating it:

- is a **live model change** on the owner's PC,
- needs another 11.61 GB,
- and produces **no new fact**.

So:

- `tools/measure_voicestudio.py` **re-reports**. Its lines are labelled
  `MEASURED` (the record), `LIVE` (read now) or `BLOCKED` (could not be read or
  deliberately refused). **A BLOCKED line is never a pass.**
- It **refuses** to unload a model, start or stop the program, download
  weights, install anything or accept a licence. `--unload` exists only to be
  refused, so the refusal is testable.
- `--measure-warm` is the one live speech call. It is opt-in, and it refuses
  when no model is already loaded - because a call then would LOAD one, which
  is the live model change this rule forbids.
- The measurement was done at a **quiet moment** (no OBS, no games, the
  everyday model resident). A new measurement is an owner decision, not a
  tidy-up.

---

## 8. What this slice does not claim

1. **No clean-GPU baseline.** Both cards carried Jarvis models during every
   measurement, so every latency and VRAM figure here is a *coexistence*
   figure. VoiceStudio alone on an idle 2080 was never measured.
2. **No soak.** The longest run was about 17 minutes; the 900 s idle unload
   was never observed.
3. **No listening test.** WAV and MP3 were validated by header, size and
   duration; nobody listened to them.
4. **No Jarvis-side latency test** while VoiceStudio was loading; driving the
   live assistant to measure that was out of scope.
5. **The cold-start 400 was seen once**, not reproduced in a controlled loop.
   The explanation is the error text plus "the next request succeeded", not a
   code-level diagnosis.
6. **Egress is inferred** from 1 Hz TCP samples of the backend process for
   900 s. Sub-second or UDP traffic was not observed and is not claimed.
7. **The 2060 lane was never exercised** by VoiceStudio in any test.
8. **No phone surface.** The desktop-only claim is in `ARCHITECTURE.md` §8 with
   its reason.

---

## 9. Where else this is written down

- `docs/MODEL-TOPOLOGY.md` - what runs on which card and why.
- `docs/ARCHITECTURE.md` §8 - the one-sided-on-purpose row.
- `THIRD-PARTY-NOTICES.txt` - "VOICESTUDIO (not generated)".
- `docs/JARVIS-API.md` - **unchanged**, because this slice adds no route.
- The raw evidence, in the evaluation tree:
  `VOICESTUDIO-EVAL/MEASURE/RESULTS.md`, and `REPORT-LEGAL.md`,
  `REPORT-ARCH.md`, `REPORT-HARDWARE.md`, `REPORT-INTEGRATION.md` beside it.
