# Chat features on the phone: play-test (studio, 2026-09-28)

Code walk-through, not a device test (no Android build; CI's face-shots job
photographs faces only). Parity clean. Every fix is app work, either card,
no extra graphics memory, unless said.

## Worst three
1. Home shows only the last question and answer - you cannot scroll back
   through the chat you are in, though Home says "follows on from the last
   7"; the question is cut to 4 lines. (Desktop keeps a fold-out "previous
   answer".)
2. An old chat cannot be picked up again, and "New conversation",
   "Temporary chat" or "Start Jarvis Live" silently throw away the Home
   chat. Same gap on the desktop.
3. Chats go missing without a word: game/role-play chats silently become
   temporary with no marker; chatbot conversations and comparisons are
   never in History (the phone forgets even the last one on restart);
   deleting the chat you are in brings it back under a new title while its
   old words keep going to the model.

## Broken
- **B1 Game chats become temporary with no marker** (`games-temporary.patch`
  `_temporary_chat`; phone `net/MemoryUsed.kt:71-72`, `net/ChatSession.kt:488`;
  desktop `memory-used.js:66-67`). Nothing sets `_temporary` from the route
  header's `"temporary": true`; JARVIS-API ~705 claims the apps show it.
  Fix: when the route says temporary for a question not sent as temporary,
  show "This chat became temporary because it is a game - it isn't kept or
  learned from", both apps.
- **B2 Deleting the chat you are in: it comes back, and its words keep
  going to the model** (`HistoryScreen.kt:151-155`; `ChatSession` keeps
  `conversationId` and `_history`; `jarvis_chat_log.py:845-854` makes a new
  row for an unknown id). Same after Erase with "also delete the chat"
  (`AutoLearnPlate.kt:355-369`) and "Forget a time frame"
  (`ForgetRangePlate.kt:160-172`). Unverified: the learner is offered the
  full re-sent list, so an erased fact might be proposed again. Fix: after
  any of these, start a new conversation on Home and say so.
- **B3 "Forget a time frame" and the chatbot form lose input on scroll or
  rotate** (plain `remember` in `ForgetRangePlate.kt:73-84`,
  `ChatbotPlate.kt:76-96` inside Brain's `LazyColumn`). Use
  `rememberSaveable` (pattern at `BrainScreen.kt:921`).
- **B4 Chatbot and comparison transcripts have no lasting home** (PC memory
  only, §60.6; phone `JarvisRuntime.chatbotLastId` `:4216` in memory). Interim:
  Copy/Share on the ended summary and "Not kept in History - copy it if you
  need it." Real fix: the designed encrypted history record
  (`CHATBOT-DRIVER-DESIGN.md:436`).
- **B5 Temporary chat on the phone never says so** (`MainActivity.kt:2214-2218`
  drops `setTemporaryChat`'s sentence). The desktop announces it.
- **B6 "Also delete the chat it came from" checkbox**: bare `Checkbox` +
  separate `Text` (`AutoLearnPlate.kt:342-345`) - reuse `CheckRow`
  (`ForgetRangePlate.kt:340-365`); and "Erased." when no chat was on record
  should say none was deleted (`MemoryErase.kt:100`).

## Confusing
- C1 No "Continue this chat" on either app (`HistoryScreen.kt:402-523`
  read-only; desktop `history-view.js`). Load kept turns (last 10
  exchanges), reuse the id, skip `answer_kept: false`, carry taint.
  **Owner's call** (new behaviour).
- C2 Starting Live or a temporary chat wipes Home silently
  (`JarvisRuntime.kt:3741, :3954`; `ChatSession.kt:233-238`). Ask "Start
  fresh? This chat stays in History."; "Back to your last chat" after.
- C3 Live's words vanish when Live ends (`LiveScreen.kt:253-256`); point to
  History; History rows have no "Live" mark (being built, owner decision).
- C4 History hard to find: a small plate ~20 sections down Brain
  (`BrainScreen.kt:560`); no Home link, no `OpenPlace` entry, no voice "open
  my chat history", no shortcut.
- C5 "Forget a time frame" is on the desktop's History tab but in the
  phone's Brain Memory group - link it from `HistoryScreen`.
- C6 Typed dates (`ForgetRangePlate.kt:228-243`) - Material date pickers;
  let a listed chat be opened read-only before unticking.
- C7 Search matches loaded titles only (`ChatLog.kt:222-226`, `:71`); say so;
  the phone's box has no TalkBack label (`HistoryScreen.kt:290-294`).
- C8 Shared-text chats are titled with the shared text
  (`jarvis_chat_log.py:849-850`) - prefer the first typed/voice row.
- C9 "Hide memory lists and chat history" hides History's settings too
  (`HistoryScreen.kt:537-539`, against its comment `:69-71`).
- C10 Oldest exchanges dropped past 10 with no sentence (`ChatHistory.kt`).
- C11 `ChatLog.kt:62-64` still says Forget is one by one - point to "Forget a
  time frame".

## Could be nicer
Old chats cannot be copied (`HistoryScreen.kt:500-504`); spoken turns carry
no mark inside an opened chat; History opens on settings, not chats; Delete
sits above the transcript; keep-days/Delete not greyed on a weak link; no
"Open on Home now" mark; "New conversation" not announced
(`MainActivity.kt:2211`); typed follow-ups after Live join the Live chat;
a retried question shows twice; Projects have no chats yet (say so); no "Ask
Jarvis about this" on a chatbot summary; chatbot and History far apart.

## Phone vs desktop
Earlier answers: none / fold-out; "Forget a time frame": Brain Memory /
History tab; temporary message: never / announced; search box name: none /
labelled; copy old chat: no / selectable; game marker: missing on both;
continue: missing on both.

## Ideas (rules checked)
Long-press icon shortcuts "Chat history" and "New temporary chat"; a Quick
Settings tile "Temporary chat"; an "Answer ready" notification (no words
under App lock / hide-lists; local only); Share one old answer by the
owner's tap (warn on tainted turns); a "Last answer" widget is the owner's
call (leans against the privacy settings).
