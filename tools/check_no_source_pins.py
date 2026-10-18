#!/usr/bin/env python3
"""No test may pin the SOURCE TEXT of a production module.

    python3 tools/check_no_source_pins.py            # the gate
    python3 tools/check_no_source_pins.py --measure  # what is here today

WHY THIS EXISTS. Seven checks in this project passed because they measured
something other than the invariant they were named for:

  1. `origin/main`'s copy of a file, instead of the file in the tree;
  2. the checkout's own topology (a detached HEAD made a check vacuous);
  3. "76% less of the tree" read as a healthy total;
  4. an unmeasured fallback path taken as the measured one;
  5. git HISTORY, which is a function of what has been committed, not of the
     tree - it detonated on the next commit that touched the file;
  6. the exact SPELLING of a call (`invoke("devices_label", ...)`) - it went red
     when the code got BETTER, because the call had been renamed to the shared
     budgeted form;
  7. a test that pinned a DEFECT, so the fix turned it red.

All seven are one mistake: asserting about source text instead of exercising the
seam at runtime. A discipline does not enforce itself, so this is the ratchet.

WHAT IT DETECTS, with `ast.parse` - never by reading source as text (which would
be the disease this cures). A module-level NAME is a SOURCE TEXT variable when
it is assigned from:

  * `Path(...).read_text()` / `.read_text()` / `.read()`, `open(...).read()`
  * `inspect.getsource(...)`
  * `subprocess.run/Popen/check_output(...)` whose arguments name git together
    with a history or tree verb (`show`, `log`, `cat-file`, `ls-tree`,
    `rev-list`, `blame`, `diff`)

and every comparison of a string against one of those names is counted:

  * `"literal" in src` / `not in` (an `ast.Compare` with `In`/`NotIn`)
  * `src.find(...)`, `src.count(...)`, `src.index(...)`, `src.startswith`,
    `src.endswith`
  * `re.search(pattern, src)` / `match` / `findall` with `src` as an argument

TWO SHAPES THAT REPLACE A SOURCE PIN - and a pin should be replaced by one of
them, not by a cleverer regex:

  1. CALL THE REAL FUNCTION, with a spy or a stub, and assert on what it
     received. That is what this project's newest tests do (a never-settling
     invoke, a readers object answering `(0.0, 0.0)`, a file written to a temp
     folder), and it cannot go red because a name was spelled differently.

  2. WHEN STATIC INSPECTION IS GENUINELY NEEDED, WALK `ast` NODES. A docstring
     is an `ast.Constant` and can never be mistaken for an `ast.Call`, so
     "this module calls X" is `any(isinstance(n, ast.Call) ...)` - structural,
     immune to comments, docstrings and reformatting. The text version of that
     check is what failed as #6 above.

THE CEILING RATCHET. `SOURCE_PIN_CEILING` records the source pins measured on
the day this landed. A file not named there may have ZERO. A recorded number is
a CEILING: it may go down, never up - so the debt is recorded honestly and can
only be paid off, never grown. When the count goes down, lower the entry: the
checker prints both numbers so the movement is visible.

The counts are deliberately CONSERVATIVE: a module-level name is treated as
source text for the whole file once it is assigned from a source read anywhere,
so a `src` reused for something else is still counted. Over-counting only makes
the ceiling honest; under-counting would hide a pin.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Where a source pin may live: the permanent suites and the checkers.
GLOBS = ("backend/test_*.py", "tools/check_*.py", "tools/test_*.py")

#: A recorded ceiling per file. Absent = 0. May only go DOWN.
SOURCE_PIN_CEILING: dict[str, int] = {
    # MEASURED ON origin/main 5e84da53 (2026-10-17): the debt as it stands.
    # A ceiling may go DOWN only. These are not approvals - they are what the
    # tool found on the day it landed, so an increase is caught and a
    # decrease is visible. A flag-day rewrite of 116 files is how this becomes
    # a PR that conflicts with everything, so the debt is recorded, not paid.
    "backend/test_account_secrets.py": 1,
    "backend/test_animal.py": 6,
    "backend/test_api_doc.py": 3,
    "backend/test_apply_outcomes.py": 7,
    "backend/test_approval_notice.py": 4,
    "backend/test_attention_route.py": 1,
    "backend/test_backoff_rule.py": 4,
    "backend/test_better_voice.py": 2,
    "backend/test_big_coder.py": 2,
    "backend/test_big_model.py": 6,
    "backend/test_blend_voices.py": 2,
    "backend/test_brain_reads.py": 1,
    "backend/test_briefing.py": 9,
    "backend/test_browser_engine.py": 2,
    "backend/test_calendar_link.py": 1,
    "backend/test_card_words.py": 1,
    "backend/test_chat_stream.py": 1,
    "backend/test_chatbot.py": 4,
    "backend/test_chatbot_api.py": 1,
    "backend/test_chatbot_keys.py": 6,
    "backend/test_chatbot_limits.py": 15,
    "backend/test_chatbot_privacy.py": 1,
    "backend/test_chatbot_routes.py": 2,
    "backend/test_chatbot_sites.py": 3,
    "backend/test_cloud_say_yes.py": 3,
    "backend/test_cloud_spend.py": 2,
    "backend/test_compaction.py": 6,
    "backend/test_data_health.py": 3,
    "backend/test_docker.py": 1,
    "backend/test_documents.py": 3,
    "backend/test_energy.py": 2,
    "backend/test_feedback.py": 9,
    "backend/test_find_phone.py": 1,
    "backend/test_focus.py": 1,
    "backend/test_focus_brief.py": 2,
    "backend/test_forecast.py": 3,
    "backend/test_front.py": 2,
    "backend/test_gate_push.py": 1,
    "backend/test_gate_risk_words.py": 1,
    "backend/test_gate_touches.py": 5,
    "backend/test_goals.py": 2,
    "backend/test_handoff.py": 5,
    "backend/test_handoff_front.py": 1,
    "backend/test_hardware.py": 1,
    "backend/test_history_import.py": 1,
    "backend/test_identity.py": 2,
    "backend/test_inbox_tidy.py": 3,
    "backend/test_injection_table.py": 8,
    "backend/test_jarvis_open.py": 1,
    "backend/test_jobs.py": 3,
    "backend/test_kokoro.py": 3,
    "backend/test_limits.py": 2,
    "backend/test_limits_settings_route.py": 1,
    "backend/test_live.py": 3,
    "backend/test_manner.py": 1,
    "backend/test_media.py": 3,
    "backend/test_memory_entities.py": 3,
    "backend/test_memory_honesty.py": 7,
    "backend/test_memory_recall.py": 1,
    "backend/test_memory_rerank.py": 2,
    "backend/test_model_lanes.py": 16,
    "backend/test_news.py": 2,
    "backend/test_note_capture.py": 6,
    "backend/test_notion_obsidian.py": 4,
    "backend/test_obscura.py": 1,
    "backend/test_ocr_words.py": 5,
    "backend/test_open_chat.py": 2,
    "backend/test_optin_models.py": 5,
    "backend/test_owner_check.py": 2,
    "backend/test_pc_help.py": 2,
    "backend/test_picture_card.py": 3,
    "backend/test_pictures.py": 4,
    "backend/test_power_switch.py": 2,
    "backend/test_progress.py": 2,
    "backend/test_projects.py": 9,
    "backend/test_prompt_coach.py": 11,
    "backend/test_quiz_cloud.py": 1,
    "backend/test_reach.py": 2,
    "backend/test_reader_promises.py": 10,
    "backend/test_readpage.py": 4,
    "backend/test_reasoning_fallback.py": 3,
    "backend/test_receipts.py": 3,
    "backend/test_referee.py": 3,
    "backend/test_retirement.py": 3,
    "backend/test_retrieve_count.py": 1,
    "backend/test_sayable.py": 2,
    "backend/test_schedule.py": 2,
    "backend/test_second_card.py": 11,
    "backend/test_second_card_suggest.py": 15,
    "backend/test_security_pc.py": 2,
    # LOWERED 2026-10-17 (self-improve diagnostic route, task-5): the old
    # `t_the_module_has_no_route_and_no_install` was six pins on the module's
    # source text; the module now HAS a read-only route, so that pin was
    # replaced with a behavioural stand-in-Handler check in the same file. The
    # six that remain are other tests' pins. The ratchet only turns DOWN.
    "backend/test_self_improve.py": 6,
    "backend/test_selftest_preflight.py": 2,
    "backend/test_shipped_modules.py": 5,
    "backend/test_skill_hub.py": 1,
    "backend/test_sky.py": 2,
    "backend/test_spending.py": 2,
    "backend/test_standby_schedule.py": 2,
    "backend/test_support_widget.py": 3,
    "backend/test_task_control.py": 1,
    "backend/test_tasks.py": 22,
    "backend/test_tellme.py": 6,
    "backend/test_token_store.py": 3,
    "backend/test_tool_schema.py": 1,
    "backend/test_tool_updates.py": 3,
    "backend/test_turn.py": 2,
    "backend/test_ui_control.py": 1,
    "backend/test_vault.py": 7,
    "backend/test_voice_strict.py": 2,
    "backend/test_voice_upgrades.py": 4,
    "backend/test_voices.py": 5,
    "backend/test_widget_sources.py": 3,
    "backend/test_widgets.py": 1,
    "backend/test_wiki.py": 5,
    "backend/test_work.py": 1,
    "backend/test_youtube.py": 2,
    "tools/check_plugins.py": 1,
}

#: git args that read history or a tree rather than the working directory.
GIT_READS = ("show", "log", "cat-file", "ls-tree", "rev-list", "blame", "diff",
             "diff-tree", "merge-base", "rev-parse")

#: subprocess entry points whose output can be source text.
SUBPROCESS = ("run", "Popen", "check_output", "check_call", "call")

#: methods on a source-text variable that count as a substring comparison.
SUBSTRING_METHODS = ("find", "count", "index", "startswith", "endswith")

#: re helpers whose second-and-later argument may be a source-text variable.
RE_CALLS = ("search", "match", "fullmatch", "findall", "finditer")


def _attr_chain(node) -> list[str]:
    """[names and attribute names] along a dotted expression, innermost first."""
    out: list[str] = []
    while isinstance(node, ast.Attribute):
        out.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        out.append(node.id)
    return out


def _py_names(tree: ast.AST) -> set[str]:
    """Names assigned from an expression that names a `.py` path.

    `SOURCE = HERE / "jarvis_widgets.py"` then `SOURCE.read_text()` is a source
    read; `FIXTURE / "cases.json"` is data, not source, and a pin on it is a
    fixture assertion (a legitimate test), not the disease this cures.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        if not any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and n.value.endswith(".py") for n in ast.walk(value)):
            continue
        for t in (getattr(node, "targets", None) or [getattr(node, "target", None)]):
            if isinstance(t, ast.Name):
                names.add(t.id)
    return names


def _is_source_read(node, py_names: set[str]) -> bool:
    """Is this Call an expression that returns the TEXT of a `.py` module?"""
    if not isinstance(node, ast.Call):
        return False
    chain = _attr_chain(node.func)
    if not chain:
        return False
    # inspect.getsource(...) is always a module's source.
    if chain[-1] == "getsource":
        return True
    # A read of a path that names a .py, directly or through a name that does.
    if chain[-1] in ("read_text", "read"):
        recv = node.func.value if isinstance(node.func, ast.Attribute) else node
        return any(
            (isinstance(n, ast.Constant) and isinstance(n.value, str)
             and n.value.endswith(".py"))
            or (isinstance(n, ast.Name) and n.id in py_names)
            for n in ast.walk(recv))
    # subprocess.run([... "git" ... "show" ...]) of a .py path.
    if chain[-1] in SUBPROCESS and any(n == "subprocess" for n in chain):
        words = [n.value for n in ast.walk(node)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
        return ("git" in words and any(w in GIT_READS for w in words)
                and (any(w.endswith(".py") for w in words)
                     or any(n in py_names for n in names)))
    return False


def _assigned_names(tree: ast.AST, py_names: set[str]) -> set[str]:
    """Every name assigned anywhere from a source read (module-wide, conservative)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            continue
        value = getattr(node, "value", None)
        if value is None:
            continue
        if not any(_is_source_read(n, py_names) for n in ast.walk(value)
                   if isinstance(n, ast.Call)):
            continue
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        for t in targets:
            if isinstance(t, ast.Name):
                names.add(t.id)
    return names


def _pins(tree: ast.AST, source_names: set[str]) -> list[int]:
    """The line numbers where a string is compared against a source-text name."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left = node.left
            if (isinstance(left, ast.Constant) and isinstance(left.value, str)
                    and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
                    and any(isinstance(c, ast.Name) and c.id in source_names
                            for c in node.comparators)):
                lines.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            recv, meth = node.func.value, node.func.attr
            if (meth in SUBSTRING_METHODS and isinstance(recv, ast.Name)
                    and recv.id in source_names
                    and any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                            for a in node.args)):
                lines.append(node.lineno)
            elif meth in RE_CALLS and any(
                    isinstance(a, ast.Name) and a.id in source_names
                    for a in node.args):
                lines.append(node.lineno)
    return sorted(set(lines))


def measure() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for pattern in GLOBS:
        for path in sorted(REPO.glob(pattern)):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"SKIP  {path.relative_to(REPO)}: could not be parsed ({exc})")
                continue
            names = _assigned_names(tree, _py_names(tree))
            if not names:
                continue
            hits = _pins(tree, names)
            if hits:
                found[str(path.relative_to(REPO)).replace("\\", "/")] = hits
    return found


def main(argv: list[str]) -> int:
    found = measure()
    total_now = sum(len(v) for v in found.values())
    total_was = sum(SOURCE_PIN_CEILING.get(f, 0) for f in found) + sum(
        n for f, n in SOURCE_PIN_CEILING.items() if f not in found)

    if "--measure" in argv:
        for f, hits in sorted(found.items()):
            print(f"{len(hits):4d}  {f}")
            for line in hits:
                print(f"        {f}:{line}")
        print(f"\n{len(found)} file(s), {total_now} source-text pin(s) - measured on "
              f"{REPO.name}")
        return 0

    failed = 0
    for f, hits in sorted(found.items()):
        ceiling = SOURCE_PIN_CEILING.get(f, 0)
        if len(hits) > ceiling:
            failed += 1
            print(f"FAIL  {f}: {len(hits)} source-text pin(s), ceiling {ceiling}")
            for line in hits:
                print(f"        {f}:{line}")
            print("      a pin on source TEXT goes red when the code is renamed or "
                  "improved and stays green when the behaviour is wrong. Call the real "
                  "function and assert on what it received, or walk `ast` nodes (a "
                  "docstring is an ast.Constant, never an ast.Call).")

    for f, ceiling in sorted(SOURCE_PIN_CEILING.items()):
        now = len(found.get(f, []))
        if now < ceiling:
            failed += 1
            print(f"FAIL  {f}: the recorded ceiling is {ceiling} but {now} is measured - "
                  f"the debt was paid, or the entry was raised")
            print("      lower the entry to the measurement: the ratchet only turns DOWN. "
                  "A ceiling left above the real count is how the next pin gets room to "
                  "slip in unnoticed.")

    if found:
        print(f"\n{len(found)} file(s) still pin source text (was {total_was}):")
        for f, hits in sorted(found.items()):
            print(f"  {f}: " + ", ".join(f"{f}:{n}" for n in hits))
    else:
        print("no file pins source text")

    if failed:
        print(f"\n{failed} file(s) above their ceiling")
        return 1
    print("\nevery source-text pin is at or below its recorded ceiling, and only "
          "outside text or `ast` may be asserted on")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
