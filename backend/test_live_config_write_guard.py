"""A suite or probe can never write the owner's live settings (2026-11-18).

    python -B backend/test_live_config_write_guard.py

THE RULING THIS PINS. A lane admitted it briefly wrote the owner's live config
while probing: it turned the standing escalation switch off and lowered his
monthly money cap to $5, then restored both. While it was in that state the
app showed him a card saying "$5.00 of $5.00" while the money file said
$10.00. The review ruled: keep the harness rule that a scratch lane passes a
temporary settings folder, AND add a fail-fast guard so a process that has SAID
it is a suite or probe - `JARVIS_SUITE_RUNNING` - cannot write
`~/.openjarvis/`, without breaking the owner's own card flows.

WHAT THIS SUITE PROVES, with the real writers the product uses:

  1. With the marker set and a target inside the live folder, EVERY settings
     writer this branch wires REFUSES in plain words naming the file, and
     NOTHING is created or changed. The guard itself is also asked about all
     six live settings files the ruling names - including the preset ones that
     this branch may not wire - and refuses each by name.
  2. With the marker set and a temporary folder, the same writers succeed.
  3. WITHOUT the marker, the owner's normal write flow is unchanged: the
     writers land their files and read back the settings they wrote, and the
     untouched preset writers still write too.
  4. With the marker set, READING a live settings file is still allowed - that
     is how the battery measures - while a WRITE on a wired path refuses and
     leaves the live file byte-for-byte unchanged.
  5. The marker is the project's own existing one: `backend/_where.py` sets
     `JARVIS_SUITE_RUNNING` for every suite, and no shipped module ever SETS
     it, so the live backend cannot trip the guard. The live folder the guard
     refuses is resolved as the owner's own `~/.openjarvis`, not from
     `CONFIG_DIR` (a temporary `OPENJARVIS_CONFIG_DIR` is already safe, and
     that is what this suite itself uses).

THE PRESETS HALF IS NOT WIRED HERE, AND THIS SUITE SAYS SO. The standing
escalation switch and the cloud choice - `escalate-cloud.json` and
`cloud-choice.json` - are written only by `jarvis_presets._write_cloud_escalate`
and `_write_cloud_choice`. `backend/jarvis_presets.py` is on this lane's
"Do not touch" list (a parallel lane owns it), so this suite proves the guard
WOULD refuse those two live paths by name (the direct-guard arm below), and it
drives their READ functions to prove reads still work, but it does not drive
their writers. Wiring each of them is one call to
`jarvis_framework.refuse_live_config_write()` at the top of the writer - the
same shape as the two writers this branch does wire - and is a follow-up for
the owner of that file.

WHICH COPIES. `jarvis_chatbot_api.py` is shipped whole, so the copy under test
is this repository's `backend/` one. `jarvis_models.py` lives only on the
owner's PC and in the published base (`backend/_base.py`'s OWNER_ONLY rule), so
the copy under test is `jarvis-backend/jarvis_models.py`, and this suite prints
which one it read.

NOTHING IS WRITTEN TO `~/.openjarvis`. The "live" folder this suite refuses
writes into is a stand-in under its own temporary root, and the guard's
live-folder resolver is pointed at that stand-in - so even a bug that failed
to refuse would write into a throwaway folder instead of the owner's. Reads use
the same throwaway folder.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FRAME = Path(tempfile.mkdtemp(prefix="live-config-write-guard-"))
#: A throwaway stand-in for the owner's live folder. The guard is pointed at
#: this, never at the real one.
LIVE = FRAME / "live-home" / ".openjarvis"
#: The temporary settings folder a suite is supposed to pass instead.
TEMP = FRAME / "temporary-settings"
#: A stand-in for the owner's folder in the no-marker (normal flow) arm.
OWNER = FRAME / "owner-home" / ".openjarvis"

# --- isolation BEFORE the backend modules are imported ----------------------
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TEMP)
os.environ.pop("JARVIS_CONFIG_DIR", None)
os.environ.pop("JARVIS_MODEL_STATE", None)

from _where import REPO                    # noqa: E402  (also sets the marker)
import _base                               # noqa: E402

BASE = _base.folder("jarvis_models.py")
_base.put_on_path(BASE)

import jarvis_framework as fw              # noqa: E402  (backend/rebuilt/, shipped)
import jarvis_presets as P                 # noqa: E402  (backend/, shipped whole)
import jarvis_chatbot_api as API           # noqa: E402  (backend/, shipped whole)
import jarvis_models as M                  # noqa: E402  (the base's copy)

#: The owner's real folder as the guard resolves it, captured before this suite
#: points the guard at its stand-in. Used once, for the identity check.
REAL_LIVE = fw.live_config_dir()

_PASSED: list = []
_FAILED: list = []


def check(name, cond, detail=""):
    (_PASSED if cond else _FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _point(folder: Path) -> None:
    """Point every live-settings writer at `folder`, as each resolves its own."""
    P._config_dir = lambda: folder
    API.money_path = lambda: folder / "chatbot" / API.MONEY_FILE
    M.STATE = folder / "model-state.json"


def _writers():
    """(the file a refusal must name, the real writer call) for the live
    settings files this branch WIRES: the money ledger/cap and the current
    model record. The two preset files the incident also touched are written
    by `jarvis_presets.py`, which this lane's brief forbids touching - the
    guard is proved against those live paths in the direct-guard arm below."""
    return (
        (os.path.join("chatbot", API.MONEY_FILE),
         lambda: API._save({"version": 1, "limits": {}, "prices": {}, "months": {}})),
        ("model-state.json",
         lambda: M._write_state({"current": "qwen3.5:9b"})),
    )


#: Every live settings file the 2026-11-18 ruling names, as it sits in the
#: owner's folder. The guard must refuse a write to each, whoever writes it.
LIVE_SETTINGS_FILES = ("escalate-cloud.json",
                       "cloud-choice.json",
                       "presets-choice.json",
                       "presets-active-lane.json",
                       os.path.join("chatbot", API.MONEY_FILE),
                       "model-state.json")


# --------------------------------------------------------------------------
#   The marker is the project's own; the live folder is the owner's own
# --------------------------------------------------------------------------

def t_the_marker_is_the_projects_own_and_the_live_folder_is_his():
    where = REPO / "backend" / "_where.py"
    check("the marker is the one backend/_where.py already sets for every suite",
          fw.SUITE_RUNNING_ENV == "JARVIS_SUITE_RUNNING"
          and 'os.environ["JARVIS_SUITE_RUNNING"] = "1"' in where.read_text("utf-8"),
          fw.SUITE_RUNNING_ENV)
    check("this run already has it set, by the suite harness rather than this file",
          fw.suite_running() is True, os.environ.get(fw.SUITE_RUNNING_ENV))
    check("the guard's live folder is the owner's own ~/.openjarvis",
          REAL_LIVE == Path(os.path.expanduser("~")) / ".openjarvis", REAL_LIVE)
    check("a file in the owner's real folder classifies as live",
          fw.is_live_config_path(REAL_LIVE / "escalate-cloud.json") is True)
    check("a temporary settings file does not classify as live",
          fw.is_live_config_path(TEMP / "escalate-cloud.json") is False)

    setters = []
    for folder in (REPO / "backend" / "rebuilt", REPO / "backend",
                   REPO / "jarvis-backend"):
        for path in sorted(folder.glob("*.py")):
            if (path.name.startswith("test_")
                    or path.name in ("_where.py", "run_suites.py")):
                continue
            src = path.read_text("utf-8", "replace")
            if re.search(r'JARVIS_SUITE_RUNNING["\']\s*\]\s*=|'
                         r'setdefault\(\s*["\']JARVIS_SUITE_RUNNING', src):
                setters.append(f"{folder.name}/{path.name}")
    check("no shipped module sets the marker, so the live backend cannot trip "
          "the guard", not setters, setters)


# --------------------------------------------------------------------------
#   A live target refuses; a temporary one writes; reads stay allowed
# --------------------------------------------------------------------------

def t_the_guard_refuses_in_plain_words_and_writes_nothing_itself():
    fw.live_config_dir = lambda: LIVE
    os.environ[fw.SUITE_RUNNING_ENV] = "1"
    refusals = []
    for name in LIVE_SETTINGS_FILES:
        target = LIVE / name
        try:
            fw.refuse_live_config_write(target)
            refusals.append((name, ""))
        except fw.LiveConfigWriteRefused as exc:
            refusals.append((name, str(exc)))
        except Exception as exc:                          # noqa: BLE001 - reported
            refusals.append((name, f"{type(exc).__name__}: {exc}"))
    check("the guard refuses a write to every live settings file the ruling "
          "names", all(message for _, message in refusals),
          [name for name, message in refusals if not message])
    for name, message in refusals:
        check(f"the guard's refusal names the file it stopped ({name})",
              str(LIVE / name) in message, message)
    message = refusals[0][1]
    check("the message says nothing was written",
          "nothing was written" in message, message)
    check("the message says a suite must pass a temporary --config-dir",
          "--config-dir" in message and "OPENJARVIS_CONFIG_DIR" in message,
          message)
    check("the message names the live folder itself", str(LIVE) in message, message)
    check("the guard wrote nothing itself, so the live folder is still absent",
          not LIVE.exists(), str(LIVE))
    check("a temporary target passes the guard without raising",
          fw.refuse_live_config_write(TEMP / "x.json") is None)


def t_a_live_target_is_refused_and_nothing_is_created():
    fw.live_config_dir = lambda: LIVE
    _point(LIVE)
    writers = _writers()
    refused = []
    unexpected = []
    for name, write in writers:
        try:
            got = write()
            unexpected.append(f"{name} returned {got!r} instead of refusing")
        except fw.LiveConfigWriteRefused as exc:
            refused.append((name, str(exc)))
        except Exception as exc:                          # noqa: BLE001 - reported
            unexpected.append(f"{name} raised {type(exc).__name__}: {exc}")
    check("every settings writer this branch WIRES refuses a live target",
          len(refused) == len(writers),
          [n for n, _ in writers if n not in [r[0] for r in refused]])
    check("each refusal is the guard's own error, not some other failure",
          not unexpected, unexpected)
    for name, message in refused:
        check(f"the refusal names the file about to be written ({name})",
              name in message, message)
        check(f"the refusal says nothing was written ({name})",
              "nothing was written" in message, message)
        check(f"the refusal asks for a temporary --config-dir ({name})",
              "--config-dir" in message, message)
    check("nothing at all was created in the live folder", not LIVE.exists(),
          str(LIVE))


def t_a_temporary_target_is_written_normally():
    fw.live_config_dir = lambda: LIVE      # the marker is still set
    _point(TEMP)
    results = []
    for name, write in _writers():
        try:
            write()
            results.append((name, "ok"))
        except Exception as exc:                          # noqa: BLE001 - reported
            results.append((name, f"{type(exc).__name__}: {exc}"))
    check("every writer succeeds when the settings folder is temporary",
          all(result == "ok" for _, result in results), results)
    expected = (TEMP / "chatbot" / API.MONEY_FILE,
                TEMP / "model-state.json")
    check("every settings file this branch wires really landed in the "
          "temporary folder",
          all(path.is_file() for path in expected),
          [str(path) for path in expected if not path.is_file()])
    check("the live folder is still untouched by the suite-mode writes",
          not LIVE.exists(), str(LIVE))
    money = json.loads((TEMP / "chatbot" / API.MONEY_FILE).read_text("utf-8"))
    check("the money file holds the writer's real shape, not a stand-in",
          money.get("version") == 1, money)
    state = json.loads((TEMP / "model-state.json").read_text("utf-8"))
    check("the model record holds the writer's real shape, not a stand-in",
          state.get("current") == "qwen3.5:9b", state)


def t_without_the_marker_the_owners_write_flow_is_unchanged():
    fw.live_config_dir = lambda: OWNER
    _point(OWNER)
    saved = os.environ.pop(fw.SUITE_RUNNING_ENV, None)
    try:
        check("with the marker gone this is not a suite process",
              fw.suite_running() is False)
        results = []
        for name, write in _writers():
            try:
                write()
                results.append((name, "ok"))
            except Exception as exc:                      # noqa: BLE001 - reported
                results.append((name, f"{type(exc).__name__}: {exc}"))
        check("every owner-flow write succeeds with no marker set",
              all(result == "ok" for _, result in results), results)
        # The preset writers are NOT wired (their file is out of this lane's
        # brief), so the owner's own escalation write must be exactly as it
        # was: it writes, and it reads back.
        P._config_dir = lambda: OWNER
        check("the untouched preset writer still writes for the owner, with no "
              "marker set", P._write_cloud_escalate(True) is True)
        check("the escalation switch really landed in the owner's folder",
              (OWNER / "escalate-cloud.json").is_file())
        check("...and reads back as the setting that was written",
              P.escalate_on() is True)
        check("the owner's model record really landed and reads back",
              M.current_model() == "qwen3.5:9b", M.current_model())
        check("the owner's money file really landed",
              (OWNER / "chatbot" / API.MONEY_FILE).is_file())
    finally:
        os.environ[fw.SUITE_RUNNING_ENV] = saved if saved is not None else "1"


def t_a_read_on_a_live_path_is_still_allowed():
    fw.live_config_dir = lambda: LIVE
    _point(LIVE)
    (LIVE / "chatbot").mkdir(parents=True, exist_ok=True)
    pid = next(iter(API.PRESETS))
    switch_path = LIVE / "escalate-cloud.json"
    switch_path.write_text(json.dumps({"on": True, "on_since": 1.0}), "utf-8")
    (LIVE / "cloud-choice.json").write_text(json.dumps({"provider": pid}), "utf-8")
    money_path = LIVE / "chatbot" / API.MONEY_FILE
    money_path.write_text(json.dumps({"version": 1, "limits": {}, "prices": {},
                                      "months": {}}), "utf-8")
    before = money_path.read_text("utf-8")
    try:
        got = (P.escalate_on(), P.escalate_why(), P.cloud_chosen())
    except Exception as exc:                              # noqa: BLE001 - reported
        got = (f"RAISED {type(exc).__name__}: {exc}",) * 3
    check("a suite may still READ the live escalation switch, as the battery "
          "does", got[0] is True, got[0])
    check("...and its plain why sentence", got[1] == "", got[1])
    check("...and the live cloud choice", got[2] == pid, got[2])
    try:
        API._save({"version": 1, "limits": {}, "prices": {}, "months": {}})
        outcome = "the write went through"
    except fw.LiveConfigWriteRefused:
        outcome = "refused"
    except Exception as exc:                              # noqa: BLE001 - reported
        outcome = f"{type(exc).__name__}: {exc}"
    check("a WRITE on that same live folder is still refused",
          outcome == "refused", outcome)
    check("the refused write left the live file byte-for-byte unchanged",
          money_path.read_text("utf-8") == before)


def t_paths_are_compared_the_way_this_platform_compares_names():
    fw.live_config_dir = lambda: LIVE
    check("a file directly in the live folder is live",
          fw.is_live_config_path(LIVE / "escalate-cloud.json") is True)
    check("a file in a subfolder of the live folder is live",
          fw.is_live_config_path(LIVE / "chatbot" / API.MONEY_FILE) is True)
    check("a `..` path that lands back in the live folder is live",
          fw.is_live_config_path(LIVE / "sub" / ".." / "x.json") is True)
    windows = os.name == "nt"
    check("case is normalised the way %s compares names"
          % ("Windows" if windows else "POSIX"),
          fw.is_live_config_path(Path(str(LIVE).upper()) / "x.json") is windows)
    check("a temporary settings file is not live",
          fw.is_live_config_path(TEMP / "x.json") is False)
    check("a different `.openjarvis` folder elsewhere is not live",
          fw.is_live_config_path(FRAME / "elsewhere" / ".openjarvis" / "x.json")
          is False)


TESTS = (t_the_marker_is_the_projects_own_and_the_live_folder_is_his,
         t_the_guard_refuses_in_plain_words_and_writes_nothing_itself,
         t_a_live_target_is_refused_and_nothing_is_created,
         t_a_temporary_target_is_written_normally,
         t_without_the_marker_the_owners_write_flow_is_unchanged,
         t_a_read_on_a_live_path_is_still_allowed,
         t_paths_are_compared_the_way_this_platform_compares_names)


def main() -> int:
    print(f"  guard {Path(fw.__file__)}")
    print(f"  file  {Path(P.__file__)}")
    print(f"  file  {Path(API.__file__)}")
    if BASE is not None:
        print(f"  file  {_base.which(BASE, 'jarvis_models.py')}")
    print(f"  live  the guard is pointed at {LIVE} (never the owner's real folder)")
    try:
        for fn in TESTS:
            try:
                fn()
            except Exception:
                traceback.print_exc()
                _FAILED.append(f"{fn.__name__} raised")
    finally:
        shutil.rmtree(FRAME, ignore_errors=True)
    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        print("failed: " + ", ".join(_FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
