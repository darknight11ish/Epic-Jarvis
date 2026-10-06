"""A new [autonomy.tiers] line must reach the owner's EXISTING config file.

    python3 backend/test_config_tiers_merge.py

THE FAILURE THIS PROVES, IN THE OWNER'S OWN WORDS (2026-10-06)

`scripts/apply-patches.ps1` never overwrote `jarvis-framework.toml` - it holds
decisions only the owner makes - and it did nothing but PRINT the difference.
So a patch could add an action whose tier is an `[autonomy.tiers]` line, and
that line never reached a file that already existed. Two actions arrived that
way in pull request #79 (`read_web_page` and `chat_card_pin`), and the owner's
patcher run ended `DONE WITH PROBLEMS - do not trust this update yet` with
`test_gate_names.py` at `6 passed, 4 failed`:

    FAIL  every action in the repository's shipped [autonomy.tiers] has a
          line in the live one
          in ...\\backend\\rebuilt\\jarvis-framework.toml but not in
             ...\\Desktop program\\jarvis-framework.toml:
          chat_card_pin
          read_web_page
          (80 live tier lines, 82 shipped, 80 in both)

The repository was right and the live file was stale. Nothing was unsafe (a
missing tier takes `unknown_action_tier`, which is "ask"), but the feature
could not work as written, and four checks were red on the owner's only PC.

WHAT IS CHECKED HERE

  1. `backend/_apply_toml_tiers.py`, on a config built to catch a careless
     one, ADDS the missing line and touches nothing else: a CRLF file, a
     comment that NAMES `[autonomy.tiers]` without being it, a tier the owner
     set to "never", one he set to a value the repository disagrees with, and
     a `[tools].enabled` list that is not the repository's. The only lines
     that may change are the ones it adds.
  2. `scripts/apply-patches.ps1` actually CALLS it, on the file it decided is
     the one in use, and reads the result back. Without that call this whole
     fix is a script nobody runs, which is exactly what
     `tools/sync-framework-tiers.py` was: correct, and never invoked.

A check that only proved (1) would pass on the very script that caused the
owner's failure, so (2) is here beside it.

WHY THE PATCHER IS NOT RUN HERE

It was, while this suite was being written, and the harness
(`test_apply_outcomes.mini_repo`) symlinks this repository's whole `rebuilt/`
FOLDER into the throwaway repository it builds - so writing "the shipped
config" in there wrote THIS repository's own copy, through the link. It was
caught by `git diff`, reported, and put back with `git checkout`; that is why
(1) drives the merge script directly and (2) reads the script's text. Running
the real patcher against a real backend is `test_apply_outcomes.py`'s job, and
running it against the OWNER's backend is the thing every rule here forbids.

Needs Python 3.11+ for tomllib (a skip, never a silent pass, without it).
Standard library only.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

try:
    import tomllib
except ImportError:                                  # Python < 3.11
    try:
        import tomli as tomllib                      # type: ignore
    except ImportError:
        tomllib = None

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


#: A live config as an owner's really is: written by an earlier version of the
#: shipped file, and edited by him since. `read_web_page` is the line this
#: repository has and this file does not - the whole point.
#:
#: Every other difference is deliberate and must survive: a tier he set to
#: "never" (nothing may loosen it), a tier he set to "auto" where the shipped
#: file says "ask" (looser - a decision that is HIS, and
#: tools/sync-framework-tiers.py's to report rather than this merge's to make),
#: a tier that is simply different, a [tools].enabled list that is not the
#: repository's, and a comment that names [autonomy.tiers] as prose.
LIVE_OLD = """\
# the owner's own settings file
[autonomy]
unknown_action_tier = "ask"

# a comment that NAMES [autonomy.tiers] without being it
# (the merge must not be fooled by prose)
[autonomy.tiers]
send_email = "never"
draft_email = "auto"
chat_card_pin = "ask"
read_files_readonly = "ask"

[tools]
enabled = ["web_search", "read_files"]

[self_modification]
enabled = true
"""

#: What the repository ships. Exactly one key the live file lacks.
SHIPPED = """\
[autonomy]
unknown_action_tier = "ask"

[autonomy.tiers]
send_email = "ask"
draft_email = "ask"
chat_card_pin = "ask"
read_files_readonly = "auto"
read_web_page = "ask"

[tools]
enabled = ["web_search"]
"""

#: The lines the merge adds: five comment lines and one tier line.
ADDED_LINES = 6


def _tiers(path: Path) -> dict:
    return (tomllib.loads(path.read_text(encoding="utf-8-sig")).get("autonomy") or {}) \
        .get("tiers") or {}


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="jarvis-tiers-")).resolve()


def t_the_merge_adds_only_what_is_missing():
    """Drive backend/_apply_toml_tiers.py on a config built to trip a careless one."""
    source = HERE / "_apply_toml_tiers.py"
    check("backend/_apply_toml_tiers.py ships in this repository", source.is_file())
    if not source.is_file():
        return
    if tomllib is None:
        return skip("no tomllib/tomli, so the result could not be read back")

    d = _tmp()
    # The script reads the shipped config from beside itself (backend/rebuilt/),
    # so the WHOLE thing is staged in the throwaway folder: the script's own
    # copy, and a shipped file this suite controls. Never the repository's -
    # the first version of this test wrote through a symlinked `rebuilt/` and
    # overwrote backend/rebuilt/jarvis-framework.toml. Measured, not guessed.
    stage = d / "backend"
    (stage / "rebuilt").mkdir(parents=True)
    merger = stage / source.name
    merger.write_bytes(source.read_bytes())
    (stage / "rebuilt" / "jarvis-framework.toml").write_text(
        SHIPPED, encoding="utf-8", newline="\n")

    live = d / "jarvis-framework.toml"
    # CRLF on purpose: the owner's file is written on Windows, and this must
    # not rewrite the endings of the 1,600 other lines.
    crlf = LIVE_OLD.replace("\n", "\r\n")
    live.write_bytes(crlf.encode("utf-8"))
    r = subprocess.run([sys.executable, str(merger), "--apply", str(live)],
                       capture_output=True, text=True, timeout=120)

    raw = live.read_bytes()
    after = raw.decode("utf-8-sig")
    tiers = _tiers(live)
    was = LIVE_OLD.splitlines()
    now = after.replace("\r\n", "\n").splitlines()
    added = [line for line in now if line not in set(was)]

    check("the merge succeeds", r.returncode == 0, r.stdout + r.stderr)
    check("it adds the line the repository has and the live file lacked",
          tiers.get("read_web_page") == "ask", tiers)
    check("it changes nothing already there",
          tiers.get("send_email") == "never" and tiers.get("draft_email") == "auto"
          and tiers.get("read_files_readonly") == "ask"
          and tiers.get("chat_card_pin") == "ask", tiers)
    check("the owner's own [tools] list is untouched",
          'enabled = ["web_search", "read_files"]' in after, after)
    check("every line he had is still there, in order",
          [line for line in after.replace("\r\n", "\n").splitlines()
           if line in set(was)] == was, after)
    check("the only lines added are the merge's own comment block and the tier",
          len(added) == ADDED_LINES
          and added[0].startswith("# Added ") and added[-1].startswith("read_web_page"),
          added)
    check("the prose comment naming [autonomy.tiers] did not fool it",
          after.count("# a comment that NAMES [autonomy.tiers] without being it") == 1,
          after)
    check("the line endings of every other line survive",
          raw.count(b"\r") == crlf.count("\r") + ADDED_LINES,
          f"{raw.count(chr(13).encode())} CRLF lines for {crlf.count(chr(13))} before")
    check("a copy from before the change is kept beside it",
          len(list(d.glob("jarvis-framework.toml.backup-*"))) == 1
          and list(d.glob("jarvis-framework.toml.backup-*"))[0].read_bytes()
          == crlf.encode("utf-8"),
          [p.name for p in d.glob("*.backup-*")])

    # Run it again: nothing left to add, and the file must not be rewritten.
    second = live.read_bytes()
    r2 = subprocess.run([sys.executable, str(merger), "--apply", str(live)],
                        capture_output=True, text=True, timeout=120)
    check("running it again adds nothing and rewrites nothing",
          r2.returncode == 0 and live.read_bytes() == second
          and "Nothing to add" in r2.stdout, r2.stdout + r2.stderr)

    # And on a file with no [autonomy.tiers] at all: refuse, change nothing.
    bare = d / "bare.toml"
    bare.write_text('[tools]\nenabled = ["web_search"]\n', encoding="utf-8")
    before = bare.read_bytes()
    r3 = subprocess.run([sys.executable, str(merger), "--apply", str(bare)],
                        capture_output=True, text=True, timeout=120)
    check("a file with no [autonomy.tiers] is refused, not invented into",
          r3.returncode == 2 and bare.read_bytes() == before,
          r3.stdout + r3.stderr)


def t_the_patcher_calls_the_merge_on_the_file_in_use():
    """The half that was missing: a correct script nobody runs changes nothing."""
    ps1 = REPO / "scripts" / "apply-patches.ps1"
    check("scripts/apply-patches.ps1 is where this repository keeps it", ps1.is_file())
    if not ps1.is_file():
        return
    text = ps1.read_text(encoding="utf-8", errors="replace")
    # Only the step that decides the settings file, so a mention anywhere else
    # (a comment about the shape of the fix, say) cannot satisfy this.
    m = re.search(r"^# --- 4\. the settings file.*?(?=^# --- 5\.)", text, re.S | re.M)
    check("the settings-file step of the script was found (test setup)", bool(m))
    # NOT an early return: with no step found, every check below must still
    # report, so the failure names what is wrong rather than one setup line.
    step = m.group(0) if m else ""
    lines = [ln.strip() for ln in step.splitlines()]
    # The four things that make it a CALL rather than a comment about one:
    # the real Python, the merger, --apply, and the file it decided is in use.
    calls = [ln for ln in lines if "$py.Exe" in ln and "$tierMerger" in ln
             and "--apply" in ln and "$cfgInUse" in ln]
    check("the patcher RUNS the merge, on the file it decided is the one in use",
          len(calls) == 1,
          "\n        ".join(ln for ln in lines if "$tierMerger" in ln))
    check("... and the merge ships in backend/, which the patcher looks in "
          "(backend\\_apply_toml_tiers.py)",
          (HERE / "_apply_toml_tiers.py").is_file()
          and 'Join-Path $PatchDir' in step,
          "the call and the file must be in the same place")
    check("... and the result is read back, not taken on trust",
          "stillMissing" in step and "$tierMerged" in step,
          "nothing reads the file afterwards")
    check("a missing tier line that could not be added ends the run as a PROBLEM",
          "Add-Problem" in step and "[autonomy.tiers] line(s)" in step,
          "an unadded tier line must not pass silently")
    check("the owner's other settings are still only PRINTED, never merged",
          "_config_diff.py" in step
          and "stays yours to add" in step,
          "the step must still refuse to decide [tools].enabled and the rest")


def main():
    for fn in (t_the_merge_adds_only_what_is_missing,
               t_the_patcher_calls_the_merge_on_the_file_in_use):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    line = f"\n{len(PASSED)} passed, {len(FAILED)} failed"
    if SKIPPED:
        line += f", {len(SKIPPED)} skipped"
    print(line)
    if SKIPPED:
        print("skipped (not proven here): " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
