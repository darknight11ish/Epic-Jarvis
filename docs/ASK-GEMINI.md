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

## Prompt 1 — the one that unblocks a tool (highest value)

`backend/jarvis_research.py` grades a repository **ADOPT / FORK AND EXTEND /
BUILD CUSTOM**. It needs four fields per repo and has never been run on real
data, because it cannot reach the API.

> For each GitHub repository below, give me exactly four values in a markdown
> table. No commentary, no recommendations — I only want the raw fields, and I
> will do the judging myself.
>
> Columns: `full_name`, `stargazers_count`, `license.spdx_id`, `pushed_at`
> (ISO 8601), `archived` (true/false).
>
> If a value is genuinely unavailable, write `unknown` — do not estimate, and
> do not round star counts.
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
