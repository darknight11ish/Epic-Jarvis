"""
jarvis_undo.py - the undo shelf.

Every approval card in this project already tells you what an action costs to
get wrong. jarvis_gate.risk_for() answers it in two words: reversible
yes/hard/no, reach local/outbound. A card can say "no undo: there is no
unsend", and it does. What no card can say is "here is the undo" - because
until this module there wasn't one anywhere. "Reversible: yes" was a claim
with no machinery behind it, which is the kind of claim that trains people to
believe the next one.

So: every action lands on a shelf, and the ones that can actually be put back
can be put back with one tap.

THREE OF SIX CATEGORIES ARE GENUINELY UNDOABLE
Files, git and config key-values, and only because this module keeps its own
before-image of each. The other three - email, browser actions, and anything
unclassified - are not undoable by anybody, and the shelf says so in words
instead of quietly leaving them out. A shelf that listed only the revertible
things would read as a complete record of what happened, and it would be
wrong in the one direction that matters: the actions you most want to see are
the ones nobody can take back.

THE SHELF IS SENSITIVE DATA, NOT A CONVENIENCE CACHE
A before-image is a copy of exactly the bytes someone chose to remove. That
makes this store a second copy of everything deleted in the last day, sitting
next to the machine that deleted it. Three consequences, all of them in the
code below rather than in a note:

  - It expires on a clock, not on a count. Entries past [undo].ttl_hours are
    deleted - index row and bytes - at the top of every public call, so the
    window is the TTL and not "whenever someone next looks".
  - It refuses to shelf an action whose PURPOSE was removing a secret.
    Undoing "strip the API key out of this file" puts the API key back.
  - It never leaves the machine. NEVER_REPLICATE is not advisory: shelf(
    for_remote=True) omits the stored bytes entirely, so the phone can see
    the list and press revert, and the before-images stay here.

Nothing here is a backup. The TTL is short on purpose, and a shelf is what
you reach for in the thirty seconds after saying "no, wait" - not the thing
you rely on in a month.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

# The whole store is one directory so that "delete the shelf" is one rmtree
# and cannot miss a stray blob left behind by a half-finished write.
STORE_DIR = Path(os.environ.get("JARVIS_UNDO_DIR", _CFG_DIR / "undo"))
_LOCK = threading.RLock()

# Read by anything that syncs, mirrors or backs up this machine's config
# directory. The phone client checks it too. It is a constant rather than a
# setting because there is no configuration of this project under which
# shipping a day of deleted file contents to another device is what the owner
# meant.
NEVER_REPLICATE = True


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("undo", {}).get(key, default)
    except Exception:
        return default


def _index_path() -> Path:
    return STORE_DIR / "index.json"


def _blob_dir() -> Path:
    return STORE_DIR / "blobs"


def _enabled() -> bool:
    return bool(_cfg("enabled", True))


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   What can actually be put back, and what only looks like it can
# --------------------------------------------------------------------------
# FILES: yes, but only from a shadow copy this module took BEFORE the write,
# into its own store.
#
#   Not the recycle bin. A script's os.remove / os.unlink does not go through
#   the shell's delete verb, so the file never reaches the recycle bin or the
#   trash at all - that is a Explorer/Finder behaviour, not a filesystem one.
#   Every deletion this assistant performs is exactly the kind that bypasses
#   it, so "it'll be in the bin" is false here specifically.
#
#   Not Volume Shadow Copy. VSS snapshots need administrator rights to create
#   or mount, which this process does not have and must not be given, and
#   they are taken on a schedule per volume - so the snapshot is whatever the
#   volume looked like at 3am, not what the file looked like one second
#   before the write. Coarse in time and privileged to read: the two things a
#   per-write undo cannot be.
#
# GIT: yes, clean tree only. Resetting a dirty tree would undo the recorded
# action and silently take uncommitted work with it, which is a worse outcome
# than not offering the undo.
#
# CONFIG / registry-style key-values: yes, from our own before-image of the
# single key, for the same reason as files - nothing else keeps one.
#
# EMAIL: no. Sending is terminal; SMTP has no unsend and the recipient's copy
# is not ours. The only honest undo for mail is to not have sent it yet - a
# hold queue with a cancel window - which lives in jarvis_preview.hold and is
# deliberately NOT reimplemented here. A cancel window is a pre-send feature;
# putting a fake one behind a post-send button would be the exact dishonesty
# this module exists to remove.
#
# BROWSER: no. A click landed on someone else's server. Nothing local knows
# what it did, and the back button is not an undo.
#
# UNCLASSIFIED: no, same direction as the gate's unknown_action_tier. An
# action nobody classified is not thereby reversible.

_CATEGORY: dict[str, str] = {
    # files, including every note store that is files on disk
    "delete_file": "file",
    "file_write": "file",
    "apply_patch": "file",
    "modify_own_code": "file",
    "create_joplin_note": "file",
    "edit_joplin_note": "file",
    "delete_joplin_note": "file",
    "create_logseq_page": "file",
    "edit_logseq_page": "file",
    "delete_logseq_page": "file",
    "append_logseq_journal": "file",
    "skill_write": "file",
    "skill_install": "file",

    "git_commit": "git",

    # key-value settings: one key, one previous value
    "change_own_config": "config",
    "switch_model": "config",
    "rollback_model": "config",
    "voice_set_mode": "config",
    "power_configure": "config",
    "power_manage": "config",
    "persona_write": "config",

    # A calendar change is an email wearing a different hat: the invite mail
    # is already in someone's inbox the moment it is written, and deleting
    # the event sends a second one. Same category because it has the same
    # only-honest-answer, the hold queue.
    "send_email": "email",
    "draft_email": "email",
    "edit_calendar_event": "email",
    "delete_calendar_event": "email",

    "control_computer": "browser",
    "web_research": "browser",
    "browse_model_catalog": "browser",
    "post_to_external_service": "browser",
    "open_public_tunnel": "browser",
}

_UNDOABLE = frozenset({"file", "git", "config"})

_NO_UNDO_REASON: dict[str, str] = {
    "email": "sending is terminal - there is no unsend, and the recipient's "
             "copy was never ours. The only honest undo is a hold queue with "
             "a cancel window before the send, which is jarvis_preview.hold",
    "browser": "the click already reached someone else's server; nothing on "
               "this machine can take it back",
    "unclassified": "not classified, so treated as irreversible - this shelf "
                    "will not offer an undo it cannot actually perform",
}

# A revert is recorded like any other action, so you can see in the shelf that
# it happened - but it is never itself revertible. Two reasons, and the second
# is the real one. Mechanically, the undo of an undo is just the original
# action, and offering it would build a ladder: revert, un-revert, re-revert,
# each rung a new shelf entry holding another copy of the same bytes, for as
# long as anyone keeps tapping. Honestly, "revert" on a revert card would mean
# "do the thing again", which is not an undo and is exactly the button someone
# taps twice by accident.
REVERT_NOT_REVERTIBLE = (
    "a revert is not itself revertible - undoing an undo is just doing the "
    "action again, and offering it would be an infinite ladder of shelf "
    "entries each holding another copy of the same bytes")


def category_for(action: str) -> str:
    return _CATEGORY.get(action or "", "unclassified")


# --------------------------------------------------------------------------
#   Secrets: the one case where keeping the before-image is the harm
# --------------------------------------------------------------------------
# "Strip the API key out of config.py" is a perfectly ordinary request, and
# the ordinary shelf behaviour - keep the previous bytes for a day - would
# turn it into "make a fresh copy of the API key and leave it somewhere the
# owner is not looking, with a button that puts it back". So: if the
# before-image contains a credential that the after-image does not, the bytes
# are not stored at all and the entry says why.
#
# Matched by fingerprint, not by count. A file that merely MOVES a key
# elsewhere still has the same string in the after-image, so the difference is
# empty and the shelf works normally. A file that ROTATES a key - old value
# out, new value in - does show a removal, and refusing there is correct
# too: the whole point of rotation is that the old value stops existing.

_SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
    r"|\bsk-[A-Za-z0-9_\-]{16,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bxox[baprs]-[A-Za-z0-9\-]{10,}"
    r"|\bAIza[0-9A-Za-z_\-]{35}\b"
    r"|\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"
    r"|\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|password|passwd|passphrase|private[_-]?key|bearer)\b"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9/+=_\-\.]{8,}"
    r"|\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s:/@]{4,}@[^\s/]+",
    re.I)


def _fingerprints(data: bytes) -> set[str]:
    """Every credential-shaped string in these bytes, folded so that the same
    secret written twice is one fingerprint.

    Decoded with errors="replace" rather than refused: a file being edited is
    text far more often than not, and a binary file simply yields no matches.
    Nothing here is stored or logged - a fingerprint is compared and dropped.
    """
    try:
        text = data.decode("utf-8", "replace")
    except Exception:
        return set()
    return {" ".join(m.group(0).split()).lower() for m in _SECRET.finditer(text)}


def _redact(text: str) -> str:
    return _SECRET.sub("<redacted secret>", text)


# --------------------------------------------------------------------------
#   Storage: one JSON index, one blob per before-image, atomic writes
# --------------------------------------------------------------------------

def _empty() -> dict:
    return {"entries": [], "pending": {}}


def _load() -> dict:
    try:
        st = json.loads(_index_path().read_text("utf-8"))
        if not isinstance(st, dict):
            raise ValueError("index is not an object")
        st.setdefault("entries", [])
        st.setdefault("pending", {})
        return st
    except Exception:
        return _empty()


def _save(st: dict) -> bool:
    """Write the index through a temp file and os.replace.

    The same shape as jarvis_content_risk._save_state, and for the same
    reason: a half-written index is indistinguishable from a truncated one,
    and this index is the only thing that says which blob belongs to which
    entry. os.replace is atomic on POSIX and on Windows, so a reader either
    sees the old index or the new one and never a prefix of the new one.
    """
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        _blob_dir().mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(STORE_DIR, 0o700)
        except Exception:
            pass                          # best effort; Windows has no mode
        tmp = _index_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1), "utf-8")
        os.replace(tmp, _index_path())
        return True
    except Exception:
        return False


def _write_blob(name: str, data: bytes) -> bool:
    try:
        _blob_dir().mkdir(parents=True, exist_ok=True)
        p = _blob_dir() / name
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _read_blob(name: str) -> Optional[bytes]:
    try:
        return (_blob_dir() / name).read_bytes()
    except Exception:
        return None


def _drop_blob(name: Optional[str]) -> None:
    if not name:
        return
    try:
        (_blob_dir() / name).unlink()
    except Exception:
        pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _ttl_seconds() -> float:
    # `_cfg(...) or 24` would make 0 mean 24, and 0 is the owner saying "keep
    # nothing" - the one setting of this knob that must not be quietly undone.
    raw = _cfg("ttl_hours", 24)
    try:
        hours = 24.0 if raw is None else float(raw)
    except (TypeError, ValueError):
        hours = 24.0
    return max(0.0, hours) * 3600.0


def _stat(path: Path) -> tuple[bool, float, str, int]:
    """(exists, mtime, sha256, size) for a path. A path that cannot be read
    reads as absent, which is the fail-closed direction: an unreadable target
    must never compare equal to a recorded one."""
    try:
        data = path.read_bytes()
    except Exception:
        return False, 0.0, "", 0
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    return True, mtime, _sha(data), len(data)


# --------------------------------------------------------------------------
#   Expiry - run at the top of every public call, never on a timer
# --------------------------------------------------------------------------

def _sweep() -> int:
    """Delete everything past its TTL, index row and bytes together.

    Called at the top of every public function rather than from a background
    thread. A sweeper thread is the version that looks tidier and is worse:
    it only runs while the process is up, so a shelf written by a process that
    then exited would keep its before-images until something happened to start
    another one. Sweeping on access means the bytes are gone by the time
    anybody - including this module - can next see that they existed.
    """
    now = time.time()
    dropped = 0
    with _LOCK:
        st = _load()
        keep, blobs_to_drop = [], []
        for e in st.get("entries", []):
            if float(e.get("expires", 0)) > now:
                keep.append(e)
            else:
                blobs_to_drop.append((e.get("plan") or {}).get("blob"))
                dropped += 1
        pending = {}
        for tok, p in (st.get("pending") or {}).items():
            if float(p.get("expires", 0)) > now:
                pending[tok] = p
            else:
                # A shadow whose write never happened (the process died, the
                # action was refused by the gate) is a before-image nobody
                # will ever redeem. It expires on the same clock.
                blobs_to_drop.append(p.get("blob"))
                dropped += 1

        # A count cap as well, and it is NOT the expiry policy - the TTL is.
        # This is only a disk backstop so that a runaway loop cannot fill the
        # volume inside one TTL window. Default high enough that ordinary use
        # never reaches it.
        try:
            cap = int(_cfg("max_entries", 500))
        except (TypeError, ValueError):
            cap = 500
        if cap > 0 and len(keep) > cap:
            keep.sort(key=lambda e: float(e.get("ts", 0)))
            for e in keep[:len(keep) - cap]:
                blobs_to_drop.append((e.get("plan") or {}).get("blob"))
                dropped += 1
            keep = keep[len(keep) - cap:]

        st["entries"] = sorted(keep, key=lambda e: float(e.get("ts", 0)))
        st["pending"] = pending
        # Only write if there is something to write. status() and shelf() are
        # reads, and a read that creates the store would mean asking "is
        # anything shelved?" leaves a shelf directory behind on a machine that
        # has never shelved anything.
        if dropped or _index_path().exists():
            _save(st)
        for name in blobs_to_drop:
            _drop_blob(name)

        # Any blob the index no longer names is unreachable by definition, so
        # leaving it would be leaving file contents on disk with nothing left
        # that knows it is there. Interrupted writes are how they appear.
        live = {(e.get("plan") or {}).get("blob") for e in st["entries"]}
        live |= {p.get("blob") for p in st["pending"].values()}
        try:
            for f in _blob_dir().iterdir():
                if f.is_file() and f.name not in live:
                    try:
                        f.unlink()
                    except Exception:
                        pass
        except Exception:
            pass
    if dropped:
        _audit("undo.expired", {"dropped": dropped,
                                "ttl_hours": _cfg("ttl_hours", 24)})
    return dropped


# --------------------------------------------------------------------------
#   shadow() - call this BEFORE writing a file
# --------------------------------------------------------------------------

def shadow(path) -> Optional[str]:
    """Copy the current bytes of `path` into the store and return a token.

    Pass the token to record() after the write. Returns None only when the
    shelf is switched off in config, and a None token is a perfectly valid
    thing to hand to record() - the entry is simply marked non-revertible.

    A path that does not exist yet is shadowed as absent, which is how
    "created a file" gets an undo: putting back "nothing" means deleting it.
    """
    if not _enabled():
        return None
    _sweep()
    p = Path(path)
    tok = _new_id()
    now = time.time()
    rec: dict[str, Any] = {"path": str(p), "ts": now,
                           "expires": now + _ttl_seconds(), "blob": None}

    exists, mtime, sha, size = _stat(p)
    if not exists:
        rec["before_absent"] = True
        rec["before_sha"], rec["before_mtime"], rec["before_bytes"] = "", 0.0, 0
    else:
        try:
            limit = float(_cfg("max_shadow_mb", 8)) * 1024 * 1024
        except (TypeError, ValueError):
            limit = 8 * 1024 * 1024
        if limit > 0 and size > limit:
            # Refusing loudly beats a shelf that silently doubles the disk
            # cost of every large write. The token is still returned so the
            # call site does not need a second code path.
            rec["refused"] = (f"the file is {size // 1024}KB, over "
                              f"[undo].max_shadow_mb - not shadowed")
        else:
            data = _read_bytes(p)
            if data is None:
                rec["refused"] = "the file could not be read before the write"
            elif not _write_blob(f"{tok}.bin", data):
                rec["refused"] = "the before-image could not be written to the shelf"
            else:
                rec["blob"] = f"{tok}.bin"
        rec["before_absent"] = False
        rec["before_sha"], rec["before_mtime"], rec["before_bytes"] = sha, mtime, size

    with _LOCK:
        st = _load()
        st.setdefault("pending", {})[tok] = rec
        _save(st)
    return tok


def _read_bytes(p: Path) -> Optional[bytes]:
    try:
        return p.read_bytes()
    except Exception:
        return None


# --------------------------------------------------------------------------
#   record() - put an entry on the shelf
# --------------------------------------------------------------------------

def record(action: str,
           detail: Optional[dict] = None,
           revert: Optional[dict] = None,
           token: Optional[str] = None) -> dict:
    """Shelf one action. Returns the entry as shelf() would show it locally.

    `revert` is the caller's before-image for the kinds that cannot be taken
    by shadowing a path:

        {"kind": "git",    "repo": <dir>, "head_before": <sha>}
        {"kind": "config", "path": <json file>, "key": <dotted key>,
         "before": <value>}            (or "before_absent": True)

    Everything else - email, browser, anything unrecognised - lands on the
    shelf marked non-revertible with the reason in plain words. That is the
    point: the shelf is a record of what happened, not a list of what is
    convenient to show.
    """
    detail = dict(detail or {})
    if not _enabled():
        return {"id": None, "shelved": False, "action": action,
                "reason": "the undo shelf is disabled in jarvis-framework.toml"}
    _sweep()
    return _shelve(action, detail, revert, token, category_for(action))


def _shelve(action: str, detail: dict, revert: Optional[dict],
            token: Optional[str], category: str,
            forced_reason: str = "") -> dict:
    now = time.time()
    plan: Optional[dict] = None
    reason = ""

    if forced_reason:
        reason = forced_reason
        _release_token(token, keep=False)
    elif category not in _UNDOABLE:
        reason = _NO_UNDO_REASON.get(category, _NO_UNDO_REASON["unclassified"])
        # There is no path on which these bytes will ever be written back, so
        # holding them is liability with no benefit. Drop them now rather than
        # at the TTL.
        _release_token(token, keep=False)
    elif category == "file":
        plan, reason = _file_plan(token)
    elif category == "git":
        plan, reason = _git_plan(revert)
        _release_token(token, keep=False)
    elif category == "config":
        plan, reason = _config_plan(revert)
        _release_token(token, keep=False)

    entry = _jsonable({
        "id": _new_id(),
        "ts": now,
        "expires": now + _ttl_seconds(),
        "action": action,
        "category": category,
        "detail": detail,
        "revertible": plan is not None,
        "reason": reason,
        "plan": plan,
        "reverted": None,
    })
    with _LOCK:
        st = _load()
        st.setdefault("entries", []).append(entry)
        _save(st)
    _audit("undo.recorded", {"id": entry["id"], "action": action,
                             "category": category,
                             "revertible": entry["revertible"]})
    return _view(entry, for_remote=False)


def _jsonable(obj):
    """Force an entry through JSON before it reaches the index.

    A caller's `detail` is whatever the call site had to hand - a Path, a
    datetime, an exception. json.dumps would raise inside _save(), _save()
    catches and returns False, and the entry would vanish with nothing said.
    An entry that silently fails to be recorded is the one failure mode a
    record of what happened cannot have, so unrepresentable values become
    their str() here instead.
    """
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return json.loads(json.dumps(str(obj)))


def _release_token(token: Optional[str], keep: bool) -> Optional[dict]:
    """Take a pending shadow off the pending list. `keep=False` also deletes
    its bytes, which is what every path that will not use them must do."""
    if not token:
        return None
    with _LOCK:
        st = _load()
        rec = (st.get("pending") or {}).pop(token, None)
        _save(st)
    if rec and not keep:
        _drop_blob(rec.get("blob"))
    return rec


def _file_plan(token: Optional[str]) -> tuple[Optional[dict], str]:
    """Turn a redeemed shadow into a revert plan, or say why there is none."""
    if not token:
        return None, ("no shadow copy was taken before the write, so the "
                      "previous bytes do not exist anywhere - call "
                      "jarvis_undo.shadow(path) before writing")
    rec = _release_token(token, keep=True)
    if rec is None:
        return None, ("the shadow expired or was already redeemed before the "
                      "action was recorded")
    if rec.get("refused"):
        _drop_blob(rec.get("blob"))
        return None, str(rec["refused"])

    path = Path(rec.get("path", ""))
    before = b"" if rec.get("before_absent") else (_read_blob(rec.get("blob")) or b"")
    if not rec.get("before_absent") and rec.get("blob") and before == b"" \
            and int(rec.get("before_bytes", 0)) > 0:
        _drop_blob(rec.get("blob"))
        return None, "the before-image is no longer readable in the shelf"

    # The after-image is read HERE, not in shadow(), because shadow() runs
    # before the write and cannot know what the write was for. This is the
    # only moment both halves exist.
    after = _read_bytes(path)
    after_bytes = after if after is not None else b""
    removed = _fingerprints(before) - _fingerprints(after_bytes)
    if removed:
        _drop_blob(rec.get("blob"))
        _audit("undo.refused_secret_removal", {"n": len(removed)})
        return None, ("this write removed a credential, and an undo would put "
                      "it back - the previous bytes were deleted rather than "
                      "shelved")

    exists, mtime, sha, size = _stat(path)
    plan = {
        "kind": "file",
        "path": str(path),
        "blob": rec.get("blob"),
        "before_absent": bool(rec.get("before_absent")),
        "before_bytes": int(rec.get("before_bytes", 0)),
        # What the target looked like immediately after the action. revert()
        # refuses unless the target still looks exactly like this.
        "after_absent": not exists,
        "after_sha": sha,
        "after_mtime": mtime,
        "after_bytes": size,
    }
    return plan, ("the previous bytes are on the shelf until they expire"
                  if not rec.get("before_absent") else
                  "the file did not exist before, so the undo is to delete it")


def _git_plan(revert: Optional[dict]) -> tuple[Optional[dict], str]:
    if not isinstance(revert, dict) or revert.get("kind") != "git":
        return None, ("no git before-image was supplied - pass "
                      "revert={'kind':'git','repo':...,'head_before':...}")
    repo = str(revert.get("repo") or "")
    head = str(revert.get("head_before") or "")
    if not repo or not head:
        return None, "the git before-image is missing repo or head_before"
    ok, now_head = _git(repo, "rev-parse", "HEAD")
    return ({"kind": "git", "repo": repo, "head_before": head,
             "head_after": now_head if ok else ""},
            "revertible while the working tree is clean")


def _config_plan(revert: Optional[dict]) -> tuple[Optional[dict], str]:
    if not isinstance(revert, dict) or revert.get("kind") != "config":
        return None, ("no key-value before-image was supplied - pass "
                      "revert={'kind':'config','path':...,'key':...,"
                      "'before':...}")
    path = str(revert.get("path") or "")
    key = str(revert.get("key") or "")
    if not path or not key:
        return None, "the key-value before-image is missing path or key"
    found, current = _kv_get(Path(path), key)
    return ({"kind": "config", "path": path, "key": key,
             "before": revert.get("before"),
             "before_absent": bool(revert.get("before_absent")),
             "after": current, "after_absent": not found},
            "the previous value is on the shelf until it expires")


# --------------------------------------------------------------------------
#   The shelf itself
# --------------------------------------------------------------------------

def _view(entry: dict, for_remote: bool) -> dict:
    plan = entry.get("plan") or {}
    out = {
        "id": entry.get("id"),
        "ts": entry.get("ts"),
        "age_seconds": round(time.time() - float(entry.get("ts", 0)), 1),
        "expires": entry.get("expires"),
        "action": entry.get("action"),
        "category": entry.get("category"),
        "detail": entry.get("detail") or {},
        "revertible": bool(entry.get("revertible")) and not entry.get("reverted"),
        "reason": entry.get("reason", ""),
        "reverted": entry.get("reverted"),
        "target": plan.get("path") or plan.get("repo") or "",
        "kind": plan.get("kind", ""),
        "before_bytes": int(plan.get("before_bytes", 0) or 0),
        "never_replicate": NEVER_REPLICATE,
    }
    if for_remote:
        # Everything above is metadata: what happened, to what, and whether it
        # can be put back. Enough for a phone to render the shelf and press
        # revert; nothing from inside the before-image. The blob NAME is left
        # out too - not because a filename is secret, but because a remote
        # client with a filename is a remote client one endpoint away from
        # asking for the file.
        return out
    out["blob"] = str(_blob_dir() / plan["blob"]) if plan.get("blob") else ""
    out["preview"] = _preview(plan)
    return out


def _preview(plan: dict) -> str:
    """A few characters of the before-image, for a desktop card that wants to
    show what would come back. Secrets are stripped even here: this store
    refuses to shelf a credential REMOVAL, but a credential that was in the
    file both before and after is still not something to paint on a card."""
    try:
        n = int(_cfg("local_preview_chars", 120))
    except (TypeError, ValueError):
        n = 120
    if n <= 0 or not plan.get("blob"):
        return ""
    data = _read_blob(plan["blob"])
    if data is None:
        return ""
    return _redact(data.decode("utf-8", "replace"))[:n]


def shelf(limit: int = 25, for_remote: bool = False) -> list[dict]:
    """Everything on the shelf, newest first, irreversible actions included.

    for_remote=True is the phone's view: same list, same ids, no bytes and no
    path into the blob store. The phone may see that something happened and
    ask for it to be put back; the before-images stay on this machine.
    """
    if not _enabled():
        return []
    _sweep()
    st = _load()
    rows = sorted(st.get("entries", []), key=lambda e: float(e.get("ts", 0)),
                  reverse=True)
    try:
        limit = max(0, int(limit))
    except (TypeError, ValueError):
        limit = 25
    return [_view(e, for_remote) for e in rows[:limit]]


def _find(entry_id: str) -> tuple[Optional[dict], list]:
    st = _load()
    for e in st.get("entries", []):
        if e.get("id") == entry_id:
            return e, st.get("entries", [])
    return None, st.get("entries", [])


# --------------------------------------------------------------------------
#   revert()
# --------------------------------------------------------------------------

def revert(entry_id: str) -> dict:
    """Put one shelved action back, or say precisely why it will not.

    Refuses, rather than clobbering, whenever the target no longer looks like
    it did right after the action - compared by both mtime and content hash.
    Newer work is not this module's to overwrite, and "the undo ate my
    changes" would make the shelf worse than nothing.
    """
    if not _enabled():
        return {"ok": False, "id": entry_id,
                "reason": "the undo shelf is disabled in jarvis-framework.toml"}
    _sweep()
    entry, _ = _find(entry_id)
    if entry is None:
        return {"ok": False, "id": entry_id,
                "reason": "no such entry - it may have passed its time to live"}
    if entry.get("reverted"):
        # The idempotence guard, and deliberately the FIRST one: the state
        # checks below would also refuse (the target now holds the
        # before-image, not the after-image), but they would refuse with a
        # confusing reason. Two taps on Revert should say "already done".
        return {"ok": False, "id": entry_id, "already": True,
                "reason": "this entry was already reverted"}
    if not entry.get("revertible") or not entry.get("plan"):
        return {"ok": False, "id": entry_id,
                "reason": entry.get("reason") or _NO_UNDO_REASON["unclassified"]}

    # Note that the three refusals above record nothing, while the ones below
    # do. The line is whether anything was attempted: a refusal the shelf can
    # make by reading its own index is not an event, and recording it would
    # make the shelf a thing you can inflate by tapping a disabled button -
    # noise, and a way to push real entries off the end of the list.

    plan = entry["plan"]
    kind = plan.get("kind")
    if kind == "file":
        ok, reason = _revert_file(plan)
    elif kind == "git":
        ok, reason = _revert_git(plan)
    elif kind == "config":
        ok, reason = _revert_config(plan)
    else:
        ok, reason = False, f"revert plan kind {kind!r} is not one this shelf performs"

    if ok:
        with _LOCK:
            st = _load()
            for e in st.get("entries", []):
                if e.get("id") == entry_id:
                    e["reverted"] = {"ts": time.time()}
                    # The bytes are back where they came from, so the shelf
                    # copy is now a second copy of a live file for no reason.
                    _drop_blob((e.get("plan") or {}).get("blob"))
                    (e.get("plan") or {}).pop("blob", None)
                    break
            _save(st)

    _audit("undo.reverted" if ok else "undo.revert_refused",
           {"id": entry_id, "action": entry.get("action"), "kind": kind})

    # Recorded either way. A refused revert is a thing that happened to the
    # shelf, and hiding it would leave the owner wondering whether they tapped.
    rec = _shelve("undo.revert",
                  {"of": entry_id, "of_action": entry.get("action"),
                   "ok": ok, "outcome": reason},
                  None, None, "undo", forced_reason=REVERT_NOT_REVERTIBLE)
    return {"ok": ok, "id": entry_id, "reason": reason, "recorded": rec["id"]}


def _revert_file(plan: dict) -> tuple[bool, str]:
    path = Path(plan.get("path", ""))
    exists, mtime, sha, _size = _stat(path)

    if bool(plan.get("after_absent")) != (not exists):
        return False, ("the target changed after the shadow was taken - it "
                       "was " + ("deleted" if plan.get("after_absent") else "present")
                       + " when the action ran and is "
                       + ("missing" if not exists else "present")
                       + " now, so reverting would clobber newer work")
    if exists and sha != plan.get("after_sha"):
        return False, ("the target changed after the shadow was taken - its "
                       "contents no longer match what the action left behind, "
                       "so reverting would clobber newer work")
    # A moved timestamp with a matching hash used to be a refusal. It should
    # not be: the hash is what says whether anybody's work is at stake, and
    # identical bytes are identical bytes however they got there - a restore
    # from backup, a rewrite of the same content, a checkout. Refusing there
    # produces a confusing error for what would have been a no-op edit, and
    # the owner learns that the shelf refuses for no visible reason, which is
    # how a safety message stops being read. So it is carried as a note on a
    # successful revert instead of blocking one.
    touched = bool(exists and plan.get("after_mtime")
                   and abs(float(mtime) - float(plan["after_mtime"])) > 1e-6)

    if plan.get("before_absent"):
        if not exists:
            return True, "nothing to delete; the file is already gone"
        try:
            path.unlink()
        except Exception as exc:
            return False, f"the file could not be deleted ({exc})"
        return True, _note(touched, "the file this action created has been deleted")

    data = _read_blob(plan.get("blob") or "")
    if data is None:
        return False, ("the before-image is no longer on the shelf - it "
                       "expired, or the store was purged")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".jarvis-undo.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except Exception as exc:
        return False, f"the previous bytes could not be written back ({exc})"
    return True, _note(touched, f"{len(data)} bytes restored byte for byte")


def _note(touched: bool, reason: str) -> str:
    """Say that the timestamp had moved, without pretending it mattered."""
    if not touched:
        return reason
    return (reason + " (its timestamp had moved since the action, but the "
            "contents still matched, so nothing newer was overwritten)")


def _git(repo: str, *args: str) -> tuple[bool, str]:
    """Run one git command. No shell, argv list, short timeout."""
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                           text=True, timeout=30)
    except Exception as exc:
        return False, f"git could not be run ({exc})"
    return p.returncode == 0, (p.stdout or p.stderr or "").strip()


def _revert_git(plan: dict) -> tuple[bool, str]:
    repo = plan.get("repo", "")
    ok, _ = _git(repo, "rev-parse", "--is-inside-work-tree")
    if not ok:
        return False, f"{repo} is not a git working tree"
    ok, dirty = _git(repo, "status", "--porcelain")
    if not ok:
        return False, f"git status failed: {dirty}"
    if dirty.strip():
        # Clean tree only. `git reset --hard` on a dirty tree would undo the
        # recorded commit and destroy every uncommitted change alongside it,
        # which is a bigger loss than the one being undone.
        return False, ("the working tree has uncommitted changes - a revert "
                       "here would discard them too, so it is refused; commit "
                       "or stash first")
    ok, head = _git(repo, "rev-parse", "HEAD")
    if not ok:
        return False, f"git rev-parse failed: {head}"
    if plan.get("head_after") and head != plan["head_after"]:
        return False, ("the repository moved on after this action (HEAD is no "
                       "longer what it was), so reverting would clobber newer "
                       "work")
    ok, out = _git(repo, "reset", "--hard", plan.get("head_before", ""))
    if not ok:
        return False, f"git reset failed: {out}"
    return True, f"HEAD reset to {str(plan.get('head_before'))[:12]}"


def _kv_get(path: Path, key: str) -> tuple[bool, Any]:
    """Read one dotted key from a JSON key-value file. (found, value)."""
    try:
        node = json.loads(path.read_text("utf-8"))
    except Exception:
        return False, None
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _kv_set(path: Path, key: str, value: Any, delete: bool) -> tuple[bool, str]:
    try:
        doc = json.loads(path.read_text("utf-8")) if path.exists() else {}
        if not isinstance(doc, dict):
            return False, "the key-value store is not a JSON object"
    except Exception as exc:
        return False, f"the key-value store could not be read ({exc})"
    parts = key.split(".")
    node = doc
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    if delete:
        node.pop(parts[-1], None)
    else:
        node[parts[-1]] = value
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".jarvis-undo.tmp")
        tmp.write_text(json.dumps(doc, indent=1), "utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        return False, f"the key-value store could not be written ({exc})"
    return True, "ok"


def _revert_config(plan: dict) -> tuple[bool, str]:
    path = Path(plan.get("path", ""))
    key = plan.get("key", "")
    found, current = _kv_get(path, key)
    if found != (not plan.get("after_absent")) or \
            (found and current != plan.get("after")):
        return False, ("the value changed after this action ran, so reverting "
                       "would clobber newer work")
    ok, msg = _kv_set(path, key, plan.get("before"),
                      delete=bool(plan.get("before_absent")))
    if not ok:
        return False, msg
    return True, (f"{key} deleted" if plan.get("before_absent")
                  else f"{key} set back to its previous value")


# --------------------------------------------------------------------------
#   forget / purge - the same delete path that clears memory clears this
# --------------------------------------------------------------------------

def forget(entry_id: str) -> bool:
    """Drop one entry and its bytes. True if there was something to drop."""
    if not _enabled():
        return False
    _sweep()
    with _LOCK:
        st = _load()
        keep, gone = [], None
        for e in st.get("entries", []):
            if e.get("id") == entry_id:
                gone = e
            else:
                keep.append(e)
        if gone is None:
            return False
        st["entries"] = keep
        _save(st)
        _drop_blob((gone.get("plan") or {}).get("blob"))
    _audit("undo.forgotten", {"id": entry_id, "action": gone.get("action")})
    return True


def purge() -> int:
    """Empty the shelf: every entry, every pending shadow, every blob.

    Removes the whole store directory rather than walking the index, because
    the index is the thing that might be wrong. If a crashed write left a blob
    the index no longer names, walking the index would leave that file on disk
    and report success - which is the failure mode this function exists to not
    have. Returns how many entries were on the shelf.
    """
    with _LOCK:
        st = _load()
        n = len(st.get("entries", [])) + len(st.get("pending", {}))
        try:
            shutil.rmtree(STORE_DIR)
        except FileNotFoundError:
            pass
        except Exception:
            # Could not remove the directory - blank the index and drop every
            # blob it named, so at worst an orphan file survives rather than a
            # working shelf that claims to have been purged.
            for e in st.get("entries", []):
                _drop_blob((e.get("plan") or {}).get("blob"))
            for p in (st.get("pending") or {}).values():
                _drop_blob(p.get("blob"))
            _save(_empty())
    _audit("undo.purged", {"entries": n})
    return n


# --------------------------------------------------------------------------
#   status()
# --------------------------------------------------------------------------

def status() -> dict:
    """What the HUD shows next to the shelf: how much is held, for how long,
    and the flag that says none of it may be replicated."""
    if not _enabled():
        return {"enabled": False, "never_replicate": NEVER_REPLICATE,
                "entries": 0, "revertible": 0, "pending": 0, "bytes": 0,
                "store": str(STORE_DIR)}
    _sweep()
    st = _load()
    entries = st.get("entries", [])
    held = 0
    for e in entries:
        blob = (e.get("plan") or {}).get("blob")
        if blob:
            try:
                held += (_blob_dir() / blob).stat().st_size
            except Exception:
                pass
    return {
        "enabled": True,
        "never_replicate": NEVER_REPLICATE,
        "store": str(STORE_DIR),
        "entries": len(entries),
        "revertible": sum(1 for e in entries
                          if e.get("revertible") and not e.get("reverted")),
        "reverted": sum(1 for e in entries if e.get("reverted")),
        "pending": len(st.get("pending", {})),
        "bytes": held,
        "config": {"ttl_hours": _cfg("ttl_hours", 24),
                   "max_shadow_mb": _cfg("max_shadow_mb", 8),
                   "max_entries": _cfg("max_entries", 500),
                   "local_preview_chars": _cfg("local_preview_chars", 120)},
        # Said here as well as in the module docstring, because this dict is
        # what a client renders and a client author may never read the module.
        "hold_queue": "email has no undo; jarvis_preview.hold is the cancel "
                      "window that happens before a send",
    }


# --------------------------------------------------------------------------
#   python jarvis_undo.py
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="The undo shelf: look, revert, purge.")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--revert", metavar="ID", help="put one shelved action back")
    ap.add_argument("--forget", metavar="ID", help="drop one entry and its bytes")
    ap.add_argument("--purge", action="store_true", help="empty the shelf")
    a = ap.parse_args()

    if a.purge:
        print(f"  purged {purge()} entries")
    elif a.revert:
        r = revert(a.revert)
        print(f"  {'reverted' if r['ok'] else 'refused'}: {r['reason']}")
    elif a.forget:
        print("  forgotten" if forget(a.forget) else "  no such entry")
    else:
        s = status()
        print(f"\n  shelf at {s.get('store')} - {s.get('entries', 0)} entries, "
              f"{s.get('bytes', 0)} bytes held, TTL "
              f"{s.get('config', {}).get('ttl_hours', '?')}h\n")
        for e in shelf(a.limit):
            mark = "revert" if e["revertible"] else "  --  "
            print(f"    {e['id']}  [{mark}] {e['action']:24} {e['target'][:48]}")
            if not e["revertible"]:
                print(f"                   {e['reason']}")
        print()
