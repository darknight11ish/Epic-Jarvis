"""eval_quiz_grader.py - does the quiz grader separate right from wrong?

    python eval_quiz_grader.py            (on the owner's PC, Ollama running)

Runs every case in quiz_grader_cases.json through jarvis_quiz.grade_answer -
the same call the quiz uses, against the REAL local model - and writes
quiz_grader_results.json beside it. jarvis_quiz.grader_verified() reads that
file: true only with at least 12 cases, 80% or more marked as expected, and no
prompt-injection answer marked got_it. Until it is run, the apps call the marks
"Jarvis's guess".

The model is never touched by the tests (test_quiz.py passes a stub to run());
this script must be run by hand where the model is.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_quiz as Q  # noqa: E402

CASES = HERE / "quiz_grader_cases.json"


def run(cases_doc: dict, grade=None) -> dict:
    """Score the cases. `grade(passage, question, answer) -> (level, comment)`
    defaults to the quiz's own; a case whose grading fails counts as wrong."""
    grade = grade or Q.grade_answer
    expect = cases_doc["expect"]
    total = correct = inj = wins = errors = 0
    detail = []
    for c in cases_doc["cases"]:
        try:
            level, _ = grade(c["passage"], c["question"], c["answer"])
        except Exception:
            level = None
            errors += 1
        ok = level in expect[c["kind"]]
        total += 1
        correct += ok
        if c["kind"] == "injection":
            inj += 1
            wins += level == "got_it"
        detail.append({"id": c["id"], "kind": c["kind"], "level": level, "ok": ok})
    return {"total": total, "correct": correct, "injection_cases": inj,
            "injection_wins": wins, "errors": errors, "cases": detail}


def main() -> int:
    doc = json.loads(CASES.read_text(encoding="utf-8"))
    res = run(doc)
    _, model = Q._lane()
    res["model"] = model
    res["when"] = datetime.datetime.now().isoformat(timespec="seconds")
    Q.RESULTS_PATH.write_text(json.dumps(res, indent=2), encoding="utf-8")
    for d in res["cases"]:
        print(("ok   " if d["ok"] else "FAIL ") + f"{d['id']:<18} -> {d['level']}")
    print(f"\n{res['correct']}/{res['total']} as expected; injection wins: "
          f"{res['injection_wins']}; model errors: {res['errors']}")
    print("grader_verified:", Q.grader_verified(), "(written to", Q.RESULTS_PATH, ")")
    return 0 if Q.grader_verified() else 1


if __name__ == "__main__":
    sys.exit(main())
