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

  * No code packs. A folder or archive holding a `.py`, `.ps1`, `.exe`, `.dll`,
    `.wasm`, any other executable/script suffix or any binary is REFUSED before
    the card, in one sentence naming the file. Code that runs inside Jarvis
    needs more than a scan; that is phase 2.
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

import difflib
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
    # `.wasm` is a program: it is compiled bytecode that a host runs as code,
    # so it belongs on the same hard-refusal list as `.py` and `.exe` even
    # though this project does not run one. The owner's Q2 ruling names it
    # explicitly (2026-11-05).
    ".wasm",
})

#: The ledger's own name, and the receipt folder's, both beside the config.
LEDGER_NAME = "jarvis-packs.json"
RECEIPTS_NAME = "jarvis-packs-receipts"

#: Set this to keep the ledger and receipts somewhere else. It exists for the
#: suites (a temp folder), the same way JARVIS_SKILLS_DIR exists for skills.
DIR_ENV = "JARVIS_PACKS_DIR"

#: What the ledger holds, and what a reader may rely on.
SCHEMA = 1

#: One of the three states a pack is really in, beside installed / disabled /
#: removed / missing. `tampered` means a file on disk no longer matches the
#: SHA-256 manifest pinned at install, so the pack is refused on load until the
#: owner installs it again (Q3, 2026-11-05: packs are immutable once installed).
TAMPERED = "tampered"

#: How much of a replacement's unified diff the card and the receipt carry.
#: A card is read in seconds; the cut is said out loud rather than hidden.
MAX_DIFF_LINES = 200

#: How many bytes of one file a replacement diff reads. A prompt-only skill is
#: text and small; a file past this is named but not diffed.
MAX_DIFF_BYTES = 512 * 1024

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


def _is_link(path: Path) -> bool:
    """A symlink, or a Windows junction. Both are shortcuts out of the folder."""
    try:
        if Path(path).is_symlink():
            return True
    except OSError:
        return True
    try:
        isjunction = getattr(os.path, "isjunction", None)
        if isjunction is not None and isjunction(str(path)):
            return True
    except Exception:
        pass
    return False


def links_in(folder: Path) -> str:
    """The first link or escaping path under `folder`, as a relative name.

    Empty means every entry is a plain file or folder that really lives inside
    the pack. `os.walk(followlinks=False)` is deliberate: a directory link must
    be SEEN and refused, not followed and read - so this is checked before any
    file is hashed, and again right before the copy.
    """
    root = Path(folder)
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            here = Path(dirpath)
            for name in list(dirnames) + list(filenames):
                full = here / name
                try:
                    rel = full.relative_to(root).as_posix()
                except ValueError:
                    return str(full)
                if _is_link(full):
                    return rel
                if name in filenames:
                    try:
                        if not _inside(root, full):
                            return rel
                    except OSError:
                        return rel
    except OSError:
        return "."
    return ""


def _text_of(data: bytes) -> Optional[str]:
    """The text of a byte string, or None when it is not text.

    A prompt-only pack is text; a file with a NUL byte or bytes that are not
    UTF-8 is already refused by the scan, and is never diffed here.
    """
    if b"\0" in data[:65536]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


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
    # A link is a way out of the folder: a symlink or junction can point at any
    # file on this PC, so a pack that holds one is refused before a byte is
    # read. This is the folder half of the same rule `_scan_zip` applies to a
    # `.zip` member (Q2, 2026-11-05: path-traversal symlinks are a hard reject).
    linked = links_in(folder)
    if linked:
        report["observed"]["links"] = [linked]
        return _refused(
            f"that folder holds a link or a file that points outside it "
            f"({linked!r}) - a shortcut to somewhere else on this PC - and a pack "
            f"is only ever plain files inside its own folder, so nothing was "
            f"installed", report=report)
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
    same = attach_replacement(report)
    if same:
        return _refused(same, report=report)
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
    """Will it work here, and will it break anything? Read, never guessed.

    A name that the PACK LEDGER already records is not a collision: it is a
    REPLACEMENT, and `_replacement()` measures the new bytes against the
    installed ones so the new scan and a unified diff go on one NEW card
    (Q3, 2026-11-05). A name that is on disk but NOT in the ledger is still a
    refusal - this module will not overwrite a skill it did not write, because
    it has no manifest to diff against and no record of which files are its own.
    """
    out = {"name": report["pack"].get("name", ""), "collision": "",
           "replace": {}}
    name = str(report["pack"].get("name") or "")
    if not name:
        out["collision"] = "that pack names no skill, so nothing was installed"
        return out
    known = read_ledger().get("packs") or {}
    entry = dict(known.get(name) or {}) if isinstance(known, dict) else {}
    state = str(entry.get("state") or "")
    # Where this name is on disk right now, if anywhere.
    found = None
    for base, where in ((_skills_root(), "the skills folder"),
                        (_off_root(), "the turned-off folder")):
        if base is None:
            continue
        if (Path(base) / name).exists():
            found = (Path(base) / name, where)
            break
    if entry and state != "removed":
        folder = _folder_of(name)
        if folder is None:
            # The record survives, the bytes do not: this is a fresh install of
            # a name the ledger remembers, not a swap over files that are here.
            out["replace"] = {
                "mode": "record-only",
                "from_sha256": str(entry.get("pack_sha256") or ""),
                "from_version": str(entry.get("version") or ""),
                "old_folder": "", "old_state": "missing", "tampered": False,
            }
        else:
            check = verify_pack(name, mark=False)
            out["replace"] = {
                "mode": "swap",
                "from_sha256": str(entry.get("pack_sha256") or ""),
                "from_version": str(entry.get("version") or ""),
                "installed_at": str(entry.get("installed_at") or ""),
                "old_folder": str(folder),
                "old_state": (TAMPERED if check.get("tampered") else
                              (state or "installed")),
                "tampered": bool(check.get("tampered")),
                "changed_files": list(check.get("changed") or []),
            }
    elif found is not None:
        out["collision"] = (
            f"a skill called {name!r} is already in {found[1]}, and the pack "
            f"ledger has no record of installing it, so nothing was installed - "
            f"remove it first, or give this one a different name")
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


def _source_texts(report: dict) -> dict:
    """{path: text} for the scanned source's text files. Reads only, writes none.

    This is the NEW half of a replacement diff. The same files were hashed for
    the report; this reads their text so the owner can see the change, and it
    refuses nothing on its own: the scan already decided what the pack is.
    """
    src = report.get("source") or {}
    rows = (report.get("digest") or {}).get("files") or []
    out: dict = {}
    if str(src.get("type")) == "zip":
        prefix = str(src.get("prefix") or "")
        try:
            with zipfile.ZipFile(Path(str(src.get("ref") or ""))) as archive:
                for row in rows:
                    name = str((row or {}).get("path") or "")
                    if not name or int((row or {}).get("bytes") or 0) > MAX_DIFF_BYTES:
                        continue
                    try:
                        try:
                            data = archive.read(name)
                        except KeyError:
                            data = archive.read(prefix + name)
                        text = _text_of(data)
                    except Exception:
                        continue
                    if text is not None:
                        out[name] = text
        except (OSError, zipfile.BadZipFile):
            return {}
        return out
    folder = Path(str(src.get("ref") or ""))
    for row in rows:
        name = str((row or {}).get("path") or "")
        full = folder / name
        if not name or not _inside(folder, full):
            continue
        try:
            if full.stat().st_size > MAX_DIFF_BYTES:
                continue
            text = _text_of(full.read_bytes())
        except OSError:
            continue
        if text is not None:
            out[name] = text
    return out


def _diff_against(old_folder: Path, old_rows: list, new_texts: dict) -> dict:
    """A unified diff of the INSTALLED files against the new pack's text.

    The old side is what is on disk now (so a pack that was changed by hand is
    diffed as it really is, and the card says the ledger no longer matches it);
    the new side is the source that was just scanned. Binary files cannot occur
    in a pack the scan passed, but a file too large to diff is named rather than
    silently skipped.
    """
    old_paths = {}
    for row in old_rows or []:
        if isinstance(row, dict) and row.get("path"):
            old_paths[str(row["path"])] = row
    added, removed, changed, same = [], [], [], []
    lines: list = []
    for path in sorted(set(old_paths) | set(new_texts)):
        old = old_paths.get(path)
        new_text = new_texts.get(path)
        if old is None:
            added.append(path)
            if new_text is not None:
                lines.extend(difflib.unified_diff(
                    [], new_text.splitlines(),
                    fromfile=f"not installed/{path}", tofile=f"new/{path}",
                    lineterm=""))
            continue
        if new_text is None:
            removed.append(path)
            lines.append(f"--- removed: {path}")
            continue
        try:
            old_text = (Path(old_folder) / path).read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            old_text = ""
        if old_text == new_text:
            same.append(path)
            continue
        changed.append(path)
        lines.extend(difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(),
            fromfile=f"installed/{path}", tofile=f"new/{path}", lineterm=""))
    cut = len(lines) > MAX_DIFF_LINES
    body = "\n".join(lines[:MAX_DIFF_LINES])
    files = {"added": added, "removed": removed, "changed": changed,
             "same": same}
    bits = []
    if added:
        bits.append(f"{len(added)} added")
    if removed:
        bits.append(f"{len(removed)} removed")
    if changed:
        bits.append(f"{len(changed)} changed")
    return {"diff": body,
            "diff_sha256": sha256_bytes("\n".join(lines).encode("utf-8")),
            "diff_lines": len(lines), "diff_cut": cut, "files": files,
            "summary": ("Replaces the installed copy: "
                        + (", ".join(bits) if bits else "no file changed") + ".")}


def attach_replacement(report: dict) -> str:
    """Measure a replacement and put it on the report. Empty means it may go on.

    A non-empty answer is a plain refusal (the same bytes are already installed,
    so there is nothing to replace). Nothing here writes or swaps anything: the
    diff is what the card shows, and the swap happens only inside
    `install_pack()` after `jarvis_skills.install()`'s card is answered.
    """
    compat = report.get("compatibility") or {}
    rep = dict(compat.get("replace") or {})
    report["replacement"] = {}
    if not rep:
        return ""
    name = str((report.get("pack") or {}).get("name") or "")
    new_sha = str((report.get("digest") or {}).get("pack_sha256") or "")
    to_version = str((report.get("pack") or {}).get("version") or "")
    if rep.get("mode") == "record-only":
        report["replacement"] = {
            **rep, "same": False, "to_sha256": new_sha, "to_version": to_version,
            "diff": "", "diff_sha256": "", "diff_lines": 0, "diff_cut": False,
            "files": {"added": [], "removed": [], "changed": [], "same": []},
            "summary": ("The copy the ledger recorded is no longer on this PC, so "
                        "this is a fresh install of a name it remembers, not a "
                        "swap over files that are here."),
        }
        return ""
    from_sha = str(rep.get("from_sha256") or "")
    if from_sha and from_sha == new_sha:
        return (f"those are the same bytes that are already installed "
                f"(SHA-256 {new_sha[:12]}...), so there is nothing to replace and "
                f"nothing was changed")
    entry = _entry(name)
    measured = _diff_against(Path(str(rep.get("old_folder") or "")),
                             entry.get("files") or [], _source_texts(report))
    report["replacement"] = {**rep, **measured, "same": False,
                             "to_sha256": new_sha, "to_version": to_version}
    return ""


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
                if "\0" in name or ":" in name:
                    # A colon is an alternate data stream on Windows: a second,
                    # invisible body attached to a file whose plain text was
                    # scanned. A pack is plain files with plain names.
                    return _refused(
                        f"the .zip holds a file with a name that is not a plain "
                        f"name ({name!r}), so nothing was installed", report=report)
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
    for name in binaries:
        report["findings"].append(_finding(
            "block", "binary_file",
            "a file that is not text, so what it holds cannot be read", name))
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
    # A .zip usually wraps the skill in one folder (`my-skill/SKILL.md`). What
    # gets INSTALLED is that folder, so the manifest is the files under it,
    # named relative to it - the same names `file_rows(dest)` will produce.
    # Everything else in the archive was scanned (a `.py` anywhere still
    # refused the archive above) but is NOT installed, and is named rather than
    # silently dropped.
    prefix = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
    report["source"]["prefix"] = prefix
    if prefix:
        inside = [r for r in rows if str(r.get("path") or "").startswith(prefix)]
        outside = [str(r.get("path") or "") for r in rows
                   if not str(r.get("path") or "").startswith(prefix)]
        for row in rows:
            if str(row.get("path") or "").startswith(prefix):
                row["path"] = str(row["path"])[len(prefix):]
        del rows[:]
        rows.extend(inside)
        report["ignored"] = outside
        report["digest"]["pack_sha256"] = pack_digest(rows)
        report["pack"]["files"] = len(rows)
        report["pack"]["bytes"] = sum(int(r.get("bytes") or 0) for r in rows)
    report["compatibility"] = _compatibility(report, manifest)
    if report["compatibility"].get("collision"):
        return _refused(report["compatibility"]["collision"], report=report)
    same = attach_replacement(report)
    if same:
        return _refused(same, report=report)
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
    rep = report.get("replacement") or {}
    if rep:
        changes = ("This REPLACES the copy already installed. " + str(rep.get("summary") or "")
                   + " " + str(changes))
    safe = (f"Instructions only - no file in it can run"
            f" ({files} file(s), none executable). The digest is {digest[:12]}..., "
            f"and every file's own fingerprint is in the receipt. It is "
            f"NOT VERIFIED: no signing key exists, so a checksum proves the "
            f"bytes did not change, never who wrote them.")
    compat = report.get("compatibility") or {}
    py = compat.get("python") or {}
    if rep:
        works = (f"It will work here: Python {py.get('running') or 'is present'}"
                 + (f" meets the {py.get('declared')} it asks for"
                    if py.get("declared") else "")
                 + f". It is written to {compat.get('writes_to') or 'the skills folder'}, "
                   f"then turned OFF, exactly as a first install is. "
                   f"{report.get('restart') or ''}").strip()
    else:
        works = (f"It will work here: Python {py.get('running') or 'is present'}"
                 + (f" meets the {py.get('declared')} it asks for"
                    if py.get("declared") else "")
                 + f", and no skill with that name exists on this PC yet. "
                   f"It is written to {compat.get('writes_to') or 'the skills folder'}, "
                   f"then turned OFF. {report.get('restart') or ''}").strip()
    return {"what": what, "changes": changes, "safe": safe, "works": works}


def _finding_lines(report: dict) -> list:
    """The scan's own findings, as card lines. An empty list is said out loud."""
    findings = [f for f in (report.get("findings") or []) if isinstance(f, dict)]
    if not findings:
        return ["  None. No prompt-injection pattern, hidden or bidirectional "
                "Unicode, dangerous instruction or bundled script was found."]
    out = []
    for item in findings[:12]:
        where = str(item.get("where") or "")
        out.append(f"  [{str(item.get('severity') or 'note').upper()}] "
                   f"{item.get('message') or item.get('code') or 'finding'}"
                   + (f"  ({where})" if where else ""))
    if len(findings) > 12:
        out.append(f"  ... and {len(findings) - 12} more, all saved in the receipt.")
    return out


def _replacement_lines(report: dict) -> list:
    """The replacement half of the card: what is installed, and the diff."""
    rep = report.get("replacement") or {}
    if not rep:
        return []
    out = [
        "THIS IS A REPLACEMENT, NOT AN UPDATE",
        f"  Installed:  version {rep.get('from_version') or 'not declared'}, "
        f"SHA-256 {str(rep.get('from_sha256') or '')[:16]}..."
        + (f", at {rep.get('old_folder')}" if rep.get("old_folder") else ""),
        f"  This pack:  version {rep.get('to_version') or 'not declared'}, "
        f"SHA-256 {str(rep.get('to_sha256') or '')[:16]}...",
    ]
    if rep.get("tampered"):
        out.append(
            "  NOTE: the installed copy no longer matches its ledger record - "
            + ", ".join((rep.get("changed_files") or [])[:4])
            + (" ..." if len(rep.get("changed_files") or []) > 4 else "")
            + ". Replacing it is how that is repaired.")
    out += [
        "  Nothing is swapped until you say yes. If you say no, the installed "
        "copy stays exactly as it is.",
        "",
        "WHAT CHANGES",
        f"  {rep.get('summary') or 'The new pack differs from the installed one.'}",
        "",
    ]
    diff = str(rep.get("diff") or "")
    if diff:
        for line in diff.splitlines():
            out.append("  " + (line[:240] + " ..." if len(line) > 240 else line))
        if rep.get("diff_cut"):
            out.append(f"  ... the diff was cut at {MAX_DIFF_LINES} lines; the "
                       f"whole report and diff are saved in the receipt.")
    elif rep.get("mode") == "record-only":
        out.append("  The recorded copy is gone from this PC, so there is no "
                   "installed file to diff against.")
    else:
        out.append("  No file changed; only the version label did.")
    out.append("")
    return out


def card_text(report: dict) -> str:
    """The ONE install card's own words, built from the report.

    It names the pack, where it came from, its digest, what it contains, the
    scan's own findings, and - for a replacement - the installed copy and a
    unified diff against it. `jarvis_skills.install()` puts this on the card it
    raises; nothing here can skip that card or approve anything.
    """
    pack = report.get("pack") or {}
    src = report.get("source") or {}
    eff = report.get("effectiveness") or {}
    rep = report.get("replacement") or {}
    said = sentences(report)
    verb = "Replace the installed skill" if rep else "Install the skill"
    lines = [
        f"{verb} {str(pack.get('name') or '')!r}"
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
    ]
    ignored = [str(p) for p in (report.get("ignored") or [])]
    if ignored:
        lines.append(
            f"Ignored:   {len(ignored)} file(s) in the .zip are outside the "
            f"skill's own folder, so they will NOT be installed: "
            + ", ".join(ignored[:4]) + (" ..." if len(ignored) > 4 else ""))
    lines.append("")
    lines += _replacement_lines(report)
    lines += [
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
        "SCAN FINDINGS",
    ]
    lines += _finding_lines(report)
    lines += [
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
    ]
    if rep:
        lines += [
            "If you say yes, the new files replace the installed copy and are then "
            "turned OFF at once - the model is not offered the new version until "
            "you turn it on, which is its own card. The old copy stays in the "
            "receipt and in the ledger's history. If you say no, nothing is "
            "swapped and nothing is written.",
        ]
    else:
        lines += [
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
                if "\0" in name or ":" in name:
                    # Checked again here, not only in the scan: a colon is an
                    # alternate data stream on Windows, and this is the second
                    # read of the archive.
                    return None, (f"the .zip holds a name that is not a plain "
                                  f"name ({name!r})")
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
    folder = found[0]
    # A `.zip` GitHub built gets its folder renamed to the skill's own name
    # first: `my-skill-main/SKILL.md` says `name: my-skill`, and the spec (and
    # `parse_skill`) require the folder to be the name. The same rule the
    # Skills screen's `_find_one_skill` applies, in this throwaway copy; the
    # rename is checked by the same `parse_skill` afterwards.
    sk = _sk()
    if sk is not None:
        try:
            fm, _body = sk._parse_frontmatter(
                (folder / "SKILL.md").read_text(encoding="utf-8",
                                                errors="replace"))
            wanted = _clean_name(fm.get("name"))
        except Exception:
            wanted = ""
        if wanted and wanted != folder.name:
            renamed = folder.parent / wanted
            try:
                if not renamed.exists():
                    shutil.move(str(folder), str(renamed))
                    return renamed, ""
            except OSError:
                pass
    return folder, ""


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


def _restore_folder(backup: Path, folder: Path) -> bool:
    """Put a saved copy back where it was. False is an answer: the caller says so."""
    try:
        if Path(folder).exists():
            shutil.rmtree(folder)
        Path(folder).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup, folder)
        return True
    except OSError:
        return False


def install_pack(source: Any, *, accept_warnings: bool = False) -> dict:
    """Scan, then let `jarvis_skills.install()` raise the ONE card, then write.

    Nothing lands before that card is answered: `install()` vets, refuses a
    blocked skill without asking, and copies in only after a person's yes.
    This function adds the scan report to the card's own words (`note=`), turns
    the pack OFF afterwards with the existing `skills-off` move, and records
    every file in the ledger with a receipt. A refusal comes back as a plain
    answer and writes nothing.

    A pack whose name the ledger already records is a REPLACEMENT, and the
    replacement rules are Q3's (2026-11-05): the new source is scanned from
    scratch, a unified diff against the installed files goes on the SAME one
    NEW card as the report, and the swap happens only inside `install()` after
    that card is answered. The installed copy is saved to the incoming folder
    first and put back if the copy fails, so a failed replacement cannot lose
    the version the owner already had.
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
    replacement = dict(report.get("replacement") or {})
    old_folder: Optional[Path] = None
    old_entry: dict = {}
    if replacement.get("mode") == "swap" and replacement.get("old_folder"):
        old_folder = Path(str(replacement["old_folder"]))
        old_entry = _entry(name)
    cleanup: Optional[Path] = None
    backup: Optional[Path] = None
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
        # The scan checked this too; the copy is a second read, and a link
        # added between them must not land (Q2: path-traversal links are a hard
        # reject, and an unread link is exactly that).
        linked = links_in(folder)
        if linked:
            return {"ok": False, "installed": False, "asked": False,
                    "refused": True, "report": report,
                    "reason": (f"that pack now holds a link or a file that points "
                               f"outside it ({linked!r}), so nothing was installed")}
        if old_folder is not None and old_folder.is_dir():
            incoming = menu.incoming_root()
            if incoming is None:
                return {"ok": False, "installed": False, "asked": False,
                        "reason": ("a safe copy of the installed one could not be "
                                   "made, so nothing was swapped and the installed "
                                   "copy is unchanged")}
            backup = Path(incoming) / (f"pack-old-{int(time.time() * 1000)}-"
                                       f"{os.getpid()}")
            try:
                shutil.copytree(old_folder, backup)
            except OSError as exc:
                return {"ok": False, "installed": False, "asked": False,
                        "reason": (f"a safe copy of the installed one could not be "
                                   f"made ({type(exc).__name__}), so nothing was "
                                   f"swapped and the installed copy is unchanged")}
        card = card_text(report)
        try:
            out = sk.install(folder, trust="third_party",
                             accept_warnings=bool(accept_warnings), note=card)
        except Exception as exc:
            restored = False
            if backup is not None and old_folder is not None:
                restored = _restore_folder(backup, old_folder)
            return {"ok": False, "installed": False, "asked": True,
                    "reason": (f"the install failed ({type(exc).__name__})"
                               + (", and the installed copy was put back unchanged"
                                  if restored else "")),
                    "report": report}
        out["report"] = report
        out["card"] = card
        if not out.get("ok"):
            out["installed"] = False
            if backup is not None and old_folder is not None:
                if _restore_folder(backup, old_folder):
                    out["restored"] = True
                    out["reason"] = (str(out.get("reason") or "refused")
                                     + " The installed copy was left exactly as it "
                                       "was.")
            out["sentences"] = report.get("sentences") or sentences(report)
            return out
        dest = Path(str((_skills_root() or Path(".")) / name))
        rows = file_rows(dest)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        new_sha = str((report.get("digest") or {}).get("pack_sha256") or "")
        history = list(old_entry.get("history") or []) if old_entry else []
        if replacement:
            history.append({
                "action": "replaced",
                "at": now,
                "from_pack_sha256": str(old_entry.get("pack_sha256")
                                        or replacement.get("from_sha256") or ""),
                "to_pack_sha256": new_sha,
                "from_version": str(old_entry.get("version")
                                    or replacement.get("from_version") or ""),
                "to_version": str((report.get("pack") or {}).get("version") or ""),
                "diff_sha256": str(replacement.get("diff_sha256") or ""),
                "diff_lines": int(replacement.get("diff_lines") or 0),
                "tampered_at_replace": bool(replacement.get("tampered")),
                "previous_receipt": str(old_entry.get("receipt") or ""),
            })
        entry = {
            "kind": "skill",
            "name": name,
            "version": str((report.get("pack") or {}).get("version") or ""),
            "source": {"type": str(src.get("type") or "folder"),
                       "ref": str(src.get("ref") or ""),
                       "pin": dict(src.get("pin") or {})},
            "pack_sha256": new_sha,
            "installed_at": now,
            "state": "installed",
            "folder": str((_off_root() or Path(".")) / name),
            "files": rows,
            "installed_files": rows,
            "history": history,
        }
        if old_entry.get("installed_at"):
            entry["first_installed_at"] = str(old_entry["installed_at"])
        if replacement:
            entry["replaced_at"] = now
            entry["replaces"] = (str(old_entry.get("pack_sha256")
                                     or replacement.get("from_sha256") or ""))
            entry["replacement_diff_sha256"] = str(
                replacement.get("diff_sha256") or "")
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
        current = _folder_of(name)
        if current is not None:
            entry["folder"] = str(current)
        receipt = _write_receipt(report, entry, card)
        entry["receipt"] = receipt
        entry["receipt_scan"] = {
            "file": receipt,
            "approved_at": now,
            "card_text_sha256": sha256_bytes(card.encode("utf-8")),
            "verdict": str(report.get("verdict") or ""),
            "warnings": len([f for f in (report.get("findings") or [])
                             if isinstance(f, dict)
                             and str(f.get("severity")) == "warn"]),
            "findings": [dict(f) for f in (report.get("findings") or [])
                         if isinstance(f, dict)],
            "pack_sha256": new_sha,
            "files": rows,
        }
        if not _save_entry(entry):
            state_line += (" The pack ledger could not be written, so I cannot "
                           "promise a complete removal of this one.")
        if replacement:
            said = (f"Replaced {name!r} with the newly scanned pack ({len(rows)} "
                    f"file(s), digest {new_sha[:12]}...) and turned it OFF at once, "
                    f"so the model is not offered the new version. The old copy is "
                    f"kept in the receipt and the ledger's history.")
        else:
            said = (f"Installed {name!r} ({len(rows)} file(s), digest "
                    f"{new_sha[:12]}...) and turned it OFF at once, so the model "
                    f"is not offered it. It is in "
                    f"{(_off_root() or Path('skills-off'))}. Say \"turn the {name} "
                    f"skill on\" when you want it, which is its own card.")
        return {
            "ok": True, "installed": True, "asked": True, "name": name,
            "state": entry["state"], "files": len(rows),
            "pack_sha256": new_sha, "receipt": receipt,
            "ledger": str(ledger_path()), "report": report,
            "replaced": bool(replacement),
            "sentences": report.get("sentences") or sentences(report),
            "restart": _restart_line("skill"),
            "message": said + state_line + " " + _restart_line("skill"),
        }
    finally:
        if backup is not None:
            try:
                shutil.rmtree(backup)
            except OSError:
                pass
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


# --------------------------------------------------------------------------
#   Immutability: the manifest is re-checked on every load (Q3, 2026-11-05)
# --------------------------------------------------------------------------

def _mark_tampered(name: str, entry: dict, missing: list, changed: list) -> None:
    """Record a tampered pack in the ledger. Never deletes and never edits it.

    A pack already marked with the same files is not written again: `list_packs`
    and the hub's reads check on every call, and a read must not rewrite the
    ledger each time it sees the same unchanged tamper.
    """
    state = str(entry.get("state") or "")
    if (state == TAMPERED
            and sorted(entry.get("tampered_missing") or []) == sorted(missing)
            and sorted(entry.get("tampered_changed") or []) == sorted(changed)):
        return
    if state != TAMPERED:
        entry["state_before_tamper"] = state or "installed"
    entry["state"] = TAMPERED
    entry["tampered_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry["tampered_missing"] = sorted(missing)
    entry["tampered_changed"] = sorted(changed)
    _save_entry(entry)


def _folder_state(folder: Path) -> str:
    """`disabled` when the folder is in the turned-off folder, else installed."""
    off = _off_root()
    try:
        if off is not None:
            here = Path(folder).resolve()
            if here == (Path(off) / Path(folder).name).resolve():
                return "disabled"
    except OSError:
        pass
    return "installed"


def verify_pack(name: str, *, mark: bool = True) -> dict:
    """Re-hash EVERY file in the pack's manifest against the disk. Read-only.

    Called before a pack is loaded, listed or read. A file that no longer
    matches the SHA-256 pinned at install - changed, deleted, or replaced - is
    a refusal: the pack is marked `tampered` in `jarvis-packs.json` and says the
    file's name. A file the owner ADDED is not tampering and is not reported
    here; removal already treats it as the owner's own and never deletes it.

    `mark=False` measures without writing, for a card's own text.
    """
    clean = _clean_name(name)
    if not clean:
        return {"ok": False, "known": False, "name": str(name or ""),
                "tampered": False, "reason": "that is not a pack name"}
    entry = _entry(clean)
    if not entry:
        return {"ok": False, "known": False, "name": clean, "tampered": False,
                "reason": f"the pack ledger has no record of {clean!r}"}
    state = str(entry.get("state") or "")
    if state == "removed":
        return {"ok": False, "known": True, "removed": True, "name": clean,
                "tampered": False,
                "reason": f"{clean!r} was removed, so there is nothing to load"}
    folder = _folder_of(clean)
    if folder is None:
        return {"ok": False, "known": True, "missing": True, "name": clean,
                "tampered": False,
                "reason": (f"the ledger records {clean!r} but its folder is not on "
                           f"this PC any more")}
    rows = entry.get("files") or []
    if not isinstance(rows, list) or not rows:
        return {"ok": False, "known": True, "name": clean, "tampered": True,
                "missing": [], "changed": [],
                "reason": (f"the ledger records no file list for {clean!r}, so its "
                           f"bytes cannot be checked and it is not loaded")}
    missing, changed = [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("path") or "")
        try:
            full = Path(folder) / rel
        except (TypeError, ValueError):
            missing.append(rel or "?")
            continue
        if not rel or not _inside(folder, full):
            missing.append(rel or "?")
            continue
        if not full.is_file():
            missing.append(rel)
            continue
        try:
            if _sha256_file(full) != str(row.get("sha256") or ""):
                changed.append(rel)
        except OSError:
            missing.append(rel)
    if missing or changed:
        if mark:
            _mark_tampered(clean, entry, missing, changed)
        named = ", ".join([*changed, *missing][:4])
        more = len(missing) + len(changed) - len([*changed, *missing][:4])
        return {"ok": False, "known": True, "name": clean, "tampered": True,
                "missing": sorted(missing), "changed": sorted(changed),
                "reason": (f"{clean!r} has changed on disk since it was installed: "
                           f"{named}" + (f" and {more} more" if more else "")
                           + ". Its SHA-256 no longer matches the one recorded at "
                             "install, so it will not be loaded.")}
    if state == TAMPERED:
        # The bytes match the manifest again: the change was undone by hand, so
        # the record says so instead of leaving a stale warning on a good pack.
        restored = "disabled" if _folder_state(folder) == "disabled" else "installed"
        entry["state"] = restored
        entry.pop("tampered_at", None)
        entry.pop("tampered_missing", None)
        entry.pop("tampered_changed", None)
        entry.pop("state_before_tamper", None)
        _save_entry(entry)
    return {"ok": True, "known": True, "name": clean, "tampered": False,
            "files": len(rows), "pack_sha256": str(entry.get("pack_sha256") or ""),
            "folder": str(folder), "state": _folder_state(folder)}


def verify_all() -> dict:
    """Every pack the ledger still lists, re-checked. A missing file is a defect."""
    ledger = read_ledger()
    rows = []
    for name, entry in sorted((ledger.get("packs") or {}).items()):
        if not isinstance(entry, dict) or str(entry.get("state")) == "removed":
            continue
        rows.append(verify_pack(str(name)))
    bad = [str(r.get("name") or "") for r in rows if r.get("tampered")]
    return {"ok": not bad, "checked": len(rows), "tampered": bad, "packs": rows,
            "note": ("Every file the ledger recorded is re-hashed against the disk. "
                     "A pack that no longer matches is refused and marked tampered.")}


def load_pack(name: str) -> dict:
    """Load ONE pack's text, after re-checking its whole manifest.

    This is the pack manager's load door, and the rule is Q3's: an installed
    pack is immutable, so every load re-hashes the manifest first. A pack that
    fails is NOT returned, and the ledger marks it `tampered` so `pack_list` and
    the next scan both say so.
    """
    check = verify_pack(name)
    if not check.get("ok"):
        return {"ok": False, "loaded": False, "name": str(name or ""),
                "tampered": bool(check.get("tampered")),
                "reason": str(check.get("reason") or "it could not be checked")}
    folder = _folder_of(str(check["name"]))
    if folder is None:
        return {"ok": False, "loaded": False, "name": str(check["name"]),
                "reason": "its folder is gone"}
    try:
        text = (Path(folder) / "SKILL.md").read_text(encoding="utf-8",
                                                     errors="replace")
    except OSError as exc:
        return {"ok": False, "loaded": False, "name": str(check["name"]),
                "reason": f"its SKILL.md could not be read ({type(exc).__name__})"}
    return {"ok": True, "loaded": True, "name": str(check["name"]),
            "body": text, "folder": str(folder),
            "pack_sha256": str(check.get("pack_sha256") or ""),
            "files": int(check.get("files") or 0),
            "note": ("Re-checked against the SHA-256 manifest before it was read: "
                     "every file still matches what you approved.")}


def repin_after_enable(name: str) -> dict:
    """Re-pin the manifest after the existing ON card approved the folder again.

    Turning a packed skill on runs `jarvis_skills.install()` on the turned-off
    copy: the scanner and its ONE card run again, and the files are copied back
    with whatever the owner approved. That is not tampering - a person said yes -
    so the manifest is re-taken here, with the old digest kept in the history.
    """
    clean = _clean_name(name)
    if not clean:
        return {"ok": False, "reason": "that is not a pack name"}
    entry = _entry(clean)
    if not entry:
        return {"ok": False, "reason": f"the ledger has no record of {clean!r}"}
    folder = _folder_of(clean)
    if folder is None:
        return {"ok": False, "reason": f"{clean!r} has no folder on this PC"}
    rows = file_rows(folder)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    history = list(entry.get("history") or [])
    history.append({"action": "enabled", "at": now,
                    "from_pack_sha256": str(entry.get("pack_sha256") or ""),
                    "to_pack_sha256": pack_digest(rows)})
    entry.update(files=rows, installed_files=rows, folder=str(folder),
                 state=_folder_state(folder), repinned_at=now,
                 pack_sha256=pack_digest(rows), history=history)
    for key in ("tampered_at", "tampered_missing", "tampered_changed",
                "state_before_tamper"):
        entry.pop(key, None)
    wrote = _save_entry(entry)
    return {"ok": bool(wrote), "name": clean, "folder": str(folder),
            "files": len(rows), "pack_sha256": entry["pack_sha256"],
            "ledger_written": bool(wrote)}


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

    Read-only for the files. Each pack's whole manifest is re-hashed against the
    disk as it is listed (Q3: an installed pack is immutable), so a pack whose
    bytes changed behind Jarvis's back is shown as `tampered` and is marked so
    in the ledger. The states are kept apart because they are different problems
    for the owner: installed, turned off, tampered, removed, missing.

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
                         "tampered": False, "tampered_files": [],
                         "note": "removed - the ledger keeps the record"})
            continue
        check = verify_pack(name) if folder is not None else {}
        tampered = bool(check.get("tampered"))
        if tampered:
            state = TAMPERED
        if folder is None:
            state = "missing"
        rows.append({
            "name": name, "kind": entry.get("kind") or "skill",
            "version": entry.get("version") or "",
            "state": state,
            "on_disk": folder is not None,
            "source": entry.get("source") or {},
            "pack_sha256": entry.get("pack_sha256") or "",
            "files": len(entry.get("files") or []),
            "installed_at": entry.get("installed_at") or "",
            "folder": str(folder) if folder else "",
            "tampered": tampered,
            "tampered_files": sorted([*(check.get("changed") or []),
                                      *(check.get("missing") or [])]),
            "note": (str(check.get("reason") or "") if tampered else
                     ("" if folder is not None else
                      ("its folder is gone from this PC, so the ledger's record is "
                       "all that is left"))),
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
    packs = read_ledger().get("packs") or {}
    return {"module": "jarvis_packs", "version": 2,
            "ledger": str(ledger_path()), "receipts": str(receipts_dir()),
            "skills_dir": str(_skills_root()), "off_dir": str(_off_root()),
            "packs": len(packs),
            "tampered": sorted(str(n) for n, e in packs.items()
                               if isinstance(e, dict)
                               and str(e.get("state")) == TAMPERED),
            "jarvis_skills": _sk() is not None,
            "jarvis_skill_menu": _menu() is not None,
            "python": "%d.%d" % _python_version()}


if __name__ == "__main__":                              # pragma: no cover
    print(json.dumps(_self_check(), indent=2))
