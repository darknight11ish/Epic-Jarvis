"""A "no" on a card that always asks proposes no memory (audit AP-11).

    python3 test_gate_denial_rule.py

gate-outcome.patch turns a denial into a PROPOSED memory: "Remember this: I
do not want Jarvis to <action> without asking me first." For an action that
always asks - the module refuses to act on any tier but "ask", or the owner
started it with a button - that sentence says nothing, and every "no" put
one in the Memory tab's review queue ("...to second card enable without
asking me first").

Runs anywhere: jarvis_gate.py is the owner's file, so the gate's lines come
from a stand-in built from the whole patch stack (backend/_stack.py), with
gate-outcome.patch rehearsed on it forwards and backwards.
test_gate_outcome.py covers the rest on the owner's PC.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

FAILED, PASSED = [], []
PATCH = "gate-outcome.patch"
#: The actions the audit named, each checked below against its module.
LISTED = ("second_card_enable", "second_card_browser_enable", "big_model_enable",
          "learning_enable", "history_enable", "learning_auto_enable",
          "learning_sensitive_enable", "wiki_update", "change_own_config",
          "custom_voice", "better_voice_enable",
          "power_manage", "append_obsidian_daily", "download_model", "switch_model")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _gate():
    text, log = _stack.stand_in("jarvis_gate.py")
    if text is None:
        raise AssertionError("\n".join(log))
    return text


def _lifted(text):
    lines = text.splitlines()
    a = [i for i, l in enumerate(lines) if l.startswith("_NO_RULE_FROM_DENIAL = frozenset(")]
    if len(a) > 1:
        raise AssertionError(f"expected one _NO_RULE_FROM_DENIAL, found {len(a)}")
    src = _stack.function_text(text, "_propose_constraint_from_denial")
    if a:
        b = next(i for i in range(a[0], len(lines)) if lines[i] == "})")
        src = "\n".join(lines[a[0]:b + 1]) + "\n\n" + src
    ns = {"_NO_RULE_FROM_DENIAL": frozenset()}   # a gate from before the list
    exec(compile(src, "<gate-outcome, lifted>", "exec"), ns)
    return ns


def _proposals(ns, action):
    calls = []
    stub = types.ModuleType("jarvis_extract")
    stub.propose = lambda turns, **kw: calls.append((turns, kw))
    real = sys.modules.get("jarvis_extract")
    sys.modules["jarvis_extract"] = stub
    try:
        ns["_propose_constraint_from_denial"](action, {})
    finally:
        if real is None:
            sys.modules.pop("jarvis_extract", None)
        else:
            sys.modules["jarvis_extract"] = real
    return calls


def t_the_patch_applies_forwards_and_backwards_on_the_stack():
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    order = _stack.order()
    upto = order[:order.index(PATCH) + 1]
    after, log = _stack.stand_in("jarvis_gate.py", upto)
    check(f"the stack up to {PATCH} builds", after is not None, "\n".join(log[-2:]))
    if after is None:
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-gate-denial-"))
    try:
        (d / "jarvis_gate.py").write_text(after, encoding="utf-8", newline="\n")
        (d / "p.patch").write_bytes((HERE / PATCH).read_bytes().replace(b"\r\n", b"\n"))
        steps = (["--check", "--reverse"], ["--reverse"], ["--check"], [])
        for extra in steps:
            r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            check(f"git apply {' '.join(extra) or '(forwards)'} {PATCH}", r.returncode == 0,
                  r.stderr.strip())
        check("and forwards again gives the same text",
              (d / "jarvis_gate.py").read_text(encoding="utf-8") == after)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    full, log = _stack.stand_in("jarvis_gate.py")
    check("every later patch for jarvis_gate.py still applies over it", full is not None,
          "\n".join(log[-2:]))


def t_a_no_on_an_always_ask_card_proposes_nothing():
    ns = _lifted(_gate())
    for action in LISTED:
        check(f"denying {action} proposes no memory", _proposals(ns, action) == [])
    # CONTROL: an ordinary action still gets its proposal, so the stub is live.
    for action in ("send_email", "delete_file", "edit_joplin_note"):
        calls = _proposals(ns, action)
        check(f"CONTROL: denying {action} still proposes one", len(calls) == 1
              and calls[0][1].get("source") == "gate_denial", repr(calls))


def t_every_module_that_forces_ask_is_on_the_list():
    """Read from the modules, not typed here: a module that refuses to act on
    any tier but "ask" makes its action always-ask, whatever the toml says."""
    ns = _lifted(_gate())
    listed = ns["_NO_RULE_FROM_DENIAL"]
    found = {}
    for f in sorted(HERE.glob("jarvis_*.py")):
        src = f.read_text(encoding="utf-8")
        # A module either reads the tier of its constant directly, or (since
        # the second card gave Browser control its own action) through
        # `action_for()`, which returns one of its *ACTION constants.
        via_action_for = re.search(r"tier_of\(action\)[\s\S]{0,200}?if tier != \"ask\"", src)
        routed = set(re.findall(r"def action_for\([\s\S]{0,300}?(?=\ndef )", src))
        for const, action in re.findall(r'^(\w*ACTION) = "(\w+)"', src, re.M):
            direct = re.search(rf"tier_of\({const}\)[\s\S]{{0,200}}?if tier != \"ask\"", src)
            if direct or (via_action_for and any(re.search(rf"\b{const}\b", r) for r in routed)):
                found.setdefault(action, []).append(f.name)
    check("the modules that force 'ask' were found (test setup)",
          {"second_card_enable", "second_card_browser_enable", "big_model_enable",
           "change_own_config"} <= set(found),
          repr(found))
    for action, files in sorted(found.items()):
        check(f"{action} ({', '.join(files)} acts only on 'ask') is on the list",
              action in listed)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    for action in LISTED:
        check(f"{action} is a real action in jarvis-framework.toml or a module",
              re.search(rf"^{action}\s*=", toml, re.M) is not None or action in found
              or action == "wiki_update" and '"wiki_update"' in
              (HERE / "jarvis_wiki.py").read_text(encoding="utf-8"))


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
