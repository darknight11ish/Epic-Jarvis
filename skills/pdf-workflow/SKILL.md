---
name: pdf-workflow
description: Use when a task involves reading, reviewing or making a PDF where the LAYOUT matters - render the pages and look at them rather than trusting extracted text. Adapted for Jarvis from OpenAI's pdf skill (Apache-2.0).
license: Apache-2.0
allowed-tools:
  - my_files
  - file_read
  - shell_exec
  - propose_plan
requires_tools:
  - my_files
  - file_read
  - shell_exec
---

# PDF workflow

Adapted from OpenAI's `pdf` skill (`openai/skills`, `skills/.curated/pdf`, Apache
License 2.0 - see THIRD-PARTY-NOTICES.txt). The tool names below are Jarvis's
own; the upstream skill assumes a terminal and a package manager, which is not
how this PC is driven.

## When to use

- Reading or reviewing a PDF where layout or visuals matter.
- Building a PDF where the formatting has to be right.
- Checking a finished document before it is handed over.

Not for: text-only extraction where layout is irrelevant - `file_read` is enough.

## The tools this uses

| step | tool | why |
|---|---|---|
| find the document | `my_files` | the owner's own files, wherever they keep them |
| read it | `file_read` | the text of one file Jarvis is allowed to open |
| render, generate, inspect | `shell_exec` | `pdftoppm` to render pages, Python for generation |
| agree the plan first | `propose_plan` | a build with several steps is worth agreeing before it runs |

**`shell_exec` goes through the approval gate like every other call.** This skill
grants no permission and skips no question: it is a note about the order to do
things in, and each command is still asked for at its own tier.

## Workflow

1. **Find it** with `my_files`, then open it with `file_read`.
2. **Prefer looking over extracting.** Render the pages to images with
   `pdftoppm` through `shell_exec`, then inspect them. Extracted text loses
   layout, so it cannot tell you whether the page is right.
3. **Agree the shape before generating** a new document: `propose_plan` with the
   sections, the page size and where it will be written.
4. **Generate with Python**, not by hand-assembling bytes. `reportlab` for
   making one, `pdfplumber` or `pypdf` for reading one, all through
   `shell_exec`.
5. **Re-render after every meaningful change** and look again. Alignment,
   spacing and legibility are checked by eye, not assumed.

## Dependencies

`reportlab`, `pdfplumber`, `pypdf` and Poppler's `pdftoppm` must already be on
this PC. **Jarvis does not install packages on its own**, and this skill asks it
to do no such thing: if one is missing, say which one is missing and stop. On a
local-first machine a package that appears without the owner's say-so is a
change nobody approved.

## Files and tidy-up

- Intermediate renders go in a scratch folder and are removed when the job is
  done; do not leave them beside the owner's documents.
- Write the finished document where the owner asked for it, with a name they
  can recognise later. Do not overwrite an existing file without saying so.

## What "finished" means here

- The latest render shows no clipped text, no overlapping elements, no broken
  tables and no unreadable glyphs.
- Headers, footers, page numbers and section breaks look deliberate.
- Charts, tables and images are sharp, aligned and labelled.
- Plain ASCII hyphens only - no non-breaking or long dashes.
- No tool tokens, placeholder strings or "TODO" text left in the output.

Do not hand it over until the last render looks right, and say plainly if it
does not.
