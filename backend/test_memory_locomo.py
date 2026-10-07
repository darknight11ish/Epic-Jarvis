"""test_memory_locomo.py - milestone 13: LoCoMo's "link two facts" questions.

    python3 backend/test_memory_locomo.py

What it proves:

1. backend/fixtures/locomo_multihop.json loads, says where it came from
   (LoCoMo's commit and its CC BY-NC 4.0 licence), stays small, and is
   sound: every question cites at least one turn, every cited turn exists
   in its chat, and most questions cite two or more (they are multi-hop).
2. The scoring runs: `eval_memory.run_locomo` stores one chat's turns in a
   scratch store (words-only, nothing downloaded), asks its questions, and
   numbers come out - found-any, found-ALL and nDCG at 5 and 10, each in
   range, found-all never above found-any, @10 never below @5.
3. `eval_memory.py --locomo --words-only` runs end to end and writes its
   two files; `--locomo --against` is refused, not silently ignored.
4. The fixture and the builder are test-only: not in _where.SHIPPED or
   scripts/apply-patches.ps1, and LoCoMo is credited in
   THIRD-PARTY-NOTICES.txt's hand-written part.

WHAT IT DOES NOT PROVE: anything about meaning search (words only here),
or what the numbers are on the owner's PC -
`python backend/eval_memory.py --locomo` there measures that.
"""
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

REPO = _where.REPO
FIXTURE = HERE / "fixtures" / "locomo_multihop.json"
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-locomo-"))
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_fixture():
    raw = FIXTURE.read_bytes()
    check("the fixture is well under 1 MB", len(raw) < 700_000, f"{len(raw):,} bytes")
    doc = json.loads(raw.decode("utf-8"))
    check("it names LoCoMo and its source commit",
          "snap-research/locomo" in doc.get("source", "")
          and len(doc.get("commit", "")) == 40, doc.get("commit"))
    check("it names the CC BY-NC 4.0 licence and says test data only",
          "CC BY-NC 4.0" in doc.get("licence", "") and "Test data only" in doc["licence"])
    chats = doc["chats"]
    qs = [q for c in chats for q in c["questions"]]
    check("five chats and well over a hundred questions",
          len(chats) == 5 and len(qs) > 150, f"{len(chats)} chats, {len(qs)} questions")
    bad = []
    for c in chats:
        ids = [t[0] for s in c["sessions"] for t in s["turns"]]
        have = set(ids)
        if len(ids) != len(have):
            bad.append(f"{c['id']}: a turn id twice")
        for s in c["sessions"]:
            for t in s["turns"]:
                if not (isinstance(t, list) and 3 <= len(t) <= 4 and t[1] in c["speakers"]
                        and (t[2].strip() or (len(t) > 3 and t[3].strip()))):
                    bad.append(f"{c['id']}: odd turn {t[:2]}")
        for q in c["questions"]:
            if not q["evidence"]:
                bad.append(f"{c['id']}: no evidence for {q['q']}")
            bad += [f"{c['id']}: {e} not in the chat" for e in q["evidence"] if e not in have]
    check("every question cites turns that exist, every turn is well formed",
          not bad, "; ".join(bad[:5]))
    multi = sum(len(q["evidence"]) >= 2 for q in qs)
    check("most questions cite two or more turns (multi-hop)",
          multi >= 0.9 * len(qs), f"{multi} of {len(qs)}")


def t_scoring():
    import eval_memory as E
    turn = ["D1:1", "Ann", "hi", "a photo of a dog"]
    check("a turn is stored as LoCoMo's own retrieval code writes it",
          E.locomo_text(turn) == 'Ann said, "hi" [shares a photo of a dog]'
          and E.locomo_text(turn[:3]) == 'Ann said, "hi"')
    res = E.run_locomo(True, _TMP / "one", chats=1)
    s = res.get("search") or {}
    check("one chat stored and asked", len(res["chats"]) == 1
          and res["chats"][0]["turns"] > 300 and s.get("questions", 0) > 20, res["chats"])
    check("words only here, and it says so", res.get("semantic") is False, res.get("embedder"))
    ok = True
    blocks = [s] + ([res["entities"]] if res.get("entities") else [])
    for b in blocks:
        for k in E.LOCOMO_KS:
            a, al, nd = b[f"recall_any_at_{k}"], b[f"recall_all_at_{k}"], b[f"ndcg_at_{k}"]
            ok &= 0 <= al <= a <= 100 and 0 <= nd <= 1
        ok &= b["recall_any_at_10"] >= b["recall_any_at_5"]
        ok &= b["recall_all_at_10"] >= b["recall_all_at_5"]
    check("numbers come out, in range, and consistent", ok, blocks)
    check("words alone find some evidence (the wiring works)",
          s["recall_any_at_10"] > 0, s)
    print(f"        one chat, words only: found-any@5 {s['recall_any_at_5']}%, "
          f"found-all@5 {s['recall_all_at_5']}%, nDCG@5 {s['ndcg_at_5']}")


def t_cli():
    out = _TMP / "cli"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("JARVIS_MEMORY_DB", None)
    # 1800 seconds, was 600. This is a TIMEOUT, not a slow assertion: the whole
    # LoCoMo evaluation runs here as a subprocess, and on the owner's 24-core PC
    # it takes 38 seconds - but GitHub's shared 2-core Windows runner is about
    # 15x slower, so 600 expired partway through and the suite failed with no
    # failing check at all (13 passed, 1 failed, `t_cli`, TimeoutExpired).
    # Measured 2026-10-07: it failed that way in three separate CI runs - twice
    # on the bug-audit branch and once on the videos branch, neither of which
    # touches this file or eval_memory.py. The Windows job's own ceiling is 90
    # minutes and the rest of the sweep takes about 40, so 1800 still fits with
    # room to spare. Raising a timeout does not hide a wrong answer: every check
    # below still runs, and the evaluation's own numbers are asserted.
    r = subprocess.run([sys.executable, str(HERE / "eval_memory.py"), "--locomo",
                        "--words-only", "--out", str(out)],
                       capture_output=True, text=True, timeout=1800, env=env)
    check("eval_memory.py --locomo --words-only runs", r.returncode == 0, r.stderr[-800:])
    js = sorted(out.glob("memory-eval-locomo-*.json"))
    md = sorted(out.glob("memory-eval-locomo-*.md"))
    res = json.loads(js[-1].read_text(encoding="utf-8")) if js else {}
    text = md[-1].read_text(encoding="utf-8") if md else ""
    check("... writes both files, all five chats",
          bool(js and md) and len(res.get("chats", [])) == 5)
    check("... and the report says words only and CC BY-NC 4.0",
          "words only" in text and "CC BY-NC 4.0" in text)
    check("... and writes no main self-test files", not list(out.glob("memory-eval-2*")))
    r = subprocess.run([sys.executable, str(HERE / "eval_memory.py"), "--locomo",
                        "--against", "x.json", "--out", str(out / "no")],
                       capture_output=True, text=True, timeout=60, env=env)
    check("--locomo with --against is refused", r.returncode == 2 and "--against" in r.stdout)


def t_test_only():
    shipped = " ".join(_where.SHIPPED)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("not shipped: not in _where.SHIPPED or apply-patches.ps1",
          "locomo" not in shipped.lower() and "locomo" not in ps1.lower())
    notices = (REPO / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    hand = notices[:notices.find("\n2. RUST LIBRARIES")]
    check("LoCoMo credited in the hand-written notices, as test data, CC BY-NC 4.0",
          "snap-research/locomo" in hand and "CC BY-NC 4.0" in hand
          and "locomo_multihop.json" in hand)


if __name__ == "__main__":
    import shutil
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
