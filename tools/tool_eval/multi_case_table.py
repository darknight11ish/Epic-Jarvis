"""Print the SAME 8-case multi-step set side by side, before and after F1.

F1 (2026-10-18) changed what the full tool list sends (a top-K diet) and added
the identical-call breaker. Gemini's ruling is to re-run the exact same 8 cases
from `#570`, report all 8 per case, and not change the cases. This script does
only the reporting: it reads two `tool_eval_results.json` files - one from the
baseline tree, one from the F1 tree - and prints each case's pass, path and why.

    py -3 tools\\tool_eval\\multi_case_table.py <baseline.json> <after.json>

Both files must be real runs of:

    py -3 tools\\tool_eval\\ollama_tool_eval.py --suites multi --lists full --models jarvis-primary

The baseline file comes from a worktree of the commit BEFORE F1 (origin/main);
the after file from the F1 worktree. The cases themselves live in
`jarvis_tool_cases.py` and are untouched by this script.
"""
import json
import sys


def rows(path):
    """{case id: row} for the first model's full-list multi suite."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    models = doc.get("models") or {}
    if not models:
        raise SystemExit(f"{path}: no model rows (was a real run saved?)")
    model = next(iter(models))
    try:
        got = models[model]["rows"]["full"]["multi"]
    except (KeyError, TypeError):
        raise SystemExit(f"{path}: no full-list 'multi' rows for {model}")
    return {row.get("id"): row for row in got}


def cell(row):
    if row is None:
        return "MISSING"
    if row.get("pass"):
        return "PASS " + " > ".join(row.get("path") or [])
    why = row.get("why") or "a call did not carry what the earlier steps found"
    return "FAIL " + " > ".join(row.get("path") or []) + "  (" + str(why) + ")"


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[0])
        print("usage: multi_case_table.py <baseline.json> <after.json>")
        return 2
    before, after = rows(argv[1]), rows(argv[2])
    order = list(before) + [k for k in after if k not in before]
    print(f"{'case':<20} {'before (#570)':<44} after (F1)")
    print("-" * 110)
    old_pass = new_pass = 0
    for case_id in order:
        b, a = before.get(case_id), after.get(case_id)
        old_pass += bool(b and b.get("pass"))
        new_pass += bool(a and a.get("pass"))
        print(f"{str(case_id):<20} {cell(b):<44} {cell(a)}")
    print("-" * 110)
    print(f"{'TOTAL':<20} {old_pass}/{len(order):<42} {new_pass}/{len(order)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
