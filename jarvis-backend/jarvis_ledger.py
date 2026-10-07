"""
jarvis_ledger.py - a tamper-evident record of what the assistant did, and a
"why did you do that" view over it.

The audit log in jarvis_framework.py answers "did this happen". It cannot
answer "has anyone edited this since", because a JSON-lines file is editable
with any text editor and says nothing about it. This module is the second
half: an append-only chain where changing one past entry changes every hash
after it.

Four decisions were argued out before any of it was written, and each one is
a place where the obvious design is the wrong one.

  1. THE CHAIN COVERS METADATA ONLY.  Chaining the payloads too is the first
     thing anyone reaches for, and it is un-redactable by construction: once
     the body of an email is inside a hash that every later entry depends on,
     "forget this" can only be honoured by destroying the chain. That would
     have made the integrity feature and the forgetting feature mutually
     exclusive, in a project whose whole claim is that you can have both. So
     the chain holds the DECISION - sequence, time, event, action, tier, lane,
     the rule that fired, which memories were retrieved BY TITLE AND TIME,
     which were skipped and why - and a commitment to the payload. The
     payload itself lives in a separate table, encrypted, and can be dropped
     on its own. After that, the chain still verifies and the row reads
     honestly: content removed on <date>, decision preserved.

  2. HMAC WITH A LOCAL KEY, NOT A SIGNATURE.  Ed25519 was on the table and
     was rejected on purpose. A signature anyone can verify turns this log
     into evidence that is credible AGAINST the owner - to a court, to an
     employer, to whoever is holding the laptop and asking questions. The
     only legitimate reader of this ledger is the person it is about, and for
     that reader a symmetric MAC is exactly as good. Non-repudiation is not a
     missing feature here; it is a liability we declined to build.

     The engineer's objection is accepted rather than argued with: the key
     lives on the same machine as the database, so code running as the owner
     can forge any chain it likes. This is tamper-evident against
     AFTER-THE-FACT EDITING - someone (or something) that opens the database
     later and changes a row - which is the threat that actually exists here.
     It is not, and is not claimed to be, proof of anything to anyone else.

  3. ROLLING RE-ANCHOR.  A chain only detects edits that do not also rewrite
     everything downstream, and a rewrite downstream is cheap when the key is
     local. So the current head hash is periodically appended to a separate
     file that this process never rewrites in the normal course of business.
     That bounds the window: anything older than the last anchor you still
     have a copy of cannot be silently rewritten, because the rewrite would
     have to match a hash that is already written down elsewhere.

  4. ENCRYPTION WITHOUT A DEPENDENCY.  There is no `cryptography` package
     here and adding one is out of scope, so the payload cipher is built from
     hashlib - see the honest accounting in the Encryption section below. It
     is weaker than an AEAD from a vetted library, it is described as such
     everywhere it appears, and it should be replaced by one if a dependency
     is ever allowed.

Nothing in this module reaches the network, and `why()` never decrypts
anything: the "why did you do that" view is metadata by construction, so it
cannot quietly become a content viewer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

DB_PATH = Path(os.environ.get("JARVIS_LEDGER_DB", _CFG_DIR / "ledger.db"))
KEY_PATH = Path(os.environ.get("JARVIS_LEDGER_KEY", _CFG_DIR / "ledger.key"))
ANCHOR_PATH = Path(os.environ.get("JARVIS_LEDGER_ANCHORS",
                                  _CFG_DIR / "ledger-anchors.jsonl"))

_LOCK = threading.RLock()

# Version byte in every hashed and MACed structure. Without it, a future
# change to the field order would silently produce hashes that cannot be
# distinguished from tampering, and the first upgrade would look like an
# attack.
_V = "jarvis-ledger/1"

# The prev_hash of the first entry. A literal run of zeroes rather than a
# hash of something, so "this is the start of the chain" cannot be confused
# with "this points at an entry that has been deleted".
_GENESIS = "0" * 64


class LedgerTampered(RuntimeError):
    """A payload failed its MAC. Raised instead of returning the plaintext,
    because returning bytes that failed authentication is how a decryption
    oracle gets built by accident."""


class LedgerUnavailable(RuntimeError):
    """The ledger cannot be written to. Unlike audit_log(), this is raised and
    not swallowed: a ledger that silently drops entries still verifies clean
    afterwards, which is a lie of exactly the kind this module exists to make
    impossible. A caller that would rather continue can catch it - but it has
    to say so."""


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("ledger", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Keys
# --------------------------------------------------------------------------

# Cached per key-file path rather than in one module-level variable, so a test
# (or a second config directory) that repoints KEY_PATH gets its own keys
# instead of whatever the last caller happened to load.
_KEYS: dict[str, dict[str, bytes]] = {}


def _new_key_file(path: Path) -> bytes:
    """Create the key file with 0600 from the first instant it exists.

    Writing it and chmod-ing afterwards leaves a window - short, but real, and
    on a shared machine the window is the whole attack - in which the key is
    world-readable. os.open with the mode argument and O_EXCL closes both that
    window and the race where two processes each think they created it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, secrets.token_bytes(32))
    finally:
        os.close(fd)
    return path.read_bytes()


def _key_mode(path: Path) -> Optional[str]:
    """The key file's permission bits as "0600", or None where the platform
    does not have any (Windows), so status() can report the truth rather than
    a reassuring guess."""
    try:
        if os.name == "nt":
            return None
        return format(stat.S_IMODE(path.stat().st_mode), "04o")
    except Exception:
        return None


def _keys() -> dict[str, bytes]:
    """Three keys derived from one 32-byte random file.

    scrypt here is domain separation, not password stretching: the input is
    already full-entropy random, so there is nothing for an attacker to guess
    faster. What it buys is that the chain key, the payload key and the
    commitment key cannot be derived from one another, and that the raw file
    bytes are never used directly as an HMAC key.
    """
    k = str(KEY_PATH)
    cached = _KEYS.get(k)
    if cached:
        return cached
    with _LOCK:
        cached = _KEYS.get(k)
        if cached:
            return cached
        try:
            master = KEY_PATH.read_bytes()
        except FileNotFoundError:
            master = _new_key_file(KEY_PATH)
        if len(master) < 16:
            raise LedgerUnavailable(f"{KEY_PATH} is too short to be the ledger key")
        mode = _key_mode(KEY_PATH)
        if mode and int(mode, 8) & 0o077:
            # Tighten it rather than refuse. Refusing would mean no ledger at
            # all, and a loose-but-present audit trail beats an absent one -
            # but the state is reported by status() either way, so it does not
            # go unnoticed.
            try:
                os.chmod(KEY_PATH, 0o600)
            except Exception as exc:      # pragma: no cover - platform-specific
                print(f"  [ledger] key file {KEY_PATH} is mode {mode} and could "
                      f"not be tightened: {exc}", file=sys.stderr, flush=True)
        try:
            raw = hashlib.scrypt(master, salt=b"jarvis-ledger/v1",
                                 n=2 ** 14, r=8, p=1, dklen=96, maxmem=64 * 1024 * 1024)
        except (ValueError, AttributeError):     # pragma: no cover - no scrypt
            raw = hashlib.pbkdf2_hmac("sha256", master, b"jarvis-ledger/v1",
                                      120_000, dklen=96)
        out = {"chain": raw[0:32], "payload": raw[32:64], "commit": raw[64:96]}
        _KEYS[k] = out
        return out


# --------------------------------------------------------------------------
#   Encryption - what this does and does not give you
# --------------------------------------------------------------------------
# HONEST ACCOUNTING, because an overstated crypto comment is how a system ends
# up trusted for something it never did.
#
# WHAT THIS IS: SHA-256 run in counter mode to produce a keystream, XORed with
# the plaintext, followed by HMAC-SHA256 over the version string, the sequence
# number, the nonce and the ciphertext. Encrypt-then-MAC, in that order, and
# the tag is checked in constant time BEFORE a single byte is decrypted.
#
# WHAT IT GIVES YOU:
#   - Confidentiality of payloads against someone who obtains the database
#     file and not the key file: a stolen backup, a synced folder, a disk
#     image, a support bundle, the laptop while it is off.
#   - Detection of any modification to a stored ciphertext, including one
#     swapped in from another entry: the sequence number is inside the MAC, so
#     moving a payload from entry 7 to entry 9 fails the tag.
#
# WHAT IT DOES NOT GIVE YOU:
#   - Anything at all against someone who has the key file, which sits on the
#     same disk. This is not protection from the machine's owner or from code
#     running as them. It is protection from a copy of the data.
#   - The scrutiny a standard construction has had. This particular assembly
#     of SHA-256 has no formal analysis behind it. It is believed sound
#     because the underlying primitives are, which is a weaker statement than
#     it sounds.
#   - Safety under nonce reuse. The nonce is 16 random bytes per payload, so a
#     collision is not a practical worry, but nothing here detects one.
#   - Any hiding of payload length. The ciphertext is the plaintext's length.
#   - Forward secrecy. One key file opens every payload ever written.
#
# If a dependency is ever permitted, replace `_encrypt`/`_decrypt` with
# AES-256-GCM or ChaCha20-Poly1305 from `cryptography` and keep everything
# else. Nothing above this line depends on the cipher's shape.

_NONCE_BYTES = 16


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:n])


def _tag(key: bytes, seq: int, nonce: bytes, ct: bytes) -> bytes:
    return hmac.new(key, _V.encode() + b"|" + seq.to_bytes(8, "big") + nonce + ct,
                    hashlib.sha256).digest()


def _encrypt(seq: int, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
    key = _keys()["payload"]
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct = bytes(a ^ b for a, b in zip(plaintext, _keystream(key, nonce, len(plaintext))))
    return nonce, ct, _tag(key, seq, nonce, ct)


def _decrypt(seq: int, nonce: bytes, ct: bytes, tag: bytes) -> bytes:
    key = _keys()["payload"]
    # compare_digest, not ==, so the check does not leak where the tag first
    # differs. And before the XOR, not after: a caller who gets plaintext back
    # alongside a "by the way, this failed" flag will use the plaintext.
    if not hmac.compare_digest(_tag(key, seq, nonce, ct), tag):
        raise LedgerTampered(f"payload for entry {seq} failed its authentication tag")
    return bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct))))


def _commit(plaintext: bytes) -> str:
    """The chain's commitment to a payload.

    An HMAC rather than a bare SHA-256, because this value outlives the
    payload: after redaction it is the only trace left, and it sits in the
    chain forever. A bare hash of a short payload - "approved", a recipient
    address, a yes/no - is a dictionary attack away from being the payload
    again, which would make redaction cosmetic for exactly the small, personal
    payloads that people ask to have forgotten.
    """
    return hmac.new(_keys()["commit"], plaintext, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------
#   Storage
# --------------------------------------------------------------------------

_INITED: set[str] = set()


def _connect() -> sqlite3.Connection:
    """Always inside `with closing(_connect()) as c:` - see the same note in
    jarvis_gate.py. `with sqlite3.connect(...)` commits, it does not close."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    key = str(DB_PATH)
    with _LOCK:
        if key in _INITED:
            return
        with closing(_connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS chain (
                    seq          INTEGER PRIMARY KEY,
                    ts           REAL NOT NULL,
                    event        TEXT NOT NULL,
                    meta         TEXT NOT NULL,      -- canonical JSON, hashed
                    turn         TEXT,               -- denormalised from meta, for why()
                    payload_hash TEXT,               -- HMAC commitment, NULL if no payload
                    payload_len  INTEGER,
                    prev_hash    TEXT NOT NULL,
                    entry_hash   TEXT NOT NULL,
                    state        TEXT NOT NULL,      -- none|present|redacted|expired
                    closed_at    REAL,               -- when redacted or expired
                    closed_why   TEXT
                )""")
            # Payloads are a separate table on purpose, not a column: dropping
            # one is a DELETE of a whole row, so there is no path where a
            # "redacted" payload is still sitting in a page of the chain table
            # waiting to be recovered by a forensics tool.
            c.execute("""
                CREATE TABLE IF NOT EXISTS payloads (
                    seq   INTEGER PRIMARY KEY,
                    kind  TEXT NOT NULL,             -- text|bytes|json
                    nonce BLOB NOT NULL,
                    ct    BLOB NOT NULL,
                    tag   BLOB NOT NULL
                )""")
            # One row. It is the cheap in-band answer to "was the tail cut
            # off"; the anchor file is the one that survives someone who knows
            # this table is here.
            c.execute("""
                CREATE TABLE IF NOT EXISTS ledger_head (
                    id   INTEGER PRIMARY KEY CHECK (id = 1),
                    seq  INTEGER NOT NULL,
                    hash TEXT NOT NULL,
                    ts   REAL NOT NULL
                )""")
            c.execute("CREATE INDEX IF NOT EXISTS chain_turn ON chain(turn)")
            c.execute("CREATE INDEX IF NOT EXISTS chain_ts ON chain(ts)")
        _INITED.add(key)


def _canonical(obj: Any) -> str:
    """One spelling of a JSON value, so a hash computed today and recomputed
    next year over the same data is the same hash."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _entry_hash(seq: int, ts: float, event: str, meta_json: str,
                payload_hash: Optional[str], prev_hash: str) -> str:
    body = _canonical([_V, seq, ts, event, meta_json, payload_hash or "", prev_hash])
    return hmac.new(_keys()["chain"], body.encode("utf-8"), hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------
#   Recording
# --------------------------------------------------------------------------

def _check_meta(meta: dict) -> dict:
    """Keep content out of the metadata.

    The split between chain and payload is only worth anything if callers
    honour it, and the reliable way to make them honour it is to refuse the
    record rather than to document the rule and hope. A long string in `meta`
    is almost always a body that belongs in `payload` - where it can be
    encrypted and later dropped - so it is rejected with an error that says
    so, instead of being quietly truncated into a half-record.
    """
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise ValueError("ledger metadata must be a dict")
    limit = int(_cfg("max_meta_value_chars", 500) or 500)

    def walk(node: Any, path: str) -> None:
        if isinstance(node, str) and len(node) > limit:
            raise ValueError(
                f"ledger metadata field {path!r} is {len(node)} chars, over the "
                f"{limit}-char limit; content belongs in the payload, which is "
                f"encrypted and can be redacted later")
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(meta, "")
    try:
        json.loads(_canonical(meta))
    except Exception as exc:
        raise ValueError(f"ledger metadata is not JSON-serialisable: {exc}") from exc
    return meta


def _as_bytes(payload: Any) -> tuple[str, bytes]:
    if isinstance(payload, bytes):
        return "bytes", payload
    if isinstance(payload, str):
        return "text", payload.encode("utf-8")
    return "json", _canonical(payload).encode("utf-8")


def record(event: str, meta: Optional[dict] = None, payload: Any = None) -> int:
    """Append one entry and return its sequence number.

    `meta` is the decision and is chained: action, tier, lane, the rule that
    fired, retrieved memory titles and times, what was skipped and why.
    `payload` is the content - the command, the mail body, the retrieved text -
    and is encrypted into a separate row that can be dropped on its own.

    Raises rather than swallowing failures; see LedgerUnavailable.
    """
    _init()
    meta = _check_meta(meta or {})
    meta_json = _canonical(meta)
    turn = meta.get(_turn_key())
    turn = str(turn) if turn is not None else None

    kind = None
    plain: Optional[bytes] = None
    payload_hash = None
    if payload is not None:
        kind, plain = _as_bytes(payload)
        cap = int(_cfg("max_payload_kb", 512) or 512) * 1024
        if len(plain) > cap:
            raise ValueError(f"ledger payload is {len(plain)} bytes, over the "
                             f"{cap}-byte max_payload_kb limit")
        payload_hash = _commit(plain)

    ts = time.time()
    with _LOCK:
        try:
            with closing(_connect()) as c:
                # IMMEDIATE, because reading the head and appending after it
                # must be one step. Two processes each reading seq 41 and each
                # writing seq 42 is not a race that shows up in testing and is
                # exactly the corruption this table cannot tolerate.
                c.execute("BEGIN IMMEDIATE")
                try:
                    row = c.execute("SELECT seq, entry_hash FROM chain "
                                    "ORDER BY seq DESC LIMIT 1").fetchone()
                    seq = (row["seq"] + 1) if row else 1
                    prev = row["entry_hash"] if row else _GENESIS
                    eh = _entry_hash(seq, ts, event, meta_json, payload_hash, prev)
                    c.execute(
                        "INSERT INTO chain (seq,ts,event,meta,turn,payload_hash,"
                        "payload_len,prev_hash,entry_hash,state) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (seq, ts, event, meta_json, turn, payload_hash,
                         len(plain) if plain is not None else None, prev, eh,
                         "present" if plain is not None else "none"))
                    if plain is not None:
                        nonce, ct, tag = _encrypt(seq, plain)
                        c.execute("INSERT INTO payloads (seq,kind,nonce,ct,tag) "
                                  "VALUES (?,?,?,?,?)", (seq, kind, nonce, ct, tag))
                    c.execute("INSERT INTO ledger_head (id,seq,hash,ts) VALUES (1,?,?,?) "
                              "ON CONFLICT(id) DO UPDATE SET seq=?,hash=?,ts=?",
                              (seq, eh, ts, seq, eh, ts))
                    c.execute("COMMIT")
                except Exception:
                    c.execute("ROLLBACK")
                    raise
        except sqlite3.Error as exc:
            raise LedgerUnavailable(f"ledger write failed: {exc}") from exc
    _maybe_anchor(seq)
    return seq


def _turn_key() -> str:
    return str(_cfg("turn_key", "turn") or "turn")


# --------------------------------------------------------------------------
#   Anchors
# --------------------------------------------------------------------------
# An append-only file opened in append mode is the practical version, not the
# strong one. O_APPEND stops this process from overwriting history by
# accident; it does nothing against a process that opens the same path with
# "w". The strong versions are a medium that physically cannot be rewritten -
# a line printer, a WORM bucket, an append-only log service on another
# machine - or simply a copy you take off this disk. What even the weak
# version buys is the window bound: to rewrite entry 300 undetectably, the
# rewrite has to also match every anchor you still hold that covers it, and
# anchors you have already copied elsewhere are not available to be matched.

def anchor() -> Optional[dict]:
    """Write the current head hash to the anchor file. Returns the anchor, or
    None if there is nothing to anchor yet."""
    _init()
    with closing(_connect()) as c:
        row = c.execute("SELECT seq, entry_hash FROM chain "
                        "ORDER BY seq DESC LIMIT 1").fetchone()
        count = c.execute("SELECT COUNT(*) AS n FROM chain").fetchone()["n"]
    if not row:
        return None
    rec = {"ts": time.time(), "seq": row["seq"], "head": row["entry_hash"],
           "count": count}
    # The MAC does not stop anyone who has the key from writing a convincing
    # anchor. It catches the other half of the problem: a truncated write, a
    # half-flushed line, a file someone edited by hand. Corruption and forgery
    # should not look the same in the report.
    rec["mac"] = hmac.new(_keys()["chain"], _canonical(
        [_V, "anchor", rec["ts"], rec["seq"], rec["head"], rec["count"]]
    ).encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        ANCHOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANCHOR_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as exc:
        _audit("ledger.anchor_failed", {"error": str(exc)})
        return None
    return rec


def _read_anchors() -> list[dict]:
    out = []
    try:
        text = ANCHOR_PATH.read_text("utf-8")
    except FileNotFoundError:
        return out
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            out.append({"bad": True, "line": line[:120]})
            continue
        want = hmac.new(_keys()["chain"], _canonical(
            [_V, "anchor", rec.get("ts"), rec.get("seq"), rec.get("head"),
             rec.get("count")]).encode("utf-8"), hashlib.sha256).hexdigest()
        rec["mac_ok"] = hmac.compare_digest(want, str(rec.get("mac", "")))
        out.append(rec)
    return out


def _maybe_anchor(seq: int) -> None:
    every = int(_cfg("anchor_every_entries", 25) or 0)
    minutes = float(_cfg("anchor_every_minutes", 60) or 0)
    if every > 0 and seq % every == 0:
        anchor()
        return
    if minutes > 0:
        try:
            last = ANCHOR_PATH.stat().st_mtime
        except Exception:
            last = 0.0
        if time.time() - last >= minutes * 60.0:
            anchor()


# --------------------------------------------------------------------------
#   Verification
# --------------------------------------------------------------------------

def verify(full: bool = False) -> dict:
    """Walk the chain and report what is wrong with it.

    Detects an edited metadata field, a deleted entry, a reordered entry, a
    truncated tail, and - with full=True, which opens every payload - a
    payload swapped for a different one.

    A redacted or expired payload is NOT tampering. It is a state the owner
    asked for, it is recorded as such, and it is reported separately: the
    whole point of splitting the chain from the payloads is that forgetting
    something does not have to look like an attack.

    full=False is the boot-time check: metadata chain, anchors, and whether
    each payload row is present when the entry says it should be. full=True
    additionally authenticates and decrypts every payload and re-derives its
    commitment, which reads the entire database.
    """
    _init()
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT seq,ts,event,meta,turn,payload_hash,payload_len,prev_hash,"
            "entry_hash,state,closed_at,closed_why FROM chain ORDER BY seq ASC"
        ).fetchall()
        head_row = c.execute("SELECT seq,hash,ts FROM ledger_head WHERE id=1").fetchone()
        have_payload = {r["seq"] for r in c.execute("SELECT seq FROM payloads").fetchall()}

    problems: list[dict] = []
    out = {"ok": True, "full": bool(full), "entries": len(rows),
           "first_seq": rows[0]["seq"] if rows else None,
           "last_seq": rows[-1]["seq"] if rows else None,
           "head": rows[-1]["entry_hash"] if rows else None,
           "redacted": 0, "expired": 0, "with_payload": 0,
           "anchors": 0, "anchors_ok": 0,
           "last_verified_seq": None, "last_verified_at": None,
           "truncated": False, "problems": problems,
           "checked_at": time.time()}
    if not rows:
        return out

    all_hashes = {r["entry_hash"] for r in rows}
    prev_row = None
    chain_intact_through = 0

    for i, r in enumerate(rows):
        seq = r["seq"]
        # 1. Gaps. A missing sequence number is the signature of a deleted
        # entry, and it is checked before the link so the report names the row
        # that is gone rather than the innocent row after it.
        expected = (prev_row["seq"] + 1) if prev_row is not None else rows[0]["seq"]
        if seq != expected:
            problems.append({"seq": expected, "code": "entry_deleted",
                             "detail": f"sequence jumps from {expected - 1} to {seq}"})

        # 2. The link. A row whose prev_hash points at an entry that exists
        # somewhere ELSE in the table has been moved; a row whose prev_hash
        # points at nothing at all is a break. The two deserve different words.
        if prev_row is not None and r["prev_hash"] != prev_row["entry_hash"]:
            if r["prev_hash"] in all_hashes:
                problems.append({"seq": seq, "code": "reordered",
                                 "detail": "this entry links to an entry that is "
                                           "not the one before it"})
            elif seq == expected:
                problems.append({"seq": seq, "code": "chain_broken",
                                 "detail": "prev_hash matches no entry in the ledger"})
        elif prev_row is None and r["prev_hash"] != _GENESIS and seq == 1:
            problems.append({"seq": seq, "code": "chain_broken",
                             "detail": "the first entry does not start from genesis"})

        # 3. The entry itself.
        want = _entry_hash(seq, r["ts"], r["event"], r["meta"], r["payload_hash"],
                           r["prev_hash"])
        if not hmac.compare_digest(want, r["entry_hash"]):
            # Only call it an edit if the row is otherwise where it belongs;
            # a moved row fails this too, and saying both is noise.
            if not any(p["seq"] == seq and p["code"] == "reordered" for p in problems):
                problems.append({"seq": seq, "code": "metadata_edited",
                                 "detail": "the stored hash does not match this "
                                           "entry's contents"})
        else:
            # The denormalised turn column is not inside the hash - it exists
            # so why() can use an index - so it gets its own check. Otherwise
            # editing it would move an entry to a different turn's trace while
            # the chain verified clean.
            try:
                mt = json.loads(r["meta"]).get(_turn_key())
                if (str(mt) if mt is not None else None) != r["turn"]:
                    problems.append({"seq": seq, "code": "index_edited",
                                     "detail": "the turn index does not match the "
                                               "entry's own metadata"})
            except Exception:
                problems.append({"seq": seq, "code": "metadata_edited",
                                 "detail": "metadata is not readable JSON"})

        # 4. Payload state.
        state = r["state"]
        if state == "redacted":
            out["redacted"] += 1
        elif state == "expired":
            out["expired"] += 1
        if state in ("redacted", "expired"):
            if seq in have_payload:
                problems.append({"seq": seq, "code": "payload_not_dropped",
                                 "detail": f"entry is marked {state} but its payload "
                                           f"is still stored"})
        elif state == "present":
            out["with_payload"] += 1
            if seq not in have_payload:
                # Distinct from redaction on purpose: a payload that is gone
                # without the entry recording WHY it is gone is a missing row,
                # not a decision anyone made.
                problems.append({"seq": seq, "code": "payload_missing",
                                 "detail": "entry claims a payload that is not stored"})
            elif full:
                problems.extend(_verify_payload(seq, r["payload_hash"]))

        if not any(p["seq"] == seq for p in problems):
            chain_intact_through = seq
        prev_row = r

    # 5. Truncation. Everything above walks what is there; nothing in it can
    # notice what is not. The recorded head and the anchors are the only two
    # things that know the chain used to be longer.
    last_seq = rows[-1]["seq"]
    if head_row and head_row["seq"] > last_seq:
        out["truncated"] = True
        problems.append({"seq": last_seq, "code": "truncated",
                         "detail": f"ledger ends at {last_seq}; the recorded head "
                                   f"is {head_row['seq']}"})
    elif head_row and head_row["seq"] == last_seq and \
            not hmac.compare_digest(str(head_row["hash"]), rows[-1]["entry_hash"]):
        problems.append({"seq": last_seq, "code": "head_mismatch",
                         "detail": "the recorded head hash is not this entry's hash"})

    by_seq = {r["seq"]: r["entry_hash"] for r in rows}
    for a in _read_anchors():
        out["anchors"] += 1
        if a.get("bad") or not a.get("mac_ok"):
            problems.append({"seq": a.get("seq"), "code": "anchor_unreadable",
                             "detail": "an anchor line is corrupt or not ours"})
            continue
        aseq, ahead = a.get("seq"), a.get("head")
        if aseq in by_seq:
            if hmac.compare_digest(str(by_seq[aseq]), str(ahead)):
                out["anchors_ok"] += 1
                if out["last_verified_seq"] is None or aseq > out["last_verified_seq"]:
                    out["last_verified_seq"] = aseq
                    out["last_verified_at"] = a.get("ts")
            else:
                problems.append({"seq": aseq, "code": "anchor_mismatch",
                                 "detail": "history was rewritten before this anchor"})
        elif aseq is not None and aseq > last_seq:
            out["truncated"] = True
            if not any(p["code"] == "truncated" for p in problems):
                problems.append({"seq": last_seq, "code": "truncated",
                                 "detail": f"ledger ends at {last_seq}; an anchor "
                                           f"covers {aseq}"})
        else:
            problems.append({"seq": aseq, "code": "anchor_mismatch",
                             "detail": "an anchored entry is no longer in the ledger"})

    out["intact_through"] = chain_intact_through
    out["ok"] = not problems
    if not out["ok"]:
        _audit("ledger.verify_failed", {"problems": len(problems),
                                        "codes": sorted({p["code"] for p in problems}),
                                        "entries": len(rows)})
    return out


def _verify_payload(seq: int, payload_hash: Optional[str]) -> list[dict]:
    try:
        plain = payload(seq, _raw=True)
    except LedgerTampered:
        return [{"seq": seq, "code": "payload_tampered",
                 "detail": "the stored payload failed its authentication tag"}]
    except Exception as exc:
        return [{"seq": seq, "code": "payload_unreadable", "detail": str(exc)}]
    if payload_hash and not hmac.compare_digest(_commit(plain), payload_hash):
        # The tag passed and the commitment did not: the payload authenticates
        # as ours but is not the one this entry was written about. Only
        # reachable by someone with the key, which is why it says "replaced"
        # rather than "corrupted".
        return [{"seq": seq, "code": "payload_replaced",
                 "detail": "the stored payload is not the one this entry commits to"}]
    return []


# --------------------------------------------------------------------------
#   Reading
# --------------------------------------------------------------------------

def payload(seq: int, _raw: bool = False):
    """The decrypted payload for one entry, or None if there never was one.

    Raises LedgerTampered if the authentication tag does not match, and
    LookupError if the payload was redacted or expired - "it is gone because
    you asked" and "it is gone and nobody knows why" must not come back as the
    same None.

    This is the ONLY function in this module that decrypts. why() and
    entries() do not, so the "why did you do that" view can be shown to
    anyone, or on a lock screen, without becoming a content viewer.
    """
    _init()
    with closing(_connect()) as c:
        row = c.execute("SELECT state, closed_at, closed_why FROM chain WHERE seq=?",
                        (seq,)).fetchone()
        if row is None:
            raise LookupError(f"no ledger entry {seq}")
        p = c.execute("SELECT kind,nonce,ct,tag FROM payloads WHERE seq=?",
                      (seq,)).fetchone()
    if p is None:
        if row["state"] in ("redacted", "expired"):
            raise LookupError(f"payload for entry {seq} was {row['state']} on "
                              f"{_day(row['closed_at'])}: {row['closed_why'] or ''}".strip())
        if row["state"] == "none":
            return None
        raise LookupError(f"payload for entry {seq} is missing")
    plain = _decrypt(seq, bytes(p["nonce"]), bytes(p["ct"]), bytes(p["tag"]))
    if _raw:
        return plain
    if p["kind"] == "text":
        return plain.decode("utf-8", "replace")
    if p["kind"] == "json":
        return json.loads(plain.decode("utf-8"))
    return plain


def _day(ts: Optional[float]) -> str:
    if not ts:
        return "an unrecorded date"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _row_to_flat(r: sqlite3.Row) -> dict:
    """One entry, flat and renderable, with no content in it."""
    try:
        meta = json.loads(r["meta"])
    except Exception:
        meta = {}
    state = r["state"]
    d = {"seq": r["seq"], "ts": r["ts"], "event": r["event"], "state": state,
         "turn": r["turn"], "meta": meta,
         "has_payload": state == "present",
         "payload_len": r["payload_len"],
         "redacted": state in ("redacted", "expired"),
         "closed_at": r["closed_at"], "closed_why": r["closed_why"],
         "note": ""}
    if state in ("redacted", "expired"):
        d["note"] = f"content removed {_day(r['closed_at'])} - decision preserved"
    return d


def entries(limit: int = 50, since: Optional[float] = None) -> list[dict]:
    """The most recent `limit` entries, oldest first, metadata only.

    `since` is a unix timestamp; entries at or after it are returned. Nothing
    here is decrypted - see payload()."""
    _init()
    sql = "SELECT seq,ts,event,meta,turn,payload_hash,payload_len,state,closed_at," \
          "closed_why FROM chain"
    args: list[Any] = []
    if since is not None:
        sql += " WHERE ts >= ?"
        args.append(float(since))
    sql += " ORDER BY seq DESC LIMIT ?"
    args.append(max(1, int(limit)))
    with closing(_connect()) as c:
        rows = c.execute(sql, args).fetchall()
    return [_row_to_flat(r) for r in reversed(rows)]


# --------------------------------------------------------------------------
#   The why-trace
# --------------------------------------------------------------------------

def why(turn_id: str) -> dict:
    """Everything recorded about one turn, as a flat dict a UI can render.

    Which lane the model ran in, which tier applied, what was retrieved - by
    title and time, never by content - what was skipped and why, and which
    rule fired. All of it is metadata, so all of it survives redaction: a row
    whose payload is gone still says what was decided and reads "content
    removed <date> - decision preserved".

    This module does no rendering. The shape is flat on purpose: lists of
    small dicts with stable keys, no nesting a template has to walk.
    """
    _init()
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT seq,ts,event,meta,turn,payload_hash,payload_len,state,closed_at,"
            "closed_why FROM chain WHERE turn=? ORDER BY seq ASC", (str(turn_id),)
        ).fetchall()

    out = {"turn": str(turn_id), "found": bool(rows), "steps": [],
           "lane": None, "tier": None, "action": None, "rule": None,
           "retrieved": [], "skipped": [], "rules": [],
           "started": None, "ended": None,
           "redacted_steps": 0, "with_payload": 0}
    if not rows:
        return out

    seen_retrieved = set()
    seen_skipped = set()
    for r in rows:
        flat = _row_to_flat(r)
        meta = flat["meta"]
        step = {"seq": flat["seq"], "ts": flat["ts"], "event": flat["event"],
                "action": meta.get("action"), "tier": meta.get("tier"),
                "lane": meta.get("lane"), "rule": meta.get("rule"),
                "reason": meta.get("reason"),
                "redacted": flat["redacted"], "has_payload": flat["has_payload"],
                "note": flat["note"]}
        out["steps"].append(step)
        if flat["redacted"]:
            out["redacted_steps"] += 1
        if flat["has_payload"]:
            out["with_payload"] += 1
        # Last writer wins for the single-valued fields: a turn that escalated
        # from local to a cloud lane, or from auto to ask, should show where it
        # ENDED UP. The steps list keeps the history for anyone who wants it.
        for k in ("lane", "tier", "action"):
            if meta.get(k):
                out[k] = meta[k]
        if meta.get("rule"):
            out["rule"] = meta["rule"]
            if meta["rule"] not in out["rules"]:
                out["rules"].append(meta["rule"])

        for m in meta.get("retrieved") or []:
            row = _memory_ref(m, flat["seq"])
            k = (row["title"], row["ts"])
            if k not in seen_retrieved:
                seen_retrieved.add(k)
                out["retrieved"].append(row)
        for m in meta.get("skipped") or []:
            row = _memory_ref(m, flat["seq"])
            k = (row["title"], row["ts"], row["why"])
            if k not in seen_skipped:
                seen_skipped.add(k)
                out["skipped"].append(row)

    out["started"] = rows[0]["ts"]
    out["ended"] = rows[-1]["ts"]
    return out


def _memory_ref(m: Any, seq: int) -> dict:
    """A retrieved or skipped memory, as title and time only.

    Deliberately lossy. If a caller puts the memory's text in here it does not
    get chained with the rest of the record and quietly become un-redactable;
    the fields that are kept are the ones agreed as safe to keep forever.
    """
    if not isinstance(m, dict):
        return {"title": str(m)[:200], "ts": None, "when": "", "id": None,
                "score": None, "why": "", "seq": seq}
    ts = m.get("ts") or m.get("time") or m.get("created")
    try:
        ts = float(ts) if ts is not None else None
    except (TypeError, ValueError):
        ts = None
    return {"title": str(m.get("title") or m.get("name") or "(untitled)")[:200],
            "ts": ts,
            "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "",
            "id": m.get("id"),
            "score": m.get("score"),
            "why": str(m.get("why") or m.get("reason") or "")[:200],
            "seq": seq}


# --------------------------------------------------------------------------
#   Forgetting: redaction and retention
# --------------------------------------------------------------------------

def redact(seq: int, reason: str = "") -> dict:
    """Drop one entry's payload. The chain is not touched and still verifies.

    The entry keeps its sequence number, its hash, its link to both
    neighbours, and its commitment to the payload that used to be there. What
    it loses is the content. Afterwards the row reads "content removed <date>
    - decision preserved", which is the honest thing for a record to say and
    the reason the chain was built over metadata in the first place.

    The redaction is itself recorded as a ledger entry, so "when did this get
    forgotten, and who asked" is answerable later. That entry names the target
    sequence number and the reason - not the content.
    """
    _init()
    now = time.time()
    with _LOCK:
        with closing(_connect()) as c:
            row = c.execute("SELECT state FROM chain WHERE seq=?", (seq,)).fetchone()
            if row is None:
                raise LookupError(f"no ledger entry {seq}")
            if row["state"] == "none":
                return {"seq": seq, "state": "none", "changed": False,
                        "note": "this entry never had a payload"}
            if row["state"] in ("redacted", "expired"):
                return {"seq": seq, "state": row["state"], "changed": False,
                        "note": "already removed"}
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute("DELETE FROM payloads WHERE seq=?", (seq,))
                c.execute("UPDATE chain SET state='redacted', closed_at=?, closed_why=? "
                          "WHERE seq=?", (now, (reason or "")[:400], seq))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
    record("ledger.redacted", {"target_seq": seq, "reason": (reason or "")[:200]})
    _audit("ledger.redacted", {"seq": seq})
    return {"seq": seq, "state": "redacted", "changed": True,
            "closed_at": now,
            "note": f"content removed {_day(now)} - decision preserved"}


def expire(before: Optional[float] = None) -> dict:
    """Drop the payloads of entries older than the retention window.

    Retention was the reviewer's unbudgeted item: without this, "the ledger
    keeps the content encrypted" quietly means "forever", and an encrypted
    copy of every command and every mail body from three years ago is a breach
    waiting for a key to leak.

    Expiry never removes an entry and never breaks the chain. Old history
    keeps verifying; it just stops holding content. `before` overrides the
    configured window for a caller that wants an explicit cutoff.
    """
    _init()
    if before is None:
        days = float(_cfg("retention_days", 30) or 0)
        if days <= 0:
            # A window of zero means "keep payloads indefinitely", which is a
            # legitimate choice for someone who wants the full record; it must
            # not be read as "expire everything immediately".
            return {"expired": 0, "cutoff": None, "freed_bytes": 0,
                    "note": "retention_days is 0; payloads are kept indefinitely"}
        before = time.time() - days * 86400.0
    now = time.time()
    with _LOCK:
        with closing(_connect()) as c:
            rows = c.execute(
                "SELECT c.seq, c.payload_len FROM chain c JOIN payloads p ON p.seq=c.seq "
                "WHERE c.ts < ? AND c.state='present'", (float(before),)).fetchall()
            if not rows:
                return {"expired": 0, "cutoff": before, "freed_bytes": 0, "note": ""}
            seqs = [r["seq"] for r in rows]
            freed = sum(r["payload_len"] or 0 for r in rows)
            c.execute("BEGIN IMMEDIATE")
            try:
                marks = ",".join("?" * len(seqs))
                c.execute(f"DELETE FROM payloads WHERE seq IN ({marks})", seqs)
                c.execute(f"UPDATE chain SET state='expired', closed_at=?, "
                          f"closed_why='retention window' WHERE seq IN ({marks})",
                          [now] + seqs)
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
    record("ledger.expired", {"count": len(seqs), "first_seq": seqs[0],
                              "last_seq": seqs[-1], "cutoff": before})
    _audit("ledger.expired", {"count": len(seqs)})
    return {"expired": len(seqs), "cutoff": before, "freed_bytes": freed,
            "first_seq": seqs[0], "last_seq": seqs[-1],
            "note": f"content removed {_day(now)} - decisions preserved"}


# --------------------------------------------------------------------------
#   Status
# --------------------------------------------------------------------------

def status() -> dict:
    """For the HUD and the desktop. Cheap - it does not verify anything."""
    _init()
    with closing(_connect()) as c:
        n = c.execute("SELECT COUNT(*) AS n FROM chain").fetchone()["n"]
        head = c.execute("SELECT seq,entry_hash,ts FROM chain "
                         "ORDER BY seq DESC LIMIT 1").fetchone()
        states = {r["state"]: r["n"] for r in c.execute(
            "SELECT state, COUNT(*) AS n FROM chain GROUP BY state").fetchall()}
        stored = c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(ct)),0) AS b "
                           "FROM payloads").fetchone()
    anchors = _read_anchors()
    last_anchor = next((a for a in reversed(anchors) if a.get("mac_ok")), None)
    return {
        "db": str(DB_PATH), "key": str(KEY_PATH), "anchors_file": str(ANCHOR_PATH),
        "entries": n,
        "head_seq": head["seq"] if head else None,
        "head": head["entry_hash"] if head else None,
        "head_ts": head["ts"] if head else None,
        "with_payload": states.get("present", 0),
        "no_payload": states.get("none", 0),
        "redacted": states.get("redacted", 0),
        "expired": states.get("expired", 0),
        "payload_rows": stored["n"], "payload_bytes": stored["b"],
        "anchors": len(anchors),
        "last_anchor_seq": (last_anchor or {}).get("seq"),
        "last_anchor_ts": (last_anchor or {}).get("ts"),
        # Reported rather than assumed. On a machine where the key file ended
        # up group-readable, a status line saying 0640 is the only way anyone
        # finds out.
        "key_mode": _key_mode(KEY_PATH),
        "config": {"retention_days": _cfg("retention_days", 30),
                   "anchor_every_entries": _cfg("anchor_every_entries", 25),
                   "anchor_every_minutes": _cfg("anchor_every_minutes", 60),
                   "max_payload_kb": _cfg("max_payload_kb", 512),
                   "max_meta_value_chars": _cfg("max_meta_value_chars", 500),
                   "turn_key": _turn_key()},
    }


# --------------------------------------------------------------------------
#   python jarvis_ledger.py [--verify | --full | --anchor | --why TURN]
# --------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--anchor" in args:
        print(json.dumps(anchor(), indent=1))
    elif "--why" in args:
        print(json.dumps(why(args[args.index("--why") + 1]), indent=1))
    elif "--verify" in args or "--full" in args:
        v = verify(full="--full" in args)
        print(json.dumps(v, indent=1))
        sys.exit(0 if v["ok"] else 1)
    else:
        s = status()
        print(f"\n  ledger   {s['db']}")
        print(f"  entries  {s['entries']}  (head {str(s['head'])[:16]} at seq "
              f"{s['head_seq']})")
        print(f"  payloads {s['with_payload']} stored, {s['redacted']} redacted, "
              f"{s['expired']} expired, {s['payload_bytes']} bytes")
        print(f"  anchors  {s['anchors']}, last at seq {s['last_anchor_seq']}")
        print(f"  key      {s['key']} mode {s['key_mode']}\n")
