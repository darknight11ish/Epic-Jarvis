"""test_deploy_hud_whitelist.py - the HUD whitelist deploy is rehearsed, not hand-done.

    python3 backend/test_deploy_hud_whitelist.py

WHAT THIS PROVES, in temp folders only (no live path is ever read or written):

  1. When the live `STATIC_ASSETS` is a subset of the published base with every
     shared value identical, the plan is a PURE INSERTION: the base's missing
     entry lines, in base order, before the closing brace - and the rest of the
     live file is byte-identical.
  2. One live-only key, or one differing value, REFUSES (exit 1) and writes
     nothing - that is the drift the 2026-10-25 hand-insertion argument does not
     cover.
  3. A dry run changes nothing: same bytes, no backup, no temp file.
  4. `--apply` writes atomically (one temp file plus `os.replace`), keeps the
     original bytes in `.before-<date>`, and the result compiles. An injected
     `os.replace` failure leaves the old file untouched.
  5. A corrupted or overlapping anchor is refused: two STATIC_ASSETS
     assignments, or a closing brace that shares its line with other code.
  6. `--verify-live FOLDER` only checks the sixteen face keys and the files
     they name: no ref, no git, no write.
  7. The tool's face-key list is exactly the published base's own face section,
     so the verify mode cannot silently under-check a deploy.

WHY THIS EXISTS. On 2026-10-25 sixteen whitelist keys were hand-inserted into
the owner's live HUD, and the safety argument was a measurement ("the live
table matches the base"), not a guard rail. The tool exists to make that
measurement the condition of the write; these checks prove the refusal, the
dry run and the atomic write really behave that way.
"""
from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import deploy_hud_whitelist as D  # noqa: E402

PASSED, FAILED = [], []
BASE_DIR = Path(tempfile.mkdtemp(prefix="jarvis-deploy-hud-"))

LIVE = '''#!/usr/bin/env python3
"""fixture live HUD - only for the deploy tool's tests."""
from pathlib import Path

HERE = Path(__file__).resolve().parent

SENTINEL_BEFORE = "must survive byte for byte"


def before_the_table():
    return SENTINEL_BEFORE


STATIC_ASSETS = {
    "/theme.css": ("theme.css", "text/css; charset=utf-8"),
}


def after_the_table():
    return STATIC_ASSETS["/theme.css"]
'''

BASE = '''#!/usr/bin/env python3
"""fixture published base HUD - only for the deploy tool's tests."""
from pathlib import Path

HERE = Path(__file__).resolve().parent

SENTINEL_BEFORE = "must survive byte for byte"


def before_the_table():
    return SENTINEL_BEFORE


STATIC_ASSETS = {
    # a comment the insertion must NOT carry: only the entry is copied
    "/theme.css": ("theme.css", "text/css; charset=utf-8"),
    # the face page
    "/faces.html": ("faces.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def after_the_table():
    return STATIC_ASSETS["/theme.css"]
'''

EXPECTED_INSERTION = (
    '    "/faces.html": ("faces.html", "text/html; charset=utf-8"),\n'
    '    "/app.js": ("app.js", "text/javascript; charset=utf-8"),\n'
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def case(live_text=LIVE, base_text=BASE, name="case"):
    """A temp folder holding one live jarvis_hud.py and one base file."""
    root = Path(tempfile.mkdtemp(dir=BASE_DIR, prefix=name + "-"))
    live = root / "jarvis_hud.py"
    live.write_bytes(live_text.encode("utf-8"))
    base = root / "published_jarvis_hud.py"
    base.write_bytes(base_text.encode("utf-8"))
    return root, live, base


def run(argv):
    """Run the tool's CLI and capture (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = D.main(argv)
    return code, out.getvalue(), err.getvalue()


def backups(folder):
    return sorted(p.name for p in folder.glob("*.before-*"))


def temps(folder):
    return sorted(p.name for p in folder.glob("*.tmp-*"))


def parses(path):
    try:
        ast.parse(path.read_bytes().decode("utf-8"))
        return True
    except (SyntaxError, UnicodeDecodeError):
        return False


# ---------------------------------------------------------------- checks ----

def t_exact_match_yields_a_pure_insertion():
    root, live, base = case(name="pure")
    before = live.read_bytes()
    plan = D.make_plan(live, BASE, "fixture base")

    check("the plan names the base's missing keys, in base order",
          plan.missing == ("/faces.html", "/app.js"), plan.missing)
    check("the insertion is exactly the base's missing entry lines",
          plan.insertion == EXPECTED_INSERTION, repr(plan.insertion))
    check("the new bytes are the old bytes with that one insertion",
          plan.new_bytes == before[:plan.offset]
          + EXPECTED_INSERTION.encode("utf-8") + before[plan.offset:])
    check("removing the insertion gives the original file back, byte for byte",
          plan.new_bytes.replace(EXPECTED_INSERTION.encode("utf-8"), b"", 1)
          == before)
    check("the insertion point is a line start and the brace is still alone",
          plan.offset > 0
          and before[plan.offset - 1:plan.offset] == b"\n"
          and plan.new_bytes.splitlines()[
              plan.anchor_line - 1 + len(plan.missing)] == b"}")
    check("the plan reports the byte delta the insertion adds",
          len(plan.new_bytes) - len(plan.old_bytes)
          == len(EXPECTED_INSERTION.encode("utf-8")))
    check("the plan reports the line delta the insertion adds",
          plan.new_lines - plan.old_lines == 2)
    check("the file on disk was not touched by make_plan",
          live.read_bytes() == before)
    check("the planned text parses and its table equals the base's",
          parses(live) and D.find_static_assets(
              plan.new_bytes.decode("utf-8"), "planned").assets
          == D.find_static_assets(BASE, "base").assets)

    root2, live2, base2 = case(live_text=LIVE.replace("\n", "\r\n"),
                               name="crlf")
    crlf_before = live2.read_bytes()
    crlf_plan = D.make_plan(live2, BASE, "fixture base")
    check("a CRLF live file gets CRLF insertion lines, not a mixed file",
          crlf_plan.insertion == EXPECTED_INSERTION.replace("\n", "\r\n"),
          repr(crlf_plan.insertion))
    check("... and the CRLF plan is still that file plus one insertion",
          crlf_plan.new_bytes == crlf_before[:crlf_plan.offset]
          + EXPECTED_INSERTION.replace("\n", "\r\n").encode("utf-8")
          + crlf_before[crlf_plan.offset:])


def t_one_drifted_live_key_is_refused():
    rogue = LIVE.replace(
        '    "/theme.css": ("theme.css", "text/css; charset=utf-8"),\n',
        '    "/theme.css": ("theme.css", "text/css; charset=utf-8"),\n'
        '    "/rogue.js": ("rogue.js", "text/javascript; charset=utf-8"),\n')
    check("the fixture really is LIVE plus one live-only key",
          rogue != LIVE and '"/rogue.js"' in rogue)
    root, live, base = case(live_text=rogue, name="live-only")
    before = live.read_bytes()
    code, out, err = run([str(live), "--base-file", str(base)])
    check("a live-only key is refused with exit 1", code == 1, (code, out, err))
    check("... and the refusal names the key and says nothing changed",
          "REFUSED" in err and "/rogue.js" in err
          and "Nothing was changed" in err, err)
    check("... and the live file is byte-identical afterwards",
          live.read_bytes() == before)
    check("... and --apply cannot write through the refusal",
          run([str(live), "--base-file", str(base), "--apply"])[0] == 1
          and live.read_bytes() == before and backups(root) == [])

    differs = LIVE.replace('"text/css; charset=utf-8"',
                           '"text/plain; charset=utf-8"')
    root2, live2, base2 = case(live_text=differs, name="differs")
    before2 = live2.read_bytes()
    code2, out2, err2 = run([str(live2), "--base-file", str(base2)])
    check("one differing value is refused with exit 1", code2 == 1, (code2, err2))
    check("... and the refusal shows both values",
          "differs" in err2 and "text/plain" in err2 and "text/css" in err2, err2)
    check("... and the live file is byte-identical afterwards",
          live2.read_bytes() == before2)


def t_a_dry_run_changes_nothing():
    root, live, base = case(name="dry-run")
    before = live.read_bytes()
    code, out, err = run([str(live), "--base-file", str(base)])
    check("a clean dry run exits 0", code == 0, (code, out, err))
    check("... and prints the exact insertion",
          EXPECTED_INSERTION in out, out)
    check("... and says it is a dry run",
          "DRY RUN" in out and "nothing was written" in out, out)
    check("... and leaves the live file byte-identical",
          live.read_bytes() == before)
    check("... and writes no backup and no temp file",
          backups(root) == [] and temps(root) == [],
          (backups(root), temps(root)))


def t_apply_is_atomic_and_keeps_a_backup():
    root, live, base = case(name="apply")
    before = live.read_bytes()
    plan = D.make_plan(live, BASE, "fixture base")
    code, out, err = run([str(live), "--base-file", str(base), "--apply",
                          "--date", "2026-10-25"])
    check("a clean --apply exits 0", code == 0, (code, out, err))
    check("... and writes exactly the planned bytes",
          live.read_bytes() == plan.new_bytes)
    backup = live.with_name(live.name + ".before-2026-10-25")
    check("... and keeps the original bytes in the dated backup",
          backup.is_file() and backup.read_bytes() == before)
    check("... and leaves no temp file behind", temps(root) == [], temps(root))
    check("... and prints the backup, the atomic write and the pass",
          "BACKUP" in out and "os.replace" in out and "PASS" in out, out)
    check("... and the written file parses and matches the base's table",
          parses(live) and D.find_static_assets(
              live.read_bytes().decode("utf-8"), "written").assets
          == D.find_static_assets(BASE, "base").assets)
    check("a second --apply is a no-op and writes nothing",
          run([str(live), "--base-file", str(base), "--apply"])[0] == 0
          and live.read_bytes() == plan.new_bytes
          and len(backups(root)) == 1)

    collide_root, collide_live, collide_base = case(name="backup-collision")
    collide_before = collide_live.read_bytes()
    stale = collide_live.with_name(collide_live.name + ".before-2026-10-25")
    stale.write_bytes(b"an older, different backup")
    code5, out5, err5 = run([str(collide_live), "--base-file", str(collide_base),
                             "--apply", "--date", "2026-10-25"])
    second = collide_live.with_name(
        collide_live.name + ".before-2026-10-25-1")
    check("--apply never overwrites a different existing backup",
          code5 == 0 and stale.read_bytes() == b"an older, different backup",
          (code5, err5))
    check("... and the new backup takes the next counter name",
          second.is_file() and second.read_bytes() == collide_before)

    atomic = root / "atomic_target.py"
    atomic.write_bytes(b"old bytes")
    try:
        with mock.patch.object(D.os, "replace", side_effect=OSError("injected")):
            D._atomic_write(atomic, b"new bytes")
        raised = False
    except OSError:
        raised = True
    check("an os.replace failure raises instead of half-writing", raised)
    check("... and the original file is untouched", atomic.read_bytes() == b"old bytes")
    check("... and the temp file is cleaned up", temps(root) == [], temps(root))

    race_root, race_live, race_base = case(name="race")
    race_plan = D.make_plan(race_live, BASE, "fixture base")
    race_live.write_bytes(race_plan.old_bytes + b"\n# changed after the plan\n")
    changed = race_live.read_bytes()
    try:
        D.apply_plan(race_plan, "2026-10-25")
        refused = False
    except D.Refused:
        refused = True
    check("a live file that changed after the plan is refused at write time",
          refused)
    check("... and that changed file is left exactly as it was, with no backup",
          race_live.read_bytes() == changed and backups(race_root) == [])


def t_a_corrupted_or_overlapping_anchor_is_refused():
    duplicate = LIVE + "\nSTATIC_ASSETS = {}\n"
    root, live, base = case(live_text=duplicate, name="duplicate")
    before = live.read_bytes()
    code, out, err = run([str(live), "--base-file", str(base), "--apply"])
    check("two STATIC_ASSETS assignments are refused (ambiguous anchor)",
          code == 1 and "REFUSED" in err and "2 module-level" in err,
          (code, err))
    check("... and nothing is written", live.read_bytes() == before
          and backups(root) == [])

    trailing = LIVE.replace("}\n", "}  # keep this comment\n", 1)
    check("the fixture really moved the closing brace", trailing != LIVE)
    root2, live2, base2 = case(live_text=trailing, name="trailing")
    before2 = live2.read_bytes()
    code2, out2, err2 = run([str(live2), "--base-file", str(base2), "--apply"])
    check("a closing brace that shares its line with other text is refused",
          code2 == 1 and "not alone on its line" in err2, (code2, err2))
    check("... and nothing is written", live2.read_bytes() == before2
          and backups(root2) == [])

    not_literal = LIVE.replace("STATIC_ASSETS = {",
                               "STATIC_ASSETS = dict([", 1)
    not_literal = not_literal.replace(
        '    "/theme.css": ("theme.css", "text/css; charset=utf-8"),\n}\n',
        '    ("/theme.css", ("theme.css", "text/css; charset=utf-8")),\n])\n')
    root3, live3, base3 = case(live_text=not_literal, name="not-literal")
    code3, out3, err3 = run([str(live3), "--base-file", str(base3)])
    check("a STATIC_ASSETS that is not a dict literal is refused",
          code3 == 1 and "not a dict literal" in err3, (code3, err3))


def t_face_keys_match_the_published_base():
    base_path = REPO / "jarvis-backend" / "jarvis_hud.py"
    assets = D.find_static_assets(
        base_path.read_bytes().decode("utf-8"), "published base").assets
    order = list(assets)
    check("the published base still carries the face page key",
          D.FACE_ANCHOR in order)
    start = order.index(D.FACE_ANCHOR) if D.FACE_ANCHOR in order else len(order)
    check("the tool's face-key list is exactly the base's face section, in order",
          tuple(order[start:]) == D.FACE_KEYS, tuple(order[start:]))
    check("the face section is sixteen keys - the count the hand insertion added",
          len(D.FACE_KEYS) == 16)


def _face_folder(name, drop_key=None):
    folder = Path(tempfile.mkdtemp(dir=BASE_DIR, prefix=name + "-"))
    entries = "".join(
        f"    {key!r}: (\"face.bin\", \"text/plain\"),\n"
        for key in D.FACE_KEYS if key != drop_key)
    (folder / "jarvis_hud.py").write_bytes(
        ("STATIC_ASSETS = {\n" + entries + "}\n").encode("utf-8"))
    return folder


def t_verify_live_checks_keys_and_files_only():
    folder = _face_folder("verify-ok")
    (folder / "face.bin").write_bytes(b"face")
    before = (folder / "jarvis_hud.py").read_bytes()
    code, out, err = run(["--verify-live", str(folder),
                          "--repo", str(folder / "no-such-repo"),
                          "--ref", "no-such-ref"])
    check("--verify-live passes with every face key and its file",
          code == 0 and "PASS" in out, (code, err))
    check("... and needs no git ref (it ignored both --repo and --ref)", code == 0)
    check("... and never writes", (folder / "jarvis_hud.py").read_bytes() == before
          and backups(folder) == [])

    missing_key = _face_folder("verify-key", drop_key=D.FACE_KEYS[-1])
    (missing_key / "face.bin").write_bytes(b"face")
    code2, out2, err2 = run(["--verify-live", str(missing_key)])
    check("--verify-live fails when one face key is missing",
          code2 == 1 and "MISSING KEY" in out2 and D.FACE_KEYS[-1] in out2,
          (code2, out2))

    missing_file = _face_folder("verify-file")
    code3, out3, err3 = run(["--verify-live", str(missing_file)])
    check("--verify-live fails when a served file is absent",
          code3 == 1 and "MISSING FILE" in out3, (code3, out3))

    no_hud = Path(tempfile.mkdtemp(dir=BASE_DIR, prefix="verify-empty-"))
    code4, out4, err4 = run(["--verify-live", str(no_hud)])
    check("--verify-live on a folder without jarvis_hud.py exits 2",
          code4 == 2 and "ERROR" in err4, (code4, err4))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
