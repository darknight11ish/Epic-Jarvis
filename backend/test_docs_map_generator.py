"""test_docs_map_generator.py - the fixed-point loop in tools/gen_docs_map.py.

WHY THIS EXISTS. `tools/gen_docs_map.py` writes the two numbers `docs/README.md`
states about `docs/`, and the page is INSIDE the directory it measures: writing a
figure changes the figure. A one-pass generator therefore writes a value that is
already wrong - it did, the first time it was run. The tool iterates to a fixed
point instead, and NOTHING ELSE CHECKS THAT: `tools/check_docs_map.py` allows a
tenth on the size, so a marginally wrong MB figure passes it silently. The loop is
the one load-bearing piece of that tool CI would not catch regressing.

WHAT IT DOES. It builds a SYNTHETIC tree in a temp directory - never the real
page, which is pointed away from with the tool's own `--docs` and `--readme` - and
then:
  1. the generator writes it, and the checker agrees with what it wrote;
  2. a second run changes nothing (idempotent);
  3. the tool's own `--check` passes.
Then THE CONTROL, which is the point of the whole file: ONE pass of the tool's own
formatting is applied to the stale page and shown NOT to be the fixed point - the
one-pass page fails `--check`. A test that passes against a one-pass generator
would not be testing the loop, so that assertion is checked first.
The real `docs/README.md` is hashed before and after and must be identical.
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REAL_PAGE = ROOT / "docs" / "README.md"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = _load("check_docs_map", ROOT / "tools" / "check_docs_map.py")
G = _load("gen_docs_map", ROOT / "tools" / "gen_docs_map.py")

#: The page as this repository writes it, with every spot the checker reads, and
#: STALE numbers whose digit count differs from the real ones - which is what
#: makes one pass insufficient.
PAGE = """# docs

There are **1 markdown documents** here, adding up to about **0.1 MB**. Neither
number is maintained by hand any more.

```powershell
(Get-ChildItem docs -Recurse -Filter *.md).Count                        # 1 documents
"{0:N0}" -f (Get-ChildItem docs -Recurse -Filter *.md |
  Measure-Object -Property Length -Sum).Sum                             # about 1 bytes
```

Re-measure the size as "around 0.1 MB" and re-measure it rather than trusting
the digits.
"""

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


def build(tmp: pathlib.Path):
    """A docs/ whose total size lands ON a rounding boundary."""
    docs = tmp / "docs"
    docs.mkdir(parents=True)
    for i in range(3):
        (docs / f"doc{i}.md").write_text("x" * (1000 + i), encoding="utf-8")
    page = docs / "README.md"
    page.write_text(PAGE, encoding="utf-8", newline="\n")
    # A whole megabyte plus 50,000 bytes is x.x5 MB: the boundary where writing
    # the MB figure can flip which way it rounds, and so change the page's own
    # length - the case this loop exists for.
    total = sum(p.stat().st_size for p in docs.rglob("*") if p.is_file())
    filler = (50_000 - (total % 1_000_000)) % 1_000_000
    if filler:
        (docs / "filler.md").write_text("y" * filler, encoding="utf-8")
    return docs, page


real_before = hashlib.sha256(REAL_PAGE.read_bytes()).hexdigest()
tmp = pathlib.Path(tempfile.mkdtemp())
try:
    docs, page = build(tmp)
    args = ["--docs", str(docs), "--readme", str(page)]
    files = C.documents(docs)
    count = len(files)
    others = sum(p.stat().st_size for p in files if p.resolve() != page.resolve())

    stale = page.read_text(encoding="utf-8")
    one_pass = G.render_page(stale, count, others, C)
    fixed = one_pass
    for _ in range(10):
        nxt = G.render_page(fixed, count, others, C)
        if nxt == fixed:
            break
        fixed = nxt

    check("THE CONTROL: one pass of the tool's own formatting is NOT the fixed point",
          one_pass != fixed, "one pass happened to be stable on this tree - the "
          "test would pass against a one-pass generator, so it is not testing the loop")

    code = G.main(args)
    check("the generator writes the page", code == 0, f"gen exit {code}")
    code = C.main(args)
    check("the checker agrees with what the generator wrote", code == 0, f"check exit {code}")
    code = G.main(args + ["--check"])
    check("a second run changes nothing (idempotent)", code == 0, f"--check exit {code}")

    # The control bites: put the ONE-PASS page back and the tool must reject it.
    page.write_text(one_pass, encoding="utf-8", newline="\n")
    code = G.main(args + ["--check"])
    check("the one-pass page FAILS the tool's own --check", code == 1, f"--check exit {code}")

    # And the page's numbers really sit on the boundary this loop is for.
    written = page.read_text(encoding="utf-8")
    mb = float(C.SIZE_SPOTS[0][1].search(fixed).group(1))
    total = others + len(fixed.encode("utf-8"))
    check("the tree's size is on a rounding boundary (x.x5 MB)",
          abs((total % 1_000_000) / 1_000_000 - 0.05) < 0.01, f"{(total % 1000000)}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

real_after = hashlib.sha256(REAL_PAGE.read_bytes()).hexdigest()
check("the repository's own docs/README.md was NOT touched", real_before == real_after,
      "the test changed the real page - the tool's --docs/--readme exist to avoid exactly this")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
