# Things to ask another model to look up

GitHub is unreachable from the container these sessions run in:
`api.github.com` and `github.com` both answer 403, and only
`raw.githubusercontent.com` gets through. So raw source files can be read, but
**star counts, issue threads, discussions and pull-request conversations
cannot.**

That is the gap. Everything below is something a model with a working browser
can fetch in minutes and this one cannot fetch at all.

## How the answers will be treated

Anything that comes back is **secondhand** and gets labelled `REPORTED` in
`PEERS.md`, not `CONFIRMED`. Where a file can be reached through
`raw.githubusercontent.com`, the claim will be re-checked against the source
before it is relied on. That is not distrust of the other model; it is the
same rule applied to this one, and it exists because a confidently relayed
guess has already cost this project real time — see `ARCHITECTURE.md` §8.

Paste the numbers back as they come. No need to tidy them.

---

## What went wrong the first time, 2026-09-15

The first version of prompt 1 below said *"do not estimate, and do not round
star counts"*. Every star count and push date came back `unknown`, and the
model explained why: it has live **web search**, not API access. Search
snippets round stars to "14.2k" and show dates as "3 days ago", so a rule
against rounding rules out the only data it can see.

**That was a prompt-design mistake, not a model failure.** `grade_repo` tests
against 500 stars, 50 stars and 365 days. "14.2k" and "3 days ago" settle all
three. Precision was demanded where none was needed, and the cost was the
whole table.

The rule that is worth keeping is the one about *labels*: three Part 2 answers
came back "could not verify" while still marked "Source Type: PRIMARY
source". Ask explicitly whether the page was opened or only summarised.

Prompt 1 below has been rewritten accordingly. The licence column is kept even
though three of its four disagreements were wrong last time, because checking
them against `raw.githubusercontent.com` took two minutes and caught an error
in `PEERS.md` — see the correction section there.

## Prompt 1 — the one that unblocks a tool (highest value)

`backend/jarvis_research.py` grades a repository **ADOPT / FORK AND EXTEND /
BUILD CUSTOM**. It needs four fields per repo and has never been run on real
data, because it cannot reach the API.

> Rounded numbers are fine. I am only testing against thresholds: 500 stars,
> 50 stars, and "pushed within the last 365 days". So "14.2k" and "3 days ago"
> are both usable. Give me your best read from search and mark anything you
> are unsure of. No recommendations — I only want the fields, and I will do
> the judging myself.
>
> Columns: `full_name`, stars, licence, last pushed, `archived?` — for the
> last one, look for the grey "This repository has been archived" banner at
> the top of the page, and give the date if it shows one.
>
> ```
> khoj-ai/khoj
> janhq/jan
> open-webui/open-webui
> letta-ai/letta
> letta-ai/letta-code
> mem0ai/mem0
> getzep/graphiti
> OpenVoiceOS/ovos-core
> rhasspy/rhasspy3
> MycroftAI/mycroft-core
> home-assistant/core
> block/goose
> cline/cline
> openai/codex
> supermemoryai/supermemory
> qualixar/superlocalmemory
> k2-fsa/sherpa-onnx
> localsend/localsend
> syncthing/syncthing
> ```

Thresholds it will be scored against, so you can sanity-check the result:
500 stars is "popular", 50 is "viable", a push older than 365 days is stale,
and AGPL/GPL count as reaching into what you build.

**Add `rhasspy/rhasspy` to the list, and ask specifically about the archive
banner on `MycroftAI/mycroft-core` and both Rhasspy repos.** `PEERS.md`
recorded those as archived on specific dates and can no longer back that up:
the README text quoted as evidence is on neither branch today, and archive
status is the one field no raw file carries.

---

## Prompt 2 — the things two research passes could not verify

These are listed at the end of `PEERS.md` as open. Each one is a specific
claim, and the honest answer to several may be "no".

> Answer each of these separately. For each, say whether you could reach a
> **primary source** (the project's own repo, docs or release notes) or only a
> secondhand summary, and give the URL. If you cannot verify something, say
> so plainly rather than reasoning it out — I would rather have five answers
> and four "could not verify" than nine confident guesses.
>
> 1. **Home Assistant speaker identification.** Does `home-assistant/core`
>    contain any speaker verification or voice-print identification — telling
>    *who* is speaking, not just what was said? I believe it does not, and I
>    want that checked, because a feature is being built on the assumption.
>
> 2. **Supermemory's review workflow.** `supermemoryai/supermemory` is said to
>    have an API that lists inferred memories awaiting review, then
>    approve/decline/undo. Is that in the open-source repo, or only the hosted
>    platform? This is the one possible counter-example to a claim that our
>    human-reviewed memory queue is unique.
>
> 3. **Jan's "Auto Optimize".** In `janhq/jan`, what does that setting
>    actually tune? Release notes only say "add label experimental".
>
> 4. **goose's `ToolPermissionStore`.** It is dead code at HEAD — zero callers
>    outside its own file. Was it ever wired up, and if it was removed, does
>    the commit or PR say why?
>
> 5. **cline PR #11865**, "disable command auto-approval by default", merged
>    2026-06-25. It reverted a change made six hours earlier. Does the PR or
>    issue discussion give a reason — a user report, an incident, a review
>    objection?
>
> 6. **Ollama VRAM estimation**, issues #7629 and #3837. What is the current
>    state, and is there a documented way to detect that a model has silently
>    fallen back to the CPU other than comparing `size` and `size_vram` from
>    `/api/ps`?

---

## Prompt 3 — only if the first two come back easily

Genuinely open-ended, so expect more noise than signal.

> Find GitHub projects, updated in the last twelve months, that do **all** of:
> run a language model entirely on the user's own machine, extract facts from
> conversations into a persistent memory, **and require the user to approve
> each fact before it is stored**. The last part is the one that matters — I
> already know about Khoj, Open WebUI, mem0, Letta and supermemory, and as far
> as I can tell none of them ask before writing. I am looking for a
> counter-example. If there is none, say so; that is a useful answer.

---

## What NOT to ask for

- **Code to paste in.** Licences differ and two of these are traps: Open WebUI
  is BSD-3 plus a clause forbidding removal of its branding above 50 users,
  and Khoj and superlocalmemory are AGPL-3.0. Ideas and file paths are safe;
  copied implementation is not, and this is a non-commercial build that should
  stay clean.
- **Opinions on what Jarvis should do.** The constraints — local-only, no
  keys, no approve-all — are settled, and a model that has not read
  `ARCHITECTURE.md` will helpfully suggest breaking all three.
- **Anything already in `PEERS.md` marked CONFIRMED.** That was read from
  source. Re-asking invites a plausible contradiction that then has to be
  adjudicated.
