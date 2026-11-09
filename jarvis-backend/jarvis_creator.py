"""jarvis_creator.py - Creator mode: a waiting folder, a scan, and ONE card a
thing.

WHAT A CREATOR DOES, IN PLAIN WORDS

A creator makes a skill (a folder with `SKILL.md` in it: instructions the model
may read) or a plug-in (a folder with `plugin.json` in it: Python that runs
inside Jarvis when it starts). Creator mode is the small, boring path from
"it is in my folder" to "Jarvis has it":

  1. the creator puts the folder in ONE fixed waiting folder on this PC;
  2. the PC reads it and SCANS it - read only, nothing copied, nothing run,
     and it raises no card just for looking;
  3. the owner installs ONE item, which raises **ONE** approval card - the
     same `modify_own_code` card every other skill install raises. There is no
     "install all", no yes-to-all, and no second card behind the first;
  4. the item lands **turned off**. Installing is not enabling: the only way
     to switch it on is the ordinary ON control in Settings, which has its own
     scanner and its own card.

WHAT THIS MODULE DOES NOT DO

  * **It is not an auto-loader.** Nothing in the waiting folder ever runs. No
    watcher, no thread, no timer and no scheduler looks at it: the scan happens
    when the owner opens the Settings card (or presses "Look again"), and the
    install happens when they answer a card.
  * **It is not a marketplace.** There is no network source, no git, no URL, no
    index. The waiting folder is a folder on this PC.
  * **It is not a second scanner.** Skills are scanned and installed by
    `jarvis_packs.scan_source()` and `jarvis_packs.install_pack()` - the pack
    manager's own scanner and its own ONE card - which in turn call
    `jarvis_skills.vet()` and `jarvis_skills.install()`. This module only
    chooses WHICH folder to hand them, and it re-uses the pack manager's own
    refusal sentence for code.
  * **It installs no plug-ins in this slice.** A plug-in is code, and the pack
    manager refuses code before a card is ever drawn (`jarvis_packs.CODE_REFUSED`).
    Creator mode shows the plug-in, scans what it can see, and refuses it in
    the pack manager's own words - it does not invent a code-install path.
    That is the whole reason a plug-in folder is still worth staging: the
    owner sees it, and sees why it cannot go in yet.
  * **It is not a phone feature.** Both routes refuse any device but this PC
    (`jarvis_owner_check.from_this_pc`). A skill is instructions the model
    follows and a plug-in is code that runs beside it, so the screen that puts
    one in is where the files are. ARCHITECTURE section 8 records why.

WHERE THE WAITING FOLDER IS

`<config folder>/creator-incoming`, beside `skills/`, `skills-off/` and
`skills-quarantine/` - the same folder the rest of the skill machinery uses.
It is made when it is first needed, so the installer carries no empty folder
and no new deploy path. `JARVIS_CREATOR_INCOMING` overrides it, for the
suites.

Nothing here copies a file, deletes one, or writes inside that folder. The
ONLY write this module does is `mkdir` for the waiting folder itself.

Standard library only. No network, no subprocess, no import of the skill or
the plug-in it reads.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

#: The waiting folder's name, under the config folder.
STAGING_NAME = "creator-incoming"

#: Set this to put the waiting folder somewhere else. It exists for the suites
#: (a temp folder), the same way JARVIS_SKILLS_DIR does for skills.
STAGING_ENV = "JARVIS_CREATOR_INCOMING"

#: The manifest a skill folder must carry, and the one a plug-in folder must.
SKILL_MANIFEST = "SKILL.md"
PLUGIN_MANIFEST = "plugin.json"

#: How many waiting folders one read looks at. A view is a scan of every item,
#: so the bound is what keeps "open the card" from becoming a long job on a
#: folder someone filled with hundreds of things. Past it the answer says so.
MAX_ITEMS = 50

#: A folder name is a name, never a path. This is checked again after
#: resolving, so a junction or a strange name cannot point outside the folder.
_MAX_NAME = 100

#: The one sentence a plug-in refusal falls back to when `jarvis_packs` is not
#: beside this file (an older published base). The REAL sentence is imported
#: from `jarvis_packs.CODE_REFUSED` at call time, so the two can never drift:
#: this is only what a base without that constant can honestly say.
_NO_PACKS = ("this PC's Jarvis has no pack manager beside Creator mode, so "
             "code cannot be judged here and nothing was installed")


# --------------------------------------------------------------------------
#   Where the waiting folder is, read per call (a suite moves it)
# --------------------------------------------------------------------------

def _packs():
    """`jarvis_packs`, or None when an older base does not carry it."""
    try:
        import jarvis_packs
        return jarvis_packs
    except Exception:                                  # pragma: no cover
        return None


def _sk():
    """`jarvis_skills`, or None - the module the pack manager scans with."""
    try:
        import jarvis_skills
        return jarvis_skills
    except Exception:                                  # pragma: no cover
        return None


def staging_dir() -> Path:
    """The one waiting folder. Read per call, never captured at import.

    `JARVIS_CREATOR_INCOMING` wins when it is set; otherwise the folder sits
    beside the skills folder, so it follows `JARVIS_SKILLS_DIR` in a suite and
    the real config folder on the owner's PC.
    """
    named = str(os.environ.get(STAGING_ENV) or "").strip()
    if named:
        return Path(named)
    sk = _sk()
    if sk is not None:
        return Path(sk.SKILLS_DIR).parent / STAGING_NAME
    return Path(os.path.expanduser("~")) / ".openjarvis" / STAGING_NAME


def _ensure_staging() -> tuple:
    """(the folder, why it could not be made). Makes it at run time, once."""
    root = staging_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return root, (f"the waiting folder could not be made ({exc}), so there "
                      f"is nowhere to look for a skill or a plug-in")
    return root, ""


def _inside(root: Path, path: Path) -> bool:
    """True when `path` really is under `root` after resolution.

    The check that stops a name, a link or a junction from choosing a folder
    somewhere else on this PC.
    """
    try:
        root = Path(root).resolve()
        path = Path(path).resolve()
    except OSError:
        return False
    return path == root or root in path.parents


# --------------------------------------------------------------------------
#   One waiting item: which kind it is, and what the scanner says
# --------------------------------------------------------------------------

def _clean_name(value: Any) -> str:
    """A folder name in the waiting folder, or "" - never a path."""
    name = str(value or "").strip()
    if not name or len(name) > _MAX_NAME:
        return ""
    if name in (".", "..") or name.startswith("."):
        return ""
    if any(ch in name for ch in ("/", "\\", ":", "\0")):
        return ""
    return name


def _kind_of(folder: Path) -> tuple:
    """("skill" | "plugin" | "", why). The two manifests are the whole rule.

    A folder holding BOTH is refused rather than guessed at: it would otherwise
    be installed as one thing while the owner staged it as the other. A folder
    with neither is not something Creator mode can judge, so it sends the owner
    back to the two shapes it does know.
    """
    has_skill = (Path(folder) / SKILL_MANIFEST).is_file()
    has_plugin = (Path(folder) / PLUGIN_MANIFEST).is_file()
    if has_skill and has_plugin:
        return "", (f"that folder holds both a {SKILL_MANIFEST} and a "
                    f"{PLUGIN_MANIFEST}, so it is not clear which one it is - "
                    f"put the skill and the plug-in in two folders, and nothing "
                    f"was installed")
    if has_plugin:
        return "plugin", ""
    if has_skill:
        return "skill", ""
    return "", (f"that folder is not a skill (it has no {SKILL_MANIFEST}) and "
                f"not a plug-in (it has no {PLUGIN_MANIFEST}), so nothing can "
                f"be installed from it")


def _plugin_module(folder: Path) -> str:
    """The module name a plug-in's own manifest names, or "".

    Read as JSON with a plain parser, never imported and never run. A manifest
    that will not parse is not fatal to the refusal: the folder is still a
    plug-in, and code is still not installed here.
    """
    try:
        data = json.loads((Path(folder) / PLUGIN_MANIFEST).read_text("utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("module") or "").strip()


def _code_refusal(folder: Path) -> str:
    """The pack manager's own refusal sentence, with this folder's evidence.

    Two steps, and neither copies a scanner:

      1. the folder is handed to `jarvis_packs.scan_source()` - the pack
         manager's OWN pre-install scan - and when its scan refuses the folder
         because it holds code or a binary, ITS refusal is returned word for
         word (`jarvis_packs.py:924`, the `CODE_REFUSED` sentence);
      2. when the folder holds no file that can run (a plug-in folder is often
         just `plugin.json` plus a README, with the module copied in
         separately), the same `jarvis_packs.CODE_REFUSED` sentence is
         IMPORTED - not copied - and given this folder's own evidence: the
         module its manifest names.

    Either way the owner reads the pack manager's words, and the two doors
    cannot drift apart because there is one sentence, in one place. Nothing is
    imported or run to read the manifest.
    """
    packs = _packs()
    if packs is None:
        return _NO_PACKS
    report = None
    try:
        report = packs.scan_source(str(folder))
    except Exception:                                  # pragma: no cover
        report = None
    if isinstance(report, dict):
        has_code = bool((report.get("pack") or {}).get("has_code"))
        observed = report.get("observed") or {}
        if report.get("refusal") and (has_code or observed.get("code_files")
                                      or observed.get("binary_files")):
            return str(report["refusal"])
    template = getattr(packs, "CODE_REFUSED", "")
    module = _plugin_module(folder)
    where = (f"its {PLUGIN_MANIFEST}, which names the module {module!r} "
             f"that would run inside Jarvis at start-up" if module
             else f"its {PLUGIN_MANIFEST}, which adds a program that runs "
                  f"inside Jarvis at start-up")
    if not template:
        return _NO_PACKS
    try:
        return str(template).format(where=where)
    except Exception:                                  # pragma: no cover
        return _NO_PACKS


def _findings_of(report: dict, severity: str) -> list:
    """The scan report's own findings at one severity, kept as dicts."""
    out = []
    for item in (report or {}).get("findings") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("severity") or "") != severity:
            continue
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        out.append({"severity": severity,
                    "code": str(item.get("code") or ""),
                    "message": message,
                    "where": str(item.get("where") or "")})
    return out


def _installed_state(name: str) -> tuple:
    """(installed, state, where) from the pack ledger, for one skill name.

    The ledger is the pack manager's own record, read and never rewritten. A
    skill installed by the Skills screen's own door is not in it, so this says
    "not known" and the row is still offered - the install would then be the
    pack manager's own collision refusal, in its own words.
    """
    packs = _packs()
    if packs is None or not name:
        return False, "", ""
    try:
        rows = (packs.read_ledger() or {}).get("packs") or {}
    except Exception:                                  # pragma: no cover
        return False, "", ""
    entry = rows.get(name) if isinstance(rows, dict) else None
    if not isinstance(entry, dict):
        return False, "", ""
    state = str(entry.get("state") or "")
    if state not in ("installed", "disabled", "tampered"):
        return False, "", ""
    where = "turned off" if state == "disabled" else state
    return True, state, where


def scan_item(folder: Path) -> dict:
    """One waiting folder: its kind, its scan, and whether it can be installed.

    Reads only. Raises no card, copies nothing, runs nothing. The scan itself
    is `jarvis_packs.scan_source()` for a skill (the pack manager's full report,
    built on `jarvis_skills.vet()`), and the pack manager's own code refusal for
    a plug-in.
    """
    folder = Path(folder)
    kind, why = _kind_of(folder)
    row = {"name": folder.name, "kind": kind, "verdict": "malformed",
           "refused": True, "can_install": False, "summary": why,
           "reason": why, "findings": [], "blocking": 0, "warnings": 0,
           "installed": False, "state": "", "where": "", "sentence": why,
           "needs_warnings": False}
    if not kind:
        return row
    packs = _packs()
    if kind == "plugin":
        # Code is refused before a card, in the pack manager's own words. The
        # folder is still listed, so the owner sees it and sees why.
        reason = _code_refusal(folder)
        row.update({
            "verdict": "refuse", "refused": True, "can_install": False,
            "summary": ("A plug-in adds a program that runs inside Jarvis at "
                        "start-up. This first slice of Creator mode stages and "
                        "scans plug-ins and installs none of them."),
            "reason": reason,
            "findings": [{"severity": "block", "code": "code_refused",
                          "message": reason, "where": PLUGIN_MANIFEST}],
            "blocking": 1, "sentence": reason,
        })
        return row
    if packs is None:
        row.update({
            "verdict": "malformed", "refused": True, "can_install": False,
            "summary": ("This PC's Jarvis has no pack manager beside Creator "
                        "mode, so a skill cannot be scanned here."),
            "reason": row["summary"], "sentence": row["summary"],
        })
        return row
    try:
        report = packs.scan_source(str(folder))
    except Exception as exc:                           # pragma: no cover
        row.update({"reason": (f"the scanner could not read that folder "
                               f"({type(exc).__name__}), so nothing was "
                               f"installed"),
                    "summary": row["reason"], "sentence": row["reason"]})
        return row
    pack = report.get("pack") or {}
    verdict = str(report.get("verdict") or "malformed")
    refused = verdict in ("refuse", "malformed")
    name = str(pack.get("name") or "")
    installed, state, where = _installed_state(name)
    summary = str((report.get("observed") or {}).get("scanner", {}).get(
        "summary") or report.get("refusal") or "")
    row.update({
        "name": name or folder.name,
        "verdict": verdict,
        "refused": refused,
        "can_install": not refused,
        "summary": summary,
        "reason": str(report.get("refusal") or "") if refused else "",
        "findings": _findings_of(report, "block") + _findings_of(report, "warn"),
        "blocking": len(_findings_of(report, "block")),
        "warnings": len(_findings_of(report, "warn")),
        "needs_warnings": verdict == "review",
        "installed": installed,
        "state": state,
        "where": where,
        "sentence": ("Installed already and turned off - turn it on in the "
                     "list above when you want it." if state == "disabled"
                     else ("Installed already." if installed else "")),
        "files": len((report.get("digest") or {}).get("files") or []),
        "bytes": int(pack.get("bytes") or 0),
    })
    return row


# --------------------------------------------------------------------------
#   The read: what is waiting, scanned once
# --------------------------------------------------------------------------

def incoming() -> dict:
    """Everything in the waiting folder, scanned, in one read.

    Read only: it makes the waiting folder if it is not there (so the owner is
    always shown a path that exists), then scans each item and stops at
    `MAX_ITEMS`. Nothing is copied, moved, installed or enabled, and no card is
    raised. A folder the scanner refuses is still listed - that is the point of
    showing it - with `can_install` False.
    """
    root, why = _ensure_staging()
    if why:
        return {"ok": False, "available": False, "reason": why,
                "folder": str(root), "items": [], "counts": {}, "note": ""}
    items, stopped = [], False
    try:
        children = sorted((p for p in root.iterdir() if p.is_dir()
                           and not p.name.startswith(".")),
                          key=lambda p: p.name.lower())
    except OSError as exc:
        return {"ok": False, "available": False,
                "reason": f"the waiting folder could not be read ({exc})",
                "folder": str(root), "items": [], "counts": {}, "note": ""}
    for folder in children:
        if len(items) >= MAX_ITEMS:
            stopped = True
            break
        if not _inside(root, folder):
            items.append({"name": folder.name, "kind": "", "verdict": "refuse",
                          "refused": True, "can_install": False,
                          "summary": ("that entry is a link, and a link can "
                                      "point anywhere on this PC, so it is not "
                                      "read"),
                          "reason": ("that entry is a link, and a link can "
                                     "point anywhere on this PC, so it is not "
                                     "read"),
                          "findings": [], "blocking": 0, "warnings": 0,
                          "installed": False, "state": "", "where": "",
                          "sentence": "", "needs_warnings": False})
            continue
        items.append(scan_item(folder))
    counts = {
        "found": len(items),
        "skills": sum(1 for r in items if r.get("kind") == "skill"),
        "plugins": sum(1 for r in items if r.get("kind") == "plugin"),
        "refused": sum(1 for r in items if r.get("refused")),
        "ready": sum(1 for r in items if r.get("can_install")),
        "installed": sum(1 for r in items if r.get("installed")),
    }
    note = ("Nothing in this folder runs or is installed until you press "
            "Install on ONE item and answer its ONE card on this PC. A "
            "plug-in is refused here in this first slice: it is a program, "
            "and programs are not installed by Creator mode yet.")
    if stopped:
        note += (f" Only the first {MAX_ITEMS} folders were read; take the "
                 f"rest out and look again.")
    return {"ok": True, "available": True, "folder": str(root), "items": items,
            "counts": counts, "note": note, "stopped": stopped,
            "max_items": MAX_ITEMS}


# --------------------------------------------------------------------------
#   The one install: the pack manager's own scan and its own ONE card
# --------------------------------------------------------------------------

def _item(name: Any) -> tuple:
    """(the folder, why) for a staged name. A name, never a path.

    Three things are proven before a byte is read: the name is a plain name,
    the folder is inside the waiting folder after resolution, and it really is
    a folder. So `..`, a drive letter and a junction all stop here.
    """
    root = staging_dir()
    clean = _clean_name(name)
    if not clean:
        return None, ("that is not the name of a folder in the waiting folder "
                      "- nothing was installed")
    folder = root / clean
    if not _inside(root, folder):
        return None, (f"{clean!r} would land outside the waiting folder, so "
                      f"nothing was installed")
    if not folder.is_dir():
        return None, (f"there is no folder called {clean!r} in the waiting "
                      f"folder any more - look again")
    return folder, ""


def install_item(name: Any, *, accept_warnings: bool = False) -> dict:
    """Install ONE waiting item, through the pack manager, with ONE card.

    A skill goes through `jarvis_packs.install_pack()`, which scans it again
    from scratch (the scan on the view is not the scan that installs), refuses
    a refused one without asking, raises exactly ONE `modify_own_code` card,
    and turns the skill OFF after the copy. Installing is not enabling: the
    only door that switches it on is the existing ON control.

    A plug-in is refused here, in the pack manager's own words, before any
    card: a plug-in is code, and this slice has no code-install path. So a
    plug-in install is honestly `asked: False` and `installed: False`, never a
    card that could talk the owner into running a program.

    `accept_warnings` is the owner saying they read the warnings; the pack
    manager still refuses a blocked item, so this cannot skip the scanner.
    """
    folder, why = _item(name)
    if folder is None:
        return {"ok": False, "installed": False, "asked": False,
                "refused": True, "reason": why}
    kind, kind_why = _kind_of(folder)
    if not kind:
        return {"ok": False, "installed": False, "asked": False,
                "refused": True, "reason": kind_why}
    if kind == "plugin":
        return {"ok": False, "installed": False, "asked": False,
                "refused": True, "kind": "plugin",
                "reason": _code_refusal(folder)}
    packs = _packs()
    if packs is None:
        return {"ok": False, "installed": False, "asked": False,
                "refused": True,
                "reason": ("this PC's Jarvis has no pack manager beside Creator "
                           "mode, so nothing can be installed from here")}
    try:
        out = packs.install_pack(str(folder),
                                 accept_warnings=bool(accept_warnings))
    except Exception as exc:                           # pragma: no cover
        return {"ok": False, "installed": False, "asked": False,
                "reason": (f"the install failed ({type(exc).__name__}), so "
                           f"nothing was installed")}
    out = dict(out or {})
    out.setdefault("kind", "skill")
    out["staged_name"] = folder.name
    if out.get("ok"):
        # The pack manager's own sentence, plus the one thing this screen
        # exists to say: it landed OFF.
        said = str(out.get("message") or "").strip()
        out["installed"] = True
        out["asked"] = True
        out["state"] = str(out.get("state") or "disabled")
        out["where"] = "turned off"
        out["sentence"] = said or (
            f"{folder.name} is installed and turned off. Turn it on in the "
            f"list above when you want it, with its own card.")
    else:
        out["installed"] = False
    return out


# --------------------------------------------------------------------------
#   The routes, PC only
# --------------------------------------------------------------------------

GET_ROUTES = ("/api/creator/incoming",)
POST_ROUTES = ("/api/creator/install",)

#: What a request from another device is told. Creator mode is where the
#: files are, so it is the PC's; the phone keeps reading the plain list of
#: what is already installed, which is unchanged.
_NOT_PC = ("Creator mode is on the PC only: it puts a skill or a plug-in into "
           "Jarvis from a folder on this PC, so nothing was changed.")


def _peer_local(handler) -> tuple:
    peer = (getattr(handler, "client_address", None) or ("",))[0]
    try:
        local = handler.connection.getsockname()[0]
    except Exception:
        local = None
    return peer, local


def _here(handler) -> bool:
    """Is this request from this PC? Fails closed for a network peer."""
    try:
        import jarvis_owner_check as owner
        peer, local = _peer_local(handler)
        return bool(owner.from_this_pc(peer, local))
    except Exception:                                  # pragma: no cover
        return False


def handle_get(route: str, query: str = "", *, here: Optional[bool] = None) -> tuple:
    """(status, payload). A read: no card and no change."""
    if route not in GET_ROUTES:
        return 404, {"error": "no such read"}
    if not (True if here is None else here):
        return 403, {"ok": False, "error": _NOT_PC}
    return 200, incoming()


def handle_post(route: str, body: Any, *, here: Optional[bool] = None) -> tuple:
    """(status, payload) for the one install route."""
    if route not in POST_ROUTES:
        return 404, {"error": "no such command"}
    if not (True if here is None else here):
        return 403, {"ok": False, "error": _NOT_PC}
    if not isinstance(body, dict):
        return 400, {"error": "need a JSON object"}
    name = body.get("name")
    if not str(name or "").strip():
        return 400, {"ok": False, "reason": "name one folder from the waiting "
                                            "folder - one at a time"}
    out = install_item(name, accept_warnings=bool(body.get("accept_warnings")))
    if out.get("ok"):
        return 200, out
    # A refusal is information, not a transport error: the same shape the pack
    # manager and the skills menu answer with, so the page shows the PC's own
    # words rather than an HTTP number.
    if out.get("refused") or out.get("needs") == "accept_warnings":
        return 200 if out.get("refused") else 409, out
    return 409, out


def install_routes(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so these two routes are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original, untouched - the same shape
    `jarvis_skill_menu.install()` uses, which is why this feature needs no
    patch: `plugins/ready/creator-mode/plugin.json` names this module and
    `jarvis_plugins.py` makes the call a patch would have made.
    """
    from urllib.parse import urlsplit

    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_creator", False):
        return "  creator     waiting folder, scan, one install (already on)"

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
            code, out = handle_get(route, parts.query, here=_here(self))
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
            code, out = handle_post(route, body, here=_here(self))
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_creator = True
    do_POST._jarvis_creator = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return "  creator     waiting folder, scan, ONE install card, PC only: on"


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """The name `jarvis_plugins` calls. ONE loader door, one item door:
    `install_item()` above installs the single folder a card installs, and this
    wraps the server so the two routes are answered here."""
    return install_routes(handler_cls, origin_ok=origin_ok, token_ok=token_ok,
                          read_body=read_body)


# --------------------------------------------------------------------------
#   For the suites
# --------------------------------------------------------------------------

def _self_check() -> dict:
    """What this module can see right now. Read-only: it opens no skill."""
    root, why = _ensure_staging()
    try:
        count = len([p for p in root.iterdir() if p.is_dir()]) if root.is_dir() else 0
    except OSError:
        count = -1
    return {"module": "jarvis_creator", "version": 1,
            "packs": _packs() is not None, "skills": _sk() is not None,
            "folder": str(root), "why": why, "items": count,
            "max_items": MAX_ITEMS}


if __name__ == "__main__":                              # pragma: no cover
    print(json.dumps(_self_check(), indent=2))
