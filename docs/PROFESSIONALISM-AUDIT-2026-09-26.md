# Professionalism audit - 26 September 2026

**The question:** does Jarvis look like something a professional team made
and packaged? That covers the installers, the version numbers, the READMEs,
the look and wording of both apps, the tidiness of the repository, and the
things a finished product usually has (an About box, a changelog, a way to
send a log).

**How it was checked:** by reading the real files on branch
`claude/admiring-ritchie-5urg5h` (commit `b21c34a`), running
`scripts/apply-patches.ps1` in PowerShell 7 against a fake backend folder,
running a spell checker (`codespell`) over the text both apps show, looking
at the committed screenshots, and asking GitHub which branches it holds.
Every finding below says where the evidence is. Nothing was changed except
this file, and nothing was committed.

---

## Summary

1. The engineering underneath is careful. The problems are mostly about **presentation**, and most of the fixes are small.
2. **The biggest one:** GitHub's `main` branch is 556 commits behind the branch you actually use. Anyone who opens the project on GitHub sees a version from two days ago.
3. **There is no desktop download.** Installing the desktop app means installing Visual Studio's build tools, Rust and Node, then building it yourself. One free signing key would fix that.
4. **No single version number.** The desktop says `0.1.x`, the phone always says `0.1`, and the backend has no version at all, so "which version are you on?" has no answer.
5. **The front page is out of date.** The README's feature list stops before voice on the PC, "Hey Jarvis", timers, briefings, web search, email and focus sessions, and it has no picture.
6. **Loose ends are visible:** the old phone app's README does not say it is old, there are six one-off test scripts in the desktop folder, about 100 MB of launch videos are committed on `main`, and internal session notes sit next to the owner's own guides in `docs/`.
7. **The wording is nearly consistent, but not quite:** some buttons are all lower case, three dots and "…" are mixed, dashes are mixed, "License" is spelled differently in different places, and the same screen is called "Brain" on the PC and "Mind" on the phone.
8. **Already professional:** no real typos were found, the icons match across both apps, error and crash screens use plain words, the phone release is signed and checked before it is published, and the patch script never leaves the backend half-patched.

---

## Ranked table

Size: **S** = under an hour, **M** = an afternoon, **L** = a day or more.
"Owner's call" = I would want your yes before doing it.

| # | What | Why it matters | Fix | Size | Owner's call? |
|---|---|---|---|---|---|
| 1 | GitHub `main` is 556 commits behind your working branch, and has 17 commits (the launch videos) the working branch lacks | The front door of the project shows old code and an old README | Open one pull request that brings `main` up to date, and decide what happens to the videos (#9) | M | Yes |
| 2 | No desktop installer to download. The updater's public key is empty, so the release job never publishes | Installing takes three big developer tools and a build. A finished product is one download | Make the free updater signing key once ("Turning on updates" in `jarvis-desktop/README.md`). CI then publishes a ready-made installer | S (your 10 minutes) | Yes: you keep the key |
| 3 | No shared version number across the desktop, the phone and the backend | Nobody can say which build they have, and a bug report cannot name one | Keep one `VERSION` file. Both apps show "0.2.0 (abc1234)" in About, and the patch script records which commit it applied | M | Yes: pick the first number |
| 4 | README feature list is out of date and has no screenshot | It is the first thing anyone reads | Rewrite "What it can do" in the same plain style, and add one picture of each app | S | No |
| 5 | Publisher, copyright and `LICENSE` all say "Jarvis Labs" | That name is invented, and a real company already trades as JarvisLabs.ai. Windows shows it as the publisher | Use your own name, or a name you choose, in all four places | S | Yes |
| 6 | Release notes: the phone's are very long and technical, neither says what changed, and neither gives a checksum | You cannot tell whether a build is worth installing, or check that the file is intact | Short notes: the list of changes since the last build, the install line, and a `SHA256SUMS.txt` file | S-M | No |
| 7 | No changelog | "What changed?" can only be answered by reading git history | Add a `CHANGELOG.md`, one line per merged piece of work, written in plain words | S, then ongoing | No |
| 8 | Phone About always says "Version 0.1". Both About boxes say only "MIT", but the phone app contains wake-word models under a non-commercial licence, and neither app lists the parts it is built from | Wrong or missing facts in the one place meant to state the facts | Show the full version and build. Say "MIT, plus third-party parts under their own licences" and add a "Third-party notices" link | S-M | No |
| 9 | About 100 MB of launch videos (three versions) are committed on `main` | Every copy of the repository downloads them for ever | Attach the videos to a GitHub Release, and keep only a link in the repository | M | Yes |
| 10 | The old phone app's README reads as if it were current | Someone could build and install the app that cannot talk to Jarvis | Add a "Legacy - kept for reference, cannot talk to Jarvis" banner at the top | S | No |
| 11 | `docs/` has 53 files. Internal session notes and a stale 720 KB source snapshot sit next to your guides, with no index | Hard to find the five documents that matter | Add `docs/README.md` as an index, and move old notes to `docs/archive/` | M | Yes: moving files breaks old links |
| 12 | Six unused test scripts (`perfprobe*.mjs`) at the top of `jarvis-desktop/`, and the legacy `server/` folder, which the README's folder table does not list | Loose ends a reviewer notices at once | Delete the probes. Label or remove `server/` | S | Yes, for `server/` |
| 13 | The patch script keeps no log file, does not say which version it is, and has your personal folder built in as the default | "Send the block above back" means copying from the terminal. And a stranger's PC gets a path that means nothing to them | Save a log file next to the backup, print a first line naming the commit, and write a small "installed from commit X" file | S | No |
| 14 | Wording is not quite consistent: lower-case buttons (including "ask jarvis about this"), "..." mixed with "…", mixed dashes, "License" and "licence" | Small things, but together they make the apps look unfinished | One wording pass, following the rules already in `card-words.js` | S | No |
| 15 | "Brain" on the PC is "Mind" on the phone, and the phone has no screen called "Settings" | The same place has two names, and the help text has to explain both | Pick one name. On the phone, gather the settings under one "Settings" heading | M | Yes |
| 16 | The installer's description is out of date and full of jargon ("glassmorphic", "LiteLLM"), and CI builds two kinds of installer | This text appears in Windows' "Apps" list and in the installer | Rewrite it in one plain sentence, and build only the `-setup.exe` that INSTALL.md tells you to use | S | No |
| 17 | `npm run test:all` runs 36 of the 70 desktop test suites (CI runs all 70) | A green result on your PC promises more than it checked | Make `test:all` run every file, the way CI does | S | No |
| 18 | The committed screenshots are three days old and show approval cards that have since been fixed | They would be the obvious pictures for the README | Take new screenshots before using them anywhere | S | No |
| 19 | Only the Rust code has a formatter and a lint check. The JavaScript, Python and Kotlin have none, and there is no `.editorconfig` | Style drifts from file to file, which reviewers notice | Add Prettier, Ruff and the full Android lint as CI warnings first | M | No |
| 20 | 18 branches on GitHub (9 already merged) and 67 on this machine | Clutter on the GitHub page | Delete the merged branches on GitHub | S | Yes |
| 21 | No README for `jarvis-client`, the phone app you actually use | The old app has a README and the real one does not | A short one: what it is, how to install it, where its settings are | S | No |
| 22 | No single "something went wrong - what to send" page | The logs, the phone's crash copy and the patch script's output are each explained in a different place | One short section in INSTALL.md that lists all three | S | No |

---

## 1. Packaging and install

**1.1 The desktop installer (`jarvis-desktop/src-tauri/tauri.conf.json`)**

- Name, version and identifier: `"productName": "Jarvis Desktop"`,
  `"version": "0.1.0"`, `"identifier": "com.jarvis.desktop"` (lines 3-5).
- Publisher: `"publisher": "Jarvis Labs"` and `"copyright": "Copyright (c)
  2026 Jarvis Labs"`. The same name is in `Cargo.toml`
  (`authors = ["Jarvis Labs"]`) and in `LICENSE` line 3. JarvisLabs.ai is a
  real GPU-cloud company. I know that from memory and did not look it up
  today. Either way, the name is not yours → table #5.
- Descriptions: `"shortDescription": "Native Windows 11 spotlight client for
  the Jarvis stack."` and a long description that promises "an Alt+Space
  glassmorphic quickbar ... live health checks against the local Jarvis,
  Ollama and LiteLLM services". LiteLLM (a go-between for cloud models) is
  not mentioned in `README.md`, `docs/INSTALL.md` or `docs/ARCHITECTURE.md`,
  but it does have a status dot of its own on the quick bar
  (`src/index.html:657`) → table #16.
- Icons: `icon.ico` holds 7 sizes (16, 24, 32, 48, 64, 128 and 256 pixels),
  checked by reading the file. Good.
- Installer targets: `"targets": ["msi", "nsis"]`. `docs/INSTALL.md` §2.1
  says "Use the NSIS one", and the release job uploads both. Offering one
  would remove a choice a beginner cannot make.
- Updater: `"pubkey": ""` (line 117). `desktop-release.yml` checks for this
  and publishes nothing without it ("The TAURI_SIGNING_PRIVATE_KEY secret is
  not set, so this build is unsigned and nothing is published"). So
  `docs/INSTALL.md:265` is accurate: "there is no download yet" → table #2.
  Unsigned installers are kept as CI run artifacts for 14 days, but they
  need a GitHub login to download and are mentioned nowhere in INSTALL.md.
- Windows code signing ("Authenticode", the check behind the SmartScreen
  warning): not done, and INSTALL.md §2.2 explains why and how to get past
  it. That is honest and correct. It is not in the table, because fixing it
  costs money.
- The identifier `com.jarvis.desktop` (and `com.jarvis.client` on the phone)
  follows the usual naming pattern, but with a web address (`jarvis.com`)
  you do not own. **Recommendation: leave both alone.** Changing them makes
  Windows treat the app as a new one, with a new settings folder, and on the
  phone it means uninstalling and pairing again. Written down only so that
  it is a known choice.

**1.2 The Android app (`jarvis-client/app/build.gradle.kts`)**

- `applicationId = "com.jarvis.client"` (line 54). The app is called
  `Jarvis` (`strings.xml`).
- `versionName = "0.1"` (line 64) never changes. `versionCode` is the CI run
  number (lines 37-39), which is the right way to stop an older build
  installing over a newer one. But Android's app info and the phone's own
  About (`FaqScreen.kt:390`,
  `AboutFact("Version", BuildConfig.VERSION_NAME)`) show "0.1" for every
  build. The build's commit is shown only under Platform checks
  (`ReadinessScreen.kt:932`) → table #3 and #8.
- Launcher icon: an adaptive icon with a separate monochrome layer for
  Android 13's themed icons (`mipmap-anydpi-v26/ic_launcher.xml`), plus a
  notification icon (`drawable/ic_notification.xml`). Good.
  `docs/launcher-icon-preview.png` shows it under every mask shape, and it
  matches the desktop icon.
- Splash screen: none set up (`themes.xml`), so Android shows the icon on
  black, which suits the app. Not a problem.

**1.3 Release jobs (`.github/workflows/`)**

- File names do not follow one pattern. The desktop installer is
  `jarvis-desktop_${VERSION}_x64-setup.exe` (named by version,
  `desktop-release.yml`). The phone APK is `jarvis-client-$short.apk` (named
  by commit, `jarvis-client.yml:969`). Keep the phone's commit in its name:
  `net/UpdateCheck.kt` reads it to spot a newer build. A version could be
  added in front of it.
- Checksums: neither release publishes a SHA-256 of the file. The phone
  notes give the *signing certificate's* fingerprint (line 1009),
  which proves who signed the app, not that the download is complete
  → table #6.
- Phone release notes (`jarvis-client.yml:979-1013`): about 40 lines, with
  jargon ("SSE on `/api/events`"), internal names ("security audit H1"), and
  a "What changed about these builds" section that describes one fix from
  weeks ago and is repeated on every build. There is no list of what
  changed in *this* build. The desktop notes (`desktop-release.yml`) are
  short and plain, which is the better model.

**1.4 `scripts/apply-patches.ps1`**

Run here against a fake backend folder. Its output is clear and calm, and
it ends with `NOTHING HAS BEEN CHANGED.` when it refuses. The exit codes are
right: `exit 1` on each refusal, `exit 0` when there is nothing left to do.
It says which files are missing and prints the exact command to find them.
That is professional. Gaps:

- It saves no log. When tests fail it says
  `Send the block above back. A failing suite here is a real finding.`
  (line 1562). Nothing is saved to a file, so the owner has to scroll and
  copy. PowerShell's `Start-Transcript` can save the whole run in one line
  → table #13.
- No first line says which version of the patches is being applied (no
  commit or date), and nothing on the PC records it afterwards.
- The default folder is the owner's own path:
  `[string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"`
  (line 72). It is fine for you, but odd to anyone else.

**1.5 Versions across the three parts**

| part | where the number comes from | what you see |
|---|---|---|
| Desktop | `0.1.0` in `tauri.conf.json`, `package.json` and `Cargo.toml`. CI replaces the last part with its run number | `0.1.<run>` from CI. A copy built on your PC always says `0.1.0`, with no commit |
| Phone | `versionName = "0.1"`, and `versionCode` = the phone job's run number | always "0.1" |
| Backend | none. It answers with a list of what it can do (`GET /api/version`, `capabilities`) | nothing |

Checking what the backend can do, instead of reading a version number, is
the right way for the apps to talk to each other (`docs/JARVIS-API.md`
§6). But people need a number too, for bug reports and for "am I up to
date?" → table #3.

---

## 2. First impressions

**2.1 `README.md`**

It is short, plain and honest, and says clearly what Jarvis is, which
matters most. What is missing or out of date:

- "What it can do" says "**Take voice**, by push-to-talk on the phone"
  (line 34). Hands-free "Hey Jarvis" is now built on the phone
  (`strings.xml`: "Listening for \"hey Jarvis\"") and there is voice on the
  PC (`src-tauri/src/voice.rs`). Timers and reminders, the morning briefing,
  web search, sending email, focus sessions and "Stop everything" are not
  mentioned.
- There is no screenshot or picture anywhere in README.md, INSTALL.md or
  `jarvis-desktop/README.md` (a search for `.png` and "screenshot" finds
  none).
- The "Layout" table leaves out `server/` and `tools/tool_eval/`.
- "20 face designs" is correct (`jarvis-visual-spec.json` has 20 `faces`).

**2.2 Module READMEs**

- `jarvis-android/README.md` begins "# Jarvis Mobile / Native Android
  companion for a self-hosted Jarvis desktop server". It says nowhere that
  the app is legacy or cannot talk to Jarvis (a search for legacy,
  reference, older and deprecated finds nothing relevant). `CLAUDE.md`
  tells readers to "See the module's own README", and the README does not
  deliver → table #10.
- `server/README.md` *does* open with "Legacy - not used by Jarvis". Good,
  but the top-level README never mentions the folder.
- `jarvis-client/` has no README → table #21.

**2.3 `docs/`**

53 entries and no index. Beside the owner's guides (ARCHITECTURE, INSTALL,
JARVIS-API, MODEL-TOPOLOGY) are working notes between sessions:
`HANDOFF.md` ("Everything a new session needs to pick this up"),
`ASK-GEMINI.md`, six `ANDROID-REPLY-*`/`CROSS-CLIENT-CONTRACT-REPLY*`
files, and `SOURCE-BUNDLE.md` (720 KB, "every source file, in one document"
at an old commit on a deleted branch), which is out of date by design. The
dated audits are useful history, but they belong in an archive folder.
INSTALL.md's "Known rough edges" section keeps fixed items struck through
("~~No autostart.~~ Fixed."), which reads as a to-do list rather than a
guide → table #11.

**2.4 Leftovers in shipped code**

- `TODO`/`FIXME`/`XXX`/`HACK` in the code that ships: **one**, in
  `JarvisTheme.kt:223` ("TODO: the product's own face is IBM Plex Sans ...
  not bundled here"). The phone uses the system font while the desktop uses
  IBM Plex, so the two apps' text looks slightly different.
- Debug output: none in the desktop's JavaScript (`console.log`: 0). The
  Rust `println!` lines go to the log file (`logfile.rs`). Three `Log.d`
  lines on the phone, which is harmless.
- Commented-out code: none found (searched for commented `val`, `fun`,
  `let`, `const` and `return` lines).
- Test leftovers: `jarvis-desktop/perfprobe.mjs` to `perfprobe6.mjs` (342
  lines, last changed 2026-09-14). Nothing refers to them → table #12.

**2.5 Naming**

- "Jarvis" is spelled the same everywhere users can see: no "JARVIS" or
  "jarvis" in on-screen text, **except** the desktop HUD's button
  `ask jarvis about this` (`jarvis_hud.html:632`).
- Window titles vary: "Jarvis — Brain", "Jarvis HUD", "Jarvis Faces",
  "Jarvis Widget", "Jarvis Desktop — Settings", "Jarvis — Welcome"
  (`src/*.html` `<title>`).
- Brain and Mind: the tray says "Open the Brain" (`tray.rs:241`). The phone
  says "Mind" (`HomeScreen.kt:1269`, `BrainScreen.kt:242`
  `TopBar("Mind", ..., subtitle = "State of mind")`). The phone's error text
  has to say both: "(Models, in the Brain on the PC or in Mind on the
  phone)" (`PlainErrors.kt:127`).
- Settings: the desktop has one Settings window with named sections. The
  phone has no "Settings". Its settings are spread over Mind (web search,
  briefing, manner, hardware and more), Appearance, Security and Platform
  checks. The phone's own pairing hint still says "On the PC: Settings, Show
  the token for my phone" (`PairingScreen.kt:167`) → table #15.

---

## 3. UI polish

**Checked:** a spell check of both apps' source and text, the wording of
buttons and placeholders, the committed screenshots, and the accessibility
basics.

- **Typos: none real.** `codespell` found only variable names
  (`HomeState`, `OptIn`) and deliberate words ("rime", "trough").
- **Capitalisation.** Settings, Brain and the phone use sentence case
  ("Open the log folder"). The HUD and the Faces window use all lower case:
  `reset view`, `pause spin`, `clear`, `ask jarvis about this`
  (`jarvis_hud.html:608-632`) and `randomise`, `reset all`, `save`,
  `use this face` (`faces.html:144-171`). Neither button style changes the
  case (checked in their CSS). Placeholders are mixed too:
  "search the brain…" (`jarvis_hud.html:607`) against "Search the graph…"
  (`brain.html:182`).
- **Three dots.** "…" is used 133 times in the desktop and 121 times on the
  phone. Four loading messages on the phone use "...": "Comparing on your
  PC..." (`VoiceTrainingScreen.kt:368`), "Asking your PC..."
  (`VoicesScreen.kt:150`, `VoiceCheckScreen.kt:484`), and "Checking on your
  PC..." (`VoiceCheckScreen.kt:362`).
- **Dashes.** Both " - " and " — " appear in on-screen sentences (phone: 58
  and 14. Desktop JavaScript: 61 and 17. Desktop pages: 9 and 11). The same
  sentence differs between the apps: "no licence stated — no permission to
  use it" (`brain.js:4444`) against "no licence stated - no permission to
  use it" (`Watch.kt:161`).
- **British or American spelling.** On screen it is mostly British
  (colour, licence, cancelled), but both About boxes say "License"
  (`settings.html:1259`, `FaqScreen.kt:391`), while the README says
  "Licence".
- **Approval cards.** `card-words.js` now makes every screen say "Needs your
  OK" and put Deny on the left. If the backend sends no short summary,
  though, both apps fall back to showing the raw data:
  `JSON.stringify(detail)` (`widget.js:598`, `main.js:1213`). I did not
  check how often the backend leaves that summary out.
- **Screenshots** (`jarvis-desktop/tests/shots/`, last committed
  2026-09-23): they still show the old cards ("APPROVAL REQUIRED", the code
  name `switch_model`, Approve on the left in the widget), which
  `card-words.js` says were fixed on 2026-09-25 → table #18.
- **Empty, loading and error states:** there is a plain-words error module
  on both sides (`src/plain-errors.js`, `net/PlainErrors.kt`), each status
  line is marked for screen readers (`role="status"` in `settings.html`),
  and the phone has a crash screen that works even if the theme is what
  broke (`CrashScreen.kt`).
- **Accessibility:** the desktop has tests for it (`tests/a11y.mjs`,
  `contrast.mjs`, `disabled.mjs`, `themes-all.mjs`). On the phone, every
  tappable item goes through `Modifier.pressable`, which tells screen
  readers it is a button (`Parts.kt:86`), and there are no images without
  a description. The phone has no automated contrast test like the
  desktop's.

---

## 4. Code-base hygiene

- **Licence:** `LICENSE` (MIT) is there, and so is `THIRD-PARTY-NOTICES.txt`
  (35 KB). The notices list the desktop's Rust libraries and name the
  wake-word models' non-commercial licence clearly. They leave out the
  phone's libraries (AndroidX, Compose, OkHttp, kotlinx and ONNX Runtime,
  from `app/build.gradle.kts:258-332`), and the phone app has no screen
  that lists them. The fonts' licence is shipped as `src/fonts/OFL.txt`
  but is not listed in the notices → table #8.
- **CONTRIBUTING, SECURITY and CHANGELOG:** none exist. CONTRIBUTING is not
  needed for a project with one owner. If the repository is public, a
  three-line `SECURITY.md` ("report privately to ...") is normal practice.
- **Formatting and lint:** CI runs `cargo fmt --check` and `cargo clippy`
  for Rust only (`ci.yml:32-33`). For the JavaScript it checks only that
  each file parses (`node --check`). Python has nothing, and Kotlin gets
  only the basic lint check that every release build runs. There is no
  `.editorconfig` → table #19.
- **Very large files:** `brain.js` (5711 lines), `commands.rs` (5334),
  `main.js` (4305), `Faces.kt` (4309), `jarvis_agent.py` (4037) and
  `JarvisRuntime.kt` (3818). Not urgent, but reviewers read file size as a
  sign of health. `backend/` holds 260 files in one folder, with patches,
  modules and tests side by side.
- **Repository size:** 77 MB packed. The biggest file on this branch is an
  8 MB ONNX model that the app needs. On `main`: `videos/v1`, `v2` and `v3`
  add about 99 MB of MP4 files (35 MB, 37 MB, 20 MB and 7 MB) plus music
  tracks → table #9.
- **`.gitignore` gaps:** `.claude/worktrees` is ignored only by this
  machine's own `.git/info/exclude`, not by `.gitignore`. The CI-made
  `jarvis-desktop/dist/` and `release.conf.json` are not ignored.
- **Branches:** GitHub holds 18 branches (`git ls-remote --heads origin`).
  9 are already merged into the working branch. There are 67 local
  branches. GitHub's `main` is `d5fa76b` (2026-09-24), which is **556
  commits behind** `claude/admiring-ritchie-5urg5h` and 17 commits ahead of
  it (the launch videos, a README rewrite and one docs fix)
  → table #1 and #20.
- **The old app:** `jarvis-android/` is labelled in the top-level README
  and in `CLAUDE.md`, but not in its own README (§2.2).
  `scripts/recover_from_claude_export.py` and `get-export.ps1` are internal
  tools with no label. `npm run test:all` (`package.json:31`) names 36
  suites; CI runs all 70 (`ci.yml:69-80`) → table #17.

---

## 5. "And more": what a professional team would add

- **About box:** the desktop has one (`settings.html:1243`: version,
  licence, source) and so does the phone (`FaqScreen.kt:373`). Missing: the
  build's commit on the desktop, a real version on the phone, and a link to
  the third-party notices.
- **Changelog:** none → table #7.
- **Logs you can send:** the desktop is good. Settings → Startup and logs →
  "Open the log folder", with a warning that the files are not redacted
  (`commands.rs:4586-4589`). The phone has "Copy" on its crash screen, and
  `CrashLog.kt` records the version. The patch script saves nothing. The
  three are not described together anywhere → table #13 and #22.
- **Uninstall instructions:** they exist (`docs/INSTALL.md:718`) and cover
  the leftover token and folders. Missing: the plain first step (Windows
  Settings → Apps → Jarvis Desktop → Uninstall), removing the phone app,
  and `apply-patches.ps1 -Revert` for the backend.
- **Support path:** for one owner it is "send the log to the Claude
  session". Writing that down in one place (table #22) is enough. No
  telemetry and no outside service is needed or suggested.

---

## Already good

- The installer is per-user with no admin prompt, the icon has 7 sizes,
  and the app has adaptive and themed icons plus a notification icon. The
  desktop and phone icons match.
- The phone release is signed with the project key, checked against it,
  and started on an emulator before it is published. Every GitHub Action
  is pinned to an exact commit (a fixed version that cannot change under
  you).
- `apply-patches.ps1` rehearses on a copy first, backs files up, says
  "NOTHING HAS BEEN CHANGED" when it refuses, and prints the exact next
  command.
- No real typos. "Jarvis" is spelled the same everywhere users see it,
  apart from one HUD button. There is one TODO in the shipped code and no
  commented-out code.
- Plain-words error messages on both sides, a crash screen on the phone,
  and log files on the desktop. INSTALL.md explains SmartScreen honestly.
- Accessibility and contrast tests on the desktop. Buttons on the phone are
  announced as buttons.
- `LICENSE` and a detailed `THIRD-PARTY-NOTICES.txt`, including the
  wake-word models' non-commercial licence, which is the reason for rule 5.
- The top-level README is short and plain, and states the five rules up
  front.

## Not checked

The phone on a real device (no phone screenshots are committed), how often
the backend omits card summaries, whether the repository is public, and the
installer on Windows itself.
