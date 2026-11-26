"""test_replace_live_gate_from_base.py - proves the one-shot gate replacement
is safe, on a COPY of the live file in a temp folder.

`tools/replace_live_gate_from_base.py` exists because the owner's live
`jarvis_gate.py` is a lineage nobody can identify: the repair tool refuses it
by hash, and hand-patching rows into it is exactly what the 2026-11-25 ruling
(Q3) forbids. The tool replaces it with the published base - once, with the
old file kept - and then the patch stack can be applied to a recognised file
again.

WHAT IS PROVED HERE, and why each one matters:

  * REFUSAL WRITES NOTHING. A live file whose SHA-256 is not the one the tool
    (and the PR) recorded is refused before any read of the base is used, and
    the bytes are unchanged afterwards. This is the guard the whole thing
    stands on: the tool is allowed to be wrong about the future, never about
    which file it is about to overwrite.
  * THE BACKUP HOLDS THE OLD BYTES. The one write keeps the file it replaces.
    A replacement that loses the old gate cannot be undone.
  * THE WRITTEN FILE IS THE BASE, AND IT RE-IMPORTS. A fresh interpreter
    imports the file that now sits on disk and answers for the two rows the
    live gate never had: `cancel_scheduled` (cardless) and `github_mode` (its
    own risk row and tool row).
  * A BASE THAT DOES NOT CARRY THEM IS ROLLED BACK. The check is not
    decoration: a base with the two rows removed makes the tool put the old
    live bytes back and say so.
  * AN EXISTING BACKUP IS NEVER OVERWRITTEN, and an already-replaced file is
    the idempotent no-op.

No case touches the real live folder or `jarvis-backend/jarvis_gate.py`: the
temp folder is built from the repository's own base, with the live file's old
timeout value (180) as the marker that makes it a different file.

Run: python -B backend/test_replace_live_gate_from_base.py
"""
import hashlib
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "replace_live_gate_from_base.py"
BASE = REPO / "jarvis-backend" / "jarvis_gate.py"
FRAMEWORK = REPO / "jarvis-backend" / "jarvis_framework.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def load_tool():
    spec = importlib.util.spec_from_file_location("replace_gate", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["replace_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_text() -> str:
    return BASE.read_text(encoding="utf-8")


def live_text() -> str:
    """The base with the one value the old live gate still carried changed.

    180 is the value the published base had before 89927a5c9 (ten minutes),
    which 88581e9cd then raised to fifteen - a byte-level difference from
    today's base that imports and runs, so it stands in for the measured live
    file without committing 236,453 bytes of a drifted install to the repo.
    """
    old = '_cfg("autonomy", "approval_timeout_seconds", 900)))'
    new = '_cfg("autonomy", "approval_timeout_seconds", 180)))'
    text = base_text()
    if old not in text:
        raise RuntimeError("this suite needs the base's timeout line to build "
                           "a different live file; it moved")
    return text.replace(old, new, 1)


def a_live_folder(gate: str | bytes | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="replace-gate-"))
    text = gate if gate is not None else live_text()
    (d / "jarvis_gate.py").write_bytes(
        text.encode("utf-8") if isinstance(text, str) else text)
    shutil.copy2(FRAMEWORK, d / "jarvis_framework.py")
    return d


def without_the_two_rows(text: str) -> str:
    """`text` with the cancel_scheduled / github_mode update blocks removed.

    A base like this still imports; it simply answers neither row, which is
    exactly the failure the re-import check exists to catch. The blocks are
    cut by their own parentheses, never by line numbers.
    """
    out, i = [], 0
    lines = text.splitlines(True)
    while i < len(lines):
        line = lines[i]
        if (line.startswith("_RISK.update({")
                or line.startswith("_TOOL_ACTIONS.update({")
                or line.startswith("_NO_RULE_FROM_DENIAL = _NO_RULE_FROM_DENIAL")):
            block = [line]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if lines[i].rstrip() == "})" or (
                        "| {" in line and lines[i].rstrip() == "}"):
                    i += 1
                    break
                i += 1
            body = "".join(block)
            if '"cancel_scheduled"' in body or '"github_mode"' in body:
                continue
            out.extend(block)
            continue
        out.append(line)
        i += 1
    return "".join(out)


def run(mod, folder: Path, **kwargs):
    lines = []
    code = mod.replace_gate(folder, out=lines.append, **kwargs)
    return code, "\n".join(lines)


def main() -> int:
    mod = load_tool()
    base = BASE.read_bytes()
    base_sha = hashlib.sha256(base).hexdigest()
    live = live_text()
    live_sha = hashlib.sha256(live.encode("utf-8")).hexdigest()

    check("the recorded live hash is a sha256",
          len(mod.LIVE_GATE_SHA256) == 64
          and all(c in "0123456789abcdef" for c in mod.LIVE_GATE_SHA256),
          mod.LIVE_GATE_SHA256)
    check("the recorded base hash is a sha256",
          len(mod.BASE_GATE_SHA256) == 64
          and all(c in "0123456789abcdef" for c in mod.BASE_GATE_SHA256),
          mod.BASE_GATE_SHA256)
    check("the replacement keeps the two rows the ruling asks for",
          tuple(mod._MUST_HAVE) == ("cancel_scheduled", "github_mode"),
          repr(mod._MUST_HAVE))
    check("the tool measures the base's approval model rather than guessing it",
          "countdown" in mod.approval_model_note(base)
          and mod.approval_model_note(b"waited_until\n") == "")

    # 1. The refusal path: a file that is not the one measured.
    refused = a_live_folder()
    before = sha(refused / "jarvis_gate.py")
    code, out = run(mod, refused, expected_live_sha="0" * 64, apply=True,
                    day="2026-11-26")
    check("a live file whose hash is not the recorded one is refused",
          code == 2, out)
    check("... its bytes are unchanged",
          sha(refused / "jarvis_gate.py") == before)
    check("... no backup was made",
          not list(refused.glob("jarvis_gate.py.bak.*")))
    check("... and the refusal names the hash it found and the one it needs",
          before in out and "0" * 64 in out, out)

    # 2. Check mode writes nothing.
    check_only = a_live_folder()
    before = sha(check_only / "jarvis_gate.py")
    code, out = run(mod, check_only, expected_live_sha=before,
                    expected_base_sha=base_sha, apply=False)
    check("a check-only run accepts the measured file", code == 0, out)
    check("... and writes nothing",
          sha(check_only / "jarvis_gate.py") == before)
    check("... and makes no backup",
          not list(check_only.glob("jarvis_gate.py.bak.*")))
    check("... and says it was a check", "check only" in out, out)
    check("... and names the base's older approval model, so it is not a surprise",
          "countdown model" in out and "NOT in" in out, out)

    # 3. The write: backup, base bytes, re-import.
    done = a_live_folder(live)
    before = sha(done / "jarvis_gate.py")
    code, out = run(mod, done, expected_live_sha=before,
                    expected_base_sha=base_sha, apply=True, day="2026-11-26")
    check("the measured file is replaced", code == 0, out)
    backup = done / "jarvis_gate.py.bak.2026-11-26"
    check("... a dated backup is created", backup.is_file())
    check("... the backup holds the old bytes exactly",
          backup.is_file() and sha(backup) == before, out)
    check("... the live file is now the base byte for byte",
          sha(done / "jarvis_gate.py") == base_sha)
    ok, detail = mod.reimport_check(done)
    check("... a fresh interpreter imports it and finds cancel_scheduled",
          ok and "cancel_scheduled" in detail, detail)
    check("... and github_mode's own rows", ok and "github_mode" in detail,
          detail)

    # 4. The re-import check can fail, and the rollback puts the old file back.
    rollback = a_live_folder()
    before = sha(rollback / "jarvis_gate.py")
    broken = without_the_two_rows(base_text())
    check("the doctored base really lacks both rows",
          '"cancel_scheduled": "auto"' not in broken
          and '"github_mode": "github_mode"' not in broken
          and '"github_mode": ("yes"' not in broken)
    broken_base = rollback / "base-without-rows.py"
    broken_base.write_bytes(broken.encode("utf-8"))
    code, out = run(mod, rollback, base_path=broken_base,
                    expected_live_sha=before,
                    expected_base_sha=sha(broken_base), apply=True,
                    day="2026-11-26")
    check("a base that does not carry the two rows is refused", code == 2, out)
    check("... the old live bytes are put back",
          sha(rollback / "jarvis_gate.py") == before)
    check("... and the backup is kept",
          (rollback / "jarvis_gate.py.bak.2026-11-26").is_file())
    check("... and the refusal says the re-import check failed",
          "re-import" in out and "put back" in out, out)

    # 5. A backup is never overwritten.
    occupied = a_live_folder()
    before = sha(occupied / "jarvis_gate.py")
    existing = occupied / "jarvis_gate.py.bak.2026-11-26"
    existing.write_bytes(b"an older backup")
    code, out = run(mod, occupied, expected_live_sha=before,
                    expected_base_sha=base_sha, apply=True, day="2026-11-26")
    check("an existing backup name makes the tool refuse", code == 2, out)
    check("... the old backup is untouched",
          existing.read_bytes() == b"an older backup")
    check("... and the live file is untouched",
          sha(occupied / "jarvis_gate.py") == before)

    # 6. An already-replaced file is the no-op, not a second backup.
    already = a_live_folder(base)
    code, out = run(mod, already, expected_live_sha=base_sha,
                    expected_base_sha=base_sha, apply=True, day="2026-11-26")
    check("a file that is already the base is a clean no-op", code == 0, out)
    check("... no backup is made", not list(already.glob("*.bak.*")))
    check("... and it says so", "already the published base" in out, out)

    # 7. A moved base needs a person to say so.
    moved = a_live_folder()
    before = sha(moved / "jarvis_gate.py")
    code, out = run(mod, moved, expected_live_sha=before,
                    expected_base_sha="1" * 64, apply=True, day="2026-11-26")
    check("a base that moved is refused by default", code == 2, out)
    check("... and nothing is written",
          sha(moved / "jarvis_gate.py") == before)
    code, out = run(mod, moved, expected_live_sha=before,
                    expected_base_sha="1" * 64, apply=True,
                    allow_new_base=True, day="2026-11-26")
    check("... unless the newer published base is allowed out loud",
          code == 0 and sha(moved / "jarvis_gate.py") == base_sha, out)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
