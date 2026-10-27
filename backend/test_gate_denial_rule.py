"""A "no" on a card that always asks proposes no memory (audit AP-11).

    python3 test_gate_denial_rule.py

gate-outcome.patch turns a denial into a PROPOSED memory. For an action that
always asks - the module refuses to act on any tier but "ask", or the owner
started it with a button - that sentence says nothing, and every "no" put
one in the Memory tab's review queue ("...to second card enable without
asking me first").

It also holds the proposal's own words to the owner's decision of 2026-10-10:
a Reject click carries none of the owner's words (`jarvis_gate.decide` NULLs
`prompt` and `detail`; the HUD's Reject sends only `{id, by}`), so the
proposal may only ever be Jarvis's guess, plainly marked as one, with no
reason invented - never the first-person sentence it used to write into the
learner's mouth ("I do not want Jarvis to ... I just said no when it asked").
The other good properties are held here too: never from a timeout, only ever
through `propose()`, `_NO_RULE_FROM_DENIAL` still skips a one-card denial, and
a failed proposal never turns a completed denial into an error.

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
SKIPPED = []
PATCH = "gate-outcome.patch"
#: The actions the audit named, each checked below against its module.
LISTED = ("second_card_enable", "second_card_browser_enable", "second_card_combined_enable",
          "second_card_third_assign",
          "big_model_enable",
          "learning_enable", "history_enable", "learning_auto_enable",
          "learning_sensitive_enable", "wiki_update", "change_own_config",
          "custom_voice", "better_voice_enable",
          "power_manage", "append_obsidian_daily", "download_model", "switch_model",
          # email-send.patch: each email is its own card, sent only on "ask".
          "send_email",
          # draft-email.patch: each draft is its own card, saved only on "ask".
          "draft_email",
          # update-in-chat.patch: the desktop update is ONE card, and
          # jarvis_quick.py acts on tier "ask" only, so a "no" is not a wish.
          "desktop_update")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


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
        return skip("git is not installed")
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


# ---------------------------------------------------------------------------
# The proposal's own words (owner, 2026-10-10)
#
# Before this change the text was "Remember this: I do not want Jarvis to
# <action> without asking me first. I just said no when it asked." - a
# first-person sentence presented to the learner as the owner's own turn, on
# the strength of a button press, with "I just said no when it asked" standing
# in for a reason the click does not carry (jarvis_gate.decide NULLs prompt and
# detail; the HUD's Reject sends only {id, by}). The owner's rule is that facts
# are learned from his own words only, so the proposal may only ever be
# Jarvis's guess, marked as one, with no reason invented. What must survive:
# never from a timeout, only ever a proposal, _NO_RULE_FROM_DENIAL, best-effort.
# ---------------------------------------------------------------------------

#: A first-person claim in the owner's voice. `\bI\b` covers "I do not want";
#: the possessives cover his own words being put in his mouth.
_OWNER_VOICE = re.compile(r"\bI\b|\bI'm\b|\bI'd\b|\bI've\b|\bmy\b|\bme\b|\bmine\b|\bwe\b",
                          re.IGNORECASE)
#: A reason the click does not carry, invented by the sentence. The old wording
#: said "I just said no when it asked"; "you said" is here because a rejection
#: carries no words of the owner's at all, so no phrase may claim it does.
_INVENTED_REASON = re.compile(r"\bI just\b|\byou said\b|\bbecause\b|\bsince\b",
                              re.IGNORECASE)
#: What the old sentence claimed, word for word. A test that only listed
#: forbidden phrases could be satisfied by any wording at all; this pins the
#: one claim that must never come back.
_OLD_CLAIM = ("Remember this: I do not want Jarvis to delete file without "
              "asking me first. I just said no when it asked.")


def _one_proposal(ns, action):
    calls = _proposals(ns, action)
    assert len(calls) == 1, f"expected exactly one proposal for {action}, got {calls!r}"
    return calls[0]


def t_the_proposal_is_a_guess_in_jarvis_s_words_never_the_owners():
    """(a) no owner-voiced first-person claim, and no invented reason.

    Measured on `detail={}` on purpose: a rejection carries no reason
    (jarvis_gate.decide erases prompt and detail), so a sentence that still
    explains itself is inventing one.
    """
    ns = _lifted(_gate())
    turns, kw = _one_proposal(ns, "delete_file")
    text = turns[0]["content"]
    check("it is still a turn handed to the learner (the same shape propose reads)",
          isinstance(turns, list) and len(turns) == 1 and turns[0].get("role") == "user"
          and isinstance(text, str) and text.strip(), repr(turns))
    check("no first-person claim in the owner's voice (\"I do not want ...\")",
          _OWNER_VOICE.search(text) is None, text)
    check("and no invented reason (\"I just said no when it asked\")",
          _INVENTED_REASON.search(text) is None, text)
    check("and not the old sentence, word for word", text != _OLD_CLAIM, text)


def t_the_proposal_is_marked_as_a_guess_for_the_owner():
    """(b) marked as a guess in the proposal itself."""
    ns = _lifted(_gate())
    turns, kw = _one_proposal(ns, "delete_file")
    text = turns[0]["content"]
    check("the text says in its own words that it is a guess",
          re.search(r"\bguess", text, re.IGNORECASE) is not None
          and re.search(r"\bmarked\b", text, re.IGNORECASE) is not None, text)
    check("and it says keeping or discarding it is the owner's call",
          re.search(r"\bkeeps?\b.{0,40}\bdiscards?\b", text, re.IGNORECASE | re.S) is not None,
          text)
    check("it names the action it is about, so the guess is readable",
          "delete file" in text, text)
    check("the source tag the review queue already shows is unchanged",
          kw.get("source") == "gate_denial", repr(kw))


def t_a_timeout_still_proposes_nothing():
    """(c) a timeout is the absence of an answer, so it proposes nothing.

    The DENIED branches are the only callers; the expired branch at the end of
    `check()` returns `timed_out` without calling this function. Read out of the
    patch stack's own text rather than restated, so a new call site is caught.
    """
    text = _gate()
    lines = text.splitlines()
    denied = [i for i, l in enumerate(lines)
              if l.strip() == "_propose_constraint_from_denial(action, detail)"]
    check("the only call sites are the two DENIED branches", len(denied) == 2,
          f"found {len(denied)}")
    expiry = next((i for i, l in enumerate(lines) if 'outcome="timed_out"' in l), None)
    check("outcome=\"timed_out\" is in the stand-in (test setup)", expiry is not None)
    if expiry is None:
        return
    for i in denied:
        guard = any('row["state"] == "denied"' in l for l in lines[max(0, i - 4):i])
        check(f"the call at line {i + 1} is guarded by state == \"denied\"", guard,
              "\n".join(lines[max(0, i - 4):i + 1]))
        check(f"and it is not the expired path (line {i + 1} is above {expiry + 1})",
              i < expiry)
    ns = _lifted(text)
    check("CONTROL: an ordinary denial still proposes one",
          len(_proposals(ns, "delete_file")) == 1)


def t_it_only_ever_proposes_nothing_is_applied():
    """(d) it must keep going through propose(), the one review queue.

    A denial writing straight into memory would be a second door into the same
    room (memory-safety.patch removed the single auto-accept path inside
    propose() for exactly this reason). The stub below offers ONLY propose():
    anything else the function reached for is recorded, and the function's own
    best-effort try/except would have hidden an AttributeError - so the check is
    what the stub was ASKED for, not that no exception escaped.
    """
    ns = _lifted(_gate())
    seen = []
    stub = types.ModuleType("jarvis_extract")

    def propose(turns, **kw):
        seen.append(("propose", kw))
        return []

    def _forbidden(name):
        def _no(*a, **k):
            seen.append((name, {}))
            raise AssertionError(f"{name}() must never be called from a denial")
        return _no

    stub.propose = propose
    for name in ("add_fact", "accept_auto", "_accept", "decide", "store", "remember"):
        setattr(stub, name, _forbidden(name))
    real = sys.modules.get("jarvis_extract")
    sys.modules["jarvis_extract"] = stub
    try:
        ns["_propose_constraint_from_denial"]("delete_file", {})
    finally:
        if real is None:
            sys.modules.pop("jarvis_extract", None)
        else:
            sys.modules["jarvis_extract"] = real
    check("it called propose() once, and nothing else on the memory layer",
          seen == [("propose", {"source": "gate_denial"})], repr(seen))


def t_a_no_on_an_always_ask_card_proposes_nothing():
    ns = _lifted(_gate())
    for action in LISTED:
        check(f"denying {action} proposes no memory", _proposals(ns, action) == [])
    # CONTROL: an ordinary action still gets its proposal, so the stub is live.
    # (send_email was the first control here until email-send.patch made
    # it always-ask: one "no" to one email is not a standing wish.)
    for action in ("spend_money", "delete_file", "edit_joplin_note"):
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
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
