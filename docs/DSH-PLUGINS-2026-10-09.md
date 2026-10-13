# Plugins for DeepSeek Harness, and what they would do for this project (research, 2026-10-09)

Status: **research only. Nothing was installed, and this is not a plan to build
anything.** The owner asked (2026-10-09) whether there are recommended plug-ins,
on GitHub, that are compatible with DeepSeek Harness (DSH) and could help the
Jarvis project, and what exists for communication between separate DSH
conversations. The owner then chose **"install nothing - write it up"**, so the
shortlist and the install lines are recorded here for a later decision.

Every line below is **read from the catalogue, from the plug-ins' own READMEs,
and - for the four plug-ins already installed on this PC - from their shipped
files and one read-only local diagnostic (`modlens doctor`)**. No plug-in's
source was audited line by line, no plug-in was downloaded into any profile, and
no file under `C:\Users\pcadmin\.dsh` was written. Where a claim comes only from
the catalogue's one-line description rather than the plug-in's own README, the
table says `catalogue only`. **Nothing was installed.** Section 7 records where
each plug-in sends data and how well that is known.

This document is the *survey* answer. The *build* answer already exists and is a
different document: [DSH-PLUGIN-BRIDGE-DESIGN.md](DSH-PLUGIN-BRIDGE-DESIGN.md)
(2026-10-04) designs writing our own plug-in once and pointing both Jarvis and
DSH at it (one MCP server on the PC, two hosts). That design is still
**designed, not built**, and this document does not change it.

## 1. The short version

- **Yes, and there is a large ecosystem.** The community catalogue
  [awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)
  listed **4,471 plug-ins** on 2026-10-09, in categories such as Sessions &
  Messages (292), Tools & Capabilities (583), Memory (207), Git & Code Review
  (110), Docs & Rendering (66) and Remote & Mobile (137).
- **This PC can already install them.** The `desktop` profile
  (`C:\Users\pcadmin\.dsh\profiles\desktop`) has the market plug-in
  (`dshmarket`) installed, which adds a **Plugins** page to the app. The CLI that
  ships inside the app can do the same thing:
  `& "C:\Users\pcadmin\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd" plugin --profile desktop add <name>`.
- **A plug-in is one npm package** that declares a `dsh.bundle` manifest. It can
  add a model tool, a sidebar panel, a settings page, or a whole replacement for
  part of the Harness.
- **Nothing on the list is made for Jarvis.** These are general helpers; the
  value is in the DSH conversations that do this project's work (the code, the
  tests, the docs, the PRs), not inside the Jarvis app itself.
- **Three things to know before installing one.** A plug-in **runs as you, in
  the Harness process, with your files and credentials, and Jarvis's or DSH's
  approval cards do not sandbox it** - the catalogue says plainly that being
  listed is not a security review. Installs and updates are **refused while an
  agent is running** (this profile's market log shows `install-blocked ... refused
  while agents are running`). And the Harness here is **0.2.0-rc.2**, a release
  candidate, so a plug-in built against a different `rc` may not load.

## 2. What this profile already has

Read from `C:\Users\pcadmin\.dsh\profiles\desktop\package.json` on 2026-10-09.
The same file lists the bundles the profile is composed from, which include the
official `@deepseek-ai/dsh-base`, `@deepseek-ai/dsh-web-app`,
`@deepseek-ai/dsh-experimental-agent-team-profile` and
`@deepseek-ai/dsh-experimental-auto-review`.

| Installed | Version | What it already does |
|---|---|---|
| `dshmarket` | 1.66.8 | The plug-in market inside the app: browse, search, one-click install and update, themes. This is why the answer to "how do I install one" is a page in Settings, not a command. |
| `dsh-better-sidebar` | 0.24.1 | File tree, editor, changes, tasks and side chat in one column, separate per conversation; also the service other plug-ins register sidebar tabs into. |
| `dsh-talk` | 0.3.19 | Voice: a microphone button in the composer, speech-to-text (Web Speech, FunASR, whisper.cpp), a `speak` tool with browser/edge-tts/piper voices, announcements with mute, and speak-to-interrupt. |
| `@liustack/modlens` | 3.26.6 | Reading an image (screenshot, photo, chart, document scan) through a vision bridge. |

So the useful answer to "what should I add" starts from what is already here:
files, editing, voice and images are covered.

## 3. The shortlist, by the job it would do here

`README read` means this session read that plug-in's own README; `catalogue only`
means the description and counts are the catalogue's, and nobody here has read
the project's own documentation.

| Job | Plug-in | What it does | Provenance |
|---|---|---|---|
| **GitHub reads and PRs** | [hh719509125/deepseek_harness_plugin](https://github.com/hh719509125/deepseek_harness_plugin) (`github-connector`) | Read-only GitHub tools - `github_api`, `github_search`, `github_file`, `github_issues` - authenticated with a Personal Access Token kept on its own settings page. Its README says it is built and verified against **Harness 0.2.0-rc.2, exactly this build**. | README read |
| | [PerryLink/dsh-github](https://github.com/PerryLink/dsh-github) | Fuller: a PR review bot that polls and comments, plus PR/issue tools, with every write behind a human approval. | catalogue only |
| | [AngelosZou/dsh-github-router](https://github.com/AngelosZou/dsh-github-router) | Read-only GitHub access that works out which access method works on this machine and tries proxies on its own. | catalogue only |
| **Reviewing the agent's own edits** | [9087/dsh-diff-approval](https://github.com/9087/dsh-diff-approval) | Collects every `edit`/`write` into a review list: keep or revert one block, a selection or the whole file, with persistent undo. | catalogue only |
| | [SiriLee/dsh-rewind](https://github.com/SiriLee/dsh-rewind), [Anionex/dsh-turn-rewind](https://github.com/Anionex/dsh-turn-rewind) | Rewind the conversation, and (optionally) the files, back to before a message. | catalogue only |
| | [MichengAI/dsh-code-review](https://github.com/MichengAI/dsh-code-review) | `/review` spawns an independent subagent over a git scope (a branch, the uncommitted changes, a commit) and returns a findings report. | catalogue only |
| **Running the tests** | [suimi8/dsh-test-runner](https://github.com/suimi8/dsh-test-runner) | A `test_run` tool that **auto-detects pytest** (also vitest/jest/node:test), returns only pass/fail counts plus each failing test's name and error, and can re-run only the failures. Its README states it was tested on Windows + PowerShell, and that an unparsed output falls back to exit code plus the tail rather than crashing. | README read |
| | [Pasumao/dsh-plugin-notify](https://github.com/Pasumao/dsh-plugin-notify) (`dsh-notify`) | A native Windows toast plus a system-tray icon that pops the moment a run stops - finished, aborted, error, or waiting for your choice. | npm metadata read |
| **Long sessions and old conversations** | [ranxianglei/billion-context](https://github.com/ranxianglei/billion-context) | Context compression for small windows; the most-downloaded plug-in in the Sessions category (about 780,000 downloads in 30 days, as the catalogue counts it). | catalogue only |
| | [MichengAI/dsh-archive-manager](https://github.com/MichengAI/dsh-archive-manager) | Search, restore and delete archived sessions by workspace. | catalogue only |
| **Remembering project decisions across sessions** | [PerryLink/dsh-memento](https://github.com/PerryLink/dsh-memento) | Cross-session memory that is **approval-gated and auditable**, with a frozen snapshot injected instead of a live store. | catalogue only |
| | [Qinling-Melon-Farmers/dsh-memoir](https://github.com/Qinling-Melon-Farmers/dsh-memoir), [vshulcz/deja-vu](https://github.com/vshulcz/deja-vu) | Local-only memory: JSON plus a generated `PROJECT_MEMORY.md`, or a local BM25 index over session files that other agents on the machine already wrote. No network, no embeddings. | catalogue only |
| **The `docs/` set** | [PolinniZhong/dsh-knit](https://github.com/PolinniZhong/dsh-knit) | Lists the Markdown, images and video already in the workspace ranked by relevance to the conversation, shows **which documents cite the one being viewed and which it cites**, and exposes the same search to the model as a `knit_docs` tool. No model calls, no network. | catalogue only |
| | [lucky8197/dsh-doc-guard](https://github.com/lucky8197/dsh-doc-guard) | Read-only document-versus-code drift audit: version headers, changelog tables, directory-structure trees, module/test counts, and cross-document references, with a static count of test markers (`def test_`, `#[test]`, `@Test`, ...). | README read |
| | [MrmoLabs/dsh-mermaid](https://github.com/MrmoLabs/dsh-mermaid), [hanzhangzzz/dsh-diagram](https://github.com/hanzhangzzz/dsh-diagram) | Render Mermaid fences, or draw an Excalidraw canvas the agent can read back. | catalogue only |
| | [hh719509125/dsh-preview-editor](https://github.com/hh719509125/dsh-preview-editor) | Edit a text file in place in the sidebar preview with save/revert and conflict protection. | README read |
| **Running the work on the PC's own model** | [1035041186/dsh-llm-ollama](https://github.com/1035041186/dsh-llm-ollama) | Adds Ollama as a model provider inside DSH through its native `/api/chat`, with a settings page, model discovery from `/api/tags`, and per-model context window and output caps. | README read |
| **The phone** | [Blank-not-black/dsh-Remote](https://github.com/Blank-not-black/dsh-Remote) | Remote control from a phone over **LAN or Tailscale**, with a bearer-token gateway and an Android app for sessions, approvals and questions. Tailscale is the network this project already trusts. | catalogue only |
| | [saya-ch/dsh-mobile](https://github.com/saya-ch/dsh-mobile) | Android app or mobile browser access with persistent device pairing. | catalogue only |
| | [picsky/dsh-pocket-console](https://github.com/picsky/dsh-pocket-console) | Forwards approvals and questions to the phone; the desktop answers first and a phone approval grants `allowed-once` only; **one outbound WebSocket, no tunnel or relay**. | catalogue only |

**Recommended starting set** (revised 2026-10-09, after the source of the first
three was read - section 9): **`dsh-knit`** (which document says what about
which; its README claims zero network egress) and **`dsh-test-runner`** (pytest,
summarised; held to its README only - nobody has read its code yet). The
**GitHub connector** is now conditional rather than recommended: small and
read-only, but its `github_api` is a general authenticated GET and its optional
`caFile` reaches the whole process (section 9.1). **`dsh-crosstalk` is out**: it
does not build against the Harness installed here, and its "same OS user only"
check cannot run on Windows at all (section 9.2). **`dsh-peer-bus`** is the
better-designed of the two, and still delivers a peer's words with no tap of the
owner's (section 9.3). The most-adopted multi-agent plug-in of all,
`@nanmicoder/dsh-agent-teams`, was read as well and is **not** in this set either:
it is offline and credential-free, but its team-creation tool **defaults to
running with no approval at all** (section 9.4).

Two entries need an honest caveat rather than a recommendation:

- **`dsh-doc-guard` reads as a strong fit and is not one.** It is genuinely
  read-only and genuinely useful, but its dimensions assume the Chinese-style
  versioned design document (`文档版本：vX.Y` headers, `| version | date | change |`
  tables, `详见 §X` cross-references). This repository's documents are dated
  English files, and its cross-references read `ARCHITECTURE.md section 9` or
  `JARVIS-API section 115`, which that parser is not written for. Expect it to
  find little here, and note that this project **already has its own drift
  checker**: `docs/CLAIMS.tsv` with `tools/check_claims.py` and
  `backend/test_claims.py`.
- **The phone category contains several plug-ins that publish the Harness over a
  public tunnel or a hosted relay** - `mrRisega/dsh-remote`, `wenbin-wb/dsh-bridge`,
  `KyoMio/dsh-zen-remote`, `shaobeichen/dsh-pocket`. They are the most popular
  entries in that category by downloads and they are **the shape rule 2 refuses**.
  The Tailscale/LAN ones above are the alternative.

## 4. How to install one (when the moment comes)

Through the app: **Plugins -> Add plugin**, then paste the package name (for
example `dsh-test-runner`) or a GitHub spec (`github:owner/repo`). Through the
CLI that ships with the app:

```powershell
$dsh = "C:\Users\pcadmin\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
& $dsh plugin --profile desktop add dsh-test-runner
& $dsh plugin --profile desktop add "github:hh719509125/deepseek_harness_plugin#path:/github-connector"
```

- **Do it with no conversation running.** The market refuses installs and updates
  while an agent is running, and that refusal is recorded in
  `.dsh-market/log.ndjson`.
- **Pin a commit for a GitHub source** (`github:owner/repo#<sha>`): the catalogue's
  own advice, because a GitHub install runs the package's build script at install
  time.
- **Re-check the version.** Plug-ins declare which Harness release they were
  built against; this build is `0.2.0-rc.2`. For example `dsh-llm-ollama`'s README
  names an older target (`0.1.0-rc.6`, compatible from `0.1.1-rc.2`), so it is the
  least certain of the four on this Harness.
- **Uninstalling is a profile edit**, not a conversation: the market writes
  `disabled: true` rows into the profile's patch layer, and DSH's own rule is not
  to hand-write the profile's `package.json` or `cordis.patch.yml`.
- **DSH's boot is all-or-nothing**: one broken plug-in can stop the Harness
  starting, which is why the market ships a recovery prompt that lets you choose
  what is enabled at the next start.

## 5. Talking between two DSH conversations

This is the half where the answer is partly "already built in".

**What this session already has.** The official
`@deepseek-ai/dsh-experimental-agent-team-profile` bundle is installed in this
profile, so a conversation can spawn named teammates, message them, hand out
shared tasks with dependencies, and wait on them. Subagents (`subagent`,
`subagent_fork`) do the same for one-off work. **This is the recommended way to
talk between conversations** - it is official, it is already here, and it needs
no third-party code.

**What is missing is horizontal.** That messaging is strictly a parent and its
own children. Two *sibling* conversations - one on `backend/`, one on
`jarvis-client/` - cannot see or message each other. Plug-ins add that:

| Plug-in | How it carries a message | Trust model |
|---|---|---|
| [Jesse-njx/dsh-crosstalk](https://github.com/Jesse-njx/dsh-crosstalk) | Each session publishes a heartbeat file under `~/.dsh/crosstalk/`; **`list_agents` gains a `peers` scope and `send_message` accepts a peer name**, so the tools already in use gain siblings rather than a second vocabulary. An idle sibling wakes; a busy one receives it at the next turn boundary. No daemon. | Same machine, **same OS user only**, no network transport. Peer turns are labelled `[message from session ...]` and framed as a peer request, not as the user's instruction. Must be installed in every participating profile. |
| [ybh1291747665/dsh-peer-bus](https://github.com/ybh1291747665/dsh-peer-bus) | `bus_send` / `bus_ask` / `bus_reply` / `bus_wait`; cross-process off by default. | **Nothing is allowed until the owner grants it** (`/bus allow <id>`, one direction at a time). Its README is explicit that messages arrive as *user* messages and that an open bus would therefore be a prompt-injection path - hence default-deny. |
| [NanmiCoder/dsh-agent-teams](https://github.com/NanmiCoder/dsh-agent-teams) | A heavier third-party team protocol (14 tools, durable members, dependency-aware task board, planning before execution, a live panel). | npm `@nanmicoder/dsh-agent-teams@0.1.22`, and its README names **exactly this Harness, 0.2.0-rc.2**. Likely redundant next to the official Agent Teams bundle already installed; worth knowing it exists. |
| [AgentConnect/dsh-awiki](https://github.com/AgentConnect/dsh-awiki), [Kanadego/dsh-heartbeat](https://github.com/Kanadego/dsh-heartbeat) | Identities and agent-to-agent messaging over a network protocol; or a periodic "send a short package of notes to the sessions you bind". | Network, not this machine - a different trust question. `dsh-heartbeat` is Windows-only. |

**Both peer plug-ins have since been read line by line** - see sections 9.2 and
9.3 before installing either. In short: `dsh-crosstalk` does not install on this
Harness at all, and `dsh-peer-bus` installs, is carefully built, and still puts a
peer's words into a session with no tap of the owner's. The team-shaped
alternative in the table above, `@nanmicoder/dsh-agent-teams`, was read too
(section 9.4) and fails the same rule for a different reason: creating a team
needs no approval unless the model remembers to ask for one.

**Honest note on the whole section:** a message from another conversation is
someone else's text arriving in a conversation that has your project open. Both
peer plug-ins treat that as the risk it is, and disagree about the answer -
crosstalk accepts any session by the same Windows user; peer-bus refuses until
you grant a direction. On a single-user PC the two are close; on a machine with
another account they are not.

## 6. Where this touches the five rules

- **Rule 1** (email, files, credentials and memory stay on the local model): a
  plug-in runs *inside* the Harness with your permissions. It is not a Jarvis
  tool and the Jarvis gate does not see it. Nothing private was sent anywhere
  during this research, and nothing is proposed that would.
- **Rule 2** (no public tunnel): the popular remote-access plug-ins open exactly
  that (Cloudflare tunnels, hosted relays). The Tailscale/LAN ones do not, and
  the phone is why this project already runs Tailscale.
- **Rule 3** (keys): the GitHub connector wants a Personal Access Token. It gets
  the same care the pairing token already gets - never logged, sent only to
  GitHub, never in a file the app writes in plain text. Not added here.
- **Rule 4** (nothing approves itself): a plug-in's own approval gate is not
  Jarvis's gate. Anything a plug-in does on this PC is outside the approval
  cards that rule 4 describes, which is the strongest argument for starting with
  the **read-only** entries (`github-connector`, `dsh-diff-approval`,
  `dsh-doc-guard`, `dsh-knit`, `dsh-test-runner`) and for reading the source of
  anything else first.
- **Rule 5** (non-commercial): the licences seen on entries here are MIT, and
  `dsh-doc-guard` is BSD-3-Clause. Credit still goes in
  `THIRD-PARTY-NOTICES.txt` if one is ever installed, and nothing is
  redistributed.

## 7. Where your data goes, plug-in by plug-in

The owner asked (2026-10-09) which plug-ins send data off the PC, and chose the
standard to judge by: **"just tell me where data goes, don't judge it"**. This
section is the answer to that, written before section 3's shortlist is turned
into an install.

Two things to hold in mind first:

- **The baseline this sits on.** The Harness on this PC runs its conversations on
  `deepseek-flash` through the owner's DeepSeek account (the profile's
  `cordis.patch.yml`, `agent-default-model`). Every conversation in this window -
  Jarvis's own code and documents included - is already sent to DeepSeek. Rule 1
  governs the Jarvis app; it says nothing about the Harness. A plug-in does not
  create that path, it adds **more destinations** to it.
- **What is evidence, and what is not.** The four plug-ins already installed were
  checked by reading their own shipped files (a scan for host names) and, for
  `modlens`, by running its own local diagnostic, which by its own description
  makes no network calls and spends no quota. The eighteen surveyed plug-ins were
  read from their READMEs **only**. **A README cannot prove that a program makes
  no network calls**: where a README is silent, this section says `not stated`,
  which means unknown, not clean.

### 7.1 The four already installed

| Plug-in | What it contacts | How this is known |
|---|---|---|
| `dshmarket` | `awesome-dsh-plugin.com` (catalogue and an updates feed), `registry.npmjs.org`, and GitHub/codeload for source installs; `giscus.app`/GitHub Discussions if a card's comments are opened; optional WebDAV backup, whose own warning is that a backup *"can contain credentials from your profile config"*. Its shipped code also names two third-party GitHub mirrors (`gh-proxy.com`, `ghfast.top`) whose purpose it does not document | shipped files, read here |
| `dsh-better-sidebar` | **nothing found.** Every URL in it is library documentation (CodeMirror, lodash, Wikipedia); it talks to the local server | shipped files, read here |
| `dsh-talk` | whatever voice engine is configured, and no others. Its README states it plainly: *"Chrome's `webkitSpeechRecognition` sends microphone audio to Google's servers for transcription"*, and `edge-tts` *"performs network synthesis"* | its README, plus what is (not) installed here |
| `@liustack/modlens` | a vision provider, by design: Gemini API, Anthropic, or any OpenAI-compatible endpoint, plus reuse of other local CLIs' logins | `modlens doctor`, run here |

**`dsh-talk` is the one that changes behaviour on this PC today.** No local engine
is installed (`piper`, `edge-tts` and `whisper.cpp` are all absent from PATH, and
the profile carries no voice config), so the shipped defaults decide:
`stt.engine: auto` prefers a configured local engine and otherwise falls back to
the browser's Web Speech, while `tts.engine: auto` prefers `piper`, then
`edge-tts`, then the browser voice. So the composer's mic button transcribes
through the browser's speech service, and the `speak` tool stays local only
because neither `piper` nor `edge-tts` is installed. Installing `edge-tts` would
send the text of spoken replies to Microsoft.

**`modlens` sends nothing today, because it cannot work at all.** Its own
diagnostic reports `agy not on PATH`, every API key missing, and both failover
chains empty - selected provider `antigravity-cli` (the built-in default) with no
way to reach it. It needs a key or the Antigravity CLI before it reads an image;
that same step is what would start sending images to a cloud provider.

### 7.2 The eighteen surveyed by README

**Six state, in their own words, that they are local-only:**

| Plug-in | Its own words |
|---|---|
| `SiriLee/dsh-rewind` | *"no network requests, does not access any credentials"* |
| `PerryLink/dsh-memento` | *"Zero network, zero credentials"* (local SQLite, mode 0600) |
| `Qinling-Melon-Farmers/dsh-memoir` | *"no cloud memory store, embedding API or vector database"* - but its `PROJECT_MEMORY.md` *"may be committed to Git by you"* |
| `PolinniZhong/dsh-knit` | *"zero model calls, zero network egress"* |
| `MrmoLabs/dsh-mermaid` | *"requires no runtime CDN"* |
| `hanzhangzzz/dsh-diagram` | assets and fonts self-hosted, and it *refuses to load* when DSH Web binds `0.0.0.0` |

**Seven describe a service they talk to:**

| Plug-in | Goes to | What the README adds |
|---|---|---|
| `PerryLink/dsh-github` | GitHub (`api.github.com`, GraphQL, `gh`) | needs a `GITHUB_TOKEN`; **writes are approval-gated, reads are not**; `reviewMode: "model"` hands the capped diff to a subagent |
| `AngelosZou/dsh-github-router` | GitHub; mirrors off by default | *"Mirrors are off by default - they are third parties that see requested paths"*; the token lives in its own settings page; *"no write verb exists"* |
| `picsky/dsh-pocket-console` | Feishu/Lark cloud | *"Feishu sees the cards, because Feishu is the transport"*; needs a Feishu app; the README calls the approval card *"a remote code-execution authorization channel"* |
| `Blank-not-black/dsh-Remote` | your network; a public announcements URL every 30 s; a cloud feedback collector | the gateway *"listens on `0.0.0.0:8787` by default"*, and its own README says not to expose that port |
| `saya-ch/dsh-mobile` | LAN HTTPS on 3443, or remote mode via *"Tailscale Funnel, cpolar, cloudflared, self-hosted FRP or your own reverse proxy"* | the remote half is a public tunnel published from this PC |
| `ranxianglei/billion-context` | the model API of every client it fronts | a TLS-terminating proxy, self-updating from npm every 3 minutes, with *"no authentication"* once it is not loopback-bound; web UI on 8787 |
| `vshulcz/deja-vu` | optional only: update, `sync ssh`, the version check, and an embedding endpoint you configure | indexes every agent's transcripts on the machine (Claude Code, Codex, Cursor's SQLite, DSH, ~38 more) into one index; `deja embed` can post *"the redacted indexed text, truncated to about 2k characters"*; *"Pattern matching is not secret detection"* |

**Four READMEs say nothing about the network at all**, so their status is
**unknown, not clean**: `MichengAI/dsh-code-review`, `9087/dsh-diff-approval`,
`Anionex/dsh-turn-rewind`, `MichengAI/dsh-archive-manager` and
`hh719509125/dsh-preview-editor`. Reading their source is the only way to settle
it; `dsh-preview-editor`'s README does say its host half *"runs outside the
workspace sandbox, as your user, in this process"*, which is a separate reason to
read it first.

**What none of this changes.** No plug-in above touches the Jarvis app, its
backend or its rules; they change the tooling that builds Jarvis. Where one would
touch this project directly: the GitHub group reaches this repository and its
pull requests and holds a token; `deja-vu` would copy this project's own session
transcripts into a single index; `dsh-memoir` writes a `PROJECT_MEMORY.md` that
could be committed; `billion-context` would sit in the path of every conversation
about the code; and `dsh-Remote` and `dsh-mobile` publish the machine that holds
Jarvis's source and its pairing token.

## 8. How this list was built, and what it does not prove

- **Source.** The catalogue's per-category pages on https://awesome-dsh-plugin.com
  (the same list the in-app market reads), the catalogue's own
  [README](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin), and the
  READMEs of the nine plug-ins marked `README read` above.
- **A sampling limit, stated plainly:** each catalogue category page renders only
  the **first 24 plug-ins by downloads** (the header reads `24 / 292` and the
  rest are not in the page's HTML), and the Tools & Capabilities page (583)
  never rendered at all. Query strings such as `?sort=` and `?page=2` are ignored
  and `/session/2/` returns 404. **So absence from this document is not evidence
  that something does not exist** - 268 of the 292 Sessions entries and almost
  all of the Tools entries were never seen. The repo's `data/plugins/*.yaml` is
  the complete source, and reading it needs paging around the fetch tool's size
  cap.
- **The counts are the catalogue's**, at the date it last checked each entry; they
  were not re-measured here.
- **No plug-in's source was audited line by line.** The four already installed
  were scanned for host names and `modlens`' own diagnostic was run (section 7.1);
  everything else is descriptions and READMEs. So where a README is silent about
  the network - five of the eighteen - this document cannot say whether that
  plug-in is clean, and says so instead of guessing. The catalogue's own warning
  applies unchanged: a listing is not a review, and installing a plug-in runs
  third-party code with your permissions.
- **Not verified at all:** that any of these installs cleanly on this build, that
  any of them works on Windows, or that any of them is maintained. Those are
  questions for the day one is actually installed, with no agent running.

## 9. What reading the source changed (2026-10-09)

Sections 1-7 are catalogue-and-README work. After the owner asked how refined
these plug-ins actually are, the four most likely to be installed were read line
by line - the GitHub connector, `dsh-crosstalk`, `dsh-peer-bus` and
`@nanmicoder/dsh-agent-teams` - each in a clone under
`.dsh-scratch/plugin-eval/`, by a separate reader, with the deciding claims
re-checked here. **This section is what changed, and it withdraws two
recommendations.**

### 9.1 The GitHub connector: conditional, not recommended

- **Clean, and it held up:** every host in the code is `api.github.com`; one GET
  per call; an absolute path off that host is refused; no timers, polling,
  telemetry, analytics or routes; the token is never logged and never returned in
  tool output; the browser half cannot read it back (`client.js:32`,
  `index.js:30`, `156-165`, `246`, `266`, `561`).
- **`github_api` is a general authenticated GET, not a GitHub-shaped read**
  (`index.js:328-344`, `350`): any path, any query values, the token attached, and
  the full URL plus body handed to the model. Text from a hostile README or issue
  can therefore steer the agent into putting something it already knows into a
  query string.
- **`caFile` changes the whole process** (`index.js:541`,
  `tls.setDefaultCACertificates`): that CA becomes trusted by every TLS
  connection in the Harness, not only GitHub's.
- **The token would land in plain text.** Checked on this PC rather than taken on
  trust: `~/.dsh/.credentials.yaml` is plain YAML keys with no encryption marker.
  That file is DSH's own credentials store, not the plug-in's, and DSH's source
  skips the file-mode protection on Windows. Rule 3 asks that a key never be
  written to disk in plain text, and this is where it would go.
- **A reader's headline finding was wrong, and is corrected here.** It reported
  that the settings page crashes because the renderer never supplies `ctx` and
  `t`. The registered component is a closure wrapper that supplies them itself
  (`client.js:359-364`), so the renderer's prop set is irrelevant to it. The
  failure mechanism does not exist.
- **Still true:** two days old, one author, one star, no tests, no CI, no
  `peerDependencies`, and the README's "verified end-to-end" claims live in the
  author's workspace rather than in the package.

### 9.2 dsh-crosstalk: does not install here, and its safety claim is inert

- **It cannot build against this Harness, so `dsh plugin add` fails.** The app
  bundles `@deepseek-ai/dsh-tools@0.2.0-rc.2` (read from the package.json inside
  `app.asar`). In `0.1.1-rc.2` that package re-exported `JsonValue`
  (`lib/types/index.d.ts:17`); in `0.2.0-rc.2` it imports it from
  `@deepseek-ai/dsh-util-values` and no longer exports it. The plug-in imports it
  from `@deepseek-ai/dsh-tools` (`src/tools.ts:15`) - a compile error - its
  `postinstall` runs exactly that build, and no compiled `lib/` is committed.
- **"Same OS user only" cannot run on Windows.** `src/deliver.ts:91` requires
  *both* uids to be defined; `process.getuid` is `undefined` on this PC (checked
  here), and `src/identity.ts:114` documents that. Acceptance rests on NTFS
  permissions alone.
- **Nothing asks the owner.** `src/deliver.ts:183` hands the peer's text to
  `agent.followup(...)` on every poll; the only guard is a system-prompt sentence.
- **What is honest about it:** no network at all, atomic writes, tool shadowing
  that is properly scoped and reversible, and 49 tests that genuinely pass (run by
  the reader against 0.1.1-rc.2, because this sandbox forbids the test runner's
  child processes).

### 9.3 dsh-peer-bus: installable, better designed, still no tap

- **The install failure above cannot happen to it:** it ships plain JavaScript
  (`"." -> ./src/index.js`) with **no build, no `postinstall` and no `lib/`** -
  verified against the committed `package.json`, not the working copy.
- **The model cannot widen its own reach.** The default is deny (`allow: []` in
  `cordis.patch.yml`), and `/bus` exists only on the human command registry
  (`src/commands.js:219-230`), with a test pinning that a command-shaped message
  executes no command.
- **But a delivered message needs no tap.** `src/message.js:88-102` builds an
  ordinary user message with a plain-text lead-in, and the target runs a whole
  turn. No system-prompt text, no confirmation, no trust downgrade - that is the
  rule 4 problem, and it is by design rather than an oversight.
- **Its Windows permission claim is also weaker than documented:** it says the
  trust boundary is enforced by file permissions, but those are POSIX mode bits,
  and six of its own tests cannot pass on Windows for that reason.
- **It documents its own gap.** `verification/` records an unfixed split-brain
  when two processes resume the same session, and states its limits plainly,
  which is more than most of this catalogue does.

### 9.4 dsh-agent-teams: careful code, and the tap is missing

The most-adopted plug-in in this whole survey (2,006 stars, 56,429 downloads last
month) is also the most carefully written - and it fails rule 4 by default.

- **The install path is sound.** `lib/` is committed with both halves
  (`lib/index.js`, `lib/client.js`), there is **no `postinstall`/`prepare`**, and
  its `peerDependencies` name `0.2.0-rc.2` explicitly. It also sidesteps the exact
  trap that stops `dsh-crosstalk`: it imports `JsonValue` from
  `@deepseek-ai/dsh-util-values` (`src/tools.ts:16`), not from `dsh-tools`.
- **The approval gate is a default, not an enforcement.** Its own schema says so:
  *"Defaults to automatic for API compatibility"* (`src/tools.ts:729-733`), and
  the whole gate is one line - `const staged = args.approval === 'required'`
  (`src/tools.ts:765`). Anything that is not the literal string `required`,
  **including omitting the argument**, starts the team at once: members spawn and
  the scheduler dispatches (`src/tools.ts:820`). The safe path rests on one line
  of system prompt (`src/index.ts:140`).
- **The approval tool can be self-approved.** `agent_teams_approve` checks only
  that the `confirmation` string is not empty (`src/tools.ts:1034`) - and the
  model writes that string. The Web **Approve & Run** button reaches the same
  runtime and *is* properly gated to the owner's own session
  (`src/web-routes.ts:83`), so a network caller cannot approve; a model can.
- **Its README overstates this.** *"Only **Approve & Run** enables scheduling"*
  (README.md:51) is not true of the default tool route.
- **Clean everywhere else, which is why the one defect stands out.** No network at
  all (every runtime fetch is a same-origin `/plugins/...` path); no credentials -
  it never touches `~/.dsh/.credentials.yaml` and never reads `process.env`; state
  is confined to `<workspace>/.agent-teams/`; members are restricted to 4 of its
  14 tools; inbound bodies are capped at 1 MB.
- **One real integrity problem:** the repo's own attestation gate fails on its
  committed HEAD. `node scripts/git-artifacts.mjs` exits 1 with *"Git artifacts
  are stale or modified"* (run here, reproduced) - so the `lib/` that would be
  installed is not provably the `src/` that is committed. Structurally the two
  match (14 tools, 4 routes, the same approval line), so the practical risk looks
  small, but the project's own gate would be red on this commit.
- **Coupling to be aware of:** it reaches sub-agents through
  `Symbol.for('dsh.subagent.queuePrompt')`/`'dsh.subagent.deliverPrompt'`
  (`src/harness-compat.ts:25-28`). It fails loudly on drift rather than quietly,
  which is the right choice, but a member spawn is where that would surface.

**Verdict: not installed.** Offline, credential-free, workspace-scoped and
honestly documented - with one one-line default standing between the owner and an
unattended team.

### 9.5 How these were checked, and what is still unknown

Each reader read its own package in its own clone, installed nothing into the
profile, and wrote nothing under `~/.dsh`. The claims that decided the verdicts
were re-checked here, against the installed build and the published packages,
rather than taken from the reports: the `JsonValue` export change, the inert
Windows uid check, peer-bus's missing build hook, agent-teams's approval default,
and its failing attestation gate.

**The limits, stated plainly:** the installed Harness's own sources are not
readable on this machine (they live inside `app.asar`), so no reader could confirm
the harness APIs these plug-ins call; `dsh-peer-bus`'s Windows named-pipe path is
unproven here, because this sandbox forbids named pipes and the author's evidence
is macOS-only; `dsh-agent-teams`'s typecheck was **not** run, because installing
its dependencies failed in this environment, and its own `doctor` cannot see the
installed Harness at all; and **`dsh-knit` and `dsh-test-runner` were not read** -
they stay README-only, which is how they are marked in section 3.

One correction to what section 3 said earlier about `dsh-peer-bus`'s declared
versions: it declares `>=0.1.7-rc.2 <0.3.0-0`, not `^0.2.0-rc.2`. The narrower
range appeared to a reader's eye because the clone's `package.json` had been
edited to install its test dependencies. Both ranges include the installed
version, so the conclusion stands, but the detail came from a dirty working copy
and is corrected here.

## 10. What the owner decided

**Install nothing for now, and keep this writer-up** (2026-10-09). The
shortlist, the install lines and the caveats above are the record, so the
decision can be made later without repeating the research.

**Record where the data goes, and do not judge it** (2026-10-09). Asked which
standard to judge "sends data off the PC" against, the owner chose *"just tell me
where data goes, don't judge it"* - so section 7 names each destination and what
is known about it, and leaves the verdict to him. He then asked for that review to
be written into this document rather than left in the conversation.

**Read the source before trusting a README** (2026-10-09). Asked how refined these
plug-ins really are, the owner asked for a full evaluation, and then chose to have
this document corrected rather than left as the record of what the READMEs said.
That correction removed two of the four from the starting set (sections 9.1-9.3),
and both live peer-messaging plug-ins were left uninstalled.

**Leave the team plug-in alone** (2026-10-09). `@nanmicoder/dsh-agent-teams` is
the most-adopted multi-agent plug-in in the catalogue and, on this reading, one
line away from being usable - its team-creation tool defaults to running without
approval. The owner chose to leave it rather than fork or patch it: the **official
Agent Teams bundle already provides teams inside this profile**, so carrying a
third-party copy whose safe behaviour would have to stay patched is not worth it.
Nothing about the cross-conversation question was installed.
