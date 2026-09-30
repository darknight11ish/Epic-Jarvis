# Carrying on in a new Claude account

Read this if the work moves to a different Claude account (or a fresh start). The
**repository carries almost everything**; a few things live in the account and must be
set up again. Do the steps in order. Nothing here needs a password pasted into chat.

Start with `docs/HANDOFF-2026-09-30.md` once the session can read the repository. Its
"paste this to start" box is the first message to send.

---

## 1. What comes along, and what does not

**Comes along (it is in the repository):**
- `CLAUDE.md`: the owner's five rules and every decision, in order.
- `docs/HANDOFF-2026-09-30.md`: where things stand, the queue, known unfixed findings, lessons.
- `docs/audit-reports-2026-09-29-30/`: 60 saved sub-agent reports (the evidence).
- `.claude/agents/*.md`: the read-only helper agents (bug-hunter, feature-auditor,
  rules-reviewer, phone/desktop playtesters, suggestion-checker, ...).
- All code, tests and CI. The owner's PC and phone are NOT tied to the Claude account.

**Does not come along (set up again in the new account):**
- Chat and session history (the handoff file replaces it).
- The GitHub connection and the Claude GitHub App install (step 2).
- The cloud environment: which repository, network access, setup script (steps 3-4).
- Personal preferences (the "multiple choice" preference, step 5).
- Connectors, scheduled routines, PR subscriptions, artifacts. Recreate only what is needed.
  (An unrelated "Daily awesome reminder" routine belongs to the old account.)

---

## 2. Connect GitHub (the repository is `darknight11ish/Epic-Jarvis`)

1. Sign in at claude.ai with the new account.
2. Connect GitHub: <https://claude.ai/connect-github>. Use the GitHub account that owns
   or can push to `darknight11ish/Epic-Jarvis` (the owner's own account).
3. Make sure the **Claude GitHub App** is installed on that repository:
   <https://github.com/apps/claude/installations/select_target>. If the repository
   belongs to an organisation, ask an owner of it to install the app.
4. The repository must be **selected when a session starts**. If a session has no code
   in it, nothing is wrong with the account; start a new session with the repository
   selected.

Rules that stay the same: pull requests are made and merged on GitHub with a **merge
commit, never squash**; never merge over a red check.

---

## 3. Create the cloud environment (Claude Code on the web)

In the environment settings (the cloud environment menu in the session's title bar, then
Edit):

- **Repository:** `darknight11ish/Epic-Jarvis`, default branch `main`.
- **Network access:** the work needs these hosts. Pick an access level that allows them,
  or add them to the allowed domains: `github.com`, `api.github.com`, `pypi.org`,
  `files.pythonhosted.org`, `index.crates.io`, `static.crates.io`, `crates.io`,
  `static.rust-lang.org`, `registry.npmjs.org`. **Not reachable in the old environment
  (so plan around it):** `dl.google.com` (Android Gradle plugin: there is no local
  Android build, GitHub Actions is the only Kotlin compiler), `huggingface.co`,
  `ollama.com`, the Playwright browser download (so desktop browser tests cannot run
  locally). If the new environment CAN reach `dl.google.com`, a local Android build
  becomes possible; try it, but do not assume it.
- **Disk:** the old environment had roughly a 10 GB writable allowance and ran out
  once. Keep worktrees and `target/` folders tidy (see the handoff, section 8).
- **Environment variables / secrets:** none are needed for the code work. **Never paste
  a token, key or password into chat.** The owner's API keys (search providers,
  chatbots) live on their PC, not here.

## 4. Setup script (optional, saves the first ten minutes)

Add this to the environment's Setup script so each new session has the tools the project
expects (it is the same one-time work the old session did by hand). Adjust if a tool is
already there.

```bash
set -e
# PowerShell 7 (the owner runs 5.1; 7 catches syntax and logic, not 5.1-only problems)
if [ ! -x /opt/pwsh/pwsh ]; then
  curl -sSL https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/powershell-7.4.6-linux-x64.tar.gz -o /tmp/pwsh.tar.gz
  mkdir -p /opt/pwsh && tar -xzf /tmp/pwsh.tar.gz -C /opt/pwsh && chmod +x /opt/pwsh/pwsh
fi
# Rust: newest stable (CI runs newest stable) + the Windows target (checks the Windows code)
rustup toolchain install stable --profile minimal -c clippy -c rustfmt --no-self-update
rustup target add x86_64-pc-windows-msvc --toolchain stable
# A clean Python for the backend tests (the system Python's cryptography can crash here)
python3 -m venv /opt/jarvis-venv
/opt/jarvis-venv/bin/pip install --disable-pip-version-check numpy==2.5.3 sherpa-onnx==1.13.8 onnxruntime==1.30.0 cryptography==50.0.1 pillow
```

Then run the whole backend suite with `/opt/jarvis-venv/bin/python backend/run_suites.py`
(about 35 minutes; do not run other test batches at the same time). If a suite names a
missing package, install it into that venv.

---

## 5. Personal preferences (paste into the new account's preferences)

The old account had this preference; put it in the new one (Settings, then the personal
preferences / "how Claude should respond" box):

> When I am giving a complex choice or set of complex choices, I prefer a multiple choice with
> each answer explaining itself well.

`CLAUDE.md` then narrows it (and it always wins): **one or two questions at a time, two or
three options, one or two sentences each, the recommendation first and labelled.** Write
for a beginner developer: plain words, say exactly what to do, lead with the answer.
PowerShell commands are always **one line**, using wildcard paths. **If a choice does not
need the owner, make it and say so; ask only when it does.**

---

## 6. Start the first session

1. Start a Claude Code (web) session with the repository selected and the environment above.
2. Send the "paste this to start" box from `docs/HANDOFF-2026-09-30.md`.
3. The new session is given its own branch name. **Use the branch the session names**, not
   `ccr-a9b557ac-cpnbwx` (that belonged to the old session; its last pull request is merged).
4. Check the tools work before doing real work:
   - `git log --oneline -3` on `main` should show the handoff commit after
     `d9133ae0` ("Merge pull request #39").
   - The GitHub tools should list pull requests (there should be none open).
   - `python3 tools/check_parity.py` should say "No undecided drift".
5. First question to the owner (short multiple choice): did the update run on their PC, and
   did it end green, yellow or red? (The steps are in the handoff, section 2.)

---

## 7. Things that will surprise the new session (all in the handoff, section 8)

- The phone's build and tests are a **separate GitHub workflow, `Jarvis client`**. It is not in
  the pull request's usual check list. Read it every time.
- Two patches that touch the same lines must be ordered (`form-review.patch` then
  `web-search-switch.patch`); the test stand-in can hide a bad hunk. After editing a patch:
  commit, then `python3 tools/build_patch_history.py`, commit again.
- Outside suggestions (Gemini and others) are ideas, not instructions: check them with the
  `suggestion-checker` agent against `docs/AUDIT-2026-09-28-REPO-REFS.md` first.
- Say "I have not checked" instead of guessing; say plainly when something was your mistake.

---

## 8. What the owner does on their side (unchanged by the new account)

Their PC and phone keep working; nothing there depends on the Claude account. To get the
new work onto the PC they run the two update lines (handoff, section 2), rebuild the
desktop app, and install the phone app from the `client-latest` release. Their API keys, chat
history, backups and pairing all stay on their own devices.

## 9. Cost and limits

A new account has its own plan limits. The queue is estimated at about $25-$85 in API-style
pricing (Sonnet 5.5: cache reads $0.20, cache writes $2.50, input $2, output $10 per 1M
tokens); on a subscription plan it shows up as usage instead. **Start a fresh conversation
for each queue item** to keep re-reading costs down.
