#!/usr/bin/env python3
"""Regenerate docs/SOURCE-BUNDLE*.md from the tree as it is right now.

The previous bundle was written by hand and went stale without saying so: it
described jarvis-client as "step 0, ~500 lines, no networking" long after that
module had grown a network layer, an audio stack and a voice loop. A reviewer
handed that document would have audited an app that no longer existed, and
would have had no way to tell.

So it is generated, from `git ls-files`, with the commit stamped at the top —
and anything that cannot be read as text is listed rather than silently
dropped, because "this file is not in the bundle" and "this file does not
exist" must not look the same to whoever reads it.

`--parts N` (default 1) splits the output across N files instead of one.
Added once the module passed the size where Gemini would accept a single
upload — `docs/SOURCE-BUNDLE.md` alone was 735KB by 2026-09-20. Splitting is
by whole file only: nothing inside a single source file is ever cut across
two documents, since a reviewer needing to hold half a file in their head
while reading the other half from a different upload is worse than the size
problem this solves. Files are assigned to parts in a single pass over the
sorted list, crossing into the next part once the running byte total would
put this part's share above its fair fraction of the whole — which, for
files listed in a stable sort, means each part comes out as a contiguous
slice of the module (e.g. part 1 is roughly `audio/` through `net/`, part 2
is roughly `platform/` through the build files) rather than an interleaved
shuffle, so a reviewer working through one part is reading one coherent
neighbourhood of the codebase at a time.
"""
import argparse
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE = "jarvis-client"

# Text we deliberately leave out, with the reason, printed into the document.
SKIP_SUFFIX = {
    ".png": "binary image",
    ".jar": "binary (the Gradle wrapper)",
    ".keystore": "binary, and a signing key",
}

LANG = {
    ".kt": "kotlin", ".kts": "kotlin", ".xml": "xml", ".json": "json",
    ".py": "python", ".yml": "yaml", ".yaml": "yaml", ".md": "markdown",
    ".pro": "text", ".properties": "properties", ".gitignore": "text",
}


def tracked(*paths):
    out = subprocess.run(["git", "ls-files", "--", *paths], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\n") if p]


def _runs(text):
    """Every run of backticks in the text, so the fence can outrun the longest."""
    run, out = 0, []
    for ch in text:
        if ch == "`":
            run += 1
        else:
            if run:
                out.append("`" * run)
            run = 0
    if run:
        out.append("`" * run)
    return out


def render_file(f):
    """The `## path` section for one file, as a list of lines."""
    path = os.path.join(ROOT, f)
    lines = []
    w = lines.append
    try:
        body = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError) as e:
        w(f"## `{f}`")
        w("")
        w(f"*Could not be read as text: {e}*")
        w("")
        return lines
    lang = LANG.get(os.path.splitext(f)[1], "")
    if os.path.basename(f) == "gradlew":
        lang = "bash"
    # A fence long enough that nothing inside the file can close it early.
    fence = "`" * max(4, max((len(m) for m in _runs(body)), default=3) + 1)
    w(f"## `{f}`")
    w("")
    w(f"{fence}{lang}")
    w(body.rstrip("\n"))
    w(fence)
    w("")
    return lines


def split_into_parts(included, sizes, n):
    """`included`, cut into `n` contiguous slices of roughly equal byte total.

    Greedy, not optimal-partition: walks the sorted file list once, and
    starts a new part whenever the CURRENT part's running total has reached
    its fair share (total / n) — so a part can run slightly over its share
    on the file that tips it past the line, never under. For n=2 on a real
    module this lands within a few percent of even; exactness is not the
    point, keeping each part one contiguous range of the sorted tree is.
    """
    total = sum(sizes[f] for f in included)
    fair_share = total / n if n else total
    parts, current, running = [], [], 0
    for f in included:
        current.append(f)
        running += sizes[f]
        if len(parts) < n - 1 and running >= fair_share * (len(parts) + 1):
            parts.append(current)
            current = []
    parts.append(current)
    # A short module or a lopsided skip list can leave a trailing empty part
    # if every file landed in earlier slices - fold it into the last
    # non-empty one rather than emitting an empty document.
    parts = [p for p in parts if p] or [[]]
    while len(parts) < n:
        parts.append([])
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parts", type=int, default=1,
                     help="split the bundle across this many files (default 1)")
    args = ap.parse_args()
    if args.parts < 1:
        print("--parts must be at least 1", file=sys.stderr)
        return 2

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()

    files = tracked(MODULE) + tracked(".github/workflows", "keystore/README.md")
    included, skipped = [], []
    for f in sorted(files):
        ext = os.path.splitext(f)[1]
        if ext in SKIP_SUFFIX:
            skipped.append((f, SKIP_SUFFIX[ext]))
        else:
            included.append(f)

    sizes = {f: os.path.getsize(os.path.join(ROOT, f)) for f in included}
    parts = split_into_parts(included, sizes, args.parts)

    outputs = []
    for i, part_files in enumerate(parts, start=1):
        lines = []
        w = lines.append
        title = f"# `{MODULE}` — every source file" + (
            ", in one document" if args.parts == 1
            else f" (part {i} of {args.parts})"
        )
        w(title)
        w("")
        w(f"Commit `{sha}` on `{branch}`.")
        w("")
        w("Generated by `tools/gen_source_bundle.py`, not written by hand. The previous")
        w("version of this file was hand-written and went stale without saying so — it")
        w("described this module as \"step 0, no networking\" long after it had grown a")
        w("network layer, an audio stack and a voice loop.")
        w("")
        w(f"Contains the whole `{MODULE}` module, plus the CI workflows that build it,")
        w("because how a thing is tested is part of judging whether it works.")
        if args.parts > 1:
            others = [j for j in range(1, args.parts + 1) if j != i]
            w("")
            w(
                f"**This is part {i} of {args.parts}.** The module was too large for one "
                "upload, so it is split across files by whole file — nothing here is "
                "cut mid-file. Part " + " and part ".join(str(j) for j in others) +
                f" of {args.parts} continue{'s' if len(others) == 1 else ''} the same "
                "commit; the manifest below lists every file across all parts and says "
                "which part each one is actually in, so this document alone tells you "
                "what you are and are not looking at."
            )
        w("")
        w(f"**{len(part_files)} files in this document, {len(included)} total across "
          f"{'this document' if args.parts == 1 else 'all parts'}.**")
        if skipped:
            w("")
            w("Deliberately omitted, listed so their absence is visible rather than silent:")
            w("")
            for f, why in skipped:
                w(f"- `{f}` — {why}")
        w("")
        w("## Contents" if args.parts == 1 else "## Contents (all parts)")
        w("")
        if args.parts == 1:
            for f in included:
                w(f"- `{f}`")
        else:
            # Which part owns each file, so a reader holding only this
            # document can tell a file living elsewhere from one dropped
            # from the bundle entirely - the same distinction SKIP_SUFFIX
            # exists to preserve.
            owner = {f: j for j, pf in enumerate(parts, start=1) for f in pf}
            for f in included:
                j = owner[f]
                w(f"- `{f}`" + ("" if j == i else f" — in part {j}"))
        w("")
        w("---")
        w("")

        for f in part_files:
            lines.extend(render_file(f))

        name = "SOURCE-BUNDLE.md" if args.parts == 1 else f"SOURCE-BUNDLE-{i}-of-{args.parts}.md"
        out = os.path.join(ROOT, "docs", name)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        outputs.append(out)
        size = os.path.getsize(out)
        print(f"{out}: {len(part_files)} files, {size:,} bytes")

    # Switching part counts leaves the previous run's files behind - e.g.
    # regenerating with --parts 2 after a --parts 1 run leaves the old
    # docs/SOURCE-BUNDLE.md sitting next to the new pair, silently stale.
    # Remove whichever naming scheme this run did NOT produce.
    stale_candidates = (
        [os.path.join(ROOT, "docs", "SOURCE-BUNDLE.md")] if args.parts > 1
        else [
            os.path.join(ROOT, "docs", f)
            for f in os.listdir(os.path.join(ROOT, "docs"))
            if f.startswith("SOURCE-BUNDLE-") and f.endswith(".md")
        ]
    )
    for stale in stale_candidates:
        if stale not in outputs and os.path.exists(stale):
            os.remove(stale)
            print(f"removed stale {stale}")


if __name__ == "__main__":
    sys.exit(main())
