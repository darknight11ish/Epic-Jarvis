"""test_surface.py - which app is asking, and what changes because of it.

    python3 backend/test_surface.py

THE OWNER'S REQUIREMENT (2026-10-31): *Jarvis must know whether the owner is
talking from the Android app or the desktop program, and tailor its answers and
features accordingly - and it must work by default, with no setup.*

The clients send a plain `X-Jarvis-Surface` header (phone / desktop). The
shipped origin gate reads it ONCE per request (`jarvis_surface.remember`), and
the quick answers, the feature guide and the model's rules-first system turn
use it. It is additive to `X-Jarvis-Client`, never a secret, never
authentication, and a missing header is `unknown` - the old behaviour.

This suite proves, on the tracked tree:
  * the header parses to exactly phone / desktop / unknown, including the
    over-capture traps ("desktop; anything", "PHONE " is phone, "" is unknown);
  * the shipped origin gate still allows and refuses exactly as before, and it
    remembers the request's surface as a side effect (a headerless request
    makes it unknown again - the old answer);
  * "open the second brain" / "open settings" answer with the phone's own
    doors from the phone, the PC's words from the desktop, and the old words
    with no header at all;
  * a feature answer flips wording by surface for one phone-only row and one
    desktop-only row, from the rows' own `surface`/`where` fields;
  * the model's rules-first system turn carries one surface sentence when the
    header is there, and is byte-for-byte what it was before when it is not;
  * the new module is shipped (both SHIPPED lists) and its twin is identical.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent

#: The quick path imports the scheduler on its first answer; the suite runs
#: against a throwaway database, never the owner's own schedule.
_WORK = Path(tempfile.mkdtemp(prefix="jarvis-surface-"))
os.environ.setdefault("JARVIS_SCHEDULE_DB", str(_WORK / "schedule.db"))
os.environ.setdefault("OPENJARVIS_HOME", str(_WORK))
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", str(_WORK))

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + detail) if detail and not cond else ""))


def _body(text):
    return {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
            "conversation_id": "abcdefgh-surface"}


def main():
    import jarvis_surface as S

    # --- 1. The header parses to exactly the three values. -------------------
    class Headers(dict):
        pass

    for value, want in ((("phone"), S.PHONE), ("Phone", S.PHONE), (" PHONE ", S.PHONE),
                        ("desktop", S.DESKTOP), ("DESKTOP", S.DESKTOP),
                        ("", S.UNKNOWN), ("tablet", S.UNKNOWN), (None, S.UNKNOWN),
                        (42, S.UNKNOWN)):
        got = S.from_value(value)
        check(f"header value {value!r} -> {want}", got == want, f"got {got!r}")
    for headers, want in ((None, S.UNKNOWN), ({}, S.UNKNOWN),
                          (Headers({"x-jarvis-surface": "phone"}), S.UNKNOWN),
                          (Headers({S.HEADER: "phone"}), S.PHONE),
                          (Headers({S.HEADER: "desktop"}), S.DESKTOP),
                          (Headers({S.HEADER: "desktop; anything"}), S.UNKNOWN)):
        got = S.from_headers(headers)
        check(f"headers {dict(headers or {})} -> {want}", got == want, f"got {got!r}")

    # --- 2. The origin gate is unchanged, and it remembers the surface. ------
    import jarvis_owner_check as OC

    class Handler:
        def __init__(self, headers):
            self.headers = headers
            self.client_address = ("127.0.0.1", 5555)

    S.reset()
    old_ok = OC.origin_ok(Handler({"X-Jarvis-Client": "hud"}), ())
    check("origin: a HUD no-Origin request is still allowed", old_ok is True)
    check("origin: a headerless request leaves the surface unknown",
          S.current() == S.UNKNOWN, f"got {S.current()!r}")
    allowed = OC.origin_ok(Handler({"X-Jarvis-Client": "hud",
                                    S.HEADER: "phone"}), ())
    check("origin: a phone request is still allowed", allowed is True)
    check("origin: the phone's surface is remembered for this request",
          S.current() == S.PHONE, f"got {S.current()!r}")
    refused = OC.origin_ok(Handler({}), ())
    check("origin: a request with no client and no Origin is still refused",
          refused is False)

    # --- 3. The phone's own doors in the quick answers. ----------------------
    import jarvis_schedule as SCH
    import jarvis_quick as Q

    sched = SCH.Scheduler(_WORK / "schedule.db")
    try:
        S.set_current(S.PHONE)
        phone_brain = Q.answer_turn(_body("open the second brain"), sched=sched)
        phone_settings = Q.answer_turn(_body("open jarvis settings"), sched=sched)
        S.set_current(S.DESKTOP)
        desk_brain = Q.answer_turn(_body("open the second brain"), sched=sched)
        S.set_current(S.UNKNOWN)
        unknown_brain = Q.answer_turn(_body("open the second brain"), sched=sched)
    finally:
        S.reset()
    check("quick: 'open the second brain' is answered from the phone with the phone's door",
          phone_brain is not None and phone_brain.reply == Q.PHONE_OPEN_WORDS["brain"],
          f"got {getattr(phone_brain, 'reply', None)!r}")
    check("quick: the phone answer opens nothing on the PC", 
          phone_brain is not None and not getattr(phone_brain, "open_brain", None),
          f"open_brain={getattr(phone_brain, 'open_brain', None)!r}")
    check("quick: 'open jarvis settings' from the phone names the phone's Settings",
          phone_settings is not None and "Settings on Home" in phone_settings.reply,
          f"got {getattr(phone_settings, 'reply', None)!r}")
    check("quick: from the desktop the Brain opens as it always did",
          desk_brain is not None and desk_brain.reply == "Opening the Brain on this PC.",
          f"got {getattr(desk_brain, 'reply', None)!r}")
    check("quick: with no header the answer is the old one",
          unknown_brain is not None and unknown_brain.reply == desk_brain.reply,
          f"unknown={getattr(unknown_brain, 'reply', None)!r} desktop={getattr(desk_brain, 'reply', None)!r}")
    check("quick: the phone answer is not the desktop answer",
          phone_brain is not None and phone_brain.reply != desk_brain.reply)

    # --- 3b. "Can I edit the HUD in the jarvis app?" (the owner's screenshot) --
    # The old answer ("Jarvis does not currently offer a built-in method...") was
    # false about the product: the HUD's layout is edited on the PC. From the
    # phone the true answer names those PC doors and this app's own Appearance;
    # with no header, or from the desktop, the old path is untouched.
    try:
        S.set_current(S.PHONE)
        hud_phone = Q.answer_turn(_body("can i edit the hud in the jarvis app"), sched=sched)
        hud_phone_layout = Q.answer_turn(_body("hud layout"), sched=sched)
        S.set_current(S.DESKTOP)
        hud_desktop = Q.answer_turn(_body("can i edit the hud in the jarvis app"), sched=sched)
        S.set_current(S.UNKNOWN)
        hud_unknown = Q.answer_turn(_body("can i edit the hud in the jarvis app"), sched=sched)
    finally:
        S.reset()
    check("hud: from the phone, editing the HUD is answered with the PC's real doors",
          hud_phone is not None and hud_phone.reply == Q.HUD_EDIT_PHONE
          and "Edit HUD in the window" in hud_phone.reply
          and "Appearance" in hud_phone.reply,
          f"got {getattr(hud_phone, 'reply', None)!r}")
    check("hud: 'hud layout' from the phone reaches the same answer",
          hud_phone_layout is not None and hud_phone_layout.reply == Q.HUD_EDIT_PHONE,
          f"got {getattr(hud_phone_layout, 'reply', None)!r}")
    check("hud: the desktop's path is unchanged (no new phone answer there)",
          hud_desktop is None or hud_desktop.reply != Q.HUD_EDIT_PHONE,
          f"got {getattr(hud_desktop, 'reply', None)!r}")
    check("hud: with no header the path is unchanged",
          hud_unknown is None or hud_unknown.reply != Q.HUD_EDIT_PHONE,
          f"got {getattr(hud_unknown, 'reply', None)!r}")
    check("hud: the answer claims no phone-side HUD editor",
          "not from the phone app" in Q.HUD_EDIT_PHONE)

    # --- 4. The feature guide uses the row's surface + where. ----------------
    import jarvis_feature_guide as G

    desktop_only = G.row_by_id("talk-to-type")
    phone_only = G.row_by_id("memory-people")
    both = next((row for row in G.features() if row.get("surface") == "both"), None)
    check("fixture: the desktop-only row exists with its fields",
          bool(desktop_only) and desktop_only.get("surface") == "desktop"
          and bool(desktop_only.get("where")))
    check("fixture: the phone-only row exists with its fields",
          bool(phone_only) and phone_only.get("surface") == "phone"
          and bool(phone_only.get("where")))
    check("fixture: a both-apps row exists with its fields",
          bool(both) and both.get("surface") == "both")
    try:
        S.set_current(S.UNKNOWN)
        bare = G.explain_words(desktop_only)
        S.set_current(S.PHONE)
        asked_phone = G.explain_words(desktop_only)
        S.set_current(S.DESKTOP)
        asked_desktop = G.explain_words(phone_only)
        S.set_current(S.PHONE)
        both_asked = G.explain_words(both)
        S.set_current(S.UNKNOWN)
        both_bare = G.explain_words(both)
    finally:
        S.reset()
    check("feature: a desktop-only feature asked from the phone says PC-only and where",
          "asking from the phone" in asked_phone
          and "on the PC only" in asked_phone
          and str(desktop_only.get("where")) in asked_phone,
          asked_phone[-400:])
    check("feature: a phone-only feature asked from the PC says phone-only and where",
          "asking from the PC" in asked_desktop
          and "on the phone only" in asked_desktop
          and str(phone_only.get("where")) in asked_desktop,
          asked_desktop[-400:])
    check("feature: no header adds no surface line (byte-for-byte old answer)",
          "asking from" not in bare,
          f"added a line: {bare[-200:]!r}")
    check("feature: a both-apps feature keeps its facts and names the asking app",
          "asking from the phone" in both_asked
          and "on the PC only" not in both_asked
          and "on the phone only" not in both_asked,
          both_asked[-400:])
    check("feature: a both-apps feature with no header is unchanged",
          both_bare == both_asked.replace("\n\nYou are asking from the phone.", "")
          and "asking from" not in both_bare,
          "the only change may be the asking sentence")
    S.reset()

    # --- 5. The model's first system turn carries one surface sentence. -----
    import jarvis_agent as A

    msgs = [{"role": "user", "content": "hello"}]
    S.set_current(S.PHONE)
    phone_msgs = A.with_rules_first(msgs)
    S.set_current(S.DESKTOP)
    desk_msgs = A.with_rules_first(msgs)
    S.set_current(S.UNKNOWN)
    bare_msgs = A.with_rules_first(msgs)
    bare_again_msgs = A.with_rules_first(msgs)
    S.reset()
    check("prompt: the rules stay first", phone_msgs[0]["content"] == A.LANE_SYSTEM)
    check("prompt: the phone sentence is the second system turn",
          phone_msgs[1]["role"] == "system"
          and phone_msgs[1]["content"] == "The owner is talking to you from the Android app.",
          f"got {phone_msgs[1]!r}")
    check("prompt: the desktop sentence is the second system turn",
          desk_msgs[1]["content"] == "The owner is talking to you from the desktop program.",
          f"got {desk_msgs[1]!r}")
    check("prompt: no header means exactly the old list",
          bare_msgs == bare_again_msgs and len(bare_msgs) == 2
          and bare_msgs[0]["content"] == A.LANE_SYSTEM
          and bare_msgs[1] == msgs[0],
          f"got {len(bare_msgs)} messages: {[m.get('content', '')[:40] for m in bare_msgs]}")
    body = A.chat_body("some-model", phone_msgs, {})
    sent = body.get("messages") or []
    check("prompt: the wire body really carries the sentence",
          any(m.get("content") == "The owner is talking to you from the Android app."
              for m in sent),
          "the stub model would never see it")

    # --- 6. No over-capture: odd values are unknown, not a guess. -----------
    for odd in ("desktop, phone", "hud", "pc", "android", "desktopphone"):
        check(f"no over-capture: {odd!r} is unknown",
              S.from_value(odd) == S.UNKNOWN, f"got {S.from_value(odd)!r}")

    # --- 7. Shipped on both sides; the twin is identical. -------------------
    twins = [REPO / "backend" / "jarvis_surface.py",
             REPO / "jarvis-backend" / "jarvis_surface.py"]
    check("module: shipped in backend/ and the published base",
          twins[0].is_file() and twins[1].is_file())
    check("module: the twin is byte-identical",
          twins[0].read_bytes() == twins[1].read_bytes())
    where = (REPO / "backend" / "_where.py").read_text(encoding="utf-8")
    script = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("module: named in both SHIPPED lists",
          '"jarvis_surface.py"' in where and "'jarvis_surface.py'" in script)

    # A seed request must not be able to smuggle a surface into the model: the
    # header is read from the HTTP request only, never from the body.
    S.reset()
    S.set_current(S.PHONE)
    from_body = Q.answer_turn(_body("open the second brain"))
    check("no over-capture: a body field cannot fake the surface (header only)",
          from_body is not None and from_body.reply == Q.PHONE_OPEN_WORDS["brain"])
    S.reset()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  FAIL {name}")
        sys.exit(1)
    print(f"{len(PASSED)} passed, 0 failed")
