# Report 13 (audit), agent a7a64a50, 2026-09-29T20:49Z

> **What it was asked** (first 600 characters of the task): Bug-hunt the NEW code in PR #35, checked out read-only at /tmp/pr35 (compare with `git -C /tmp/pr35 diff origin/main...HEAD`; ignore docs/SOURCE-BUNDLE.md). New: backend/jarvis_obscura.py, backend/jarvis_browser_engine.py (headless Obscura browser driver: install/verify SHA-256, subprocess over stdin/stdout, click/URL/typed-value checks, idle/total timeouts, captcha/sign-in detection, kill switch), the reach/settings-registry/card-words changes, desktop browser-engine.js/browser_engine.rs/settings.html, phone BrowserEngine.kt/BrowserEnginePlate.kt/JarvisRuntime.kt. Focus: bypasses of the URL/c

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

PR #35 bug hunt (Obscura headless browser). I found one confirmed bypass and several smaller gaps. I changed no files.

I ran these scripts against /tmp/pr35: `backend/test_obscura.py` (92 pass) and my own probes using `_fake_obscura.py`. `test_browser_engine.py` would not run here because the `cryptography` library crashes on import. I read the Kotlin and Rust, nothing built. I also read Obscura's real source on GitHub `main` (`crates/obscura-mcp/src/lib.rs`, `obscura-ssrf`), and I downloaded and hashed the v0.2.3 release zip. Obscura's source came from `main`, which may not be exactly v0.2.3.

## Worst first

**1. A stray space in the action name skips the plan-time refusals (medium, proven by running).**
- `jarvis_browser_engine.py:472-475`: `reject_request` reads `action = str(r.get("action") or "")` with no `.strip()`.
- `jarvis_browser_control.py:1656`: `plan()` reads `action = str(r.get("action","")).strip()`.
- So `{"action":" navigate", "value":"https://a.test/?token=<JWT>"}` gets `None` from `reject_request`, but the plain `"navigate"` is refused. I ran it: `plan()` on the plain form gives 0 steps ("looks like a password, key or token"). The `" navigate"` form gives 1 step and the card shows the token.
- The same slip lets `" read_new"`, `" type"` and `" select"` past `reject_request`.
- The claim "REFUSED at plan time, before any card" (module docstring lines 34-43) is therefore false for these.
- Fix: strip the action in `reject_request`, or better, run the checks on the `Step` objects that `plan()` actually builds.

**2. `open()` has no secret check of its own, so #1 reaches the website (medium, proven by running).**
- `jarvis_browser_engine.py:1002-1014`: `open()` checks only `address_problem` and `_private_problem`. It never calls `_secret_kind`.
- `fill()` and `select()` do re-check at run time (lines 1213, 1227), so typed values are covered. URLs are not.
- I built a plan with `" navigate"` plus the JWT URL, ran it with `B.run(p, approved=True)` and got `ok=True`. Nothing refused the address after the card.
- The owner would see the token on the card. But the promise is that this is refused before any card.
- Fix: call `_secret_kind(url)` in `open()`, or fix #1.

**3. On a one-card PC the "sign-in words" test refuses ordinary reading (low-medium, proven by running).**
- `_choose` line 612 with `choose` line 573: with headless on and no visible browser, the goals "what is the best laptop to buy…", "summarise this article about pay rises" and a navigate to `stripe.com/docs/payments` all end in "This task needs the visible browser… Nothing was opened."
- The words `buy`, `pay` and `payments` match `_SIGN_WORDS`, and the navigate URL text is included.
- Only `mode:"headless"` gets past it. "Look up the weather" works.
- Effect: the headless option is much less useful on the owner's current 8 GB setup.
- Fix: match sign-in words in the goal only, not in URLs. Or, when visible is unavailable, let the headless engine run and rely on its own stop at captcha and sign-in pages.

**4. The install check is trust-on-first-use although the real hash is known (low, design).**
- `jarvis_obscura.py:146` `PINNED_DIGEST = ""`. `check()` (line 854) runs `obscura.exe --version` before any pin exists, then remembers whatever file it ran.
- Since the zip hash is pinned in the PR, the exe hash could be pinned too. From the release zip I computed `obscura.exe` = `b2fa7e453261c92c5124f8c77c2838eb4b6e74f6e6343a0c9e26b40016754bb6`.
- The zip also holds `obscura-worker.exe` (`c603fdd4ef5f02b4c2f177edc99e276b090c0693706c096e160a1de3c8ae7596`), which is never hashed by `problem()`.
- `digest_of` (line 302) caches by size and mtime, so a same-size swap that keeps the mtime would pass.
- All of these need a program already running as the owner. Fix: pin the exe digest, and hash the worker as well.

**5. A click can be guarded on the wrong element, and part of the fence is unverified (low, cannot prove).**
- `_guard_click` (lines 1120-1182) reads `href`, `formaction` and `form` only from the clicked element.
- I did not verify that a `<button>` or `[onclick]` child inside an `<a href="…other site…">` is caught. Obscura's `tool_click` calls `el.click()`, and whether the anchor's default action fires is unknown to me. Worth a test on the real binary via `tools/check_obscura.py`.
- Real `browser_detect_forms` does list `button` fields with `ref`, so the form-action check is sound.
- Real `browser_get_attribute` returns `""` for a missing attribute, and the code handles that correctly.

**6. A saved-fact leak through the URL path (low).**
- `jarvis_browser_engine.py:519`: `private_words_problem` compares saved facts only against the query and fragment.
- A path-style search (`…/search/<owner's street name>`) or a host that repeats a fact is not caught.
- The module docstring says "path, query and fragment" for the secret check only, so this is partly by design. Say it plainly on the card or extend the check.

**7. A process that dies mid-plan gives a silent empty read (low).**
- `read()` (lines 977-979) returns a blank page when the process is not alive.
- After the 10-minute limit, the 15-page limit or a crash, a later `read_page` step passes `_page_problem`. `_call` then starts a fresh blank process and returns empty text as a success, not a stop.
- Fix: make `read_page` fail when the process it planned against is gone.

**8. The redirect check fails open (low).**
- Line 1017: if the navigate reply does not match `_NAV_REPLY`, the fence check is skipped.
- The after-step check in `_run_steps` would still catch an out-of-fence page. But `run()` then leaves the process alive on that page until the 3-minute idle stop.
- Fix: call `self.driver.stop` when the run halts for a fence problem.

## Checked and fine

- **Obscura's private-network guard and env:** Obscura's own guard rejects private and CGNAT (Tailscale) IP ranges at DNS-resolve time (`obscura-net/client.rs` and `obscura-ssrf`). `OBSCURA_ALLOW_PRIVATE_NETWORK="0"` is safe, because only 1/true/yes/on enable it. `file://` is refused by Obscura.
- **Address tricks:** backslashes, control characters, `name@host`, `javascript:`, `data:`, `file:` and `https:evil.com` are all refused (I read the code and checked with `urljoin`).
- **Install line:** downloading `obscura-x86_64-windows-stealth.zip` from v0.2.3 gives SHA-256 `4d7311c6…6fb9`, which equals `RELEASE_ZIP_SHA256`. `obscura.exe` sits at the zip's top level, so `Expand-Archive` and `Get-FileHash` work. There is no zip-slip issue, because the zip's hash is pinned before it is unpacked.
- **Kill switch, timeouts, process tree:**
  - `set_obscura(False)` kills the process at once and outside the lock.
  - The start-gate stops later steps from restarting it.
  - The watchdog, idle limit and session limit work.
  - Windows `taskkill /T` and the Linux process group are used.
- **Card contents:** the plan card lists every step in full, plus the allowed sites, unmatched steps and a note when outside text was read.
- **Phone and desktop:** the words, modes and panel logic match the backend. The only difference is minor: the desktop mode dropdown stays enabled on a stale link and then shows the held message. No drift worth fixing.

Files:
- `/tmp/pr35/backend/jarvis_browser_engine.py`
- `/tmp/pr35/backend/jarvis_obscura.py`
- `/tmp/pr35/backend/jarvis_browser_control.py`
