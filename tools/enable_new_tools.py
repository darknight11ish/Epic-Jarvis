#!/usr/bin/env python3
"""Enable named tools in the owner's OWN `jarvis-framework.toml` - additively.

    python -B tools/enable_new_tools.py --backend "<live folder>" \\
        --add project_create,work_item_add            # dry run, prints the change
    python -B tools/enable_new_tools.py --backend "<live folder>" \\
        --add project_create,work_item_add --apply    # writes, with a backup

WHY THIS EXISTS (measured 2026-11-21, off-peak field test)

PM2 shipped its eight project tools **ON in the published config**
(`jarvis-backend/jarvis-framework.toml`), and deploy #5 carried every module -
but the owner's live `jarvis-framework.toml` still listed 29 tools and none of
the eight, so `jarvis_agent.enabled_tools_for_turn()` returned 29 and the model
was never offered a single project tool. Measured on the live install:

    project_create: in enabled=False | in offered=False
    ... all eight the same

The deploy never touches that file **on purpose** ("the OWNER'S settings"), and
it is right not to: replacing it would overwrite the owner's vault path, bind
address and every switch they chose. What was missing is the small, explicit
step between "a release ships a new ON tool" and "the owner's config lists it".

THE RULE THIS TOOL KEEPS

* It only ever **adds** names the caller names with `--add`. It never removes or
  reorders anything, and it never re-enables a tool the owner turned off - the
  caller passes exactly the tools the release newly ships (the update flow can
  pass its own release's list).
* A name that is not a real tool in this install (`jarvis_agent.TOOLS`) is
  refused, so a typo can never write a row nothing answers.
* Dry run by default. `--apply` copies the file to
  `<name>.before-enable-tools-<stamp>` first, writes only the `[tools] enabled`
  array, and reads it back to prove the other sections are byte-identical.
* A second run is a no-op, so an update path can call it unconditionally.

WHAT IT WILL NOT DO

It does not add a tool that is absent from `jarvis_agent.TOOLS` (that is a code
deploy's job), it does not change a tool's tier, and it does not touch any
other key - a settings file the owner has edited is theirs.
"""
import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

FRAMEWORK = "jarvis-framework.toml"
TOOLS_HEADER = re.compile(r"^\[tools\]\s*$")
SECTION_HEADER = re.compile(r"^\[[^\]]+\]\s*$")
ENABLED_START = re.compile(r'^enabled\s*=\s*\[(.*)$')


def _section_range(lines):
    """(header index, end index) of the [tools] section, or (None, None)."""
    start = None
    for i, line in enumerate(lines):
        if TOOLS_HEADER.match(line.strip()):
            start = i
            continue
        if start is not None and SECTION_HEADER.match(line.strip()):
            return start, i
    return (start, len(lines)) if start is not None else (None, None)


def _enabled_span(lines, start, end):
    """(first line index, last line index, names) of [tools]'s enabled array."""
    for i in range(start, end):
        if ENABLED_START.match(lines[i].strip()):
            last = i
            while "]" not in lines[last]:
                last += 1
                if last >= end:
                    return None, None, None
            block = "\n".join(lines[i:last + 1])
            body = block.split("[", 1)[1].rsplit("]", 1)[0]
            names = re.findall(r'"([^"]*)"', body)
            return i, last, names
    return None, None, None


def _render(names):
    return 'enabled = [' + ", ".join(f'"{n}"' for n in names) + ']'


def plan(framework: Path, add):
    """(lines, added, why) - the new file text and the names added, or (None, [], why)."""
    text = framework.read_text(encoding="utf-8")
    lines = text.splitlines()
    start, end = _section_range(lines)
    if start is None:
        return None, [], f"{framework} has no [tools] section"
    first, last, names = _enabled_span(lines, start, end)
    if first is None:
        return None, [], f"{framework}'s [tools] section has no enabled = [...] line"
    wanted = []
    for name in add:
        name = str(name).strip()
        if name and name not in wanted:
            wanted.append(name)
    added = [n for n in wanted if n not in names]
    if not added:
        return lines, [], ""
    new_lines = list(lines)
    new_lines[first:last + 1] = [_render(names + added)]
    return new_lines, added, ""


def real_tools(backend: Path):
    """The tool names this install really has, or (set(), why)."""
    try:
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        import jarvis_agent  # noqa: E402
        return set(jarvis_agent.TOOLS), ""
    except Exception as exc:  # noqa: BLE001 - an unreadable install is a state
        return set(), f"jarvis_agent.TOOLS could not be read in {backend} ({type(exc).__name__})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", required=True,
                    help="the folder holding jarvis_hud.py and the owner's jarvis-framework.toml")
    ap.add_argument("--add", action="append", default=[],
                    help="a tool name to enable; repeatable, or one comma-separated list")
    ap.add_argument("--apply", action="store_true", help="write it (default is a dry run)")
    ap.add_argument("--allow-unknown", action="store_true",
                    help="do not check the names against jarvis_agent.TOOLS (tests only)")
    args = ap.parse_args(argv)

    backend = Path(args.backend).expanduser()
    framework = backend / FRAMEWORK
    if not framework.is_file():
        print(f"REFUSED: no {FRAMEWORK} in {backend}")
        return 2
    add = []
    for chunk in args.add:
        add.extend(part.strip() for part in chunk.split(",") if part.strip())
    if not add:
        print("REFUSED: --add names nothing")
        return 2

    known, why = real_tools(backend)
    if not args.allow_unknown:
        if not known:
            print(f"REFUSED: {why}")
            return 2
        unknown = [n for n in add if n not in known]
        if unknown:
            print("REFUSED: not a real tool in this install: " + ", ".join(unknown))
            return 2

    lines, added, problem = plan(framework, add)
    if problem:
        print(f"REFUSED: {problem}")
        return 2
    if not added:
        print("nothing to add: every named tool is already enabled in "
              f"{framework}")
        return 0
    print(f"would add {len(added)} tool(s) to {framework}: " + ", ".join(added))
    if not args.apply:
        print("DRY RUN - the file was not written. Add --apply to write it.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = framework.with_name(f"{framework.name}.before-enable-tools-{stamp}")
    shutil.copy2(framework, backup)
    before = framework.read_text(encoding="utf-8")
    framework.write_text("\n".join(lines) + ("\n" if before.endswith("\n") else ""),
                         encoding="utf-8", newline="")
    after = framework.read_text(encoding="utf-8")
    # Prove the only changed line is the [tools] enabled array: every other line
    # is present, in order, unchanged.
    changed = [a for a in after.splitlines() if a not in before.splitlines()
               and not a.startswith("enabled = [")]
    if changed:
        shutil.copy2(backup, framework)
        print("REFUSED: the write would have changed more than the enabled list "
              f"({len(changed)} line(s)); the file was restored from {backup.name}")
        return 2
    print(f"added {len(added)} tool(s); backup at {backup.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
