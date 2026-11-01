# Your Obsidian notes: what Jarvis can do, and how

This page is for you, not for the code. It says what to say or click to read
and change a note in your Obsidian vault, what should happen next, and what
Jarvis will refuse. Every sentence on it was checked against the matcher the
code really uses and the words the approval cards really say - not written
from a wish list.

**Where this stands (2026-10-31).** The notes editor itself (list, search,
open, save) is on `main`. The chat doors that read, search and open a note,
and this page's customization wave - formatting, line shapes, headings,
properties, links, templates, the desktop toolbar and the organizer's
choose-your-own-notes mode - are built and tested too, and at the time of
writing they are in pull request #1049, still in CI. Rename and move with link
preservation are built and tested on their own branch and are the "coming
next" section. A deploy is its own pass, and **none of the customization wave
has been driven on the live apps yet** - the cards are the proof point to
watch when it reaches you. Where this page and the app disagree, the app's
card is the truth; say so and the page gets fixed.

## The one rule every change follows

No change to a note happens silently. Every change - one line, one word in
bold, one tag - is:

1. **One approval card**, naming the file and what will change. You say yes or
   no; nothing is written before the yes.
2. **Shown before it lands.** The card carries a small before/after preview of
   the exact change. While your memory lists are hidden, the card shows only a
   count ("counts only") and none of the note's words.
3. **Backed up first.** Right after your yes, and before the write, Jarvis
   takes a File Guardian copy of the note. If that copy cannot be made,
   nothing is written.
4. **One Undo.** The answer says "You can undo it.", and one Undo puts the
   exact old bytes back.
5. **One note at a time, and one exact match when editing existing words.** A
   sentence that changes a word, a line or a heading must match exactly once;
   none or several is refused with the count, never guessed. A whole note is
   never rewritten by one of these edits.
6. **Never a deletion.** No sentence on this page deletes a line, a note or a
   tag's words. There is no delete in the notes lane.

While your lists are hidden, the write doors refuse in the same words before a
card is raised: "Your lists are hidden on this PC, so I did not open or change
a note. Tap Show and confirm it is you, then ask again." The read and search
doors answer with their own withheld sentences, quoted below.

## Where your notes are

**On the PC.** Open the Brain window and choose the **Notes** plate. It lists
every `.md` and `.txt` note in your vault with its title, size and last change;
the search box at the top narrows the list by title and path. Click a note to
open it in the editor. Save is the only thing that writes.

**On the phone.** Open the **Brain** screen; the **Notes** plate is there. You
can search, open, edit and save, and the save asks on the PC with the same one
card - the phone never approves anything by itself. The phone's editor is the
plain text box: the toolbar below is the desktop's.

**In chat, on either app.** Most of this page is sentences you say in chat.
They are answered by fixed code, not by the model, so they work the same every
time and need no AI thinking.

## Read, search and open a note (no card)

These are read-only: no approval card, no write, no model.

| Say | What happens |
|---|---|
| "what does my Shopping note say?" | Jarvis quotes the note's text. It reads the first 4,000 characters, then says "…and N more characters." |
| "read my note Shopping" / "what is in my Shopping note?" | The same read. |
| "which notes mention milk?" / "find my notes about milk" | Matches titles first, then words inside notes. Answers with the count and up to five titles - never note bodies. It looks through at most the first 500 notes and says so when it stopped early. |
| "open my Shopping note" | Names the note and opens the Brain window where the Notes plate is. |

"Read my notes" is answered with "I can read one note at a time; tell me which
one." While the lists are hidden, a read says "The memory lists and chat
history are hidden on this PC right now, so I will not show a note's words."
and a search gives the count only.

The PC's Notes plate search matches **titles and paths**, not the words inside
notes; the chat search above is the one that looks inside notes.

## Create one note

Say: **"create a note called Shopping"**, or **"create a note called Shopping
with milk, eggs"**.

- One approval card says "create Shopping.md in your Obsidian vault (N bytes)".
- If a note is already there: "There is already a note at Shopping.md, so
  nothing was created." - no card, nothing overwritten.
- After your yes: "Created Shopping.md in your Obsidian vault. You can undo
  it." Undo removes exactly the file that was created (and refuses if the file
  changed since).

From the editor, the same thing is: type the text and press Save - the save
card is the only write.

## Add words to the end of a note

Say: **"add milk to my Shopping note"**, or **"add this to my Shopping note:
milk, eggs"**.

- The card says "add N bytes to the end of Shopping.md in your Obsidian
  vault". The old bytes are never rewritten; the new words are added at the end
  with a blank line in front when one is needed.
- The answer says "Added to Shopping.md in your Obsidian vault. You can undo
  it."
- The note must exist. If not: "I could not find a note called "Shopping" in
  your Obsidian vault. Nothing was written - open the Brain window's Notes
  plate to check the name."
- A name that matches more than one note is refused, and the answer lists the
  paths and asks you to say the folder too.

## Put one line under a heading, or next to an exact line

Say one of:

- **"add plank under the Strength heading in my workout log"** - adds the line
  at the end of that section, just before the next heading of the same or a
  higher level.
- **"add mobility before squats 3x5 in my workout log"** - adds the line just
  before the one line that contains that text.
- **"add 5 minutes of rest after Warmed up in my journal"** - adds that line
  just after that line.
- **"add rest to the Strength section of my workout log"** - the same as
  "under the heading".

The heading or the anchor must match **exactly once**. None, or several, gets
a plain refusal naming the count, before any card - nothing is guessed. The
card shows the line before and the line after, and where it will land.

## Format a word: bold, italic, strikethrough, inline code

Say one of:

- **"make bench 3x5 bold in my workout log"** (or "put bench 3x5 in bold in my
  workout log")
- **"put bench 3x5 in italic in my workout log"**
- **"make bench 3x5 strikethrough in my workout log"**
- **"make bench 3x5 code in my workout log"**
- To undo it: **"unbold bench 3x5 in my workout log"**, **"remove the italic
  from bench 3x5 in my workout log"**, or the same with strikethrough or code.

It wraps exactly one occurrence. A style that is already there is a no-op and
raises no card (the answer says "That text is already bold." and the like);
text inside a fenced code block is refused; and text that appears more than
once is refused with the count.

## Replace one exact occurrence

Say: **"replace bench 3x5 with press 3x5 in my workout log"**.

Only one literal occurrence is replaced, and the words must be whole words - a
match inside a longer word is refused and said so. It is never a regular
expression. The card previews the before and after; the answer says what was
replaced and "You can undo it."

## Turn a line into a bullet, number, checklist item, quote or heading - and back

Say one of:

| Say | The line becomes |
|---|---|
| "turn milk into a bullet in my Shopping note" / "add a bullet for milk in my Shopping note" | `- milk` |
| "number milk in my Shopping note" | `1. milk` |
| "turn milk into a checklist item in my Shopping note" / "add a checkbox for milk in my Shopping note" | `- [ ] milk` |
| "turn milk into a quote in my Shopping note" | `> milk` |
| "make milk a heading in my Shopping note" | `## milk` |
| "make milk a # heading in my Shopping note" | `# milk` (one to six `#`, your choice) |
| "turn ## milk back into plain text in my Shopping note" | the heading mark is removed |
| "tick - [ ] milk in my Shopping note" | `- [x] milk` |
| "untick - [x] milk in my Shopping note" | `- [ ] milk` |

The line must be **exactly** the words you name, matched once. Two identical
lines are refused with the count. For tick, untick and "back to plain text",
say the whole line **as it reads**, marks included: "tick - [ ] milk",
"turn ## milk back into plain text", "remove the bullet from - milk". The card
previews the line before and after. "these lines", a whole paragraph, or "move
this block somewhere" are not built - one line at a time.

## Rename a heading, or add a new section

- **"rename the Session heading to Today's session in my workout log"** - one
  exact heading, its level (`##`) kept, every other byte untouched. None or
  several matching headings get a count refusal.
- **"add a new section called Cool-down notes to my workout log"** - adds the
  section at the end of the note (heading plus an optional first line). If a
  heading with that name already exists, the answer says so and nothing
  changes.

## Set or remove a property (front matter)

Front matter is the block between two `---` lines at the top of a note, where
Obsidian keeps properties like `status: active`.

- **"set status to active in my project note"** (also "set status with value
  active in my project note")
- **"remove the status property from my project note"**

One property line at a time. `true`, `false` and numbers are written bare;
anything else is written as a quoted string. Every other property, and every
other byte of the note, is kept. A note with broken front matter is refused,
never "repaired". The card previews the property line.

## Add a wikilink

Say: **"add a link to Workout log in my chat"**. Jarvis appends one line,
`[[Workout log]]`, at the end of the note. One link per request; a link that
is already in the note says so and changes nothing; reciprocal links and
picking a `#section` from chat are not built. (The route behind it can link
under a heading; chat does not offer that yet.)

## Tags: add or remove one

Say one of:

- **"add tag recipes to my Shopping note"**
- **"tag my Shopping note with recipes"**
- **"remove the tag recipes from my Shopping note"**

Where the tag lands: in the note's front-matter `tags:` list when the note has
front matter, otherwise as a visible `#recipes` line - only that one place is
changed. A tag cannot contain spaces. If the tag is already there (or already
absent), the answer says it needed no change and raises no card.

## Templates

**Four built-in templates you can create as a real note**, by saying:

| Say | It needs | What the new note contains |
|---|---|---|
| "create a workout log" | nothing | `# Workout log` with checkboxes under Warm-up, Session, Cool-down and Notes |
| "create meeting notes for the launch" | the topic | `# Meeting notes - <topic>` with Attendees, Agenda, Decisions and Actions checkboxes |
| "create a daily journal" | nothing | `# Daily journal - <today's date>` with What happened, What I noticed and Tomorrow |
| "create a project note for the kitchen remodel" | the name | `# Project - <name>` with Goal, Next steps and Notes |

Each is created through the ordinary create card - one card, collision
refused, one Undo. Saying "create meeting notes" without a topic is refused
with "say the meeting's topic".

**Save a note as a template.** Say: **"save my workout log as a template"**, or
**"save my workout log as a template called My workout"**. It writes one new
`.md` file into the Templates folder: the folder Obsidian's own
`.obsidian/templates.json` names, or `<vault>/Templates` when it names none. An
existing template is refused, never overwritten. The answer names the file, and
one Undo removes it. **"list my templates"** lists the names only, never the
text.

**The desktop editor's template menu.** Above the note box on the PC, a
template picker inserts one of four simple built-in bodies - Workout log,
Meeting notes, Daily journal, Project note - or any `.md` file in your vault's
Templates folder. It inserts the text at the cursor in the box; it creates and
overwrites nothing, and nothing is saved until Save. These four toolbar bodies
are the desktop's own simple text for now; if you want the canonical built-in
body, say "create a workout log" in chat instead.

## The desktop editor's toolbar and shortcuts

The Notes plate on the PC is a real editor with a formatting toolbar above the
box. Every button changes only the words in the box - Save is still the only
write, with its one card. Each button's tooltip says the exact Markdown it
inserts.

| Button | What it inserts |
|---|---|
| B | `**word**` (bold) |
| I | `_word_` (italic) |
| S | `~~word~~` (strikethrough) |
| <> | `` `word` `` (inline code) |
| ❝ | `> ` at the start of each selected line (quote) |
| • | `- ` at the start of each selected line (bullet list) |
| 1. | `1. `, `2. ` … (numbered list) |
| ☐ | `- [ ] ` at the start of each selected line (checklist) |
| H2 / H3 | `## ` / `### ` at the start of the line |
| — | `---` on a line of its own (horizontal rule) |
| [[ | wraps the selection in `[[...]]`; with no selection it inserts `[[]]` with the cursor inside |
| # | `#` before the selection (a tag) |
| Date | the local date and time, for example `2026-10-31 17:58` |
| Code fence | wraps the selection in a fenced code block |

**Keyboard shortcuts** work only while the cursor is inside the note box (no
app-wide shortcut is changed): Ctrl+B bold, Ctrl+I italic, Ctrl+K wikilink,
Ctrl+E inline code, Ctrl+Shift+X strikethrough, Ctrl+Shift+Q quote, Ctrl+2 /
Ctrl+3 headings, Ctrl+Shift+7 numbered list, Ctrl+Shift+8 bullets,
Ctrl+Shift+9 checklist.

Under the box are word and character counts, including the selected words. The
editor does not autocomplete wikilinks: `[[` inserts the brackets only.

**The phone keeps the plain editor.** The toolbar is desktop-only on purpose
(it changes only the box, needs no route, and the phone's box is small); the
reason is written in [ARCHITECTURE.md](ARCHITECTURE.md) section 8.

## Organize the vault

The vault organizer reads every note and proposes a tidy-up; it is **off by
default**, and nothing is plotted or changed while it is off.

**Turn it on** by saying **"turn on the vault organizer"**. That raises one
approval card; until you approve, it stays off.

**Plan the whole vault** by saying **"organize my notes"**, **"plan my vault"**
or **"tidy my vault"**. It answers with its read-only plan and ends with
"Nothing has been changed yet." For example:

> A plan for "vault", without moving a single file:
>   1 note(s) read, 1 to be tagged, 1 Map-of-Content note(s) and 1 Vault Home
>   to be created.
> Nothing has been changed yet.
>
> Applying it asks for ONE approval card for the whole batch, and a note is
> never deleted. Say "apply the plan" when you are ready.

**Apply the plan** by saying **"apply the plan"** (or "organize my vault now",
"tidy it for real", "apply it", "go ahead and organize"). Applying raises ONE
card for the whole batch. On no, "the card was denied, so nothing changed". On
yes:

> Organized "vault": 3 file(s) written, 0 note(s) moved, 2 note(s) created
> (1 Map of Content and the Vault Home). Nothing was deleted. One click of
> Undo puts the whole vault back.

**Plan only some notes** by naming them: **"organize these notes: Welcome,
Alpha"** or **"organize just my Welcome note"**. You get a read-only plan for
just those notes - only the picked notes are read for content or changed, no
note moves, and no Map of Content or Vault Home is created:

> A scoped plan for 2 selected note(s) in "vault":
>   2 note(s) read, 2 to be tagged.
>   Only the notes you picked are read or changed; no other note is read for
>   content, no note moves, and no Map-of-Content or Vault Home is created in a
>   scoped run.
> Nothing has been changed yet.
>
> Applying it asks for ONE approval card for the whole selected batch; only
> those notes are written, no note is ever deleted, and one Undo restores
> exactly that batch. Say "apply the plan" when you are ready.

If you do not name any notes, it says "Name the notes to organize, for example
"organize these notes: Welcome, Alpha". Nothing was changed." - and so does a
name that is not a real, unique `.md` file inside the vault, or one that is
hidden, protected or a link: each gets its own plain sentence ending "nothing
was planned or changed". There is no per-note mode outside an explicit
selection.

## A worked example: make a workout log and log today's session

Say each sentence in chat and press Approve on the card. Everything below is
the real wording.

1. **You say:** `create a workout log`
   **Card:** "create workout log.md in your Obsidian vault (N bytes)", action
   "create a new note". **After yes:** "Created workout log.md in your
   Obsidian vault. You can undo it." The new note is plain Markdown with
   Warm-up, Session, Cool-down and Notes sections, each with a checkbox line.

2. **You say:** `add squats 3x5 under the Session heading in my workout log`
   **Card:** before "- [ ] Exercise - sets x reps", after "squats 3x5", note
   'under the "Session" heading'. **After yes:** 'Added under the "Session"
   heading in workout log.md. You can undo it.' The line lands at the end of
   that section, just before Cool-down.

3. **You say:** `add a checkbox for squats 3x5 in my workout log`
   **Card:** before "squats 3x5", after "- [ ] squats 3x5", note "the line".
   **After yes:** "Turned that line into a checklist item. You can undo it."
   Now today's session is a checkbox you can tick later with `tick - [ ]
   squats 3x5 in my workout log`.

4. **You say:** `make squats 3x5 bold in my workout log`
   **Card:** the exact before/after of the wrap. **After yes:** 'Made "squats
   3x5" bold in workout log.md. You can undo it.' The line becomes
   `- [ ] **squats 3x5**`.

There is no "log my session" sentence that invents text: Jarvis writes the
words you give it. Say the sets and reps as you did above, and tick when the
session is done.

## If something is refused

Refusals are a feature here: they keep a guess from touching your vault. The
message names what to change.

| The answer says | What it means | What to do |
|---|---|---|
| "There is no line that is exactly "X"" | The whole line in the note is not "X". | Say the line as it reads, including any `- [ ]` marks. |
| "X is the whole line N times" / "There are N "X" headings" | The target matches more than once. | Add a word that appears once, or name one heading's exact words. |
| "X appears N times in this note" | The anchor or the formatting target is not unique. | Give words that appear once. |
| "There is no "X" heading in this note" | The heading title is not there. | Copy the heading from the note; headings are matched without the `#`. |
| "that text is inside a code block" | Formatting never edits code. | Change the wording outside the code block. |
| "That name matches more than one note (...)" | Your words fit two notes' titles or paths. | Say the folder too: e.g. "add milk to my Shopping note in 02 - Areas". |
| "I could not find a note called "X" in your vault" | There is no note by that name. | Open the Notes plate and copy the title; check the folder. |
| "There is already a note at ..." / "There is already a template at ..." | Creating would overwrite something. | Pick another name; nothing was changed. |
| "X changed while the card waited" | The note was edited between asking and the yes. | Open the note again, check it, ask again. |
| "Your lists are hidden on this PC, so I did not open or change a note." | Hidden lists or App lock are on - by design no words or titles appear and no card is raised. | Tap Show and confirm it is you, then ask again. |
| "I change one note at a time, so nothing was written" | You said "all my notes"/"every note". | Name ONE note. |
| "Deleting a line or a note is not built, so nothing was changed." | There is no delete in this lane. | Add, format, replace, tag, rename a heading, or move a line into a section instead. |
| "I can read one note at a time; tell me which one." | "read my notes" is not a thing. | Name one note. |
| "Name the notes to organize, for example ..." | A scoped organizer plan had no valid selection. | Name the notes exactly, e.g. "organize these notes: Welcome, Alpha". |
| "That is not one of my features on this PC. Jarvis does not change your Obsidian theme, styles or templates - only Obsidian does that." | Themes, CSS and template files are Obsidian's own, not Jarvis's. | Change them in Obsidian; Jarvis can create a note from a template, not edit Obsidian's template files. |
| "that is not one of the built-in templates" / "say the meeting's topic" | The template name or its required subject is missing. | Use workout log, meeting notes, daily journal or project note; add the topic or name. |

A note that is larger than 2 MiB, is not `.md` or `.txt`, is hidden, is inside
`.obsidian`, or is outside the vault by any path trick is refused before a card
is raised. A note that is a link or junction is refused too.

## Coming next: rename and move, with links kept

Built and tested on its own branch (not part of #1049, so not in the apps yet):

- **"rename my Welcome note to Home"** - one note, same folder, new title. The
  card previews "updates N link(s) in M note(s)", or says there are no links.
- **"move my Welcome note into Projects"** - one note into a folder inside the
  vault; "and create the folder" is needed when the folder does not exist yet.
- Links are kept: `[[old]]`, `[[old|alias]]`, `[[old#section]]`, `![[old]]`
  and path-style `[[folder/old]]` are rewritten where they point at the note,
  and relative Markdown links are resolved from the linking note's folder.
  A move leaves a bare `[[old]]` alone because the title did not change.
  Fenced code blocks and inline code are never rewritten.
- One card covers the whole batch, and ONE Undo restores every original byte
  and path (and removes a folder the move created).
- Refused: deleting, moving outside the vault, renaming or moving folders,
  renaming onto an existing name, moving several notes at once, updating links
  inside protected or hidden notes, and remote-URL links.

## Where the wording came from

The sentences and card/answer words above were read from the code that really
runs them: the notes module (`backend/jarvis_notes_edit.py`) and the chat
matcher (`backend/jarvis_quick.py`), documented in [JARVIS-API.md](JARVIS-API.md)
sections 170.7 to 170.9, with the organizer in section 151. The claims are
proved by the module's own suites (`backend/test_notes_edit.py`,
`test_notes_surgical.py`, `test_notes_write.py`, `test_notes_read_search.py`,
`test_note_and_vault_asking.py`, `test_vault_organizer.py`) and by the desktop
toolbar's Node test. They are **not** a live drive: the customization wave is
still in CI, and the desktop toolbar's real-browser half says SKIPPED where
Playwright is absent. When it deploys, drive it once and compare the cards;
that drive is the last proof this page needs.
