# Questions for the owner - 2026-09-27

Short multiple choice, most important first. The first option is always the
recommendation. Reply with numbers and letters ("1a, 2a, 3b ...") or just
"all recommended". I will also ask them in the chat, two at a time.

The reasons are in the linked reports, not here:
feasibility audit `docs/FEASIBILITY-AUDIT-2026-09-26.md` (F-numbers are its
section 5), UI audit `docs/UI-AUDIT-2026-09-26.md`.

**Already done without asking, because your own rule decided it:** the memory
re-ranker is being switched OFF until your PC's self-test shows it helps (you
decided on 2026-09-26 that every memory change must be measured first). Run the
one line in `docs/MEMORY-SCOREBOARD.md` when convenient.

---

## Most important

**1. Email drafts** (F1). When Jarvis saves a draft to your Gmail Drafts
folder, the text goes up to Google.
- **a. A card every time, showing the full draft** (recommended)
- b. A card only if the chat read an email, web page or file, or used a private fact

**2. Plug-in servers ("MCP")** (F2). You said "local servers only". Some
plug-ins are small programs on this PC; others are web services.
- **a. Programs on this PC only, for now** (recommended)
- b. Also services at this PC's own address, such as Logseq's

**3. Back up Jarvis's memory to NordLocker** (your question). Jarvis would
write ONE backup file, locked with a recovery code only you have, into a
folder you pick; if NordLocker syncs that folder, it uploads it, locked
again. Nobody at Nord could read it. Limits: lose the code and the backup is
useless; a fact you "Erase" stays inside older backups until they age out
(Jarvis keeps only the last few). This bends rule 1 for that one locked file.
(The security reviewer recommended "this PC or USB only" before you asked.)
- **a. Locked file into a folder I pick, NordLocker included** (recommended)
- b. This PC or a USB drive only
- c. No backups for now

**4. The 31 new small items** (F3): backup, a crisis help line, "who are you"
answers, both graphics cards' health, and similar.
- **a. Add them to the queue after your four groups** (recommended)
- b. Only the four groups for now

## Looks (UI audit)

**5. Build the UI audit's "do first" list?** The desktop face moves with the
real voices, one animation at a time instead of seven, formatted answers on
the phone, clearer text sizes, and the phone's Brain screen grouped. Approval
cards and errors stay exactly as plain. A picture page is at
`docs/ui-audit-2026-09-26/ui-mockups.html`.
- **a. Yes** (recommended)
- b. Show me the pictures first

**6. The HUD window's colours** (some are too faint to read).
- **a. Use the app's normal colours, following your theme** (recommended)
- b. Keep it always dark, but fix the faint ones

**7. The widget's Approve button** is solid bright green (the bar's is softer).
- **a. Make the widget match the bar** (recommended)
- b. Leave it

**8. Titles on the phone.**
- **a. Keep the phone's own font** (recommended - your 2026-09-23 choice)
- b. Use the desktop's squared-off title font

## Safety and character

**9. Crisis help line** (F8). If you ever write about suicide or self-harm,
Jarvis shows a help number. It contacts nobody and records nothing.
- **a. UK and Ireland: Samaritans 116 123, and 999** (recommended - guessed from your spelling)
- b. Another country (say which)

**10. Messages about a crisis are never learned from** (wellbeing report).
- **a. Yes, never learned from and never counted** (recommended)
- b. Treat them like any other message

**11. The plan card** (F6): one card listing every step of a job; your yes
runs the safe steps; risky ones still get their own card. You wrote "never
approve in bulk", so this is yours.
- **a. Allow it later, only after the safety tests pass** (recommended)
- b. Never - one card per step

**12. "From now on, keep answers short"** and similar (growth report).
- **a. Applies at once, with Undo, no card** (recommended - like the manner setting)
- b. Ask with a card first

**13. The focus streak** (F13): the report card says "Streak: N clean sessions".
- **a. Keep the report card, drop the streak line** (recommended)
- b. Keep the streak

## Smaller ones

**14. The 12 GB card's job** (F7), once it is installed.
- **a. Longer conversations and pictures, with one model** (recommended)
- b. A better voice
- c. Making pictures

**15. Starting a plug-in server** (F9).
- **a. A card when a server is added, and again when its version changes** (recommended)
- b. A card every time it starts

**16. Music and video control on this PC** ("pause", "next") (F10).
- **a. No card, only when you say it yourself** (recommended)
- b. A switch, off until turned on with a card

**17. Alarms on a smartwatch** (F11). A fix last night keeps every Jarvis
notification on the phone, alarms included - made without asking you.
- **a. Keep everything on the phone** (recommended)
- b. Let alarms (only) reach the watch

**18. News headlines and "tell me when this page changes"** (F12) - a new way out of the PC.
- **a. Not now** (recommended)
- b. Yes, one card per address you add

**19. Games and role-play** could be saved as facts by automatic learning.
- **a. Run them in a temporary chat automatically** (recommended)
- b. Leave it to me to switch on temporary chat

**20. Inside jokes** (growth report): let Jarvis keep a short "between us" list you can see and forget.
- **a. Yes, listed in Brain like other facts** (recommended)
- b. No

---

## Things to do on the PC (not decisions)

- Run the memory self-test: the one line in `docs/MEMORY-SCOREBOARD.md`.
- After the next update, check that installing a model from the phone still
  works (a new safety setting, `OLLAMA_NO_CLOUD=1`, should not affect it, but
  nobody could test it here).
- Send copies of four files that only exist on your PC, so they can be read
  before anything builds on them: `jarvis_undo.py`, `jarvis_ledger.py`,
  `jarvis_watch.py`, `jarvis_persona.py`.
