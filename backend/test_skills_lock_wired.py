#!/usr/bin/env python3
"""The skills.lock writer is WIRED into the skill life cycle (fixed 2026-11-09).

WHY THIS SUITE EXISTS. `jarvis_skill_hub` shipped `lock_entry()` / `write_lock()`
- the audit record of what a skill was scanned for and how far it may be
trusted - with tests, and `GET /api/skills/hub/lock` to read it. On 2026-11-09 an
audit found nothing in production ever WROTE it: the same built-but-unwired
shape as the four scan checks (DEF-049), and Gemini's ruling Q3 said wire it.

What is proven here, against temp folders and a stub gate - no network, no live
data, and the owner's real skills folder is never named:

  * an install writes ONE lock row: the name, the sha256 the install pinned, the
    verdict, the findings (including the four extra checks' codes), the scanner
    version, and a timestamp;
  * a review-level install (a bare URL warning) records `review` AND the
    `bare_url` finding - the extra checks reach the record, not only the card;
  * an edit (the same install path with new text) REPLACES the row with the new
    sha256 and a fresh timestamp;
  * a refused install writes NO row; a denied card writes NO row;
  * uninstall deletes that skill's row and leaves the OTHER rows alone;
  * with the hub absent, an install still works and writes no lock (an older
    base behaves exactly as before).

    py -3 -B backend/test_skills_lock_wired.py
"""
import os
import sys
import traceback
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402,F401

sys.path.insert(0, str(HERE / "rebuilt"))
# jarvis_skills.py is a base-only module: it lives in jarvis-backend/.
sys.path.append(str(REPO / "jarvis-backend"))

_SCRATCH = Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp") / (
    "jarvis-skills-lock-" + uuid.uuid4().hex[:8])
os.makedirs(_SCRATCH / "skills", exist_ok=True)
os.makedirs(_SCRATCH / "quarantine", exist_ok=True)
os.makedirs(_SCRATCH / "cfg", exist_ok=True)
os.environ["JARVIS_SKILLS_DIR"] = str(_SCRATCH / "skills")
os.environ["JARVIS_SKILLS_QUARANTINE"] = str(_SCRATCH / "quarantine")
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_SCRATCH / "cfg"))

require_shipped("jarvis_skill_hub.py")

import jarvis_skills as SK  # noqa: E402
import jarvis_skill_hub as H  # noqa: E402

SOURCES = _SCRATCH / "sources"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))
    return bool(cond)


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def make_skill(name, body):
    folder = SOURCES / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: does a thing\n---\n\n{body}\n",
        encoding="utf-8")
    return folder


class _Verdict:
    def __init__(self, allowed, tier, reason):
        self.allowed, self.tier, self.reason = allowed, tier, reason


class StubGate:
    def __init__(self, allowed=True, tier="ask", reason=""):
        self.allowed, self.tier, self.reason = allowed, tier, reason
        self.calls = []

    def check(self, action, detail=None, prompt=""):
        self.calls.append({"action": action, "detail": detail or {},
                           "prompt": prompt})
        return _Verdict(self.allowed, self.tier, self.reason)


class _GateModule:
    def __init__(self, gate):
        self.gate = gate

    def check(self, action, detail=None, prompt=""):
        return self.gate.check(action, detail=detail, prompt=prompt)


class with_gate:
    def __init__(self, gate):
        self.gate = gate

    def __enter__(self):
        self.had = sys.modules.get("jarvis_gate", "MISSING")
        sys.modules["jarvis_gate"] = _GateModule(self.gate)
        return self.gate

    def __exit__(self, *exc):
        if self.had == "MISSING":
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = self.had
        return False


def rows():
    return H.read_lock(skills_dir=Path(SK.SKILLS_DIR))


def findings_codes(row):
    return {f.get("code") for f in (row.get("findings") or [])}


# --------------------------------------------------------------------------
#   Install writes the row; edit replaces it; uninstall removes it
# --------------------------------------------------------------------------

def t_an_install_writes_one_lock_row():
    folder = make_skill("lock-plain",
                        "Use the punching-bag log when the owner asks about a workout.")
    expected_sha = SK.parse_skill(folder).sha256
    with with_gate(StubGate(allowed=True, tier="ask")):
        out = SK.install(folder)
    check("the install lands", out.get("ok") is True, out)
    report = out.get("report") or {}
    row = rows().get("lock-plain")
    check("exactly one lock row is written for it", row is not None, rows())
    if row:
        check("the row carries the sha256 the install pinned",
              row.get("sha256_hash") == expected_sha,
              (row.get("sha256_hash"), expected_sha))
        check("the row carries the scan verdict",
              row.get("verdict") == report.get("verdict") == "clean",
              (row.get("verdict"), report.get("verdict")))
        check("the row says which scanner version judged it",
              row.get("scanner_version") == H.SCANNER_VERSION, row)
        check("the row is on the trust ladder", row.get("trust_level") in H.TRUST_ORDER,
              row.get("trust_level"))
        check("the row has a timestamp", float(row.get("timestamp") or 0) > 0, row)
        check("the lock FILE is really there", Path(H.lock_path()).is_file(),
              Path(H.lock_path()))


def t_a_review_install_records_the_extra_finding():
    folder = make_skill("lock-review",
                        "See https://example.com/skills for the full procedure.")
    with with_gate(StubGate(allowed=True, tier="ask")):
        out = SK.install(folder, accept_warnings=True)
    check("the warned install lands once a person accepted", out.get("ok") is True, out)
    row = rows().get("lock-review")
    check("the row records the review verdict", row and row.get("verdict") == "review",
          row)
    check("and the four extra checks' finding is IN the record",
          row is not None and "bare_url" in findings_codes(row),
          row.get("findings") if row else None)


def t_an_edit_replaces_the_row():
    folder = make_skill("lock-edited", "First version of the instructions.")
    with with_gate(StubGate(allowed=True, tier="ask")):
        SK.install(folder)
    first = rows().get("lock-edited") or {}
    (folder / "SKILL.md").write_text(
        "---\nname: lock-edited\ndescription: does a thing\n---\n\n"
        "Second version of the instructions, longer.\n", encoding="utf-8")
    new_sha = SK.parse_skill(folder).sha256
    with with_gate(StubGate(allowed=True, tier="ask")):
        out = SK.install(folder)
    second = rows().get("lock-edited") or {}
    check("the edit lands", out.get("ok") is True, out)
    check("the row now carries the NEW sha256",
          second.get("sha256_hash") == new_sha
          and second.get("sha256_hash") != first.get("sha256_hash"),
          (first.get("sha256_hash"), second.get("sha256_hash"), new_sha))
    check("and a fresh timestamp",
          float(second.get("timestamp") or 0) >= float(first.get("timestamp") or 0),
          (first.get("timestamp"), second.get("timestamp")))


def t_a_refused_install_writes_no_row():
    folder = make_skill("lock-refused",
                        "Run !`git config --global user.email` first.")
    gate = StubGate()
    with with_gate(gate):
        out = SK.install(folder)
    check("the refused install never asks", out.get("asked") is False, out)
    check("no lock row is written for a refused skill",
          "lock-refused" not in rows())


def t_a_denied_card_writes_no_row():
    folder = make_skill("lock-denied", "An ordinary body that looks fine.")
    gate = StubGate(allowed=False, tier="ask", reason="you said no")
    with with_gate(gate):
        out = SK.install(folder)
    check("the person said no", out.get("ok") is False, out)
    check("no lock row is written for a denied skill",
          "lock-denied" not in rows())


def t_uninstall_removes_only_that_row():
    keep = make_skill("lock-kept", "An ordinary body that looks fine.")
    drop = make_skill("lock-dropped", "Another ordinary body, fine too.")
    with with_gate(StubGate(allowed=True, tier="ask")):
        SK.install(keep)
        SK.install(drop)
    check("both rows exist before removal",
          {"lock-kept", "lock-dropped"} <= set(rows()), sorted(rows()))
    out = SK.uninstall("lock-dropped")
    check("the removal lands", out.get("ok") is True, out)
    left = rows()
    check("the removed skill's row is GONE", "lock-dropped" not in left, sorted(left))
    check("the other skill's row is untouched", "lock-kept" in left, sorted(left))


def t_without_the_hub_an_install_still_works():
    folder = make_skill("lock-no-hub", "An ordinary body that looks fine.")
    had = sys.modules.get("jarvis_skill_hub", "MISSING")
    sys.modules["jarvis_skill_hub"] = None
    try:
        with with_gate(StubGate(allowed=True, tier="ask")):
            out = SK.install(folder)
    finally:
        if had == "MISSING":
            sys.modules.pop("jarvis_skill_hub", None)
        else:
            sys.modules["jarvis_skill_hub"] = had
    check("the install still works with no hub beside the base",
          out.get("ok") is True, out)


def t_forget_lock_is_whole_file_and_idempotent():
    ok = H.forget_lock("lock-never-installed")
    check("forgetting an unknown skill is a plain answer, not an error",
          ok.get("ok") is False and ok.get("removed") is False, ok)
    check("the lock is still readable afterwards", isinstance(rows(), dict))


def main():
    print("jarvis_skills.py + jarvis_skill_hub.py: skills.lock is WIRED")
    for fn in (t_an_install_writes_one_lock_row,
               t_a_review_install_records_the_extra_finding,
               t_an_edit_replaces_the_row,
               t_a_refused_install_writes_no_row,
               t_a_denied_card_writes_no_row,
               t_uninstall_removes_only_that_row,
               t_without_the_hub_an_install_still_works,
               t_forget_lock_is_whole_file_and_idempotent):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
