# Chat features: whole-system audit (studio, 2026-09-28)

Branch tip 40717107. Parity clean; test_chat_log 182, test_temporary_chat 74,
test_forget_range 154, test_live 290, test_chatbot 214, test_chatbot_compare
108, test_games_temp_chat 64; desktop chat-history, history, live, chatbot,
memory-used, forget-range pass. Nothing needs a graphics card.

## How chats are organised today
One encrypted store on the PC (`chat-history.db`, `jarvis_chat_log.py`),
keyed by an app-made `conversation_id`; both apps' History lists, loads
older, filters by title, opens read-only, deletes one (confirm), history on/off
(on = card), "Delete conversations older than", "Forget a time frame". The
conversation in progress lives only in the app's memory (up to 10 pairs
re-sent). Desktop Jarvis bar: current answer + one folded; new on New
conversation, Esc, app start, Temporary toggle, Live start. Desktop HUD: its
own chat, recorded as "HUD", no New conversation. Phone Home: last exchange
only; new on New conversation, process end, Temporary toggle, Live start.
Special kinds: temporary (nothing kept); games (meant temporary - finding
1); voice (kept); Live (new conversation per session, Resume continues; side
remarks not kept; labels decided, not built); crisis (kept, undocumented);
chatbot/compare and deep questions (memory only); project chats (not built);
support transcripts (designed as evidence, with export).

## Findings, worst first
1. **BUG: game and role-play turns ARE saved to history**, against the
   owner's decision. `games-temporary.patch:16-19` calls `record_turn`
   when `TEMPORARY_CHAT` is true; `record_turn` decides "temporary" only from
   `body.get("temporary") is True` (`jarvis_chat_log.py:757`); the app never
   sends it for a PC-detected game. Reproduced: "let's roleplay..." / "I
   attack the dragon" -> recorded, listed in History. The test's stub lacks
   `TEMPORARY_CHAT` (`test_games_temp_chat.py:238`). Fix: pass
   `dict(body, temporary=True)` when `_temporary_chat(body)`; test against a
   real ChatLog; unshallow + `build_patch_history.py`.
2. **No sign that a game chat is temporary** (JARVIS-API §4 ~704 promises
   it): `memory-used.js:66-67`, `MemoryUsed.kt:71-72` show nothing unless the
   app sent `temporary`. Show "This looks like a game or role-play, so it's a
   temporary chat: nothing is kept or learned." and the Remember-off line;
   optionally `temporary_why: "game"` from the PC.
3. **"Move it here" in Live continues the wrong chat on the phone**
   (`LiveScreen.kt:196` `resume = true` skips `newConversation()`,
   `JarvisRuntime.kt:3741`); the desktop starts new (`main.js:5145-5148`);
   comments claim the same chat carries on. Now: `resume = false`.
   Properly (owner's call): the PC's Live status carries the session's
   `conversation_id` and the receiving app takes it over.
4. **Gap: no way to pick up an old chat; the current one is easy to lose**
   (read-only History, `HistoryScreen.kt`, `history-view.js`; lost on Esc,
   phone process end, Live start; no History link from the bar or Home).
   Owner's call: "Continue this chat" + "Earlier chats" links.
5. **Search weaker than it looks** (loaded pages, titles only); the phone's
   "No conversations match that search." (`ChatLog.kt:76`) should copy the
   desktop's wording (`brain.js:2837`). PC-side title search is the owner's
   call (§5).
6. **History has no "kind"** (`jarvis_chat_log.py:417`): Live labels,
   support records, project chats and chatbot transcripts each need one. Add
   `kind` (chat / live / support / chatbot / compare) and `project` once.
7. **Chatbot/compare transcripts thrown away while support transcripts are
   kept** (§60.6; stale comment `jarvis_chatbot.py:112-114`). Owner's call:
   keep them encrypted, outside text, kind `chatbot`.
8. **Support-chat design vs existing rules**: plain-text export breaks
   ARCHITECTURE §5 "no plain-text path" (a named exception or drop it);
   "History search finds it" isn't true for title search; an "evidence"
   record is deleted by keep_days / Forget a time frame / Delete - owner's
   call: exempt or warn.
9. **Crisis turns are kept and can title a chat** - undocumented (§38).
   Owner's call: keep and write it down / neutral title / don't keep.
10. **A conversation never ends on its own** - the next morning continues
    yesterday's (and its "read outside text" mark). Owner's call: new
    conversation after ~30 idle minutes.
11. **You can barely see the conversation you are in** (phone: last
    exchange; desktop: one more). Owner's call.
12. **Two chat boxes on the PC**: the HUD's chat lacks New conversation,
    Temporary, "Used in this answer", the crisis panel, but is recorded.
    Owner's call: open the Jarvis bar from it, or write the gaps in §8.
13. **Undocumented differences** (§8): what ends a conversation; how much is
    on screen; the phone files History under "Memory" though §5 says chat
    history is not memory.
14. Low: stale "Forget those one by one" (`history-view.js:95`,
    `ChatLog.kt:68`); "Mind" leftovers (`HistoryScreen.kt` header,
    `backend/README.md:6416`); the `live` field not stripped before a model
    (`_CHAT_CLIENT_FIELDS`, `temporary-chat.patch:129`) - add it; with History
    off, a project would show no chats - decide before Projects step 4.

## Good, keep
One encrypted store that refuses plain text; the per-conversation "read
outside text" mark; temporary chat end to end; Live side remarks never kept;
Forget a time frame; "Also delete the chat it came from"; stale-link holds on
delete and keep-days; clear transcript notes (shared, pasted, not kept);
"Deleting a chat does not forget facts"; the phone's "follows on from the
last N"; chatbot transcripts never reach memory or the learner; parity clean.

Note: the phone play-test (chat-audit-phone.md, B1) read the game path as
"not kept"; this audit reproduced the opposite against the real chat log -
game turns ARE kept. Trust the reproduction.
