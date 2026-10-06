# The second graphics card

**Short version:** everything Jarvis can do with a second graphics card is
built, and all of it is **off**. Nothing can be switched on until Jarvis sees
a capable second card in the PC. Each switch, when you turn it on, asks you
first with an approval card. Turning a switch off never asks.

This page says what each feature does, how to fit the card, the one command
you need to run once, and what was deliberately not built.

The numbers behind all of it (how much memory each model needs) are in
[MODEL-TOPOLOGY.md](MODEL-TOPOLOGY.md), "The planned second card".

---

## What "capable" means

Jarvis looks at your graphics cards with `nvidia-smi` (NVIDIA's own
command-line tool, installed with the driver). A second card counts only if:

- it is **Turing or newer** (the RTX 20 series, or GTX 16, or later). Older
  cards cannot use the compact memory format everything here is sized for.
  A Tesla P100 in particular is a poor fit - MODEL-TOPOLOGY.md explains why.
- it has **8 GB or more** of memory (added 2026-09-30; before, 10 GB). A card
  sold as 8 GB reports 8,192 MiB, and some drivers a few MiB less, so the
  line is drawn at 7,680 MiB. A 6 GB card is still refused.

What a card can do depends on its size. **The cards are now installed and
measured** (2026-10-05): both are present, the everyday model is on the 12 GB
card, it is 100% on the card with nothing spilling to the processor, and its
context is 4,096 while 16,384 fits and leaves room
([MEASURED-2026-10-05-owner-pc.md](MEASURED-2026-10-05-owner-pc.md); re-measure
with `scripts\measure-cards.ps1`, described in
[MEASURE-CARDS.md](MEASURE-CARDS.md)). **The rows below are still worked out on
paper and none of them is measured** - they are what each card size *can* run
once its lane is switched on, and no lane is on yet:

| Card | What it runs |
|---|---|
| **8 GB** | Learning in the background and the Wiki builder (the 8B model with room for 16,384 tokens, or 8,192 if a monitor is plugged into the card), and Pictures (8,192 tokens) **only when no monitor is plugged into it**. **Not** Longer conversations or Browser control: an 8 GB card holds no more conversation than your main card's 16,384, so they would not help. What it is good for is taking that work **off** the main card, so chat is never slowed by it. About 6.5 GB of its 8 GB is used, so it is tight: if answers get slow, the model may not fully fit. |
| **10, 11, 12 GB** | Everything, exactly as before (the 8B model with room for 32,768 tokens). |
| **16 GB and 24 GB** | The same as a 12 GB card. The 8B model's own length is 32,768 tokens, and going past it is not something Jarvis has tested. A bigger model (Qwen 3 14B, about 11.7 GB with 32,768 tokens) would fit, but it is **not switched on**: it would change which model writes your answers, and Jarvis's tool and learning tests were measured on the 8B. That is your call, later. The extra memory stays free until then. |

The card that runs everyday chat (the "main" card) is: the one named in
`[compute] primary_gpu` in `jarvis-framework.toml`, if you set it; else the
one the "Everyday chat runs on" setting in the Hardware screen pins, if you
pinned one there; else **the card the model is really on**, read from
`ollama ps` and `nvidia-smi`; else the one your monitor is plugged into; else
the first one `nvidia-smi` lists.

**The "card the model is really on" step was added to the plan on 2026-10-06,
and it is the one that changes what you see.** Before it, the plan took the
monitor rule while the "Everyday chat runs on" setting read the machine - so
on this PC the boot banner and the Brain pane said chat was on the 2080
SUPER (the monitor card) while the model was really on the 12 GB 2060. Now
both read the same thing, in the same words. When the model cannot be read
at all - nothing is loaded, or the driver does not name the program using a
card - the sentence says so plainly ("Jarvis cannot see which card the model
is on, so everyday chat is only ASSUMED to be on the ... - an assumption,
not something it read") rather than naming a card it did not see. Jarvis
still has to pick one card to plan around; it just no longer claims to have
read it.

**Corrected 2026-10-05.** This used to end "With the monitors on the 2080
Super, that is the 2080 Super, which is what you want: it is the faster
card." Two things were wrong with that. The machine says otherwise - the
model is running on the 12 GB card, which `nvidia-smi` calls **GPU 0**,
while the 2080 SUPER is **GPU 1** and runs the desktop
([MEASURED-2026-10-05-owner-pc.md](MEASURED-2026-10-05-owner-pc.md)) - and
**no speed comparison between these two cards has been measured on this
PC**, so "the faster card" was never a measured claim here.

The monitor rule above is now only the *fallback for planning*: with nothing
pinned, Jarvis does not claim to know which card chat is on. It reads
`ollama ps` and `nvidia-smi` and says what it sees - the "Everyday chat runs
on" setting on the Hardware screen in both apps shows that sentence, the
facts behind it, and a button to pin a card (one approval card) or to go
back to leaving it to Ollama (immediate). `scripts\measure-cards.ps1` reads
the same thing by hand.

## The choice: two ways to use your cards, pick one

*(Added 2026-10-05, because you asked for it.)* At the top of Settings →
**Second graphics card** (and above the second-card plate in the phone's
Brain) there is now **one choice, in plain words**, instead of leaving you to
work it out from the switches:

- **One model across both cards** (`split`) - Jarvis loads one bigger model
  and spreads it across both cards, so you get a model neither card could hold
  on its own. It is **slower per word**, because every word has to cross from
  one card to the other and back, and it needs **both cards to itself**, so
  none of the switches below can be on at the same time.
- **Two models at once, one on each card** (`concurrent`) - your everyday
  model stays on your main card and a second, different model runs on the
  other card. Each one runs at its own full speed and the two work at the same
  time; that is what the switches below set up. The catch is size - each model
  still has to fit on its own card.

**They cannot both run, and the screen will not let you think they can.**
Picking the first one while any switch below is on is refused, and the refusal
tells you **exactly which switches to turn off** by name (it used to say "the
second-card features", which left you to find them). Picking the second one
just turns the first one off, straight away and with no approval card -
turning something off never needs one.

**Picking "one model across both cards" asks you first.** It raises the same
approval card the "One bigger model on both cards" switch already raises
(`second_card_combined_enable`), because it is the same decision: nothing runs
until you say yes on that card. Its own row is still lower down the page -
**it is the same setting, and either control moves both.**

**There is nothing to keep in step.** Jarvis does not save "which one you
picked" anywhere. It works the answer out from the switches themselves every
time it reads them, so the choice and the switches cannot disagree. This is
deliberate: a saved "mode" beside the switches would be a second thing to keep
in step, and the one mistake that would matter - the file saying "split" while
the switches say the other - is exactly the mistake a second stored field
invites.

**The spread setting, plainly.** For one model to cross both cards, Ollama has
to be told to use every card it can see. That is one setting
(`OLLAMA_SCHED_SPREAD=1`), and **Jarvis sets it on the copy of Ollama it
starts for this** - you do not set it, and your everyday Ollama is not changed
at all. Your everyday Ollama stays pinned to your main card by the one command
in "The one command to run" below, exactly as before. **You never need to
restart Ollama for this**: the copy that carries the setting is started fresh
when you pick this way, and stopped when you pick the other.

**Worth knowing before you pick it, and calculated rather than measured.**
Ollama divides the model between the cards by how much **free** memory each
one has, so if your everyday model is still loaded on a card, that card has
less room than this plan expects. On your PC today your everyday model is held
on the 12 GB card for as long as Ollama runs, with no time limit set. Nothing
unloads it for you. If "one model across both cards" turns out slower than
expected, or will not fit, that is the first thing to look at.

## The seven switches

(Five since 2026-09-24; **Study helper** and **Referee suggestions** joined on 2026-09-30, both off.
The card they were waiting on is installed and measured as of 2026-10-05, so
turning either one on is the owner's decision now - see the two rows at the end
of the table.)

There is one main switch ("use the second card") and one switch per feature.
The main switch must be on before any feature can be.

| Feature | What it does | Model | Memory on the card |
|---|---|---|---|
| **Longer conversations** (`long_context`) | When a chat grows past what the main card has room for, that answer is written on the second card, which has room for twice as much of it (32,768 tokens; the everyday model on the main card has 16,384). Short chats stay on the fast main card. | `qwen3:8b` with room for 32,768 tokens, on any capable card (10, 11 or 12 GB). | about 7.7 GB |
| **Pictures** (`vision`) | A message with a picture (a screenshot from Alt+Shift+S) goes to a picture-reading model on the second card, so Jarvis actually sees it. Pictures still never go to the internet. | `qwen2.5vl:7b` | about 7.2 GB (**an estimate** - see "Not checked" below) |
| **Learning in the background** (`learning`) | The memory learner (which suggests facts for you to review) runs on the second card, so it never slows chat down, and it waits only 10 seconds of quiet instead of 45. If the second card does not answer, that pass is skipped (it is not moved to the main card after only the short wait). For the next 10 minutes learning then works as it did before: the full wait, on the main card. After that the second card is tried again. | same as Longer conversations | shared |
| **Browser control** (`browser_control`) | Jarvis can work a web page for you, one approved step at a time. Needs Longer conversations on too, and `"browser_control"` in `[tools].enabled`. Its approval card is a different kind from the others (`second_card_browser_enable` in `jarvis-framework.toml`, which must stay `"ask"`), and it says plainly that the pages are on the internet, so what Jarvis types or clicks there reaches that website. | same as Longer conversations | shared |
| **Wiki builder** (`wiki`) | Turns documents you put in your vault's `Jarvis Wiki/Sources` folder into linked wiki pages, one approval card each. See "Wiki builder" below. | same as Longer conversations | shared |
| **Study helper** (`study`) | "Quiz me on a text" and Spanish practice write their questions, and mark your answers, on the second card, so a quiz never slows the everyday chat. Your text and answers stay on this PC. The marks stay "Jarvis's guess" until the grader test has been run on this model too (`eval_quiz_grader.py`, JARVIS-API section 108.3). Using the bigger model for marking is not built. | same as Longer conversations | shared |
| **Referee suggestions** (`referee`) | When a goal step's number reaches its target, Jarvis asks "This looks done - tick it?" on a card with the numbers. Only your tap ticks it; it never runs a test and never ticks by itself (at most 3 cards a day, none in a focus session or Quiet). Today it compares numbers on this PC and loads **no model**, so it starts no second Ollama and does not stop "One bigger model on both cards". It needs the card only because the later version (reading a project's changes) will use its model. JARVIS-API section 108. | none yet | none |

The second card holds **one model at a time**. If Pictures and Longer
conversations are both on, the second card swaps between the two models as
needed (a few seconds each time). That never touches the main card, so
everyday chat is never slowed by it.

**If a model is not installed**, the switch can still be on; the feature just
waits, and its status line says which model to install. Install it the usual
way: Brain window, Model, Models (the Install box), or `ollama pull <name>` in a terminal (for example
`ollama pull qwen3:8b`).

## One bigger model on both cards (a sixth switch, off by default)

The five switches above each run a small model (7-8B). This one is
different: instead of picking one card for a small model, it uses **both
cards at once for one bigger model** - `qwen3:14b`, with room for 32,768
tokens (double the everyday model's room). Off by default, and not
something the five switches above can share: turning this on needs both
cards to itself, so it refuses to turn on while any of them is genuinely
on, and turning any of them on is refused while this is on. Turn one side
off first.

**Why bother**, if it needs both cards? Because 14B is a noticeably smarter
model than the 7-8B models everything else in this file uses, and neither
card alone has room for it at a useful context size - together they do.

**How fast is it?** Slower than either card would be on its own, and here
is the honest reason why, checked in Ollama's and llama.cpp's own code
(not guessed): Ollama splits the model between the two cards **by how much
free memory each one has right now, not by how fast it is**. Your planned
pair has an RTX 2060 with more memory than the RTX 2080 Super, but the
2060's memory is the *slower* of the two - so most of the model lands on
the slower card, and answers come out at roughly its pace. **Real speed has
not been measured yet** - the card is installed (2026-10-05), but no lane is
switched on, so nothing about the split's speed has been measured. Once one is,
the desktop's Hardware screen "Measure" button (or asking Jarvis one
question and timing it) tells the truth about it.

**Turning it on**: Settings → "Second graphics card" (desktop) or Brain
(phone), the same place as the five switches, a new "One bigger model on
both cards" toggle underneath them. It asks with one approval card first
(`second_card_combined_enable`), the same as any other switch here.

## Jarvis noticing you might want the bigger model

Jarvis can also notice, on its own, that this conversation could use the
bigger model above - and OFFER to turn it on. It never turns it on by
itself; the offer is the exact same approval card the switch above already
raises, just raised by Jarvis instead of by your own tap, with one added
line saying what it noticed.

Two things Jarvis watches for, each its own switch under "When to suggest
the bigger model" (same screen, both on to start):

- **When Jarvis is visibly struggling** - it had to ask the model to try a
  tool call again more than a couple of times in one conversation.
- **When you correct an answer more than once** - you told Jarvis it got
  something wrong more than once in the same conversation (a "wrong" mark,
  or saying something like "that's wrong" or "try again").

It only ever offers when a genuinely capable second card is actually there
right now - the exact same check the switch above needs, never a looser
one - and it will not nag: at most a few offers wait for an answer at any
time, never while you are mid-conversation, and a "no" keeps it quiet for a
day, then a week, then a month. Turning either switch off just means Jarvis
never asks that way; it never stops you turning the switch above on
yourself, any time.

## A third graphics card

If your PC has a THIRD card - besides the everyday one and the second one
above - and it is capable (the same rule as the second card: Turing or
newer, 8 GB or more), Jarvis finds it and shows it, but it does nothing on
its own. That is on purpose: which of the five switches above runs on which
physical card is a real decision, and Jarvis never makes it for you by
guessing "the biggest card wins" or any other default.

**The card must be the one you approved (2026-09-30).** Jarvis picks the
third card afresh each time it looks (most memory first, then the lowest
number), so swapping, moving or adding a card can put a different one in
the third place. When you approve a move, Jarvis saves the card's own id
with it, and the move only counts while that same card is in the third
place. If it is not, nothing runs on the new card, the app says so in
words, your choice is kept, and the feature keeps working on the second
card until you approve the move again. A choice saved before this was
added has no card id, so it asks again once (the safe way). The third
card also only offers the switches its own size can run: an 8 GB third
card offers Learning and the Wiki builder (and Pictures without a
monitor), never Longer conversations or Browser control.

**Move a switch there.** Once one of the five switches above is already
on, Settings → "Second graphics card" (desktop) or Brain (phone) shows a
new "Third graphics card" section underneath "One bigger model on both
cards", listing the switches that are currently on. Pick one, and it moves
there - it does not turn the switch off or on, it only changes WHICH card
its model calls go to. Moving one there asks with one approval card first
(`second_card_third_assign`), naming the exact card, its model and how much
memory it uses - the same shape as the five switches' own cards. Moving a
switch back to "Not used" is immediate, like turning any switch off.

**It runs at the same time as the second card**, not instead of it - two
different switches can each be working on their own card at once. Only one
switch can be on the third card at a time, since there is only the one
extra lane; the switch itself still has to be turned on above before it can
be moved here.

**"One bigger model on both cards" stays two-card-only.** A third card is
never part of it - that switch still only ever uses the everyday card and
the second one, because how fast splitting one model across even two cards
really is has not been measured yet (the card is installed; no lane is on, so
nothing about the split has been measured).
Adding a third untested unknown on top of a first untested one is not a
decision Jarvis makes on its own.

## What happens when a switch is on

Jarvis starts a **second copy of Ollama** (the program that runs the models)
that:

- listens on `127.0.0.1:11435` - this PC only. Not your network, not
  Tailscale, not the internet. This cannot be changed.
- can see **only the second card** (it is told the card's id, which starts
  `GPU-`).
- holds one model at a time, with the compact `q8_0` memory format.

**It waits while the big model is using this card.** If the big model
([BIG-MODEL.md](BIG-MODEL.md)) is running on the second card, turning a
switch on is refused with "Not now: the big model is using the ...", and
says when it will stop. Try again once it has stopped. The two never run on
the card at the same time.

**`flash_attention = "off"` is refused.** If `[second_card]` in
`jarvis-framework.toml` says `flash_attention = "off"`, the second copy of
Ollama does not start, and the switch says why: the compact memory format
cannot work with it off. Delete that line (or set it to `"auto"`, the
default) and it starts.

**Standby frees this card too.** Choosing Standby (tray menu or phone)
stops this copy, which frees everything it held on the card. It stays
stopped until you use a second-card feature again, or Jarvis leaves
Standby; background learning does not wake it. The big model is stopped
the same way, unless it is in the middle of a job you asked for - that is
left to finish.

When every switch is off again, Jarvis stops that copy. It never stops an
Ollama it did not start: if something else is already using port 11435,
Jarvis says so and leaves it alone. Its log is `second-card-ollama.log` in
the Jarvis settings folder (`%USERPROFILE%\.openjarvis\` unless you moved it).

## Fitting the card

Follow the checklist in [MODEL-TOPOLOGY.md](MODEL-TOPOLOGY.md), "Before and
after installing": check the power supply, plug **the monitors into the 2080
Super**, and after installing run `nvidia-smi` in a terminal to see both
cards listed with the same driver version.

## The one command to run: keep everyday Ollama on the main card

Your everyday Ollama (the one Jarvis chats with) must only use the main card.
Otherwise, once the second card is in, it may put the everyday model on the
second card, where it is slower and takes memory the features need.

Jarvis cannot change another program's settings, so this is yours to run,
once. Jarvis shows the exact line, with your card's real id already filled
in, on the second-card screen (`pin_command` in `GET /api/second-card`). It
looks like this - **use the one Jarvis shows, not this example**, because the
id below is made up:

```powershell
[Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', 'GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10', 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', '0', 'User'); Write-Host 'Done. Now quit Ollama (right-click its icon by the clock, then Quit Ollama) and start it again from the Start menu. Nothing was written to any file.'
```

To find the id yourself: run `nvidia-smi -L` and copy the `GPU-...` part of
the 2080 Super's line.

What it does: it sets two settings for your Windows user, which Ollama reads
when it starts. The first says "use only the main card". The second
(`OLLAMA_VULKAN=0`) turns off Ollama's other way of reaching graphics cards
(Vulkan), which ignores the first setting and could still reach the second
card. Nothing is written to a file. To undo both later:
`[Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', $null, 'User'); [Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', $null, 'User')`.

Jarvis checks this for you, as well as it can (`main_ollama_pinned`): it
reads that setting, and asks `nvidia-smi` whether an Ollama it did not start
is using the second card. Windows sometimes does not tell `nvidia-smi` which
program uses which card, so a "yes" is a good sign, not a guarantee.

**Since 2026-09-25 there is a fuller command.** Settings, "Hardware and
models" (Brain, "Hardware" on the phone) offers three setups for your cards,
and each comes with its own one-line command: the two settings above, plus
the conversation format, keep-alive and the owner's 0.75 GB gap - and an
undo line that puts back what was there before. **Once you choose a setup,
use that command instead of this one.** This one keeps working as it does
today. With a setup chosen, the switches below follow it: it can move the
extra features to the other card (it turns the main switch off, so its card
names the new place), and on one big card it runs them beside chat in your
everyday Ollama, which the switches could not do before
([HARDWARE-PROFILES.md](HARDWARE-PROFILES.md), section 7.1).

## Switching on

1. Fit the card, run `nvidia-smi`, run the command above.
2. Install the models you want (`ollama pull qwen3:8b`, `ollama pull
   qwen2.5vl:7b`).
3. Turn on the main switch, then a feature. Each one raises one approval
   card that says which card, which model, how much memory, and that nothing
   leaves the PC. Say yes on the PC or the phone.

**On the phone:** open the Brain (the button on Home), then the "Second graphics
card" section, under Model. It shows what Jarvis found, the main switch and
one switch per feature. Turning one on raises the approval card; the switch
says "Waiting for your approval. Approve it on your PC or on this phone's
Home screen." until you answer it. If the card ends without turning the
switch on, a line under the switch says how (for example "You said no, so
"Pictures" stays off."). With Pictures working, chat gets a Photo button.

**On the desktop:** Settings, "Second graphics card". The same list, the main
switch and one switch per feature; turning one on raises the same approval
card. It also has **"Everyday chat runs on"** (2026-10-05): leave the choice
to Ollama (the default), or pin one card - its own approval card, and going
back is immediate. Under it is where the model really is, read from `ollama ps`
and `nvidia-smi`, and a "Show the analysis" button with each card's own facts
and the lines from your own measurement. With Pictures working, a screenshot
question goes to the second card, and the answer's badge says "on the second
graphics card".

**Then measure before trusting it** (CLAUDE.md: "installed and measured").
With a feature on, ask something that uses it and watch `nvidia-smi` in a
second terminal: the second card's memory should go up and the 2080 Super's
should not. The log file above shows what Ollama did.

## Wiki builder

**Short version:** put a document in a folder, press **Add to wiki**, and say
yes to the card. The model on the second card reads it and writes linked
pages about the people, topics and things in it, in your Obsidian vault.
Nothing leaves this PC, and nothing is written until you say yes.

It works only when the "Wiki builder" switch above is on and working (the
second card is in, its Ollama is running, the model is installed). Until
then the Wiki plate says why, in the same words as the switch.

**Or on the big model.** If you switch the big model on for the wiki
([BIG-MODEL.md](BIG-MODEL.md)), the wiki uses that instead - and then only
that: much slower (it may wait minutes for the big model to load, and says
so), and it never falls back to the second card by itself.

### Using it

1. **Make the folders, once.** In Obsidian (or Explorer), inside your vault,
   make a folder called `Jarvis Wiki`, and inside that a folder called
   `Sources`. Jarvis uses the same vault as `#obs` and the notes search:
   `[notes.obsidian] vault_directory` in `jarvis-framework.toml`, or
   `JARVIS_OBSIDIAN_VAULT`.
2. **Drop a document in.** Put a `.md` or `.txt` file in `Jarvis Wiki/Sources`.
   Other kinds of file (PDF, Word, pictures) are not read yet; they show as
   "can't read", with the reason.
3. **Press Add to wiki.** On the PC: Brain window, Memory tab, the Wiki card.
   On the phone: Brain, the Wiki section. The document's line says what is
   happening: the model is reading it (a minute or two for a long one), then
   an approval card appears.
4. **Read the card and answer it.** It lists every page it would create or
   change, with one line about each, and what it thinks this document
   disagrees with. Yes writes them; no writes nothing.

### What it writes, and where

Everything is inside `<your vault>/Jarvis Wiki/`, never anywhere else:

- `Pages/` - one page per topic, person or thing. Each starts with
  `sources: [...]` (the documents it came from) and links to other pages
  with `[[Page name]]`, so Obsidian's graph and backlinks work.
- `index.md` - one line per page. New lines are added at the end.
- `log.md` - one entry per document added, like
  `## [2026-09-24] ingest | spring-meeting.md`, added at the end.
- `.versions/` - before a page is changed, its old copy is saved here. To
  undo a change, copy the old file back into `Pages/`. Only pages get a
  copy: `index.md` and `log.md` are only ever added to, never rewritten, so
  no copy of them is kept. To undo a line there, delete it by hand.
- Your document in `Sources` is never changed.

A document already added and not changed since shows "in the wiki" and is
not read again. Edit it and it shows "changed"; adding it again updates the
pages.

### What it will not do

- Read a document too big for the model's room. It says "too big" with the
  numbers; split the document into smaller files. Nothing is ever cut short.
- Write more than 12 pages from one document, or a page over 6,000
  characters, or a page anywhere but `Jarvis Wiki/Pages`. A plan that tries
  is refused whole, with the reason.
- Load anything from outside your vault. A picture that is not a file in
  your vault (a web address, or a file or network path elsewhere) becomes
  a plain link, so opening the page in Obsidian fetches nothing.
- Write HTML beyond simple formatting. Only a short list of harmless tags
  (bold, tables, lists, headings and the like) is allowed; a page with
  anything else is refused, with the reason.
- Put markup in `index.md`. Each page's one-line summary is written there
  as plain text: the `<`, `>`, `[`, `]` and backtick characters are taken
  out, and the approval card shows the summary exactly as it will be
  written.
- Work on two documents at once. The second waits for the first.

### Not checked yet, said plainly

No real model has written a wiki page here yet: the tests use a stand-in.
How good the pages are, and how often a real answer is refused, will only
be known once the second card is in. "Too big" is worked out from an
estimate (about 3 bytes per token, on the cautious side).

## The better voice (custom voices)

A sixth use of the second card, with its **own** switch - it is not one of
the five above and is not listed by `GET /api/second-card`. When Jarvis
speaks in a custom voice you recorded (`backend/README.md`, "Custom
voices"), it normally makes that voice on the processor (ZipVoice). With the
better voice on, it starts **F5-TTS** on the second card instead, in its own
program, for a more natural copy of the voice.

- **Off by default.** Turning it on is one approval card
  (`better_voice_enable`); off is immediate. It can only be turned on when a
  capable second card is detected.
- **On demand.** Nothing starts until Jarvis actually speaks in a custom
  voice. While F5-TTS loads, the processor's copy of the same voice speaks,
  so there is never silence.
- **It does not hold the card.** It stops after 10 minutes with nothing to
  say (`[voice] f5_idle_minutes`), in standby, and when switched off.
- **It shares the card.** It does not start while the big model is using
  the card, or when the card has less than about 3 GB free (an estimate, not
  measured). It does not stop the second Ollama; both may be on the card at
  once, which the 12 GB card's plan (7.7 GB for the long-context lane) leaves
  room for only on paper.
- **Not checked:** F5-TTS has never run in this project - there was no
  graphics card where it was written. Its speed and real memory use on the
  RTX 2060 are the first things to measure.

## What was not built, and why

- **Voice on the graphics card.** Speech-to-text, the voice check and the
  spoken voice all run on the processor today (sherpa-onnx). Moving them to
  the card would need the CUDA builds of onnxruntime and sherpa-onnx - a
  large install - and the clips are short, so it would gain little. Measure
  how long voice takes now before deciding it is worth it.
- **Overnight memory tidying.** Nothing about it depends on the second card,
  and it is not designed yet (docs/ARCHITECTURE.md section 10). If it is ever
  built, it may only raise review cards.

## Not checked, said plainly

- **Real `nvidia-smi` output from your PC.** The tests replay lines in
  `nvidia-smi`'s documented CSV format with made-up values. In particular,
  exactly how many MB a 12 GB RTX 2060 reports is not known here; Jarvis
  treats anything from 11.5 GB up as a 12 GB card to allow for that.
- **Ollama accepting a card id in `CUDA_VISIBLE_DEVICES`.** Ollama's own
  documentation (docs/gpu.mdx) says ids are "more reliable" than numbers,
  and NVIDIA's documents that CUDA accepts them. It has not been run on your
  two cards.
- **The picture model's size.** ollama.com could not be reached from where
  this was written. 7.2 GB (with room for 32,768 tokens) is worked out from
  the model's published shape;
  run `ollama show qwen2.5vl:7b` after installing it to see the real one.
- **Whether `qwen2.5vl:7b` takes tools.** Not assumed: a picture turn on the
  second card is offered no tools.
