"""Run every backend suite that can run without the owner's PC, and skip - by
name, with the reason - the ones that cannot. This is what CI runs.

    python3 backend/run_suites.py

WHY A RUNNER AND NOT JUST A LOOP. Twelve suites test a patch against the
file it patches - jarvis_hud.py, jarvis_gate.py, jarvis_extract.py,
jarvis_models.py - and those files live only on the owner's PC, never in this
repository (backend/.gitignore refuses them). Run anywhere else, those suites
fail with an ImportError that looks exactly like a broken patch. A CI job
that is always red teaches everyone to ignore it, so those suites are
SKIPPED here, each one named with the files it is waiting for - and only
while those files are absent. (It was about twenty until 2026-10-27, when the
four that can run their own checks without those files were taken off the
list; see NEEDS_OWNER below.) FOUR MORE SUITES ARE A SECOND, SEPARATE SKIP
CLASS (2026-10-26, below): they are skipped by name even when their files are
present, unless JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1 is set, because each
starts a real, visible Chromium window. Every other suite must pass.

THE BACKEND IT RUNS AGAINST. Not this folder: a temporary folder holding a
copy of every module apply-patches.ps1 ships (backend/_where.py SHIPPED),
side by side, the way they sit on the owner's PC - rebuilt/ flattened in.
So the suites exercise the shipped LAYOUT, not the repository's folders, and
a module that only works because of where it sits in this repository fails
here.

**A DEFAULT RUN IS HERMETIC, AND IT SAYS SO (2026-10-21).** `JARVIS_BACKEND`
is set for the owner's Windows account on this PC, pointing at the LIVE backend
folder - so a plain `python -B backend/run_suites.py` used to run the suites
against the live folder without the person typing anything. That was not a
choice anybody made in that moment, and it made a routine test run a live-code
run. Now the ambient variable is **ignored** unless it is asked for:
`--use-env-backend` runs against whatever `JARVIS_BACKEND` names, and
`--backend-path DIR` runs against DIR, explicitly. Both are refused when what
they name is not a folder, and the default prints one line when it had to
ignore the ambient value, so nobody is surprised. A suite is skipped when
its files are really not there, whichever backend is used - or, for the four
visible-browser suites below, even when its files are there and the opt-in is
not set.

   python3 backend/run_suites.py                       # throwaway copy (default)
   python3 backend/run_suites.py --backend-path "C:/Users/you/Documents/jarvis-backend"
   python3 backend/run_suites.py --use-env-backend     # whatever JARVIS_BACKEND says
   python3 backend/run_suites.py --help                # what it accepts; runs nothing

A suite named on the command line is a BARE file name (`test_ui_control.py`).
A path (`backend/test_ui_control.py`) is refused with the valid form and a
non-zero exit, never silently ignored - the runner used to drop it and run the
whole fleet instead, which two agents hit on 2026-10-26. `--help` is read
before the update lock and before anything is staged.

THE OWNER'S STATE IS LEFT ALONE. The suites run real code that writes -
the audit log, approval queues, switch files - so each run gets a temporary
config folder, audit log and HOME, deleted afterwards (private_state below).
`OPENJARVIS_HOME` and `JARVIS_HOME` are the folder most modules treat as "the
owner's" (databases, inboxes, receipts, the guardian store) and
`JARVIS_LOG_DIR` is what jarvis_framework.log_dir() obeys for the audit log;
pointing them at a throwaway folder is what keeps a suite that forgot its own
`_TMP` from reading or writing the owner's real data during a patcher run. The one way to
ask for the real home is `JARVIS_TESTS_USE_REAL_HOME=1`, and it is never the
default. apply-patches.ps1 asks for the same variables with
`--state-env DIR`; whatever that prints is what its test loop sets, and the
home folder is made before it is printed, so the patcher is hermetic without
a second list to keep in step.

The skip list is explicit, not guessed from a failure: a suite that is not in
it and fails is a failure, and a suite in it whose files ARE present runs.
The four visible-browser suites below are the exception: they are skipped by
name even when present, unless JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1 is set.

AND FOUR SUITES ARE NOT RUN AT ALL UNLESS ASKED (2026-10-26).
`test_chatbot_sites.py`, `test_chatbot_gemini.py`, `test_handoff.py` and
`test_support_widget.py` each start a real, VISIBLE browser window on whatever
machine runs them - all four drive `jarvis_chatbot_web`'s one `headless=False`
launch. On the owner's PC, where Playwright is installed, a plain run of this
file put Chromium windows on his screen one after another ("the browser keeps
opening and closing rapidly"), and the suite's own "is Playwright installed?"
check could never stop it. The default run now prints each of them as `skip`
with its reason and starts none of them. Set
`JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1` to run them; each suite reads the same
variable itself, so the runner and the suites cannot disagree, and either
layer alone is enough to stop a window.

    python3 backend/run_suites.py --jobs 14

`--jobs N` runs N suites at once. **The default is 1, and CI uses the
default**, so the output of the ordinary run is what it has always been. The
updater is the only caller that asks for more (`tools/update_backend.py`, the
owner's own choice of how hard the update should work), and it changes ONLY
the number of workers: the suite list is the same glob in every mode, so a
"quick" update and a "safe" one run exactly the same checks. Each worker gets
its own config folder, audit log and scratch folder inside the same run root,
because the suites write real state and two of them writing into one folder
is not a check either of them asked for.

A SUITE THAT SKIPS EVERY CHECK IS NOT A PASS (2026-10-27). A suite that exits
0 having skipped every check it owns is reported as `NO-CHECKS`, not `ok`, and
it makes the run exit non-zero - because a skip is never a pass, and a guard
phrase that stopped matching must not turn a whole suite green. Three suites
are exempt by name, with the reason, in ZERO_CHECK_ALLOWED: the ones that need
an OPTIONAL package (playwright, cryptography, Pillow) and so legitimately
prove nothing on a machine without it - while the required backend job
installs all three and runs them for real.

THE UPDATE LOCK. A backend update holds `update-in-progress.lock` in the
folder Jarvis keeps its own data in (`OPENJARVIS_CONFIG_DIR`, then
`JARVIS_CONFIG_DIR`, then `~/.openjarvis`). While that lock is VALID (live pid,
heartbeat under 30 minutes, run under 3 hours), this runner REFUSES immediately
with exit 3, naming the lock's pid, pace and start time - a sweep beside an
update starves the CPU and skews the update's timing. The update's own suite
phase is the one exception: `tools/update_backend.py` passes
`--ignore-update-lock`, and `JARVIS_INSIDE_PATCHER=1` does the same for a
caller that must set an environment instead. The lock rules and reading live
in `tools/update_backend.py`'s lock section (one implementation, so the tool,
this runner and the desktop cannot disagree); a checkout without that tool
simply cannot check, and this runner never claims it did.
"""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

# Suite -> the backend files it needs. Found by running each suite in a
# checkout without them and reading which import or file read failed first,
# then reading the suite for its other imports and BACKEND / "..." reads.
# Every entry names at least one file that only the owner's PC has
# (OWNER_FILES), which is what makes it skip here; the rebuilt modules it
# also uses are listed for completeness. test_embedding_guard.py is NOT here:
# it needs only jarvis_memory.py, the staged rebuilt copy satisfies it, and
# it passes against that copy - so it runs.
#
# A SUITE THAT CAN BUILD WHAT IT NEEDS DOES NOT BELONG HERE. test_appearance.py
# was on this list until 2026-10-10 for `jarvis_hud.py`, and it did not need
# the whole file - only the block `appearance.patch` writes, which the patch
# stack's own stand-in carries (`backend/_stack.py`). Sitting here meant its 14
# checks were skipped in CI and ran only on the owner's PC. It now reads the
# real file when there is one and the stand-in when there is not, so it is not
# listed. The three suites that could run PART of themselves were taken off the
# same day, for the same reason, and each one names as a skip whatever still
# needs the owner's whole file:
#
#   * test_voice_503.py - 11 of its 20 checks execute `_no_speech()` and read
#     `_SAY_FALLBACK`, both written whole by voice-503.patch, so the stand-in
#     has them. The other 9 read whole-file route statements with ast.
#   * test_memory_pane.py - 13 of its 49 checks (the learning switch and the
#     query-string reader) come out of the stand-in the same way. The other 36
#     read whole-file route statements.
#   * test_documents_honesty.py - 1 of its 19. MEASURED, not assumed: the two
#     checks that EXECUTE `_has_table` cannot be lifted, because it calls
#     `_ro_sqlite`, which the owner wrote and no patch does - the stand-in has
#     that function's `def` line and the first line of its docstring and none
#     of its body (`mode=ro` and `as_uri` appear nowhere in it), so `_has_table`
#     run from the stand-in raises NameError instead of answering. Passing in a
#     helper of our own would be a paraphrase of the code under test. What is
#     left in CI is the check that a failed documents read is REPORTED - both
#     sentences are written by the patch - which is one real guard where there
#     were none.
#
# Naming the skips, rather than leaving the whole suite listed, is the point:
# the runner prints "N passed, M skipped" beside each of them, so a reader sees
# how much of the suite actually ran.
#
# FOUR WERE TAKEN OFF ON 2026-10-27, after the test audit named 14 suites that
# no CI job ran (`.dsh-scratch/AUDIT-TESTS-2026-10-27/FINDINGS.md`, F-02). Each
# was run DIRECTLY against a staged backend with NO owner files - which is what
# the required backend job runs - and each PASSED, naming as a skip whatever
# still needs the owner's whole file:
#
#   * test_bitemporal.py        28 passed,  1 skipped   (needs no owner file now)
#   * test_extraction_wiring.py 13 passed, 10 skipped   (10 lift jarvis_hud.py)
#   * test_gate_push.py          7 passed,  6 skipped   (6 lift jarvis_gate.py)
#   * test_import_history.py    13 passed,  6 skipped   (6 lift jarvis_extract.py)
#
# That is 61 checks the required backend job gains. The other 10 stay below,
# with the files each is waiting for: they fail or prove nothing without those
# files, and a skip with a reason is honest where a red would only teach people
# to ignore the job. Measured the same way, 2026-10-27:
#
#   test_approval_notice.py, test_gate_outcome.py, test_gpu_offload.py and
#   test_memory_safety.py exit 1 at import with no output at all (they import
#   the owner's module at module level); test_events_pump.py (1 failure) and
#   test_gate_egress.py (5 failures) fail checks that read the owner's real
#   file; test_decide_once.py, test_degrade_filter.py, test_memory_noise.py and
#   test_memory_prefix.py print one whole-suite skip and exit 0 (0 checks).
NEEDS_OWNER = {
    "test_approval_notice.py": ("jarvis_gate.py", "jarvis_events.py"),
    "test_decide_once.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_degrade_filter.py": ("jarvis_hud.py",),
    "test_events_pump.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_gate_egress.py": ("jarvis_gate.py", "jarvis_hud.py", "jarvis_events.py"),
    "test_gate_outcome.py": ("jarvis_gate.py",),
    "test_gpu_offload.py": ("jarvis_hud.py", "jarvis_models.py"),
    "test_memory_noise.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_memory_prefix.py": ("jarvis_hud.py",),
    "test_memory_safety.py": ("jarvis_extract.py", "jarvis_memory.py"),
    # It lifts the real `_completions_url` and `_auth_headers` out of
    # jarvis_hud.py, so it needs that file - and, since 2026-10-06, the real
    # jarvis_chatbot_api too (the cloud lane's resolver): without it the
    # module-level `import jarvis_chatbot_api` inside the lifted function
    # fails and every cloud check would read as "no lane".
    "test_ollama_direct.py": ("jarvis_hud.py",),
    "test_token_file.py": ("jarvis_hud.py",),
}

# The files only the owner's PC has. Checked below: every NEEDS_OWNER entry
# must name one, so the list cannot be used to skip a suite that could run.
OWNER_FILES = {"jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py", "jarvis_models.py",
               "jarvis_skills.py"}

#: THE FOUR SUITES THAT PUT A REAL, VISIBLE BROWSER WINDOW ON THE SCREEN.
#: Measured on the owner's PC, 2026-10-26: a plain `python -B backend/run_suites.py`
#: ran test_chatbot_sites.py, and Playwright opened a real Chromium window for
#: every site profile (`chatgpt-profile10` and the rest, under a temp folder),
#: so the owner saw "the browser keeps opening and closing rapidly". Playwright
#: being INSTALLED is the normal state on that PC, so a suite's own "is
#: Playwright installed?" check could never be the guard. Every suite below
#: imports `jarvis_chatbot_web`, whose one `headless=False` launch
#: (jarvis_chatbot_web.py:620) is the visible launch THESE FOUR reach.
#:
#: THAT IS NOT A BACKEND-WIDE CLAIM, and it must not be read as one.
#: `jarvis_browser_control.py` has its own visible launch by default too:
#: `_HEADLESS = False` (:1284) and `launch(headless=_HEADLESS, ...)` (:1460),
#: with the comment at :1273-1284 saying the default "stays a visible window".
#: No current default-run suite reaches it with a real page - its one live
#: suite switches it off (test_browser_control_live.py:139, `B._HEADLESS =
#: True`) and the other suites fake the page - but the completeness pin in
#: `test_browser_test_guard.py` covers only direct importers of
#: `jarvis_chatbot_web`, so a NEW suite that drives `jarvis_browser_control`
#: visibly would not be caught by it. This list is the four that open a window
#: in the default run today, not every visible-browser suite the backend could
#: ever have.
#:
#: A DEFAULT RUN DOES NOT RUN THEM. Each is skipped by name, with the reason,
#: unless VISIBLE_BROWSER_ENV=1. That is the second, independent layer: each
#: suite also reads the same variable itself and prints one SKIPPED sentence
#: before it starts anything, so a bug in either layer cannot put a window on
#: the owner's screen. A skip is printed as `skip` and counted separately, and
#: is never a pass.
VISIBLE_BROWSER_ENV = "JARVIS_ALLOW_VISIBLE_BROWSER_TESTS"
VISIBLE_BROWSER_SUITES = {
    "test_chatbot_gemini.py": "it opens a real, VISIBLE browser window (Gemini)",
    "test_chatbot_sites.py": "it opens a real, VISIBLE browser window per chatbot site",
    "test_handoff.py": "it opens a real, VISIBLE browser window (the hand-off page)",
    "test_support_widget.py": "it opens a real, VISIBLE browser window (a support chat)",
}

#: SUITES THAT MAY LEGITIMATELY RUN NO CHECK (2026-10-27). A suite that exits
#: 0 having skipped every check it owns proves nothing, so it is reported as
#: `NO-CHECKS` - neither a pass nor a skip - and it is a FAILURE by default: a
#: skip guard that stopped matching, or a loop over an empty list, would
#: otherwise turn a whole suite into a green line forever. These three are the
#: exception, because what they need is OPTIONAL on a developer machine (the
#: required backend job installs all three packages, so there they really run):
#:
#:   * test_browser_control_live.py - needs playwright. The Ubuntu backend job
#:     installs no Playwright (the browser page tests live in the frontend
#:     job), so there it prints one SKIP line and exits 0 today.
#:   * test_mesh_tls_cert.py - needs cryptography, optional at run time; with
#:     no cryptography it skips all 16 checks and says so.
#:   * test_pillow_pictures.py - needs Pillow, optional at run time (four
#:     shipped modules load it by name and the backend starts without it);
#:     with no Pillow it names the whole-suite skip and exits 0.
#:
#: A suite whose checks are skipped for ANY OTHER reason is NOT exempt. Add an
#: entry here only with a one-line reason, never to silence a red.
ZERO_CHECK_ALLOWED = {
    "test_browser_control_live.py":
        "needs playwright, which is optional and which the backend job leaves out",
    "test_mesh_tls_cert.py":
        "needs cryptography, optional at run time (the backend job installs it)",
    "test_pillow_pictures.py":
        "needs Pillow, optional at run time (the backend job installs it)",
}


def visible_browser_opted_in(env=None) -> bool:
    """True only when the operator has explicitly asked for a visible window.

    Exactly "1", the same rule every guarded suite reads, so the runner and the
    suites cannot disagree about what an opt-in is. `env` is for a caller with
    its own mapping; it defaults to os.environ.
    """
    env = os.environ if env is None else env
    return str(env.get(VISIBLE_BROWSER_ENV) or "").strip() == "1"


CONFIG_NAME = "jarvis-framework.toml"

# --- where a run's own folders live, and how they are taken away ------------
#
# WHY THIS IS NOT JUST mkdtemp AND A rmtree AT THE END (2026-10-11). A run used
# to leave TWO folders under %TEMP% - `jarvis-staged-backend-<random>` (a copy
# of every shipped module, measured at 10 MB) and `jarvis-suite-state-<random>`
# (the config folder and audit log the suites write, 64 MB in one measured
# case) - and both rmtree calls sat at the END of main(), outside any
# try/finally. A run that was killed, Ctrl-C'd, cancelled by CI, or wedged
# until the 900-second suite timeout skipped both. Twenty thousand of them
# reached 123.6 GB and took C: from 165 GB free down to 34 GB. A 131 GB hand
# cleanup followed; the mechanism did not change.
#
# It was worse than those two folders. EVERY suite in this folder makes its own
# `jarvis-<suite>-<random>` at import time with `tempfile.mkdtemp` (296 of them
# do today - `jarvis-enrol-`, `jarvis-big-model-`, `jarvis-referee-`, ...) and
# most never remove it, which is one folder per suite per run: the bulk of the
# twenty thousand. Fixing only the runner's own two folders would have left
# that in place, so the sweep root below owns the suites' scratch as well.
#
# Four things hold now:
#
#   1. ONE FOLDER PER RUN. The staged backend, the config/audit state and the
#      suites' own scratch all live inside a single `jarvis-sweep-<random>`
#      root, removed in a `finally` however main() leaves - a normal return, a
#      failed suite, or an exception.
#
#   2. THE SUITES' SCRATCH GOES THERE TOO. The children are given TMPDIR, TEMP
#      and TMP pointing into the sweep root; `tempfile.gettempdir()` reads
#      exactly those, so every `mkdtemp` a suite makes lands inside the root
#      and goes with it.
#
#   3. A REAPER FOR WHAT A KILL LEAVES. A terminated process runs no `finally`
#      at all, so a killed run's root stays. Each root carries an `_owner.json`
#      marker (pid, start time, kind) and the run that made it holds an
#      exclusive LOCK on that file for its whole life - the operating system
#      drops the lock when the process ends, however it ends. The start of
#      every run reaps roots whose lock can be taken (so no run is using them)
#      and which are older than REAP_AFTER.
#
#   4. A LIVE FOLDER IS NEVER TOUCHED. A folder whose lock is still held
#      belongs to a running sweep, and deleting its staging underneath it is a
#      worse bug than the litter. Two sweeps really were running when this was
#      written (both on the old code, both holding a staged-backend and a
#      suite-state folder), which is why the lock, and not the pid, is what
#      answers "is the owner still alive".
SWEEP_PREFIX = "jarvis-sweep-"
#: A DIRECT run's root - `python backend/<suite>.py` with no runner - claimed by
#: `_where._stage_a_direct_run()` with the same marker and lock as a sweep, so
#: one mechanism covers both and a killed direct run is reapable by the reaper
#: below. It is one folder per direct process instead of one per suite.
DIRECT_PREFIX = "jarvis-direct-"
STAGE_PREFIX = "jarvis-staged-backend-"
BACKEND_NAME = "backend"
STATE_NAME = "state"
SUITE_TEMP_NAME = "tmp"
#: The throwaway HOME under this run's state folder, and the two names every
#: module in this backend reads it by. See private_state.
HOME_NAME = "home"
HOME_ENVS = ("OPENJARVIS_HOME", "JARVIS_HOME")
#: The ONE escape hatch for a suite that genuinely needs the owner's real home
#: (his databases, his inbox): `JARVIS_TESTS_USE_REAL_HOME=1`. Never the
#: default, and a run that sets it SAYS SO in its header.
REAL_HOME_ENV = "JARVIS_TESTS_USE_REAL_HOME"
#: Where the suites' audit log goes: the variable jarvis_framework.log_dir()
#: honours over both the config's `[logging].log_directory` and CONFIG_DIR/logs
#: (2026-10-20). It is not covered by the config-folder move: the config shipped
#: beside the modules sets log_directory = "~/.openjarvis/logs/", so a suite that
#: only redirects its config folder (or its approvals DB) appended synthetic
#: events to the OWNER's real log. Every suite gets a per-run temporary folder
#: through this variable; the logging-machinery suites are exempt below.
LOG_DIR_ENV = "JARVIS_LOG_DIR"
#: The suites that test the audit-log machinery ITSELF, or read audit lines back
#: from a log folder they choose. They set up and read their own log directory
#: (by patching load_framework, or by testing this runner's isolation), so the
#: runner leaves JARVIS_LOG_DIR out of their environment - otherwise they would
#: be reading a directory nobody set up. Each of them ALSO clears the variable
#: itself, because apply-patches.ps1 runs every suite directly with the
#: variables `--state-env` printed, which include JARVIS_LOG_DIR and cannot be
#: varied per suite. A new suite that reads audit lines back from its own folder
#: joins this list, the same way it would join NEEDS_OWNER when it needs a file
#: from the owner's PC; the full sweep is what catches an omission.
LOG_MACHINERY_SUITES = {
    "test_log_retention.py": "tests prune_logs()/log_dir() against a folder it builds",
    "test_rebuilt.py": "tests audit_log()/log_dir() by patching load_framework",
    "test_suite_state.py": "tests this runner's own state isolation; its CONTROL "
                           "runs are unisolated on purpose",
    # Discovered by the first full sweep after the switch was added (2026-10-20):
    # these two read the audit lines back from a log folder they choose
    # themselves, so the override made them look in the wrong place.
    "test_skill_discovery.py": "reads audit lines back from a log folder it chooses",
    "test_memory_erase.py": "reads audit lines back from a log folder it chooses",
}
#: The model loaders must be OFFLINE in every suite's environment (2026-10-18).
#: test_attention_phrases.py says "no model, no network" in its own header, but
#: importing the memory store taught the old memory library to fetch its 5 model files for a
#: cold cache, and under the patcher the suite sat for 900 s. A suite cannot be
#: fixed from here, but a stray download can be made to FAIL AT ONCE instead of
#: hanging: huggingface_hub (and the transformers/datasets libraries) honour
#: these, and the telemetry switches are the same names and values
#: jarvis_child_env and jarvis_voices already send. Forced, not defaulted: this
#: is a hermetic-run rule, so a caller's `HF_HUB_OFFLINE=0` cannot switch it off
#: in a test run (it does not touch the owner's own environment, only `env`).
OFFLINE_ENVS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "ANONYMIZED_TELEMETRY": "False",
}
OWNER_MARKER = "_owner.json"
#: A marked folder - one this runner made - may be reaped once its owner is
#: gone and it is at least this old.
REAP_AFTER = 3600.0
#: A folder with NO marker (an older run's, from before markers existed) cannot
#: be asked about its owner at all, so age is the only proof available and it
#: has to be long: a suite is killed at 900 s and this is far beyond any sweep,
#: so nothing can still be writing into a folder this old.
REAP_AFTER_UNMARKED = 86400.0
#: What is even a candidate: a folder under the system temp folder whose NAME
#: is the shape this runner or a suite builds - `jarvis-<something>-<random>`,
#: where the random tail is the one `tempfile.mkdtemp` appends. Deliberately a
#: SHAPE and not a list of suite names: suites are added and removed constantly,
#: and a fixed list would stop protecting them the day after it was written.
#: The tail is 6+ characters of the alphabet mkdtemp uses and carries no dot, so
#: a data file that merely starts with `jarvis-` (jarvis-framework.toml) and a
#: folder with no random tail at all are both left alone - the rule only ever
#: claims the throwaway folders, never a name a person chose.
REAPABLE = re.compile(r"^jarvis-[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{6,}$")
#: This process's own wall-clock start, written into every marker so a reader
#: can tell one run's folder from the next run's.
_STARTED = time.time()

#: "N passed" / "N skipped" / "N failed" as a suite prints them at the end.
#: Looked up by the word, not by position: every harness in this folder prints
#: the three, but the older ones print them in a different order.
_SUMMARY = {"passed": re.compile(r"(\d+)\s+passed\b"),
            "skipped": re.compile(r"(\d+)\s+skipped\b"),
            "failed": re.compile(r"(\d+)\s+failed\b")}

#: What a reader counts by eye, for a suite that prints no summary at all:
#: `ok` and `FAIL` from check(), `skip` from skip() (or an older harness's own
#: "SKIP  <name>"). The word has to end there or be followed by a space or a
#: colon - test_topics.py has a real check named "skipped-this-week is a number
#: per topic", and counting a check as a skip would be this bug in reverse.
_LINE = {"passed": re.compile(r"^ok\b"),
         "skipped": re.compile(r"^skip(ped)?(?=[ \t:]|$)", re.I),
         "failed": re.compile(r"^FAIL\b")}

#: unittest's own summary, for the three suites built on it (test_rebuilt.py,
#: test_speech.py, test_thinking.py). Without this the three of them reported as
#: "0 passed, 0 skipped, 0 failed" - the same numbers a suite that printed
#: nothing at all gives, which is the one shape this runner must never confuse
#: with a pass. It matters two ways round: unittest exits 0 just as happily
#: having run NO tests (every method renamed away, or a TestCase that stopped
#: matching `unittest.main()`'s default), and a suite that prints nothing is
#: exactly the class `tools/check_vacuous_checks.py` exists for one level down.
#: unittest counts a skipped test inside "Ran N tests", so the passes are what
#: is left after the skips and the failures, not the total on its own.
_UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_UNITTEST_BAD = re.compile(r"^FAILED \(([^)]*)\)", re.M)
_UNITTEST_SKIPPED = re.compile(r"skipped=(\d+)")

#: A line that LOOKS like a suite's own summary: a count, then "passed" or
#: "failed". Used to find the summary anywhere in the output rather than only in
#: its last four lines - see `_last_summary_line`.
_SUMMARY_LINE = re.compile(r"^\s*\d+\s+(?:passed|failed)\b")

#: The line a Python traceback ENDS on, matched at column 0 where Python writes
#: it: `PermissionError: [WinError 5] Access is denied: ...`,
#: `jarvis_backup.RestoreError: could not replace a file (PermissionError)`.
#: The `Traceback (most recent call last):` header says only that something
#: went wrong. Until 2026-10-25 that header was the whole of what a failed
#: suite echoed - the reason itself is on stderr, one of these lines, and it
#: was dropped, so a red CI run named the suite and never the cause.
_EXC_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit)\b.*$")


def _last_summary_line(out: str) -> str:
    """The last line of `out` that carries a suite's own summary, or "".

    WHY NOT THE LAST FOUR LINES. That is what this used to read, and a suite
    that prints a traceback AFTER its summary pushed the summary out of the
    window: `test_news.py` failed with a traceback on stderr and the runner
    printed "FAIL test_news.py (exit 1) 65 passed, 0 skipped, 0 failed" beside
    it. The verdict was still right - it comes from the exit code - but the
    numbers were wrong, and the numbers are what a reader believes. The last
    line that looks like a summary is the suite's own last word whatever
    happens after it."""
    last = ""
    for line in out.splitlines():
        if _SUMMARY_LINE.match(line):
            last = line
    return last


def counts(out: str) -> dict:
    """{'passed': n, 'skipped': n, 'failed': n} for one suite's output.

    The suite's OWN final line is believed when it has one: it knows what it
    counted, and a `skip()` no longer lands in its "passed". A unittest suite
    is believed through unittest's own summary. Only a suite that prints
    neither is counted from its own lines."""
    summary = _last_summary_line(out)
    got = {}
    for word, pat in _SUMMARY.items():
        m = pat.search(summary)
        got[word] = int(m.group(1)) if m else None
    if got["passed"] is not None and got["failed"] is not None:
        return {"passed": got["passed"], "skipped": got["skipped"] or 0,
                "failed": got["failed"]}
    m = _UNITTEST_RAN.search(out)
    if m:
        total = int(m.group(1))
        bad = _UNITTEST_BAD.search(out)
        failed = 0
        if bad:
            for _kind, number in re.findall(r"(failures|errors)=(\d+)", bad.group(1)):
                failed += int(number)
        skipped = _UNITTEST_SKIPPED.search(out)
        skipped = int(skipped.group(1)) if skipped else 0
        return {"passed": max(0, total - skipped - failed), "skipped": skipped,
                "failed": failed}
    counted = {w: 0 for w in _LINE}
    for line in out.splitlines():
        for word, pat in _LINE.items():
            if pat.match(line):
                counted[word] += 1
                break
    return counted


def _config_the_suites_would_read(env: dict, backend: Path):
    """The jarvis-framework.toml jarvis_framework.config_path() would find for
    a suite, BEFORE the config folder is moved: the override, the config
    folder, beside the modules, one folder up - and last this repository's
    rebuilt/ copy, which is what a suite that imports rebuilt/ directly
    (test_voice_enroll, test_speech, ...) finds beside jarvis_framework.py.
    Its log_directory is ~/.openjarvis/logs/ too."""
    raw = env.get("JARVIS_FRAMEWORK_TOML")
    home_cfg = env.get("OPENJARVIS_CONFIG_DIR") or env.get("JARVIS_CONFIG_DIR")
    cfg_dir = Path(os.path.expanduser(home_cfg)) if home_cfg \
        else Path(os.path.expanduser("~")) / ".openjarvis"
    for c in (Path(os.path.expanduser(raw)) if raw else None, cfg_dir / CONFIG_NAME,
              backend / CONFIG_NAME, backend.parent / CONFIG_NAME,
              HERE / "rebuilt" / CONFIG_NAME):
        if c is not None and c.is_file():
            return c
    return None


def _with_log_directory(toml: str, where: Path) -> str:
    """`toml` with [logging].log_directory set to `where` - a TOML literal
    string, forward slashes, so a Windows path needs no escaping."""
    line = f"log_directory = '{where.as_posix()}'"
    lines = toml.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "[logging]")
    except StopIteration:
        return toml.rstrip("\n") + f"\n\n[logging]\n{line}\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
               len(lines))
    for i in range(start + 1, end):
        if lines[i].split("=", 1)[0].strip() == "log_directory":
            lines[i] = line
            break
    else:
        lines.insert(start + 1, line)
    return "\n".join(lines) + "\n"


def private_state(env: dict, backend: Path, where: Path) -> dict:
    """`env`, changed so the suites write their state under `where`, never
    into the owner's real config folder or real HOME.

    Several suites run real code that writes: the audit log (131 fake
    events - "voice.training.decided", "wiki.asked", "task.stop" - landed
    in ~/.openjarvis/logs in one run), approval queues, switch files. That
    folder is jarvis_framework._config_dir(): OPENJARVIS_CONFIG_DIR, then
    JARVIS_CONFIG_DIR, then ~/.openjarvis. Both variables now point at a
    temporary folder.

    That alone is not enough on the owner's PC: the config beside the
    modules sets [logging].log_directory = "~/.openjarvis/logs/", which the
    audit log honours over the config folder. So that config is copied into
    the temporary folder with only log_directory changed, and
    JARVIS_FRAMEWORK_TOML points at the copy. A suite that sets
    JARVIS_FRAMEWORK_TOML itself (test_rebuilt, test_router_private_terms)
    still reads the file it chose.

    THE LOG GETS ITS OWN SWITCH AS WELL (2026-10-20, night audit). The config
    copy is one path to the audit log; a suite that does not go through it - one
    that reads another config, or is run directly with only some variables set -
    still honoured log_directory = "~/.openjarvis/logs/" and appended synthetic
    events to the owner's REAL log (191 gate.asked, 180 backup.restore.card, 420
    media_index.deleted, measured 22:00-23:22). So this function now also sets
    JARVIS_LOG_DIR, which jarvis_framework.log_dir() honours over the config and
    over CONFIG_DIR/logs, to `<state>/logs` - the same folder the config copy
    names, through a switch that does not depend on which config a suite reads.
    `suite_env()` removes it for the suites that test the logging itself.

    AND THE CONFIG FOLDER IS NOT THE HOME. `OPENJARVIS_HOME` is checked
    BEFORE that rule, by the modules that keep the owner's own data
    (jarvis_receipts, jarvis_file_guardian, jarvis_chat_log, ...), and a
    suite that never sets it falls through to ~/.openjarvis - the owner's
    real databases and inbox. During a patcher run that is data a check can
    read, and a write can change. So each run gets a throwaway
    `<state>/home` and BOTH names point at it. That is the default and stays
    the default; a suite that genuinely needs the real home is run with
    JARVIS_TESTS_USE_REAL_HOME=1, and the run's header says so in plain
    words. Cleanup is the run's own: the home is under `where`, which lives
    under the run root removed in main()'s finally (and, for --state-env,
    under the state folder apply-patches.ps1 removes in its finally).

    PYTHONIOENCODING is set here too, and it is not about state: it is a
    bug this runner had on Windows. A Windows console (and a pipe) defaults
    Python's stdout to the ANSI code page, cp1252 here, and 56 of the
    suites print a non-ASCII character that cp1252 cannot encode - the
    Cyrillic host test_youtube.py refuses, an em dash, a curly quote. The
    print raises UnicodeEncodeError, the suite exits 1, and it is reported
    as a FAILING SUITE when the check itself passed. test_youtube.py failed
    that way in both the 15:48 and the 19:09 runs on 2026-10-03, for a link
    its parser had correctly refused. jarvis_voices.py:2490 and
    backend/README.md's own preflight line already set this variable for
    the same reason; the runners simply never did.

    THE MODEL LOADERS ARE OFFLINE HERE TOO (2026-10-18). `OFFLINE_ENVS` is
    applied to every run's environment, so a suite that accidentally imports a
    model loader stops at once instead of fetching a model (the 900 s
    fastembed hang test_attention_phrases.py caused under the patcher). It is
    outside the home hatch on purpose: the hatch is about WHERE state lives,
    never about letting a download through."""
    out = dict(env)
    out["PYTHONIOENCODING"] = "utf-8"
    out.update(OFFLINE_ENVS)
    cfg = where / "config"
    logs = where / "logs"
    cfg.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    out[LOG_DIR_ENV] = str(logs)
    found = _config_the_suites_would_read(env, backend)
    out["OPENJARVIS_CONFIG_DIR"] = str(cfg)
    out["JARVIS_CONFIG_DIR"] = str(cfg)
    if str(env.get(REAL_HOME_ENV) or "").strip() == "1":
        # The escape hatch. The caller asked for the real home; nothing here
        # touches it, and the header of a run says "NOT hermetic".
        pass
    else:
        home = where / HOME_NAME
        home.mkdir(parents=True, exist_ok=True)
        for name in HOME_ENVS:
            out[name] = str(home)
    if found is not None:
        copy = cfg / CONFIG_NAME
        copy.write_text(_with_log_directory(found.read_text(encoding="utf-8"), logs),
                        encoding="utf-8")
        out["JARVIS_FRAMEWORK_TOML"] = str(copy)
    return out


def suite_env(name: str, env: dict) -> dict:
    """`env` for ONE suite, with the audit-log isolation removed for the suites
    that test the logging machinery itself.

    `private_state()` gives the whole run one temporary log folder through
    JARVIS_LOG_DIR. That is right for every suite except the ones in
    LOG_MACHINERY_SUITES: they choose their own log directory and would then be
    reading one nobody set up (test_log_retention patches load_framework; the
    runner would override the patch). They also clear the variable at import, so
    the patcher's direct loop behaves the same way; this is the runner's own
    half of that one rule. A suite not in the set gets the dict unchanged, so
    the common path allocates nothing."""
    if name not in LOG_MACHINERY_SUITES:
        return env
    out = dict(env)
    out.pop(LOG_DIR_ENV, None)
    return out


def home_words(env: dict) -> str:
    """The header line saying where the suites' HOME points - and saying it out
    loud when that is the owner's real home. Never silent about the hatch."""
    home = str(env.get("OPENJARVIS_HOME") or "")
    if str(env.get(REAL_HOME_ENV) or "").strip() == "1":
        return (f"home: {home or 'the real home'}  (NOT hermetic: "
                f"{REAL_HOME_ENV}=1 - the suites may read and write real data)")
    if home:
        return (f"home: {home}  (throwaway: the suites' OPENJARVIS_HOME and "
                f"JARVIS_HOME, not yours)")
    return (f"home: the owner's REAL home  (NOT hermetic: {REAL_HOME_ENV}=1 - "
            f"the suites may read and write real data)")


def stage(root: Path = None) -> Path:
    """A folder holding every module apply-patches.ps1 ships, flattened.

    With `root`, it is made INSIDE that folder, so it goes when the run's own
    folder goes (see SWEEP_PREFIX above). With no root it is its own %TEMP%
    folder, which is what the suites that stage a backend for themselves ask
    for - `test_suite_state.py` calls `stage()` twice and removes each one
    itself, so it must keep working exactly as it did."""
    if root is None:
        d = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX))
    else:
        d = root / BACKEND_NAME
        d.mkdir(parents=True, exist_ok=True)
    for rel in _where.SHIPPED:
        shutil.copy2(HERE / rel, d / rel.rsplit("/", 1)[-1])
    return d


def _lock_nb(fd: int) -> bool:
    """An exclusive, non-blocking lock on an open file: True if we got it.

    `msvcrt` on Windows and `fcntl` everywhere else, both standard library.
    This is what makes "is the owner of this folder still running?" answerable.
    The owner holds the lock for its whole life and the operating system drops
    it when that process ends - returned, raised, or killed outright - so the
    answer survives every way a run can die, and cannot be fooled by a pid
    being reused (which is why a pid alone is not enough).

    If neither module is importable the answer is False, "still owned", so a
    folder is never removed on a guess."""
    try:
        import msvcrt
    except ImportError:
        pass
    else:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    try:
        import fcntl
    except ImportError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def claim(root: Path, kind: str):
    """Write `root`'s owner marker and lock it; the descriptor is returned.

    THE DESCRIPTOR MUST STAY OPEN for as long as the folder is to count as
    live, and must be CLOSED before the folder is removed - on Windows a file
    this process still holds open cannot be deleted, so removing the folder
    first would silently leave the marker (and the folder) behind. Returns None
    if the lock could not be taken, which means someone else owns it."""
    info = {"pid": os.getpid(), "started": _STARTED, "kind": kind, "folder": root.name}
    marker = root / OWNER_MARKER
    marker.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fd = os.open(str(marker), os.O_RDWR)
    if not _lock_nb(fd):
        os.close(fd)
        return None
    return fd


def _owner_gone(folder: Path) -> bool:
    """True only when `folder` carries a marker whose lock can be taken, which
    means the run that made it has ended. A folder with no marker, or one whose
    marker cannot be opened, is NOT gone - never a reason to delete."""
    marker = folder / OWNER_MARKER
    if not marker.is_file():
        return False
    try:
        fd = os.open(str(marker), os.O_RDWR)
    except OSError:
        return False
    try:
        return _lock_nb(fd)
    finally:
        os.close(fd)            # releases the lock we just took, if we took one


def _older_than(folder: Path, seconds: float) -> bool:
    """True when nothing has changed in `folder` for `seconds`.

    THE MODIFICATION TIME, AND NOT THE CREATION TIME TOO (measured 2026-10-11).
    `st_ctime` reads as the creation time on Windows and as the inode-change
    time on Linux, and on both it is set to NOW by `os.utime` - so a rule
    demanding BOTH timestamps be old is a rule no test can set up, which makes
    it a guard that is never exercised and fails silently the day it matters.
    mtime is also the better question: "has anything touched this folder
    recently?" is exactly what says whether a run might still be using it, and
    it is the one timestamp a person with `touch -t` can reproduce.

    The lock, not this, is what protects a LIVE run's folder (see
    `_owner_gone`); this is the second gate, and the only one available for a
    folder from a run old enough to have no marker."""
    try:
        return (time.time() - folder.stat().st_mtime) > seconds
    except OSError:
        return False


def reap_orphans(temp=None, keep=()) -> list:
    """Remove staging folders an ended run left under the temp folder, and name
    the ones removed.

    Only a DIRECTORY directly under the temp folder, whose name is the shape
    this runner or a suite builds (REAPABLE), is ever considered - never a
    symlink, never anything else's folder. A marked folder goes only when its
    lock can be taken (no run is using it) AND it is older than REAP_AFTER; a
    folder with no marker, left by an older run, must be older than
    REAP_AFTER_UNMARKED, because there is nothing to ask about its owner. The
    current run's own folder is passed in `keep` and is never a candidate.

    Nothing here raises. A folder that cannot be listed or removed is left
    alone, because the only thing at stake is litter."""
    temp = Path(temp) if temp is not None else Path(tempfile.gettempdir())
    keep = {str(Path(k)) for k in keep}
    gone = []
    try:
        entries = sorted(temp.iterdir())
    except OSError:
        return gone
    for d in entries:
        try:
            if not d.is_dir() or d.is_symlink() or not REAPABLE.match(d.name):
                continue
            if str(d) in keep:
                continue
            marked = (d / OWNER_MARKER).is_file()
            if not _older_than(d, REAP_AFTER if marked else REAP_AFTER_UNMARKED):
                continue
            if marked and not _owner_gone(d):
                continue                     # a live run: never touched
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                gone.append(d.name)
        except OSError:
            continue
    return gone


def suite_temp_env(env: dict, root: Path) -> dict:
    """`env` with the suites' OWN scratch pointed inside this run's folder.

    Every suite here makes `jarvis-<suite>-<random>` at import time with
    `tempfile.mkdtemp` and most never remove it. `tempfile.gettempdir()` reads
    TMPDIR, then TEMP, then TMP, so pointing all three into the sweep root is
    what keeps those out of the machine's real temp folder - and so out of the
    count that reached 20,633. The folder is made here because Python falls
    back to the WORKING DIRECTORY for a temp directory it cannot write to,
    which would put a suite's scratch inside the checkout instead."""
    tmp = root / SUITE_TEMP_NAME
    tmp.mkdir(parents=True, exist_ok=True)
    out = dict(env)
    for name in ("TMPDIR", "TEMP", "TMP"):
        out[name] = str(tmp)
    return out


def remove_tree(path: Path, what: str) -> None:
    """Remove `path`, and SAY SO if anything is left behind.

    `shutil.rmtree(..., ignore_errors=True)` is how 123.6 GB went unnoticed: a
    folder a killed child still holds open is not removed and nothing says so.
    One retry first (the handle is usually gone a moment later), then a plain
    line naming what stayed, so a leak can never again be silent."""
    for _ in range(2):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.2)
    try:
        left = sorted(p.name for p in path.iterdir())
    except OSError:
        left = []
    print(f"NOTE  {what} could not be fully removed: {path}"
          + (f" (still holds: {', '.join(left[:5])})" if left else "")
          + ". A later run's reaper removes it once nothing holds it open.")


def suite_result(name: str, took: str, code, stdout, stderr, why="") -> tuple:
    """How one finished suite is reported: ("ok"|"FAIL", counts, the line, the
    lines to echo under it). Every suite is reported, including the one that
    printed nothing at all - which is why `stdout`/`stderr` may be None and
    are read as empty text, never assumed to be a string. That None is not
    hypothetical: it is what subprocess leaves behind when a suite is killed
    by a signal, or when the spawn itself fails. Reading it as a string
    raised TypeError at `r.stdout + r.stderr` and ended the whole sweep, so
    the results of every suite after it were never printed.

    `why` is the runner's own reason for a suite that never produced a line of
    its own - a spawn that raised, say. The suite's counts are honestly zero,
    so the reason is what says the suite did not run at all.

    A suite that exits 0 having reported NO checks at all is the one shape this
    runner must never call a pass. It cannot be told apart from a suite whose
    checks all vanished - a loop over an empty list, a guard that can never be
    true, a main() that returns before printing - and the browser suite found on
    2026-10-05 did exactly that: it exited 0 having run nothing, and stayed
    green. So exit 0 with every count zero is reported as failed, and the reason
    says which shape it was.

    Only exit 0 is "ok". Anything else is reported as failed - including a
    suite the runner could not read an exit code for at all, which is why
    the check is `code == 0` and not `code == 0 or code is None`."""
    out = (stdout or "") + (stderr or "")
    n = counts(out)
    said = f"{n['passed']} passed, {n['skipped']} skipped, {n['failed']} failed"
    silent = code == 0 and not any(n.values())
    if silent:
        code = "printed no checks"
    # A suite that exits 0 having run NO non-skipped check proves nothing: it is
    # the whole-suite version of `check("SKIP ...", True)`, the shape this
    # runner exists to distrust. It is reported as NO-CHECKS - neither "ok" nor
    # "skip" - and, unless it is named on the allowlist above, it FAILS.
    zero = code == 0 and n["passed"] == 0 and n["failed"] == 0 and n["skipped"] > 0
    if zero and name in ZERO_CHECK_ALLOWED:
        return ("zero", n,
                f"NO-CHECKS  {name:<34} {took}  {said}  (every check was skipped: "
                f"{ZERO_CHECK_ALLOWED[name]})", [])
    if zero:
        line = (f"FAIL  {name:<34} {took}  (exit 0)  {said}  "
                f"(every check was skipped - no check ran)")
        skips = [l for l in out.splitlines() if _LINE["skipped"].match(l)]
        echo = ["      it ran NO checks: every check it has was skipped, and a "
                "skip is never a pass."]
        echo += ["      " + l for l in skips[:6]]
        if len(skips) > 6:
            echo.append(f"      ... and {len(skips) - 6} more skip line(s)")
        echo.append("      If this machine genuinely cannot run it, add it to "
                    "ZERO_CHECK_ALLOWED with the reason; otherwise one of its skip "
                    "guards has just hidden every check it owns.")
        return "FAIL", n, line[:200], echo
    if code == 0:
        # The numbers are shown whenever they are not already on the suite's
        # own last line: a suite that skipped something (its own line would
        # have said so), or one that prints no "N passed" summary of its own -
        # the three unittest suites, and the older harnesses counted from
        # their own `ok` lines. Otherwise a reader sees
        # `ok  test_speech.py  2.0s` with no idea whether 25 checks ran or
        # none did, which is the blind spot this runner closed.
        tail = "\n".join(out.strip().splitlines()[-4:])
        own_summary = _SUMMARY["passed"].search(tail)
        note = f"  {said}" if (n["skipped"] or not own_summary) else ""
        return "ok", n, f"ok    {name:<34} {took}{note}", []
    if not out.strip() and not why:
        # a suite that said nothing is still reported in full: which suite,
        # what it exited with, and that there was no output to quote.
        said += "  (no output)"
    line = f"FAIL  {name:<34} {took}  (exit {code})  {said}"
    echo = [f"      {why}"] if why else []
    if silent:
        echo.append("      it exited 0 having printed no `ok`, `FAIL` or `skip` line "
                    "and no summary - so nothing here proves that any check ran. A "
                    "check that cannot fail, one level up.")
    echo += ["      " + l for l in out.splitlines()
             if l.startswith("FAIL") or "Traceback" in l or "failed:" in l
             or _EXC_LINE.match(l)]
    # One GitHub annotation is built from this line, and a spawn failure
    # carries the operating system's whole sentence. Capped so the suite's
    # name and its exit code are never pushed out of the annotation; the full
    # text is echoed under the line.
    return "FAIL", n, line[:200], echo


# ---------------------------------------------------------------------------
#   The update lock - never run a suite sweep beside a live backend update
# ---------------------------------------------------------------------------
#
# An update patches the backend and then runs these very suites; a second
# sweep beside it (or the desktop's watchdog restarting the backend mid-run)
# starves the CPU and doubles the wall time a real update measured at 2h8m.
# The update tool writes `update-in-progress.lock` in the folder Jarvis keeps
# its own data in; this runner refuses to start while that lock is VALID
# (live pid, fresh heartbeat, under the 3-hour ceiling) unless the caller is
# the update's own suite phase: `--ignore-update-lock` or
# JARVIS_INSIDE_PATCHER=1. The rules and the reading live in ONE place,
# `tools/update_backend.py`'s lock section, so the tool, this runner and the
# desktop app cannot disagree about what "stale" means.
LOCK_BYPASS_ENV = "JARVIS_INSIDE_PATCHER"
LOCK_BYPASS_FLAG = "--ignore-update-lock"

#: The explicit opt-in to run against the backend folder `JARVIS_BACKEND`
#: names. A DEFAULT run never reads that variable - it is set for the owner's
#: Windows account on this PC (to the live backend), so reading it meant a
#: routine test run silently became a live-code run. See `_named_backend`.
USE_ENV_BACKEND_FLAG = "--use-env-backend"
#: The explicit way to name a backend folder on the command line, without
#: relying on any environment variable. What the updater uses, so the update's
#: own proof run can never be redirected by an ambient variable either.
BACKEND_PATH_FLAG = "--backend-path"
#: The patcher's own subcommand: print the environment its suite loop needs.
STATE_ENV_FLAG = "--state-env"

#: `--help` prints exactly this and exits 0, before the update lock is read and
#: before anything is staged. Deliberately short.
USAGE = """\
usage: run_suites.py [test_name.py ...] [options]

  (no names)            run every backend suite
  test_ui_control.py    run exactly the suite(s) named - BARE file names only
  --help                print this and exit 0

options:
  --jobs N              run N suites at once (default 1, what CI uses)
  --backend-path DIR    run against the backend folder DIR
  --use-env-backend     run against whatever JARVIS_BACKEND names
  --ignore-update-lock  run even while a backend update holds the lock
  --state-env DIR       print the suite-state environment for DIR

A path is not a suite name: `backend/test_x.py` is refused, not ignored.
The four suites that open a real, VISIBLE browser window are skipped, with
their reason, unless JARVIS_ALLOW_VISIBLE_BROWSER_TESTS=1 is set.
"""


def suite_arguments(args) -> tuple:
    """The BARE suite names on the command line; anything else is a UsageError.

    WHY (measured 2026-10-26, twice in one day). This runner used to keep every
    argument that started with "test_" and silently DROP the rest, so
    `run_suites.py backend/test_x.py` - the spelling a person or an agent
    reaches for - named no suite and ran the WHOLE fleet instead. Two agents
    started the full sweep by accident that day. A typo must stop the run, not
    widen it, so a path or an unknown flag is refused before the backend is
    even staged.
    """
    names = []
    for arg in args:
        if arg.startswith("-"):
            raise UsageError(
                f"{arg} is not an option this runner knows (a suite is named by "
                f"its bare file name, e.g. test_ui_control.py). No suite was run.")
        if "/" in arg or "\\" in arg:
            bare = arg.replace("\\", "/").rsplit("/", 1)[-1]
            hint = (bare if bare.startswith("test_") and bare.endswith(".py")
                    else "test_ui_control.py")
            raise UsageError(
                f"{arg} is a path, not a suite name. Name the suite by its bare "
                f"file name instead, e.g. {hint}. No suite was run.")
        if arg.startswith("test_") and not arg.endswith(".py"):
            raise UsageError(
                f"{arg} is not a suite file name - add .py, e.g. {arg}.py. "
                f"No suite was run.")
        if not arg.startswith("test_") or not arg.endswith(".py"):
            raise UsageError(
                f"{arg} is not a suite name. Name a suite by its bare file name, "
                f"e.g. test_ui_control.py. No suite was run.")
        names.append(arg)
    return tuple(names)


class UsageError(ValueError):
    """A command line that cannot be honoured; `__main__` prints it and exits 2."""


def _named_backend(use_env_backend: bool = False, backend_path=None):
    """The backend a run must use, or None meaning "stage a throwaway copy".

    THE DEFAULT IS HERMETIC. `JARVIS_BACKEND` is set for the owner's Windows
    account on this PC, pointing at the LIVE backend folder, so a plain
    `python -B backend/run_suites.py` used to run the suites against live code
    without the person typing anything. This pops that ambient value and
    returns None, so the caller stages its usual copy - and it prints one line
    when it did, because silently ignoring a setting is its own surprise.

    `--use-env-backend` asks for the ambient value explicitly;
    `--backend-path DIR` names the folder outright (the updater uses this, so
    not even a changed environment variable can redirect an update's proof
    run). Passing both is refused: they can only name different folders.
    """
    if use_env_backend and backend_path:
        raise UsageError(
            f"{USE_ENV_BACKEND_FLAG} and {BACKEND_PATH_FLAG} name the backend two "
            "ways; pass one of them")
    if backend_path:
        named = Path(os.path.expanduser(str(backend_path))).resolve()
        if not named.is_dir():
            raise UsageError(f"{BACKEND_PATH_FLAG} {backend_path!r} is not a folder")
        print(f"[run_suites] LIVE MODE: running against un-staged backend at "
              f"{named} ({BACKEND_PATH_FLAG})")
        return named
    if use_env_backend:
        ambient = (os.environ.get("JARVIS_BACKEND") or "").strip()
        if not ambient:
            raise UsageError(
                f"{USE_ENV_BACKEND_FLAG} was given but JARVIS_BACKEND is not set; "
                f"pass {BACKEND_PATH_FLAG} DIR or set JARVIS_BACKEND")
        named = Path(os.path.expanduser(ambient)).resolve()
        if not named.is_dir():
            raise UsageError(
                f"JARVIS_BACKEND {ambient!r} is not a folder, so "
                f"{USE_ENV_BACKEND_FLAG} cannot use it")
        print(f"[run_suites] LIVE MODE: running against un-staged backend at "
              f"{named} ({USE_ENV_BACKEND_FLAG})")
        return named
    ambient = os.environ.pop("JARVIS_BACKEND", None)
    if ambient:
        print("[run_suites] Note: ignoring ambient JARVIS_BACKEND (staging "
              "hermetic copy; pass --use-env-backend to test live folder)")
    return None


def _update_lock_api():
    """`tools/update_backend.py`, imported for its lock section - or None.

    Guarded, and deliberately quiet when absent: a checkout without the update
    tool (or an import that fails) means this runner CANNOT know about a lock,
    and must not print a line claiming it checked for one. The lock is advisory;
    a missing reader is not a pass.
    """
    try:
        tools = HERE.parent / "tools"
        if not (tools / "update_backend.py").is_file():
            return None
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import update_backend          # noqa: PLC0415 - one guarded import
        return update_backend
    except Exception:                  # noqa: BLE001 - never a crash
        return None


def update_lock_refusal(ignore: bool = False) -> str:
    """The plain refusal when a VALID update lock is held, else "".

    `ignore` is `--ignore-update-lock`; the environment variable is the other
    way the update's own suite phase says who it is. A lock that is stale, a
    lock file that is unreadable, or no update tool to read it with all answer
    "" - nothing is enforced there, and nothing claims it was.
    """
    if ignore:
        return ""
    if str(os.environ.get(LOCK_BYPASS_ENV) or "").strip() == "1":
        return ""
    api = _update_lock_api()
    if api is None:
        return ""
    try:
        state = api.read_lock(api.lock_path())
    except Exception:                  # noqa: BLE001 - a read never blocks a run
        return ""
    return api.lock_refusal_words(state) if state.get("valid") else ""


def main(only=(), jobs: int = 1, ignore_update_lock: bool = False,
         use_env_backend: bool = False, backend_path=None) -> int:
    """Every suite, or only the ones named (`run_suites.py test_x.py ...`).

    Refuses immediately (exit 3, nothing staged, no suite started) while a
    valid backend-update lock is held; see `update_lock_refusal`. It asks AGAIN
    after the backend has been staged, immediately before the first suite, so a
    lock published while it was staging still stops it. The update's own suite
    phase passes `ignore_update_lock=True` (or sets JARVIS_INSIDE_PATCHER=1),
    which is the only thing that bypasses both checks.

    **The backend it runs against is chosen explicitly** (see
    `_named_backend`): by default a throwaway copy of the shipped modules is
    staged and the ambient `JARVIS_BACKEND` is ignored; `--use-env-backend`
    takes the ambient value and `--backend-path DIR` names a folder. A bad
    choice (`use_env_backend` for a non-folder, both at once) is a `UsageError`
    for the caller to print and exit 2; when `main` is called programmatically
    from the suites the refused value must not be silently replaced by a
    staged copy, so the error is raised rather than swallowed.

    `jobs` is how many suites to run at once: **1 by default, and that is what
    CI runs**, so the ordinary output is byte-for-byte what it has always been.
    The updater (the owner's own "how hard should this update work" choice) is
    the only caller that passes more; which suites run never changes, only how
    many are in flight.

    A name given on the command line that is not a suite here is a FAILURE, not
    an empty run: a sweep that prints "0 passed, 0 skipped, 0 failed" and exits
    0 for a mistyped name is the same lie one level up from the suites this
    runner exists to distrust (`backend/test_jobs.py` is named in the docs but
    lives only on the owner's PC, so a typo there was easy to make).

    THIS IS THE FOLDER THAT MUST NOT BE LEFT BEHIND. Everything the run makes
    lives inside `root`, and `root` is removed in a `finally` - so an exception
    (a suite's output that will not decode, a KeyboardInterrupt) cleans up
    exactly as a normal end does. A kill cannot run a `finally` at all, which
    is what the reaper at the start of `_sweep` is for: next time it finds this
    folder by its `_owner.json` marker, whose lock this process no longer
    holds, and removes it."""
    refusal = update_lock_refusal(ignore_update_lock)
    if refusal:
        # Immediately, before a folder is made: this is a "come back later",
        # not a run that tried and failed.
        print(f"REFUSED  {refusal}", file=sys.stderr)
        print("Not run: nothing was staged and no suite was started.", file=sys.stderr)
        return 3
    jobs = max(1, int(jobs))
    backend = _named_backend(use_env_backend, backend_path)
    root = Path(tempfile.mkdtemp(prefix=SWEEP_PREFIX))
    lock = claim(root, "sweep")
    try:
        return _sweep(root, only, jobs, ignore_update_lock, backend)
    finally:
        # The lock goes FIRST: on Windows a file this process still holds open
        # cannot be deleted, so the marker would keep the whole folder alive -
        # the exact silent leak this change exists to end.
        if lock is not None:
            os.close(lock)
        remove_tree(root, "this run's own staging folder")


def _suite_job(s: Path, backend: Path, env: dict) -> dict:
    """Run ONE suite and hand back what to print. Never prints.

    Split out of `_sweep` for `--jobs`: with more than one worker the jobs
    finish in a different order than the list, and a job that printed from
    inside a thread would interleave another suite's lines into its own
    failure block. The caller owns the printing. The result carries exactly
    the same four things a single-worker run printed, so the two paths cannot
    disagree about what a suite means."""
    if s.name in VISIBLE_BROWSER_SUITES and not visible_browser_opted_in(env):
        return {"name": s.name, "status": "skip",
                "counts": {"passed": 0, "skipped": 0, "failed": 0},
                "line": (f"skip  {s.name:<34} {VISIBLE_BROWSER_SUITES[s.name]}; "
                         f"set {VISIBLE_BROWSER_ENV}=1 to run it"),
                "echo": [], "tail": []}
    need = NEEDS_OWNER.get(s.name, ())
    absent = [f for f in need if not (backend / f).is_file()]
    if absent:
        return {"name": s.name, "status": "skip",
                "counts": {"passed": 0, "skipped": 0, "failed": 0},
                "line": f"skip  {s.name:<34} needs the owner's {', '.join(absent)}",
                "echo": [], "tail": []}
    t0 = time.time()
    why = ""
    env = suite_env(s.name, env)
    try:
        # errors="replace" and an explicit utf-8 decode: the child is run
        # with PYTHONIOENCODING=utf-8 (see private_state), so decoding its
        # output with the console's own code page raised
        # UnicodeDecodeError INSIDE subprocess's reader thread, which left
        # r.stdout as None and crashed this whole runner with
        # "unsupported operand type(s) for +: 'NoneType' and 'str'" - one
        # suite's non-ASCII output taking the entire run down with it.
        # That happened on 2026-10-03, at test_mail_mask.py.
        r = subprocess.run([sys.executable, str(s)], cwd=HERE, env=env,
                           capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace")
        code, got_out, got_err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        code, got_out, got_err = "timeout", "", ""
    except OSError as exc:
        # The child never started at all - an executable that cannot run,
        # a path that is gone, a permission the sandbox refuses. The suite
        # has no exit code to compare with 0, so it is FAILED and the
        # reason is carried into the report; continuing is the point,
        # because the suites after this one still have results worth
        # printing.
        code, got_out, got_err = None, "", ""
        why = f"the suite could not be started: {exc}"
    took = f"{time.time() - t0:5.1f}s"
    status, n, line, echo = suite_result(s.name, took, code, got_out, got_err, why)
    tail = ((got_out or "") + (got_err or "")).strip().splitlines()[-40:]
    return {"name": s.name, "status": status, "counts": n, "line": line,
            "echo": echo, "tail": tail}


def _print_job(got: dict, ran: dict, passed: list, failed: list,
               skipped: list, zero: list) -> None:
    """Print one finished suite exactly as the one-at-a-time run always has.

    `zero` collects the allowlisted suites that ran NO check (status "zero").
    They are printed as NO-CHECKS and counted in neither `passed` nor `failed`
    nor the by-name `skipped` list - a skip is never a pass, and a suite that
    proves nothing must not read like one."""
    if got["status"] == "skip":
        skipped.append(got["name"])
        print(got["line"])
        return
    for word in ran:
        ran[word] += got["counts"][word]
    if got["status"] == "ok":
        passed.append(got["name"])
        print(got["line"])
        return
    if got["status"] == "zero":
        zero.append(got["name"])
        print(got["line"])
        return
    failed.append(got["name"])
    print(got["line"])
    for line in got["echo"]:
        print(line)
    print("\n".join("      " + line for line in got["tail"]))


def _sweep_parallel(suites: list, backend: Path, worker_envs: list, ran: dict,
                    passed: list, failed: list, skipped: list, zero: list) -> None:
    """The same suites, `len(worker_envs)` at a time.

    The only thing the extra workers change is the ORDER the finished lines are
    printed in - and that is deliberate: the updater reads them as they arrive
    to refine its ETA. Which suites run, what each result means and the final
    counts are the same code (`_suite_job`) as the one-at-a-time path.

    Each worker owns one private state folder (made in `_sweep`), so two
    suites never write their config folder, audit log or scratch into one
    another. A job that raises is reported as a FAILED suite with its error
    rather than taking the other 300 results down with it."""
    free = list(worker_envs)
    guard = threading.Lock()
    print_lock = threading.Lock()

    def work(suite: Path) -> dict:
        with guard:
            env = free.pop()
        try:
            return _suite_job(suite, backend, env)
        finally:
            with guard:
                free.append(env)

    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(worker_envs)) as pool:
        for suite in suites:
            futures[pool.submit(work, suite)] = suite
        for future in concurrent.futures.as_completed(futures):
            try:
                got = future.result()
            except Exception as exc:            # noqa: BLE001 - one job's bug
                name = futures[future].name
                got = {"name": name, "status": "FAIL",
                       "counts": {"passed": 0, "skipped": 0, "failed": 1},
                       "line": f"FAIL  {name:<34}  (worker error)  the job "
                               f"raised {type(exc).__name__}: {exc}",
                       "echo": [], "tail": []}
            with print_lock:
                _print_job(got, ran, passed, failed, skipped, zero)


def _sweep(root: Path, only=(), jobs: int = 1,
           ignore_update_lock: bool = False, named_backend: "Path|None" = None) -> int:
    """One run, inside `root`: reap what a dead run left, stage, run each
    suite, report. Never called except from `main`, which owns `root`.

    `ignore_update_lock` is the update's own suite phase (see `main`); the
    second lock check below must respect the same bypass and must run after the
    backend is staged, so an update that starts while this run is staging is
    still refused.

    `named_backend` is the folder `main` resolved from an EXPLICIT
    `--use-env-backend` / `--backend-path`; None means the default: stage a
    throwaway copy. The ambient `JARVIS_BACKEND` is never read here - `main`
    has already decided (and popped it when the run is hermetic)."""
    jobs = max(1, int(jobs))
    reaped = reap_orphans(keep=(root,))
    if reaped:
        print(f"reaped {len(reaped)} staging folder(s) an earlier run left behind: "
              + ", ".join(reaped))
    backend = Path(named_backend).resolve() if named_backend else stage(root)
    print(f"backend: {backend}"
          + ("" if named_backend else "  (staged: every shipped module, flattened)"))
    # S4: the check at the top of `main()` is not the last word - a lock can be
    # published while this run is staging the backend (that staging can take a
    # second). Ask again immediately before the first suite starts; on a
    # refusal, stop here and let `main`'s `finally` remove the staging root.
    late_refusal = update_lock_refusal(ignore_update_lock)
    if late_refusal:
        print(f"REFUSED  {late_refusal}", file=sys.stderr)
        print("Not run: the backend was staged first, but no suite was started; "
              "the staging folder is removed.", file=sys.stderr)
        return 3
    known = sorted(HERE.glob("test_*.py"))
    suites = [s for s in known if s.name in only] if only else known
    names = {s.name for s in suites}
    unknown = [n for n in only if n not in {s.name for s in known}]
    stale = [] if only else sorted(set(NEEDS_OWNER) - names)
    # The visible-browser list is permanent, not "whatever was selected": a
    # renamed or deleted suite must be caught even by `run_suites.py test_x.py`.
    stale_visible = sorted(set(VISIBLE_BROWSER_SUITES) - {s.name for s in known})
    # The zero-check allowlist is a promise about three files that exist; a
    # renamed suite must not leave a dead exemption behind (as NEEDS_OWNER and
    # the visible-browser list are checked above).
    stale_zero = sorted(set(ZERO_CHECK_ALLOWED) - {s.name for s in known})
    passed, failed, skipped, zero = [], [], [], []
    # The checks inside the suites that ran, summed from what each suite
    # reported. A suite that exits 0 having skipped every check it has is NOT
    # "ok" (2026-10-27): it is NO-CHECKS, kept in `zero`, and it fails the
    # sweep unless it is named on ZERO_CHECK_ALLOWED.
    ran = {"passed": 0, "skipped": 0, "failed": 0}
    if unknown:
        print(f"FAIL  no suite here is named: {', '.join(unknown)}  "
              f"(a suite is named by its bare file name, e.g. test_ui_control.py)")
        failed += unknown
    if stale:
        print(f"FAIL  run_suites.py lists suites that do not exist: {stale}")
        failed += stale
    if stale_visible:
        print(f"FAIL  run_suites.py's visible-browser skip list names suites that do not "
              f"exist: {stale_visible}")
        failed += stale_visible
    if stale_zero:
        print(f"FAIL  run_suites.py's zero-check allowlist names suites that do not exist: "
              f"{stale_zero}")
        failed += stale_zero
    no_owner = sorted(k for k, v in NEEDS_OWNER.items() if not set(v) & OWNER_FILES)
    if no_owner:
        print(f"FAIL  run_suites.py skips suites that need nothing from the owner's PC: {no_owner}")
        failed += no_owner
    if visible_browser_opted_in() and any(s.name in VISIBLE_BROWSER_SUITES for s in suites):
        print(f"[run_suites] VISIBLE BROWSER TESTS ON ({VISIBLE_BROWSER_ENV}=1): the "
              f"browser halves may open real windows on this screen (they still skip "
              f"when Playwright or a browser is not installed)")
    base = dict(os.environ, JARVIS_BACKEND=str(backend),
                PYTHONDONTWRITEBYTECODE="1")
    if jobs == 1:
        state = root / STATE_NAME
        worker_envs = [suite_temp_env(private_state(base, backend, state), root)]
        print(f"state: {state}  (config folder and audit log for this run, not yours)")
        print(home_words(worker_envs[0]))
        for suite in suites:
            _print_job(_suite_job(suite, backend, worker_envs[0]),
                       ran, passed, failed, skipped, zero)
    else:
        worker_envs = []
        for index in range(jobs):
            state = root / f"{STATE_NAME}-{index + 1}"
            worker_envs.append(suite_temp_env(
                private_state(dict(base), backend, state), state))
        print(f"state: {root / STATE_NAME}-1 .. -{jobs}  ({jobs} worker folders: "
              f"config folder and audit log for this run, not yours)")
        print(home_words(worker_envs[0]) + f"  (one home per worker: "
              f"state-1 .. state-{jobs})")
        _sweep_parallel(suites, backend, worker_envs, ran, passed, failed, skipped, zero)
    # No rmtree here any more: `root` - which holds the staged backend (unless
    # an EXPLICIT --use-env-backend / --backend-path named a real one), the
    # state folder and the suites' own scratch - is removed by main()'s
    # `finally`, on every path out of here.
    print(f"\n{ran['passed']} passed, {ran['skipped']} skipped, {ran['failed']} failed")
    if zero:
        shown = sorted(zero) if jobs > 1 else zero
        print(f"      ({len(zero)} suite(s) ran NO checks - every check was skipped: "
              f"{', '.join(shown)}. Each is allowed by ZERO_CHECK_ALLOWED and none is a "
              f"pass; a skip is never a pass)")
    if ran["skipped"] or skipped:
        print(f"      (a skip is a check that could not run here: {ran['skipped']} inside the "
              f"suites above, {len(skipped)} whole suite(s) skipped by name - each line above "
              f"says why)")
    if failed:
        shown = sorted(failed) if jobs > 1 else failed
        print("failed: " + ", ".join(shown))
    return 1 if failed else 0


def state_env(where: str) -> int:
    """`--state-env DIR`: print, one KEY=VALUE a line, the variables that send
    the suites' state to DIR. apply-patches.ps1 runs the suites itself, one by
    one, and sets these first - so the two runners cannot disagree about
    where test state goes.

    That now includes `OPENJARVIS_HOME` / `JARVIS_HOME`: the owner's own data
    (databases, inbox, receipts, the guardian store) is the one thing a
    patcher-run suite must never read or write, and both names point at
    DIR/home, which is made here before it is printed. The one exception is
    `JARVIS_TESTS_USE_REAL_HOME=1`: then no home line is printed at all, so
    the caller's real home is left alone - and the caller has asked for it.

    PYTHONIOENCODING is printed here for a different reason: apply-patches.ps1
    runs each suite as its own process, so without it in this list the suites
    it runs would still be on the console's code page and still crash on a
    non-ASCII suite name (see private_state). A variable already set to this
    value is not printed, which is fine - the script's own copy is the same.

    JARVIS_LOG_DIR is printed too, since 2026-10-20: the patcher's own loop runs
    suites directly, and that alone gave them the config's
    log_directory = "~/.openjarvis/logs/" - the owner's REAL audit log. The
    logging-machinery suites (LOG_MACHINERY_SUITES) clear it themselves, because
    this list cannot vary per suite.

    THIS IS THE ONE PLACE THAT STILL READS THE AMBIENT JARVIS_BACKEND, on
    purpose: `--state-env` is the patcher's own subcommand, and apply-patches.ps1
    sets `$env:JARVIS_BACKEND` in its own process right before calling it (see
    its test loop), so the value is the patcher's explicit choice for this run,
    not an ambient surprise. A normal suite run never reaches this branch and
    never reads the variable (see `_named_backend`)."""
    backend = Path(os.environ.get("JARVIS_BACKEND") or HERE).resolve()
    env = private_state(dict(os.environ), backend, Path(where))
    for k in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR", "JARVIS_FRAMEWORK_TOML",
              "OPENJARVIS_HOME", "JARVIS_HOME", "PYTHONIOENCODING", LOG_DIR_ENV,
              *OFFLINE_ENVS):
        if env.get(k) and env.get(k) != os.environ.get(k):
            print(f"{k}={env[k]}")
    return 0


if __name__ == "__main__":
    args = list(sys.argv[1:])
    if any(arg in ("-h", "--help") for arg in args):
        # FIRST, and before the update lock is read or anything is staged:
        # asking what the runner does must never run the fleet (measured trap,
        # 2026-10-26 - `--help` was silently ignored and every suite ran).
        print(USAGE)
        sys.exit(0)
    jobs = 1
    ignore_update_lock = False
    use_env_backend = False
    backend_path = None
    if LOCK_BYPASS_FLAG in args:
        # The update's own suite phase: it holds the lock, so it must not
        # refuse itself. Any other caller asking for this is saying "I know an
        # update is running and I want to add to the CPU load anyway".
        ignore_update_lock = True
        args.remove(LOCK_BYPASS_FLAG)
    if "--jobs" in args:
        at = args.index("--jobs")
        try:
            jobs = int(args[at + 1])
        except (IndexError, ValueError):
            print("FAIL  --jobs needs a whole number of workers, e.g. --jobs 14",
                  file=sys.stderr)
            sys.exit(2)
        del args[at:at + 2]
    if USE_ENV_BACKEND_FLAG in args:
        use_env_backend = True
        args.remove(USE_ENV_BACKEND_FLAG)
    if BACKEND_PATH_FLAG in args:
        at = args.index(BACKEND_PATH_FLAG)
        try:
            backend_path = args[at + 1]
        except IndexError:
            print(f"FAIL  {BACKEND_PATH_FLAG} needs a folder, e.g. "
                  f'{BACKEND_PATH_FLAG} "C:\\Users\\you\\Documents\\jarvis-backend"',
                  file=sys.stderr)
            sys.exit(2)
        del args[at:at + 2]
    if STATE_ENV_FLAG in args:
        at = args.index(STATE_ENV_FLAG)
        try:
            state_where = args[at + 1]
        except IndexError:
            print(f"FAIL  {STATE_ENV_FLAG} needs a folder, e.g. "
                  f'{STATE_ENV_FLAG} "C:\\Temp\\suite-state"', file=sys.stderr)
            sys.exit(2)
        del args[at:at + 2]
        if args:
            print(f"FAIL  {STATE_ENV_FLAG} takes one folder and no suite names; "
                  f"unexpected: {' '.join(args)}", file=sys.stderr)
            sys.exit(2)
        sys.exit(state_env(state_where))
    # A TYPO MUST STOP THE RUN, NOT WIDEN IT. A path-shaped or unknown argument
    # is refused here, before any staging, so the fleet cannot start by
    # accident (see `suite_arguments`).
    try:
        only = suite_arguments(args)
    except UsageError as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(only,
                      max(1, jobs), ignore_update_lock=ignore_update_lock,
                      use_env_backend=use_env_backend,
                      backend_path=backend_path))
    except UsageError as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        sys.exit(2)
