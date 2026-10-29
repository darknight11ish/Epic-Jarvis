"""A card past its deadline leaves the queue the next time the queue is read.

    python3 test_pending_expiry_on_read.py

THIS SUITE IS ABOUT ITS PATCH IN ISOLATION, AND THE STACK SUPERSEDED IT
(2026-10-28). It proves the every-read sweep `no-expiry-cards.patch` added for
the owner's "approval cards that are expired" report. The owner then ruled
that no card has a time limit at all ("if there doesn't need to be a time
limit don't have one"), and `no-deadline-cards.patch` - applied AFTER this one
in the stack - removes that sweep from `pending()`: a card past its request's
wait now STAYS, with its buttons, and a late yes is refused with the reason
instead of the card vanishing. Both halves are proven on the full stack by
`backend/test_gate_no_deadline.py`; this file keeps the evidence for the patch
it is about.

WHY THIS EXISTS

The owner asked on 2026-10-28: "there is approval cards that are expired, how
do I clear them easily from my android phone". The phone was telling the truth.
Measured on his OnePlus (`f0a5b32b`, app 0.2.3086, uiautomator dumps kept under
`.dsh-scratch/PHONE-EXPIRED-CARDS-2026-10-28/`): the Home list was headed
"4 WAITING ON YOU" with "Nothing runs until you decide.", and every one of the
four cards said "Timed out - ask the desktop to raise this again." and drew no
Approve and no Deny, because the phone had already worked out that the deadline
had passed. There was nothing to press on the card and nothing on the screen to
clear it.

The gate's half was one line: the sweep that marks an overdue row 'expired' -
the UPDATE inside `_init()` - runs ONCE PER PROCESS, behind `if _inited:
return`. A card whose waiting thread died with an earlier process (a backend
restart, a killed backend, an abandoned request) is not old enough to be swept
by the NEXT start-up if it was raised inside the last timeout-plus-grace
window, and after that nothing ever sweeps it. It stays 'pending' for the life
of that process: `/api/pending` serves it, both apps draw it as an unanswerable
card, the count at the top calls it "waiting on you", and a LATER identical
request is told "the same request is already waiting for you" about a card
nobody is waiting on.

The fix is not a new control, a new route or an APK: `pending()` runs the same
sweep before it reads (`_expire_overdue`), so the list every client is handed
holds only rows still inside their own window. Nothing is approved by that,
and a live card cannot be taken: the deadline is recomputed here, server-side,
at the moment of the read, and no client sends an id it could name a card with.

WHAT THIS PROVES

  1. t_the_start_up_sweep_is_once_per_process
     The defect as it stood: after the first read, `_init()` does not sweep
     again, so a row inserted later and already overdue stays 'pending'.
  2. t_an_overdue_card_is_gone_from_the_next_read
     ... and the next `pending()` settles it: not in the list, row 'expired'
     (never 'denied'), `decided` set, and `history()` still shows the lapse.
  3. t_a_live_card_is_never_removed
     Cards inside their window - one raised now, one ten minutes old, one at
     the very edge of the grace - are all still listed and still 'pending'.
  4. t_a_card_inside_the_grace_is_left_alone
     The 60 seconds `_init()` always allowed is kept: a card one second past
     its deadline is still listed, so a decision landing a moment late is
     still honoured by `check()`'s own late-answer path.
  5. t_a_card_with_no_deadline_is_never_swept
     All four APPROVAL_NEVER_EXPIRES actions, a day old, are still listed.
     That is the whole point of the rest of the patch.
  6. t_a_swept_card_cannot_be_approved_afterwards
     `decide()` returns False on it, so a stale page's Approve is refused
     instead of recording a yes for something that already lapsed.
  7. t_a_clean_queue_settles_nothing
     `_expire_overdue()` returns 0 and leaves a live row alone when there is
     nothing overdue, so the common read does no settling work.
  8. t_a_swept_card_no_longer_blocks_an_identical_request
     `_pending_card_id()` no longer matches it, which is the "already waiting
     for you" refusal that a stuck row used to cause for ever.

HOW THE GATE IS LOADED. `jarvis_gate.py` is the owner's file; this repository
holds the published base in `jarvis-backend/` (see jarvis-backend/README.md and
backend/test_base_matches_repo.py). This suite copies that base into a scratch
folder and applies `no-expiry-cards.patch` to it with `git apply`, so what it
drives is the patch's real output on the file it is published against - not a
copy typed to suit the test.

Needs nothing from the owner's PC and no network. Runs anywhere git does.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
import uuid
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _gitapply  # noqa: E402  (beside this file; its docstring says why)
from _where import REPO  # noqa: E402

PATCH = HERE / "no-expiry-cards.patch"
BASE = REPO / "jarvis-backend"

#: The shipped `approval_timeout_seconds` #378 left on 2026-10-13: 15 minutes.
MINUTES_15 = 15 * 60
#: The margin `_init()` has always allowed between a card's deadline and the
#: sweep that settles it (its `APPROVAL_TIMEOUT + 60`).
GRACE = 60.0
#: The four cards the rest of the patch exists to let wait for the owner.
NEVER_EXPIRES = ("pair_device", "unretire_shared_key", "register_approval_key",
                 "restore_backup")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# The published base, plus this patch, as a module
# ---------------------------------------------------------------------------

def built():
    """(folder holding the patched gate, why not)."""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the patch cannot be applied"
    if not PATCH.is_file():
        return None, f"{PATCH.name} is missing"
    base_gate = BASE / "jarvis_gate.py"
    if not base_gate.is_file():
        return None, f"{base_gate} is missing"
    d = Path(tempfile.mkdtemp(prefix="jarvis-read-sweep-"))
    d.joinpath("jarvis_gate.py").write_bytes(
        base_gate.read_bytes().replace(b"\r\n", b"\n"))
    env = _gitapply.env_for(git, d)
    r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                        "apply", str(PATCH)], cwd=str(d), capture_output=True,
                       text=True, env=env)
    if r.returncode != 0:
        return None, (f"git apply refused {PATCH.name}: "
                      f"{(r.stderr or r.stdout).strip().splitlines()[:2]}")
    return d, ""


def load_gate(folder: Path):
    """Import `jarvis_gate` out of `folder`, fresh, with its own approvals DB.

    Fresh every time: the module reads `JARVIS_APPROVALS_DB` at import and its
    `_init()` runs once per PROCESS, so a module left in `sys.modules` carries
    an earlier test's database and `_inited` flag into the next one - which is
    the very state this suite is about.
    """
    cfg = Path(tempfile.mkdtemp(prefix="jarvis-read-sweep-state-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(cfg / "approvals.db")
    os.environ.pop("JARVIS_APPROVAL_TIMEOUT", None)
    os.environ["JARVIS_NTFY_TOPIC"] = ""      # never a socket, said explicitly
    os.environ["JARVIS_NTFY_SERVER"] = ""
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = cfg
    fw.LOG_DIR = cfg
    # A real tier table: an empty one is "the policy could not be read" and
    # `check()` refuses before any card exists, which would prove nothing.
    tiers = {a: "ask" for a in NEVER_EXPIRES + ("send_email", "search_the_web")}
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": "ask",
                     "approval_timeout_seconds": MINUTES_15,
                     "tiers": tiers},
    }
    fw.audit_log = lambda *a, **k: None
    sys.modules["jarvis_framework"] = fw
    for name in [n for n in sys.modules if n.startswith("jarvis_gate")]:
        del sys.modules[name]
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return __import__("jarvis_gate")


# ---------------------------------------------------------------------------
# Reading and writing the gate's own rows
# ---------------------------------------------------------------------------

def seed(G, action: str = "send_email", age: float = 0.0,
         state: str = "pending", detail: str = "{}", prompt: str = "") -> str:
    """Write one stored card `age` seconds old, exactly as `check()` would.

    A row written straight into the table is the state a card is left in when
    its waiting thread dies - which is the case this suite is about and the one
    a `check()`-driven test cannot reach without killing a process.
    """
    G._init()
    rid = uuid.uuid4().hex[:12]
    with closing(G._connect()) as c:
        c.execute(
            "INSERT INTO approvals (id,action,tier,detail,prompt,state,created,"
            "raised,target_digest) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, action, "ask", detail, prompt, state, time.time() - age,
             None, None))
    return rid


def row_of(G, rid: str):
    with closing(G._connect()) as c:
        r = c.execute("SELECT id,action,state,created,decided,decided_by"
                      " FROM approvals WHERE id=?", (rid,)).fetchone()
    return dict(r) if r is not None else None


def listed(G) -> list:
    return [r["id"] for r in G.pending()]


# ---------------------------------------------------------------------------
# 1. The defect, as it stood
# ---------------------------------------------------------------------------

def t_the_start_up_sweep_is_once_per_process():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()                       # the first read: _init() runs, _inited set
    rid = seed(G, age=MINUTES_15 + 120)   # already two minutes overdue
    G._init()                         # everything the old read path did
    row = row_of(G, rid)
    check("the start-up sweep is once per process: _init() does not touch a "
          "row inserted after the first read", row["state"] == "pending", row)
    check("...and that is the state the owner's phone was in: a 'pending' row "
          "whose deadline has long passed", row["decided"] is None, row)


# ---------------------------------------------------------------------------
# 2. What the fix does
# ---------------------------------------------------------------------------

def t_an_overdue_card_is_gone_from_the_next_read():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    overdue = seed(G, action="send_email", age=MINUTES_15 + GRACE + 60)
    live = seed(G, action="search_the_web", age=5)
    now_listed = listed(G)
    check("an overdue card is not in the list the next read answers",
          overdue not in now_listed, now_listed)
    check("...while a card inside its window still is",
          live in now_listed, now_listed)
    row = row_of(G, overdue)
    check("its row is 'expired' - a lapse, not a decision",
          row["state"] == "expired", row)
    check("...and it carries the moment it lapsed, so the record is complete",
          row["decided"] is not None, row)
    hist = {r["id"]: r for r in G.history(20)}
    check("history() still shows it as expired, so nothing was hidden",
          hist.get(overdue, {}).get("state") == "expired", hist.get(overdue))
    check("the live card's row is untouched",
          row_of(G, live)["state"] == "pending", row_of(G, live))


# ---------------------------------------------------------------------------
# 3. A live card is never removed
# ---------------------------------------------------------------------------

def t_a_live_card_is_never_removed():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    ages = {"a card raised a moment ago": 0.0,
            "a card ten minutes old": 600.0,
            "a card at the very edge of the window": float(MINUTES_15)}
    ids = {name: seed(G, age=age) for name, age in ages.items()}
    now_listed = listed(G)
    for name, rid in ids.items():
        check(f"{name} is still waiting after the read", rid in now_listed, now_listed)
        check(f"{name} is still 'pending' in the table",
              row_of(G, rid)["state"] == "pending", row_of(G, rid))


# ---------------------------------------------------------------------------
# 4. The grace the start-up sweep always gave
# ---------------------------------------------------------------------------

def t_a_card_inside_the_grace_is_left_alone():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    just_past = seed(G, age=float(MINUTES_15) + 1.0)
    check("a card one second past its deadline is still listed inside the "
          "60-second grace", just_past in listed(G), listed(G))
    check("...and is still 'pending', so check()'s late-answer path can honour "
          "a decision that lands a moment late",
          row_of(G, just_past)["state"] == "pending", row_of(G, just_past))


# ---------------------------------------------------------------------------
# 5. The four cards that have no deadline at all
# ---------------------------------------------------------------------------

def t_a_card_with_no_deadline_is_never_swept():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    ids = {a: seed(G, action=a, age=86400.0) for a in NEVER_EXPIRES}
    now_listed = listed(G)
    for action, rid in ids.items():
        check(f"{action}, a day old, is still waiting", rid in now_listed, now_listed)
        check(f"{action}'s row is still 'pending'",
              row_of(G, rid)["state"] == "pending", row_of(G, rid))


# ---------------------------------------------------------------------------
# 6. A swept card cannot be approved afterwards
# ---------------------------------------------------------------------------

def t_a_swept_card_cannot_be_approved_afterwards():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    overdue = seed(G, age=MINUTES_15 + GRACE + 60)
    G.pending()                       # settles it
    check("decide() refuses a card that has lapsed, so a stale page's Approve "
          "is not recorded as a yes", G.decide(overdue, True, by="the test") is False)
    row = row_of(G, overdue)
    check("...and nobody is recorded as having decided it: a lapse has no "
          "decider", row["decided_by"] is None, row)


# ---------------------------------------------------------------------------
# 7. The common read does no settling work
# ---------------------------------------------------------------------------

def t_a_clean_queue_settles_nothing():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    live = seed(G, age=5)
    with closing(G._connect()) as c:
        settled = G._expire_overdue(c)
    check("a queue with nothing overdue settles 0 rows", settled == 0, settled)
    check("...and leaves the live card alone",
          row_of(G, live)["state"] == "pending", row_of(G, live))


# ---------------------------------------------------------------------------
# 8. A stuck row no longer blocks the same request for ever
# ---------------------------------------------------------------------------

def t_a_swept_card_no_longer_blocks_an_identical_request():
    folder, why = built()
    if folder is None:
        raise RuntimeError(why)
    G = load_gate(folder)
    G.pending()
    action, detail, prompt = "send_email", {}, "send it"
    stale = seed(G, action=action, age=MINUTES_15 + GRACE + 60,
                 detail="{}", prompt=prompt)
    with closing(G._connect()) as c:
        check("a stuck card is what 'the same request is already waiting for "
              "you' was matching",
              G._pending_card_id(c, action, detail, prompt) == stale)
    G.pending()
    with closing(G._connect()) as c:
        check("...and after the read settles it, a new identical request gets "
              "a card of its own",
              G._pending_card_id(c, action, detail, prompt) is None)


if __name__ == "__main__":
    for fn in (t_the_start_up_sweep_is_once_per_process,
               t_an_overdue_card_is_gone_from_the_next_read,
               t_a_live_card_is_never_removed,
               t_a_card_inside_the_grace_is_left_alone,
               t_a_card_with_no_deadline_is_never_swept,
               t_a_swept_card_cannot_be_approved_afterwards,
               t_a_clean_queue_settles_nothing,
               t_a_swept_card_no_longer_blocks_an_identical_request):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
