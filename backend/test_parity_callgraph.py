"""`tools/check_parity.py` must not report a route as called when the only code
that names it is a function nothing calls.

    python3 test_parity_callgraph.py

WHY THIS SUITE EXISTS. On 2026-10-11 `check_parity.py` told this project that
the phone called `POST /api/work/recommend`. Nothing did: the route is built
inside `JarvisRuntime.offerWorkSetup`, and no Kotlin file under
`jarvis-client/app/src/main` called that function - so the offer panel in
`HardwarePlate.kt` ("Jarvis suggests a setup") could never be populated. The
checker had matched a string, and a string is not a call.

The checker now carries `UNREACHABLE`: each entry names the file and the
function that builds a route nothing calls, and the checker refuses to let that
declaration go stale in EITHER direction. This suite proves the second
direction, which is the one that matters for shipping: **the moment the route
is genuinely wired up, the declaration must be deleted, and the checker says so
out loud instead of quietly passing.**

HOW IT PROVES IT, without touching this repository. It builds a throwaway
checkout holding only the files the check reads (three Kotlin constants, the
runtime's one function, a stub `routes.rs` and an empty desktop `src/`), points
the REAL `tools/check_parity.py` at it through `JARVIS_PARITY_ROOT`, and runs it
three times:

  1. as the branch really is - one function, no caller. The declaration must
     hold: no "declared unreachable" error, and (the defect itself) no
     "the phone calls it" warning either. The route must instead be NAMED as
     one neither app calls, once, and kept out of the list of routes the phone
     is on - going quiet about it was the follow-up defect, and this suite pins
     the sentence both docs quote;
  2. with one real call site added in the phone's UI and a live caller above it
     - the shape a genuine fix takes. The checker MUST fail, and its message
     must name the entry to delete;
  3. with the same call site but its own function uncalled. This is the defect
     one level down, and the interesting case: a checker that only counts call
     sites passes this tree, and such a checker would also have passed the real
     phone on 2026-10-11. It must still say the declaration is stale - and still
     name the route as one neither app calls.

The fake checkout fails other checks of its own (it has no desktop routes at
all), so the runs are told apart by the message, never by the exit code alone.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, missing  # noqa: E402

TOOL = REPO / "tools" / "check_parity.py"
REAL_ROUTES = REPO / "jarvis-desktop" / "src-tauri" / "src" / "brain" / "routes.rs"

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   The tiny checkout the checker is pointed at
# --------------------------------------------------------------------------

#: The real runtime, cut to the one function. Kept as source rather than a copy
#: of the file so the suite cannot drift into testing the whole phone.
RUNTIME = """package com.jarvis.client

object JarvisRuntime {
    private val api: Api = Api()

    suspend fun offerWorkSetup(words: String): String? {
        val result = api.workPost(WorkSetups.RECOMMEND_PATH, words)
        return result
    }
}
"""

#: The three route constants, exactly as `net/WorkSetups.kt` declares them.
CONSTS = """package com.jarvis.client.net

object WorkSetups {
    const val PATH = "/api/work"
    const val RECOMMEND_PATH = "/api/work/recommend"
    const val CHOOSE_PATH = "/api/work/choose"
}
"""

#: What a real fix looks like: the phone's own screen asks for the offer before
#: it draws one. `wiredTurn` is called, so `offerWorkSetup` is reachable.
WIRED = """package com.jarvis.client.ui

suspend fun wiredTurn(words: String) {
    askThePcForAnOffer(words)
}

private suspend fun askThePcForAnOffer(words: String) {
    JarvisRuntime.offerWorkSetup(words)
}
"""

#: The same call site with its own function UNCALLED - the defect one level
#: down, and the case a call-site-only check gets wrong.
GHOST = """package com.jarvis.client.ui

private suspend fun askThePcForAnOffer(words: String) {
    JarvisRuntime.offerWorkSetup(words)
}
"""

DESKTOP_STUB = """// a stub: this suite is about the phone's side of the check
pub fn brain_read() {}
pub fn nothing_else() {}
"""


def _put(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _routes_stub():
    """The real READ_ROUTES list, so `apply_allowlists` has nothing to report,
    inside a file small enough to write into a temporary tree."""
    if not REAL_ROUTES.is_file():
        return None
    text = REAL_ROUTES.read_text(encoding="utf-8")
    start = text.find("READ_ROUTES")
    if start < 0:
        return None
    at = text.find("&[", start)
    end = text.find("];", at)
    if at < 0 or end < 0:
        return None
    return DESKTOP_STUB + "\n" + text[start:end + 2] + "\n"


def _run(root):
    env = dict(os.environ)
    env.pop("JARVIS_BACKEND", None)
    env["JARVIS_PARITY_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    done = subprocess.run([sys.executable, str(TOOL)], cwd=str(root),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)
    return (done.stdout or "") + (done.stderr or "")


DECLARED_GONE = "is declared unreachable in tools/check_parity.py"
NOT_WIRED = "/api/work/recommend is 'planned' and the phone calls it"
#: What the tool must SAY instead of the false line above - the missing half.
#: Silently saying nothing was the follow-up defect: the line was gone, and with
#: it every mention of the route, so the tool under-reported what it knew. The
#: checker must name it, and `docs/WORK-SETUPS.md` and `docs/JARVIS-API.md`
#: section 124.4 quote this sentence.
NOTHING_CALLS_IT = "/api/work/recommend is 'planned' and NEITHER app calls it"


def main():
    if not TOOL.is_file():
        skip("tools/check_parity.py is not in this checkout")
        return 0
    stub = _routes_stub()
    if stub is None:
        skip("jarvis-desktop/.../routes.rs is not in this checkout, so the "
             "checker cannot be run against a stand-in")
        return 0

    root = Path(tempfile.mkdtemp(prefix="parity-callgraph-"))
    try:
        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/net/WorkSetups.kt",
             CONSTS)
        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
             RUNTIME)
        _put(root, "jarvis-desktop/src-tauri/src/brain/routes.rs", stub)
        _put(root, "jarvis-desktop/src/empty.js", "// a desktop window file, in name only\n")

        first = _run(root)
        check("the real checker runs against the stand-in", bool(first), first[-400:])
        check("as the branch is, the UNREACHABLE declaration is NOT stale",
              DECLARED_GONE not in first)
        check("... and the checker no longer claims the phone calls it",
              NOT_WIRED not in first)
        check("... and it SAYS the missing half instead: NEITHER app calls it",
              NOTHING_CALLS_IT in first, first[-600:])
        check("... and says it once, not twice",
              first.count(NOTHING_CALLS_IT) == 1, first[-600:])
        check("... and does not list it among the routes the phone is on",
              "\n  /api/work/recommend " not in first,
              "the route is in `phone` only because a literal names it; a literal "
              "is not a call, so it must not appear in the phone's own list")

        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/ui/Wired.kt", WIRED)
        second = _run(root)
        check("... but ONE real call site makes the checker fail",
              DECLARED_GONE in second,
              "the checker passed with the offer wired up; the UNREACHABLE "
              "entry for /api/work/recommend would now be a lie")
        check("... and the failure names the route and what to do",
              "/api/work/recommend" in second and "Delete the UNREACHABLE entry" in second,
              second[-600:])
        check("... and it says the function is REACHED, and from where",
              "offerWorkSetup is now REACHED" in second
              and "askThePcForAnOffer()" in second
              and "Wired.kt:8" in second,
              second[-600:])

        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/ui/Wired.kt", GHOST)
        third = _run(root)
        check("a call site inside a function NOTHING calls does not count either",
              DECLARED_GONE not in third,
              "the checker counted a call site without asking whether its own "
              "function is called - the exact defect it exists to catch:\n"
              + third[-600:])
        check("... and that tree still SAYS NEITHER app calls it",
              NOTHING_CALLS_IT in third,
              "the declaration holds, so the tool must keep naming the missing "
              "half rather than going quiet about the route:\n" + third[-600:])

        # F11 (2026-10-22): the dead phone work-offer surface is removed WHOLE.
        # The declaration is then obsolete, not stale: it must be dropped
        # silently, on both trees, so the parity fix can land before or after
        # the phone PR without a deadlock. This is the shape #727 produces.
        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/net/WorkSetups.kt",
             CONSTS.replace('    const val RECOMMEND_PATH = "/api/work/recommend"\n', ""))
        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
             "package com.jarvis.client\n\nobject JarvisRuntime {\n"
             "    private val api: Api = Api()\n}\n")
        fourth = _run(root)
        check("the removed-surface tree does not call the declaration stale",
              DECLARED_GONE not in fourth,
              "the declaration describes a surface that no longer exists; it must "
              "not fail the tree it is obsolete on:\n" + fourth[-600:])
        check("... and it is dropped silently rather than named as a missing half",
              NOTHING_CALLS_IT not in fourth,
              "the route is not in either app at all, so there is no missing half "
              "to name:\n" + fourth[-600:])
        check("... and the route is not put back into the phone's set",
              "/api/work/recommend is 'planned' and the phone calls it" not in fourth,
              fourth[-600:])
    finally:
        shutil.rmtree(str(root), ignore_errors=True)

    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed in test_parity_callgraph: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
