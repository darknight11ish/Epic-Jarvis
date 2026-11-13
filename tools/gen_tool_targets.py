#!/usr/bin/env python3
"""Writes the spoken names of every switchable tool into jarvis_settings_registry.

    python -B tools/gen_tool_targets.py            # write both registry copies
    python -B tools/gen_tool_targets.py --check    # compare only, exit 1 if stale

THE MEASURED GAP (2026-11-07, feature-awareness audit H7 / live-parity LP-2).
`jarvis_asks_first.TOOLS_SWITCHABLE` lists every tool an app may switch ON -
60 of them on 2026-11-05 - and Settings draws a row for each even though the
backend never read those rows before this run. Chat and Jarvis Live resolve a
tool switch through `jarvis_settings_registry._TOOL_TARGETS`, and that table
named only the four reading tools (`calendar_read`, `email_read`,
`notes_search`, `home_read`). Measured: *"Turn on the browser control tool."*
went to the model in typed chat and gave an outside-text refusal in Live - for
a switch that Settings has had all along. 56 of the 60 tools could not be
switched by asking.

WHY A GENERATOR. The table must be exactly the switchable list. Hand-typing
56 entries once is not the problem; hand-typing them AGAIN when a tool is
added is, and a missing row is a switch the owner can see but cannot ask for.
So the table is generated from `jarvis_asks_first.TOOLS_SWITCHABLE` itself:
`jarvis_quick.py`'s `settings_tool` grammar resolves through it, and
`backend/test_settings_registry.py` (the natural-phrase completeness check)
plus this generator's `--check` mode fail if the two drift.

THE NAMES ARE DETERMINISTIC, from each tool's own name:
    browser_control -> "the browser control tool", "browser control tool",
                       "the browser control", "browser control"
The four reading tools keep their hand-written names FIRST (they shipped
before this, and phrases/labels use them): "the calendar tool", "calendar",
"my calendar", and so on. A legacy alias is only kept for the four rows that
had one - the rest are derived, never guessed.

WHAT THE CARDS ARE IS UNCHANGED. `_TOOL_TARGETS` is only a NAME table: the
switch itself still runs through `jarvis_asks_first.request_tool_enable` (ON
is the PC only, one approval card plus Windows Hello; OFF is instant), and
nothing here approves, loosens or writes anything. `find_tool_target` matches
a WHOLE alias and returns None otherwise, so a sentence naming no switchable
tool falls through untouched (the closed-world rule the "turn off the kitchen
light" regression test pins).

Run after ANY change to TOOLS_SWITCHABLE (a new tool, a rename, a removal).
Standard library only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.append(str(BACKEND / "rebuilt"))

#: Every copy of the registry this repository ships. They are byte-equal
#: (tools/check_stale_twins.py), so the same generated block is written to
#: each; a copy whose block is edited by hand is a stale copy.
COPIES = (
    BACKEND / "jarvis_settings_registry.py",
    REPO / "jarvis-backend" / "jarvis_settings_registry.py",
)

BEGIN = "# BEGIN GENERATED: tool target names (tools/gen_tool_targets.py)\n"
END = "# END GENERATED: tool target names (tools/gen_tool_targets.py)\n"

#: The four tools that had hand-written names before 2026-11-07. Their old
#: names come FIRST and are kept word-for-word, so every phrase and label
#: that already worked still resolves; the derived forms are added after them.
#: `email_check` is the real tool name the old `email_read` row maps to
#: (jarvis_asks_first.LEGACY_TOOL_NAMES), so both keys carry the old names.
LEGACY_NAMES = {
    "calendar_read": ("the calendar tool", "calendar", "my calendar"),
    "email_read": ("the email tool", "email", "my email"),
    "notes_search": ("the notes tool", "notes", "my notes"),
    "home_read": ("the home status tool", "home status"),
}

#: The ONE explicit table for natural names the key's own words cannot
#: produce (a leading verb hides the noun a person says: "set_timer" is "the
#: timer tool"). Kept small on purpose, and every entry goes through the same
#: collision check as a derived name.
EXTRA_NAMES = {
    "set_timer": ("timer",),
    "set_reminder": ("reminder",),
    "append_obsidian_daily": ("obsidian daily note", "obsidian note"),
    "create_joplin_note": ("joplin note",),
    "append_logseq_journal": ("logseq journal",),
    "my_spending": ("spending summary", "spending"),
    "read_web_page": ("one web page", "web page"),
    "send_file_to_phone": ("file to phone",),
    # The owner says "pull request", and the tool's own name says "pr" (wave 16,
    # 2026-11-10: the cockpit, the carded merge and the carded fix-and-push).
    # The EXACT tool name is the real name and stays the first form; these are
    # the words a person actually uses, added after it like every other entry.
    "github_pr_scan": ("the github pull request scan tool", "github pull request scan tool",
                       "the github pull request scan", "github pull request scan"),
    "github_merge_pr": ("the github pull request merge tool", "github pull request merge tool",
                        "the github pull request merge", "github pull request merge"),
    "github_fix_and_push": ("the github pull request fix tool", "github pull request fix tool",
                            "the github pull request fix", "github pull request fix"),
    # The 2026-11-10 22:30 ruling's Step 2 surface: the owner says "pull
    # request", not "pr", and "review", not "pr review".
    "github_pr_detail": ("the github pull request detail tool",
                         "github pull request detail tool",
                         "the github pull request detail",
                         "github pull request detail"),
    "github_open_pr": ("the github open pull request tool",
                       "github open pull request tool",
                       "the github open pull request", "github open pull request"),
    "github_workflow": ("the github workflow tool", "github workflow tool",
                        "the github workflow", "github workflow"),
    "github_issue_labels": ("the github issue labels tool",
                            "github issue labels tool",
                            "the github issue labels", "github issue labels",
                            "the github labels tool", "github labels tool"),
    "github_edit_pr": ("the github pull request edit tool",
                       "github pull request edit tool",
                       "the github pull request edit", "github pull request edit"),
    "github_pr_review": ("the github pull request review tool",
                         "github pull request review tool",
                         "the github pull request review",
                         "github pull request review"),
}


def names_for(tool: str) -> tuple:
    """The whole spoken aliases this tool answers to.

    Deterministic from the tool's own real name (a legacy saved name such as
    `email_read` is read through jarvis_asks_first.real_tool first, so the
    words are the model's own tool name), plus the two small explicit tables
    above.
    """
    try:
        import jarvis_asks_first as AF

        real = AF.real_tool(tool)
    except Exception:                        # noqa: BLE001 - generator input only
        real = tool
    words = " ".join(str(real).replace("_", " ").split())
    derived = () if not words else (
        f"the {words} tool",
        f"{words} tool",
        f"the {words}",
        words,
    )
    legacy = LEGACY_NAMES.get(tool) or LEGACY_NAMES.get(real) or ()
    out = []
    for name in tuple(legacy) + tuple(derived) + tuple(EXTRA_NAMES.get(tool, ())):
        if name not in out:
            out.append(name)
    return tuple(out)


def targets() -> dict:
    """{tool: (alias, ...)} for every switchable tool, in TOOLS_SWITCHABLE order."""
    import jarvis_asks_first as AF

    out: dict = {}
    seen: dict = {}
    for tool in AF.TOOLS_SWITCHABLE:
        names = names_for(tool)
        for name in names:
            other = seen.get(name)
            if other is not None and other != tool:
                raise SystemExit(
                    f"two switchable tools would answer to the same words "
                    f"{name!r}: {other!r} and {tool!r}. The generator will not "
                    "guess which one the owner meant - rename one tool or add "
                    "an explicit LEGACY_NAMES entry made distinct on purpose.")
            seen[name] = tool
        out[str(tool)] = names
    # The old email_read row is not itself in TOOLS_SWITCHABLE any more (the
    # real tool is email_check), but its spoken names must keep resolving to
    # the READING-tool row: the reading-tool suites pin "don't let the ai
    # model read my email" to email_read, and set_reading_tool accepts the
    # legacy name. It gets ONLY the old names - its derived words would
    # collide with email_check's own ("email check").
    for tool, legacy in LEGACY_NAMES.items():
        if tool in out:
            continue
        for name in legacy:
            other = seen.get(name)
            if other is not None and other != tool:
                raise SystemExit(
                    f"two switchable tools would answer to the same words "
                    f"{name!r}: {other!r} and {tool!r}")
            seen[name] = tool
        out[tool] = tuple(legacy)
    return out


def block() -> str:
    """The exact generated text, markers included."""
    lines = [BEGIN, "_TOOL_TARGETS = {\n"]
    for tool, names in targets().items():
        lines.append("    " + repr(tool) + ": (" +
                     ", ".join(repr(n) for n in names) + "),\n")
    lines.append("}\n")
    lines.append(END)
    return "".join(lines)


def _replace_block(text: str, new_block: str, path: Path) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end < start:
        raise SystemExit(
            f"{path} does not carry both generated-tool-target markers "
            f"({BEGIN.strip()!r} ... {END.strip()!r}) - restore them from git "
            "before running this generator.")
    return text[:start] + new_block + text[end + len(END):]


def main(argv) -> int:
    import jarvis_asks_first as AF

    count = len(AF.TOOLS_SWITCHABLE)
    new = block()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            if not path.is_file():
                stale.append(f"{path.relative_to(REPO)} (absent)")
                continue
            text = path.read_text(encoding="utf-8")
            try:
                got = _replace_block(text, new, path)
            except SystemExit:
                stale.append(f"{path.relative_to(REPO)} (no markers)")
                continue
            if got != text:
                stale.append(str(path.relative_to(REPO)))
        if stale:
            print("out of date (run python -B tools/gen_tool_targets.py): "
                  + ", ".join(stale))
            return 1
        print(f"tool targets: {count} switchable tools up to date in "
              f"{len(COPIES)} registry copies")
        return 0
    for path in COPIES:
        text = path.read_text(encoding="utf-8")
        new_text = _replace_block(text, new, path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
        print(f"wrote {path.relative_to(REPO)} ({count} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
