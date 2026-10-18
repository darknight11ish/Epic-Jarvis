"""LM-4 - the owner-only person-dossier route (JARVIS-API section 143).

What this proves, in words:
  * the route is a READ, on the existing brain-reads door, listed once;
  * a request from another device is refused BEFORE the module is imported or
    the name is read, and the refusal carries no name and no dossier word;
  * the module's own answer is passed back unchanged (dossier builder owns
    every field, including the withheld answer while the apps hide it);
  * a missing name, a missing backend and an unreadable module each answer in
    the dossier's own shape with one plain sentence;
  * nothing is written and no name is printed anywhere in the exchange.

Run: python -B backend/test_people_dossier.py
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import sys
import traceback
import types
from urllib.parse import quote

PASSED, FAILED = [], []


def check(what, ok, detail=None):
    if ok:
        PASSED.append(what)
        print(f"ok    {what}")
    else:
        FAILED.append(what)
        print(f"FAIL  {what}")
        if detail is not None:
            print(f"      {detail}")


def fake_module(build):
    mod = types.ModuleType("jarvis_people_crm")
    mod.build_person_dossier = build
    return mod


class FakeGet:
    """The barest handler `install()` can wrap: records what `_send` was given."""

    def __init__(self, path):
        self.path = path
        self.sent = None
        self.client_address = ("127.0.0.1", 50000)
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8765))

    def do_GET(self):          # replaced by install()
        raise AssertionError("the original handler must not run")

    def _send(self, code, body):
        self.sent = (code, body)


def t_the_route_is_a_read_listed_once():
    import jarvis_brain_reads as B
    check("the dossier is in PATHS exactly once",
          B.PATHS.count(B.PEOPLE_DOSSIER_PATH) == 1, B.PATHS)
    check("the dossier is NOT a POST route (a read has no POST form)",
          B.PEOPLE_DOSSIER_PATH not in B.POST_PATHS, B.POST_PATHS)
    check("the route path is the documented one",
          B.PEOPLE_DOSSIER_PATH == "/api/people/dossier", B.PEOPLE_DOSSIER_PATH)


def t_another_device_learns_nothing_before_the_module_is_read():
    import jarvis_brain_reads as B
    calls = []
    saved_from, saved_mod = B._from_this_pc, sys.modules.get("jarvis_people_crm")
    B._from_this_pc = lambda peer, local: False
    sys.modules["jarvis_people_crm"] = fake_module(
        lambda name: (calls.append(name), {"ok": True, "text": "not reached"})[1])
    try:
        code, out = B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=Priya",
                                 peer="100.64.0.9", local="100.64.0.1")
    finally:
        B._from_this_pc = saved_from
        if saved_mod is None:
            sys.modules.pop("jarvis_people_crm", None)
        else:
            sys.modules["jarvis_people_crm"] = saved_mod
    check("another device gets 403", code == 403, code)
    check("... before the dossier builder is called at all", calls == [], calls)
    check("... and the refusal carries no name and no dossier words",
          "Priya" not in json.dumps(out) and out.get("name") == "", out)


def t_the_answer_is_the_modules_own_dict_unchanged():
    import jarvis_brain_reads as B
    built = {"ok": True, "withheld": False, "name": "Priya", "private": True,
             "active_facts": [{"id": 1, "text": "Sister, lives in Lisbon"}],
             "recent_chat": [], "recent_email": [], "commitments": [],
             "next_event": None, "states": {"facts": "ok"}, "why": {},
             "read": [], "counts": {"active_facts": 1}, "text": "Priya - person dossier."}
    saved_from, saved_mod = B._from_this_pc, sys.modules.get("jarvis_people_crm")
    called = []
    B._from_this_pc = lambda peer, local: True
    sys.modules["jarvis_people_crm"] = fake_module(
        lambda name: (called.append(name), dict(built))[1])
    try:
        code, out = B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=Priya",
                                 peer="127.0.0.1", local="127.0.0.1")
    finally:
        B._from_this_pc = saved_from
        if saved_mod is None:
            sys.modules.pop("jarvis_people_crm", None)
        else:
            sys.modules["jarvis_people_crm"] = saved_mod
    check("this PC gets 200 and the builder's own dict", code == 200 and out == built,
          (code, out))
    check("... the name is handed to the builder, unescaped once",
          called == ["Priya"], called)


def t_a_missing_name_is_a_plain_sentence():
    import jarvis_brain_reads as B
    saved_from = B._from_this_pc
    B._from_this_pc = lambda peer, local: True
    try:
        code, out = B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=",
                                 peer="127.0.0.1", local="127.0.0.1")
        code2, out2 = B.handle_get(B.PEOPLE_DOSSIER_PATH, "",
                                   peer="127.0.0.1", local="127.0.0.1")
    finally:
        B._from_this_pc = saved_from
    check("an empty name is 400, in the dossier's shape",
          code == 400 and out.get("ok") is False and "name" in out, (code, out))
    check("... with one plain sentence and no dossier words",
          "Say whose dossier" in str(out.get("why")), out.get("why"))
    check("... missing entirely is the same answer", code2 == 400 and out2.get("why"),
          (code2, out2))


def t_an_older_backend_says_update_in_the_same_shape():
    import jarvis_brain_reads as B
    saved_from, saved_mod = B._from_this_pc, sys.modules.get("jarvis_people_crm")
    B._from_this_pc = lambda peer, local: True
    sys.modules.pop("jarvis_people_crm", None)
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "jarvis_people_crm":
            raise ImportError("older backend")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = blocked
    try:
        code, out = B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=Priya",
                                 peer="127.0.0.1", local="127.0.0.1")
    finally:
        builtins.__import__ = real_import
        B._from_this_pc = saved_from
        if saved_mod is not None:
            sys.modules["jarvis_people_crm"] = saved_mod
    check("a PC without the module answers 501",
          code == 501 and out.get("ok") is False, (code, out))
    check("... with the apply-patches sentence, in the dossier's shape",
          "apply-patches.ps1" in str(out.get("why")) and "text" in out, out)
    check("... and no name", out.get("name") == "", out)


def t_the_route_echoes_no_name_on_any_refusal():
    import jarvis_brain_reads as B
    saved_from = B._from_this_pc
    B._from_this_pc = lambda peer, local: False
    try:
        _code, out = B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=" + quote("Priya"),
                                  peer="100.64.0.9", local="100.64.0.1")
    finally:
        B._from_this_pc = saved_from
    check("a cross-device refusal never echoes the name",
          "Priya" not in json.dumps(out), out)


def t_a_withheld_module_answer_is_passed_through():
    import jarvis_brain_reads as B
    withheld = {"ok": False, "withheld": True, "why": "Hidden while App lock is on.",
                "name": "", "private": True, "made": 0.0, "states": {}, "read": []}
    saved_from, saved_mod = B._from_this_pc, sys.modules.get("jarvis_people_crm")
    B._from_this_pc = lambda peer, local: True
    sys.modules["jarvis_people_crm"] = fake_module(lambda name: dict(withheld))
    try:
        code, out = B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=Priya",
                                 peer="127.0.0.1", local="127.0.0.1")
    finally:
        B._from_this_pc = saved_from
        if saved_mod is None:
            sys.modules.pop("jarvis_people_crm", None)
        else:
            sys.modules["jarvis_people_crm"] = saved_mod
    check("the module's withheld answer is passed back unchanged",
          code == 200 and out == withheld, (code, out))
    check("... and it carries no name and no facts",
          out.get("name") == "" and "active_facts" not in out, out)


def t_the_install_door_answers_it_after_the_servers_checks():
    import jarvis_brain_reads as B
    saved_from, saved_mod = B._from_this_pc, sys.modules.get("jarvis_people_crm")
    B._from_this_pc = lambda peer, local: True
    sys.modules["jarvis_people_crm"] = fake_module(
        lambda name: {"ok": True, "withheld": False, "name": name, "text": "x"})
    try:
        class Hd(FakeGet):
            pass

        Hd.do_GET = FakeGet.do_GET
        B.install(Hd, origin_ok=lambda s: True, token_ok=lambda s: True,
                  read_body=lambda s: b"{}")
        h = Hd(B.PEOPLE_DOSSIER_PATH + "?name=Priya")
        h.do_GET()
        check("the installed door answers GET /api/people/dossier",
              h.sent and h.sent[0] == 200 and h.sent[1].get("name") == "Priya", h.sent)
        class Hd2(FakeGet):
            pass

        Hd2.do_GET = FakeGet.do_GET
        B.install(Hd2, origin_ok=lambda s: True, token_ok=lambda s: False,
                  read_body=lambda s: b"{}")
        h2 = Hd2(B.PEOPLE_DOSSIER_PATH + "?name=Priya")
        h2.do_GET()
        check("... after the token check, never before it",
              h2.sent and h2.sent[0] == 401, h2.sent)
    finally:
        B._from_this_pc = saved_from
        if saved_mod is None:
            sys.modules.pop("jarvis_people_crm", None)
        else:
            sys.modules["jarvis_people_crm"] = saved_mod


def t_nothing_is_printed_and_no_name_is_logged():
    import jarvis_brain_reads as B
    saved_from, saved_mod = B._from_this_pc, sys.modules.get("jarvis_people_crm")
    B._from_this_pc = lambda peer, local: True
    sys.modules["jarvis_people_crm"] = fake_module(
        lambda name: {"ok": True, "name": name, "text": "a dossier"})
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            B.handle_get(B.PEOPLE_DOSSIER_PATH, "name=CanaryName",
                         peer="127.0.0.1", local="127.0.0.1")
    finally:
        B._from_this_pc = saved_from
        if saved_mod is None:
            sys.modules.pop("jarvis_people_crm", None)
        else:
            sys.modules["jarvis_people_crm"] = saved_mod
    check("the route prints nothing at all", out.getvalue() == "", out.getvalue())
    check("... so no dossier name can reach a log", "CanaryName" not in out.getvalue(),
          out.getvalue())


if __name__ == "__main__":
    for fn in (t_the_route_is_a_read_listed_once,
               t_another_device_learns_nothing_before_the_module_is_read,
               t_the_answer_is_the_modules_own_dict_unchanged,
               t_a_missing_name_is_a_plain_sentence,
               t_an_older_backend_says_update_in_the_same_shape,
               t_the_route_echoes_no_name_on_any_refusal,
               t_a_withheld_module_answer_is_passed_through,
               t_the_install_door_answers_it_after_the_servers_checks,
               t_nothing_is_printed_and_no_name_is_logged):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
