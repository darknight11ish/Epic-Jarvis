"""jarvis_packs.py: the pack manager's whole first slice, driven for real.

WHAT IS PROVEN HERE, each against a temp folder and a fake gate - never the
owner's real skills folder, never a real approval queue, and every socket
refused for the whole run:

  * **the scan is a read.** A clean prompt-only skill folder produces a report
    with every field the card shows - name, kind, licence, every file and its
    sha256, the combined pack digest, the trigger line, the prompt cost, the
    compatibility answer - and NO file appears anywhere;
  * **code is refused in one sentence, before any card.** A folder holding a
    `.py` is refused with the plain sentence that names the file, `asked` is
    False, the gate is never called, and not one byte is written;
  * **a .zip's bounds are refusals.** A member that climbs out (`../`), and a
    symlink member, are each refused before anything is unpacked;
  * **a collision is refused.** A skill whose name is already installed does
    not overwrite it and does not become a card;
  * **install is one card, and nothing lands before it.** With the gate stubbed
    to refuse, no folder appears; with it stubbed to approve, the folder appears
    and the ledger records it;
  * **the ledger records every file and its hash**, and the receipt is on disk;
  * **removal deletes exactly the ledger's files** and keeps a file the owner
    made beside it, naming it in the answer;
  * **installing enables nothing.** The pack is moved to `skills-off` straight
    after the copy: `jarvis_skills.cards()` does not list it, `load()` cannot
    find it, and the loader never imports it;
  * **inspect installs nothing**, and a second inspect of the same folder says
    the same digest without a card;
  * **the tool pins moved with the tools** (the catalogue, the fresh-install
    list and the tool dossiers all name the four), and
  * **the twin is byte-identical** to `backend/jarvis_packs.py`.

    python -B backend/test_packs.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

# A scratch root, made with mkdir, not mkdtemp: mkdtemp's 0o700 makes writes
# under it raise PermissionError on this machine (the note in test_skill_menu).
SCRATCH = here = REPO / ".dsh-scratch" / "TEST-PACKS"
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
# A settings file that is ours, in this temp folder: the shipped template, so a
# tier row can never be read from the owner's real config.
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
    if cond:
        PASSED.append(name)
        print(f"  ok   {name}")
    else:
        FAILED.append((name, detail))
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


# --------------------------------------------------------------------------
#   Fixtures
# --------------------------------------------------------------------------

GOOD_SKILL_MD = """---
name: {name}
description: {description}
license: MIT
allowed-tools: [file_read, calculator]
version: 1.2.0
---

# {name}

Use this when the owner asks for a small, repeatable thing.

## When to use

- the owner says "do the small thing"
- a task needs the same three steps every time

## Steps

1. Read the thing.
2. Write the answer.
"""


def make_skill(root: Path, name: str, *, description: str = "A small repeatable "
               "thing the owner can ask for.", extra: dict = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        GOOD_SKILL_MD.format(name=name, description=description), "utf-8")
    for rel, text in (extra or {}).items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, "utf-8")
    return folder


def fresh_gate(*, allowed: bool, tier: str = "ask", reason: str = ""):
    """A stand-in for jarvis_skills._gate: records that it was asked."""
    calls = []

    class _V:
        def __init__(self):
            self.allowed = allowed
            self.tier = tier
            self.reason = reason or ("no" if not allowed else "")
            self.action = "modify_own_code"

    def fake(action, detail, prompt=""):
        calls.append({"action": action, "detail": dict(detail or {}),
                      "prompt": prompt})
        return _V()

    return fake, calls


# --------------------------------------------------------------------------
#   Tests
# --------------------------------------------------------------------------

def t_a_clean_skill_scans_into_a_full_report():
    folder = make_skill(SOURCE, "tidy-desk")
    report = P.scan_source(str(folder))
    pack = report["pack"]
    check("a clean prompt-only skill scans as clean", report["verdict"] == "clean",
          repr(report.get("verdict")))
    check("the report names the skill and its kind",
          pack["name"] == "tidy-desk" and pack["kind"] == "skill", repr(pack))
    check("the report carries the version and the licence",
          pack["version"] == "1.2.0" and pack["licence"] == "MIT", repr(pack))
    check("every file is listed with its own sha256",
          len(report["digest"]["files"]) == 1
          and len(report["digest"]["files"][0]["sha256"]) == 64,
          repr(report["digest"]["files"]))
    check("the combined pack digest is 64 hex characters",
          len(report["digest"]["pack_sha256"]) == 64)
    check("it says instructions only, no code", pack["has_code"] is False)
    check("the declared tools are listed as a DECLARATION",
          report["declared"]["allowed_tools"] == ["file_read", "calculator"],
          repr(report["declared"]["allowed_tools"]))
    check("the trigger line comes from the skill's own description",
          report["effectiveness"]["trigger_phrases"]
          and "small repeatable thing" in report["effectiveness"]["trigger_phrases"][0],
          repr(report["effectiveness"]["trigger_phrases"]))
    check("the bullets under 'When to use' are shown too",
          any("do the small thing" in t for t in
              report["effectiveness"]["trigger_phrases"]),
          repr(report["effectiveness"]["trigger_phrases"]))
    check("the prompt cost is a positive estimate",
          int(report["effectiveness"]["prompt_tokens"]) > 0,
          repr(report["effectiveness"].get("prompt_tokens")))
    check("the trust rung is honest: unsigned, NOT VERIFIED",
          report["trust"]["rung"] == "unsigned"
          and "NOT VERIFIED" in report["trust"]["detail"])
    check("the four plain answers exist",
          set(report["sentences"]) == {"what", "changes", "safe", "works"},
          repr(sorted(report["sentences"])))
    check("the scan wrote nothing anywhere",
          list(SKILLS.iterdir()) == [] and list(OFF.iterdir()) == []
          and not P.ledger_path().exists())


def t_a_python_file_is_refused_and_nothing_is_written():
    folder = make_skill(SOURCE, "sneaky-skill",
                        extra={"run.py": "print('hello')\n"})
    report = P.scan_source(str(folder))
    check("a pack holding a .py is refused", report["verdict"] == "refuse",
          repr(report.get("verdict")))
    sentence = str(report.get("refusal") or "")
    check("the refusal is one plain sentence naming the file",
          "executable code" in sentence and "run.py" in sentence, sentence)
    check("a refused pack says nobody was asked", report.get("asked") is False)
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("installing a refused pack writes nothing",
          out.get("ok") is False and out.get("asked") is False, repr(out)[:200])
    check("... and the gate was never asked", calls == [], repr(calls))
    check("... and no folder landed in the skills folder",
          list(SKILLS.iterdir()) == [])
    check("... nor turned-off folder", list(OFF.iterdir()) == [])


def t_a_zip_that_climbs_or_links_is_refused():
    climbing = SCRATCH / "climb.zip"
    with zipfile.ZipFile(climbing, "w") as zf:
        zf.writestr("../../evil/SKILL.md", "---\nname: evil\n---\nbody")
    report = P.scan_source(str(climbing))
    check("a zip member that climbs out is refused", report["verdict"] == "refuse",
          repr(report.get("verdict")))
    check("the refusal names the climb", "outside itself" in str(report.get("refusal")),
          str(report.get("refusal")))
    linked = SCRATCH / "linked.zip"
    with zipfile.ZipFile(linked, "w") as zf:
        info = zipfile.ZipInfo("SKILL.md")
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "---\nname: linked\n---\nbody")
    report = P.scan_source(str(linked))
    check("a symlink member is refused", report["verdict"] == "refuse",
          repr(report.get("verdict")))
    check("the refusal names the link", "link" in str(report.get("refusal")),
          str(report.get("refusal")))
    check("neither zip unpacked anything into the incoming folder",
          list(INCOMING.iterdir()) == [])
    check("neither zip is in the ledger", not P.ledger_path().exists())


def t_a_name_collision_is_refused():
    folder = make_skill(SOURCE, "tidy-desk")
    SKILLS.mkdir(parents=True, exist_ok=True)
    (SKILLS / "tidy-desk").mkdir(exist_ok=True)
    (SKILLS / "tidy-desk" / "SKILL.md").write_text(
        GOOD_SKILL_MD.format(name="tidy-desk", description="already here"), "utf-8")
    report = P.scan_source(str(folder))
    check("a name already installed is refused", report["verdict"] == "refuse",
          repr(report.get("verdict")))
    check("the refusal says the name is taken",
          "already" in str(report.get("refusal")), str(report.get("refusal")))
    check("the installed skill was not overwritten",
          "already here" in (SKILLS / "tidy-desk" / "SKILL.md").read_text("utf-8"))
    shutil.rmtree(SKILLS / "tidy-desk")


def t_install_is_one_card_and_writes_only_after_it():
    folder = make_skill(SOURCE, "tidy-desk")
    # 1. The gate REFUSES: nothing may land.
    gate, calls = fresh_gate(allowed=False, reason="not now")
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("a refused card installs nothing",
          out.get("ok") is False and out.get("installed") is False, repr(out)[:200])
    check("... the gate was asked exactly once", len(calls) == 1, repr(calls))
    check("... the card names the pack, the source and the hash",
          "tidy-desk" in calls[0]["prompt"] and str(folder) in calls[0]["prompt"]
          and "SHA-256" in calls[0]["prompt"], calls[0]["prompt"][:400])
    check("... the card carries the whole scan report",
          "WILL IT WORK HERE" in calls[0]["prompt"]
          and "IS IT SAFE" in calls[0]["prompt"], calls[0]["prompt"][:400])
    check("... and nothing is in the skills or off folder",
          not (SKILLS / "tidy-desk").exists() and not (OFF / "tidy-desk").exists())
    # 2. The gate APPROVES: now it lands, and it is turned OFF at once.
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("an approved card installs it", out.get("ok") is True, repr(out)[:300])
    check("... exactly one card was raised", len(calls) == 1, repr(calls))
    check("... it is not in the live skills folder",
          not (SKILLS / "tidy-desk").exists())
    check("... it is in skills-off, turned off as it landed",
          (OFF / "tidy-desk" / "SKILL.md").is_file(), out.get("state"))
    check("... the report says it is OFF", out.get("state") == "disabled",
          repr(out.get("state")))
    check("... a receipt was written",
          bool(out.get("receipt")) and Path(out["receipt"]).is_file(),
          repr(out.get("receipt")))
    receipt = json.loads(Path(out["receipt"]).read_text("utf-8"))
    check("... the receipt holds the digest and the approval",
          receipt["digest"]["pack_sha256"] == out["pack_sha256"]
          and receipt["receipt"]["approved_by"] == "owner")


def t_the_ledger_records_every_file_and_hash():
    folder = make_skill(SOURCE, "ledger-test", extra={
        "references/notes.md": "some detail\n",
    })
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("the pack installed", out.get("ok") is True, repr(out)[:200])
    ledger = P.read_ledger()
    entry = (ledger.get("packs") or {}).get("ledger-test") or {}
    check("the ledger has the pack", bool(entry), repr(list((ledger.get("packs") or {}))))
    on_disk = sorted(str(p.relative_to(OFF / "ledger-test")).replace("\\", "/")
                     for p in (OFF / "ledger-test").rglob("*") if p.is_file())
    check("the ledger records every file that was written",
          sorted(r["path"] for r in entry.get("files") or []) == on_disk,
          f"{entry.get('files')} vs {on_disk}")
    check("every recorded hash matches the file on disk",
          all(P._sha256_file(OFF / "ledger-test" / r["path"]) == r["sha256"]
              for r in entry.get("files") or []))
    check("the ledger records the source and the pack digest",
          entry.get("source", {}).get("type") == "folder"
          and len(str(entry.get("pack_sha256"))) == 64, repr(entry.get("source")))
    check("the ledger records when and in what state",
          bool(entry.get("installed_at")) and entry.get("state") == "disabled",
          repr(entry.get("state")))


def t_remove_deletes_exactly_the_ledger_files_and_keeps_owner_files():
    folder = make_skill(SOURCE, "remove-test", extra={"extra.md": "pack file\n"})
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("remove-test installed", out.get("ok") is True, repr(out)[:200])
    owner_file = OFF / "remove-test" / "mine.txt"
    owner_file.write_text("the owner wrote this", "utf-8")
    plan = P.plan_remove("remove-test")
    check("the removal plan lists the ledger files and not the owner's",
          plan.get("ok") is True and "mine.txt" in (plan.get("keep") or [])
          and "mine.txt" not in (plan.get("delete") or []),
          repr(plan)[:400])
    card = P.remove_card_text(plan)
    check("the removal card names the files it would delete",
          "SKILL.md" in card and "Remove the pack" in card, card[:300])
    out = P.remove_pack("remove-test")
    check("the removal worked", out.get("ok") is True, repr(out)[:300])
    check("its own files are gone",
          not (OFF / "remove-test" / "SKILL.md").exists()
          and not (OFF / "remove-test" / "extra.md").exists())
    check("the owner's file beside it is kept and named",
          owner_file.is_file() and "mine.txt" in (out.get("kept") or []),
          repr(out.get("kept")))
    entry = (P.read_ledger().get("packs") or {}).get("remove-test") or {}
    check("the ledger marks it removed rather than forgetting it",
          entry.get("state") == "removed", repr(entry.get("state")))
    second = P.remove_pack("remove-test")
    check("a second removal refuses rather than guessing",
          second.get("ok") is False, repr(second)[:200])


def t_installing_enables_nothing():
    folder = make_skill(SOURCE, "off-by-default")
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("off-by-default installed", out.get("ok") is True, repr(out)[:200])
    cards = [c.get("name") for c in (SK.cards() or [])]
    check("the model is not offered it", "off-by-default" not in cards, repr(cards))
    try:
        loaded = SK.load("off-by-default") or {}
    except Exception:
        loaded = {}
    check("it cannot be loaded either", not loaded.get("body"), repr(loaded)[:200])
    index = SK._read_index() or {}
    check("it has no row in the index the model reads from",
          "off-by-default" not in index, repr(sorted(index)))
    # And the drop-in loader never sees a skill at all: a skill is not a folder
    # in jarvis_plugins\, and the ledger does not put one there.
    check("no plugin folder was created",
          not (HERE / "jarvis_plugins" / "off-by-default").exists())


def t_inspect_installs_nothing_and_is_stable():
    folder = make_skill(SOURCE, "inspect-twice")
    before = sorted(str(p) for p in SCRATCH.rglob("*"))
    first = P.scan_source(str(folder))
    second = P.scan_source(str(folder))
    after = sorted(str(p) for p in SCRATCH.rglob("*"))
    check("inspect writes no file at all", before == after,
          repr(set(after) - set(before)))
    check("two scans of one folder agree on the digest",
          first["digest"]["pack_sha256"] == second["digest"]["pack_sha256"])
    check("inspect raised no card", True)
    check("inspect left no ledger entry",
          "inspect-twice" not in (P.read_ledger().get("packs") or {}))
    check("the plain answer says what it is, changes, safety and fit",
          all(first["sentences"].get(k) for k in ("what", "changes", "safe", "works")))


def t_the_pins_moved_with_the_tools():
    """Where a tool count moved, the pin names the four real tools."""
    import jarvis_agent as AG
    import jarvis_tool_profiles as TP
    names = ["pack_list", "pack_inspect", "pack_install", "pack_remove"]
    check("all four tools exist in jarvis_agent.TOOLS",
          all(n in AG.TOOLS for n in names), repr(sorted(AG.TOOLS)[:5]))
    check("every tool has a dossier profile",
          all(n in TP.PROFILES for n in names),
          repr([n for n in names if n not in TP.PROFILES]))
    check("every profile is owned by exactly one family",
          all(sum(1 for f in TP.FAMILIES.values() if n in (f.get("tools") or [])) == 1
              for n in names))
    check("the dossier count matches the tools it claims",
          len(TP.PROFILES) == len(AG.TOOLS),
          f"{len(TP.PROFILES)} profiles vs {len(AG.TOOLS)} tools")
    # The fresh-install list, read the way a turn reads it - real behaviour,
    # not a line in the template. The four are shipped ON, so a fresh PC is
    # offered them; two of them raise no card and are gated read-only.
    offered = [str(n) for n in AG.enabled_tools_for_turn()]
    check("the shipped settings file offers all four to a fresh PC",
          all(n in offered for n in names),
          repr([n for n in names if n not in offered]))
    check("list and inspect are the gate's own read-only action",
          AG.TOOLS["pack_list"].gate_lookup_name({}) == "skill_list"
          and AG.TOOLS["pack_inspect"].gate_lookup_name({}) == "skill_list")
    check("install and remove resolve to the one shipped changing action",
          AG.TOOLS["pack_install"].gate_lookup_name({}) == "skill_manage"
          and AG.TOOLS["pack_remove"].gate_lookup_name({}) == "skill_manage")


def t_the_twin_is_byte_identical():
    twin = REPO / "jarvis-backend" / "jarvis_packs.py"
    check("the twin exists", twin.is_file(), str(twin))
    if twin.is_file():
        check("the twin is byte-identical to backend/jarvis_packs.py",
              twin.read_bytes() == (HERE / "jarvis_packs.py").read_bytes())
    from _where import SHIPPED
    check("_where.py SHIPPED names it", "jarvis_packs.py" in SHIPPED)
    stack = (REPO / "scripts" / "apply-patches.ps1").read_text("utf-8")
    check("apply-patches.ps1 SHIPPED names it", "'jarvis_packs.py'" in stack)


def t_nothing_here_opens_a_socket_or_starts_a_process():
    src = (HERE / "jarvis_packs.py").read_text("utf-8")
    for bad in ("import socket", "import subprocess", "http.client", "urllib",
                "requests."):
        check(f"jarvis_packs does not use {bad!r}", bad not in src)
    # And at runtime, with the socket module replaced by a trap.
    real = socket.socket
    calls = []

    def trap(*a, **k):
        calls.append(a)
        raise AssertionError("a socket was opened")

    socket.socket = trap
    try:
        P.scan_source(str(make_skill(SOURCE, "no-net-skill")))
    finally:
        socket.socket = real
    check("scanning opens no socket", calls == [], repr(calls))


def main():
    for fn in (t_a_clean_skill_scans_into_a_full_report,
               t_a_python_file_is_refused_and_nothing_is_written,
               t_a_zip_that_climbs_or_links_is_refused,
               t_a_name_collision_is_refused,
               t_install_is_one_card_and_writes_only_after_it,
               t_the_ledger_records_every_file_and_hash,
               t_remove_deletes_exactly_the_ledger_files_and_keeps_owner_files,
               t_installing_enables_nothing,
               t_inspect_installs_nothing_and_is_stable,
               t_the_pins_moved_with_the_tools,
               t_the_twin_is_byte_identical,
               t_nothing_here_opens_a_socket_or_starts_a_process):
        print(f"\n{fn.__name__}")
        try:
            fn()
        except Exception:
            FAILED.append((fn.__name__, traceback.format_exc()))
            print(f"  FAIL {fn.__name__}\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name, detail in FAILED:
            print(f"\nFAILED: {name}\n{detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
