"""test_approval_sign.py - a fingerprint-signed yes from the phone (backend half).

    python3 backend/test_approval_sign.py

Phase 2 of pairing (docs/PAIRING-DESIGN.md section 11, the owner's go-ahead
of 2026-09-29; docs/JARVIS-API.md section 91). Needs the `cryptography`
package (the checks generate a real P-256 key and sign with it); without it
the suite FAILS and says why - it never skips.

What is proved, with a temporary settings folder and stand-ins for the gate,
the clock and Windows Hello:

  * the design's two frozen test vectors for the words hash, and the message
    the phone signs;
  * register_approval_key: the public key is checked (EC P-256 only), one card
    is raised, the key is stored ONLY after it is approved; denied, timed out,
    withdrawn (replaced, or the device removed) store nothing; a shared or PC
    key cannot ask; no `cryptography` -> 503; the tier and the owner check
    must be in place; the list reads "waiting" / true / false;
  * the challenge: a nonce for one card and one device, 22 characters, single
    use, 120 seconds, a few per device; 404 for an unknown card; 403 for the
    shared key and for a device with no approval key;
  * POST /api/approve for a RISKY card from another device: a valid signature
    goes through and is stamped; none, a wrong card, a wrong action, a reused
    or expired nonce, a card changed after the challenge, another device's
    name, a removed device, a device with no approval key are all refused, and
    a used nonce is burnt even when the signature was bad; the old shared key
    from another device still works until it is retired; a card that is not
    risky, Deny, and an approval from this PC are unchanged;
  * end to end through the wrapped server handlers on a fake handler;
  * nothing secret (key, nonce, signature) in any audit line, event or print;
  * the tables that must know the new action, and the shared cases file.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_devices as T  # noqa: E402  (the fixtures: fake handler, gate, clock, pairing)

D, OC, check, fresh, pair = T.D, T.OC, T.check, T.fresh, T.pair
REPO = T.REPO

if D._crypto() is None:
    print("FAIL  test_approval_sign.py needs the `cryptography` package (pip install cryptography; "
          "it is in backend/requirements.txt and CI installs it)")
    sys.exit(1)

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, rsa  # noqa: E402

MESH, PC_MESH = T.MESH, T.PC_MESH
ARMED = lambda: True  # noqa: E731
ASK = lambda action: "ask"  # noqa: E731


# --------------------------------------------------------------- helpers --

def spki_of(priv) -> str:
    raw = priv.public_key().public_bytes(serialization.Encoding.DER,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)
    return D._b64u(raw)


def new_key():
    return ec.generate_private_key(ec.SECP256R1())


def risky_row(rid="r1", action="send_email", text="To: sam@example.com\n\nSee you at noon."):
    return {"id": rid, "action": action, "tier": "ask", "expires_in": 150, "raised": None,
            "notice": {"title": "Jarvis wants to send an email"},
            "detail": {"text": text},
            "risk": {"classified": True, "reach": "outbound", "reversible": "no", "why": "w"}}


def safe_row(rid="s1"):
    row = risky_row(rid, "append_obsidian_daily", "x")
    row["risk"] = {"classified": True, "reach": "local", "reversible": "yes", "why": "w"}
    return row


def phone(register=True):
    """A fresh settings folder, one paired phone, and (by default) its
    approval key registered through an approved card."""
    fresh()
    with T.Clock():
        dev, token, _ = pair()
    priv = new_key()
    if register:
        code, out = D.register_key({"public_key": spki_of(priv)}, you=dev, gate=T.Gate(T.APPROVE),
                                   tier_of=ASK, spawn=T.now_spawn, armed=ARMED)
        assert code == 202 and out == {"waiting": True}, (code, out)
        assert D.approval_key_of(dev) == spki_of(priv)
    return dev, token, priv


def challenge(dev, row, rows=None):
    code, out = D.challenge({"id": row["id"]}, you=dev, pending=lambda: rows if rows is not None else [row])
    assert code == 200, (code, out)
    return out


def sign(priv, row, nonce, *, action=None, words=None, card_id=None) -> str:
    msg = D.sign_message(str(row["id"]) if card_id is None else card_id,
                         row["action"] if action is None else action, nonce,
                         D.words_sha256(row) if words is None else words)
    return D._b64u(priv.sign(msg, ec.ECDSA(hashes.SHA256())))


def approve(dev, row, signature="--", *, rows=None, peer=MESH, local=PC_MESH, device="--"):
    """approve_check as the wrapped server calls it."""
    body = {"id": row["id"]}
    if signature != "--":
        body["signature"] = signature
    return OC.approve_check(body, peer=peer, local=local, own=[],
                            pending=lambda: rows if rows is not None else [row],
                            device=dev if device == "--" else device)


def signed(dev, priv, row, **kw):
    c = challenge(dev, row)
    return {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"], **kw)}


def why(res):
    return None if res is None else (res[0], res[1].get("owner_check"))


# ================================================================ vectors ==

def t_the_frozen_vectors_hold():
    a = {"id": "a1", "action": "send_email", "notice": {"title": "Jarvis wants to send an email"},
         "detail": {"text": "To: sam@example.com\nSubject: Lunch\n\nSee you at noon."}}
    b = {"id": "b2", "action": "lockdown_off",
         "notice": {"title": "Jarvis wants to turn Lockdown off"}}
    check("vector 1", D.words_sha256(a)
          == "9f37085786f66802d4749c0d8ee5d12416ef264ac438efb4c071c3b25a907145")
    check("vector 2 (no detail)", D.words_sha256(b)
          == "b6def5b9c7862ccb21bd2989ede743136284ef9147e1c14abbe21434e63e758c")
    check("a plain-text detail is the text itself",
          D.detail_text({"detail": "hello"}) == "hello")
    check("an object with no text, or a text that is not text, is empty",
          D.detail_text({"detail": {"to": "x"}}) == "" and D.detail_text({"detail": {"text": 5}}) == ""
          and D.detail_text({"detail": 5}) == "" and D.detail_text({}) == "")
    check("no notice: the title is the shared fallback",
          D.card_title({"action": "pair_device"}) == "Jarvis wants to connect a new device")
    msg = D.sign_message("a1", "send_email", "AAECAwQFBgcICQoLDA0ODw", "ab" * 32)
    check("the message is magic, id, action, nonce, hash split by 0x00",
          msg == b"jarvis-approve-v1\x00a1\x00send_email\x00AAECAwQFBgcICQoLDA0ODw\x00" + b"ab" * 32)
    row = risky_row()
    check("a numeric id hashes as its text",
          D.words_sha256(dict(row, id=12)) == D.words_sha256(dict(row, id="12")))


# ===================================================== the approval key ==

def t_a_good_key_is_stored_only_after_the_card_is_approved():
    fresh()
    with T.Clock():
        dev, _tok, _ = pair()
    priv = new_key()
    seen = {}

    def gate(action, detail, prompt):
        seen["card"] = (action, detail, prompt)
        seen["stored_while_waiting"] = D.approval_key_of(dev)
        seen["state_while_waiting"] = D.approval_key_state(dev)
        return T.APPROVE

    code, out = D.register_key({"public_key": spki_of(priv)}, you=dev, gate=gate, tier_of=ASK,
                               spawn=T.now_spawn, armed=ARMED)
    check("202 {waiting: true}", (code, out) == (202, {"waiting": True}), (code, out))
    action, detail, prompt = seen["card"]
    check("exactly the register_approval_key card, with the phone's name and no key",
          action == "register_approval_key" and "Pixel 9" in prompt
          and spki_of(priv) not in json.dumps(detail) + prompt and detail["leaves_this_pc"] is False)
    check("nothing is stored while the card waits, and the list says waiting",
          seen["stored_while_waiting"] is None and seen["state_while_waiting"] == "waiting")
    check("approved: the SPKI is in that device's row", D.approval_key_of(dev) == spki_of(priv))
    rows = {r["id"]: r for r in D.devices_view(you=dev, here=False)["devices"]}
    check("the list reads approval_key: true for it", rows[dev]["approval_key"] is True, rows)
    check("and the PC row has none", "approval_key" not in rows["pc"])
    check("the registry file keeps the key in that row",
          json.loads(D.registry_path().read_text())["devices"][0]["approval_key"] == spki_of(priv))
    check("audited by id and state, published as a devices event",
          ("devices.approval_key", {"id": dev, "state": "registered"}) in T.AUDIT
          and ("devices", {}) in T.EVENTS)


def t_denied_timed_out_or_refused_stores_nothing():
    for name, verdict in (("denied", T.DENY), ("timed out", T.TIMEOUT),
                          ("wrong tier", T.Verdict(True, "auto", "approved"))):
        dev, _t, _p = phone(register=False)
        code, _out = D.register_key({"public_key": spki_of(new_key())}, you=dev,
                                    gate=T.Gate(verdict), tier_of=ASK, spawn=T.now_spawn,
                                    armed=ARMED)
        check(f"{name}: 202 then nothing stored", code == 202 and D.approval_key_of(dev) is None)
        check(f"{name}: the list is back to false",
              D.approval_key_state(dev) is False, D.approval_key_state(dev))


def t_a_new_request_replaces_the_waiting_one():
    dev, _t, _p = phone(register=False)
    first, second = new_key(), new_key()

    def gate1(action, detail, prompt):
        # While the first card waits, the phone asks again (its own second card).
        code, _ = D.register_key({"public_key": spki_of(second)}, you=dev,
                                 gate=T.Gate(T.APPROVE), tier_of=ASK, spawn=T.now_spawn,
                                 armed=ARMED)
        assert code == 202
        return T.APPROVE          # the OLD card is approved afterwards

    D.register_key({"public_key": spki_of(first)}, you=dev, gate=gate1, tier_of=ASK,
                   spawn=T.now_spawn, armed=ARMED)
    check("only the newer request's key is stored; the withdrawn card stores nothing",
          D.approval_key_of(dev) == spki_of(second), D.approval_key_of(dev))
    check("a withdrawal is audited", any(e == "devices.approval_key" and d.get("state") == "withdrawn"
                                         for e, d in T.AUDIT))


def t_removing_the_device_withdraws_its_waiting_card_and_its_key():
    dev, _t, priv = phone()
    check("a key was registered", D.approval_key_of(dev) == spki_of(priv))
    D.remove({"id": dev}, you="pc")
    check("removing the device drops the key (the row keeps none)",
          json.loads(D.registry_path().read_text())["devices"][0]["approval_key"] is None)
    dev2, _t2, _p2 = phone(register=False)

    def gate(action, detail, prompt):
        D.remove({"id": dev2}, you="pc")      # removed while the card waits
        return T.APPROVE

    D.register_key({"public_key": spki_of(new_key())}, you=dev2, gate=gate, tier_of=ASK,
                   spawn=T.now_spawn, armed=ARMED)
    check("a card approved after the device was removed stores nothing",
          D.approval_key_of(dev2) is None)


def t_a_bad_public_key_is_refused_in_plain_words():
    dev, _t, _p = phone(register=False)
    p384 = ec.generate_private_key(ec.SECP384R1())
    rsa_key = rsa.generate_private_key(65537, 2048)
    other = lambda k: D._b64u(k.public_key().public_bytes(  # noqa: E731
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    good = spki_of(new_key())
    cases = {"not base64": "!!!", "empty": "", "garbage bytes": D._b64u(b"x" * 91),
             "a P-384 key": other(p384), "an RSA key": other(rsa_key),
             "way too long": "A" * 500, "a number": 5, "nothing": None,
             "padding characters": good + "=="}
    for name, value in cases.items():
        gate = T.Gate(T.APPROVE)
        code, out = D.register_key({"public_key": value}, you=dev, gate=gate, tier_of=ASK,
                                   spawn=T.now_spawn, armed=ARMED)
        check(f"{name}: 400 with the plain sentence, and no card",
              code == 400 and out["error"] in (D.SIGN_WORDS["bad_key"],)
              and not gate.cards, (code, out))
    for name, body in (("a stray field", {"public_key": good, "x": 1}), ("no field", {}),
                       ("not an object", [good])):
        code, out = D.register_key(body, you=dev, gate=T.Gate(), tier_of=ASK, spawn=T.now_spawn,
                                   armed=ARMED)
        check(f"{name}: 400 bad_request", code == 400 and out["reason"] == "bad_request", out)
    check("nothing was stored", D.approval_key_of(dev) is None)


def t_only_a_device_key_can_ask():
    dev, _t, _p = phone(register=False)
    for who in ("pc", "shared", "", None, "d00000000"):
        gate = T.Gate()
        code, out = D.register_key({"public_key": spki_of(new_key())}, you=who, gate=gate,
                                   tier_of=ASK, spawn=T.now_spawn, armed=ARMED)
        check(f"{who!r}: 403 and no card", code == 403 and not gate.cards, (code, out))
    check("a device id that is not paired (removed) cannot ask either",
          D.register_key({"public_key": spki_of(new_key())}, you="d00000000", gate=T.Gate(),
                         tier_of=ASK, spawn=T.now_spawn, armed=ARMED)[0] == 403)


def t_without_cryptography_it_says_so_and_fails_safe():
    dev, _t, priv = phone()
    keep = D._crypto
    D._crypto = lambda: None
    try:
        code, out = D.register_key({"public_key": spki_of(new_key())}, you=dev, gate=T.Gate(),
                                   tier_of=ASK, spawn=T.now_spawn, armed=ARMED)
        check("register: 503 with the package named",
              code == 503 and "cryptography" in out["error"], (code, out))
        row = risky_row()
        c = challenge(dev, row)
        sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"])}
        res = approve(dev, row, sig)
        check("a signature that cannot be checked is refused, never waved through",
              res is not None and res[0] == 503 and res[1]["owner_check"] == "cannot_check", res)
        OC.set_verifier(lambda m, t: OC.CONFIRMED)
        try:
            check("the PC's own approval is untouched (no signature is asked of this PC)",
                  approve(dev, row, peer="127.0.0.1", local="127.0.0.1", device="pc") is None)
        finally:
            OC.set_verifier(None)
    finally:
        D._crypto = keep


def t_the_tier_and_the_owner_check_must_be_in_place():
    dev, _t, _p = phone(register=False)
    code, out = D.register_key({"public_key": spki_of(new_key())}, you=dev, gate=T.Gate(),
                               tier_of=lambda a: "auto", spawn=T.now_spawn, armed=ARMED)
    check("tier not ask: 503", code == 503 and "ask" in out["error"], out)
    code, out = D.register_key({"public_key": spki_of(new_key())}, you=dev, gate=T.Gate(),
                               tier_of=ASK, spawn=T.now_spawn, armed=lambda: False)
    check("the PC not checking approvals itself: 503 with the sentence",
          code == 503 and out["error"] == D.DEVICES_WORDS["no_owner_check"], out)


def t_the_card_is_pc_only_and_in_every_table():
    check("register_approval_key is in PC_ONLY_ACTIONS", "register_approval_key" in OC.PC_ONLY_ACTIONS)
    row = risky_row("k1", "register_approval_key")
    res = OC.approve_check({"id": "k1"}, peer=MESH, local=PC_MESH, own=[], pending=lambda: [row],
                           device="dabcdef01")
    check("approved from another device: 403 pc_only, even with a device key",
          why(res) == (403, "pc_only"), res)
    import jarvis_asks_first as AF
    import jarvis_card_words as CW
    check("card words title", CW.title_for("register_approval_key").startswith("Jarvis wants to let a phone"))
    check("What asks first: a hard limit, must-ask, on the page",
          "register_approval_key" in AF.HARD_LIMITS and "register_approval_key" in AF.MUST_ASK
          and any("register_approval_key" in rows for _title, rows in AF.GROUPS))
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("framework toml: ask", 'register_approval_key     = "ask"' in toml)
    patch = (REPO / "backend" / "devices.patch").read_text(encoding="utf-8")
    check("devices.patch: the no-rule-from-denial set and the risk table both name it",
          patch.count('"register_approval_key"') == 2, patch.count('"register_approval_key"'))
    text, _log = __import__("_stack").stand_in("jarvis_gate.py")
    check("the stacked gate has it once in each",
          text is not None and text.count('"register_approval_key"') == 2)


# =========================================================== the challenge ==

def t_a_challenge_is_one_card_one_device_single_use():
    dev, _t, priv = phone()
    row = risky_row()
    c = challenge(dev, row)
    check("the answer's shape", set(c) == {"nonce", "words_sha256", "expires_in"}
          and len(c["nonce"]) == 22 and c["expires_in"] == 120
          and c["words_sha256"] == D.words_sha256(row), c)
    check("the nonce is 16 bytes, base64url", len(D._unb64u(c["nonce"])) == 16)
    check("two challenges never share a nonce", challenge(dev, row)["nonce"] != c["nonce"])
    code, out = D.challenge({"id": "nope"}, you=dev, pending=lambda: [row])
    check("404 for a card that is not waiting", code == 404 and out["reason"] == "no_such_card", out)
    for body in ({}, {"id": ""}, {"id": True}, {"id": "r1", "x": 1}, {"id": ["r1"]}, [], "r1"):
        code, out = D.challenge(body, you=dev, pending=lambda: [row])
        check(f"bad body {body!r}: 400", code == 400, (code, out))
    code, out = D.challenge({"id": 12}, you=dev, pending=lambda: [dict(row, id=12)])
    check("a numeric card id works", code == 200, out)
    code, out = D.challenge({"id": "r1"}, you=dev, pending=lambda: (_ for _ in ()).throw(OSError()))
    check("an unreadable queue is a 503", code == 503, out)


def t_a_challenge_needs_a_device_key_with_an_approval_key():
    dev, _t, _p = phone(register=False)
    row = risky_row()
    code, out = D.challenge({"id": "r1"}, you=dev, pending=lambda: [row])
    check("a device with no approval key: 403 no_approval_key, the frozen sentence",
          code == 403 and out["owner_check"] == "no_approval_key"
          and out["error"] == "Turn on signed approvals for this phone first.", out)
    for who in ("shared", "pc", None):
        code, out = D.challenge({"id": "r1"}, you=who, pending=lambda: [row])
        check(f"{who!r}: 403", code == 403, (code, out))


def t_nonces_expire_and_only_a_few_stay_outstanding():
    dev, _t, priv = phone()
    row = risky_row()
    with T.Clock() as clock:
        c = challenge(dev, row)
        clock.tick(119)
        sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"])}
        check("119 s later it still works", approve(dev, row, sig) is None)
        c = challenge(dev, row)
        clock.tick(121)
        sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"])}
        check("121 s later it is expired: bad_signature", why(approve(dev, row, sig)) == (403, "bad_signature"))
        first = challenge(dev, row)["nonce"]
        for _ in range(D.NONCES_PER_DEVICE):
            challenge(dev, row)
        sig = {"device": dev, "nonce": first, "sig": sign(priv, row, first)}
        check("more than the limit outstanding: the oldest is gone",
              why(approve(dev, row, sig)) == (403, "bad_signature"))
        check("at most the limit are kept in memory",
              sum(1 for v in D._NONCES.values() if v["device"] == dev) <= D.NONCES_PER_DEVICE)


# ======================================================== the check itself ==

def t_a_valid_signature_is_accepted_and_stamped():
    dev, _t, priv = phone()
    row = risky_row()
    OC._STAMPS.clear()
    res = approve(dev, row, signed(dev, priv, row))
    check("a valid signature: go ahead", res is None, res)
    check("the approval was stamped for the gate", OC.take_stamp("r1", "send_email"))


def t_nothing_or_junk_in_place_of_a_signature_is_refused():
    dev, _t, priv = phone()
    row = risky_row()
    check("no signature: 403 no_signature", why(approve(dev, row)) == (403, "no_signature"))
    res = approve(dev, row)
    check("with plain words", res[1]["error"] == D.SIGN_WORDS["no_signature"] and res[1]["ok"] is False)
    for junk in ("x", 5, [], {}, {"device": dev}, {"device": dev, "nonce": "n", "sig": 5}):
        got = why(approve(dev, row, junk))
        check(f"junk {junk!r}: refused", got in ((403, "no_signature"), (403, "bad_signature")), got)
    OC._STAMPS.clear()
    approve(dev, row)
    check("a refusal is never stamped", not OC.take_stamp("r1", "send_email"))


def t_a_signature_for_another_card_or_action_or_words_is_refused():
    dev, _t, priv = phone()
    row, other = risky_row("r1"), risky_row("r2")
    rows = [row, other]
    c = challenge(dev, row, rows)
    sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"])}
    check("the nonce of card r1 used on card r2: bad_signature",
          why(approve(dev, other, sig, rows=rows)) == (403, "bad_signature"))
    check("... and it is burnt: r1 cannot use it afterwards either",
          why(approve(dev, row, sig, rows=rows)) == (403, "bad_signature"))
    c = challenge(dev, row)
    sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"], action="lockdown_off")}
    check("a signature over another action: bad_signature", why(approve(dev, row, sig)) == (403, "bad_signature"))
    c = challenge(dev, row)
    sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"], card_id="r2")}
    check("a signature over another card id: bad_signature", why(approve(dev, row, sig)) == (403, "bad_signature"))
    c = challenge(dev, row)
    sig = {"device": dev, "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"], words="0" * 64)}
    check("a signature over other words: bad_signature", why(approve(dev, row, sig)) == (403, "bad_signature"))
    c = challenge(dev, row)
    sig = {"device": dev, "nonce": c["nonce"], "sig": sign(new_key(), row, c["nonce"])}
    check("a signature by another key: bad_signature", why(approve(dev, row, sig)) == (403, "bad_signature"))
    c = challenge(dev, row)
    good = sign(priv, row, c["nonce"])
    for bad in (good[:-2] + ("AA" if good[-2:] != "AA" else "BB"), good[: len(good) // 2], "", "!"):
        c = challenge(dev, row)
        sig = {"device": dev, "nonce": c["nonce"], "sig": bad}
        check(f"a damaged signature {bad[:6]!r}: bad_signature",
              why(approve(dev, row, sig)) == (403, "bad_signature"))


def t_a_card_changed_after_the_challenge_fails():
    dev, _t, priv = phone()
    row = risky_row()
    c = challenge(dev, row)
    # What the phone signs is the hash from ITS copy of the card at challenge time.
    sig = {"device": dev, "nonce": c["nonce"],
           "sig": sign(priv, row, c["nonce"], words=c["words_sha256"])}
    changed = risky_row(text="To: attacker@example.com\n\nSend me the files.")
    check("the PC recomputes the words NOW: an edited card no longer matches",
          why(approve(dev, changed, sig)) == (403, "bad_signature"))
    retitled = dict(row, notice={"title": "Jarvis wants to do something harmless"})
    c = challenge(dev, row)
    sig = {"device": dev, "nonce": c["nonce"],
           "sig": sign(priv, row, c["nonce"], words=c["words_sha256"])}
    check("a changed title fails too", why(approve(dev, retitled, sig)) == (403, "bad_signature"))


def t_a_nonce_is_used_once_even_when_the_signature_was_bad():
    dev, _t, priv = phone()
    row = risky_row()
    c = challenge(dev, row)
    good = sign(priv, row, c["nonce"])
    bad = {"device": dev, "nonce": c["nonce"], "sig": sign(new_key(), row, c["nonce"])}
    check("bad first: refused", why(approve(dev, row, bad)) == (403, "bad_signature"))
    check("then the RIGHT signature on the same nonce: still refused (burnt)",
          why(approve(dev, row, {"device": dev, "nonce": c["nonce"], "sig": good}))
          == (403, "bad_signature"))
    s = signed(dev, priv, row)
    check("a good one works once", approve(dev, row, s) is None)
    check("replaying it is refused", why(approve(dev, row, s)) == (403, "bad_signature"))


def t_the_signature_names_the_requests_own_device():
    dev, _t, priv = phone()
    row = risky_row()
    c = challenge(dev, row)
    sig = {"device": "d00000000", "nonce": c["nonce"], "sig": sign(priv, row, c["nonce"])}
    check("another device's name in the signature: bad_signature",
          why(approve(dev, row, sig)) == (403, "bad_signature"))
    # Another paired phone cannot use the first phone's nonce.
    with T.Clock():
        dev2, _tok2, _ = pair("Galaxy")
    priv2 = new_key()
    D.register_key({"public_key": spki_of(priv2)}, you=dev2, gate=T.Gate(T.APPROVE), tier_of=ASK,
                   spawn=T.now_spawn, armed=ARMED)
    c = challenge(dev, row)
    sig = {"device": dev2, "nonce": c["nonce"], "sig": sign(priv2, row, c["nonce"])}
    check("phone B cannot use phone A's nonce", why(approve(dev2, row, sig)) == (403, "bad_signature"))
    check("and phone A's signature does not pass as B",
          why(approve(dev2, row, {"device": dev2, "nonce": c["nonce"],
                                  "sig": sign(priv, row, c["nonce"])})) == (403, "bad_signature"))
    s = signed(dev2, priv2, row)
    check("B's own signature by B's own key works", approve(dev2, row, s) is None)


def t_a_removed_device_or_no_approval_key():
    dev, _t, priv = phone()
    row = risky_row()
    s = signed(dev, priv, row)
    D.remove({"id": dev}, you="pc")
    check("after Remove, its signed approval is refused (no approval key left)",
          why(approve(dev, row, s)) in ((403, "no_approval_key"), (403, "bad_signature")))
    dev2, _t2, _p2 = phone(register=False)
    res = approve(dev2, row, {"device": dev2, "nonce": "x" * 22, "sig": "AAAA"})
    check("a device with no approval key: 403 no_approval_key, the frozen sentence and shape",
          res == (403, {"ok": False, "owner_check": "no_approval_key",
                        "error": "Turn on signed approvals for this phone first."}), res)


def t_the_shared_key_is_allowed_until_it_is_retired():
    dev, _t, _p = phone(register=False)
    row = risky_row()
    check("the old shared key from another device: as today (allowed)",
          approve(None, row, device="shared") is None)
    orig = T.Original()
    ok = D.wrap_token_ok(orig)
    h = T.FakeHandler(token=T.SHARED, peer=MESH)
    check("before Retire the request is 'shared' and passes the key check",
          ok(h) is True and h._jarvis_device == "shared")
    check("... so approve_check leaves it alone", approve(None, row, device=h._jarvis_device) is None)
    D.shared({"retired": True}, you="pc", here=True)
    check("after Retire the shared key is refused from another device before any approval",
          ok(T.FakeHandler(token=T.SHARED, peer=MESH)) is False)
    h = T.FakeHandler(token=T.SHARED, peer="127.0.0.1")
    check("... and this PC's own shared key still works",
          ok(h) is True and h._jarvis_device == "pc")
    check("without the devices module (device None) nothing changes",
          approve(None, row, device=None) is None)


def t_cards_that_are_not_risky_deny_and_this_pc_are_unchanged():
    dev, _t, _p = phone()          # a key registered, but no signature offered below
    safe = safe_row()
    check("a card that is not risky needs no signature", approve(dev, safe) is None)
    OC.set_verifier(lambda m, t: OC.CONFIRMED)
    try:
        row = risky_row()
        res = approve(dev, row, peer="127.0.0.1", local="127.0.0.1")
        check("from this PC: Windows Hello, no signature asked", res is None, res)
        res = approve("pc", row, peer="127.0.0.1", local="127.0.0.1")
        check("the PC's own key: the same", res is None, res)
    finally:
        OC.set_verifier(None)
    OC.set_verifier(lambda m, t: OC.CANCELLED_)
    try:
        res = approve(dev, risky_row(), peer="127.0.0.1", local="127.0.0.1")
        check("this PC with Windows Hello cancelled: still refused, as before",
              why(res) == (403, "cancelled"), res)
    finally:
        OC.set_verifier(None)
    # Deny: the wrapper never touches it (below, end to end).


# ================================================= through the real wrappers ==

class _Body:
    def __init__(self, data: bytes):
        self._b = io.BytesIO(data)

    def read(self, n=-1):
        return self._b.read(n)


def t_end_to_end_through_the_wrapped_handlers():
    dev, token, priv = phone()
    row = risky_row()
    keep_pending, keep_devpend = OC._pending_rows, D._pending
    OC._pending_rows = lambda: [row]
    D._pending = lambda: [row]

    class H(T.FakeHandler):
        def __init__(self, path, body, tok=token, peer=MESH):
            super().__init__(path, token=tok, peer=peer, local=PC_MESH, body=body)
            self.rfile = _Body(self.body)

    class Handler(H):
        """The owner's handler: what runs when nothing above refused."""
        def do_POST(self):
            self.sent.append(("original POST", self.path))

        def do_GET(self):
            self.sent.append(("original GET", self.path))

    orig_token = T.Original()
    keep_armed = D._owner_check_armed
    D._owner_check_armed = ARMED
    OC._OWN_CACHE.update(at=OC.time.monotonic() + 1e9, set=frozenset())
    try:
        read = lambda h: h.body  # noqa: E731
        allow = lambda h: True  # noqa: E731
        D.install(Handler, origin_ok=allow, token_ok=orig_token, read_body=read)
        tok = D.wrap_token_ok(orig_token)
        OC.install(Handler, origin_ok=allow, token_ok=tok, read_body=read)

        def post(path, body, **kw):
            h = Handler(path, json.dumps(body).encode(), **kw)
            h.do_POST()
            return h.sent[-1]

        code, out = post("/api/approve/challenge", {"id": "r1"})
        check("challenge through the server: 200 and a nonce", code == 200 and len(out["nonce"]) == 22, out)
        nonce = out["nonce"]
        check("the shared key on the challenge route: 403",
              post("/api/approve/challenge", {"id": "r1"}, tok=T.SHARED)[0] == 403)
        sent = post("/api/approve", {"id": "r1"})
        check("approve without a signature: refused by the wrapper, never reaches the owner's handler",
              sent[0] == 403 and sent[1]["owner_check"] == "no_signature", sent)
        good = {"id": "r1", "signature": {"device": dev, "nonce": nonce,
                                           "sig": sign(priv, row, nonce)}}
        sent = post("/api/approve", good)
        check("approve with a valid signature: handed to the owner's handler",
              sent == ("original POST", "/api/approve"), sent)
        check("... and stamped", OC.take_stamp("r1", "send_email"))
        sent = post("/api/approve", good)
        check("the same request again: nonce burnt, refused",
              sent[0] == 403 and sent[1]["owner_check"] == "bad_signature", sent)
        sent = post("/api/deny", {"id": "r1"})
        check("Deny is never held up", sent == ("original POST", "/api/deny"), sent)
        sent = post("/api/approve", {"id": "r1"}, tok=T.SHARED)
        check("the old shared key from another device: handed on, as today",
              sent == ("original POST", "/api/approve"), sent)
        code, out = post("/api/devices/approval-key", {"public_key": spki_of(new_key())}, tok=T.SHARED)
        check("the register route with the shared key: 403", code == 403, out)
        h = Handler("/api/devices", b"{}")
        h.do_GET()
        me = [r for r in h.sent[-1][1]["devices"] if r.get("this_device")][0]
        check("GET /api/devices shows the caller's approval_key", me["approval_key"] is True, me)
    finally:
        OC._pending_rows, D._pending = keep_pending, keep_devpend
        D._owner_check_armed = keep_armed
        D._ARMED = False


# =========================================================== secrets, docs ==

def t_nothing_secret_is_logged_published_or_printed():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        dev, _t, priv = phone()
        row = risky_row()
        c = challenge(dev, row)
        sig = sign(priv, row, c["nonce"])
        approve(dev, row, {"device": dev, "nonce": c["nonce"], "sig": sig})
        approve(dev, row, {"device": dev, "nonce": c["nonce"], "sig": sig})
        _code, refused = D.register_key({"public_key": "junk"}, you=dev, gate=T.Gate(),
                                        tier_of=ASK, spawn=T.now_spawn, armed=ARMED)
    said = buf.getvalue() + json.dumps(T.AUDIT) + json.dumps(T.EVENTS) + json.dumps(refused)
    check("no key, nonce or signature in any audit line, event, error or printed line",
          all(x not in said for x in (spki_of(priv), c["nonce"], sig)), said[:200])


def t_the_cases_file_is_current_and_says_what_the_backend_says():
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_approval_sign_cases.py"), "--check"],
                       capture_output=True, text=True)
    check("approval-sign-cases.json (desktop and phone) equals a fresh run",
          r.returncode == 0, r.stdout + r.stderr)
    path = REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract" / "approval-sign-cases.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    first = doc["words_hash"][0]
    check("the file carries the frozen vectors",
          first["words_sha256"] == "9f37085786f66802d4749c0d8ee5d12416ef264ac438efb4c071c3b25a907145"
          and doc["words_hash"][1]["words_sha256"]
          == "b6def5b9c7862ccb21bd2989ede743136284ef9147e1c14abbe21434e63e758c")
    sig = doc["signature"]
    check("its fixed test signature verifies with the backend's own check, another message does not",
          D.signature_ok(sig["public_key"], bytes.fromhex(sig["message_hex"]), sig["sig"]) is True
          and D.signature_ok(sig["public_key"], bytes.fromhex(sig["other_message_hex"]), sig["sig"]) is False)
    for c in doc["words_hash"]:
        if D.words_sha256(c["row"]) != c["words_sha256"]:
            check(f"case {c['name']!r}", False)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                T.FAILED.append(name)
                traceback.print_exc()
    T.shutil.rmtree(T._TMP, ignore_errors=True)
    print(f"\n{len(T.PASSED)} passed, {len(T.FAILED)} failed")
    if T.FAILED:
        print("failed: " + ", ".join(T.FAILED))
    return 1 if T.FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
