#!/usr/bin/env python3
"""test_feature_controls.py - the bite test for the feature-controls matrix.

The owner's requirement is only real if the matrix can FAIL. This suite proves
that for `tools/check_feature_controls.py`:

1. the real tree passes (the matrix agrees with the real sources);
2. a deliberately removed typed phrase makes it fail;
3. a deliberately removed feature row makes it fail (no silent omission);
4. an unknown feature row makes it fail (a new catalogue entry must be added);
5. a deliberately removed settings row makes it fail;
6. a Settings page that lost a toggle row makes it fail;
7. `--strict` prints the known gaps and still exits 0 on a clean tree.

It copies only the files the checker reads into a temporary tree, so nothing
outside this test's own directory is touched. Run: python -B backend/test_feature_controls.py
"""
import json
import os
import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "tools" / "check_feature_controls.py"
SOURCES = [
    "backend/jarvis_feature_catalogue.py",
    "backend/jarvis_settings_registry.py",
    "backend/jarvis_quick.py",
    "contract/feature-controls.json",
    "jarvis-desktop/src/settings.html",
    "jarvis-desktop/src/settings-catalog.js",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/net/SettingsCatalog.kt",
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt",
]


def copy_tree(tmp):
    """The surface/source files, plus the importable backend modules.

    The backend tree holds ~640 files, 410 of them tests. Copying all of them
    for every bite case made the CI backend job exceed its 40-minute limit, so
    (a) only the ~230 importable modules are copied, and (b) the temporary
    tree is built ONCE; each case restores just the mutated surface files.
    """
    for rel in SOURCES:
        dest = tmp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dest)
    (tmp / "backend").mkdir(parents=True, exist_ok=True)
    for src in (ROOT / "backend").glob("*.py"):
        if src.name.startswith("test_") or src.name == "run_suites.py":
            continue
        shutil.copyfile(src, tmp / "backend" / src.name)
    return tmp


def reset_surfaces(tmp):
    """Undo any mutation from the previous bite case (backend never changes)."""
    shutil.copyfile(ROOT / "contract/feature-controls.json", tmp / "contract/feature-controls.json")
    shutil.copyfile(ROOT / "jarvis-desktop/src/settings.html", tmp / "jarvis-desktop/src/settings.html")


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_feature_controls", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# run_suites.py runs every suite against a staged backend with a throwaway
# OPENJARVIS_HOME/config. The contract checks the SHIPPED grammar, not a run's
# isolation state; a choice phrase (custom voices) resolves differently when a
# suite inherits that throwaway config. This suite is read-only, so make the
# check hermetic and deterministic the same way a fresh process is.
for _k in ("OPENJARVIS_HOME", "JARVIS_HOME", "JARVIS_CONFIG_DIR", "OPENJARVIS_CONFIG_DIR",
           "JARVIS_FRAMEWORK_TOML", "JARVIS_LOG_DIR", "JARVIS_BACKEND"):
    os.environ.pop(_k, None)

CHECKER = _load_checker()


class _Result:
    def __init__(self, returncode, output):
        self.returncode = returncode
        self.stdout = output
        self.stderr = ""


def run(root, *args):
    """Run the checker IN-PROCESS: one Python startup, ten bite cases.

    Fresh subprocesses each cold-import the backend and took ~8 minutes on CI,
    which pushed the 40-minute backend job over its limit. The checker is a
    pure function of the tree, so importing it once and calling main() per
    case is equivalent and takes seconds.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = CHECKER.main(["--root", str(root), *args])
    return _Result(code, buf.getvalue())


def read_json(root):
    return json.loads((root / "contract/feature-controls.json").read_text(encoding="utf-8"))


def write_json(root, doc):
    (root / "contract/feature-controls.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    passed = failed = 0

    def check(name, ok, why=""):
        nonlocal passed, failed
        if ok:
            print("ok    " + name); passed += 1
        else:
            print("FAIL  " + name + (" - " + why if why else "")); failed += 1

    with tempfile.TemporaryDirectory(prefix="feature-controls-") as td:
        tmp = Path(td)
        copy_tree(tmp)

        clean = run(tmp)
        check("the real tree passes the matrix check", clean.returncode == 0, clean.stdout + clean.stderr)

        strict = run(tmp, "--strict")
        check("--strict prints the gaps and still exits 0",
              strict.returncode == 0 and "GAP" in strict.stdout and "NOT-ENFORCED" in strict.stdout, strict.stdout)

        doc = read_json(tmp)
        feature = next(f for f in doc["features"] if f["status"] == "enforced")
        feature["control"]["turn_on"] = None
        write_json(tmp, doc)
        phrase = run(tmp)
        check("a deliberately removed typed phrase fails",
              phrase.returncode == 1 and feature["id"] in phrase.stdout, phrase.stdout + phrase.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        victim = doc["features"][0]["id"]
        doc["features"] = [f for f in doc["features"] if f["id"] != victim]
        write_json(tmp, doc)
        dropped = run(tmp)
        check("a deliberately removed feature row fails (no silent omission)",
              dropped.returncode == 1 and victim in dropped.stdout, dropped.stdout + dropped.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        doc["features"].append({"id": "a-brand-new-feature", "name": "New", "status": "enforced",
                                "owner": "none-needed", "reason": "x", "control": {}})
        write_json(tmp, doc)
        unknown = run(tmp)
        check("an unknown new feature fails loudly",
              unknown.returncode == 1 and "a-brand-new-feature" in unknown.stdout, unknown.stdout + unknown.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        victim = doc["setting_rows"][0]["id"]
        doc["setting_rows"] = [r for r in doc["setting_rows"] if r["id"] != victim]
        write_json(tmp, doc)
        row_gone = run(tmp)
        check("a deliberately removed settings row fails",
              row_gone.returncode == 1 and victim in row_gone.stdout, row_gone.stdout + row_gone.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        victim = doc["multi_field"][0]["id"]
        doc["multi_field"] = [r for r in doc["multi_field"] if r["id"] != victim]
        write_json(tmp, doc)
        mf_gone = run(tmp)
        check("a deliberately removed multi-field row fails",
              mf_gone.returncode == 1 and "multi-field rows were added or removed" in mf_gone.stdout,
              mf_gone.stdout + mf_gone.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        victim = doc["settings_only"][0]["feature"]
        doc["settings_only"] = [r for r in doc["settings_only"] if r["feature"] != victim]
        write_json(tmp, doc)
        so_gone = run(tmp)
        check("a deliberately removed Settings-only allowlist entry fails",
              so_gone.returncode == 1 and victim in so_gone.stdout, so_gone.stdout + so_gone.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        doc["features"][0].pop("label", None)
        write_json(tmp, doc)
        no_label = run(tmp)
        check("a deliberately removed label fails",
              no_label.returncode == 1 and "label" in no_label.stdout.lower(), no_label.stdout + no_label.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        lights = next(f for f in doc["features"] if f["id"] == "lights")
        lights["control"]["turn_on"] = "speak faster"
        write_json(tmp, doc)
        wrong_words = run(tmp)
        check("a feature phrase that changes a DIFFERENT setting fails",
              wrong_words.returncode == 1 and "lights" in wrong_words.stdout
              and "not this feature's own control" in wrong_words.stdout,
              wrong_words.stdout + wrong_words.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        command = next(f for f in doc["features"] if f["id"] == "typing")
        command["name"] = "Picture mode"
        command["control"]["turn_on"] = "turn on Picture mode"
        write_json(tmp, doc)
        command_change = run(tmp)
        check("a Command-Only title that changes a setting fails",
              command_change.returncode == 1 and "typing" in command_change.stdout
              and "changes a setting" in command_change.stdout,
              command_change.stdout + command_change.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        multi = doc["multi_field"][0]
        phrase = next(p for p in multi["phrases"] if p.get("resolved"))
        phrase["resolved"] = False
        write_json(tmp, doc)
        stale_multi = run(tmp)
        check("a stale multi-field resolved flag fails",
              stale_multi.returncode == 1 and multi["id"] in stale_multi.stdout
              and "resolved=" in stale_multi.stdout,
              stale_multi.stdout + stale_multi.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        switchable = next(f for f in doc["features"]
                          if f["label"].startswith("Switchable") and f["id"] == "email-read")
        switchable["control"]["turn_on"] = "this sentence is not in the grammar"
        write_json(tmp, doc)
        unresolved = run(tmp)
        check("a Switchable/Adjustable phrase that does not resolve fails",
              unresolved.returncode == 1 and "email-read" in unresolved.stdout
              and "does not resolve" in unresolved.stdout,
              unresolved.stdout + unresolved.stderr)

        reset_surfaces(tmp)
        doc = read_json(tmp)
        planned = next(f for f in doc["features"] if f["id"] == "wake-word")
        planned.pop("label_note", None)
        write_json(tmp, doc)
        no_note = run(tmp)
        check("a planned Switchable row without a label_note fails",
              no_note.returncode == 1 and "wake-word" in no_note.stdout
              and "label_note" in no_note.stdout,
              no_note.stdout + no_note.stderr)

        reset_surfaces(tmp)
        html = tmp / "jarvis-desktop/src/settings.html"
        text = html.read_text(encoding="utf-8")
        html.write_text(text.replace('id="follow-system"', 'id="not-the-row"', 1), encoding="utf-8")
        page_gone = run(tmp)
        check("a Settings page that lost a toggle row fails",
              page_gone.returncode == 1 and "follow-system" in page_gone.stdout, page_gone.stdout + page_gone.stderr)

    print("\nfeature controls: %d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
