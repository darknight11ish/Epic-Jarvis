"""test_about_claims.py - the six claims totals in docs/ABOUT-JARVIS.md are generated.

WHY THIS EXISTS. `docs/ABOUT-JARVIS.md` quotes the totals in `docs/CLAIMS.tsv` in
SIX places, and every pull request that moves a claim had to hand-edit all six.
Three consecutive PRs did (`b24634c77`, `f75b34e1f`, `9d70ec02b`), and the last
one only exists because CI caught the page stale: `backend/test_claims.py` found
269 rows / 257 built while the page still printed 268 / 256. The owner's ruling of
2026-11-15 08:35 (Q4) is that those six numbers are generated, the way the two
figures in `docs/README.md` already are (`tools/gen_docs_map.py` writes them,
`tools/check_docs_map.py` is the gate).

WHAT THIS PROVES, in the order it checks it:

  1. ONE TABLE, NOT TWO. `tools/gen_about_claims.py` gets its six statements from
     `backend/test_claims.py`'s own `ABOUT_COUNT_SPOTS` - the table the required
     `backend` job already uses to fail a stale page - and its totals from
     `tools/check_claims.py`'s own register reader. Neither is copied here or
     there, so a second copy cannot drift from the gate that judges the page.
  2. THE REAL PAGE MATCHES THE REGISTER at all six statements, the three states
     add up to the rows, both readers count the register the same way, and the
     section 6 line really is the checker's summary sentence word for word.
  3. THE GENERATOR IS IDEMPOTENT on a copy of the page: a write changes no byte,
     and `--check` is green straight after it. The real page is never written by
     this suite - every write is pointed at a temporary copy.
  4. THE BITE, once per statement. ONE number is hand-changed on a copy, the way
     a person editing the page would; `--check` must exit 1 and name the line and
     the number, and the generator must put the page back byte for byte. All six
     are tested, so "five of six are generated" cannot pass as "the numbers are
     generated".
  5. THE REGISTER FOLLOWS. A copy of the register with one more `built` row moves
     the totals by exactly one, and the generator writes the new numbers into all
     six statements - with no statement left carrying the old row count. This is
     the property that makes the next claim change one command instead of a hand
     edit CI has to catch.
  6. A PAGE REWORDED PAST THE GATE'S PATTERN IS REFUSED, in both modes, and
     nothing is written: a number this tool can no longer see is not a number it
     may quietly leave alone.
  7. The repository's own page and register are hashed before and after and must
     be identical.

Needs nothing from the owner's PC, no network and no third-party package: the
generator, the gate and the checker are standard library only, and so is this.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PAGE = ROOT / "docs" / "ABOUT-JARVIS.md"
REGISTER = ROOT / "docs" / "CLAIMS.tsv"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: pathlib.Path) -> str:
    """The file's own bytes as text: no newline translation, nothing rewritten."""
    return path.open(encoding="utf-8", newline="").read()


G = _load("gen_about_claims", ROOT / "tools" / "gen_about_claims.py")
GATE = G.gate()

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("ok    " + name)
    else:
        failed += 1
        print("FAIL  " + name)
        if detail:
            print("      " + str(detail))


def run(args):
    """(exit code, everything it printed) for one generator invocation."""
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = G.main(args)
    return code, captured.getvalue()


page_before, register_before = sha(PAGE), sha(REGISTER)
page_text = read(PAGE)
values = G.counts(REGISTER)
#: The page the register says it should be. On a healthy tree this is the page
#: itself; the battery below compares against THIS rather than the file's current
#: bytes, so a stale page fails the two checks that say so and does not cascade
#: a third failure into every place the generator would have restored it.
canonical = G.render_page(page_text, values, GATE)


# --------------------------------------------------------------------------
#   1. One table, not two - the definitions are the gate's and the checker's
# --------------------------------------------------------------------------

check("the six statements come from backend/test_claims.py, not a copy in the tool",
      pathlib.Path(GATE.__file__).resolve() == (ROOT / "backend" / "test_claims.py").resolve(),
      str(GATE.__file__))
check("the totals come from tools/check_claims.py's own register reader",
      pathlib.Path(G.checker().__file__).resolve()
      == (ROOT / "tools" / "check_claims.py").resolve(),
      str(G.checker().__file__))

spot_names = [name for name, _pattern, _fields in GATE.ABOUT_COUNT_SPOTS]
check("the page's totals live in six statements, which is the number the ruling names",
      len(spot_names) == 6, str(spot_names))

found = G.statements(page_text, GATE)
check("every one of those six statements is on the page, once and in order",
      [entry["name"] for entry in found] == spot_names,
      f"found {[entry['name'] for entry in found]}")


# --------------------------------------------------------------------------
#   2. The real page matches the register
# --------------------------------------------------------------------------

diffs, _found = G.problems(page_text, values, GATE)
check("the page states the register's totals at all six statements",
      not diffs, "\n".join(diffs))
check("the register's three states add up to its rows",
      values["built"] + values["open"] + values["unverifiable"] == values["rows"],
      str(values))
check("the checker's reader and the gate's reader count the register the same way",
      values == G.gate_counts(REGISTER, GATE),
      f"{values} against {G.gate_counts(REGISTER, GATE)}")

summary = (f"{values['rows']} claim(s) checked against the code: {values['built']} built, "
           f"{values['open']} still open, {values['unverifiable']} unverifiable "
           f"(the reason is in each row).")
check("the page quotes the checker's own summary line word for word",
      summary in page_text, summary)

code, out = run(["--check"])
check("the generator's --check passes on the real page", code == 0, out)


# --------------------------------------------------------------------------
#   3-6. Idempotence, the bite, a changed register, a reworded page - all on copies
# --------------------------------------------------------------------------

tmp = pathlib.Path(tempfile.mkdtemp(prefix="about-claims-"))
try:
    copy = tmp / "ABOUT-JARVIS.md"
    shutil.copyfile(PAGE, copy)

    code, out = run(["--page", str(copy)])
    check("a write of the page's own numbers leaves the register's version byte for byte",
          code == 0 and copy.read_bytes() == canonical.encode("utf-8"), out)
    code, out = run(["--page", str(copy), "--check"])
    check("... and --check is green straight after it (idempotent)", code == 0, out)

    # 4. THE BITE, once per statement: one hand-changed number, on a copy.
    for entry in found:
        start, end = entry["spans"][0]
        field = entry["fields"][0]
        bumped = str(int(page_text[start:end]) + 1)
        hand = page_text[:start] + bumped + page_text[end:]
        check(f"THE BITE ({entry['name']}): one number is hand-changed, and only one",
              hand != page_text and hand.count("\n") == page_text.count("\n"))
        copy.write_bytes(hand.encode("utf-8"))
        code, out = run(["--page", str(copy), "--check"])
        check(f"THE BITE ({entry['name']}): --check fails and names it",
              code == 1 and f"line {entry['line']}" in out
              and f"{field}={bumped}" in out and f"holds {field}={values[field]}" in out,
              f"exit {code}\n{out}")
        code, out = run(["--page", str(copy)])
        check(f"THE BITE ({entry['name']}): the generator puts the page back byte for byte",
              code == 0 and copy.read_bytes() == canonical.encode("utf-8"),
              f"exit {code}\n{out}")

    # 5. THE REGISTER FOLLOWS: one more built row, and the page is rewritten.
    register_text = read(REGISTER)
    if not register_text.endswith("\n"):
        register_text += "\n"
    grown = tmp / "CLAIMS.tsv"
    grown.write_text(
        register_text
        + "X-about-claims\tthe row this test invented to move the totals\t"
          "file:README.md\tbuilt\tREADME.md:1\n",
        encoding="utf-8", newline="")
    moved = G.counts(grown)
    check("one more built row moves the totals by exactly one, on the right state",
          (moved["rows"], moved["built"], moved["open"], moved["unverifiable"])
          == (values["rows"] + 1, values["built"] + 1, values["open"],
              values["unverifiable"]), str(moved))
    check("... and the gate's own reader moves with it",
          G.gate_counts(grown, GATE) == moved, str(G.gate_counts(grown, GATE)))

    copy.write_bytes(PAGE.read_bytes())
    code, out = run(["--page", str(copy), "--register", str(grown)])
    check("the generator rewrites the page from the changed register", code == 0, out)
    grown_page = read(copy)
    new_diffs, new_found = G.problems(grown_page, moved, GATE)
    check("... and the page states the new totals at all six statements",
          not new_diffs, "\n".join(new_diffs))
    stale = [entry["name"] for entry in new_found
             if "rows" in entry["fields"]
             and entry["values"][entry["fields"].index("rows")] == values["rows"]]
    check("... with no statement left carrying the old row count", not stale, str(stale))
    check("... and the quoted checker line follows too",
          f"{moved['rows']} claim(s) checked against the code: "
          f"{moved['built']} built, {moved['open']} still open, "
          f"{moved['unverifiable']} unverifiable" in grown_page,
          "no line on the rewritten page quotes the checker")

    # 6. A page reworded past the gate's pattern cannot be written - loudly.
    entry = next(item for item in found
                 if item["name"] == "the quoted output of the checker itself")
    start, end = entry["span"]
    statement = page_text[start:end]
    reworded = statement.replace("checked", "tallied")
    check("the reworded page really is reworded in the statement this tool reads",
          reworded != statement)
    copy.write_bytes((page_text[:start] + reworded + page_text[end:]).encode("utf-8"))
    code, out = run(["--page", str(copy), "--check"])
    check("a page reworded past the gate's pattern is refused, not quietly passed",
          code == 1, f"exit {code}\n{out}")
    check("... and it names the statement it can no longer see",
          "nothing on the page states" in out and entry["name"] in out, out)
    before = sha(copy)
    code, out = run(["--page", str(copy)])
    check("... in write mode too, and it writes nothing",
          code == 1 and sha(copy) == before, f"exit {code}\n{out}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
#   7. The repository's own files are unchanged
# --------------------------------------------------------------------------

check("the repository's own docs/ABOUT-JARVIS.md was NOT touched",
      sha(PAGE) == page_before,
      "the suite changed the real page - every write is meant to go to a copy")
check("the repository's own docs/CLAIMS.tsv was NOT touched",
      sha(REGISTER) == register_before)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
