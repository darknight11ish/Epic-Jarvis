# Memory review - 2026-09-27

Written for the owner. Every claim was checked by a second reviewer against the
source; where the check changed a claim, the corrected version is used here.
"Self-test" means `backend/eval_memory.py` (memory) and `backend/eval_learner.py`
(learning). "Card" means an approval card. Nothing in the repo was changed.

## Summary (8 lines)

1. **Your bug (old "repeats" wording in the approval test) is fixed - but only on the working branch, not on GitHub's `main` yet.** Fix is commit `ddc2e8a`; the test now passes 65/65. It reaches `main` with the planned catch-up pull request.
2. The memory self-test numbers in the README are real: I (and a second reviewer) re-ran them and got the same results.
3. **Biggest memory bug:** asking about the past ("where did I live in February?") puts today's fact first, unlabelled, even when it was not true yet. The self-test cannot see this.
4. **Biggest learning bug:** a new fact that contradicts an old one ("I live in York now" when Jarvis knows "Leeds") can be saved automatically, leaving both as true.
5. **Biggest safety bug:** since the 2026-09-26 people-facts change, some private details about other people (a suicide attempt, a cancer diagnosis, prison) are read aloud once saved, because only the word lists are consulted then.
6. Forget does not fully forget: a forgotten fact still comes back when you ask about the past.
7. The cheapest real gain found: teaching memory that "boss" = "manager" and "GP" = "doctor" (+2 points on the main score, measured).
8. Two questions need your decision (end of file). Several numbers can only be settled by the test run on your PC.

---

## 1. Your reported bug - status

- **What you saw:** `backend/test_approval_contract.py` read the old wording of the "repeats" (`schedule_repeat`) card, because the new wording has quote marks (`\"tell me when\"`) and the old reader stopped at the first quote mark, silently.
- **What is true now:** fixed by commit `ddc2e8a` ("Approval contract test reads each _RISK entry's newest wording", 2026-09-26).
  - `backend/test_approval_contract.py:91` now reads the wording as a proper Python string, quote marks included.
  - `:103` reads the patches in the same order `scripts/apply-patches.ps1` applies them.
  - `:115-117` and `:219`: any card line it cannot read now **fails the test loudly** ("UNREAD") instead of being skipped.
  - `:221-223` checks that `schedule_repeat` has exactly `backend/asks-first.patch:97`'s wording.
  - I ran `python3 backend/test_approval_contract.py`: **65 passed, 0 failed**.
- **Where the fix is (correction of an earlier claim):** it is on branch `claude/admiring-ritchie-5urg5h`, **not** on `main`. `git merge-base --is-ancestor ddc2e8a origin/main` says no, and `origin/main` does not have this test file at all. So "pull main" will NOT bring it. It arrives when you press Merge on the planned catch-up pull request.
- **Two leftovers:**
  - Two old helper copies (`.claude/worktrees/agent-a4d69393e5376ccb0/` and `agent-a85710b02d8399f76/`) still hold the old reader. When those branches are merged, make sure they do not bring the old file back.
  - Small gap: if a patch named in `apply-patches.ps1` is missing, the test skips it without a word (`:107-108`, `if not patch.exists(): continue`). Today all 73 exist. Fix: fail like UNREAD does. Proof: rename one patch temporarily; the test must fail.

---

## 2. Bugs to fix now

Each has the test that proves the fix. "Gate" = `eval_learner`'s card-or-automatic cases (18/18 today, must stay 18/18).

### Memory (finding facts)

**B1. Past questions get a fact that was not true yet, first and unlabelled** (recall-2)
- Where: `backend/jarvis_past.py:338-356` (`recall()` returns today's hits unchanged; only retired facts get "(no longer true since ...)").
- Seen: "Where did I live in February?" -> "Owner lives in York" (true from 2026-03-01) first, Harrogate second. 8 time questions do this (q116, q117, q120, q140, q144, q146, q148, q161).
- Also: the model is shown the date Jarvis was *told* a fact, never its "true from" date (`memory-profile.patch` ~:100-104 keeps only text, id, created, pinned).
- Fix: when the question names a time, label a current fact "(true since <date>)" if it started after that time (same style as `label()`, `jarvis_past.py:268-274`).
- Proof: extend the scorer so an unlabelled later fact counts as "wrong version" (`eval_memory.py:417, 471`) and add the newer fact to `stale` for q142/q144/q146/q148. **Time: wrong version about 4/10 today -> 0.** Time found must stay 9/10 (10/10 with B2).

**B2. Month names are ignored, so "What phone did I have in June?" finds nothing** (recall-3)
- Where: `backend/rebuilt/jarvis_memory.py:261-281` (`_FRAME`, `_floor_terms`). The comment says time words are never in a fact; since idea 4 they are ("...a Pixel 8 in June 2026").
- Fix: take january..december out of the set used by the word floor **only**. Do not remove them from `_FRAME` itself: `_FRAME` is also used for names and nicknames (`:3217, :3228, :3242`), and "May", "June", "April" would become possible names.
- Proof (measured, words only): **Time found 9 -> 10/10** at 71 facts; the self-test's own chosen word floor goes back **0.0 -> 0.1** (today it quietly picks 0.0). Recall@5, don't-know and two-fact unchanged.

**B3. In a chatty conversation, the learner cannot see the fact it should be correcting** (recall-4)
- Where: `backend/jarvis_intake.py:642-662` (`candidates()` searches all of the last 6 messages at once with the normal word floor).
- Seen: "I don't live in York any more, I moved to Leeds" alone finds York; after three chatty messages it finds nothing, the learner is told "leave replaces out", and the fact can be saved automatically next to York.
- Fix: pass `word_floor=0` in `candidates()` (`find_one` already does, `jarvis_memory.py:1922-1925`).
- Proof: new learner case L-C1 below (the old fact must be in the candidate list). "Replaced came back" stays 0; gate stays 18/18.

**B4. Jarvis's own "memory_search" tool uses a weaker search than chat** (recall-8)
- Where: `backend/jarvis_agent.py:165-173` calls `store().search()` directly - no people layer, no re-ranker, no past recall.
- Fix: call `jarvis_past.recall(store, query, k)`.
- Proof: a test that the tool and chat recall return the same facts for "What's my sister called?". Expected (from the self-test's entity line): nickname questions 4/9 -> 9/9, recall@5 73.4% -> 78.7% on the tool path.

### Learning (saving facts)

**B5. A contradicting fact is saved automatically; the old one stays true** (learning-1)
- Where: `backend/jarvis_auto_learn.py:800-804` only looks at whether the model filled in "replaces"; nothing compares the new fact with stored ones.
- Fix: before an automatic save, search current facts; if one shares subject and verb but differs, or the new fact has a change word (now, no longer, moved, quit, stopped, switched) and shares 2+ words with a stored fact, make it a card (with `replaces_id` set). It only ever turns a save into a card, never retires anything.
- Proof: learner cases L-G1, L-G2 (want card) and guard L-G3 (want auto).

**B6. Something about another named person is saved as about you** (learning-2)
- Where: `backend/jarvis_auto_learn.py:1008-1035`; sentences are split at `. ! ? ;` only (`:985-989`), so the "I" in the other half of the sentence passes the check.
- Seen: "Dana works at Google and I work at Apple" -> "Owner works at Google" saved automatically.
- Fix: split into clauses (commas, "and", "but"); if the clause the fact comes from names a person the fact leaves out and has no "I/my", make it a card.
- Proof: L-G4, L-G5 (card), guards L-G6 and existing g04 (auto).

**B7. Past tense saved as true now** (learning-3)
- Where: `backend/jarvis_auto_learn.py:843-853` (lived/lives share a stem), `:888-893`.
- Seen: "I lived in Paris for two years in my twenties" -> "Owner lives in Paris", automatic.
- Fix: if every matching word you said is past tense and the fact is present tense, card.
- Proof: L-G7, L-G8 (card), guard L-G9 (auto); g01-g04 stay auto.

**B8. Wrong "true from" dates, which then wrongly trigger "older news"** (learning-4)
- Where: `backend/rebuilt/jarvis_memory.py:704-716` (`_BEGAN`, `_NOT_YET`).
- Seen: "Owner works at Initech, which was founded in 2010" gets 2010; on a correction this left the OLD job current and filed the new one as history. "stopped eating meat", "gave up smoking" get no date. "next to the park" counts as the future.
- Fix: drop founded/opened/launched from `_BEGAN`; add stopped/gave up/ended/moved out/broke up; make "next" mean only "next week/month/year/<day>/time".
- Proof: true-from cases T09-T12 below; t01-t08 stay 8/8.

**B9. "In a month" as a length of time gets a wrong future date** (learning-7)
- Where: `backend/jarvis_intake.py:396-399` ("a"/"an" count as numbers), `:496`.
- Seen: "I read one book in a month" -> "(around 2026-10-24)".
- Fix: only date "in <n> <unit>" when the sentence points ahead (is, will, due, exam, trip...), never after "times", "once", "per" or a past-tense verb. Leaving it undated is the safe side.
- Proof: date cases D07, D08 (unchanged); d04 ("exam is in two weeks") still dated. Dates stay 6/6 or better.

**B10. A saved "Remember: I live in Leeds" and the learner's "Owner lives in Leeds" never match** (learning-6)
- Where: `backend/jarvis_intake.py:884-907` ("I/me/my" are marks, "owner" is a stop word).
- Result: two copies of the same fact, and "said again" never counts.
- Fix: when *comparing* only (not when saving - your words stay as said), treat I/me/myself as "owner" and my/mine as "owner's".
- Proof: said-again case S-A1 (want 1), a near-duplicate unit test; s01-s12 stay 12/12; y04 stays 0.

**B11. "Nurse" (and similar jobs) treated as health when written as "Owner is a nurse"** (learning-11)
- Where: `backend/jarvis_sensitive.py:1259-1264` allows jobs only after "I'm / I am / work as".
- Goes against your 2026-09-26 decision (everyday facts about people save automatically).
- Fix: also allow "<anyone> is / was / works as a <job>". Keep "ill / in hospital / on medication" sensitive.
- Proof: L-G10, L-G11 (auto); guards g13 (asthma, card) and "sister is pregnant" (card); `jarvis_sensitive.py --measure` on all sets must not drop.

**B12. Keeping a correction card on a fact that ends in the future leaves the old fact in use** (learning-5; already listed as not fixed in `backend/README.md:10401-10404`)
- Where: `backend/rebuilt-patches/memory-safety.patch:123` and `backend/memory-safety.patch:384`; context line in `backend/auto-learn.patch:314`.
- Fix: use the same "still in use" rule as `feedback.patch:77-80` (retire unless the end date has already passed). Update auto-learn.patch's context line and check with `_stack` and apply-patches.ps1.
- Proof: unit test in `test_memory_true_from.py`: after Keep, the old fact has `retired_by` = new id and is not in `current_facts()`.

### Safety

**B13. Private details about other people are read aloud and repeated in web-search cards** (safety-1)
- Where: `backend/jarvis_sensitive.py:2842` (commit `8f8f8a4` added `or p["everyday_other"]`); read-aloud and web search use `topic()` only (`jarvis_auto_learn.py:1491-1500`, `jarvis_search.py:851-859`, `jarvis_agent.py:1401-1426`).
- Measured: 55 lines labelled sensitive in the test sets now look "normal" (e.g. "my best mate Liam tried to kill himself in may", "Kieran's in the Scrubs for another 18 months"). Two are about **you**: "I had a TIA two years ago" (the word lists read "tia" as Spanish for aunt), "bi and my family doesn't know".
- Fix (fits your rules): when a fact is saved after a sensitive card, or under the sensitive switch, store the topic with the fact (e.g. `meta.sensitive="health"`); read-aloud and web search use it when `topic()` is empty. Everyday people-facts stay normal. Also: do not treat a relation word as "about someone else" when the sentence is "I had ...".
- Proof: a test that saves through `classify()` with a stand-in model saying "health", then checks `is_sensitive_fact()` is True. The new "topic()" column (I5) falls from 55 toward 0.

**B14. The word lists miss common ways of saying suicide attempt, self-harm, domestic violence, stalking, homelessness, immigration status** (safety-3)
- Where: `backend/jarvis_sensitive.py:149-300`, `:761-986`, `:1104-1165`.
- Seen: "I tried to kill myself" gets no category at all.
- Fix: add those phrasings (see the finding; "overdosed" is already caught, not needed). Keep "this deadline is killing me" not sensitive.
- Proof: `jarvis_sensitive.py --measure` on all four sets - recall must not fall, harmless-line mistakes must not rise; put the probe lines in a new held-out file nobody tunes on.

**B15. Forgotten facts come back when you ask about the past** (safety-2)
- Where: `backend/jarvis_past.py:277-312`; Forget is a plain `retire()` (`memory-pane.patch:158-178`).
- Seen: forgot "Owner has been seeing a therapist for depression on Tuesdays"; "what did I use to do on Tuesdays?" brought it back, labelled "no longer true since today" (also untrue).
- Why it is a bug: both apps promise "Jarvis will not use it again" (`jarvis-desktop/src/auto-learn.js:185-194`) and CLAUDE.md says Forget hides a fact. `docs/ARCHITECTURE.md:1120` says the opposite and needs correcting.
- Fix: mark a Forget (e.g. `meta.forgotten_at`); past recall skips those. Facts replaced by a correction or that simply ended stay recallable. A "stop using this fact?" card counts as a Forget.
- Proof: golden/past test F-1 below; existing past questions must not drop.

### App wording and docs (small)

**B16. Both apps' voice setting still says answers about "other people" are not read aloud** (apps-7) - `jarvis-desktop/src/voice-training.js:446`, `jarvis-client/.../voice/StrictVoice.kt:116-117`. Change to "other people's private details", as the backend card says. Proof: update both apps' voice-setting tests.

**B17. Both memory models are stored in Windows' temp folder** (apps-6) - `jarvis_memory.py:428-430, 522-524` pass no `cache_dir`, so fastembed uses `%TEMP%\fastembed_cache`. A disk clean-up means a re-download, or (offline) the re-ranker switches off and search falls back to words only. Fix: pass `cache_dir=<Jarvis data folder>/models` (or set `FASTEMBED_CACHE_PATH` at start). Not checked: your own backend start-up, which is outside the repo. Proof on the PC: empty `%TEMP%`, restart, `/api/memory/status` still shows meaning search on and re-ranker on, no download.

**B18. Docs say the re-ranker "never makes a chat wait"** (apps-4, recall-6) - `backend/README.md:10348`, `docs/JARVIS-API.md:~5505`. It can hold one answer for up to 1.5 s (`jarvis_memory.py:504, 641`). Change to "waits at most 1.5 s, then answers in the old order". (After one slow run, the next questions skip the re-ranker at once, so it is not every question.)

**B19. JARVIS-API section 6 says the phone does not read memory status** (apps-8) - `docs/JARVIS-API.md:1047`. The phone does (`JarvisRuntime.kt:2914`). Also add `reranker` and `said_again` to the field list.

---

## 3. Improvements, ranked by gain for the effort

Each one is kept only if it moves the named number by the stated amount without hurting the others.

| # | What | Effort | Keep it only if |
|---|------|--------|-----------------|
| I1 | **"boss" = "manager", "GP" = "doctor"** and a few more (mum/mom/mother, dad/father, flatmate/roommate/housemate, neighbour/neighbor), used only when *looking up*, never when saving; **never** partner/husband/wife (that made "my wife" find the partner). `jarvis_memory.py:3231-3251`. (recall-9) | Small | Recall@5 rises at least +2 points at 71 facts (measured 78.7 -> 80.9) and don't-know stays 1.47. Words only; the PC may already find these by meaning. |
| I2 | **Skip the re-ranker when there are 5 facts or fewer** (it cannot change which 5 are used). (recall-6) | Tiny | Recall@5 identical (it must be); report Recall@1/MRR. Time saved only shows on the PC. |
| I3 | **Number words = digits** ("three cats" = "3 cats") when checking your own words. Matters most for voice. `jarvis_auto_learn.py:884-886`. (learning-10) | Small | Cases V01-V03 go card -> automatic; guard V04 ("three" vs "4") stays a card; g05, g06, g14 stay cards. Not checked: whether your speech-to-text writes digits or words. |
| I4 | **"Said again" checks the date**: "started yesterday" said on a later day is a new event, not a repeat. `jarvis_intake.py:564-588, 1024-1038`. (learning-9) | Small | Case S-A2 goes 1 -> 0; s01-s12 stay 12/12. |
| I5 | **Self-test honesty for sensitive topics**: add a "topic() - what read-aloud and web search use" column to `--measure`; relabel everyday people lines in `dev.jsonl`/`round2.jsonl` as not sensitive; stand-in model answers from the case's label. (safety-4) | Small | Column shows 55 today and falls as B13/B14 land. |
| I6 | **Self-test tunes on the path chat really uses**: run both floor sweeps with the people layer on, score don't-know questions through `P.recall`, give the distance floor the same tune/test split. `eval_memory.py:399-406, 621-647`. (recall-11) | Medium | Report the chosen floors and test-half numbers; this is what sets `JARVIS_MEMORY_MAX_DISTANCE` on the PC, so do it **before** the PC run. |
| I7 | **`--against old.json`** for `eval_memory.py`: prints better/worse per column, fails if recall@5, time-wrong or learner cases get worse (not on timing, which varies). (apps-11) | Small | Run against today's report: all "unchanged", exit 0. |
| I8 | **Show the re-ranker in both apps**: "Answer ordering (re-ranker): on / still loading / off - why", plus "said again: N". Rename the desktop's "Repeats" to "Repeated cards dropped". (apps-5) | Small | Same status fixture passes on both apps' tests. You need this to decide whether it stays on. |
| I9 | **"Older news" warning on its own line**, not after "Not saved automatically:", with a plain date ("1 January 2026"). (apps-2) | Small | New desktop and phone tests read the same fixture. |
| I10 | **Show "true from" dates**: add `true_from` to `/api/memory/auto` rows; both apps show "true from 1 January 2026"; desktop's full list stops showing a bare "2825d ago". (apps-3) | Medium | eval_learner true-from 8/8 unchanged; both apps build the same line from one fixture. |
| I11 | **One shared wording fixture for memory** (`contract/memory-words-cases.json`), read by both apps' tests; pick one wording for "no longer recalled" vs "true then / no longer true". (apps-9) | Medium | Changing one app's words breaks the other app's test. |
| I12 | **Round "said again" times to the day** (the code comment already says so), so after Erase they cannot point at an exact chat turn. `jarvis_memory.py:1851-1870`. (safety-6) | Tiny | `test_memory_said_again.py`: after Erase every time is a whole day; counts shown unchanged. |
| I13 | **One step out from a person**: when a top fact names a known person, add the fact that says who they are (1-2 extra at most). (recall-10) | Medium | Two-fact questions 6/10 -> 7/10 (q156) and don't-know per question does not rise. Not measured yet. |
| I14 | **Judge the re-ranker on the big same-topic row** (10,071 facts) in the scoreboard, not only at 71. (recall-7) | Docs | A column for recall@5 and two-fact at 10,071 same-topic. |

Not worth doing: raising k (facts per turn) above 5 - at 5, 8 and 10 the two-fact score stayed 6/10 and wrong facts only grew (words only; see PC list). Counting "living" as a framing word: it lost a right answer.

---

## 4. New self-test cases to add

### `backend/eval/golden_questions.jsonl`
- **q142, q144, q146, q148 (change):** add the NEWER current fact to `stale` (e.g. f11 "Owner lives in York" for q148), and make the scorer count an unlabelled later fact as "wrong version". Proves B1.
- **F-1 (new, needs a "forgotten" setup field or put it in `test_memory_true_from.py`):** fact "Owner has been seeing a therapist on Tuesdays", then Forget it; question "What did I use to do on Tuesdays?"; want: that fact **absent**. Proves B15.
- **F-2 (new, guard):** fact "Owner worked at Globex" replaced by a correction "Owner works at Initech"; question "Where did I use to work?"; want: Globex, labelled "no longer true since ...". Makes sure B15 does not hide corrected facts.
- **Q-boss / Q-GP:** q063 "What's my boss called?" and q077 "Who is my GP?" already exist and fail today; want them found after I1.

### `backend/eval/learner_cases.jsonl` - gate (card or automatic)
- **L-C1 (B3):** stored `Owner lives in York`; turns: three chatty messages (e.g. "The weather's awful today", "Work was busy, loads of meetings", "Anyway I watched a film last night") then "I don't live in York any more, I moved to Leeds last week"; want: York in the candidate list, result **card**.
- **L-G1 (B5):** stored `Owner lives in Leeds`; turn "I live in York now"; fact "Owner lives in York now"; want **card**, why change.
- **L-G2 (B5):** stored `Owner lives in Leeds`; turn "I don't live in Leeds any more"; fact "Owner does not live in Leeds any more"; want **card**.
- **L-G3 (guard):** stored `Owner likes jazz`; turn "I also like folk"; fact "Owner likes folk"; want **auto**.
- **L-G4 (B6):** turn "Dana works at Google and I work at Apple"; fact "Owner works at Google"; want **card**.
- **L-G5 (B6):** turn "Tom is a pilot, I'm a chef"; fact "Owner is a pilot"; want **card**.
- **L-G6 (guard):** same turn as L-G4; fact "Owner works at Apple"; want **auto**.
- **L-G7 (B7):** turn "I lived in Paris for two years in my twenties"; fact "Owner lives in Paris"; want **card**.
- **L-G8 (B7):** turn "I worked at Tesco for years"; fact "Owner works at Tesco"; want **card**.
- **L-G9 (guard):** turn "I moved to York in 2024"; fact "Owner moved to York in 2024"; want **auto**.
- **L-G10 (B11):** turn "I am a nurse"; fact "Owner is a nurse"; want **auto**.
- **L-G11 (B11):** turn "my partner Sam is a nurse"; fact "Owner's partner Sam is a nurse"; want **auto**.
- **V01 (I3):** voice (heard, strictest check) "I have three cats"; fact "Owner has 3 cats"; want **auto**.
- **V02 (I3):** "I have two kids"; fact "Owner has 2 kids"; want **auto**.
- **V03 (I3):** "I have 2 dogs"; fact "Owner has two dogs"; want **auto**.
- **V04 (guard):** "I have three cats"; fact "Owner has 4 cats"; want **card**.
- **P-1..P-n (B13/I5):** private people-facts the word lists see only as "a person" (from the safety-1 list, e.g. "my best mate Liam tried to kill himself in may"), with the stand-in model answering from the case's label; want **card**.

### `learner_cases.jsonl` - true from
- **T09:** "Owner stopped eating meat three weeks ago (around 2026-09-05)", told 2026-09-26; want 2026-09-05.
- **T10:** "Owner works at Initech, which was founded in 2010"; want no date.
- **T11:** "Owner gave up smoking in 2021"; want 2021-01-01.
- **T12:** "Owner moved to a flat next to the park in 2024"; want 2024-01-01.

### `learner_cases.jsonl` - dates
- **D07:** "Owner read the whole series in a month"; want unchanged (no date added).
- **D08:** "Owner goes to the gym three times in a week"; want unchanged.

### `learner_cases.jsonl` - said again
- **S-A1 (B10):** stored "I live in Leeds"; turn "I live in Leeds"; proposed "Owner lives in Leeds"; want 1.
- **S-A2 (I4):** stored "Owner started at the new office yesterday (2026-09-23)"; turn "I started at the new office yesterday" on 2026-09-26; proposed "Owner started at the new office yesterday"; want 0.

### Unit test (no learner_cases kind exists for it yet)
- **B12:** old fact retired with an end date 90 days ahead; correction card kept; want old fact `retired_by` = new id and not in `current_facts()`.

---

## 5. Your decisions

**Question 1 - may the re-ranker drop weak facts?**
Today the re-ranker only re-orders facts, it never removes any. Questions Jarvis cannot know the answer to still get 1.5-2 wrong facts each, and nothing fixes that yet.
- **Let it drop weak facts, only if the PC test shows it helps** (recommended). The cut-off is chosen on half the questions and checked on the other half.
- **Keep it only re-ordering**, as the docs promise now.

**Question 2 - should "Erase the words" also offer to delete the chat it came from?**
Erase wipes the fact from memory, but the conversation where you said it stays in chat history. The confirm today says "from your PC for good", which is not quite true.
- **Offer "Also delete the chat it came from"** on the same screen (recommended).
- **Only fix the wording** to say the chat stays in history until you delete it.

(Forget coming back in past questions, B15, is treated as a bug because your rule already says Forget hides a fact; `docs/ARCHITECTURE.md:1120` gets corrected to match. Say so if you meant past questions to still see forgotten facts.)

---

## 6. What only the test run on your PC can settle

Everything above was measured with word search only (no meaning search, and a stand-in for the re-ranker). On your PC run (`eval_memory.py` at sizes 0,100,1000,10000 with the real models):

1. **Is the re-ranker worth keeping on?** Judge it on the 10,071 same-topic row (recall@5 75.5% and two-fact 5/10 without it, per README), not on the 71-fact row.
2. **How long the real re-ranker takes** (p50/p95 ms). That sets the time limit (today 1.5 s; 0.3-0.5 s is a guess) and how much I2 saves.
3. **The distance floor** (`JARVIS_MEMORY_MAX_DISTANCE`, still a guess at 1.0) - after I6, so it is not tuned on the questions it is judged on.
4. **The re-ranker score floor** (Question 1): don't-know facts per question 1.47 -> under 0.7, "none returned" 50% -> above 70%, with recall@5 and people found (20/20) not dropping.
5. **Whether k=5 is still right** with meaning search, and on the future 12 GB card. q157 ("what food should I avoid?") can only be found by meaning.
6. **Whether "boss/GP" (I1) still adds anything** once meaning search is on.
7. **Learner model behaviour:** how often the real model leaves out "replaces" (B5), and whether a long phone conversation dates "yesterday" wrongly (learning-8: every turn is dated to the newest turn, `memory-intake.patch:352, 380`; real weakness in the code, harm not measured). Fix idea: tell the model each turn's own date when turns span more than one day.
8. **Whether your speech-to-text writes "3" or "three"** (decides how much I3 matters).
9. **The temp-folder check** for B17.
