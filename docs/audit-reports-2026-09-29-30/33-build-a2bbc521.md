# Report 33 (build), agent a2bbc521, 2026-09-30T06:37Z

> **What it was asked** (first 600 characters of the task): You are working in a git worktree of the Epic-Jarvis repo (read CLAUDE.md first, all of it: rules, wording rules, 'do not claim more than the evidence supports', the Screen safety and picture-mode decisions). Do NOT push and do NOT open PRs; commit on your worktree branch and report branch name and commit sha. OWNER DECISION (2026-09-30, from a multi-GPU audit): "Look at this" (screen looks) should USE the second/third card's vision model (Pictures lane, qwen2.5vl:7b via jarvis_second_card.lane_for("vision")) WHEN that lane is running, with the slow processor-only picture mode (MiniCPM-V, jarv

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Branch `worktree-agent-a2bbc521dfced9f55`, HEAD `29c48505` (two commits: the change, then the patch-history record). Not pushed, no PR.

WHAT CHANGED
- backend/jarvis_screen_picture.py: a look now asks `pictures_lane()` (wraps `jarvis_second_card.lane_for("vision")`; refuses non-127.0.0.1 addresses and cloud model names). If the lane is running, the same CLEANED, shrunk picture goes to it (`chat_via_lane`, lane's model and context, 90 s ceiling, no `num_gpu 0`). The slow CPU reader is the fallback on error, timeout, missing model or empty answer. With the lane up, a missing MiniCPM model no longer blocks a look. If both fail: words only, said plainly (note suffix + a sentence in the answer). The cleaner runs first for both readers, fail closed. No new switch, no new download. Picture mode's own switch still gates everything.
- Card wording (`describe_on`), picture-mode detail text and the gate risk line now say a running Pictures card is used first. The detail text is mirrored in jarvis-client `net/ScreenPicture.kt` and jarvis-desktop `src/look-rules.js`. Fixtures regenerated with `tools/gen_screen_cases.py` and `gen_live_cases.py`.
- screen-picture.patch and browser-engine.patch: one gate risk-text line (it said "never the graphics card"). I ran `build_patch_history.py` and committed, as CLAUDE.md asks. The clone was not shallow.
- backend/jarvis_chatbot_local.py: new `lane_max_bytes()` = the card's real memory minus 3 GiB (12 GB gives 9 GiB as before, 10 GB gives 7, 8 GB gives 5, unreadable gives the old 9 GiB). It uses the smallest of the second and third cards. Wording no longer says "second card".
- backend/jarvis_chatbot.py TIER_WORDS and backend/jarvis_live.py CAMERA_NEEDS reworded ("extra graphics card", no "12 GB one").
- Docs: SCREEN-DESIGN.md, JARVIS-API.md §96.1, ARCHITECTURE.md §8.
- `jarvis_agent.py` untouched. It is shipped whole, but I left `choose_lane` alone on purpose. It keeps phone screenshots away from the chat "vision" lane so a raw picture never reaches a model before `clean_picture`.

TESTS
- test_screen_picture.py: 305 to 352 passed, 0 failed.
- test_chatbot_local.py: 54 to 64 passed, 0 failed.
- test_screen 198, test_live 300, test_patch_history 24, test_gate_risk_words 15: all pass.
- `run_suites.py`: 202 passed, 0 failed, 19 skipped (they need the owner's own files).
- `check_parity.py` clean; screen and live fixtures match in both apps.
- New tests use fakes. They prove the lane gets only the cleaned picture. A secret through the real cleaner is solid black in what the lane receives. No cleaner or a failing cleaner sends nothing to the lane. A Never-look program in front sends nothing. A lane that errors, is slow, has no model or answers empty falls back to the CPU reader with the note. Lane refusal for non-local addresses and cloud names.

NOT VERIFIED
Nothing ran on Windows or with a real card or a real qwen2.5vl:7b. The Kotlin edit is a string change only and is unbuilt (CI). Desktop JS tests were not run.

OWNER DECISIONS I MADE (please check)
- "Pictures on, picture mode off" stays words only. I chose that so no new consent path appears. It is explained on the picture-mode card and in the docs, not at look time. Say if you want the lane used even then.
- The phone's static "Picture mode" text now mentions the lane. It is a Kotlin string, built only in CI.

PASTE-READY NOTE FOR CLAUDE.md
Built 2026-09-30, the owner's decision after the multi-GPU audit: **"Look at this" and "Watch with me" use the Pictures graphics-card lane first, the slow processor reader is the backup.** When "Pictures" is already on for the second or third card and its lane is running, a look sends the same cleaned picture (secrets blacked out, Never-look windows painted black, no cleaner means no picture) to that lane on 127.0.0.1. If the lane is down, errors, times out or gives nothing, Jarvis says so in plain words and uses the processor reader, or words only. No new switch, no new download; picture mode's own switch still decides whether a picture is read (Pictures on with picture mode off = words only). Same commit: the second AI's model-size limit follows the lane card's real memory (memory minus 3 GiB, 9 GiB on a 12 GB card) instead of assuming 12 GB, and wording no longer assumes "the second card" or "12 GB". Verified with fakes only (`test_screen_picture.py` 352, `test_chatbot_local.py` 64, full runner 202 pass); nothing ran on Windows or with a real card. See JARVIS-API §96.1.
