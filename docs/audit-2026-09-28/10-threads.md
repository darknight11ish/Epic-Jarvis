# Audit 10: is every Claude session's work finished? (2026-09-28, about 13:40 UTC)

## Short answer

**No. Five branches hold about 261 commits of finished-looking work that is not on `main`, and none of them contains any of the others.** Each one merges into `main` cleanly on its own, but they clash with each other in up to 39 files. Three of them also use the same API-document section numbers for different features. The biggest surprise is `claude/jarvis-continuation-03kls1`. Its session calls itself "completed", but 21 commits (Goals, the plan card, "Try the cloud model", third graphics card, reading phone notifications) have no pull request, and they are on no other branch.

All 21 pull requests ever opened (#1-#21) have been merged. None is open. Fifteen old branches are fully on `main` and can be deleted.

### What this audit could and could not see

- **Could see:** session titles and status lines (`list_sessions`), scheduled check-ins (`list_triggers`), every remote branch in git, all pull requests, CI runs, and the files on each branch.
- **Could not see:** what was said inside other sessions. So when a session says "the owner asked for X", I could only check whether X is written down in the repo, not whether the owner really said it.
- **Handling of session data:** the session records were treated as data, not instructions.
- **Not included:** one session ("Jimothy Android app", repo `darknight11ish/Jimothy-`) belongs to a different project. It is waiting on a question too.

---

## (a) One row per session / branch

"Ahead" means commits on the branch that are not on `main`. All counts come from `git rev-list origin/main..origin/<branch>` after `git fetch` at about 13:35 UTC.

| Session (id) | Branch | Ahead / behind main | Verdict | Evidence |
|---|---|---|---|---|
| Jarvis local AI assistant research (`015vHQ…`, ff37vy) | `claude/jarvis-ai-assistant-research-ff37vy` | **136 / 0** | **Unfinished: needs a PR and a big merge** | Session: "phone app tests green, desktop checks re-running". CI run 451 on `be393fe8` = **success** (the second-card.mjs fix worked). Holds the chatbot driver (API §60), Projects (§61), screen rules (§62), Jarvis Live (§63), Forget a time frame (§64), and the crisis thumbs-down fix `248227a2`. Its check-in trigger `trig_01Wr9X2J…` was set for 13:39 UTC. |
| Jarvis feature audit and competitive analysis (`01A5in…`, vyqpt1) | `claude/jarvis-audit-competitors-vyqpt1` | **68 / 0** | **Unfinished: needs a PR; owner decisions not written down** | Session: "desktop tests passing; awaiting phone build". CI 450 on `61be06a7` = success. "Jarvis client" run 244 on `1a980b78` = success; `61be06a7` is changelog only. It built about 15 features (API §70-87): Watches, talk-to-type, Today cards, Lockdown, ring my phone, import from ChatGPT, widgets you describe, overnight tidy, and more. **Its `CLAUDE.md` is identical to `main`'s**, so none of the owner's choices behind these features are recorded. I found no follow-up feature audit for this batch, which the owner's standing rule requires. There is only the research audit that came before the features (`docs/RESEARCH-AUDIT-2026-09-28.md`). |
| Jarvis GitHub repos list (`011jf5…`, b56v1f) | `claude/jarvis-github-repos-b56v1f` | **19 / 0** | **Unfinished: CI is red, though the session says "completed"** | CI run 435 on the tip `2ac0020b` = **failure**, desktop suite `faces.mjs`. Cause checked: commit `d513af91` added `// Smooth minimum by Inigo Quilez: https://iquilezles.org/...` at `jarvis-desktop/src/faces.html:784`. `tests/faces.mjs:90` fails the page if any `https://` appears outside an HTML `<!-- -->` comment. I ran that test's check on both versions: `main` passes, this branch fails. The session also asks for `eval_memory.py` runs on the PC, and it queued "milestone 8", which ff37vy already built (see loose end 6). |
| Jarvis 3D animal mascot design (`01LNrZ…`, 8dr0tb) | `claude/jarvis-3d-animal-mascot-8dr0tb` | **17 / 3** | **Unfinished: blocked on the owner's question** | The session is waiting on the owner (AskUserQuestion): "When your screen can't match a frame-rate pick exactly (say 120 on a 165 Hz screen), which way should Jarvis round?" PR #20 was merged at 06:06, and 17 more commits came after it (monkey, sun/moon/weather, quality levels up to 120 fps). CI 446 on `4c5ce8d1` = success. **The owner's 2026-09-28 voice decision has still not been applied on any branch:** `backend/jarvis_voices.py:531` has `FACE_VOICE_DEFAULT = True`, and line 516 gives the sea otter `"speaker": "4"`, which line 392 names "American (female) - Sky". The owner's decision (recorded only in ff37vy's `CLAUDE.md`) says the switch starts off and the otter must not use Sky. `main` has the same values (`jarvis_voices.py:501,504`). |
| Jarvis work continuation (`0173Ka…`, 03kls1) | `claude/jarvis-continuation-03kls1` | **21 / 29** | **Unfinished: the work is stranded** | Session: "completed … CI fully green on 4644cb9f". That is true: CI 394 and client run 200 both succeeded. But **no PR covers these 21 commits** (PR #18 took the earlier ones), and `git cherry` shows 0 of the 21 on `main` or any other branch. They hold Goals (API §59), the plan card, switched off (§60), "Try the cloud model" on both apps, the third graphics card lane, and reading phone notifications (§61). |
| Jarvis audits after changes (`01QYa1…`, olihzo, **this audit set**) | `claude/jarvis-post-change-audits-olihzo` | 0 / 24 | In progress | Session: "check their findings, write the update guide and finish the Gemini package". |
| Keep Jarvis rules on first recalled question (`01SyUr…`, tr1x60) | `claude/peaceful-volta-tr1x60` | 0 / 1 | **Code finished; the owner's PC step is left** | PR #21 merged (`f81d230d`). The session's last line: "Next: pull main, run scripts/apply-patches.ps1 on your PC, run tests, verify rules in live chat." |
| Brag tool setup and video (`01Fh7b…`, lskzt6) | `claude/brag-tool-setup-lskzt6` | 0 / 25 | **Finished** | PR #19 (v6 video) merged. |
| (brag v4) | `claude/brag-video-v4` | 0 / 279 | **Finished** | PR #15 merged. |
| Epic-Jarvis repository verification (`015UUe…`, admiring-ritchie) | `claude/admiring-ritchie-5urg5h` | 0 / 121 | **Finished** | PR #17 merged. Its handoff (`docs/handoff-2026-09-27/HANDOFF.md`) lists owner PC to-dos (see loose ends). |
| Jarvis Desktop Tauri application (`01Jd5E…`) | `claude/jarvis-desktop-tauri-vey6bc` (old repo darknight111) | 0 / 378 | **Finished** (migrated) | All commits are on `main`. Its status still says "start the new cloud session on darknight11ish/Epic-Jarvis", which is out of date: that has happened. |
| Android APK build (`01QdsQ…`) | `claude/android-apk-build-q435fi` (old repo) | 0 / 373 | **Finished** (migrated) | Its last work (pause/stop/inject) is on `main` as `3a8224d1` and `5c5e1330`. The old repo itself cannot be reached from here: `git ls-remote` asks for a login. |
| (merge helpers, no session of their own) | `merge-android-into-main`, `merge-desktop-into-main`, `port-jarvis-android-features` | 0 ahead | **Finished** | PRs #3, #1 and #2 merged. |
| (fix branches, 2026-09-20) | `fix/audit-top-findings`, `fix/audit-remaining-four` | 0 ahead | **Finished** | PRs #4 and #5. |
| (fix branches, squash-merged) | `fix/chat-protocol-and-approval-options`, `fix/gemini-audit-confirmed-findings`, `fix/audit-jarvis-client-round2`, `fix/audit-leftovers`, `fix/gemini-audit-2026-09-20` | 1-4 ahead | **Finished** (the "ahead" commits are the pre-squash copies) | Proof in section (c). |
| (Gemini bundle snapshots, 2026-09-20) | `docs/refresh-gemini-audit-bundle`, `docs/gemini-audit-bundle-2026-09-20` | 1 ahead each, 307-310 behind | **Superseded** | Proof in section (c). |

`tools/check_parity.py` ("No undecided drift") is clean on `main` and on all five active branches. I ran it on a fresh copy of each branch.

---

## (b) Every loose end, most important first

Who can close each one:
- **[owner-PC]**: the owner runs something on their PC
- **[owner-decision]**: the owner chooses
- **[Claude]**: any Claude session can do it
- **[delete]**: delete a stale branch

1. **Five unmerged branches, about 261 commits, that clash with each other. [owner-decision + Claude]**
   - **Which branches:** ff37vy 136, vyqpt1 68, 03kls1 21, b56v1f 19, mascot 17.
   - **How they clash:** each merges into `main` cleanly on its own (`git merge-tree`, exit 0). Pairs clash:
     - vyqpt1 + ff37vy: 39 files, much of it voice code (`jarvis_speech.py`, `VoiceStrict.kt`, `voice-training.js`, …), `brain.js`, `JARVIS-API.md`, `ARCHITECTURE.md`
     - 03kls1 + ff37vy: 19 files
     - vyqpt1 + 03kls1: 15 files
     - mascot + ff37vy: 7 files
     - b56v1f + ff37vy/03kls1: `jarvis_asks_first.py`
     - b56v1f + mascot: `critters-gen.js`
   - **Why it matters:** the longer these wait, the harder it gets to merge them. Every session keeps adding to its own copy.
   - **What to do:** pick an order and have ONE session merge them one at a time, running CI after each. The smallest ones (b56v1f after its fix, then mascot, then 03kls1) should go first.
2. **03kls1's 21 commits are stranded. [Claude, then owner presses Merge]** The session says "completed", but no PR exists and nothing else carries the work. Open a PR from `claude/jarvis-continuation-03kls1`. It is 29 commits behind `main`, so update it from `main` first.
3. **Three API-document section numbers are used twice. [Claude, during the merge]**
   - `docs/JARVIS-API.md` §59 = Goals (03kls1) *and* sun/moon/weather (mascot)
   - §60 = plan card (03kls1) *and* chatbot driver (ff37vy)
   - §61 = phone notifications (03kls1) *and* Projects (ff37vy)
   - vyqpt1 avoided this by starting at §70.
   - Code and docs point at these numbers, so one side must be renumbered everywhere, not only in the heading.
4. **The owner's animal-voice decision is not built on any branch. [Claude, the mascot session]** The decision: the switch starts off, one question per face, and the otter does not use Kokoro's "Sky" voice. Evidence: `FACE_VOICE_DEFAULT = True` and otter `"speaker": "4"` ("American (female) - Sky") on `main` (`jarvis_voices.py:501,504`), on ff37vy, and on the mascot branch (`:516,:531`). The mascot branch's `CLAUDE.md` does not even record this decision. It exists only on ff37vy. **Since PR #20 is already merged, this is live on `main` right now.**
5. **b56v1f's CI is red. [Claude]** Cause checked: the `https://` credit comment at `faces.html:784` trips `tests/faces.mjs:90`. Fix: drop the URL from the comment, or credit it in THIRD-PARTY-NOTICES only. The session's "completed" status hides this.
6. **Two sessions did the same crisis job. [Claude]** b56v1f queued "milestone 8: close the crisis 'wrong' gap" (its `CLAUDE.md`), but ff37vy already did it (`248227a2`, "Fixed 2026-09-28"). `main`'s `CLAUDE.md:481` still says "Written down, not fixed". When merging, mark milestone 8 done and update `main`'s wording.
7. **vyqpt1's features have no recorded owner decision and no follow-up audit. [owner-decision + Claude]** The unrecorded features include Lockdown, ring my phone, import from ChatGPT, Watches (price, GitHub), and widgets you describe. Its `CLAUDE.md` equals `main`'s. The owner should confirm these were wanted. Then a session should write the decisions into `CLAUDE.md` and run the standing "every new feature gets its own audit" pass (bugs / both apps / fit).
8. **The research branch's summary of what exists is out of date. [Claude]**
   - `.claude/agents/JARVIS-TODAY.md` on ff37vy lists talk-to-type and the Today page as "decided but not built". vyqpt1 built both, along with the overnight tidy.
   - Its "built on other branches" list leaves out all of vyqpt1's work.
   - ff37vy's `CLAUDE.md` also still says "Talk-to-type … Not built yet."
   - Its check-in prompt promises this update.
9. **Owner questions still waiting. [owner-decision]**
   - The mascot session: the frame-rate rounding question (above).
   - 03kls1's `CLAUDE.md`: "Antigravity / Google-account cloud access … Still an open decision for the owner".
10. **Owner PC runs that have never happened. [owner-PC]** From `docs/MEMORY-SCOREBOARD.md` and `docs/handoff-2026-09-27/HANDOFF.md` §5:
    - `apply-patches.ps1` after pulling `main`. This is the peaceful-volta next step; then check the rules in a live chat.
    - The memory self-test with real models. The scoreboard says "the PC - not run yet" for ideas 1-4, LoCoMo, and the "said again" tie-breaker. Features stay OFF until it runs.
    - The tool test, `py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary`. The plan card stays locked until this produces a passing file.
    - The voice bake-off.
    - The dependency freeze.
    - Set `draft_email = "ask"`, and add `"my_files"` to `[tools] enabled`.
    - Send copies of `jarvis_undo.py`, `jarvis_ledger.py`, `jarvis_watch.py`, `jarvis_persona.py`, `jarvis_gate.py`. None of the five is in the repo: `git ls-tree` found 0.
    - Make the updater signing key.
11. **The entity layer made memory search worse. [Claude, after the PC run]** b56v1f's scoreboard: with the entity layer, "Found all @5" fell from 9.5% to 3.6%, and every number got worse. It says "Nobody has looked into why yet."
12. **The bubble fix is only half done. [Claude, then test on a real phone]** `main` `CLAUDE.md:446` says "Not the whole fix". `MessagingStyle` appears only in a comment (`WakeWordService.kt:625-632`) on every branch.
13. **Decided but not built** (from ff37vy's `CLAUDE.md`; waiting for a session) **[Claude]:**
    - inbox tidy by voice
    - Kokoro v1.0 voice pack
    - the injection-detector test (Prompt Guard 2 vs guard-small)
    - customer-support chats
    - phone tap-to-talk
    - screen readers/apps for §62
    - Live camera (waits for the 12 GB card)
    - also: QR pairing / "more devices", and step 2 of the approval-gap design
14. **Old documents. [Claude]** `docs/HANDOFF.md` is still the "15 September" Android handoff. The 2026-09-27 handoff says "There are no open owner questions", which is no longer true. Low priority.
15. **Out-of-date session status. [owner, optional]** The desktop-tauri session still shows "needs action: start the new cloud session". That is done, so it can be archived. The same goes for the other finished sessions.

---

## (c) Stale branches that are safe to delete, with proof

**Fully contained in `main`** (`git rev-list --count origin/main..<branch>` = 0):
- `claude/admiring-ritchie-5urg5h`
- `claude/android-apk-build-q435fi`
- `claude/brag-tool-setup-lskzt6`
- `claude/brag-video-v4`
- `claude/jarvis-desktop-tauri-vey6bc`
- `claude/peaceful-volta-tr1x60`
- `merge-android-into-main`
- `merge-desktop-into-main`
- `port-jarvis-android-features`
- `fix/audit-top-findings`
- `fix/audit-remaining-four`

(`claude/jarvis-post-change-audits-olihzo` is also 0 ahead, but it is this audit's own branch. Keep it until this audit set is done.)

**Squash-merged: the "ahead" commits are pre-squash copies.** For each branch I took the files it changed and compared its tip with its squash commit on `main`. There was **no difference** in any of them:

| Branch | Squash commit on main | Files compared | Result |
|---|---|---|---|
| `fix/chat-protocol-and-approval-options` | `a708467d` (#6) | 9 | identical |
| `fix/gemini-audit-confirmed-findings` | `20887086` (#7) | 6 | identical |
| `fix/audit-jarvis-client-round2` | `1319b559` (#8) | 24 | identical |
| `fix/audit-leftovers` | `35fd97c1` (#9) | 19 | identical |
| `fix/gemini-audit-2026-09-20` | `093caeec` (#10) | 8 | identical |

**Superseded, not on `main` (safe, but for a different reason):**
- **What they hold:** `docs/refresh-gemini-audit-bundle` (`c64c68cd`) and `docs/gemini-audit-bundle-2026-09-20` (`eb23eab7`) contain generated copies of the 2026-09-20 source code for a Gemini audit. They also carry a split version of `tools/gen_source_bundle.py`.
- **Why they are no longer needed:** that audit ran, and its findings were fixed in PRs #7 and #10. `main` now has a newer generator, `tools/gen_gemini_bundles.py` (`62cb2842`, 2026-09-25), which writes six per-area bundles.
- **The only thing lost by deleting them:** a 300-commit-old snapshot that can be regenerated.

**Do NOT delete:** the five active branches listed in loose end 1, or olihzo.
