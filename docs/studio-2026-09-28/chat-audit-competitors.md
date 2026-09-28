# Chat organisation: Jarvis vs the leading assistants (studio, 2026-09-28)

Most official help pages were blocked from the container; Claude's help
pages and LM Studio's docs were read, the rest are search summaries
("summary") or single sources ("unverified"). An earlier audit
(`docs/ease-audit-2026-09-27/history.md`) found no search, no "carry on", no
export; since then a title-only search and the "answer not kept" note were
added (JARVIS-API §18.4).

## Side by side

| Ability | Others | Jarvis today |
|---|---|---|
| History list | all | **Has** (both apps, newest first, "Load older") |
| Search old chats | ChatGPT, Claude (paid), Gemini, Perplexity, Open WebUI | **Partly** - titles only, loaded chats only; searching chat words waits (owner, 2026-09-26) |
| Rename | Claude, Copilot, Open WebUI | **No** - title = first line, 80 chars |
| Pin / star | ChatGPT, Claude, Gemini, Open WebUI | **No** (only facts can be pinned) |
| Folders / projects holding chats | ChatGPT, Claude, Gemini notebooks, Copilot, Perplexity Spaces, Open WebUI, LM Studio | **Partly** - Projects exist (§61) but no chat can belong to one yet (Projects step 4) |
| Archive | ChatGPT, Open WebUI | **No** |
| Delete one | all | **Has** (with "are you sure?") |
| Delete in bulk | ChatGPT, Claude | **No on purpose** (§18.3); safe versions: keep_days, "Forget a time frame" (§64) |
| Export | Claude, ChatGPT | **No, on purpose so far** (ARCHITECTURE §5; the locked backup is the only way out) |
| Temporary chat | ChatGPT 30 d, Claude 30 d, Gemini 72 h, Perplexity 24 h | **Has, stricter** - nothing kept at all |
| Edit an earlier message / branch | ChatGPT (web only), Claude, Open WebUI, LM Studio | **No** (only "Try again" after a failed answer) |
| Regenerate | ChatGPT, Claude, Open WebUI, LM Studio | **No** |
| Carry on an old chat | all | **No** - History is read-only |
| Voice transcripts in history | ChatGPT | **Has** (voice label; Live kept; side remarks not) |
| Memory that recalls past chats | ChatGPT, Claude, Gemini, Meta AI | **Partly, on purpose** - facts only; chat text never recalled (§5) |
| Public share link | ChatGPT, Grok, Meta AI, Open WebUI | **No on purpose** (rules 1 and 2) |
| Retention settings | Gemini, Copilot, Claude | **Has** (forever / 30 / 90 / 365 days, history off, space wiped) |

## Gaps that matter most (0 GB, either card setup)

1. **Carry on an old chat** - "Carry on" in History reloads the kept turns
   with the same conversation id and each turn's original label (outside
   text stays marked); on one card, only the newest turns that fit, saying
   "older turns not loaded".
2. **Rename, plus better automatic titles** (optionally a short title by the
   local model when a chat ends; never for temporary chats).
3. **Search the words inside chats** - PC-side, snippets on screen only, no
   stored index, nothing to the AI. **Owner's call** (the 2026-09-26 "waits"
   decision).
4. **Chats inside Projects** (Projects step 4) **plus Pin** - a pinned chat
   stays on top and is exempt from "Delete conversations older than".
5. **"Facts learned in this chat"** in an open chat, each with Forget; on
   delete, offer to forget them as a ticked list (per-fact, never a bulk
   shortcut - owner's OK if beyond per-fact buttons).
6. **Edit the last question and resend**; branching later. Editing pasted
   text must not turn it into "typed".

## Complaints elsewhere to avoid

"Share" that quietly publishes (ChatGPT discoverable links, Aug 2025; Grok
~370,000 chats, Forbes 20 Aug 2025; Meta AI Discover, June 2025); "deleted"
or "temporary" that is not gone; chats used for ads or training by default;
history that seems to disappear (keep ONE hidden place if Archive is added,
and search it); memory from past chats that feels like a secret file (keep
"Used in this answer"); plain-text chat files on disk (LM Studio).

## Do not copy

Public share links; automatic recall of all past chats; a "delete all"
button; cloud or phone-side sync of history; temporary chats that use
memory; plain-text export (only if the owner changes §5, and then like
memory export: a Save-as dialog, never the clipboard, saying plainly the
file is not locked).

## Where Jarvis is already better

Encrypted history, nothing recorded if encryption fails; every turn says
where its words came from; a temporary chat that truly keeps nothing; the
paste guard hides passwords and codes; "Forget a time frame"'s list, card
and Undo; Live side remarks never kept; retention choices with wiped
space; no training, ads or public links.
