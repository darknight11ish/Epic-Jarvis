# Final report: the pasted repo list and the four proposed modules

**Short answer.** About half of the pasted list was right. The rest was only partly true, wrong, or out of date. All four modules are worth building, and none of them lets anything act without your approval card. But two of them (skills and MCP) each have a real hole that must be fixed first. I found those holes by running the code, not just by reading it. Nothing has run on Windows yet. Nobody has seen your real `jarvis_gate.py` either, because it is not in the repo, so every design guesses its answer fields from `backend/gate-outcome.patch:67-87`.

Nothing in `/home/user/Epic-Jarvis` was changed. All design files are in `/tmp/claude-0/research/out/`.

---

## 1. Was the pasted list right?

| Repo | Claim | Verdict | Why (evidence) |
|---|---|---|---|
| open-jarvis/OpenJarvis | Exists, Apache-2.0 | **True** | `LICENSE:1`; clone HEAD e86c582 |
| | "5 primitives" | **True** | `docs/index.md:116-124`. It describes how the code is organised. There is nothing to copy. |
| | agentskills.io skills, import from OpenClaw/Hermes | **True** | `skills/parser.py:31-34`; `skills/sources/hermes.py:22`, `openclaw.py:23` |
| | CodeAct agent | **True** | `agents/native_openhands.py:380-398`. It runs the model's Python **without asking you** (no `requires_confirmation`). On Windows the resource limits are skipped (`tools/code_interpreter.py:185-186`). |
| | Persistent multi-turn orchestration | **Partly** | `orchestrator` is not persistent. `operative.py:1-37` and `manager.py:60,387` are. |
| | Background schedulers (morning_digest, scheduled-monitor) | **Partly** | The scheduler is real (`scheduler/scheduler.py:28-29`). "scheduled-monitor" is only a config file (`configs/.../scheduled-monitor.toml`), not an agent. |
| | Per-query GPU energy profiling | **True** | `telemetry/energy_nvidia.py:111,126` |
| | Secret redactor for logs and telemetry | **Partly** | Logs: yes (`security/credential_stripper.py:6-25`). Telemetry stores no text, so there is nothing to redact (`telemetry/store.py:19-70`). |
| isair/jarvis | Exists | **True, but** | Its licence is non-commercial and share-alike. Epic-Jarvis is MIT, so **we cannot copy its code**. Ideas only. |
| | On-device voice assistant | **True** | `README.md:7,24`. It is built mainly for macOS (`README.md:124`). |
| | SQLite diary and memory graph | **True** | `memory/db.py:32-94`. The graph is written with no review step (`graph_ops.py:836`). The viewer has no login (`memory_viewer.py:271-397`). |
| | "MCP router" | **Partly** | It picks up to 5 tools per request (`tools/selection.py:268-269,363`). It is not a router. |
| | Push-to-talk dictation | **True** | `dictation/dictation_engine.py:36-42,143-190` |
| KillianLucas/open-interpreter | Repo location | **Moved / changed** | The old URL still clones. But `main` is now a Rust fork of OpenAI's Codex (`README.md:52`, `NOTICE:1-2`). The Python program is on branch `main-backup` and is **AGPL**. I could not confirm a move to an "OpenInterpreter" organisation. |
| | Sandboxed code loop with "self-healing" | **Partly** | The Python version is **not** sandboxed: plain `Popen` (`subprocess_language.py:44-60`). "Self-healing" just means errors are shown back to the model. |
| | Process-group isolation | **Partly** | Only in the new Rust code (`codex-rs/windows-sandbox-rs/src/process.rs:10,105`) |
| | "01" device protocol | **Partly** | Old Python branch only (`core/async_core.py:437-470`). No use to us. |
| all-hands-ai/OpenHands | Repo location | **Moved** | Now `OpenHands/OpenHands`, which is an Electron front end. The agent code moved to `OpenHands/software-agent-sdk` (MIT). |
| | Event stream (action/observation log) | **True** | In the SDK: `conversation/event_store.py:34-48` |
| | AST-aware patching | **False** | `str_replace` is plain text replacement (`file_editor/editor.py:178-195`). tree-sitter is used only to parse bash commands. |
| microsoft/UFO | Exists, MIT | **True** | We already rebuilt the useful part as `backend/jarvis_ui_control.py` |
| | UI Automation tree | **True** | `automator/ui_control/inspector.py:174-200` |
| | Breaks goals into Win32 steps | **Partly** | It splits goals into per-app sub-tasks. Worse: **the model decides when to ask you** (`app_agent.yaml:36-49`). |
| OpenVoiceOS/ovos-core | Exists, Apache-2.0 | **True** | HEAD f3d08e9 |
| | Wake word, VAD, speech-to-text, intent pipeline | **Partly** | Only the intent step is in this repo (`intent_services/service.py:203`) |
| | Sandboxed skills | **Partly** | Skills load in the same process, with no sandbox. It even installs pip packages when a message on its bus asks it to (`skill_installer.py:44-47,110`). |

---

## 2. The four modules (approve by number)

Every module follows the one approval model: plan, show the card, `jarvis_gate`, run. None of them has an "approve all" button, and none lets the model pick its own risk level. That is true of all four designs as written, and I checked it in the code.

### Module 1: Log scrubber (`jarvis_scrub.py`). Effort **S**
**What it does for you:** it removes passwords, API keys and your pairing token from `backend.log` and from error messages before they are written to disk. That matters because you paste those files into bug reports.

**Safe as designed?** Yes. It never uses the network and never runs code. It only reads your token file so that it can hide the token. 95 of its 95 tests pass.

**Change first:**
- **A key block with no end marker silences the log.** I printed one line containing `-----BEGIN PRIVATE KEY-----` with no matching end line. Every line after it disappeared from the log (`_emit`, `jarvis_scrub.py:551-575`). Cap how many lines it hides.
- **Loggers created too early are not covered.** A Python logger set up before the scrubber starts still wrote an OpenAI key in clear text; I tested this. Also re-point any existing logging handlers when the scrubber starts. (No logger shows up in the backend files in this repo, so this risk is low.)
- **Leave the audit log alone for now** (call site 5). `rebuilt/jarvis_framework.py:416-420` records a decision not to put a redactor there. Changing that is your call.

**Two real bugs it found, which I confirmed. Fix them either way:**
- The router's secret detector misses `sk-ant-`, `sk-proj-` and `github_pat_` keys (`backend/rebuilt/jarvis_router.py:113,115`). Your real copy may differ.
- The Joplin token can end up in an error message if `JARVIS_JOPLIN_URL` has no `http://` in front (`jarvis_notes.py:243,296`). I reproduced the `ValueError` with the token in it.

### Module 2: Skills that run a script (`jarvis_skill_tools.py`). Effort **M/L**
**What it does for you:** a skill can include one small Python script. Each time it runs, you see the whole script and its exact input, and you say yes or no. Secrets are removed from the script's environment, and it runs from a checked private copy. 111 of its 111 tests pass. It is named differently from your existing `jarvis_skills.py` on purpose, so it does not overwrite it.

**Safe as designed?** It always asks you. But three weaknesses need fixing first, because the card can tell you something false:
- **The code-reader can be fooled.** If a skill contains a file named `subprocess.py` or `socket.py` in *any* sub-folder, then `import subprocess` or `import socket` becomes invisible. I ran `detect_effects` on exactly that: it found **nothing**, so the card would say "calculation only" (`jarvis_skill_tools.py:190,222`). An outside skill could slip past the "no network for outside code" rule this way. **Fix:** treat only files in the entry script's own folder as the skill's modules, and refuse any skill file named like a standard Python module.
- **"Private data plus network is always refused" only works if the skill admits it reads private data.** The code-reader never detects private data (it appears only at `:112,:635,:661`). A script reading `memory.db` shows up only as "reads files".
- **Trust is looked up by the skill's name alone** (`:683-694`). If another skill that is allowed to write files changes a skill you wrote, the changed skill keeps your "local" trust. **Fix:** record the files' fingerprints when you approve the install, and tie trust to those fingerprints.

**Smaller fixes:**
- A result that read files should switch on the "has read something private" latch.
- If the gate's answer has no outcome, the module assumes "approved" (`:1068`). Require the approval ID instead.
- Setting a skill action to `"never"` does nothing until `jarvis_gate` knows the action names. Until then those calls fall into `unclassified_tool` (`jarvis_agent.py:376-380`). It still asks, so it fails safe.
- **The two `jarvis_agent.py` patches clash.** I applied the skills diff first; the MCP patch then failed its second part. They need to be merged into one patch.

### Module 3: MCP bridge (`jarvis_mcp.py`). Effort **L**
**What it does for you:** it lets Jarvis use tools from local "MCP servers". Those are helper programs you install, such as a file-browsing server.
- Only servers you list are ever started, and starting one needs your approval.
- By default, every tool call gets its own approval card.
- A tool is shown to the model only while its fingerprint matches the one you pinned in config.
- Tool results are cleaned, and "act now / ignore your instructions" text is flagged.
- When a server is stopped, everything it started is killed too.

123 of its 123 tests pass. It was also checked against a real server built with the official SDK.

**Safe as designed?** Not yet. Three problems:
- **It never checks the "has read something private" latch.** Searching `jarvis_mcp.py` for "taint" finds nothing. If you let a harmless-looking tool skip the card (its `below_ask_ok` list) and set its tier to `auto`, then a tool like `search(q)` could send email text to an outside program with nobody asked. **Fix:** always ask while that latch is on, and switch the latch on after every MCP result.
- **It reads the server's "may reach the internet" flag the wrong way round.** When a server says nothing, the bridge assumes "no internet", but the MCP spec says the default is "yes" (`mcp-spec 2025-11-25/schema.mdx:1229`). Treat "says nothing" as "yes".
- **Your config can hand your pairing token to a server.** A line like `X = "env:HUD_TOKEN"` is accepted (`jarvis_mcp.py:338-346`). Block `HUD_TOKEN` and Jarvis's other secrets.

**Also know this:**
- A running MCP server is an ordinary program under your Windows account. It can read your files and use the internet on its own, whatever the approval cards say. Only list servers you trust.
- None of the Windows parts have run on Windows yet: the job object (what kills the server's child processes), Credential Manager, and `.cmd` servers.
- Servers that only speak the newest MCP version (2026-07-28) will not connect (`changelog.mdx:14`).

### Module 4: Tighten the existing approval gate (from `gate/REVIEW.md`). Effort **S/M**
**What it does for you:** it closes gaps that already exist in Jarvis today. Every change only makes things stricter.

**Must do (4a is the most important item in this whole report):**
- **4a. Check whether OpenJarvis's auto-approve code is on your PC.** Current OpenJarvis approves tools automatically in 7 places; I confirmed all 7 lines, for example `server/agent_manager_routes.py:1030` and `cli/ask.py:422`. `jarvis ask` also has `--yes` switched on by default (`cli/agent_cmd.py:816-821`). If your backend ever reaches that code, those tool calls skip `jarvis_gate`. Paste this into PowerShell. It changes nothing on your PC:
  ```
  $d = [Environment]::GetFolderPath('Desktop'); $p = python -c "import openjarvis,os;print(os.path.dirname(openjarvis.__file__))" 2>$null; if (-not $p) { Write-Host 'OpenJarvis is not importable from this Python, so there is nothing to check' } else { Get-ChildItem -Path $p -Recurse -Filter *.py | Select-String -Pattern 'confirm_callback\W{0,3}\s*=\s*lambda[^:]*:\s*True' | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" } | Out-File -Encoding utf8 (Join-Path $d 'openjarvis-autoapprove.txt'); Write-Host "Saved to $d\openjarvis-autoapprove.txt (an empty file means none were found)" }
  ```
  The result lands on your Desktop as `openjarvis-autoapprove.txt`. I changed one thing from the reviewer's version: it now finds your real Desktop even if OneDrive has moved it. I tested this command in PowerShell 7 against the OpenJarvis copy here, and it found all 7 lines. I have not tested it on your 5.1.
- **4b. Stop approved shell commands from seeing your keys.** Right now they inherit every setting, including `JARVIS_GITHUB_TOKEN` and `HUD_TOKEN` (`jarvis_agent.py:180-182`, no `env=`). Pass only a short list of safe settings.
- **4c. Check that a person actually said yes.** `jarvis_agent.py:771` only checks `allowed`, which is also true when nobody was asked (`ARCHITECTURE.md:98`). For tools that run code, require tier "ask" and outcome "approved".

**Nice to have:**
- A tool's output can switch the "private" latch on.
- An outside tool cannot borrow a built-in tool's name.
- A limit on how many approval cards one turn can raise.

---

## 3. Not recommended, and why

- **OpenJarvis CodeAct and its code interpreter.** They run code the model wrote without asking you, with no limits on Windows (`code_interpreter.py:185-186`). That breaks "nothing runs code without passing the gate".
- **Every auto-approve path:** OpenJarvis's 7 callbacks and `--yes`, Open Interpreter's `auto_run` and `-y`, approving by typing "yes" in chat, and remembered "always approve". Each one breaks "no auto-approve".
- **UFO's confirmations.** The model decides when to ask you (`app_agent.yaml:36-49`). That is the model choosing its own risk level.
- **Scheduled agents such as `morning_digest`.** Nobody is there to approve, and it reads your email (`agents/morning_digest.py:104-110`).
- **Downloading skills from OpenClaw or Hermes.** That is new internet access plus untrusted text going to the model. Using the SKILL.md *format* is fine.
- **isair's memory graph and viewer.** It writes memory with no review, its viewer has no login, and the licence forbids copying. The viewer *design* is worth studying for the memory review pane.
- **isair's dictation (typing into other windows).** It is a new kind of action, and it overwrites your clipboard. It would need its own design and approval step first.
- **Old Python Open Interpreter.** It is AGPL (cannot be copied into MIT), it is not sandboxed, and its only sandbox runs in the cloud (`e2b.py`), which breaks local-only.
- **The "01" protocol and duplex audio streaming.** The phone already uses `JARVIS-API.md`, and streaming was deliberately not ported.
- **OVOS's pip-install-over-message-bus and OpenJarvis's crypto-mining add-on** (`src/openjarvis/mining/`). Do not copy either.
- **"AST-aware patching".** It does not exist in the named code (`editor.py:178-195`).
- **Replacing Jarvis's per-destination redaction with one shared redactor.** Module 1 adds to the existing redaction and replaces nothing, and that is how it should stay.

Per-query GPU energy numbers (OpenJarvis telemetry) are harmless but low value on one PC. That can wait.

**What I could not check:**
- Nothing has been run on Windows.
- The real `jarvis_gate.py`, `jarvis_hud.py` and `jarvis_skills.py` are not in the repo.
- Whether OpenJarvis's auto-approve code is on your PC. Command 4a answers that one.

**Suggested order:** 4a, then 4b and 4c, then 1, then 2 and 3 after their must-fix lists are done.
