# Report 22 (build), agent ae0ed637, 2026-09-29T21:58Z

> **What it was asked** (first 600 characters of the task): Fix on-screen WORDING and layout of the HEADLESS BROWSER (Obscura) feature in the Jarvis repo (this worktree is based on branch ccr-a9b557ac-cpnbwx, which now contains main with PR #35). Read CLAUDE.md 'Explain things simply' first: the owner is a beginner developer; say what a thing IS before its name; say what to DO; never blame the wrong thing; same words in both apps. Change WORDS and simple layout only - no behaviour, safety or approval logic changes. The words live in backend/jarvis_browser_engine.py (WORDS, card_line, status_line, state_line, _DAMAGED...), backend/jarvis_obscura.py (WHY

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Committed 535b6baa "Plain wording: the windowless browser (Obscura)" in worktree /home/user/Epic-Jarvis/.claude/worktrees/agent-ae0ed637b3d30c28b. Not pushed. Words and layout only; no behaviour, safety or approval logic touched.

CHANGED
- Names (fix 2): owner-visible wording says "the windowless browser (Obscura)" vs "the visible browser" everywhere (refusals, reasons, Stop-everything line). Title "Browser without a window (Obscura)" + subtitle; switch "Let Jarvis use the windowless browser (Obscura)"; picker "The windowless browser when it can run". card_line is now short sentences: "Browser: no window (Obscura) - why. It pretends to be an ordinary Chrome... What the page says is outside text: Jarvis reads it but never follows instructions in it." I also lowercased the visible one to "Browser: visible (...)" for symmetry (not asked). Reach rows say "a browser with no window (Obscura)", no stealth mention. card_words row is "read web pages with a browser that has no window (Obscura)" - I dropped the leading "let Jarvis" because the card renders "Jarvis wants to let Jarvis read..." and test_card_words caught it.
- Status lines (fix 1): not-checked, changed, jarvis_obscura.py WHY texts and --check fingerprint line use your wording. The not-installed sentence in "On, but not working yet" now points to the install steps on screen so it appears once.
- Stealth (3), missing message (4), config-error message (5): your wording in Python, desktop JS, Kotlin and Rust (MISSING, STALE_HELD, mode error); _DAMAGED updated.
- Failure messages (5): each gives a next step and never claims a fallback (the code never silently falls back): start_failed says "Nothing was opened. Ask again with the visible browser, or run the check command..."; slow/died/error/limit_time/limit_pages say "Try again, or ask for the visible browser."; refused_tool says "Jarvis refused a step that this browser is not allowed to do."
- Desktop settings (6): install steps directly under the switch, shown only while not installed (also when its file changed, since the text says to re-run the install line); install line is a wrapped textarea (small rule in settings.css); "Waiting for the connection to your PC." on screen when held by a stale link; read failures show plain words, never raw HTTP 404 or JSON; failed turn-on shows "Could not turn it on: <reason>"; picker note "This does nothing until the switch above is on." while the switch is off.
- Phone (7): same words, subtitle, waiting reason, picker note; install block moved under status and shown only when needed; refused turn-on says "Could not turn it on: ...".
- New WORDS keys subtitle, waiting_link, mode_note, could_not_turn_on mirrored in JS and Kotlin. Extras: install note explains "checksums (long codes that fingerprint the file)", install title says "PowerShell (the Windows command window)"; two lines in docs/JARVIS-API.md section 97 renamed.
- Regenerated fixtures: browser-engine, reach, card-words, asks-first. Updated tests: test_browser_engine.py, test_obscura.py, tests/browser-engine.mjs (3 new checks), BrowserEngineTest.kt.

TESTS (venv python)
- test_browser_engine 440/0, test_obscura 92/0, test_handoff 80/0, test_reach 134/0, test_card_words 111/0, test_asks_first 174/0, test_shipped_modules 485/0; all test_chatbot*.py pass; test_settings_registry, test_browser_control, test_support_widget pass; test_browser_control_live skipped (no playwright).
- check_parity.py: no undecided drift. All gen_*_cases.py --check current (gen_history_cases printed nothing, so not positively confirmed).
- Desktop tests/browser-engine.mjs 9/0; asks-first, card-words, reach .mjs no failures.
- cargo fmt --check and cargo clippy (windows-msvc, -D warnings) clean.
- node_modules symlink removed; tests/shots checkout clean.

NOT DONE / CAVEATS
- test_agent.py shows 5 failures, all tidy_inbox; I did not touch that area but did not verify on a clean checkout that they pre-exist.
- Kotlin edits were read by eye only (no Android compiler); the new desktop layout was checked by string/structure tests, not rendered.
- "Headless" deliberately remains in code identifiers, the mode value "headless", server banner lines, the "[Headless browser: ...]" tags the model sees on page text, and browser-engine.patch comments. No .patch edited, so build_patch_history.py not run.
