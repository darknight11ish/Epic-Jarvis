# More Docker integration — design note

Written 2026-10-09, for the owner's request in his own words: *"add more docker
integration into jarvis that can be toggled with settings inside both the
android app and desktop program."*

This note does three things: says honestly what Docker does in Jarvis today,
sets out **three separate things** "more integration" could mean so the owner
can pick (they are not one feature), and writes down the safety shape that is
**not** up for a vote whatever he picks. Section 6 is the questions he answers.

Nothing here is built yet except the first slice named in section 7. This is a
design note, not a claim.

---

## 1. What Docker does in Jarvis today — exactly one thing, started by hand

Docker Desktop 29.7.2 is installed and the engine works on this PC. **Docker is
used for exactly one thing: SearXNG, the default web-search provider.** It is
started by hand, and nothing in Jarvis manages it.

| What | Where |
| --- | --- |
| The compose file, and SearXNG's settings template | `docker/searxng/docker-compose.yml`, `docker/searxng/settings.template.yml` |
| The manual runbook ("Web search", step 3a) | `backend/README.md` |
| The address Jarvis calls | `backend/jarvis_search.py:122` — `DEFAULT_SEARXNG_URL = "http://127.0.0.1:8888"` |
| The provider that is the default | `backend/jarvis_search.py:121` — `DEFAULT_PROVIDER = "searxng"` |
| Which provider needs Docker at all | `backend/jarvis_search.py:1303` — `"needs_docker": pid == "searxng"` |
| What Jarvis prints when it is down | `backend/jarvis_search.py:1002` — sends the owner to that README step |

The owner has since started the container by hand, and it answers: `docker ps`
shows `searxng | searxng/searxng:2026.10.9-f4822b3fc | Up | 127.0.0.1:8888->8080/tcp`,
and Jarvis's own `POST /api/search/test` says *"SearXNG (on this PC) works"*.

**Where the compose file lives.** It landed on `main` while this note was being
written (`feat/searxng-setup`, merged as PR #156, `df36eb23`). Earlier the same
day it was only on that branch, and anyone reading `main` would not have found
`docker/` at all — worth knowing, because everything below points at those two
files. `backend/test_docker.py` now compares the pinned image and the published
port against that file for real rather than skipping the check.

### The honest answer to "is a dashboard already half-built?"

**No — not one line of it exists.** Nothing in the backend runs `docker`. There
is no module, no route, no screen, and no setting. What is true is narrower and
worth saying plainly, because it changes only the *cost*, not the *work*:

- `docker` is on `PATH` and answers, so the backend **can** call it through a
  subprocess — no installation step, no new dependency, no admin rights.
- SearXNG already publishes on loopback only (`127.0.0.1:8888`), which is the
  shape every option below has to keep.
- The settings screens, the approval gate and the phone's "open a settings
  section" machinery all already exist and are reused — a Docker screen is a new
  *user* of them, not a new mechanism.

So: the plumbing is there, the feature is not. A dashboard is a real new module
plus a route plus a screen on each app — not a wire-up of something already
built.

**One thing already decided against, which option (c) would revisit.**
`backend/jarvis_agent.py:34-35` says, of the AI's own tool list: *"Docker-based
execution and connectors remain excluded with the reasons README.md gives."*
Running code in a container as an AI tool was deliberately left out. Option (c)
is not a new idea — it is that decision, asked again in a narrower form.

---

## 2. Three options, and what each costs

These are deliberately kept apart. Picking (a) does not get you (b) or (c), and
each one is a different amount of work and a different amount of risk.

### Option (a) — A container dashboard

**What it is.** A page in both apps that lists the containers Jarvis knows
about, says whether each is running, and lets the owner start, stop or restart
one. Per-service toggles. Reading a container's recent log lines.

**What it is not.** Not a general Docker manager. Jarvis lists and acts on the
containers **it created** (today: `searxng`), named in one allow-list in code. A
container the owner started from a terminal shows up as "not one of mine" and no
button touches it.

**What it costs.** One new backend module (the `docker` subprocess calls, the
allow-list, the pinned-tag and loopback checks, the gate), one route, one
settings card on each app, and a screen. This is the largest of the three by UI
work — the desktop wants a status row per service, the phone a plate — but it is
also the only one that gives the owner something he can see and use immediately.

**What it risks.** Low, if the safety shape in section 3 is followed. The action
is start/stop on a named container: it cannot read the owner's files, cannot
send anything anywhere, and cannot exceed what the compose file already asks for.
The one real risk is a *pull* hiding inside a start (see section 3) — which is
why the module checks that no image has to be fetched before it starts anything.

**Honest verdict.** The best first thing to build, and the first slice in
section 7 is a narrow piece of it.

### Option (b) — Auto-start

**What it is.** Jarvis brings the services it needs up when it launches, and
stops them when it exits. "Web search works because Jarvis started it", instead
of "web search works if you remembered to run `docker compose up -d`".

**What it costs.** Less UI than (a) — one switch per service, in both apps — but
more moving parts: Jarvis has to decide what "when it launches" means (the
desktop app? the backend? the Windows session?), what happens when Docker
Desktop itself is not running (starting Docker Desktop is a multi-second,
visible thing, and Jarvis must not fight the owner for it), and what "when it
exits" means for a container with `restart: unless-stopped` in its compose file —
which is what SearXNG has today, so a stop Jarvis issues will be undone by
Docker on the next engine start.

**What it risks.** The real risk is not safety, it is **surprise**: a service
that starts by itself is a container the owner did not just ask for, and one
that stops by itself can take away something he was using. This is why (b)
should only ever cover services on the same allow-list as (a), and why it must
be a switch that starts **off**.

**Honest verdict.** Cheap once (a) exists — it reuses the same allow-list and the
same calls. Do (a) first; (b) is a small addition on top, not a separate project.
Its cost is mostly in deciding the "when", not in code.

### Option (c) — Running Projects' code in a container instead of on the PC

**What it is.** The "Jarvis does real work" feature (`docs/PROJECTS-DESIGN.md`)
already writes files and runs tests and benchmarks **directly on the owner's
PC**. Option (c) runs that code inside a container instead, so a test suite or a
benchmark cannot touch the owner's real files, real `PATH` or real network.

**What it costs.** Much the most of the three. A container is only a safe place
if the code inside it is *closed in*, and closing it in means deciding, per
project, what the code is allowed to see: which folder is mounted, whether it
gets the network at all, which image and therefore which language toolchain.
Those are not defaults Jarvis can guess — a Python project and a Node project
want different images, and a project with no `Dockerfile` has no obvious image
at all. Every one of those decisions is a per-project card.

**What it risks.** This is the one option that can genuinely hurt the owner if
it is built carelessly, because the whole point is to let code run. The named
dangers are all in section 4. It also revisits a written decision
(`jarvis_agent.py:34-35`, section 1 above) and would need that line changed on
purpose rather than quietly.

**Honest verdict.** Worth doing, and worth doing **last**. It is the only option
that needs new decisions from the owner per project, and it is the only one whose
mistakes are not merely annoying.

---

## 3. The safety shape — not negotiable, whichever option is picked

These are not options and not defaults to tune. They follow from
`docs/ARCHITECTURE.md` section 4 ("The egress boundary") and `CLAUDE.md`'s rules
1, 2 and 4. If an option cannot be built this way, that option does not get
built.

1. **Every published port is on `127.0.0.1` only.** Never `0.0.0.0`, never a
   bare `8888:8080`, never a public tunnel. This is already true of SearXNG
   (`docker/searxng/docker-compose.yml:46` — `"127.0.0.1:8888:8080"`, and the
   file's own header says why it must keep saying that), and it stays true of
   anything added. Rule 2 forbids a public tunnel; `127.0.0.1` is what makes a
   container on this PC reachable from this PC and nowhere else.

2. **Pulling an image is a way out of the PC, and is treated as one.** A pull
   fetches bytes from the internet from a registry that is not the owner's, so
   it belongs in `ARCHITECTURE.md` section 4's list of named ways out. That
   means: an approval card that shows **exactly which image, from which
   registry, at which tag** — `docker.io/searxng/searxng:2026.10.9-f4822b3fc`,
   not "SearXNG" — and the card is raised **before** anything is fetched.

3. **Nothing auto-pulls. Ever.** No start, no restart, no repair, no
   "conveniently missing" step in an auto-start may fetch an image. A missing
   image is a thing Jarvis *reports* and offers to fetch with a card, never a
   thing it quietly obtains. This is the trap that makes (b) dangerous: `docker
   compose up` will pull by default, so an auto-start built on `compose up`
   would pull images with no card at all. An auto-start has to check first that
   every image is already present locally, and refuse to start anything
   otherwise.

4. **Every start, stop and re-exec goes through the same gate as any other
   action.** One action name per kind of act, one approval card, decided by a
   person — the mechanism in `docs/ARCHITECTURE.md` section 3. A looser switch
   (for instance "start SearXNG without asking") is allowed only in the shape
   every other loosening in this repo has: **off by default, turning it on is
   one card plus Windows Hello on the PC, turning it off is immediate.**

5. **The stale-link rule applies.** `CLAUDE.md` rule 4: the app blocks acting
   when the event stream is stale. That already covers the search that uses
   SearXNG; it covers the container's own start/stop the same way, with no
   exception for "it is only a container".

6. **Pinned tags only.** No `:latest`, no untagged image. SearXNG is pinned by
   dated tag and says why (`docker-compose.yml:27-33`) — image tags are mutable,
   so an unpinned image is a thing that can change under the owner without him
   approving the change.

7. **Jarvis says what it did not create.** A container not on Jarvis's
   allow-list is listed as "started elsewhere — Jarvis will not touch it", and
   no button, no voice command and no auto-start reaches it. Silence here would
   read as ownership.

---

## 4. What Jarvis must never do here

Written as prohibitions, because a list of good intentions is not checkable.

- **Never `--privileged`.** Not for a service, not for a Project, not to "make
  it work". A privileged container is the owner's PC with the door taken off.
- **Never mount the owner's home directory, or the backend folder, into a
  container** without his explicit approval **for that one mount**. Not
  `%USERPROFILE%`, not `C:\Users\pcadmin`, not the folder the backend lives in
  (`docs/ARCHITECTURE.md` section 9 — it holds the owner's `.py` files, and
  `backend/test_security_pc.py:619` already treats `.docker/config.json` as a
  secret worth listing). SearXNG today mounts exactly two things, and both are
  about SearXNG itself: its own settings folder and its own settings template
  (`docker-compose.yml:47-61`). Any mount that reaches further is a card naming
  the exact host path and the exact container path.
- **Never publish a port beyond loopback.** Covered above; repeated here because
  it is the one line a careless `docker run` gets wrong by default.
- **Never use an image without a pinned tag.** Covered above.
- **Never act on a container it did not create without saying so.** Covered
  above. "Saying so" means both apps and the log, not a comment in the code.
- **Never let a container be a way out of the PC that the owner did not name.**
  A container with the network open is a program that can send things. If an
  option needs one, that is a new named way out in `ARCHITECTURE.md` section 4,
  and the owner's yes comes before the first run.
- **Never put the owner's token, keys or memory inside a container.** Rule 3
  and rule 1. `jarvis_child_env.py` already exists for exactly this reason on
  the machine side — an allowlist of what a child process inherits, so no token
  or key goes with it. A container gets less than that, not more.

---

## 5. What "toggled with settings in both apps" means here

The owner asked for the switch to exist in both apps. The repo already has one
way to do that, and this feature should use it rather than invent a second:
declare the setting **once** in `backend/jarvis_settings_registry.py`, give it a
place on the phone in `jarvis-client`'s `OpenPlace.kt` / `MenuPlaces.kt` /
`SettingsJump.kt` / `SettingsScreen.kt`, and let both apps show the same words
from the PC. "When the phone does not answer" (`backend/jarvis_handoff_mode.py`,
the owner's decision of 2026-10-08) is the model: one module, one route, one
`WORDS` table both apps render word for word.

Two consequences worth writing down now, so they are not a surprise later:

- **A per-service toggle is a loosening, and loosening asks.** "Start SearXNG
  without asking" is off by default, on is one card plus Windows Hello on the
  PC, off is immediate — the shape every other loosening here has. The *first*
  start always asks; only a switch the owner deliberately turned on makes the
  second one quiet.
- **The phone is told what the PC decided.** The phone renders the words the PC
  serves; it does not keep its own copy of the list of services.

---

## 6. The owner's questions

Short, and answerable in batches — ask these two at a time, not all four.

**Q1. Which of the three do you want first?**
- **(a) A container dashboard** — see what is running, start and stop it. *(recommended: it is the one you can use immediately, and (b) gets cheaper once it exists)*
- **(b) Auto-start** — Jarvis brings SearXNG up itself and stops it on exit.
- **(c) Projects' code in a container** — tests and benchmarks run boxed in instead of straight on your PC.

**Q2. When a start would need to download a new image, what should happen?**
- **Ask me with a card naming the exact image and registry** — and if I say no, nothing starts. *(recommended: this is the safety shape in section 3, and a pull is a way out of your PC)*
- **Never download at all** — a missing image is an error I fix by hand at a terminal.

**Q3. Should Jarvis be able to start SearXNG without asking, once you have turned it on?**
- **No — ask every time.** *(recommended: starting a container is a small thing, but a standing permission is not)*
- **Yes, with a switch** — off by default, turning it on asks for your approval on the PC with Windows Hello, turning it off is immediate.

**Q4. For option (c) only: what may a project's container see?**
- **Nothing but that project's own folder, no network.** *(recommended, and the only version this repo can build without a new named way out of the PC)*
- **That folder plus the internet** — needed for a project that installs its own packages, and it is a new named way out, so it gets its own card and its own line in `ARCHITECTURE.md` section 4.
- **Leave (c) alone for now.**

---

## 7. The first slice — what is being built alongside this note

The smallest genuinely useful piece of option (a), and **nothing else**:

- `backend/jarvis_docker.py` — a new module that lists the containers on
  Jarvis's own allow-list and can start or stop one. It refuses to act on a
  container it did not create, refuses an unpinned image, refuses to start
  anything whose image is not already on this PC, and refuses a start or stop
  that did not come through the gate.
- `backend/test_docker.py` — the tests, mostly about the refusals, run for real
  (`175 passed, 0 failed`). Two of them read
  `docker/searxng/docker-compose.yml` itself and fail if the image it pins, or
  the port it publishes, ever drifts from what the module expects.
- It is declared in `scripts/apply-patches.ps1`'s `$SHIPPED` and in
  `backend/_where.py`'s `SHIPPED` tuple, which is what makes it a module the
  patcher copies in at all.
- The setting in the registry, its menu, and both apps' screens are **written
  and proved but not landed yet** — see section 7a, which has the failing tests
  that say why.
- The gate lines for the two new action names are written into the module's
  design rather than shipped as `docker.patch`: reason in section 7a.

**Status, said plainly: the reading and the start/stop are built, tested and
proved against the real engine. They are not yet reachable over HTTP, and
neither app shows a row yet.**

**What this slice deliberately does not do:** no auto-start, no image pulling (so
no pull card yet — the card described in section 3.2 is designed but the first
slice never pulls, which is the safe order to build it in), no logs view, no
restart button, and no running of code.

## 7a. The settings row is genuinely blocked, and this is the proof

The brief for this work said to declare the setting in
`backend/jarvis_settings_registry.py` and `backend/jarvis_menus.py` and let the
generated catalogues follow. **That cannot land yet, and the repository's own
tests say so.** Declaring the section was tried, and three suites failed:

| Suite | Its own words |
| --- | --- |
| `backend/test_settings_registry.py` | `FAILED: every 'both'/'desktop' section is a real settings.html <section id>` |
| `backend/test_menu_visibility.py` | `failed: settings.docker is a real Settings card` |
| `backend/test_feature_list.py` | `failed: the feature list covers every route section and menu id` |

The reason is the same in all three, and it is the missing generator: a registry
`Section` whose `app` is `both` or `desktop` **must** correspond to a real
`<section class="card" id="...">` in `jarvis-desktop/src/settings.html`, and a
menu in `jarvis_menus.py` must correspond to a real card too. The desktop row is
supposed to be produced by `tools/gen_settings_cases.py`, which has **not**
landed — it is not on `origin/main` and does not exist in this worktree
(`Test-Path tools\gen_settings_cases.py` → `False`; `git grep gen_settings_cases`
→ nothing). Hand-writing the row into `settings.html` is exactly what this work
was told not to do, because the generator will own that file.

So the whole settings-and-phone layer was **written, compiled and tested, then
taken back out of the tree** so the branch is green rather than red:

- it is preserved verbatim in `docs/DOCKER-INTEGRATION-SETTINGS-LAYER.patch.txt`
  (14 files, 1,456 lines): the `Section("docker", ...)` and
  `_m("settings.docker", ...)` declarations, the phone's
  `OpenPlace` / `MenuPlaces` / `SettingsJump` / `SettingsScreen` wiring, the
  regenerated catalogues, and `net/Docker.kt` + `ui/screens/DockerPlate.kt` —
  the phone screen that shows each container's state and offers Start and Stop,
  reading its words from the PC's own `WORDS` table so both apps say the same
  thing.
- it **compiled and passed**: with that layer applied,
  `.\gradlew.bat testDebugUnitTest` reported **1,972 tests, 0 failures, 0
  errors**, and `python tools/gen_menu_cases.py --check` printed
  `menu-cases.json (both copies), MenuCatalog.kt and menu-catalog.js match`.

**To land it:** once `tools/gen_settings_cases.py` is on `main`, add the two
registry lines, apply the preserved layer, regenerate the catalogues with the
repo's own tools (`gen_menu_cases.py`, then the new `gen_settings_cases.py`),
and run `test_settings_registry.py`, `test_menu_visibility.py`,
`test_feature_list.py`, `check_parity.py` and the phone suite.

**What this slice deliberately does not do:** no auto-start, no image pulling (so
no pull card yet — the card described in section 3.2 is designed but the first
slice never pulls, which is the safe order to build it in), no logs view, no
restart button, no running of code, and no settings row on either app until the
generator lands (section 7a).

### The one line that is still missing on the PC

`jarvis_docker.py` ends with an `install(handler_cls, *, origin_ok, token_ok,
read_body)` function, the same shape every other new module here uses, and its
routes are `GET /api/docker/containers` and `POST /api/docker/service`. The one
remaining step is the small patch that adds the call to it in `jarvis_hud.py`,
next to the other `... .install(Handler, origin_ok=_origin_ok, ...)` blocks
(`backend/chatbot-routes.patch` is the template).

**It is not in this branch, on purpose.** Every such patch is written against
the owner's live `jarvis_hud.py`, and that file cannot be read from here: the
only copy in this repository, `jarvis-backend/jarvis_hud.py`, is a published
snapshot that **predates** the very patches it would have to sit beside — it
contains no `jarvis_chatbot_routes.install(...)` block and no `jarvis_limits`
reference, both of which are on `main`. A patch anchored on context I cannot
read would be a guess, and `backend/test_patch_wellformed.py` exists precisely
because a malformed patch shipped once already. So the patch is left to be
written where the live file can be read, with `git apply --check` proving it —
the same standard every other patch here meets.

Until then the module is **not reachable over HTTP**, and the honest status is:
the container reading and the start/stop, with every refusal, are built, tested
and proved against the real engine (section 7b); the route and the two screens
are the next step.


---

## 7b. The evidence, as it was actually produced

```
$ cd backend; python jarvis_docker.py
{'docker': True,
 'path': '/api/docker/service',
 'services': [{'can_start': True,
               'can_stop': True,
               'container': 'searxng',
               'image_present': True,
               'ours': True,
               'pinned_image': 'docker.io/searxng/searxng:2026.10.9-f4822b3fc',
               'present': True,
               'provides': "web search on this PC (Jarvis's default search provider)",
               'published': '127.0.0.1:8888:8080',
               'running': True,
               'service': 'searxng',
               'status': 'Up About an hour',
               'url': 'http://127.0.0.1:8888'}],
 ...}
```

That is the module reading the **real** Docker engine on this PC, and deciding
`ours: True` for the running SearXNG: the pinned tag matches, the only published
port is `127.0.0.1:8888`, and it is not privileged. Nothing mock, nothing
pretended.

```
$ cd backend; python test_docker.py
175 passed, 0 failed
```

The tests are mostly refusals, and the load-bearing one is
`test_start_never_pulls`: with the image absent, a start answers `409` with
`needs_download` and the suite proves **`docker start` was never reached and no
card was raised** — which is section 3.3 made checkable rather than promised.
`test_module_source_cannot_pull_or_privilege` walks the module's syntax tree and
fails if any call ever passes `pull`, `compose`, `run`, `-v` or `--privileged`.

```
$ python tools/check_parity.py    # exit 0
$ python tools/gen_menu_cases.py --check
menu-cases.json (both copies), MenuCatalog.kt and menu-catalog.js match
$ python backend/test_shipped_modules.py
596 passed, 0 failed        # it fails if the two SHIPPED lists ever differ
```

With the settings-and-phone layer of section 7a applied,
`.\gradlew.bat testDebugUnitTest` reported **1,972 tests, 0 failures, 0 errors,
0 skipped** — so that layer is known-good and only waits on the generator.

---

## 8. What still needs the owner's decision before more is built
1. Q1–Q4 above.
2. ~~Whether `docker/` lands on `main` first~~ — **settled**: it merged as PR #156
   (`df36eb23`) while this note was being written.
3. If (c) is ever picked: changing `backend/jarvis_agent.py:34-35` on purpose,
   and adding the new named way out of the PC to `docs/ARCHITECTURE.md`
   section 4.

## 9. What is still to build, in the order it can actually be done

1. **The route patch** (section 7a): one `install(...)` call in `jarvis_hud.py`.
   Needs someone who can read the owner's live file, with `git apply --check`.
2. **The gate risk rows** for `docker_service_start` and `docker_service_stop`
   (`jarvis_gate.py`'s two tables, the shape `backend/handoff-mode.patch` uses).
   Until they land the actions take `unknown_action_tier`, which is `"ask"` in
   the shipped config — so a fresh install **asks on both directions** rather
   than failing open, and `jarvis_docker.py` refuses a start outright if the
   tier is anything but `"ask"`. Adding the rows makes the card explain itself
   in the owner's words; it does not change what is allowed.
3. **The settings row and both screens** (section 7a): apply
   `docs/DOCKER-INTEGRATION-SETTINGS-LAYER.patch.txt` once
   `tools/gen_settings_cases.py` is on `main`.
4. Then, and only then, the rest of option (a) — logs, restart, per-service
   toggles — and options (b) and (c) if the owner picks them.
