# Report 50 (audit), agent a6c4aa03, 2026-09-30T07:20Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first; verify with file:line + quote; 'not checked' honestly; change no files). AREA: TEST QUALITY, especially the stand-in harness. Known incident: backend/screen.patch's look-mark hunk skipped a middle context line; every test passed because backend/_stack.py 'materialises' missing pre-image text; only the owner's real jarvis_hud.py failed. PR #37 added a contiguity test for that one hunk. Audit: (1) backend/_stack.py and related helpers (grep who imports it: test_*patch*.py, test_rules_first_relay.py, test_patch_history.py, etc.): ex

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

TEST-QUALITY AUDIT (read-only; no repo files changed; scripts in scratchpad: scan.py, scan2.py, scan3.py, m.py)

WORST FIRST

1. The stand-in cannot see a skipped middle line (the screen.patch incident) except by luck; the fix was one hunk only. (ran)
   - backend/_stack.py:137-149: any hunk that fails `git apply` gets its whole pre-image appended after "# gap" and is applied there. That makes it pass by construction.
   - I replayed all 103 patches (310 hunks, 5 targets: jarvis_hud/gate/extract/models/skills) without materialising. 125 hunks are "materialised", meaning their context is the owner's original text, which the repo does not hold.
   - I then flagged any hunk whose pre-image lines partly overlap text earlier patches wrote, but not contiguously. There were 23 flags.
   - I read the 4 "all lines present but not contiguous" ones (voice-enroll #0, gate-outcome #6, approval-notice #1, memory-intake #4). Each is just a hunk that runs one line past an earlier patch's fragment into original text. That is normal, and unprovable here.
   - I then checked adjacent pre-image line pairs that both exist in the stand-in but never next to each other. Only one pair hit: voice-503 hunk 1, `except Exception as exc:` then `return self._send(200, {"available": False,`. Both lines are generic, so this is probably coincidence, not a bug. Not verified against a real file.
   - Conclusion: no second screen.patch-style break is detectable here. Nothing detected does not mean none exist. Only the owner's real file (apply-patches.ps1 on a copy) can prove it.
   - Patches ordered after 29 in the stack materialise almost nothing. The exception is cloud-say-yes.patch (order 81, 1 hunk), which CLAUDE.md says was hand-checked against the real file.
   - Remaining risk: hunks that straddle "earlier patch's lines plus original lines". Examples are voice-enroll #0 and memory-intake #4.
   - Only ad-hoc guards exist: test_gate_stack_clean.py (gate patches listed by hand), and "nothing materialised" checks in test_devices:433, test_settings_switches:351, test_screen_picture:1501, test_between_us:366. Every new patch must remember to add one.
   - Smallest fix: one generic test with a pinned per-patch materialised count (a ratchet). Patches numbered above 29 must be 0, except a named allow-list (cloud-say-yes: 1). A new patch that starts materialising then fails CI and needs a stated reason.
   - Owner decision: (a) recommended, add the ratchet test now; (b) leave the per-patch checks as they are.

2. Skips inside tests count as PASS. (read + counted)
   - The pattern is `return check("SKIP - ...", True)`. 62 suites use it. Counts: 35 "git is not installed", 29 `"SKIP - " + out` where the patch rehearsal returned None, 12 cryptography missing, 8 "no jarvis_hud.py here; the rehearsal above is the proof".
   - Examples: test_bind_wildcard.py:134, test_chat_stream.py:499, test_cloud_one_turn.py:81, test_documents_owned.py:152.
   - test_agent.py:392 skips when jarvis_gate is not importable.
   - CI has git and cryptography, so most do run there. But the runner's summary shows 0 skips for them, so a CI image without git would go green with the whole patch-applies layer unproven.
   - Smallest fix: have `check("SKIP...")` record into a SKIPPED list and print it. Better, make run_suites.py fail when git is missing on CI (`CI=true`).

3. The 19 runner-level skips (a real-PC-only gap; run_suites.py:52-72, output confirmed).
   - Skipped when the owner's files are absent: test_appearance, approval_notice, bitemporal, decide_once, degrade_filter, documents_honesty, events_pump, extraction_wiring, gate_egress, gate_outcome, gate_push, gpu_offload, import_history, memory_noise, memory_pane, memory_prefix, memory_safety, token_file, voice_503.
   - Coverage lost in CI: every check that runs a patched real jarvis_hud, jarvis_gate or jarvis_extract. That includes gate egress, gate outcomes, memory safety and extraction wiring, which are safety-critical.
   - They ran only on the owner's PC.
   - Nothing tells the owner when they last ran. Smallest fix: apply-patches.ps1 already runs them, so print "19 real-file suites ran: N ok" in the final summary. Not checked whether it does.

4. TOOLS_SWITCHABLE-style name mismatches. (ran, partially)
   - The email_read vs email_check bug is fixed and mapped at jarvis_asks_first.py:280 (TOOL_NAME) and LEGACY_TOOL_NAMES. I imported the modules: all 4 mapped tool names exist in jarvis_agent.TOOLS.
   - jarvis_reach.TOOL_NAMES has the same 27 keys as TOOLS (no drift).
   - jarvis_card_words.TITLES has 83 keys. Every `_RISK` key in the patches is in TITLES.
   - Unverifiable in this repo: jarvis_reach._FALLBACK_ACTIONS (jarvis_reach.py:~124-137) is the lookup-name to gate-action table used "when jarvis_gate cannot be asked". The real table lives in the owner's jarvis_gate.py. The `jarvis_*_read_run` names (calendar, email, notes, home) appear in no patch here. No test compares the fallback to the real gate table. If the two drift, the "What asks first" page shows the wrong answer offline.
   - Smallest fix: a test that, when jarvis_gate is present, asserts `action_for_tool(k)[0] == v` for every fallback entry. It would be one of the real-PC-only suites.
   - Also read: test_auto_learn.py:1133-1136 passes ("not even queued as a card (fine)") if `_remember` queues nothing. A regression that queues nothing passes silently.

5. Fixtures and generators. (ran)
   - I ran `--check` on all 50+ tools/gen_*_cases.py and gen_golden.py: no drift now.
   - Backend tests call `--check` for only some of them. Rough grep, not all confirmed: no backend/CI `--check` for gen_support_cases (only support.mjs and SupportTest.kt read the fixture), and gen_animal_cases and gen_sky_cases (CI does run these directly).
   - A stale support fixture would still pass in both apps, because both read the same wrong file.
   - Generators compute expectations from the real Python modules, so a generator bug is less likely to fool both apps. But if the backend function is itself wrong, both apps agree with it.
   - Smallest fix: add gen_support_cases.py --check to ci.yml, or a backend test like test_asks_first:912.

6. CI collection. (read)
   - run_suites.py globs backend/test_*.py, so all 222 files are collected. It fails on stale skip-list entries and on skip entries that need no owner file.
   - Desktop: ci.yml runs every tests/*.mjs except uikit and shots.
   - Not collected: server/test_jarvis_mobile_ws.py (old jarvis-android server, not run by CI or run_suites) and docs/designs/skills-draft-2026-09-23/test_skill_tools.py. Both look intentional. Not checked whether they are stale.
   - Suites run as plain scripts by exit code. A suite that prints FAIL but exits 0 would pass; I did not audit every suite's exit code.

7. Time-flaky tests. (grep + ran)
   - test_tidy was already fixed (commit d9765e3a pins noon).
   - I ran the full suite once with TZ=Pacific/Kiritimati (UTC+14): 197 ok, 19 owner-file skips, 0 failures.
   - Remaining unpinned clock reads: test_email_send.py:123 and test_email_draft.py:121 (datetime.now for a date header, low risk), and test_rebuilt.py:1433-1444 (SL.hour(), uses explicit setup).
   - 44 suites read time.time(). I did not classify each. Not run at a midnight, DST-change or 01:59 UTC boundary. Not checked.
   - Smallest fix: the runner sets TZ and a pinned clock (faketime-style) for a second run in CI.

Not checked: Kotlin/mjs fixture-consumer logic, and whether the 44 time.time() suites are hour-sensitive.
