"""jarvis_events.py - the one event bus. A doorbell, not a database.

PART RECOVERED, PART REBUILT. READ THIS FIRST.

The original is gone - see jarvis_framework.py for where it was searched for.
But unlike most of the missing ten, a real fraction of this file survived, as
context lines inside the patches in `backend/`. These are VERBATIM original
source, not reconstruction:

    the Event dataclass and its four fields      extraction-wiring.patch @ 63
    _poll_approvals's note()/data.update() shape extraction-wiring.patch @ 159
    POLLERS = [_poll_approvals, _poll_power, _poll_persona]              @ 255
    class Pump                                                          @ 258
    _DOORBELL_KEYS and _doorbell_item            event-allowlist.patch @ 181
    the notice passthrough                       approval-notice.patch @ 223

The wire format is not guesswork either. `JARVIS-API.md` section 3 specifies
it exactly - frame layout, event kinds, the 512-event ring, the 20-second
keepalive, `hello.stale` - and three clients already parse it. Where this file
had to be invented, the comment says INFERRED.

THE ONE RULE, from JARVIS-API.md, and everything here follows from it:

    "An event says SOMETHING CHANGED, not HERE IS THE STATE. The bus is a
     doorbell, not a database."

That is why `note()` exists and why `_doorbell_item` throws almost everything
away. An event that carried the state would be a second, unauthenticated copy
of /api/pending - and it reaches lock screens.

WHAT WENT WRONG HERE BEFORE, so it is not reintroduced:

  * Nothing ever STARTED the pump. `Pump` existed, `POLLERS` listed three
    pollers, the docstring said "Started by the proxy" - and the proxy never
    instantiated it. `approval` events were documented, parsed by both
    clients, and fiction. Fixed by events-pump.patch, in jarvis_hud.
  * The doorbell shipped `raised` - the field that quotes hostile text - to
    every subscriber, because it filtered with a DENYLIST naming `detail` and
    `prompt`, and `raised` was added later. It is an allowlist now, and
    `raised` travels as a boolean.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

# --------------------------------------------------------------------------
#   Tuning
# --------------------------------------------------------------------------

#: How many events the ring holds. JARVIS-API.md names this number to clients:
#: "hello.stale == true means you fell off the back of the ring buffer (512
#: events)". Changing it changes a documented contract.
RING = 512

#: Seconds between poller sweeps. Printed at startup by events-pump.patch as
#: "pump on, {n} pollers every {POLL_SECONDS:g}s", so it is a float and small.
POLL_SECONDS = 1.0

#: Seconds between `: keepalive` comment lines. JARVIS-API.md tells clients
#: "~20 s" and that a longer silence means the connection is dead - so this
#: must stay at or under that, or a healthy stream looks dead.
KEEPALIVE_SECONDS = 20.0

#: How long a stream is held open before the server closes it politely. The
#: HUD's own comment says "the stream lives for an hour with keepalives".
STREAM_MAX_SECONDS = 3600.0

#: What a client should wait before reconnecting, in milliseconds. Sent as the
#: SSE `retry:` field and echoed in hello.retry_ms.
RETRY_MS = 3000

#: The API version reported by hello(). JARVIS-API.md section 2: "api": 1.
API_VERSION = 1


# --------------------------------------------------------------------------
#   An event
# --------------------------------------------------------------------------
#
# VERBATIM from extraction-wiring.patch. The comment listing the kinds is the
# original's, and it is one longer than JARVIS-API.md's list - the doc says
# hello, approval, finding, power, persona, model, voice; the code also has
# `voice`. Kept as the code had it, because the code is what clients met.

@dataclass
class Event:
    id: int
    kind: str                  # hello | approval | proposal | finding | power
                               # | persona | model | voice | activity
    data: dict = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    def sse(self) -> str:
        """This event as an SSE frame.

        THE NAME IS RECOVERED, the body is inferred. test_extraction_wiring.py
        line 351 calls `events[-1].sse()` and then tests `"prompt" not in blob`
        against the result - so the original method was called sse() and
        returned a STRING. A rebuild that called it frame() and returned bytes
        made that assertion raise AttributeError, and the leak check it guards
        - an email body reaching a phone lock screen - stopped running.

        The exact output is pinned by JARVIS-API.md's worked example:

            id: 414
            event: approval
            data: {"key":"approvals","value":["a1","a2"],"count":2,"items":[...]}

        Newlines inside the payload are the one hazard: a raw \\n in a data
        line ends the frame early and the client sees two broken events rather
        than one good one. json.dumps escapes them, so the payload is always
        one line - but the JSON is generated defensively anyway, because a
        value that will not serialise must not take the whole stream down.
        """
        try:
            payload = json.dumps(self.data, default=str, ensure_ascii=False)
        except Exception:
            payload = json.dumps({"error": "unserialisable"})
        # No stray newline can reach the wire even if json.dumps is replaced.
        payload = payload.replace("\r", " ").replace("\n", " ")

        # kind and id are sanitised too. Only `data` was, and a kind carrying
        # a newline splits one frame into two - a forged event, from anything
        # that can influence a kind string.
        kind = str(self.kind).replace("\r", " ").replace("\n", " ")
        try:
            ident = int(self.id)
        except (TypeError, ValueError):
            ident = 0

        head = "" if ident <= 0 else f"id: {ident}\n"
        text = f"{head}event: {kind}\ndata: {payload}\n\n"
        # errors="replace", and this is the important one. The encode used to
        # sit OUTSIDE the try above, so a single lone surrogate - which
        # json.dumps(ensure_ascii=False) emits happily, and which arrives from
        # any surrogateescape-decoded filename or environment string - raised
        # UnicodeEncodeError out of the generator. That killed the stream for
        # EVERY connected client, and each reconnect re-read the same poisoned
        # event and died again: a 3-second reconnect loop on a phone until the
        # event fell off the ring. The docstring already promised "a value
        # that will not serialise must not take the whole stream down"; only
        # json.dumps was guarded. The encode now lives in frame(), below.
        return text

    def frame(self) -> bytes:
        """The same frame, encoded, because stream() yields bytes.

        errors="replace", and this is the important one. The encode used to sit
        outside the try in sse(), so a single lone surrogate - which
        json.dumps(ensure_ascii=False) emits happily, and which arrives from
        any surrogateescape-decoded filename or environment string - raised
        UnicodeEncodeError out of the generator. That killed the stream for
        EVERY connected client, and each reconnect re-read the same poisoned
        event and died again: a 3-second reconnect loop on a phone until the
        event fell off the ring.
        """
        return self.sse().encode("utf-8", "replace")


# --------------------------------------------------------------------------
#   The bus
# --------------------------------------------------------------------------

#: Parked under a key by forget(). json.dumps never produces this, so the next
#: note() for that key compares unequal and fires - while the key stays PRESENT,
#: which is what keeps it from being read as a fresh baseline.
_REARMED = object()


class Bus:
    """A ring of recent events, and the waiters watching it.

    Thread-safe because the pollers run on the pump's thread while HTTP
    handlers publish from theirs, and `stream()` reads from a third per
    connected client.
    """

    def __init__(self, size: int = RING) -> None:
        self._size = max(8, int(size))
        self._events: list[Event] = []
        self._next = 1
        self._seen: dict[str, object] = {}
        self._cv = threading.Condition()

    # ---- writing ----------------------------------------------------------

    def publish(self, kind: str, data: Optional[dict] = None) -> Event:
        """Announce that something changed. Always emits.

        Five surviving call sites use this, all as BUS.publish(kind, dict).
        """
        with self._cv:
            ev = Event(id=self._next, kind=str(kind),
                       data=dict(data or {}), at=time.time())
            self._next += 1
            self._events.append(ev)
            # Trim from the front. A client that was on an id now gone will be
            # told `stale` by hello() rather than silently missing events.
            if len(self._events) > self._size:
                del self._events[:len(self._events) - self._size]
            self._cv.notify_all()
            return ev

    def note(self, key: str, value: object, kind: str,
             extra: Optional[dict] = None,
             announce_first: bool = False) -> Optional[Event]:
        """Announce a change ONLY if this key's value actually changed.

        Shape recovered from extraction-wiring.patch @ 159, which calls it and
        then conditionally updates the result:

            ev = bus.note("approvals", ids, "approval")
            if ev is not None:
                ev.data.update({...})

        The `is not None` is the whole point: pollers run every second, and
        without this every subscriber would get 86,400 identical "approvals
        unchanged" events a day. Returning None when nothing moved is what
        makes a one-second poll acceptable on a phone.

        THE FIRST OBSERVATION IS A BASELINE for a POLLER, and also returns
        None. A key a poller has never seen has not CHANGED - there is nothing
        to compare it against - and this is a change feed, not a snapshot
        feed. Publishing the first sighting meant every start of the pump
        fired one approval, one power and one proposal event describing a
        queue that had been sitting there unchanged for a week, to clients
        about to read /api/pending anyway. On a phone that is three
        notifications for nothing, at the moment the desktop comes back.

        `announce_first=True` IS FOR THE OTHER KIND OF CALLER, and leaving it
        off is a bug that only shows up once. A poller asks "has the world
        moved?". set_activity() and Notebook.file() are not asking: something
        just happened and they are reporting it. For those the first call
        after a restart is the most important one there is - the first thing
        the watcher notices, the first "thinking" of the first turn - and the
        baseline rule swallowed it whole. Measured: after a restart the first
        turn published only `idle`, never `thinking`, and the Brain window
        (which has no fallback poll) never redrew.

        Nothing is lost by a poller staying quiet: both clients fetch the real
        state on connect, and every later change is announced.

        The baseline is taken at the first SUCCESSFUL poll, not at process
        start, because a poller that cannot reach its source returns without
        noting. If the gate's database is locked for the first few seconds,
        whatever is queued when it unlocks is the baseline. The 30-second
        fallback poll in the HUD covers that; a client driven purely by this
        stream would be told on the next change instead.

        The caller mutating `ev.data` afterwards means the Event this returns
        must be the same object that is in the ring - not a copy - or those
        extra fields would never reach a subscriber.
        """
        try:
            # Compared by value, and normalised so an equal-but-differently-
            # ordered list does not read as a change. The approvals poller
            # already sorts its ids; this makes that not matter.
            #
            # default= returns the TYPE NAME, not str(o). With default=str an
            # object with the usual repr tokenises to "<X object at 0x7f...>",
            # whose address changes every poll - so an unchanged value fired
            # an event every single second. A type name cannot distinguish two
            # instances either, but it fails in the quiet direction.
            token = json.dumps(value, sort_keys=True,
                               default=lambda o: f"<{type(o).__name__}>")
        except Exception:
            token = f"<{type(value).__name__}>"

        with self._cv:
            first = key not in self._seen
            if not first and self._seen[key] == token:
                return None
            self._seen[key] = token
            if first and not announce_first:
                return None

        # `extra` is merged BEFORE publish, so subscribers waiting on the
        # condition variable see the complete payload. The recovered caller
        # pattern - `ev = bus.note(...); if ev: ev.data.update({...})` - is
        # still supported and still works for a client that RESUMES, because
        # the Event in the ring is the same object. But a LIVE subscriber is
        # woken by publish() and reads the frame before that update lands:
        # measured, 4990 of 5000 approval events reached a live stream with no
        # `count` and no `items`, while a resuming client got the same event
        # id WITH them. Same id, two payloads. Pass `extra` to avoid the race.
        data = {"key": key, "value": value}
        if extra:
            data.update(extra)
        return self.publish(kind, data)

    def forget(self, key: Optional[str] = None) -> None:
        """Re-arm a key, so the NEXT note() for it fires whatever it carries.

        Not a delete. Deleting would make the key unseen, and an unseen key is
        a baseline - so `forget()` followed by `note()` published nothing at
        all, which is the exact opposite of what the name promises. The key is
        instead set to a token no real value can produce, so it counts as seen
        (not a baseline) and compares equal to nothing (so the next note is a
        change).

        INFERRED, and there are no callers. It is here because a poller whose
        source is replaced wholesale - a store reopened on a different file -
        should be able to re-announce rather than report the swap as a change.
        """
        with self._cv:
            if key is None:
                for k in list(self._seen):
                    self._seen[k] = _REARMED
            else:
                if key in self._seen:
                    self._seen[key] = _REARMED

    # ---- reading ----------------------------------------------------------

    @property
    def latest(self) -> int:
        with self._cv:
            return self._next - 1

    @property
    def oldest(self) -> int:
        with self._cv:
            return self._events[0].id if self._events else self._next

    def since(self, last_id: int) -> tuple:
        """Events after last_id, AND the new cursor.

        A PAIR, not a list. test_jobs.py:807 unpacks it:

            got, _ = self.bus.since(0)

        and the shape is right for what it is for - a caller resuming a stream
        needs to know where it got to, and deriving that from `out[-1].id`
        breaks on an empty result, which is the common case.
        """
        with self._cv:
            out = [e for e in self._events if e.id > last_id]
            return out, (out[-1].id if out else max(last_id, self._next - 1))

    def wait(self, last_id: int, timeout: float) -> list[Event]:
        """Block until there is something after last_id, or timeout."""
        deadline = time.monotonic() + timeout
        with self._cv:
            while True:
                out = [e for e in self._events if e.id > last_id]
                if out:
                    return out
                left = deadline - time.monotonic()
                if left <= 0:
                    return []
                self._cv.wait(left)


#: The one bus. Six surviving call sites reach it as `jarvis_events.BUS`.
BUS = Bus()


# --------------------------------------------------------------------------
#   Activity
# --------------------------------------------------------------------------

_ACTIVITY = {"state": "idle", "detail": "", "at": time.time()}


def set_activity(state: str, detail: str = "") -> None:
    """What Jarvis is doing right now. Called by jarvis_hud._activity.

    Deduplicated through note(), because this is called around every turn and
    an unchanged "idle" does not need to wake a sleeping phone's radio.

    announce_first, because this is a REPORT, not an observation: the caller
    knows something just happened. _ACTIVITY starts at "idle", so without it
    the first "thinking" of the first turn after a restart was taken as the
    baseline and swallowed, and the only frame a client saw for that whole
    turn was the "idle" that followed it.
    """
    _ACTIVITY.update({"state": str(state), "detail": str(detail or ""),
                      "at": time.time()})
    BUS.note("activity", {"state": _ACTIVITY["state"],
                          "detail": _ACTIVITY["detail"]}, "activity",
             announce_first=True)


def activity() -> dict:
    return dict(_ACTIVITY)


# --------------------------------------------------------------------------
#   The doorbell
# --------------------------------------------------------------------------
#
# VERBATIM from event-allowlist.patch, including the reasoning, because this
# is the third place in this project where a rule stated in one module was not
# enforced at the next one along.

# The approval event is a DOORBELL. Everything needed to render the queue comes
# from /api/pending, behind the same token; this says only that something is
# waiting, and enough about it to sort and de-duplicate.
#
# A denylist fails silently - a new column ships itself. An allowlist fails
# visibly - a new field is missing until someone adds it, and the person who
# added the column is the person who notices.
_DOORBELL_KEYS = ("id", "action", "tier", "created")


def _doorbell_item(item: dict) -> dict:
    """One queue entry, reduced to what a notification may say.

    Everything needed to RENDER the queue comes from /api/pending, behind the
    same token. This says only that something is waiting, and enough about it
    to sort and de-duplicate.

    SELF-CONTAINED ON PURPOSE. _scalar is nested rather than a module
    function, and this is not style. Two suites - test_gate_egress.py and
    test_approval_notice.py - audit this filter by pulling _DOORBELL_KEYS and
    this function out of the source with ast and exec-ing the two of them in
    an empty namespace, deliberately, so the check needs no sqlite, no import
    and no running server. A module-level helper is not in that namespace, so
    the audit died with NameError and both suites recorded the doorbell test
    as failed without ever running a row through it - the leak check that
    exists to stop an attacker's words reaching a lock screen was silently
    not being performed. Anything this function needs, it defines.
    """
    def _scalar(v, limit: int = 200):
        """A value safe to put on a doorbell: a number, a bool, None, or a
        short string. Anything else becomes its TYPE NAME, not its contents."""
        if v is None or isinstance(v, (bool, int, float)):
            return v
        if isinstance(v, str):
            return v[:limit]
        return f"<{type(v).__name__}>"

    # Keys AND types. An allowlist of key names lets a non-scalar through
    # wholesale - {"id": {"nested": "SECRET"}} passed intact - so each value is
    # coerced to the scalar it is supposed to be. Not reachable today (these
    # come from SQLite columns) but the guarantee should not depend on that
    # staying true one schema change from now.
    out = {k: _scalar(item.get(k)) for k in _DOORBELL_KEYS}

    # The notice IS allowed through, and it is the one piece of prose that is.
    # jarvis_gate.notice_for builds it from the action name and the risk table
    # and never reads detail, prompt or the contents of raised - so unlike
    # everything else on the row it cannot carry text somebody else wrote.
    notice = item.get("notice")
    if isinstance(notice, dict):
        # A longer limit than the row fields, because this one is PROSE and
        # cutting it loses meaning rather than detail. notice_for builds body
        # as the risk table's `why` plus a fixed ~116 characters ending in
        # "nothing has happened yet." - the reassurance test_approval_notice
        # requires - so a 200-character cap would truncate it for any `why`
        # over about 84 characters. It is still capped: this is a
        # notification, and a cap is what stops an unbounded string reaching
        # a tray.
        out["notice"] = {k: _scalar(notice.get(k), 600) for k in
                         ("title", "body", "weight", "deny_ok", "approve_ok")}

    # A BOOLEAN, never the object. The rule in docs/ARCHITECTURE.md - "an item
    # carrying `raised` never belongs in a group that can be actioned quickly"
    # - needs to survive out here, and a client cannot apply it without
    # knowing the flag. Its CONTENTS are the attacker's words and stay behind
    # the token.
    out["raised"] = bool(item.get("raised"))
    return out


# --------------------------------------------------------------------------
#   Pollers
# --------------------------------------------------------------------------
#
# Each one answers "has this changed?" and says nothing when it has not. They
# import lazily and swallow their own failures on purpose: a poller for a
# module that is not installed must not stop the other two, and the pump
# thread must not die because a database was briefly locked.

def _poll_approvals(bus: Bus) -> None:
    try:
        import jarvis_gate
        pending = jarvis_gate.pending()
    except Exception:
        return
    if not isinstance(pending, list):
        return

    ids = sorted(str(p.get("id", "")) for p in pending)
    bus.note("approvals", ids, "approval",
             extra={"count": len(pending),
                    "items": [_doorbell_item(i) for i in pending[:10]]})


def _poll_power(bus: Bus) -> None:
    try:
        import jarvis_power
        mode = jarvis_power.current()
    except Exception:
        return
    bus.note("power", mode, "power")


def _poll_persona(bus: Bus) -> None:
    """Persona changes.

    NOT WIRED, AND SAYING SO. This called `jarvis_hud.persona_state()`, which
    DOES NOT EXIST in jarvis_hud - the AttributeError was swallowed by the
    poller's own except, so `persona` events were documented in JARVIS-API.md,
    parsed by both clients, and never emitted. That is precisely the failure
    this module's header describes for the pump ("documented, parsed by both
    clients, and fiction"), reintroduced by a reconstruction that guessed a
    function name.

    Guessing another name would repeat the mistake. The poller stays, does
    nothing, and reports itself through status() so the gap is visible rather
    than silent. Wire it when the real accessor is identified in jarvis_hud.
    """
    return


def _poll_proposals(bus: Bus) -> None:
    """Memory proposals waiting for review. Added by extraction-wiring.

    Counts only. A proposal's TEXT is a sentence extracted from a private
    conversation, which is the category the privacy section says never leaves
    the device - and an event reaches a lock screen.
    """
    try:
        import jarvis_extract
        rows = jarvis_extract.pending()
    except Exception:
        return
    if not isinstance(rows, list):
        return
    # kind "proposal", which is what extraction-wiring.patch emits and adds
    # to the documented kind list. A reconstruction had it as "finding",
    # which is a different kind with a different meaning on both clients.
    # The IDS, not the count, and extraction-wiring.patch @ 372 is explicit
    # about it: "A doorbell, like approvals: the count AND the ids". Keyed on
    # the count, a queue that changes without changing SIZE is silent for
    # ever - the owner reviews proposal 7 while the extractor queues 8, the
    # count stays 1, and the new one never rings. The ids are still safe on a
    # lock screen: an id is a row number, the TEXT is what quotes the
    # conversation and it is not here.
    ids = sorted(int(p.get("id") or 0) for p in rows if isinstance(p, dict))
    bus.note("proposals", ids, "proposal", extra={"count": len(rows)})


#: VERBATIM from extraction-wiring.patch @ 385, which is where _poll_proposals
#: joins the list - second, not last. Order has no effect (Pump.tick runs them
#: all and none depends on another) but the comment said "verbatim" while the
#: list was reordered, and a provenance note that is not true is worse than no
#: note. events-pump.patch prints len(POLLERS) at startup.
POLLERS: list[Callable] = [_poll_approvals, _poll_proposals, _poll_power,
                           _poll_persona]


# --------------------------------------------------------------------------
#   The pump
# --------------------------------------------------------------------------

class Pump:
    """Runs the pollers on a background thread. Started by the proxy.

    "Started by the proxy" is the original docstring, quoted in
    events-pump.patch - and for a long time it was false, because this file is
    not the proxy and jarvis_hud never instantiated it. The patch fixes the
    other half. This half must keep its side of the bargain: never raise out
    of the thread, and never let one poller's failure stop the others.
    """

    def __init__(self, engine: object = None, bus: Optional[Bus] = None,
                 interval: float = POLL_SECONDS) -> None:
        # `engine=` is how events-pump.patch constructs it:
        #     _PUMP = _ev.Pump(engine=_ENGINE)
        # Nothing surviving shows what the pump does with it, so it is kept
        # and exposed, not used. Inventing a use would be worse than holding
        # it: a wrong use of the engine is a wrong answer, an unused one is
        # only a missing feature. INFERRED, and deliberately inert.
        self.engine = engine
        self.bus = bus or BUS
        self.interval = max(0.05, float(interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.ticks = 0
        self.errors = 0

    def start(self) -> "Pump":
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        # daemon: the pump must never be the reason the process will not exit.
        self._thread = threading.Thread(target=self._run, name="jarvis-events",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def tick(self) -> None:
        """One sweep. Separate from _run so a test can drive it without a
        thread and without waiting a second per assertion."""
        for poll in POLLERS:
            try:
                poll(self.bus)
            except Exception:
                # Counted, not printed. A poller that fails every second would
                # otherwise produce 86,400 identical lines a day, and the
                # count is what tells you it is happening.
                self.errors += 1
        self.ticks += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            # Event.wait rather than sleep, so stop() is immediate instead of
            # up to a full interval late.
            self._stop.wait(self.interval)


# --------------------------------------------------------------------------
#   The stream
# --------------------------------------------------------------------------

def stream(last_id: object = 0, bus: Optional[Bus] = None) -> Iterator[bytes]:
    """The SSE body. Yields bytes; jarvis_hud writes each chunk and flushes.

    Frame layout is fixed by JARVIS-API.md section 3 and by three clients that
    already parse it.

    `last_id` arrives from a `Last-Event-ID` header or a `?since=` query, so it
    is whatever the client sent - a string, empty, or nonsense. Coerced here
    rather than trusted: a ValueError in this generator closes the stream on
    connect, which looks to the client exactly like the server being down.
    """
    bus = bus or BUS
    try:
        cursor = int(str(last_id).strip() or 0)
    except (TypeError, ValueError):
        cursor = 0
    if cursor < 0:
        cursor = 0

    # `stale` means "you fell off the back of the ring - re-fetch everything
    # and do not replay". Computed BEFORE anything is sent, because the ring
    # can move while this stream is being set up.
    oldest = bus.oldest
    latest = bus.latest
    stale = bool(cursor and cursor < oldest - 1)

    yield f"retry: {RETRY_MS}\n\n".encode("utf-8")

    # NO `id:` LINE ON HELLO. It used to carry `id=latest`, which duplicated a
    # real event's id and then replayed events counting UP FROM BELOW it -
    # ids going backwards inside one stream. A client that treats
    # Last-Event-ID as monotonic, which the spec's own example invites,
    # discards the whole replay. A frame with no id leaves the client's cursor
    # where it was, which is exactly right for a handshake.
    hello_ev = Event(id=0, kind="hello", data={
        "resumed_from": cursor,
        "stale": stale,
        "latest": latest,
        "retry_ms": RETRY_MS,
    })
    yield hello_ev.frame()

    # A stale client is told to re-fetch, so replaying the ring at it would be
    # the exact thing rule 2 forbids. Start it at the live edge.
    #
    # A FIRST-TIME client is the same case. With no Last-Event-ID the cursor
    # is 0, `stale` is False by the `bool(cursor and ...)` short-circuit, and
    # the whole ring - up to 512 events, including doorbells for approvals
    # already decided - was replayed at a phone on connect. Rule 1 says the
    # client re-fetches state anyway, so the replay buys nothing and costs a
    # notification storm.
    if stale or not cursor:
        cursor = latest
    elif cursor > latest:
        # A corrupted Last-Event-ID from the future would otherwise leave the
        # client receiving nothing until the bus caught up.
        cursor = latest

    started = time.monotonic()
    last_beat = time.monotonic()

    while time.monotonic() - started < STREAM_MAX_SECONDS:
        # A short wait, not KEEPALIVE_SECONDS: the keepalive deadline has to be
        # checked on a timer of its own, or a quiet bus would delay it.
        events = bus.wait(cursor, timeout=1.0)
        if events:
            for ev in events:
                yield ev.frame()
                cursor = max(cursor, ev.id)
            last_beat = time.monotonic()
            continue

        if time.monotonic() - last_beat >= KEEPALIVE_SECONDS:
            # A comment line. Every SSE client ignores these; their ABSENCE is
            # how a client detects a dead connection the socket has not
            # noticed yet.
            yield b": keepalive\n\n"
            last_beat = time.monotonic()


# --------------------------------------------------------------------------
#   Handshake
# --------------------------------------------------------------------------

def _capability_probe() -> dict:
    """What is installed on THIS machine right now.

    JARVIS-API.md is emphatic about why this is probed rather than declared:
    "A capability that is false means hide the UI for it, not show a button
    that 404s." So each one is an actual import attempt, not a constant.
    """
    def has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    caps: dict = {
        "approvals": has("jarvis_gate"),
        "memory": has("jarvis_memory"),
        "models": has("jarvis_models"),
        "skills": has("jarvis_skills"),
        "power": has("jarvis_power"),
        "voice": has("jarvis_voice"),
        "persona": has("jarvis_style"),
        # GET/POST /api/appearance (appearance.patch). The phone only syncs
        # its face when this is true, and it was never sent - so a face
        # chosen on one device never reached the other. Not an import:
        # appearance.patch adds functions to jarvis_hud itself, so this asks
        # the running server whether it has them.
        "appearance": _hud_has("_appearance_view"),
        # A temporary chat (`"temporary": true` on /api/chat): no memory
        # used, nothing learned, nothing kept (temporary-chat.patch, the
        # owner's decision of 2026-09-25). Asked of the running server, like
        # appearance: both apps refuse to offer it - rather than send the
        # flag to a PC that would ignore it - unless this is true.
        "temporary_chat": _hud_has("_temporary_chat"),
        "connectors": {},
    }

    # The power mode, not just "the module is there". The desktop reads
    # capabilities.power.mode at connect time (stream.rs prime_from_version),
    # and a bare `true` left it on "active" through quiet hours until the
    # mode next changed. jarvis_power.status() is the same dict /api/status
    # is built from: mode (with quiet hours applied), why, since. A non-empty
    # object still reads as "available" on the phone (ApiModels.kt
    # asCapabilityFlag).
    if caps["power"]:
        try:
            import jarvis_power
            st = jarvis_power.status()
            if isinstance(st, dict) and st:
                caps["power"] = st
        except Exception:
            pass

    # Voice is the one the doc singles out: "false until the models are
    # downloaded", so importable is not the same as available. Ask the module
    # if it can say.
    if caps["voice"]:
        try:
            import jarvis_voice
            st = jarvis_voice.status()
            if isinstance(st, dict):
                caps["voice"] = st
        except Exception:
            caps["voice"] = False
    return caps


def _hud_has(name: str) -> bool:
    """Does the running server define `name`? jarvis_hud.py normally runs as
    __main__; under a test or an importer it is `jarvis_hud`."""
    import sys
    for modname in ("__main__", "jarvis_hud"):
        mod = sys.modules.get(modname)
        if mod is not None and callable(getattr(mod, name, None)):
            return True
    return False


def hello(client: str = "") -> dict:
    """The /api/version handshake body. Shape from JARVIS-API.md section 2.

    `client` is the X-Jarvis-Client header. It is echoed so a client can
    confirm the server saw it, and it is NOT used for anything else - the
    doc's own note says "Do not rely on X-Jarvis-Client for security".
    """
    return {
        "api": API_VERSION,
        "server": "jarvis-hud",
        "client": str(client or ""),
        "auth": {
            "token_required": True,
            "header": "X-Jarvis-Token",
            "note": "Native clients: always the header. "
                    "Do not rely on X-Jarvis-Client for security.",
        },
        "events": {
            "path": "/api/events",
            "resume_header": "Last-Event-ID",
            "resume_query": "since",
            "retry_ms": RETRY_MS,
            "ring": RING,
            "latest": BUS.latest,
        },
        # What Jarvis is doing right now. docs/JARVIS-API.md says /api/version
        # "also carries activity", and the desktop reads it from here at
        # connect time - but it was never sent, so a client connecting
        # mid-turn showed "idle". The state word only; `detail` stays on the
        # activity event and /api/status, like every other doorbell field.
        "activity": str(_ACTIVITY.get("state") or "idle"),
        "capabilities": _capability_probe(),
    }


def status() -> dict:
    """INFERRED. For `python jarvis_events.py` and the brain map."""
    return {"latest": BUS.latest, "oldest": BUS.oldest,
            "ring": RING, "pollers": len(POLLERS),
            "poll_seconds": POLL_SECONDS, "activity": activity(),
            "persona_events": "NOT WIRED - see _poll_persona"}


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<16} {v}")
