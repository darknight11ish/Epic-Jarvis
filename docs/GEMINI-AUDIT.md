# Running an independent audit with Google Gemini

A second pair of eyes on this codebase, from a model that has not seen any of
it being written. That independence is the whole value, so the prompt below
is deliberately **blind**: it does not tell Gemini what a previous audit
found. An auditor handed a list of known bugs tends to confirm that list
rather than find the next one.

There is a cross-check prompt at the end for after the blind pass, if you
want the two audits compared.

---

## 1. Why four sessions rather than one

Everything here totals roughly 2.5 MB of source — about 600k tokens. Gemini
can hold that, but a model asked to audit four languages at once spreads
itself thin and returns shallower findings in every one of them. Four
focused sessions, each well inside the context limit, is the better trade:

| session | what | size |
|---|---|---|
| 1 | Desktop Rust (`src-tauri/src/*.rs`) | ~490 KB |
| 2 | Desktop frontend (`src/*.js`, `src/*.html`) | ~815 KB |
| 3 | Android Kotlin (`jarvis-client/.../*.kt` + manifest) | ~810 KB |
| 4 | Python backend (`backend/*.py`) | ~385 KB |

Session 3 is the one to run first if you only run one. That code has never
been compiled by anything — the Android app has no local build and CI is out
of minutes — so it is the only place where "does this even build?" is still
an open question.

---

## 2. Collecting the files

Each command below writes **one** `.txt` to your Desktop with every relevant
file concatenated and clearly delimited, ready to drag into Gemini. Run each
from the root of your checkout (the folder containing `jarvis-desktop`,
`backend` and `jarvis-client`).

One line each, as always.

**Session 1 — Rust:**

```
$o="$HOME\Desktop\jarvis-audit-1-rust.txt"; if(Test-Path $o){Remove-Item $o}; Get-ChildItem .\jarvis-desktop\src-tauri\src -Filter *.rs -Recurse | Sort-Object FullName | ForEach-Object { $p=$_.FullName.Replace("$($PWD.Path)\",""); Add-Content $o "`n`n===== FILE: $p =====`n"; Add-Content $o (Get-Content $_.FullName -Raw) }; Write-Host "Wrote $o"
```

**Session 2 — frontend:**

```
$o="$HOME\Desktop\jarvis-audit-2-frontend.txt"; if(Test-Path $o){Remove-Item $o}; Get-ChildItem .\jarvis-desktop\src\* -Include *.js,*.html -Recurse | Sort-Object FullName | ForEach-Object { $p=$_.FullName.Replace("$($PWD.Path)\",""); Add-Content $o "`n`n===== FILE: $p =====`n"; Add-Content $o (Get-Content $_.FullName -Raw) }; Write-Host "Wrote $o"
```

**Session 3 — Android** (run this one from the `claude/android-apk-build-q435fi`
branch, or from a checkout of it — that is where the Kotlin lives):

```
$o="$HOME\Desktop\jarvis-audit-3-android.txt"; if(Test-Path $o){Remove-Item $o}; Get-ChildItem .\jarvis-client\app\src\main\* -Include *.kt,*.xml -Recurse | Sort-Object FullName | ForEach-Object { $p=$_.FullName.Replace("$($PWD.Path)\",""); Add-Content $o "`n`n===== FILE: $p =====`n"; Add-Content $o (Get-Content $_.FullName -Raw) }; Write-Host "Wrote $o"
```

**Session 4 — Python:**

```
$o="$HOME\Desktop\jarvis-audit-4-python.txt"; if(Test-Path $o){Remove-Item $o}; Get-ChildItem .\backend\* -Include *.py -Recurse | Where-Object { $_.Name -notlike "test_*" } | Sort-Object FullName | ForEach-Object { $p=$_.FullName.Replace("$($PWD.Path)\",""); Add-Content $o "`n`n===== FILE: $p =====`n"; Add-Content $o (Get-Content $_.FullName -Raw) }; Write-Host "Wrote $o"
```

**Also attach to every session** (small, and they carry the rules the code is
supposed to obey — an auditor without them will miss every "the code
disagrees with its own contract" finding):

- `CLAUDE.md`
- `docs/ARCHITECTURE.md`
- `jarvis-desktop/src/jarvis-visual-spec.json` — only for sessions 1-3; its
  `limits.flash` block defines the photosensitivity bounds both renderers
  must honour.

---

## 3. The prompt

Paste this, with the session's `.txt` and the context files attached. Replace
the bracketed line with the one matching the session.

> You are auditing a personal AI-assistant project for **correctness bugs**.
> I wrote this with AI assistance and I want an independent, skeptical second
> opinion. Assume nothing has been reviewed.
>
> **What this project is.** A private assistant with three parts: a Windows
> desktop app (Rust/Tauri + an HTML/JS frontend), an Android companion app
> (Kotlin/Compose) that is a thin client to the desktop, and a Python backend
> that runs on the owner's own machine. The desktop and the phone cannot share
> drawing code, so they share DATA — `jarvis-visual-spec.json` — and each
> implements it separately. That split is where a lot of the risk lives.
>
> **[SESSION LINE — use one:]**
> - *Session 1:* You are looking at the desktop's Rust. It compiles clean
>   (`cargo check` and `cargo clippy -D warnings` against
>   `x86_64-pc-windows-msvc` both pass), so compile errors are already ruled
>   out — find LOGIC bugs.
> - *Session 2:* You are looking at the desktop's frontend. `faces.html` is a
>   ~5000-line inline script that renders twenty procedural animated "faces";
>   the rest is the app's real UI.
> - *Session 3:* You are looking at the Android app. **This code has never
>   been compiled by anything** — the project has no local Android build and
>   its CI is out of minutes. So your FIRST job is: would this actually
>   build? Unresolved imports, methods that do not exist at compileSdk 36 /
>   minSdk 33, wrong override signatures, Kotlin scoping errors, Compose
>   scope errors (`Modifier.weight` only resolves inside Row/ColumnScope;
>   Glance's `defaultWeight()` likewise), and manifest declarations that
>   Android would reject. Then logic bugs.
> - *Session 4:* You are looking at the Python backend. Note that three real
>   production modules (`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_memory.py`)
>   are NOT included — they live only on the owner's machine. Files under
>   `rebuilt/` are reconstructions of lost modules. Do not report the absence
>   of the missing modules as a bug.
>
> **Safety rules this code must obey.** Violations of these are the most
> serious findings you can make:
> 1. **No auto-approve, anywhere.** One action, one human decision. Nothing
>    may approve on the owner's behalf.
> 2. **Deny may be a notification/widget action. Approve may not** —
>    approving must mean opening the app.
> 3. **No client-side speech-to-text on the phone.** Audio goes to the
>    desktop to be transcribed there.
> 4. **Photosensitivity limits are hard limits** — see `limits.flash` in the
>    visual spec: max 3 opposing transitions per second per surface, minimum
>    0.10 relative-luminance swing to count as a transition, and a flicker
>    rate ceiling. Both renderers must enforce them.
> 5. **Nothing private leaves the machine** except on three named lanes.
>
> **How to work.**
> - Verify every claim against the actual code in the attached file. Never
>   report a bug you inferred without reading the real lines. Quote
>   `file:line` and the actual code for every finding.
> - Mark each finding **CONFIRMED** (you read it and the bug is definitely
>   there) or **SUSPECTED** (looks wrong but you are not certain of the API
>   or runtime behaviour). An honest "I am not sure this method exists" is
>   more useful to me than a confident guess. Do not pad the list.
> - Pay specific attention to **comments and docstrings that claim behaviour
>   the code does not implement.** This codebase is heavily commented and
>   those comments are treated as the contract, so a comment that lies is a
>   real defect, not a nit.
> - Look hard for: logic errors and wrong conditionals; state that never
>   updates or updates too late; race conditions and lifecycle bugs;
>   error handling that silently swallows real failures; resource leaks;
>   injection surfaces (shell, URL, SQL, XML); off-by-one; and data loss —
>   anything that can overwrite or discard the owner's own data.
> - **Do NOT report** style, naming, formatting, "could be more idiomatic",
>   missing tests, or performance micro-optimisation. Correctness only.
>
> **Output.** A ranked list, worst first, capped at your 15 strongest
> findings. For each: `file:line`, what is wrong, **what actually breaks for
> a user as a result**, and the minimal fix. A few sentences each — no
> essays. Then a short section listing anything you checked carefully and
> found sound, so it does not get re-audited later.

---

## 4. Optional: cross-checking against the audit already done

Run this **only after** the blind pass above has produced its own list.
Attach the same files plus Gemini's own findings and the other audit's.

> Here are two independent audits of the same code: your own, and one done
> earlier by a different model. Compare them.
>
> 1. Which findings do both agree on? Those are the highest-confidence bugs.
> 2. Which did the other audit find that you missed — and, reading the code
>    again now, do you agree it is real? Say plainly if you think it is
>    wrong, and why.
> 3. Which did you find that it missed?
> 4. Are any of either audit's findings actually **false** — a bug that is
>    not a bug, because the code is correct for a reason the auditor missed?
>    Be specific about the reason. Finding a false positive is as valuable
>    here as finding a real bug, because acting on a phantom bug costs real
>    changes to working code.
>
> Then give a single merged, de-duplicated, ranked fix list.

---

## 5. What to do with the results

Treat the output as a list of *claims*, not facts — the same way this
document treats the audit that preceded it. Before changing anything:

- Re-read the cited lines yourself. A model quoting `file:line` can still be
  quoting a line it reconstructed rather than read.
- Prefer findings where the auditor described a concrete failure a user
  would actually experience over ones that describe a theoretical smell.
- For anything in `faces.html` or `spec.rs` touching the flash governor,
  check the twin implementation too — the two ports are meant to be
  line-for-line equivalent, so a real bug in one is usually a bug in both,
  and a "fix" to one alone creates drift.
