# Chat features on the phone, second play-test (studio, 2026-09-28)

Code walk-through at ffde34a9, not a device test. Parity clean. No certain
compile error found (watch, low risk: `ChatLog.kt` `liveLine` `secs`
Long/0 literal ~610; `HistoryScreen.kt:763-769` multi-line if/else with a
shadowed `t`; `ChatLog.kt` regex `$\\n`; `HomeScreen.kt` import order).
No finding needs graphics memory, a card or a new route.

## Worst three
1. **Starting Live still wipes the Home chat silently** (`JarvisRuntime.kt:4084,
   :4326`, `LiveScreen.kt:271`); no pointer to History when Live ends; plain
   "New conversation" doesn't say the old chat is in History (the desktop
   does).
2. **History's on/off status is hidden** inside the folded "History
   settings" at the very bottom (`HistoryScreen.kt:428-472`): "Waiting for
   your approval to turn chat history on" and the "not recording" warning.
3. **The Home thread and Continue land at the wrong end**: the open fold
   starts at the OLDEST pair, capped at 360 dp (`HomeScreen.kt:2453+`), and
   composes up to 100 pairs eagerly.

## Broken
- B1 The 30-minute note says "The last one is in History." for temporary
  and game chats (`ChatHistory.kt:282`, `ChatSession.kt:353-360`).
- B2 "Live only" filter + word search returns every kind
  (`HistoryScreen.kt:156-176`, `JarvisRuntime.kt:5488`; the desktop
  `brain.js:3128-3146` too). Filter `found` by kind.
- B3 Home's thread pops the wrong pair when the same question is asked twice
  and the second fails (`ChatHistory.kt:329`); the desktop `threadPairs`
  requires phase "done" and a non-empty answer.
- B4 The chatbot plate's "kept in History" promise is unconditional
  (`Chatbot.kt:80-82,118-120,101,132`; `ChatbotPlate.kt:479,612`); read the
  PC's real saved/why-not answer like the support plate (`Support.kt:457`).
- B5 "Continue this chat" on an invalid id says "That chat was deleted…"
  after Home was already wiped (`JarvisRuntime.kt:5449-5452`).
- B6 A chat can be deleted without Home noticing: `setHistoryKeepDays` does
  not call `chatsGone`; Erase with the box ticked before the fact-chat read
  passes `chatId = null` (`AutoLearnPlate.kt:396-410`).
- B7 Possible early "chat gone" after Forget a time frame when the PC
  records the outcome after the card leaves the queue
  (`ForgetRange.kt:340-345`); compare a card id/timestamp.
- B8 Continuing a chat while Live runs here swaps `conversationId` under
  the running session - refuse while `liveOnHere()`.
- B9 Crisis chats and Continue (unverified): a re-sent old crisis message
  may not be skipped by the learner after a restart. Safest: carry nothing
  for a chat titled "A difficult moment"; ask the backend owner.

## Confusing
- C1 "Your next question follows on from the last 3." stays after 30 minutes
  (`HomeScreen.kt:~2415`); the new-conversation note appears only after the
  next send, small, at the bottom (`:2644`).
- C2 A long Continue note can crowd out Home at large text
  (`HomeScreen.kt:2644-2653`); cap at 2 lines with "More".
- C3 Continue skips pairs silently; the line "Carrying on 'X'. Nothing in
  this chat can be carried on…" contradicts itself; say how many were left
  out.
- C4 The "Jarvis read outside text" warning vanishes with the next send.
- C5 Delete/Continue don't say "this is the chat you are in on Home".
- C6 The temporary toggle wipes silently (doesn't say the old chat stays in
  History).
- C7 After Continue nothing scrolls to the Reply plate.
- C8 History rebuilds and jumps to the top on Back; find/continue state is
  lost on rotation (`HistoryScreen.kt:239, 648-669`).
- C9 The kind filter can show a stale error (`HistoryScreen.kt:283-290`).
- C10 No "Open in History" from the ended chatbot/comparison plate.
- C11 "Hide memory lists and chat history" still shows up to 100 earlier
  answers in the Home thread; a crisis question stays in the fold (owner's
  call: rename/expand the sentence).
- C12 "Move it here" reads History even when lists are hidden
  (`JarvisRuntime.kt:4111`); the desktop refuses in Rust.

## Slow, silent, dead-end
`ThreadFold` is a plain Column of up to 100 `FormattedAnswer`s - use a
LazyColumn or the newest 20 + "Show older"; `ChatLog.plainAnswer` runs 7
regexes per message per recomposition - `remember` it; the fact-chat
checkbox vanishes when no chat is on record; Back from "Forget a time
frame" skips Brain; the row date's `today` goes stale after midnight.

## Weak/stale link per control
Reads and navigation are never gated (right). Continue isn't gated by
`actionBlocker` (reads, then local state; plain warn line offline).
New conversation's 30-minute rule fires even when the send then fails.

## Accessibility
`Quiet("Show"/"Hide")` for History settings has no object; `Quiet("Dismiss")`
has no context; `ThreadFold` has no expanded/collapsed state; Continue's
`contentDescription` ("Carry on this conversation on Home.") doesn't contain
its visible words (Voice Access); a newly added live-region note may not be
announced; rotating Home closes the fold.

## Phone vs desktop
New chat by hand (phone says only "New conversation."; desktop says "Chat
ended. Kept chats are in Brain > History."); thread pop rule; thread
question length (full vs 400 chars); "Move it here" with lists hidden;
search vs kind (both wrong); History refresh after removal (re-entry vs
`historyChanged`).
