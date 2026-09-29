# Chat features on the desktop, second play-test (studio, 2026-09-28)

At ffde34a9, fake-backend harness (real frontend; Rust, Windows and the
backend are not proven). `test:ui`, `test:a11y`, `test:themes`: 36 commands,
all exit 0, 592 ok. No JavaScript errors. Scripts and screenshots in the
session scratchpad `pt2/`.

## Worst three
1. **After the bar hides and is shown again, an existing conversation can be
   invisible but still re-sent** (needs a Windows check, medium confidence):
   Rust `set_size(750, 80)` on show (`windows.rs:314-317`), then
   `syncWindowHeight` (`main.js:796-810`) reports 80 px and nothing re-grows
   it - no thread, no answer, no "New conversation". Fix: on `focus-input`
   or show, `commitWindowHeight()` with the measured height, or clear a chat
   older than the 30-minute rule when the bar is shown.
2. **History search drops each row's kind** (`history-view.js:583-609`
   `readSearch` copies `hasVoice`/`tainted`, not `kind`; `brain.js` ~3372,
   delete ~2959): search results lose the "Chat with an AI" / "Live · 12
   min" tags, and **deleting a support chat from a search result skips the
   support-chat warning** (the owner decided support chats ask first). Search
   also ignores the "Show" filter. Fix: `kind: readKind(c.kind)`; pass the
   kind to the search or say "all chats" beside results.
3. **The bar never shows the question you just asked, and the thread opens
   on the wrong end**: the phone has a "You" line (`ChatSession.kt`
   `question`, `HomeScreen.kt:2266`); the desktop shows it only after the
   next question. The "Earlier in this chat" thread opens scrolled to the
   OLDEST turns and its scrollbar is effectively invisible
   (`style.css:1004-1009`, `:1836`). Fix: a "You: ..." line above the answer
   (`state.lastPrompt`, `main.js` ~2954); scroll the thread to the bottom on
   open; a visible scrollbar or a fade.

## Broken
- B1 "Erase the words" + "also delete the chat" never offers the chat's
  other facts (plain Delete offers a ticked list) (`brain.js:3808-3835`,
  `answer-memory.js:298-315`). Show the same tick list, or one sentence "N
  other facts learned in that chat are kept".
- B2 `readFactChat` drops `kind`, so a support record reached that way skips
  the support warning (unlikely).
- B3 The "Chat ended. Kept chats are in Brain > History." line is wrong for a
  game chat (`closeCard` only knows temporary from the switch,
  `main.js:608-609, 912`).
- B4 On the "Continuing a chat" card, Copy is live on an empty answer,
  "Earlier chats" sits in the chat you are in, an empty divider under the
  thread.

## Confusing
- C1 The owner's OWN message shows the amber "read outside text" mark beside
  "You" in History; say "Jarvis read outside text during this message" or
  move the mark to the assistant turn; the row note says "a web page, a
  file, an email or another tool's output" on chatbot/comparison/support
  records where "another AI"/"the company" is true.
- C2 After 30 quiet minutes a follow-up ("what did we say about the
  dentist?") loses its context; the note appears only after the send; no
  "Carry on the last chat" button; the card still shows the old answer.
  Keep the old id for a while and add the button (`continueChat(oldId)`).
- C3 Esc's "Chat ended" is not announced (`closeCard` `main.js:881-925`
  never calls `announce`); the "New conversation" button never shows the
  line (`newConversation()` `main.js:3288` clears first, so `hadChat` is
  false); the line stays until the next question.
- C4 Continue drops a pair whose answer was not kept without saying so; a
  very long chat says "Older messages were not loaded" without the count;
  the thread shows only the 10 newest of 25.
- C5 Chatbot, comparison and support views say "kept in History" with no
  link (`chatbot.js:66,79,98,109`, `support.js:93`); add "Open in History"
  (reuse `open_fix_place`); the summary says "Once it ends..." after it ended.
- C6 "Continue" refused while private lists are hidden is a dead end - no
  button for the fix; the search box is shown and does nothing.
- C7 The game notice is one small quiet line; no "Temporary chat" strip.
- C8 The temporary strip reads "Temporary chat  Temporary chat: Jarvis
  won't use...".
- C9 History: "Show" touches its select, the search box wraps; no "Just
  chats" option; the Live row shows the start time, others the last update.

## Accessibility and sizes
- A1 (medium) Every History row has buttons named just "Open"/"Delete" - use
  `aria-label="Open <title>"`/`"Delete <title>"`.
- A2 The thread has no name or role - `role="region"` + `aria-label="Earlier
  in this chat"`.
- A3 (medium) Paper theme contrast: `.thread-q` 2.6:1, the "Earlier in this
  chat" summary 2.7, the chat note 2.8, the status word 3.0, answer text 4.1
  (`.previous-answer .markdown {opacity:.8}` `style.css:999`); `test:themes`
  doesn't cover these pairs. Deep-space 8-10:1, high-contrast 17:1.
- A4 (medium, existing) At 200% text the bar's icon row overflows (fixed
  750 px window, `windows.rs:32`): Live, Temporary, Pin, Enter off-screen;
  at 250% the card-action buttons are cut off.
- A5 (medium) Brain at 200% text: the sidebar's "Work" and "Advanced"
  collide, the content is 531 px in a 440 px view; fine at the 880x600
  minimum unzoomed.

## Worked well
Continue keeps the conversation id and taint, drops unkept answers and turns
Temporary off with a line; support/chatbot/comparison records refuse
Continue with a plain reason; kind tags, Today/Yesterday, the Live filter;
deleting the chat you are in tells the bar; Forget a time frame leaves the
support chat unticked and marks it; the crisis chat is "A difficult moment";
chatbot links show as plain words.

## Desktop vs phone
No "You" line on the desktop; the phone's note has Dismiss, the desktop's
doesn't; the phone's History rows are whole-row targets; the thread scrolls
oldest-first on both.
