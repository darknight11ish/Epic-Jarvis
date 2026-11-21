"""test_enable_new_tools.py - the additive tool-enable step for a real install.

WHAT THIS PROVES, in temp folders only (the owner's real `jarvis-framework.toml`
is never touched):

1. It adds exactly the tools it was told to add, to the `[tools]` section's
   `enabled` list, and **every other line of the file is unchanged** - a
   settings file the owner has edited is theirs.
2. A second run is a no-op, so an update path can call it unconditionally.
3. A tool the owner removed by hand stays removed: only `--add` names are added,
   never anything else.
4. A name that is not a real tool in that install is refused (no row that
   nothing answers), a missing `[tools]` section or `enabled` line is refused,
   and a dry run writes nothing.
5. The `enabled = ...` lines in OTHER sections are left alone (the live file has
   dozens of them: `[app_control]`, `[voice]`, ...).
6. On `--apply` the original is backed up before the write, and the backup is
   byte-identical to the file as it was.
7. A multi-line `enabled` array is handled and collapsed to one line without
   losing a name.

WHY THIS EXISTS (measured 2026-11-21, off-peak). PM2 shipped eight project
tools ON in the published config, but the owner's live `[tools] enabled` list
had 29 names and none of the eight, so `jarvis_agent.enabled_tools_for_turn()`
was 29 and the model was never offered a project tool. The deploy never touches
that file on purpose; this is the missing explicit step between "a release
ships a new ON tool" and "the owner's config lists it".

Run: python3 backend/test_enable_new_tools.py
"""
import io
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import enable_new_tools as E  # noqa: E402

PASSED, FAILED = [], []
BASE = Path(tempfile.mkdtemp(prefix="jarvis-enable-tools-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


TOML = """# the owner's settings
[voice]
enabled = true
mode = "local"

[app_control]
enabled = true

[tools]
# the owner's own list
enabled = ["calculator", "change_setting", "notes_search"]

[notes.obsidian]
vault_directory = 'C:\\Users\\pcadmin\\Documents\\Obsidian Vault'
"""


def install(name="case", body=TOML, tools=("calculator", "change_setting",
                                        "notes_search", "project_create",
                                        "work_item_add")):
    """A temp backend folder: the config plus a stub jarvis_agent with TOOLS."""
    folder = BASE / name
    folder.mkdir(parents=True, exist_ok=True)
    framework = folder / "jarvis-framework.toml"
    framework.write_text(body, encoding="utf-8")
    stub = folder / "jarvis_agent.py"
    stub.write_text("TOOLS = {\n" + "".join(f"    {t!r},\n" for t in tools) + "}\n",
                    encoding="utf-8")
    return folder, framework


def t_a_dry_run_and_a_real_run_add_only_the_named_tools():
    folder, framework = install("dry")
    before = framework.read_text(encoding="utf-8")
    code = E.main(["--backend", str(folder), "--add", "project_create,work_item_add"])
    check("a dry run exits 0", code == 0, code)
    check("... and writes nothing", framework.read_text(encoding="utf-8") == before)
    code = E.main(["--backend", str(folder), "--add", "project_create,work_item_add",
                   "--apply"])
    check("the apply exits 0", code == 0, code)
    text = framework.read_text(encoding="utf-8")
    check("... the two names are in the [tools] enabled list",
          '"project_create"' in text and '"work_item_add"' in text, text)
    check("... the owner's existing three names are kept, in order",
          text.index('"calculator"') < text.index('"change_setting"')
          < text.index('"notes_search"'), text)
    # Every line that is not the tools enabled line is untouched.
    old_lines = [ln for ln in before.splitlines() if not ln.startswith("enabled = [")]
    new_lines = [ln for ln in text.splitlines() if not ln.startswith("enabled = [")]
    check("... every other line of the file is unchanged", old_lines == new_lines,
          [ln for ln in new_lines if ln not in old_lines])
    check("... the other sections' enabled = true lines are still there",
          text.count("enabled = true") == 2, text.count("enabled = true"))
    backups = list(folder.glob("jarvis-framework.toml.before-enable-tools-*"))
    check("... a backup of the file was made", len(backups) == 1,
          [b.name for b in backups])
    check("... and the backup is the file as it was",
          len(backups) == 1 and backups[0].read_text(encoding="utf-8") == before)


def t_a_second_run_is_a_no_op():
    folder, framework = install("second")
    E.main(["--backend", str(folder), "--add", "project_create", "--apply"])
    once = framework.read_text(encoding="utf-8")
    code = E.main(["--backend", str(folder), "--add", "project_create", "--apply"])
    check("a second apply exits 0", code == 0, code)
    check("... and the file is byte-identical", framework.read_text(encoding="utf-8") == once)
    check("... and no second backup was needed",
          len(list(folder.glob("*.before-enable-tools-*"))) == 1)


def t_a_tool_the_owner_removed_stays_removed():
    # The stub knows three tools; the owner's config lists one - they took the
    # other two out on purpose. Only --add names may move.
    folder, framework = install("removed", body='[tools]\nenabled = ["calculator"]\n',
                                tools=("calculator", "change_setting", "notes_search"))
    E.main(["--backend", str(folder), "--add", "notes_search", "--apply"])
    text = framework.read_text(encoding="utf-8")
    check("a name the owner took out is NOT re-added", '"change_setting"' not in text, text)
    check("... while the requested name is added", '"notes_search"' in text, text)


def t_an_unknown_tool_is_refused_and_nothing_is_written():
    folder, framework = install("unknown")
    before = framework.read_text(encoding="utf-8")
    code = E.main(["--backend", str(folder), "--add", "not_a_tool", "--apply"])
    check("an unknown tool name exits non-zero", code == 2, code)
    check("... and the file is untouched",
          framework.read_text(encoding="utf-8") == before)


def t_a_missing_section_or_line_is_refused():
    folder, framework = install("noheader", body="[voice]\nenabled = true\n")
    check("no [tools] section is refused",
          E.main(["--backend", str(folder), "--add", "project_create", "--apply"]) == 2)
    folder2, framework2 = install("noline", body="[tools]\n# nothing here\n")
    check("a [tools] section with no enabled line is refused",
          E.main(["--backend", str(folder2), "--add", "project_create", "--apply"]) == 2)
    check("... and neither file was written",
          framework.read_text(encoding="utf-8") == "[voice]\nenabled = true\n"
          and framework2.read_text(encoding="utf-8") == "[tools]\n# nothing here\n")


def t_an_empty_add_is_refused():
    folder, framework = install("empty")
    check("--add with nothing in it is refused",
          E.main(["--backend", str(folder), "--add", ",,", "--apply"]) == 2)


def t_a_multi_line_enabled_array_is_handled():
    body = ('[tools]\nenabled = [\n  "calculator",\n  "change_setting",\n]\n'
            '\n[app_control]\nenabled = true\n')
    folder, framework = install("multiline", body=body)
    code = E.main(["--backend", str(folder), "--add", "project_create", "--apply"])
    check("a multi-line enabled array applies", code == 0, code)
    text = framework.read_text(encoding="utf-8")
    for name in ('"calculator"', '"change_setting"', '"project_create"'):
        check(f"... {name} survives", name in text, text)
    check("... and [app_control] still says enabled = true", "enabled = true" in text, text)


def t_a_repeated_add_flag_and_a_comma_list_both_work():
    folder, framework = install("repeat")
    code = E.main(["--backend", str(folder), "--add", "project_create",
                   "--add", "work_item_add", "--apply"])
    text = framework.read_text(encoding="utf-8")
    check("repeated --add flags work", code == 0
          and '"project_create"' in text and '"work_item_add"' in text, text)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
