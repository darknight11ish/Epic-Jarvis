"""The memory pane's "as of" view: "current" from what Jarvis knew THEN.

    python3 test_bitemporal_asof.py

Runs anywhere: the route's code is taken from bitemporal.patch itself (both
copies - the whole patch and its rebuilt-patches half), the patch is
rehearsed on a stand-in jarvis_hud.py built from memory-pane.patch, and the
rows come from a real store (the rebuilt jarvis_memory.py) in a temp folder.
test_bitemporal.py covers the rest of the route, but needs the owner's
jarvis_hud.py; this part does not.

THE BUG IT PINS (audit K4). GET /api/memory/facts?known_at=T marked each row
"current" from TODAY's valid_to. The owner says on March 1 "I stopped living
on Elm Street on Feb 1": the fact gets retired_at = March 1, valid_to = Feb 1.
Asked "what did Jarvis believe on Feb 15", the row is rightly in the answer
(it was believed until March 1) but was marked not current - an end date
Jarvis only learned two weeks later. The rule now: a row in the belief set at
T with retired_at after T was current at T; valid_to is read only when
retired_at is empty (an end date nobody retracted, like a lease).
"""
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))    # after BACKEND: its copy wins

import _skeleton  # noqa: E402
import jarvis_memory as M  # noqa: E402

FAILED, PASSED = [], []
DAY = 86400.0
COPIES = ("bitemporal.patch", "rebuilt-patches/bitemporal.patch")
START = "rows = st.known_at(known, limit=limit)"
END = "return self._send(200, {"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def route_loop(after_image: str) -> str:
    """The code between the as-of query and its answer, dedented."""
    lines = after_image.splitlines()
    a = next(i for i, l in enumerate(lines) if l.strip() == START)
    b = next(i for i in range(a, len(lines)) if lines[i].strip() == END)
    return textwrap.dedent("\n".join(lines[a + 1:b]))


def rehearsed(copy: str):
    """(ok, jarvis_hud.py after the patch) on a stand-in memory-pane wrote."""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed"
    d = Path(tempfile.mkdtemp(prefix="jarvis-asof-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(_skeleton.build("memory-pane.patch"))
        (d / "p.patch").write_bytes((HERE / copy).read_bytes().replace(b"\r\n", b"\n"))
        inc = ["--include", "jarvis_hud.py"]
        for args in (["apply", "--check"], ["apply"], ["apply", "--check", "--reverse"]):
            r = subprocess.run([git] + args + inc + ["p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode:
                return False, f"git {' '.join(args)}: {r.stderr.strip()}"
        return True, (d / "jarvis_hud.py").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def world():
    """A store with the four kinds of row the as-of view has to label."""
    s = M.MemoryStore(path=Path(tempfile.mkdtemp(prefix="jarvis-asof-db-")) / "memory.db")
    now = time.time()
    jan1, feb1, feb15, mar1 = now - 60 * DAY, now - 45 * DAY, now - 30 * DAY, now - 20 * DAY
    ids = {k: s.add_fact(t) for k, t in (
        ("elm", "The owner lives on Elm Street"),
        ("live", "The owner likes tea"),
        ("lease", "The allotment lease runs out"),
        ("gone", "The owner drives a blue car"))}
    s.retire(ids["elm"], valid_to=feb1)             # told today: ended Feb 1
    s.retire(ids["lease"], valid_to=now + 90 * DAY)  # a future end: not retracted
    c = s._connect()
    c.execute("UPDATE facts SET created=?, valid_from=?", (jan1, jan1))
    # "gone": an end date nobody retracted (retired_at empty) that has passed.
    c.execute("UPDATE facts SET valid_to=?, retired_at=NULL WHERE id=?", (feb1, ids["gone"]))
    c.commit()
    c.close()
    return s, ids, {"feb15": feb15, "mar1": mar1, "now": now}


def labels(loop: str, rows: list, known: float) -> dict:
    ns = {"rows": rows, "known": known}
    exec(compile(loop, "<bitemporal.patch as-of loop>", "exec"), ns)
    return {r["id"]: r["current"] for r in rows}


def t_both_copies_rehearse_and_label_from_what_was_known():
    s, ids, at = world()
    for copy in COPIES:
        ok, out = rehearsed(copy)
        if ok is None:
            check(f"SKIP - {out}", True)
            continue
        check(f"{copy} applies to what memory-pane wrote, and reverses", ok, out[:400])
        if not ok:
            continue
        loop = route_loop(out)
        feb15 = labels(loop, s.known_at(at["feb15"], limit=500), at["feb15"])
        check(f"{copy}: Feb 15, a fact retired later (today) was current then, "
              f"although the end date given today is Feb 1", feb15.get(ids["elm"]) is True,
              feb15)
        check(f"{copy}: a fact never retired is current", feb15.get(ids["live"]) is True)
        check(f"{copy}: a lease with a future end date is current",
              feb15.get(ids["lease"]) is True)
        check(f"{copy}: an unretracted end date that had passed by then is not current",
              feb15.get(ids["gone"]) is False, feb15)
        today = labels(loop, s.known_at(at["now"] + 1, limit=500), at["now"] + 1)
        check(f"{copy}: asked about now, the Elm Street fact is not in the belief set",
              ids["elm"] not in today and today.get(ids["live"]) is True, today)


def t_the_two_copies_say_the_same():
    loops = []
    for copy in COPIES:
        text = (HERE / copy).read_text(encoding="utf-8").replace("\r\n", "\n")
        plus = "\n".join(l[1:] for l in text.splitlines() if l.startswith("+"))
        loops.append(route_loop(plus))
    check("bitemporal.patch and its rebuilt-patches half hold the same as-of loop",
          loops[0] == loops[1])
    check("and it reads retired_at before valid_to", 'r.get("retired_at")' in loops[0])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
