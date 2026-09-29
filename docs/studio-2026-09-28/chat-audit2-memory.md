# Second chat audit: chat features with memory and learning (branch claude/jarvis-ai-assistant-research-ff37vy, ffde34a9)

No repo file was changed. `git status` is clean. `eval_memory.py` wrote its result files to `/root/jarvis-memory-eval/`, outside the repo.

## Bottom line

The chat features fit together well. There is one encrypted store, one permission model, and the outside-text mark is fail-closed. Parity is clean and every suite I ran passes.

Most of what I found comes from one new fact: **"Continue this chat" and the scrollable thread bring old words back into places that assumed old words could not return.** That affects the learner, the game rule, erase/forget, and the model's re-send window. The four most useful findings are:

- A game or role-play silently stops being temporary after 11 exchanges (finding 1).
- Continuing a chat makes the learner turn every new fact into a card for about 10 questions (finding 2).
- Facts you accepted by hand lose the link to their chat (finding 3).
- The delete dialogs promise more than they can keep, because backups exist (finding 4).

## What I ran and what I only read

**Ran, all pass:**
- `python3 tools/check_parity.py` (no undecided drift).
- Backend suites: test_chat_log 182, test_chat_kinds 47, test_temporary_chat 75, test_games_temp_chat 70, test_brain_reads 118, test_forget_range 160, test_history_import 90, test_auto_learn 367, test_wellbeing 135, test_learning_integration 22.
  - test_learning_integration skipped its "patched-extractor half", because `jarvis_hud.py` is not in this container.
- Desktop node tests: chat-history, conversation, provenance, history, auto-learn, erase, memory-used, forget-range and live all exit 0. I did not run the full `test:ui`.
- `eval_memory.py`, which runs `eval_learner.py` inside it.
- Four throwaway scripts in the scratchpad that reproduced findings 1 and 2 and the game/manner problem in finding 7. They used the real `jarvis_chat_log`, `jarvis_auto_learn`, `jarvis_intake` and `jarvis_quick` modules.

**Only read, not run:**
- All Kotlin. There is no Android build here.
- All Rust.
- `jarvis_hud.py`, which the repo does not hold. The chat route is read from the `.patch` files only.
- No real model or real embedder. `fastembed` is missing, so the re-ranker and distance floor are not measured. Those numbers only come from the owner's PC.

## Eval numbers

Nothing moved. These match the 2026-09-28 row of `docs/MEMORY-SCOREBOARD.md`. All are words-only, since there is no real embedder here.

| Measure | Result |
|---|---|
| Recall@5, 71 facts, entity layer | 80.9% |
| Recall@5, 171 to 1,071 facts | 79.8% to 77.7% |
| Two-fact questions | 7/10 |
| Time questions | 10/10, 0 wrong versions |
| "Where did I put" | 13/13 |
| Overnight tidy finder (stand-in model) | precision 1.0, recall 1.0 |
| Learner rows | 6/6, 4/4, 8/8, 37/37, 14/14, 12/12, 10/10, 12/12 |
| Word floor chosen | 0.1 |

**Gap in the tests:** neither eval touches a chat-interplay case. Nothing tests Continue re-sent turns, a game window sliding, or the quick-answer path. Findings 1, 2 and 7 would have shown up if it did. I suggest adding small cases for each.

## What each kind of chat does with learning

Verified against source unless marked.

| Kind | Kept in History | Learned from | Notes |
|---|---|---|---|
| Normal typed | yes | automatic, if typed, untainted and seen live | fine |
| Temporary | never | nothing; only a hash in memory, provenance "temporary" | `jarvis_chat_log.py:1016-1033`; `Remember:` off |
| Voice / hands-free | yes | only with the strict voice check and a trusted start (`check_voice`) | fine |
| Live | yes, kind `live` | like the talk button by default | side talk is neither kept nor learned |
| Continue this chat | same conversation id | same rules, plus finding 2 | taint decided from the PC's own record |
| Chatbot / compare / support | yes, as one record with role `chatbot`/`support` | never, because the learner reads `role == "user"` only | not continuable. Support records are exempt from the keep-days sweep; chatbot and comparison records are not |
| Project | not built | not built | the `project` column is always empty. The Projects screen now says so honestly |
| Imported (§85) | not added to History | cards only, never saved automatically | these facts carry no chat link |
| Game / role-play | see finding 1 | see finding 1 | |
| Crisis | yes, titled "A difficult moment" | never (`owner_turns` skips it) | fine |
| Screen / camera words | words never kept | never; the picture's words count as a tool read and taint the chat | `jarvis_agent.py:5849-5857`. The camera is off; the screen route is not wired yet |

**The outside-text mark survives** Continue, the 30-minute rule, restarts and History reads:
- A new conversation is correctly clean.
- A restart with history on reads the mark from the database (`jarvis_chat_log.py:893-931`).
- A restart with history off, or a temporary chat, fails closed to tainted.

## Findings, worst first

### 1. A game or role-play silently turns into a normal chat after 11 exchanges (medium; reproduced)

- **Cause:** the PC decides "this is a game" from the messages the app re-sends (`jarvis_intake.py:345-360`, via `_temporary_chat` in `games-temporary.patch:39`). The apps keep at most 10 pairs, then cut to the newest 6 (`chat-history.js:66,104,133`; `ChatHistory.kt:113-115,173-182`).
- **Failing case:** "let's play a text adventure", then 15 moves. I ran the apps' exact trim rule. The game is detected for questions 1 to 11 and not from question 12.
- **From question 12:**
  - The chat is written to History as a normal chat, titled with a move such as "I go through door 11".
  - Saved memory is recalled into the role-play.
  - The learner runs. The earlier game turns were registered as "temporary", so any facts become cards rather than saves.
  - The "This looks like a game" line disappears, with no notice.
- **Smallest fix:** the PC keeps an in-memory set of conversation ids it has seen as games, as it does for taint, and `_temporary_chat` checks it. Alternatively, the apps resend `temporary: true` for the rest of that conversation once the route header says the PC made it temporary. The PC-side set is more robust.

### 2. After "Continue this chat", every new fact becomes a card for about 10 questions (medium; reproduced)

- **Cause:** the learner reads every re-sent user turn, and every one must be in the PC's in-memory "seen live" registry (`jarvis_auto_learn.py:1574-1590`, `check_provenance` at `:589-592`). The registry is empty after a backend restart and holds only 200 turns (`jarvis_chat_log.py:200`).
- **Reproduction:** with a real `ChatLog`, I recorded a conversation, simulated a restart, and continued it.
  - "same process": PASS.
  - After restart and Continue: every pass fails with "from a message this PC did not see arrive (re-sent or older history)". It stays that way until the old turns slide out of the window, about 10 turns.
  - Only the new turn on its own passes.
- **Effects:**
  - The owner sees a stream of cards instead of automatic saves.
  - The card's reason reads like a fault.
  - Auto-save is only ever restored by waiting.
- **Related, from reading `jarvis_auto_learn.py:1003-1041` and `:1042-1062`:** "already-forgotten stays forgotten" is held only in memory. Its own comment says the gap "cannot outlive" a restart, because old turns cannot come back. Continue makes them come back.
  - If the owner Forgot or Erased a fact but kept the chat, then after a restart Continue re-proposes it as a card.
  - Layer 2 (`like_forgotten`) matches Forgotten facts only, never Erased ones.
- **Smallest fix now:** reword the card reason ("older messages carried on from History") and say so in the Continue note.
- **Owner's call:** the real fix has the PC re-register the typed and voice rows of a chat from its own encrypted record, when a chat is continued. That changes a safety invariant ("only turns seen arriving live"), so it needs the owner's word.

### 3. Facts accepted by hand lose the link to their chat (medium)

- **Cause:** only auto-saved facts and `Remember:` facts record `conversation_id`. A card accepted by hand keeps only `confidence` and `proposal_id` (`auto-learn.patch:390-397`). `_note_card` stores no chat id (`jarvis_auto_learn.py:1621-1625`).
- **Who is hit:** the sensitive facts (health, money, other people) are exactly the ones that wait for a card.
- **Consequences:**
  - "Erase the words" then says "no chat was on record".
  - Delete's list of "facts this chat taught" (`jarvis_memory.py:4199-4235`) omits them, and the dialog does not say the list is partial.
  - A Forget-a-time-frame chat delete leaves them.
- **Smallest fix:** store the conversation id on the proposal and copy it into the fact's meta on accept. Say "facts you accepted by hand are not listed" until then.

### 4. The delete wording is not fully true, and deleting a chat never says what happens to what was learned (medium)

- **Backups:** the backup file holds `chat-history.db` and its key (`jarvis_backup.py:212`). The backup wording covers only "erased facts stay in older backups" (`:223-225`). The chat dialogs say "removed from this PC", "cannot be undone" and "gone for good" (`history-view.js:261,266,493`; `ChatLog.kt:73,810`; `jarvis_forget_range.py:175`). With backups on, that is not true.
- **Keep-days:** its confirmation says "Delete every conversation older than… from your PC" (`history-view.js:324-326`; `ChatLog.kt:499`). It never says the facts stay.
- **The four delete paths explain themselves differently:**
  - Single Delete offers the facts, with none ticked.
  - Erase-with-chat is silent about the chat's other facts.
  - Keep-days is silent about the facts.
  - Forget a time frame lists facts by the day they were saved, not by which chat taught them.
- **Smallest fix:** add one sentence to the four dialogs: "Facts Jarvis learned stay. Copies in older backups stay until they age out." Whether a deleted chat should be added to the backup wording is the owner's call.

### 5. On two cards, the chat's re-send caps keep the "Longer conversations" lane out of reach (needs two cards; owner's call, measure first)

- **The lane:** SECOND-CARD.md:39 promises a 32,768-token lane on the 12 GB card, costing about 7.7 GB. It is chosen only when the main card would have to trim (`jarvis_agent.py:4207-4224`).
- **The caps:** both apps cap re-sent history at 10 pairs and 18,000 characters (`chat-history.js:66,104`), sized for 16,384 tokens.
- **The arithmetic:** the cap is at most about 6,100 tokens against a budget of about 12,400. History alone can never trigger the lane. Only a single question of about 17,000 pasted characters could.
- **The screen misleads:** the thread shows up to 100 pairs, but the model reads 10 or fewer. When the loaded model has less room, `fit_messages` (`jarvis_agent.py:2338`) drops more, with no sign to the app.
- **Cheap now, either card:** draw a line in the thread, "Jarvis reads from here".
- **Two-card option:** once the second card is installed and measured, the PC reports the lane's size and the apps raise the caps. Keep one card exactly as it is.

### 6. The new thread ignores "Hide memory lists and chat history" (low-medium; owner's call)

- **Phone:** Home's `ThreadFold` shows up to 100 old pairs regardless of the flag (`HomeScreen.kt:2251-2262,2453-2470`). The "Used" list and sources for the same answer do respect it (`HomeScreen.kt:1181,1189`).
- **Desktop:** the bar's thread is not gated either (`main.js:933-955`).
- **Before:** the flag left only the last answer showing. Now a locked-down phone can show a whole chat.
- **Smallest fix:** gate the thread on the same flag.

### 7. The quick-answer path ignores the game rule (low; reproduced)

- **Cause:** `jarvis_quick.py:3707` tests only `temporary is True`. The chat route uses the wider `_temporary_chat`.
- **In a role-play chat:**
  - "Where is my passport" answers from saved memory (`:2847-2855`), while the header says temporary.
  - "From now on, be more plain" writes `manner.json` for good. In a real temporary chat it stays in the chat. I reproduced the write.
- **Fix:** one line, calling the same game check.

### 8. The History kind filter and the word search do not combine (low)

- **Cause:** search takes no `kind`. The desktop asks with `{query, limit}` (`brain.js:3151`); the phone's `searchPath` has none (`ChatLog.kt:126-130`); the phone's search never re-runs on a kind change (`HistoryScreen.kt:155-172`).
- **Failing case:** with "Live only" chosen and a search typed, the results include every kind while the filter still says "Live only".

### 9. An opened chat cannot show what Jarvis learned from it (low)

- The list of facts a chat taught appears only inside Delete (`brain.js:2962`).
- The route exists (§79). Showing it on an opened chat is cheap, and matches the competitors report's gap 5.

### 10. Continue makes "spills" routine in Forget a time frame (low; owner's call)

- A continued chat now spans weeks. "Forget last week" lists it ticked and deletes the whole chat if one message falls inside the days. The warning is there, but it is ticked by default.
- Consider unticking a chat that spills.

### 11. Small silent moments (low)

- Live while Temporary is on is a temporary Live session. It is never in History, and the phone's Live screen shows no sign (`LiveScreen.kt`, `LiveService.kt` and `LiveRules.kt` have no "temporary" text). Reading only.
- Starting Live on the phone wipes Home's chat with no note (`JarvisRuntime.kt:4082`, note `null`). The desktop keeps the screen until the next question.
- Continue with history off gives no warning that new turns will not be kept.
- Deleting the chat another device is in leaves that device's words in its memory, and they keep going to the model until it starts fresh. This only happens for the Continue or Move-it-here same-id cases.

### 12. Docs and dead code (low)

- **§18.6 says Continue skips shared text.** Only a shared message sitting right before a typed one is dropped. A shared-only turn is loaded, with the "shared" tag. Neither app's tests cover that case.
- **`ChatLog.tainted_from`** is used nowhere except tests.
- **"Mind" is still in a comment:** `ChatLog.kt:29`.
- **The word "History"** means the chat list, "History of this fact", and a fact's own history. That is confusing for a beginner.
- Otherwise ARCHITECTURE §5 and §8 are true to the code. The HUD's one chat box, the tray's "Chat history…", the kinds and the Continue rules all match.
- The Projects wording is fixed.

## Efficiency

- The History list is cheap: pages of 30 (max 100), with three small counts per row.
- Word search decrypts every turn of up to 5,000 chats, capped at 4 seconds. It is debounced on both apps and has no index, as required.
- Per-turn work on the PC is small: a hash, a crisis phrase check, and one database read on first contact with a conversation.
- The learner reads the whole re-sent window (up to 8,000 characters) each pass. It runs at most once per 5 minutes. The first question after Continue also pays a cold prompt, about 3 seconds by the code's own estimate.
- Places a beginner must visit: Brain (Memory and History) for what Jarvis knows and what was said, the bar or Home for the chat, and Brain, Work for chatbots. This is reasonable now that the bar has "Earlier chats", and the tray has "Chat history…". There is still no voice "open my chat history".

## Journeys (each app; walked in words, not run on a device)

- **Ask; ask again the next day:**
  - Fine. After 30 quiet minutes a new conversation starts, with one line saying so. The old chat is in History.
  - The phone's conversation vanishes if Android kills the app, and nothing says so.
- **Find an old chat:** desktop, tray "Chat history…" or "Earlier chats" on the bar. Phone, "Earlier chats" on Home. Search works (two letters or more), but see finding 8.
- **Continue it:** works. Watch finding 2, and the extra note it needs.
- **Delete it, and what Jarvis learned:** the facts list appears in the delete dialog only, and is partial (findings 3, 4 and 9).
- **Temporary chat:** works. Games silently stop being temporary (finding 1).
- **Live, then find it:** History marks it "Live" with its length, and can filter to Live only. See finding 11 for the temporary case.
- **A chatbot answer:** kept read-only in History as "Chat with an AI". It is a dead end: you cannot ask Jarvis about it.
- **A support chat:** kept, never auto-deleted, export on the desktop. Fine.
- **Forget last week:** voice fills in the list, and one card plus Windows Hello approves it. Ten minutes of Undo. Fine. See finding 10.

## Good, and should stay

- **One encrypted store, with no plain-text path.** The "seen live" registry stores only hashes.
- **Taint is decided by the PC, from its own record.** It survives restarts and Continue.
- **Chatbot, comparison and support records** are never `user` role, so they are never learned from.
- **The Forget and Erase "hush"** protects against re-learning within a session.
- **Search has no index and reaches no model.**
- **Every risky bulk action keeps its card and Windows Hello.** Delete is a single, owner-approved action.
- **Both apps carry the same words** for kinds, Continue and 30 minutes, tested against one shared contract file.
- **A crisis chat is kept but neutrally titled, and never learned from.**
- **The overnight tidy and "remind me next time"** honour temporary chats and games.

## Owner's call

- **Finding 2:** re-registering a continued chat's own recorded turns.
- **Finding 4:** adding a deleted chat to the backup wording.
- **Finding 5:** raising the re-send caps on two cards.
- **Finding 6:** whether the thread hides under "Hide memory lists".
- **Finding 10:** unticking spilled chats.

The rest are plain fixes.
