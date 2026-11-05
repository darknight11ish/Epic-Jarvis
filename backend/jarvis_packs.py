"""jarvis_packs.py - add and remove "packs" (a skill, later a plug-in) from a
local folder or a local .zip, with a FULL pre-install scan report.

WHAT A PACK IS HERE, AND WHY THIS FILE EXISTS

A *skill* is a folder with a `SKILL.md`: prompt text the model may read, and a
`scripts/` folder that is never run (`jarvis-backend/jarvis_skills.py:5-10`).
It is added through `jarvis_skill_menu.py`, which scans it and raises ONE
`modify_own_code` card. A *plug-in* is a folder of Python that runs inside the
backend at start-up (`jarvis_plugins.py:57-63`) and is NOT installed here yet:
phase 1 installs prompt-only skills only, and refuses anything that carries
code before a card is ever drawn.

What was missing, and this module adds, is four things:

  1. **A source.** Nothing recorded where an installed thing came from. The
     ledger (`jarvis-packs.json`, beside the config) records the kind, the
     name, the version, the source and its pin, the sha256 of every file
     written, when, and whether the pack is installed, off or removed.
  2. **A scan you can read before anything lands.** `scan_source()` builds one
     structured report - safety, compatibility, effectiveness, and the
     bookkeeping - and `sentences()` says the same thing in plain words. It is
     computed from the folder or the archive's own bytes, writes nothing, and
     is saved as a receipt on approval (`jarvis-packs-receipts/<name>-<hash>.json`).
  3. **A complete removal.** `remove_pack()` deletes exactly the files the
     ledger recorded, and never deletes a file the ledger does not know: a file
     the owner made beside it is reported and kept.
  4. **The verbs in chat**: `pack_list`, `pack_inspect`, `pack_install`,
     `pack_remove`.

IT DOES NOT DUPLICATE THE SCANNER OR THE CARD

`jarvis_skills.install()` is called for the copy - the same function the
Skills screen calls: the same scanner, the same quarantine, the same ONE
`modify_own_code` card. This module hands it a `note=` line carrying the scan
report, so the card shows exactly what was scanned. `jarvis_skill_menu.set_state`
is called to turn the pack off after install (the existing move to
`skills-off`), because nothing is enabled implicitly. Nothing here re-implements
`parse_skill`, `vet`, `install` or the off/on move.

WHAT THIS DELIBERATELY DOES NOT DO (phase 1)

  * No code packs. A folder or archive holding a `.py`, `.ps1`, `.exe`, `.dll`
    or any binary is REFUSED before the card, in one sentence naming the file.
    Code that runs inside Jarvis needs more than a scan; that is phase 2.
  * No network source: a local folder and a local `.zip` only. No git, no URL,
    no marketplace. Nothing here opens a socket, starts a program or writes
    outside the skills folder, `skills-off/`, the throwaway unpack folder and
    the ledger's own two files.
  * No update, no enable-from-here, no bulk install.

THE HONEST BOUNDARY, SAID ON THE CARD AND IN EVERY ANSWER

  * The scan reduces risk; it does not sandbox. A prompt-only skill is text,
    and text the model follows is still an instruction it will try to obey.
  * A sha256 proves the bytes did not change between the card and the disk. It
    does not prove who wrote them: there is no signing key in this project, so
    every pack reads `NOT VERIFIED`.
  * Nothing is enabled by installing it: the pack is moved to `skills-off`
    straight afterwards, so it is not offered to the model until the owner
    turns it on (the existing ON card).

Standard library only. No network, no subprocess, no import of the pack.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

#: The gate action the copy is decided under. `jarvis_skills.install()` raises
#: it and `jarvis_skill_menu` names the same one: the shipped action for
#: "changes the running program's own code", tier "ask". No new action, no new
#: tier line and no gate patch is invented here.
ACTION = "modify_own_code"

#: The one sentence every refusal-about-code answer carries. One wording, one
#: place, so the card, the chat answer and the suite cannot drift apart.
CODE_REFUSED = ("that pack contains executable code ({where}) - a file that can "
                "run on this PC - and code packs are not installed in this "
                "phase, so nothing was installed")

#: Suffixes that are code, a program, or a binary that can carry one. A
#: prompt-only skill has none of them; the existing skill scanner makes the
#: same judgement for a `scripts/` folder, which it keeps inert.
CODE_SUFFIXES = frozenset({
    ".py", ".pyw", ".pyc", ".pyo", ".pyd",
    ".ps1", ".psm1", ".psd1", ".bat", ".cmd", ".com", ".exe", ".dll", ".msi",
    ".scr", ".cpl", ".hta", ".vbs", ".vbe", ".wsf", ".wsh", ".jse",
    ".sh", ".bash", ".zsh", ".fish", ".command",
    ".js", ".mjs", ".cjs", ".ts", ".jar", ".class", ".war",
    ".so", ".dylib", ".bin", ".elf", ".apk", ".dex",
})

#: The ledger's own name, and the receipt folder's, both beside the config.
LEDGER_NAME = "jarvis-packs.json"
RECEIPTS_NAME = "jarvis-packs-receipts"

#: Set this to keep the ledger and receipts somewhere else. It exists for the
#: suites (a temp folder), the same way JARVIS_SKILLS_DIR exists for skills.
DIR_ENV = "JARVIS_PACKS_DIR"

#: What the ledger holds, and what a reader may rely on.
SCHEMA = 1

#: The files a pack is allowed to be. A skill's own bounds are the scanner's
#: (`jarvis_skills.MAX_FILES` / `MAX_SKILL_DIR`), read per call, never copied.
MAX_FILES = 64
MAX_BYTES = 5 * 1024 * 1024

#: How deep a `.zip` may nest a SKILL.md before it is refused. The same depth
#: `jarvis_skill_menu` uses for a Hermes folder.
MAX_DEPTH = 4

#: A skill name: the same rule `jarvis_skills` uses to address one.
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: A zip member that is absolute, has a drive letter, or climbs out.
_NOT_A_MEMBER = re.compile(r"^(?:[A-Za-z]:|[\\/]|.*(?:^|[\\/])\.\.(?:[\\/]|$))")

#: A heading that says when a skill should be used, and a short bullet under it.
_WHEN_RE = re.compile(r"^#{1,6}\s*(?:when to use|when to use this|triggers?|"
                      r"use this when|when this applies)\b.*$", re.I)

#: How many trigger bullets are worth showing. A card is read in seconds.
MAX_TRIGGERS = 4


# --------------------------------------------------------------------------
#   The modules beside this one, reached lazily so this file imports anywhere
# --------------------------------------------------------------------------

def _sk():
    """jarvis_skills, or None. None is an answer: every door says so."""
    try:
        import jarvis_skills
        return jarvis_skills
    except Exception:
        return None


def _menu():
    """jarvis_skill_menu, or None. The OFF move is its own, reused."""
    try:
        import jarvis_skill_menu
        return jarvis_skill_menu
    except Exception:
        return None


def _plugins():
    """jarvis_plugins, or None - so a plugin folder can be listed, not changed."""
    try:
        import jarvis_plugins
        return jarvis_plugins
    except Exception:
        return None


# --------------------------------------------------------------------------
#   Where the ledger lives. Read per call, never captured at import: a suite
#   points JARVIS_PACKS_DIR at a temp folder and then imports this module.
# --------------------------------------------------------------------------

def config_dir() -> Path:
    """The folder the config lives in - `jarvis-framework.toml`'s own parent.

    `jarvis_framework.config_path()` is the one authority on where that is,
    including the JARVIS_FRAMEWORK_TOML override. When no config file exists
    at all (a bare suite, or a PC before the first run), the same fallback the
    framework module itself uses: `~/.openjarvis`.
    """
    try:
        import jarvis_framework as fw
        found = fw.config_path()
        if found is not None:
            return Path(found).resolve().parent
        base = Path(str(getattr(fw, "CONFIG_DIR", "")))
        if str(base):
            return base
    except Exception:
        pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def packs_dir() -> Path:
    """Where the ledger and the receipts go: the config folder by default."""
    named = str(os.environ.get(DIR_ENV) or "").strip()
    if named:
        return Path(named)
    return config_dir()


def ledger_path() -> Path:
    return packs_dir() / LEDGER_NAME


def receipts_dir() -> Path:
    return packs_dir() / RECEIPTS_NAME


def _skills_root() -> Optional[Path]:
    menu = _menu()
    if menu is not None:
        try:
            root = menu.skills_root()
            return Path(root) if root is not None else None
        except Exception:
            return None
    sk = _sk()
    return Path(sk.SKILLS_DIR) if sk is not None else None


def _off_root() -> Optional[Path]:
    menu = _menu()
    if menu is not None:
        try:
            root = menu.off_root()
            return Path(root) if root is not None else None
        except Exception:
            return None
    root = _skills_root()
    return None if root is None else root.parent / "skills-off"


# --------------------------------------------------------------------------
#   The ledger: one JSON file, every file that was written
# --------------------------------------------------------------------------

def read_ledger() -> dict:
    """The ledger as a dict. A missing or broken file is an empty ledger, and
    both are said out loud rather than raising into a turn."""
    path = ledger_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA, "packs": {}, "note": ""}
    except Exception as exc:
        return {"schema": SCHEMA, "packs": {},
                "note": (f"the pack ledger at {path} could not be read "
                         f"({type(exc).__name__}), so it was treated as empty. "
                         f"Nothing was deleted.")}
    if not isinstance(data, dict):
        return {"schema": SCHEMA, "packs": {},
                "note": f"the pack ledger at {path} is not an object"}
    if not isinstance(data.get("packs"), dict):
        data["packs"] = {}
    return data


def _write_ledger(data: dict) -> bool:
    """Write the ledger atomically. False is an answer: the caller says so."""
    path = ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _entry(name: str) -> dict:
    return dict((read_ledger().get("packs") or {}).get(name) or {})


def _save_entry(entry: dict) -> bool:
    data = read_ledger()
    packs = data.setdefault("packs", {})
    packs[str(entry.get("name"))] = entry
    data["schema"] = SCHEMA
    data.pop("note", None)
    return _write_ledger(data)


# --------------------------------------------------------------------------
#   Hashing, and the small filesystem steps
# --------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(262144), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_digest(files: list) -> str:
    """One digest over every (path, sha256) in a pack, in path order.

    It proves the SET of files and their bytes are what the card showed. It is
    not a signature and says nothing about who wrote them.
    """
    h = hashlib.sha256()
    for row in sorted(files, key=lambda r: str(r.get("path", ""))):
        h.update(str(row.get("path", "")).replace("\\", "/").encode("utf-8"))
        h.update(b"\0")
        h.update(str(row.get("sha256", "")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _walk_files(folder: Path) -> list:
    """Every regular file under `folder`, as posix relative paths, sorted."""
    out = []
    try:
        for f in sorted(Path(folder).rglob("*")):
            if f.is_file():
                out.append(f.relative_to(folder).as_posix())
    except OSError:
        return out
    return out


def file_rows(folder: Path) -> list:
    """[{path, sha256, bytes}] for every file in a folder, in path order."""
    rows = []
    for rel in _walk_files(folder):
        full = Path(folder) / rel
        try:
            rows.append({"path": rel, "sha256": _sha256_file(full),
                         "bytes": int(full.stat().st_size)})
        except OSError as exc:
            rows.append({"path": rel, "sha256": "", "bytes": 0,
                         "error": type(exc).__name__})
    return rows


def _is_code(path: str) -> bool:
    return Path(str(path)).suffix.lower() in CODE_SUFFIXES


def _is_binary(path: Path) -> bool:
    """A NUL byte, or bytes that are not UTF-8 text. A skill is text."""
    try:
        raw = path.read_bytes()[:65536]
    except OSError:
        return False
    if b"\0" in raw:
        return True
    try:
        raw.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _inside(root: Path, path: Path) -> bool:
    """True when `path` is really under `root` after resolution."""
    try:
        root = Path(root).resolve()
        path = Path(path).resolve()
    except OSError:
        return False
    return path == root or root in path.parents


def _clean_name(value: Any) -> str:
    name = str(value or "").strip()
    if not _NAME_RE.match(name) or len(name) > 64:
        return ""
    return name


# --------------------------------------------------------------------------
#   Reading a skill's own SKILL.md WITHOUT copying it anywhere
# --------------------------------------------------------------------------

def _frontmatter(text: str) -> tuple:
    """(fields, body) from a SKILL.md's own frontmatter, or ({}, text).

    `jarvis_skills._parse_frontmatter` is the existing parser, called - never
    copied. A file that will not parse is the caller's refusal, not a crash.
    """
    sk = _sk()
    if sk is not None:
        try:
            return sk._parse_frontmatter(text)
        except Exception:
            return {}, text
    return {}, text


def _declared_tools(values: Any) -> list:
    """The tool names a skill DECLARES it would like, as plain names.

    Never a grant: nothing in the skill menu or the hub enforces `allowed-tools`
    (measured 2026-11-05), so the report shows them as a request and says so.
    """
    raw = values if isinstance(values, (list, tuple)) else [values]
    out = []
    for item in raw:
        for part in re.split(r"[,\s]+", str(item or "").strip().strip("[]'\"")):
            part = part.strip().strip("[]'\"")
            if part and part.lower() not in ("none", "null"):
                out.append(part)
    return out


def _trigger_phrases(body: str, description: str) -> list:
    """What the model would pick this skill up on, in the skill's own words.

    The description is the line that actually drives selection - it is the one
    every card carries for every skill. The bullets under a "when to use"
    heading are shown too when the skill writes them, because they are the
    clearest statement a reader gets.
    """
    out = []
    line = " ".join(str(description or "").split())
    if line:
        out.append(line)
    lines = str(body or "").splitlines()
    for i, raw in enumerate(lines):
        if not _WHEN_RE.match(raw.strip()):
            continue
        for follow in lines[i + 1:]:
            text = follow.strip()
            if text.startswith("#"):
                break
            if text.startswith(("- ", "* ")):
                text = text[2:].strip()
                if 3 <= len(text) <= 120:
                    out.append(text)
                if len(out) >= MAX_TRIGGERS:
                    break
        break
    return out[:MAX_TRIGGERS]


def _tokens(text: str) -> int:
    """The honest prompt-token estimate for a text, with the chat's own rule.

    `jarvis_agent.estimate_tokens` is the function the chat's budget uses, so
    the number on the card is the number that is really spent - not a guess in
    a different unit. When the agent module cannot be imported (a bare suite),
    the same pessimistic 4-characters-per-token rule it uses.
    """
    try:
        import jarvis_agent
        return int(jarvis_agent.estimate_tokens(
            [{"role": "user", "content": str(text or "")}]))
    except Exception:
        return max(1, len(str(text or "")) // 4)


# --------------------------------------------------------------------------
#   The scan: safety, compatibility, effectiveness, and the bookkeeping
# --------------------------------------------------------------------------

def _finding(severity: str, code: str, message: str, where: str = "") -> dict:
    return {"severity": severity, "code": code, "message": message, "where": where}


def _refused(why: str, *, report: Optional[dict] = None) -> dict:
    """A report nobody is asked about: a hard refusal, never a card."""
    out = dict(report or _empty_report())
    out["verdict"] = "refuse"
    out["asked"] = False
    out["refusal"] = why
    out.setdefault("findings", []).append(
        _finding("block", "refused", why))
    out["sentences"] = sentences(out)
    return out


def _empty_report() -> dict:
    return {
        "schema": SCHEMA,
        "pack": {"name": "", "kind": "skill", "version": "", "summary": "",
                 "has_code": False, "licence": "", "bytes": 0, "files": 0,
                 "modified": ""},
        "source": {"type": "folder", "ref": "", "pin": {}},
        "digest": {"pack_sha256": "", "files": []},
        "verdict": "malformed",
        "findings": [],
        "declared": {"allowed_tools": [], "requires": {}, "kind": "skill"},
        "observed": {"code_files": [], "binary_files": [], "scanner": {}},
        "compatibility": {},
        "effectiveness": {},
        "trust": {"rung": "unsigned", "detail": "unsigned - NOT VERIFIED",
                  "signer": None},
        "uninstall": {"files": [], "stores": [], "routes": [], "jobs": [],
                      "credentials": [],
                      "completeness": "complete"},
        "restart": "",
        "receipt": {},
        "asked": False,
    }


def _manifest_of(folder: Path) -> dict:
    """A pack's optional `pack.json`, or {} - the extra manifest a pack may
    carry beside its SKILL.md. A malformed one refuses the pack."""
    path = Path(folder) / "pack.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"pack.json will not parse ({type(exc).__name__})"}
    if not isinstance(data, dict):
        return {"_error": "pack.json is not an object"}
    return data


def _scan_folder_folder(folder: Path) -> dict:
    """The report for a local folder. Reads only; writes nothing at all."""
    report = _empty_report()
    report["source"] = {"type": "folder", "ref": str(folder),
                        "pin": {"mtime": ""}}
    try:
        report["source"]["pin"]["mtime"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(Path(folder).stat().st_mtime))
    except OSError:
        pass
    # A pack is not a backend. Both names are refused before anything else is
    # read, because a folder holding them is not a skill by any reading.
    for bad in ("jarvis_hud.py", "backend"):
        if (Path(folder) / bad).exists():
            return _refused(
                f"that folder is a Jarvis backend, not a pack - it holds {bad!r} "
                f"- so nothing was read and nothing was installed",
                report=report)
    sk = _sk()
    if sk is None:
        return _refused("the skill library is not beside this file, so there is "
                        "nothing to scan with", report=report)
    manifest = _manifest_of(folder)
    if manifest.get("_error"):
        return _refused(f"that pack's pack.json cannot be read ({manifest['_error']})",
                        report=report)
    kind = str(manifest.get("kind") or "skill").strip().lower() or "skill"
    report["declared"]["kind"] = kind
    if kind != "skill":
        return _refused(
            f"that pack says it is a {kind!r} pack, and phase 1 installs "
            f"prompt-only skills only - nothing was installed", report=report)

    # ---- SAFETY: every file, its hash, and whether any of it can run -------
    rows = file_rows(folder)
    code, binaries = [], []
    for row in rows:
        if _is_code(row["path"]):
            code.append(row["path"])
        else:
            try:
                if _is_binary(Path(folder) / row["path"]):
                    binaries.append(row["path"])
            except OSError:
                pass
    report["digest"]["files"] = rows
    report["digest"]["pack_sha256"] = pack_digest(rows)
    report["pack"]["files"] = len(rows)
    report["pack"]["bytes"] = sum(int(r.get("bytes") or 0) for r in rows)
    report["observed"]["code_files"] = code
    report["observed"]["binary_files"] = binaries
    report["pack"]["has_code"] = bool(code or binaries)
    for row in rows:
        if _is_code(row["path"]):
            report["findings"].append(_finding(
                "block", "code_file",
                "a file that can run on this PC", row["path"]))
        elif row["path"] in binaries:
            report["findings"].append(_finding(
                "block", "binary_file",
                "a file that is not text, so what it holds cannot be read",
                row["path"]))
    if code or binaries:
        where = (code or binaries)[0]
        return _refused(CODE_REFUSED.format(where=where), report=report)

    # ---- the existing scanner's verdict, before anything else is decided ---
    skill, why = None, ""
    try:
        skill = sk.parse_skill(Path(folder), trust="third_party")
    except Exception as exc:
        why = str(exc)
    if skill is None:
        return _refused(f"that folder is not a skill: {why}", report=report)
    report["pack"]["name"] = skill.name
    report["pack"]["summary"] = skill.description
    report["pack"]["licence"] = str(getattr(skill, "license", "") or "")
    report["pack"]["version"] = str(
        (getattr(skill, "extra_fields", {}) or {}).get("version")
        or manifest.get("version") or "")
    report["declared"]["allowed_tools"] = _declared_tools(
        getattr(skill, "allowed_tools", []) or [])
    report["declared"]["requires"] = dict(manifest.get("requires") or {})

    md = Path(folder) / "SKILL.md"
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    try:
        vet = sk.vet(skill)
    except Exception as exc:
        return _refused(f"the skill scanner could not read it ({type(exc).__name__})",
                        report=report)
    report["observed"]["scanner"] = {
        "verdict": vet.get("verdict"), "summary": vet.get("summary"),
        "blocking": vet.get("blocking"), "warnings": vet.get("warnings")}
    for item in vet.get("findings") or []:
        sev = str(item.get("severity") or "note")
        report["findings"].append(_finding(
            sev, str(item.get("code") or "scanner"),
            str(item.get("message") or ""), str(item.get("where") or "")))
    if vet.get("verdict") == "refuse":
        return _refused(
            "the existing skill scanner refuses this one, so it never becomes a "
            "card: " + str(vet.get("summary") or "a blocking finding"),
            report=report)

    # ---- COMPATIBILITY -----------------------------------------------------
    report["compatibility"] = _compatibility(report, manifest)
    if report["compatibility"].get("collision"):
        return _refused(report["compatibility"]["collision"], report=report)
    report["uninstall"] = {
        "files": [r["path"] for r in rows], "stores": [], "routes": [],
        "jobs": [], "credentials": [], "completeness": "complete"}
    report["restart"] = _restart_line("skill")

    # ---- EFFECTIVENESS -----------------------------------------------------
    body = text
    fm, parsed_body = _frontmatter(text)
    if parsed_body:
        body = parsed_body
    if not report["pack"]["version"]:
        report["pack"]["version"] = str(fm.get("version") or "")
    report["effectiveness"] = {
        "mode": "rubric",
        "trigger_phrases": _trigger_phrases(body, skill.description),
        "prompt_tokens": _tokens(text),
        "prompt_tokens_note": ("an estimate from the SKILL.md's own text, with "
                               "the chat's own token estimate"),
        "what_changes": _what_changes(skill, body),
        "smoke": {"ran": False,
                  "why": ("a prompt-only skill has nothing to run: its text is "
                          "read by the model, never executed")},
    }
    report["verdict"] = "clean" if vet.get("verdict") == "clean" else "review"
    report["pack"]["modified"] = str(report["source"]["pin"].get("mtime") or "")
    report["sentences"] = sentences(report)
    return report


def _compatibility(report: dict, manifest: dict) -> dict:
    """Will it work here, and will it break anything? Read, never guessed."""
    out = {"name": report["pack"].get("name", ""), "collision": ""}
    name = str(report["pack"].get("name") or "")
    if not name:
        out["collision"] = "that pack names no skill, so nothing was installed"
        return out
    # A name that is already installed, or already turned off, is a collision:
    # installing would replace a skill the owner has, which is an UPDATE and
    # gets its own diff and its own card - not a silent overwrite.
    root, off = _skills_root(), _off_root()
    for base, where in ((root, "the skills folder"), (off, "the turned-off folder")):
        if base is None:
            continue
        if (Path(base) / name).exists():
            out["collision"] = (f"a skill called {name!r} is already in {where}, "
                                f"so nothing was installed - remove it first, or "
                                f"give this one a different name")
            return out
    known = read_ledger().get("packs") or {}
    if name in known and str((known.get(name) or {}).get("state")) != "removed":
        out["collision"] = (f"the pack ledger already records a pack called "
                            f"{name!r}, so nothing was installed")
        return out
    out["python"] = {"running": "%d.%d" % _python_version()}
    want = str((manifest.get("requires") or {}).get("python") or "").strip()
    if want:
        out["python"]["declared"] = want
        out["python"]["ok"] = _python_ok(want)
        if not out["python"]["ok"]:
            out["collision"] = (f"that pack needs Python {want} and this PC runs "
                                f"{out['python']['running']}, so nothing was installed")
            return out
    else:
        out["python"]["declared"] = ""
        out["python"]["ok"] = True
    jarvis_min = str((manifest.get("requires") or {}).get("min_jarvis_version") or "")
    out["jarvis"] = {"declared": jarvis_min, "running": _jarvis_version(),
                     "ok": True}
    if jarvis_min and not _version_ok(_jarvis_version(), jarvis_min):
        out["collision"] = (f"that pack needs Jarvis {jarvis_min} or newer and this "
                            f"PC runs {out['jarvis']['running'] or 'an unknown version'}, "
                            f"so nothing was installed")
        return out
    out["writes_to"] = str((_off_root() or Path("skills-off")) / name)
    out["restart"] = _restart_line("skill")
    return out


def _python_version() -> tuple:
    import sys
    return (sys.version_info[0], sys.version_info[1])


def _python_ok(declared: str) -> bool:
    """Does `>=3.10` / `>=3.10,<4` hold for the running Python? False if the
    declaration cannot be read - an unreadable requirement is not a pass."""
    try:
        import sys
        cur = "%d.%d.%d" % (sys.version_info[0], sys.version_info[1],
                            sys.version_info[2])
        for part in str(declared).split(","):
            part = part.strip()
            m = re.match(r"^(>=|<=|==|>|<)\s*(\d+)(?:\.(\d+))?", part)
            if not m:
                if part:
                    return False
                continue
            op, major, minor = m.group(1), int(m.group(2)), m.group(3)
            want = (major, int(minor) if minor is not None else 0)
            have = (sys.version_info[0], sys.version_info[1])
            if op == ">=" and not have >= want:
                return False
            if op == ">" and not have > want:
                return False
            if op == "<=" and not have <= want:
                return False
            if op == "<" and not have < want:
                return False
            if op == "==" and not have == want:
                return False
        del cur
        return True
    except Exception:
        return False


def _jarvis_version() -> str:
    try:
        import jarvis_framework as fw
        return str(getattr(fw, "VERSION", "") or "")
    except Exception:
        return ""


def _version_ok(running: str, wanted: str) -> bool:
    if not running:
        return False
    try:
        return tuple(int(p) for p in running.split(".")[:3]) >= tuple(
            int(p) for p in wanted.split(".")[:3])
    except Exception:
        return False


def _restart_line(kind: str) -> str:
    """Does this need Jarvis restarted? The honest answer, per kind.

    A skill is read by the model, not loaded into the process: its list is
    re-read on the next turn, so nothing needs restarting. A plug-in is
    imported at start-up, so its routes and code answer until Jarvis restarts -
    which is why phase 1 has no plug-in case, and the sentence is still here for
    the day one lands.
    """
    if kind == "plugin":
        return ("A plug-in is loaded when Jarvis starts: until Jarvis is "
                "restarted its code and its routes answer as they did before. I "
                "cannot restart Jarvis for you.")
    return ("Nothing needs restarting for a skill: the model is given the skill "
            "list again on the next turn, so the change is live at once.")


def _what_changes(skill: Any, body: str) -> str:
    """One sentence, in the owner's words, on what this pack changes."""
    line = " ".join(str(getattr(skill, "description", "") or "").split())
    if line:
        return (f"The model gets one more thing it can do: {line} It is OFF "
                f"until you turn it on.")
    return ("The model gets one more page of instructions it may read. It is OFF "
            "until you turn it on.")


def scan_source(source: Any) -> dict:
    """The full report for a folder or a .zip. WRITES NOTHING, raises no card.

    This is what `pack_inspect` answers with, and what `pack_install` shows on
    the card. A refusal here never becomes a card.
    """
    named = str(source or "").strip()
    report = _empty_report()
    if not named:
        return _refused("name a folder or a .zip on this PC to scan, so nothing "
                        "was scanned and nothing was installed", report=report)
    try:
        path = Path(os.path.expanduser(named)).resolve()
    except OSError as exc:
        return _refused(f"that path could not be read ({exc})", report=report)
    if path.is_dir():
        return _scan_folder_folder(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return _scan_zip(path)
    return _refused(f"{named!r} is not a folder or a .zip on this PC, so nothing "
                    f"was scanned and nothing was installed", report=report)


def _scan_zip(zip_path: Path) -> dict:
    """A .zip's report, read from the archive IN MEMORY - nothing is unpacked.

    Every bound is a refusal, never a truncation: an absolute member, a climb,
    a link, too many files, too much bytes, or two SKILL.md refuses the whole
    archive before a byte is written. The zip's own sha256 is the pin, and the
    pack's digest is computed over the files it holds.
    """
    report = _empty_report()
    try:
        raw = Path(zip_path).read_bytes()
    except OSError as exc:
        return _refused(f"that .zip could not be read ({exc})", report=report)
    report["source"] = {"type": "zip", "ref": str(zip_path),
                        "pin": {"sha256": sha256_bytes(raw)}}
    if len(raw) > 4 * MAX_BYTES:
        return _refused(f"that .zip is larger than {4 * MAX_BYTES // (1024 * 1024)} "
                        f"MB, which is far more than a skill may hold", report=report)
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        return _refused(f"that .zip could not be opened ({exc})", report=report)
    rows, code, binaries, skills = [], [], [], []
    total, files = 0, 0
    try:
        with archive:
            for info in archive.infolist():
                name = str(info.filename or "").replace("\\", "/")
                if not name or name.endswith("/") or name.startswith("__MACOSX/"):
                    continue
                if _NOT_A_MEMBER.match(name):
                    return _refused(
                        f"the .zip holds a file that points outside itself "
                        f"({name!r}), so it was not unpacked and nothing was "
                        f"installed", report=report)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    return _refused(
                        f"the .zip holds a link ({name!r}), and a skill is only "
                        f"ever plain files, so nothing was installed", report=report)
                files += 1
                total += int(info.file_size or 0)
                if files > MAX_FILES:
                    return _refused(f"the .zip holds more than {MAX_FILES} files, "
                                    f"which is more than a skill may have, so "
                                    f"nothing was installed", report=report)
                if total > MAX_BYTES:
                    return _refused(
                        f"the .zip unpacks to more than {MAX_BYTES // (1024 * 1024)} "
                        f"MB, which is more than a skill may have, so nothing was "
                        f"installed", report=report)
                data = archive.read(info)
                digest = sha256_bytes(data)
                rows.append({"path": name, "sha256": digest, "bytes": len(data)})
                base = Path(name).name
                if _is_code(name):
                    code.append(name)
                elif b"\0" in data[:65536]:
                    binaries.append(name)
                if base == "SKILL.md":
                    skills.append((name, data))
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        return _refused(f"that .zip could not be read ({exc})", report=report)
    report["digest"]["files"] = rows
    report["digest"]["pack_sha256"] = pack_digest(rows)
    report["pack"]["files"] = len(rows)
    report["pack"]["bytes"] = total
    report["observed"]["code_files"] = code
    report["observed"]["binary_files"] = binaries
    report["pack"]["has_code"] = bool(code or binaries)
    for name in code:
        report["findings"].append(_finding(
            "block", "code_file", "a file that can run on this PC", name))
    if code or binaries:
        return _refused(CODE_REFUSED.format(
            where=(code or binaries)[0]), report=report)
    if not skills:
        return _refused("that .zip holds no SKILL.md, so there is no skill in it "
                        "and nothing was installed", report=report)
    if len(skills) > 1:
        names = ", ".join(sorted(Path(n).name for n, _ in skills[:6]))
        return _refused(f"that .zip holds {len(skills)} skills ({names}), and one "
                        f"at a time is the only thing chat installs, so nothing "
                        f"was installed", report=report)
    rel, data = skills[0]
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    fm, body = _frontmatter(text)
    name = _clean_name(fm.get("name"))
    if not name:
        return _refused("the SKILL.md in that .zip names no skill, so nothing was "
                        "installed", report=report)
    report["pack"]["name"] = name
    report["pack"]["summary"] = str(fm.get("description") or "")
    report["pack"]["licence"] = str(fm.get("license") or "")
    report["pack"]["version"] = str(fm.get("version") or "")
    tools = str(fm.get("allowed-tools") or fm.get("allowed_tools") or "").strip()
    report["declared"]["allowed_tools"] = [
        t.strip().strip("[]'\"") for t in re.split(r"[, ]+", tools) if t.strip()]
    manifest: dict = {}
    for row in rows:
        if Path(row["path"]).name == "pack.json":
            try:
                found = archive_read(zip_path, row["path"])
                manifest = json.loads(found.decode("utf-8"))
                if not isinstance(manifest, dict):
                    manifest = {"_error": "pack.json is not an object"}
            except Exception as exc:
                manifest = {"_error": f"pack.json will not parse ({type(exc).__name__})"}
            break
    if manifest.get("_error"):
        return _refused(f"that pack's pack.json cannot be read ({manifest['_error']})",
                        report=report)
    kind = str(manifest.get("kind") or "skill").strip().lower() or "skill"
    if kind != "skill":
        return _refused(f"that pack says it is a {kind!r} pack, and phase 1 "
                        f"installs prompt-only skills only, so nothing was "
                        f"installed", report=report)
    report["declared"]["kind"] = kind
    report["declared"]["requires"] = dict(manifest.get("requires") or {})
    report["pack"]["version"] = report["pack"]["version"] or str(
        manifest.get("version") or "")
    report["compatibility"] = _compatibility(report, manifest)
    if report["compatibility"].get("collision"):
        return _refused(report["compatibility"]["collision"], report=report)
    report["uninstall"] = {"files": [r["path"] for r in rows], "stores": [],
                           "routes": [], "jobs": [], "credentials": [],
                           "completeness": "complete"}
    report["restart"] = _restart_line("skill")
    report["effectiveness"] = {
        "mode": "rubric",
        "trigger_phrases": _trigger_phrases(body, report["pack"]["summary"]),
        "prompt_tokens": _tokens(text),
        "prompt_tokens_note": ("an estimate from the SKILL.md's own text, with "
                               "the chat's own token estimate"),
        "what_changes": (f"The model gets one more thing it can do: "
                         f"{report['pack']['summary']} It is OFF until you turn "
                         f"it on." if report["pack"]["summary"] else
                         "The model gets one more page of instructions it may "
                         "read. It is OFF until you turn it on."),
        "smoke": {"ran": False, "why": "nothing to run: prompt-only"},
    }
    sk = _sk()
    scan = {}
    if sk is not None:
        try:
            found = sk.scan_text(text, "SKILL.md")
            scan = {"blocking": len([f for f in found
                                     if getattr(f, "severity", "") == "block"]),
                    "warnings": len([f for f in found
                                     if getattr(f, "severity", "") == "warn"])}
            for item in found:
                scan.setdefault("findings", []).append(
                    {"severity": getattr(item, "severity", "note"),
                     "code": getattr(item, "code", ""),
                     "message": getattr(item, "message", ""),
                     "where": getattr(item, "where", "")})
            if scan.get("blocking"):
                report["observed"]["scanner"] = scan
                return _refused(
                    "the existing skill scanner refuses the SKILL.md in that .zip, "
                    "so it never becomes a card", report=report)
        except Exception:
            scan = {}
    report["observed"]["scanner"] = scan
    report["verdict"] = "review" if scan.get("warnings") else "clean"
    report["sentences"] = sentences(report)
    return report


def archive_read(zip_path: Path, member: str) -> bytes:
    """One member's bytes, by name. Only used on the already-bounded archive."""
    with zipfile.ZipFile(zip_path) as archive:
        return archive.read(member)


# --------------------------------------------------------------------------
#   The same report, in plain words - the thing the owner actually reads
# --------------------------------------------------------------------------

def sentences(report: dict) -> dict:
    """`what is this, what will it change, is it safe, will it work here`.

    Built from the report's own fields, never from a model: every sentence here
    is a restatement of something measured above it.
    """
    pack = report.get("pack") or {}
    ref = str((report.get("source") or {}).get("ref") or "")
    name = str(pack.get("name") or "")
    kind = str(pack.get("kind") or "skill")
    files = int(pack.get("files") or 0)
    size = int(pack.get("bytes") or 0)
    digest = str((report.get("digest") or {}).get("pack_sha256") or "")
    verdict = str(report.get("verdict") or "malformed")
    if verdict in ("refuse", "malformed"):
        return {
            "what": f"Nothing would be installed: {ref or 'that source'} was refused.",
            "changes": "Nothing changes on this PC.",
            "safe": str(report.get("refusal") or "The scan refused it."),
            "works": "Not asked - a pack the scan refuses never becomes a card.",
        }
    summary = str(pack.get("summary") or "").strip().rstrip(".")
    what = (f"{'A skill' if kind == 'skill' else 'A pack'} called {name!r}"
            + (f" - {summary}" if summary else "")
            + f", in {files} file(s), {size} bytes, from {ref}.")
    eff = report.get("effectiveness") or {}
    tokens = eff.get("prompt_tokens")
    changes = (eff.get("what_changes")
               or "It adds one more thing the model may read. It is OFF until "
                  "you turn it on.")
    safe = (f"Instructions only - no file in it can run"
            f" ({files} file(s), none executable). The digest is {digest[:12]}..., "
            f"and every file's own fingerprint is in the receipt. It is "
            f"NOT VERIFIED: no signing key exists, so a checksum proves the "
            f"bytes did not change, never who wrote them.")
    compat = report.get("compatibility") or {}
    py = compat.get("python") or {}
    works = (f"It will work here: Python {py.get('running') or 'is present'}"
             + (f" meets the {py.get('declared')} it asks for" if py.get("declared") else "")
             + f", and no skill with that name exists on this PC yet. "
               f"It is written to {compat.get('writes_to') or 'the skills folder'}, "
               f"then turned OFF. {report.get('restart') or ''}").strip()
    return {"what": what, "changes": changes, "safe": safe, "works": works}


def card_text(report: dict) -> str:
    """The ONE install card's own words, built from the report.

    It names the pack, where it came from, its digest, what it contains, and
    the honest boundary. `jarvis_skills.install()` puts this on the card it
    raises; nothing here can skip that card or approve anything.
    """
    pack = report.get("pack") or {}
    src = report.get("source") or {}
    eff = report.get("effectiveness") or {}
    compat = report.get("compatibility") or {}
    said = sentences(report)
    lines = [
        f"Install the skill {str(pack.get('name') or '')!r}"
        + (f" version {pack.get('version')}" if pack.get("version") else "")
        + "?",
        "",
        f"From:      {src.get('ref') or 'a folder on this PC'}"
        + (f"  (zip sha256 {str((src.get('pin') or {}).get('sha256'))[:12]}...)"
           if (src.get("pin") or {}).get("sha256") else
           f"  (folder last changed {str((src.get('pin') or {}).get('mtime') or 'unknown')})"),
        f"SHA-256:   {str((report.get('digest') or {}).get('pack_sha256') or '')[:16]}...",
        f"Contains:  instructions only - no code ({pack.get('files')} file(s), "
        f"{pack.get('bytes')} bytes)",
        "",
        "WHAT IT IS",
        f"  {said['what']}",
        "",
        "WHAT IT CHANGES FOR YOU",
        f"  {said['changes']}"
        + (f"  It costs about {eff.get('prompt_tokens')} prompt tokens when read."
           if eff.get("prompt_tokens") else ""),
        "",
        "IS IT SAFE",
        f"  {said['safe']}",
        "",
        "WILL IT WORK HERE",
        f"  {said['works']}",
        "",
        "LICENCE:   " + (str(pack.get("licence") or "") or "not declared"),
        "TRUST:     NOT VERIFIED - unsigned. A hash proves the bytes, never the author.",
        "REMOVAL:   " + (
            "say \"remove the " + str(pack.get("name")) + " pack\" and I delete "
            "exactly the files in this receipt; a file you made beside it is kept."),
        "",
        "WHAT THE SCAN CANNOT DO: it does not sandbox anything, and a clean scan "
        "is not permission.",
        "",
        "If you say yes, the files are copied in and then turned OFF at once - "
        "the model is not offered it until you turn it on, which is its own "
        "card. If you say no, nothing is written at all.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Installing: the existing scanner and card, then the ledger and receipt
# --------------------------------------------------------------------------

def _extract_zip(zip_path: Path, into: Path) -> tuple:
    """Unpack the already-scanned archive into a throwaway folder.

    The archive's names were checked by `_scan_zip` (absolute, climb, link,
    count, size), and are checked AGAIN here because the scan and the copy are
    two different reads: a file that changed between them must not land. The
    same `_inside()` containment check `jarvis_skill_menu` uses closes it.
    """
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        return None, f"that .zip could not be opened ({exc})"
    files = 0
    total = 0
    try:
        with archive:
            for info in archive.infolist():
                name = str(info.filename or "").replace("\\", "/")
                if not name or name.endswith("/") or name.startswith("__MACOSX/"):
                    continue
                if _NOT_A_MEMBER.match(name):
                    return None, (f"the .zip holds a file that points outside "
                                  f"itself ({name!r})")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    return None, f"the .zip holds a link ({name!r})"
                files += 1
                total += int(info.file_size or 0)
                if files > MAX_FILES or total > MAX_BYTES:
                    return None, "the .zip is larger than a skill may be"
                parts = [p for p in name.split("/") if p not in ("", ".")]
                dest = Path(into).joinpath(*parts)
                if not _inside(into, dest):
                    return None, (f"the .zip holds a file that points outside "
                                  f"itself ({name!r})")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out, 64 * 1024)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        return None, f"that .zip could not be unpacked ({exc})"
    # One SKILL.md, at most MAX_DEPTH deep, is the one skill in it.
    found = []
    try:
        for md in sorted(Path(into).rglob("SKILL.md")):
            if not md.is_file():
                continue
            rel = md.relative_to(into)
            if len(rel.parts) > MAX_DEPTH or any(p.startswith(".") for p in rel.parts):
                continue
            found.append(md.parent)
    except OSError as exc:
        return None, f"the unpacked folder could not be read ({exc})"
    if not found:
        return None, "the .zip holds no SKILL.md"
    if len(found) > 1:
        return None, "the .zip holds more than one skill"
    return found[0], ""


def _write_receipt(report: dict, entry: dict, card: str) -> str:
    """Save the report as a receipt, beside the ledger. Never overwrites: an
    install of the same digest a second time gets its own file."""
    folder = receipts_dir()
    name = str((report.get("pack") or {}).get("name") or "pack")
    digest = str((report.get("digest") or {}).get("pack_sha256") or "0" * 12)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}-{digest[:12]}-{stamp}.json"
        body = dict(report)
        body["receipt"] = {
            "approved_by": "owner",
            "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "card_text_sha256": sha256_bytes(card.encode("utf-8")),
            "ledger": entry,
        }
        path.write_text(json.dumps(body, indent=2, sort_keys=True), "utf-8")
        return str(path)
    except Exception:
        return ""


def install_pack(source: Any, *, accept_warnings: bool = False) -> dict:
    """Scan, then let `jarvis_skills.install()` raise the ONE card, then write.

    Nothing lands before that card is answered: `install()` vets, refuses a
    blocked skill without asking, and copies in only after a person's yes.
    This function adds the scan report to the card's own words (`note=`), turns
    the pack OFF afterwards with the existing `skills-off` move, and records
    every file in the ledger with a receipt. A refusal comes back as a plain
    answer and writes nothing.
    """
    sk = _sk()
    menu = _menu()
    if sk is None or menu is None:
        return {"ok": False, "installed": False, "asked": False,
                "reason": "the skill library or its menu is not beside this "
                          "file, so nothing can be installed"}
    report = scan_source(source)
    if report.get("verdict") in ("refuse", "malformed"):
        return {"ok": False, "installed": False, "asked": False,
                "refused": True, "report": report,
                "reason": str(report.get("refusal") or "the scan refused it"),
                "sentences": report.get("sentences") or sentences(report)}
    name = str((report.get("pack") or {}).get("name") or "")
    src = report.get("source") or {}
    ref = Path(str(src.get("ref") or ""))
    cleanup: Optional[Path] = None
    try:
        folder = ref
        if str(src.get("type")) == "zip":
            incoming = menu.incoming_root()
            if incoming is None:
                return {"ok": False, "installed": False, "asked": False,
                        "reason": "a folder to unpack the .zip into could not be "
                                  "worked out, so nothing was installed"}
            cleanup = Path(incoming) / f"pack-{int(time.time() * 1000)}-{os.getpid()}"
            try:
                cleanup.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return {"ok": False, "installed": False, "asked": False,
                        "reason": f"a folder to unpack the .zip into could not be "
                                  f"made ({exc}), so nothing was installed"}
            folder, why = _extract_zip(ref, cleanup)
            if folder is None:
                return {"ok": False, "installed": False, "asked": False,
                        "reason": why, "refused": True, "report": report}
        card = card_text(report)
        out = sk.install(folder, trust="third_party",
                         accept_warnings=bool(accept_warnings), note=card)
        out["report"] = report
        out["card"] = card
        if not out.get("ok"):
            out["installed"] = False
            out["sentences"] = report.get("sentences") or sentences(report)
            return out
        dest = Path(str((_skills_root() or Path(".")) / name))
        rows = file_rows(dest)
        entry = {
            "kind": "skill",
            "name": name,
            "version": str((report.get("pack") or {}).get("version") or ""),
            "source": {"type": str(src.get("type") or "folder"),
                       "ref": str(src.get("ref") or ""),
                       "pin": dict(src.get("pin") or {})},
            "pack_sha256": str((report.get("digest") or {}).get("pack_sha256") or ""),
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "state": "installed",
            "folder": str((_off_root() or Path(".")) / name),
            "files": rows,
            "installed_files": rows,
        }
        # NOTHING IS ENABLED IMPLICITLY. The existing off move is used: the
        # folder goes to `skills-off`, the index row goes, and the model is not
        # offered it - the same state as a skill the owner switched off.
        state_line = ""
        try:
            code, payload = menu.set_state({"name": name, "on": False})
            if code == 200 and (payload or {}).get("ok"):
                entry["state"] = "disabled"
            else:
                state_line = (f" It could not be turned off automatically ("
                              f"{(payload or {}).get('reason') or 'unknown reason'}), "
                              f"so it is ON until you switch it off.")
        except Exception as exc:
            state_line = (f" It could not be turned off automatically "
                          f"({type(exc).__name__}), so it is ON until you switch "
                          f"it off.")
        receipt = _write_receipt(report, entry, card)
        entry["receipt"] = receipt
        if not _save_entry(entry):
            state_line += (" The pack ledger could not be written, so I cannot "
                           "promise a complete removal of this one.")
        return {
            "ok": True, "installed": True, "asked": True, "name": name,
            "state": entry["state"], "files": len(rows),
            "pack_sha256": entry["pack_sha256"], "receipt": receipt,
            "ledger": str(ledger_path()), "report": report,
            "sentences": report.get("sentences") or sentences(report),
            "restart": _restart_line("skill"),
            "message": (
                f"Installed {name!r} ({len(rows)} file(s), digest "
                f"{entry['pack_sha256'][:12]}...) and turned it OFF at once, so "
                f"the model is not offered it. It is in "
                f"{(_off_root() or Path('skills-off'))}. Say \"turn the {name} "
                f"skill on\" when you want it, which is its own card."
                + state_line + " " + _restart_line("skill")),
        }
    finally:
        if cleanup is not None:
            try:
                shutil.rmtree(cleanup)
            except OSError:
                pass


# --------------------------------------------------------------------------
#   Removing: exactly the ledger's files, and nothing else
# --------------------------------------------------------------------------

def _folder_of(name: str) -> Optional[Path]:
    """Where a pack's folder is now - installed, or turned off."""
    for base in (_skills_root(), _off_root()):
        if base is None:
            continue
        folder = Path(base) / name
        if folder.is_dir():
            return folder
    return None


def plan_remove(name: str) -> dict:
    """What a removal CAN delete, and what it must keep. Read-only."""
    clean = _clean_name(name)
    if not clean:
        return {"ok": False, "name": str(name or ""),
                "reason": "that is not a pack name"}
    entry = _entry(clean)
    if not entry:
        return {"ok": False, "name": clean,
                "reason": (f"the pack ledger has no record of {clean!r}, so I "
                           f"cannot know which files it wrote and I will not "
                           f"guess. Nothing was deleted.")}
    if str(entry.get("state")) == "removed":
        return {"ok": False, "name": clean, "removed": True,
                "reason": f"{clean!r} was already removed."}
    folder = _folder_of(clean)
    if folder is None:
        return {"ok": False, "name": clean,
                "reason": (f"the ledger records {clean!r} but its folder is not "
                           f"on this PC any more, so there is nothing to delete.")}
    own = [str(r.get("path")) for r in (entry.get("files") or [])]
    here = set(_walk_files(folder))
    delete, keep, changed = [], [], []
    for row in entry.get("files") or []:
        rel = str(row.get("path") or "")
        if rel not in here:
            continue
        full = folder / rel
        try:
            digest = _sha256_file(full)
        except OSError:
            keep.append(rel)
            continue
        if digest == str(row.get("sha256") or ""):
            delete.append(rel)
        else:
            changed.append(rel)
    keep += sorted(here - set(own))
    return {"ok": True, "name": clean, "folder": str(folder),
            "kind": str(entry.get("kind") or "skill"),
            "delete": delete, "keep": sorted(set(keep)),
            "changed": changed, "source": entry.get("source") or {},
            "pack_sha256": entry.get("pack_sha256") or "",
            "files": len(entry.get("files") or []),
            "restart": _restart_line(str(entry.get("kind") or "skill"))}


def remove_card_text(plan: dict) -> str:
    """The ONE removal card's own words: exactly what it would delete."""
    name = str(plan.get("name") or "")
    delete = plan.get("delete") or []
    keep = plan.get("keep") or []
    changed = plan.get("changed") or []
    src = plan.get("source") or {}
    shown = "\n".join(f"  - {p}" for p in delete[:40])
    more = (f"\n  ... and {len(delete) - 40} more" if len(delete) > 40 else "")
    kept = ("\nIt will KEEP these, because the pack did not write them:\n"
            + "\n".join(f"  - {p}" for p in keep[:20])) if keep else ""
    moved = ("\nThese changed since install, so I will not delete them:\n"
             + "\n".join(f"  - {p}" for p in changed[:20])) if changed else ""
    return (
        f"Remove the pack {name!r}?\n\n"
        f"From:      {src.get('ref') or 'a folder on this PC'}\n"
        f"SHA-256:   {str(plan.get('pack_sha256') or '')[:16]}...\n\n"
        f"If you say yes, I delete exactly these {len(delete)} file(s), the ones "
        f"the ledger recorded when it was installed:\n"
        + (shown or "  (none - they are already gone)") + more
        + "\n\n"
        f"Its row in the pack ledger is marked removed, and its entry in the "
        f"skill list goes, so the model stops being offered it."
        + kept + moved + "\n\n"
        + (str(plan.get("restart") or "")) + "\n\n"
        f"If you say no, nothing changes at all."
    )


def remove_pack(name: str) -> dict:
    """Delete exactly the ledger's files, keep everything else, mark removed."""
    plan = plan_remove(name)
    if not plan.get("ok"):
        return {"ok": False, "removed": False, "reason": plan.get("reason"),
                "plan": plan}
    clean = str(plan["name"])
    folder = Path(str(plan["folder"]))
    deleted, skipped = [], []
    for rel in plan.get("delete") or []:
        full = folder / rel
        if not _inside(folder, full):
            skipped.append(rel)
            continue
        try:
            full.unlink()
            deleted.append(rel)
        except OSError:
            skipped.append(rel)
    # Only directories this pack's own files left empty. A folder with any file
    # left in it - the owner's, or one that changed - is never removed.
    try:
        for child in sorted(folder.rglob("*"), key=lambda p: len(p.parts),
                            reverse=True):
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
        try:
            folder.rmdir()
        except OSError:
            pass
    except OSError:
        pass
    if folder.exists() and _off_root() is None:
        pass
    # Out of the load path even if something is left in it: a folder with the
    # owner's own files beside it is moved to skills-off, never deleted.
    left_in_place = ""
    root, off = _skills_root(), _off_root()
    if folder.exists() and root is not None and off is not None:
        try:
            still = folder == Path(root) / clean
        except Exception:
            still = False
        if still:
            try:
                off.mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder), str(off / clean))
                left_in_place = (f" The files it did not write stay in "
                                 f"{off / clean}.")
            except OSError:
                left_in_place = (f" Its folder, with the files it did not write, "
                                 f"stays at {folder}.")
    # The index row is what the model is offered from; take it out.
    sk = _sk()
    if sk is not None:
        try:
            ix = dict(sk._read_index() or {})
            if ix.pop(clean, None) is not None:
                sk._write_index(ix)
        except Exception:
            pass
        try:
            import jarvis_content_risk as _cr
            _cr.unpin("skill", clean)
        except Exception:
            pass
    entry = _entry(clean)
    entry.update(state="removed",
                 removed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 deleted=deleted, kept=list(plan.get("keep") or []),
                 changed=list(plan.get("changed") or []))
    wrote = _save_entry(entry)
    return {
        "ok": True, "removed": True, "name": clean,
        "deleted": deleted, "kept": plan.get("keep") or [],
        "changed": plan.get("changed") or [],
        "ledger": str(ledger_path()), "ledger_written": bool(wrote),
        "restart": plan.get("restart") or _restart_line("skill"),
        "message": (
            f"Removed {clean!r}: {len(deleted)} file(s) deleted"
            + (f", {len(plan.get('keep') or [])} kept because the pack did not "
               f"write them" if plan.get("keep") else "")
            + (f", {len(plan.get('changed') or [])} left because they changed "
               f"since install" if plan.get("changed") else "")
            + "." + left_in_place + " "
            + ("" if wrote else "The pack ledger could not be rewritten. ")
            + str(plan.get("restart") or _restart_line("skill"))),
    }


# --------------------------------------------------------------------------
#   Listing: what is installed, where it came from, and what it is doing
# --------------------------------------------------------------------------

def list_packs() -> dict:
    """Every pack the ledger knows, plus what is on disk without a record.

    Read-only. The three states are kept apart because they are three
    different problems for the owner: installed, turned off, and removed.
    Nothing here imports a pack or reads its body.
    """
    ledger = read_ledger()
    rows, seen = [], set()
    for name, entry in sorted((ledger.get("packs") or {}).items()):
        if not isinstance(entry, dict):
            continue
        seen.add(name)
        folder = _folder_of(name)
        state = str(entry.get("state") or "installed")
        if state == "removed":
            rows.append({"name": name, "kind": entry.get("kind") or "skill",
                         "version": entry.get("version") or "",
                         "state": "removed", "on_disk": False,
                         "source": entry.get("source") or {},
                         "pack_sha256": entry.get("pack_sha256") or "",
                         "files": len(entry.get("files") or []),
                         "installed_at": entry.get("installed_at") or "",
                         "note": "removed - the ledger keeps the record"})
            continue
        rows.append({
            "name": name, "kind": entry.get("kind") or "skill",
            "version": entry.get("version") or "",
            "state": state if folder is not None else "missing",
            "on_disk": folder is not None,
            "source": entry.get("source") or {},
            "pack_sha256": entry.get("pack_sha256") or "",
            "files": len(entry.get("files") or []),
            "installed_at": entry.get("installed_at") or "",
            "folder": str(folder) if folder else "",
            "note": "" if folder is not None else
                    ("its folder is gone from this PC, so the ledger's record is "
                     "all that is left"),
        })
    # On disk but not in the ledger: installed some other way. Named, never
    # dropped - a list that hides one is the failure this tool removes.
    root, off = _skills_root(), _off_root()
    for base, state in ((root, "installed"), (off, "disabled")):
        if base is None or not Path(base).is_dir():
            continue
        try:
            for child in sorted(Path(base).iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if not (child / "SKILL.md").is_file() or child.name in seen:
                    continue
                seen.add(child.name)
                rows.append({"name": child.name, "kind": "skill", "version": "",
                             "state": state, "on_disk": True,
                             "source": {"type": "unknown", "ref": ""},
                             "pack_sha256": "", "files": 0, "installed_at": "",
                             "folder": str(child),
                             "note": ("not installed by the pack manager, so I do "
                                      "not know where it came from")})
        except OSError:
            pass
    loader = _plugins()
    if loader is not None:
        try:
            for row in loader.available() or []:
                if not isinstance(row, dict) or row.get("name") in seen:
                    continue
                rows.append({
                    "name": str(row.get("name") or ""), "kind": "plugin",
                    "version": "", "state": "off" if row.get("disabled") else "on",
                    "on_disk": bool(row.get("ok")),
                    "source": {"type": "plugins-folder",
                               "ref": str(loader.plugins_dir())},
                    "module": str(row.get("module") or ""),
                    "pack_sha256": "", "files": 0,
                    "installed_at": "",
                    "note": ("a plug-in is code loaded at start-up; phase 1 does "
                             "not install or remove one"),
                })
        except Exception:
            pass
    counts = {}
    for row in rows:
        counts[str(row.get("state"))] = counts.get(str(row.get("state")), 0) + 1
    return {
        "ok": True,
        "ledger": str(ledger_path()),
        "ledger_note": str(ledger.get("note") or ""),
        "packs": rows, "counts": counts,
        "note": (f"Nothing needs restarting for a skill. "
                 f"{_restart_line('skill')}"),
    }


def _self_check() -> dict:
    """What this module can see right now. Read-only."""
    return {"module": "jarvis_packs", "version": 1,
            "ledger": str(ledger_path()), "receipts": str(receipts_dir()),
            "skills_dir": str(_skills_root()), "off_dir": str(_off_root()),
            "packs": len((read_ledger().get("packs") or {})),
            "jarvis_skills": _sk() is not None,
            "jarvis_skill_menu": _menu() is not None,
            "python": "%d.%d" % _python_version()}


if __name__ == "__main__":                              # pragma: no cover
    print(json.dumps(_self_check(), indent=2))
