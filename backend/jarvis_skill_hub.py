#!/usr/bin/env python3
"""jarvis_skill_hub.py - the skill library's other doors: a reference manual
read only when it is asked for, a leading `/skill` chain, a project's own
skills, and `/learn`.

READ jarvis_skills.py FIRST. THIS IS NOT A SECOND COPY OF IT, AND IT DOES NOT
EDIT IT.

jarvis_skills.py owns the skill: the frontmatter parser (`parse_skill`, :187),
the scanner (`scan_text` :375, `vet` :455), the quarantine (`_quarantine`
:621), the ~100-token card (`cards` :684), the full body (`load` :705),
installing (`install` :556), removing (`uninstall` :634) and writing one
(`write_skill` :775). Every one of those is CALLED from here.

WHAT WAS ALREADY THERE, MEASURED BEFORE A LINE WAS WRITTEN (2026-10-15)

Four of the eight things this work item asked for already existed. Building
them again would have been a second copy of a working feature and a second
place for it to drift:

  * the compact index - `jarvis_skills.cards()` (jarvis_skills.py:684) returns
    name/description/trust/uses/notes for every installed skill and no body,
    and `jarvis_hud._skills_view()` (jarvis_hud.py:448) already serves it over
    `GET /api/skills` (jarvis_hud.py:2435, 2502);
  * the full body - `jarvis_skills.load(name)` (jarvis_skills.py:705) returns
    it, re-vetted and re-hashed on every load, not only at install;
  * List + Forget-with-confirm - `POST /api/skills/decide` with
    `{"remove": true}` (jarvis_hud.py:756) calls `jarvis_skills.uninstall`,
    and the "are you sure?" question is already in BOTH apps: the phone's
    `Skills.removeWarning()` (jarvis-client .../client/net/Skills.kt:84) and
    the desktop's `brain_remove_skill`. The owner's 2026-09-24 decision is
    what that question IS, so it is kept exactly where it already is;
  * saving one with a card - `jarvis_skills.write_skill()` (:775) scans the
    body (`:799`), refuses on a block finding (`:801`) and raises the
    `modify_own_code` card BEFORE it writes (`:806`).

Genuinely missing, and therefore what this module is:

  1. `references()` / `level2_reference()` - the reference manuals.
     `parse_skill` collects `references/<file>.md` into `Skill.files`
     (:223-231) and `load()` returns them as names only (:752). Nothing in
     this repository ever read one. A large manual is listed by name and size
     for free and read only when asked for, and what is read goes through
     `scan_text` before it can reach a model.
  2. `parse_chain()` - up to five LEADING `/skill-name` or `/bundle-name`
     tokens off the front of a message, stopping at the first token that is
     not a known name, so `/path/to/file` is never swallowed.
  3. `project_roots()` / `project_skills()` - `<project folder>/.jarvis/skills`
     for projects the owner explicitly trusted (`jarvis_projects.py`), with any
     skill that fails the scan quarantined rather than loaded.
  4. `learn()` - `/learn`: a distillation document with the four sections
     (When to Use / Procedure / Pitfalls / Verification), scrubbed through
     `jarvis_scrub`, writing NOTHING AT ALL when the scrubber is absent, and
     saved only THROUGH `write_skill()` so the scanner and the card run where
     they have always run.

THE TWO RULES THAT MATTER MOST HERE

SCRUBBED, OR NOTHING. `/learn` turns the owner's own words into a file the
agent will read and follow. `jarvis_scrub` is the door this backend puts that
kind of text through, and the rule is the one chat history follows ("no key,
nothing is recorded"): no scrubber, nothing is written. `_scrubber()` returns
None rather than raising, and `learn()` returns before it touches a file. A
scrubber that FAILS also withholds the whole text (jarvis_scrub.scrub_text,
:460), and that marker is refused here too rather than saved as a skill.

A PERSON ANSWERS, OR NOTHING IS SAVED. `write_skill()` checks
`Verdict.allowed`, and `allowed` is True on the tiers `notify` and `auto`
where nobody was asked - `jarvis_skills.refine()` (:853-869) says exactly
that about the gate it shares. `modify_own_code` is `ask` in the shipped
config, so today it is a person's answer; `learn()` re-checks the TIER itself
the way `jarvis_skill_discovery.offer()` does (:631), so a config that listed
it as `notify` cannot turn the card into a rubber stamp.

WHAT THIS DOES NOT DO

- It never approves anything, there is no "yes to all", and no loop here
  raises more than one card.
- It does not read a web page, an email, a document, a note or tool output.
  `/learn` writes down what its caller hands it and nothing else.
- It does not edit `jarvis_skills.py`, which is one of the five files the
  patcher edits.
- It does not re-implement level 0, level 1, the list, the forget, the
  scanner, the quarantine or the card. It calls them.
- It is standard library plus the modules beside it. No network, no child
  process, no socket.

The routes it serves come from its own `install()`, called by the
`plugins/ready/skill-hub/` drop-in folder - no patch and no edit to the core.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlsplit

# --------------------------------------------------------------------------
#   Bounds. Every one of these is a refusal, never a truncation.
# --------------------------------------------------------------------------

#: The most leading `/skill` or `/bundle` tokens one message may open with.
MAX_CHAIN = 5

#: A reference manual larger than this is refused rather than read. It is well
#: past any real manual, and the reason a cap exists at all is written down in
#: jarvis_skills.py (:80): one skill padded its README with 22 MB of filler
#: purely to get past a scanner's size threshold. Size is a finding.
MAX_REFERENCE = 256 * 1024

#: Members one bundle may name. A bundle is a shortcut, not a script.
MAX_BUNDLE_SKILLS = 20

#: The file that names the bundles, beside the skill index jarvis_skills.py
#: already keeps (`INDEX = SKILLS_DIR / ".index.json"`, jarvis_skills.py:514).
BUNDLES_NAME = ".bundles.json"

#: One reference is one `.md` file name. No separator, so nothing here can
#: climb out of the folder it belongs to - `.../references/../../jarvis_gate.py`
#: is not a name this accepts, and neither is an absolute path.
_REF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.md$")

#: The name of a subfolder under a project's `.jarvis/skills/`.
_DIR_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: What a `/token` must look like on its own: `/skill-name`, and nothing glued
#: to the end of it, which is what keeps a file path out of the chain.
_TOKEN = re.compile(r"^/([A-Za-z0-9][A-Za-z0-9._-]{0,63})")

#: `scrub_text` replaces text it could not handle with this phrase rather than
#: passing it through unscrubbed (jarvis_scrub.py:481). A skill whose whole
#: body came back withheld is not a skill; it is a failed scrub, and it is
#: refused rather than saved.
_WITHHELD = "text withheld"

#: The gate action a new skill goes through. It is the one jarvis_skills.py
#: already uses for write_skill() and refine(), and the shipped
#: jarvis-framework.toml gives it tier "ask" (:281).
ACTION = "modify_own_code"

#: The four sections a distilled skill is made of, in order.
SECTIONS = ("When to Use", "Procedure", "Pitfalls", "Verification")

#: Routes this module answers. Nothing here duplicates `GET /api/skills` or
#: `POST /api/skills/decide` - those already exist and already have a caller in
#: both apps.
GET_ROUTES = ("/api/skills/hub/references", "/api/skills/hub/projects",
              "/api/skills/hub/lock")
POST_ROUTES = ("/api/skills/chain", "/api/skills/learn")

_NO_SKILLS = ("jarvis_skills.py is not beside this file, so there is no skill "
              "library to open")


# --------------------------------------------------------------------------
#   The modules beside this one, reached lazily so this file imports anywhere
# --------------------------------------------------------------------------

def _skills():
    """jarvis_skills, or None. None is an answer, not an error: every entry
    point here says so in words rather than raising into the caller."""
    try:
        import jarvis_skills
        return jarvis_skills
    except Exception:
        return None


def _scrubber():
    """jarvis_scrub, or None. Fails CLOSED: no scrubber, nothing is written.

    The same shape jarvis_receipts.py uses for the same reason (:289), and the
    rule chat history follows - no door, nothing written - applied to a skill
    rather than to a receipt.
    """
    try:
        import jarvis_scrub
        return jarvis_scrub
    except Exception:
        return None


def _tier(action: str = ACTION) -> str:
    """The tier `action` has right now, or "unknown" if it cannot be read.

    Read through jarvis_framework's own accessor, which is the one the gate
    itself trusts, rather than re-reading the TOML here.
    """
    try:
        import jarvis_framework
        return str(jarvis_framework.action_tier(action))
    except Exception:
        return "unknown"


def _audit(event: str, detail: dict) -> None:
    """One line in the audit log the project already keeps, or nothing. Never
    raises: a log that is off is not a reason for a feature to fail."""
    try:
        import jarvis_framework
        jarvis_framework.audit_log(event, detail)
    except Exception:
        pass


def _root(skills_dir=None) -> Path:
    if skills_dir is not None:
        return Path(skills_dir)
    sk = _skills()
    return Path(sk.SKILLS_DIR) if sk is not None else Path(
        os.path.expanduser("~/.openjarvis/skills"))


def _name_ok(name: Any) -> bool:
    """The name rule is jarvis_skills' own compiled pattern and its own 64
    character cap (jarvis_skills.py:100, :205), reused rather than restated -
    the rule is what stops `../../jarvis_gate` being addressable by name."""
    sk = _skills()
    if sk is None:
        return False
    s = str(name or "")
    try:
        return bool(sk._NAME_RE.match(s)) and len(s) <= 64
    except Exception:
        return False


def _under(root: Path, name: str) -> Path:
    """`root / name`, or ValueError. The containment check is the same one
    jarvis_skills._safe_dest makes (:545) for its own single root; a project's
    `.jarvis/skills` is a second root, so the check is applied to that root
    here rather than reached through a function that only knows one."""
    if not _name_ok(name):
        raise ValueError(f"unsafe skill name {name!r}")
    base = Path(root).resolve()
    dest = (base / str(name)).resolve()
    if dest == base or base not in dest.parents:
        raise ValueError(f"{name!r} would land outside {base}")
    return dest


# --------------------------------------------------------------------------
#   1. Progressive disclosure, level 2: the reference manuals
# --------------------------------------------------------------------------

def references(name: str, *, skills_dir=None) -> dict:
    """What reference manuals this skill ships, by name and size - and NOT
    their text. This is the free half of level 2: a caller can see that a
    manual exists, and how big it is, without paying a token for it.

    `parse_skill` already walks the folder and records every file
    (jarvis_skills.py:223); this filters that list to `references/` and reads
    none of them.
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS}
    try:
        dest = _under(_root(skills_dir), name)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}
    if not (dest / "SKILL.md").is_file():
        return {"ok": False, "reason": f"no skill called {name}"}
    try:
        skill = sk.parse_skill(dest)
    except Exception as exc:
        return {"ok": False, "reason": f"{name} does not parse: {exc}"}

    out = []
    for rel in list(skill.files):
        posix = str(rel).replace("\\", "/")
        if not posix.startswith("references/") or not posix.endswith(".md"):
            continue
        ref = posix.split("/", 1)[1]
        if "/" in ref or not _REF_NAME.match(ref):
            continue
        try:
            size = (dest / "references" / ref).stat().st_size
        except OSError:
            continue
        out.append({"reference": ref, "bytes": int(size),
                    "too_big_to_read": int(size) > MAX_REFERENCE})
    out.sort(key=lambda r: r["reference"])
    return {"ok": True, "name": name, "references": out,
            "note": ("Only the names and sizes are here. Ask for one and only "
                     "that one is read, scanned, and handed over.")}


def level2_reference(name: str, ref_file: str, *, skills_dir=None) -> dict:
    """One reference manual, read on demand - the third level of progressive
    disclosure, and the reason the other two can stay cheap.

    Read and then SCANNED, in that order, and refused outright if the scan
    finds a block. A reference is text an agent will read and follow, exactly
    like a SKILL.md, so it earns the same scanner; and the scan is over the raw
    bytes before the text reaches a model, which is the whole point of
    `scan_text` (jarvis_skills.py:375).
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS}
    ref = str(ref_file or "").strip()
    if "/" in ref or "\\" in ref or ref in (".", "..") or not _REF_NAME.match(ref):
        return {"ok": False, "reason":
                "a reference is one .md file name inside the skill's own "
                "references/ folder - letters, digits, dot, dash and "
                "underscore only, and no folder in it"}
    try:
        dest = _under(_root(skills_dir), name)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}
    if not (dest / "SKILL.md").is_file():
        return {"ok": False, "reason": f"no skill called {name}"}

    path = dest / "references" / ref
    try:
        if path.resolve().parent != (dest / "references").resolve():
            return {"ok": False, "reason": "that reference is not inside the skill"}
    except OSError:
        return {"ok": False, "reason": "that reference could not be resolved"}
    if not path.is_file():
        known = [r["reference"] for r in references(name, skills_dir=skills_dir)
                 .get("references", [])]
        return {"ok": False, "reason": f"{name} has no reference called {ref}",
                "references": known}
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"ok": False, "reason": f"that reference could not be measured ({exc})"}
    if size > MAX_REFERENCE:
        return {"ok": False, "reason":
                f"{ref} is {size // 1024} KB, over the {MAX_REFERENCE // 1024} KB "
                f"a reference may be. Refused rather than read: padding a file "
                f"past a scanner's limit is a known evasion, so an oversized "
                f"one is not opened"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "reason": f"that reference could not be read ({exc})"}

    where = f"references/{ref}"
    try:
        findings = sk.scan_text(text, where)
    except Exception as exc:
        # A scanner that raises is a scanner that did not clear the text.
        return {"ok": False, "refused": True, "name": name, "reference": ref,
                "findings": [], "reason":
                f"{ref} was refused: the scanner raised "
                f"{type(exc).__name__}, so it was not cleared"}
    blocked = [f.as_dict() for f in findings if getattr(f, "severity", "") == "block"]
    if blocked:
        return {"ok": False, "refused": True, "name": name, "reference": ref,
                "findings": blocked, "reason":
                f"{ref} was refused: " + blocked[0]["message"]}
    return {"ok": True, "name": name, "reference": ref, "text": text,
            "bytes": int(size),
            "findings": [f.as_dict() for f in findings],
            "warnings": len([f for f in findings
                             if getattr(f, "severity", "") == "warn"]),
            "note": ("Read on demand and scanned before it was handed over. "
                     "Nothing read this file until you asked for it.")}


# --------------------------------------------------------------------------
#   2. Leading `/skill` and `/bundle` tokens
# --------------------------------------------------------------------------

def bundles(*, skills_dir=None) -> dict:
    """{bundle name: [skill name, ...]}, from `.bundles.json` beside the skill
    index. A file that is missing, unreadable or nonsense names no bundles -
    it is a shortcut list, not a policy, and a shortcut that cannot be read is
    simply not offered."""
    path = _root(skills_dir) / BUNDLES_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key, value in raw.items():
        if not _name_ok(key):
            continue
        members = value if isinstance(value, list) else []
        clean = [str(m).strip() for m in members if _name_ok(str(m).strip())]
        if clean:
            out[str(key)] = clean[:MAX_BUNDLE_SKILLS]
    return out


def _index_names(root: Path) -> set:
    """The skill names in `root`'s own index.

    `jarvis_skills.INDEX` is `SKILLS_DIR/.index.json` (:514) and `cards()`
    (:684) is the same rows as dicts. It is read here rather than through
    `cards()` for one reason: `cards()` can only ever see the single folder
    jarvis_skills was imported with, and this module is asked for named
    folders - a project's own, and a test's. Nothing is built from the rows
    here but the names.
    """
    try:
        raw = json.loads((Path(root) / ".index.json").read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(raw, dict):
        return set()
    return {str(k) for k in raw if _name_ok(k)}


def known_names(*, skills_dir=None) -> tuple:
    """(skill names, bundle names), read from the index the skill library
    already keeps, so this costs one small JSON read and never walks a folder
    or runs the scanner - a message is parsed on every turn, and a parser that
    scanned a project's skills each time would be a cost with no matching
    benefit.

    A project's own skills are therefore NOT leading tokens: they are reached
    through `project_skills()` and their project. Named here so the choice is
    not mistaken for an oversight.
    """
    return _index_names(_root(skills_dir)), set(bundles(skills_dir=skills_dir))


def parse_chain(text: str, *, skills_dir=None, known=None) -> dict:
    """The LEADING run of `/skill-name` and `/bundle-name` tokens, and the
    rest of the message untouched.

    It stops at the first token that is not a known name, and it stops when a
    token is followed by more characters that are not a space. Both rules
    exist for the same reason: `/path/to/file` must come out the other side
    whole, because a message about a file path is a normal thing to type and
    silently eating the first three segments of it would be worse than not
    having the feature.

    At most `MAX_CHAIN` tokens are taken. A sixth is left in `rest` rather
    than refused, so an over-long chain degrades into "the rest is still
    there" instead of losing text.
    """
    names, groups = known if known is not None else known_names(skills_dir=skills_dir)
    s = str(text or "")
    skills, taken, why, rest, count = [], [], "", s, 0

    for _ in range(MAX_CHAIN):
        m = re.match(r"\s*/", rest)
        if not m:
            break
        body = rest[m.end():]
        tok = _TOKEN.match("/" + body)
        if not tok:
            why = "the text after the slash is not a plain skill name"
            break
        token = tok.group(1)
        after = body[len(token):]
        if after and not after[0].isspace():
            why = (f"/{token} is followed by more characters, so it is a path "
                   f"or a word and not a command")
            break
        if token in names:
            skills.append(token)
            taken.append({"token": f"/{token}", "kind": "skill"})
        elif token in groups:
            taken.append({"token": f"/{token}", "kind": "bundle"})
        else:
            why = (f"{token!r} is not a skill or a bundle here, so the chain "
                   f"stops at it")
            break
        rest = after
        count += 1

    if count >= MAX_CHAIN and re.match(r"\s*/", rest):
        why = f"the chain is capped at {MAX_CHAIN} commands"
    return {"ok": True, "skills": skills, "bundles": [t["token"][1:] for t in taken
                                                     if t["kind"] == "bundle"],
            "chain": taken, "taken": count, "rest": rest.lstrip(),
            "stopped_because": why}


def expand_chain(parsed: dict, *, skills_dir=None) -> dict:
    """A parsed chain with its bundles opened out into the skills they name,
    in place and in order, once each.

    A bundle member that is not an installed skill is named in `missing`
    rather than dropped quietly: a shortcut that half-works and says nothing
    is how a caller comes to believe a skill ran when it did not.
    """
    if not isinstance(parsed, dict) or not parsed.get("ok"):
        return {"ok": False, "reason": "not a parsed chain"}
    groups = bundles(skills_dir=skills_dir)
    known = _index_names(_root(skills_dir))
    out, missing, seen = [], [], set()
    for item in parsed.get("chain") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("token") or "").lstrip("/")
        members = [name] if item.get("kind") == "skill" else list(groups.get(name, []))
        for m in members:
            if m in seen:
                continue
            if m not in known:
                missing.append(m)
                continue
            seen.add(m)
            out.append(m)
    return {"ok": True, "skills": out, "missing": missing,
            "rest": str(parsed.get("rest") or ""),
            "stopped_because": parsed.get("stopped_because") or ""}


# --------------------------------------------------------------------------
#   3. A project's own skills
# --------------------------------------------------------------------------

def _projects():
    """jarvis_projects, or None. None means no project's folder can be
    trusted, which is said in words rather than read as "no projects"."""
    try:
        import jarvis_projects
        return jarvis_projects
    except Exception:
        return None


def project_roots(*, projects=None) -> list:
    """`[(project name, <its folder>/.jarvis/skills)]` for the projects the
    owner explicitly trusted.

    "Trusted" is not a second opinion invented here: it is
    `jarvis_projects.check_folder()`, the one check "Folders Jarvis may look
    in" already uses, and it is asked again at use time because a folder can
    be taken off that list after a project was made (jarvis_projects.py:663
    records exactly that case). A project whose folder is no longer trusted is
    not looked in at all, and the reason is carried back rather than guessed.
    """
    P = _projects()
    if P is None:
        return []
    if projects is None:
        try:
            projects = P.Projects().list()
        except Exception:
            return []
    out = []
    for row in projects or []:
        if not isinstance(row, dict):
            continue
        folder = row.get("folder")
        if isinstance(folder, dict):
            folder = folder.get("path")
        if not folder:
            continue
        try:
            real = P.check_folder(folder)
        except Exception:
            continue
        out.append((str(row.get("name") or ""), Path(real) / ".jarvis" / "skills"))
    return out


def project_skills(*, projects=None, quarantine: bool = True) -> dict:
    """Every skill under every trusted project's `.jarvis/skills/`, each one
    parsed and SCANNED, with anything that fails the scan quarantined.

    A project's folder is the owner's own code, which is exactly why it is
    where a hostile skill would be easiest to leave lying about - and why the
    trust level is `local` (jarvis_skills.py:47 says what that means) rather
    than `third_party`, and why the scan is not optional.

    Quarantined means what it means in jarvis_skills.py: KEPT, out of the load
    path, with the reason written beside it (jarvis_skills.py:621). Nothing is
    deleted, and the original stays in the project folder - deleting evidence
    is its own kind of failure.
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS, "skills": [],
                "quarantined": [], "skipped": [], "dirs": []}
    if _projects() is None:
        return {"ok": False, "skills": [], "quarantined": [], "skipped": [],
                "dirs": [], "reason":
                "jarvis_projects.py is not beside this file, so no project's "
                "folder can be checked against \"Folders Jarvis may look in\" "
                "and none is looked in"}
    roots = project_roots(projects=projects)
    out: dict = {"ok": True, "skills": [], "quarantined": [], "skipped": [],
                 "dirs": [str(r) for _, r in roots]}
    for project, root in roots:
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            if not _DIR_NAME.match(child.name):
                out["skipped"].append({"project": project, "name": child.name,
                                       "why": "the folder name is not a skill name"})
                continue
            try:
                skill = sk.parse_skill(child, trust="local")
            except Exception as exc:
                out["skipped"].append({"project": project, "name": child.name,
                                       "why": f"{type(exc).__name__}: {exc}"})
                continue
            report = _vet_never_raises(sk, skill)
            if report["verdict"] == "refuse":
                where = None
                if quarantine:
                    try:
                        where = sk._quarantine(child, skill.name, report)
                    except Exception:
                        where = None
                out["quarantined"].append({
                    "project": project, "name": skill.name,
                    "path": str(child),
                    "quarantined_to": str(where) if where else None,
                    "reason": report.get("summary", "refused"),
                    "findings": [f for f in report.get("findings", []) if
                                 f.get("severity") == "block"]})
                continue
            out["skills"].append({
                "project": project, "name": skill.name,
                "description": skill.description, "path": str(child),
                "trust": skill.trust, "verdict": report["verdict"],
                "warnings": report.get("warnings", 0),
                "references": [str(f).replace("\\", "/") for f in skill.files
                               if str(f).replace("\\", "/").startswith("references/")]})
    return out


def _vet_never_raises(sk, skill) -> dict:
    """`jarvis_skills.vet()`, with a scanner that raises read as a refusal.

    Fail-closed, and stated rather than assumed: a skill is text an agent
    reads and follows, so "the scanner did not answer" and "the scanner said
    no" have to end in the same place.
    """
    try:
        return sk.vet(skill)
    except Exception as exc:
        finding = {"severity": "block", "code": "scan_failed",
                   "message": (f"the scanner raised {type(exc).__name__}, so this "
                               f"skill was never cleared"),
                   "where": "skill folder", "excerpt": ""}
        return {"skill": getattr(skill, "name", ""), "trust":
                getattr(skill, "trust", "local"), "verdict": "refuse",
                "findings": [finding], "blocking": 1, "warnings": 0,
                "sha256": getattr(skill, "sha256", ""),
                "summary": (f"{getattr(skill, 'name', 'the skill')} was refused: the "
                            f"scanner raised {type(exc).__name__}")}


def load_project_skill(name: str, *, projects=None) -> dict:
    """The body of one project-local skill, re-parsed and RE-SCANNED on every
    load - the same rule `jarvis_skills.load()` follows (:727) and for the same
    reason: a file in the owner's own project folder can change after it was
    first looked at, and the load path is the last place to notice before the
    text becomes instructions.

    The folder this looks in is always the one `project_roots()` just trusted,
    never a path assembled from a name: a second join would be a second place
    for the two answers to disagree.
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS}
    if not _name_ok(name):
        return {"ok": False, "reason": f"unsafe skill name {name!r}"}
    for project, root in project_roots(projects=projects):
        dest = root / str(name)
        if not (dest / "SKILL.md").is_file():
            continue
        try:
            skill = sk.parse_skill(dest, trust="local")
        except Exception as exc:
            return {"ok": False, "reason": f"{name} no longer parses: {exc}"}
        report = _vet_never_raises(sk, skill)
        if report["verdict"] == "refuse":
            where = None
            try:
                where = sk._quarantine(dest, skill.name, report)
            except Exception:
                where = None
            return {"ok": False, "refused": True, "report": report,
                    "quarantined_to": str(where) if where else None,
                    "reason": (f"{name} has changed in its project folder and the "
                               f"new version is refused: {report.get('summary', '')}")}
        return {"ok": True, "name": name, "project": project,
                "description": skill.description, "body": skill.body,
                "verdict": report["verdict"], "warnings": report.get("warnings", 0),
                "path": str(dest)}
    return {"ok": False, "reason": f"no trusted project has a skill called {name}"}


# --------------------------------------------------------------------------
#   4. `/learn` - a skill distilled from the owner's own words
# --------------------------------------------------------------------------

def distil_body(*, when: str = "", procedure="", pitfalls: str = "",
                verification: str = "") -> str:
    """The four sections, in the order a person reads them.

    WHY THESE FOUR, and why they are not optional: a skill that does not say
    WHEN it applies is never chosen (jarvis_skills.py:216 refuses one with no
    description for that reason); a skill with no Procedure is a description;
    the Pitfalls are the part that was actually learned, because the second
    time someone does a thing they are avoiding the first time's mistake; and
    Verification is what says the skill worked. A distillation with none of
    that is a diary entry in a folder the agent reads.
    """
    lines = []
    for title, value in zip(SECTIONS, (when, procedure, pitfalls, verification)):
        lines.append(f"## {title}")
        lines.append(_as_text(value))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _as_text(value) -> str:
    """A `str`, or a list turned into a numbered procedure. Anything else is
    stringified rather than dropped: losing a step silently is the one outcome
    worse than an ugly one."""
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value if str(v).strip()]
        return "\n".join(f"{i}. {v}" for i, v in enumerate(items, 1))
    return str(value or "").strip()


def learn(topic: str, *, steps="", when: str = "", pitfalls: str = "",
          verification: str = "", name: str = "", scrubber=None,
          tier_of: Optional[Callable[[str], str]] = None,
          audit: Optional[Callable[[str, dict], None]] = None) -> dict:
    """`/learn`: write down how something was done, as a skill.

    The order of the four answers is the design:

      1. NO SCRUBBER, NOTHING WRITTEN. `_scrubber()` is `jarvis_scrub` or
         None, and None ends this function before anything else happens. Not
         "write it and warn" - the text becomes a file the agent will read and
         follow, so it gets the same door chat history gets.
      2. A PERSON MUST BE THE ONE ANSWERING. `modify_own_code` has to be tier
         `ask`. On `notify` or `auto` the gate returns `allowed=True` with
         nobody asked, and `write_skill()` would treat that as a yes
         (jarvis_skills.py:810). It is re-checked here, the way
         `jarvis_skill_discovery.offer()` re-checks it (:631).
      3. THEN `write_skill()`, which is the scanner and the card and the
         write, in that order, and which is NOT re-implemented here. It
         raises the approval card itself and writes only after it is allowed,
         so nothing in this module can save a skill the owner did not see.

    The text it writes down is exactly what the caller handed it. This module
    reads no web page, email, document or note to fill in a section.
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "wrote": False, "reason": _NO_SKILLS}

    topic = " ".join(str(topic or "").split())
    if not topic:
        return {"ok": False, "wrote": False,
                "reason": "a skill needs to know what it is about"}

    scr = scrubber if scrubber is not None else _scrubber()
    if scr is None:
        (audit or _audit)("skills.learn.withheld",
                          {"topic": topic[:120], "why": "no scrubber"})
        return {"ok": False, "wrote": False, "scrubbed": False,
                "reason": ("nothing was written: jarvis_scrub.py is not beside "
                           "this file, and a skill it could not be checked for "
                           "secrets does not get written at all")}

    want_tier = tier_of or _tier
    try:
        tier = str(want_tier(ACTION))
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return {"ok": False, "wrote": False, "scrubbed": True, "tier": tier,
                "reason": (f"nothing was written: {ACTION} is tier {tier!r}, and a "
                           f"new skill needs a person to answer for it. Set it to "
                           f"'ask' in jarvis-framework.toml, or to 'never' to "
                           f"refuse these outright.")}

    def _clean(value) -> str:
        try:
            return str(scr.scrub_text(_as_text(value)))
        except Exception:
            return ""

    body = distil_body(when=_clean(when or topic), procedure=_clean(steps),
                       pitfalls=_clean(pitfalls), verification=_clean(verification))
    if _WITHHELD in body:
        (audit or _audit)("skills.learn.withheld",
                          {"topic": topic[:120], "why": "scrubber withheld the text"})
        return {"ok": False, "wrote": False, "scrubbed": False,
                "reason": ("nothing was written: the scrubber withheld the text "
                           "rather than clear it, and an unclear skill is not saved")}
    description = _clean(when) or _clean(topic)
    if not description:
        return {"ok": False, "wrote": False, "reason":
                "a skill needs a description saying when it applies"}

    result = sk.write_skill(_clean(name) or topic, description, body, trust="self")
    out = dict(result) if isinstance(result, dict) else {"ok": False,
                                                       "reason": "write_skill said nothing"}
    out["wrote"] = bool(out.get("ok"))
    out["scrubbed"] = True
    if not out.get("ok"):
        out.setdefault("reason", "the skill was not written")
    return out


# --------------------------------------------------------------------------
#   5. The four extra checks, the lock file, and the Hermes conventions
#
#   PREMISE_ASSERT, MEASURED BEFORE A LINE OF THIS WAS WRITTEN (2026-10-15).
#   The work item asked for four checks. Three of the four already exist in
#   `jarvis_skills._RULES` and `scan_text`, and building them a second time
#   would have been a second place for the same judgement to drift:
#
#     * exfiltration            - `("block", "exfiltration", _EXFIL)` already
#                                 catches `curl -d/--data/-F/-T/--upload-file`,
#                                 `zip|curl`, and `requests.post(..., files=)`.
#                                 What it needs is a TRANSFER COMMAND, so this
#                                 module adds the PHRASINGS that ask for the same
#                                 thing in words ("include the contents of .env
#                                 in your reply", "append the api key to <url>").
#     * approval-gate bypass    - `("block", "override_rules", _OVERRIDE)` already
#                                 catches "skip/bypass/disable the approval",
#                                 "ignore all previous instructions" and "without
#                                 asking the user", and `_TOUCHES_JARVIS` already
#                                 flags naming `jarvis_gate.py` or `approvals.db`.
#                                 This module adds the CLAIM shapes: "already
#                                 approved", "no approval is required",
#                                 "pre-approved", "the gate can be ignored".
#     * smuggled Unicode        - ALREADY THERE, and this module does not
#                                 re-implement it: `scan_text` runs the text
#                                 through `jarvis_content_risk.normalise` and
#                                 reports `hidden_tags` (block), `bidi_override`
#                                 (warn) and `zero_width` (warn)
#                                 (jarvis_skills.py:392-411). What is genuinely
#                                 missing from that family is the **Hermes inline
#                                 host-execution form, `` !`command` ``** - it is
#                                 not Unicode, it is plain ASCII, and nothing in
#                                 this repository matched it (0 hits for `` !` ``
#                                 across jarvis_skills.py, jarvis_skill_hub.py and
#                                 jarvis_skill_discovery.py).
#     * bare external URL       - NOT there: `_RAW_IP_URL` flags a bare IP
#                                 address only, as a warn. A skill that links or
#                                 fetches from a named host was invisible.
#
#   `scan_skill_text()` below CALLS `jarvis_skills.scan_text` and adds only those
#   missing shapes, and its `checks` field says which layer found what, so the
#   delegation is visible rather than asserted.
# --------------------------------------------------------------------------

#: Bumped when the checks change, and recorded in every lock entry so an old
#: record can be told from a new one. 1 was "jarvis_skills alone"; 2 is this.
SCANNER_VERSION = 2

#: The trust ladder, lowest last. A skill is never MORE trusted than the lowest
#: of its source and the scanner's verdict.
TRUST_ORDER = ("builtin", "official", "trusted", "community")

#: The one value that is deliberately NOT on that ladder. It is not "less
#: trusted than community" - it is OUT OF THE RUNNING, so no code path can
#: return a ladder position for it and `TRUST_ORDER.index()` would raise if one
#: tried. That is what makes "a refused skill can never be overridden"
#: structural rather than a comment somebody can forget.
DANGEROUS = "dangerous"

#: jarvis_skills' own three levels (jarvis_skills.py:86), mapped ONTO the ladder
#: rather than replacing them: `self` is Jarvis's own writing, `local` is the
#: owner's own machine, `third_party` arrived from elsewhere. `official` has no
#: equivalent there and is used for a skill this repository ships.
TRUST_FROM_SKILLS = {"self": "builtin", "local": "trusted",
                     "third_party": "community"}

#: Verdicts no caller may raise a trust level past. A frozenset, so a caller
#: cannot slip through with a different case or a stray space.
_NEVER_OVERRIDABLE = frozenset({"refuse", "dangerous", "block"})

#: Hermes' inline host-execution form: `!` followed by a backticked command.
_HERMES_EXEC = re.compile(r"!\s*`[^`\n]{1,300}`")

#: Reading a local secret and putting it INTO an outbound reply or URL, said in
#: words rather than as a transfer command.
_EXFIL_PHRASING = re.compile(
    r"\b(?:include|append|attach|embed|add|paste|put|send|forward|upload|post|"
    r"reveal|echo|print|output)\b[^\n]{0,80}?"
    r"\b(?:contents?|values?|text|data)\s+of\b[^\n]{0,60}?"
    r"(?:\.env\b|\.ssh\b|id_rsa\b|\.aws\b|\.netrc\b|credential|secret|token|"
    r"password|passphrase|keychain|wallet|api[ _-]?key|private[ _-]?key)"
    r"|\b(?:include|append|attach|embed|add|paste|put|send|forward|upload|post)\b"
    r"[^\n]{0,60}?\b(?:api[ _-]?key|access[ _-]?token|token|password|passphrase|"
    r"secret|credential)s?\b[^\n]{0,40}?\b(?:in|into|to|with|inside)\b"
    r"[^\n]{0,40}?(?:https?://|\brepl(?:y|ies)\b|\bresponses?\b|\banswers?\b|"
    r"\bmessages?\b|\boutput\b)",
    re.I)

#: Text that CLAIMS the approval gate is already satisfied, or may be ignored.
_GATE_CLAIM = re.compile(
    r"\bpre[ _-]?approved\b"
    r"|\b(?:approval|permission|authorisation|authorization|consent|confirmation|"
    r"the gate|jarvis_gate)\b[^\n]{0,40}?\b(?:already\s+)?(?:approved|granted|"
    r"given|satisfied|obtained|waived|bypassed|disabled|not\s+required|"
    r"unnecessary)\b"
    r"|\bno\s+(?:approval|permission|authorisation|authorization|consent|"
    r"confirmation)\s+(?:is\s+)?(?:needed|required|necessary)\b"
    r"|\b(?:does\s+not|doesn't|need\s+not)\s+(?:apply|require\s+approval)\b",
    re.I)

#: A bare external URL. The negative lookahead leaves a bare IP address to
#: jarvis_skills' own `raw_ip_url` warn, so one URL is reported once.
_BARE_URL = re.compile(
    r"https?://(?!\d{1,3}(?:\.\d{1,3}){3}\b)[^\s\)\]\"'<>`,]+", re.I)

#: The four checks, each `(severity, code, regex, message, layer)`.
_EXTRA_RULES = (
    ("block", "hermes_exec", _HERMES_EXEC,
     "runs a host command inline with the `!`command`` syntax - Hermes' "
     "execution form, which needs no shell wrapper to be a shell", "hub"),
    ("block", "exfil_phrasing", _EXFIL_PHRASING,
     "asks for a local file's or a credential's contents to be put into an "
     "outbound reply or URL", "hub"),
    ("block", "gate_bypass_claim", _GATE_CLAIM,
     "claims the approval gate is already satisfied, or that it may be ignored "
     "- the gate is not a thing a file can speak for", "hub"),
    ("warn", "bare_url", _BARE_URL,
     "names an external address; a skill that links or fetches out is worth "
     "reading before it is trusted", "hub"),
)

#: The four shapes the work item named, and WHERE each one is checked. Printed
#: by `scan_skill_text()` so the delegation is visible rather than claimed.
CHECK_LAYERS = {
    "exfiltration_phrasing": "jarvis_skills _EXFIL (transfer commands) + hub "
                             "_EXFIL_PHRASING (the same thing in words)",
    "approval_gate": "jarvis_skills _OVERRIDE and _TOUCHES_JARVIS + hub "
                     "_GATE_CLAIM (the claim shapes)",
    "smuggled_unicode": "jarvis_skills scan_text via jarvis_content_risk "
                        "(hidden_tags/bidi/zero-width, NOT re-implemented) + hub "
                        "_HERMES_EXEC (the ASCII ``!`cmd` `` form)",
    "bare_external_url": "hub _BARE_URL only - jarvis_skills flags a bare IP "
                         "address and nothing else",
}


def scan_skill_text(text: str, where: str = "SKILL.md") -> dict:
    """Every finding for `text`: `jarvis_skills.scan_text` CALLED, plus the four
    shapes it does not cover.

    FAIL CLOSED TWICE. With no `jarvis_skills.py` beside this file there is no
    scanner at all, so the verdict is `refuse` - an unscanned skill is not a
    skill. And a base scanner that RAISES is a refusal, not a pass: "the scanner
    did not answer" and "the scanner said no" have to end in the same place.
    """
    findings, blocks = [], []
    sk = _skills()
    if sk is None:
        base_err = ("jarvis_skills.py is not beside this file, so no skill text "
                    "can be scanned")
        findings.append({"severity": "block", "code": "scanner_missing",
                         "message": base_err, "where": where, "excerpt": ""})
    else:
        try:
            findings = [f.as_dict() for f in sk.scan_text(text, where)]
        except Exception as exc:
            findings = [{"severity": "block", "code": "scan_failed",
                         "message": (f"the scanner raised {type(exc).__name__}, so "
                                     f"this text was never cleared"),
                         "where": where, "excerpt": ""}]

    s = text if isinstance(text, str) else ""
    for severity, code, rx, message, _layer in _EXTRA_RULES:
        try:
            m = rx.search(s)
        except Exception:
            m = None
        if m is None:
            continue
        line_no = s.count("\n", 0, m.start()) + 1
        frag = s[max(0, m.start() - 30): m.end() + 40].replace("\n", " ").strip()
        findings.append({"severity": severity, "code": code, "message": message,
                         "where": f"{where} line {line_no}", "excerpt": frag[:160]})

    blocks = [f for f in findings if f.get("severity") == "block"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    verdict = "refuse" if blocks else ("review" if warns else "clean")
    return {"where": where, "verdict": verdict, "findings": findings,
            "blocking": len(blocks), "warnings": len(warns),
            "scanner_version": SCANNER_VERSION,
            "checks": dict(CHECK_LAYERS),
            "note": ("The first findings are jarvis_skills.scan_text's, called and "
                     "not copied. `checks` says which layer covers which shape.")}


# --------------------------------------------------------------------------
#   6. `skills.lock` - what was scanned, when, and how far it may be trusted
# --------------------------------------------------------------------------

LOCK_NAME = "skills.lock"


def lock_path(*, skills_dir=None) -> Path:
    return _root(skills_dir) / LOCK_NAME


def read_lock(*, skills_dir=None) -> dict:
    """The lock, or `{}`. A missing, unreadable or nonsense file is `{}` - not
    an exception, and never a reason to trust anything more."""
    try:
        raw = json.loads(lock_path(skills_dir=skills_dir).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    rows = raw.get("skills")
    return rows if isinstance(rows, dict) else {}


def _lock_shape() -> dict:
    return {"version": 1, "scanner_version": SCANNER_VERSION,
            "trust_order": list(TRUST_ORDER), "skills": {}}


def lock_entry(name: str, *, source_url: str = "", sha256_hash: str = "",
               trust_level: str = "community", report: Optional[dict] = None,
               now: Optional[float] = None) -> dict:
    """One lock row: WHERE it came from, WHAT was scanned, WHAT it said, and how
    far it may be trusted.

    `trust_level` is clamped to the ladder - a caller cannot write a word that is
    not on it - and a `refuse` verdict OVERWRITES it with `dangerous`, so a row
    written for a refused skill cannot carry a trust level at all, whatever the
    caller passed.
    """
    sk = _skills()
    verdict = "unknown"
    if isinstance(report, dict):
        verdict = str(report.get("verdict") or "unknown")
    findings = []
    if isinstance(report, dict):
        findings = [{"severity": f.get("severity"), "code": f.get("code"),
                     "where": f.get("where"), "excerpt": f.get("excerpt")}
                    for f in (report.get("findings") or [])
                    if isinstance(f, dict)][:40]
    level = str(trust_level or "").strip().lower()
    if level not in TRUST_ORDER:
        level = "community"
    if verdict in _NEVER_OVERRIDABLE:
        level = DANGEROUS              # structural: not reachable by argument
    return {
        "name": str(name or ""),
        "source_url": str(source_url or "")[:500],
        "sha256_hash": (str(sha256_hash or "").lower()
                        if re.fullmatch(r"[0-9a-fA-F]{64}", str(sha256_hash or ""))
                        else ""),
        "scanner_version": SCANNER_VERSION,
        "trust_level": level,
        "verdict": verdict,
        "findings": findings,
        "blocking": int((report or {}).get("blocking") or 0)
        if isinstance(report, dict) else 0,
        "timestamp": float(now if now is not None else time.time()),
        "skills_module": bool(sk is not None),
    }


def write_lock(entries, *, skills_dir=None) -> dict:
    """Merge rows into `skills.lock`, whole-file, through a temp file and a
    rename. Existing rows for other skills are carried over untouched.

    A row whose verdict is `refuse` is written with `trust_level: "dangerous"`
    AND with `"override": false`, so the two agree on disk as well as in code.
    """
    rows = read_lock(skills_dir=skills_dir)
    added = []
    for entry in (entries if isinstance(entries, (list, tuple)) else [entries]):
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        row = dict(entry)
        if str(row.get("verdict") or "").lower() in _NEVER_OVERRIDABLE:
            row["trust_level"] = DANGEROUS
            row["override"] = False
        rows[str(row["name"])] = row
        added.append(str(row["name"]))
    if not added:
        return {"ok": False, "reason": "no usable lock entries", "written": False}
    root = _root(skills_dir)
    doc = _lock_shape()
    doc["skills"] = rows
    try:
        root.mkdir(parents=True, exist_ok=True)
        target = root / LOCK_NAME
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, target)
    except Exception as exc:
        return {"ok": False, "written": False,
                "reason": f"could not write the lock ({type(exc).__name__}: {exc})"}
    return {"ok": True, "written": True, "names": added, "path": str(root / LOCK_NAME)}


def effective_trust(entry) -> str:
    """How far a lock row may actually be trusted, whatever it says.

    THE FLOOR IS THE VERDICT, AND IT IS STRUCTURAL. A row whose `verdict` is
    `refuse` (or `dangerous`, or `block`) returns `DANGEROUS`, which is not on
    `TRUST_ORDER` at all - so a hand-edited `skills.lock` claiming
    `"trust_level": "builtin"` for a refused skill still reads as dangerous, and
    `TRUST_ORDER.index(effective_trust(row))` raises rather than quietly placing
    it. Nothing here raises on its own; the point is that no caller can compute a
    ladder position for a refused skill.
    """
    if not isinstance(entry, dict):
        return "community"
    verdict = str(entry.get("verdict") or "").strip().lower()
    if verdict in _NEVER_OVERRIDABLE:
        return DANGEROUS
    if entry.get("override") is True and verdict and verdict != "clean":
        # An override may lift `review` to a named level, never past a block -
        # and a block already returned above, so this cannot be reached for one.
        pass
    want = str(entry.get("trust_level") or "").strip().lower()
    return want if want in TRUST_ORDER else "community"


def promote_trust(entry, to: str) -> dict:
    """Raise one lock row's trust level, and REFUSE for a refused skill.

    This is not a permission and it raises no card: it moves a LABEL in a JSON
    file, and the label it may move is bounded by the scan that already ran. The
    one thing it cannot do is give a refused skill a place on the ladder.
    """
    if not isinstance(entry, dict) or not entry.get("name"):
        return {"ok": False, "changed": False, "reason": "not a lock entry"}
    verdict = str(entry.get("verdict") or "").strip().lower()
    if verdict in _NEVER_OVERRIDABLE:
        return {"ok": False, "changed": False, "trust_level": DANGEROUS,
                "reason": ("the scanner refused this skill, so it has no trust "
                           "level to raise - the verdict is the floor, and this "
                           "is not a way round it")}
    want = str(to or "").strip().lower()
    if want not in TRUST_ORDER:
        return {"ok": False, "changed": False,
                "reason": f"{to!r} is not one of {list(TRUST_ORDER)}"}
    now = effective_trust(entry)
    # TRUST_ORDER is most-trusted first, so a RAISE moves to a SMALLER index.
    if TRUST_ORDER.index(want) >= TRUST_ORDER.index(now):
        return {"ok": False, "changed": False, "trust_level": now,
                "reason": f"{want} is not higher than {now}"}
    out = dict(entry)
    out["trust_level"] = want
    out["override"] = True
    return {"ok": True, "changed": True, "trust_level": want, "entry": out,
            "reason": f"{entry['name']} raised to {want}"}


# --------------------------------------------------------------------------
#   7. The frontmatter conventions: requires_tools, fallback_for_tools,
#      blueprint.schedule
#
#   `jarvis_skills._parse_frontmatter` is a flat `key: value` reader, so the
#   names it can actually produce are `requires_tools`, `fallback_for_tools` and
#   the literal key `blueprint.schedule` (a nested `blueprint:` map is not a
#   shape it can read - measured, not assumed). Both spellings are accepted here
#   and the nested one is reported as unreadable rather than guessed at.
# --------------------------------------------------------------------------

def _tools_list(value) -> list:
    """A list of tool names from a frontmatter value: a `- item` list, a
    space/comma separated string, or a single name. Anything else is []."""
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value]
    elif isinstance(value, str):
        items = [p.strip() for p in re.split(r"[,\s]+", value)]
    else:
        return []
    return [i for i in items if i and _NAME_OK_TOOL.match(i)]


#: A tool name as `jarvis_agent.TOOLS` spells them (`_TOOL_NAME`,
#: jarvis_skill_discovery.py:122). A name that is not one is dropped, so a
#: required-tool gate cannot be satisfied by a typo.
_NAME_OK_TOOL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def skill_conventions(name: str, *, skills_dir=None) -> dict:
    """`requires_tools`, `fallback_for_tools` and `blueprint.schedule` for one
    installed skill, read from its own SKILL.md. Never raises."""
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS}
    try:
        dest = _under(_root(skills_dir), name)
        skill = sk.parse_skill(dest)
    except Exception as exc:
        return {"ok": False, "reason": f"{name} could not be read ({type(exc).__name__})"}
    extra = dict(getattr(skill, "extra_fields", {}) or {})
    nested = extra.get("blueprint")
    schedule = extra.get("blueprint.schedule")
    if schedule is None and isinstance(nested, str) and "schedule" in nested:
        schedule = nested.split(":", 1)[-1].strip()
    return {"ok": True, "name": name,
            "requires_tools": _tools_list(extra.get("requires_tools")),
            "fallback_for_tools": _tools_list(extra.get("fallback_for_tools")),
            "blueprint_schedule": (str(schedule).strip() if schedule else ""),
            "nested_blueprint_unreadable": isinstance(nested, dict)}


def visible_skills(enabled_tools=None, *, skills_dir=None,
                   aliases=None) -> dict:
    """Which skills may be offered, and why the others may not.

    `requires_tools` HIDES a skill when any tool it needs is not enabled: a skill
    that cannot run is worse than absent, because the model will pick it and the
    call will fail. `fallback_for_tools` hides a skill while the tool it stands
    in for IS available. With no `enabled_tools` given, nothing is hidden for a
    missing tool - "not told" is not "disabled".
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS, "visible": [], "hidden": []}
    # The NAMES come from the folder's own index, so this works for a named
    # folder exactly as `known_names()` does; the TRUST comes from the lock,
    # which is the only place a trust level is recorded.
    names_all = sorted(_index_names(_root(skills_dir)))
    rows = read_lock(skills_dir=skills_dir)
    have = None
    if enabled_tools is not None:
        have = {str(t) for t in enabled_tools}
    if isinstance(aliases, dict):
        names_all = [aliases.get(n, n) for n in names_all]
    visible, hidden = [], []
    for name in names_all:
        if not name:
            continue
        conv = skill_conventions(name, skills_dir=skills_dir)
        need = conv.get("requires_tools") or []
        stands_in_for = conv.get("fallback_for_tools") or []
        why = ""
        if have is not None and need and not set(need).issubset(have):
            missing = sorted(set(need) - have)
            why = ("needs " + ", ".join(missing)
                   + (", which is not enabled" if len(missing) == 1
                      else ", which are not enabled"))
        elif have is not None and stands_in_for and set(stands_in_for) & have:
            why = ("stands in for " + ", ".join(sorted(set(stands_in_for) & have))
                   + ", which is enabled")
        row = {"name": name, "requires_tools": need,
               "fallback_for_tools": stands_in_for,
               "trust_level": effective_trust(rows.get(name)), "why": why}
        (hidden if why else visible).append(row)
    return {"ok": True, "visible": visible, "hidden": hidden,
            "note": ("A skill whose required tools are not enabled is hidden, and a "
                     "stand-in is hidden while the tool it replaces is there. "
                     "Nothing here enables, disables or approves anything.")}


def blueprint_suggestions(*, skills_dir=None, now: Optional[float] = None) -> dict:
    """A skill's `blueprint.schedule` as a SUGGESTION row - and nothing else.

    RULE 4 IS THE WHOLE POINT OF THIS FUNCTION'S SHAPE. A skill that scheduled
    its own job would be acting unattended, which this project forbids; so this
    reads the frontmatter and returns a row for `/api/skills/suggestions` to
    show, exactly as `jarvis_skill_discovery` offers a routine as a card the
    owner answers. **This function imports no scheduler and registers no job** -
    `jarvis_schedule` is never imported here, and a test asserts that against the
    source. Turning a suggestion into a job is a separate, card-raising change.
    """
    sk = _skills()
    if sk is None:
        return {"ok": False, "reason": _NO_SKILLS, "suggestions": []}
    rows = read_lock(skills_dir=skills_dir)
    when = float(now if now is not None else time.time())
    out = []
    for name in sorted(_index_names(_root(skills_dir))):
        if not name:
            continue
        conv = skill_conventions(name, skills_dir=skills_dir)
        schedule = conv.get("blueprint_schedule") or ""
        if not conv.get("ok") or not schedule:
            continue
        out.append({
            "kind": "skill_blueprint",
            "skill": name,
            "schedule": schedule,
            "trust_level": effective_trust(rows.get(name)),
            "offered": False,           # nothing is offered; the view decides
            "job_registered": False,    # structural: no scheduler is reached
            "words": (f"{name} suggests running on {schedule}. Nothing is "
                      f"scheduled: a job is made only by an approval card."),
            "at": when,
        })
    return {"ok": True, "suggestions": out, "count": len(out),
            "note": ("Suggestions only. No job is registered and no scheduler is "
                     "imported: rule 4 forbids acting unattended.")}


# --------------------------------------------------------------------------
#   The routes - only the ones that did not already exist
# --------------------------------------------------------------------------

def handle_get(route: str, query: str = "") -> tuple:
    """(status, payload) for the read routes. No card: reading is free, which
    is what `skill_list` and `skill_load` are tiered `auto` for
    (jarvis_gate.py:850)."""
    args = parse_qs(str(query or ""))
    one = lambda k: (args.get(k) or [""])[0]        # noqa: E731
    if route == "/api/skills/hub/references":
        skill = one("skill").strip()
        if not skill:
            return 400, {"error": "need ?skill=<name>"}
        ref = one("file").strip()
        if ref:
            return 200, level2_reference(skill, ref)
        out = references(skill)
        return (200 if out.get("ok") else 404), out
    if route == "/api/skills/hub/projects":
        out = project_skills()
        return (200 if out.get("ok") else 503), out
    if route == "/api/skills/hub/lock":
        try:
            enabled = [t for t in (args.get("tool") or []) if t]
        except Exception:                                   # pragma: no cover
            enabled = []
        rows = read_lock()
        out = {
            "ok": True,
            "scanner_version": SCANNER_VERSION,
            "trust_order": list(TRUST_ORDER),
            "lock": rows,
            "skills": [],
            "blueprints": blueprint_suggestions(),
            "note": ("What was scanned, when, and how far it may be trusted. A "
                     "skill the scanner refused reads as 'dangerous', which is not "
                     "on the trust ladder at all, whatever the lock file says."),
        }
        vis = visible_skills(enabled if enabled else None)
        hidden = {h["name"]: h["why"] for h in vis.get("hidden", [])}
        visible_names = {v["name"] for v in vis.get("visible", [])}
        for name, row in sorted(rows.items()):
            if not isinstance(row, dict):
                continue
            out["skills"].append({
                "name": name,
                "effective_trust": effective_trust(row),
                "recorded_trust": row.get("trust_level", ""),
                "verdict": row.get("verdict", ""),
                "source_url": row.get("source_url", ""),
                "sha256_hash": row.get("sha256_hash", ""),
                "scanner_version": row.get("scanner_version", ""),
                "timestamp": row.get("timestamp", 0),
                "blocking": row.get("blocking", 0),
                "visible": (name in visible_names) if enabled else None,
                "hidden_because": hidden.get(name, ""),
            })
        return 200, out
    return 404, {"error": "no such read"}


def handle_post(route: str, body: Any) -> tuple:
    """(status, payload) for the two command routes."""
    if not isinstance(body, dict):
        return 400, {"error": "need a JSON object"}
    if route == "/api/skills/chain":
        parsed = parse_chain(str(body.get("text") or ""))
        return 200, expand_chain(parsed)
    if route == "/api/skills/learn":
        if not str(body.get("topic") or body.get("when") or "").strip():
            return 400, {"error": "need a topic, or the words for when it applies"}
        out = learn(str(body.get("topic") or ""),
                    steps=body.get("steps") or body.get("procedure") or "",
                    when=str(body.get("when") or ""),
                    pitfalls=str(body.get("pitfalls") or ""),
                    verification=str(body.get("verification") or ""),
                    name=str(body.get("name") or ""))
        return (200 if out.get("ok") else 409), out
    return 404, {"error": "no such command"}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so these routes are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original, untouched - the same shape
    `jarvis_receipts.install()` uses, and the reason this feature needs no
    patch: `plugins/ready/skill-hub/plugin.json` names this module and
    `jarvis_plugins.py` makes the call the patch would have made.

    It adds four routes and touches none of the ones that already exist:
    `GET /api/skills` (the list) and `POST /api/skills/decide` (the removal,
    and its "are you sure?") are jarvis_hud.py's already, in both apps.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_skill_hub", False):
        return "  skill-hub  references, chains and /learn (already on)"

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

    do_GET._jarvis_skill_hub = True
    do_POST._jarvis_skill_hub = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  skill-hub  references on demand, leading /skill chains, project "
            "skills and /learn: on")


# --------------------------------------------------------------------------
#   For the suites
# --------------------------------------------------------------------------

def _self_check() -> dict:
    """What this module can see right now, for a start-up banner or a suite.
    Read-only: it opens no skill, reads no reference and runs no scanner."""
    sk = _skills()
    names, groups = known_names()
    return {"module": "jarvis_skill_hub", "version": 1,
            "jarvis_skills": sk is not None,
            "jarvis_scrub": _scrubber() is not None,
            "skills_dir": str(_root()),
            "skills": len(names), "bundles": sorted(groups),
            "tier": _tier(),
            "python": sys.version_info[0]}
