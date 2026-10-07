"""jarvis_extract.py - propose durable facts from conversation (mem0 pattern).

WHAT IT DOES
After a local turn, the transcript is handed to the LOCAL model with one
job: list anything in it that would still be true and useful next month.
Each proposal goes into a review queue. Nothing reaches memory until a
human accepts it. There is no path that writes one without a decision:
the auto_accept branch that used to sit in propose() has been removed.

WHY THE QUEUE
A system deciding on its own what to remember about you is exactly the
thing the privacy rule constrains. The queue makes the decision visible:
you see what it thought was worth keeping, and you learn what it gets wrong
before you let it run unattended.

SETUP REQUIRED - said plainly
This is a working scaffold with a deliberately conservative prompt. The
threshold for "durable", the handling of corrections ("actually I moved"),
and the dedupe against what is already known all need tuning against REAL
conversations. The owner asked for a proper set-up pass once Jarvis is
running; until [memory.extraction].setup_complete is true the boot banner
says so.

NEVER CLOUD
The extractor talks to Ollama on localhost and nothing else. If the local
model is not reachable, no proposals are made; it does not fall back.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.request
from contextlib import closing
from typing import Any, Callable, Optional

import jarvis_memory as M

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def _cfg(key: str, default):
    try:
        import jarvis_framework as fw
        return fw.load_framework().get("memory", {}).get("extraction", {}).get(key, default)
    except Exception:
        return default


_PROMPT = """You extract durable personal facts from a conversation for a private assistant's memory.

Rules:
- Only facts that will still be true and useful in a month: preferences, ongoing projects, hardware, people, decisions.
- Never questions, never one-off tasks, never anything the assistant said unless the user confirmed it.
- If the user CORRECTS an earlier fact, output the new one and set "replaces" to the old wording.
- Output JSON only: {"facts":[{"text":"...","replaces":null|"...","confidence":0.0-1.0}]}
- If there is nothing durable, output {"facts":[]}.

Conversation:
"""


def _init(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id         INTEGER PRIMARY KEY,
            text       TEXT NOT NULL,
            replaces   TEXT,
            confidence REAL,
            source     TEXT,
            created    REAL NOT NULL,
            state      TEXT NOT NULL DEFAULT 'pending',   -- pending|accepted|rejected
            decided    REAL,
            fact_id    INTEGER
        )""")
    # Added later: the fact a correction resolves to, settled when the
    # proposal is queued rather than when it is accepted. Accepting used to
    # re-run the lookup and retire whatever came back, so the human approved
    # a destructive edit without being told what it destroyed.
    for col, decl in (("replaces_id", "INTEGER"), ("replaces_text", "TEXT")):
        try:
            c.execute(f"ALTER TABLE proposals ADD COLUMN {col} {decl}")
        except Exception:
            pass                      # already there


def _local_llm(prompt: str, model: Optional[str] = None, timeout: float = 60) -> Optional[str]:
    """One call to the LOCAL model. Returns None if it is not there."""
    # format="json" used to be here. It promises that the reply parses and
    # nothing else - and `{}` parses, as does `{"facts": "lots"}`. A schema
    # constrains the decoding itself, so the shape stops being something to
    # check after the fact.
    body = {"model": model or os.environ.get("JARVIS_LOCAL_MODEL", "qwen3:8b"),
            "prompt": prompt, "stream": False,
            "options": {"temperature": 0.1}}
    try:
        import jarvis_structured
        body["format"] = jarvis_structured.FACTS_SCHEMA
    except Exception:
        body["format"] = "json"        # older, looser, better than nothing
    req = urllib.request.Request(f"{OLLAMA}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())["response"]
    except Exception:
        return None


def propose(messages: list[dict], *, llm: Optional[Callable[[str], Optional[str]]] = None,
            source: str = "conversation") -> list[dict]:
    """Run extraction over a transcript and queue the proposals. Returns them.

    `llm` is injectable so tests (and a future tuned extractor) can replace
    the model call; the default is the local Ollama model and nothing else.
    """
    if not _cfg("enabled", True):
        return []
    convo = "\n".join(f"{m.get('role','?')}: {m.get('content','')}"
                      for m in messages if isinstance(m, dict) and isinstance(m.get("content"), str))
    if not convo.strip():
        return []
    raw = (llm or _local_llm)(_PROMPT + convo[-6000:])
    if not raw:
        return []
    try:
        data = json.loads(raw)
        facts = data.get("facts", []) if isinstance(data, dict) else []
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            facts = json.loads(m.group(0)).get("facts", []) if m else []
        except Exception:
            facts = []
    store = M.store()
    known = {f["text"].lower() for f in store.current_facts()}
    out = []
    with closing(store._connect()) as c:
        _init(c)
        # 'pending' AND 'rejected'. Only pending was checked, and the effect
        # was that discarding a proposal did not make it go away: the learner
        # re-reads the WHOLE conversation on the next pass - the transcript
        # grows every turn, so the guard against "nothing new was said" does
        # not stop it - the model proposes the same fact from the same
        # sentence again, and it is back in the queue within the minute.
        #
        # A review queue that re-asks what you just declined trains you to
        # stop reading it, which costs more than the feature is worth. Open
        # WebUI's #18603 is people asking to switch memory off per agent
        # because it is "indiscriminately using information"; this is the
        # shape of complaint that gets you there. See docs/PEERS.md.
        #
        # 'accepted' is deliberately NOT here: an accepted proposal became a
        # fact, and `known` above already holds every current fact, so adding
        # it would only double-cover - and would wrongly suppress a re-propose
        # after the owner later retires that fact and genuinely wants it back.
        have = {r[0].lower() for r in c.execute(
            "SELECT text FROM proposals WHERE state IN ('pending','rejected')")}
        cap = int(_cfg("review_queue_max", 200))
        pending_n = c.execute("SELECT COUNT(*) FROM proposals WHERE state='pending'").fetchone()[0]
        for f in facts:
            if not isinstance(f, dict):
                continue
            text = " ".join(str(f.get("text", "")).split())
            # A model that writes "confidence": "high" raised ValueError out
            # of propose(), keeping the facts queued before it and losing
            # every one after it. An unparseable confidence is a missing
            # confidence, not a reason to abandon the batch.
            try:
                conf = float(f.get("confidence") or 0.5)
            except (TypeError, ValueError):
                conf = 0.5
            # Cheap filters before anything reaches the queue: a question is
            # not a fact, a fragment is not a fact, and the model's own low
            # confidence is a signal worth honouring.
            if not text or text.endswith("?") or conf < 0.3:
                continue
            # The old guard dropped anything under three words and anything
            # opening with an auxiliary. Measured against realistic output it
            # discarded "Can't eat gluten", "Does not drink alcohol", "Is
            # vegetarian", "Wife: Dana", "Do not suggest Docker, ever" and
            # "Should always use metric units" - a coeliac diagnosis and four
            # standing instructions - while keeping "Whose birthday is 3
            # March". It was matching the shape of a question word, not a
            # question. An auxiliary is only interrogative when a subject
            # follows it, and a wh-word almost never opens a durable fact.
            if len(text.split()) < 2:
                continue
            if re.match(r"^(what|when|where|which|who|whose|why|how)\b", text, re.I):
                continue
            if re.match(r"^(is|are|was|were|do|does|did|can|could|would|should|will|have|has)\s+"
                        r"(i|you|we|they|he|she|it|there|that|this)\b", text, re.I):
                continue
            # memory-intake: a relative date gets its real date added in
            # brackets ("yesterday (2026-09-22)"), anchored to when the
            # conversation happened. Before the dedupe, so both compare the
            # dated form. See jarvis_intake.learned_text.
            text = _intake_text(text)
            if text.lower() in known or text.lower() in have:
                continue
            # memory-intake: the same statement in slightly different words
            # as a kept fact or a waiting/discarded card. Never a correction,
            # never on a number/date/negation difference, never before the
            # real embedder is loaded - and counted. Drops the PROPOSAL only;
            # no stored fact is touched. See jarvis_intake.near_duplicate.
            if _intake_near_duplicate(text, f, store):
                continue
            if pending_n >= cap:
                # Counted, not just silently folded into the same `continue`
                # as the dedupe check. Once the queue is at its cap, every
                # further proposal this pass produces was going on the floor
                # with no record of it ever having existed - visible only as
                # the boolean `queue_full` staying true, which cannot
                # distinguish "nothing new to learn" from "still learning
                # things, and losing all of them". This is a running total
                # for the process's life, not a persisted count: it exists so
                # the owner can tell the difference, not to reconstruct what
                # was lost.
                global _dropped_full
                _dropped_full += 1
                continue
            replaces = f.get("replaces")
            # Settle the target now, so the approval card can name the fact
            # this will retire. find_one returns None rather than a guess, and
            # None means "add it, retire nothing" - two facts that disagree is
            # a recoverable state, a silently deleted allergy is not.
            #
            # memory-intake: when the learner's prompt listed the closest
            # stored facts by number, the model answered with a number and
            # this is that exact fact - or None for a number off the list.
            # Otherwise find_one() on the model's words, exactly as before.
            target = _intake_target(f, replaces, store)
            cur = c.execute(
                "INSERT INTO proposals (text, replaces, confidence, source, created,"
                " replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
                (text, replaces, conf, source, time.time(),
                 target["id"] if target else None,
                 target["text"] if target else None))
            row = {"id": cur.lastrowid, "text": text, "replaces": replaces,
                   "replaces_id": target["id"] if target else None,
                   "replaces_text": target["text"] if target else None,
                   "confidence": conf, "state": "pending"}
            out.append(row); have.add(text.lower()); pending_n += 1
            # There is deliberately no auto-accept branch here. There used to
            # be one, behind two config keys: a fact scoring 0.8 was written
            # with no human decision. Nothing in Jarvis approves on the
            # owner's behalf, and a queue whose contents can retire existing
            # facts is the last place to make an exception.
    return out


#: The `source` of a "retire this?" card. jarvis_feedback raises these when a
#: fact keeps turning up in answers the owner marked wrong. The clients read
#: this value to label the card's two buttons for what they really do - see
#: backend/README.md's feedback section.
RETIRE_SOURCE = "feedback_retire"


def propose_retire(fact_id: int, *, helpful: int, harmful: int) -> Optional[int]:
    """Queue ONE card asking whether to retire one fact. Retires nothing.

    Added by feedback.patch, for jarvis_feedback. It goes in THIS queue - the
    one every fact Jarvis ever learns already passes through, one id and one
    decision at a time - rather than a new approval flow of its own, because
    docs/ARCHITECTURE.md is right that a feature needing its own approval
    flow is a design mistake.

    The card carries the fact in `replaces_id`/`replaces_text`, which is
    where every card already names the fact it would retire, so a client
    that shows "would replace: ..." shows the right thing without changing.
    Accepting it retires that fact (an end date - it stays in the history)
    and adds nothing: see _accept_retire(). Discarding it changes nothing.

    Returns the proposal id, or None when there is nothing to ask: the fact
    is gone or already retired, a card for it is already waiting, or the
    queue is full (counted in _dropped_full, like any other dropped
    proposal). No text from the conversation is involved - only the fact's
    own words and the two counts.
    """
    store = M.store()
    fact = store.get(int(fact_id))
    if not fact:
        return None
    vt = fact.get("valid_to")
    if vt is not None and float(vt) <= time.time():
        return None
    with closing(store._connect()) as c:
        _init(c)
        if c.execute("SELECT 1 FROM proposals WHERE state='pending' AND source=?"
                     " AND replaces_id=?", (RETIRE_SOURCE, int(fact_id))).fetchone():
            return None
        cap = int(_cfg("review_queue_max", 200))
        if c.execute("SELECT COUNT(*) FROM proposals WHERE state='pending'").fetchone()[0] >= cap:
            global _dropped_full
            _dropped_full += 1
            return None
        text = (f"Stop using this fact? It was part of {int(harmful)} "
                f"answer{'s' if int(harmful) != 1 else ''} you marked wrong and "
                f"{int(helpful)} you marked right. Accepting this card retires "
                f"the fact (it stays in the history); discarding it keeps the "
                f"fact exactly as it is.")
        cur = c.execute(
            "INSERT INTO proposals (text, replaces, confidence, source, created,"
            " replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
            (text, fact.get("text"), None, RETIRE_SOURCE, time.time(),
             int(fact_id), fact.get("text")))
        try:
            c.commit()
        except Exception:
            pass
        return cur.lastrowid


def _accept_retire(c, store, row) -> int:
    """Accepting a "retire this?" card: retire the fact it names, add nothing.

    Returns the retired fact's id, so decide() still reads as "accepted" to
    every caller. If something else already retired the fact since the card
    was queued, there is nothing left to do and nothing is done.
    """
    fid = row.get("replaces_id")
    if fid:
        still = store.get(int(fid))
        if still and (still.get("valid_to") is None
                      or float(still["valid_to"]) > time.time()):
            store.retire(int(fid))
    c.execute("UPDATE proposals SET state='accepted', decided=?, fact_id=? WHERE id=?",
              (time.time(), fid, row["id"]))
    return int(fid or 0)


#: memory-entities.patch - the `source` of an "are these the same?" card.
#: jarvis_memory raises one when a newly named person or thing is a likely
#: typo of one already known ("Priya Sharma" / "Priya Sharmaa"): ONE card per
#: pair, ever. Accepting it joins the two entries so a question about one
#: finds the other's facts; discarding keeps them apart. No fact is added,
#: changed or retired either way. Clients label its buttons for that (see
#: backend/README.md, "Memory wave 3"), which is why /api/memory/pending
#: leaves it out unless asked for with ?merge_cards=1.
MERGE_SOURCE = "entity_merge"


def propose_merge(text: str) -> Optional[int]:
    """Queue ONE "are these the same?" card with these words. Merges
    nothing. Called only by jarvis_memory.MemoryStore.raise_merge_cards,
    once per pair. In THIS queue, like propose_retire, so it is one card and
    one decision like every other - never a list, never an approve-all.

    Returns the proposal id, or None when the queue is full (counted in
    _dropped_full, like any other dropped proposal; the pair waits and is
    asked about after the next save)."""
    store = M.store()
    with closing(store._connect()) as c:
        _init(c)
        cap = int(_cfg("review_queue_max", 200))
        if c.execute("SELECT COUNT(*) FROM proposals WHERE state='pending'").fetchone()[0] >= cap:
            global _dropped_full
            _dropped_full += 1
            return None
        cur = c.execute(
            "INSERT INTO proposals (text, replaces, confidence, source, created,"
            " replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
            (str(text), None, None, MERGE_SOURCE, time.time(), None, None))
        try:
            c.commit()
        except Exception:
            pass
        return cur.lastrowid


def _accept_merge(c, store, row) -> int:
    """Accepting an "are these the same?" card: join that one pair, add no
    fact. Returns 0 - there is no new fact - and the card is marked accepted
    either way (a pair that has gone since, because its facts were erased,
    has nothing left to join)."""
    join = getattr(M, "accept_merge_card", None)
    if join is None:
        raise RuntimeError("this jarvis_memory.py cannot join two entries - "
                           "apply-patches.ps1 copies in the one that can")
    join(int(row["id"]))
    c.execute("UPDATE proposals SET state='accepted', decided=? WHERE id=?",
              (time.time(), row["id"]))
    return 0


def _accept(c, store, row) -> int:
    # A "retire this?" card has no new fact in it. Without this branch its
    # sentence would be stored as a fact and the named fact superseded by it.
    if row.get("source") == RETIRE_SOURCE:
        return _accept_retire(c, store, row)
    # memory-entities.patch: nor has an "are these the same?" card. Without
    # this branch its question would be saved as a fact.
    if row.get("source") == MERGE_SOURCE:
        return _accept_merge(c, store, row)
    # Only the target recorded when the proposal was queued, which is the one
    # the approval card showed. The old code re-ran `store.search(replaces,
    # k=1)` here and retired the top hit - and search has no floor, so it
    # always returned something. Accepting a fact about a car retired the
    # owner's editor preference; a replaces string of "Mario's allergy"
    # retired a note about Vim. Both permanent: retire() has no route back.
    supersedes = row.get("replaces_id")
    if supersedes:
        # It may have been retired by something else since it was queued.
        # "Still in use" is the rule every reader uses (and feedback.patch's
        # _accept_retire): no end date, or one still to come. `valid_to is
        # not None` alone left a fact that ENDS later (a lease to December)
        # in use when its correction card was kept (the memory review of
        # 2026-09-27, B12).
        still = store.get(int(supersedes))
        if not still or (still.get("valid_to") is not None
                         and float(still["valid_to"]) <= time.time()):
            supersedes = None
    # auto-learn.patch: the fact keeps the proposal's own source
    # ("conversation", "remember", "gate_denial", "import:claude", ...)
    # instead of every one becoming "extracted", and a fact saved without a
    # card (accept_auto) is "auto", with where it came from in its meta.
    fid = store.add_fact(row["text"], source=_fact_source(row), supersedes=supersedes,
                         meta=_fact_meta(row, c))
    c.execute("UPDATE proposals SET state='accepted', decided=?, fact_id=? WHERE id=?",
              (time.time(), fid, row["id"]))
    return fid


def pending() -> list[dict]:
    store = M.store()
    with closing(store._connect()) as c:
        _init(c)
        # memory-intake: each row also gets `flags` (does this read like a
        # planted instruction?), `keep_both_ok` and `verbatim`. Computed, not
        # stored: a card queued before this patch gets them too.
        return _intake_annotate([dict(r) for r in c.execute(
            "SELECT id,text,replaces,replaces_id,replaces_text,confidence,source,created"
            " FROM proposals WHERE state='pending' ORDER BY created")])


def decide(proposal_id: int, accept: bool) -> Optional[int]:
    """Returns the new fact id on accept, 0 on reject, None if unknown.

    CLAIMED BEFORE ACTED ON. This used to SELECT the row, check it was
    pending, and only then act - a plain check-then-act with nothing between
    the two. Two concurrent decide(id, True) calls (a double-tap, a retried
    request, two devices open on the same review card) could both pass the
    SELECT before either commits its UPDATE, and both then call _accept(),
    writing two fact rows for one human decision. store.add_fact() has its
    own lock against concurrent writers, so nothing crashed and nothing
    corrupted - it just quietly duplicated a memory the owner decided about
    exactly once. The UPDATE below is the claim: only the caller whose
    UPDATE actually changes a row proceeds, and a loser sees exactly what an
    already-decided proposal looks like - None - rather than a race.
    """
    store = M.store()
    with closing(store._connect()) as c:
        _init(c)
        if accept:
            row = c.execute(
                "SELECT * FROM proposals WHERE id=? AND state='pending'",
                (proposal_id,)).fetchone()
            if not row:
                return None
            claimed = c.execute(
                "UPDATE proposals SET state='accepting' WHERE id=? AND state='pending'",
                (proposal_id,))
            if claimed.rowcount == 0:
                # Something else claimed it between the SELECT and here.
                return None
            try:
                return _accept(c, store, dict(row))
            except Exception:
                # Give the row back rather than leave it stuck in a state
                # neither pending() nor decide() recognise.
                c.execute("UPDATE proposals SET state='pending' WHERE id=?",
                         (proposal_id,))
                raise
        cur = c.execute(
            "UPDATE proposals SET state='rejected', decided=? WHERE id=? AND state='pending'",
            (time.time(), proposal_id))
        return 0 if cur.rowcount else None


#: A running total, never decremented, of proposals dropped because the
#: queue was already at its cap. See the comment where it is incremented, in
#: propose(). Reset to 0 on process restart - this is a diagnostic for "is
#: this still happening", not a durable log.
_dropped_full = 0


def setup_status() -> dict:
    out = {"enabled": bool(_cfg("enabled", True)),
           "setup_complete": bool(_cfg("setup_complete", False)),
           # Always false, and reported so a client that warns about it
           # keeps working. The config key is honoured nowhere: nothing in
           # Jarvis writes a fact the owner has not decided on.
           "auto_accept": False,
           "pending": len(_pending_rows()),
           "queue_full": _queue_full(),
           "note": None if _cfg("setup_complete", False) else
                   "extraction is a scaffold: review its proposals and tune the prompt "
                   "against real conversations"}
    if _dropped_full:
        # Only when it has happened, same rule jarvis_memory's bad_vectors
        # counter follows: a permanent "dropped_full: 0" line is noise on
        # every screen that renders this.
        out["dropped_full"] = _dropped_full
        out["dropped_full_note"] = (
            f"{_dropped_full} proposal(s) since this backend started were "
            "never queued because the review queue was already full - "
            "clear some pending items to keep learning new things")
    # memory-intake: near-duplicate drops, whether that check is running yet,
    # and how the last "Remember:" went.
    out.update(_intake_status())
    return out


def _pending_rows() -> list[dict]:
    return pending()


def _queue_full() -> bool:
    """Is the review queue at its cap, and therefore silently dropping?

    propose() folds `pending_n >= cap` into the same `continue` as the dedupe
    check, so once the queue fills, every further proposal goes on the floor
    with no record. A client that can see this can say so.
    """
    try:
        return len(pending()) >= int(_cfg("review_queue_max", 200))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   memory-intake.patch
#
#   Two new decisions-shaped functions, and the hooks propose(), pending() and
#   setup_status() call into jarvis_intake.py. Every hook falls back to this
#   file's old behaviour when jarvis_intake cannot be imported, so the patch
#   without the module is the backend as it was.
# --------------------------------------------------------------------------

def propose_verbatim(text: str, source: str = "remember") -> dict:
    """Queue the owner's own words as a proposal - no model, no rewording.

    What "Remember: ..." turns into. It is still a PROPOSAL: it waits in the
    same review queue as everything else and becomes a fact only through
    decide(). It skips propose()'s shape filters on purpose - they exist to
    catch a model's fragments and questions, and "Remember: when I say the
    usual I mean a flat white" opens with a wh-word the owner meant.

    The same three guards as propose(), in the same order: already a current
    fact, already waiting or already discarded in these exact words, queue
    full (counted in _dropped_full like any other full-queue drop).
    """
    global _dropped_full
    text = " ".join(str(text or "").split())
    if not text:
        return {"queued": False, "reason": "empty"}
    store = M.store()
    with closing(store._connect()) as c:
        _init(c)
        low = text.lower()
        now = time.time()
        for r in c.execute("SELECT text FROM facts WHERE valid_to IS NULL OR valid_to > ?",
                           (now,)):
            if str(r[0]).lower() == low:
                return {"queued": False, "reason": "already_known"}
        for r in c.execute("SELECT id, text, state FROM proposals"
                           " WHERE state IN ('pending','rejected') ORDER BY id DESC"):
            if str(r[1]).lower() == low:
                return {"queued": False, "proposal_id": r[0],
                        "reason": "already_pending" if r[2] == "pending" else "rejected_before"}
        cap = int(_cfg("review_queue_max", 200))
        pending_n = c.execute("SELECT COUNT(*) FROM proposals WHERE state='pending'").fetchone()[0]
        if pending_n >= cap:
            _dropped_full += 1
            return {"queued": False, "reason": "queue_full"}
        cur = c.execute(
            "INSERT INTO proposals (text, replaces, confidence, source, created,"
            " replaces_id, replaces_text) VALUES (?,?,?,?,?,?,?)",
            (text, None, 1.0, source, now, None, None))
        return {"queued": True, "proposal_id": cur.lastrowid}


def decide_keep_both(proposal_id: int) -> Optional[dict]:
    """The third answer on a correction card: keep the new fact AND the old.

    One id, one decision, the same as decide(): there is no list form. It
    claims the row exactly the way decide() does - the UPDATE is the claim -
    so a double-tap or two devices on one card write one fact, not two.

    The new fact is written with nothing superseded, so the fact the card
    named stays current. Unlike the "keep new" button this was modelled on,
    nothing is deleted or retired here at all.

    Returns None when the proposal is not pending (unknown, or already
    decided), {"ok": False, "reason": "not_a_correction"} when there is no
    old fact to keep - use decide() for that card - and otherwise
    {"ok": True, "fact_id": ..., "kept_id": ..., "kept_text": ...}.
    """
    store = M.store()
    with closing(store._connect()) as c:
        _init(c)
        row = c.execute("SELECT * FROM proposals WHERE id=? AND state='pending'",
                        (proposal_id,)).fetchone()
        if not row:
            return None
        row = dict(row)
        if not row.get("replaces_id"):
            return {"ok": False, "reason": "not_a_correction", "id": proposal_id,
                    "note": "this card retires nothing, so there is no old fact to "
                            "keep - answer it with keep or discard"}
        if row.get("source") == "feedback_retire":
            # feedback.patch's "retire this?" card names a fact but has no
            # new one in it. Its answers are retire (decide accept) or keep
            # using (decide discard); "both" would mean nothing.
            return {"ok": False, "reason": "not_a_correction", "id": proposal_id,
                    "note": "this card asks whether to stop using a fact - "
                            "answer it with retire or keep using"}
        claimed = c.execute(
            "UPDATE proposals SET state='accepting' WHERE id=? AND state='pending'",
            (proposal_id,))
        if claimed.rowcount == 0:
            return None
        try:
            fid = _accept(c, store, dict(row, replaces_id=None))
        except Exception:
            c.execute("UPDATE proposals SET state='pending' WHERE id=?", (proposal_id,))
            raise
        # Recorded on the proposal, so "why are both of these current?" has
        # an answer later. Added on first use, like replaces_id was.
        try:
            c.execute("ALTER TABLE proposals ADD COLUMN kept_both REAL")
        except Exception:
            pass                      # already there
        c.execute("UPDATE proposals SET kept_both=? WHERE id=?", (time.time(), proposal_id))
        return {"ok": True, "id": proposal_id, "fact_id": fid,
                "kept_id": row["replaces_id"], "kept_text": row.get("replaces_text")}


def _intake():
    try:
        import jarvis_intake
        return jarvis_intake
    except Exception:
        return None


def _intake_text(text: str) -> str:
    I = _intake()
    if I is None:
        return text
    try:
        return I.learned_text(text)
    except Exception:
        return text


def _intake_near_duplicate(text: str, f: dict, store) -> bool:
    I = _intake()
    if I is None:
        return False
    try:
        return bool(I.near_duplicate(text, f, store))
    except Exception:
        return False                  # never drop because a check failed


def _intake_target(f: dict, replaces, store):
    I = _intake()
    if I is not None:
        try:
            return I.resolve_target(f, replaces, store)
        except Exception:
            pass
    # The old line, minus one crash: a model that answered a bare number with
    # no list to index used to reach find_one() with an int.
    return store.find_one(replaces) if isinstance(replaces, str) and replaces else None


def _intake_annotate(rows: list) -> list:
    I = _intake()
    if I is not None:
        try:
            return I.annotate(rows)
        except Exception:
            pass
    for r in rows:
        r["flags"] = []
        r["flags_checked"] = False
        r["keep_both_ok"] = (bool(r.get("replaces_id"))
                             and r.get("source") != "feedback_retire")
        r["verbatim"] = r.get("source") == "remember"
    return rows


def _intake_status() -> dict:
    I = _intake()
    if I is None:
        return {"near_duplicate_check": "off (jarvis_intake.py is not installed)"}
    try:
        return I.status(M.store())
    except Exception:
        return {}


# --------------------------------------------------------------------------
#   The local model only - checked HERE, where every caller passes through.
#
#   propose() sends the conversation to whatever OLLAMA points at, and OLLAMA
#   comes from the OLLAMA_URL environment variable. The live learner in
#   jarvis_hud.py refused an address that is not this machine, but it was
#   the only caller that checked: import_history.py (a whole Claude or Gemini
#   history) and the gate's "your no becomes a proposed rule" went straight
#   through. One check here covers all of them, and any caller added later.
#
#   Why re-binding the name works: every caller reaches this function as
#   jarvis_extract.propose (or X.propose), looked up at the moment of the
#   call, so each one gets this version. A caller that passes its own `llm`
#   is checked too - fail closed.
# --------------------------------------------------------------------------

def _is_loopback(url) -> bool:
    """Is that address this machine? Anything unparseable is a no."""
    try:
        import urllib.parse
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def local_model_ok() -> bool:
    """May propose() run? Only when OLLAMA is on this machine."""
    return _is_loopback(globals().get("OLLAMA"))


_propose_unchecked = propose


def propose(*args, **kwargs):
    """propose(), but it refuses to run unless the model is on this machine.

    Refusing returns [] ("nothing proposed") and sends nothing anywhere; the
    reason goes to the console, where the other learning messages go.
    """
    if not local_model_ok():
        import sys
        print(f"  ! memory: not reading this conversation - OLLAMA_URL is "
              f"{globals().get('OLLAMA')!r}, which is not this machine. "
              f"Nothing was sent there.", file=sys.stderr)
        return []
    return _propose_unchecked(*args, **kwargs)


# --------------------------------------------------------------------------
#   auto-learn.patch - saving a proposal without a card
#
#   jarvis_auto_learn.py decides WHETHER (the owner's own words, seen live
#   by this PC, on a local model, nothing sensitive unless allowed); this is
#   HOW, and it is deliberately the same path as a card the owner accepted:
#   the row is claimed exactly as decide() claims it (the UPDATE is the
#   claim), and written by _accept(), so the words, the meaning search and
#   both dates are stored the same way. Only two sources can be saved like
#   this, and a proposal that would replace a stored fact never is.
# --------------------------------------------------------------------------

AUTO_SOURCES = ("conversation", "remember")


def accept_auto(proposal_id: int, meta: dict) -> Optional[int]:
    """Save one pending proposal as a fact with source "auto". Returns the
    fact id, or None when it is not pending, not a conversation or
    "Remember:" proposal, or would replace a fact (then it stays a card)."""
    if not isinstance(meta, dict) or isinstance(proposal_id, bool) \
            or not isinstance(proposal_id, int):
        return None
    store = M.store()
    with closing(store._connect()) as c:
        _init(c)
        row = c.execute("SELECT * FROM proposals WHERE id=? AND state='pending'",
                        (proposal_id,)).fetchone()
        if not row:
            return None
        row = dict(row)
        if row.get("source") not in AUTO_SOURCES or row.get("replaces_id") \
                or row.get("replaces"):
            return None
        claimed = c.execute(
            "UPDATE proposals SET state='accepting' WHERE id=? AND state='pending'",
            (proposal_id,))
        if claimed.rowcount == 0:
            return None
        try:
            return _accept(c, store, dict(row, _auto=dict(meta)))
        except Exception:
            c.execute("UPDATE proposals SET state='pending' WHERE id=?", (proposal_id,))
            raise


def _fact_source(row) -> str:
    """The stored fact's source: "auto" only through accept_auto()."""
    if isinstance(row.get("_auto"), dict):
        return "auto"
    src = row.get("source")
    if not isinstance(src, str) or not src or src == "auto":
        return "extracted"
    return src


def _fact_meta(row, c=None) -> dict:
    meta = {"confidence": row.get("confidence"), "proposal_id": row.get("id")}
    extra = row.get("_auto")
    if isinstance(extra, dict):
        meta.update(extra)
        meta["auto"] = True
    elif c is not None:
        # A card the owner accepted BY HAND keeps the link to the chat it
        # came from, like an automatically saved fact does (the second chat
        # audit, 2026-09-28): the sensitive facts are the ones that wait for
        # a card, and "Erase the words" and the list of what a chat taught
        # need the link. The chat is noted with the card (jarvis_auto_learn.
        # _note_card); a card with no note, or a database without the
        # table, simply has none.
        cid = _proposal_chat(c, row.get("id"))
        if cid:
            meta["conversation_id"] = cid
    return meta


def _proposal_chat(c, proposal_id) -> Optional[str]:
    try:
        got = c.execute("SELECT conversation_id FROM auto_learn_notes WHERE proposal_id=?",
                        (int(proposal_id),)).fetchone()
    except Exception:
        return None
    cid = got[0] if got else None
    return cid if isinstance(cid, str) and cid else None
