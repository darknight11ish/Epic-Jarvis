"""test_sky_cases_tool.py - tools/gen_sky_cases.py, the fixture AND its guard.

    python3 backend/test_sky_cases_tool.py

`tools/gen_sky_cases.py` writes the one "Sun, moon and weather" contract both
apps read, by running the real backend module and writing down what it answers.
Two things about it are worth a suite of its own:

  1. THE FIXTURE IS CURRENT. CI runs `python tools/gen_sky_cases.py --check`
     (ci.yml, the `frontend` job), so a backend change nobody carried into the
     two copies is caught there. This asserts the same thing where the
     repository's own suite sweep can see it, and it fails the same way, by
     naming the file that is out of date.

  2. THE EMPTY QUEUE SAYS SO. Measured 2026-10-07 (BUG-AUDIT-2026-10-05 B4,
     infra audit D8), the generator died in CI with
     `IndexError: list index out of range`. The shape: `held = []`,
     `request_weather(..., spawn=held.append)`, then `held[0]()`; the two
     `handle_post` calls above it DISCARD their return codes, so a throwaway
     config folder that cannot be written leaves no town stored,
     `request_weather` answers 409 before it ever reaches `spawn`, `held` stays
     empty, and the failure reaches the reader as a bare traceback naming a
     line rather than a sentence naming the cause.

     So the empty case is exercised here ON PURPOSE - the 409 path is injected
     rather than waited for, because a disk that refuses a write is not
     something a suite can arrange portably. On the unguarded code this fails
     loudly with the IndexError; on the guarded code it is a plain SystemExit
     whose message names the request, the cause and that nothing was written.

Nothing here touches the owner's PC, the network or a real settings file: the
generator points its own config at a throwaway folder before it imports the
backend, and every call below is a read or an injected answer.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools"))

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_both_copies_are_current():
    """The same comparison CI makes, so a stale fixture fails here too."""
    import gen_sky_cases as G
    text = G.render()
    for path in (G.DESKTOP, G.PHONE):
        have = path.read_text(encoding="utf-8") if path.exists() else ""
        check(f"{path.relative_to(G.ROOT).as_posix()} matches "
              f"(python3 tools/gen_sky_cases.py)", have == text,
              "re-run `python tools/gen_sky_cases.py` and commit both copies")


def _cases_with_no_queue():
    """What `cases()` does when the weather request never reaches `spawn`.

    Returns the exception it raised, or None if it returned normally. The 409
    is injected at `request_weather` - the one seam that decides whether
    `spawn` is called at all - and put back afterwards, so the other checks in
    this file still run the real module.
    """
    import gen_sky_cases as G
    real = G.SK.request_weather
    G.SK.request_weather = lambda *a, **k: (
        409, {"ok": False, "error": "Open-Meteo needs your town first"})
    try:
        G.cases()
        return None
    except BaseException as exc:            # SystemExit is not an Exception
        return exc
    finally:
        G.SK.request_weather = real


def t_the_empty_queue_is_a_sentence_not_an_index_error():
    exc = _cases_with_no_queue()
    check("a weather request that never reaches `spawn` does not come out as an "
          "IndexError", not isinstance(exc, IndexError),
          f"cases() raised {type(exc).__name__}: {exc}")
    check("... it exits with a SystemExit, so the reader gets a message and a "
          "non-zero code rather than a traceback",
          isinstance(exc, SystemExit), f"cases() raised {type(exc).__name__}: {exc}")
    said = str(exc) if exc is not None else ""
    check("... and the message names the request that did not queue",
          "spawn" in said, said)
    check("... and the cause a reader can act on (no town stored / an unwritable "
          "config folder)", "town" in said and "written" in said, said)


if __name__ == "__main__":
    for fn in (t_both_copies_are_current,
               t_the_empty_queue_is_a_sentence_not_an_index_error):
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
