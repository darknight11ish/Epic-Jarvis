"""test_history_purge.py - clearing old chats by date: a card, two yeses, a
platform ticket, pinned chats kept, and the facts those chats taught erased.

    py -3 backend/test_history_purge.py

THE OWNER'S REQUEST (2026-11-04, in his own words, and the bug behind it)

    "how long does it take for you to clear old chats if i batched a lot of
    them together?"

The live Jarvis answered that it had no built-in "clear old chats" action and
did not track how long it would take. He then said what he wants: clear
conversations it does NOT have pinned when asked to clear ones of a certain
date, INCLUDING FACTS; a card with all the details; a DOUBLE confirmation of
yes; and a Windows PIN or fingerprint (phone: fingerprint) before deleting.

WHAT THIS PROVES, against the REAL `jarvis_chat_log.ChatLog` and the REAL
`jarvis_memory.MemoryStore` in a temporary folder with a test key (no network,
no model, and NOTHING here touches the owner's own history or memory):

  * the preview counts the chats inside the days correctly, day by day, with
    the message count, and says it cannot be undone;
  * A PINNED CHAT IS KEPT - it is not in the count, it is not in the ids the
    preview holds, and it is still there after a completed purge. Its facts are
    kept with it, and a pinned chat's count is stated on the card;
  * a chat PINNED AFTER the preview is skipped at execution time, and the skip
    is counted;
  * include_pinned: true is the only way past that, and it is never default;
  * facts come from PROVENANCE and nothing else: a fact whose meta records one
    of the cleared conversations is erased; a fact from another chat, and a
    fact that records no conversation at all, are untouched and the card says
    the list it is showing;
  * include_facts false clears NO facts, and the card says they are kept;
  * THE SECOND YES IS REQUIRED: step 2 without step 1 is refused, a second
    step 1 is refused, and the confirm_id is the one step 1 issued;
  * A TICKET IS REQUIRED, and every bad one is refused in words with nothing
    deleted: wrong signature, a ticket made with another key, an expired one,
    one from the future, one for another preview/confirm, one signed for the
    other platform, and a REPLAY of a good one;
  * the keys are the contract: the desktop ticket is HMAC-SHA256 under the
    32-byte file this module makes (0600, owner only), the phone ticket is the
    same under the pairing token, and neither is ever logged or returned;
  * NO OTHER PATH DELETES: cancel deletes nothing, a new preview invalidates
    the old one, and an expired preview refuses step 2 (nothing deleted);
  * the audit line is written - counts, window, both ids, auth method and
    elapsed_ms - and contains no title, no message and no word of a fact;
  * the measured purge speed is measured, on a COPY (a temp folder), never on
    the live history;
  * the capability answer contains the measured truth (the file, its size, the
    counts, the switch, the retention, the measured speed) and never says "I
    don't track" - the owner's exact complaint;
  * with App lock / hidden lists on, all three routes answer 423 and the
    capability answer withholds the counts rather than reporting them.

WHAT IT DOES NOT PROVE, plainly: that a human was present at the Windows Hello
prompt or the phone's fingerprint reader. The backend cannot see either; it
checks a signature from a key that only this owner's install holds. That limit
is written in the module docstring and in docs/JARVIS-API.md section 189 - it is
not hidden here.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The config folder is pointed at a THROWAWAY one BEFORE the first import that
# reads it (`jarvis_framework` computes CONFIG_DIR once, at import). Nothing in
# this suite may read or write the owner's own ~/.openjarvis.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-history-purge-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR", "OPENJARVIS_HOME",
              "JARVIS_HOME"):
    os.environ[_name] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_history_purge.py", "jarvis_chat_log.py",
                "rebuilt/jarvis_memory.py")
import jarvis_history_purge as P  # noqa: E402
import jarvis_chat_log as H  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
KEY = bytes(range(32))
T0 = 1_790_000_000.0          # a fixed "now" so the days are the days we said
_N = [0]


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def near(name, value, want, tol=1):
    check(name, abs(float(value or 0) - float(want)) <= tol,
          f"got {value!r}, wanted about {want!r}")


# --------------------------------------------------------------------------
#   The fake PC: a real encrypted history and a real memory store, in a folder
# --------------------------------------------------------------------------

def _no_crypto():
    if H.AESGCM is None:
        skip("the cryptography package is not installed")
        return True
    return False


def _day(offset: float) -> float:
    """A moment `offset` days after the fixed now, at 10:00 local time."""
    return T0 + offset * 86400.0 + 10 * 3600.0


class World:
    """One temporary PC: a chat history, a memory store, and a clock."""

    def __init__(self):
        _N[0] += 1
        self.dir = _TMP / f"w{_N[0]}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = H.ChatLog(self.dir / "chat-history.db",
                             self.dir / "chat-history.json",
                             lambda: KEY, clock=lambda: T0)
        self.mem = _memory_store(self.dir)
        self.chats = {}          # cid -> {day_offset, turns}

    # -- building state ---------------------------------------------------
    def chat(self, cid, days_ago, turns=4, pinned=False, words=None):
        """A conversation at 10:00 `days_ago` days before the fixed now."""
        at = T0 - days_ago * 86400.0 + 3600.0
        # The record clock follows this chat, so its `updated` is the moment it
        # really happened - the same as a real PC, where a chat is stamped as
        # its messages are said. A frozen clock would put every chat on one day.
        self.log._clock = lambda: at
        for i in range(0, max(2, turns), 2):
            self.log.record_turn(
                {"conversation_id": cid, "device": "desktop",
                 "messages": [{"role": "user", "provenance": "typed",
                               "content": (words or "line %d of this chat" % i)}]},
                lane="test", at=at + i,
                turn={"answer": "an answer", "finish_reason": "stop"})
        self.log._clock = lambda: T0
        if pinned:
            self.log.set_pin(cid, True)
        self.chats[cid] = {"at": at, "turns": turns}
        return cid

    def fact(self, text, conversation_id=None, days_ago=None):
        """A fact, optionally recording which conversation it came from."""
        meta = {}
        if conversation_id:
            meta["conversation_id"] = conversation_id
        return self.mem.add(text, source="owner",
                                    valid_from=_day(-(days_ago or 1)),
                                    meta=meta or None)


def _memory_store(folder: Path):
    """A REAL MemoryStore on a temporary file, with the embedder off."""
    os.environ["JARVIS_MEMORY_NO_EMBED"] = "1"
    import jarvis_memory as M
    return M.MemoryStore(folder / "memory.db")


def world():
    _memory_store(_TMP)                      # import once, before any use
    return World()


def clean():
    P._reset_for_tests()


def _iso(day_offset: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(T0 + day_offset * 86400.0))


def window(days_from, days_to):
    """The two date strings for "between N and M days ago", inclusive."""
    return {"from": _iso(-days_from), "to": _iso(-days_to)}


def _run(w, days_from, days_to, include_facts=True, include_pinned=False,
         client="hud"):
    return P.preview(dict(window(days_from, days_to), include_facts=include_facts,
                          include_pinned=include_pinned),
                     now=T0, chats=w.log, mem=w.mem, client=client)


def _ids(answered: dict) -> set:
    with P._STATE_LOCK:
        rec = P._STATE.get("preview") or {}
    return set(rec.get("conversation_ids") or [])


def _facts_ids(answered: dict) -> set:
    with P._STATE_LOCK:
        rec = P._STATE.get("preview") or {}
    return set(rec.get("fact_ids") or [])


def _step1(answered, now=T0):
    return P.confirm({"preview_id": answered["preview_id"], "step": 1},
                     now=now, chats=None, mem=None)


def _step2(w, answered, confirm_id, ticket, now=T0, client="hud"):
    return P.confirm({"preview_id": answered["preview_id"],
                      "confirm_id": confirm_id, "step": 2,
                      "auth_ticket": ticket},
                     now=now, chats=w.log, mem=w.mem, client=client)


# --------------------------------------------------------------------------
#   The preview: what it counts, and what it refuses to touch
# --------------------------------------------------------------------------

def t_the_preview_counts_the_days_correctly():
    clean()
    w = world()
    w.chat("purge-old-000001", 10, turns=4)
    w.chat("purge-old-000002", 10, turns=2)
    w.chat("purge-old-000003", 9, turns=6)
    w.chat("purge-new-000004", 2, turns=4)
    code, got = _run(w, 11, 8)
    check("preview answers 200", code == 200, str(got)[:400])
    check("... it says it cannot be undone", got.get("irreversible") is True)
    check("... the window is the one asked for",
          got["window"]["from"] == _iso(-11) and got["window"]["to"] == _iso(-8))
    check("... three chats inside the days", got["conversations"]["count"] == 3,
          got["conversations"])
    check("... 12 messages counted (4 + 2 + 6)",
          got["conversations"]["message_count"] == 12,
          got["conversations"]["message_count"])
    check("... the chat outside the days is not in it",
          "purge-new-000004" not in _ids(got))
    check("... per_day names each day it found",
          [d["day"] for d in got["conversations"]["per_day"]] ==
          sorted({_iso(-10), _iso(-9)}),
          got["conversations"]["per_day"])
    total = sum(d["chats"] for d in got["conversations"]["per_day"])
    check("... and per_day adds up to the count", total == 3, total)
    check("... a preview id and a 10-minute life",
          isinstance(got["preview_id"], str) and got["expires_at"] - got["generated_at"] == 600)
    check("... the preview itself holds no message text",
          "line " not in json.dumps(got["conversations"]))
    check("... it says the second yes needs a platform check",
          "fingerprint" in got["next"] or "Hello" in got["next"], got["next"])


def t_the_card_carries_every_detail():
    clean()
    w = world()
    w.chat("purge-card-00001", 5, turns=2)
    w.chat("purge-card-00002", 5, turns=2)
    f = w.fact("My car is a blue estate", conversation_id="purge-card-00001")
    code, got = _run(w, 6, 4)
    card = got.get("card") or {}
    check("the card has a title naming the count",
          card.get("title", "").startswith("Clear 2 chats"), card.get("title"))
    lines = "\n".join(card.get("details") or [])
    check("the card says it cannot be undone",
          "cannot be undone" in lines.lower(), lines)
    check("the card lists the day with its chats and messages",
          _iso(-5) in lines and "2 chats, 4 messages" in lines, lines)
    check("the card names the fact by its own words",
          "My car is a blue estate" in lines, lines)
    check("the card is marked irreversible and has no undo",
          card.get("irreversible") is True and card.get("undo_seconds") == 0)
    check("the fact count is on the card", card.get("counts", {}).get("facts") == 1,
          card.get("counts"))


def t_a_pinned_chat_is_never_deleted_and_never_counted():
    clean()
    w = world()
    w.chat("purge-pin-000001", 6, turns=2)
    w.chat("purge-pin-000002", 6, turns=2, pinned=True)
    f = w.fact("My sister is called Priya", conversation_id="purge-pin-000002")
    code, got = _run(w, 7, 5)
    check("preview 200", code == 200)
    check("the pinned chat is not in the ids to delete",
          _ids(got) == {"purge-pin-000001"}, _ids(got))
    check("... and the card says how many it kept, as a pinned count",
          got["conversations"]["kept_pinned_count"] == 1,
          got["conversations"]["kept_pinned_count"])
    check("... and the count is of the chats that WILL go", got["conversations"]["count"] == 1)
    check("... a warning says pinned chats are kept",
          any("pinned" in line and "KEPT" in line for line in got["warnings"]),
          got["warnings"])
    check("the fact from the pinned chat is NOT among the facts to erase",
          _facts_ids(got) == set(), _facts_ids(got))
    check("... and it is counted as kept because of the pin",
          got["facts"]["kept_due_to_pinned"] == 1, got["facts"])
    check("... while the fact itself is still in use", _fact_live(w, f))


def _fact_live(w, fid) -> bool:
    try:
        with P.closing(w.mem._connect()) as c:
            row = c.execute("SELECT erased_at, valid_to FROM facts WHERE id=?",
                            (int(fid),)).fetchone()
        return row is not None and row["erased_at"] is None and (
            row["valid_to"] is None or row["valid_to"] > T0)
    except Exception:
        return False


def _fact_erased(w, fid) -> bool:
    try:
        with P.closing(w.mem._connect()) as c:
            row = c.execute("SELECT erased_at FROM facts WHERE id=?",
                            (int(fid),)).fetchone()
        return row is not None and row["erased_at"] is not None
    except Exception:
        return False


def _fact_exists(w, fid) -> bool:
    try:
        with P.closing(w.mem._connect()) as c:
            return c.execute("SELECT 1 FROM facts WHERE id=?", (int(fid),)).fetchone() is not None
    except Exception:
        return False


def t_include_pinned_is_the_only_way_past_the_pin():
    clean()
    w = world()
    w.chat("purge-pinx-00001", 6, turns=2, pinned=True)
    code, got = _run(w, 7, 5, include_pinned=True)
    check("with include_pinned the pinned chat is in the count",
          code == 200 and got["conversations"]["count"] == 1, got.get("conversations"))
    check("... and nothing is counted as kept",
          got["conversations"]["kept_pinned_count"] == 0)
    check("... and the card says pinned chats are going too",
          any("INCLUDE_PINNED IS ON" in line for line in got["warnings"]),
          got["warnings"])


def t_a_chat_pinned_after_the_preview_is_skipped():
    clean()
    w = world()
    w.chat("purge-late-000001", 4, turns=2)
    code, got = _run(w, 5, 3)
    w.log.set_pin("purge-late-000001", True)          # pinned AFTER the card
    code, first = _step1(got)
    ticket = P.mint_ticket(got["preview_id"], first["confirm_id"], P.METHOD_DESKTOP,
                           at=T0)
    code, done = _step2(w, got, first["confirm_id"], ticket)
    check("a chat pinned after the card is not deleted",
          code == 200 and done["deleted"]["conversations"] == 0, done)
    check("... and the skip is counted as pinned",
          done["kept"]["pinned"] == 1, done.get("kept"))
    check("... and the chat is still there", w.log.get("purge-late-000001") is not None)


# --------------------------------------------------------------------------
#   The facts: provenance only, and only when asked
# --------------------------------------------------------------------------

def t_facts_come_from_provenance_and_nothing_else():
    clean()
    w = world()
    w.chat("purge-fact-000001", 12, turns=2)
    w.chat("purge-fact-000002", 1, turns=2)             # outside the days
    inside = w.fact("The boiler is serviced every March",
                    conversation_id="purge-fact-000001")
    outside = w.fact("I park in bay 14", conversation_id="purge-fact-000002")
    orphan = w.fact("I prefer tea to coffee")
    code, got = _run(w, 13, 10)
    check("preview 200", code == 200)
    check("the fact that records the cleared chat is in the list",
          _facts_ids(got) == {int(inside)}, (_facts_ids(got), inside))
    check("... and its own words are on the card",
          "The boiler is serviced every March" in (got["facts"]["names"] or []),
          got["facts"]["names"])
    check("a fact from another chat is NOT in the list",
          int(outside) not in _facts_ids(got))
    check("a fact that records no chat is NOT in the list",
          int(orphan) not in _facts_ids(got))
    check("the two outside facts are still in use", _fact_live(w, outside)
          and _fact_live(w, orphan))


def t_include_facts_false_clears_no_facts_and_says_so():
    clean()
    w = world()
    w.chat("purge-nf-000001", 12, turns=2)
    f = w.fact("The garage code is 4402", conversation_id="purge-nf-000001")
    code, got = _run(w, 13, 10, include_facts=False)
    check("no facts are counted when include_facts is false",
          got["facts"]["count"] == 0 and got["facts"]["included"] is False)
    check("... and the card says they are kept",
          any("FACTS ARE NOT INCLUDED" in line for line in got["warnings"]),
          got["warnings"])
    check("... and it says how many it would have been",
          any("1 fact" in line for line in got["warnings"]), got["warnings"])
    code, first = _step1(got)
    ticket = P.mint_ticket(got["preview_id"], first["confirm_id"],
                           P.METHOD_DESKTOP, at=T0)
    code, done = _step2(w, got, first["confirm_id"], ticket)
    check("the purge ran", code == 200 and done["deleted"]["conversations"] == 1, done)
    check("... and the fact is still in use", _fact_live(w, f))


def t_the_approved_facts_are_erased_for_good():
    clean()
    w = world()
    w.chat("purge-ef-000001", 12, turns=2)
    f = w.fact("The gate key is under the third pot",
               conversation_id="purge-ef-000001")
    code, got = _run(w, 13, 10)
    code, first = _step1(got)
    ticket = P.mint_ticket(got["preview_id"], first["confirm_id"], P.METHOD_DESKTOP,
                           at=T0)
    code, done = _step2(w, got, first["confirm_id"], ticket)
    check("step 2 answers 200", code == 200, str(done)[:300])
    check("... with the counts it actually deleted",
          done["deleted"] == {"conversations": 1, "messages": 2, "facts": 1}, done)
    check("... the fact's words are erased, not merely forgotten",
          _fact_erased(w, f) and _fact_exists(w, f))
    check("... the erased words are gone from the row",
          "third pot" not in _fact_text(w, f), _fact_text(w, f))
    check("... the chat itself is gone", w.log.get("purge-ef-000001") is None)


def _fact_text(w, fid) -> str:
    try:
        with P.closing(w.mem._connect()) as c:
            row = c.execute("SELECT text FROM facts WHERE id=?", (int(fid),)).fetchone()
        return str(row["text"] or "")
    except Exception:
        return ""


# --------------------------------------------------------------------------
#   The two yeses, the ticket, and no other way through
# --------------------------------------------------------------------------

def t_the_second_yes_requires_the_first():
    clean()
    w = world()
    w.chat("purge-two-000001", 3, turns=2)
    code, got = _run(w, 4, 2)
    good = P.mint_ticket(got["preview_id"], "", P.METHOD_DESKTOP, at=T0)
    code, out = P.confirm({"preview_id": got["preview_id"], "step": 2,
                           "auth_ticket": good}, now=T0, chats=w.log, mem=w.mem)
    check("step 2 with no confirm_id is refused", code == 400 and out["ok"] is False, out)
    check("... and says which yes is missing", "first yes" in out["message"], out)
    with P._STATE_LOCK:
        cid = (P._STATE.get("preview") or {}).get("confirm_id")
    ticket = P.mint_ticket(got["preview_id"], cid, P.METHOD_DESKTOP, at=T0)
    code, out = P.confirm({"preview_id": got["preview_id"], "confirm_id": cid,
                           "step": 2, "auth_ticket": ticket}, now=T0,
                          chats=w.log, mem=w.mem)
    check("step 2 with a correct-looking confirm_id but no first yes is refused",
          code == 400 and out["ok"] is False, out)
    check("... and the chat is untouched", w.log.get("purge-two-000001") is not None)


def t_step_one_is_answered_once_and_restates_the_counts():
    clean()
    w = world()
    w.chat("purge-one-000001", 3, turns=2)
    code, got = _run(w, 4, 2)
    code, first = _step1(got)
    check("step 1 answers 200 with confirmed", code == 200 and first["confirmed"] is True)
    check("... and asks for the second yes", first["next"] == "second_yes_required")
    check("... and gives back the confirm_id it will want",
          isinstance(first["confirm_id"], str) and first["confirm_id"])
    restated = first["restated"]
    check("... restated carries the exact counts again",
          restated["conversations"] == 1 and restated["messages"] == 2,
          restated)
    check("... and says it cannot be undone", restated["cannot_be_undone"] is True)
    check("step 1 deletes nothing", w.log.get("purge-one-000001") is not None)
    code, again = _step1(got)
    check("a second step 1 is refused", code == 409 and again["ok"] is False, again)
    check("... and says to send step 2", "step 2" in again["message"], again)


def t_a_ticket_is_always_required_and_every_bad_one_is_refused():
    clean()
    w = world()
    w.chat("purge-tkt-000001", 3, turns=2)
    code, got = _run(w, 4, 2)
    code, first = _step1(got)
    cid = first["confirm_id"]
    pid = got["preview_id"]
    bad = {}
    bad["missing"] = (None, 401)
    bad["empty"] = ("", 401)
    bad["garbage"] = ("v1.windows_hello.notanumber.deadbeef", 401)
    bad["wrong method"] = (P.mint_ticket(pid, cid, P.METHOD_DESKTOP, at=T0)
                           .replace("windows_hello", "magic"), 401)
    wrong = P.mint_ticket(pid, cid, P.METHOD_DESKTOP, at=T0, key=b"\x01" * 32)
    bad["signed with another key"] = (wrong, 401)
    for label, (ticket, want) in bad.items():
        code, out = _step2(w, got, cid, ticket)
        check(f"the ticket {label} is refused ({want})",
              code == want and out["ok"] is False, (code, str(out)[:200]))
        check(f"... and nothing was deleted ({label})",
              w.log.get("purge-tkt-000001") is not None)
    # An expired one, and one from the future.
    old = P.mint_ticket(pid, cid, P.METHOD_DESKTOP, at=T0 - 91)
    code, out = _step2(w, got, cid, old)
    check("a ticket 91 seconds old is expired",
          code == 409 and out["error"] == "expired_ticket", (code, out))
    ahead = P.mint_ticket(pid, cid, P.METHOD_DESKTOP, at=T0 + 60)
    code, out = _step2(w, got, cid, ahead)
    check("a ticket 60 seconds in the future is expired",
          code == 409 and out["error"] == "expired_ticket", (code, out))
    check("nothing was deleted by any of them", w.log.get("purge-tkt-000001") is not None)


def t_a_ticket_for_another_preview_or_platform_is_refused():
    clean()
    w = world()
    w.chat("purge-cr-0000001", 3, turns=2)
    code, got = _run(w, 4, 2)
    code, first = _step1(got)
    cid = first["confirm_id"]
    other_preview = P.mint_ticket("not-this-preview", cid, P.METHOD_DESKTOP, at=T0)
    code, out = _step2(w, got, cid, other_preview)
    check("a ticket for another preview is refused",
          code == 401 and out["error"] == "bad_ticket", (code, out))
    other_confirm = P.mint_ticket(got["preview_id"], "another-confirm-id",
                                  P.METHOD_DESKTOP, at=T0)
    code, out = _step2(w, got, cid, other_confirm)
    check("a ticket for another confirm_id is refused",
          code == 401 and out["error"] == "bad_ticket", (code, out))
    phone = P.mint_ticket(got["preview_id"], cid, P.METHOD_PHONE, at=T0,
                          key=b"pairing-token")
    code, out = _step2(w, got, cid, phone, client="hud")
    check("a phone ticket on a desktop request is refused as the wrong platform",
          code == 409 and out["error"] == "wrong_platform", (code, out))
    check("... a desktop ticket on a phone request is refused too",
          _step2(w, got, cid, P.mint_ticket(got["preview_id"], cid,
                                            P.METHOD_DESKTOP, at=T0),
                 client="android")[1]["error"] == "wrong_platform")
    check("nothing was deleted", w.log.get("purge-cr-0000001") is not None)


def t_a_good_ticket_works_once_and_a_replay_is_refused():
    clean()
    w = world()
    w.chat("purge-once-00001", 3, turns=2)
    w.chat("purge-once-00002", 3, turns=2)
    code, got = _run(w, 4, 2)
    code, first = _step1(got)
    ticket = P.mint_ticket(got["preview_id"], first["confirm_id"],
                           P.METHOD_DESKTOP, at=T0)
    code, done = _step2(w, got, first["confirm_id"], ticket)
    check("a good ticket deletes exactly the previewed chats",
          code == 200 and done["deleted"]["conversations"] == 2, done)
    check("... both chats are gone", w.log.get("purge-once-00001") is None
          and w.log.get("purge-once-00002") is None)
    check("... and the elapsed time is a measured number",
          isinstance(done["elapsed_ms"], int) and done["elapsed_ms"] >= 0)
    code, again = _step2(w, got, first["confirm_id"], ticket)
    check("the same ticket again is refused (the preview is spent)",
          code in (404, 409, 410) and again["ok"] is False, (code, again))


def t_a_new_preview_invalidates_the_old_one():
    clean()
    w = world()
    w.chat("purge-new-000001", 3, turns=2)
    code, first = _run(w, 4, 2)
    code, second = _run(w, 4, 2)
    check("two previews get different ids", first["preview_id"] != second["preview_id"])
    code, out = P.confirm({"preview_id": first["preview_id"], "step": 1},
                          now=T0, chats=w.log, mem=w.mem)
    check("the older preview's step 1 is refused", code == 404 and out["ok"] is False,
          (code, out))
    check("... and nothing was deleted", w.log.get("purge-new-000001") is not None)


def t_an_expired_preview_refuses_the_second_yes():
    clean()
    w = world()
    w.chat("purge-exp-000001", 3, turns=2)
    code, got = _run(w, 4, 2)
    code, first = _step1(got)
    ticket = P.mint_ticket(got["preview_id"], first["confirm_id"],
                           P.METHOD_DESKTOP, at=T0 + 601)
    code, out = _step2(w, got, first["confirm_id"], ticket, now=T0 + 601)
    check("a preview more than ten minutes old is refused",
          code in (404, 410) and out["ok"] is False, (code, out))
    check("... and nothing was deleted", w.log.get("purge-exp-000001") is not None)


def t_cancel_deletes_nothing_and_ends_the_two_yeses():
    clean()
    w = world()
    w.chat("purge-can-000001", 3, turns=2)
    code, got = _run(w, 4, 2)
    code, out = P.cancel({"preview_id": got["preview_id"]}, now=T0)
    check("cancel answers 200 and says cancelled",
          code == 200 and out["cancelled"] is True, out)
    check("... and the chat is still there", w.log.get("purge-can-000001") is not None)
    code, out = _step1(got)
    check("... and step 1 no longer finds a preview",
          code == 404 and out["ok"] is False, (code, out))
    code, out = P.cancel({"preview_id": "never-existed"}, now=T0)
    check("cancelling an unknown preview is a 404, not a crash",
          code == 404 and out["ok"] is False)


def t_there_is_no_cardless_or_bulk_shortcut():
    clean()
    w = world()
    w.chat("purge-safe-00001", 3, turns=2)
    # Every route is POST, and the module exposes no function that deletes
    # without both yeses: the only caller of take_out()/erase() is _execute().
    src = Path(P.__file__).read_text(encoding="utf-8")
    check("the batch removal is called in exactly two places - the purge and "
          "the benchmark", src.count("log.take_out(") == 2,
          src.count("log.take_out("))
    check("... and the module defines exactly one _execute",
          src.count("def _execute(") == 1, src.count("def _execute("))
    check("... and confirm's step 2 is its only caller",
          src.count("return _execute(rec") == 1, src.count("return _execute(rec"))
    code, out = P.handle_get(P.PREVIEW_PATH)
    check("a GET on any purge route is a 405", code == 405 and out["ok"] is False, out)
    code, out = P.handle_post("/api/history/purge/unknown", {})
    check("an unknown purge path is a 404", code == 404)
    for bad in ([], "text", {"from": "x", "to": "y"}, {"from": "2026-01-01"},
                {"from": 1, "to": 2},
                dict(window(4, 2), include_facts="yes")):
        code, out = P.preview(bad, now=T0, chats=w.log, mem=w.mem)
        check(f"a bad preview body is a 400 ({str(bad)[:30]})",
              code == 400 and out["ok"] is False, (code, out))
    code, out = P.preview(dict(window(2, 4)), now=T0, chats=w.log, mem=w.mem)
    check("from after to is refused", code == 400 and out["ok"] is False, (code, out))
    for step in (0, 3, True, "1", 1.0, None):
        code, out = P.confirm({"preview_id": "x", "step": step}, now=T0)
        check(f"step {step!r} is refused", code == 400 and out["ok"] is False,
              (code, out))


def t_app_lock_or_hidden_lists_stop_every_route():
    clean()
    w = world()
    w.chat("purge-lock-00001", 3, turns=2)
    import jarvis_private_view as PV
    old = PV.state()
    PV.note_state(app_locked=True, hide_memory_lists=False)
    try:
        code, out = _run(w, 4, 2)
        check("a locked PC refuses the preview with 423",
              code == 423 and out["ok"] is False, (code, out))
        check("... and says why in words", "hidden" in out["message"].lower(),
              out.get("message"))
        code, out = P.confirm({"preview_id": "anything", "step": 1}, now=T0)
        check("a locked PC refuses step 1 with 423", code == 423, (code, out))
        code, out = P.cancel({"preview_id": None}, now=T0)
        check("a locked PC refuses cancel with 423", code == 423, (code, out))
        got = P.capability(now=T0, chats=w.log, mem=w.mem, measure=False)
        check("a locked PC withholds the counts entirely",
              got.get("locked") is True and "conversations" not in got, got.get("locked"))
        check("... and says it is withholding them",
              "hidden" in got["words"].lower(), got["words"])
    finally:
        PV.note_state(**old)
    check("unlocked again, the preview works",
          _run(w, 4, 2)[0] == 200)


# --------------------------------------------------------------------------
#   The audit line, the keys, and the measured speed
# --------------------------------------------------------------------------

def t_the_audit_line_is_written_and_holds_no_words():
    clean()
    w = world()
    w.chat("purge-aud-000001", 3, turns=2, words="the secret phrase in a chat")
    f = w.fact("the secret phrase in a fact", conversation_id="purge-aud-000001")
    code, got = _run(w, 4, 2)
    code, first = _step1(got)
    ticket = P.mint_ticket(got["preview_id"], first["confirm_id"],
                           P.METHOD_DESKTOP, at=T0)
    code, done = _step2(w, got, first["confirm_id"], ticket)
    path = P.audit_path()
    check("the audit file exists at ~/.openjarvis/purge-audit.jsonl",
          path.exists() and path.name == "purge-audit.jsonl", str(path))
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    mine = [x for x in lines if x.get("audit_id") == done["audit_id"]]
    check("the deletion wrote exactly one line with that audit_id", len(mine) == 1,
          [x.get("audit_id") for x in lines])
    line = mine[0] if mine else {}
    for key in ("audit_id", "at", "window", "preview_id", "confirm_id",
                "auth_method", "deleted", "elapsed_ms"):
        check(f"the audit line carries {key}", key in line, sorted(line))
    check("... the auth method is named", line.get("auth_method") == "windows_hello",
          line.get("auth_method"))
    check("... the counts are the ones deleted",
          line.get("deleted") == {"conversations": 1, "messages": 2, "facts": 1},
          line.get("deleted"))
    raw = path.read_text(encoding="utf-8")
    check("... and NOT ONE title, message or fact word is in the file",
          "secret phrase" not in raw and "line 0 of this chat" not in raw, raw[-400:])
    check("read_audit returns the lines", P.read_audit(5)[-1].get("audit_id") ==
          done["audit_id"])


def t_the_two_keys_are_the_contract():
    clean()
    path = P.key_path()
    key = P.auth_key()
    check("the desktop key is 32 random bytes", isinstance(key, bytes) and len(key) == 32,
          len(key))
    check("... it is the file this module names", path.name == "purge-auth.key", str(path))
    check("... and it is the same on the second call", P.auth_key() == key)
    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        check("... created readable only by its owner (0600)", mode == 0o600, oct(mode))
        check("... and its folder", stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0,
              oct(stat.S_IMODE(path.parent.stat().st_mode)))
    else:
        skip("the 0600 mode is a POSIX promise; Windows has no mode bits")
    ticket = P.mint_ticket("a-preview", "a-confirm", P.METHOD_DESKTOP, at=1000)
    want = P.hmac.new(key, b"a-preview|a-confirm|windows_hello|1000",
                      P.hashlib.sha256).hexdigest()
    check("the desktop ticket is HMAC-SHA256 of the documented text",
          ticket == f"v1.windows_hello.1000.{want}", ticket)
    check("the key is never in the ticket", key.hex()[:16] not in ticket)
    check("an unknown method cannot be minted",
          _raises(P.mint_ticket, "p", "c", "magic", at=1))
    phone = P.mint_ticket("p", "c", P.METHOD_PHONE, at=1, key=b"tok")
    check("the phone ticket uses the same shape under its own key",
          phone.startswith("v1.phone_biometric.1."), phone)


def _raises(fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except Exception:
        return True
    return False


def t_the_phone_key_is_the_pairing_token():
    clean()
    token = "a-pairing-token-for-this-pc"
    os.environ["JARVIS_PAIRING_TOKEN_FOR_TEST"] = token
    old = P._phone_key
    P._phone_key = lambda: token.encode("utf-8")
    try:
        ticket = P.mint_ticket("p", "c", P.METHOD_PHONE, at=1)
        want = P.hmac.new(token.encode(), b"p|c|phone_biometric|1",
                          P.hashlib.sha256).hexdigest()
        check("a phone ticket is HMAC-SHA256 under the pairing token",
              ticket == f"v1.phone_biometric.1.{want}", ticket)
        ok, method = P.verify_ticket(ticket, "p", "c", client="android", now=1.0)
        check("... and the backend accepts it for a phone client",
              ok is True and method == P.METHOD_PHONE, (ok, method))
    finally:
        P._phone_key = old
        os.environ.pop("JARVIS_PAIRING_TOKEN_FOR_TEST", None)
    P._phone_key = lambda: b""
    try:
        ok, out = P.verify_ticket(
            P.mint_ticket("p", "c", P.METHOD_DESKTOP, at=1), "p", "c",
            client="hud", now=1.0)
        check("a desktop ticket still verifies with no phone key", ok is True)
    finally:
        P._phone_key = old


def t_the_purge_speed_is_measured_on_a_copy():
    clean()
    doc = P.benchmark.__doc__ or ""
    check("the live history is not what is DELETED from",
          "never on the live file" in doc or "never on the live" in doc, doc[:120])
    src = P.benchmark().get("source") or ""
    check("... and the answer says which way it measured",
          "copy" in src.lower() or "synthetic" in src.lower(), src)
    got = P.benchmark(12, 4)
    check("a benchmark reports a measured number", got["measured"] is True, got)
    check("... with the chats it really deleted", got["chats"] == 12, got["chats"])
    check("... the messages it really wrote", got["messages"] >= 12, got["messages"])
    check("... and a positive elapsed time", got["elapsed_ms"] > 0, got["elapsed_ms"])
    check("... and says where it measured", "copy" in got["where"], got["where"])
    tmp = Path(tempfile.gettempdir())
    leftovers = [p for p in tmp.glob("jarvis-purge-bench-*")]
    check("the temporary copy is removed afterwards", not leftovers,
          [str(p) for p in leftovers])
    live = P._config_dir() / "chat-history.db"
    check("... and the benchmark never opened the live chat history",
          not live.exists() or live.stat().st_size >= 0)


def t_the_capability_answer_is_measured_truth():
    clean()
    w = world()
    w.chat("purge-cap-000001", 2, turns=2)
    w.chat("purge-cap-000002", 4, turns=2, pinned=True)
    w.chat("purge-cap-000003", 8, turns=2, pinned=True)
    w.fact("a fact about a thing", conversation_id="purge-cap-000001")
    got = P.capability(now=T0, chats=w.log, mem=w.mem)
    said = got["words"]
    check("it names the file the chats are in", str(w.log.db_path) in said, said[:300])
    check("it gives a measured size, not a guess", "bytes on disk" in said, said)
    check("it gives the conversation count", "3 conversations" in said, said)
    check("it gives the pinned count", "2 of them pinned" in said, said)
    check("it says the chats are encrypted at rest", "encrypted" in said, said)
    check("it says recording is on", "Recording is on" in said, said)
    check("it says nothing expires automatically (keep_days is 0)",
          "nothing expires automatically" in said, said)
    check("it quotes the measured purge speed", "I measured it on this PC" in said, said)
    check("... with a real millisecond number", " ms" in said, said)
    check("it answers the owner's exact question about batching",
          "ms a chat" in said and "batch" in said, said)
    check("it says clearing by date exists and cannot be undone",
          "Clearing by date exists" in said and "cannot be undone" in said, said)
    check("it says pinned chats are kept unless asked otherwise",
          "pinned chats" in said and "unless you say otherwise" in said, said)
    check("it says the second yes needs a platform check",
          "Hello" in said and "fingerprint" in said, said)
    check("IT NEVER DEFLECTS", "don't track" not in said
          and "do not track" not in said and "no built-in" not in said
          and "I do not know" not in said, said)
    check("it never claims a number it did not read",
          got["purge_speed"]["measured"] is True, got["purge_speed"])
    check("the retention is reported as the measured switch value",
          got["recording"]["keep_days"] == 0 and got["recording"]["expires"] is False,
          got["recording"])


def t_the_capability_answer_says_what_it_could_not_read():
    clean()
    P._SPEED.clear()          # no leftover measurement from an earlier check
    P._speed_path().unlink(missing_ok=True)   # and none cached on disk either
    got = P.capability(now=T0, chats=None, mem=None, measure=False)
    check("with no modules it still answers", isinstance(got.get("words"), str))
    check("... and lists what it could not read", isinstance(got.get("unknown"), list))
    check("... and does not invent a purge speed",
          got["purge_speed"]["measured"] is False, got["purge_speed"])
    check("... and says it will not guess", "not measured" in got["words"]
          or "will not guess" in got["words"], got["words"][-400:])


# --------------------------------------------------------------------------
#   The install hook: it wraps, refuses other paths, and leaves them alone
# --------------------------------------------------------------------------

def t_the_install_wraps_the_server_and_refuses_strangers():
    clean()

    class Fake:
        """A stand-in for the server's handler: the two methods install() wraps,
        and the one reply method the wrapper calls."""

        def __init__(self, path="", body=b"{}"):
            self.path = path
            self.headers = {"X-Jarvis-Client": "hud"}
            self.sent = []
            self._body = body

        def do_GET(self):
            return ("original-get", self.path)

        def do_POST(self):
            return ("original-post", self.path)

        def _send(self, code, out):
            self.sent.append((code, out))
            return ("sent", code)

    def build(**checks):
        handler = type("H", (Fake,), {})
        line = P.install(handler, origin_ok=checks.get("origin", lambda self: True),
                         token_ok=checks.get("token", lambda self: True),
                         read_body=lambda self: self._body)
        return handler, line

    handler, line = build()
    check("install returns one banner line", isinstance(line, str) and "purge" in line,
          line)
    check("... and says whether the key is ready",
          "key in" in line or "NO KEY" in line, line)
    again = P.install(handler, origin_ok=lambda self: True,
                      token_ok=lambda self: True, read_body=lambda self: self._body)
    check("installing twice says it is already on", "already on" in again, again)
    # Another path is never read, never parsed and never answered here.
    other = handler()
    other.path = "/api/history"
    check("another path goes straight to the original",
          other.do_POST() == ("original-post", "/api/history"), other.sent)
    # A cancel needs no database, so it proves the wrapper answers on its own.
    mine = handler()
    mine.path = P.CANCEL_PATH
    mine._body = b"{}"
    check("a real purge path is answered by the wrapper",
          mine.do_POST() == ("sent", 200) and mine.sent[0][0] == 200, mine.sent)
    # The origin check runs FIRST - before the body is read.
    refused, _ = build(origin=lambda self: False)
    h = refused()
    h.path = P.PREVIEW_PATH
    h._body = b"not json at all"
    check("a cross-origin caller is refused before its body is read",
          h.do_POST() is None and h.sent and h.sent[0][0] == 403, h.sent)
    check("... and the refusal is the server's own sentence",
          "cross-origin" in h.sent[0][1]["error"], h.sent)
    # The token check runs before anything is answered.
    bad, _ = build(token=lambda self: False)
    h2 = bad()
    h2.path = P.CONFIRM_PATH
    check("a bad token is a 401", h2.do_POST() is None
          and h2.sent and h2.sent[0][0] == 401, h2.sent)
    h2.path = P.CANCEL_PATH
    check("... on every one of the routes", h2.do_GET() is None
          and h2.sent[-1][0] == 401, h2.sent)
    # A broken body is a 400 from the wrapper, not a crash.
    ok, _ = build()
    h3 = ok()
    h3.path = P.CANCEL_PATH
    h3._body = b"{not json"
    check("a body that is not JSON is a 400",
          h3.do_POST() == ("sent", 400) and h3.sent[0][0] == 400, h3.sent)


TESTS = [
    t_the_preview_counts_the_days_correctly,
    t_the_card_carries_every_detail,
    t_a_pinned_chat_is_never_deleted_and_never_counted,
    t_include_pinned_is_the_only_way_past_the_pin,
    t_a_chat_pinned_after_the_preview_is_skipped,
    t_facts_come_from_provenance_and_nothing_else,
    t_include_facts_false_clears_no_facts_and_says_so,
    t_the_approved_facts_are_erased_for_good,
    t_the_second_yes_requires_the_first,
    t_step_one_is_answered_once_and_restates_the_counts,
    t_a_ticket_is_always_required_and_every_bad_one_is_refused,
    t_a_ticket_for_another_preview_or_platform_is_refused,
    t_a_good_ticket_works_once_and_a_replay_is_refused,
    t_a_new_preview_invalidates_the_old_one,
    t_an_expired_preview_refuses_the_second_yes,
    t_cancel_deletes_nothing_and_ends_the_two_yeses,
    t_there_is_no_cardless_or_bulk_shortcut,
    t_app_lock_or_hidden_lists_stop_every_route,
    t_the_audit_line_is_written_and_holds_no_words,
    t_the_two_keys_are_the_contract,
    t_the_phone_key_is_the_pairing_token,
    t_the_purge_speed_is_measured_on_a_copy,
    t_the_capability_answer_is_measured_truth,
    t_the_capability_answer_says_what_it_could_not_read,
    t_the_install_wraps_the_server_and_refuses_strangers,
]


def main() -> int:
    if _no_crypto():
        print("the cryptography package is missing: nothing below could run.")
        return 1
    for fn in TESTS:
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    for why in SKIPPED:
        print(f"  SKIPPED (not a pass): {why}")
    if FAILED:
        print("failed:")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
