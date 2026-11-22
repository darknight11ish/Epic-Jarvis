"""test_update_progress_shape.py - the two ends of one wire, checked against
each other.

    python3 backend/test_update_progress_shape.py

`scripts/apply-patches.ps1` prints one line per failing test suite, and
`jarvis-desktop/src-tauri/src/update_progress.rs` reads those lines to tell the
owner where the update has got to. The two only work if they agree about the
SHAPE of that line, and until now nothing checked that they did.

**Why this exists (Hazard 4, 2026-10-16).** Every call to `apply-patches.ps1` in
`.github/workflows/ci.yml` passes `-SkipTests` (lines 912, 941, 1060, 1212,
1229), so the required `powershell-5` job proves the script parses and runs and
**never executes the test loop**. `FAIL <name> - <reason>` was therefore covered
by nothing at all: an edit to either side would ship green and the owner's
update screen would quietly stop showing the reason.

This is the project's recurring shape - the two sides of a contract, each tested
alone and never against each other - so the fix is a test that reads BOTH files
and holds them to the same shape. It runs in the required `backend` job through
`backend/run_suites.py`, in milliseconds, without running 335 suites.

No pytest, no network, no model, no PowerShell, no cargo.
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

PS1 = REPO / "scripts" / "apply-patches.ps1"
RUST = REPO / "jarvis-desktop" / "src-tauri" / "src" / "update_progress.rs"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n      {detail}" if not cond else ""))
    return bool(cond)


def _must(pattern, text, what):
    """The one match, or a failure that says the extraction itself broke.

    Every check below is only as good as its own regex. If one stops matching -
    because the code moved, or was reworded - the check must FAIL rather than
    quietly pass on an empty string. That is the control this file needs most,
    and it is why `_must` is used everywhere instead of `re.search(...).group(1)`
    inline.
    """
    found = re.search(pattern, text, re.S)
    if not found:
        raise AssertionError(
            f"could not read {what} out of {pattern!r} - the extraction this "
            f"check is built on no longer matches, so the check proves nothing")
    return found


def _script_separator():
    """The separator the .ps1 puts between a suite's name and its reason."""
    text = PS1.read_text(encoding="utf-8-sig")
    return _must(r'Bad "\$\(\$t\.Name\)([^"]*)\$why"', text,
                 "the failing-suite line the script prints").group(1)


def _parser_separator():
    """The separator the Rust splits a FAILING-SUITE line's name from its reason.

    Deliberately NOT "the first `.split_once(...)` in the file". The reader now
    handles TWO wire shapes: the bounded proof's `PROOF: Step N/M - <phase> -
    x of y` step line (whose count it splits on ` of `) and the `ok`/`FAIL`/
    `skip` item lines the failing suite's reason rides on. The proof's split
    appears EARLIER in the file, so a first-match regex reads the wrong wire -
    it reports a disagreement that does not exist (this is exactly how the
    check went red on 2026-11-21, when the proof reader landed) and would miss
    a real one the day the item separator moved. The item parser's own split is
    the one taken on `rest`, the line's body after `ok `/`FAIL `/`skip `.
    """
    rust = RUST.read_text(encoding="utf-8")
    return _must(r'rest\.split_once\("([^"]*)"\)', rust,
                 "the separator the parser splits a failing-suite line on").group(1)


def t_the_script_prints_the_reason_after_a_separator():
    """The .ps1 puts `<name><sep><reason>` on the failing suite's line."""
    text = PS1.read_text(encoding="utf-8-sig")
    separator = _script_separator()
    check("the failing-suite line carries a reason, not just the suite name",
          separator.strip() != "", repr(separator))
    check("Get-FirstFailureReason is still the function that makes it",
          "function Get-FirstFailureReason($out)" in text)
    check("the parser's separator was read out of the Rust at all",
          _parser_separator() != "", repr(_parser_separator()))


def t_the_two_ends_agree_about_the_separator():
    printed = _script_separator()
    parsed = _parser_separator()
    check(f"the script prints {printed!r} and the parser splits on {parsed!r}: the same",
          printed == parsed,
          f"the script prints {printed!r}, the parser splits on {parsed!r} - a "
          f"failing suite's reason would reach the screen glued to its name, or "
          f"be dropped, and NOTHING ELSE IN CI WOULD NOTICE")


def t_a_proof_step_line_is_never_read_as_a_suite():
    """The bounded proof added a second line shape; the suite wire must stay apart.

    `tools/update_backend.py` prints `PROOF: Step N/M - <phase> - x of y` for the
    app path's bounded proof, and that line carries the SAME ` - ` separator the
    failing suite's line does. So the parser must consume a proof line FIRST, by
    its own prefix, and return: a proof line must never be counted as a check,
    named as a failed one, or have its words split as a failure's reason. This
    is what keeps the guarantee this whole file exists for true under the new
    output - and it is why `_parser_separator` reads the ITEM branch's split
    rather than the proof's count split (` of `) earlier in the same file.
    """
    rust = RUST.read_text(encoding="utf-8")
    check("the proof line has its own reader", "pub fn proof_line" in rust)
    check("... it is told apart from an item line by its own prefix",
          'strip_prefix("PROOF: Step ")' in rust)
    proof_at = rust.find("if let Some(line) = proof_line(trimmed)")
    item_at = rust.find('let body = ["ok ", "FAIL ", "skip "]')
    check("... and a proof line is consumed before an item line is classified",
          proof_at != -1 and item_at != -1 and proof_at < item_at,
          f"the proof branch is at {proof_at}, the item branch at {item_at} - a "
          f"PROOF line could reach the item branch, and its ` - ` words would be "
          f"read as a failed suite's name and reason")
    check("... and it returns, so the item branch never reads a proof line",
          re.search(r"if let Some\(line\) = proof_line\(trimmed\) \{\s*"
                    r"p\.proof = Some\(line\);\s*return;", rust) is not None,
          "the proof branch no longer returns before the item classifier - a "
          "PROOF line would fall through and its ` - ` separator would be read "
          "as the failing-suite separator")


def t_a_suite_the_script_runs_is_a_name_the_parser_counts():
    """The name side of the same contract.

    The parser counts an item only when it names a file (see its own rule), and
    the script finds its suites with a `-Filter` glob. If those two ever stop
    agreeing, every failing suite silently vanishes from the update screen -
    which is the one thing this whole feature exists to prevent.
    """
    text = PS1.read_text(encoding="utf-8-sig")
    glob = _must(r"\$tests = @\(Get-ChildItem[^\n]*-Filter '([^']+)'", text,
                 "the glob the script finds its suites with").group(1)
    rust = RUST.read_text(encoding="utf-8")
    extensions = re.findall(r'name\.ends_with\("(\.[a-z]+)"\)', rust)
    check("the parser's accepted extensions were read out of the Rust",
          extensions != [], f"read {extensions}")
    # A name the glob can produce: `test_whatever.py`.
    example = glob.replace("*", "thing")
    check(f"a suite the script runs ({example}) is a name the parser counts",
          any(example.endswith(ext) for ext in extensions),
          f"the script runs {glob}, so a suite is named like {example}, and the "
          f"parser accepts only {extensions}")
    check("... and the parser's no-spaces half accepts it too",
          "split_whitespace().count() != 1" in rust,
          "the parser no longer checks that an item name is one word")


def t_a_reason_can_never_break_the_line_it_rides_on():
    """The line is one line, and the parser reads one line.

    The reason is a suite's own words, which can be a two-thousand character
    list of file names - so the script caps it and joins it with ` - ` rather
    than letting a newline through, and `take_lines` in the Rust hands over
    COMPLETE lines only. A reason containing a newline would arrive as a
    second line, and the parser would read it as another item.
    """
    text = PS1.read_text(encoding="utf-8-sig")
    cap = _must(r"\$script:WhyMax\s*=\s*(\d+)", text,
                "the cap the script puts on a reason").group(1)
    check("the reason is capped", int(cap) > 0 and int(cap) <= 400, cap)
    check("... and the cap is applied before the line is printed",
          "Substring(0, $script:WhyMax)" in text)
    body = _must(r"function Get-FirstFailureReason\(\$out\) \{(.*?)\n\}", text,
                 "Get-FirstFailureReason's body").group(1)
    check("the reason is built from single lines, never a whole block",
          "-split" in body and "Trim()" in body,
          "the function no longer splits the output into lines")
    rust = RUST.read_text(encoding="utf-8")
    check("the Rust still hands over complete lines only",
          "pub fn take_lines" in rust and "b'\\n'" in rust)


def t_the_script_still_has_a_reason_to_print():
    """CONTROL: the function must be reachable from the failing branch.

    Without this, deleting the call would leave every check above passing on a
    function nobody calls - the same "tested alone, never against each other"
    mistake one level down.
    """
    text = PS1.read_text(encoding="utf-8-sig")
    check("the failing branch asks for the reason",
          re.search(r"\$why = Get-FirstFailureReason \$txt", text) is not None)
    check("... and prints it when there is one, the bare name when there is not",
          re.search(r'if \(\$why\) \{ Bad "\$\(\$t\.Name\) - \$why" \} else \{ Bad \$t\.Name \}',
                    text) is not None)


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
