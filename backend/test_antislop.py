"""The Anti-Slop filter (jarvis_antislop.py): the engine, its wiring, and the
six mutation bite-proofs the blueprint names.

    py -3 test_antislop.py

WHAT THIS PROVES

  1. THE SWITCH IS REALLY A SWITCH. Off: `prompt_block()` is "" (0 tokens) and
     `post_process_reply()` returns its input unchanged (0 work). On: a block of
     at most MAX_PROMPT_CHARS, and the scrub runs. Every setter writes the file,
     emits the event and leaves ONE Undo receipt.
  2. `R-37`: "Write Like Me" wins. When the owner's own samples use em dashes
     and he has asked Jarvis to write like him, the R-02 line goes out of the
     prompt and the scrub leaves his dashes alone - even with the filter ON.
  3. `antislop-code`: a decorative banner or an emoji comment inside a fenced
     block goes; the "why" comment and every code line stay (an em dash inside
     code is code, not prose).
  4. `R-25` UNROUNDED: #777777 on white is 4.4781:1 and FAILS 4.5, even though
     it rounds to 4.5; #757575 is 4.6075:1 and passes.
  5. THE AUDIT'S TIERS: R-02/R-25/R-26/R-32 are HIGH, R-10/R-13 MEDIUM,
     R-15/R-16/antislop-code LOW, and a `during` UI audit carries the 4-block
     Delivery Gate. `after` mode rewrites nothing.
  6. THE FAST PATH: "turn on anti-slop", "turn off anti-slop", "set anti-slop
     mode to after", "turn on anti-slop for code" and "is anti-slop on" resolve
     in jarvis_quick.py, raise ZERO approval cards, change the real state and
     leave a receipt.

THE MUTATION BITES, and how they are run

Each bite is proved the way this repository proves a check has teeth: the real
module must pass, a THROWAWAY COPY with one specific line broken must FAIL the
same check. A copy is written into a temp folder, loaded under its own name,
and (for the wiring bites) put in `sys.modules["jarvis_antislop"]` for the
duration so jarvis_quick and jarvis_settings_registry call it. A bite whose
mutant still passes is reported as a FAILED bite: the check would be proving
nothing.

WHAT THIS DOES NOT PROVE

It does not run the real backend, the real Handler, or the real Ollama. The
routes are driven through a stand-in Handler with the same three callbacks, and
the agent wiring through `run_local_turn`'s own `post`/`open_stream` seams (the
same ones backend/test_agent.py uses). It writes nothing outside its temp
folder.
"""
import importlib.util
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# JARVIS_BACKEND, AND WHY THIS SUITE USUALLY IGNORES IT.
#
# `_where.BACKEND` is that variable when it is set, and on the owner's PC it
# points at the live backend folder. This suite ships the module it tests, so a
# backend that has not had apply-patches.ps1 run since the module was added
# cannot hold it - and then every check here would fail against a folder that
# simply does not have the feature yet, which reads as "the patch broke
# something". So the variable is dropped when (and only when) that folder has no
# jarvis_antislop.py, and the reason is printed. Against a PATCHED backend the
# variable is honoured exactly as every other suite honours it.
_BACKEND_ENV = (os.environ.get("JARVIS_BACKEND") or "").strip()
if _BACKEND_ENV and not (Path(_BACKEND_ENV) / "jarvis_antislop.py").is_file():
    os.environ.pop("JARVIS_BACKEND", None)
    print(f"note: JARVIS_BACKEND named {_BACKEND_ENV}, which has no "
          f"jarvis_antislop.py yet, so this run tested the checkout's own copy.")
    _BACKEND_ENV = ""

import _where  # noqa: E402,F401  (BACKEND on sys.path, rebuilt/ appended, utf-8 out)

#: A settings folder of this suite's own: never the owner's real one. Set
#: before the modules are imported, so jarvis_framework's own answer (which
#: reads these variables) points here too.
_CFG = Path(tempfile.mkdtemp(prefix="antislop-test-"))
os.environ["JARVIS_CONFIG_DIR"] = str(_CFG)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CFG)

import jarvis_antislop as A  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

A._config_dir = lambda: _CFG
A._reset_for_tests()

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def state_file() -> Path:
    return _CFG / A.STATE_NAME


def reset() -> None:
    """A clean, OFF state before each check group."""
    try:
        state_file().unlink()
    except FileNotFoundError:
        pass
    A._reset_for_tests()


# --------------------------------------------------------------------------
#   Mutation harness: a throwaway copy with ONE line broken
# --------------------------------------------------------------------------

_MUT_DIR = Path(tempfile.mkdtemp(prefix="antislop-mut-"))
_SOURCE = (HERE / "jarvis_antislop.py").read_text(encoding="utf-8")


def load_mutant(tag: str, old: str, new: str):
    """A copy of the module with `old` replaced by `new`, loaded fresh.

    Raises if `old` is not in the file: a mutation that silently matched
    nothing would leave the copy identical and the bite would pass for the
    wrong reason - which is the failure this whole harness exists to prevent.
    """
    if old not in _SOURCE:
        raise AssertionError(f"the mutation for {tag} matched nothing: {old[:60]!r}")
    if _SOURCE.count(old) != 1:
        raise AssertionError(f"the mutation for {tag} is ambiguous: {old[:60]!r}")
    path = _MUT_DIR / f"mut_{tag}.py"
    path.write_text(_SOURCE.replace(old, new, 1), encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(f"_antislop_mutant_{tag}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._config_dir = lambda: _CFG
    return module


class using:
    """Put `module` where `import jarvis_antislop` finds it, for the block.

    jarvis_quick and jarvis_settings_registry import the module INSIDE their
    functions, so this is the honest way to make the real wirings call a
    mutant: the name they look up is the mutant while the block runs.
    """

    def __init__(self, module):
        self.module = module

    def __enter__(self):
        self.was = sys.modules.get("jarvis_antislop")
        sys.modules["jarvis_antislop"] = self.module
        return self.module

    def __exit__(self, *_a):
        if self.was is not None:
            sys.modules["jarvis_antislop"] = self.was
        else:
            sys.modules.pop("jarvis_antislop", None)
        return False


def bites(tag: str, old: str, new: str, proves) -> None:
    """One bite: the real module passes `proves`, the mutant fails it."""
    reset()
    good = proves(A)
    check(f"bite {tag}: the real module holds the property", good is False or bool(good),
          repr(good))
    try:
        mutant = load_mutant(tag, old, new)
    except Exception as exc:                 # noqa: BLE001 - a broken mutant is a FAILED bite
        check(f"bite {tag}: the mutant loads", False, f"{type(exc).__name__}: {exc}")
        return
    reset()
    try:
        with using(mutant) as m:
            got = proves(m)
    except Exception as exc:                 # noqa: BLE001 - an exception IS a failed property
        got = f"raised {type(exc).__name__}: {exc}"
    check(f"bite {tag}: breaking {old.splitlines()[0].strip()[:48]!r} makes it FAIL",
          not got, f"the mutant still passed: {got!r}")


# --------------------------------------------------------------------------
#   1. The switch: 0 tokens, 0 work, one receipt
# --------------------------------------------------------------------------

def t_the_default_is_off_and_says_so():
    reset()
    state = A.get_state()
    check("a PC that has never run it: OFF", state["enabled"] is False, repr(state))
    check("...during mode", state["mode"] == "during", repr(state))
    check("...all three scopes on", state["scopes"] == {"copy": True, "code": True, "ui": True},
          repr(state))
    check("...the rulebook's own starting dials ENERGY 1 / RHYTHM 2 / MOTION 1",
          state["dials"] == {"energy": 1, "rhythm": 2, "motion": 1}, repr(state))
    check("...and the state file itself is not written by a read",
          not state_file().exists(), str(state_file()))
    check("every key the schema names is in the state, and nothing else",
          set(A.STATE_KEYS) == set(state), sorted(set(state) - set(A.STATE_KEYS)))


def t_the_switch_is_zero_tokens_and_zero_work_when_off():
    reset()
    check("OFF: the prompt block is the empty string, so 0 tokens are added",
          A.prompt_block("build me a landing page in html and css") == "",
          repr(A.prompt_block("build me a landing page")))
    sample = "Fast — and seamless! Get Started with our revolutionary tool."
    check("OFF: the post-processor returns the string UNCHANGED (0 work)",
          A.post_process_reply(sample) == sample, repr(A.post_process_reply(sample)))
    check("OFF: no reply filter is made at all, so the streaming path adds no call",
          A.reply_filter() is None)
    check("OFF: a fenced banner comment survives untouched, because nothing runs",
          "# ==========\n" in A.post_process_reply("```py\n# ==========\nx = 1\n```\n"))


def t_turning_it_on_writes_the_file_an_event_and_one_receipt():
    reset()
    receipts_before = _receipt_count()
    out = A.set_enabled(True)
    check("ON: the setter says what is now being watched", "Anti-Slop filter on" in out["message"],
          repr(out.get("message")))
    check("ON: the file is there and really holds enabled=true",
          state_file().is_file()
          and json.loads(state_file().read_text(encoding="utf-8"))["enabled"] is True,
          str(state_file()))
    check("ON: is_enabled() agrees with the file", A.is_enabled() is True)
    check("ON: one action receipt was recorded for the Undo button",
          _receipt_count() == receipts_before + 1,
          f"{receipts_before} -> {_receipt_count()}")
    block = A.prompt_block("build me a landing page in html and css")
    check("ON: the prompt block is not empty", bool(block), repr(block))
    check(f"ON: and it is at most {A.MAX_PROMPT_CHARS} characters",
          0 < len(block) <= A.MAX_PROMPT_CHARS, len(block))
    check("ON: it is wrapped in the antislop_filter element, carrying the mode",
          block.startswith('<antislop_filter mode="during">')
          and block.rstrip().endswith("</antislop_filter>"), repr(block[:60]))
    check("ON: a prose answer loses its em dash", A.post_process_reply("Fast — really") == "Fast, really",
          repr(A.post_process_reply("Fast — really")))
    A.set_enabled(False)
    check("OFF again: instant, and the block is back to 0 tokens",
          A.is_enabled() is False and A.prompt_block("html page") == "")


def t_the_prompt_block_is_scoped_and_bounded():
    reset()
    A.set_enabled(True)
    # A plain question gets no UI rules: the longest set is only paid for when
    # a screen is being built.
    plain = A.prompt_block("what is the capital of Peru")
    ui = A.prompt_block("design a landing page in html and css")
    check("the UI rules are absent from an everyday question", "antislop-ui" not in plain,
          repr(plain))
    check("...and present when a page is being built", "antislop-ui" in ui, repr(ui))
    check("the 1,050-character ceiling holds for the LONGEST block",
          len(ui) <= A.MAX_PROMPT_CHARS, len(ui))
    spoken = A.prompt_block("design a landing page", spoken_live=True)
    check("a spoken turn carries neither the code rules nor the UI rules",
          "antislop-code" not in spoken and "antislop-ui" not in spoken, repr(spoken))
    A.set_scope("ui", False)
    check("with the ui scope off, a UI question gets no ui rules",
          "antislop-ui" not in A.prompt_block("design a landing page in html"))
    A.set_scope("ui", True)
    A.set_scope("copy", False)
    A.set_scope("code", False)
    A.set_scope("ui", False)
    check("with every scope off, the block is empty again - 0 tokens",
          A.prompt_block("design a landing page") == "",
          repr(A.prompt_block("design a landing page")))
    A.set_scope("copy", True)
    A.set_scope("code", True)
    A.set_scope("ui", True)


def t_after_mode_asks_for_an_audit_and_rewrites_nothing():
    reset()
    A.set_enabled(True)
    A.set_mode("after")
    block = A.prompt_block("design a landing page in html")
    check("after mode tells the model to list findings and not edit",
          "do not edit" in block.lower() and "HIGH" in block, repr(block))
    sample = "This — is a finding I am reporting"
    check("after mode NEVER rewrites: an audit may quote the em dash it reports",
          A.post_process_reply(sample) == sample, repr(A.post_process_reply(sample)))
    check("after mode makes no reply filter", A.reply_filter() is None)
    try:
        A.set_mode("sideways")
        check("an unknown mode is refused", False)
    except ValueError as exc:
        check("an unknown mode is refused, in words naming the two real ones",
              "during" in str(exc) and "after" in str(exc), str(exc))
    A.set_mode("during")


def t_the_dials_are_bounded_and_refused_out_of_range():
    reset()
    out = A.set_dials(energy=3, motion=2)
    check("set_dials writes the ones it was given and keeps the rest",
          out["dials"] == {"energy": 3, "rhythm": 2, "motion": 2}, repr(out["dials"]))
    for bad in (0, 4, True, "2"):
        try:
            A.set_dials(energy=bad)
            check(f"a dial of {bad!r} is refused", False)
        except ValueError:
            check(f"a dial of {bad!r} is refused rather than clamped", True)
    reset()


def _receipt_count() -> int:
    """How many action receipts exist, or 0 when the receipts module is absent
    (then the bite below is honestly skipped rather than counted as a pass).

    Counted from the table itself, not from the list route: that route caps its
    answer at DEFAULT_LIMIT (20), so a list-based count saturates and a check
    built on it silently stops proving anything after the twentieth receipt.
    """
    try:
        import jarvis_receipts
        from contextlib import closing
        with closing(jarvis_receipts._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM action_receipts")
                       .fetchone()["n"])
    except Exception:
        return 0


def _receipts_available() -> bool:
    try:
        import jarvis_receipts
        from contextlib import closing
        with closing(jarvis_receipts._connect()) as conn:
            conn.execute("SELECT COUNT(*) FROM action_receipts").fetchone()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   2. R-37: "Write Like Me" wins
# --------------------------------------------------------------------------

def _voiceprint_says_yes():
    """A stand-in for jarvis_voiceprint whose samples use em dashes."""
    import jarvis_voiceprint as VP
    real = VP.handle_get

    def fake(route, query=""):
        if route != VP.LIST_PATH:
            return real(route, query)
        return 200, {"ok": True, "status": {"enabled": True, "samples": 2},
                     "samples": [{"text": "A sentence with an em dash — right there"},
                                 {"text": "no dash here"}],
                     "count": 2, "voiceprint": {}}

    return fake, real


def _voiceprint_says_off():
    import jarvis_voiceprint as VP
    real = VP.handle_get

    def fake(route, query=""):
        if route != VP.LIST_PATH:
            return real(route, query)
        return 200, {"ok": True, "status": {"enabled": False, "samples": 1},
                     "samples": [{"text": "dash — here"}], "count": 1, "voiceprint": {}}

    return fake, real


def _exemption_is_read_from_the_voiceprint(module) -> bool:
    """True when the module honours R-37 while the filter is ON."""
    import jarvis_voiceprint as VP
    module.set_enabled(True)
    fake, real = _voiceprint_says_yes()
    VP.handle_get = fake
    try:
        exempt = module.voiceprint_uses_em_dash()
        kept = module.post_process_reply("A — B") == "A — B"
        block = module.prompt_block("html page", voiceprint_uses_em_dash=True)
        no_line = "R-02" not in block
    finally:
        VP.handle_get = real
    module.set_enabled(False)
    return exempt and kept and no_line


def t_write_like_me_wins_under_r37():
    reset()
    import jarvis_voiceprint as VP
    fake, real = _voiceprint_says_yes()
    VP.handle_get = fake
    try:
        check("the voiceprint is asked, and says the owner writes with em dashes",
              A.voiceprint_uses_em_dash() is True)
    finally:
        VP.handle_get = real
    off, real_off = _voiceprint_says_off()
    VP.handle_get = off
    try:
        check("...and a voiceprint that is switched OFF excused nothing",
              A.voiceprint_uses_em_dash() is False)
    finally:
        VP.handle_get = real_off
    reset()
    A.set_enabled(True)
    sample = "The owner wrote it like this — so Jarvis may too"
    check("with the exemption passed in, the scrub leaves the dash alone",
          A.post_process_reply(sample, voiceprint_uses_em_dash=True) == sample,
          repr(A.post_process_reply(sample, voiceprint_uses_em_dash=True)))
    check("without it, the same words are scrubbed",
          A.post_process_reply(sample) == "The owner wrote it like this, so Jarvis may too",
          repr(A.post_process_reply(sample)))
    check("and the prompt drops the R-02 line when the exemption is on",
          "R-02" not in A.prompt_block("copy for a note", voiceprint_uses_em_dash=True))
    A.set_enabled(False)


# --------------------------------------------------------------------------
#   3. antislop-code: banners out, "why" comments and code in
# --------------------------------------------------------------------------

CODE_SAMPLE = (
    "Here is the retry.\n"
    "```python\n"
    "# ================\n"
    "# 🚀 Set the counter to one\n"
    "# Why: retry needed for WDDM counter\n"
    "count = 1  # a dash in code — stays\n"
    "// ----------------\n"
    "```\n"
    "And that is that.\n"
)


def _comment_cleanup_is_right(module) -> bool:
    module.set_enabled(True)
    try:
        out = module.post_process_reply(CODE_SAMPLE)
    finally:
        module.set_enabled(False)
    want = ("Here is the retry.\n"
            "```python\n"
            "# Why: retry needed for WDDM counter\n"
            "count = 1  # a dash in code \u2014 stays\n"
            "```\n"
            "And that is that.\n")
    return out == want


def t_the_code_comment_cleanup_is_exact():
    reset()
    A.set_enabled(True)
    out = A.post_process_reply(CODE_SAMPLE)
    check("the box-drawing banner line is removed", "# ================" not in out, repr(out))
    check("the emoji comment is removed", "🚀" not in out, repr(out))
    check("the 'why' comment SURVIVES", "# Why: retry needed for WDDM counter" in out, repr(out))
    check("the code line survives, em dash and all (that is code, not prose)",
          "count = 1  # a dash in code \u2014 stays" in out, repr(out))
    check("prose outside the fence IS scrubbed", " \u2014 " not in out.split("```")[0]
          and "And that is that." in out, repr(out))
    check("an indented 'why' comment is untouched",
          A.post_process_reply("```\n    # Why: the retry needs 2 seconds\n```\n")
          == "```\n    # Why: the retry needs 2 seconds\n```\n")
    check("a three-dash separator with a reason is NOT a banner",
          A.post_process_reply("```\n# --- why: WDDM wants a retry\n```\n")
          == "```\n# --- why: WDDM wants a retry\n```\n")
    A.set_enabled(False)


def t_the_stream_filter_matches_the_whole_text_scrub():
    """The piece-by-piece scrub must produce exactly what the whole-text one
    does - including an em dash split across two pieces, which is the case a
    naive per-piece replace gets wrong."""
    reset()
    A.set_enabled(True)
    pieces = ["Fast ", "\u2014", " and ", "seam", "less!", "\n```py\n",
              "# ====\n", "x = 1\n", "```\n", "after \u2014 prose"]
    flt = A.reply_filter()
    streamed = "".join(flt.feed(p) for p in pieces) + flt.flush()
    whole = A.post_process_reply("".join(pieces))
    check("streamed piece by piece == scrubbed in one piece", streamed == whole,
          f"{streamed!r} != {whole!r}")
    check("...and the em dash that straddled two pieces really went",
          "\u2014" not in streamed.split("```")[0], repr(streamed))
    A.set_enabled(False)


# --------------------------------------------------------------------------
#   4. R-25: the contrast number is compared UNROUNDED
# --------------------------------------------------------------------------

def t_contrast_is_unrounded():
    fails = A.check_contrast("#777777", "#ffffff")
    passes = A.check_contrast("#757575", "#ffffff")
    check("#777777 on white really is 4.4781:1", abs(fails["ratio"] - 4.4781) < 0.001,
          fails["ratio"])
    check("#777777 on white FAILS 4.5:1 (it is not 4.5, it is 4.4781)",
          fails["passes"] is False, fails)
    check("...and rounding it to one decimal would have said 4.5, which is the trap",
          round(fails["ratio"], 1) == 4.5, round(fails["ratio"], 1))
    check("#757575 on white is 4.6075:1 and PASSES", passes["passes"] is True
          and abs(passes["ratio"] - 4.6075) < 0.001, passes)
    check("the same pair passes as LARGE text, where the floor is 3:1",
          A.check_contrast("#777777", "#ffffff", large=True)["passes"] is True)
    check("a colour that is not hex is NOT CHECKED rather than guessed at",
          A.check_contrast("rgb(1,2,3)", "#fff")["checked"] is False)
    audit = A.audit_text_or_ui(".a { color: #777777; background: #ffffff; }", kind="css")
    rules = [(f["rule"], f["tier"]) for f in audit["findings"]]
    check("the audit reports an unrounded contrast failure as HIGH R-25",
          ("R-25", "HIGH") in rules, rules)


# --------------------------------------------------------------------------
#   5. The audit's tiers, and after mode
# --------------------------------------------------------------------------

AUDIT_SAMPLE = (
    "<style>\n"
    ".card { color: #777777; background: #ffffff; outline: none; }\n"
    ".g1 { backdrop-filter: blur(4px); }\n"
    ".g2 { backdrop-filter: blur(5px); }\n"
    ".g3 { backdrop-filter: blur(6px); }\n"
    "</style>\n"
    "<h1>Revolutionary — and seamless</h1>\n"
    "<a href=\"#\">Go</a>\n"
    "<button>Press me</button>\n"
    "```python\n"
    "# ================\n"
    "```\n"
)


def t_the_audit_tiers_are_the_rulebooks_own():
    reset()
    out = A.audit_text_or_ui(AUDIT_SAMPLE, kind="html")
    got = {(f["rule"], f["tier"]) for f in out["findings"]}
    for want in (("R-02", "HIGH"), ("R-10", "MEDIUM"), ("R-16", "LOW"),
                 ("R-25", "HIGH"), ("R-26", "HIGH"), ("R-32", "HIGH")):
        check(f"the audit reports {want[0]} as {want[1]}", want in got, sorted(got))
    check("a generic CTA was not present, and the audit does not invent one",
          ("R-15", "LOW") not in got, sorted(got))
    cta = A.audit_text_or_ui("<button>Get Started</button>", kind="html")
    check("R-15 is reported when a generic CTA IS there",
          ("R-15", "LOW") in {(f["rule"], f["tier"]) for f in cta["findings"]},
          cta["findings"])
    check("every finding carries the line it is on",
          all(isinstance(f["line"], int) and f["line"] >= 1 for f in out["findings"]))
    check("the counts add up to the findings", sum(out["counts"].values()) == len(out["findings"]))
    check("the audit is deterministic: two runs are identical",
          out["findings"] == A.audit_text_or_ui(AUDIT_SAMPLE, kind="html")["findings"])
    audit = A.audit_text_or_ui("# a banner\n# ==========\n", kind="code")
    check("antislop-code is LOW", any(f["rule"] == "antislop-code" and f["tier"] == "LOW"
                                      for f in audit["findings"]), audit["findings"])


def t_the_four_block_delivery_gate():
    reset()
    A.set_enabled(True)
    out = A.audit_text_or_ui(AUDIT_SAMPLE, kind="ui")
    gate = out["gate"]
    names = [b["block"] for b in gate["blocks"]]
    check("the gate has the rulebook's four blocks",
          names == ["Hard Gate", "Purpose-Gate", "Liveliness",
                    "Craftsmanship & Quality Locks"], names)
    check("a UI audit in during mode carries the report itself",
          "delivery_gate" in out and "Anti-Slop Delivery Gate:" in out["delivery_gate"],
          out.get("delivery_gate"))
    check("Hard Gate FAILS on this sample (R-02/R-25/R-26/R-32 are in it)",
          gate["blocks"][0]["verdict"] == "FAIL", gate["blocks"][0])
    check("Purpose-Gate FAILS too (three glass declarations, cap is 2)",
          gate["blocks"][1]["verdict"] == "FAIL", gate["blocks"][1])
    check("Liveliness is NOT CHECKED rather than claimed as a pass",
          gate["blocks"][2]["verdict"] == "NOT CHECKED", gate["blocks"][2])
    A.set_mode("after")
    out2 = A.audit_text_or_ui(AUDIT_SAMPLE, kind="ui")
    check("after mode does not attach the delivery gate to the report",
          "delivery_gate" not in out2, sorted(out2))
    A.set_mode("during")
    clean = A.audit_text_or_ui("<p>A plain sentence with nothing wrong.</p>", kind="html")
    check("a clean page passes every block a program can check",
          clean["gate"]["blocks"][0]["verdict"] == "PASS", clean["gate"]["blocks"][0])
    A.set_enabled(False)


# --------------------------------------------------------------------------
#   6. The fast path: 0 cards, real state, a receipt
# --------------------------------------------------------------------------

class FakeSched:
    def mark_command(self, text): pass
    def note_set(self, *a, **k): pass
    def forget_set(self, *a, **k): pass
    def last_set(self, *a, **k): return None


class _GateSpy:
    """Any approval card raised during the fast path would come through
    jarvis_gate.check. This counts calls and refuses to answer one.

    jarvis_gate.py is NOT in this repository (it is one of the owner's own
    modules, delivered by the base), so on a checkout the name is stood up as a
    stand-in module for the duration: a quick path that imported it would get
    this spy and be caught, which is the property being proved.
    """

    def __init__(self):
        self.calls = []
        self._fake = None

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        raise AssertionError("an approval card was raised by a cardless setting")

    def __enter__(self):
        import types
        self.was = sys.modules.get("jarvis_gate")
        if self.was is not None:
            self.real = getattr(self.was, "check", None)
            self.was.check = self
        else:
            self._fake = types.ModuleType("jarvis_gate")
            self._fake.check = self
            sys.modules["jarvis_gate"] = self._fake
        return self

    def __exit__(self, *_a):
        if self._fake is not None:
            sys.modules.pop("jarvis_gate", None)
        elif getattr(self, "real", None) is not None:
            self.was.check = self.real
        return False


def _say(text, sched=None) -> tuple:
    """(intent name, reply) for one sentence, through the real fast path."""
    import time
    intent = Q.match(text, time.time())
    res = Q.answer(text, sched=sched or FakeSched(), now=time.time())
    return (intent.name if intent else None), (res.reply if res else None)


def t_every_named_sentence_resolves_with_zero_cards():
    reset()
    cases = [
        ("turn on anti-slop", "settings_bool"),
        ("turn off anti-slop", "settings_bool"),
        ("enable anti-slop", "settings_bool"),
        ("disable anti-slop", "settings_bool"),
        ("is anti-slop on", "settings_antislop_state"),
        # The mode goes through the repo's OWN generic "set <name> to <value>"
        # grammar (antislop_mode is a CHOICE_SETTINGS row), so its intent is
        # settings_choice - one way to say it, one setter.
        ("set anti-slop mode to after", "settings_choice"),
        ("set anti-slop mode to during", "settings_choice"),
        ("turn on anti-slop for copy", "settings_antislop_scope"),
        ("turn off anti-slop for code", "settings_antislop_scope"),
        ("turn on anti-slop for ui", "settings_antislop_scope"),
    ]
    with _GateSpy() as spy:
        for text, want in cases:
            name, reply = _say(text)
            check(f"{text!r} resolves to {want} with an answer",
                  name == want and bool(reply), f"{name} / {reply!r}")
    check("...and not one approval card was raised (0 cards, both directions)",
          spy.calls == [], spy.calls)
    reset()
    a1_name, a1 = _say("turn on anti-slop")
    check("'turn on anti-slop' really writes the state", A.is_enabled() is True)
    check("...and says so, naming what it watches", "Anti-Slop filter on" in (a1 or ""), a1)
    b_name, b = _say("turn off anti-slop")
    check("'turn off anti-slop' really writes the state", A.is_enabled() is False)
    check("...and says so", "Anti-Slop filter off" in (b or ""), b)
    mode_name, mode_reply = _say("set anti-slop mode to after")
    check("'set anti-slop mode to after' really changes the mode",
          A.get_state()["mode"] == "after", A.get_state()["mode"])
    check("...and says which mode it is now in", "after" in (mode_reply or ""), mode_reply)
    scoped, scoped_reply = _say("turn off anti-slop for code")
    check("'turn off anti-slop for code' turns off ONE scope",
          A.get_state()["scopes"] == {"copy": True, "code": False, "ui": True},
          A.get_state()["scopes"])
    check("...and the answer says the other scopes are unchanged",
          "unchanged" in (scoped_reply or ""), scoped_reply)
    on_name, _ = _say("turn on anti-slop for code")
    _say("turn on anti-slop")
    state_reply = _say("is anti-slop on")[1] or ""
    check("'is anti-slop on' reports the mode, the scopes and the dials",
          "Mode:" in state_reply and "Watching:" in state_reply and "Dials:" in state_reply,
          state_reply)
    reset()


def t_the_fast_path_leaves_a_receipt():
    reset()
    before = _receipt_count()
    if not before and not _receipts_available():
        skip("jarvis_receipts is not importable here, so the receipt half of "
             "bite 6 could not run (this is NOT a pass)")
        return
    _say("turn on anti-slop")
    after = _receipt_count()
    check("one 1-click Undo receipt was recorded by the fast path",
          after == before + 1, f"{before} -> {after}")
    reset()


# --------------------------------------------------------------------------
#   The routes: a stand-in Handler with the core's own three callbacks
# --------------------------------------------------------------------------

class Core:
    """The four things the backend hands a module's install(): its Handler and
    three checks - the same shape as jarvis_receipts.install()."""

    def __init__(self):
        self.sent = []
        core = self

        class Handler:
            def __init__(self, path="/", body=b"{}"):
                self.path = path
                self._body = body

            def do_GET(self):
                core.sent.append(("core-GET", self.path))

            def do_POST(self):
                core.sent.append(("core-POST", self.path))

            def _send(self, code, payload):
                core.sent.append((code, payload))
                return payload

        self.Handler = Handler
        self.token_ok_answer = True

    def origin_ok(self, req):
        return True

    def token_ok(self, req):
        return self.token_ok_answer

    def read_body(self, req):
        return req._body

    def ctx(self):
        return {"origin_ok": self.origin_ok, "token_ok": self.token_ok,
                "read_body": self.read_body}

    def call(self, method, path, body=None):
        req = self.Handler(path, b"{}" if body is None else json.dumps(body).encode())
        self.sent.clear()
        getattr(req, "do_" + method)()
        return self.sent[-1] if self.sent else None


def t_the_routes_answer_through_the_core_handler():
    reset()
    core = Core()
    line = A.install(core.Handler, **core.ctx())
    check("install() returns a banner line naming both routes",
          isinstance(line, str) and "/api/antislop" in line, repr(line))
    code, out = core.call("GET", "/api/antislop")
    check("GET /api/antislop answers 200", code == 200, (code, out))
    check("...with the state a client draws a toggle from",
          {"enabled", "mode", "scopes", "dials"} <= set(out or {}), sorted(out or {}))
    code, out = core.call("POST", "/api/antislop", {"enabled": True})
    check("POST /api/antislop turns it on and answers the new state",
          code == 200 and out.get("enabled") is True and A.is_enabled() is True, (code, out))
    code, out = core.call("POST", "/api/antislop", {"mode": "after"})
    check("POST /api/antislop changes the mode",
          code == 200 and A.get_state()["mode"] == "after", (code, out))
    code, out = core.call("POST", "/api/antislop", {"scopes": {"code": False}})
    check("POST /api/antislop changes one scope without touching the others",
          code == 200 and A.get_state()["scopes"]["code"] is False
          and A.get_state()["scopes"]["copy"] is True, (code, out))
    code, out = core.call("POST", "/api/antislop", {"dials": {"energy": 3}})
    check("POST /api/antislop changes a dial", code == 200
          and A.get_state()["dials"]["energy"] == 3, (code, out))
    code, out = core.call("POST", "/api/antislop", {"nonsense": 1})
    check("a typo in the body is REFUSED, not silently stored",
          code == 400 and "nonsense" in str(out), (code, out))
    code, out = core.call("POST", "/api/antislop", {"mode": "sideways"})
    check("an unknown mode is refused with the two real ones",
          code == 400 and "during" in str(out), (code, out))
    code, out = core.call("POST", "/api/antislop/audit",
                          {"content": "a — b", "kind": "text"})
    check("POST /api/antislop/audit answers a findings report",
          code == 200 and out.get("ok") is True and out.get("findings"), (code, out))
    check("...and it is READ-ONLY: the audit changed no setting",
          A.get_state()["enabled"] is True and A.get_state()["mode"] == "after")
    code, out = core.call("POST", "/api/antislop/audit", {"content": ""})
    check("an empty audit is refused, not answered with a false all-clear",
          code == 400, (code, out))
    core.token_ok_answer = False
    code, out = core.call("GET", "/api/antislop")
    check("a bad token is refused before anything is read", code == 401, (code, out))
    core.token_ok_answer = True
    code = core.call("GET", "/some/other/route")
    check("a route of the core's own is handed straight back to it",
          code == ("core-GET", "/some/other/route"), code)
    reset()


# --------------------------------------------------------------------------
#   The agent: the note in the request, the scrub on the words
# --------------------------------------------------------------------------

def _no_real_io():
    """Fail loudly if the real (network-touching) post/stream ever runs - the
    same guard backend/test_agent.py uses."""
    import jarvis_agent as AG

    class Guard:
        def __enter__(self):
            self.real = AG._post, AG._open_stream, AG._get_json

            def boom(*_a, **_k):
                raise AssertionError("a real HTTP call ran")

            def no_lookup(*_a, **_k):
                raise OSError("no network in this test")

            AG._post, AG._open_stream, AG._get_json = boom, boom, no_lookup
            AG._CTX_CACHE.clear()
            AG._TOOLS_CACHE.clear()
            return self

        def __exit__(self, *_a):
            AG._post, AG._open_stream, AG._get_json = self.real
            return False

    return Guard()


def _one_turn(words: str, question: str = "hello") -> dict:
    """One local turn whose model says exactly `words`. Returns what was sent
    to the model (`request`) and what the app was given (`streamed`)."""
    import jarvis_agent as AG
    streamed, calls = [], []

    def opener(url, payload):
        calls.append(payload)

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self, _n=4096):
                if getattr(self, "done", False):
                    return b""
                self.done = True
                body = {"id": "x", "created": 1,
                        "choices": [{"delta": {"content": words}, "finish_reason": "stop"}]}
                return b"data: " + json.dumps(body).encode() + b"\n\ndata: [DONE]\n\n"
        return R()

    with _no_real_io():
        AG.run_local_turn([{"role": "user", "content": question}], "qwen3:8b",
                          ollama_url="http://127.0.0.1:11434",
                          stream_out=streamed.append, enabled_tools=set(),
                          open_stream=opener, manner=None, request={})
    text = []
    for line in b"".join(streamed).split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            continue
        obj = json.loads(line[5:])
        delta = (obj.get("choices") or [{}])[0].get("delta") or {}
        text.append(delta.get("content") or "")
    return {"request": calls[0] if calls else {}, "streamed": "".join(text),
            "raw": b"".join(streamed)}


def t_the_agent_adds_the_note_only_when_it_is_on():
    reset()
    off = _one_turn("hi")
    messages = json.dumps(off["request"].get("messages") or [])
    check("OFF: the request carries no antislop_filter block at all",
          "antislop_filter" not in messages, messages[-300:])
    reset()
    A.set_enabled(True)
    on = _one_turn("hi", question="design a landing page in html and css")
    messages = json.dumps(on["request"].get("messages") or [])
    check("ON: the request carries the <antislop_filter> block",
          "antislop_filter" in messages, messages[-400:])
    check("ON: it is a system message just before the question",
          messages.rfind("antislop_filter") < messages.rfind("\"user\""),
          "the block is after the user message")
    A.set_enabled(False)


def t_the_agent_scrubs_the_words_it_sends():
    reset()
    sample = "Fast \u2014 and seamless!"
    off = _one_turn(sample)
    check("OFF: the app gets the model's words exactly as written",
          off["streamed"] == sample, repr(off["streamed"]))
    reset()
    A.set_enabled(True)
    on = _one_turn(sample)
    check("ON: the app never sees the em dash", "\u2014" not in on["streamed"],
          repr(on["streamed"]))
    check("ON: and the words are otherwise the model's own",
          on["streamed"] == "Fast, and seamless!", repr(on["streamed"]))
    check("ON: the em dash is nowhere in the bytes that went out either",
          b"\xe2\x80\x94" not in on["raw"], on["raw"][-200:])
    A.set_enabled(False)


# --------------------------------------------------------------------------
#   The wiring that has to exist for any of this to reach the PC
# --------------------------------------------------------------------------

def t_the_module_ships_and_the_drop_in_folder_names_it():
    where = (HERE / "_where.py").read_text(encoding="utf-8")
    script = (_where.REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_antislop.py is in backend/_where.py's SHIPPED list",
          '"jarvis_antislop.py"' in where)
    check("...and in scripts/apply-patches.ps1's $SHIPPED list",
          "'jarvis_antislop.py'" in script)
    manifest = _where.REPO / "plugins" / "ready" / "antislop" / "plugin.json"
    check("the drop-in folder that installs its routes is there", manifest.is_file(),
          str(manifest))
    if manifest.is_file():
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        check("...it names this module and its install()",
              doc.get("module") == "jarvis_antislop" and doc.get("install") == "handler",
              doc)
        check("...and it replaces no patch, so the catalogue leaves it alone",
              "replaces_patch" not in doc, doc)
        check("...and it carries the whole number the loader sorts by",
              isinstance(doc.get("stack_order"), int), doc.get("stack_order"))


def t_the_registry_row_and_its_reader_exist():
    setting = next((b for b in R.BOOL_SETTINGS if b.key == "antislop"), None)
    check("BOOL_SETTINGS has an antislop row", setting is not None)
    if setting is not None:
        check("...it is named the way a person says it",
              R.find_bool_setting("anti-slop") is setting
              and R.find_bool_setting("slop filter") is setting
              and R.find_bool_setting("ai slop filter") is setting)
    choice = next((c for c in R.CHOICE_SETTINGS if c.key == "antislop_mode"), None)
    check("CHOICE_SETTINGS has an antislop_mode row", choice is not None)
    if choice is not None:
        check("...whose two choices are during and after",
              set(choice.options().values()) == {"during", "after"},
              choice.options())
    import jarvis_feature_guide as FG
    check("the feature guide can READ the switch (so 'is it on?' is never a guess)",
          "antislop" in FG.STATE_READERS)
    check("...and the read agrees with the module",
          FG.read_state("antislop") is A.is_enabled())
    check("'antislop' is in jarvis_quick's CHANGE_BY_ASKING list",
          "antislop" in Q.CHANGE_BY_ASKING)
    check("'is anti-slop on' is a read-only intent (it must not eat 'cancel that')",
          "settings_antislop_state" in Q.READ_ONLY_INTENTS)
    check("...and the two that change or refuse are NOT read-only",
          "settings_antislop_mode" not in Q.READ_ONLY_INTENTS
          and "settings_antislop_scope" not in Q.READ_ONLY_INTENTS)


# --------------------------------------------------------------------------
#   The six bites
# --------------------------------------------------------------------------

def run_bites():
    print("\n--- bite 1: instant ON/OFF, 0 tokens when off ---")

    def proves_off_is_free(module):
        module.set_enabled(False)
        return module.prompt_block("html page") == "" and module.reply_filter() is None

    bites("1-off", '    state = get_state()\n    if not state.get("enabled", False):\n        return ""',
          '    state = get_state()\n    if False:\n        return ""',
          proves_off_is_free)

    def proves_on_costs_no_more_than_the_ceiling(module):
        module.set_enabled(True)
        size = len(module.prompt_block("design a landing page in html and css"))
        module.set_enabled(False)
        return 0 < size <= module.MAX_PROMPT_CHARS

    bites("1-ceiling", "MAX_PROMPT_CHARS = 1050", "MAX_PROMPT_CHARS = 60",
          proves_on_costs_no_more_than_the_ceiling)

    print("\n--- bite 2: R-37, Write Like Me wins ---")

    def proves_the_exemption(module):
        return _exemption_is_read_from_the_voiceprint(module)

    # The exemption lives in two places (the filter and the prompt); break the
    # filter's half, which is the one that would silently rewrite the owner's
    # own style.
    bites("2-r37", 'need_dashes = bool(scopes.get("copy", True)) and not voiceprint_uses_em_dash',
          'need_dashes = bool(scopes.get("copy", True))', proves_the_exemption)

    print("\n--- bite 3: antislop-code comment cleanup ---")

    def proves_the_cleanup(module):
        return _comment_cleanup_is_right(module)

    bites("3-code", 'r"^[ \\t]*(?:#|//|--|/\\*)[ \\t]*[=\\-*~_─━═]{4,}[ \\t]*$")',
          'r"^[ \\t]*(?:#|//|--|/\\*)[ \\t]*NEVERMATCHES{4,}[ \\t]*$")',
          proves_the_cleanup)

    print("\n--- bite 4: R-25, unrounded contrast ---")

    def proves_unrounded(module):
        return module.check_contrast("#777777", "#ffffff")["passes"] is False

    bites("4-contrast", "    passes = ratio >= need                       # unrounded, deliberately",
          "    passes = round(ratio, 1) >= need              # the rounding trap",
          proves_unrounded)

    print("\n--- bite 5: the audit's tiers ---")

    def proves_the_tiers(module):
        found = {(f["rule"], f["tier"]) for f in
                 module.audit_text_or_ui(AUDIT_SAMPLE, kind="html")["findings"]}
        return ("R-02", "HIGH") in found and ("R-10", "MEDIUM") in found

    bites("5-tiers", '    "R-02": "HIGH",     # em dash in agent-written prose',
          '    "R-02": "LOW",      # em dash in agent-written prose',
          proves_the_tiers)

    print("\n--- bite 6: the fast path, 0 cards and a receipt ---")

    def proves_the_fast_path(module):
        module.set_enabled(False)
        before = _receipt_count()
        name, reply = _say("turn on anti-slop")
        state = module.get_state()
        receipts = _receipt_count()
        module.set_enabled(False)
        return (bool(reply) and state.get("enabled") is True
                and receipts >= before + 1)

    # The fast path is only cardless and verified because the setter really
    # writes. A mutant that "succeeds" without writing must be caught by the
    # same check - which is what this breaks.
    bites("6-fastpath", "    _write(state)\n    _publish(state)\n    receipt = _receipt(",
          "    _publish(state)\n    receipt = _receipt(",
          proves_the_fast_path)


# --------------------------------------------------------------------------
#   Runner
# --------------------------------------------------------------------------

CHECKS = [
    t_the_default_is_off_and_says_so,
    t_the_switch_is_zero_tokens_and_zero_work_when_off,
    t_turning_it_on_writes_the_file_an_event_and_one_receipt,
    t_the_prompt_block_is_scoped_and_bounded,
    t_after_mode_asks_for_an_audit_and_rewrites_nothing,
    t_the_dials_are_bounded_and_refused_out_of_range,
    t_write_like_me_wins_under_r37,
    t_the_code_comment_cleanup_is_exact,
    t_the_stream_filter_matches_the_whole_text_scrub,
    t_contrast_is_unrounded,
    t_the_audit_tiers_are_the_rulebooks_own,
    t_the_four_block_delivery_gate,
    t_every_named_sentence_resolves_with_zero_cards,
    t_the_fast_path_leaves_a_receipt,
    t_the_routes_answer_through_the_core_handler,
    t_the_agent_adds_the_note_only_when_it_is_on,
    t_the_agent_scrubs_the_words_it_sends,
    t_the_module_ships_and_the_drop_in_folder_names_it,
    t_the_registry_row_and_its_reader_exist,
]


def main() -> int:
    print(f"settings folder for this run: {_CFG}")
    for fn in CHECKS:
        print(f"\n--- {fn.__name__} ---")
        reset()
        try:
            fn()
        except Exception:                    # noqa: BLE001 - one check never stops the suite
            check(f"{fn.__name__} raised", False, traceback.format_exc()[-900:])
    try:
        run_bites()
    except Exception:                        # noqa: BLE001
        check("run_bites raised", False, traceback.format_exc()[-900:])
    print()
    if SKIPPED:
        print(f"{len(SKIPPED)} SKIPPED (not passes):")
        for why in SKIPPED:
            print(f"  - {why}")
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print(f"{len(PASSED)} passed, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
