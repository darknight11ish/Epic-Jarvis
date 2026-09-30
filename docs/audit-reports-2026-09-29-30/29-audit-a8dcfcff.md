# Report 29 (audit), agent a8dcfcff, 2026-09-30T06:23Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md, docs/MODEL-TOPOLOGY.md, docs/HARDWARE-PROFILES.md, docs/GPU-SUPPORT-RESEARCH-2026-09-27.md first). Owner: "Some single GPUs can be up to 16 or 24 GB each. Make sure Jarvis can read them and use them properly. And the FIRST (primary) card can be anywhere between 8 GB and 32 GB VRAM and should work properly too. Review these features to make sure they work well." Today Jarvis was built around an 8 GB RTX 2080 Super primary (everyday model jarvis-primary, qwen3 8B, num_ctx 16384 in backend/jarvis-primary.Modelfile, KV q8_0, etc.). Audit, 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

AUDIT: Jarvis on 8 / 12 / 16 / 24 / 32 GB primary cards (read-only, no files changed)

BOTTOM LINE: Detection is sound for big cards. Sizing is not. Nothing is unsafe, but a 16, 24 or 32 GB primary is barely used unless the owner picks a preset, and even then Jarvis tops out at 14B at 32K.

WHAT I RAN
- `python3 backend/test_profiles.py`: 217 passed.
- `python3 backend/test_hardware.py`: 148 passed.
- `python3 backend/test_second_card.py`: crashed on a `cryptography` import panic in this container. NOT checked.
- I called `jarvis_profiles.plan()` by hand with 8, 12, 16, 24 and 32 GB cards and with 32+24 GB. These are calculated results, not measured on a card.
- I called `jarvis_second_card._combined_capable` and `_long_context_plan` by hand with 16, 24 and 32 GB second cards.
- Everything else I only read. Not checked: the Rust code, the Kotlin build, the Playwright tests, the router (its file is not in this repo), the `jarvis_agent` context trim, and a real Windows or Ollama run.

TABLE
"Now" is the default path with no preset chosen. "Should" is a proposal.

| Primary | Now | Should |
|---|---|---|
| 8 GB | jarvis-primary, 8B, 16K, q8_0 (calculated; the presets say 8K for "Smartest") | Unchanged |
| 12 GB | The same 8B at 16K. The "Smartest" preset picks 14B at only 8K. | 8B at 32K (calculated) |
| 16 GB | 8B at 16K. Extra features need a second card. "Most features" gives 8B 32K plus a 3B picture model beside it. "Smartest" gives 14B 32K and no pictures. | 14B at 32K, calculated |
| 24 GB | The same 8B at 16K. "Smartest" gives 14B 32K with pictures off by choice. "Features" gives 8B 32K plus the 7B picture model. | A 14B and the 7B picture model together fit, calculated. A 32B model is not in the catalogue. |
| 32 GB | Same as 24 GB | Same as 24 GB, with more headroom |
| Second card of 16, 24 or 32 GB | The long-conversation lane is always qwen3:8b at 32K, 7.69 GiB. | A bigger model or context, only after measuring. All unmeasured. |

FINDINGS, WORST FIRST

1. The everyday model is a fixed file that never looks at card size (`backend/jarvis-primary.Modelfile:119`, `PARAMETER num_ctx 16384`).
   - The header says it targets the 8 GB 2080 Super, so a 24 or 32 GB card runs 8B at 16K. Only the preset path (owner-run, several approval cards) makes `jarvis-chat`.
   - The preset catalogue stops at `CHAT_MODELS = ("qwen3:14b", "qwen3:8b", "qwen3:4b")` and `CONTEXTS` ends at 32768 (`jarvis_profiles.py:64`, `:204`). No 30B, 32B or MoE model exists in it, so 24 and 32 GB cards are never fully used.

2. One big card and no second card means no extra features without a preset.
   - `_detect` returns `capable: False`, "only one graphics card found" (`jarvis_second_card.py:1134`). Pictures, browser, wiki and camera all check `lane_for(...)`.
   - With the "Most features" preset on one card, `_detect_preset` makes it capable, and `test_hardware.py:545` tests that on 16 GB. So a 16 to 32 GB primary works, but only after the owner finds and applies the preset. This is a discoverability gap. The screen picture mode and the app builder read the same lane, so this hits them too.

3. The second-card lane ignores size above 12 GB.
   - `LONG_BIG` and `LONG_SMALL` are identical, `("qwen3:8b", 32768, 7.69)` (`jarvis_second_card.py:448-449`), and `BIG_TOTAL_MB = 11776` is dead. Verified: 16, 24 and 32 GB cards all get 8B at 32K.
   - The vision size is derived from that same context.
   - "Combined" is fixed at 14B/32K (`COMBINED_MODEL`, `:522`). Its floor is 18 GiB combined (`:526`). It is allowed for 24+24 GB, where it is pointless. A single 24 GB card holds 14B by itself, and combined never picks a larger model.

4. Camera, chatbot and app-builder wording bakes in "12 GB" or "8 GB".
   - `jarvis_live.py:1238` `CAMERA_NEEDS` says "second graphics card (the 12 GB one)".
   - `jarvis_live_photo_test.py:379` says "Install the 12 GB card".
   - `jarvis_chatbot_local.py:116` `NEEDS_SECOND` says "your 8 GB card".
   - `jarvis_chatbot_local.py:86` `LANE_MAX_BYTES = 9 GiB` refuses any local model over 9 GiB even on a 24 GB second card.
   - The one-card chatbot rule is "only the model already loaded", which is wrong when the primary is 24 GB.
   - The features themselves are still gated correctly; the gate is "lane running plus photo test", not a size.

5. Names are only guessed when an old driver gives no compute capability.
   - `COMPUTE_BY_NAME` is a substring list (`jarvis_compute.py:143-150`). "RTX 50" matches "RTX 5000 Ada" (really 8.9) and "Quadro RTX 5000" (really 7.5). RTX A-series cards (A4000 16 GB, A6000 48 GB) match nothing and are treated as not capable. Low: this fires only when nvidia-smi lacks `compute_cap`.

6. `nvidia-smi` `[N/A]` memory is skipped (`parse_smi`), so a unified-memory or laptop-style card would silently be invisible. Laptop and iGPU: only NVIDIA is read there. The presets read AMD and Intel through the registry and Ollama's log and mark them best-effort.
   - Only the presets plan more than one card (two at most). A third card is ignored there (`jarvis_profiles.py:499`, "plans for up to two cards"). Lane-3 support exists only in `jarvis_second_card`.

7. The 12 GB preset picks 14B at 8K for "Smartest", which is a poor tradeoff. Card sizes near a label boundary render as "15.9 GB" on the desktop (`_gb`) but round to "16 GB" in the apps. This is cosmetic.

DETECTION: PASS
- nvidia-smi is read in MiB into Python ints, so there is no overflow and 32 GB is fine.
- Older drivers get fallback field sets, and the registry uses `qwMemorySize` (64-bit). No 4 GB cap.
- Cards are pinned by uuid, and a lost id makes the card "not capable".
- A card reporting slightly under its label is handled in comments and code (11776 threshold, "0.05" GB rounding).

APPS: MOSTLY PASS
- Both apps render sizes from the backend (`Hardware.kt:288`, `SecondCard.kt:627`, `settings.js:1748` `scGigabytes`) and round rather than hard-code them.
- The 8 GB text in `jarvis_hud.html:981` is a demo-graph fact, not UI.
- Not checked: how the second-card screen looks with one big card and no second (not run).

TESTS
- Profiles cover 6, 8, 16 and 24 GB (`test_profiles.py:278-287`), but not 32 GB.
- `test_second_card.py` only uses 8, 12 and about 10 GB cards (`:158`, `:341`, `:999`, `:1516`).
- Missing: a 16, 24 or 32 GB second card, and a primary above 12 GB with no preset.
- Missing: `_long_context_plan` scaling (nothing scales), COMBINED with two large cards, and the `COMPUTE_BY_NAME` collisions above.
- The apps are only tested with recorded backend data.

OFF BY DEFAULT: PASS
- Nothing here switches on by itself. Presets are choices, and every step raises a card. Do not switch on anything sized for a large card until it is measured.

OWNER DECISIONS

A. How should Jarvis treat a 16 to 32 GB primary?
- (recommended) Show a one-line suggestion in Brain > Model ("your card can hold the 14B at 32K - try Smartest"), and change nothing by itself.
- Add larger model sizes to the catalogue (32B, 30B-A3B) after they are measured.
- Leave it as it is.

B. Wording on camera, chatbot and app builder
- (recommended) Say "second card, or a large single card" everywhere, and remove the 12 GB and 8 GB text.
- Leave it.

C. Second-card lane above 12 GB
- (recommended) Keep 8B/32K until measured, then add rows per size.
- Give a 24 GB card a 14B lane now, unmeasured.

D. Feature gates on a single big primary
- (recommended) Let the no-preset path treat a 16 GB or larger primary as capable, with pictures beside chat, only if the owner approves the switch.
- Keep needing the preset.

Fixes 4, 5 and the tests are mechanical; the rest are the owner's call.
