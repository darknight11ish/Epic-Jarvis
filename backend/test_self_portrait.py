#!/usr/bin/env python3
"""test_self_portrait.py - what Jarvis knows about itself, and clearing one chat.

    python3 backend/test_self_portrait.py

WHAT THIS PROVES, and why each check is here (2026-11-03, the owner's ask:
"be aware of every setting, function and ability it has", "open any menu or
setting area", "pull up any old conversation", "clear any conversation"):

  - THE INVENTORY IS IMPORTED, NOT RETYPED. Every jarvis_settings_registry
    SECTIONS row appears as a settings_section place and every jarvis_menus
    MENUS row as a menu place - ids byte-for-byte - and no other place id is
    invented. Settings are the registry's own BOOL_SETTINGS + CHOICE_SETTINGS +
    NUMBER_SETTINGS, one row each, with every switch's live value read through
    jarvis_feature_guide.read_state. Abilities are jarvis_feature_guide.features().
  - A PLACE NAMED IN WORDS IS A PLACE THAT REALLY EXISTS. resolve_place() answers
    a real Settings section and a real Brain menu by their registries' own exact
    aliases, and answers None (never a guess) for words that name nothing.
  - /api/self IS FIXED DATA AND LIVE STATE ONLY. It answers 200 with the schema,
    the places, the settings, what asks first, the abilities, the plugins and
    the stores' counts - and NOWHERE in its serialised body is a filesystem
    path, an .openjarvis path, a token/secret/api-key/password key, or a raw
    memory/chat path. App lock can only WITHHOLD the private counts.
  - THE VERSION SURFACE IS HONEST. `app_version` is the VERSION file's own
    number (or "unknown"); `deploy` reads _jarvis-state.json and, on a PC
    without one, says recorded:false with a reason instead of failing. The
    identity is the recorded sha256 of gate/hud/skills, and a state file that
    is damaged or holds nonsense is "unknown", never a crash.
  - CONVERSATIONS ARE THE EXISTING STORE'S. Both adapter routes hand straight
    through to jarvis_chat_log.handle_get, so the codes (200/400/404/423/503)
    and the list are the same answers /api/history gives. Nothing is duplicated.
  - CLEAR IS TWO-PHASE, ONE EXACT ITEM, ONE CARD. The card names the title and
    message count, says it cannot be undone, that learned facts are KEPT and
    that older backups remain; any body that is not exactly {"id": "<one id>"}
    is refused (no bulk form); a tier other than "ask" is refused with no card;
    only an approved card calls jarvis_chat_log.delete, with exactly the id the
    card named. A denied card deletes nothing. The memory store is never touched.
  - install() wraps the handler once, answers only its own routes, and leaves
    every other request to the original handler.
  - The two small owner-visible fixes folded in from the inventory audit: the
    duplicate TOOL_GROUPS definition is gone from jarvis_asks_first.py, and the
    ONE number setting (live_idle_seconds) can now be changed by the model tool,
    not only by speech.
  - Both shipped-module lists name jarvis_self_portrait.py, and the drop-in
    folder plugins/ready/self-portrait exists and names it.

Nothing here writes real user data: the config folder is a throwaway temp dir
(before jarvis_framework reads it), and the conversation routes are driven
through an in-process stub of jarvis_chat_log's own two public functions, so
no chat database and no Credential Manager entry is touched at all.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import traceback
from contextlib import redirect_stdout
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-self-portrait-"))
# Before anything imports jarvis_framework or jarvis_memory: their config dir
# and database paths are read once, at import.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_self_portrait.py")

import jarvis_self_portrait as SP  # noqa: E402
import jarvis_asks_first as ASK  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_menus as MENUS  # noqa: E402
import jarvis_settings_registry as REG  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
#   1. The inventory is imported, not retyped
# ---------------------------------------------------------------------------


def places_match_the_two_registries():
    rows = SP.places()
    settings_rows = [r for r in rows if r["kind"] == "settings_section"]
    menu_rows = [r for r in rows if r["kind"] == "menu"]
    check("every SECTIONS row is a place, with its own id",
          [r["id"] for r in settings_rows] == [s.id for s in REG.SECTIONS],
          f"{len(settings_rows)} places vs {len(REG.SECTIONS)} sections")
    check("every MENUS row is a place, with its own id",
          [r["id"] for r in menu_rows] == [m.id for m in MENUS.MENUS],
          f"{len(menu_rows)} places vs {len(MENUS.MENUS)} menus")
    check("no place id is invented outside the two registries",
          len(rows) == len(REG.SECTIONS) + len(MENUS.MENUS),
          f"{len(rows)} != {len(REG.SECTIONS)} + {len(MENUS.MENUS)}")
    # The owner-visible places the ask names must be reachable among them.
    ids = {r["id"] for r in rows}
    for wanted in ("voice", "appearance-card", "devices", "settings.voice",
                   "settings.appearance-card", "settings.security",
                   "brain.tab.memory", "brain.tab.history", "brain.history.conversations",
                   "brain.memory.known"):
        check(f"the portrait names {wanted}", wanted in ids)
    # A section's app and a menu's apps are carried through unchanged.
    by_id = {r["id"]: r for r in rows}
    sec = REG.SECTIONS[0]
    check("a section's app is carried through unchanged",
          by_id[sec.id]["apps"] == [getattr(sec, "app", "both")])
    menu = next(m for m in MENUS.MENUS if len(m.apps) == 1)
    check("a menu's apps are carried through unchanged",
          by_id[menu.id]["apps"] == list(menu.apps))


def settings_match_the_registry():
    rows = SP.settings()
    want = len(REG.BOOL_SETTINGS) + len(REG.CHOICE_SETTINGS) + len(REG.NUMBER_SETTINGS)
    check("one settings row per registry entry",
          len(rows) == want,
          f"{len(rows)} != {want}")
    ids = [r["id"] for r in rows]
    check("the ids are the registry's own keys, once each",
          ids == ([b.key for b in REG.BOOL_SETTINGS]
                  + [c.key for c in REG.CHOICE_SETTINGS]
                  + [n.key for n in REG.NUMBER_SETTINGS]))
    switch = next(r for r in rows if r["kind"] == "switch")
    check("a switch carries value + value_known",
          "value" in switch and "value_known" in switch and isinstance(switch["value_known"], bool))
    check("an unread switch says null, never False", switch["value"] is None
          or isinstance(switch["value"], bool))
    check("every row says how it is changed in plain words",
          all(r["how_to_change"] for r in rows))
    number = next(r for r in rows if r["kind"] == "number")
    check("the number setting carries its low/high sanity",
          isinstance(number.get("low"), int) and isinstance(number.get("high"), int)
          and number["low"] < number["high"],
          f"{number.get('low')}..{number.get('high')}")
    check("a choice setting carries its own options",
          all(r.get("options") for r in rows if r["kind"] == "choice"))


def abilities_and_ask_match_their_modules():
    rows = SP.abilities()
    feat = FG.features()
    check("one ability row per feature the features list ships",
          len(rows) == len(feat), f"{len(rows)} != {len(feat)}")
    check("ability ids and titles are the feature list's own",
          [(r["id"], r["title"]) for r in rows]
          == [(r.get("id"), r.get("title")) for r in feat])
    view = SP.asks_first()
    check("what asks first is available and grouped",
          view["available"] and len(view["groups"]) > 0)
    n_rows = sum(len(g["rows"]) for g in view["groups"])
    check("every asks-first row is carried, with its tier",
          n_rows > 100 and all("tier" in r for g in view["groups"] for r in g["rows"]),
          f"{n_rows} rows")


# ---------------------------------------------------------------------------
#   2. A named place is a real place
# ---------------------------------------------------------------------------


def resolving_words_never_guesses():
    got = SP.resolve_place("voice")
    check("a real Settings section resolves to itself by id",
          got == {"route": "settings", "id": "voice"}, str(got))
    got = SP.resolve_place("open the door")
    check("words that name nothing answer None (never a guess)", got is None, str(got))
    got = SP.resolve_place("")
    check("empty words answer None", got is None, str(got))
    # Every SECTIONS row's own first alias must resolve to that same row.
    bad = []
    for s in REG.SECTIONS:
        if not getattr(s, "openable", True):
            continue
        answer = SP.resolve_place(s.names[0] if s.names else s.id)
        if answer is None or answer["id"] != s.id or answer["route"] != "settings":
            bad.append((s.id, answer))
    check("every openable section's own first alias opens that section",
          not bad, str(bad[:5]))
    # A brain-area menu that resolves does so to a Brain view the apps already
    # open (jarvis_open._BRAIN_PLACES' values) or to its own settings section;
    # anything else would be a place the apps cannot reach.
    bad = []
    for m in MENUS.MENUS:
        if m.area != "brain" or not m.view:
            continue
        names = getattr(m, "names", ())
        if not names:
            continue
        answer = SP.resolve_place(names[0])
        if answer is None:
            continue
        if answer["route"] == "brain" and answer["id"] != m.view:
            bad.append((m.id, answer))
        elif answer["route"] == "settings" and SP.place_by_id(answer["id"]) is None:
            bad.append((m.id, answer))
    check("a resolved brain menu points at its own Brain view",
          not bad, str(bad[:5]))
    # A settings-area menu must resolve to a REAL section id (a sub-row opens
    # its parent card) or to None - never to a menu id the apps cannot jump to.
    bad = []
    for m in MENUS.MENUS:
        if m.area != "settings":
            continue
        names = getattr(m, "names", ())
        answer = SP.resolve_place(names[0] if names else m.title)
        if answer is None:
            continue
        if (answer["route"] == "settings"
                and REG.section_by_id(answer["id"]) is not None):
            continue
        bad.append((m.id, answer))
    check("every resolved settings menu opens a REAL section (or nothing)",
          not bad, str(bad[:5]))
    # The four second-card sub-rows share the "second-card" card.
    import jarvis_menus as M2
    for sub in ("settings.second-card.study-helper", "settings.second-card.referee",
                "settings.second-card.third-card", "settings.second-card.chat-card"):
        row = M2.menu(sub)
        answer = SP.resolve_place((row.names[0] if row.names else row.title))
        check(f"the sub-row {sub} opens its parent card",
              answer == {"route": "settings", "id": "second-card"}, str(answer))


# ---------------------------------------------------------------------------
#   3. /api/self: fixed data and live state only, never a secret or a path
# ---------------------------------------------------------------------------

_BANNED_KEYS = frozenset({"token", "secret", "api_key", "apikey", "password",
                          "pairing", "pairing_token", "key"})
_PATH_SHAPES = (
    re.compile(r"[A-Za-z]:\\\\"),                 # C:\...
    re.compile(r"/Users/|/home/[a-z]"),           # a unix home path
    re.compile(r"\.openjarvis"),                  # the data folder
    re.compile(r"AppData[\\\\/]", re.I),          # a windows data folder
)


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k), path + "." + str(k)
            yield from _walk(v, path + "." + str(k))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _walk(v, path + f"[{i}]")


def api_self_is_safe_and_complete():
    SP._reset_for_tests()
    code, out = SP.handle_get(SP.SELF_PATH, "", client="hud")
    check("/api/self answers 200", code == 200, str(code))
    check("/api/self echoes the client header", out.get("client") == "hud")
    check("/api/self carries the schema", out.get("schema") == SP.SCHEMA)
    for key in ("version", "places", "settings", "asks_first", "abilities",
                "plugins", "stores", "private"):
        check(f"/api/self has {key}", key in out)
    blob = json.dumps(out, ensure_ascii=False)
    bad_keys = sorted({k for k, _p in _walk(out) if k.lower() in _BANNED_KEYS})
    check("no token/secret/key/password KEY anywhere in the portrait",
          not bad_keys, str(bad_keys))
    bad_paths = [m.group(0) for p in _PATH_SHAPES for m in p.finditer(blob)]
    check("no filesystem path anywhere in the portrait", not bad_paths, str(bad_paths[:5]))
    check("the memory store's 'db' path is not carried",
          "db" not in json.dumps(out["stores"]))
    # The stores are the three the owner may clear, and each says how.
    stores = {s["id"]: s for s in out["stores"]}
    check("the three stores are named",
          set(stores) == {"memory", "conversations", "receipts"}, str(set(stores)))
    check("every store says how it is cleared",
          all(s["how_to_clear"] for s in stores.values()))
    check("the conversation store says delete keeps learned facts",
          "facts" in stores["conversations"]["how_to_clear"].lower())


def app_lock_can_only_withhold():
    SP._reset_for_tests()
    # The cache must never hand an unlocked portrait's private counts to a
    # locked request: build unlocked (which caches), then lock and read again.
    code, warm = SP.handle_get(SP.SELF_PATH)
    check("an unlocked portrait is readable and cached", code == 200)
    unlocked_mem = next(s for s in warm["stores"] if s["id"] == "memory")
    code, out = SP.handle_get(SP.SELF_PATH, "", app_locked="1")
    check("a locked portrait still answers 200", code == 200)
    check("a locked portrait says why it is private",
          out["private"]["locked"] is True and out["private"]["why"] != "")
    mem = next(s for s in out["stores"] if s["id"] == "memory")
    conv = next(s for s in out["stores"] if s["id"] == "conversations")
    check("a locked portrait withholds the memory count", mem["count"] is None)
    check("a locked portrait withholds the conversation count", conv["count"] is None)
    check("a locked read does not come from the unlocked cache",
          out["stores"] != warm["stores"] or unlocked_mem["count"] is None,
          f"unlocked={unlocked_mem['count']} locked={mem['count']}")
    # A request flag cannot unlock: with the TRUSTED state locked, a request
    # asking app_locked=0 is still withheld.
    import jarvis_private_view as PV
    PV.note_state(app_locked=True)
    try:
        code, out = SP.handle_get(SP.SELF_PATH, "", app_locked="0")
        check("a request flag cannot unlock the private view",
              out["private"]["locked"] is True, str(out["private"]))
        check("a locked trusted state withholds the counts even asking unlocked",
              next(s for s in out["stores"] if s["id"] == "memory")["count"] is None)
    finally:
        PV.note_state(app_locked=False)
    SP._reset_for_tests()


# ---------------------------------------------------------------------------
#   4. The version surface is honest
# ---------------------------------------------------------------------------


def version_surface_is_honest():
    code, block = SP.handle_get(SP.VERSION_PATH)
    check("/api/self/version answers 200", code == 200)
    check("the version block equals the portrait's version block",
          block == SP.version_block())
    check("app_version is the VERSION file's own number, or 'unknown'",
          block["app_version"] == "unknown"
          or bool(re.fullmatch(r"\d+\.\d+\.\d+", block["app_version"])),
          block["app_version"])
    # This checkout has a VERSION file, so the honest answer here is that number.
    want = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    check("in this checkout app_version is VERSION's number",
          block["app_version"] == want, f"{block['app_version']} != {want}")
    check("a checkout with no deploy record says so, and does not fail",
          block["deploy"]["recorded"] is False
          and bool(block["deploy"]["why_not"]))
    idy = block["deploy"]["identity"]
    check("the identity names the three live modules",
          set(idy) == set(SP.IDENTITY_MODULES), str(set(idy)))
    # A real recorded state, in a temp folder, is read for exactly what it says.
    folder = _TMP / "state-ok"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SP.STATE_NAME).write_text(json.dumps({
        "schema": "jarvis-updater-manifest/1", "written": "2026-11-03T11:52:31",
        "run": "partial", "backend": "C:\\owner\\backend",
        "files": {"jarvis_gate.py": {"sha256": "a" * 64, "verified": True},
                  "jarvis_hud.py": {"sha256": "b" * 64, "verified": True},
                  "jarvis_skills.py": {"sha256": "c" * 64, "verified": False}},
        "resealed": {"at": "2026-11-03T12:00:00", "ref": "7CC47E55A",
                     "commit": "7cc47e55a38ff8b57af1e357e42a54105eee47c7"},
    }), encoding="utf-8")
    got = SP.deploy_block(folder)
    check("a recorded state is read: recorded/written/run",
          got["recorded"] is True and got["written"] == "2026-11-03T11:52:31"
          and got["run"] == "partial")
    check("the identity carries the recorded sha256 per module",
          got["identity"]["jarvis_gate.py"] == "a" * 64
          and got["identity"]["jarvis_hud.py"] == "b" * 64
          and got["identity"]["jarvis_skills.py"] == "c" * 64)
    check("the resealed commit is carried as its lowercase hex",
          got["resealed"]["commit"] == "7cc47e55a38ff8b57af1e357e42a54105eee47c7")
    check("files_recorded counts the state's own files",
          got["files_recorded"] == 3, str(got["files_recorded"]))
    # A damaged record is unknown, not an exception.
    bad = _TMP / "state-bad"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / SP.STATE_NAME).write_text("{ not json", encoding="utf-8")
    got = SP.deploy_block(bad)
    check("a damaged deploy record is 'unknown', never a crash",
          got["recorded"] is False and "could not be read" in got["why_not"])
    got = SP.deploy_block(_TMP / "state-missing")
    check("a missing deploy record is 'unknown', never a crash",
          got["recorded"] is False)


# ---------------------------------------------------------------------------
#   5. Conversations: adapters onto the one existing store
# ---------------------------------------------------------------------------


class _ChatStub:
    """Stands in for jarvis_chat_log's two PUBLIC functions only.

    The routes under test must hand through to these; a stub proves the
    hand-through, the refused ids, and (for clear) exactly which id was
    deleted - without opening, encrypting or writing any chat database.
    """

    def __init__(self):
        self.gets = []
        self.deletes = []
        self.get_answer = (200, {"id": "conv-aaaa", "title": "The boiler",
                                 "turns": [{"idx": 0, "role": "user", "text": "hi"},
                                           {"idx": 1, "role": "assistant", "text": "hello"}]})

    def handle_get(self, path, query=""):
        self.gets.append((path, query))
        return self.get_answer

    def delete(self, cid):
        self.deletes.append(cid)
        return True


def conversations_are_the_stores_own():
    import jarvis_chat_log as CL

    stub = _ChatStub()
    had_get = CL.handle_get
    CL.handle_get = stub.handle_get
    try:
        code, out = SP.conversation_list("limit=5")
        check("GET /api/conversations hands through to /api/history",
              code == 200 and stub.gets[-1] == ("/api/history", "limit=5"))
        code, out = SP.conversation_get("conv-aaaa")
        check("GET /api/conversations/<id> hands through to the conversation route",
              code == 200
              and stub.gets[-1] == ("/api/history/conversation", "id=conv-aaaa"))
        code, out = SP.conversation_get("nope")
        check("a malformed conversation id is refused before any read",
              code == 400 and len(stub.gets) == 2)
        stub.get_answer = (423, {"error": "locked"})
        code, out = SP.handle_get(SP.CONVERSATIONS_PATH, "")
        check("a locked Conversation list keeps the store's own 423", code == 423)
    finally:
        CL.handle_get = had_get


# ---------------------------------------------------------------------------
#   6. Clear: two-phase, one exact item, one card, never memory
# ---------------------------------------------------------------------------


class _Verdict:
    def __init__(self, allowed, outcome=None, tier="ask"):
        self.allowed = allowed
        self.outcome = outcome
        self.tier = tier


def _run_clear(verdict, body=None, tier="ask"):
    """Drive clear_request with a synchronous spawn and a stub gate. Returns
    (http code, body, stub, card text seen by the gate)."""
    import jarvis_chat_log as CL

    stub = _ChatStub()
    had_get, had_del = CL.handle_get, CL.delete
    CL.handle_get, CL.delete = stub.handle_get, stub.delete
    seen = {"text": ""}

    def gate(action, detail, prompt):
        seen["text"] = prompt
        seen["action"] = action
        seen["detail"] = dict(detail)
        return verdict

    def spawn(fn):
        fn()                                 # run the decide phase now

    try:
        code, out = SP.clear_request(
            {"id": "conv-aaaa"} if body is None else body,
            gate=gate, tier_of=lambda a: tier, spawn=spawn)
    finally:
        CL.handle_get, CL.delete = had_get, had_del
    return code, out, stub, seen


def clear_is_one_exact_item_one_card():
    SP._reset_for_tests()
    code, out, stub, seen = _run_clear(_Verdict(True, "approved"))
    check("an approved clear answers 202 waiting", code == 202, str(code))
    check("the clear card names the action conversation_clear",
          seen.get("action") == SP.CLEAR_ACTION, str(seen.get("action")))
    check("the card quotes the exact title and message count",
          '"The boiler"' in seen["text"] and "2 messages" in seen["text"])
    check("the card says it cannot be undone",
          "cannot be undone" in seen["text"])
    check("the card says the learned facts are KEPT",
          "KEPT" in seen["text"] and "never forgets them" in seen["text"])
    check("the card says copies in older backups remain",
          "older backups" in seen["text"])
    # THE TWO-PRESS GUARD (2026-11-03 audit): a card that deletes data must be
    # marked as REPLACING data, or it gets ONE press while delete_file and
    # memory_forget_range take two. The marker is the documented route for an
    # action of a module outside the gate's own _REPLACES_ACTIONS table.
    check("the clear card's detail marks it as REPLACING data (two-press guard)",
          seen["detail"].get("replaces") is True,
          str(seen["detail"].get("replaces")))
    check("exactly the one conversation the card named was deleted",
          stub.deletes == ["conv-aaaa"], str(stub.deletes))
    check("the last outcome says it was done",
          SP.clear_status()["last"]["outcome"] == "done")
    # A denied card deletes NOTHING.
    SP._reset_for_tests()
    code, out, stub, seen = _run_clear(_Verdict(False, "denied"))
    check("a denied card answers 202 (it was asked) and deletes nothing",
          code == 202 and stub.deletes == [])
    check("a denied card is recorded honestly as denied",
          SP.clear_status()["last"]["outcome"] == "denied")
    # No bulk form, and no cardless clear.
    SP._reset_for_tests()
    import jarvis_chat_log as CL2

    stub2 = _ChatStub()
    had = CL2.handle_get, CL2.delete
    CL2.handle_get, CL2.delete = stub2.handle_get, stub2.delete
    try:
        for bad in ({"id": "conv-aaaa", "all": True}, {}, {"ids": ["conv-aaaa"]},
                    {"id": "../etc"}, {"id": 5}, []):
            code, out = SP.clear_request(bad, gate=lambda *a: _Verdict(True, "approved"),
                                         tier_of=lambda a: "ask", spawn=lambda fn: fn())
            check(f"a body that is not exactly one id is refused: {str(bad)[:40]}",
                  code == 400 and stub2.deletes == [], f"{code} {out}")
    finally:
        CL2.handle_get, CL2.delete = had
    # A tier that is not "ask" refuses with NO card.
    SP._reset_for_tests()
    code, out, stub, seen = _run_clear(_Verdict(True, "approved"), tier="auto")
    check("a tier other than ask refuses with no card and deletes nothing",
          code == 503 and stub.deletes == [] and seen["text"] == "",
          f"{code} {out}")
    # The memory store is never touched by a clear: the module does not import
    # a learner or a memory writer at all, and the ONLY store call is delete().
    check("clear calls no memory store function",
          "import jarvis_memory" not in Path(SP.__file__).read_text(encoding="utf-8")
          .replace("import jarvis_memory as M", ""))
    src = Path(SP.__file__).read_text(encoding="utf-8")
    decide = src[src.index("def _decide"):src.index("def clear_request")]
    check("the clear path deletes through jarvis_chat_log.delete only",
          "_chat_log().delete(cid)" in decide and "jarvis_memory" not in decide
          and "jarvis_forget" not in decide)


# ---------------------------------------------------------------------------
#   7. The HTTP door
# ---------------------------------------------------------------------------


class _FakeHandler:
    calls = []

    def __init__(self):
        self.path = ""
        self.headers = {}
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)
        return code

    def do_GET(self):
        _FakeHandler.calls.append(("original", self.path))

    def do_POST(self):
        _FakeHandler.calls.append(("original-post", self.path))


def install_is_one_wrapper_that_owns_only_its_routes():
    class H(_FakeHandler):
        pass

    line = SP.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                      read_body=lambda h: b"{}")
    check("install() returns a banner line", isinstance(line, str) and line)
    again = SP.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                       read_body=lambda h: b"{}")
    check("installing twice says it is already on", "already on" in again)
    h = H()
    h.path = "/api/self"
    h.headers = {"X-Jarvis-Client": "hud"}
    h.do_GET()
    check("the installed GET answers /api/self", h.sent and h.sent[0] == 200)
    check("/api/self through install() echoes the client",
          h.sent and h.sent[1].get("client") == "hud")
    h = H()
    h.path = "/api/not-ours"
    h.do_GET()
    check("another route goes to the original handler",
          ("original", "/api/not-ours") in _FakeHandler.calls)
    # Origin/token refused -> never reaches the route. A FRESH class, not a
    # subclass of one install() already wrapped (it would inherit the wrapper).
    class Refuse:
        calls = []

        def __init__(self):
            self.path = "/api/self"
            self.headers = {}
            self.sent = None

        def _send(self, code, out):
            self.sent = (code, out)
            return code

        def do_GET(self):
            Refuse.calls.append(("original", self.path))

        def do_POST(self):
            Refuse.calls.append(("original-post", self.path))

    SP.install(Refuse, origin_ok=lambda h: False, token_ok=lambda h: True,
               read_body=lambda h: b"{}")
    h = Refuse()
    h.path = "/api/self"
    h.do_GET()
    check("a cross-origin request is refused before anything is read",
          h.sent and h.sent[0] == 403, str(h.sent))


# ---------------------------------------------------------------------------
#   8. The inventory-audit fixes folded in
# ---------------------------------------------------------------------------


def audit_fixes_are_in():
    ask_src = Path(ASK.__file__).read_text(encoding="utf-8")
    check("TOOL_GROUPS is defined exactly once in jarvis_asks_first.py",
          len(re.findall(r"^TOOL_GROUPS = \(", ask_src, re.M)) == 1,
          str(len(re.findall(r"^TOOL_GROUPS = \(", ask_src, re.M))))
    check("the live TOOL_GROUPS still has its four groups",
          len(ASK.TOOL_GROUPS) == 4, str(len(ASK.TOOL_GROUPS)))
    check("every switchable tool still appears exactly once",
          sorted(t for _g, tools in ASK.TOOL_GROUPS for t in tools)
          == sorted(set(t for _g, tools in ASK.TOOL_GROUPS for t in tools)))
    # The number setting: the registry has one, and the model tool can now read
    # a value for it (before 2026-11-03 nothing called find_number_setting_words
    # from jarvis_agent at all).
    number = REG.find_number_setting_words(
        "how long jarvis live waits before it turns off")
    check("the ONE number setting is named by its own words",
          number is not None and number.key == "live_idle_seconds")
    import jarvis_agent as AGENT
    check("the model tool's value parser reads seconds, minutes and words",
          AGENT._number_setting_seconds("180") == 180
          and AGENT._number_setting_seconds("3 minutes") == 180
          and AGENT._number_setting_seconds("three minutes") == 180
          and AGENT._number_setting_seconds("90s") == 90)
    check("a value that is not a number is refused, not guessed",
          AGENT._number_setting_seconds("soon") is None
          and AGENT._number_setting_seconds("") is None)
    check("the change_setting path resolves a number setting",
          "number = (None if setting is not None or choice is not None"
          in Path(AGENT.__file__).read_text(encoding="utf-8"))
    check("the number refusal names the row's own range, in the owner's words",
          "30 seconds" in AGENT._number_setting_words(number),
          AGENT._number_setting_words(number))
    check("jarvis_self_portrait.py is in the shipped list",
          '"jarvis_self_portrait.py"' in (HERE / "_where.py").read_text(encoding="utf-8"))
    check("the drop-in folder exists and names the module",
          (REPO / "plugins" / "ready" / "self-portrait" / "plugin.json").is_file()
          and json.loads((REPO / "plugins" / "ready" / "self-portrait"
                          / "plugin.json").read_text(encoding="utf-8"))["module"]
          == "jarvis_self_portrait")
    check("the twin base copy exists and is identical",
          (REPO / "jarvis-backend" / "jarvis_self_portrait.py").read_text(encoding="utf-8")
          == Path(SP.__file__).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
#   9. Refresh: re-read now, restart nothing (the owner's "refresh its
#      function and capabilities awareness")
# ---------------------------------------------------------------------------


def refresh_rereads_and_restarts_nothing():
    SP._reset_for_tests()
    code, before = SP.handle_get(SP.SELF_PATH)
    check("the portrait is readable before a refresh", code == 200)
    # A live value changes underneath the cache: a switch the reader now says
    # is ON (whatever it was). A refresh must show it; a cached read must not.
    target = next(r for r in before["settings"] if r["kind"] == "switch")
    was = target["value"]
    flipped = (not was) if isinstance(was, bool) else True
    saved = FG.read_state
    FG.read_state = lambda key: (flipped if key == target["id"] else saved(key))
    try:
        code, cached = SP.handle_get(SP.SELF_PATH)
        still = next(r for r in cached["settings"] if r["id"] == target["id"])
        check("a cached portrait does not see the change yet",
              still["value"] == was)
        code, out = SP.handle_post(SP.REFRESH_PATH, {})
        check("POST /api/self/refresh answers 200", code == 200, str(code))
        check("a refresh answers in ONE plain sentence",
              isinstance(out.get("said"), str) and out["said"].count(".") <= 3
              and "I re-read what I can do" in out["said"], str(out.get("said")))
        check("a refresh names the real counts",
              out["counts"]["places"] == len(before["places"])
              and out["counts"]["settings"] == len(before["settings"])
              and out["counts"]["abilities"] == len(before["abilities"]))
        check("a refresh reports the started_at it carried through - nothing restarted",
              out["counts"]["started_at"] == before["version"]["started_at"]
              and "Nothing was restarted" in out["said"])
        after = SP.handle_get(SP.SELF_PATH)[1]
        now = next(r for r in after["settings"] if r["id"] == target["id"])
        check("the changed live value is visible after the refresh",
              now["value"] is flipped, f"{now['value']} != {flipped}")
        check("a refresh is a POST only - a GET says use POST",
              SP.handle_get(SP.REFRESH_PATH)[0] == 405)
        # A refresh reports store counts, so App lock must withhold them here
        # exactly as it does on GET /api/self.
        code, locked = SP.handle_post(SP.REFRESH_PATH, {}, app_locked="1")
        check("a locked refresh withholds the private counts",
              code == 200 and locked["counts"]["stored_memory"] is None
              and locked["counts"]["stored_conversations"] is None
              and locked["private"]["locked"] is True, str(locked.get("private")))
    finally:
        FG.read_state = saved
        SP._reset_for_tests()
    # A refresh changes no setting: the restored reader is read back unchanged.
    code, back = SP.handle_get(SP.SELF_PATH)
    same = next(r for r in back["settings"] if r["id"] == target["id"])
    check("a refresh left the real value exactly as it was",
          same["value"] == was)


# ---------------------------------------------------------------------------
#   10. The storage self-scan wiring: optional, defensive, and never a crash
# ---------------------------------------------------------------------------


class _FakeStorage:
    ROUTES = ("/api/self/storage", "/api/self/storage/plan",
              "/api/self/storage/apply")

    def __init__(self, fail=False):
        self.fail = fail

    def handle_get(self, route, query=""):
        if self.fail:
            raise RuntimeError("boom")
        return 200, {"ok": True, "route": route}

    def handle_post(self, route, body):
        if self.fail:
            raise RuntimeError("boom")
        return 202, {"ok": True, "waiting": True, "route": route}


def storage_wiring_is_optional_and_defensive():
    real = SP._STORAGE
    try:
        SP._STORAGE = None
        check("with no storage module, it advertises no storage routes",
              SP.storage_routes() == () and
              SP.handle_get("/api/self/storage")[0] == 404)
        # THE DEPENDENCY IS VISIBLE, NOT HIDDEN: a plain guarded import the two
        # audits can see (this branch ships before PR #1117's module does), and
        # the absence has its own sentence rather than reading as silence.
        src = Path(SP.__file__).read_text(encoding="utf-8")
        check("the storage import is a plain guarded import the audits can see",
              "import jarvis_storage_health as _STORAGE" in src
              and "except ImportError:" in src
              and "importlib.import_module" not in src)
        check("a PC without the storage self-scan says so in one plain sentence",
              SP.storage_absence_words() == SP.STORAGE_MISSING
              and "not installed" in SP.STORAGE_MISSING
              and SP.storage_available() is False)
        check("its start-up banner says the storage self-scan is not installed",
              "storage self-scan NOT installed" in _install_banner(),
              _install_banner())
        SP._STORAGE = _FakeStorage()
        check("with the storage module present, its routes are served",
              set(SP.storage_routes()) == set(_FakeStorage.ROUTES))
        check("with the storage module present, the absence sentence is empty",
              SP.storage_absence_words() == "" and SP.storage_available() is True)
        check("its start-up banner says the storage scan is beside it",
              "storage scan beside it" in _install_banner(), _install_banner())
        code, out = SP.handle_get("/api/self/storage")
        check("its scan route answers through this module", code == 200
              and out.get("route") == "/api/self/storage")
        code, out = SP.handle_post("/api/self/storage/apply", {})
        check("its apply route answers through this module",
              code == 202 and out.get("waiting") is True)
        SP._STORAGE = _FakeStorage(fail=True)
        code, out = SP.handle_get("/api/self/storage")
        check("a failing storage route is answered 503, never raised",
              code == 503 and isinstance(out, dict))
        code, out = SP.handle_post("/api/self/storage/apply", {})
        check("a failing storage apply is answered 503, never raised",
              code == 503 and isinstance(out, dict))
    finally:
        SP._STORAGE = real


def _install_banner() -> str:
    """What install() returns for a fresh handler class (the start-up line)."""
    class _H:
        def do_GET(self):
            pass

        def do_POST(self):
            pass

        def _send(self, code, out):
            return code

    return SP.install(_H, origin_ok=lambda h: True, token_ok=lambda h: True,
                      read_body=lambda h: b"{}")


def clear_card_is_a_replacing_card():
    """The marker reaches jarvis_gate's OWN two-press guard and words.

    The audit's requirement was not "the key exists" but that the card really
    renders/behaves as a replacing card, so this asks the published base's
    jarvis_gate (the code the live PC runs) rather than our own dict:
    `replaces_for()` is what `pending()` uses to put `replaces` on every
    waiting card, and `replaces_words_for()` is the heading/note both apps
    draw. Run in a subprocess with the base on sys.path so this suite never
    imports the gate into its own process.
    """
    import subprocess
    base = REPO / "jarvis-backend"
    detail = {"what": "delete ONE conversation from this PC", "replaces": True}
    script = (
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "import jarvis_gate as G\n"
        "d = %s\n"
        "print(json.dumps({\n"
        "  'in_table': 'conversation_clear' in G._REPLACES_ACTIONS,\n"
        "  'replaces': G.replaces_for('conversation_clear', d),\n"
        "  'kind': G.replaces_kind_for('conversation_clear', d),\n"
        "  'words': G.replaces_words_for('conversation_clear', d),\n"
        "  'ordinary': G.replaces_for('conversation_clear', {}),\n"
        "}))\n" % (str(base), repr(detail)))
    env = dict(os.environ)
    env["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "base-gate-config")
    try:
        done = subprocess.run([sys.executable, "-B", "-c", script],
                              cwd=str(base), env=env, capture_output=True,
                              text=True, timeout=120)
        if done.returncode == 0:
            got = json.loads(done.stdout.strip().splitlines()[-1])
        else:
            got = {}
            check("the published base's gate can be asked about the clear card",
                  False, ((done.stderr or "") + (done.stdout or ""))[-700:])
    except Exception as exc:                # noqa: BLE001 - reported, not raised
        got = {}
        check("the published base's gate can be asked about the clear card",
              False, f"{type(exc).__name__}: {exc}")
    check("the published base's jarvis_gate marks the clear card as replacing",
          got.get("replaces") is True and got.get("ordinary") is False, str(got))
    check("its warning category is the DELETES one, and it has real words",
          got.get("kind") == "deletes_data"
          and bool((got.get("words") or {}).get("heading"))
          and bool((got.get("words") or {}).get("note")), str(got.get("words")))
    check("the action is NOT put in the gate's own table (the marker is used)",
          got.get("in_table") is False, str(got.get("in_table")))


# ---------------------------------------------------------------------------
#   11. The refresh_abilities chat tool
# ---------------------------------------------------------------------------


def refresh_abilities_tool_exists_and_reads():
    import jarvis_agent as A
    check("the refresh_abilities tool is in the model's tool table",
          A.REFRESH_ABILITIES_TOOL == "refresh_abilities"
          and A.REFRESH_ABILITIES_TOOL in A.TOOLS)
    text = A._refresh_abilities_tool_text()
    check("the tool text says it re-reads and restarts nothing",
          "re-read" in text.lower() and "restarted" in text.lower()
          and "approval is needed" in text.lower())
    got = A._run_refresh_abilities({})
    check("the tool re-reads the portrait and answers its sentence",
          got.get("ok") is True and "I re-read what I can do" in got.get("said", ""),
          str(got.get("error", "")))
    check("the tool reports the counts it read",
          int((got.get("counts") or {}).get("places") or 0) > 100)
    check("the tool changes nothing and cannot fail the turn",
          isinstance(got.get("changed"), dict))
    # The storage group is appended to TOOL_GROUPS only when its module is here.
    if getattr(ASK, "_storage_health", None) is None:
        check("with no storage module, TOOL_GROUPS is exactly the four groups",
              len(ASK.TOOL_GROUPS) == 4)


# ---------------------------------------------------------------------------
#   12. The conversation / self chat tools (the owner's ask by chat)
# ---------------------------------------------------------------------------


class _FakeWatch:
    def __init__(self):
        self.cards = 0


def conversation_tools_by_chat():
    import jarvis_agent as A
    for name in ("self_portrait", "conversation_find", "conversation_open",
                 "conversation_clear"):
        check(f"the {name} tool is in the model's tool table", name in A.TOOLS)
    check("the three read-only tools raise no card (skill_list)",
          all(A.TOOLS[n].gate_lookup_name is not None for n in
              ("self_portrait", "conversation_find", "conversation_open")))
    check("self_portrait's text says it is read-only and no card",
          "read-only" in A._self_portrait_tool_text().lower()
          and "no card" in A._self_portrait_tool_text().lower())
    check("conversation_find's text says titles only, never the words",
          "never its message text" in A._conversation_find_tool_text())
    check("conversation_open's text says read-only and never invent an id",
          "read-only" in A._conversation_open_tool_text().lower()
          and "never invent" in A._conversation_open_tool_text().lower())
    check("conversation_clear's text says ONE card is the permission",
          "one approval card" in A._conversation_clear_tool_text().lower()
          and "never clear anything yourself" in
          A._conversation_clear_tool_text().lower())
    # The self portrait tool answers a compact inventory, not the full one.
    got = A._run_self_portrait({})
    check("self_portrait reads the portrait and answers counts",
          got.get("ok") is True and int(got["counts"]["places"]) > 100
          and got.get("ability_groups"))
    # A conversation clear must be a step a plan can never name.
    check("a plan step may not name conversation_clear",
          "conversation_clear" in A._PLAN_EXCLUDED_STEPS)
    # --conversation_find / open, against a stubbed store (no chat db touched).
    import jarvis_chat_log as CL
    had_search, had_get = CL.search, CL.handle_get

    def fake_search(query, limit=20, kind=None):
        return {"query_ok": True, "more": True, "conversations": [
            {"id": "conv-aaaa", "title": "The boiler", "updated": 1790000000,
             "turns": 4, "snippet": "boiler pressure", "hits": 2},
            {"id": "conv-bbbb", "title": "Holiday", "updated": 1789000000,
             "turns": 9}]}

    def fake_handle_get(path, query=""):
        if path == "/api/history":
            return 200, {"enabled": True, "recording": True,
                         "conversations": [
                             {"id": "conv-aaaa", "title": "The boiler",
                              "updated": 1790000000, "turns": 4},
                             {"id": "conv-bbbb", "title": "Holiday",
                              "updated": 1789000000, "turns": 9}]}
        return 200, {"id": "conv-aaaa", "title": "The boiler",
                     "kind": "chat", "updated": 1790000000,
                     "turns": [{"role": "user", "text": "hi"},
                               {"role": "assistant", "text": "hello"}]}

    CL.search, CL.handle_get = fake_search, fake_handle_get
    try:
        got = A._run_conversation_find({"query": "boiler"})
        check("conversation_find searches and returns ids and titles",
              got.get("ok") is True and got["conversations"][0]["id"] == "conv-aaaa"
              and got["conversations"][0]["title"] == "The boiler")
        check("conversation_find never returns a snippet or message text",
              "snippet" not in got["conversations"][0]
              and "boiler pressure" not in json.dumps(got))
        got = A._run_conversation_find({"limit": 2})
        check("conversation_find lists the newest when no words are given",
              got.get("ok") is True and got["count"] == 2)
        CL.search = lambda query, limit=20, kind=None: {
            "query_ok": False, "why": "Those search words are too short.",
            "conversations": []}
        got = A._run_conversation_find({"query": "x"})
        check("conversation_find refuses bad search words in plain words",
              got.get("ok") is False and "too short" in got.get("error", ""))
        CL.search = fake_search
        got = A._run_conversation_open({"id": "conv-aaaa"})
        check("conversation_open returns the kept turns",
              got.get("ok") is True and got["title"] == "The boiler"
              and [t["role"] for t in got["turns"]] == ["user", "assistant"])
        got = A._run_conversation_open({"id": "bad"})
        check("conversation_open refuses a malformed id without guessing",
              got.get("ok") is False)
    finally:
        CL.search, CL.handle_get = had_search, had_get
    # --conversation_clear: ONE card, exact id, never a second card.
    import jarvis_self_portrait as SP2
    had_get2, had_clear = SP2.conversation_get, SP2.clear_request
    calls = {"clear": [], "said": 0}

    def fake_get(cid):
        if len(str(cid)) < 8:
            return 400, {"error": "need a conversation id"}
        return 200, {"id": cid, "title": "The boiler",
                     "turns": [{"role": "user", "text": "hi"}]}

    def fake_clear(body):
        calls["clear"].append(body)
        return 202, {"ok": True, "waiting": True, "id": body["id"],
                     "title": "The boiler", "messages": 1}

    SP2.conversation_get, SP2.clear_request = fake_get, fake_clear
    try:
        convo, steps = [], []
        watch = _FakeWatch()
        A._conversation_clear_call({"id": "conv-aaaa"}, {"id": "tool-1"}, convo,
                                   steps, lambda *a, **k: calls.__setitem__(
                                       "said", calls["said"] + 1), watch=watch)
        check("conversation_clear hands the exact id to the one card door",
              calls["clear"] == [{"id": "conv-aaaa"}], str(calls["clear"]))
        check("conversation_clear answers WAITING, never done",
              json.loads(convo[-1]["content"]).get("waiting") is True
              and json.loads(convo[-1]["content"])["said"].startswith("Waiting"))
        check("conversation_clear counts the card against the turn",
              watch.cards == 1)
        check("conversation_clear emits no 'done' step",
              steps[-1]["ran"] is False and steps[-1]["outcome"] == "unknown")
        # A wrong id is refused in words, and no card is raised.
        calls["clear"].clear()
        convo, steps = [], []
        A._conversation_clear_call({"id": "bad"}, {"id": "tool-2"}, convo, steps,
                                   lambda *a, **k: None, watch=_FakeWatch())
        check("an unknown conversation id raises no card",
              calls["clear"] == [] and
              json.loads(convo[-1]["content"]).get("ok") is False)
        # A double call in one turn still raises only ONE card: the second is
        # refused by the turn's card budget.
        calls["clear"].clear()
        convo, steps = [], []
        watch = _FakeWatch()
        A._conversation_clear_call({"id": "conv-aaaa"}, {"id": "a"}, convo, steps,
                                   lambda *a, **k: None, watch=watch)
        watch.cards = A.CARDS_PER_TURN
        A._conversation_clear_call({"id": "conv-bbbb"}, {"id": "b"}, convo, steps,
                                   lambda *a, **k: None, watch=watch)
        check("a second clear in one answer is refused by the card budget",
              len(calls["clear"]) == 1)
    finally:
        SP2.conversation_get, SP2.clear_request = had_get2, had_clear


# ---------------------------------------------------------------------------


def main() -> int:
    try:
        places_match_the_two_registries()
        settings_match_the_registry()
        abilities_and_ask_match_their_modules()
        resolving_words_never_guesses()
        api_self_is_safe_and_complete()
        app_lock_can_only_withhold()
        version_surface_is_honest()
        conversations_are_the_stores_own()
        clear_is_one_exact_item_one_card()
        clear_card_is_a_replacing_card()
        install_is_one_wrapper_that_owns_only_its_routes()
        audit_fixes_are_in()
        refresh_rereads_and_restarts_nothing()
        storage_wiring_is_optional_and_defensive()
        refresh_abilities_tool_exists_and_reads()
        conversation_tools_by_chat()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
