"""jarvis_outbox.py - what Jarvis still owes you, written down BEFORE it says it.

THE DEFECT THIS EXISTS FOR (2026-11-04, the restart card loss). A background job
asks for something and parks in `waiting_approval`; the queue publishes one
`job` event and the Work pane draws the card. Now the backend restarts - a
deploy, a crash, the owner's own Update press. The job row is still there and
the grant is still pending, but NOTHING re-announces it: the event was a moment,
not a record, and the one thing every client needs to hear has already been
said. The card is lost without being answered. The same shape applies to a
completion notice: a job that finished while the process was going down was
never told to anybody, and the next start does not know it was owed.

THE ANSWER IS AN OUTBOX, NOT A RETRY. This is the outbox pattern from
`dsh-superagent`'s `docs/007-architecture.md` (`Effects` and `Outbox`), which
this project adopted on 2026-11-04: before anything is delivered, the intention
to deliver it is written to disk with a deterministic `(kind, key)`; delivery
happens after that write; and the entry is settled only once delivery has
actually happened. A restart then has a list of what it still owes and can
re-announce it. "Never lose a pending card" is the write-before-send. "Never
double-send" is the `(kind, key)` pair plus the settle, and it holds within a
process and across a restart for anything already settled.

THE HONEST LIMIT, SAID PLAINLY. This is at-least-once, not exactly-once. A
process that dies after the send and before the settle will re-send that one
entry on the next start. It can never do the opposite - an entry that exists is
an entry somebody will be told about - because the write comes first. Given the
choice between one repeated notice and one lost approval card, this module
takes the repeat every time; a card the owner never sees is a job that waits
for ever (`docs/ARCHITECTURE.md` section 10).

WHY JSON AND NOT THE JOBS DATABASE. `jarvis_jobs.py` already owns a SQLite
database, and this could have been a table in it. It is not, on purpose:

  * the watchers write here too (`jarvis_watch_ci.py`'s `pr_ci_notice`), and a
    fan-out watcher must not have to open the job queue's writer thread to say
    one sentence;
  * the file is small, bounded and read whole, so the atomic write-then-rename
    below is the entire consistency story. There is no second writer thread, no
    `database is locked`, and nothing to reclaim after a crash: a half-written
    temp file is discarded and the previous file is still the truth.

THE THREE KINDS, AND WHAT "SETTLED" MEANS FOR EACH. `KINDS` is deliberately
closed, because the key is `(kind, key)` and a typo in `kind` would silently
create a second, always-duplicate slot:

  * `job_card` - a parked job's one-shot capability question. It stays PENDING
    until a person answers it, because until then the owner is still owed the
    card. `jarvis_jobs.answer()`/`_stop_denied()`/`cancel()` settle it.
  * `job_done` - a job finished and nobody has been told. Settled on send.
  * `pr_ci_notice` - what the GitHub CI watcher decided to say about one pull
    request at one commit. Settled on send.

`PRINTS NOTHING, DECIDES NOTHING` is still true of the whole watch family: this
module writes a file and calls the sender it is handed. It raises no approval
card, approves none, and never widens a capability.

WHERE THE FILE IS. `JARVIS_OUTBOX_PATH` if it is set; otherwise beside the jobs
database when `JARVIS_JOBS_DB` names one (so a test that moves the queue moves
this too, and a direct run cannot write the owner's real folder); otherwise
`outbox.json` in the settings folder. `bind()` is how `jarvis_jobs.py` points it
at the database it is actually using, including after `shutdown()` moves it.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

#: A closed set, because the dedupe key is `(kind, key)`: a typo in `kind`
#: would make a second slot that never collides with the real one.
KINDS = ("job_card", "job_done", "pr_ci_notice")

#: How many entries the file holds. Settled entries are dropped oldest-first
#: once this is passed; a PENDING entry is never dropped, however old, because
#: dropping one is exactly the lost card this module exists to prevent.
MAX_ENTRIES = 500

#: Field length caps. The payload is the owner's own material (a job label, a
#: pull request title), so it is stored for a notice but never trusted to be
#: small.
KEY_CHARS = 200
TEXT_CHARS = 600

_LOCK = threading.RLock()
_BOUND: Optional[Path] = None
_LAST_ERROR: str = ""


# --------------------------------------------------------------------------
#   Where the file is
# --------------------------------------------------------------------------

def _config_dir() -> Path:
    """The same folder every other small store here uses, found the same way:
    the backend's own CONFIG_DIR when the framework is importable, then the
    environment, then `~/.openjarvis`."""
    try:
        import jarvis_framework as fw          # noqa: F401 - imported for CONFIG_DIR
        return Path(fw.CONFIG_DIR)
    except Exception:
        env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
        if env:
            return Path(os.path.expanduser(env))
        return Path(os.path.expanduser("~")) / ".openjarvis"


def path() -> Path:
    """The outbox file this process uses, resolved on every call.

    Resolved every time rather than once at import, for the same reason
    `jarvis_watch.check()` resolves its fetcher at call time: a caller that
    moves the queue (a test, a backup restore, a second profile) must not find
    this module still writing the old place.
    """
    with _LOCK:
        if _BOUND is not None:
            return _BOUND
    env = os.environ.get("JARVIS_OUTBOX_PATH")
    if env:
        return Path(os.path.expanduser(env))
    jdb = os.environ.get("JARVIS_JOBS_DB")
    if jdb:
        return Path(os.path.expanduser(jdb)).parent / "outbox.json"
    return _config_dir() / "outbox.json"


def bind(p) -> Optional[Path]:
    """Point this module at the store beside a specific jobs database.

    `jarvis_jobs._init()` calls this with `DB_PATH.parent / "outbox.json"`,
    because that module's database can be moved between cases with a plain
    assignment (its own `shutdown()` contract) and this must follow it.
    `bind(None)` clears the binding and puts the resolution back on the
    environment, which is what the suite uses to prove the order.
    """
    global _BOUND
    with _LOCK:
        _BOUND = Path(p) if p else None
        return _BOUND


def _reset_for_tests() -> None:
    global _BOUND, _LAST_ERROR
    with _LOCK:
        _BOUND = None
        _LAST_ERROR = ""


# --------------------------------------------------------------------------
#   Crash-safe JSON, shared with the watcher
# --------------------------------------------------------------------------
# One writer for every small JSON store in this slice. Write to a temp file in
# the SAME folder, flush it to the disk, then `os.replace` it over the real
# name: a reader sees either the whole old file or the whole new one, and a
# power cut in the middle leaves the old one, never half of a new one. The temp
# name is fixed rather than random so a crashed run leaves ONE stray file that
# the next write reuses instead of a litter of them.

def read_json(p) -> tuple:
    """`(document, note)`. A missing file is an empty outbox, not an error."""
    try:
        raw = Path(p).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, ""
    except OSError as exc:
        return {}, f"could not be read ({type(exc).__name__})"
    try:
        doc = json.loads(raw)
    except Exception:
        return {}, "is not valid JSON"
    if not isinstance(doc, dict):
        return {}, "is not a JSON object"
    return doc, ""


def write_json_atomic(p, doc: dict) -> None:
    """Write `doc` to `p` so a reader never sees a half-written file."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, sort_keys=True,
                  separators=(",", ":"))
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:                                # pragma: no cover
            pass
    os.replace(tmp, p)


# --------------------------------------------------------------------------
#   The store
# --------------------------------------------------------------------------

def _text(value, cap: int) -> str:
    return str(value if value is not None else "")[:cap]


def _entry_doc(e: dict) -> dict:
    """One entry, with only the fields this module promises and no more."""
    return {
        "kind": _text(e.get("kind"), 40),
        "key": _text(e.get("key"), KEY_CHARS),
        "payload": e.get("payload") if isinstance(e.get("payload"), dict) else {},
        "created": float(e.get("created") or 0.0),
        "state": "pending" if e.get("state") != "done" else "done",
        "settled": e.get("settled"),
        "seq": int(e.get("seq") or 0),
    }


def _load() -> dict:
    """`{"version", "seq", "entries"}`. A damaged file is set aside rather than
    overwritten, because it is the only evidence of what was owed at the crash
    - and the job rows are the authority anyway: a parked job with a pending
    grant is re-registered by `jarvis_jobs` on startup, so a lost outbox file
    delays a card by one restart and cannot lose it for ever."""
    global _LAST_ERROR
    p = path()
    doc, note = read_json(p)
    entries = doc.get("entries")
    if note:
        _LAST_ERROR = f"{p.name} {note}"
        if p.exists():
            try:
                os.replace(p, p.with_name(f"{p.name}.corrupt-{int(time.time())}"))
            except OSError:
                pass
        return {"version": 1, "seq": 0, "entries": []}
    if not isinstance(entries, list):
        entries = []
    clean = []
    for e in entries:
        if isinstance(e, dict) and e.get("kind") and e.get("key"):
            clean.append(_entry_doc(e))
    return {"version": 1, "seq": int(doc.get("seq") or 0), "entries": clean}


def _save(doc: dict) -> None:
    write_json_atomic(path(), doc)


def _find(doc: dict, kind: str, key: str) -> Optional[dict]:
    for e in doc["entries"]:
        if e["kind"] == kind and e["key"] == key:
            return e
    return None


def _prune(doc: dict) -> None:
    """Keep the file bounded WITHOUT ever dropping something still owed."""
    if len(doc["entries"]) <= MAX_ENTRIES:
        return
    # Settled entries go first, oldest first; pending ones are all kept. If
    # there are more pending items than the cap the cap is exceeded and
    # `status()` says so: losing one would be the defect this module exists for.
    surplus = len(doc["entries"]) - MAX_ENTRIES
    keep = []
    for e in sorted(doc["entries"], key=lambda x: x.get("seq") or 0):
        if surplus > 0 and e.get("state") == "done":
            surplus -= 1
            continue
        keep.append(e)
    doc["entries"] = keep


def enqueue(kind: str, key: str, payload: Optional[dict] = None, *,
            now: Optional[float] = None) -> dict:
    """Record that this exact notice is owed, BEFORE anybody is told.

    Returns `{"ok", "state": "pending"|"duplicate", "entry"}`. `duplicate`
    means an entry with the same `(kind, key)` already exists - pending, so
    somebody still owes it, or done, so it has already been delivered. Either
    way this call wrote nothing and the caller must not deliver again.
    """
    kind = _text(kind, 40)
    key = _text(key, KEY_CHARS)
    if kind not in KINDS:
        raise ValueError(f"{kind!r} is not an outbox kind; try one of "
                         f"{', '.join(KINDS)}")
    if not key:
        raise ValueError("an outbox key cannot be empty - it is the dedupe")
    now = time.time() if now is None else float(now)
    with _LOCK:
        doc = _load()
        found = _find(doc, kind, key)
        if found is not None:
            return {"ok": True, "state": "duplicate", "entry": dict(found)}
        doc["seq"] = int(doc.get("seq") or 0) + 1
        entry = _entry_doc({"kind": kind, "key": key, "payload": payload or {},
                            "created": now, "state": "pending",
                            "settled": None, "seq": doc["seq"]})
        doc["entries"].append(entry)
        _prune(doc)
        _save(doc)
        return {"ok": True, "state": "pending", "entry": dict(entry)}


def get(kind: str, key: str) -> Optional[dict]:
    with _LOCK:
        doc = _load()
        found = _find(doc, kind, _text(key, KEY_CHARS))
        return dict(found) if found else None


def pending(kind: Optional[str] = None, limit: int = 200) -> list:
    """Everything still owed, oldest first."""
    with _LOCK:
        doc = _load()
        rows = [dict(e) for e in doc["entries"]
                if e.get("state") == "pending" and (kind is None or e["kind"] == kind)]
    return rows[:max(1, int(limit))]


def resolve(kind: str, key: str, *, now: Optional[float] = None,
            why: str = "") -> bool:
    """Settle one entry: it is no longer owed. False if it was not there or had
    already been settled - so a second call cannot look like a fresh delivery."""
    kind = _text(kind, 40)
    key = _text(key, KEY_CHARS)
    now = time.time() if now is None else float(now)
    with _LOCK:
        doc = _load()
        found = _find(doc, kind, key)
        if found is None or found.get("state") == "done":
            return False
        found["state"] = "done"
        found["settled"] = now
        if why:
            found["payload"] = dict(found.get("payload") or {}, settled_why=_text(why, 120))
        _save(doc)
        return True


def deliver(kind: str, key: str, payload: Optional[dict], send: Callable[[dict], object], *,
            now: Optional[float] = None) -> str:
    """Write it down, then send it, then settle it. In that order.

    `send(entry)` receives the stored entry and may return `False` to mean "the
    owner is still owed this" - the correctness a parked card needs, since the
    card is not settled by being announced. Any other return settles it.

    Returns:

      * `"sent"` - newly written, sent just now, and settled;
      * `"owed"` - an entry with this key was already announced and is still
        owed (a card nobody answered). NOTHING is sent again: the same question
        asked on every tick is one card, not one per tick, and the next restart
        re-announces it once through `rehydrate()`;
      * `"already"` - an entry with this key was already settled (a notice
        already delivered), so nothing is sent;
      * `"failed"` - the sender raised; the entry stays pending for the next
        start. A sender that raises must not take the caller down with it -
        `_park()` is inside a job's own lifecycle, and a notification that could
        not be published is not a reason to fail a job.
    """
    global _LAST_ERROR
    st = enqueue(kind, key, payload, now=now)
    if st["state"] == "duplicate":
        return "already" if st["entry"].get("state") == "done" else "owed"
    entry = st["entry"]
    try:
        verdict = send(entry)
    except Exception as exc:                           # noqa: BLE001 - see docstring
        with _LOCK:
            _LAST_ERROR = f"send failed: {type(exc).__name__}"
        return "failed"
    if verdict is False:
        return "owed"
    resolve(kind, key, now=now)
    return "sent"


def rehydrate(send: Callable[[dict], object], *, kinds=None,
              limit: int = 200, now: Optional[float] = None) -> list:
    """Re-announce everything still owed. The startup call, once per process.

    Every pending entry is handed to `send(entry)`, in the order it was
    recorded. `send` returning `False` leaves the entry pending (a card nobody
    has answered yet, which the next restart will announce again); anything
    else settles it, so a notice that was written before a crash and never
    delivered is delivered exactly once.
    """
    owed = pending(limit=limit)
    if kinds:
        want = tuple(kinds)
        owed = [e for e in owed if e.get("kind") in want]
    sent = []
    for e in owed:
        try:
            verdict = send(e)
        except Exception:                              # noqa: BLE001
            continue
        if verdict is False:
            continue
        resolve(e["kind"], e["key"], now=now)
        sent.append(f"{e['kind']}:{e['key']}")
    return sent


def status() -> dict:
    """What the boot banner and the suites read: how much is owed, of what, and
    whether the last write failed."""
    with _LOCK:
        doc = _load()
        rows = doc["entries"]
        counts = {k: 0 for k in KINDS}
        for e in rows:
            if e.get("state") == "pending":
                counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        return {"path": str(path()),
                "entries": len(rows),
                "pending": sum(counts.values()),
                "by_kind": counts,
                "last_error": _LAST_ERROR,
                "kinds": list(KINDS)}
