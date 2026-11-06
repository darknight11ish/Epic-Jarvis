#!/usr/bin/env python3
"""jarvis_skill_menu.py - the skills menu's PC doors: install from a folder or
a .zip, import from Hermes, turn a skill off and back on, and edit one.

READ jarvis_skills.py FIRST. THIS IS NOT A SECOND COPY OF IT, AND IT DOES NOT
EDIT IT.

jarvis_skills.py owns the skill itself: the frontmatter parser (`parse_skill`
:187), the scanner (`scan_text` :375, `vet` :455), the quarantine
(`_quarantine` :621), the ~100-token card (`cards` :684), the full body
(`load` :705), installing (`install` :556), removing (`uninstall` :634) and
writing one (`write_skill` :775). Every install, every turn-on and every edit
here goes THROUGH `install()` - the scanner runs before the card, a "refuse"
verdict never reaches the approval queue, and the copy, the index row and the
content-risk pin are the ones that already existed. This module re-implements
none of them.

WHY IT EXISTS (the owner, 2026-11-02: "is jarvis fully compatible with hermes
skills? if so, can we make a plug in menu where i can add or remove or change
plug ins for hermes?" - scope B of the research document, which is the option
they chose)

Before this, a skill got in only by chat (`/learn`, `write_skill`) or by hand
in `~/.openjarvis/skills`. There was deliberately **no install route and no
screen**: `jarvis-client`'s `Skills.kt` said so in as many words ("there is
deliberately no route that installs a skill, because installing runs the
scanner and the approval gate on the PC"). This is that route - on the PC, in
Settings, where the scanner and the gate already live.

WHAT EACH DOOR DOES, AND WHAT IT CANNOT DO

  * **Install from a folder or a .zip.** `parse_skill` + `vet` run first (over
    the .zip's contents too, which are unpacked into a throwaway folder with
    the same file-count and size caps), and then `install()` raises ONE
    `modify_own_code` card. A skill the scanner REFUSES is quarantined and
    never becomes a card - a dialog asking "install this?" for a
    curl-pipe-bash skill is the exploit's last step, not a safeguard. A skill
    the scanner merely WARNS about needs `accept_warnings` from a person who
    has read the warnings, and only then does its card appear.
  * **Import my Hermes skills.** A READ-ONLY scan of `%USERPROFILE%\\.hermes\\
    skills` (Hermes's own folder; categories collapse to leaf names, as they
    must, because the spec says the folder is the name). Each folder is then
    installed through the same scanner and its own ONE card - never a card
    that approves several skills at once, because this project does not build
    bulk approval. Nothing is copied, moved or deleted by the scan.
  * **Turn a skill off, and back on.** Off MOVES the folder to
    `<config>\\skills-off\\<name>` and takes its row out of the index, which is
    the list `cards()` hands the model - so it is not offered, and `load()`
    cannot find it either. Nothing is deleted: turning it back on runs the same
    scanner and the same ONE card as installing it, then deletes only the
    moved copy. Turning OFF is immediate, like every other switch that takes
    something away; turning ON is a card, like every other switch that adds
    instructions the agent will follow.
  * **Edit.** The edited SKILL.md is written into a copy of the skill folder
    and goes through `install()` - the same scanner and the same ONE card. A
    block finding is refused before any card, and the quarantine keeps the
    attempt. Fixed fields: the `name:` in the frontmatter still has to match
    the folder name, so an edit cannot rename a skill; that would be a new
    install plus a removal.
  * **Remove of an INSTALLED skill is not here.** It already exists
    (`POST /api/skills/decide` with `{"remove": true}` ->
    `jarvis_skills.uninstall`), with its "are you sure?" in both apps, and the
    menu calls that same route. The one thing that route cannot reach is a
    skill THIS menu parked in `skills-off\\`: `uninstall()` resolves a name
    only under the skills folder (`_safe_dest`), so a skill the owner switched
    off could be switched back on and never got rid of at all. `POST
    /api/skills/state` with `{"remove": true}` deletes that parked copy - the
    menu's own bookkeeping, ONE name per request, no card (it is already out of
    the load path), and it refuses an installed name outright so there are
    never two doors to the same folder.

WHAT A HERMES SKILL REALLY GETS, SAID ON THE CARD AND ON THE ROW

Hermes and Jarvis both follow the agentskills.io format, so a Hermes skill
folder usually installs as it is. What does NOT come across is Hermes's
extra semantics (`platforms`, `metadata.hermes.*` conditional activation,
`required_environment_variables`) - they are kept in `extra_fields` and do
nothing here - and **a skill's `scripts/` folder is never run**. Jarvis skills
are instructions, full stop. Every card and every row for a skill that ships
one says it in the owner's words (Gemini's ruling 6):

    Imported SKILL.md instructions (N file(s) in scripts/ are kept inert and
    never run automatically).

THE SENTENCE IS BUILT HERE AND SHOWN HERE, AND THE CARD SHOWS IT TOO

`install()` grows one additive parameter for this (`note=`, `skill-install-
note.patch`): the line joins the ONE card's prompt. That patch also re-checks
the gate's TIER, because `jarvis_gate.check` returns allowed=True on `notify`
and `auto` - no person asked - and `refine()` already refuses those tiers for
exactly this reason.

WHAT THIS DOES NOT DO

- No marketplace, no network, no download, no auto-install: nothing here opens
  a socket, imports `urllib`/`http.client`/`requests`, or starts a process.
  The only sources are a folder the owner picked on this PC, a `.zip` they
  picked, and `~/.hermes/skills` if it happens to exist.
- It never approves anything, it raises no more than ONE card per request, and
  it has no "yes to all", no batch install and no bulk approval.
- It does not run a skill, a script, or anything inside a skill folder. The
  `.zip` is unpacked with `zipfile` and its members are written as plain
  files: no symlink, no absolute path, no `..`, no drive letter, and the same
  file-count and total-size caps `parse_skill` applies.
- It does not read an email, a document, a note, a web page or tool output.
- It edits no module and no config; the only files it writes or deletes are the
  skill folders, `skills-off/`, the throwaway unpack folder, and the index row
  `jarvis_skills.py` already owns.

Its routes come from its own `install()`, called by the
`plugins/ready/skill-menu/` drop-in folder - no patch and no edit to the core.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

#: The gate action every install, turn-on and edit goes through. It is the one
#: `jarvis_skills.install()` already names, and the shipped
#: jarvis-framework.toml gives it tier "ask".
ACTION = "modify_own_code"

#: The tiers a person really answers on. `jarvis_gate.check` returns
#: allowed=True on "notify" ("you were told after") and on "auto" (nobody in
#: the loop at all); `jarvis_skills.refine()` refuses those for the same
#: reason. `install()` checks this itself (skill-install-note.patch), and this
#: module re-checks it before it writes anything of its own.
ASKED_TIERS = ("ask", "never")

#: The exact sentence the owner required on the card and on the row (Gemini's
#: ruling 6, 2026-11-02). One wording, one place: every card, every row and
#: every reply builds it here, so it cannot drift between surfaces.
INERT_SENTENCE = ("Imported SKILL.md instructions ({n} file(s) in scripts/ are "
                  "kept inert and never run automatically).")

#: How many folders a Hermes scan will look at. A scan that walks forever is a
#: hang, and no real `~/.hermes/skills` holds this many. A refusal, not a
#: truncation: the scan says it stopped.
MAX_HERMES = 200

#: How deep the Hermes scan looks for a SKILL.md. Hermes keeps category
#: folders (`mlops/axolotl/SKILL.md`), so one level is not enough and an
#: unbounded walk is not a bound.
MAX_HERMES_DEPTH = 4

#: The name a skill is addressed by. The same rule as
#: `jarvis_skills._NAME_RE`, taken from there rather than typed twice.
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: What a zip member may not be: an absolute path, a drive letter, or a climb.
_NOT_A_MEMBER = re.compile(r"^(?:[A-Za-z]:|[\\/]|.*(?:^|[\\/])\.\.(?:[\\/]|$))")

#: Routes this module answers. Nothing here duplicates `GET /api/skills` or
#: `POST /api/skills/decide` - those already exist and both apps use them.
GET_ROUTES = ("/api/skills/menu",)
POST_ROUTES = ("/api/skills/install", "/api/skills/import/scan",
               "/api/skills/state", "/api/skills/edit")

_NO_SKILLS = ("jarvis_skills.py is not beside this file, so there is no skill "
              "library to open")

#: Why a card is not raised, in the PC's own words, for the tiers that are not
#: a person's answer. Kept in step with jarvis_skills.refine()'s message.
_NOT_ASKED = ("installing or editing a skill needs a person to answer for it, "
              "and modify_own_code is tier {tier!r}. Set it to 'ask' in "
              "jarvis-framework.toml, or to 'never' to refuse these outright.")


# --------------------------------------------------------------------------
#   The modules beside this one, reached lazily so this file imports anywhere
# --------------------------------------------------------------------------

def _sk():
    """jarvis_skills, or None. None is an answer, not an error: every entry
    point here says so in words rather than raising into the caller."""
    try:
        import jarvis_skills
        return jarvis_skills
    except Exception:
        return None


def _gate():
    """The gate, or None. None fails CLOSED - see `_tier_of`."""
    try:
        import jarvis_gate
        return jarvis_gate
    except Exception:
        return None


# --------------------------------------------------------------------------
#   Where things live. Read per call, never captured at import: a suite points
#   JARVIS_SKILLS_DIR at a temp folder and then imports this module.
# --------------------------------------------------------------------------

def skills_root() -> Optional[Path]:
    sk = _sk()
    return Path(sk.SKILLS_DIR) if sk is not None else None


def off_root() -> Optional[Path]:
    """Where a skill goes when it is turned off: beside the skills folder, not
    inside it, because everything inside it is a skill the model may read."""
    named = str(os.environ.get("JARVIS_SKILLS_OFF") or "").strip()
    if named:
        return Path(named)
    root = skills_root()
    return None if root is None else root.parent / "skills-off"


def incoming_root() -> Optional[Path]:
    """A throwaway folder for what a .zip turned out to hold, and for the copy
    an edit is written into before the scanner sees it. Emptied after every
    request; nothing here is ever loaded as a skill."""
    named = str(os.environ.get("JARVIS_SKILLS_INCOMING") or "").strip()
    if named:
        return Path(named)
    root = skills_root()
    return None if root is None else root.parent / "skills-incoming"


def hermes_root() -> Path:
    """`%USERPROFILE%\\.hermes\\skills` - Hermes's own folder, read only."""
    named = str(os.environ.get("JARVIS_HERMES_SKILLS") or "").strip()
    if named:
        return Path(named)
    return Path(os.path.expanduser("~")) / ".hermes" / "skills"


def inert_line(n: int) -> str:
    """The one sentence, in the owner's words, for `n` files in scripts/."""
    return INERT_SENTENCE.format(n=max(0, int(n)))


# --------------------------------------------------------------------------
#   Small shared steps
# --------------------------------------------------------------------------

def _clean_name(value: Any) -> str:
    """A skill name, or "". The same rule jarvis_skills uses to address one."""
    name = str(value or "").strip()
    if not _NAME_RE.match(name) or len(name) > 64:
        return ""
    return name


def _inside(root: Path, path: Path) -> bool:
    """True when `path` really is under `root` after resolution - the check
    that stops a name, a link or a zip member climbing out."""
    try:
        root = Path(root).resolve()
        path = Path(path).resolve()
    except OSError:
        return False
    return path == root or root in path.parents


def _scripts_in(folder: Path) -> list:
    """Every file under `scripts/` in a skill folder, as posix relative paths.

    The same predicate the scanner's `is_bundled_script()` uses for the head
    of the path, split on BOTH separators for the reason written there: a
    boundary that only holds because something upstream stayed correct is one
    refactor from being wrong.
    """
    out = []
    try:
        for f in sorted(Path(folder).rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(folder).as_posix()
            if rel.replace("\\", "/").split("/")[0] == "scripts":
                out.append(rel)
    except OSError:
        return out
    return out


def _rmtree(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _parse(folder: Path, trust: str = "third_party"):
    """(skill, error words). The existing parser, called, never copied."""
    sk = _sk()
    if sk is None:
        return None, _NO_SKILLS
    try:
        return sk.parse_skill(Path(folder), trust=trust), ""
    except Exception as exc:                      # SkillError, and anything odd
        return None, str(exc)


# --------------------------------------------------------------------------
#   A .zip, unpacked safely into a throwaway folder
# --------------------------------------------------------------------------

def _zip_bytes() -> int:
    sk = _sk()
    return int(getattr(sk, "MAX_SKILL_DIR", 5 * 1024 * 1024))


def _zip_files() -> int:
    sk = _sk()
    return int(getattr(sk, "MAX_FILES", 64))


def unpack_zip(zip_path: Path, into: Path) -> tuple:
    """Unpack one .zip into `into`. Returns (folder, why).

    Every bound is a REFUSAL, never a truncation, and they are the skill's own
    (jarvis_skills.MAX_FILES / MAX_SKILL_DIR): a zip that unpacks to more than a
    skill could ever hold is refused before it is written, not after. A member
    that is absolute, carries a drive letter, climbs with `..` or is a symlink
    refuses the whole archive - one bad member is not a warning, it is a
    different file than the one the owner picked.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        return None, f"that .zip could not be opened ({exc})"
    files, total = 0, 0
    try:
        with zf:
            for info in zf.infolist():
                raw = str(info.filename or "").replace("\\", "/")
                if not raw or raw.endswith("/"):
                    continue
                if raw.startswith("__MACOSX/"):
                    continue
                if _NOT_A_MEMBER.match(raw):
                    return None, (f"the .zip holds a file that points outside "
                                  f"itself ({raw!r}); it was not unpacked")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    return None, (f"the .zip holds a link ({raw!r}), and a "
                                  f"skill is only ever plain files")
                files += 1
                total += int(info.file_size or 0)
                if files > _zip_files():
                    return None, (f"the .zip holds more than {_zip_files()} "
                                  f"files, which is more than a skill may have")
                if total > _zip_bytes():
                    return None, (f"the .zip unpacks to more than "
                                  f"{_zip_bytes() // (1024 * 1024)} MB, which is "
                                  f"more than a skill may have")
                parts = [p for p in raw.split("/") if p not in ("", ".")]
                dest = Path(into).joinpath(*parts)
                if not _inside(into, dest):
                    return None, (f"the .zip holds a file that points outside "
                                  f"itself ({raw!r}); it was not unpacked")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out, 64 * 1024)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        return None, f"that .zip could not be unpacked ({exc})"
    return _find_one_skill(Path(into))


def _find_one_skill(root: Path) -> tuple:
    """The ONE skill folder in an unpacked archive. (folder, why).

    More than one SKILL.md is refused rather than guessed at: picking the first
    would install a skill the owner did not choose, and installing them all
    would be a bulk approval, which this project does not build.

    A `.zip` GitHub built gets its folder renamed to the skill's own name
    first: `my-skill-main/SKILL.md` says `name: my-skill`, and the spec (and
    `parse_skill`) require the folder to be the name. The rename happens in the
    throwaway copy, is checked by the same `parse_skill`, and is named in the
    reply - nothing here decides a name of its own.
    """
    found = []
    try:
        for f in sorted(Path(root).rglob("SKILL.md")):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            if len(rel.parts) > MAX_HERMES_DEPTH:
                continue
            if any(p.startswith(".") for p in rel.parts):
                continue
            found.append(f.parent)
    except OSError as exc:
        return None, f"the unpacked folder could not be read ({exc})"
    if not found:
        return None, ("the .zip holds no SKILL.md, so there is no skill in it")
    if len(found) > 1:
        names = ", ".join(sorted(p.name for p in found[:6]))
        return None, (f"the .zip holds {len(found)} skills ({names}). Unzip it "
                      f"and install the one you want.")
    folder = found[0]
    skill, _why = _parse(folder)
    if skill is not None:
        return folder, ""
    sk = _sk()
    if sk is not None:
        try:
            fm, _body = sk._parse_frontmatter(
                (folder / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
            wanted = _clean_name(fm.get("name"))
        except Exception:
            wanted = ""
        if wanted and wanted != folder.name:
            renamed = folder.parent / wanted
            try:
                if not renamed.exists():
                    shutil.move(str(folder), str(renamed))
                    skill, _why = _parse(renamed)
                    if skill is not None:
                        return renamed, ""
            except OSError:
                pass
    return folder, ""


# --------------------------------------------------------------------------
#   What the owner sees: the list, and what a folder would do
# --------------------------------------------------------------------------

def _row(name: str, row: dict, folder: Optional[Path], enabled: bool) -> dict:
    """One skill, as the menu shows it, with the sentence when it has scripts."""
    skill, why = (None, "")
    if folder is not None:
        skill, why = _parse(folder, trust=str(row.get("trust") or "third_party"))
    scripts = _scripts_in(folder) if folder is not None else []
    n = len(scripts)
    # Q3 (2026-11-05): a pack's whole SHA-256 manifest is re-checked as it is
    # listed, and a pack that no longer matches is shown as changed rather than
    # silently offered. The check is the pack manager's; a skill that was not
    # installed by it is simply not in its ledger and answers unchanged.
    tampered, tampered_files = False, []
    try:
        import jarvis_packs as _packs
        check = _packs.verify_pack(name)
        tampered = bool(check.get("tampered"))
        tampered_files = sorted([*(check.get("changed") or []),
                                 *(check.get("missing") or [])])
    except Exception:
        pass
    out = {
        "name": name,
        "description": row.get("description", "") or (skill.description if skill else ""),
        "trust": row.get("trust", "") or (skill.trust if skill else "third_party"),
        "uses": int(row.get("uses", 0) or 0),
        "verdict": row.get("verdict", ""),
        "installed": float(row.get("installed", 0) or 0),
        "enabled": bool(enabled),
        "indexed": bool(row),
        "files": len(skill.files) if skill else 0,
        "scripts": n,
        # The owner's sentence, on every row that ships a scripts/ folder. On a
        # row with none it is "" - there is nothing to say, and saying it would
        # train the owner to stop reading it.
        "inert": inert_line(n) if n else "",
        "parses": skill is not None,
        "tampered": tampered,
        "tampered_files": tampered_files,
        "why": why if skill is None else (
            "it has changed on disk since it was installed, so it is not loaded "
            "until it is installed again" if tampered else ""),
    }
    return out


def _index() -> dict:
    sk = _sk()
    if sk is None:
        return {}
    try:
        return dict(sk._read_index() or {})
    except Exception:
        return {}


def _write_index(ix: dict) -> bool:
    sk = _sk()
    if sk is None:
        return False
    try:
        return bool(sk._write_index(ix))
    except Exception:
        return False


def _skill_text(folder: Optional[Path]) -> str:
    """One skill's SKILL.md, or "". Never raises: a missing file is ""."""
    if folder is None:
        return ""
    try:
        md = Path(folder) / "SKILL.md"
        if not md.is_file():
            return ""
        limit = int(getattr(_sk(), "MAX_SKILL_MD", 64 * 1024))
        return md.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _folder_of(name: str) -> Optional[Path]:
    """The folder a named skill is in right now - installed, or turned off."""
    root, off = skills_root(), off_root()
    for base in (root, off):
        if base is None:
            continue
        folder = base / name
        if (folder / "SKILL.md").is_file():
            return folder
    return None


def _installed_dirs() -> list:
    root = skills_root()
    if root is None or not root.is_dir():
        return []
    try:
        return sorted(p for p in root.iterdir()
                      if p.is_dir() and not p.name.startswith(".")
                      and (p / "SKILL.md").is_file())
    except OSError:
        return []


def _off_dirs() -> list:
    root = off_root()
    if root is None or not root.is_dir():
        return []
    try:
        return sorted(p for p in root.iterdir()
                      if p.is_dir() and not p.name.startswith(".")
                      and (p / "SKILL.md").is_file())
    except OSError:
        return []


_OFF_NAME = ".off.json"


def _read_off() -> dict:
    root = off_root()
    if root is None:
        return {}
    try:
        data = json.loads((root / _OFF_NAME).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_off(rows: dict) -> bool:
    root = off_root()
    if root is None:
        return False
    try:
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / (_OFF_NAME + ".tmp")
        tmp.write_text(json.dumps(rows, indent=2), "utf-8")
        os.replace(tmp, root / _OFF_NAME)
        return True
    except Exception:
        return False


def menu() -> dict:
    """Everything the PC's Skills settings needs in one read."""
    sk = _sk()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS, "skills": [], "off": [],
                "counts": {}, "hermes": {"available": False, "root": "",
                                         "why": _NO_SKILLS}}
    ix = _index()
    on_rows, off_rows, seen = [], [], set()
    for folder in _installed_dirs():
        seen.add(folder.name)
        on_rows.append(_row(folder.name, ix.get(folder.name, {}), folder, True))
    stored = _read_off()
    for folder in _off_dirs():
        if folder.name in seen:
            continue
        meta = stored.get(folder.name) or {}
        row = meta.get("row") if isinstance(meta, dict) else {}
        off_rows.append(_row(folder.name, row or {}, folder, False))
        seen.add(folder.name)
    # A row in the index whose folder is gone is a skill that was deleted from
    # under Jarvis (or a half-finished move). It is NOT an installed skill, and
    # saying it is would be a claim the load path cannot back.
    missing = sorted(n for n in ix if n not in seen)
    root = hermes_root()
    return {
        "ok": True,
        "skills": on_rows,
        "off": off_rows,
        "missing": missing,
        "counts": {
            "installed": len(on_rows),
            "off": len(off_rows),
            "with_scripts": sum(1 for r in on_rows + off_rows if r["scripts"]),
        },
        "hermes": {
            "available": root.is_dir(),
            "root": str(root),
            "why": "" if root.is_dir() else
                   (f"There is no {root} folder on this PC, so there are no "
                    f"Hermes skills to import. Nothing is downloaded."),
        },
        "sentence": INERT_SENTENCE,
        "note": ("Nothing here installs, turns a skill on or edits one without "
                 "ONE approval card you answer on this PC. Turning one off, and "
                 "removing one - installed or turned off - are immediate."),
    }


def preview(folder: Path, trust: str = "third_party") -> dict:
    """What installing this folder would do - the scanner's answer, no card.

    `vet()` is the existing scanner, called. Nothing here decides a verdict:
    the findings, the summary and the block/warn counts are its own.
    """
    sk = _sk()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS, "verdict": "malformed"}
    skill, why = _parse(folder, trust=trust)
    if skill is None:
        return {"ok": False, "verdict": "malformed", "reason": why,
                "inert": "", "scripts": 0, "needs_warnings": False}
    report = sk.vet(skill)
    n = len([f for f in skill.files
             if f.replace("\\", "/").split("/")[0] == "scripts"])
    return {
        "ok": True,
        "name": skill.name,
        "description": skill.description,
        "trust": skill.trust,
        "verdict": report["verdict"],
        "summary": report["summary"],
        "findings": report["findings"],
        "blocking": report["blocking"],
        "warnings": report["warnings"],
        "files": len(skill.files),
        "sha256": skill.sha256,
        "scripts": n,
        "inert": inert_line(n) if n else "",
        "question": inert_line(n),
        "needs_warnings": report["verdict"] == "review",
    }


# --------------------------------------------------------------------------
#   Where an install comes from
# --------------------------------------------------------------------------

def _hermes_folder(rel: Any) -> tuple:
    """One folder under the Hermes root, from a RELATIVE name. (folder, why).

    The client never sends a path: it sends the relative name the scan showed
    it, and this joins it under the one root and proves the result is still
    inside - so `../../` is not a way to make Jarvis read somewhere else.
    """
    rel = str(rel or "").strip().replace("\\", "/").strip("/")
    if not rel or rel.startswith("/") or ":" in rel:
        return None, "need a folder name from the Hermes scan"
    parts = [p for p in rel.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        return None, f"{rel!r} is not a folder name under the Hermes skills"
    root = hermes_root()
    folder = root.joinpath(*parts)
    if not _inside(root, folder) or not (folder / "SKILL.md").is_file():
        return None, (f"there is no skill at {rel!r} in {root} any more. Scan "
                      f"again.")
    return folder, ""


def _source(body: dict) -> tuple:
    """(folder, kind, cleanup, why) for one install request.

    Three kinds, and only three: a folder on this PC, a `.zip` on this PC, and
    a folder the Hermes scan named. There is no fourth, and nothing here opens
    a socket.
    """
    wanted = str(body.get("path") or "").strip()
    if wanted:
        path = Path(wanted)
        try:
            path = path.resolve()
        except OSError as exc:
            return None, "", None, f"that path could not be read ({exc})"
        if path.is_dir():
            return path, "folder", None, ""
        if path.is_file() and path.suffix.lower() == ".zip":
            base = incoming_root()
            if base is None:
                return None, "", None, _NO_SKILLS
            throwaway = base / f"zip-{int(time.time() * 1000)}-{os.getpid()}"
            _rmtree(throwaway)
            try:
                throwaway.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return None, "", None, (f"a folder to unpack the .zip into "
                                        f"could not be made ({exc})")
            folder, why = unpack_zip(path, throwaway)
            if folder is None:
                _rmtree(throwaway)
                return None, "", None, why
            return folder, "zip", throwaway, ""
        return None, "", None, (f"{wanted!r} is not a folder or a .zip on this "
                                f"PC")
    rel = body.get("hermes")
    if rel is not None:
        folder, why = _hermes_folder(rel)
        return (folder, "hermes", None, "") if folder is not None else (None, "", None, why)
    return None, "", None, ("need a folder, a .zip, or a Hermes folder name")


# --------------------------------------------------------------------------
#   Installing: the existing scanner, then ONE card
# --------------------------------------------------------------------------

def install_source(body: dict) -> tuple:
    """POST /api/skills/install. (status, payload).

    `dry_run` stops after the scanner: the findings and the sentence, so the
    owner can read what they are about to be asked about, and no card. Anything
    else calls `jarvis_skills.install()` - which vets, refuses a blocked skill
    without ever asking, and raises exactly ONE `modify_own_code` card.
    """
    sk = _sk()
    if sk is None:
        return 503, {"ok": False, "reason": _NO_SKILLS}
    folder, kind, cleanup, why = _source(body)
    try:
        if folder is None:
            return 400, {"ok": False, "reason": why, "verdict": "malformed"}
        # The TRUST IS NOT THE CLIENT'S TO SET. `local` is scanned less
        # strictly than `third_party` (bundled scripts become a note, and a
        # missing licence is not flagged), so a request that could name its own
        # trust would be a request that could weaken the scanner. Anything that
        # arrives from outside this PC is third_party, which is what the
        # scanner's strictest rules are for.
        trust = "third_party"
        dry = bool(body.get("dry_run"))
        if dry:
            out = preview(folder, trust=trust)
            out["source"] = kind
            return (200 if out.get("ok") else 409), out

        n = len(_scripts_in(folder))
        note = inert_line(n)
        out = sk.install(folder, trust=trust,
                         accept_warnings=bool(body.get("accept_warnings")),
                         note=note)
        out["source"] = kind
        out["scripts"] = n
        out["inert"] = inert_line(n)
        if out.get("ok"):
            return 200, out
        if out.get("needs") == "accept_warnings":
            return 409, out
        if out.get("asked") is False and out.get("quarantined"):
            return 200, out          # refused, quarantined, and never asked
        return 409, out
    finally:
        _rmtree(cleanup)


# --------------------------------------------------------------------------
#   Import from Hermes: a read-only scan, and then the same install
# --------------------------------------------------------------------------

def import_scan() -> tuple:
    """POST /api/skills/import/scan. (status, payload).

    Read-only. It lists what is in `~/.hermes/skills` and what the scanner says
    about each one; it copies, moves and installs NOTHING, and it raises no
    card. Each row is then installed by its own `/api/skills/install` request
    with `{"hermes": <folder>}` - one skill, one card.
    """
    sk = _sk()
    if sk is None:
        return 503, {"ok": False, "reason": _NO_SKILLS, "found": []}
    root = hermes_root()
    if not root.is_dir():
        return 200, {
            "ok": True, "available": False, "root": str(root), "found": [],
            "counts": {"found": 0, "clean": 0, "review": 0, "refused": 0,
                       "installed": 0},
            "why": (f"There is no {root} folder on this PC, so there are no "
                    f"Hermes skills to import. Nothing is downloaded."),
        }
    ix = _index()
    have = set(ix) | {p.name for p in _installed_dirs()} | {p.name for p in _off_dirs()}
    found, seen, stopped = [], 0, False
    try:
        for md in sorted(root.rglob("SKILL.md")):
            if not md.is_file():
                continue
            rel = md.relative_to(root)
            if len(rel.parts) > MAX_HERMES_DEPTH:
                continue
            if any(part.startswith(".") for part in rel.parts):
                continue          # `.hub/` is Hermes's own install bookkeeping
            folder = md.parent
            rel_name = folder.relative_to(root).as_posix()
            seen += 1
            if seen > MAX_HERMES:
                stopped = True
                break
            row = preview(folder, trust="third_party")
            row["folder"] = rel_name
            row["installed"] = folder.name in have
            found.append(row)
    except OSError as exc:
        return 503, {"ok": False, "reason": f"the Hermes folder could not be "
                                            f"read ({exc})", "found": []}
    counts = {"found": len(found),
              "clean": sum(1 for r in found if r.get("verdict") == "clean"),
              "review": sum(1 for r in found if r.get("verdict") == "review"),
              "refused": sum(1 for r in found if r.get("verdict") == "refuse"),
              "malformed": sum(1 for r in found if r.get("verdict") == "malformed"),
              "installed": sum(1 for r in found if r.get("installed"))}
    return 200, {
        "ok": True,
        "available": True,
        "root": str(root),
        "found": found,
        "counts": counts,
        "stopped": stopped,
        "why": (f"Stopped after {MAX_HERMES} skills. Nothing is installed by "
                f"this scan; each one is its own card." if stopped else ""),
        "note": ("Each folder here is installed on its own, through the same "
                 "scanner and its own ONE card. Nothing is copied or changed by "
                 "this list - a skill the scanner refuses cannot be installed "
                 "at all, which is why its button is not offered."),
    }


# --------------------------------------------------------------------------
#   Turning one off, and back on
# --------------------------------------------------------------------------

def _discard_off(name: str) -> tuple:
    """Delete ONE skill that is TURNED OFF, and only that.

    `jarvis_skills.uninstall()` is the one removal for an INSTALLED skill and
    stays that way: it resolves a name only under the skills folder, which is
    deliberate. The effect was that a folder THIS module parked in
    `skills-off\\` was beyond every removal door in either app - a turned-off
    skill could be turned back on (one card) and never got rid of. This deletes
    the copy this module parked, plus its own row in `skills-off\\.off.json`,
    and nothing else.

    No card: the folder is already out of the load path - nothing is offered
    from it and `load()` cannot find it - so this only takes a capability away,
    the same rule that makes turning one off immediate. ONE name per request:
    there is no list form, and an installed name is refused rather than
    removed.
    """
    root, off = skills_root(), off_root()
    if root is None or off is None:
        return 503, {"ok": False, "reason": _NO_SKILLS}
    if (root / name / "SKILL.md").is_file():
        return 409, {"ok": False, "reason": (
            f"{name} is installed, not turned off. Remove it with Remove, "
            f"which is the same question that has always removed a skill.")}
    dest = off / name
    if not (dest / "SKILL.md").is_file():
        return 404, {"ok": False, "reason": f"no turned-off skill called {name}"}
    _rmtree(dest)
    if dest.exists():
        return 503, {"ok": False, "reason": (
            f"{name} could not be deleted - close anything that has one of its "
            f"files open and try again")}
    rows = _read_off()
    rows.pop(name, None)
    _write_off(rows)
    # The pin belongs to a body that no longer exists anywhere. Leaving it
    # would judge a later skill of the same name against a deleted one.
    try:
        import jarvis_content_risk as _cr
        _cr.unpin("skill", name)
    except Exception:
        pass
    return 200, {"ok": True, "name": name, "enabled": False, "removed": True,
                 "reason": (f"{name} is deleted. Its folder is gone from this "
                            f"PC, and there is no undo.")}


def set_state(body: dict) -> tuple:
    """POST /api/skills/state. (status, payload).

    OFF is immediate: it MOVES the folder out of the skills folder and takes
    its row out of the index, which is the list `cards()` hands the model - so
    the skill stops being offered and `load()` cannot find it. Nothing is
    deleted.

    ON runs the same scanner and the same ONE card as installing it, then
    deletes only the moved copy. A skill that has changed while it was off (or
    that was refused) does not come back on.

    `{"remove": true}` deletes ONE skill that is already turned off - see
    `_discard_off`. It is the only door to that parked copy, and it refuses an
    installed name.
    """
    sk = _sk()
    if sk is None:
        return 503, {"ok": False, "reason": _NO_SKILLS}
    name = _clean_name(body.get("name"))
    if not name:
        return 400, {"ok": False, "reason": "need a skill name"}
    if body.get("remove"):
        # ONE request, ONE thing: "remove" and "on" are opposite questions.
        if body.get("on"):
            return 400, {"ok": False, "reason": (
                "one request, one thing: send either remove or on, not both")}
        return _discard_off(name)
    on = bool(body.get("on"))
    root, off = skills_root(), off_root()
    if root is None or off is None:
        return 503, {"ok": False, "reason": _NO_SKILLS}

    if not on:
        dest = root / name
        if not (dest / "SKILL.md").is_file():
            return 404, {"ok": False, "reason": f"no installed skill called {name}"}
        moved = off / name
        _rmtree(moved)
        try:
            off.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(moved))
        except OSError as exc:
            return 503, {"ok": False, "reason": f"{name} could not be moved out "
                                                f"of the skills folder ({exc})"}
        ix = _index()
        row = ix.pop(name, {}) or {}
        _write_index(ix)
        rows = _read_off()
        rows[name] = {"row": row, "at": time.time()}
        _write_off(rows)
        # The content-risk pin belongs to the approved text; taking the skill
        # out of the load path must not silently disarm the drift check, so the
        # pin is left alone and `install()` re-pins it when it comes back on.
        return 200, {"ok": True, "name": name, "enabled": False,
                     "reason": (f"{name} is off. It is not offered to the model "
                                f"and cannot be loaded, and nothing was deleted "
                                f"- turn it back on to scan it again.")}

    src = off / name
    if not (src / "SKILL.md").is_file():
        return 404, {"ok": False, "reason": f"{name} is not turned off"}
    stored = (_read_off().get(name) or {}).get("row") or {}
    trust = str(stored.get("trust") or "third_party")
    n = len(_scripts_in(src))
    note = (inert_line(n) + " Turning it back on lets the model read it again "
            "from now on.")
    out = sk.install(src, trust=trust,
                     accept_warnings=bool(body.get("accept_warnings")),
                     note=note)
    out["name"] = name
    out["scripts"] = n
    out["inert"] = inert_line(n) if n else ""
    if out.get("ok"):
        _rmtree(src)
        rows = _read_off()
        rows.pop(name, None)
        _write_off(rows)
        # A pack the pack manager installed is IMMUTABLE once installed, and its
        # SHA-256 manifest is the ledger's. Turning it on just ran the scanner and
        # its ONE card again, so the manifest is re-taken with the old digest kept
        # in the history: this is an approved change, not tampering (Q3, 2026-11-05).
        try:
            import jarvis_packs as _packs
            _packs.repin_after_enable(name)
        except Exception:
            pass
        # install() writes a FRESH index row (uses 0, no notes). The skill's
        # own history should survive being switched off and on again, so it is
        # put back - but only when the text is the one that was turned off:
        # `install()` re-pinned and re-hashed whatever it just copied, and a
        # changed body must not inherit notes written about the old one.
        ix = _index()
        fresh = ix.get(name)
        if isinstance(fresh, dict) and fresh.get("sha256") == stored.get("sha256"):
            for key in ("uses", "notes", "installed"):
                if key in stored:
                    fresh[key] = stored[key]
            ix[name] = fresh
            _write_index(ix)
        out["enabled"] = True
        return 200, out
    out["enabled"] = False
    if out.get("needs") == "accept_warnings":
        return 409, out
    if out.get("asked") is False and out.get("quarantined"):
        return 200, out
    return 409, out


# --------------------------------------------------------------------------
#   Editing one
# --------------------------------------------------------------------------

def edit(body: dict) -> tuple:
    """POST /api/skills/edit. (status, payload).

    The new SKILL.md is written into a COPY of the skill folder and installed
    through `jarvis_skills.install()` - the same scanner, the same quarantine
    and the same ONE card. A block finding is refused before any card; the copy
    is thrown away either way.

    Only SKILL.md is replaced. `references/`, `scripts/` and anything else the
    skill ships are carried across untouched, and nothing in them is run.
    """
    sk = _sk()
    if sk is None:
        return 503, {"ok": False, "reason": _NO_SKILLS}
    name = _clean_name(body.get("name"))
    if not name:
        return 400, {"ok": False, "reason": "need a skill name"}
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        return 400, {"ok": False, "reason": "need the SKILL.md text"}
    if len(text.encode("utf-8")) > int(getattr(sk, "MAX_SKILL_MD", 64 * 1024)):
        return 413, {"ok": False,
                     "reason": (f"that SKILL.md is larger than a skill may be "
                                f"({getattr(sk, 'MAX_SKILL_MD', 65536) // 1024} "
                                f"KB). Split the detail into a references/ file.")}
    root, base = skills_root(), incoming_root()
    if root is None or base is None:
        return 503, {"ok": False, "reason": _NO_SKILLS}
    src = root / name
    if not (src / "SKILL.md").is_file():
        off = off_root()
        if off is not None and (off / name / "SKILL.md").is_file():
            return 409, {"ok": False,
                         "reason": (f"{name} is turned off. Turn it back on "
                                    f"before editing it.")}
        return 404, {"ok": False, "reason": f"no installed skill called {name}"}

    # A block finding is not askable, so the card must not even be raised for
    # one. install() would refuse it too - this refuses it BEFORE a temp copy
    # is quarantined, and says what the finding was.
    blocking = [f.as_dict() for f in sk.scan_text(text, "SKILL.md")
                if getattr(f, "severity", "") == "block"]
    if blocking:
        return 200, {"ok": False, "asked": False, "changed": False,
                     "reason": ("that edit contains something the scanner "
                                "refuses to store in a skill: "
                                + blocking[0].get("message", "a block finding")),
                     "findings": blocking}

    stored = (_index().get(name) or {})
    trust = str(stored.get("trust") or "third_party")
    work = base / f"edit-{int(time.time() * 1000)}-{os.getpid()}" / name
    try:
        try:
            shutil.copytree(src, work)
        except OSError as exc:
            return 503, {"ok": False, "reason": f"the skill could not be copied "
                                                f"for editing ({exc})"}
        try:
            (work / "SKILL.md").write_text(text, "utf-8")
        except OSError as exc:
            return 503, {"ok": False, "reason": f"the edited SKILL.md could not "
                                                f"be written ({exc})"}
        before = (src / "SKILL.md").stat().st_size if (src / "SKILL.md").is_file() else 0
        n = len(_scripts_in(work))
        note = (inert_line(n) + f" This REPLACES the SKILL.md of the installed "
                                f"skill {name!r} ({before} -> "
                                f"{len(text.encode('utf-8'))} bytes).")
        out = sk.install(work, trust=trust,
                         accept_warnings=bool(body.get("accept_warnings")),
                         note=note)
        out["name"] = name
        out["edited"] = True
        out["scripts"] = n
        out["inert"] = inert_line(n) if n else ""
        if out.get("ok"):
            out["asked"] = True
            return 200, out
        if out.get("needs") == "accept_warnings":
            return 409, out
        if out.get("asked") is False and out.get("quarantined"):
            return 200, out
        return 409, out
    finally:
        # The parent of `work` is the whole throwaway tree for this request.
        _rmtree(work.parent)


# --------------------------------------------------------------------------
#   The routes - only the ones that did not already exist
# --------------------------------------------------------------------------

def handle_get(route: str, query: str = "") -> tuple:
    """(status, payload) for the read route. No card: reading is free."""
    args = parse_qs(str(query or ""))
    one = lambda k: (args.get(k) or [""])[0]        # noqa: E731
    if route == "/api/skills/menu":
        out = menu()
        if one("name") and out.get("ok"):
            wanted = one("name")
            for r in out["skills"] + out["off"]:
                if r["name"] == wanted:
                    # ONE skill's own SKILL.md, so the owner can read and edit
                    # what the model will follow. The list itself never carries
                    # a body: a menu of 200 skills would be 200 bodies.
                    r = dict(r)
                    r["text"] = _skill_text(_folder_of(wanted))
                    return 200, r
            return 404, {"ok": False, "reason": f"no skill called {wanted}"}
        return (200 if out.get("ok") else 503), out
    return 404, {"error": "no such read"}


def handle_post(route: str, body: Any) -> tuple:
    """(status, payload) for the four command routes."""
    if not isinstance(body, dict):
        return 400, {"error": "need a JSON object"}
    if route == "/api/skills/install":
        return install_source(body)
    if route == "/api/skills/import/scan":
        return import_scan()
    if route == "/api/skills/state":
        return set_state(body)
    if route == "/api/skills/edit":
        return edit(body)
    return 404, {"error": "no such command"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so these routes are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original, untouched - the same shape
    `jarvis_skill_hub.install()` uses, and the reason this feature needs no
    patch: `plugins/ready/skill-menu/plugin.json` names this module and
    `jarvis_plugins.py` makes the call a patch would have made.

    It adds five routes and touches none of the ones that already exist:
    `GET /api/skills` (the list) and `POST /api/skills/decide` (the removal,
    and its "are you sure?") are jarvis_hud.py's already, in both apps.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_skill_menu", False):
        return "  skill-menu  install, import, on/off and edit (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in GET_ROUTES:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_ROUTES:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_skill_menu = True
    do_POST._jarvis_skill_menu = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  skill-menu  install from a folder or .zip, import from Hermes, "
            "on/off and edit: on")


# --------------------------------------------------------------------------
#   For the suites
# --------------------------------------------------------------------------

def _self_check() -> dict:
    """What this module can see right now. Read-only: it opens no skill and
    raises no card."""
    sk = _sk()
    root = skills_root()
    return {"module": "jarvis_skill_menu", "version": 1,
            "jarvis_skills": sk is not None,
            "gate": _gate() is not None,
            "skills_dir": str(root) if root else "",
            "off_dir": str(off_root()) if off_root() else "",
            "incoming": str(incoming_root()) if incoming_root() else "",
            "hermes": str(hermes_root()),
            "hermes_available": hermes_root().is_dir(),
            "installed": len(_installed_dirs()),
            "off": len(_off_dirs()),
            "sentence": INERT_SENTENCE,
            "python": sys.version_info[0]}


if __name__ == "__main__":                              # pragma: no cover
    print(json.dumps(_self_check(), indent=2))
