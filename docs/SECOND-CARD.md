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
- it has **10 GB or more** of memory.

The card that runs everyday chat (the "main" card) is: the one named in
`[compute] primary_gpu` in `jarvis-framework.toml`, if you set it; else the
one your monitor is plugged into; else the first one `nvidia-smi` lists.
With the monitors on the 2080 Super, that is the 2080 Super, which is what
you want: it is the faster card.

## The five switches

There is one main switch ("use the second card") and one switch per feature.
The main switch must be on before any feature can be.

| Feature | What it does | Model | Memory on the card |
|---|---|---|---|
| **Longer conversations** (`long_context`) | When a chat grows past what the main card has room for, that answer is written on the second card, which has room for twice as much of it (32,768 tokens; the everyday model on the main card has 16,384). Short chats stay on the fast main card. | `qwen3:8b` with room for 32,768 tokens, on any capable card (10, 11 or 12 GB). | about 7.7 GB |
| **Pictures** (`vision`) | A message with a picture (a screenshot from Alt+Shift+S) goes to a picture-reading model on the second card, so Jarvis actually sees it. Pictures still never go to the internet. | `qwen2.5vl:7b` | about 7.2 GB (**an estimate** - see "Not checked" below) |
| **Learning in the background** (`learning`) | The memory learner (which suggests facts for you to review) runs on the second card, so it never slows chat down, and it waits only 10 seconds of quiet instead of 45. If the second card does not answer, that pass is skipped (it is not moved to the main card after only the short wait). For the next 10 minutes learning then works as it did before: the full wait, on the main card. After that the second card is tried again. | same as Longer conversations | shared |
| **Browser control** (`browser_control`) | Jarvis can work a web page for you, one approved step at a time. Needs Longer conversations on too, and `"browser_control"` in `[tools].enabled`. Its approval card is a different kind from the others (`second_card_browser_enable` in `jarvis-framework.toml`, which must stay `"ask"`), and it says plainly that the pages are on the internet, so what Jarvis types or clicks there reaches that website. | same as Longer conversations | shared |
| **Wiki builder** (`wiki`) | Turns documents you put in your vault's `Jarvis Wiki/Sources` folder into linked wiki pages, one approval card each. See "Wiki builder" below. | same as Longer conversations | shared |

The second card holds **one model at a time**. If Pictures and Longer
conversations are both on, the second card swaps between the two models as
needed (a few seconds each time). That never touches the main card, so
everyday chat is never slowed by it.

**If a model is not installed**, the switch can still be on; the feature just
waits, and its status line says which model to install. Install it the usual
way: Brain window, Faculties, Models (the Install box), or `ollama pull <name>` in a terminal (for example
`ollama pull qwen3:8b`).

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
models" (Mind, "Hardware" on the phone) offers three setups for your cards,
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

**On the phone:** open Mind (the button on Home), then the "Second graphics
card" section, under Model. It shows what Jarvis found, the main switch and
one switch per feature. Turning one on raises the approval card; the switch
says "Waiting for your approval. Approve it on your PC or on this phone's
Home screen." until you answer it. If the card ends without turning the
switch on, a line under the switch says how (for example "You said no, so
"Pictures" stays off."). With Pictures working, chat gets a Photo button.

**On the desktop:** Settings, "Second graphics card". The same list, the main
switch and one switch per feature; turning one on raises the same approval
card. It also shows the one-line command that keeps everyday chat on the main
card, with a Copy button. With Pictures working, a screenshot question goes to
the second card, and the answer's badge says "on the second graphics card".

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
   On the phone: Mind, the Wiki section. The document's line says what is
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
