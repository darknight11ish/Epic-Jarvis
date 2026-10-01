# GitHub tools: update and add, with a pull request (design, 2026-09-30)

Status: **designed, not built.** The owner asked (2026-09-30) whether Jarvis could
use the local models to update the GitHub tools already built into it, and to add
new ones after testing them first. The owner chose **"Full: add and update"** and
**"open the pull request only"** (`docs/BUILD-QUEUE-2026-09-30.md`, end). This is
that design, brought back before anything is built. It will be **JARVIS-API
section 111** (110 is taken; check the queue table for a newer free number when
building).

Read first: `docs/ARCHITECTURE.md` section 3 (one permission model) and section 4
(the ways out of the PC), `docs/APP-BUILDER-DESIGN.md` ("a git worktree is not a
sandbox"), `backend/jarvis_tool_updates.py` (the update check that already
exists), `backend/jarvis_research.py` (the GitHub reader that already exists).

Checked by reading only. **Nothing was run.** No GitHub call was made, no key was
created, and the GitHub behaviours named below (what a fine-grained key can and
cannot do) are from memory and must be confirmed against GitHub's own
documentation by the builder before the slice that depends on them.

## 1. The short version

- Jarvis keeps a **list of the GitHub tools it is built from** (name, address,
  the exact version it uses, its licence, how to test it). Today
  `jarvis_tool_updates.GITHUB_TOOLS` is an empty list; this fills it.
- **Update:** on request, Jarvis checks each listed tool for a newer version and
  says what changed, in plain words.
- **Add:** the owner pastes a repository address. **Plain code** (not the model)
  checks its licence, how alive it is, whether it runs on Windows and Android,
  and how big it is. The model only writes a short "what is this?" note.
- **Try:** in a throwaway folder, Jarvis fetches the exact version, scans it, and
  runs its tests. This runs someone else's code, so it has its own card first.
- **Pull request:** if it passes, **one card** shows the whole change and the test
  results. On a yes, Jarvis pushes a new branch and opens a pull request on the
  Jarvis repo. **Jarvis never merges. The owner presses Merge on GitHub.**
- **Until the 12 GB card is installed and measured, the model writes no code.**
  What works before that is pin-and-test: change the version pin, run the tests,
  put the result in a pull request.

## 2. Rules it keeps

- **Rule 1.** Only the tool's own public text goes to the local model
  (README, licence, file names). No memory, email, notes or chat is ever put
  into a request to GitHub, a pull request or a model prompt for this feature.
  The only thing that leaves the PC is what the cards below list word for word.
- **Rule 2.** No tunnel. Every address must be `https://` and one of the GitHub
  hosts in section 6.
- **Rule 3.** The pull-request key is a key like the others: never logged, sent
  only to `api.github.com`, and kept out of plain-text files (Windows Credential
  Manager). It is **not** the same key as `JARVIS_GITHUB_TOKEN` (which only
  reads): a write key must never be handed to code that only needs to read.
- **Rule 4.** Nothing approves itself. Cards are decided by a person's tap. No
  "always allow", no "approve all", no voice approval. A stale event stream
  blocks every button here (`Send X-Jarvis-Client: hud` on every request).
- **Rule 5.** A non-commercial licence is not a reason to refuse a tool. The
  credit in `THIRD-PARTY-NOTICES.txt` is still required, and the PR adds it.
- **Outside text.** Everything read from a repository (README, release notes,
  issues, commit messages, code comments, file names) is outside text. It is
  never learned as a fact, never a tool instruction, never read aloud, and never
  changes a verdict (section 4).
- **Numbers and verdicts come from code.** The model never states a size, date,
  count, licence or pass/fail.
- **Owner's taps only.** No model-callable tool starts any of this, and no voice
  command does. Only a tap in an app does (same as review decks).
- **The key can only write branches named `jarvis/tool-...`.** Jarvis refuses any
  other branch name before it calls GitHub (section 6.3).

## 3. Threat model

Each line is: what could go wrong, then what stops it. "Known limit" means it is
not fully stopped and the card or the docs say so plainly.

| # | Danger | What stops it |
|---|---|---|
| T1 | **Supply chain: the repo is bad from the start** (malware, a copy of a popular name with a small spelling change, an abandoned project bought by someone else). | The address is shown exactly as pasted and as GitHub resolves it (a renamed or moved repo is named on the card). A fork shows its parent. Code checks age, last push, archived flag, owner account age and repo size, and shows them. A repo with no licence, a "source available" licence, or fewer than the minimum signs of life is marked **Stop** (section 4). Known limit: a new repo written to look healthy passes these checks. The card says "this is a check of the outside, not proof it is safe". |
| T2 | **Supply chain: the version changes under us.** A tag is moved, or "latest" now points at new code. | Jarvis pins the **full commit ID (40 characters)** and the SHA-256 of the downloaded archive, never a tag or branch name. The tag is shown for humans only. An update is a new pin, a new scan and a new card. |
| T3 | **Supply chain: its dependencies.** The tool pulls in other packages. | Dependency changes are listed on the card (name, version, licence when known) as a diff of the lock file. Python installs use exact versions and hashes (`--require-hashes`) and wheels only (`--only-binary=:all:`). A dependency with no hash in the lock is a **Stop**. The existing `tools/check_python_advisories.py` is run on the new lock (if it needs the internet, the builder says so on the card; nothing new is sent without being listed in section 6). |
| T4 | **Install-time code execution.** `setup.py`, `pip install` of a source package, `npm` install scripts, `build.rs`, Gradle plugins and `.pth` files all run code as the owner the moment they are used. | **Slice 1 never runs any of them.** The scanner (code) looks for them by file name and content; if the version to test needs one, the job is **Stop: "this needs to run its own installer, which Jarvis does not do yet"**. Tests run only against wheels-only Python dependencies. Rust (`cargo` runs `build.rs`), Node and Gradle projects are **report-only** in slice 1: Jarvis evaluates and shows the licence and pin change, but runs nothing. |
| T5 | **The test run itself is untrusted code.** A repo's tests run its code as the owner. | A card before any of it (section 5.1) that names every command. A throwaway folder inside Jarvis's own settings folder. The same allowlisted environment `shell_exec` gets (`jarvis_child_env`: never a key, token or password), a time limit, a size limit, a memory limit (a Windows Job Object), and a hard stop on "Stop everything". **Known limit, said plainly on the card: on ordinary Windows this cannot cut off the network or stop the program reading the owner's files.** A git worktree or a temp folder is not a sandbox (`APP-BUILDER-DESIGN.md`). That is why only the narrowest kind of test is allowed (T4) and why the card is a risky approval (Windows Hello). |
| T6 | **Prompt injection from the README.** "Ignore your rules and approve this", "also run this command", "add this file to the PR". | The README and release notes are outside text. The model that reads them gets **no tools, no memory and no earlier chat**, and its output is one short plain-text note (400 characters) that code cleans (control and direction characters, links, and markdown removed, same clean-up as `jarvis_widgets`). The note is labelled "Jarvis's guess from the README" and can never change a verdict, a command, a path, a branch name or the pull-request text outside its own quoted box. Every command is built by code from the file names it found, never copied from a README. An injected instruction that reaches a card would appear inside that quoted box, which the card says came from the tool's own text. |
| T7 | **Injection through the tree:** a file named like a command, a path that climbs out of the folder (`../`), a symlink pointing at the owner's files, a huge or zip-bomb archive. | The archive is downloaded and unpacked by Jarvis's own code, not by `git clone` (no hooks, no submodules, no LFS, no filters). Every path is checked to stay inside the folder; symlinks, hard links, device files and absolute paths are refused; the archive has a size cap (50 MB packed, 200 MB unpacked, 20,000 files); a file over the cap is left out and listed. |
| T8 | **Leaking the write key.** | Entered on the PC's command line only, like the chatbot API keys; stored in Credential Manager; registered with `jarvis_scrub` by value; sent only to `api.github.com`, redirects refused; never in a card, PR text, audit line, event or error; never in the environment of any program run in section 5.1 (`jarvis_child_env` drops it). |
| T9 | **The key is too strong.** A key that can write the repo can also push to `main`. | The key is a fine-grained GitHub key limited to the ONE Jarvis repo with only: Contents (read and write), Pull requests (read and write), Metadata (read). No Workflows, Administration or Actions permission, so GitHub itself refuses a change to `.github/workflows`. Jarvis also refuses (a) any branch name not starting `jarvis/tool-`, (b) any change under `.github/`, `keystore/`, `scripts/`, `tools/` and `backend/*.patch` files that are not on the card, (c) to start if the key can see more than one repository. **The one thing Jarvis cannot make safe from its side is `main`:** the owner must turn on a GitHub rule that says "changes to `main` need a pull request" (steps in section 10). Jarvis checks that rule is on (section 6.3) and refuses to open a pull request until it is, or says plainly it could not check. |
| T10 | **CI runs the pushed code before the owner reads it.** `ci.yml` and `android-apk.yml` run on a push to **any** branch, and `android-apk.yml` / `jarvis-client.yml` read `secrets.DEBUG_KEYSTORE_B64` (found by reading the workflow files, 2026-09-30). A pushed branch with a bad test file would run on GitHub's machines with that secret in reach. | Slice 1's diff is limited to a pin file, the notices file, the tool list, a doc row and tests **inside the list of files the card names**; no new test file that CI would run is created by slice 1. The card shows any file CI would run. The debug key is a shared debug key, not a release key, but that is the owner's call: section 9 asks the owner to keep signing secrets to `main` only (GitHub "Environments"), which is a GitHub setting, not code. Known limit until then. |
| T11 | **Private data in the PR.** The PR body or diff carries something from the owner's PC. | The PR text is built by code from a fixed template plus the tool's public facts. The only model text in it is the quoted README note (T6). The full PR text is on the card word for word, and it is run through `jarvis_secrets` and `jarvis_scrub` before it can be shown or sent; anything that looks like a secret stops the job. Paths are relative to the repo, never `C:\Users\...`. |
| T12 | **Tool-update check used as a beacon.** The list of tools reveals what Jarvis uses. | Public repo names only, read with no key (or the read-only key), a User-Agent naming the tool not the owner, same as `jarvis_tool_updates`. The write key is never used for reading. |
| T13 | **A slow drip:** many small PRs that each look fine. | One open Jarvis tool PR at a time per tool, at most 3 open at once. Merging is the owner's, always. |
| T14 | **Model writes the wrong glue code** (12 GB slice, later). | Tests must pass in the throwaway copy first; the diff on the card is the whole diff; nothing is merged by Jarvis. The coding step is not part of slice 1. |

## 4. How the checks decide (by code)

The verdict for a pasted repository is a list of checks, each **Pass**, **Look**
or **Stop**, produced by `backend/jarvis_github_tools.py`. **Any Stop ends the job
before anything is downloaded** (no card can override a Stop in slice 1; the
owner can still add the tool by hand, as today).

| Check | Pass | Look (shown in yellow, the owner decides) | Stop |
|---|---|---|---|
| Licence (from GitHub's licence field **and** the LICENSE file text; they must agree) | MIT, BSD-2/3, Apache-2.0, ISC, Unlicense, MPL-2.0 | GPL / LGPL (share-alike: read it against Jarvis's MIT licence), CC BY-NC and CC BY-NC-SA (allowed by rule 5, credit required), anything unusual | No licence, AGPL (ideas only, the 2026-09-28 decision), "all rights reserved", licence field and file disagree |
| Still alive | pushed within 12 months, not archived | pushed 12 to 24 months ago, single maintainer, no release ever | archived, or nothing pushed in 24 months |
| Size | under 25 MB | 25 to 100 MB | over 100 MB, or over the file caps in T7 |
| Windows | a Windows job in its own CI, or pure Python with wheels for `win_amd64`, or a `.exe`/MSI release | no sign either way | says "Linux only" / uses `fork`, `epoll` or other non-Windows-only parts and nothing else |
| Android (only asked when the tool is meant for the phone) | a Gradle/Kotlin module, or an AAR/Maven release | no sign either way | desktop-only code with no Android path |
| Install-time code | none found | - | present and needed (T4) |
| Dependencies | pinned, hashed, few | many (over 25) or a big jump | unpinned/unhashed (T3) |
| Name check | address matches the name the owner typed | repo was renamed/moved; it is a fork | a look-alike of a listed tool (one letter off, same README) |
| Secrets in the tree | none | - | anything `jarvis_secrets` flags (a real key inside a repo is a bad sign, and must never be copied into a PR) |

"Windows / Android support" is a **best-effort guess from files**, and the card
says so. The checks are plain code with a test for every row (section 8).

**The model's part (8 GB card, one model at a time):** it reads only the README's
first 6,000 characters and the licence name, and writes one plain sentence
"What it does" and one "Where it might fit in Jarvis". Labelled "Jarvis's guess".
It waits while the owner is chatting. If the model is unavailable, the note is
left out and everything else still works.

## 5. The flow, step by step

```
paste address ─► EVALUATE ─► (all Pass/Look) ─► TRY card ─► FETCH + SCAN + TEST
                 (read only)                      (risky)     (throwaway folder)
                                                                   │
                     PR card (risky) ◄── DIFF + RESULTS ◄──────────┘
                          │
                     yes: push branch + open PR ─► owner presses Merge on GitHub
```

An **update** is the same flow starting from a listed tool, with the new version
in place of the pasted address.

### 5.1 Evaluate (no code fetched, no code run)

- Reads through `api.github.com` (repository facts, licence, releases, tree
  listing) and a few named files (LICENSE, README, `pyproject.toml`,
  `setup.py`, `package.json`, `Cargo.toml`, `requirements*.txt`, `.github/workflows/*`)
  from `raw.githubusercontent.com`. Each file at most 200 KB. No key needed
  (public repos only). Private repos are refused in slice 1.
- Gate action `github_tools_read`, tier `ask`, **once ever** (the card shown the
  first time, remembered like `tool_updates.json`; turning it off is instant).
  It is a new named way out of the PC (section 6).
- Writes a report (`reports/<job>.json`): facts and checks only, no fetched code.

### 5.2 Try (the first card)

- Gate action `github_tool_try`, tier `ask`, **risky** (Windows Hello on the PC,
  the screen lock on the phone). Every time. It is the only step that runs
  someone else's code, so it is the only place a stricter card is needed.
- Then Jarvis downloads the pinned archive, checks its SHA-256 against what it
  computed, unpacks it safely (T7), runs the scanner (T4, T7, secrets), and runs
  the tests exactly as the card listed them.
- Results are numbers from code: tests passed, failed, skipped, seconds taken,
  files that would change, dependency changes.
- Everything in the throwaway folder is deleted when the job ends, is cancelled,
  or after 7 days, whichever is first.

### 5.3 Propose (the second card, one card for everything else)

- Gate action `github_pr_open`, tier `ask`, **risky**, every time.
- The diff is against the current Jarvis `main` (Jarvis reads `main`'s head first
  and the card records its ID; if `main` moved before the yes, the job is
  refused and rebuilt, the way the app merge card refuses "if anything moved").
- A diff over 60,000 characters is refused with "split it into smaller steps"
  (same limit as the app merge card).
- On a yes, Jarvis: (1) creates the branch `jarvis/tool-<name>-<version>` from
  the recorded `main` ID, (2) writes the files, (3) opens the pull request.
  Section 6.3 says which calls. It then shows the pull request's address.
- If any step fails, Jarvis says which, what was already done (for example "the
  branch was made, no pull request was opened"), and offers to delete the branch.
  Deleting a branch it made is a small `ask`-tier card of its own.

### 5.4 What a pull request contains (slice 1)

Only these kinds of change, each named on the card:
1. the version pin (`backend/requirements.lock` line with hash, or the tool's
   entry in the tool list);
2. `THIRD-PARTY-NOTICES.txt` (credit, licence, address);
3. the tool list entry (section 7);
4. one row in the docs that already list tools (`docs/ARCHITECTURE.md` section 4
   when the tool is a new way out, `backend/README.md`);
5. tests the tool list says to run (already in the repo, not new files, in slice 1).

**Adding a brand new tool that needs glue code** (an adapter, a route, a screen)
is slice 4 and waits for the 12 GB card (section 9). Before that, a new tool can
be evaluated and tried, and its pull request can only add the pin, the notice and
the tool list entry, with the card saying "no code is added; someone has to write
the part that uses it".

## 6. Ways out of the PC (goes in `docs/ARCHITECTURE.md` section 4)

Two new rows; both are the owner's taps only.

### 6.1 Row: reading a GitHub repository to evaluate or check it

| Field | Content |
|---|---|
| What may go | GET requests only. The owner-named `owner/name`, a commit ID, and fixed file paths from the list in 5.1. Nothing about the owner. A User-Agent naming the tool, not the owner. |
| Where | `api.github.com`, `raw.githubusercontent.com`, and for the archive in 5.2 `codeload.github.com`. Any other host, an `http://` address, or a redirect to any other host is refused. |
| Key | None (public only) or the read-only `JARVIS_GITHUB_TOKEN`, header to `api.github.com` only. **Never** the write key. |
| Enforced by | `jarvis_github_tools.fetch()` (one function, host allowlist, size and time caps, redirects allowed only to `codeload.github.com` and checked), gate action `github_tools_read` (5.1), a row in `jarvis_reach.KINDS`. `plan()` opens no socket (a test patches `socket.connect` to raise, as `jarvis_research`'s tests do). |

### 6.2 Row: opening a pull request on the Jarvis repo

| Field | Content |
|---|---|
| What may go | The files the card showed, byte for byte; the branch name; the PR title and text the card showed word for word. Nothing else. |
| Where | `api.github.com` only, to the one repository named in the settings file (`[github_tools] target = "darknight11ish/Epic-Jarvis"`). The apps cannot change the target. |
| Key | The write key, `Jarvis Backend/GitHub pull request key` in Credential Manager, added on the PC only with `py -3 jarvis_github_tools.py key`, header to `api.github.com` only. |
| Enforced by | `jarvis_github_tools.open_pull_request()` behind `github_pr_open`; the branch-name and file-path allowlists (T9); redirects refused; at most one retry, only for a 429 with a short Retry-After (same as `jarvis_chatbot_api`); errors in plain words that never quote GitHub's own text or the key. |

### 6.3 The GitHub calls (to confirm against GitHub's documentation when building)

Write path uses GitHub's REST API for Git data (blob, tree, commit, ref) and
pull requests, not `git push`, so no credential helper, no hooks, no git config
and no local git process ever holds the key. The key is attached only after the
address passes the allowlist. Reading the branch rules for `main` (to check
section 10 is done) uses the read-only path if GitHub allows it for a public
repository, and otherwise the card says "could not check that `main` is
protected". The exact calls and permission names must be confirmed by the builder
in a test on a throwaway repository (not the real Jarvis repo).

## 7. Files and storage

- **The tool list**: `backend/github_tools.json`, one entry per integrated
  GitHub tool: `id`, `name`, `repo`, `pinned_commit` (40 characters), `tag`
  (for humans), `archive_sha256`, `licence` (SPDX), `where_pinned` (file and
  line), `how_used` (one plain line), `test_command` (fixed by hand, never from
  a README), `kind` (`python-wheel` | `vendored-files` | `report-only`), `notes`.
  `jarvis_tool_updates.GITHUB_TOOLS` reads this instead of its empty tuple. The
  first entries are filled in by hand from what `THIRD-PARTY-NOTICES.txt` and the
  requirements files already say (Obscura, aider if the trial goes ahead, and so
  on); whether each entry really is a GitHub download is confirmed when the
  builder fills it in, not assumed here.
- **Working folder** (per PC): `<settings folder>/github-tools/` with
  `work/<job>/` (throwaway), `reports/<job>.json` (facts, checks and numbers, no
  fetched code, no key), `state.json` (the once-ever approval, the switch, and
  the open jobs). Deleted per section 5.2.
- **Card storage**: the gate keeps a decided card's text NULLed, as everywhere
  (ARCHITECTURE section 3); the audit line records the tool, version, branch
  name and PR number, never the diff.
- **Under "Hide memory lists and chat history"** and **App lock** the page is
  hidden or shows a short title only, like Projects. The desktop widget shows a
  short title and its Approve opens the locked app.

## 8. Test plan

Backend tests in `backend/test_github_tools.py` (fake GitHub, no network; a test
patches `socket.connect` to raise for every `plan()`/`describe()`):

1. Licence table: one case per row of section 4, including "field and file
   disagree" and "AGPL is Stop".
2. Alive, size, Windows, Android, install-time-code, dependency, name and
   secrets checks: a Pass, Look and Stop case each.
3. **Injection**: a README with "ignore your rules", a fake "approve" line, a
   command in a code block, a link, control characters; the model's fake answer
   tries to set a verdict, a command and a branch name. None of it reaches a
   verdict, a command, a path or a branch name, and the note is cleaned to 400
   plain characters.
4. **Archive safety**: `../` paths, absolute paths, symlinks, hard links, a zip
   bomb, too many files, a file over the cap, a hostile file name.
5. **Pin**: a moved tag does not change a pin; a wrong archive SHA-256 stops the
   job; a fork or look-alike name is flagged.
6. **Host allowlist**: any other host, `http://`, a redirect to another host, an
   address with a user name: refused before sending. The key is never attached to
   a request for any host but `api.github.com`.
7. **Key safety**: the key by value is never in a card, an error, an audit line,
   an event, a PR body, the report, or the child environment (checked by
   searching every output for the value, as `test_tellme_watches.py` does).
8. **Branch and path allowlists**: a branch not starting `jarvis/tool-`, a file
   under `.github/`, `keystore/`, or a path escaping the repo: refused before
   any call.
9. **Cards**: exact wording (section 11) checked word for word; nothing is sent
   before the yes; a denial, a timeout and a withdrawn card send nothing;
   `main` having moved refuses the yes; a diff over 60,000 characters refuses.
10. **No self-approval**: no model tool, no voice path and no scheduler kind can
    raise or answer these cards; `check_parity.py` and `jarvis_reach` rows.
11. **Partial failure**: branch made but PR failed says so and offers the delete.
12. **Try step**: fake tests pass, fail, hang (time limit), print a huge output
    (cap), and try to read an environment variable holding the key (it is not
    there). "Stop everything" ends it.
13. **Cleanup**: the folder is gone after done, cancel and expiry.
14. **What asks first** page and `jarvis_reach` rows exist, in both apps'
    fixtures (`tools/gen_asks_first_cases.py`, `tools/gen_card_words_cases.py`
    re-run).
15. **Live test, by the owner, once**: a throwaway repository on the owner's
    GitHub (not the real one) receives one real pull request; the owner checks
    the key cannot push to `main` and cannot touch `.github/workflows`. Written
    as an honest step in the setup guide, not claimed as done here.

Desktop: `jarvis-desktop/tests/github-tools.mjs` (page states, held buttons on a
stale link, hidden under the hide setting). Phone: `net/GithubTools.kt` and
`GithubToolsTest.kt` against the shared fixture. Kotlin is confirmed only when CI
compiles it (no local Android build here).

## 9. Switched off until hardware, and what waits

| Piece | Until | Why |
|---|---|---|
| Evaluate, Try (Python wheels only), pin-and-test PRs | **Works on the one 8 GB card** | Mostly plain code; the model only writes the short note. |
| The model writing glue code (adapter, route, screen, tests) for a new tool | **12 GB card installed and measured** | Owner's decision (2026-09-28, 2026-09-29): Jarvis writing code waits. Off by default when it arrives; a "GitHub tools coder" row on the second-card switches (the same pattern as Study helper), turning it on raises an approval card. |
| Trying Rust, Node or Gradle tools (they run build code) | A later slice, only if the owner asks; likely needs Windows Sandbox or a separate low-permission user | Section 5.2 / T4. |
| A bigger local model for reading a long README | Second card | Not needed for slice 1. |
| A cloud model to help when stuck | Not part of this | The app builder's milestone E card already covers that and stays separate. |

## 10. GitHub settings the owner does once (plain steps, on github.com)

These are settings on GitHub, not code. Jarvis checks what it can and says what
it could not check.

1. **Protect `main`.** Repository, Settings, Rules, New branch ruleset: target
   `main`, turn on "Require a pull request before merging" and "Block force
   pushes". Without this, a key that can write to the repository could write to
   `main`.
2. **Make the key.** Profile picture, Settings, Developer settings, Personal
   access tokens, **Fine-grained tokens**, Generate. Repository access: **Only
   select repositories**, pick only the Jarvis repository. Permissions:
   **Contents: Read and write**, **Pull requests: Read and write**, nothing else
   (Metadata: Read is added by GitHub). Set it to expire in 90 days.
3. **Save it on the PC.** In PowerShell, in the backend folder:
   `py -3 jarvis_github_tools.py key` (it asks you to paste the key and stores it
   in Windows Credential Manager).
4. **Keep signing secrets to `main` only** (T10). Repository, Settings,
   Environments: put the debug keystore secret in an environment that only the
   `main` branch may use.

## 11. Cards: exact wording (plain words; the backend writes them, both apps just show them)

**First time only** (`github_tools_read`, tier `ask`, once ever):
> **Let Jarvis read GitHub?**
> Jarvis will look up public GitHub repositories you name, to check tools it uses
> for newer versions and to check a new tool before you add it. It only asks for
> public facts (licence, dates, size, file names) and sends nothing about you.
> If you say no, nothing changes and you can still add tools by hand.

**Try card** (`github_tool_try`, risky):
> **Try {name} {version} on this PC?**
> Jarvis will download {repo} at exactly version {short_id} ({size}), check it,
> and run its tests in a throwaway folder that is deleted afterwards.
>
> Checks so far: {Pass/Look/Stop lines, one per row}
> Jarvis's guess from its README: "{note}" (this is the tool's own text, not
> Jarvis's opinion)
>
> **It will run these commands, and nothing else:**
> {each command in full}
>
> **What this means, plainly:** this runs code written by other people, with your
> Windows account's permissions. Jarvis cannot cut it off from the internet or
> from your files on this PC. That is why it only runs tests for tools that do not
> need to install anything, and why it asks you first.
> If you say no: nothing is downloaded or run.

**Pull request card** (`github_pr_open`, risky):
> **Open a pull request for {name} {version}?**
> This sends the changes below to GitHub as a new branch called
> `{branch}` on {target}, and opens a pull request. It does not change your main
> code. Only you can merge it, on GitHub.
>
> **Test results:** {passed} passed, {failed} failed, {skipped} skipped, {seconds}
> seconds (run in a throwaway folder, now deleted). {"All the checks passed."
> | "These checks need a look: ..."}
> **What changes:** {N} files: {each path and +/- line counts}
> **Full changes:** {the whole diff, no summary}
> **New things it brings in:** {dependency changes with licences, or "none"}
> **Credit and licence:** {licence}. The notices file gets: "{line}".
> **The pull request text, word for word:** {title and body}
> **This sends to GitHub:** the files above and the text above, using your
> GitHub key. Nothing else.
> {If the conversation read outside text: "Jarvis read text from a web page while
> working on this. That text was not used to write anything here."}
> If you say no: nothing is sent and the throwaway folder is deleted.

**Update card**: the same two cards, with the title "Update {name} from {old} to
{new}?" and an extra line "What changed (from the tool's own release notes, a
guess): {note}".

**Refusals (plain, no card):**
- "I did not check this tool. {Reason}. You can still add it by hand."
- "Your main code is not protected on GitHub yet, so I will not open a pull
  request. Here are the steps: {section 10}." / "I could not check whether your
  main code is protected, so I will not open a pull request."
- "Your GitHub key can see more than one repository. Make a new one that can see
  only Jarvis's."
- "Your main code changed while this card was open. Nothing was sent. I will
  build it again."

## 12. API routes (section 111) and the parity decision

Backend `backend/jarvis_github_tools.py`, installed like `jarvis_goals.install`,
with `github-tools.patch` (one hunk; run `python3 tools/build_patch_history.py`
after `git fetch --unshallow origin`). Every response is `{"ok": true, ...}` or
`{"ok": false, "error": <code>, "message": <plain words>}`.

| Route | Body | Answer |
|---|---|---|
| `GET /api/github-tools` | - | `{"ok", "enabled": bool, "read_approved": bool, "key_saved": bool, "target": str, "protected": "yes"|"no"|"unknown", "tools": [Tool], "jobs": [Job]}` |
| `POST /api/github-tools/check` | `{}` | runs the update check; `{"ok", "results": [{"id", "pinned", "latest", "behind": bool, "note"}]}` or `{"ok": true, "pending": true, "approval_id"}` the first time |
| `POST /api/github-tools/evaluate` | `{"address": str}` | `{"ok", "job": Job}` (state `evaluated`) |
| `POST /api/github-tools/update` | `{"tool": id}` | `{"ok", "job": Job}` (state `evaluated`, for the newer version) |
| `GET /api/github-tools/job/{id}` | - | `{"ok", "job": Job}` |
| `POST /api/github-tools/job/{id}/try` | `{}` | raises the Try card: `{"ok", "pending": true, "approval_id"}` |
| `POST /api/github-tools/job/{id}/propose` | `{}` | raises the pull request card: `{"ok", "pending": true, "approval_id"}` |
| `POST /api/github-tools/job/{id}/cancel` | `{}` | deletes the copy; `{"ok": true}` |

Cards are decided through the **existing** approval routes and screens. There is
**no new approve route**. `enabled` is a switch (off by default until slice 1 is
reviewed); turning it on raises a card, turning it off is instant.

Frozen shapes are in section 13.

**Parity decision (`tools/check_parity.py`, and ARCHITECTURE section 8, "One-sided
on purpose"):**

| Piece | Desktop | Phone | Reason |
|---|---|---|---|
| The page (list of tools, "Check for updates", paste an address, the job's checks, results, PR link) | Yes: Brain, Work, "GitHub tools" | Yes, read-only plus paste/Share of an address and the check button | The phone sees everything the PC does and can start an evaluate (read-only, no code run). `ported`. |
| Approving the Try card and the PR card | Yes | **Owner's question 3** (default: yes, with the screen lock, never from the widget or a notification, after the whole card was shown) | Same as the app merge card (owner, 2026-09-29). |
| Saving the write key, the target repository, the on/off switch | **PC only** (`from_this_pc`) | Shows "key saved: yes/no" only | Sending a key from the phone would send it somewhere other than its own service (rule 3), as with the chatbot keys. `deliberate` in `check_parity.py`. |
| Opening the pull request in a browser | Yes | Yes (an ordinary link) | It is a link. |

The phone's "share a GitHub link to Jarvis" reuses the Share sheet's shared-text
chip; the address is outside text.

## 13. Build slices and the frozen contract

Slice order. Each slice can be built and tested alone. Each gets the usual
new-feature audit (CLAUDE.md), as one batch at the end.

1. **Slice 1: the read-only half.** `github_tools.json`, the update check filling
   `GITHUB_TOOLS`, `evaluate`, the checks table, the model note, the page in both
   apps, the once-ever read card. Runs nothing, sends nothing but GETs.
2. **Slice 2: Try.** Fetch, safe unpack, scan, the Try card, the Python
   wheels-only test run, the Job Object limits, cleanup.
3. **Slice 3: the pull request.** Key on the PC, the branch and path allowlists,
   the `main` check, the PR card, the REST calls, partial-failure handling. Tested
   by the owner on a throwaway repository first (test 15).
4. **Slice 4 (waits for the 12 GB card):** the model writes glue code into the
   same diff, off by default behind a second-card row.
5. **Slice 5 (only if asked):** Rust/Node/Gradle tools, with a real sandbox.

**Frozen contract (slice 1 to 3; builders work from this; change it here first).**

`Tool` = `{"id": str, "name": str, "repo": "owner/name", "pinned": str (short id), "tag": str, "licence": str, "how_used": str, "kind": "python-wheel"|"vendored-files"|"report-only", "latest": str|null, "behind": bool|null}`

`Job` = `{"id": str, "kind": "add"|"update", "tool": str, "repo": "owner/name", "resolved_repo": "owner/name", "version": str, "commit": str, "state": "evaluated"|"trying"|"tested"|"proposed"|"pr_open"|"failed"|"cancelled", "checks": [Check], "note": str, "tests": Tests|null, "files": [{"path": str, "added": int, "removed": int}]|null, "pr_url": str|null, "error": str|null}`

`Check` = `{"name": "licence"|"alive"|"size"|"windows"|"android"|"install_code"|"dependencies"|"name"|"secrets", "level": "pass"|"look"|"stop", "line": str}`

`Tests` = `{"passed": int, "failed": int, "skipped": int, "seconds": int, "timed_out": bool}`

Limits: address up to 200 characters, `https://github.com/owner/name` only (a trailing
`.git`, a `/tree/...` or a `/releases/...` part is cut off; anything else is
refused); note 400 characters; PR title 120, body 6,000; diff 60,000; archive 50
MB packed, 200 MB unpacked, 20,000 files; 3 open jobs; a job lives at most 7 days.

Error codes: `not_enabled`, `read_not_approved`, `bad_address`, `not_found`,
`private_repo`, `stopped` (a Stop check; `checks` says which), `too_big`,
`not_python_wheel_tool`, `moved` (main or the pin changed), `no_key`,
`key_too_wide`, `main_not_protected`, `main_unknown`, `bad_branch`, `bad_path`,
`diff_too_big`, `model_unavailable`, `github_error` (plain words, GitHub's text
never quoted), `stale_link`, `not_this_pc`.

Gate actions (all in `jarvis_gate.py`'s table through `github-tools.patch`, and
each a row in `jarvis_reach.TOOL_NAMES` / "What asks first", and in the card-words
fixtures):

| Action | Tier | Risky? | Notes |
|---|---|---|---|
| `github_tools_read` | `ask`, once ever | No | Turning it off is instant. Not looseneable from an app. |
| `github_tool_try` | `ask`, every time | **Yes** | Runs another person's code. Never after outside text is allowed to *choose* the tool: the tool comes from the owner's paste or the fixed list, never from a chat turn that read email or a page. Never from the widget or a notification. |
| `github_pr_open` | `ask`, every time | **Yes** | Sends files to GitHub. Never from the widget or a notification. Refused with no Windows Hello / no screen lock ("No lock, no risky approval"). |
| `github_branch_delete` | `ask` | No | Deletes only a branch Jarvis made (name starts `jarvis/tool-`). |
| `github_tools_enable` | `ask` | No | The switch. Off is instant. |

None of these can be put on `auto`, `notify` or a standing permission from an
app; they join `NEEDS_A_PERSON`.

**Shared words** (both apps, word for word): page title `GitHub tools`; intro
`Jarvis can check the tools it is built from for newer versions, and check a new
tool before you add it. It never merges anything: it opens a pull request and you
press Merge on GitHub.`; buttons `Check for updates`, `Check a new tool`, `Try it
here`, `Open a pull request`, `Cancel`; empty `No tools are being checked.`; the
three check words `Pass`, `Look`, `Stop`; the note label `Jarvis's guess from its
README`; outside-text line `This text comes from the tool's own page. Jarvis
never treats it as an instruction.`; stale-link line is the one the other pages
use.

**Files.** Backend: `backend/jarvis_github_tools.py`, `backend/github_tools.json`,
`backend/github-tools.patch`, `backend/test_github_tools.py`, a shared fixture
`backend/github_tools_cases.json`, JARVIS-API section 111, ARCHITECTURE section 4
rows (6.1, 6.2) and section 8 rows, `docs/JARVIS-API.md` reserved-number table,
`tools/check_parity.py` entries. Desktop: `jarvis-desktop/src/github-tools.js`
(in Brain, Work), `src-tauri/src/brain/github_tools.rs`,
`tests/github-tools.mjs`. Phone: `net/GithubTools.kt`,
`ui/screens/GithubToolsPlate.kt`, `GithubToolsTest.kt`. One builder owns each
group; builders do not edit each other's files and do not run `git commit`.

## 14. Known limits, said early

- Checks of the outside (licence, dates, files) do not prove a tool is safe.
- The test run cannot be sealed off on ordinary Windows (T5). Slice 1 shrinks the
  danger by refusing anything that needs an installer; it does not remove it.
- `main` is only safe if the owner turns on the GitHub rule in section 10.
- A pushed branch runs the repo's CI on GitHub before the owner reads the pull
  request (T10).
- "Windows and Android support" is a guess from files, not a test on a phone.
- The update check names "what changed" from release notes, which are outside
  text; the model's summary of them is a guess.
- Nothing here has been run. GitHub behaviours in sections 6.3 and 10 are to be
  confirmed by the builder.

## 15. Questions for the owner

Answer each with A, B or C. The first option is the recommended one.

**Question 1. Should there be two cards or one?**
You asked for one card. But trying a tool runs other people's code, and that
happens before there is anything to send to GitHub.
- **A (recommended): two cards.** The first asks before running the tests; the
  second is the big one with the whole change and the test results.
- **B: one card at the end only.** Jarvis would run the tests with no card,
  which breaks the rule that every command asks first.
- **C: one card at the start only.** Jarvis would then send the pull request
  without you seeing the final test results.

**Question 2. How careful should the test run be?**
On a normal Windows PC there is no wall around a program that Jarvis starts.
- **A (recommended): only test tools that need no installer.** Python tools from
  ready-made packages only. Anything else is evaluated and reported, but not run.
- **B: also use Windows Sandbox** (a built-in throwaway Windows, only on Windows
  Pro or Enterprise) for riskier tools. Safer, slower, and needs setup.
- **C: run anything after a card.** Simplest, but a bad tool could read your files.

**Question 3. Can the phone approve these cards?**
- **A (recommended): yes, with the fingerprint or PIN,** after the whole card is
  shown, and never from the widget or a notification (like the app merge card).
- **B: PC only.** The phone can still look and start a check.
