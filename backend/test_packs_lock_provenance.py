"""The curator lock, and where a pack came from (2026-11-06).

    python3 -B backend/test_packs_lock_provenance.py

THE OWNER'S RULING (2026-11-06 11:35 PT, next-sprint PR 2, Hermes borrows
#5/#8), two additions to `jarvis_packs.py`:

  1. `curator_lock`: a per-pack `"locked": true` in `jarvis-packs.json`, with
     the exact sentence "Owner-locked: cannot be replaced or removed until
     unlocked on PC". `pack_install` (including a REPLACEMENT) and
     `pack_remove` must refuse a locked pack until it is unlocked. The flag is
     written only by the PC - `set_locked(..., here=True)`, or
     `py -3 jarvis_packs.py lock <name>` on this PC. There is no route, so no
     phone path can write it, and `here=False` is refused outright.
  2. A provenance tier on the install card, decided by WHERE the pack came
     from: `owner-local` (a folder on this PC), `imported-hermes` (a .zip whose
     own manifest names Hermes/agentskills), `unverified-archive` (any other
     .zip). Each has one plain sentence, and the tier is in the ledger too.

Driven for real against a temp config/skills/packs folder and a fake gate -
never the owner's real skills folder, never a real approval queue.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

# The same scratch shape test_packs.py uses: mkdir, not mkdtemp, because
# mkdtemp's 0o700 makes writes under it raise PermissionError on this machine.
SCRATCH = REPO / ".dsh-scratch" / "TEST-PACKS-LOCK"
try:
    shutil.rmtree(SCRATCH)
except OSError:
    pass
CONFIG = SCRATCH / "config"
SKILLS = CONFIG / "skills"
OFF = CONFIG / "skills-off"
INCOMING = CONFIG / "skills-incoming"
PACKS = CONFIG / "packs"
SOURCE = SCRATCH / "source"
for folder in (CONFIG, SKILLS, OFF, INCOMING, PACKS, SOURCE):
    folder.mkdir(parents=True, exist_ok=True)

os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["JARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["JARVIS_SKILLS_DIR"] = str(SKILLS)
os.environ["JARVIS_SKILLS_OFF"] = str(OFF)
os.environ["JARVIS_SKILLS_INCOMING"] = str(INCOMING)
os.environ["JARVIS_SKILLS_QUARANTINE"] = str(CONFIG / "skills-quarantine")
os.environ["JARVIS_PACKS_DIR"] = str(PACKS)
TEMPLATE = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
SETTINGS = CONFIG / "jarvis-framework.toml"
shutil.copyfile(TEMPLATE, SETTINGS)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(SETTINGS)

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.append(str(REPO / "jarvis-backend"))

import jarvis_packs as P  # noqa: E402
import jarvis_skills as SK  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"\n       {detail}" if detail and not cond else ""))


SKILL_MD = """---
name: {name}
description: A small repeatable thing the owner can ask for.
license: MIT
version: {version}
---

# {name}

Use this when the owner asks for a small, repeatable thing.

## Steps

1. Read the thing.
2. Write the answer.
Version {version}.
"""


def make_skill(root: Path, name: str, version: str = "1.0.0", extra: dict = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(SKILL_MD.format(name=name, version=version), "utf-8")
    for rel, text in (extra or {}).items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, "utf-8")
    return folder


def make_zip(filename: str, members: dict) -> Path:
    path = SCRATCH / filename
    with zipfile.ZipFile(path, "w") as zf:
        for member, data in members.items():
            zf.writestr(member, data)
    return path


def fresh_gate(*, allowed: bool = True):
    calls = []

    class _V:
        allowed = True
        tier = "ask"
        reason = ""
        action = "modify_own_code"

    def fake(action, detail, prompt=""):
        calls.append({"action": action, "prompt": prompt})
        v = _V()
        v.allowed = allowed
        v.reason = "" if allowed else "not now"
        return v

    return fake, calls


def install(source, *, allowed: bool = True):
    gate, calls = fresh_gate(allowed=allowed)
    SK._gate = gate
    try:
        out = P.install_pack(str(source))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    return out, calls


# --------------------------------------------------------------------------
#   1. The three provenance tiers, and their card sentences
# --------------------------------------------------------------------------

def t_a_folder_pack_is_owner_local():
    folder = make_skill(SOURCE, "prov-local")
    report = P.scan_source(str(folder))
    check("a folder scan reports owner-local provenance",
          P.provenance_of(report) == P.PROVENANCE_OWNER_LOCAL, P.provenance_of(report))
    card = P.card_text(report)
    check("the install card names the tier", "PROVENANCE: owner-local" in card,
          card[:300])
    check("... and says where it came from in the owner's words",
          P.PROVENANCE_WORDS[P.PROVENANCE_OWNER_LOCAL] in card, card[:300])
    out, calls = install(folder)
    check("the folder pack installed", out.get("ok") is True, repr(out)[:300])
    entry = (P.read_ledger().get("packs") or {}).get("prov-local") or {}
    check("the ledger keeps the tier",
          entry.get("provenance") == P.PROVENANCE_OWNER_LOCAL, entry.get("provenance"))


def t_a_plain_zip_is_an_unverified_archive():
    path = make_zip("plain.zip", {
        "plain-pack/SKILL.md": SKILL_MD.format(name="prov-plain", version="1.0.0"),
    })
    report = P.scan_source(str(path))
    check("a plain .zip reports unverified-archive",
          P.provenance_of(report) == P.PROVENANCE_ARCHIVE, P.provenance_of(report))
    card = P.card_text(report)
    check("its card names the tier", "PROVENANCE: unverified-archive" in card, card[:300])
    check("... and says nobody wrote down who made it",
          "Nothing in the archive says" in card, card[:400])


def t_a_hermes_zip_is_imported_hermes():
    path = make_zip("hermes.zip", {
        "hermes-pack/SKILL.md": SKILL_MD.format(name="prov-hermes", version="1.0.0"),
        "hermes-pack/pack.json": json.dumps(
            {"kind": "skill", "origin": "hermes", "publisher": "agentskills.io"}),
    })
    report = P.scan_source(str(path))
    check("a .zip whose pack.json names Hermes reports imported-hermes",
          P.provenance_of(report) == P.PROVENANCE_HERMES, P.provenance_of(report))
    card = P.card_text(report)
    check("its card names the tier", "PROVENANCE: imported-hermes" in card, card[:300])
    check("... and says Jarvis did not write it",
          "Jarvis did not write it" in card, card[:400])
    check("the three tiers are exactly the three the ruling names",
          P.PROVENANCE_TIERS == ("owner-local", "imported-hermes", "unverified-archive"),
          P.PROVENANCE_TIERS)
    check("every tier has its own sentence",
          set(P.PROVENANCE_WORDS) == set(P.PROVENANCE_TIERS), sorted(P.PROVENANCE_WORDS))


def t_a_report_with_no_source_is_the_cautious_tier():
    check("no source reads as the cautious tier, never as the owner's own folder",
          P.provenance_of({}) == P.PROVENANCE_ARCHIVE, P.provenance_of({}))


# --------------------------------------------------------------------------
#   2. The curator lock
# --------------------------------------------------------------------------

def t_locking_writes_the_owners_exact_sentence_and_is_pc_only():
    check("the sentence is the owner's own, word for word",
          P.LOCKED_WORDS == "Owner-locked: cannot be replaced or removed until "
                            "unlocked on PC", P.LOCKED_WORDS)
    folder = make_skill(SOURCE, "lock-me")
    out, _calls = install(folder)
    check("lock-me installed", out.get("ok") is True, repr(out)[:200])
    # NOT the PC: refused, and nothing is written.
    refused = P.set_locked("lock-me", True, here=False)
    check("locking from anywhere but the PC is refused",
          refused.get("ok") is False and "PC" in str(refused.get("error")), refused)
    check("... and the ledger is not locked", P.locked_of("lock-me") is False)
    # The PC: written at once (a tightening).
    got = P.set_locked("lock-me", True, here=True, by="the owner")
    check("the PC locks it", got.get("ok") is True and got.get("locked") is True, got)
    check("... with the owner's sentence", got.get("words") == P.LOCKED_WORDS, got)
    entry = (P.read_ledger().get("packs") or {}).get("lock-me") or {}
    check("the ledger row carries \"locked\": true", entry.get("locked") is True, entry.get("locked"))
    check("... and when it was locked", bool(entry.get("locked_at")), entry.get("locked_at"))
    check("... and who did it", "PC" in str(entry.get("locked_by"))
          or "owner" in str(entry.get("locked_by")).lower(), entry.get("locked_by"))
    rows = {r["name"]: r for r in P.list_packs()["packs"]}
    check("the pack list says it is locked", rows.get("lock-me", {}).get("locked") is True,
          rows.get("lock-me"))


def t_a_locked_pack_cannot_be_replaced():
    folder = make_skill(SOURCE, "lock-me", version="2.0.0")
    before = (OFF / "lock-me" / "SKILL.md").read_text("utf-8")
    out, calls = install(folder, allowed=True)
    check("a replacement of a locked pack is refused",
          out.get("ok") is False and out.get("locked") is True, repr(out)[:300])
    check("... the reason is the owner's sentence",
          P.LOCKED_WORDS in str(out.get("reason")), out.get("reason"))
    check("... nobody was asked", out.get("asked") is False and calls == [], calls)
    check("... and the installed copy is byte for byte what it was",
          (OFF / "lock-me" / "SKILL.md").read_text("utf-8") == before)
    check("... the ledger still records version 1.0.0",
          ((P.read_ledger().get("packs") or {}).get("lock-me") or {}).get("version")
          == "1.0.0",
          ((P.read_ledger().get("packs") or {}).get("lock-me") or {}).get("version"))


def t_a_locked_pack_cannot_be_removed_until_unlocked():
    plan = P.plan_remove("lock-me")
    check("a removal is not even planned for a locked pack",
          plan.get("ok") is False and plan.get("locked") is True, plan)
    check("... and says the owner's sentence", P.LOCKED_WORDS in str(plan.get("reason")),
          plan.get("reason"))
    out = P.remove_pack("lock-me")
    check("a locked pack is not removed",
          out.get("ok") is False and out.get("removed") is False, out)
    check("... and its files are still on disk", (OFF / "lock-me" / "SKILL.md").is_file())
    check("... the ledger row is not marked removed",
          ((P.read_ledger().get("packs") or {}).get("lock-me") or {}).get("state")
          != "removed")
    # The unlock path: exists, and is the PC's alone.
    refused = P.set_locked("lock-me", False, here=False)
    check("unlocking from anywhere but the PC is refused",
          refused.get("ok") is False, refused)
    check("... and it is still locked", P.locked_of("lock-me") is True)
    got = P.set_locked("lock-me", False, here=True)
    check("the PC unlocks it", got.get("ok") is True and got.get("locked") is False, got)
    check("... and the ledger says so", P.locked_of("lock-me") is False)
    # Now the removal the lock refused is allowed.
    plan2 = P.plan_remove("lock-me")
    check("an unlocked pack can be planned for removal again", plan2.get("ok") is True, plan2)
    out2 = P.remove_pack("lock-me")
    check("... and removed", out2.get("ok") is True and out2.get("removed") is True, out2)


def t_the_command_line_is_a_pc_door():
    _calls = []
    line = P._cli(["lock", "lock-me"])
    check("the command line answers with JSON and exit 0 on success", line == 0, line)
    check("... and it really locked the pack", P.locked_of("lock-me") is True)
    check("the locked list names it", "lock-me" in P._self_check()["locked"],
          P._self_check()["locked"])
    check("an unlock from the command line works", P._cli(["unlock", "lock-me"]) == 0)
    check("... and it is unlocked", P.locked_of("lock-me") is False)
    check("an unknown command is refused", P._cli(["nonsense"]) == 2)


def t_a_lock_cannot_be_written_by_installing_a_pack():
    """The "locked" key is the OWNER's. A pack whose own pack.json carries
    `"locked": true` must not be able to lock itself through the ledger write
    at the end of install."""
    path = make_zip("self-lock.zip", {
        "self-lock/SKILL.md": SKILL_MD.format(name="self-lock", version="1.0.0"),
        "self-lock/pack.json": json.dumps({"kind": "skill", "locked": True}),
    })
    out, _calls = install(path, allowed=True)
    check("a pack carrying its own 'locked' key installs", out.get("ok") is True,
          repr(out)[:300])
    entry = (P.read_ledger().get("packs") or {}).get("self-lock") or {}
    check("... and it is NOT locked: only the PC writes that flag",
          entry.get("locked") is False, entry.get("locked"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
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
