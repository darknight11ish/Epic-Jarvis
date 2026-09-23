"""Where the four learning jobs of 2026-09-23 meet each other.

    python3 test_learning_integration.py

No pytest, no network, no model. Each job (memory intake, feedback, skill
suggestions, speed/doctor/documents) has its own test file and was built on
its own. This file checks only what none of them could check alone: the
places where two of them touch the same code or the same card.

  1. The patch ORDER in scripts/apply-patches.ps1. feedback.patch must come
     before memory-intake.patch: feedback's POST hunk ends on the memory
     route line ("/api/memory/learning", "/api/memory/sleep_time"):) and
     memory-intake rewrites that line to add /api/memory/keep_both. The
     other way round, feedback's context is gone and the run stops before
     changing anything. Every new patch also has to come after the older
     patches whose output it quotes.

  2. The "retire this?" card (feedback) must not get the "Both are true"
     button (memory intake). That card has replaces_id set - it names the
     fact it asks about - so memory intake's first rule ("offer keep-both on
     any card that would retire a fact") offered it there. Pressing it would
     have marked the card accepted and retired nothing: a third answer that
     means the same as "keep using it" but records something else.

  3. The retire card's own wording must not trip the planted-instruction
     warning. It is text Jarvis wrote, not text from outside.

Parts 2 and 3 run twice: against jarvis_intake.py on its own (always), and
against a jarvis_extract.py carrying BOTH patches (only when one is there -
set JARVIS_BACKEND to a patched backend folder).
"""
import os, re, sys, tempfile, traceback, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-learning-integration-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.setdefault("JARVIS_NO_EMBED", "1")

if missing("jarvis_memory.py"):
    sys.path.append(str(HERE / "rebuilt"))
import jarvis_memory as M

# Ours: this directory first, so a stale copy in a backend folder cannot
# shadow the one being tested.
sys.path.insert(0, str(HERE))
# On a real install (JARVIS_BACKEND set), the backend's own copy must be
# there and be this one - see _where.require_shipped.
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_intake.py", "jarvis_feedback.py")
import jarvis_intake as I
import jarvis_feedback as F

FAILED, PASSED = [], []

# The card's wording, as feedback.patch's propose_retire() builds it for
# 7 wrong answers and 1 right one. Kept in step with the patch by
# t_the_retire_wording_is_the_patchs below.
RETIRE_TEXT = ("Stop using this fact? It was part of 7 answers you marked wrong "
               "and 1 you marked right. Accepting this card retires the fact (it "
               "stays in the history); discarding it keeps the fact exactly as "
               "it is.")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---- 1. the order of the stack ----------------------------------------------

def _stack():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    body = ps1[ps1.index("$PATCHES = @("):]
    body = body[:body.index("\n)")]
    return re.findall(r"^\s*'([^']+\.patch)'", body, re.M)


def t_the_stack_order():
    names = _stack()
    pos = {n: i for i, n in enumerate(names)}
    new = ["feedback.patch", "memory-intake.patch", "skill-suggest.patch",
           "documents-owned.patch", "speed-record.patch"]
    for n in new:
        check(f"apply-patches.ps1 lists {n}", n in pos)
    if not all(n in pos for n in new):
        return
    check("feedback.patch comes BEFORE memory-intake.patch - memory-intake "
          "rewrites the line feedback's hunk ends on",
          pos["feedback.patch"] < pos["memory-intake.patch"])
    # Each new patch after the older ones whose output it quotes, as its own
    # README section says.
    needs = {
        "feedback.patch": ["memory-safety.patch", "memory-noise.patch",
                           "decide-once.patch", "memory-pane.patch",
                           "tool-calling-wiring.patch"],
        "memory-intake.patch": ["memory-safety.patch", "memory-noise.patch",
                                "decide-once.patch", "extraction-wiring.patch",
                                "memory-pane.patch"],
        "skill-suggest.patch": ["appearance.patch"],
        "documents-owned.patch": ["documents-honesty.patch"],
        "speed-record.patch": ["gpu-offload.patch", "tool-calling-wiring.patch"],
    }
    for n, deps in needs.items():
        late = [d for d in deps if pos.get(d, -1) > pos[n] or d not in pos]
        check(f"{n} comes after every patch whose output it quotes",
              not late, f"out of order or missing: {late}")
    on_disk = sorted(p.name for p in (REPO / "backend").glob("*.patch"))
    check("every .patch in backend/ is in the list (the script refuses to "
          "run otherwise)", not [p for p in on_disk if p not in pos],
          repr([p for p in on_disk if p not in pos]))


def t_the_retire_wording_is_the_patchs():
    src = (REPO / "backend" / "feedback.patch").read_text(encoding="utf-8")
    for bit in ("Stop using this fact? It was part of", "you marked wrong and",
                "you marked right. Accepting this card retires",
                "the fact (it stays in the history); discarding it keeps the",
                "fact exactly as it is."):
        check(f"feedback.patch still words the card with {bit!r}", bit in src)
    check("and marks it with source='feedback_retire'",
          'RETIRE_SOURCE = "feedback_retire"' in src)


# ---- 2 and 3, on jarvis_intake alone ----------------------------------------

def _retire_row():
    return {"id": 1, "text": RETIRE_TEXT, "replaces": "Mario's editor is Vim",
            "replaces_id": 4, "replaces_text": "Mario's editor is Vim",
            "confidence": None, "source": "feedback_retire", "created": 0}


def t_intake_alone():
    rows = I.annotate([_retire_row(),
                       {"id": 2, "text": "Mario's editor is VS Code now",
                        "replaces_id": 4, "source": "conversation"}])
    check("a retire card does NOT offer 'Both are true'",
          rows[0]["keep_both_ok"] is False, repr(rows[0]))
    check("CONTROL an ordinary correction card still offers it",
          rows[1]["keep_both_ok"] is True, repr(rows[1]))
    check("the retire card's own wording raises no planted-instruction flag",
          rows[0]["flags"] == [] and rows[0]["flags_checked"] is True,
          repr(rows[0]["flags"]))


# ---- 2 and 3, through a jarvis_extract.py with both patches ----------------

def t_through_the_patched_extractor():
    if missing("jarvis_extract.py"):
        return check("SKIP patched-extractor half - " + explain(), True)
    import jarvis_extract as X
    have = [hasattr(X, "propose_retire"), hasattr(X, "decide_keep_both")]
    if not all(have):
        return check("jarvis_extract.py carries feedback.patch AND "
                     "memory-intake.patch", False,
                     f"propose_retire={have[0]} decide_keep_both={have[1]}")
    d = Path(tempfile.mkdtemp(prefix="case-", dir=_TMP))
    os.environ["JARVIS_FEEDBACK_DB"] = str(d / "feedback.db")
    s = M.MemoryStore(path=d / "memory.db")
    M._store = s
    fid = s.add_fact("Mario's main editor is Vim")
    before = s.status()["facts"]
    for _ in range(5):
        tid = F.record_turn([f"mem:{fid}"])
        assert F.mark(tid, "wrong")["ok"]
    cards = [p for p in X.pending() if p.get("source") == "feedback_retire"]
    check("five wrong answers queue one retire card", len(cards) == 1, repr(X.pending()))
    if not cards:
        return
    card = cards[0]
    check("pending() says keep_both_ok is false on it", card.get("keep_both_ok") is False,
          repr(card))
    check("and its wording raises no flag", card.get("flags") == [], repr(card.get("flags")))
    got = X.decide_keep_both(card["id"])
    check("decide_keep_both refuses it as not a correction",
          isinstance(got, dict) and got.get("ok") is False
          and got.get("reason") == "not_a_correction", repr(got))
    check("...the card is still waiting for a real answer",
          any(p["id"] == card["id"] for p in X.pending()))
    check("...the fact is still current", s.get(fid)["valid_to"] is None)
    check("...and nothing was added", s.status()["facts"] == before)
    check("CONTROL accepting it still retires the fact",
          X.decide(card["id"], True) == fid and s.get(fid)["valid_to"] is not None)


if __name__ == "__main__":
    for fn in (t_the_stack_order, t_the_retire_wording_is_the_patchs,
               t_intake_alone, t_through_the_patched_extractor):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
