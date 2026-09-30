# Report 31 (outside-suggestion-check), agent af8b1279, 2026-09-30T06:31Z

> **What it was asked** (first 600 characters of the task): Check this outside (Gemini) suggestion against the real code and past decisions in /home/user/Epic-Jarvis (read CLAUDE.md, docs/ARCHITECTURE.md, docs/MODEL-TOPOLOGY.md, docs/GPU-SUPPORT-RESEARCH-2026-09-27.md, docs/HARDWARE-PROFILES.md, docs/AUDIT-2026-09-28-REPO-REFS.md - read that one first: outside reviews' disproven findings stay closed - and grep docs/ and backend/ for any earlier mention of each name). The suggestion: replace/augment Jarvis's multi-model management with (1) xorbitsai/inference (Xinference; Apache-2.0; supervisor/worker pinned by --gpu-idx, one OpenAI endpoint for LLM, VL

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Verdict: SKIP all five as replacements. Borrow two or three ideas. I could not reach GitHub, so licences and the projects' own claims are NOT CHECKED. I have no web tool here. Everything about Jarvis below I did open and grep in this repo.

**Already researched?**
- I searched the whole repo for Xinference, LocalAI, GPUStack, Triton and `jarvis_supervisor`. There are zero hits. These names are new to the project, so this is not a reopened finding.
- `docs/AUDIT-2026-09-28-REPO-REFS.md` §7, round eight, already refuses other frameworks that bring their own scheduler or Docker. It says "ONE permission model ... ONE scheduler".
- `docs/RESEARCH-AUDIT-2026-09-28.md:444` says "Not now: ExLlamaV3 (it would replace Ollama), vLLM or SGLang".
- No `jarvis_supervisor.py` exists (Glob found nothing). psutil appears in one backend file only (`jarvis_pc_help.py`).

**What Jarvis already does (this is most of the suggestion)**
- `backend/jarvis_second_card.py` runs separate Ollama processes for the second lane and the third lane.
  - The second lane is on port 11435 and the third on 11436 (lines 403 and 407).
  - Each is pinned with `CUDA_VISIBLE_DEVICES=<card uuid>` (line 114), bound to loopback only, with `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_NUM_PARALLEL=1` (lines 1386-1387).
  - Each has `OLLAMA_KEEP_ALIVE` (default 30m, `_keep_alive()` at line 841).
  - The lane stops after idle minutes (line 773: "it stops after N idle minutes").
  - Vulkan is turned off so the pin holds (line 1390).
- Routing is in `jarvis_agent.choose_lane()` and `lane_for`.
- So "a supervisor pins lanes to GPUs and kills idle ones after 15 minutes" is already built, in Ollama form. Claim 5 is mostly done.
- The claim that a supervisor sends chat to GPU0 and coding/vision to GPU1 is wrong for Jarvis. The owner names which feature goes on which card, and a card is never chosen automatically (`CLAUDE.md`, third-card entry, and GPU-SUPPORT-RESEARCH §1.3).

**Wrong or unverified facts**
- The suggestion says the 2060 12 GB sits in a chipset PCIe 3.0 x4 slot on a B550 board. I grepped docs for "B550", "chipset" and "x4 slot". The only hit is `MODEL-TOPOLOGY.md:513`, a generic line: "The second slot on many motherboards runs slower (x4 or x8). That only slows loading". The board and slot are not in the docs, so treat them as UNVERIFIED. The 2060 is also not installed yet (`CLAUDE.md`, `MODEL-TOPOLOGY.md:5`).
- The claim that Xinference could replace Ollama, Kokoro, sherpa and Whisper: I did not check that against Xinference itself. It would also replace Jarvis's own voice-check and wake-word pipeline, which are built around separate parts.

**Verdicts**
1. **Xinference: SKIP.** It is a second model server and supervisor, on top of Ollama. It would break the Ollama-specific pieces: `/api/models` switch and install (approval cards on the phone), the Ollama tool wire format, `num_ctx` set by Modelfile, and the `q8_0` KV cache and flash-attention settings tuned in `HARDWARE-PROFILES.md`. Licence, WSL2 and Windows support: not checked.
2. **LocalAI: SKIP.** Same reasoning. Its TTL eviction is already covered by keep_alive and lane idle-stop. Licence: not checked.
3. **GPUStack: SKIP.** It is a cluster scheduler with its own control plane, which clashes with "one scheduler". A bin-packing scheduler is overkill for at most three fixed cards, where the owner chooses placement. WSL2 needs are not checked, and the project's ban on Docker as a general dependency (SearXNG is the only Docker use, `ARCHITECTURE.md:2355`) applies if it runs in a container.
4. **Triton: SKIP.** It targets datacenter serving with WSL2 or Docker. A beginner owner on Windows 11 with PowerShell 5.1 would have to run it, and it has no Ollama-style pull flow.
5. **Native dual llama-server: SKIP as a replacement.** Ollama already runs llama.cpp underneath, and Jarvis reads its "starting llama-server" log (`HARDWARE-PROFILES.md:1188`). Dropping Ollama would lose the model library, pull and install flow, `/api/models` cards, tool-call wire format, the `tool_eval` results and the hardware presets. It would also need a new `jarvis_supervisor.py` that duplicates `jarvis_second_card.py`. The `--device CUDA0/CUDA1` flag is not checked against current llama.cpp.

**Rules check**
- Rule 1 and 2: local loopback is fine for all of them. I did not check telemetry defaults for any of the five.
- `OLLAMA_NO_CLOUD=1` is a second lock behind rule 1 (`CLAUDE.md`). It exists only for Ollama, so a replacement server would lose it.
- Rule 5 and licences: fine either way. Anything adopted would need credit in `THIRD-PARTY-NOTICES.txt`.
- No approval clash from the pure ideas below.

**Worth considering (ideas only, no new dependency)**
- **A measured per-lane log.** Record time-to-first-token, tokens per second and VRAM used per lane. It could sit beside the existing prompt-cache share shown in Brain -> Model (milestone 7). It changes nothing until read; the owner decides whether to show it in both apps. It would also supply the missing numbers for the still-unmeasured 2060.
- **PCIe-aware placement, as a note only.** Slot speed mostly affects load time (`JARVIS-API.md:1952`, `MODEL-TOPOLOGY.md:513`). At most, a preflight line could warn "second card is on a slow slot, so switching models will load slowly". The owner would need to run one `nvidia-smi` check to read the real link width first.
- **Per-lane idle unload.** This already exists. If the owner wants a different time for the third lane than the 30-minute default, that is a one-line setting, not a new supervisor.

**Files opened:**
- `/home/user/Epic-Jarvis/docs/AUDIT-2026-09-28-REPO-REFS.md`
- `/home/user/Epic-Jarvis/backend/jarvis_second_card.py`
- `/home/user/Epic-Jarvis/docs/MODEL-TOPOLOGY.md` (lines 505-520 only)
- `/home/user/Epic-Jarvis/docs/ARCHITECTURE.md` (grep hits only)

**Not checked:** `docs/GPU-SUPPORT-RESEARCH-2026-09-27.md` and `docs/HARDWARE-PROFILES.md` were not read in full. I only grepped them. `_ollama_wire.py` was not opened.
