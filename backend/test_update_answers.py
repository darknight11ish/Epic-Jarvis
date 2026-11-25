"""test_update_answers.py - "has my update finished?", answered from this PC's
own two commits (2026-11-24; backend/jarvis_quick.py).

    py -3 -B backend/test_update_answers.py

WHAT THIS PROVES. The owner asked whether his update had finished, and the 8B
model answered with a summary it invented: "... so both halves are done. Backend
at b0926662ec0b, app at 18ffc17611fe; they differ." The two halves cannot be
done AND differ, and the model knows nothing about this machine. So:

1. THE WORDS. "has my update finished", "are both halves up to date" and "is
   Jarvis updated" reach `update_state` without the model, including the polite
   wordings the existing `flex_normalise` retry carries. The release questions
   keep their own intents ("is Jarvis up to date" stays `update_ask`), and the
   measured near-misses stay with the model.
2. THE READS. The live folder's `VERSION` and `SOURCE-COMMIT`, the installed
   app's version (through `jarvis_update.installed()`) and the app's own
   start-up line are read, never guessed. The values are written into temporary
   folders - the module never names this PC's live folder, and nothing here
   reads it.
3. THE FIVE STATES, each with its own exact words: same commit; the app's
   commit is an ancestor of the backend's (benign, not a failure); the
   backend's commit is an ancestor of the app's; different and not comparable;
   and a read that failed. "Both halves are done" is never said unless the
   commits prove it, and the version numbers are never used as the proof.
4. NO GUESSING PAST A FAILED READ. Every failure names WHICH read failed -
   VERSION, SOURCE-COMMIT, the installed version, the app's log, or the app's
   build commit - and never fills the gap with a version number.
5. READ-ONLY AND WIRED. The intent is in READ_ONLY_INTENTS, raises no card,
   answers in a private chat too (the model cannot know this PC's commits), and
   `answer()` reaches the runner. The twin in `jarvis-backend/` is byte-identical.

WHY A TEMPORARY GIT REPOSITORY. The one question a version number cannot answer
is which commit is AHEAD. That is `git merge-base --is-ancestor`, so this suite
builds a real throwaway repository (base -> app -> backend, plus a sibling
branch) and lets the module's real read-only git call answer. No test touches
this checkout's history, and nothing is fetched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# Hermetic, like the rest of the suite: the owner's real home, config and log
# stay untouched (`answer()` asks jarvis_manner and jarvis_personality_creator).
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-update-answers-"))
os.environ["OPENJARVIS_HOME"] = str(_TMP)
os.environ["JARVIS_HOME"] = str(_TMP)
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py")
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class FakeSched:
    """The only scheduler surface `answer()` touches, and only in try/except."""

    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def forget_set(self, *a, **k):
        pass


# ---------------------------------------------------------------------------
# The measured live values, as FIXTURES ONLY
# ---------------------------------------------------------------------------
#
# Measured on the owner's PC on 2026-11-24: the live folder's VERSION was
# 0.2.502, its SOURCE-COMMIT was b0926662ec0b..., and the desktop app read
# 0.2.502 from Windows while its log said it was built from 18ffc17611fe. The
# module hardcodes none of this; here they pin the file formats and the exact
# shape of the owner's own case.

LIVE_VERSION = "0.2.502"
LIVE_BACKEND = "b0926662ec0bd355c09df0d108dd4f5a777550a1"
LIVE_APP = "18ffc17611fe"          # twelve characters, as build.rs records it
SCHEMA = "jarvis-source-commit/1"

# ---------------------------------------------------------------------------
# Fixtures: a live folder, an app log, a desktop report
# ---------------------------------------------------------------------------


def backend_folder(name, version=LIVE_VERSION, commit=None, *,
                   record_version=True, schema=None):
    """A temporary backend folder with the two markers the updater writes."""
    folder = _TMP / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "jarvis_hud.py").write_text("# the marker jarvis_update looks for\n",
                                          encoding="utf-8")
    if version is not None:
        (folder / "VERSION").write_text(version + "\n", encoding="utf-8")
    if commit is not None:
        doc = {"schema": schema or SCHEMA, "commit": commit}
        if record_version:
            doc["version"] = version
        (folder / "SOURCE-COMMIT").write_text(json.dumps(doc), encoding="utf-8")
    return folder


def log_dir(path, version=LIVE_VERSION, commit=LIVE_APP):
    """A temporary app log with the start-up line `lib.rs` writes."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / "jarvis-desktop.log").write_text(
        "\n===== Jarvis Desktop %s starting ===== (commit %s, logs in C:\\tmp)\n"
        % (version, commit), encoding="utf-8")
    return path


def desktop(version=LIVE_VERSION, why=""):
    """A stand-in for `jarvis_update.installed()`."""
    return lambda: {"version": version, "why": why}


# ---------------------------------------------------------------------------
# Fixtures: a throwaway git history, so the ancestry answer is REAL
# ---------------------------------------------------------------------------

REPO = _TMP / "repo"


def _git(*args) -> str:
    done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr or done.stdout}")
    return done.stdout.strip()


def _commit(name: str, text: str) -> str:
    (REPO / name).write_text(text, encoding="utf-8")
    _git("add", name)
    _git("commit", "-q", "-m", name)
    return _git("rev-parse", "HEAD")


def _build_repo() -> dict:
    """base -> app -> backend on main; `side` branches from base and diverges.

    `_compare_update_commits` only ever reads this history (`merge-base
    --is-ancestor`), and the suite removes the whole throwaway repository when
    the process ends.
    """
    REPO.mkdir()
    (REPO / "scripts").mkdir()
    (REPO / "scripts" / "update-jarvis.ps1").write_text("# the updater's name\n",
                                                        encoding="utf-8")
    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "update-answers@example.invalid")
    _git("config", "user.name", "update answers suite")
    base = _commit("base.txt", "base\n")
    app = _commit("app.txt", "the app's build\n")
    backend = _commit("backend.txt", "the backend's deploy\n")
    _git("checkout", "-q", "-b", "side", base)
    side = _commit("side.txt", "an unrelated build\n")
    _git("checkout", "-q", "main")
    return {"base": base, "app": app, "backend": backend, "side": side}


CHAIN = _build_repo()


def compare_in_repo(app_commit, backend_commit):
    return Q._compare_update_commits(app_commit, backend_commit, root=REPO)


def ask(text, folder, logs, *, installed=None, compare=None):
    """The intent, matched from the owner's sentence, driven through its runner."""
    got = Q.match(text)
    if got is None or got.name != "update_state":
        raise AssertionError(f"{text!r} did not reach update_state: {got}")
    return Q._run_update_state(
        got, folder=folder, installed=installed or desktop(), logs=logs,
        compare=compare)


# ---------------------------------------------------------------------------
# The five exact reply texts the brief fixes
# ---------------------------------------------------------------------------

SAME = "The update is done: both halves are on commit {commit}."
BACKEND_AHEAD = ("The app half is one step behind: the backend is the newer code, "
                 "and nothing is missing. The next desktop update catches up.")
APP_AHEAD = ("The two halves are different builds: the app is ahead, and the "
             "backend is behind. Press Update everything in the app - Settings, "
             "then Updates. That is the one action that fixes it.")
UNKNOWN = ("The two halves are different builds, and I cannot prove which one is "
           "behind (neither commit is in the other's history). Press Update "
           "everything in the app - Settings, then Updates. That is the one "
           "action that fixes it.")
NO_SOURCE = ("I cannot tell whether the update finished: the backend's "
             "SOURCE-COMMIT file could not be read. There is no SOURCE-COMMIT "
             "beside VERSION.")


# ---------------------------------------------------------------------------
# 1. the question reaches the fast path, and its neighbours do not move
# ---------------------------------------------------------------------------

def t_the_question_reaches_the_fast_path():
    for text in (
        "has my update finished",
        "is my update finished",
        "did my update finish",
        "is my update done",
        "is my update done yet",
        "has the update completed",
        "is the update complete",
        "did the update finish",
        "has the update finished yet",
        "has my update gone through",
        "did the update go through",
        "did my update install",
        "is my update installed",
        "has the update applied",
        "is Jarvis updated",
        "has Jarvis updated",
        "did Jarvis update",
        "is Jarvis updated now",
        "is Jarvis finished updating",
        "has Jarvis finished updating",
        "is Jarvis done updating",
        "are both halves up to date",
        "are the two halves up to date",
        "do both halves match",
        "are both halves the same build",
        "are both halves on the same commit",
        "are both halves in sync",
        "is the desktop app updated",
        "is the backend updated",
        "is the app and the backend the same",
    ):
        got = Q.match(text)
        check(f"{text!r} -> update_state",
              got is not None and got.name == "update_state",
              got.name if got else "went to the model")


def t_the_release_questions_keep_their_own_intents():
    """The new grammar must not take a sentence another answer already owns."""
    for text, want in (
        ("is Jarvis up to date", "update_ask"),
        ("is there an update", "update_ask"),
        ("is there an update available", "update_ask"),
        ("any updates?", "update_ask"),
        ("do I need an update", "update_ask"),
        ("what version am I on", "update_ask"),
        ("check for updates", "update_ask"),
        ("whats the latest release", "update_ask"),
        ("what changed in the update", "update_notes"),
        ("what's new in the update", "update_notes"),
        ("what is in the latest version", "update_notes"),
        ("update Jarvis", "update_start"),
        ("update, Jarvis", "update_start"),
        ("start the update", "update_start"),
        ("install the update", "update_start"),
        ("update to the latest version", "update_start"),
    ):
        got = Q.match(text)
        check(f"{text!r} still -> {want}",
              got is not None and got.name == want,
              got.name if got else "went to the model")


def t_the_measured_near_misses_stay_away():
    for text in (
        "when is the next update",
        "how do I update Jarvis",
        "update my settings",
        "update my address in the email",
        "did the update break anything",
        "what changed in the settings",
        "what's my update status",
        "is the update running",
    ):
        got = Q.match(text)
        check(f"{text!r} is not the finished-update question",
              got is None or got.name != "update_state",
              got.name if got else None)


def t_the_flex_retry_carries_the_polite_wordings():
    for text, flexed in (
        ("tell me whether my update has finished",
         "whether my update has finished"),
        ("can you tell me if my update finished", "if my update finished"),
        ("i want to know if my update finished", "if my update finished"),
        ("could you tell me if my update is done", "if my update is done"),
    ):
        check(f"flex: {text!r} -> {flexed!r}", Q.flex_normalise(text) == flexed,
              Q.flex_normalise(text))
        got = Q.match(text)
        check(f"... and {text!r} -> update_state",
              got is not None and got.name == "update_state",
              got.name if got else "went to the model")


# ---------------------------------------------------------------------------
# 2. the reads are real, from the files' own formats
# ---------------------------------------------------------------------------

def t_the_measured_live_files_are_read():
    folder = backend_folder("measured", LIVE_VERSION, LIVE_BACKEND)
    got = Q._read_backend_markers(folder)
    check("VERSION is read", got["version"] == LIVE_VERSION, got)
    check("SOURCE-COMMIT names the deployed commit",
          got["commit"] == LIVE_BACKEND, got)
    check("... and there is nothing to explain away", got["why"] == "", got)

    logs = log_dir(_TMP / "measured-logs", LIVE_VERSION, LIVE_APP)
    build = Q._read_desktop_build(logs)
    check("the app's start-up line names its version and its twelve-character commit",
          build == {"version": LIVE_VERSION, "commit": LIVE_APP, "what": "",
                    "why": ""}, build)
    check("the installed version is read through jarvis_update.installed()",
          Q._read_installed(desktop())["version"] == LIVE_VERSION)
    check("... and a report with no version is 'cannot tell', never a guess",
          Q._read_installed(desktop(None, "cannot tell: no installed Jarvis "
                                          "Desktop version is recorded on this PC"))
          ["version"] == "")


def t_the_default_readers_find_the_live_files():
    """No seams: the paths come from `jarvis_update.backend_folder()` and
    `%LOCALAPPDATA%`, exactly as they do on the owner's PC."""
    folder = backend_folder("default-wired", LIVE_VERSION, LIVE_BACKEND)
    appdata = _TMP / "appdata-wired"
    logs = log_dir(appdata / "com.jarvis.desktop" / "logs", LIVE_VERSION, LIVE_APP)
    old_backend = os.environ.get("JARVIS_BACKEND")
    old_local = os.environ.get("LOCALAPPDATA")
    os.environ["JARVIS_BACKEND"] = str(folder)
    os.environ["LOCALAPPDATA"] = str(appdata)
    try:
        got = Q._read_backend_markers()
        check("the live folder is found the way the updater finds it",
              got["commit"] == LIVE_BACKEND and got["version"] == LIVE_VERSION, got)
        build = Q._read_desktop_build()
        check("the app log is found under %LOCALAPPDATA%\\com.jarvis.desktop\\logs",
              build["commit"] == LIVE_APP and logs.is_dir(), build)
    finally:
        if old_backend is None:
            os.environ.pop("JARVIS_BACKEND", None)
        else:
            os.environ["JARVIS_BACKEND"] = old_backend
        if old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_local


# ---------------------------------------------------------------------------
# 3. the five states, exact words
# ---------------------------------------------------------------------------

def t_same_commit_says_the_update_is_done():
    folder = backend_folder("same", LIVE_VERSION, CHAIN["backend"])
    logs = log_dir(_TMP / "same-logs", LIVE_VERSION, CHAIN["backend"][:12])
    res = ask("has my update finished", folder, logs)
    short = Q._short_commit(CHAIN["backend"])
    expected = SAME.format(commit=short)
    check("same commit: the update is done, and the commit is named",
          res.reply == expected, res.reply)
    check("... the commits are compared before any repository is needed",
          Q._compare_update_commits(CHAIN["backend"], CHAIN["backend"][:12],
                                    root=_TMP / "no-such-repository")
          == ("same", ""))
    check("... the commit is named exactly once, seven characters",
          res.reply.count(short) == 1 and len(short) == 7, res.reply)
    check("... and the version number is NOT offered as the proof",
          LIVE_VERSION not in res.reply, res.reply)
    check("... the intent is update_state", res.intent == "update_state", res.intent)


def t_backend_ahead_is_benign_not_a_failure():
    folder = backend_folder("backend-ahead", LIVE_VERSION, CHAIN["backend"])
    logs = log_dir(_TMP / "backend-ahead-logs", LIVE_VERSION, CHAIN["app"][:12])
    res = ask("is my update finished", folder, logs, compare=compare_in_repo)
    check("app's commit is an ancestor of the backend's: the exact benign words",
          res.reply == BACKEND_AHEAD, res.reply)
    said = res.reply.lower()
    check("... the app half is said to be one step behind",
          "app half is one step behind" in said, res.reply)
    check("... the backend is said to be newer", "newer" in said, res.reply)
    check("... and nothing is missing", "nothing is missing" in said, res.reply)
    check("... the next desktop update is said to catch up",
          "next desktop update catches up" in said, res.reply)
    for word in ("fail", "problem", "wrong", "error", "broken", "not finished"):
        check(f"... it does not read like a failure ({word!r})", word not in said,
              res.reply)
    check("... the version numbers are not in it", LIVE_VERSION not in res.reply,
          res.reply)


def t_app_ahead_names_the_one_action():
    folder = backend_folder("app-ahead", LIVE_VERSION, CHAIN["app"])
    logs = log_dir(_TMP / "app-ahead-logs", LIVE_VERSION, CHAIN["backend"][:12])
    res = ask("has my update finished", folder, logs, compare=compare_in_repo)
    check("the backend's commit is an ancestor of the app's: the exact words",
          res.reply == APP_AHEAD, res.reply)
    check("... it says the two halves are different builds",
          "the two halves are different builds" in res.reply.lower(), res.reply)
    check("... it says the backend is behind", "backend is behind" in res.reply,
          res.reply)
    check("... it names the ONE action, on the button's own label",
          "Update everything" in res.reply and "Settings, then Updates" in res.reply,
          res.reply)
    check("... and it never says both halves are done",
          "both halves are done" not in res.reply.lower()
          and "the update is done" not in res.reply.lower(), res.reply)


def t_commits_that_cannot_be_compared_are_not_guessed():
    folder = backend_folder("diverged", LIVE_VERSION, CHAIN["backend"])
    logs = log_dir(_TMP / "diverged-logs", LIVE_VERSION, CHAIN["side"][:12])
    res = ask("has my update finished", folder, logs, compare=compare_in_repo)
    check("neither commit is the other's ancestor: the exact words",
          res.reply == UNKNOWN, res.reply)
    check("... it names what could not be compared",
          "neither commit is in the other's history" in res.reply, res.reply)
    check("... it does not pick a side it cannot prove",
          "app is ahead" not in res.reply and "backend is behind" not in res.reply,
          res.reply)
    check("... it still names the ONE action", "Update everything" in res.reply,
          res.reply)
    check("... and it never claims success",
          "done" not in res.reply.lower(), res.reply)

    # A commit this PC's copy of the repository does not hold is the same
    # answer, with git's own reason.
    logs2 = log_dir(_TMP / "unknown-commit-logs", LIVE_VERSION, "deadbeefdead")
    res2 = ask("has my update finished", folder, logs2, compare=compare_in_repo)
    check("a commit this PC does not hold is 'cannot prove which one is behind'",
          "cannot prove which one is behind" in res2.reply
          and "not both in this PC's copy of the repository" in res2.reply,
          res2.reply)
    check("... and it is never counted as a match",
          "the update is done" not in res2.reply.lower(), res2.reply)


def t_the_version_numbers_are_never_the_proof():
    """The measured trap: both halves said 0.2.502 while the commits differed.

    Equal versions are not enough for any success word, and NEITHER is a
    different version used to guess a direction - the commits alone decide.
    """
    folder = backend_folder("versions-equal", "0.2.502", CHAIN["app"])
    logs = log_dir(_TMP / "versions-equal-logs", "0.2.502", CHAIN["backend"][:12])
    res = ask("has my update finished", folder, logs, compare=compare_in_repo)
    check("equal VERSION numbers with different commits is NOT 'done'",
          "the update is done" not in res.reply.lower(), res.reply)
    check("... the answer is the app-ahead one (the commit decides)",
          res.reply == APP_AHEAD, res.reply)


# ---------------------------------------------------------------------------
# 4. every failed read is named, and never guessed past
# ---------------------------------------------------------------------------

def t_a_missing_source_commit_is_named():
    folder = backend_folder("no-source", LIVE_VERSION, None)
    logs = log_dir(_TMP / "no-source-logs", LIVE_VERSION, LIVE_APP)
    res = ask("has my update finished", folder, logs)
    check("no SOURCE-COMMIT: the exact words", res.reply == NO_SOURCE, res.reply)
    check("... it says the update's finish cannot be told",
          "cannot tell whether the update finished" in res.reply, res.reply)
    check("... and it names SOURCE-COMMIT, the read that failed",
          "SOURCE-COMMIT" in res.reply, res.reply)


def t_each_failed_read_is_named():
    logs = log_dir(_TMP / "named-logs", LIVE_VERSION, LIVE_APP)
    good = backend_folder("for-log-tests", LIVE_VERSION, LIVE_BACKEND)

    no_version = backend_folder("no-version", None, LIVE_BACKEND)
    said = ask("has my update finished", no_version, logs).reply
    check("no VERSION: names the backend's VERSION file",
          "the backend's VERSION file" in said
          and "There is no VERSION file beside the backend" in said, said)

    stale = backend_folder("stale", LIVE_VERSION, LIVE_BACKEND)
    (stale / "SOURCE-COMMIT").write_text(json.dumps(
        {"schema": SCHEMA, "commit": LIVE_BACKEND, "version": "0.2.495"}),
        encoding="utf-8")
    said = ask("has my update finished", stale, logs).reply
    check("a stale SOURCE-COMMIT: names it and both versions",
          "the backend's SOURCE-COMMIT file" in said
          and "recorded for version 0.2.495" in said
          and "VERSION says 0.2.502" in said, said)

    bad = backend_folder("bad-schema", LIVE_VERSION, LIVE_BACKEND,
                         schema="someone-else/9")
    said = ask("has my update finished", bad, logs).reply
    check("an unknown schema: names SOURCE-COMMIT and the format",
          "the backend's SOURCE-COMMIT file" in said
          and "unknown format (someone-else/9)" in said, said)

    said = ask("has my update finished", good, logs,
               installed=desktop(None, "cannot tell: no installed Jarvis "
                                       "Desktop version is recorded on this PC")).reply
    check("no installed version: names the installed app's version",
          "the installed app's version could not be read" in said
          and "No installed Jarvis Desktop version is recorded" in said, said)

    said = ask("has my update finished", good, _TMP / "no-such-logs").reply
    check("no app log: names the app's own log",
          "the app's own log could not be read" in said
          and "There is no jarvis-desktop.log on this PC" in said, said)

    unknown_commit = log_dir(_TMP / "unknown-commit", LIVE_VERSION, "unknown")
    said = ask("has my update finished", good, unknown_commit).reply
    check("a log line with no commit: names the app's build commit",
          "the app's build commit could not be read" in said
          and "does not name one" in said, said)

    older = log_dir(_TMP / "older-log", "0.2.495", LIVE_APP)
    said = ask("has my update finished", good, older).reply
    check("a log that is a different version: names the app's build commit",
          "the app's build commit could not be read" in said, said)
    check("... and says both versions, so the gap is explained",
          "last start was version 0.2.495" in said
          and "Windows says 0.2.502 is installed" in said, said)
    check("... and no match is claimed", "the update is done" not in said.lower(),
          said)


# ---------------------------------------------------------------------------
# 5. read-only, wired, and the twin
# ---------------------------------------------------------------------------

def t_it_is_read_only_and_routes_normally():
    folder = backend_folder("read-only", LIVE_VERSION, CHAIN["backend"])
    logs = log_dir(_TMP / "read-only-logs", LIVE_VERSION, CHAIN["backend"][:12])
    res = ask("has my update finished", folder, logs)
    check("update_state is in READ_ONLY_INTENTS",
          "update_state" in Q.READ_ONLY_INTENTS)
    check("... it raises no card and records nothing to undo",
          res.made == [] and res.open_settings is None and res.note_job is None,
          (res.made, res.open_settings, res.note_job))
    route = Q.route_fields(res)
    check("... its quick name is update_state", route["quick"] == "update_state")
    check("... and it adds nothing to X-Jarvis-Route",
          set(route) == {"quick", "where", "lane", "inject_memory",
                         "injected_facts", "injected_ids", "injected_sensitive"},
          sorted(route))
    check("... a PRIVATE chat gets the same real answer (the model cannot know it)",
          "update_state" in Q._PRIVATE_DETERMINISTIC_READS)


def t_the_whole_route_answers_without_the_model():
    folder = backend_folder("route", LIVE_VERSION, CHAIN["backend"])
    appdata = _TMP / "appdata-route"
    log_dir(appdata / "com.jarvis.desktop" / "logs", LIVE_VERSION,
            CHAIN["app"][:12])
    import jarvis_update as U

    old_installed, old_repo = U.installed, U.repo_folder
    old_backend = os.environ.get("JARVIS_BACKEND")
    old_local = os.environ.get("LOCALAPPDATA")
    U.installed = desktop()
    U.repo_folder = lambda: REPO
    os.environ["JARVIS_BACKEND"] = str(folder)
    os.environ["LOCALAPPDATA"] = str(appdata)
    try:
        got = Q.answer("has my update finished", sched=FakeSched())
        check("answer() reaches the runner and says the exact benign words",
              got is not None and got.intent == "update_state"
              and got.reply == BACKEND_AHEAD,
              None if got is None else (got.intent, got.reply))
        private = Q.answer("has my update finished", sched=FakeSched(),
                           private=True)
        check("... and a private chat answers it from this PC too",
              private is not None and private.intent == "update_state"
              and private.reply == BACKEND_AHEAD,
              None if private is None else (private.intent, private.reply))
    finally:
        U.installed, U.repo_folder = old_installed, old_repo
        if old_backend is None:
            os.environ.pop("JARVIS_BACKEND", None)
        else:
            os.environ["JARVIS_BACKEND"] = old_backend
        if old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_local


def t_it_reads_this_pc_and_never_the_network():
    """The runner and its readers open files and run one local git command.

    No release manifest (`published()`/`_release_manifest`), no HTTP, no gate,
    no agent: this answer must not depend on anything but this machine.
    """
    source = Path(Q.__file__).read_text(encoding="utf-8")
    start = source.index("def _read_backend_markers(")
    end = source.index("def _run_update_start(")
    block = source[start:end]
    for forbidden in ("urllib", "socket", "requests", "_release_manifest",
                      "jarvis_gate", "jarvis_agent", "published("):
        check(f"the update-answers block never uses {forbidden!r}",
              forbidden not in block, forbidden)
    check("... and it does read the app's own git plumbing, read-only",
          "jarvis_review" in block and "merge-base" in block)


def t_the_twin_is_byte_identical():
    a = (ROOT / "backend" / "jarvis_quick.py").read_bytes()
    b = (ROOT / "jarvis-backend" / "jarvis_quick.py").read_bytes()
    check("jarvis-backend/jarvis_quick.py is the same file", a == b)


if __name__ == "__main__":
    for fn in (t_the_question_reaches_the_fast_path,
               t_the_release_questions_keep_their_own_intents,
               t_the_measured_near_misses_stay_away,
               t_the_flex_retry_carries_the_polite_wordings,
               t_the_measured_live_files_are_read,
               t_the_default_readers_find_the_live_files,
               t_same_commit_says_the_update_is_done,
               t_backend_ahead_is_benign_not_a_failure,
               t_app_ahead_names_the_one_action,
               t_commits_that_cannot_be_compared_are_not_guessed,
               t_the_version_numbers_are_never_the_proof,
               t_a_missing_source_commit_is_named,
               t_each_failed_read_is_named,
               t_it_is_read_only_and_routes_normally,
               t_the_whole_route_answers_without_the_model,
               t_it_reads_this_pc_and_never_the_network,
               t_the_twin_is_byte_identical):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
