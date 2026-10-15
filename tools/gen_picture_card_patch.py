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
"""
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


def main():
    want, note = build(HUD.read_text(encoding="utf-8").splitlines())
    if want is None:
        print("picture-card.patch NOT WRITTEN:", note)
        return 1
    if "--check" in sys.argv:
        have = OUT.read_bytes() if OUT.exists() else b""
        if have == want:
            print("picture-card.patch is up to date:", note, "|",
                  len(ADDED), "added lines")
            return 0
        print("picture-card.patch is OUT OF DATE - the committed patch is not what this "
              "script builds.")
        print("Fix it with: py -3 tools/gen_picture_card_patch.py")
        n, got, expected = first_difference(have, want)
        if n is not None:
            print("  first difference at line {0}".format(n))
            print("    committed: {0!r}".format(got[:200]))
            print("    generated: {0!r}".format(expected[:200]))
        return 1
    OUT.write_bytes(want)
    print("wrote", OUT)
    print("hunk:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
