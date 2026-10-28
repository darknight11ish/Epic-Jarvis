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

A fourth tree is the shape #727 / F11 produces: the phone's work-offer surface is
removed whole, so the old builder is gone and the route has NO call site in
either app while still classified `planned` (the PC route remains). It must be a
`RETIRED` warning naming the reason, never the "classified 'planned' but nothing
checks it" error. A fifth tree wires the route up again in BOTH apps (a real
literal in the desktop's JS and the phone's Kotlin): the same `RETIRED` entry
must then be a FAILURE in both directions - a retired route is not allowed to be
called again - with the "remove RETIRED, reclassify" message, never a warning.

THE DOCUMENTED ROUTE UNIVERSE (added 2026-10-28; the wiring audit's blind spot).
The checker used to build its route sets only from the two apps' source, so a
route neither app called was in neither set and failed nothing. It now also
reads `docs/JARVIS-API.md` and requires every route documented there to be
called, classified, or in `BACKEND_ONLY` with a written reason. This suite
proves that half without touching the repository: the fixture checkout carries a
small `docs/JARVIS-API.md` that documents every `BACKEND_ONLY` route (so the
register's own reverse check is satisfied) plus one classified route and a fake
section-8 table naming a route that does not exist. It then proves:

  6. the base tree passes the new check - a documented route in BACKEND_ONLY,
     and a documented route in CLASSIFICATION, are both accounted for;
  7. a documented route that is in neither fails, names the route, and says
     both ways out (add it to BACKEND_ONLY with a reason, or wire a caller);
  8. a BACKEND_ONLY route the desktop starts calling fails, so the reason
     cannot go stale and hide a route that is no longer backend-only;
  9. a BACKEND_ONLY route the doc stops documenting fails, so the register
     cannot carry routes the contract does not name.
"""
import os
import runpy
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


def _backend_only_routes():
    """The checker's own BACKEND_ONLY keys.

    Read by executing check_parity.py as a module (its `main()` is under the
    usual `if __name__` guard), so this suite cannot drift from the register:
    the fixture doc always documents exactly the routes the register claims.
    """
    return sorted(runpy.run_path(str(TOOL))["BACKEND_ONLY"])


def _doc_stub(extra=(), omit=()):
    """A small JARVIS-API.md the checker will parse.

    It documents every BACKEND_ONLY route (so the register's reverse check is
    satisfied), one classified route, any `extra` routes, and a section 8 table
    naming a route that does not exist - proving the draft section is skipped
    rather than demanded.
    """
    routes = [r for r in _backend_only_routes() if r not in omit]
    routes += list(extra)
    routes.append("/api/work/recommend")  # classified in CLASSIFICATION
    body = "\n".join(f"GET  {r}" for r in routes)
    return (
        "# JARVIS-API (fixture, for backend/test_parity_callgraph.py)\n\n"
        "## 1. The routes this fixture documents\n\n"
        "```\n" + body + "\n```\n\n"
        "## 8. Draft, proposed, or not actually wired\n\n"
        "| Route | Status |\n|---|---|\n"
        "| `/api/not-a-real-route` | **Does not exist.** |\n\n"
        "## 9. Rules that constrain this API\n"
    )


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
#: The planned-loop failure the pre-#731 tree raised on the removed-surface
#: tree; a retired route must never produce it.
PLANNED_NOTHING = "/api/work/recommend is classified 'planned' but nothing checks it"
#: What the checker says instead: retired, with the F11 reason, as a warning.
RETIRED_SAID = "/api/work/recommend is 'planned' and RETIRED"
#: A retired route called again by an app is a FAILURE, not a warning.
RETIRED_DESK_ERROR = "/api/work/recommend is RETIRED but the desktop calls it again"
RETIRED_PHONE_ERROR = "/api/work/recommend is RETIRED but the phone calls it again"
#: The new documented-route check (2026-10-28). A documented route in no app
#: and in no table used to be invisible; it must now FAIL and say both ways out.
DOC_UNCLASSIFIED = "is documented in docs/JARVIS-API.md (line"
DOC_WAYS_OUT = "Add it to BACKEND_ONLY with a written reason"
#: The register's own two stale directions.
BACKEND_ONLY_WIRED = "is in BACKEND_ONLY but the desktop calls it now"
BACKEND_ONLY_UNDOCUMENTED = "is in BACKEND_ONLY in tools/check_parity.py but"


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
        _put(root, "docs/JARVIS-API.md", _doc_stub())

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
        # A documented route in BACKEND_ONLY, and a documented route that is
        # classified, are both accounted for: the new check must stay silent
        # about them (the fixture doc documents every register entry).
        check("a documented route in BACKEND_ONLY is accounted for",
              DOC_UNCLASSIFIED not in first, first[-800:])

        # ... but a documented route in NO app and NO table is the blind spot
        # this check exists for, and it must FAIL with both ways out.
        _put(root, "docs/JARVIS-API.md",
             _doc_stub(extra=["/api/zzz-not-classified"]))
        sixth = _run(root)
        check("a documented route no app calls and no table names FAILS",
              DOC_UNCLASSIFIED in sixth,
              "the checker stayed silent over a documented route in no app:\n"
              + sixth[-800:])
        check("... naming the route", "/api/zzz-not-classified" in sixth,
              sixth[-800:])
        check("... and both ways out: BACKEND_ONLY with a reason, or a caller",
              DOC_WAYS_OUT in sixth and "wire a caller" in sixth, sixth[-800:])
        _put(root, "docs/JARVIS-API.md", _doc_stub())
        check("... and the same tree passes again once the route is accounted for",
              DOC_UNCLASSIFIED not in _run(root))

        # The register's own honesty: it must not carry a route the doc does not
        # document, and it must not carry a route an app has started calling.
        _put(root, "docs/JARVIS-API.md", _doc_stub(omit=["/api/receipts"]))
        seventh = _run(root)
        check("a BACKEND_ONLY route the doc stops documenting FAILS",
              BACKEND_ONLY_UNDOCUMENTED in seventh, seventh[-800:])
        _put(root, "docs/JARVIS-API.md", _doc_stub())
        _put(root, "jarvis-desktop/src/receipts.js",
             "fetch('/api/receipts');\n")
        eighth = _run(root)
        check("a BACKEND_ONLY route the desktop starts calling FAILS",
              BACKEND_ONLY_WIRED in eighth,
              "a backend-only reason that has stopped being true must not pass:\n"
              + eighth[-800:])
        (root / "jarvis-desktop/src/receipts.js").unlink()

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
        # #727 / F11 removes the phone surface whole. The route is still classified
        # `planned` (the PC route remains) and no app calls it; the RETIRED
        # declaration must make that a warning that says so, never an error.
        check("... and the planned loop does NOT fail the removed-surface tree",
              PLANNED_NOTHING not in fourth, fourth[-600:])
        check("... and it says the route is RETIRED, with the F11 reason, as a warning",
              RETIRED_SAID in fourth and "F11" in fourth, fourth[-600:])
        check("... naming it once", fourth.count(RETIRED_SAID) == 1, fourth[-600:])

        # A retired route being wired up AGAIN must fail, not warn. Put a real
        # `/api/...` literal in BOTH apps (the desktop's JS window and the phone's
        # Kotlin) - the shape a re-wire takes in the checker's scanner.
        _put(root, "jarvis-desktop/src/rewired.js",
             "fetch('/api/work/recommend');\n")
        _put(root, "jarvis-client/app/src/main/java/com/jarvis/client/ui/Rewired.kt",
             "package com.jarvis.client.ui\n\n"
             "suspend fun rewired() {\n"
             "    api.post(\"/api/work/recommend\")\n"
             "}\n")
        fifth = _run(root)
        check("a retired route the DESKTOP calls again is an ERROR, not a warning",
              RETIRED_DESK_ERROR in fifth, fifth[-700:])
        check("... and the same for the PHONE calls it again",
              RETIRED_PHONE_ERROR in fifth, fifth[-700:])
    finally:
        shutil.rmtree(str(root), ignore_errors=True)

    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed in test_parity_callgraph: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
