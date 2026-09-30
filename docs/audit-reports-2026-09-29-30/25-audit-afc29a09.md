# Report 25 (audit), agent afc29a09, 2026-09-30T06:13Z

> **What it was asked** (first 600 characters of the task): Read-only audit for the owner of /home/user/Epic-Jarvis. Question: does EVERY Jarvis tool/feature that uses a GPU or a model correctly and fully use a 2nd or 3rd graphics card when installed (expect the extra cards to be 8 GB to 12 GB VRAM each, alongside the 8 GB RTX 2080 Super primary), AND is every tool that cannot run on the ONE primary card OFF by default? Start with docs/MODEL-TOPOLOGY.md, docs/GPU-SUPPORT-RESEARCH-2026-09-27.md, docs/ARCHITECTURE.md, and CLAUDE.md sections on the second card, third card, chatbot driver, screen 'picture mode', Live camera, projects/app builder, prompt gu

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Audit: does every GPU/model feature use card 2 or 3 correctly, and is everything that cannot run on one card OFF by default? Read-only. I ran no tests and no code; every row is from reading source. Not checked: jarvis_hardware.py presets in depth, the desktop and phone UI, jarvis_profiles.py, tests, and the docs beyond the topology headers.

**Short answer.** Every second-card feature is OFF by default and gated by an approval card. Lane routing is correct for cards 2 and 3, with one gap: the F5 "better voice" cannot go on card 3. Two problems matter for your 8 to 12 GB expectation: an 8 GB extra card is refused outright, and the screen "Look at this" pictures never use the second card's vision model.

**Table.** "2nd" and "3rd" mean the lane on the second or third card.

| Feature | Runs on | Lanes | VRAM (source) | Needs >1 card | Default / gate | Picks card 2/3 |
|---|---|---|---|---|---|---|
| Chat model | primary GPU, Ollama :11434 | none | 8 GB card, 16K context (MODEL-TOPOLOGY) | no | on | n/a |
| Longer conversations | 2nd or 3rd | `long_context` | qwen3:8b at 32K = 7.69 GiB, calculated (second_card.py:~447) | yes | OFF, card `second_card_enable` | Yes. `CUDA_VISIBLE_DEVICES=<uuid>` (second_card.py:1383), ports 11435/11436, `OLLAMA_VULKAN=0` |
| Pictures (Qwen2.5-VL 7B) | 2nd or 3rd | `vision` | 5.59 GiB weights plus KV, "guess" (:~466) | yes | OFF, same card | Yes, via `lane_for("vision")`, used by `choose_lane` (jarvis_agent.py:4861) |
| Learning in the background | 2nd or 3rd | `learning` | as long_context | yes | OFF, same card. Without the lane it runs on the primary card | Yes. `_learning_lane` (:2160), `check_local_model` |
| Browser control | 2nd or 3rd | `browser_control`, needs `long_context` | as long_context | yes | OFF | Yes. Only the visible browser needs it (jarvis_browser_engine.py:565); the windowless one does not |
| Wiki builder | 2nd or 3rd | `wiki` | as long_context | yes | OFF | Yes (jarvis_wiki.py:211) |
| One bigger model on both cards | 2nd plus primary | `combined` (not assignable to 3rd) | qwen3:14b at 32K = 12.28 GiB, estimated, unmeasured (:~520) | yes | OFF, card `second_card_combined_enable` | Yes. Runs with no pin, so both cards are visible. The floor is 18 GiB combined (:526) |
| F5 "better voice" | 2nd only | none | 3072 MB, "NOT MEASURED" (jarvis_voices.py:166) | yes | OFF, card `better_voice_enable` | 2nd only. `worker_env` sets `CUDA_VISIBLE_DEVICES=<uuid>` (:2475) from `det["second"]` (:2423) |
| Big model "colibri" | CPU; card 2 if `[big_model] cuda="on"` | n/a | unmeasured | no | OFF | 2nd only (jarvis_big_model.py:918). Needs a source build for Turing |
| Screen picture mode (MiniCPM-V 4.6) | CPU only, `CUDA_VISIBLE_DEVICES=-1`, port 11437 | none | 0 GB by design | no | OFF, card `screen_picture_enable` | Deliberately CPU. Not routed to any card |
| Chatbot "second local AI" and full version | the `long_context` lane | follows it | model swaps in and out of that lane | full version only | `full_version` false in config | Follows whichever card holds `long_context` |
| Live camera | the `vision` lane | follows it | as vision | yes | OFF until a photo test passes | Follows the vision lane |
| Wake word (openWakeWord) | CPU, `providers=["CPUExecutionProvider"]` (jarvis_wakeword.py:359) | n/a | 0 | no | as before | CPU |
| Speech to text (Parakeet), Kokoro, Silero, voice check, ZipVoice, Pocket | CPU (sherpa-onnx with `num_threads`, no GPU provider set) | n/a | 0 | no | as before | Not checked deeper than grep. No `device_id` or CUDA provider found anywhere |
| Embeddings, re-ranker | CPU (fastembed). No CUDA or provider setting found | n/a | 0 | no | re-ranker off | CPU |
| Prompt Guard 2, or the other injection detector | Not built. No code in `backend/*.py` | n/a | n/a | n/a | n/a | n/a |
| Projects with Jarvis writing code | Not built. It waits for the 12 GB card | n/a | n/a | n/a | n/a | n/a |

**Behaviour by card count (from `_detect`, jarvis_second_card.py:1075).**
- **1 card:** `capable` is false, every lane returns None, and Jarvis behaves exactly as before.
- **2 cards:** the biggest capable non-primary card becomes "second".
- **3 cards:** the next card becomes "third" (`lanes[1]`). It runs one owner-assigned feature on a separate Ollama on :11436, alongside the second card's lane. The assignment needs its own card, `second_card_third_assign`.
- **Combined mode** uses only the primary plus "second". A third card is left out.
- **Presets** are two-slot. `_third` is always None under a preset.

**Findings, worst first.**

1. **An 8 GB extra card is refused entirely.** `MIN_TOTAL_MB = 10240` (second_card.py:407) and `_not_capable` (:1006-1008) say "not enough: the second-card features need at least 10 GB". So an 8 GB second or third card runs nothing. It is not offered a smaller lane, such as the 5.6 GB vision model or a 4B learner, even though picture reading would fit. F5 is blocked too, because it relies on `det["capable"]`. Your stated 8 to 12 GB range is only half served. Owner decision below.

2. **The PC screen "Look at this" pictures never reach the second card's vision lane.** `jarvis_screen.py` and `jarvis_screen_picture.py` contain no `lane_for` or `vision` call. Picture mode is hard-wired to the processor: `CUDA_VISIBLE_DEVICES=-1` (jarvis_screen_picture.py:727) and `num_gpu 0` (:1001). `choose_lane` also excludes phone screen pictures (jarvis_agent.py:4861 and `_phone_screen_turn`). So with a 12 GB card and Pictures on, screen looks still use the slow CPU model. This is a feature that fits but has no route. The Live camera does use the vision lane correctly.

3. **F5 "better voice" cannot go on the third card.** It reads `det["second"]` (jarvis_voices.py:2423-2431) and is not one of the five assignable features. It also has no coordination with the third lane, and only a `free_mb` check at start (:2567). With 2 cards its 3 GB estimate against the 7.69 GiB lane on a 12 GB card is unmeasured. This is a design gap, not a wrong-card bug. It does not silently land on GPU 0, since the uuid is pinned.

4. **No feature is ON by default that needs a second card. I found no violation.** `_read_switches` defaults are all False (second_card.py:906-914), and `better_voice` (jarvis_voices.py:1501), `full_version`, picture mode and `[big_model] cuda` are all off. Each ON goes through a card. Picture mode is the exception in a good way: it needs no card at all.

5. **Hardcoded model and size assumptions.**
   - The lane model is fixed as qwen3:8b at 32K for any card of 10 GB or more (`LONG_BIG` and `LONG_SMALL` are identical, :447). Nothing uses a bigger model or a longer context on a 12 GB card.
   - Vision is fixed to `qwen2.5vl:7b` (:466), which is not checked against ollama.com. VRAM numbers are estimated, not measured.
   - Combined mode is hardwired to qwen3:14b with a total of at least 18 GiB. With an 8 GB primary plus a 10 GB card that is exactly 18 GiB, so it passes.
   - The card's memory total is the only thing sized from the actual card (via `card=third`), which is correct.

6. **Compute capability is gated everywhere.** `MIN_COMPUTE = 7.5` applies to each extra card in `_not_capable`, and to the primary in `_combined_capable`. Unknown compute is treated as not capable. This passes.

7. **The third card cannot hold combined mode or F5.** This is documented in CLAUDE.md and the module docstring, and matches the code.

8. **Not verified.** None of this has run on real multi-GPU hardware. The `backend/test_second_card.py` suite exists, but I did not run it.

**Open owner decisions.**
- Should 8 GB extra cards get a smaller lane, or stay refused? I recommend a smaller lane, marked "unmeasured".
- Should screen looks use the Pictures lane when it is running, with CPU picture mode as the fallback? I recommend yes.
- Should F5 be assignable to the third card, or stay on the second only? I recommend leaving it on the second.

Key files, all under /home/user/Epic-Jarvis/backend/: jarvis_second_card.py, jarvis_agent.py, jarvis_screen_picture.py, jarvis_voices.py, jarvis_big_model.py, jarvis_wakeword.py.
