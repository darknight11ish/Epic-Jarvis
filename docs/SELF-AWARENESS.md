# What Jarvis knows about itself, and how to ask

This page is for the owner, not for a programmer. It answers one question: now
that Jarvis can describe its own settings, tools, screens and stored things,
what can you actually type or say - and what will it refuse to do?

Lead with the honest part: **three pieces arrived on 2026-11-03 and one is
plumbing that the owner-facing doors will use later.**

What you can use today:

- **More than one chat window on the PC.** Two new buttons beside the HUD's
  settings gear, and a new tray row: **New chat window** and **Open this chat in
  a new window**. Each window is its own conversation; opening a chat you
  already have open brings that window forward instead of making a second copy
  of it. The phone keeps one chat at a time.
- **A self portrait you can read** - the PC's own inventory of every place it can
  open, every setting, every tool, every plug-in, every store and every ability,
  at `GET /api/self`. That is a door for programs, not a screen in either app
  yet; the apps and the HUD can read it.
- **Settings open by asking, as before.** "Open web search", "show me the
  security settings", "take me to what asks first" already jump the app in front
  of you to that section. Nothing changed there except that the two apps now
  understand a wider set of place names from the PC.
- **The Updates card can now read both halves back.** After an update it checks
  the PC's own version and says whether the desktop and the backend really moved
  together, or reports the mismatch honestly.
- **Jarvis can re-read what it can do.** Ask it to "refresh your abilities" (or
  the PC can ask `POST /api/self/refresh`) and it re-reads its own inventory and
  says in one sentence what changed - nothing restarted, nothing changed, no
  approval needed.
- **Jarvis can size up the PC's storage, and only clears anything after one
  card that lists every file.** The scan, the dry run and the card are built and
  tested (see "Storage and space" below); the chat tools that would let you ask
  for it in words are not wired yet.

What is built but not yet connected, said plainly:

- **Opening any menu or screen by asking is not finished.** The PC can name a
  settings section today ("open web search" works end to end). It cannot yet
  name every menu and screen: the two apps are ready for those names, but the
  PC's own side that turns "open history" or "open memory" into a place id is
  not wired up yet. Until it is, asking for one of those is answered in words
  rather than by jumping.
- **Clearing a conversation through one approval card has a route but no button
  yet.** The PC can raise the one carded clear (`POST /api/conversations/clear`,
  one conversation per request, facts kept), and its card is answerable in
  either app; no screen calls it yet. What the History screens do today is
  unchanged: the app asks you "are you sure?" and deletes the one chat, no card
  from the PC.
- **The conversation/opening chat tools are built - and clearing is
  deliberately not one of them.** `self_portrait`, `conversation_find` (titles
  and dates only, never the words), `conversation_open` (one kept chat's turns,
  local model only) and `refresh_abilities` are read-only model tools with no
  card; since 2026-11-04 all four are in the shipped settings file, so a new
  install is offered them without a hand edit. A PC that already has its own
  settings file keeps the list it had - an update never overwrites it - and the
  four can be added there by hand when you want them. **Clearing a kept
  conversation is never a model tool** (Gemini
  ruling 1, 2026-11-03): an AI must never have an autonomous way to wipe the
  transcript, so clearing stays the REST route, an app UI action or the fast
  path, always behind its ONE card.
- **There is no storage tool and no storage screen yet.** The PC can scan, plan
  and raise the cleanup card, and the card is real; nothing in either app or in
  chat asks for it yet, so for now this is plumbing with a tested card.

The rest of this page explains the pieces in plain words.

## One picture of itself

On the PC, Jarvis serves one read-only address, `GET /api/self`. Think of it as
a portrait of the running Jarvis, taken the moment you ask:

| Part of the portrait | What it tells you |
|---|---|
| version and start time | which version of the backend is running, when it started, and what the installer recorded |
| places | every Settings section and every menu an app can open, by the same ids the screens use |
| settings | every setting, its section, its live value - a switch's and a named choice's (the personality, the voice, the focus preset, the hand-off mode and the rest all read their real stored value now) - and how to change it |
| asks first | every action and whether it reads or asks, straight from the "What asks first" page |
| abilities | the plain-words feature list, one row per ability |
| tools | how many tools the backend has built in and which of them are switched on in your own settings file, read live from `[tools].enabled` - the same read the "What asks first" page makes |
| plugins | the optional add-on folders, whether each is on, and why it is off |
| stores | how much it is keeping - memories, conversations, receipts - and how to clear each |
| private | whether App lock or "Hide memory lists and chat history" is on |

**The portrait is read-only.** Asking for it cannot change a setting, clear
anything, run a tool or send anything anywhere. It is served on the PC's own
private network like everything else, and it never contains a password, a
pairing token, a secret value, a word of your memory or chats, or one of your
file paths. If a value cannot be read, it says "unknown" - it never guesses and
it never says "off" for something it could not check.

**The list of places is not a new list.** It comes from the two lists the
project already keeps and tests against the real screens: the Settings registry
(every Settings card, on both apps) and the menu registry (every menu "Show or
hide menus" knows). So a new Settings card or menu appears in the portrait with
no second list to update - and there is nothing that can disagree with the app.

## Asking about itself

These questions are answered by the PC, in one step, with no AI model in the
loop - each from the list or module that already owns the fact, so none of them
can invent an ability:

- "What can you do?" - the feature list, counted and grouped.
- "Where do I change how Jarvis talks?" - the feature guide, with the real
  Settings place.
- "What is connected?" - the "What Jarvis can reach" list's ON rows (accounts
  and services) plus the plug-in folders on this PC. **Not** the model or the
  graphics cards; ask "are you using both cards" for the cards.
- "What tools do you have?" - the registered tool count and the tools switched
  on in your own settings file (`[tools].enabled`), with their plain names.
- "Which of your tools ask before they act?" - the "What asks first" page's own
  rows whose words say they ask you first, with the count.
- "refresh your abilities" - re-reads the inventory above and says in one
  sentence what changed; nothing restarted, nothing changed, no approval
  needed. The same read is `POST /api/self/refresh`.

When the portrait is given to a model (a later piece of work), the same kind of
question will be answerable from the portrait itself, so the answer agrees with
what Settings shows. Until then, the portrait is the source the apps and the
desktop's own version check read - and the questions above are answered by the
PC directly, not by the model.

## "Open <a place>"

Ask in plain words: "open settings", "open the memory screen", "take me to
reminders", "open your voices", "show me goals", "open what asks first".

What happens is **display only**:

1. The PC puts the place into the answer's existing route line (the same line
   that has carried "open this settings section" since September).
2. The app in front of you opens that screen, and the row inside it if you
   named one.
3. Nothing is changed, nothing is approved, and no setting is written. The
   change is still yours to make by hand.

Two honest rules:

- **An app that has no such screen says so.** The phone and the desktop do not
  have the same screens. A place the app in front of you does not have gets one
  plain sentence - "Jarvis asked to open X, but the desktop has no X. Nothing
  was opened." (the phone has its own wording, including "There is no habits
  screen in this app yet") - rather than opening the wrong place or doing
  nothing.
- **Only the window you are in moves.** A navigation is delivered to the main
  HUD window, never to the other chat windows, so asking for a screen cannot
  make a conversation you are reading jump somewhere else.

If the app you are using has hidden that menu ("Show or hide menus"), opening
it brings it back for that visit - it does not change your menu settings.

## More than one conversation window (PC only)

The HUD has two new buttons beside the settings gear:

- **New chat window** (a plus) opens another copy of Jarvis's chat, on a fresh
  conversation.
- **Open this chat in a new window** (two overlapping rectangles) moves the
  conversation you are reading into its own window, so you can keep typing
  there while the first window carries on.

There is also a tray row, **New chat window**, if you keep Jarvis in the tray.
The rules that make it safe:

- **Eight extra windows at most.** That is the guard, not a policy: every window
  is a real browser process holding a conversation, so a runaway loop cannot
  fill the machine.
- **One conversation, one window.** Asking to open a chat that is already open
  brings that window to the front instead of opening a second copy of the same
  transcript - two windows can never write into one chat.
- **Windows are not reopened at start-up.** They are something you asked for in
  that session; Jarvis does not silently reopen five of them when you log in.
  Their size and place are remembered for the next time you open one.
- **App lock and screen capture cover them.** A locked PC hides them exactly as
  it hides the HUD, and they are kept out of screen captures like the HUD.
- **Closing one never closes the others.**

The phone keeps one chat at a time and switches conversations on its History
screen; there is no window fleet there, by design.

## Clearing a conversation

Clearing is **one conversation, one card, one decision**, and on the card the
PC says exactly what will go:

- the conversation's title and how many messages it has;
- that it is removed from this PC and cannot be undone;
- that **the facts Jarvis learned from it are KEPT** - deleting a chat never
  forgets them;
- that copies in older backups stay until they age out.

Approve to delete that one conversation; deny or ignore it and nothing is
deleted. There is no "clear all", no bulk form, and a clear cannot happen
without that card.

**What you can do today:** the History screens delete one chat each, after their
own "are you sure?" question - unchanged. The carded clear above is the PC's new
route (`POST /api/conversations/clear`); it works and its card is answerable in
either app, but no screen calls it yet. When one does, the rule will be the same
one written here.

**Forgetting a memory is a different thing.** It keeps its existing doors: one
fact with Forget, or "Forget a time frame" with its own card, preview and
10-minute Undo. Deleting a chat does not forget its facts, and clearing memory
does not delete chats.

## The Update button: both halves in step

The Updates card has always been able to update the desktop program and the
Python backend together ("Update both halves"). What changed is the **read-back**:

1. The PC's portrait carries the backend's version and the installer's own
   record - which files it replaced, their fingerprints, and after a re-seal the
   repository commit they came from.
2. After an update, and whenever you ask from the Updates card, the desktop
   compares its own version with the backend's.
3. The answer is one plain sentence, and it only says "in sync" when both sides
   really name the same version:
   - **in sync** - both the same;
   - **mismatch** - the backend is older (including a backend too old to answer
     at all): it says so and points at the button that updates both;
   - **newer backend** - safe, the desktop keeps working; updating the desktop
     gets them in step;
   - **cannot be compared / unreachable** - says that instead of pretending.

At start-up Jarvis says it once, only when the backend is behind. It never
checks GitHub from there and it never updates anything by itself.

## Storage and space

Jarvis can take a bounded inventory of this PC's storage and offer to clear only
the temporary things it can prove are safe. The shape is always the same: **look
first, show exactly what would go, then one approval card - and only then is
anything deleted or moved.**

**The look.** The scan reports the drives' free and used space, the folders
Jarvis itself uses (the live Jarvis folder, this repository, its saved-data
folder, the Ollama folder and `%TEMP%`) with how many files and bytes each holds,
and a candidate list of temporary things: Python cache (`__pycache__` folders and
`.pyc` files), Jarvis's own log folder, old deploy backups and the
`.before-`/`.backup-`/`.old-` copies an update left behind, and scratch files
Jarvis made in `%TEMP%`. Every candidate carries exact bytes and times. The scan
is bounded - it says when it stopped early and its counts are then not exact - and
it never follows a link or junction. The big build folders (`node_modules`,
`target`, `build`) are reported as "regenerable, slow to rebuild" and are never
offered for clearing: rebuilding them can take a long time, so that is your call,
not a temporary file.

**The dry run.** Before anything happens, Jarvis builds the exact list of
absolute paths it would clear, with the size of each and one line per path -
delete this, or move that into a quarantine folder. Python cache and its own
`%TEMP%` scratch files are deleted (they rebuild or are worthless); its logs and
the old deploy backups are **moved into `_jarvis-quarantine-<date>` beside the
live program, never deleted**, so you can put them back by hand.

**The one card.** Nothing is cleared until you approve one card that lists every
path in full and says what it means: a deleted file cannot be undone, moved files
are kept, and **nothing of yours is touched** - no memory, no chat history, no
approvals, no receipts, no notes, and never a file this repository tracks. If the
list changes between the card and the yes, the whole run stops rather than
deleting something you did not see.

**What it will never touch.** The saved-data folder (`~\.openjarvis` - memory,
chat history, approvals, receipts, the voiceprint and projects), your Downloads
folder, any file the repository tracks in git, anything behind a link or
junction, anything outside the folders Jarvis is allowed to clean, and the live
program's own files. There is no "clean everything" button and no route that
clears without the card.

**What you can do today:** the PC side and the card are built and tested; the
chat tools and any app screen are not wired yet, so there is nothing to type or
tap just yet. When they land, this is the flow they will use.

## Refreshing what Jarvis knows it can do

Ask "refresh your abilities" (the tool is in the shipped settings file since
2026-11-04, so a new install is offered it; an existing PC's own file keeps its
list until the name is added there) and Jarvis re-reads
its own inventory - settings, tools, places, plugins, abilities - and answers in
one plain sentence: how many of each it can see now, and what changed since it
last looked. The same thing is one address on the PC, `POST /api/self/refresh`.

Three things it never does: it does not restart anything, it does not change a
setting, and it does not need an approval card. It is a fresh look at the same
running Jarvis, not a reset. If nothing changed, it says exactly that.

## What it will never do

- **Never claim more than it can see.** An unknown screen, an unknown setting
  or a missing route gets one honest sentence, not a guess and not a silent
  no-op.
- **Never clear anything without one approval card**, never clear in bulk, and
  never clear from a spoken sentence alone.
- **Never change a setting while "opening" it.** Navigation is display only.
- **Never send the portrait anywhere.** It is served on the PC's own networks to
  the owner's own devices, and it holds no secret values, no chat or memory
  words and no folder paths.
- **Never approve anything.** Reading its own portrait is not a new permission
  and grants no new reach: the same one-card-per-action rules govern everything
  above.

## Where this is written down

- The wire shapes, every route, the card's exact words, the storage scan and
  cleanup, and the version states: [JARVIS-API.md](JARVIS-API.md) section 184.
- The storage module itself: `backend/jarvis_storage_health.py` (its own header
  is the design, in plain words).
- Why it is built this way - read-only portrait, display-only navigation, one
  source for the ids, one card per clear, both halves in step - and what is
  deliberately one-sided: [ARCHITECTURE.md](ARCHITECTURE.md) section 13 and
  section 8 ("One-sided on purpose").
- The owner's own decision, dated:
  `decisions.d/2026-11-03-self-portrait-imported-and-clear-one-card.md`.
