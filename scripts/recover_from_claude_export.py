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


def load(where: Path) -> object:
    """Read the export, whether it is the zip or a file inside it."""
    if where.is_dir():
        for cand in ("conversations.json", "conversations/conversations.json"):
            p = where / cand
            if p.is_file():
                where = p
                break
        else:
            found = sorted(where.rglob("conversations.json"))
            if not found:
                raise SystemExit(
                    f"No conversations.json anywhere under {where}.\n"
                    "Point this at the .zip Claude emailed you, or at the "
                    "folder you unzipped it into.")
            where = found[0]

    if where.suffix.lower() == ".zip":
        with zipfile.ZipFile(where) as z:
            names = [n for n in z.namelist() if n.endswith("conversations.json")]
            if not names:
                # Some exports name it differently; take any sizeable .json.
                names = sorted((n for n in z.namelist() if n.endswith(".json")),
                               key=lambda n: -z.getinfo(n).file_size)
            if not names:
                raise SystemExit(f"No .json inside {where}.")
            print(f"Reading {names[0]} from the zip.")
            with z.open(names[0]) as fh:
                return json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    size = where.stat().st_size
    print(f"Reading {where.name} ({size / 1e6:.0f} MB). This can take a minute.")
    # utf-8-sig, not utf-8: a BOM would otherwise read as a corrupt file.
    return json.loads(where.read_text(encoding="utf-8-sig"))


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
    args = ap.parse_args()

    if not args.export.exists():
        print(f"Nothing at {args.export}")
        return 1

    found: list = []
    walk(load(args.export), found)

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
