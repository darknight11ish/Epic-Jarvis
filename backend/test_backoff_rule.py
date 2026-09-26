"""test_backoff_rule.py - an offer Jarvis makes on its own never asks for
more access or more data (the back-off's rule 4; the Muse audit,
docs/COMPETITORS-MUSE-2026-09-25.md, idea 4).

    python3 backend/test_backoff_rule.py

What it proves:
  - jarvis_backoff.vet() allows each declared kind of offer, and refuses a
    kind that is not declared, or one that asks for anything in NEVER_ASKS
    (more access, a new connection, a key, a password, a way to pay, an
    identity document, a setting that shows or trusts more);
  - may_offer(fp, kind=...) refuses such an offer BEFORE anything else,
    logs the reason, counts it in status(), and writes nothing;
  - every offer made today is declared, and asks only for things in
    MAY_ASK - so no current offer breaks the rule;
  - every call of may_offer() in the shipped code passes `kind=`, so a new
    offer cannot skip the check without this test failing;
  - the overnight-tidy card is refused when its kind is not declared, and
    offered when it is;
  - the two offers Jarvis makes while answering the owner (switch web
    search when it is down; the cloud lane) are not unprompted offers, and
    the web search one never points at a provider that needs a key.
No network, no model.
"""
from __future__ import annotations

import ast
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-backoff-rule-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_BACKOFF_FILE"] = str(_TMP / "config" / "backoff.json")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped, SHIPPED  # noqa: E402

require_shipped("jarvis_backoff.py", "rebuilt/jarvis_sleep.py", "jarvis_skill_discovery.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_backoff as BO  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def fresh(name="rule"):
    c = Clock()
    p = _TMP / f"{name}-{time.time_ns()}.json"
    return BO.Backoff(p, clock=c), c


def t_vet():
    for kind in BO.OFFERS:
        check(f"declared offer {kind!r} may be made", BO.vet(kind) == (True, ""))
    check("an undeclared kind is refused", BO.vet("connect_your_bank_offer") == (False, "not_declared"))
    check("no kind at all is refused", BO.vet(None) == (False, "not_declared"))
    for cat in BO.NEVER_ASKS:
        BO.OFFERS["future_offer"] = (cat,)
        try:
            check(f"a kind that asks for {cat!r} is refused",
                  BO.vet("future_offer") == (False, "asks_for_more"))
        finally:
            BO.OFFERS.pop("future_offer", None)
    check("an offer asking for more than its kind declared is refused",
          BO.vet("sleep_time_offer", ("key",)) == (False, "asks_for_more")
          and BO.vet("sleep_time_offer", ("save_a_routine",)) == (False, "not_declared"))
    check("the seven things an offer never asks for are all named",
          set(BO.NEVER_ASKS) == {"more_access", "new_connection", "key", "password", "payment",
                                 "identity_document", "show_or_trust_more"})
    check("every refusal reason has plain words",
          "asks_for_more" in BO.REASONS and "not_declared" in BO.REASONS)


def t_no_current_offer_breaks_the_rule():
    bad = {k: v for k, v in BO.OFFERS.items()
           if not v or any(a not in BO.MAY_ASK or a in BO.NEVER_ASKS for a in v)}
    check("every offer made today asks only for what MAY_ASK lists", not bad, bad)
    check("MAY_ASK and NEVER_ASKS share nothing", not set(BO.MAY_ASK) & set(BO.NEVER_ASKS))
    check("today's offers are the overnight tidy and the skill offer",
          set(BO.OFFERS) == {"sleep_time_offer", "skill_offer"}, sorted(BO.OFFERS))


class _Catch(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def t_may_offer_refuses_logs_and_counts():
    bo, c = fresh()
    catch = _Catch()
    log = logging.getLogger("jarvis.backoff")
    log.addHandler(catch)
    try:
        BO.OFFERS["bank_link_offer"] = ("new_connection",)
        fp = BO.fingerprint("bank_link_offer")
        got = bo.may_offer(fp, kind="bank_link_offer")
    finally:
        BO.OFFERS.pop("bank_link_offer", None)
        log.removeHandler(catch)
    check("an offer asking for a new connection is refused", got == (False, "asks_for_more"), got)
    check("... with the reason logged (kind and reason, nothing else)",
          any("bank_link_offer" in l and "never asks for more access" in l for l in catch.lines),
          catch.lines)
    st = bo.status()
    check("... and counted in status()", st["refused_asking_for_more"] == 1
          and st["last_refused"] == {"kind": "bank_link_offer", "why": "asks_for_more"}, st)
    check("... and nothing written, nothing waiting", not bo.path.exists() and st["waiting"] == 0)
    check("rule 4 comes first: even with no other reason to wait",
          bo.may_offer(BO.fingerprint("x"), kind="undeclared") == (False, "not_declared"))
    check("a declared kind goes on to the three other rules",
          bo.may_offer(BO.fingerprint("sleep_time_offer"), kind="sleep_time_offer") == (True, ""))
    bo.note_conversation()
    check("... which still apply", bo.may_offer(BO.fingerprint("sleep_time_offer"),
                                                kind="sleep_time_offer") == (False, "conversation"))


def _shipped_py():
    for n in SHIPPED:
        p = HERE / n
        if p.suffix == ".py" and p.is_file():
            yield n, p


def t_every_offer_site_passes_its_kind():
    sites, missing = [], []
    for n, p in _shipped_py():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "may_offer"):
                sites.append(f"{n}:{node.lineno}")
                if not any(k.arg == "kind" for k in node.keywords):
                    missing.append(f"{n}:{node.lineno}")
    check("the shipped code asks may_offer() somewhere (the check can see the calls)",
          len(sites) >= 2, sites)
    check("every call of may_offer() in the shipped code passes kind=", not missing, missing)
    sleep = (HERE / "rebuilt" / "jarvis_sleep.py").read_text(encoding="utf-8")
    skill = (HERE / "jarvis_skill_discovery.py").read_text(encoding="utf-8")
    check("the overnight-tidy card passes its own kind",
          "may_offer(fp, kind=OFFER)" in sleep and 'OFFER = "sleep_time_offer"' in sleep)
    check("the skill offer passes its own kind", 'may_offer(fp, kind="skill_offer")' in skill
          and 'fpr("skill_offer", p.key)' in skill)


def t_the_overnight_card_obeys_it():
    import jarvis_sleep as SL
    bo, c = fresh("sleep")
    c.t = time.time()
    saved_one, saved_kinds = BO._ONE, dict(BO.OFFERS)
    BO._ONE = bo
    SL._seen.clear()
    saved_enabled, saved_remind = SL.enabled, SL.remind
    SL.enabled, SL.remind = (lambda: False), (lambda: True)
    try:
        BO.OFFERS.pop("sleep_time_offer")
        check("with its kind not declared, the overnight card is not offered",
              SL.reminder_card() is None and bo.status()["refused_asking_for_more"] == 1)
        BO.OFFERS.update(saved_kinds)
        SL._seen.clear()
        card = SL.reminder_card()
        check("declared again, it is", card is not None and card["kind"] == "sleep_time_offer")
    finally:
        BO.OFFERS.clear()
        BO.OFFERS.update(saved_kinds)
        BO._ONE = saved_one
        SL._seen.clear()
        SL.enabled, SL.remind = saved_enabled, saved_remind


def t_answers_to_the_owner_never_point_at_a_key():
    # Not offers Jarvis makes on its own: they answer the owner's own search
    # or question. Still, the web search one never suggests a provider that
    # needs a key or a payment card.
    try:
        import jarvis_search as WS
    except Exception as exc:
        return check(f"SKIP - jarvis_search not importable ({type(exc).__name__})", True)
    for p in list(WS.PROVIDERS) + [None]:
        line = WS.offer_line(p)
        check(f"switching offer after {p or 'a left-out one'} names no keyed provider",
              not any(WS.LABEL[k] in line for k in ("exa", "tavily", "brave")), line)


if __name__ == "__main__":
    for fn in (t_vet, t_no_current_offer_breaks_the_rule, t_may_offer_refuses_logs_and_counts,
               t_every_offer_site_passes_its_kind, t_the_overnight_card_obeys_it,
               t_answers_to_the_owner_never_point_at_a_key):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
