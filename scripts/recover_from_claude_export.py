#!/usr/bin/env python3
"""Pull lost backend modules out of a Claude conversation export.

WHY THIS EXISTS

Ten of the backend's twenty-six modules are not on the owner's machine, are
not in any installer, package or archive on it, and have no public upstream.
The evidence says they were produced in assistant conversations and saved to
disk, and that some were never saved. So the chat history is the only copy.

Reading that history by hand means scrolling months of conversation looking
for ten filenames. Claude will instead export the whole lot as data:

    claude.ai -> Settings -> Privacy -> Export data

An email arrives with a .zip. This reads it and writes out every Python module
it can find, so the search is a command rather than an afternoon.

USAGE

    python scripts/recover_from_claude_export.py path\\to\\data-export.zip

    # or, if you already unzipped it
    python scripts/recover_from_claude_export.py path\\to\\conversations.json

    # write straight into the backend folder instead of ./recovered
    python scripts/recover_from_claude_export.py export.zip --out "C:\\...\\Desktop program"

Nothing is overwritten unless you pass --force. Standard library only.

WHAT IT LOOKS AT

An export puts code in more than one place depending on how it was sent, so
all of them are checked:

  * attachments      - a file uploaded or handed back, with its real name
  * fenced blocks    - ```python ... ``` inside a message
  * artifacts        - code panels, which appear as structured content

A fenced block does not carry a filename, so the name is recovered from the
block itself: a `# jarvis_x.py` first line, or a module docstring that names
it, or a filename mentioned in the text just before the fence. A block whose
name cannot be established is counted and reported, never guessed at.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

#: The modules known to be missing, most-needed first. Used only for the
#: summary - anything named jarvis_*.py is recovered whether it is listed or
#: not, because a module nobody has noticed missing is still worth having.
WANTED = [
    "jarvis_framework", "jarvis_memory", "jarvis_events", "jarvis_voice",
    "jarvis_power", "jarvis_compute", "jarvis_router", "jarvis_recall",
    "jarvis_sleep", "jarvis_initiative",
]

_FENCE = re.compile(
    r"```(?:python|py)?[ \t]*\n(.*?)```",
    re.DOTALL,
)
#: `# jarvis_memory.py` or `#!/usr/bin/env python3` then the name, in the
#: first few lines of a block.
_HEAD_NAME = re.compile(r"^[ \t]*#[ \t]*([A-Za-z_][\w]*\.py)\b", re.M)
#: A docstring that opens by naming the file: `"""jarvis_gate.py - the ..."""`
_DOC_NAME = re.compile(r'^[ \t]*[ruRU]{0,2}("""|\'\'\')\s*([A-Za-z_][\w]*\.py)\b')
#: Any .py filename, for reading the text immediately before a fence.
_ANY_PY = re.compile(r"\b([A-Za-z_][\w]*\.py)\b")


def looks_like_module(code: str) -> bool:
    """Is this a whole file, or a three-line illustration of one?

    A conversation is full of short snippets - a corrected function, an
    example call. Writing those out as `jarvis_memory.py` would be worse than
    finding nothing, because the result imports cleanly and does almost
    nothing. The bar: it has to have real substance and at least one
    definition.
    """
    if len(code) < 400:
        return False
    if not re.search(r"^\s*(def|class)\s+\w+", code, re.M):
        return False
    # A diff is not a module, however long it is.
    if code.lstrip().startswith(("--- ", "+++ ", "@@ ", "diff --git")):
        return False
    return True


def name_from_block(code: str, before: str) -> str | None:
    """Work out which file a fenced block is, or return None.

    Three sources, strongest first. `before` is the message text immediately
    preceding the fence, which often reads "here is the updated
    jarvis_router.py:" - weaker than the block naming itself, so it is last.
    """
    head = "\n".join(code.splitlines()[:6])
    m = _HEAD_NAME.search(head)
    if m:
        return m.group(1)
    m = _DOC_NAME.search(code.lstrip("\n"))
    if m:
        return m.group(2)
    # Last 200 characters before the fence, nearest mention wins.
    names = _ANY_PY.findall(before[-200:])
    if names:
        return names[-1]
    return None


def walk(node, out: list, depth: int = 0) -> None:
    """Collect (name, code, when) from any shape of export.

    The export format has changed more than once and differs between message
    kinds, so rather than encode one schema this walks everything and picks up
    anything that looks like a message, an attachment or a content block. A
    walker that finds nothing is a bug worth seeing; a parser that throws on an
    unexpected key is a bug that looks like an empty history.
    """
    if depth > 40:
        return

    if isinstance(node, list):
        for item in node:
            walk(item, out, depth + 1)
        return

    if not isinstance(node, dict):
        return

    when = ""
    for key in ("created_at", "updated_at", "timestamp"):
        if isinstance(node.get(key), str):
            when = node[key]
            break

    # 1. An attachment or file: it carries its own real name.
    fname = node.get("file_name") or node.get("filename") or node.get("name")
    body = node.get("extracted_content") or node.get("content") or node.get("text")
    if (isinstance(fname, str) and fname.endswith(".py")
            and isinstance(body, str) and body.strip()):
        out.append((fname, body, when, "attachment"))

    # 2. Message text, which may hold fenced blocks.
    for key in ("text", "content", "input", "prompt"):
        val = node.get(key)
        if not isinstance(val, str) or "```" not in val:
            continue
        for m in _FENCE.finditer(val):
            code = m.group(1)
            if not looks_like_module(code):
                continue
            nm = name_from_block(code, val[:m.start()])
            out.append((nm or "", code, when, "code block"))

    for value in node.values():
        walk(value, out, depth + 1)


def sources(where: Path):
    """Every JSON document worth reading, from whatever was pointed at.

    An export is FIVE archives, not one - conversations, projects, memories,
    feedback and metadata - because `get-export.ps1` downloads the lot. The
    modules could be in a Project as easily as in a chat, so a folder means
    "read all of them", not "find the conversations one".

    Yields (label, parsed) and keeps going when one file is unreadable: with
    five single-use downloads behind this, one bad archive must not throw away
    the other four.
    """
    if where.is_dir():
        # Anything NAMED like an export file is a candidate, even if it turns
        # out not to be readable. A first version filtered on
        # `is_zipfile(f) or suffix == ".json"`, which quietly dropped a
        # truncated .zip before anything was reported - and a truncated
        # archive is the exact thing a spent one-time link produces. A file
        # that cannot be read has to be NAMED, because it is the one the user
        # may have to get a fresh export for.
        files = sorted(
            [f for f in where.iterdir()
             if f.is_file() and f.suffix.lower() in (".zip", ".json")],
            key=lambda f: -f.stat().st_size)
        if not files:
            raise SystemExit(
                f"No archives or .json files in {where}.\n"
                "Point this at the folder get-export.ps1 wrote to.")
        for f in files:
            try:
                yield f.name, load(f)
            except SystemExit as exc:
                print(f"  {f.name}: UNREADABLE - {str(exc).splitlines()[0]}")
            except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
                print(f"  {f.name}: UNREADABLE - {type(exc).__name__}: {exc}")
        return
    yield where.name, load(where)


def load(where: Path) -> object:
    """Read one export file, whether it is an archive or the JSON inside it."""
    # Look at the CONTENT, not the extension. The export Claude emails is
    # named like `manifest-<uuid>-<numbers>-<hash>-<date>` with no `.zip` on
    # the end at all, so deciding by suffix reads a perfectly good archive as
    # though it were text and fails with a UnicodeDecodeError - an error that
    # says nothing about the real problem.
    if zipfile.is_zipfile(where):
        with zipfile.ZipFile(where) as z:
            names = [n for n in z.namelist() if n.endswith("conversations.json")]
            if not names:
                # Some exports name it differently; take any sizeable .json.
                names = sorted((n for n in z.namelist() if n.endswith(".json")),
                               key=lambda n: -z.getinfo(n).file_size)
            if not names:
                inner = [n for n in z.namelist() if zipfile.is_zipfile(n)]
                raise SystemExit(
                    f"No .json inside {where.name}. It holds: "
                    + ", ".join(z.namelist()[:12])
                    + ("" if len(z.namelist()) <= 12 else " ...")
                    + ("\n\nThere is a zip inside the zip - unpack it and "
                       "point this at what comes out." if inner else ""))
            print(f"Reading {names[0]} from the archive.")
            with z.open(names[0]) as fh:
                return json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    size = where.stat().st_size

    # Named .zip but is not one. This is what a SPENT one-time link produces:
    # claude.ai answers a used link with an HTML page, which saves happily
    # under the name you asked for. Saying "not valid JSON" here would send
    # someone looking at the wrong thing entirely.
    if where.suffix.lower() == ".zip":
        head = where.read_bytes()[:200].lstrip()
        html = head[:1] == b"<"
        raise SystemExit(
            f"{where.name} is named .zip but is not one "
            f"({size / 1024:.0f} KB)."
            + ("\n  It looks like an HTML page, which is what claude.ai "
               "returns for a link\n  that has already been used. That file "
               "needs a fresh export."
               if html else
               "\n  The download was probably cut short. That file needs a "
               "fresh export."))

    print(f"Reading {where.name} ({size / 1e6:.0f} MB). This can take a minute.")
    # utf-8-sig, not utf-8: a BOM would otherwise read as a corrupt file.
    try:
        text = where.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise SystemExit(
            f"{where.name} is neither a zip nor text, so it cannot be read.\n"
            "If Claude emailed you a link rather than a file, download the "
            "archive itself\nand point this at that.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{where.name} is not valid JSON: {exc}")


_URLISH = re.compile(r"https?://|^[A-Za-z0-9_\-]{40,}$")


def inspect(node, prefix: str = "", depth: int = 0, lines: list | None = None) -> list:
    """Print the SHAPE of a file, with anything secret-looking held back.

    An export can arrive as a manifest - a small index naming the real data
    files - rather than the data. Working out which you have means looking
    inside, and a manifest carries signed download URLs: long strings that are
    effectively passwords for the archive. So this shows keys, types and short
    values, and replaces anything that looks like a URL or a key with its
    length. The output is safe to paste into a chat; the file itself is not.
    """
    if lines is None:
        lines = []
    if depth > 6 or len(lines) > 200:
        return lines

    pad = "  " * depth
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                n = len(v)
                kind = "object" if isinstance(v, dict) else f"list of {n}"
                lines.append(f"{pad}{k}: {kind}")
                inspect(v, prefix, depth + 1, lines)
            else:
                lines.append(f"{pad}{k}: {redact(v)}")
    elif isinstance(node, list):
        for item in node[:5]:
            inspect(item, prefix, depth + 1, lines)
        if len(node) > 5:
            lines.append(f"{pad}... and {len(node) - 5} more")
    else:
        lines.append(f"{pad}{redact(node)}")
    return lines


def redact(v) -> str:
    """A value, unless showing it would hand someone the download."""
    if not isinstance(v, str):
        return repr(v)
    if _URLISH.search(v) or len(v) > 80:
        return f"<{len(v)} chars, hidden - may be a download key>"
    return repr(v)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path,
                    help="the .zip Claude emailed, the folder you unzipped it "
                         "into, or conversations.json itself")
    ap.add_argument("--out", type=Path, default=Path("recovered"),
                    help="where to write the files (default: ./recovered)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite files that already exist in --out")
    ap.add_argument("--all", action="store_true",
                    help="also write modules that are not jarvis_*")
    ap.add_argument("--inspect", action="store_true",
                    help="show what the file CONTAINS and stop, with URLs and "
                         "long keys hidden so the output is safe to paste")
    args = ap.parse_args()

    if not args.export.exists():
        print(f"Nothing at {args.export}")
        return 1

    found: list = []
    read_any = False
    for label, data in sources(args.export):
        if args.inspect:
            print(f"\nWhat is inside {label}:\n")
            for line in inspect(data):
                print("  " + line)
            read_any = True
            continue
        before = len(found)
        walk(data, found)
        print(f"  {label}: {len(found) - before} code block(s)")
        read_any = True

    if args.inspect:
        if read_any:
            print("\n(Anything that looked like a URL or a key is hidden. "
                  "This output is\nsafe to paste; the file itself is not.)")
        return 0

    # A manifest is an INDEX of the export, not the export. It is small, it
    # holds no messages, and it is what you get if you save the wrong link -
    # so say that, rather than "no modules found", which reads as "your
    # history is empty" and sends you looking in the wrong place.
    size = args.export.stat().st_size if args.export.is_file() else 1 << 30
    if not found and size < 2_000_000:
        print(f"\n{args.export.name} is {size / 1024:.0f} KB and contains no "
              f"messages at all.")
        print("\nThat is a MANIFEST - an index naming the real data files - "
              "not the export.\nThe conversations are a separate, much larger "
              "download.")
        print("\nSee what it points at:")
        print(f"    python .\\scripts\\recover_from_claude_export.py "
              f"\"{args.export.name}\" --inspect")
        return 1

    unnamed = sum(1 for n, _, _, _ in found if not n)
    named = [f for f in found if f[0]]

    # Best copy per filename. Longest wins, because a conversation usually
    # shows a file growing: excerpt, then section, then the whole thing. Ties
    # break on the later timestamp.
    best: dict = {}
    for name, code, when, how in named:
        if not args.all and not name.startswith("jarvis_"):
            continue
        cur = best.get(name)
        if cur is None or (len(code), when) > (len(cur[0]), cur[1]):
            best[name] = (code, when, how)

    if not best:
        print("\nNo Python modules found in that export.")
        print(f"({len(found)} code block(s) seen, {unnamed} of them unnamed.)")
        print("\nIf you expected some, the export may be from the wrong "
              "account, or\nthe files were shared in a project rather than a "
              "conversation.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    wrote, skipped = [], []
    for name in sorted(best):
        code, when, how = best[name]
        dest = args.out / name
        if dest.exists() and not args.force:
            skipped.append(name)
            continue
        if not code.endswith("\n"):
            code += "\n"
        # LF. The patches are LF and the context must match byte for byte;
        # newline="" stops Windows turning every one into CRLF on the way out.
        with open(dest, "w", encoding="utf-8", newline="") as fh:
            fh.write(code)
        wrote.append((name, len(code.splitlines()), when[:10], how))

    print(f"\nWrote {len(wrote)} file(s) to {args.out.resolve()}\n")
    for name, lines, when, how in wrote:
        star = "  <- WANTED" if name[:-3] in WANTED else ""
        print(f"  {name:<26} {lines:>5} lines   {when or 'undated'}  "
              f"({how}){star}")
    if skipped:
        print(f"\n  {len(skipped)} already existed, left alone "
              f"(use --force to replace): {', '.join(skipped)}")

    got = {n[:-3] for n, _, _, _ in wrote}
    still = [w for w in WANTED if w not in got]
    print()
    if still:
        print(f"Still missing {len(still)} of the {len(WANTED)} known-lost "
              f"modules:")
        for s in still:
            print(f"  {s}.py")
        print("\nThose were probably never in a conversation on this account.")
    else:
        print("Every known-lost module was recovered.")

    if unnamed:
        print(f"\n{unnamed} code block(s) looked like modules but named no "
              f"file, so\nthey were left out rather than guessed at.")

    print("\nBEFORE COPYING ANYTHING INTO YOUR BACKEND: open one and check it "
          "is whole.\nA conversation can hold a half-written draft, and this "
          "cannot tell the\ndifference between that and a finished file. Then:")
    print("    .\\scripts\\check-backend.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
