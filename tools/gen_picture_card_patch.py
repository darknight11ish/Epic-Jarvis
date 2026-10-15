"""Write picture-card.patch with the real context lines taken from jarvis_hud.py.

    py -3 tools/gen_picture_card_patch.py            write the patch
    py -3 tools/gen_picture_card_patch.py --check    is the committed patch this one?

Building the hunk by hand is how patches silently drift; this reads the anchor
block out of the file and writes the counts from what it actually found.

WHERE IT INSERTS, AND WHY THAT MOVED ON 2026-10-11 (this script was not updated
at the time; it is now). The first version anchored the block inside
progress.patch's `try: import jarvis_progress` chain - which is what the old
comment's "here, before anything listens, like progress above" describes. That
placement is the one thing this patch must NOT do: every install block in that
chain writes into the lines the NEXT patch's hunk needs for context, so a block
added in the middle of it leaves the following patch unmatchable. Measured
2026-10-11: anchored there, with topics.patch's banner underneath it, the whole
apply run was refused.

So the patch moved to the owner's own lines, immediately before the socket is
built, and its comment was rewritten to say why. This script kept emitting the
REJECTED placement for three days. That mattered the moment the script was moved
into `tools/` beside the other generators - `tools/gen_tasks_patch.py` and its
neighbours are things people run - because running it would have put the broken
hunk back over the good one, and the next `apply-patches.ps1` would then have
refused a patch that had worked for days. It now reads the same anchor the
committed patch uses and prints its counts from the file, and `--check` is wired
into CI beside the other generators so the two cannot drift apart in silence.

WHAT `--check` COMPARES, AND WHY THE LINE NUMBER IS NOT PART OF IT
(2026-10-14). `--check` used to compare bytes. That made the hunk header's LINE
NUMBER load-bearing, and it is not: `git apply` finds a hunk by matching its
context contiguously, so the number is advisory. Measured on 4d1812b7 - the
committed patch says `@@ -6591,3 +6591,25 @@` and this script derives
`@@ -6629,3 +6629,25 @@`, because jarvis_hud.py has since moved 38 lines. Both
files are 29 lines long and line 3 is the ONLY line that differs. The full
143-patch rehearsal passes with the stale number, which is the proof it applies.

A byte-exact check on an advisory number is not a check on anything the owner
cares about - it went red on EVERY branch, including branches that never touch
this patch, and held up ten pull requests for a line shift `git apply` ignores.
It also imposed a maintenance burden the repository never asked for: every
change to jarvis_hud.py would have meant regenerating this patch.

So `--check` is SEMANTIC now. It compares what actually decides whether the
patch does the right thing, and what would have caught the real bug this script
was fixed for (it emitted the REJECTED placement for three days):

  * WHERE the block goes      - the same host line number in both;
  * the lines it sits between - the before-context and after-context, line for line;
  * the lines it adds         - all 22 of them, line for line;
  * the header's own counts   - old count == the context lines present, and
                                new count == old + the added lines present.

The hunk header's line number is reported when it is stale (so the drift is
still visible) and is not a failure. Everything else still fails the check, and
`tools/../backend/test_picture_card.py` proves that with mutations of each kind.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
HUD = HERE / "jarvis-backend" / "jarvis_hud.py"
OUT = HERE / "backend" / "picture-card.patch"

#: The line the block is inserted BEFORE: the owner's own statement that builds
#: the socket. Deliberately not another patch's block - that is the whole point
#: of the placement. If this line ever moves, `lines.index()` below raises and
#: nothing is written, which is the wanted failure: a patch anchored on a line
#: that is gone would be a guess.
ANCHOR = "    httpd = ThreadingHTTPServer((bind, HUD_PORT), Handler)"

#: Real context lines taken from the file, before the insertion point and after.
BEFORE, AFTER = 2, 1

ADDED = [
    "    # picture-card.patch (\"Which card draws the pictures\", the owner's decision of",
    "    # 2026-10-10; docs/PICTURE-CARDS-DESIGN.md, JARVIS-API section 124): GET and POST",
    "    # /api/picture-card. The three ways of running a picture-maker beside the everyday",
    "    # chat - pictures on the 12 GB card with the chat stepping aside, pictures on the",
    "    # 12 GB card with the chat moved to the 8 GB card, small pictures on the 8 GB card",
    "    # with the chat left alone - each its own switch, all off until the owner turns one",
    "    # on. It draws nothing itself (asking for a picture is jarvis_pictures.py's route,",
    "    # section 123) and it starts nothing: D:\\Jarvis\\ImageGen\\Start-Pictures.ps1 starts",
    "    # the picture-maker on the right card, reading these settings. Wrapped round Handler",
    "    # here, just before the main socket is built, and on the OWNER's own lines rather",
    "    # than on another patch's block: every install block above writes into the chain",
    "    # that ends at `# Before the main socket`, so a block added in the middle of it",
    "    # leaves the next patch's hunk without its context (measured 2026-10-11 - this one",
    "    # was anchored on progress.patch's block with topics.patch's banner, a patch that",
    "    # runs after it, and the whole run would have been refused).",
    "    try:",
    "        import jarvis_picture_card",
    "        print(jarvis_picture_card.install(Handler, origin_ok=_origin_ok,",
    "                                          token_ok=_token_ok, read_body=_read_body))",
    "    except Exception as exc:",
    "        print(f\"  picture-card NOT ON ({type(exc).__name__}) - the three ways of making pictures are off\")",
    "        print(\"             until jarvis_picture_card.py is back: run apply-patches.ps1 again\")",
]


def build(lines):
    """(patch bytes, header) for `lines`, or (None, sentence saying why not)."""
    if ANCHOR not in lines:
        return None, ("the anchor line is not in jarvis_hud.py any more, so this script will "
                      "not guess where the block goes:\n    " + ANCHOR)
    idx = lines.index(ANCHOR)
    start = idx - BEFORE
    if start < 0:
        return None, "the anchor is too near the top of the file to take context lines"
    before = lines[start:idx]
    after = lines[idx:idx + AFTER]
    old_count = len(before) + len(after)
    new_count = old_count + len(ADDED)
    header = "@@ -{0},{1} +{0},{2} @@".format(start + 1, old_count, new_count)
    body = ["--- a/jarvis_hud.py", "+++ b/jarvis_hud.py", header]
    body.extend(" " + line for line in before)
    body.extend("+" + line for line in ADDED)
    body.extend(" " + line for line in after)
    # LF, not CRLF: this repository is LF everywhere (.gitattributes says so), and
    # a CRLF patch does not apply against LF files.
    return ("\n".join(body) + "\n").encode("utf-8"), header


def first_difference(have, want):
    """Where two byte strings first disagree: (line number, committed, generated)."""
    a = have.split(b"\n")
    b = want.split(b"\n")
    for n in range(max(len(a), len(b))):
        if n >= len(a):
            return n + 1, b"<nothing - the file is shorter>", b[n]
        if n >= len(b):
            return n + 1, a[n], b"<nothing - the file is longer>"
        if a[n] != b[n]:
            return n + 1, a[n], b[n]
    return None, None, None


#: `@@ -old_start,old_count +new_start,new_count @@`. The trailing section
#: heading (git writes `@@ ... @@ def foo():`) is optional and is kept out of the
#: numbers so this script's own bare headers and a hand-edited one both parse.
HUNK_HEADER = re.compile(rb"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@[ \t]*(.*)$")


def semantify(patch):
    """The parts of `patch` that decide whether it does the right thing.

    Returns (shape, why) where shape is None when the patch cannot be read as
    this script's shape - a missing/renamed file line, more than one hunk, a
    header that is not `@@ -a,b +c,d @@`, a body line that is neither context,
    addition nor deletion, or counts that disagree with the lines present.
    `why` is then the sentence saying which of those it was.

    `body` keeps every line in the order it appears, each tagged with whether it
    is context or an addition. The ORDER matters and is compared: a context line
    swapped with its neighbour, or with an added line, is a different placement
    even though the same lines are present and the counts are unchanged.
    """
    lines = patch.split(b"\n")
    while lines and lines[-1] == b"":
        lines.pop()          # the trailing newline of the file, not a body line
    if len(lines) < 3:
        return None, "the patch is {0} line(s) long, which is not a hunk".format(len(lines))
    if lines[0] != b"--- a/jarvis_hud.py" or lines[1] != b"+++ b/jarvis_hud.py":
        return None, ("the patch does not start `--- a/jarvis_hud.py` / "
                      "`+++ b/jarvis_hud.py`: {0!r}".format(b" | ".join(lines[:2])[:120]))
    m = HUNK_HEADER.match(lines[2])
    if m is None:
        return None, "the hunk header is not `@@ -a,b +c,d @@`: {0!r}".format(lines[2][:120])
    old_start, old_count, new_start, new_count = (int(g) for g in m.groups()[:4])
    body, context, added, removed = [], [], [], []
    for line in lines[3:]:
        if line.startswith(b"+"):
            added.append(line[1:])
            body.append((b"+", line[1:]))
        elif line.startswith(b"-"):
            removed.append(line[1:])
            body.append((b"-", line[1:]))
        elif line.startswith(b" "):
            context.append(line[1:])
            body.append((b" ", line[1:]))
        else:
            return None, ("a body line starts with neither ' ', '+' nor '-': "
                          "{0!r}".format(line[:120]))
    if removed:
        return None, ("the patch removes {0} line(s); this script only ever adds a "
                      "block".format(len(removed)))
    if old_count != len(context):
        return None, ("the header says {0} old line(s) but {1} context line(s) are "
                      "present".format(old_count, len(context)))
    if new_count != old_count + len(added):
        return None, ("the header says {0} new line(s) but {1} context + {2} added = "
                      "{3} are present".format(new_count, old_count, len(added),
                                               old_count + len(added)))
    shape = {
        "old_start": old_start,
        "new_start": new_start,
        "old_count": old_count,
        "new_count": new_count,
        "body": body,
        "context": context,
        "added": added,
        "heading": m.group(5),
        "header": lines[2],
    }
    return shape, None


def where_bodies_differ(a_body, b_body):
    """The first position at which two patch bodies disagree, as a sentence."""
    for n, (a, b) in enumerate(zip(a_body, b_body), 1):
        if a != b:
            return ("body line {0} differs:\n      committed: {1}{2!r}\n      generated: "
                    "{3}{4!r}".format(n, a[0].decode("ascii", "replace"), a[1][:160],
                                      b[0].decode("ascii", "replace"), b[1][:160]))
    if len(a_body) != len(b_body):
        longer = "committed" if len(a_body) > len(b_body) else "generated"
        extra = (a_body if len(a_body) > len(b_body) else b_body)[
            min(len(a_body), len(b_body))]
        return ("the {0} patch has {1} more body line(s); the first is "
                "{2}{3!r}".format(longer, abs(len(a_body) - len(b_body)),
                                  extra[0].decode("ascii", "replace"), extra[1][:160]))
    return None


def check(have, want):
    """Is `have` the patch `want` says should be committed? (ok, summary, why)

    `want` is what build() just derived from jarvis_hud.py, so it is the truth
    about placement, context, added lines and counts. `have` is the bytes on
    disk. The hunk header's line NUMBER is not compared - see the module
    docstring for the 2026-10-14 measurement that says why.
    """
    if have == want:
        return True, "byte for byte", None
    have_shape, have_why = semantify(have)
    if have_shape is None:
        return False, None, "the committed patch cannot be read: " + have_why
    want_shape, want_why = semantify(want)
    if want_shape is None:                      # a bug in build(), not in the patch
        return False, None, "this script's own output cannot be read: " + want_why
    skew = have_shape["old_start"] - want_shape["old_start"]
    if skew != 0 and have_shape["new_start"] - have_shape["old_start"] != 0:
        return False, None, ("the committed hunk header is internally inconsistent: "
                             "{0!r} puts its old and new starts {1} apart, not "
                             "0".format(have_shape["header"],
                                        have_shape["new_start"] - have_shape["old_start"]))
    # The whole body, in order, with each line tagged: a changed line, a dropped
    # or added line, and a context line swapped with its neighbour all show up here.
    differs = where_bodies_differ(have_shape["body"], want_shape["body"])
    if differs:
        return False, None, differs
    if have_shape["heading"] != want_shape["heading"]:
        return False, None, ("the hunk header's trailing heading differs: committed "
                             "{0!r}, generated {1!r}".format(have_shape["heading"][:80],
                                                             want_shape["heading"][:80]))
    if skew:
        summary = ("the hunk was {0} line(s) {1} than this script derives - the "
                   "placement, the context, the {2} added line(s) and the counts all "
                   "match, so the patch still applies (git apply finds a hunk by its "
                   "context, not its number); committed {3!r}, generated "
                   "{4!r}".format(abs(skew),
                                  "further down" if skew > 0 else "higher up",
                                  len(want_shape["added"]), have_shape["header"],
                                  want_shape["header"]))
    else:
        summary = ("the header line number matches too; placement, context, the {0} "
                   "added line(s) and the counts all match".format(
                       len(want_shape["added"])))
    return True, summary, None


def main():
    want, note = build(HUD.read_text(encoding="utf-8").splitlines())
    if want is None:
        print("picture-card.patch NOT WRITTEN:", note)
        return 1
    if "--check" in sys.argv:
        have = OUT.read_bytes() if OUT.exists() else b""
        ok, summary, why = check(have, want)
        if ok:
            print("picture-card.patch is up to date:", note, "|", len(ADDED),
                  "added lines")
            print("  " + summary)
            return 0
        print("picture-card.patch is OUT OF DATE - the committed patch is not what this "
              "script builds.")
        print("  " + why)
        print("Fix it with: py -3 tools/gen_picture_card_patch.py")
        n, got, expected = first_difference(have, want)
        if n is not None:
            print("  first byte difference at line {0}".format(n))
            print("    committed: {0!r}".format(got[:200]))
            print("    generated: {0!r}".format(expected[:200]))
        return 1
    OUT.write_bytes(want)
    print("wrote", OUT)
    print("hunk:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
