# Stream F — upstream dependency drift

**Audited:** clean `main` worktree at `.dsh-scratch/audit-main`, commit `fa2b379f`.
**Date of every upstream lookup: 2026-10-07.**
**Read-only on product code.** Nothing in the worktree was modified.

**What this answers:** the owner asked whether the GitHub repos Jarvis was built
from, and the other programs and libraries it integrates with, have moved on
since the versions this repository pins or assumes.

**How the versions were read.** `Invoke-RestMethod`/`curl` from PowerShell to
PyPI and crates.io fail in this sandbox (TLS refused), and `pip-audit` cannot run
(piped child stdio is blocked). Every lookup below therefore came from one of:

| Source | URL shape | Used for |
|---|---|---|
| PyPI JSON API | `https://pypi.org/pypi/<name>/json` | the 85 Python packages |
| crates.io API | `https://crates.io/api/v1/crates/<name>` | the Rust crates |
| GitHub REST (`gh api`) | `https://api.github.com/repos/<owner>/<repo>[/releases/latest]` | CI actions, external programs, whether a repo is archived/dormant |
| Google Maven metadata | `https://dl.google.com/dl/android/maven2/<path>/maven-metadata.xml` | androidx, AGP |
| Maven Central metadata | `https://repo1.maven.org/maven2/<path>/maven-metadata.xml` | OkHttp, Okio, ZXing, ONNX Runtime, kotlinx, Kotlin plugins |
| npm registry | `https://registry.npmjs.org/<pkg>/latest` | gsap, `@tauri-apps/cli` |
| Gradle | `https://services.gradle.org/versions/current` | the Gradle wrapper |
| OSV | `POST https://api.osv.dev/v1/query` | advisories against the exact pinned Python versions |
| Ollama library | `https://ollama.com/library/<model>/tags` | whether the pinned model tags still exist |

**Clickable examples of each source, so every row's citation can be followed:**
[PyPI — numpy](https://pypi.org/pypi/numpy/json) ·
[PyPI — cryptography](https://pypi.org/pypi/cryptography/json) ·
[crates.io — tauri](https://crates.io/api/v1/crates/tauri) ·
[GitHub — ollama releases](https://api.github.com/repos/ollama/ollama/releases/latest) ·
[GitHub — obscura releases](https://api.github.com/repos/h4ckf0r0day/obscura/releases) ·
[GitHub — ChatVRM (archived)](https://api.github.com/repos/pixiv/ChatVRM) ·
[Google Maven — AGP](https://dl.google.com/dl/android/maven2/com/android/tools/build/gradle/maven-metadata.xml) ·
[Google Maven — Compose BOM](https://dl.google.com/dl/android/maven2/androidx/compose/compose-bom/maven-metadata.xml) ·
[Maven Central — OkHttp](https://repo1.maven.org/maven2/com/squareup/okhttp3/okhttp/maven-metadata.xml) ·
[Maven Central — ONNX Runtime Android](https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/maven-metadata.xml) ·
[npm — gsap](https://registry.npmjs.org/gsap/latest) ·
[Gradle current](https://services.gradle.org/versions/current) ·
[OSV API](https://api.osv.dev/v1/query) ·
[Ollama — qwen3 tags](https://ollama.com/library/qwen3/tags).
Substitute the dependency's own name into the same shape for any row whose exact URL
is not spelled out — every number in this report came from one of these.

**Totals: 178 items checked with a live upstream lookup, 70 behind.**

- Python packages: 78 pinned in `backend/requirements.lock` + 7 optional extras = 85 checked, **18 behind**
- Rust crates: 25 declared in `Cargo.toml` + 3 notable transitive = 28 checked (the lock holds 666 crates.io entries), **20 behind**
- GitHub Actions: 9 checked, **7 behind**
- Android / Gradle / npm: 23 checked, **20 behind**
- External programs, model files and borrowed-code upstreams: 33 checked, **5 behind, plus 6 dormant or archived**

**"70 behind" is not "70 problems".** A large share of those are pins this
project made *on purpose* and documents as such — `onnxruntime-android` (avoiding a
telemetry provider), the Compose BOM (avoids `minCompileSdk 37`), `tauri-plugin-window-state`
(Rust 1.89 MSRV), `rustls`→`native-tls`, `screenshots`→`xcap`. Only the items in
the Findings section below are drift the project does not appear to have chosen.

---

## Table 1 — Python packages (`backend/requirements.lock`)

All 78 packages pinned in the lock were checked against PyPI. Only the ones that
are **behind** are listed; the rest are in "checked and already current" below.
(Pinned value = `backend/requirements.lock`; current = `https://pypi.org/pypi/<name>/json` → `info.version`.)

| Dependency | Used for | Pinned | Current | Behind | Matters? | Action |
|---|---|---|---|---|---|---|
| `cryptography` | encrypting every kept chat on the PC | 50.0.1 | **50.0.2** | 1 patch | Low. Not a security release — wheels rebuilt against OpenSSL 4.0.3, free-threaded 3.15 wheels, PyO3 0.29.2 fix | None now; take it at the next lock refresh |
| `fastembed` | fact search by meaning + the re-ranker | 0.8.0 | **0.8.1** | 1 patch | Low–medium: it downloads two models on first use, so a surprise change is user-visible | Test the re-ranker on a copy before moving |
| `huggingface-hub` | pulled in by fastembed | 1.32.0 | **2.1.1** | major | Medium. A major bump under fastembed — do **not** bump alone | Keep the lock's transitive pin |
| `magika` | file-type detection under MarkItDown | 0.6.3 | **1.0.3** | major | Medium. MarkItDown 0.1.8 requires `magika~=0.6.1`, so 1.x is out of range for the pinned MarkItDown | Do not bump in isolation |
| `mammoth` | MarkItDown's Word reader | 1.11.0 | **1.13.0** | 2 minors | Medium. MarkItDown pins `mammoth~=1.11.0` — same reasoning as magika | Do not bump in isolation |
| `onnx` | the one-off mouth-timing model build | 1.23.0 | **1.23.2** | 1 patch | Low | None |
| `pypdfium2` | MarkItDown's PDF rendering | 5.13.0 | **5.14.0** | 1 minor | Low | None |
| `hf-xet` | Hugging Face transfer acceleration | 1.6.0 | **1.7.0** | 1 minor | Low | None |
| `comtypes` | `uiautomation`'s COM layer | 1.4.16 | **1.4.17** | 1 patch | Low | None |
| `tzdata` | calendar time zones | 2026.4 | **2026.5** | 1 | Low but real: tzdata carries IANA rule changes | Safe; data only |
| `pytz` | pulled in by pandas | 2026.3.post1 | **2026.5** | 2 | Low | None |
| `filelock` | pulled in by fastembed/huggingface-hub | 4.0.0 | **4.0.12** | 12 patches | Low | None |
| `soupsieve` | CSS selectors for BeautifulSoup | 2.9.2 | **2.10** | 1 | Low | None |
| `mpmath` | pulled in by sympy | 1.3.0 | **1.4.1** | 1 minor | Low | None |
| `charset-normalizer` | requests' decoder | 3.5.1 | **3.5.2** | 1 patch | Low | None |
| `mmh3` | pulled in by ddgs | 5.3.0 | **5.3.1** | 1 patch | Low | None |
| `python-dotenv` | Marks: env loading in the backend | 1.2.3 | **1.2.4** | 1 patch | Low | None |
| `torch` (optional, **not** in the lock) | the better voice / F5-TTS worker | 2.14.0 | **2.14.1** | 1 patch | Low | None |

**Advisories (independent check, not a guess).** All 78 pinned versions were
queried against OSV at their **exact** version —
`POST https://api.osv.dev/v1/query` with
`{"package":{"name":"<name>","ecosystem":"PyPI"},"version":"<pinned>"}`.
**Zero advisories returned for any of them.** PyPI's own `vulnerabilities` array
(in the same `/pypi/<name>/json` payload) was also empty for all 78. Two control
queries with deliberately wrong versions (`aiohttp 0.0.0`, `lxml-html-clean 0.0.1`)
returned dozens of hits, so the query path was working.

Note the project already has this covered twice over: `tools/check_python_advisories.py`
(reads `https://pypi.org/pypi/<name>/<version>/json`) runs in CI at
`.github/workflows/ci.yml:1198`, and `cargo deny check licenses advisories sources`
runs at `.github/workflows/ci.yml:1072`. So Python/Rust advisories are *already*
gated — this finding is confirmation, not a new hole.

---

## Table 2 — Rust crates (`jarvis-desktop/src-tauri/Cargo.lock`)

Pinned = the version resolved in `Cargo.lock`; current =
`https://crates.io/api/v1/crates/<name>` → `crate.max_stable_version`.
Only the 25 crates **declared** in `Cargo.toml` plus three notable transitive ones.

| Dependency | Used for | Pinned | Current | Behind | Matters? | Action |
|---|---|---|---|---|---|---|
| `tauri` | the desktop shell | 2.11.6 | **2.12.1** | 1 minor | Medium — see **F5** | Take with the plugin set, in one bump |
| `tauri-build` | build script | 2.6.3 | **2.7.1** | 1 minor | Low | Same bump as `tauri` |
| `tauri-plugin-window-state` | window size/position memory | 2.4.1 | **2.5.0** | 1 minor | **Deliberate.** `Cargo.toml:38` pins `=2.4.1` because 2.5.0 needs Rust 1.90 and the crate is `rust-version = "1.89"` | Leave, or raise the MSRV first |
| `tauri-plugin-updater` | the in-app updater | 2.11.0 | **2.13.1** | 2 minors | Medium — the updater is a security surface | Bump, then re-run `tests/updater-manifest.mjs` |
| `tauri-plugin-notification` | toasts | 2.4.0 | **2.5.1** | 1 minor | Low | None |
| `tauri-plugin-store` | settings persistence | 2.4.4 | **2.5.0** | 1 minor | Low | None |
| `tauri-plugin-single-instance` | second launch focuses the first | 2.4.4 | **2.5.2** | 1 minor | Low | None |
| `tauri-plugin-clipboard-manager` | clipboard | 2.3.3 | **2.4.1** | 1 minor | Low | None |
| `tauri-plugin-global-shortcut` | hotkeys | 2.3.2 | **2.4.0** | 1 minor | Low | None |
| `window-vibrancy` | acrylic/mica | 0.6.0 | **0.8.1** | 2 minors | Medium — `Cargo.toml:39-43` explains 0.6 was chosen so Tauri 2.11.5's own 0.6.0 is not duplicated. A jump to 0.8 duplicates it again | Leave until Tauri itself moves |
| `reqwest` | HTTP to the backend | 0.12.28 | **0.13.5** | major | **Deliberate-ish.** `Cargo.toml:58-63` picks `native-tls` over rustls on purpose. 0.13 is a major with a different TLS feature story | Leave; revisit with F5 |
| `tokio` | async runtime | 1.53.1 | **1.53.2** | 1 patch | Low | None |
| `sysinfo` | CPU/RAM telemetry panel | 0.32.1 | **0.39.6** | 7 minors | Medium: 0.33 removed/changed several APIs | Only with a code change |
| `cpal` | microphone capture for push-to-talk | 0.15.3 | **0.18.2** | 3 minors | Medium: WASAPI backend changed across these | Only with a device test |
| `base64` | encoding | 0.22.1 | **0.23.1** | major | Low (API is small) | None now |
| `windows-sys` | Win32 bindings | 0.59.0 | **0.61.2** | 2 | Low — `Cargo.toml:87` deliberately picks 0.59 so Tauri's graph is not duplicated | Leave |
| `windows` | WinRT toasts, Hello, WASAPI AEC | 0.61.3 | **0.62.2** | 1 | Low–medium | Leave; the feature list is large |
| `windows-future` | the `IAsyncOperation` type for Hello | 0.2.1 | 0.100.0¹ | n/a | Low — pinned to match the `windows` crate's own copy (`Cargo.toml:171-176`) | Leave |
| `libc` | Unix process groups | 0.2.189 | **0.2.190** | 1 patch | Low | None |
| `wry` (transitive) | the webview | 0.55.1 | **0.57.0** | 2 | Follows Tauri | — |
| `tao` (transitive) | windowing | 0.35.3 | **0.37.1** | 2 | Follows Tauri | — |
| `quick-xml` (transitive) | XML | 0.42.0 | 0.42.0 | — | Current. `Cargo.toml:53-57` records that **xcap replaced `screenshots` specifically to drop two CVSS 7.5 quick-xml DoS advisories** | — |
| `native-tls`, `ring` (transitive) | TLS | 0.2.18 / 0.17.14 | same | — | Current | — |

¹ crates.io's `max_stable_version` for `windows-future` is `0.100.0`, a different
versioning line from the `windows` crate this project uses. Not a real gap.

**Current:** `image` 0.25.10, `serde` 1.0.229, `serde_json` 1.0.151, `xcap` 0.9.8,
`hound` 3.5.1, `qrcodegen` 1.8.0.

---

## Table 3 — GitHub Actions (`.github/workflows/*.yml`)

Every `uses:` is pinned to a full commit SHA with the tag in a comment. Current =
`https://api.github.com/repos/<owner>/<repo>/releases/latest`.

| Action | Pinned tag | Current | Behind | Matters? |
|---|---|---|---|---|
| `actions/checkout` | v5.0.1 | **v7.0.1** | 2 majors | Low risk, and this is the one action that runs with a token in every job |
| `actions/upload-artifact` | v6.0.0 | **v7.0.1** | 1 major | Low |
| `actions/download-artifact` | v7.0.0 | **v8.0.1** | 1 major | Low |
| `actions/setup-node` | v5.0.0 | **v7.0.0** | 2 majors | Low |
| `actions/setup-python` | v6.0.0 | **v7.0.0** | 1 major | Low |
| `actions/setup-java` | v5.0.0 | **v6.0.1** | 1 major | Low |
| `taiki-e/install-action` | v2.87.20 | **v2.87.26** | 6 patches | Low (installs `cargo-deny`) |
| `android-actions/setup-android` | v4.0.4 | v4.0.4 | — | Current |
| `Swatinem/rust-cache` | v2.9.2 | v2.9.2 | — | Current |
| `dtolnay/rust-toolchain` | `@6bed0761…` "stable branch" | floating by design | n/a | It tracks stable on purpose |

`.github/workflows/verify-toolchain.yml` exists exactly to resolve these tags to
SHAs on a runner, so a tag-rewrite cannot silently change what CI runs. That is
the right shape; the drift above is only *age*, not exposure.

*(`dtolnay/rust-toolchain` is listed last for completeness and is **not** counted
in the "9 checked / 7 behind" — it is pinned to a branch commit on purpose, so
there is no release to compare against.)*

---

## Table 4 — Android, Gradle and npm

Pinned = the manifest (`jarvis-client/app/build.gradle.kts`,
`jarvis-client/build.gradle.kts`, `gradle/wrapper/gradle-wrapper.properties`,
`videos/*/composition/package.json`, `jarvis-desktop/package.json`).
Current = Google Maven / Maven Central `maven-metadata.xml`, **latest stable**
(alpha/beta/rc excluded — see the note under the table).

| Dependency | Used for | Pinned | Current stable | Behind | Matters? |
|---|---|---|---|---|---|
| `com.android.tools.build:gradle` (AGP) | Android build | 9.4.0 | **9.4.1** | 1 patch | Low |
| `androidx.compose:compose-bom` | Compose versions | 2026.06.00 | **2026.09.00** | 3 | Medium — but **deliberate**: `build.gradle.kts:272-284` shows 1.12.x needs `minCompileSdk 37` and the brief forbids compiling against 37 (Beta) |
| `androidx.core:core-ktx` | Android core | 1.15.0 | **1.19.1** | 4 minors | Low–medium |
| `androidx.activity:activity-compose` | `enableEdgeToEdge` | 1.12.4 | **1.13.0** | 1 minor | Deliberate (chosen contemporaneous with Compose 1.11.3) |
| `androidx.lifecycle:*` | lifecycle | 2.8.7 | **2.11.0** | 3 minors | Low–medium |
| `androidx.glance:glance-appwidget` | home-screen widget | 1.1.1 | **1.2.0** | 1 minor | Deliberate: 1.1.1 is the only version with a precedent in this monorepo |
| `androidx.fragment:fragment` | raises biometric's floor | 1.3.0 | **1.9.1** | 6 minors | **Only a floor** — Gradle takes the highest anyway |
| `androidx.camera:*` | QR pairing scan | 1.4.2 | **1.6.2** | 2 minors | Low–medium |
| `androidx.test.*` | instrumented tests | 1.2.1 / 1.6.2 / 1.6.1 | **1.3.0 / 1.7.0 / 1.7.0** | 1 each | Low (test-only) |
| `com.squareup.okhttp3:okhttp` | the transport (SSE, streaming) | 4.12.0 | **5.5.0** | major | Medium — 5.x is a real migration (and `mockwebserver` must move with it) |
| `com.squareup.okio:okio` | OkHttp's IO | 3.6.0 | **3.18.2** | 12 minors | Low |
| `com.google.zxing:core` | QR decoding | 3.5.3 | **3.5.4** | 1 patch | Low |
| `com.microsoft.onnxruntime:onnxruntime-android` | "hey Jarvis" spotter | 1.22.0 | **1.30.0** | 8 minors | **Deliberate and important.** `build.gradle.kts:349-358` records that 1.30.0's manifest adds INTERNET, ACCESS_NETWORK_STATE and a launch-time telemetry provider — a phone-home this app must not carry |
| `kotlinx-serialization-json` | event models | 1.7.3 | **1.11.0** | 4 minors | Low–medium |
| `kotlinx-coroutines-android` | coroutines | 1.9.0 | **1.11.0** | 2 minors | Low–medium |
| `androidx.biometric:biometric` | fingerprint gate | 1.1.0 | 1.1.0 | — | Current (latest stable) |
| Kotlin compose plugin | `plugin.compose` | 2.4.20 | 2.4.20 | — | Current |
| Kotlin serialization plugin | `plugin.serialization` | 2.4.20 | 2.4.20 | — | Current |
| Gradle wrapper | the build tool | 9.6.0 | **9.8.0** | 2 minors | Low. `distributionSha256Sum` is pinned, which is the important part |
| `gsap` (videos v1–v6) | launch-video animation | ^3.14.2 | **3.15.0** | 1 minor | Cosmetic. **Note:** the brief expected **Remotion** — `grep -i remotion` over the whole worktree returns **nothing**. The videos are hand-written compositions using gsap only |
| `@tauri-apps/cli` | `tauri dev`/`build` | `^2.1.0` (2.11.5 installed) | **2.12.1** | 1 minor | Low |

*Note on "latest stable":* the newest published version of most androidx
artifacts is an alpha (e.g. activity-compose 1.14.0-alpha03, biometric
1.4.0-alpha07). This table deliberately compares against the newest **stable**
release so nothing looks "behind" merely because an alpha exists.

---

## Table 5 — External programs, model files and borrowed code

Current = the upstream release page / repo metadata from
`https://api.github.com/repos/<owner>/<repo>`. "Pinned" is where the repository
records it.

| Program / model | Used for | Pinned in the repo | Current upstream | Behind | Matters? | Action |
|---|---|---|---|---|---|---|
| **Ollama** | runs the everyday model | research read at commit `b2da9e4` (2026-09-23) = ~v0.34.4 — `docs/HARDWARE-PROFILES.md:103` | **v0.40.0** (tag list + `/releases/latest`) | ~6 releases | **Yes — see F3** | Re-read the four source claims before trusting the VRAM numbers |
| **llama.cpp** | the engine inside Ollama | `b11081` (2026-09-21) = `161755f` — `docs/HARDWARE-PROFILES.md:104` | build **`b11460`** (2026-10-07); also now has semver tags up to `v0.6.0` | ~379 builds | **Yes — see F3** | Same |
| **colibri** (`JustVugg/colibri`) | the very large model engine | none — `docs/BIG-MODEL.md:71` tells the owner to download "the newest release" | **v2.0.0** (2026-10-06), repo active | n/a by design | Medium: the docs' model table and RAM figures were written against an older release | Re-read `BIG-MODEL.md`'s numbers against the v2.0.0 notes |
| **Obscura** (`h4ckf0r0day/obscura`) | the headless "windowless" browser | **`RELEASE_TAG = "v0.2.3"`** — `backend/jarvis_obscura.py:137` | **v0.2.4** (2026-10-04) | 1 minor, **212 commits** | **Yes — see F2** | Bump the tag + hash, or at minimum fix the stale "newest release" comment |
| **SearXNG** (`searxng/searxng`) | the **default** web-search provider | `docker.io/searxng/searxng:latest` — `backend/README.md:10057` | no GitHub releases; continuous rolling | unbounded | **Yes — see F4** | Pin a digest or a dated tag |
| `sherpa-onnx` (k2-fsa) | STT, TTS, voice print | 1.13.8 (`requirements.txt` + `requirements.lock`) | **v1.13.8** | — | Current | — |
| Silero VAD | "have they stopped talking?" | v6.2.3 | **v6.2.3** | — | Current | — |
| `py-fsrs` (open-spaced-repetition) | review decks | 6.3.2 | **v6.3.2** | — | Current | — |
| `ddgs` (deedy5) | DuckDuckGo search | 9.16.0 | **v9.16.0** | — | Current | — |
| `markitdown` (Microsoft) | PDF/Word/Excel/PowerPoint reading | 0.1.8 | **v0.1.8 / 0.1.8** | — | Current | — |
| `youtube-transcript-api` (jdepoix) | caption text | 1.2.4 | **v1.2.4** | — | Current | — |
| ONNX Runtime (Microsoft) | spotter + Smart Turn | 1.30.0 (Python) | **v1.30.0** | — | Current | — |
| `playwright-python` | browser control + chatbot windows | 1.63.0 | **v1.63.0** | — | Current | — |
| F5-TTS (SWivid) | the better custom voice | 1.1.22 | **1.1.22** | — | Current (optional) | — |
| Pocket TTS (kyutai-labs) | bake-off candidate voice | not pinned | **v3.3.0** (2026-09-24), active | n/a | Low (candidate only) | — |
| `livekit-wakeword` (LiveKit) | trains a "hey Jarvis" detector | commit `95448a75` (2026-08-01) | HEAD `fb92cb36` (2026-09-30) | **2 commits** | Low | Effectively current |
| `openWakeWord` (dscripka) | the `hey_jarvis` model on both apps | models **v0.5.1** | models v0.5.1 (newest model release); library release v0.6.0 | — | **Repo dormant since 2025-12-30** | Watch it; nothing to do now |
| Smart Turn (pipecat-ai) | "finished or only paused?" | v3.2 model | no releases; last push **2026-01-29** | — | **Dormant ~8 months** | Watch it |
| `sqlite-vec` (asg017) | the memory vector index | 0.1.9 | **v0.1.9** | — | Current version, but **last push 2026-05-18** — quiet | Watch it |
| Kokoro (hexgrad) | the voice pack | `kokoro-multi-lang-v1_0`, 350 MB, **sha256-pinned** | repo last push **2025-08-06** (~14 months) | — | Low: the *model file* is hash-pinned, so drift cannot happen silently | Watch the repo; the pin is the protection |
| `browser-use` | page reading adapted into `jarvis_browser_control.py` | v0.13.10 (notices) | **0.13.11** (2026-10-07) | 1 patch | Low — adapted code, not a dependency | None |
| Handy (cjpais) | talk-to-type paste logic adapted | **no version recorded**, "read 2026-09-28" | **v0.9.8** (2026-10-03) | unrecorded | Low–medium: see F6 | Record the commit that was read |
| Spring-It-On (orangeduck) | animal motion logic, MIT | no version | last push **2026-03-23**, no releases | — | Low — a demo repo; already adapted | None |
| TalkingHead (met4citizen) | animal motion + HeadTTS | no version | **v1.7.0**, active (push 2026-09-25) | — | Low | None |
| airi (moeru-ai) | animal motion | no version | **v0.12.0-beta.5**, active | — | Low | None |
| ChatVRM (pixiv) | animal motion | no version | **ARCHIVED**, last push 2025-05-27 | — | See F7 | None (MIT, already adapted) |
| leon (leon-ai) | "offers nobody asked for" idea | no version | active, no releases | — | Low | None |
| gitleaks / Presidio | secret rules / scrubbing ideas | ideas only, not shipped | v8.30.1 / 2.2.364 | — | Low | None |
| Inter / Fraunces fonts | launch videos | bundled, OFL-1.1 | v4.1 / 1.000 | — | Low — bundled and subset | None |
| `pymicro-wakeword` | second "both detectors agree" wake word | **2.5.0, sha256-pinned** | 2.5.0 | — | Current | — |
| Everything (`es.exe`, voidtools) | **not** integrated (feasibility I39) | — | — | — | Not a dependency; `jarvis_tool_updates.py:76-81` says so correctly | — |

**Model files still exist?** `qwen3:8b` (the base of `jarvis-primary`) — **yes**,
`https://ollama.com/library/qwen3/tags` lists `8b` and `8b-q4_K_M`/`8b-q8_0`/`8b-fp16`.
`qwen3.5:9b` (the second-card candidate) — **yes**, `9b` and its quants are listed.
**`minicpm-v:4.6` — no. See F1.**

**How Jarvis tracks this itself.** `backend/jarvis_tool_updates.py` has a
`GITHUB_TOOLS` registry that is **empty by design** (line 216), with a written
reason for each candidate: Everything is not actually integrated; colibri always
installs "the newest release" so there is no pin to compare; livekit-wakeword is
pinned to a commit, which `/releases/latest` cannot honestly compare. That
reasoning is sound — but it means the *only* things that check itself covers are
`requirements.lock` (PyPI) and `rust-crates.lock` (crates.io). **Everything in
Table 5 is outside that check**, which is why F1–F4 were not caught.

---

# Findings

### F1. `minicpm-v:4.6` does not exist — picture mode's install line cannot work

**Confidence: high (two independent URLs read).**

`backend/jarvis_screen_picture.py:136` sets `DEFAULT_MODEL = "minicpm-v:4.6"`, and
the on-screen install line the owner is told to paste is
`ollama pull 'minicpm-v:4.6'; …` (`tools/gen_screen_cases.py:132`, asserted by
`backend/test_screen_picture.py:1314`).

- **404:** [ollama.com/library/minicpm-v:4.6](https://ollama.com/library/minicpm-v:4.6).
- **No `4.6` tag:** [ollama.com/library/minicpm-v/tags](https://ollama.com/library/minicpm-v/tags)
  → the `minicpm-v` model's tags are `latest, 8b, 8b-2.6-q2_K … 8b-2.6-fp16`.
- The model does exist, under a **different name:**
  [ollama.com/library/minicpm-v4.6](https://ollama.com/library/minicpm-v4.6)
  → HTTP 200, "MiniCPM-V 4.6", vision, 1b, **1.6 GB**, 256K context, `ollama run minicpm-v4.6`.
  The [search page](https://ollama.com/search?q=minicpm) also lists
  [openbmb/minicpm-v4.6](https://ollama.com/library/openbmb/minicpm-v4.6) as a second, namespaced copy.

So the owner pasting the line the app shows gets "model not found", and the
feature's own "not installed yet" wording will keep appearing. The doc comment in
the same file (`jarvis_screen_picture.py:78`) already quotes llama.cpp as having
`docs/multimodal/minicpmv4.6.md`, so the model name was known — the Ollama *tag*
is what was guessed.

**What the update buys:** picture mode's install actually completing.
**What it risks:** the model is 1.6 GB and the file also carries a hash-pinned
`PINNED_DIGEST = ""` (trust-on-first-use) — see `docs/DEEP-AUDITS-2026-10-05.md:89`.
Changing the name is a one-line change plus regenerating the fixtures; the
measurement step (`--measure`) then has to be re-run, because the current
"measured" numbers, if any, are for a model that was never installed.
**Suggested action:** change the default and the generated line to
`minicpm-v4.6`, re-run `tools/gen_screen_cases.py`, and re-measure.

### F2. Obscura is a patch behind, and the code comment now says something untrue

**Confidence: high.**

`backend/jarvis_obscura.py:133-137` says, in as many words:

> The release the install line downloads: v0.2.3, **the newest release** on
> https://github.com/h4ckf0r0day/obscura/releases (dated 2026-09-20, **marked
> Latest**, read 2026-09-29)

[api.github.com/repos/h4ckf0r0day/obscura/releases](https://api.github.com/repos/h4ckf0r0day/obscura/releases)
now shows **v0.2.4, published 2026-10-04**, marked
[Latest](https://api.github.com/repos/h4ckf0r0day/obscura/releases/latest) —
**212 commits** past v0.2.3. Its own notes say it "fixes frame teardown crashes,
adds recovery for failed CDP workers, improves input and navigation behavior, and
tightens the release validation gate".

Why this matters more here than the version number suggests:

- Obscura is run as a downloaded `.exe` with `--stealth` — `docs/DEEP-AUDITS-2026-10-05.md:89`
  calls it "the highest-trust unaudited binary in the project".
- `PINNED_DIGEST = ""` (line 145): the exe hash is trust-on-first-use.
- The **release-zip** pin `RELEASE_ZIP_SHA256` (line 143) was itself "read …
  through a page reader, NOT by downloading the file and hashing it".
- `--stealth mcp` is passed and the tool is driven over stdio; v0.2.4's changes
  are in exactly that area (CDP worker recovery, frame teardown).
- The feature is **off by default and has never been run for real**
  (`docs/ARCHITECTURE.md:646`: "Nothing of it was ever run where it was built").

**What the update buys:** crash fixes in the automation path, and a binary whose
release page still matches the comment.
**What it risks:** a new 212-commit binary that nobody has run, a new zip hash to
verify, and `tools/check_obscura.py` / `backend/test_obscura.py` (92 checks) would
need re-running. Doing nothing is also defensible *while the switch stays off* —
but then the comment must stop claiming v0.2.3 is the newest release.

### F3. The hardware research is built on an Ollama and llama.cpp snapshot that has moved

**Confidence: high for the versions; medium for which specific claims changed.**

`docs/HARDWARE-PROFILES.md:99-104` records the exact sources the VRAM/model
topology work was read from:

| Source | Commit | Date |
|---|---|---|
| `ollama/ollama` | `b2da9e4` | 2026-09-23 — "`LLAMA_CPP_VERSION` says it builds llama.cpp `b11081`" |
| `ggml-org/llama.cpp` | tag `b11081` = `161755f` | 2026-09-21 |

Today:

- [api.github.com/repos/ollama/ollama/releases/latest](https://api.github.com/repos/ollama/ollama/releases/latest)
  → **v0.40.0**. The commit the docs read sits between **v0.34.4** (2026-09-23) and
  v0.35.0 (2026-09-28) — see
  [the release list](https://api.github.com/repos/ollama/ollama/releases?per_page=10):
  v0.40.0, v0.35.1, v0.35.0, v0.34.4, v0.34.3, … That is roughly **six releases** of drift.
- [api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8](https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8)
  → build **`b11460` (2026-10-07)**. From `b11081` that is **~379 builds**.
  llama.cpp has also begun cutting semver tags alongside the build numbers
  ([tags](https://api.github.com/repos/ggml-org/llama.cpp/tags) → `v0.6.0`, `v0.5.0`, …).

Why it matters for *this* project specifically: the four claims the doc says
"change the answer" are all read out of that source —

1. llama.cpp keeps a 1 GB gap per card (`LLAMA_ARG_FIT_TARGET`) — the doc's whole
   "8.60 GiB of an 8.0 GiB card" calculation depends on it;
2. flash attention is now on by default when `q8_0` KV cache is used;
3. Ollama's own estimator over-counts by ~1.88×;
4. each loaded model is its own llama.cpp process.

It also notes `q8_0` and Turing (compute 7.5) behaviour, and the second-card lane
is explicitly "installed but not measured". Six Ollama releases and ~379
llama.cpp builds is enough that re-reading those four files is worthwhile before
the owner acts on any number in `HARDWARE-PROFILES.md`.

**What the update buys:** confidence that the 8 GB and 12 GB presets still match
what the runtime does. **What it risks:** none by itself — this is a *reading*
task, and the doc already says which files to re-read. Note also that Ollama's
v0.40.0 notes advertise MLX-by-default on Apple Silicon and new model families
(`gemma4`, `qwen3.6`, `qwen3.5`) — irrelevant to a Windows/NVIDIA PC, but it shows
the release cadence.

**Suggested action:** re-read `common/common.h` (`LLAMA_ARG_FIT_TARGET` default),
`src/llama-context.cpp` (the fit path) and Ollama's `LLAMA_CPP_VERSION` /
`vram-estimate.patch` at today's commits, and stamp a new date on the doc.

### F4. SearXNG — the **default** search provider — is pulled as an unpinned `:latest`

**Confidence: high.**

`backend/README.md:10057` tells the owner to run:

```
docker run -d --name searxng --restart unless-stopped -p 127.0.0.1:8888:8080 -v "$env:USERPROFILE\searxng:/etc/searxng" docker.io/searxng/searxng:latest
```

`https://api.github.com/repos/searxng/searxng` → no GitHub releases at all
([`/releases/latest` → 404](https://api.github.com/repos/searxng/searxng/releases/latest));
the project ships continuously. So `:latest` is not merely careless here — there
is no release to pin to instead.

Two consequences for this project:

- It is the **default** provider (`jarvis_search.py`'s `DEFAULT_PROVIDER = "searxng"`),
  so every fresh install runs whatever image `:latest` resolves to that day.
- Being AGPL-3.0 and run-beside in a container, the *licence* is fine (it is not
  linked into Jarvis). The risk is an untracked image change under a security
  feature: the search provider is one of the "named ways out of the PC".

This was already found internally (`docs/audit-reports-2026-09-29-30/42-audit-aed58634.md:17`,
"Fix: pin `@sha256:`") and has not been fixed. **What it buys:** a reproducible
provider. **What it risks:** a digest pin means the owner must change it by hand
to get security fixes — so the honest form is a *dated tag* plus a note, or a
digest plus a written update line.

### F5. The Tauri stack has drifted a full minor, and the desktop is the app the owner uses

**Confidence: high.**

`jarvis-desktop/src-tauri/Cargo.lock` resolves **tauri 2.11.6**; crates.io's
`max_stable_version` is **2.12.1**
([crates.io/api/v1/crates/tauri](https://crates.io/api/v1/crates/tauri)).
Every `tauri-plugin-*` this app declares is also behind (updater 2.11.0 → 2.13.1
being the largest gap), as are `wry` 0.55.1 → 0.57.0 and `tao` 0.35.3 → 0.37.1
underneath it. `@tauri-apps/cli` resolves 2.11.5 with `^2.1.0` declared, current
2.12.1 ([registry.npmjs.org/@tauri-apps/cli/latest](https://registry.npmjs.org/@tauri-apps/cli/latest)).

Not an emergency — nothing here is a security advisory, and the project's habit of
pinning deliberately ("a new release must not change what CI tests overnight") is
why the numbers are where they are. But it is a whole minor of the shell that
holds the tray icon, the updater, the global shortcuts and Windows Hello.

Also worth recording: **Tauri 3.0.0-alpha.4 exists on crates.io** — crates.io
reports `newest_version = 3.0.0-alpha.4` alongside `max_stable_version = 2.12.1`
on the same [crate page](https://crates.io/api/v1/crates/tauri). Nothing in this
repository references a v3 migration path; when v3 lands it is a coordinated
change across the 8 plugins plus `window-vibrancy` plus `wry`/`tao`, not a bump.

**Suggested action:** one deliberate burn-down — `cargo update` the plugin set +
`tauri` together, then the existing desktop suites (`npm run test:all`, plus
`cargo test`), rather than piecemeal bumps.

### F6. Borrowed code is credited but not *versioned* — so drift is invisible

**Confidence: high for the observation, medium for the impact.**

`THIRD-PARTY-NOTICES.txt` records exact versions where the component *is* a
dependency (`fsrs 6.3.2`, `youtube-transcript-api 1.2.4`, `onnxruntime 1.22.0`,
`pymicro-wakeword 2.5.0`, `Silero VAD v6.2.3`, `openWakeWord v0.5.1`,
`browser-use v0.13.10`). But for the code that was **read and re-written**, it
records only a date or nothing at all:

- **Handy** — "read 2026-09-28" (line 735), no version. Upstream is now **v0.9.8**
  (2026-10-03) — [api.github.com/repos/cjpais/Handy/releases/latest](https://api.github.com/repos/cjpais/Handy/releases/latest).
- **Spring-It-On, TalkingHead, airi, ChatVRM** — no version at all
  (lines 586-616), though the notice is careful to say "no file of theirs is
  shipped". Their current state:
  [Spring-It-On](https://api.github.com/repos/orangeduck/Spring-It-On) (last push 2026-03-23),
  [TalkingHead](https://api.github.com/repos/met4citizen/TalkingHead) (v1.7.0, active),
  [airi](https://api.github.com/repos/moeru-ai/airi) (active),
  [ChatVRM](https://api.github.com/repos/pixiv/ChatVRM) (archived — see F7).

This is a *record-keeping* finding, not a licence finding: all of these are MIT and
the notices are complete and accurate about attribution. The gap is that nobody
can later answer "has upstream changed the thing we copied?", which is precisely
what the owner asked. `docs/DEEP-AUDITS-2026-10-05.md:90` already notes the same
class of problem in `tools/gen_notices.py` (it walks `cargo metadata` only).

**Suggested action:** add `(read at <commit>, <date>)` to each adapted-code notice
block. Cheap, and it makes the next audit a lookup instead of a re-read.

### F7. One of the four MIT motion sources is archived

**Confidence: high.**

`https://api.github.com/repos/pixiv/ChatVRM` →
[**`archived: true`**](https://api.github.com/repos/pixiv/ChatVRM), last push
2025-05-27. It is one of the four projects the animal motion logic follows
(`THIRD-PARTY-NOTICES.txt:604`).

Low impact: the code was **re-written in Jarvis's own pose code**, no file of
theirs is shipped, the licence is MIT (perpetual and irrevocable for what was
already taken), and the other three sources are alive (TalkingHead v1.7.0,
airi active, Spring-It-On quiet but not archived). Recording it so that
"archived upstream" is not mistaken for "we owe something".

---

## Checked and already current

Listed so that the absence of a row above is meaningful.

**Python (61 of 78):** `numpy 2.5.3`, `sherpa-onnx 1.13.8`, `sherpa-onnx-core 1.13.8`,
`onnxruntime 1.30.0`, `sqlite-vec 0.1.9`, `fsrs 6.3.2`, `ddgs 9.16.0`,
`markitdown 0.1.8`, `youtube-transcript-api 1.2.4`, `openpyxl 3.1.5`, `pandas 3.0.6`,
`pillow 12.3.0`, `pdfminer-six 20260107`, `pdfplumber 0.11.10`, `uiautomation 2.0.29`,
`winrt-runtime 3.2.1` and all seven `winrt-Windows.*` 3.2.1, `espeakng-loader 0.2.4`,
`pyyaml 6.0.3`, `requests 2.34.2`, `py-rust-stemmers 0.1.8`, `protobuf 7.36.2`,
`lxml 6.1.3`, `urllib3 2.8.0`, `pycparser 3.0`, `cffi 2.1.1`, `tqdm 4.70.1`,
`defusedxml 0.7.1`, `flatbuffers 25.12.19`, `tokenizers 0.23.2`, `loguru 0.7.3`,
`markdownify 1.2.3`, `primp 2.0.1`, `xlsxwriter 3.2.9`, `python-pptx 1.0.2`,
`python-dateutil 2.9.0.post0`, `sympy 1.14.0`, `packaging 26.3`, `fsspec 2026.9.0`,
`anyio 4.15.1`, `httpx 0.28.1`, `httpcore 1.0.9`, `h11 0.16.0`, `beautifulsoup4 4.15.0`,
`click 8.5.0`, `colorama 0.4.6`, `cobble 0.1.4`, `win32-setctime 1.2.0`,
`ml-dtypes 0.6.0`, `et-xmlfile 2.0.0`, `typing-extensions 4.16.0`, `tomli 2.4.1`,
`certifi 2026.7.22`, `idna 3.20`, `six 1.17.0`.
**Optional extras current:** `pymicro-wakeword 2.5.0`, `pymicro-features 2.0.2`,
`playwright 1.63.0`, `speechbrain 1.1.1`, `f5-tts 1.1.22`, `soundfile 0.14.0`.

**Rust current (of the declared set):** `image 0.25.10`, `serde 1.0.229`,
`serde_json 1.0.151`, `xcap 0.9.8`, `hound 3.5.1`, `qrcodegen 1.8.0`; transitive
`quick-xml 0.42.0`, `native-tls 0.2.18`, `ring 0.17.14`.

**CI:** `android-actions/setup-android v4.0.4`, `Swatinem/rust-cache v2.9.2`.

**Android/npm:** `androidx.biometric:biometric 1.1.0`, Kotlin compose plugin
`2.4.20`, Kotlin serialization plugin `2.4.20`, `junit:junit 4.13.2`.

**External:** sherpa-onnx, Silero VAD, py-fsrs, ddgs, markitdown,
youtube-transcript-api, ONNX Runtime (Python), playwright-python, F5-TTS,
pymicro-wakeword, openWakeWord's model release, livekit-wakeword (2 commits),
`qwen3:8b` and `qwen3.5:9b` still present in the Ollama library, Obscura's
Apache-2.0 licence, colibri's Apache-2.0 licence and activity.

**Licences:** none of the components checked has changed licence. Everything the
project relies on is still MIT / Apache-2.0 / BSD / OFL / AGPL-run-beside, which
is compatible with the non-commercial build rule. `cargo deny check licenses`
already gates the Rust side in CI.

---

## What I could not check, and why

1. **The Rust lockfile's other 638 crates.io entries.** I checked the 25 declared
   crates plus 3 notable transitive ones out of 666 in `Cargo.lock`. Checking all
   666 would mean 666 crates.io requests; the project's own
   `jarvis_tool_updates.py` already does exactly that on demand from the owner's
   PC, and `cargo deny check advisories` covers the security half in CI. **Not a
   gap in coverage of the declared dependency set — a gap in the transitive set.**
2. **`pip-audit`.** Not runnable here (piped child stdio is blocked). Substituted
   with a direct OSV query per exact pinned version plus PyPI's own
   `vulnerabilities` array — a *different* source, not the same tool.
3. **Whether the newer versions actually work.** Nothing was installed, built or
   run. Every "current" number is a version read from a registry, and every
   "matters?" judgement is reasoning about the release notes, not a measurement.
4. **Ollama's cloud/registry API for tag digests** — `https://registry.ollama.ai/v2/library/<m>/tags/list`
   returned HTTP 401, so model *tags* were read from `https://ollama.com/library/<m>/tags`
   instead. Digests of the pinned model blobs were **not** checked.
5. **`gemma4:e4b`, `nomic-embed-text` and the other named-but-unpinned candidate
   models** — only the two the repository actually defaults to (`qwen3:8b`,
   `minicpm-v:4.6`) plus `qwen3.5:9b` were checked against the Ollama library.
6. **The `docs/` claims about third-party APIs** (Home Assistant, the chatbot
   sites, Exa/Tavily/Brave, Home Assistant's own versions) — out of scope: they
   are not pinned dependencies.
7. **Obscura v0.2.4's actual asset hash.** I read the release page's metadata
   through the GitHub API but did **not** download the zip and hash it. The row in
   F2 says the tag and the commit count; it does not certify a new hash.
8. **`dtolnay/rust-toolchain`** is pinned to a branch commit on purpose, so there
   is no "behind" number to report for it.

*Every version in this report was read from a URL named next to it, on
2026-10-07. Where a number came from a registry payload rather than a human-readable
page, the URL shape is given in the header table.*
