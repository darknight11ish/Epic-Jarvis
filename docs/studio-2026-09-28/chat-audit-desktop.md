# Chat features on the desktop: play-test (studio, 2026-09-28)

Fake-backend harness (real frontend, stubbed Tauri bridge). `test:ui` 519
ok, `test:a11y` 31 ok, `test:themes` 11 ok. Screenshots and driver scripts
in the session scratchpad.

## Worst three
1. Yesterday's chat can be found but not carried on - History only reads or
   deletes; no Continue, no Copy (both apps). Esc in the bar quietly ends
   the conversation with nothing saying where it went.
2. Chats with other AIs and project chats are not in History; Projects
   promises "project chats" that do not exist.
3. History is hard to scan: first-line titles ("ok", "hey", "(no title)"),
   Live not marked, title-only search, dates without time or "Yesterday",
   raw markdown in answers, "Forget a time frame" at the very bottom.

## Broken or untrue
- **B1** Projects says "Jarvis reads this in this project's chats"
  (`projects.js:32`, phone `Projects.kt:61`) but project chats are step 4,
  not built (`jarvis_projects.py:26-40`). Say "Saved for later: Jarvis does
  not read this in chats yet." in both apps and the contract file.
- **B2** A finished chatbot/compare summary vanishes when the Brain window
  closes (`brain.js:3971, 3986-4009` keep ids in page JS; `windows.rs:497-518`
  has no close handler for the Brain). Keep the ids in `localStorage` (ids
  only) or ask the PC for its latest; add "Not kept after Jarvis restarts.
  Copy the summary if you need it."
- **B3** History's status line stuck on "Link live · reading…"
  (`brain.js:295` `history: []` in `VIEW_SECTIONS`; `paintFreshness`
  `:860-878`); likely the same for projects (`:302`). Record
  `state.readAt.history` in `loadHistory()`.
- **B4** Erase + "Also delete the chat it came from": the second confirm
  (`auto-learn.js:230`) doesn't name the chat; if none is found
  (`chat_deleted: false`) the toast is just "Erased." Name the chat, or skip
  the question when there is none; say when it was not found.
- **B5** History doesn't refresh after Erase or "Forget a time frame"
  (`forget-range-panel.js`, `eraseFact` don't call `loadHistory()`; 15 s
  re-read, `brain.js:2546`). Reset `chats.at` and reload after writes and
  Undo.

## Confusing
- C1 Esc ends the conversation (`main.js:826-854` `closeCard()`), clicking
  away keeps it; footer says "Esc dismiss". Label "Esc: end chat" and show
  "Saved in History (Brain > History)", or make Esc only hide.
- C2 The bar shows only the latest answer and one folded question; the
  current question isn't shown. "Conversation · 3 questions · See all".
- C3 No way from the bar to History (tray > Open the Brain > History,
  `tray.rs:267`). A tray item "Chat history…" and a bar link.
- C4 No Continue / Copy in History (`brain.js:2849-2853`,
  `history-view.js:297`; phone the same). Continue loads kept turns into the
  bar's conversation with the same id; taint carries over.
- C5 Titles don't identify chats; the delete dialog shows only the title
  (`history-view.js:269`). Date and time in the delete question; first line
  with 4+ words as title; later a local-model title.
- C6 Live sessions not marked (no kind field). A `live` flag and tag.
- C7 Search is titles in loaded rows only (`brain.js:2831-2833`);
  placeholder "Search titles…".
- C8 Times vague and different from the phone (`history-view.js:234-252`
  vs `ChatLog.kt:333-351`); "turns" vs "messages". Copy the phone's
  `whenLine` and "messages"; optionally group Today / Yesterday / This week.
- C9 Raw markdown in History answers (`history-view.js:320`; phone
  `HistoryScreen.kt:500`) - use the bar's safe `markdown.js`; the phone
  strips `**`, `#`, list markers at least.
- C10 "Forget a time frame" at the bottom (~2,290 px down, `brain.html:459`)
  - a button at the top.
- C11 The temporary-chat ghost mid-chat wipes the screen silently
  (`main.js:563-568`); announce "Your earlier chat is in History. This one is
  temporary."; a visible "Temporary" word.
- C12 Chatbot/compare transcripts live only on Brain > Work until the PC
  restarts (§60; `chatbot.js:75,104`) - say so, Copy button, a History line
  pointing there; later keep them in encrypted history as outside text.

## Could be nicer
Search box enabled over the hidden list (`brain.js:2809`); "Delete
conversations older than" doesn't say how many first; `DELETE_KEEPS_FACTS`
(`history-view.js:95`) should point to "Forget a time frame"; a "Back to
list" link for long transcripts; checkbox alignment in "Forget a time frame".

## Desktop vs phone
Dates and "turns"/"messages" differ; Erase has two dialogs vs one checkbox
(written down); neither has Continue, markdown in History, or a Live mark;
both carry the untrue Projects line.

## Ideas (either card, no graphics memory, rules checked)
Continue in History; a tray item and bar link "Chat history…"; Ctrl+H opens
History on the current chat; group History by day with times; short
local-model titles made while idle (never temporary chats); chatbot and
compare transcripts in the encrypted History as outside text; a "Live" tag.
