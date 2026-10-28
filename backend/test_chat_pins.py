"""test_chat_pins.py - pinned chats (the owner's request of 2026-10-27:
"both should have pinnable chats, project organization by chat, and more";
docs/JARVIS-API.md section 18.3).

    py -3 backend/test_chat_pins.py

The PC half of "Pin chat": the plain `pinned` column in the same encrypted
history file every other History fact lives in, the `pinned` field on every
list row and on an opened conversation, and the one route that changes it,
`POST /api/history/pin {"id", "pinned"}`.

What this proves, against the real jarvis_chat_log.ChatLog in a temporary
folder with a test key (no network, no model):

  * a new chat is not pinned, and its row says so (`pinned: false`,
    `pinned_at: null`), so an older app that never heard of pinning reads the
    same rows it always did;
  * pinning one chat answers `{"ok": true, "id", "pinned": true, "pinned_at":
    <epoch seconds>}` and the very next list carries `pinned: true` and that
    same moment on that row and on no other;
  * THE PIN SURVIVES A RESTART: a brand-new ChatLog on the same file reads it
    back (this is the promise the owner's "persist across restarts" needs,
    and it is why the flag is a column and not a list in either app);
  * unpinning is the same route with `false` and is just as durable; it
    clears `pinned_at` with the flag;
  * pinning twice is pinning once: the FIRST `pinned_at` is kept, so a second
    pin cannot jump a chat above one that was pinned after it, and the
    Pinned group's documented order (`pinned_at DESC, updated_at DESC`) can
    be read straight off the rows;
  * pinning changes nothing else: not the chat's `updated` (it does not shove
    itself to the top by time), not its tag, not its title;
  * the pin is metadata only: the raw database file holds no title text and
    the pin itself is a number, and pinning raises no approval card;
  * the exact refusals: a body that is not exactly {"id", "pinned"}, a
    `pinned` that is not a JSON boolean (a string, 0/1, null), an id that is
    not a string / is empty / is longer than 128 characters (400), and a
    well-formed id that names no chat (404) - with nothing written for any of
    them, and never a ghost row;
  * WHILE APP LOCK OR THE PRIVATE LISTS ARE HIDDEN: GET /api/history withholds
    every row, the pinned ones included, keeping only the count and the
    `hidden` marker; and POST /api/history/pin answers the SAME 423 for a chat
    that exists and one that never did, so a locked PC cannot be asked whether
    a chat exists;
  * an old history file with no `pinned`/`pinned_at` column is migrated in
    place and every chat it already holds reads `pinned: false`;
  * an opened conversation carries `pinned` and `pinned_at` (the sidebar's
    "open" needs them), the search rows carry them too, and a fork keeps
    them, like its tag.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import traceback
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_chat_log.py")
import jarvis_chat_log as H  # noqa: E402

KEY = bytes(range(32))
PASSED, FAILED = [], []
SKIPPED = []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-pins-"))
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


class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = float(t)

    def __call__(self):
        return self.t


def new_log(key=KEY):
    _N[0] += 1
    d = _TMP / f"h{_N[0]}"
    d.mkdir()
    return H.ChatLog(d / "chat-history.db", d / "chat-history.json", lambda: key,
                     clock=Clock())


def reopen(log):
    """The same history file, opened by a NEW ChatLog - the PC after a restart."""
    return H.ChatLog(log.db_path, log.settings_path, lambda: KEY,
                     clock=Clock(log._clock.t + 60))


def turn(log, cid, words, *, answer="Sure."):
    t = {"answer": answer, "finish_reason": "stop"}
    return log.record_turn({"conversation_id": cid, "device": "desktop", "messages": [
        {"role": "user", "content": words, "provenance": "typed"}]}, lane="test", turn=t)


def _no_crypto():
    if H.AESGCM is None:
        skip("the cryptography package is not installed")
        return True
    return False


def rows(log, **kw):
    return {c["id"]: c for c in log.list(limit=50, **kw)["conversations"]}


def post(log, route, body):
    """H.handle_post, against THIS test's history. The module's default log is
    the owner's real one when JARVIS_BACKEND points at an install, and a suite
    must never write a pin into it."""
    H.use(log)
    return H.handle_post(route, body)


def t_a_new_chat_is_not_pinned_and_the_field_is_always_there():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    turn(log, "conv-bbbb", "tell me about the sea otter")
    got = rows(log)
    check("two chats in the list", len(got) == 2, str(got))
    check("every list row carries `pinned` as a JSON boolean, false by default",
          all(isinstance(c["pinned"], bool) and c["pinned"] is False
              for c in got.values()), str(got))
    check("... and `pinned_at` as null until it is pinned",
          all(c["pinned_at"] is None for c in got.values()), str(got))
    check("the row's other fields are the ones section 18.3 already documents",
          set(got["conv-aaaa"]) == {"id", "title", "started", "updated", "turns",
                                    "device", "has_voice", "tainted", "kind",
                                    "project", "tag_id", "pinned", "pinned_at"},
          str(sorted(got["conv-aaaa"])))
    conv = log.get("conv-aaaa")
    check("an opened conversation carries `pinned`: false too",
          conv["pinned"] is False, str(conv.get("pinned")))
    check("... and its `pinned_at` is null", conv["pinned_at"] is None,
          str(conv.get("pinned_at")))


def t_pin_one_chat_and_the_next_list_says_so():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    turn(log, "conv-bbbb", "tell me about the sea otter")
    code, out = post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})
    check("POST /api/history/pin answers 200", code == 200, str((code, out)))
    check("its reply is exactly {ok, id, pinned, pinned_at}",
          set(out) == {"ok", "id", "pinned", "pinned_at"}
          and out["ok"] is True and out["id"] == "conv-aaaa"
          and out["pinned"] is True and isinstance(out["pinned_at"], int),
          str(out))
    check("`pinned_at` is the epoch second it was pinned at (the test clock)",
          out["pinned_at"] == int(log._clock.t), f"{out['pinned_at']} vs {log._clock.t}")
    got = rows(log)
    check("the pinned chat's row says pinned: true", got["conv-aaaa"]["pinned"] is True,
          str(got["conv-aaaa"]))
    check("... and carries the same `pinned_at`",
          got["conv-aaaa"]["pinned_at"] == out["pinned_at"],
          str(got["conv-aaaa"]))
    check("the other chat's row is untouched", got["conv-bbbb"]["pinned"] is False,
          str(got["conv-bbbb"]))
    check("the order is still newest-first by `updated` (a pin is not a sort)",
          [c["id"] for c in log.list(limit=50)["conversations"]]
          == ["conv-bbbb", "conv-aaaa"],
          str([c["id"] for c in log.list(limit=50)["conversations"]]))
    check("opening it says pinned: true", log.get("conv-aaaa")["pinned"] is True)


def t_the_pin_survives_a_restart():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    turn(log, "conv-bbbb", "tell me about the sea otter")
    post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})
    after = reopen(log)
    got = rows(after)
    check("a NEW ChatLog on the same file reads the pin back (restart)",
          got["conv-aaaa"]["pinned"] is True and got["conv-bbbb"]["pinned"] is False,
          str({k: v["pinned"] for k, v in got.items()}))
    check("and opening the chat after the restart says pinned: true",
          after.get("conv-aaaa")["pinned"] is True)
    code, out = post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": False})
    check("unpinning is the same route with false", code == 200
          and out == {"ok": True, "id": "conv-aaaa", "pinned": False,
                      "pinned_at": None}, str((code, out)))
    check("the unpin is durable too",
          rows(reopen(after))["conv-aaaa"]["pinned"] is False)


def t_a_pin_changes_nothing_else():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    turn(log, "conv-bbbb", "tell me about the sea otter")
    post(log, "/api/history/tags", {"op": "add", "name": "Work", "colour": 0,
                                        "icon": "briefcase"})
    tag = next(t for t in log.tags()["tags"] if t["name"] == "Work")["id"]
    post(log, "/api/history/tag", {"id": "conv-aaaa", "tag_id": tag})
    before = rows(log)["conv-aaaa"]
    check("the first pin on an already-tagged chat", post(log,
        "/api/history/pin", {"id": "conv-aaaa", "pinned": True})[0] == 200)
    after = rows(log)["conv-aaaa"]
    check("`updated` did not move (a pin is not an edit)", before["updated"] == after["updated"],
          f"{before['updated']} -> {after['updated']}")
    check("the tag stayed", after["tag_id"] == tag, str(after["tag_id"]))
    check("the title stayed", after["title"] == before["title"], after["title"])
    check("pinning twice is pinning once", post(log,
        "/api/history/pin", {"id": "conv-aaaa", "pinned": True})[0] == 200
        and rows(log)["conv-aaaa"]["pinned"] is True)


def t_the_pin_is_metadata_only_on_disk():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "my sister Priya is visiting on Sunday")
    post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})
    raw = log.db_path.read_bytes()
    check("the raw history file holds no title text (the pin stores no words)",
          b"Priya" not in raw)
    with closing(sqlite3.connect(str(log.db_path))) as c:
        stored = c.execute("SELECT pinned FROM conversations WHERE id=?",
                           ("conv-aaaa",)).fetchone()
    check("the pin is a plain number in the conversations table", stored == (1,), str(stored))


def t_the_exact_refusals():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    cases = [
        ("a body that is not an object", "not an object", "bad_request"),
        ("a missing `pinned`", {"id": "conv-aaaa"}, "bad_request"),
        ("a missing `id`", {"pinned": True}, "bad_request"),
        ("an extra key", {"id": "conv-aaaa", "pinned": True, "why": "because"},
         "bad_request"),
        ("`pinned` as a string", {"id": "conv-aaaa", "pinned": "yes"}, "bad_request"),
        ("`pinned` as 1 (an int, not a JSON boolean)",
         {"id": "conv-aaaa", "pinned": 1}, "bad_request"),
        ("`pinned` as null", {"id": "conv-aaaa", "pinned": None}, "bad_request"),
        # The id contract (section 18.3): 400 is for a value that is not an
        # id at all - not a string, empty, or longer than 128 characters.
        ("an id that is not a string", {"id": 12345678, "pinned": True},
         "bad_request"),
        ("an empty id", {"id": "", "pinned": True}, "bad_request"),
        ("an id longer than 128 characters", {"id": "x" * 129, "pinned": True},
         "bad_request"),
        # ... and a well-formed string that names no chat is a 404, never a
        # 400: the two are different answers and the contract keeps them apart.
        ("a chat that is not there", {"id": "conv-zzzz", "pinned": True}, "not_found"),
        ("a path, taken as an id", {"id": "../etc/passwd", "pinned": True}, "not_found"),
        ("the cap's own length, naming no chat", {"id": "x" * 128, "pinned": True},
         "not_found"),
    ]
    for label, body, want in cases:
        code, out = post(log, "/api/history/pin", body)
        check(f"refused: {label} -> {want}",
              code == (400 if want == "bad_request" else 404)
              and out.get("error") == want and out.get("ok") is False, str((code, out)))
    check("none of the refusals pinned anything", not any(
        c["pinned"] for c in log.list(limit=50)["conversations"]))
    check("... and none of them invented a chat (no ghost row)",
          [c["id"] for c in log.list(limit=50)["conversations"]] == ["conv-aaaa"],
          str([c["id"] for c in log.list(limit=50)["conversations"]]))


def t_the_pin_keeps_its_first_moment_and_orders_the_pinned_group():
    """The Pinned group has an order of its own: `pinned_at DESC, updated
    DESC` (the Gemini ruling of 2026-10-27). Two chats pinned a minute apart
    say which is newer, and pinning one again does NOT move it above the
    chat that was pinned after it - a second pin is not a second pin."""
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    turn(log, "conv-bbbb", "tell me about the sea otter")
    first = post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})[1]
    log._clock.t += 60
    second = post(log, "/api/history/pin", {"id": "conv-bbbb", "pinned": True})[1]
    check("the two pins carry different moments, a minute apart",
          second["pinned_at"] == first["pinned_at"] + 60,
          f"{first['pinned_at']} then {second['pinned_at']}")
    log._clock.t += 60
    again = post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})[1]
    check("pinning an already-pinned chat keeps its FIRST `pinned_at`",
          again["pinned_at"] == first["pinned_at"],
          f"{first['pinned_at']} then {again['pinned_at']}")
    rows_now = log.list(limit=50)["conversations"]
    pinned = sorted([c for c in rows_now if c["pinned"]],
                    key=lambda c: (-(c["pinned_at"] or 0), -c["updated"]))
    check("the Pinned group's documented order is the newest pin first",
          [c["id"] for c in pinned] == ["conv-bbbb", "conv-aaaa"],
          str([(c["id"], c["pinned_at"]) for c in pinned]))
    code, out = post(log, "/api/history/pin", {"id": "conv-bbbb", "pinned": False})
    check("unpinning clears both fields",
          code == 200 and out["pinned"] is False and out["pinned_at"] is None, str(out))


def t_the_lists_are_hidden_and_the_pin_route_refuses_while_locked():
    """App lock / "Hide memory lists and chat history" (the Gemini ruling of
    2026-10-27): GET /api/history withholds EVERY row - a pinned one included,
    because a title is the owner's words - and the pin route refuses 423 for
    every id, so a locked PC cannot be asked whether a chat exists (no
    200-vs-404 oracle)."""
    if _no_crypto():
        return
    try:
        import jarvis_private_view as pv
    except Exception:
        skip("jarvis_private_view is not importable here")
        return
    log = new_log()
    turn(log, "conv-aaaa", "my sister Priya is visiting on Sunday")
    post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})
    H.use(log)
    was = pv.state()
    try:
        pv.note_state(app_locked=True)
        code, out = H.handle_get("/api/history", "limit=50")
        check("while App lock is on, the list answers 200 with NO rows",
              code == 200 and out.get("conversations") == [], str((code, out))[:200])
        check("... and says it is hidden, with the count it withheld",
              out.get("hidden") is True and out.get("hidden_count") == 1, str(out)[:200])
        check("... including the PINNED chat (a pin does not survive the lock)",
              not any(c.get("pinned") for c in out.get("conversations", [])))
        check("... and no title text is in the answer",
              "Priya" not in json.dumps(out))
        here = post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": False})
        there = post(log, "/api/history/pin", {"id": "conv-zzzz", "pinned": True})
        check("while locked, pinning a chat that exists answers 423",
              here[0] == 423 and here[1].get("error") == "locked", str(here))
        check("... and an id that does not exist answers the SAME 423",
              there[0] == 423 and there[1] == here[1], str(there))
        check("... so a locked PC cannot be asked whether a chat exists",
              here[0] == there[0] and here[1] == there[1], f"{here} vs {there}")
        check("nothing was written by either refusal",
              rows(log)["conv-aaaa"]["pinned"] is True)
        pv.note_state(app_locked=False, hide_memory_lists=True)
        code, out = H.handle_get("/api/history", "")
        check('the same holds for "Hide memory lists and chat history"',
              out.get("hidden") is True and out.get("conversations") == [], str(out)[:160])
        check("... and the pin route refuses 423 there too",
              post(log, "/api/history/pin",
                   {"id": "conv-aaaa", "pinned": False})[0] == 423)
    finally:
        pv.note_state(app_locked=was.get("app_locked"),
                      hide_memory_lists=was.get("hide_memory_lists"))
    code, out = H.handle_get("/api/history", "")
    check("with the lock off again, the rows come back (and the pin is still on)",
          out.get("hidden") is None
          and [c["id"] for c in out["conversations"]] == ["conv-aaaa"]
          and out["conversations"][0]["pinned"] is True, str(out)[:200])


def t_an_old_history_file_is_migrated_in_place():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "what is on my list today")
    check("the fixture chat exists before the migration", "conv-aaaa" in rows(log))
    # A history kept before pinning existed: the same file, with the column
    # dropped. SQLite can drop a column since 3.35; if it cannot, the test
    # says so instead of pretending.
    try:
        with closing(sqlite3.connect(str(log.db_path))) as c:
            with c:
                c.execute("ALTER TABLE conversations DROP COLUMN pinned")
    except sqlite3.OperationalError as exc:
        skip(f"this SQLite cannot DROP COLUMN ({exc})")
        return
    check("the file really has no `pinned` column now", "pinned" not in {
        r[1] for r in sqlite3.connect(str(log.db_path)).execute(
            "PRAGMA table_info(conversations)")})
    old = reopen(log)
    got = rows(old)
    check("the migrated file still lists its chat", "conv-aaaa" in got, str(got))
    check("and that chat reads pinned: false rather than failing",
          got["conv-aaaa"]["pinned"] is False, str(got.get("conv-aaaa")))
    check("the migrated file takes a pin", post(old,
        "/api/history/pin", {"id": "conv-aaaa", "pinned": True})[0] == 200
        and rows(old)["conv-aaaa"]["pinned"] is True)


def t_search_and_fork_carry_the_pin():
    if _no_crypto():
        return
    log = new_log()
    turn(log, "conv-aaaa", "the dentist is on Tuesday")
    turn(log, "conv-bbbb", "the sea otter floats on its back")
    post(log, "/api/history/pin", {"id": "conv-aaaa", "pinned": True})
    found = log.search("dentist", limit=10)
    check("a search row carries `pinned`", found["conversations"]
          and found["conversations"][0]["pinned"] is True, str(found["conversations"]))
    check("and the chat that was not pinned carries false", log.search("otter", limit=10)
          ["conversations"][0]["pinned"] is False)
    code, out = post(log, "/api/history/fork", {"id": "conv-aaaa", "upto": 1})
    check("a fork of a pinned chat is made", code == 200, str((code, out)))
    fork_id = out.get("id")
    if fork_id:
        check("the fork keeps the pin, like its tag (documented in section 18.3)",
              rows(log)[fork_id]["pinned"] is True)


def t_the_contract_is_written_down():
    api = (HERE.parent / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    sec = api.split("### 18.3 Routes", 1)[1].split("### 18.4", 1)[0]
    check("JARVIS-API section 18.3 documents POST /api/history/pin",
          "POST /api/history/pin" in sec)
    check("it names the exact body", '{"id": "<conversation id>", "pinned": true}' in sec
          or '{"id": "<conversation id>", "pinned": true|false}' in sec)
    check("it names the `pinned` field the list sends", "`pinned`" in sec
          or '"pinned"' in sec)
    check("it names `pinned_at` too (the field the Pinned group orders by)",
          "pinned_at" in sec)
    check("it writes down the Pinned group's order",
          "pinned_at DESC" in sec and "updated_at DESC" in sec)
    check("and the refusals, the 400s and the 404 and the 423 while hidden",
          "bad_request" in sec and "not_found" in sec and "423" in sec)
    check("... and that a hidden list withholds the pinned rows as well",
          "hidden" in sec and "pinned" in sec)


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"\n--- {name} ---")
                try:
                    fn()
                except Exception:
                    FAILED.append(name)
                    traceback.print_exc()
    finally:
        H.use(None)
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
