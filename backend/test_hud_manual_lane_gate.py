"""test_hud_manual_lane_gate.py - F-01: a hand-picked cloud lane runs the gates.

    python3 backend/test_hud_manual_lane_gate.py

THE DEFECT (F-01, 2026-10-27, re-verified against the published base). In
`do_POST` for `/api/chat`, the AUTOMATIC path called `jarvis_router.choose()`,
which runs every gate - the private-topic backstop, a real secret, conversation
taint, a picture, the owner's screen, Lockdown, lane availability, the
complexity threshold and the cloud budget. The MANUAL path (`else:`) called
`_manual_decision(chosen, local_model)`, which returned a Decision with
`gate="manual"` and ran NO gate at all. So a client that sent
`{"lane": "<cloud lane>", "auto": false}` reached a cloud model with private
memory text, a tainted conversation, a picture, or the owner's screen attached.

THE RULE THIS SUITE PINS. A manual pick of the local model is unchanged: that
lane, gate "manual", memory riding along as on any local turn. A manual pick of
any OTHER lane is a pick of a CLOUD lane, and it is used only when the very
decision the automatic path would have made for this turn landed on a cloud
lane (gate "escalate") - the pick stands in for the owner's yes for this one
question and answers gate 6, nothing else. A refused pick stays on the LOCAL
model, and the reason says why in the same `X-Jarvis-Route` field a refused
automatic decision already uses.

HOW IT IS PROVED, without a running HUD:

  1. THE PATCH: `f01-manual-lane-gate.patch` is the last code patch in
     apply-patches.ps1's order, applies to the published base
     (`jarvis-backend/jarvis_hud.py`), reverses out of it byte for byte, and
     the patched file parses.
  2. THE RULE, DRIVEN DIRECTLY: `_manual_lane` is a pure function, and this
     suite hands it REAL `jarvis_router` decisions - from the same module the
     PC runs (`backend/rebuilt/jarvis_router.py`) - for a tainted
     conversation, a picture, the owner's screen, a private question, a real
     secret, Lockdown, a spent budget, an Ollama cloud model as the everyday
     model, a lane this PC does not offer, and no router at all.
  3. THE FALLBACK: `_manual_decision` turns each of those into a Decision whose
     lane is the local model, whose gate is the router's own, and whose reason
     names the pick and the router's own sentence.
  4. THE CONTROL - what fails on today's code: the pre-image function lifted
     out of the patch's own REMOVED lines returns the CLOUD lane for the same
     tainted turn and has no gate at all. That is the defect, kept as the
     control, which is why every check above is a change rather than a
     description.
  5. THE WIRING, pinned two ways: the number of `jarvis_router.choose()` calls
     in the chat turn is ONE (found as an ast node, not by counting text), and
     the manual pick is read and applied on the pinned lines - `if ROUTING:`,
     `manual_pick = not body.get("auto", True)`,
     `owner_said_yes=bool(body.get("cloud_yes")) or manual_pick`, and
     `_manual_decision(body.get("lane") or local_model, local_model, decision,
     lanes)` under it.

No pytest, no network, no model. The only text this suite reads is the
published base and the file it itself just produced from it.
"""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402,F401  (also puts BACKEND and rebuilt/ on sys.path)

import _stack  # noqa: E402
import jarvis_router as RT  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: The everyday model on a normal PC, and two cloud lanes PROXY_FILE could list.
LOCAL = "qwen3.5:9b"
# cloud-escalate.patch keeps ONE cloud lane and drops every other name, so the
# tests use the real name: any other list is filtered to EMPTY by the router
# (gate "unavailable"), which is exactly what this file proves below.
LANES = ["jarvis-escalate"]

#: A question the router escalates on its own merits when the owner says yes:
#: long, clause-heavy and public. Used as the CLEAN control everywhere below.
COMPLEX = (" ".join(["word"] * 60)
           + ", explain the trade-offs step by step in detail")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass (the BLOCKED-is-never-a-pass rule)."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------- the patched file

PATCH = HERE / "f01-manual-lane-gate.patch"
BASE = REPO / "jarvis-backend" / "jarvis_hud.py"
PATCHED = ""          # the published base with the patch applied, read once
PRE_IMAGE_OLD = ""    # the OLD `_manual_decision`, from the patch's removed lines


def _load_functions(text, *names, routing=True):
    """Exec the named top-level functions out of `text` and hand them back.

    `_stack.function_text` is this repository's own way of lifting one
    top-level `def` and its body out of a file it does not execute (the base's
    neighbours need modules this box has not got). The namespace carries the
    two globals the functions use: `ROUTING` and `jarvis_router`.
    """
    ns = {"ROUTING": routing, "jarvis_router": RT}
    for name in names:
        src = _stack.function_text(text, name)
        if src is None:
            return None
        exec(compile(src, f"<{name}>", "exec"), ns)
    return [ns[n] for n in names]


def _pre_image_of(patch_text, needle):
    """The patch's own pre-image lines for the hunk that removes `needle`."""
    try:
        hunks = _stack.hunks(patch_text, "jarvis_hud.py")
    except Exception:
        return ""
    for _hunk, pre in hunks:
        joined = "\n".join(pre)
        if needle in joined:
            return joined
    return ""


def t_the_patch_and_the_base():
    global PATCHED, PRE_IMAGE_OLD
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("f01-manual-lane-gate.patch is in apply-patches.ps1's order",
          "f01-manual-lane-gate.patch" in names, names[-3:])
    check("... and it is the last code patch, immediately before the loader",
          "f01-manual-lane-gate.patch" in names
          and names.index("f01-manual-lane-gate.patch")
          == names.index("plugin-loader.patch") - 1, names[-4:])
    check("... stacked directly after cloud-escalate.patch, whose hunks are now "
          "part of this patch's own context",
          "cloud-escalate.patch" in names
          and names.index("f01-manual-lane-gate.patch")
          == names.index("cloud-escalate.patch") + 1, names[-4:])
    check("the published base is there to patch", BASE.is_file(), str(BASE))
    check("the patch file is there", PATCH.is_file(), str(PATCH))
    if not (BASE.is_file() and PATCH.is_file()):
        return
    git = shutil.which("git")
    if not git:
        return skip("git is not installed, so the patch cannot be applied here")
    raw = PATCH.read_bytes()
    check("the patch has no CRLF in it (git apply reads those as broken context)",
          b"\\r\\n" not in raw, f"{raw.count(b'\\r\\n')} CRLF line(s)")
    # F-01 is the SECOND of two new patches in one release: cloud-escalate.patch
    # comes first, so this patch's context is that patch's own output. The
    # apply/reverse pair below walks the stack in its real order, forwards and
    # back, and checks the base is reached exactly.
    cloud = PATCH.parent / "cloud-escalate.patch"
    check("the patch before this one (cloud-escalate.patch) is there to stack",
          cloud.is_file(), str(cloud))
    if not cloud.is_file():
        return
    base_text = BASE.read_bytes().decode("utf-8").replace("\\r\\n", "\\n")
    d = Path(tempfile.mkdtemp(prefix="jarvis-f01-"))

    def _read():
        return ((d / "jarvis_hud.py").read_bytes().decode("utf-8")
                .replace("\\r\\n", "\\n"))

    def _run(*args):
        # core.autocrlf is `true` on some Windows clones (this desk, measured
        # 2026-10-27). The patches are LF, so the conversion is turned off.
        return subprocess.run([git, "-c", "core.autocrlf=false", "apply", *args],
                              cwd=d, capture_output=True, text=True)

    try:
        (d / "jarvis_hud.py").write_text(base_text, encoding="utf-8", newline="")
        (d / "p.patch").write_bytes(raw.replace(b"\\r\\n", b"\\n"))
        (d / "c.patch").write_bytes(cloud.read_bytes().replace(b"\\r\\n", b"\\n"))
        r = _run("c.patch")
        check("git apply cloud-escalate.patch (the patch this one stacks on)",
              r.returncode == 0, r.stderr.strip())
        if r.returncode != 0:
            return
        pre_text = _read()
        for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"]):
            r = _run(*extra, "p.patch")
            check(f"git apply {' '.join(extra) or '(forwards)'} f01-manual-lane-gate.patch",
                  r.returncode == 0, r.stderr.strip())
        back = _read()
        check("reversing f01 restores cloud-escalate.patch's own result exactly",
              r.returncode == 0 and back == pre_text, r.stderr.strip())
        r = _run("--reverse", "c.patch")
        base_back = _read()
        check("reversing the stack restores the published base exactly",
              r.returncode == 0 and base_back == base_text, r.stderr.strip())
        r1, r2 = _run("c.patch"), _run("p.patch")
        check("the two-patch stack re-applies after the reverse (both directions clean)",
              r1.returncode == 0 and r2.returncode == 0, (r1.stderr + r2.stderr).strip())
        PATCHED = _read()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    try:
        ast.parse(PATCHED)
        check("the patched file parses (the patch compiles)", True)
    except SyntaxError as exc:
        check("the patched file parses (the patch compiles)", False, str(exc))
    for name in ("_manual_lane", "_manual_decision"):
        check(f"the patched file carries {name}()",
              _stack.function_text(PATCHED, name) is not None)
    PRE_IMAGE_OLD = _pre_image_of(PATCH.read_text(encoding="utf-8"),
                                  "def _manual_decision(")
    check("the patch's own removed lines hold the OLD manual decision (the control)",
          "def _manual_decision(chosen: str, local_model: str):" in PRE_IMAGE_OLD,
          PRE_IMAGE_OLD[:200])


# ------------------------------------------------------------------- the wiring

def t_the_wiring():
    if not PATCHED:
        return skip("the patched file was not produced, so the wiring cannot be read")
    # The argument block: ONE call, reached by both paths. Counted as ast nodes,
    # because the file's prose mentions jarvis_router.choose() several times.
    calls = [n for n in ast.walk(ast.parse(PATCHED))
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "choose"
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "jarvis_router"]
    check("wiring: ONE jarvis_router.choose() call in the whole file, not one per path",
          len(calls) == 1, f"{len(calls)} call(s)")
    check("wiring: the manual pick is read from `auto`, in one place",
          bool(re.search(r'^            manual_pick = not body\.get\("auto", True\)$',
                         PATCHED, re.M)))
    check("wiring: both paths reach that one call (`if ROUTING:`, not `and auto`)",
          bool(re.search(r'^        if ROUTING:$', PATCHED, re.M))
          and not bool(re.search(r'^        if ROUTING and body\.get\("auto", True\):$',
                                 PATCHED, re.M)))
    check("wiring: the universal gate block is the one the manual path now passes through",
          bool(re.search(r'^            decision = jarvis_router\.choose\($', PATCHED, re.M)))
    check("wiring: the pick stands in for the owner's yes - gate 6 and nothing else "
          "(stacked on cloud-escalate.patch's standing-yes expression)",
          bool(re.search(r'owner_said_yes=\(\n[ \t]+\(bool\(body\.get\("cloud_yes"\)\)'
                         r' and \(', PATCHED))
          and "or manual_pick)," in PATCHED)
    check("wiring: a manual pick is decided AFTER the router's own decision",
          bool(re.search(r'^            if manual_pick:$', PATCHED, re.M)
               and re.search(r'if manual_pick:\n(?:[ \t]*#.*\n)*[ \t]*decision = '
                             r'_manual_decision\(body\.get\("lane"\) or local_model,\n'
                             r'[ \t]*local_model, decision, lanes\)', PATCHED)))
    check("wiring: the no-router branch is left as it was (no second argument block)",
          bool(re.search(r'decision = _manual_decision\(chosen, local_model\)$',
                         PATCHED, re.M)))
    check("wiring: nothing calls the old two-argument form to decide a lane any more",
          len(re.findall(r'_manual_decision\(chosen, local_model\)', PATCHED)) == 1,
          re.findall(r'.*_manual_decision\(.*', PATCHED))
    rule = _stack.function_text(PATCHED, "_manual_lane")
    check("the rule lives in a PURE function a test can call (no module, no file, "
          "no request in it)",
          rule is not None and "import " not in rule
          and "open(" not in rule and "body" not in rule, (rule or "")[:200])
    built_in = [n for n in ast.walk(ast.parse(PATCHED))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_manual_lane"]
    check("the decision builder is the only caller of the rule (one call, ast-counted)",
          len(built_in) == 1, f"{len(built_in)} call(s)")


# --------------------------------------------------------------------- the rule

def _lane_and_reason(fns, decide, chosen, lanes=None):
    _ml, _md = fns
    return _ml(decide, chosen, LOCAL, LANES if lanes is None else lanes)


def t_the_rule_refuses_what_the_router_refuses():
    fns = _load_functions(PATCHED, "_manual_lane", "_manual_decision")
    if not fns:
        return skip("the patched functions could not be lifted out")
    _ml, md = fns
    pick = LANES[0]

    # A clean, complex, public question with the owner's yes: the CONTROL. If
    # this does not escalate there is nothing for the refusals below to be
    # refusals OF.
    clean = RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES, owner_said_yes=True)
    check("CONTROL: the router really does escalate this clean, complex question",
          clean.gate == "escalate" and clean.lane in LANES,
          f"gate={clean.gate} lane={clean.lane}")
    check("CONTROL: a pick the router would escalate is USED, and named as picked",
          _ml(clean, pick, LOCAL, LANES) == (pick, "you chose this lane", "manual"),
          _ml(clean, pick, LOCAL, LANES))
    d = md(pick, LOCAL, clean, LANES)
    check("CONTROL: ... and the Decision sends the turn to that lane, no memory",
          d.lane == pick and d.gate == "manual" and d.inject_memory is False,
          d.as_dict())

    gates = {
        "taint": dict(conversation_tainted=True),
        "image": dict(has_image=True),
        "screen": dict(has_screen=True),
    }
    for gate, kw in gates.items():
        dec = RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES,
                        owner_said_yes=True, **kw)
        lane, reason, got = _ml(dec, pick, LOCAL, LANES)
        check(f"{gate}: the router keeps the turn local (gate '{gate}')",
              dec.gate == gate, dec.gate)
        check(f"{gate}: so a hand-picked cloud lane is NOT used", lane == LOCAL, lane)
        check(f"{gate}: the reason names the pick and says it stays local",
              reason.startswith(f"you chose {pick},") and "stays local" in reason, reason)
        check(f"{gate}: the header carries the router's own gate, not 'manual'",
              got == gate, got)
        check(f"{gate}: ... and the Decision lands on the local model",
              md(pick, LOCAL, dec, LANES).lane == LOCAL)

    for label, query in (("private", "what is my api key"),
                         ("secret", "here is my key sk-" + "a1B2c3D4e5F6g7H8i9J0"),
                         ("complexity", "hello")):
        dec = RT.choose(query, local_model=LOCAL, lanes=LANES, owner_said_yes=True)
        lane, reason, got = _ml(dec, pick, LOCAL, LANES)
        check(f"{label}: refused (gate '{dec.gate}') and the pick stays local",
              lane == LOCAL and got == dec.gate, f"lane={lane} gate={got}")
        check(f"{label}: the reason is the router's own sentence, after the pick",
              reason.startswith(f"you chose {pick},") and dec.reason in reason, reason)

    # Lockdown: the router asks jarvis_asks_first, which this box may not have.
    # Pin the branch the real choose() reads, then give it back.
    real_lockdown = RT.lockdown_on
    try:
        RT.lockdown_on = lambda: True
        dec = RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES, owner_said_yes=True)
    finally:
        RT.lockdown_on = real_lockdown
    check("Lockdown: the router keeps the turn local whatever the question",
          dec.gate == "lockdown", dec.gate)
    check("Lockdown: a hand-picked cloud lane is NOT used",
          _ml(dec, pick, LOCAL, LANES)[0] == LOCAL)

    class _Spent:
        """The two methods choose() asks a budget for, both refusing."""

        def allows_cloud(self):
            return False

        def day_exceeded(self):
            return False

    dec = RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES, owner_said_yes=True,
                    budget=_Spent())
    lane, reason, got = _ml(dec, pick, LOCAL, LANES)
    check("budget: a spent cloud budget keeps the turn local (gate 'budget')",
          dec.gate == "budget" and lane == LOCAL and got == "budget",
          f"gate={dec.gate} lane={lane}")
    check("budget: ... and the reason says the budget is spent",
          "budget is spent" in reason, reason)

    dec = RT.choose(COMPLEX, local_model="gpt-oss:120b-cloud", lanes=LANES,
                    owner_said_yes=True)
    check("cloud model: an everyday model that is one of Ollama's own cloud models "
          "is refused before anything else (gate 'cloud_model')",
          dec.gate == "cloud_model", dec.gate)
    check("cloud model: a hand-picked lane is NOT used from that state",
          _ml(dec, pick, "gpt-oss:120b-cloud", LANES)[0] == "gpt-oss:120b-cloud")

    dec = RT.choose(COMPLEX, local_model=LOCAL, lanes=[], owner_said_yes=True)
    check("unavailable: with no lane offered the pick is not used either",
          dec.gate == "unavailable" and _ml(dec, pick, LOCAL, [])[0] == LOCAL, dec.gate)


def t_the_rule_handles_what_is_not_a_decision():
    fns = _load_functions(PATCHED, "_manual_lane", "_manual_decision")
    off = _load_functions(PATCHED, "_manual_lane", "_manual_decision", routing=False)
    if not (fns and off):
        return skip("the patched functions could not be lifted out")
    _ml, md = fns
    _ml_off, md_off = off
    pick = LANES[0]
    check("no router at all: a cloud pick stays local, and says so",
          _ml_off(None, pick, LOCAL, LANES)[0] == LOCAL
          and "routing module is not installed" in _ml_off(None, pick, LOCAL, LANES)[1],
          _ml_off(None, pick, LOCAL, LANES))
    check("no router at all: the Decision lands on local with memory",
          md_off(pick, LOCAL, None, LANES).lane == LOCAL
          and md_off(pick, LOCAL, None, LANES).inject_memory is True)
    clean = RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES, owner_said_yes=True)
    for label, lanes in (("a lane this PC does not offer", LANES),
                         ("no lanes at all", [])):
        chosen = "not-a-lane:cloud" if lanes else pick
        lane, reason, got = _ml(clean, chosen, LOCAL, lanes)
        check(f"{label}: refused as unavailable, never sent to a proxy",
              lane == LOCAL and got == "unavailable", f"lane={lane} gate={got}")
        check(f"{label}: the reason names the lane and says this PC has no such lane",
              reason.startswith(f"you chose {chosen},") and "no cloud lane by that name" in reason,
              reason)
    # The client's own string is not trusted for anything but a label.
    weird = "bad\nname\x00with stuff"
    lane, reason, _got = _ml(clean, weird, LOCAL, LANES)
    check("a hostile lane name is refused and flattened to one line",
          lane == LOCAL and "\n" not in reason and "\x00" not in reason, repr(reason))
    dict_pick = _ml(clean, {"a": "b"}, LOCAL, LANES)
    check("a non-string lane is refused rather than trusted",
          dict_pick[0] == LOCAL, dict_pick)


def t_the_local_pick_is_unchanged():
    fns = _load_functions(PATCHED, "_manual_lane", "_manual_decision")
    off = _load_functions(PATCHED, "_manual_lane", "_manual_decision", routing=False)
    if not (fns and off):
        return skip("the patched functions could not be lifted out")
    _ml, md = fns
    _ml_off, md_off = off
    d = md_off(LOCAL, LOCAL)                 # no router: exactly today's shape
    check("local pick, no router: the SAME lane, reason and gate as before",
          d.lane == LOCAL and d.reason == "you chose this lane" and d.gate == "manual",
          d.as_dict())
    check("local pick, no router: memory rides along, and complexity is 0.0",
          d.inject_memory is True and d.as_dict()["complexity"] == 0.0, d.as_dict())
    check("local pick, no router: as_dict() keeps the same five keys",
          sorted(d.as_dict()) == ["complexity", "gate", "inject_memory", "lane", "reason"],
          sorted(d.as_dict()))
    # ... and with a real decision in hand - including one that refuses the
    # turn to a cloud lane - the local pick is still simply honoured.
    for label, dec in (
        ("clean", RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES, owner_said_yes=True)),
        ("tainted", RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES,
                              owner_said_yes=True, conversation_tainted=True)),
    ):
        d = md(LOCAL, LOCAL, dec, LANES)
        check(f"local pick ({label} turn): same lane, same reason, same gate",
              d.lane == LOCAL and d.reason == "you chose this lane"
              and d.gate == "manual", d.as_dict())
        check(f"local pick ({label} turn): memory still rides along",
              d.inject_memory is True, d.as_dict())
    check("local pick: the rule does not even look at the router's answer",
          _ml_off(None, LOCAL, LOCAL, []) == (LOCAL, "you chose this lane", "manual"))


# ------------------------------------------------------------------- the control

def t_the_control_would_fail_on_todays_code():
    """The old function, lifted out of the patch's own removed lines.

    Every check above is a CHANGE only if this control is what the code did
    before it. On today's code there is no `_manual_lane` at all, so the checks
    that call it fail; this one shows WHY they matter.
    """
    if not PRE_IMAGE_OLD:
        return skip("the patch's pre-image could not be read, so the control cannot run")
    lines = PRE_IMAGE_OLD.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.startswith("def _manual_decision(")), None)
    old_src = "\n".join(lines[start:]) + "\n" if start is not None else ""
    ns = {"ROUTING": True, "jarvis_router": RT}
    try:
        exec(compile(old_src, "<old _manual_decision>", "exec"), ns)
    except SyntaxError as exc:
        return check("the OLD function lifts out of the patch's removed lines", False, str(exc))
    old = ns["_manual_decision"]
    dec = RT.choose(COMPLEX, local_model=LOCAL, lanes=LANES,
                    owner_said_yes=True, conversation_tainted=True)
    check("CONTROL: the router keeps this tainted turn local (gate 'taint')",
          dec.gate == "taint", dec.gate)
    old_decision = old(LANES[0], LOCAL)
    check("CONTROL (today's code): the manual path sends the tainted turn to the "
          "CLOUD lane anyway", old_decision.lane == LANES[0], old_decision.as_dict())
    check("CONTROL (today's code): ... with no gate at all but 'manual'",
          old_decision.gate == "manual", old_decision.gate)
    check("CONTROL (today's code): ... and it never even asks the router",
          "choose(" not in old_src and "decide" not in old_src, old_src[:300])
    check("CONTROL: the patched code refuses that same pick",
          _load_functions(PATCHED, "_manual_lane", "_manual_decision")[1](
              LANES[0], LOCAL, dec, LANES).lane == LOCAL)


def main():
    tests = [t_the_patch_and_the_base,
             t_the_wiring,
             t_the_rule_refuses_what_the_router_refuses,
             t_the_rule_handles_what_is_not_a_decision,
             t_the_local_pick_is_unchanged,
             t_the_control_would_fail_on_todays_code]
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception:
            FAILED.append(t.__name__)
            print(f"FAIL  {t.__name__} raised:\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
