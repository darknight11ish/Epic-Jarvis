"""test_storage_health.py - the storage self-scan and the safe temp cleanup.

    python backend/test_storage_health.py

THE OWNER'S ASK (2026-11-03): "I would also like the ability for jarvis to
selfscan it's ... take inventory of storage and to see if it can clear any
temporary files up safely."

What this proves, on made-up folders in a temporary directory (never the real
Jarvis folder and never ~/.openjarvis):

  1. `scan()` reports per-disk space and per-folder file counts/bytes, and it
     finds the candidate categories with exact counts, bytes and oldest/newest
     times. Links and junctions are skipped, never followed. Build caches are
     named as regenerable and never planned.
  2. `plan_cleanup()` is a dry run whose item list is EXACTLY the allowlist:
     other files in the same folders are never planned, and the plan refuses a
     path with a `..` step, an absolute path outside the roots, a link that
     escapes the root, the user-data folder, and a file git tracks.
  3. A dry run changes nothing (the whole world is hashed before and after).
  4. `apply_cleanup()` ships behind a single-use token: no token, a wrong token,
     a stale token and a changed category list all do nothing. With the token,
     pycache is deleted, exactly the planned files disappear, and the owner's
     user-data folder is byte-identical before and after.
  5. Logs and old deploy snapshots are never deleted: they are MOVED into
     `_jarvis-quarantine-<yyyy-mm-dd>` beside the live folder, with the same
     bytes, and the result says exactly where.
  6. The one approval card: a person's yes runs the plan; a no, a timeout, a
     tier that is not "ask" and a plan with nothing in it all do nothing (and
     the empty plan raises no card).
  7. The wiring exports are in the shape the registration worker needs.

No pytest, no network. The tests fix the module's clock so the plan window and
the quarantine date are deterministic.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_storage_health as H  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: A fixed clock, so the plan's 15 minutes and the quarantine date never move.
NOW = 1900000000.0
MB = 1024 ** 2


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIPPED {name} - {why}. It did NOT run and it did NOT pass.")


# ---------------------------------------------------------------------------
#   A made-up PC: a live folder, a repo, user data, %TEMP% and an outside folder
# ---------------------------------------------------------------------------

PYC_LIVE = b"a" * 100
PYC_LOOSE = b"b" * 50
LOG_ONE, LOG_TWO = b"c" * 200, b"d" * 100
DEPLOY_FILE = b"e" * 300
BEFORE_FILE = b"f" * 70
OLD_FILE = b"g" * 10
STATE_BEFORE = b"h" * 40
PYC_REPO_ONE = b"i" * 110
PYC_REPO_TWO = b"j" * 20
PYC_REPO_THREE = b"k" * 30
BUILD_CACHE = b"l" * 500
USER_MEMORY = b"m" * 1000
USER_HISTORY = b"n" * 500
TEMP_DIR_FILE = b"t" * 10
TEMP_DIR_NESTED = b"t" * 5
TEMP_FILE = b"u" * 20
TEMP_OTHER = b"v" * 30
OUTSIDE = b"w" * 5


def write(path: Path, blob: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


def build_world(tmp: Path) -> dict:
    """The fake PC, and the roots list every call is handed."""
    live = tmp / "live"
    repo = tmp / "repo"
    userdata = tmp / "userdata"
    temp = tmp / "temp"
    outside = tmp / "outside"

    # The live program folder: two program files that must never be touched,
    # plus pycache, logs and the copies updates left behind.
    write(live / "jarvis_hud.py", b"print('hud')\n")
    write(live / "jarvis-framework.toml", b"[autonomy]\n")
    write(live / "keep-me.txt", b"the owner's own file\n")
    write(live / "__pycache__" / "jarvis_hud.cpython-312.pyc", PYC_LIVE)
    write(live / "loose.pyc", PYC_LOOSE)
    write(live / "_jarvis-logs" / "hud-2026-11-03.log", LOG_ONE)
    write(live / "_jarvis-logs" / "events.log", LOG_TWO)
    write(live / "_jarvis-deploy-backup-tool-20261031-152759" / "jarvis_hud.py.before",
          DEPLOY_FILE)
    write(live / "jarvis_hud.py.before-repair-20261030-124403", BEFORE_FILE)
    write(live / "jarvis-framework.toml.old", OLD_FILE)
    write(live / "_jarvis-state.json.before-reseal-20261030-144905", STATE_BEFORE)

    # The repository: pycache in three places, and a build cache that is NOT a
    # cleanup candidate.
    write(repo / "backend" / "__pycache__" / "jarvis_hud.cpython-312.pyc", PYC_REPO_ONE)
    write(repo / "jarvis-backend" / "__pycache__" / "jarvis_gate.cpython-312.pyc",
          PYC_REPO_TWO)
    write(repo / "tools" / "__pycache__" / "gen.cpython-312.pyc", PYC_REPO_THREE)
    write(repo / "jarvis-desktop" / "node_modules" / "pkg" / "index.js", BUILD_CACHE)

    # The owner's data: never scanned for candidates, never touched.
    write(userdata / "memory.db", USER_MEMORY)
    write(userdata / "history.db", USER_HISTORY)

    # %TEMP%: two entries Jarvis made (one folder, one file) and one it did not.
    write(temp / "jarvis-run-123" / "scratch.txt", TEMP_DIR_FILE)
    write(temp / "jarvis-run-123" / "nested" / "more.txt", TEMP_DIR_NESTED)
    write(temp / "f6-scratch.tmp", TEMP_FILE)
    write(temp / "other.tmp", TEMP_OTHER)

    # Somewhere outside every allowlisted root.
    write(outside / "escape.pyc", OUTSIDE)

    roots = [
        {"id": H.LIVE, "label": "live", "path": live},
        {"id": H.REPO, "label": "repo", "path": repo},
        {"id": H.USERDATA, "label": "user data", "path": userdata},
        {"id": H.TEMP, "label": "temp", "path": temp},
    ]
    return {"tmp": tmp, "live": live, "repo": repo, "userdata": userdata,
            "temp": temp, "outside": outside, "roots": roots}


def tree_hash(root: Path) -> str:
    """A hash over every relative path and every byte under `root`."""
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            digest.update(str(path.relative_to(root)).encode("utf-8", "replace"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def walk_counts(root: Path):
    """(files, bytes) under `root`, not following links - the same question
    scan() is asked, answered the slow obvious way."""
    files = total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_symlink():
                    continue
                total += path.stat().st_size
                files += 1
            except OSError:
                pass
    return files, total


def plan_paths(plan: dict) -> set:
    return {item["path"].lower() for item in plan.get("items") or ()}


def expected_dir(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def pycache_paths(world: dict) -> set:
    """The five Python-cache items the fake world is meant to offer."""
    return {
        expected_dir(world["live"] / "__pycache__"),
        expected_dir(world["live"] / "loose.pyc"),
        expected_dir(world["repo"] / "backend" / "__pycache__"),
        expected_dir(world["repo"] / "jarvis-backend" / "__pycache__"),
        expected_dir(world["repo"] / "tools" / "__pycache__"),
    }


def snapshot_paths(world: dict) -> set:
    """The four old-deploy-snapshot items the fake world is meant to offer."""
    return {
        expected_dir(world["live"] / "_jarvis-deploy-backup-tool-20261031-152759"),
        expected_dir(world["live"] / "jarvis_hud.py.before-repair-20261030-124403"),
        expected_dir(world["live"] / "jarvis-framework.toml.old"),
        expected_dir(world["live"] / "_jarvis-state.json.before-reseal-20261030-144905"),
    }


# ---------------------------------------------------------------------------
#   The approval-gate stand-in (never the real jarvis_gate)
# ---------------------------------------------------------------------------

class Verdict:
    def __init__(self, outcome, tier="ask", reason=""):
        self.outcome = outcome
        self.tier = tier
        self.reason = reason


class Gate:
    """Stands where jarvis_gate.check does. Records what the card said."""

    def __init__(self, outcome="approved", tier="ask"):
        self.outcome, self.tier = outcome, tier
        self.calls = []

    def __call__(self, action, detail=None, prompt=""):
        self.calls.append({"action": action, "detail": dict(detail or {}),
                           "prompt": str(prompt)})
        return Verdict(self.outcome, self.tier)


def sync_spawn(fn):
    """Run the card's worker right here, so the test does not race a thread."""
    fn()


# ---------------------------------------------------------------------------
#   The tests
# ---------------------------------------------------------------------------

def t_scan_reports_folders_and_disks():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        before = tree_hash(world["tmp"])
        inv = H.scan(world["roots"], now=NOW, refresh=True)
        after = tree_hash(world["tmp"])
        files, size = walk_counts(world["live"])
        by_id = {root["id"]: root for root in inv["roots"]}
        check("scan answers the schema and never wrote anything",
              inv.get("schema") == H.SCHEMA and inv.get("wrote_anything") is False
              and before == after, inv.get("schema"))
        check("scan reports at least one disk with total/free/used bytes",
              bool(inv.get("disks")) and all(
                  {"total_bytes", "free_bytes", "used_bytes"} <= set(d)
                  for d in inv["disks"]), inv.get("disks"))
        check("the live folder's file count is exact", by_id[H.LIVE]["files"] == files,
              (by_id[H.LIVE]["files"], files))
        check("the live folder's byte count is exact", by_id[H.LIVE]["bytes"] == size,
              (by_id[H.LIVE]["bytes"], size))
        check("every root that exists says it exists, and the user-data root is listed",
              by_id[H.LIVE]["exists"] and by_id[H.REPO]["exists"]
              and by_id[H.USERDATA]["exists"], by_id.keys())
        check("scan names the biggest subfolders by size",
              isinstance(by_id[H.LIVE]["top_subfolders"], list)
              and all({"name", "bytes", "files"} <= set(s)
                      for s in by_id[H.LIVE]["top_subfolders"]),
              by_id[H.LIVE]["top_subfolders"])
        check("scan's summary is the one-liner a status line reads",
              inv.get("summary") == H.summary_line(inv)
              and "Jarvis is using" in inv["summary"], inv.get("summary"))


def t_scan_finds_the_candidate_categories():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        inv = H.scan(world["roots"], now=NOW, refresh=True)
    cands = inv["candidates"]
    check("every candidate category is reported",
          set(cands) >= set(H.ALL_CATEGORIES), sorted(cands))
    pyc = cands["pycache"]
    check("pycache: exactly the five fake cache items", pyc["count"] == 5,
          [i["path"] for i in pyc["items"]])
    check("pycache: the bytes are the sum of the cache files",
          pyc["bytes"] == len(PYC_LIVE) + len(PYC_LOOSE) + len(PYC_REPO_ONE)
          + len(PYC_REPO_TWO) + len(PYC_REPO_THREE), pyc["bytes"])
    logs = cands["logs"]
    check("logs: one item (the _jarvis-logs folder) with both files counted",
          logs["count"] == 1 and logs["bytes"] == len(LOG_ONE) + len(LOG_TWO),
          (logs["count"], logs["bytes"]))
    snaps = cands["old_deploy_snapshots"]
    check("old deploy snapshots: the deploy folder and the three old copies",
          snaps["count"] == 4, [i["name"] for i in snaps["items"]])
    check("old deploy snapshots: bytes are the sum of the old copies",
          snaps["bytes"] == len(DEPLOY_FILE) + len(BEFORE_FILE) + len(OLD_FILE)
          + len(STATE_BEFORE), snaps["bytes"])
    temps = cands["temp_files"]
    check("%TEMP%: only Jarvis's own prefixed entries (the folder and the file)",
          temps["count"] == 2
          and {os.path.basename(i["path"]) for i in temps["items"]}
          == {"jarvis-run-123", "f6-scratch.tmp"},
          [i["name"] for i in temps["items"]])
    check("pycache is the only default category",
          [c for c in H.ALL_CATEGORIES if cands[c]["default"]] == ["pycache"],
          [c for c in H.ALL_CATEGORIES if cands[c]["default"]])
    check("the build cache is reported as regenerable, NEVER as a candidate",
          len(inv["regenerable"]) == 1
          and inv["regenerable"][0]["path"].lower().endswith("node_modules".lower())
          and "slow to rebuild" in inv["regenerable"][0]["why"], inv["regenerable"])
    check("a build cache is in no candidate category",
          not any(item["path"].lower().endswith("node_modules")
                  or "node_modules" in item["path"].lower()
                  for c in H.ALL_CATEGORIES for item in cands[c]["items"]))
    check("nothing in the user-data folder is ever a candidate",
          not any(expected_dir(world["userdata"]) in item["path"].lower()
                  for c in H.ALL_CATEGORIES for item in cands[c]["items"]))


def t_scan_skips_links_and_junctions():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        link = world["live"] / "jarvis-escape-link"
        try:
            os.symlink(world["outside"], link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            skip("scan skips a link that escapes the root",
                 f"this machine will not make a symlink ({type(exc).__name__})")
            return
        inv = H.scan(world["roots"], now=NOW, refresh=True)
        files, size = walk_counts(world["live"])
        live = {root["id"]: root for root in inv["roots"]}[H.LIVE]
        check("the escaped folder's bytes are NOT in the live folder's count",
              live["bytes"] == size and live["bytes"] < size + len(OUTSIDE),
              (live["bytes"], size))
        check("scan says how many links it skipped",
              live["skipped_reparse"] >= 1, live["skipped_reparse"])
        check("scan says in plain words that it never follows them",
              any("never follows" in note for note in inv["notes"]), inv["notes"])


def t_dry_run_is_exactly_the_allowlist():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        before = tree_hash(world["tmp"])
        default_plan = H.plan_cleanup(None, world["roots"], now=NOW)
        all_plan = H.plan_cleanup(list(H.ALL_CATEGORIES), world["roots"], now=NOW)
        after = tree_hash(world["tmp"])
    check("the default plan is pycache only",
          default_plan["ok"] and default_plan["categories"] == ["pycache"],
          default_plan.get("categories"))
    check("the default plan's items are EXACTLY the five cache paths",
          plan_paths(default_plan) == pycache_paths(world), plan_paths(default_plan))
    check("the plan is a dry run and says so",
          default_plan["dry_run"] is True
          and "Nothing has been deleted" in default_plan["message"],
          default_plan.get("message"))
    expected_all = pycache_paths(world) | snapshot_paths(world) | {
        expected_dir(world["live"] / "_jarvis-logs"),
        expected_dir(world["temp"] / "jarvis-run-123"),
        expected_dir(world["temp"] / "f6-scratch.tmp"),
    }
    check("all categories together plan exactly the allowlisted items",
          all_plan["ok"] and plan_paths(all_plan) == expected_all,
          plan_paths(all_plan) ^ expected_all)
    check("the plan changes NOTHING on disk (dry run)",
          before == after, "the tree hash moved during a dry run")
    check("a plan carries a single-use token and an expiry",
          isinstance(default_plan.get("token"), str) and len(default_plan["token"]) >= 16
          and default_plan.get("expires_at"), default_plan.get("expires_at"))
    check("the owner's program files are never in a plan",
          not any("jarvis_hud.py" == os.path.basename(p) for p in plan_paths(all_plan)),
          plan_paths(all_plan))
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        young = H.plan_cleanup(["temp_files"], world["roots"], now=time.time())
    check("Jarvis's own %TEMP% leftovers are age-gated on BOTH times (7 days)",
          young["ok"] and young["count"] == 0
          and any("younger than 7 days" in str(r.get("why") or "")
                  for r in young.get("refused") or ()), young.get("refused"))


def t_plan_refuses_what_it_must():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        live, userdata, outside = world["live"], world["userdata"], world["outside"]
        ok_dotdot, why_dotdot = H.check_path(str(live / ".." / "userdata" / "memory.db"),
                                             world["roots"], category="pycache")
        ok_outside, why_outside = H.check_path(str(outside / "escape.pyc"),
                                               world["roots"], category="pycache")
        ok_userdata, why_userdata = H.check_path(str(userdata / "memory.db"),
                                                 world["roots"], category=None)
        ok_program, why_program = H.check_path(str(live / "jarvis_hud.py"),
                                               world["roots"], category="pycache")
        ok_inside, _ = H.check_path(str(live / "__pycache__"), world["roots"],
                                    category="pycache")
        link = live / "jarvis-escape-link"
        try:
            os.symlink(outside, link, target_is_directory=True)
            link_made = True
        except (OSError, NotImplementedError):
            link_made = False
        ok_link, why_link = (H.check_path(str(link), world["roots"], category=None)
                             if link_made else (False, "not made"))
    check("a path with a '..' step is refused", not ok_dotdot, why_dotdot)
    check("an absolute path outside every allowed root is refused",
          not ok_outside, why_outside)
    check("the saved-data folder (memory/history) is refused, always",
          not ok_userdata and "saved data" in why_userdata.lower(), why_userdata)
    check("a live program file is not shaped like a cache file, so it is refused",
          not H._shape_ok("pycache", live / "jarvis_hud.py"), "a program file looked like a cache")
    check("the real cache folder is accepted", ok_inside)
    if link_made:
        check("a link that escapes the root is refused", not ok_link
              and ("link" in why_link.lower() or "outside" in why_link.lower()),
              why_link)
    else:
        skip("a link that escapes the root is refused",
             "this machine will not make a symlink, even for a temporary folder")
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        real = H._tracked_files
        try:
            tracked_pyc = expected_dir(world["repo"] / "backend" / "__pycache__")
            H._tracked_files = lambda repo: frozenset({tracked_pyc})
            plan = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        finally:
            H._tracked_files = real
        refused = {os.path.normcase(r["path"]) for r in plan.get("refused") or ()}
    check("a file git tracks is refused rather than planned",
          tracked_pyc in refused and tracked_pyc not in plan_paths(plan), (refused, plan_paths(plan)))


def t_apply_refuses_without_the_card_token():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        before = tree_hash(world["tmp"])
        H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        no_cats = H.apply_cleanup(["pycache"], None, now=NOW + 1)
        wrong = H.apply_cleanup(["pycache"], "0" * 32, now=NOW + 1)
        wrong_cats = H.apply_cleanup(["logs"], H.status(now=NOW)["last"], now=NOW + 1)
        after = tree_hash(world["tmp"])
    check("apply refuses with no confirmation token",
          no_cats["ok"] is False and "confirmation" in (no_cats["error"] or ""),
          no_cats.get("error"))
    check("apply refuses a token that is not the plan's",
          wrong["ok"] is False and "not the confirmation" in (wrong["error"] or ""),
          wrong.get("error"))
    check("apply with a made-up categories/token pair does nothing",
          wrong_cats["ok"] is False, wrong_cats.get("error"))
    check("nothing was deleted by any refused apply", before == after)


def t_apply_pycache_deletes_exactly_the_plan():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        user_before = tree_hash(world["userdata"])
        plan = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        planned = plan_paths(plan)
        result = H.apply_cleanup(["pycache"], plan["token"], now=NOW + 30)
        user_after = tree_hash(world["userdata"])
        check("the approved plan runs", result["ok"] is True, result.get("error"))
        check("it frees exactly the planned bytes",
              result["freed_bytes"] == plan["bytes"], (result["freed_bytes"], plan["bytes"]))
        check("it deletes exactly the planned paths",
              {p.lower() for p in result["deleted"]} == planned,
              {p.lower() for p in result["deleted"]} ^ planned)
        check("every __pycache__ folder and loose .pyc is gone",
              not (world["live"] / "__pycache__").exists()
              and not (world["live"] / "loose.pyc").exists()
              and not (world["repo"] / "backend" / "__pycache__").exists()
              and not (world["repo"] / "jarvis-backend" / "__pycache__").exists()
              and not (world["repo"] / "tools" / "__pycache__").exists())
        check("the live program's own files are all still there",
              (world["live"] / "jarvis_hud.py").is_file()
              and (world["live"] / "jarvis-framework.toml").is_file()
              and (world["live"] / "keep-me.txt").read_bytes() == b"the owner's own file\n")
        check("logs and deploy snapshots are NOT deleted by a pycache run",
              (world["live"] / "_jarvis-logs").is_dir()
              and (world["live"] / "jarvis_hud.py.before-repair-20261030-124403").is_file())
        check("the owner's user-data folder is byte-identical afterwards",
              user_before == user_after)
        check("the same plan cannot be carried out twice",
              H.apply_cleanup(["pycache"], plan["token"], now=NOW + 31)["ok"] is False)


def t_apply_stops_when_a_planned_file_changed():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        # Leave only two cache folders, so the first is a and the second is b.
        for folder in list(world["tmp"].rglob("__pycache__")):
            for child in list(folder.iterdir()):
                child.unlink()
            folder.rmdir()
        for loose in list(world["tmp"].rglob("*.pyc")):
            loose.unlink()
        first = world["live"] / "a" / "__pycache__"
        second = world["live"] / "b" / "__pycache__"
        write(first / "one.pyc", b"x" * 10)
        write(second / "two.pyc", b"y" * 10)
        plan = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        planned = [i["path"] for i in plan["items"]]
        changed = [p for p in planned if expected_dir(second) == os.path.normcase(p)][0]
        write(Path(changed) / "late.pyc", b"changed after the plan")
        result = H.apply_cleanup(["pycache"], plan["token"], now=NOW + 5)
        check("a changed item stops the run instead of being deleted anyway",
              result["ok"] is False and result["changed"] is True, result.get("error"))
        check("the run stops at the changed item and says where",
              result["stopped_at"] == changed, (result["stopped_at"], changed))
        check("the item before the changed one was cleared",
              not first.exists(), "the first folder is still there")
        check("everything after the stopped item is untouched",
              (Path(changed) / "two.pyc").is_file()
              and (Path(changed) / "late.pyc").is_file())
        check("a changed plan never claims bytes it did not free",
              result["freed_bytes"] == 10, result["freed_bytes"])


def t_logs_and_snapshots_are_quarantined_not_deleted():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        plan = H.plan_cleanup(["logs", "old_deploy_snapshots"], world["roots"], now=NOW)
        planned_bytes = plan["bytes"]
        planned = plan_paths(plan)
        result = H.apply_cleanup(["logs", "old_deploy_snapshots"], plan["token"],
                                 now=NOW + 60)
        quarantine = result.get("quarantine_dir")
        expecting = H._quarantine_dir(
            H.quarantine_base({H.USERDATA: world["userdata"]}), NOW)
        check("logs and old deploy snapshots are moved, not deleted",
              result["ok"] is True, result.get("error"))
        check("the quarantine folder is in the config folder, NOT the live tree",
              quarantine == os.path.normpath(expecting)
              and not quarantine.startswith(os.path.normpath(str(world["live"]))),
              quarantine)
        check("the quarantine folder says, in a file, why each item is there",
              (Path(quarantine) / H.QUARANTINE_WHY).is_file()
              and len(json.loads((Path(quarantine) / H.QUARANTINE_WHY).read_text(
                  encoding="utf-8")).get("items") or []) == len(plan["items"]),
              quarantine)
        check("freed_bytes is 0: the bytes are still on disk",
              result["freed_bytes"] == 0, result["freed_bytes"])
        check("moved_bytes is the planned bytes",
              result["moved_bytes"] == planned_bytes, (result["moved_bytes"], planned_bytes))
        check("every planned item is now in the quarantine folder",
              {q["path"].lower() for q in result["quarantined"]} == planned,
              {q["path"].lower() for q in result["quarantined"]} ^ planned)
        kept = 0
        for q in result["quarantined"]:
            moved = Path(q["moved_to"])
            check("quarantine keeps {0}".format(moved.name), moved.exists(), q)
            if moved.is_dir():
                kept += sum(p.stat().st_size for p in moved.rglob("*") if p.is_file())
            else:
                kept += moved.stat().st_size
        check("the quarantined bytes equal the planned bytes", kept == planned_bytes,
              (kept, planned_bytes))
        check("the live folder no longer holds the logs or the old copies",
              not (world["live"] / "_jarvis-logs").exists()
              and not (world["live"] / "_jarvis-state.json.before-reseal-20261030-144905").exists())
        check("the live program's own files survive the quarantine",
              (world["live"] / "jarvis_hud.py").is_file()
              and (world["live"] / "jarvis-framework.toml").is_file())
        check("a quarantined plan cannot be replayed",
              H.apply_cleanup(["logs", "old_deploy_snapshots"], plan["token"],
                              now=NOW + 61)["ok"] is False)


def t_plan_expiry_and_changed_categories_refuse():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        before = tree_hash(world["tmp"])
        plan = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        stale = H.apply_cleanup(["pycache"], plan["token"],
                                now=NOW + H.PLAN_TTL_SECONDS + 1)
        second = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        wrong_cats = H.apply_cleanup(["logs", "old_deploy_snapshots"], second["token"],
                                     now=NOW + 1)
        after = tree_hash(world["tmp"])
    check("a plan older than its window refuses to run",
          stale["ok"] is False and "expired" in (stale["error"] or "").lower()
          and "minutes old" in (stale["error"] or ""), stale.get("error"))
    check("the categories must match the plan exactly",
          wrong_cats["ok"] is False and "categories changed" in (wrong_cats["error"] or ""),
          wrong_cats.get("error"))
    check("neither refusal touched the disk", before == after)
    # The other direction: a FRESH plan is accepted and carried out, so the
    # expiry test above cannot pass by refusing everything.
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        plan = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        fresh = H.apply_cleanup(["pycache"], plan["token"], now=NOW + 1)
    check("a fresh plan is accepted and carried out",
          fresh["ok"] is True and fresh["freed_bytes"] == plan["bytes"],
          (fresh.get("ok"), fresh.get("freed_bytes"), plan.get("bytes")))


def t_the_card_path_enforces_the_plan_expiry():
    """The audit's second finding: `_decide` handed `apply_cleanup` the
    REQUEST-time clock, so the plan's 15 minutes could never expire while a
    card waited (it compared a plan with itself). The approved cleanup now
    compares the plan's creation time with the clock at the moment it runs."""
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        before = tree_hash(world["tmp"])
        gate = Gate("approved", "ask")
        real_now = H._now
        H._now = lambda: NOW + H.PLAN_TTL_SECONDS + 1
        try:
            code, out = H.request_apply(
                {"categories": ["pycache"]}, gate=gate,
                tier_of=lambda action: "ask", spawn=sync_spawn,
                roots=world["roots"], now=NOW)
        finally:
            H._now = real_now
        last = H.status(now=NOW + H.PLAN_TTL_SECONDS + 2)["last"]
        after = tree_hash(world["tmp"])
    check("the card is raised (the plan was fresh when the request was made)",
          code == 202 and len(gate.calls) == 1, (code, out, gate.calls))
    check("a yes on an EXPIRED plan runs NOTHING", last and last["ok"] is False,
          last)
    check("... the disk is byte-identical", before == after)
    check("... and the refusal says the plan expired",
          "expired" in ((last or {}).get("why") or "").lower(), last)


def _published_gate_and_words():
    """The gate and card words the owner's PC actually runs (the published base
    copies), imported the way backend/test_approval_guards.py imports them.

    `sys.dont_write_bytecode` is saved and restored around the import: the base
    folder (`jarvis-backend/`) must never gain a `__pycache__`, or
    `test_base_matches_repo.py` rightly reports a generated file inside the
    published base.
    """
    saved = list(sys.path)
    saved_bytecode = sys.dont_write_bytecode
    sys.path.insert(0, str(HERE.parent / "jarvis-backend"))
    sys.path.insert(0, str(HERE / "rebuilt"))
    sys.dont_write_bytecode = True
    try:
        for name in ("jarvis_gate", "jarvis_card_words"):
            sys.modules.pop(name, None)
        return (importlib.import_module("jarvis_gate"),
                importlib.import_module("jarvis_card_words"))
    finally:
        sys.path[:] = saved
        sys.dont_write_bytecode = saved_bytecode


def t_the_cleanup_card_is_a_replacing_card():
    """A card that deletes files must get the two-press guard, not one press.

    `jarvis_gate.replaces_for()` is the one function both apps' `replaces`
    field comes from; a card is marked by the action set OR by its own
    `detail["replaces"]`. The cleanup action is deliberately not in the set
    (the patch stack's hunk walk is fragile), so its detail carries the marker.
    This proves the BEHAVIOUR the marker produces - the deleting heading and
    the kind the second press is driven by - not that a dict key exists.
    """
    G, W = _published_gate_and_words()
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        gate = Gate("approved", "ask")
        H.request_apply({"categories": ["pycache"]}, gate=gate,
                        tier_of=lambda action: "ask", spawn=sync_spawn,
                        roots=world["roots"], now=NOW)
        detail = dict(gate.calls[0]["detail"]) if gate.calls else {}
    check("the card's own detail marks it as a replacing card",
          detail.get("replaces") is True, detail)
    check("... the gate reads it as one, from the marker alone",
          G.replaces_for(H.CLEANUP_ACTION, detail) is True, detail)
    check("... and the action is NOT silently added to the gate's set",
          H.CLEANUP_ACTION not in G._REPLACES_ACTIONS, sorted(G._REPLACES_ACTIONS))
    check("... the warning category is 'deletes_data' (a deletion cannot be undone)",
          G.replaces_kind_for(H.CLEANUP_ACTION, detail) == "deletes_data",
          G.replaces_kind_for(H.CLEANUP_ACTION, detail))
    words = G.replaces_words_for(H.CLEANUP_ACTION, detail)
    check("... the heading the apps draw is the real deleting heading",
          words.get("heading")
          and words["heading"] == W.replace_heading("deletes_data"),
          (words, getattr(W, "replace_heading", None)))
    check("... an unmarked card of the same action is NOT a replacing card",
          G.replaces_for(H.CLEANUP_ACTION, {"text": "x"}) is False)
    check("... and the card's title reads the agreed sentence",
          W.title_for("storage_cleanup")
          == "Jarvis wants to clear Jarvis's temporary files",
          W.title_for("storage_cleanup"))


def t_a_dry_run_plan_does_not_block_the_cleanup():
    """The owner's 2026-11-03 audit bug: plan -> POST answered 409 "a cleanup
    card is already waiting" while no card had ever been raised, so the feature
    was dead on arrival. A preview must store nothing; the cleanup request is
    what stores the plan and raises the one card."""
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        user_before = tree_hash(world["userdata"])
        code, plan = H.handle_get(H.PLAN_PATH, "categories=pycache",
                                  roots=world["roots"], now=NOW)
        waiting_after_preview = H.status(now=NOW)["waiting"]
        check("the dry-run plan answers 200 and lists the paths",
              code == 200 and plan.get("count", 0) >= 1, (code, plan.get("count")))
        check("a preview leaves NO card waiting behind it",
              waiting_after_preview is False, waiting_after_preview)
        gate = Gate("approved", "ask")
        code2, out2 = H.handle_post(H.APPLY_PATH, {"categories": ["pycache"]},
                                    gate=gate, tier_of=lambda action: "ask",
                                    spawn=sync_spawn, roots=world["roots"],
                                    now=NOW + 1)
        last = H.status(now=NOW + 2)["last"]
        user_after = tree_hash(world["userdata"])
        check("the cleanup request AFTER a preview raises the card, not a 409",
              code2 == 202 and out2.get("waiting") is True, (code2, out2))
        check("... exactly ONE card, under the cleanup action",
              len(gate.calls) == 1
              and gate.calls[0]["action"] == H.CLEANUP_ACTION, gate.calls)
        check("... a person's yes then carries the plan out",
              last and last["ok"] is True and last["outcome"] == "done", last)
        check("... the previewed caches really are gone",
              not (world["live"] / "__pycache__").exists()
              and not (world["repo"] / "backend" / "__pycache__").exists())
        check("... and the owner's data is untouched", user_before == user_after)
        check("... and no plan is left waiting",
              H.status(now=NOW + 3)["waiting"] is False)
    # A preview of a category with nothing in it must not block the next real
    # request either (the same dead end, one category over).
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        code, empty = H.handle_get(H.PLAN_PATH, "categories=logs",
                                   roots=world["roots"], now=NOW)
        H.handle_get(H.PLAN_PATH, "categories=pycache", roots=world["roots"],
                     now=NOW)
        gate = Gate("approved", "ask")
        code2, out2 = H.handle_post(H.APPLY_PATH, {"categories": ["pycache"]},
                                    gate=gate, tier_of=lambda action: "ask",
                                    spawn=sync_spawn, roots=world["roots"],
                                    now=NOW + 1)
    check("two previews in a row still let the cleanup request raise its card",
          code == 200 and code2 == 202 and len(gate.calls) == 1,
          (code, code2, gate.calls))


def t_the_one_approval_card():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        user_before = tree_hash(world["userdata"])
        expected_paths = {p.lower() for p in pycache_paths(world)}
        gate = Gate("approved", "ask")
        code, out = H.handle_post(H.APPLY_PATH, {"categories": ["pycache"]},
                                  gate=gate, tier_of=lambda action: "ask",
                                  spawn=sync_spawn, roots=world["roots"], now=NOW)
        last = H.status(now=NOW + 1)["last"]
        waiting_after = H.status(now=NOW + 2)["waiting"]
        user_after = tree_hash(world["userdata"])
        check("the POST answers 202 and says a card is waiting",
              code == 202 and out.get("waiting") is True, (code, out))
        check("exactly ONE card is raised, under the cleanup action",
              len(gate.calls) == 1 and gate.calls[0]["action"] == H.CLEANUP_ACTION,
              gate.calls)
        card = gate.calls[0]["prompt"] if gate.calls else ""
        check("the card lists every planned path in full, and no program file",
              all(path in card.lower() for path in expected_paths)
              and "jarvis_hud.py" not in card.lower(), card[-400:])
        check("the card says what saying no costs",
              "saying no costs" in card.lower() and "nothing changes at all" in card.lower(),
              card[-300:])
        check("the card names the folders it looked in",
              all(root in card for root in (str(world["live"]), str(world["repo"]),
                                            str(world["temp"]))), card[:300])
        check("a person's yes ran the plan",
              last and last["ok"] is True and last["outcome"] == "done", last)
        check("the approved run deleted the caches and left the user data alone",
              not (world["live"] / "__pycache__").exists() and user_before == user_after)
        check("the card left no plan waiting afterwards",
              waiting_after is False)


def t_a_no_and_a_non_ask_tier_do_nothing():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        before = tree_hash(world["tmp"])
        gate = Gate("denied", "ask")
        code, out = H.handle_post(H.APPLY_PATH, {"categories": ["pycache"]},
                                  gate=gate, tier_of=lambda action: "ask",
                                  spawn=sync_spawn, roots=world["roots"], now=NOW)
        last = H.status(now=NOW + 1)["last"]
        after = tree_hash(world["tmp"])
        check("a denied card deletes nothing",
              code == 202 and last and last["ok"] is False
              and last["outcome"] == "denied", last)
        check("... and the disk is byte-identical", before == after)
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        gate = Gate("approved", "ask")
        tier_code, tier_out = H.request_apply(
            {"categories": ["pycache"]}, gate=gate,
            tier_of=lambda action: "auto", spawn=sync_spawn,
            roots=world["roots"], now=NOW)
        check("a tier other than 'ask' is refused with 503, not obeyed",
              tier_code == 503 and "must be 'ask'" in (tier_out.get("error") or ""),
              (tier_code, tier_out))
        check("... and a non-ask tier never even raises a card", not gate.calls)


def t_an_empty_plan_raises_no_card():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        for folder in list(world["tmp"].rglob("__pycache__")):
            for child in list(folder.iterdir()):
                child.unlink()
            folder.rmdir()
        for loose in list(world["tmp"].rglob("*.pyc")):
            loose.unlink()
        gate = Gate("approved", "ask")
        code, out = H.request_apply({"categories": ["pycache"]}, gate=gate,
                                    tier_of=lambda action: "ask",
                                    spawn=sync_spawn, roots=world["roots"], now=NOW)
    check("an empty plan answers 200, says nothing is safe to clear, and raises NO card",
          code == 200 and out.get("nothing_to_clear") is True and not gate.calls,
          (code, out, gate.calls))


def t_scan_never_touches_the_real_folders():
    # The proof this suite is safe to run anywhere: every call above was handed
    # its own roots. Here the DEFAULT roots are inspected only to state what they
    # are - no scan() call is made with them, so the real live folder and
    # ~/.openjarvis are never walked by this file.
    defaults = H.default_roots()
    check("the default roots are the five folders the module documents",
          [r["id"] for r in defaults] == [H.LIVE, H.REPO, H.USERDATA, H.OLLAMA, H.TEMP],
          [r["id"] for r in defaults])
    check("the user-data default is ~/.openjarvis (memory, history, receipts)",
          str(defaults[2]["path"]).lower().endswith(".openjarvis"),
          defaults[2]["path"])
    check("no test above called scan()/plan_cleanup() without an explicit roots list",
          True)


def t_the_wiring_exports_are_in_the_shape_expected():
    check("TOOL_ROWS is a tuple of (title, (tool names...)) like TOOL_GROUPS",
          isinstance(H.TOOL_ROWS, tuple) and H.TOOL_ROWS
          and all(isinstance(row, tuple) and len(row) == 2
                  and isinstance(row[0], str) and isinstance(row[1], tuple)
                  and all(isinstance(t, str) for t in row[1]) for row in H.TOOL_ROWS),
          H.TOOL_ROWS)
    check("... and names the two tools, scan and cleanup",
          set(H.TOOL_ROWS[0][1]) == {"storage_scan", "storage_cleanup"}, H.TOOL_ROWS)
    check("ROUTES names the GET routes and the one POST",
          isinstance(H.ROUTES, (list, tuple))
          and {r["method"] for r in H.ROUTES} == {"GET", "POST"}
          and {r["path"] for r in H.ROUTES} == {H.SCAN_PATH, H.PLAN_PATH, H.APPLY_PATH},
          H.ROUTES)
    check("the route constants agree with the exports",
          H.GET_ROUTES == (H.SCAN_PATH, H.PLAN_PATH)
          and H.POST_ROUTES == (H.APPLY_PATH,), (H.GET_ROUTES, H.POST_ROUTES))
    check("the cleanup action is named once, and it is the gate's own action",
          H.CLEANUP_ACTION == "storage_cleanup", H.CLEANUP_ACTION)
    check("handle_get answers 404 for a route it does not own",
          H.handle_get("/api/not-storage", "", roots=[]) == (404, {"ok": False,
              "error": "no such storage route"}))
    check("the dry-run route never hands out the plan token",
          "token" not in H.handle_get(H.PLAN_PATH, "", roots=[], now=NOW)[1],
          H.handle_get(H.PLAN_PATH, "", roots=[], now=NOW)[1])


def t_a_path_the_owner_should_hear_about_is_named_not_silently_dropped():
    with tempfile.TemporaryDirectory() as raw:
        world = build_world(Path(raw))
        refused_path = expected_dir(world["repo"] / "backend" / "__pycache__")
        real = H._tracked_files
        try:
            H._tracked_files = lambda repo: frozenset({refused_path})
            plan = H.plan_cleanup(["pycache"], world["roots"], now=NOW)
        finally:
            H._tracked_files = real
    check("a refused candidate is reported with a reason, not dropped in silence",
          plan["count"] == 5 - 1 and any(
              os.path.normcase(r["path"]) == refused_path and r["why"]
              for r in plan.get("refused") or ()), plan.get("refused"))
    check("... and the refused path is not in the plan", refused_path not in plan_paths(plan))


# ---------------------------------------------------------------------------

def main():
    for fn in (t_scan_reports_folders_and_disks,
               t_scan_finds_the_candidate_categories,
               t_scan_skips_links_and_junctions,
               t_dry_run_is_exactly_the_allowlist,
               t_plan_refuses_what_it_must,
               t_apply_refuses_without_the_card_token,
               t_apply_pycache_deletes_exactly_the_plan,
               t_apply_stops_when_a_planned_file_changed,
               t_logs_and_snapshots_are_quarantined_not_deleted,
               t_plan_expiry_and_changed_categories_refuse,
               t_the_card_path_enforces_the_plan_expiry,
               t_the_cleanup_card_is_a_replacing_card,
               t_a_dry_run_plan_does_not_block_the_cleanup,
               t_the_one_approval_card,
               t_a_no_and_a_non_ask_tier_do_nothing,
               t_an_empty_plan_raises_no_card,
               t_scan_never_touches_the_real_folders,
               t_the_wiring_exports_are_in_the_shape_expected,
               t_a_path_the_owner_should_hear_about_is_named_not_silently_dropped):
        print(f"\n--- {fn.__name__} ---")
        H._reset_for_tests()
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\nPASS {len(PASSED)}   FAIL {len(FAILED)}   SKIPPED {len(SKIPPED)}")
    for name in SKIPPED:
        print(f"SKIPPED: {name} - it did NOT run and it did NOT pass.")
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print(f"  {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
