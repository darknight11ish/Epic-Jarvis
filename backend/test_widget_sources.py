"""test_widget_sources.py - the three widget sources A11-A13 are about.

    python3 backend/test_widget_sources.py

WHY THIS FILE EXISTS, AND WHY IT IS NOT IN test_widgets.py

`docs/CLAIMS.tsv` carried three open rows saying three widget sources were
offered and not built:

    A11  "approvals waiting"       -> jarvis_widgets' `approvals_count`
    A12  "graphics memory per card"-> `gpu_memory`
    A13  "tokens per second"       -> `tokens_per_second`

Measured 2026-10-16, the truth was three different things:

  * A11 - the data EXISTS: `jarvis_gate.pending()` is the real list of waiting
    approval cards, the PC's menu already offers the source, and the PHONE
    already knows it. Only the desktop's own list was missing it, so the desktop
    drew the block as if it held the owner's own words.
  * A13 - the source was offered and its reader was a PLACEHOLDER: `_tokens()`
    returned the literal string "not measured" while `jarvis_speed` has been
    writing one `tokens_per_s` row per answer all along.
  * A12 - the data does NOT exist: `_gpu()` calls
    `jarvis_hardware.gpu_memory_used()`, which is defined in no file of this
    repository, in no patch, and on no copy of the owner's PC - so the block
    printed "0 GB used of 0 GB", a bare zero that was really "I could not read
    it". Its row is still open on purpose (that is a real card, and per-card
    memory is the second card's, which CLAUDE.md says is not measured).

`test_widgets.py` is the module's own suite and is not this file's to change, so
the checks above live here - including the one that would have caught all three:
EVERY source on the PC's menu must be in both clients' lists.

    python3 backend/test_widget_sources.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_speed  # noqa: E402
import jarvis_widgets as W  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why: str) -> None:
    """Said out loud, never counted as a pass (the project's rule)."""
    print(f"skip  {why}")


def _with_config_dir(where: Path):
    """Point every module that asks at a scratch config folder, and hand back
    the old value. `jarvis_speed._config_dir()` reads this variable, so the
    speed log the suite writes is the one `_tokens()` reads - the REAL read
    path, not a stubbed one - and the owner's own ~/.openjarvis is untouched."""
    had = os.environ.get("OPENJARVIS_CONFIG_DIR")
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(where)
    return had


def _restore_config_dir(had):
    if had is None:
        os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
    else:
        os.environ["OPENJARVIS_CONFIG_DIR"] = had


def _speed_log(rows) -> Path:
    """A speed log in a scratch folder, written by jarvis_speed's own writer."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-widget-speed-"))
    log = jarvis_speed.SpeedLog(path=d / jarvis_speed.FILE_NAME)
    for row in rows:
        log.append(row)
    return d


def _row(tokens, model="a-test-model"):
    return {"kind": "answer", "model": model, "tokens_per_s": tokens,
            "words_per_s": 20.0, "first_word_ms": 100, "total_ms": 900,
            "at": 1790589600}


# --------------------------------------------------------------------------
#   A13 - tokens per second is a real measurement, or it says so
# --------------------------------------------------------------------------

def t_tokens_reads_the_real_speed_log():
    """The widget's number is the middle of the last 20 answers' tokens a
    second, read through `jarvis_speed.view()` - the same read the speed screen
    does. Written by jarvis_speed's own writer into a scratch folder, so this is
    the real path and not a stub."""
    d = _speed_log([_row(11.1), _row(22.2), _row(33.3)])
    had = _with_config_dir(d)
    try:
        got = W._tokens()
    finally:
        _restore_config_dir(had)
        shutil.rmtree(d, ignore_errors=True)
    check("the middle of three answers is the middle value", got == "22.2", got)

    d = _speed_log([_row(10.0), _row(20.0), _row(30.0), _row(44.4)])
    had = _with_config_dir(d)
    try:
        got = W._tokens()
    finally:
        _restore_config_dir(had)
        shutil.rmtree(d, ignore_errors=True)
    check("... and of four it is the upper middle, not an average",
          got == "30.0", got)


def t_tokens_says_nothing_rather_than_zero():
    """No measurement must be "", never a 0 and never the old placeholder.

    The wording rule: a number that was never measured is not a number, and the
    block says so in words instead."""
    d = Path(tempfile.mkdtemp(prefix="jarvis-widget-speed-empty-"))
    had = _with_config_dir(d)
    try:
        empty = W._tokens()
    finally:
        _restore_config_dir(had)
        shutil.rmtree(d, ignore_errors=True)
    check("an empty log answers ''", empty == "", empty)
    check("... not the placeholder it used to answer", empty != "not measured", empty)

    d = _speed_log([{"kind": "answer", "model": "m", "words_per_s": 20.0}])
    had = _with_config_dir(d)
    try:
        no_tokens = W._tokens()
    finally:
        _restore_config_dir(had)
        shutil.rmtree(d, ignore_errors=True)
    check("a row with no tokens_per_s answers ''", no_tokens == "", no_tokens)

    block = W.fill({"type": "number", "source": "tokens_per_second"},
                   W.Readers(tokens=lambda: ""))
    check("the block says why in a note, in words", block.get("note") == W.NO_SPEED_YET,
          block)
    check("... and its value is EMPTY, not 0", block.get("value") == "", block.get("value"))
    check("... so nothing shows a bare zero", block.get("value") != "0", block.get("value"))

    with_number = W.fill({"type": "number", "source": "tokens_per_second"},
                         W.Readers(tokens=lambda: "41.2"))
    check("a measured speed is what the block shows", with_number.get("value") == "41.2",
          with_number)


def t_tokens_never_raises_and_never_reaches_the_owner_itself():
    """A speed log that cannot be read is not an exception on a widget route:
    `fill()` catches, and the block says it could not read this."""
    block = W.fill({"type": "number", "source": "tokens_per_second"},
                   W.Readers(tokens=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    check("a reader that raises is caught by fill()",
          block.get("note") == "Could not read this on your PC just now.", block)
    check("... and no value is invented", block.get("value") in (None, ""), block)


# --------------------------------------------------------------------------
#   A12 - the graphics card, and the bare zero that was not a measurement
# --------------------------------------------------------------------------

def t_an_unreadable_card_is_not_an_empty_card():
    """`gpu_memory_used()` does not exist, so `_gpu()` answers (0.0, 0.0). The
    block must NOT turn that into "0 GB used of 0 GB": a card nobody could read
    is not a card with nothing on it.

    THE INVARIANT IS THE TEST, and it is a function of the WORKING TREE only.

    It used to also read the file as it was BEFORE this change out of git
    (`git log -1 origin/main -- <path>`, then `git show <sha>~1:<path>`) to prove
    the defect really shipped. That is a function of git history, not of the
    tree, and it detonates on the next commit that touches the file: the "last
    commit that touched it" becomes that commit, and its parent is the already
    fixed file, so the check fails ON `main` and reddens the required `backend`
    job on every open pull request. **A standing test must be a function of the
    working tree. Anything else is a test of the weather.** The "this defect
    really shipped" proof belongs in the pull request that fixes it, where it is
    read once and then kept by git itself."""
    block = W.fill({"type": "progress", "source": "gpu_memory"},
                   W.Readers(gpu=lambda: (0.0, 0.0)))
    check("an unreadable card shows no value", block.get("value") == "", block.get("value"))
    check("... and says it could not be read", block.get("note") == W.NO_GPU, block)
    check("... and the bar is empty", block.get("fraction") == 0.0, block.get("fraction"))

    # The same invariant on the CURRENT file: it reads `jarvis_widgets.py` as the
    # working tree has it - no git, no history - so it stays true for ever.
    now_src = (HERE / "jarvis_widgets.py").read_text(encoding="utf-8")
    check("... and the CODE does not print a bare zero any more",
          'else "0 GB used of 0 GB"' not in now_src,
          "the else-branch is still there (a comment mentioning the old words is fine)")
    check("... and the file no longer returns the placeholder 'not measured'",
          'return "not measured"' not in now_src)

    real = W.fill({"type": "progress", "source": "gpu_memory"},
                  W.Readers(gpu=lambda: (3 * 1024 ** 3, 12 * 1024 ** 3)))
    check("a card that CAN be read still shows its numbers",
          real.get("value") == "3.0 GB used of 12 GB" and abs(real.get("fraction") - 0.25) < 1e-9,
          real)
    check("... and carries no note", not real.get("note"), real)


def t_the_gpu_source_is_honest_about_what_it_cannot_do():
    """The module says in its own words that the reader it calls does not exist,
    so nobody has to rediscover it. This check is on the SOURCE, because the
    fact is about a missing function, not about a value."""
    src = (HERE / "jarvis_widgets.py").read_text(encoding="utf-8")
    check("the reader is named where it is called",
          "jarvis_hardware.gpu_memory_used()" in src)
    check("... and a comment says it is not defined anywhere", "IS NOT DEFINED ANYWHERE" in src)
    check("... and says why it cannot be added from here",
          "hardware.patch" in src, "the patch-delivered reason is gone")


# --------------------------------------------------------------------------
#   A11 - approvals waiting
# --------------------------------------------------------------------------

def t_approvals_count_is_the_real_waiting_list():
    """The count is `len(jarvis_gate.pending())` - the approval cards really
    waiting - and a reader that answers something else is not counted twice."""
    block = W.fill({"type": "number", "source": "approvals_count"},
                   W.Readers(pending=lambda: [{"id": "a1"}, {"id": "a2"}]))
    check("two waiting cards show as 2", block.get("value") == "2", block)
    check("... and it is not private", block.get("private") is False, block)

    none = W.fill({"type": "number", "source": "approvals_count"},
                  W.Readers(pending=lambda: []))
    check("none waiting shows as 0, which IS a count and not a read failure",
          none.get("value") == "0", none)

    odd = W.fill({"type": "number", "source": "approvals_count"},
                 W.Readers(pending=lambda: "not a list"))
    check("a reader that answers a non-list counts as none, never as 1",
          odd.get("value") == "0", odd)

    src = (HERE / "jarvis_widgets.py").read_text(encoding="utf-8")
    check("the real reader is the gate's own waiting list",
          "import jarvis_gate" in src and "jarvis_gate.pending()" in src)


def t_the_three_sources_are_on_the_pcs_menu():
    for key in ("approvals_count", "gpu_memory", "tokens_per_second"):
        src = W.SOURCES.get(key)
        check(f"{key} is on the PC's menu", src is not None, sorted(W.SOURCES))
        if src:
            check(f"... and says it is not private", src.private is False, src.private)
    menu = W.menu()
    ids = {s["id"] for s in menu["sources"]}
    check("... and the menu a builder reads carries all three",
          {"approvals_count", "gpu_memory", "tokens_per_second"} <= ids, sorted(ids))


# --------------------------------------------------------------------------
#   The drift guard: every menu source must be in BOTH clients' lists
# --------------------------------------------------------------------------

def _js_known_sources(text: str):
    """The EFFECTIVE list `widget-board.js` uses: the array it spreads in
    (`PRIVATE_SOURCES`) plus the explicit names. Reading only the explicit half
    was measured to under-report six sources and fail the check below for the
    wrong reason."""
    m = re.search(r"const KNOWN_SOURCES = \[(.*?)\];", text, re.S)
    if not m:
        return None
    private = re.search(r'PRIVATE_SOURCES = \[(.*?)\];', text, re.S)
    names = set(re.findall(r'"([a-z_0-9]+)"', m.group(1)))
    if private:
        names |= set(re.findall(r'"([a-z_0-9]+)"', private.group(1)))
    return names


def _kt_known_sources(text: str):
    """The same for `JarvisWidgets.kt`: `PRIVATE_SOURCES + listOf(...)`."""
    m = re.search(r"KNOWN_SOURCES\s*=\s*PRIVATE_SOURCES\s*\+\s*listOf\((.*?)\)", text, re.S)
    if not m:
        return None
    private = re.search(r'PRIVATE_SOURCES\s*=\s*listOf\((.*?)\)', text, re.S)
    names = set(re.findall(r'"([a-z_0-9]+)"', m.group(1)))
    if private:
        names |= set(re.findall(r'"([a-z_0-9]+)"', private.group(1)))
    return names


def _unlisted(menu_keys, listed):
    """The sources a client would draw as private although the PC fills them."""
    return sorted(set(menu_keys) - set(listed or ()))


def t_every_source_on_the_menu_is_known_to_both_apps():
    """THE CHECK THAT WOULD HAVE CAUGHT A11-A13.

    A source a client does not list is drawn as PRIVATE (`widget-board.js:91`,
    `JarvisWidgets.kt:171`), so a client list that lags the PC's menu hides a
    value the PC says is not private. This compares all three lists directly."""
    board = ROOT / "jarvis-desktop" / "src" / "widget-board.js"
    phone = (ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" /
             "jarvis" / "client" / "net" / "JarvisWidgets.kt")
    if not board.is_file() or not phone.is_file():
        skip("this is not a checkout of the repository, so the two clients are not here")
        return
    js = _js_known_sources(board.read_text(encoding="utf-8"))
    kt = _kt_known_sources(phone.read_text(encoding="utf-8"))
    check("the desktop's list was found", js is not None)
    check("the phone's list was found", kt is not None)
    if js is None or kt is None:
        return
    menu = set(W.SOURCES)
    check("the desktop knows every source the PC's menu can fill",
          not _unlisted(menu, js), _unlisted(menu, js))
    check("the phone knows every source the PC's menu can fill",
          not _unlisted(menu, kt), _unlisted(menu, kt))
    check("... and neither app lists a source the PC cannot fill",
          not (js - menu) and not (kt - menu), sorted((js | kt) - menu))
    check("... and the two apps agree with each other", js == kt, sorted(js ^ kt))


def t_that_drift_guard_bites():
    """BITE: put the three back out of the desktop's list and the guard reports
    exactly them - which is the state main was in when A11-A13 were filed."""
    menu = set(W.SOURCES)
    old_js = {"current_task", "now_playing", "reminders", "timers", "today", "todo",
              "disk_free", "email_count", "events_count", "focus", "reminders_count",
              "todo_count"}
    check("BITE: the guard names the three the desktop was missing",
          _unlisted(menu, old_js) == ["approvals_count", "gpu_memory", "tokens_per_second"],
          _unlisted(menu, old_js))
    check("... and nothing is reported once they are in", _unlisted(menu, menu) == [])


# --------------------------------------------------------------------------
#   The shared cases both apps are held to
# --------------------------------------------------------------------------

def t_the_shared_cases_cover_the_three_sources():
    """`tools/gen_widget_cases.py` writes the answers both apps must draw the
    same way. A source with NO case in there is a source nothing compares - which
    is how the desktop's list drifted from the PC's menu three times unnoticed."""
    fixture = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "widget-cases.json"
    phone_fixture = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract" / "widget-cases.json"
    if not fixture.is_file():
        skip("the widget cases fixture is not here")
        return
    data = json.loads(fixture.read_text(encoding="utf-8"))
    used = set()
    for name, case in (data.get("cases") or {}).items():
        if name == "hostile":
            continue          # it carries "brand_new_source" ON PURPOSE
        for block in (case.get("answer") or {}).get("blocks") or []:
            if isinstance(block, dict) and isinstance(block.get("source"), str):
                used.add(block["source"])
    for key in ("approvals_count", "gpu_memory", "tokens_per_second"):
        check(f"a shared case uses {key}", key in used, sorted(used))
    check("... and every source a real case uses is on the menu",
          used <= set(W.SOURCES), sorted(used - set(W.SOURCES)))
    if phone_fixture.is_file():
        check("the phone's copy of the cases is byte-identical",
              phone_fixture.read_bytes() == fixture.read_bytes())
    else:
        skip("the phone's copy of the cases is not here")


# --------------------------------------------------------------------------
#   The suite's own registration (the trap the project has been bitten by)
# --------------------------------------------------------------------------

def _unregistered(names, run) -> list:
    return sorted(set(names) - set(run))


def t_every_test_here_is_registered():
    """A `def t_...` that is not in RUN never runs, and this file hand-lists
    them, so the file is checked against its own tuple."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = sorted(n.name for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name.startswith("t_"))
    running = sorted(fn.__name__ for fn in RUN)
    check("every t_ function here is in the RUN tuple", not _unregistered(defined, running),
          _unregistered(defined, running))
    check("... and every name in RUN is a function here", not _unregistered(running, defined),
          _unregistered(running, defined))
    check("BITE: a name left out of RUN would be named",
          _unregistered(["t_a", "t_never_run"], ["t_a"]) == ["t_never_run"])


if __name__ == "__main__":
    RUN = (
        t_tokens_reads_the_real_speed_log,
        t_tokens_says_nothing_rather_than_zero,
        t_tokens_never_raises_and_never_reaches_the_owner_itself,
        t_an_unreadable_card_is_not_an_empty_card,
        t_the_gpu_source_is_honest_about_what_it_cannot_do,
        t_approvals_count_is_the_real_waiting_list,
        t_the_three_sources_are_on_the_pcs_menu,
        t_every_source_on_the_menu_is_known_to_both_apps,
        t_that_drift_guard_bites,
        t_the_shared_cases_cover_the_three_sources,
        t_every_test_here_is_registered,
    )
    for fn in RUN:
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

