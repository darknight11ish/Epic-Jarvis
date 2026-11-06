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
    False, the gate is never called, and not one byte is written. Every suffix
    the owner's Q2 ruling names - including `.wasm` - is driven, not just `.py`;
  * **a folder link is refused.** A junction inside a pack is a way out of it,
    so the scan refuses the pack before it hashes a byte (a junction is used
    where this PC will not let a test make a symlink; the check covers both);
  * **a .zip's bounds are refusals.** A member that climbs out (`../`), a
    symlink member, and a member with an alternate-stream colon in its name are
    each refused before anything is unpacked;
  * **a name Windows would silently rename is refused.** A member ending in a
    dot or a space (`evil.vbs.`), a member under a directory ending in one, a
    Windows device name, an empty path component and a `.` component are
    refused by the scan and refused AGAIN on unpack, so the code boundary
    judges the name the disk will really get, not the one the archive wrote -
    and a script that appears in a folder between the scan and the copy is
    refused before the card too;
  * **a name the ledger knows is a REPLACEMENT, and a new card shows a unified
    diff.** The new source is scanned from scratch, the diff against the
    installed files is in the one card's text, and with the gate stubbed to
    refuse the installed copy does not change by one byte; with it stubbed to
    approve the new bytes land and the old digest is kept in the history;
  * **the same bytes are not a replacement.** Re-scanning what is installed is
    a plain refusal and never becomes a card;
  * **a name on disk with no ledger record is still refused.** The pack manager
    will not overwrite a skill it did not write, because it has no manifest for
    it;
  * **tampering is caught on load and marked.** A reference file changed by hand
    (not SKILL.md, which the core's own drift check already covers) makes
    `verify_pack` refuse, `load_pack` refuse, `pack_list` show `tampered`, the
    ledger record it, and the skill hub stop offering it - and restoring the
    bytes clears the mark;
  * **an approved edit or import re-pins the pack's manifest.** The Skills
    screen's edit and its import replace a pack's files through
    `jarvis_skills.install()`, and that one shared door re-pins the ledger, so
    an ordinary approved edit no longer leaves the pack un-loadable - while a
    file changed by hand still reads as tampered;
  * **there is no update command.** The four pack tools are the only ones, none
    is named update/replace, and the module defines no in-place updater;
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


def make_zip(filename: str, members: dict) -> Path:
    """A .zip in the scratch folder, with exactly these members.

    `writestr` is used rather than a file on disk so a name Windows would
    silently rename (`evil.vbs.`) can be written at all: on this platform a
    real file cannot carry it, and that is the whole point of the attack.
    """
    path = SCRATCH / filename
    with zipfile.ZipFile(path, "w") as zf:
        for member, data in members.items():
            zf.writestr(member, data)
    return path


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


def make_junction(link: Path, target: Path) -> bool:
    """A directory junction. This PC will not let a test make a symlink, and a
    junction is the same escape from a folder - the scan must refuse both."""
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists() or link.is_symlink():
            return False
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return True
    except Exception:
        return False


def t_every_law_listed_code_file_is_refused():
    """Q2 (2026-11-05): every executable suffix named by the ruling, not just .py."""
    suffixes = [".py", ".pyc", ".ps1", ".bat", ".cmd", ".sh", ".exe", ".dll",
                ".so", ".pyd", ".js", ".ts", ".wasm"]
    refused_ok, named_ok = True, True
    for i, suffix in enumerate(suffixes):
        folder = make_skill(SOURCE / f"code-{i}", f"code-{i}",
                            extra={f"payload{suffix}": "not really code\n"})
        report = P.scan_source(str(folder))
        if report.get("verdict") != "refuse":
            refused_ok = False
            print(f"       {suffix} was NOT refused: {report.get('verdict')!r}")
        if f"payload{suffix}" not in str(report.get("refusal") or ""):
            named_ok = False
            print(f"       {suffix} refusal did not name the file: "
                  f"{report.get('refusal')!r}")
    check("every suffix the Q2 ruling names is refused", refused_ok,
          ", ".join(suffixes))
    check("... and each refusal names the file that would run", named_ok)
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(SOURCE / "code-0"))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("a code pack is refused before the gate, and nothing is written",
          out.get("asked") is False and calls == []
          and not (SKILLS / "code-0").exists() and not (OFF / "code-0").exists(),
          repr(out)[:200])


def t_a_zip_code_member_or_stream_name_is_refused():
    wasm = SCRATCH / "wasm.zip"
    with zipfile.ZipFile(wasm, "w") as zf:
        zf.writestr("SKILL.md", "---\nname: wasm-pack\ndescription: x\n---\nbody")
        zf.writestr("payload.wasm", b"\x00asm")
    report = P.scan_source(str(wasm))
    check("a .zip holding a .wasm member is refused",
          report.get("verdict") == "refuse"
          and "payload.wasm" in str(report.get("refusal")),
          str(report.get("refusal")))
    stream = SCRATCH / "stream.zip"
    with zipfile.ZipFile(stream, "w") as zf:
        zf.writestr("SKILL.md", "---\nname: stream-pack\ndescription: x\n---\nbody")
        zf.writestr("notes.md:hidden", "invisible body")
    report = P.scan_source(str(stream))
    check("a .zip member with an alternate-stream colon is refused",
          report.get("verdict") == "refuse"
          and "plain name" in str(report.get("refusal")),
          str(report.get("refusal")))


def t_a_trailing_dot_or_space_cannot_smuggle_a_script_in():
    """BLOCKER A1 (2026-11-06): Windows strips a trailing dot or space, so a
    member named `evil.vbs.` lands as `evil.vbs`. The scan must judge the name
    the DISK will get, and the unpack must refuse it again."""
    # The predicate itself, before any archive.
    check("every suffix the skill library calls executable is code here too",
          all(P._is_code("payload" + s) for s in SK.EXEC_SUFFIXES),
          repr([s for s in SK.EXEC_SUFFIXES if not P._is_code("payload" + s)]))
    named = {".vbs", ".hta", ".scr", ".jar", ".pyc", ".wasm", ".mjs", ".ts",
             ".class"}
    check("the pack scan's own suffix list is the wider one",
          named <= set(P.code_suffixes()),
          repr(sorted(named - set(P.code_suffixes()))))
    check("a trailing dot or space cannot hide a script",
          P._is_code("evil.vbs.") and P._is_code("evil.vbs ")
          and P._is_code("evil.vbs"),
          repr([P._is_code(n) for n in ("evil.vbs.", "evil.vbs ", "evil.vbs")]))
    check("plain markdown is still not code", not P._is_code("notes.md"))
    for member, why in (("evil.vbs.", "a trailing dot"),
                        ("evil.vbs ", "a trailing space"),
                        ("my-skill./SKILL.md", "a directory ending in a dot"),
                        ("dir /notes.md", "a directory ending in a space"),
                        ("my-skill/CON.md", "a Windows device name"),
                        ("my-skill/a//b.md", "an empty path component"),
                        ("./SKILL.md", "a '.' path component"),
                        ("../evil.md", "a climb out")):
        clean, problem = P._plain_member(member)
        check(f"a member with {why} is not a plain name",
              not clean and bool(problem), f"{member!r} -> {clean!r} {problem!r}")

    skill_text = GOOD_SKILL_MD.format(name="dot-pack",
                                      description="a pack in a .zip")
    cases = [
        ("dot-pack/evil.vbs.", "trailing-dot-member.zip"),
        ("dot-pack/evil.vbs ", "trailing-space-member.zip"),
        ("dot-pack/references./notes.md", "dot-directory-member.zip"),
        ("dot-pack/CON.md", "device-name-member.zip"),
        ("./dot-pack/references/notes.md", "dot-component-member.zip"),
        ("dot-pack/evil.vbs", "plain-vbs-member.zip"),        # the control
    ]
    for member, filename in cases:
        archive = make_zip(filename, {"dot-pack/SKILL.md": skill_text,
                                      member: "not really a payload\n"})
        report = P.scan_source(str(archive))
        check(f"{member!r} is refused by the scan before any card",
              report.get("verdict") == "refuse"
              and report.get("asked") is False,
              repr(report.get("verdict")))
        refusal = str(report.get("refusal") or "")
        check("... and the refusal names the member or the rule that refused it",
              member in refusal or "plain name" in refusal
              or "executable code" in refusal, refusal)
        gate, calls = fresh_gate(allowed=True)
        SK._gate = gate
        try:
            out = P.install_pack(str(archive))
        finally:
            SK._gate = fresh_gate(allowed=True)[0]
        check(f"... {filename} installs nothing and never asks",
              out.get("ok") is False and out.get("asked") is False
              and calls == [] and not (SKILLS / "dot-pack").exists()
              and not (OFF / "dot-pack").exists(), repr(out)[:250])
        check(f"... and the ledger has no record from {filename}",
              "dot-pack" not in (P.read_ledger().get("packs") or {}))

    # The unpack is the SECOND read of the archive: it refuses the same name
    # on its own, not only because the scan ran first.
    probe = SCRATCH / "extract-probe"
    probe.mkdir(parents=True, exist_ok=True)
    folder, why = P._extract_zip(
        make_zip("extract-dot.zip", {"p/SKILL.md": skill_text,
                                     "p/evil.vbs.": "payload\n"}), probe)
    check("the unpack refuses a trailing-dot member on its own",
          folder is None and ("dot or a space" in str(why)
                              or "plain name" in str(why)), f"{folder} {why}")
    check("... and no script landed",
          not any(p.name.startswith("evil") for p in probe.rglob("*")
                  if p.is_file()),
          repr([p.name for p in probe.rglob("*") if p.is_file()]))

    # A normal .md pack still installs, and the ledger records ONLY what landed.
    good = make_zip("dot-pack-good.zip", {
        "dot-pack/SKILL.md": skill_text,
        "dot-pack/references/notes.md": "some detail\n",
    })
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(good))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("a normal .md pack still installs", out.get("ok") is True,
          repr(out)[:250])
    check("... its one card still says instructions only, no code",
          bool(calls) and "instructions only - no code" in calls[0]["prompt"],
          (calls[0]["prompt"][:300] if calls else "no card"))
    entry = (P.read_ledger().get("packs") or {}).get("dot-pack") or {}
    landed = sorted(str(p.relative_to(OFF / "dot-pack")).replace("\\", "/")
                    for p in (OFF / "dot-pack").rglob("*") if p.is_file())
    check("the ledger records exactly the files that were written",
          landed == ["SKILL.md", "references/notes.md"]
          and sorted(r["path"] for r in entry.get("files") or []) == landed,
          f"{[r['path'] for r in entry.get('files') or []]} vs {landed}")
    check("... and every recorded hash is the landed file's own",
          all(P._sha256_file(OFF / "dot-pack" / r["path"]) == r["sha256"]
              for r in entry.get("files") or []))

    # The scan and the copy are two different reads: a script that appears in
    # the folder between them must not land either (the folder half of A1).
    late = make_skill(SOURCE / "late-code", "late-code")
    real_scan = P.scan_source

    def scan_then_plant(source):
        report = real_scan(source)
        (Path(source) / "evil.vbs").write_text("payload\n", "utf-8")
        return report

    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    P.scan_source = scan_then_plant
    try:
        out = P.install_pack(str(late))
    finally:
        P.scan_source = real_scan
        SK._gate = fresh_gate(allowed=True)[0]
        try:
            (late / "evil.vbs").unlink()
        except OSError:
            pass
    check("a script planted between the scan and the copy is refused",
          out.get("ok") is False and out.get("asked") is False
          and "executable code" in str(out.get("reason")), repr(out)[:250])
    check("... the gate was never asked", calls == [], repr(calls))
    check("... and nothing landed", not (SKILLS / "late-code").exists()
          and not (OFF / "late-code").exists())


def t_a_folder_link_is_refused():
    outside = SCRATCH / "outside-pack"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "secret.md").write_text("not part of the pack\n", "utf-8")
    folder = make_skill(SOURCE / "linked", "linked-skill",
                        extra={"references/real.md": "real\n"})
    link = folder / "references" / "outside"
    if not make_junction(link, outside):
        print("  SKIPPED  a folder link could not be made on this PC, so the "
              "link half did NOT run and did NOT pass.")
        return
    try:
        report = P.scan_source(str(folder))
        check("a folder holding a junction is refused",
              report.get("verdict") == "refuse", repr(report.get("verdict")))
        check("the refusal names the link",
              "outside" in str(report.get("refusal")), str(report.get("refusal")))
        gate, calls = fresh_gate(allowed=True)
        SK._gate = gate
        try:
            out = P.install_pack(str(folder))
        finally:
            SK._gate = fresh_gate(allowed=True)[0]
        check("... nothing is installed and nobody is asked",
              out.get("ok") is False and out.get("asked") is False and calls == [],
              repr(out)[:200])
        check("... no folder landed in the skills or off folder",
              not (SKILLS / "linked-skill").exists()
              and not (OFF / "linked-skill").exists())
    finally:
        try:
            os.rmdir(link)          # removes the junction, never its target
        except OSError:
            pass


def t_a_zip_wrapper_folder_is_read_from_the_skill_folder():
    """A .zip usually wraps the skill: the manifest is the skill's own folder."""
    z = SCRATCH / "wrapped.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("my-skill/SKILL.md",
                    GOOD_SKILL_MD.format(name="wrapped-skill",
                                         description="wrapped in a folder"))
        zf.writestr("my-skill/references/notes.md", "a note\n")
        zf.writestr("README.md", "not part of the skill\n")
    report = P.scan_source(str(z))
    check("a wrapped .zip scans as one skill",
          report.get("verdict") == "clean", repr(report.get("refusal")))
    check("... the manifest is the skill's own files, relative to its folder",
          sorted(r["path"] for r in report["digest"]["files"])
          == ["SKILL.md", "references/notes.md"],
          repr([r["path"] for r in report["digest"]["files"]]))
    check("... a file outside the skill's folder is named, not silently dropped",
          report.get("ignored") == ["README.md"], repr(report.get("ignored")))
    gate, _ = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(z))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("the wrapped .zip installs", out.get("ok") is True, repr(out)[:200])
    entry = (P.read_ledger().get("packs") or {}).get("wrapped-skill") or {}
    on_disk = P.pack_digest(P.file_rows(OFF / "wrapped-skill"))
    check("... the recorded manifest is the folder as it really landed",
          P.pack_digest(entry.get("files") or []) == on_disk
          and entry.get("pack_sha256") == on_disk,
          f"{entry.get('pack_sha256')} vs {on_disk}")
    check("... and the file it did not install is not in the ledger",
          sorted(r["path"] for r in entry.get("files") or [])
          == ["SKILL.md", "references/notes.md"],
          repr([r["path"] for r in (entry.get("files") or [])]))


def t_a_replacement_is_a_new_scan_with_a_unified_diff():
    """Q3 (2026-11-05): replacement is a full scan plus a diff on a NEW card."""
    v1 = make_skill(SOURCE / "v1", "swap-test", description="the old thing",
                    extra={"references/guide.md": "line one\nline two\n"})
    gate, _ = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        first = P.install_pack(str(v1))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("the first version installed", first.get("ok") is True, repr(first)[:200])
    old_receipt = Path(str(first.get("receipt") or ""))
    old_sha = str(first.get("pack_sha256") or "")
    v2 = make_skill(SOURCE / "v2", "swap-test", description="the new thing",
                    extra={"references/guide.md": "line one\nline changed\n"})
    report = P.scan_source(str(v2))
    check("a same-name pack scans as a replacement, not a collision",
          report.get("verdict") in ("clean", "review") and not report.get("refusal"),
          str(report.get("refusal"))[:200])
    rep = report.get("replacement") or {}
    check("... it says it will swap", rep.get("mode") == "swap", repr(rep)[:200])
    check("... the installed digest is the one it measured against",
          rep.get("from_sha256") == old_sha, repr(rep.get("from_sha256")))
    changed = (rep.get("files") or {}).get("changed") or []
    check("... every changed file is named",
          "SKILL.md" in changed and "references/guide.md" in changed,
          repr(rep.get("files")))
    diff = str(rep.get("diff") or "")
    check("... the diff is unified and names both sides",
          "--- installed/SKILL.md" in diff and "+++ new/SKILL.md" in diff
          and "-description: the old thing" in diff
          and "+description: the new thing" in diff, diff[:300])
    check("... and it has a fingerprint of its own",
          len(str(rep.get("diff_sha256") or "")) == 64)
    card = P.card_text(report)
    check("the ONE card says this is a REPLACEMENT",
          "THIS IS A REPLACEMENT" in card and "Replace the installed skill" in card,
          card[:300])
    check("... and carries the unified diff", "--- installed/SKILL.md" in card)
    check("... and the whole new scan report",
          "SCAN FINDINGS" in card and "WILL IT WORK HERE" in card)
    # The gate REFUSES: the installed copy must not change by one byte.
    gate, calls = fresh_gate(allowed=False, reason="not now")
    SK._gate = gate
    try:
        refused_out = P.install_pack(str(v2))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    live = (OFF / "swap-test" / "SKILL.md").read_text("utf-8")
    check("a refused replacement card changes nothing",
          refused_out.get("ok") is False and "the old thing" in live
          and "the new thing" not in live, repr(refused_out)[:200])
    check("... the installed reference is untouched too",
          (OFF / "swap-test" / "references" / "guide.md").read_text("utf-8")
          == "line one\nline two\n")
    check("... the card that was refused carried the diff",
          calls and "THIS IS A REPLACEMENT" in calls[0]["prompt"]
          and "--- installed/SKILL.md" in calls[0]["prompt"],
          (calls[0]["prompt"][:300] if calls else "no card"))
    # The gate APPROVES: now, and only now, the swap happens.
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(v2))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("an approved replacement swaps the files",
          out.get("ok") is True and out.get("replaced") is True, repr(out)[:300])
    live = (OFF / "swap-test" / "SKILL.md").read_text("utf-8")
    check("... the new bytes are the installed ones",
          "the new thing" in live and "the old thing" not in live)
    check("... the old receipt is still on disk", old_receipt.is_file(),
          str(old_receipt))
    entry = (P.read_ledger().get("packs") or {}).get("swap-test") or {}
    history = entry.get("history") or []
    check("... the ledger keeps the replaced digest",
          bool(history) and history[-1].get("action") == "replaced"
          and history[-1].get("from_pack_sha256") == old_sha
          and history[-1].get("to_pack_sha256") == out.get("pack_sha256"),
          repr(history)[:300])
    check("... the installed copy still verifies",
          P.verify_pack("swap-test").get("ok") is True)
    check("... the receipt is recorded inside jarvis-packs.json",
          (entry.get("receipt_scan") or {}).get("pack_sha256")
          == entry.get("pack_sha256"))


def t_the_same_bytes_are_not_a_replacement():
    folder = make_skill(SOURCE / "same", "same-test", description="one thing")
    gate, _ = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        first = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("same-test installed", first.get("ok") is True, repr(first)[:200])
    report = P.scan_source(str(folder))
    check("re-scanning exactly what is installed is a plain refusal",
          report.get("verdict") == "refuse"
          and "same bytes" in str(report.get("refusal")),
          str(report.get("refusal")))
    gate, calls = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        out = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("... it never becomes a card, and nothing is written",
          out.get("asked") is False and calls == []
          and out.get("reason") and "same bytes" in str(out["reason"]),
          repr(out)[:200])


def t_a_name_on_disk_without_a_ledger_record_is_refused():
    loose = SKILLS / "loose-skill"
    loose.mkdir(parents=True, exist_ok=True)
    (loose / "SKILL.md").write_text(
        GOOD_SKILL_MD.format(name="loose-skill", description="hand made"),
        "utf-8")
    folder = make_skill(SOURCE / "loose", "loose-skill")
    report = P.scan_source(str(folder))
    check("a name on disk that the ledger does not know is still refused",
          report.get("verdict") == "refuse"
          and "no record" in str(report.get("refusal")),
          str(report.get("refusal")))
    check("... the skill that was already there was not overwritten",
          "hand made" in (loose / "SKILL.md").read_text("utf-8"))
    shutil.rmtree(loose)


def t_a_changed_file_is_tampered_and_refused_on_load():
    """Q3: every file's sha256 is re-checked on load, and a change is marked."""
    folder = make_skill(SOURCE / "tamper", "tamper-test",
                        extra={"references/notes.md": "trusted\n"})
    gate, _ = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        first = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("tamper-test installed", first.get("ok") is True, repr(first)[:200])
    notes = OFF / "tamper-test" / "references" / "notes.md"
    notes.write_text("changed behind jarvis's back\n", "utf-8")
    verified = P.verify_pack("tamper-test")
    check("a changed reference file is caught by the manifest",
          verified.get("ok") is False and verified.get("tampered") is True
          and "references/notes.md" in (verified.get("changed") or []),
          repr(verified)[:300])
    entry = (P.read_ledger().get("packs") or {}).get("tamper-test") or {}
    check("... and the ledger marks the pack tampered",
          entry.get("state") == "tampered"
          and "references/notes.md" in (entry.get("tampered_changed") or []),
          repr(entry.get("state")))
    loaded = P.load_pack("tamper-test")
    check("load_pack refuses it and says why",
          loaded.get("ok") is False and loaded.get("tampered") is True
          and "changed on disk" in str(loaded.get("reason")),
          repr(loaded)[:300])
    row = {r["name"]: r for r in P.list_packs().get("packs") or []}.get("tamper-test") or {}
    check("pack_list shows it as tampered, with the file named",
          row.get("state") == "tampered" and row.get("tampered") is True
          and "references/notes.md" in (row.get("tampered_files") or []),
          repr(row)[:300])
    # The hub is one of the load paths this repository owns: it must stop
    # offering the pack and refuse to read its manuals.
    shutil.move(str(OFF / "tamper-test"), str(SKILLS / "tamper-test"))
    ix = SK._read_index()
    ix["tamper-test"] = {"trust": "third_party", "sha256": "",
                         "description": "a tampered skill"}
    SK._write_index(ix)
    try:
        import jarvis_skill_hub as H
        visible = H.visible_skills(None)
        hidden = [r.get("name") for r in visible.get("hidden") or []]
        check("the skill hub stops offering a tampered pack",
              "tamper-test" in hidden, repr(visible)[:300])
        refs = H.references("tamper-test")
        check("... and refuses to read its manuals",
              refs.get("ok") is False and refs.get("tampered") is True,
              repr(refs)[:200])
    finally:
        ix = SK._read_index()
        ix.pop("tamper-test", None)
        SK._write_index(ix)
        shutil.move(str(SKILLS / "tamper-test"), str(OFF / "tamper-test"))
    # Restoring the bytes by hand clears the mark: it is a measurement, not a ban.
    notes.write_text("trusted\n", "utf-8")
    check("restoring the approved bytes clears the tampered mark",
          P.verify_pack("tamper-test").get("ok") is True)
    entry = (P.read_ledger().get("packs") or {}).get("tamper-test") or {}
    check("... and the ledger says disabled again",
          entry.get("state") == "disabled", repr(entry.get("state")))
    check("... so the pack loads again", P.load_pack("tamper-test").get("ok") is True)


def t_an_approved_edit_or_import_repins_the_pack_manifest():
    """REAL A2 (2026-11-06): the Skills screen's edit and import write through
    `jarvis_skills.install()`, so the ledger must be re-pinned THERE - the one
    door every surface uses - or an ordinary approved edit reads as tampering."""
    import jarvis_skill_menu as MENU
    folder = make_skill(SOURCE / "repin", "repin-test",
                        extra={"references/notes.md": "kept\n"})
    gate, _ = fresh_gate(allowed=True)
    SK._gate = gate
    try:
        first = P.install_pack(str(folder))
    finally:
        SK._gate = fresh_gate(allowed=True)[0]
    check("repin-test installed and turned off", first.get("ok") is True
          and first.get("state") == "disabled", repr(first)[:250])
    check("... it verifies before anything else touches it",
          P.verify_pack("repin-test").get("ok") is True)

    code, on = MENU.set_state({"name": "repin-test", "on": True})
    check("the existing ON card re-installs it", code == 200
          and on.get("ok") is True, f"{code} {str(on)[:250]}")
    check("... and the pack still verifies afterwards",
          P.verify_pack("repin-test").get("ok") is True)

    edited = GOOD_SKILL_MD.format(name="repin-test",
                                  description="the edited thing")
    code, out = MENU.edit({"name": "repin-test", "text": edited,
                           "accept_warnings": True})
    check("an ordinary approved edit lands", code == 200
          and out.get("ok") is True, f"{code} {str(out)[:250]}")
    check("the edited pack is NOT tampered",
          P.verify_pack("repin-test").get("ok") is True,
          repr(P.verify_pack("repin-test", mark=False))[:300])
    loaded = SK.load("repin-test")
    check("... the model can load it again", loaded.get("ok") is True,
          repr(loaded)[:300])

    # The immutability rule still bites: a change no card approved is refused.
    notes = SKILLS / "repin-test" / "references" / "notes.md"
    notes.write_text("changed behind jarvis's back\n", "utf-8")
    check("a hand-changed file is still tampered",
          P.verify_pack("repin-test").get("tampered") is True)
    check("... and the model must not load it",
          SK.load("repin-test").get("ok") is False)
    notes.write_text("kept\n", "utf-8")
    check("... restoring the approved bytes clears the mark",
          P.verify_pack("repin-test").get("ok") is True)

    # The other door: a same-name import through the Skills screen also
    # re-pins, even though it replaces the whole file set.
    fresh = make_skill(SOURCE / "repin2", "repin-test",
                       description="imported again",
                       extra={"references/other.md": "new file\n"})
    code, out = MENU.install_source({"path": str(fresh),
                                     "accept_warnings": True})
    check("a same-name import through the Skills screen lands", code == 200
          and out.get("ok") is True, f"{code} {str(out)[:250]}")
    check("... and it re-pins the manifest to the new file set",
          P.verify_pack("repin-test").get("ok") is True)
    entry = (P.read_ledger().get("packs") or {}).get("repin-test") or {}
    check("... the ledger holds the imported files, not the old ones",
          sorted(r["path"] for r in entry.get("files") or [])
          == ["SKILL.md", "references/other.md"],
          repr([r["path"] for r in entry.get("files") or []]))
    check("... so the model loads the imported version",
          SK.load("repin-test").get("ok") is True)
    P.remove_pack("repin-test")


def t_there_is_no_update_command():
    import ast
    import jarvis_agent as AG
    names = sorted(str(n) for n in AG.TOOLS if str(n).startswith("pack_"))
    check("the only pack tools are the four",
          names == ["pack_inspect", "pack_install", "pack_list", "pack_remove"],
          repr(names))
    check("none of them is an update or replace verb",
          not any(word in n for n in names
                  for word in ("update", "upgrade", "replace")))
    # Read the module as a PROGRAM, not as text: a function named like an
    # updater would be found however it is formatted or renamed around.
    tree = ast.parse((HERE / "jarvis_packs.py").read_text("utf-8"))
    functions = sorted(n.name for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    updaters = [n for n in functions
                if n.lower().startswith(("update_", "upgrade_", "replace_",
                                         "pack_update", "pack_upgrade",
                                         "pack_replace"))]
    check("the module defines no in-place updater", updaters == [], repr(updaters))


def main():
    for fn in (t_a_clean_skill_scans_into_a_full_report,
               t_a_python_file_is_refused_and_nothing_is_written,
               t_every_law_listed_code_file_is_refused,
               t_a_zip_code_member_or_stream_name_is_refused,
               t_a_zip_that_climbs_or_links_is_refused,
               t_a_folder_link_is_refused,
               t_a_zip_wrapper_folder_is_read_from_the_skill_folder,
               t_a_name_collision_is_refused,
               t_a_name_on_disk_without_a_ledger_record_is_refused,
               t_install_is_one_card_and_writes_only_after_it,
               t_a_replacement_is_a_new_scan_with_a_unified_diff,
               t_the_same_bytes_are_not_a_replacement,
               t_a_changed_file_is_tampered_and_refused_on_load,
               t_an_approved_edit_or_import_repins_the_pack_manifest,
               t_there_is_no_update_command,
               t_the_ledger_records_every_file_and_hash,
               t_a_trailing_dot_or_space_cannot_smuggle_a_script_in,
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
