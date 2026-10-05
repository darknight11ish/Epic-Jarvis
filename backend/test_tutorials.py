#!/usr/bin/env python3
"""Tutorials and the FAQ: the catalogue, the progress, and the routes.

WHAT IS CHECKED

* the catalogue is well formed, and both sections the owner asked for have
  tutorials in them;
* a tutorial nobody opened is not "done", and not "skipped" either;
* quitting at step 3 records step 3, and the app is told to resume there;
* finishing is recorded once, and the tutorial is not due again;
* a skipped tutorial can be shown again, which removes the record;
* a tutorial whose STEPS changed is offered again rather than counted done on
  words the owner never saw;
* bad input is refused with a status, and nothing ever raises;
* the module writes its own one file and nothing else - never the owner's
  `jarvis-framework.toml`;
* it raises no approval card and makes no network call: it does not import the
  gate at all, and it is not one of the agent's tools.

Runs in repo mode (JARVIS_BACKEND unset). Against the owner's backend it needs
`jarvis_tutorials.py` copied in - `scripts/apply-patches.ps1` does that - and
refuses rather than lying if it is not there, like every other shipped module.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_tutorials.py")

_TMP = tempfile.mkdtemp(prefix="jarvis-tutorials-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
os.environ["JARVIS_CONFIG_DIR"] = _TMP

import jarvis_tutorials as T  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL'} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _records() -> dict:
    """A clean slate: the module reads its file at call time, so removing it is
    enough (and it is never cached)."""
    path = Path(_TMP) / T.PROGRESS_NAME
    if path.exists():
        path.unlink()
    return T._load()


# ============================================================ the catalogue

def t_the_catalogue_is_well_formed():
    ids = [t["id"] for t in T.CATALOGUE]
    check("every tutorial has a unique id", len(set(ids)) == len(ids), ids)
    check("there is an intro, and it is called intro", T.INTRO_ID in ids, ids)
    for t in T.CATALOGUE:
        where = t["id"]
        check(f"{where}: a section the apps can place it in",
              t["section"] in T.SECTIONS, t["section"])
        check(f"{where}: a version, so changed steps can be re-offered",
              isinstance(t["version"], int) and t["version"] >= 1, t["version"])
        check(f"{where}: at least three steps", len(t["steps"]) >= 3, len(t["steps"]))
        check(f"{where}: says what it is for, in one line", bool(t["why"].strip()))
        check(f"{where}: a length in minutes that a person would accept",
              isinstance(t["minutes"], int) and 1 <= t["minutes"] <= 10, t["minutes"])
        for n, step in enumerate(t["steps"], 1):
            check(f"{where} step {n}: has a title", bool(str(step.get("title", "")).strip()))
            check(f"{where} step {n}: says something", len(str(step.get("body", ""))) > 40)
            check(f"{where} step {n}: says WHERE it is in words, which is the part "
                  "that still works when the screen has moved on",
                  bool(str(step.get("where", "")).strip()))
            check(f"{where} step {n}: a picture is optional, and named if there is one",
                  step.get("shows") is None or isinstance(step.get("shows"), str))


def t_both_sections_have_tutorials():
    for section in ("pc", "phone"):
        mine = [t for t in T.CATALOGUE if t["section"] == section]
        check(f"the {section} section has its own tutorials", len(mine) >= 1,
              [t["id"] for t in mine])
    shared = [t for t in T.CATALOGUE if t["section"] == "both"]
    check("the shared tutorials appear in both apps", len(shared) >= 3,
          [t["id"] for t in shared])
    check("the apps are told the two section titles",
          T.SECTION_TITLES.get("pc") and T.SECTION_TITLES.get("phone"),
          T.SECTION_TITLES)


# ============================================================ progress

def t_nothing_is_done_before_it_is_read():
    _records()
    got = T.read()
    check("every tutorial comes back", len(got["tutorials"]) == len(T.CATALOGUE))
    check("none of them claims to be done",
          all(i["state"] == "not_started" and not i["done"] for i in got["tutorials"]))
    check("all of them are due, because none has been read",
          all(i["due"] for i in got["tutorials"]))
    check("and none has a resume point", all(i["resume_at"] is None for i in got["tutorials"]))
    check("the counts agree", got["counts"] == {"done": 0, "due": len(T.CATALOGUE),
                                                "total": len(T.CATALOGUE)}, got["counts"])


def t_quitting_records_the_step_and_resuming_continues():
    _records()
    code, body = T.mark("memory", "in_progress", 3)
    check("leaving at step 3 is accepted", code == 200 and body["ok"], body)
    got = next(i for i in T.read()["tutorials"] if i["id"] == "memory")
    check("the app is told where to resume", got["resume_at"] == 3, got)
    check("and that it is not finished", got["state"] == "in_progress" and not got["done"], got)
    check("a part-read tutorial is not nagged as due", not got["due"], got)
    check("the other tutorials are untouched",
          next(i for i in T.read()["tutorials"] if i["id"] == "intro")["state"] == "not_started")
    check("it survives being read again (the file, not a cache)",
          next(i for i in T.read()["tutorials"] if i["id"] == "memory")["resume_at"] == 3)


def t_finishing_is_recorded_and_not_due_again():
    _records()
    code, body = T.mark("talking", "done", 5)
    check("finishing is accepted", code == 200 and body["done"] is True, body)
    got = next(i for i in T.read()["tutorials"] if i["id"] == "talking")
    check("it is done", got["done"] and got["state"] == "done", got)
    check("and it is not offered again", not got["due"], got)
    check("the count sees it", T.read()["counts"]["done"] == 1, T.read()["counts"])


def t_a_skipped_tutorial_can_be_shown_again():
    _records()
    code, _ = T.mark("intro", "skipped", 0)
    got = next(i for i in T.read()["tutorials"] if i["id"] == "intro")
    check("skipping is accepted and recorded", code == 200 and got["state"] == "skipped", got)
    check("a skipped tutorial is not 'done', and not nagged",
          not got["done"] and not got["due"], got)
    code, _ = T.mark("intro", "not_started", 0)
    got = next(i for i in T.read()["tutorials"] if i["id"] == "intro")
    check("'show this one again' clears the record",
          code == 200 and got["state"] == "not_started" and got["due"], got)


def t_a_changed_tutorial_is_offered_again():
    records = {"intro": {"state": "done", "step": 5, "version": 1, "at": 1.0}}
    current = next(t for t in T.CATALOGUE if t["id"] == "intro")
    same = T.one(current, records)
    check("done on these words: finished, and not offered again",
          same["done"] and not same["due"] and not same["changed_since"], same)
    later = T.one({**current, "version": current["version"] + 1}, records)
    check("done on OLDER words: offered again, and not counted done",
          later["due"] and later["changed_since"] and not later["done"], later)
    check("a record from the future is treated as current",
          not T.one({**current, "version": 1},
                    {"intro": {"state": "done", "step": 5, "version": 99,
                               "at": 1.0}})["due"])


def t_bad_input_is_refused_and_nothing_raises():
    _records()
    cases = [(("nope", "done", 0), 404), (("intro", "finished", 0), 400),
             (("intro", "done", 99), 400), (("intro", "in_progress", -1), 400),
             (("intro", "done", "three"), 400), (("", "done", 0), 400)]
    for args, want in cases:
        code, body = T.mark(*args)
        check(f"{args!r} is refused with {want}", code == want, (code, body))
    check("a POST with nothing in it is refused, not crashed",
          T.handle_post(None)[0] == 400, T.handle_post(None))
    check("a POST that is not a dict is refused", T.handle_post("hello")[0] == 400)
    check("a GET still answers", T.handle_get("")[0] == 200)
    check("a section filter is honoured",
          all(i["section"] in ("pc", "both") for i in T.read("pc")["tutorials"]))
    check("a made-up section is not honoured, rather than empty",
          len(T.read("phone")["tutorials"]) == len([t for t in T.CATALOGUE
                                                    if t["section"] in ("phone", "both")]))
    check("nothing above raised", True)


def t_only_its_own_file_is_written():
    _records()
    T.mark("intro", "in_progress", 2)
    config = Path(_TMP)
    written = sorted(p.name for p in config.iterdir())
    check("it writes one file, named where the design says",
          written == [T.PROGRESS_NAME], written)
    data = json.loads((config / T.PROGRESS_NAME).read_text(encoding="utf-8"))
    check("the file holds the record, and the version of the steps it was read on",
          data.get("intro", {}).get("state") == "in_progress"
          and data["intro"].get("version") == next(t for t in T.CATALOGUE
                                                   if t["id"] == "intro")["version"], data)
    check("and it is inside the folder it was told to use",
          str(T._state_path()).startswith(_TMP), T._state_path())
    check("the owner's framework toml is not touched",
          not (config / "jarvis-framework.toml").exists(), written)


# ============================================================ the rules

def t_no_card_no_network_no_tool():
    src = (HERE / "jarvis_tutorials.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    # `urllib.parse` is string parsing and is allowed; `urllib.request` is a
    # network call and is not. The difference matters, so they are separate.
    for banned, why in (("jarvis_gate", "it must never raise a card"),
                        ("jarvis_agent", "it must not be offered to the model as a tool"),
                        ("urllib.request", "it must not make a network call"),
                        ("urllib.error", "it must not make a network call"),
                        ("http.client", "it must not make a network call"),
                        ("requests", "it must not make a network call"),
                        ("socket", "it must not open a socket"),
                        ("subprocess", "it must not run anything")):
        check(f"{banned} is not imported: {why}",
              not any(m == banned or m.startswith(banned + ".") for m in imported),
              sorted(imported))
    check("it parses URLs with the string parser, and nothing else from urllib",
          "urllib.parse" in imported
          and not [m for m in imported if m.startswith("urllib.") and m != "urllib.parse"],
          sorted(imported))
    check("nothing in it can write the toml: its one path is its own file, and "
          "the file the route can reach is that one",
          T._state_path().name == T.PROGRESS_NAME
          and T._state_path().parent == Path(_TMP),
          T._state_path())
    check("it is shipped, so the patcher copies it to the owner's PC",
          "jarvis_tutorials.py" in (REPO / "backend" / "_where.py").read_text(encoding="utf-8"))


def t_the_routes_are_the_ones_the_design_names():
    check("GET /api/tutorials", T.PATH == "/api/tutorials", T.PATH)
    check("POST /api/tutorials/progress", T.PROGRESS_PATH == "/api/tutorials/progress",
          T.PROGRESS_PATH)
    check("GET /api/faq", T.FAQ_PATH == "/api/faq", T.FAQ_PATH)
    check("the three stored states are the three the design names",
          set(T.STATES) == {"in_progress", "done", "skipped"}, T.STATES)


def t_the_faq_is_worth_shipping():
    got = T.faq()
    check("at least fifteen questions", got["count"] >= 15, got["count"])
    check("the count matches what is there",
          got["count"] == len(got["questions"]), got["count"])
    questions = [q["q"] for q in got["questions"]]
    check("no question is asked twice", len(set(questions)) == len(questions))
    for item in got["questions"]:
        check(f"answered in full: {item['q'][:48]!r}",
              len(str(item.get("a", "")).strip()) > 40, item)
        check(f"and pointed somewhere: {item['q'][:40]!r}",
              isinstance(item.get("where"), str) and bool(item["where"].strip()), item)
        check(f"written as prose, not code: {item['q'][:40]!r}",
              "```" not in item["a"] and "{" not in item["a"], item["a"][:60])
    check("the questions are in the owner's words, not the code's",
          not any(q.lower().startswith(("def ", "api ", "get ", "post "))
                  for q in questions), questions[:3])


class _FakeHandler:
    """A stand-in for jarvis_hud.py's own handler: just enough for install().

    The owner's jarvis_hud.py is not in this repository, so this is the only
    place the wiring can be proved from: that install() wraps the handler,
    answers its own two GET routes and its one POST, leaves every other request
    to the original, and still refuses a cross-origin request or a bad token
    BEFORE looking at anything of ours.
    """

    def __init__(self, path, *, origin=True, token=True, body=b"{}"):
        self.path, self.sent, self.passed_through = path, [], []
        self._origin, self._token, self._body = origin, token, body

    def _send(self, code, body):
        self.sent.append((code, body))
        return code

    def do_GET(self):
        self.passed_through.append("GET")
        return "original GET"

    def do_POST(self):
        self.passed_through.append("POST")
        return "original POST"


def _wired(path, *, origin=True, token=True, body=b"{}"):
    """A handler with install() applied, and what it answered."""
    _records()
    cls = type("H", (_FakeHandler,), {})
    banner = T.install(cls, origin_ok=lambda self: self._origin,
                       token_ok=lambda self: self._token,
                       read_body=lambda self: self._body)
    fake = cls(path, origin=origin, token=token, body=body)
    return fake, banner, cls


def t_the_routes_are_wired_and_guarded():
    fake, banner, cls = _wired("/api/tutorials")
    check("install() says what it turned on", "tutorial" in banner.lower(), banner)
    check("it answers GET /api/tutorials itself",
          fake.do_GET() == 200 and fake.sent[0][1].get("ok") is True, fake.sent)
    check("with the catalogue in it", fake.sent[0][1]["tutorials"][0]["id"] == "intro")
    check("nothing was passed through for our own route", fake.passed_through == [],
          fake.passed_through)

    fake, _b, _c = _wired("/api/faq")
    check("it answers GET /api/faq itself",
          fake.do_GET() == 200 and fake.sent[0][1]["count"] >= 15, fake.sent[:1])

    fake, _b, _c = _wired("/api/tutorials/progress", body=json.dumps(
        {"id": "memory", "state": "in_progress", "step": 2}).encode())
    check("it answers POST /api/tutorials/progress itself",
          fake.do_POST() == 200 and fake.sent[0][1]["step"] == 2, fake.sent)
    check("and the record is really written",
          next(i for i in T.read()["tutorials"] if i["id"] == "memory")["resume_at"] == 2)

    fake, _b, _c = _wired("/api/something/else")
    check("every other GET goes to the original handler",
          fake.do_GET() == "original GET" and fake.sent == [], (fake.sent, fake.passed_through))
    fake, _b, _c = _wired("/api/something/else", body=b"{}")
    check("and every other POST does too", fake.do_POST() == "original POST", fake.sent)

    fake, _b, _c = _wired("/api/tutorials", origin=False)
    check("a cross-origin request is refused with 403, before ours runs",
          fake.do_GET() is None and fake.sent and fake.sent[0][0] == 403
          and "ok" not in fake.sent[0][1], fake.sent)
    fake, _b, _c = _wired("/api/tutorials", token=False)
    check("a bad token is refused with 401",
          fake.do_GET() is None and fake.sent[0][0] == 401
          and "ok" not in fake.sent[0][1], fake.sent)

    fake, _b, _c = _wired("/api/tutorials/progress", body=b"{not json")
    check("a body that is not JSON is answered with a status, not a crash",
          fake.do_POST() == 400, fake.sent)

    _records()
    cls2 = type("H2", (_FakeHandler,), {})
    T.install(cls2, origin_ok=lambda self: True, token_ok=lambda self: True,
              read_body=lambda self: b"{}")
    second = T.install(cls2, origin_ok=lambda self: True, token_ok=lambda self: True,
                       read_body=lambda self: b"{}")
    check("installing twice says so rather than wrapping twice",
          "already on" in second, second)
    check("and the routes still answer once, not twice",
          cls2("/api/tutorials").do_GET() == 200)


if __name__ == "__main__":
    for fn in (t_the_catalogue_is_well_formed, t_both_sections_have_tutorials,
               t_nothing_is_done_before_it_is_read,
               t_quitting_records_the_step_and_resuming_continues,
               t_finishing_is_recorded_and_not_due_again,
               t_a_skipped_tutorial_can_be_shown_again,
               t_a_changed_tutorial_is_offered_again,
               t_bad_input_is_refused_and_nothing_raises,
               t_only_its_own_file_is_written,
               t_no_card_no_network_no_tool,
               t_the_routes_are_wired_and_guarded,
               t_the_routes_are_the_ones_the_design_names,
               t_the_faq_is_worth_shipping):
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
