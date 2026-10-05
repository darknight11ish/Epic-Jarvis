"""test_devices.py - pairing a phone by QR code, and a key per device.

    python3 backend/test_devices.py

docs/PAIRING-DESIGN.md section 10's backend list, row by row:
  * the key: its shape and length; only its hash is written (the registry
    file and every audit line are searched for the key's text);
  * wrap_token_ok: a device key works; a removed or unknown one is refused
    and never falls back to the old check; the shared key works before
    Retire, is refused from a mesh address after it and still works from
    loopback and from this PC's own address; an unreadable registry refuses
    device keys and treats the shared key as retired - except from this PC;
    the 401 gets its `key` reason; last_seen is written at most once a
    minute;
  * the shared key is a FIRST-PAIRING bootstrap (2026-10-05): accepted from
    another device only while no device holds a key of its own, refused
    afterwards with `key: shared_first_pair_only` and an audit line, and the
    window reopens when every device is removed; this PC and every device
    with its own key keep working either way, and Bring it back is refused
    with plain words instead of a card that could not work;
  * the stream guard: a write after Remove raises BrokenPipeError;
  * the hunk order on the stacked jarvis_hud.py;
  * pairing: start is PC only; the address rule; the QR text round-trips
    through the parser; the session view never holds the code or secret;
    claim from outside the mesh, and from this PC, is refused; 3 wrong
    proofs burn it and a 4th right one is refused; the 10 minutes are
    enforced with a fake clock; a good claim raises exactly one pair_device
    card with the name and words in its text; wrong tier -> refused;
    denied, timed out, cancelled while waiting -> no key; approved ->
    collect gives the key once, a second collect is 410; a new start
    withdraws the old card;
  * Remove, Retire (uses_it_yourself), Bring back (a card, PC only, 409
    under Lockdown - and 409 with plain words, no card, while a device holds
    a key of its own);
  * devices/registry.json is not in a backup (jarvis_backup's own code);
  * the tables that must know the new actions;
  * no key, secret or code in any audit line, event or printed line.

No pytest, no network, no model. A temporary settings folder; the gate,
tiers and clocks are stand-ins.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_devices.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-devices-"))
AUDIT: list = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None, *a, **k: AUDIT.append((event, detail))
fw.action_tier = lambda a: "ask"
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_devices as D  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402
import _stack  # noqa: E402

# This container's own addresses must not make a test peer "this PC".
OC._OWN_CACHE.update(at=time.monotonic() + 1e9, set=frozenset())

PASSED, FAILED = [], []
SKIPPED = []
EVENTS: list = []
D._publish = lambda kind, data: EVENTS.append((kind, dict(data)))

MESH = "100.101.2.3"
MESH6 = "fd7a:115c:a1e0::5"
HOME = "192.168.1.20"
PC_MESH = "100.64.9.9"          # this PC's own Tailscale address
SHARED = "S" * 43               # the old shared key in these tests


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Verdict:
    def __init__(self, allowed, tier="ask", outcome=None, reason=""):
        self.allowed, self.tier, self.outcome, self.reason = allowed, tier, outcome, reason


APPROVE = Verdict(True, "ask", "approved")
DENY = Verdict(False, "ask", "denied")
TIMEOUT = Verdict(False, "ask", "timed_out")


class Gate:
    """Records every card; answers with `verdict` (or calls it)."""

    def __init__(self, verdict=APPROVE):
        self.verdict, self.cards = verdict, []

    def __call__(self, action, detail, prompt):
        self.cards.append((action, detail, prompt))
        return self.verdict() if callable(self.verdict) else self.verdict


def now_spawn(fn):
    fn()


class Clock:
    def __init__(self):
        self.mono, self.wall = 1000.0, 1_790_000_000.0

    def __enter__(self):
        self._keep = (D._now, D._wall)
        D._now, D._wall = (lambda: self.mono), (lambda: self.wall)
        return self

    def __exit__(self, *exc):
        D._now, D._wall = self._keep

    def tick(self, s):
        self.mono += s
        self.wall += s


def fresh():
    """A new, empty settings folder and a clean module."""
    d = Path(tempfile.mkdtemp(prefix="cfg-", dir=_TMP))
    fw.CONFIG_DIR = d
    fw.action_tier = lambda a: "ask"
    D._reset_for_tests()
    AUDIT.clear()
    EVENTS.clear()
    return d


class FakeHandler:
    def __init__(self, path="/", token=None, peer="127.0.0.1", local="127.0.0.1", body=b"{}"):
        self.path = path
        self.headers = {"X-Jarvis-Token": token} if token is not None else {}
        self.client_address = (peer, 50000)
        self.connection = types.SimpleNamespace(getsockname=lambda: (local, 4719))
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.wfile = io.BytesIO()
        self.sent = []

    def do_GET(self):
        self.sent.append(("original GET", self.path))

    def do_POST(self):
        self.sent.append(("original POST", self.path))

    def _send(self, code, obj):
        self.sent.append((code, obj))
        return code


class Original:
    """The owner's _token_ok, as far as these tests need it: the shared key."""

    def __init__(self):
        self.calls = 0

    def __call__(self, handler):
        self.calls += 1
        return handler.headers.get("X-Jarvis-Token") == SHARED


def pair(name="Pixel 9", method="qr", gate=None, peer=MESH):
    """Run one whole pairing; returns (device_id, token, session answers)."""
    code, out = D.start({"address": "jarvis-pc.tail1234.ts.net", "port": 4719}, here=True,
                        armed=lambda: True)
    assert code == 200, out
    q = D.parse_qr(out["qr"])
    nonce = D._b64u(bytes(range(16)))
    k = q["secret"] if method == "qr" else D.code_key(D.normalise_code(out["code"]))
    ref = q["pair_id"] if method == "qr" else "-"
    t = D.transcript(method, ref, nonce, name)
    body = {"method": method, "phone_nonce": nonce, "name": name,
            "proof": D.claim_proof(k, t)}
    if method == "qr":
        body["pair_id"] = q["pair_id"]
    c, claimed = D.claim(body, peer=peer, gate=gate or Gate(), spawn=now_spawn)
    assert c == 202, (c, claimed)
    c, got = D.collect({"pair_id": claimed["pair_id"],
                        "proof": D.collect_proof(k, claimed["pair_id"], nonce)}, peer=peer)
    assert c == 200, (c, got)
    return got["device_id"], got["token"], (out, claimed, got)


# ==========================================================================
#   1. The key, and what is written
# ==========================================================================

def t_the_key_and_only_its_hash_is_written():
    fresh()
    with Clock():
        dev, token, (started, claimed, got) = pair()
    check("the key's shape is jdk1.<id>.<43 characters>",
          re.fullmatch(D.KEY_PATTERN, token) is not None and len(token) == 58, token[:9])
    check("the id is d + 8 lowercase hex and the key names it",
          re.fullmatch(r"d[0-9a-f]{8}", dev) is not None and token.split(".")[1] == dev)
    secret = token.split(".")[2]
    check("the secret part is 32 random bytes (43 base64url characters)",
          len(D._unb64u(secret)) == 32)
    text = D.registry_path().read_text(encoding="utf-8")
    check("the registry holds the key's SHA-256 ...",
          hashlib.sha256(token.encode()).hexdigest() in text)
    check("... and never the key or its secret part", token not in text and secret not in text)
    check("the registry lives in a devices/ subfolder of the settings folder",
          D.registry_path().parent.name == "devices"
          and D.registry_path().parent.parent == Path(fw.CONFIG_DIR))
    lines = json.dumps(AUDIT) + json.dumps(EVENTS)
    check("no audit line or event holds the key, the QR text, the secret or the code",
          all(x not in lines for x in (token, secret, started["qr"], started["code"],
                                        started["code"].replace("-", ""),
                                        started["qr"].split("/")[4])), lines[:300])
    check("the pairing was audited by id", ("devices.paired", {"id": dev}) in AUDIT)
    check("and a devices event, {} and nothing else, was sent", ("devices", {}) in EVENTS)
    row = json.loads(text)["devices"][0]
    check("the row has the design's fields",
          set(row) == {"id", "name", "kind", "token_sha256", "created", "last_seen",
                       "removed", "approval_key"} and row["approval_key"] is None
          and row["kind"] == "phone" and row["name"] == "Pixel 9", row)


def t_the_sums_match_the_design_vectors():
    k = bytes(range(16))
    nonce, pcn = D._b64u(bytes(range(16, 32))), D._b64u(bytes(range(32, 48)))
    t = D.transcript("qr", "00112233445566ff", nonce, "Pixel 9")
    check("qr proof", D.claim_proof(k, t) == "H0lGV2Jnwf0UFy1oAmBO4EZNtAWRnoyX8RjVNFIqq9c")
    check("qr pc_proof", D.pc_proof(k, t, pcn) == "HkPzmveXlM4XdYo_7TECbY7y3HF1Q4mIXmSxVXxDM80")
    check("qr word numbers", D.word_numbers(k, t, pcn) == [330, 679, 1036, 970])
    check("qr collect", D.collect_proof(k, "00112233445566ff", nonce)
          == "xqsJqE1r6hkgKSjlXeofy2K_C65PQiTjkZgEtpuTCEg")
    kc = D.code_key(D.normalise_code("K7QM-4TXD"))
    check("code K", kc.hex() == "e898e958c53b4f306488422d76cbdd30ba929057ac21bc70fb8ffbaeadff5c2e")
    t = D.transcript("code", "-", nonce, "Pixel 9")
    check("code proof", D.claim_proof(kc, t) == "5cbB9b5oknDpoMN3xu_fPdO5q_GvgR5BwN19a2eXxQ4")
    check("code pc_proof", D.pc_proof(kc, t, pcn) == "WM3nmfZziLG4yNxam4xdbLkbCmz34-67h9-Vig0ZdUo")
    check("code word numbers", D.word_numbers(kc, t, pcn) == [1164, 578, 141, 383])
    check("code collect", D.collect_proof(kc, "00112233445566ff", nonce)
          == "vGv4Z06RSHN36fZ3dWXisIq7S6ALIBm_EsRAgf7xeqE")
    check("the word list: 1,296 words, each first three letters unique",
          len(D.WORDS) == 1296 and len({w[:3] for w in D.WORDS}) == 1296)


# ==========================================================================
#   2. The check on every request
# ==========================================================================

def t_a_device_key_works_and_never_falls_back():
    fresh()
    with Clock():
        dev, token, _ = pair()
    orig = Original()
    ok = D.wrap_token_ok(orig)
    check("wrapping is idempotent", D.wrap_token_ok(ok) is ok)
    h = FakeHandler(token=token, peer=MESH)
    check("a device key works from the mesh", ok(h) is True and orig.calls == 0)
    check("the request knows its device", h._jarvis_device == dev)
    wrong = token[:-1] + ("A" if token[-1] != "A" else "B")
    h = FakeHandler(token=wrong, peer="127.0.0.1")
    check("a key with the right id but the wrong secret is refused, even from this PC",
          ok(h) is False and orig.calls == 0)
    h._send(401, {"error": "bad or missing X-Jarvis-Token"})
    check("... and its 401 says device_removed",
          h.sent[-1] == (401, {"error": "bad or missing X-Jarvis-Token", "key": "device_removed"}),
          h.sent)
    other = "jdk1.d00000000." + "x" * 43
    h = FakeHandler(token=other, peer=MESH)
    check("an unknown device is refused, never passed to the old check",
          ok(h) is False and orig.calls == 0)
    h = FakeHandler(token="jdk1.nonsense", peer=MESH)
    h._send(401, {"error": "x"})
    check("a malformed jdk1. key is refused, without claiming it was removed",
          ok(h) is False and orig.calls == 0)
    h = FakeHandler(token=token, peer=MESH)
    ok(h)
    D.remove({"id": dev}, you="pc")
    check("once removed, the same key is refused", ok(FakeHandler(token=token, peer=MESH)) is False)


def t_the_shared_key_and_retire():
    fresh()
    orig = Original()
    ok = D.wrap_token_ok(orig)
    check("the shared key works from the mesh before Retire",
          ok(FakeHandler(token=SHARED, peer=MESH)) is True)
    check("a wrong key is still the old check's no", ok(FakeHandler(token="nope", peer=MESH)) is False)
    h = FakeHandler(token=SHARED, peer=MESH)
    ok(h)
    check("... and that request is 'shared'", h._jarvis_device == "shared")
    code, out = D.shared({"retired": True}, you="pc", here=True)
    check("Retire from this PC: immediate", code == 200 and out["retired"] is True, out)
    check("... sends a devices event", ("devices", {}) in EVENTS)
    h = FakeHandler(token=SHARED, peer=MESH)
    check("after Retire the shared key is refused from the mesh", ok(h) is False)
    h._send(401, {"error": "bad or missing X-Jarvis-Token"})
    check("... with key: shared_retired", h.sent[-1][1].get("key") == "shared_retired", h.sent)
    check("... and from IPv6 Tailscale", ok(FakeHandler(token=SHARED, peer=MESH6)) is False)
    h = FakeHandler(token=SHARED, peer="127.0.0.1")
    check("... but still works from loopback", ok(h) is True and h._jarvis_device == "pc")
    check("... and from this PC's own mesh address",
          ok(FakeHandler(token=SHARED, peer=PC_MESH, local=PC_MESH)) is True)
    check("... and IPv6 loopback", ok(FakeHandler(token=SHARED, peer="::1", local="::1")) is True)
    h = FakeHandler(token="S" * 42, peer="127.0.0.1")
    check("a wrong key from this PC is still refused (the old check)", ok(h) is False)
    h._send(401, {"error": "x"})
    check("... with no key reason", "key" not in h.sent[-1][1])


def t_an_unreadable_registry_fails_closed_for_others_only():
    fresh()
    with Clock():
        dev, token, _ = pair()
    D.registry_path().write_text("{not json", encoding="utf-8")
    ok = D.wrap_token_ok(Original())
    check("a device key is refused", ok(FakeHandler(token=token, peer=MESH)) is False)
    check("the shared key is refused from another device",
          ok(FakeHandler(token=SHARED, peer=MESH)) is False)
    check("the shared key still works from this PC",
          ok(FakeHandler(token=SHARED, peer="127.0.0.1")) is True)
    v = D.devices_view(you="pc", here=True, armed=lambda: True)
    check("the device list says why pairing cannot work",
          v["pairing"]["available"] is False
          and v["pairing"]["why_not"] == D.DEVICES_WORDS["registry_unreadable"], v["pairing"])
    code, out = D.start({"address": "jarvis-pc.tail1234.ts.net"}, here=True, default_port=4719,
                        armed=lambda: True)
    check("start answers 503", code == 503, (code, out))
    check("Remove will not write over it", D.remove({"id": dev}, you="pc")[0] == 503)
    check("start fresh moves it aside and begins empty",
          "moved aside" in D.start_fresh() and D.load()[1] == ""
          and any(p.name.startswith("registry.json.broken-")
                  for p in D.registry_path().parent.iterdir()))
    check("afterwards the old device stays refused (every phone pairs again)",
          ok(FakeHandler(token=token, peer=MESH)) is False)


def t_last_seen_at_most_once_a_minute():
    fresh()
    with Clock() as c:
        dev, token, _ = pair()
        writes = []
        keep = D._write
        D._write = lambda doc: (writes.append(1), keep(doc))
        try:
            ok = D.wrap_token_ok(Original())
            for _ in range(5):
                ok(FakeHandler(token=token, peer=MESH))
                c.tick(5)
            check("five requests in 25 s write last_seen once", len(writes) == 1, writes)
            c.tick(60)
            ok(FakeHandler(token=token, peer=MESH))
            check("a minute later, once more", len(writes) == 2, writes)
            # 2026-10-05: a device holds a key of its own now, so the shared
            # key is no longer a way in from another device (the next test
            # covers that rule). Nothing is written for those requests, and
            # the shared key's own once-a-minute write is checked there.
            for _ in range(3):
                ok(FakeHandler(token=SHARED, peer=MESH))
            check("the shared key from another device: refused, and nothing written",
                  len(writes) == 2, writes)
        finally:
            D._write = keep
        doc = json.loads(D.registry_path().read_text(encoding="utf-8"))
        row = doc["devices"][0]
        check("last_seen is rounded to the minute", row["last_seen"] % 60 == 0, row)
        check("... and a refused shared key left the shared row alone",
              doc["shared"]["last_other_address"] is None
              and doc["shared"]["last_other_seen"] is None, doc["shared"])


def t_the_shared_key_is_a_first_pairing_only():
    """The old shared key brings the FIRST device in, and then stops.

    The owner decided per-device keys are the right shape ("more devices",
    docs/APPROVAL-GAP-DESIGN.md) and the QR pairing above gives every device
    one. What was left was the shared key, still accepted from any device on
    the mesh - so a device could still be brought in with a key that cannot be
    removed on its own. Since 2026-10-05 it is a bootstrap and nothing else:
    it works from another device only while NO device holds a key of its own.

    Removing the shared path outright was the other option and was NOT taken:
    what the owner has today is a PC with no device key at all (no
    devices/registry.json on it), so the shared key is the only way in that has
    ever worked there, and the QR path needs Windows Hello set up before its
    card can be approved at all ("no lock, no risky approval"). Narrowing it to
    the first pairing keeps today's behaviour for him, and the refusal only
    ever starts once a device key exists - which is itself the proof that the
    QR way works on that PC.
    """
    # 1. No device yet: the shared key still brings the first device in.
    fresh()
    with Clock():
        h = FakeHandler(token=SHARED, peer=MESH)
        check("with no device paired, the shared key works from the mesh",
              D.wrap_token_ok(Original())(h) is True)
        check("... and that request is 'shared'", h._jarvis_device == "shared")
        check("... and it is written down as the first pairing",
              ("devices.shared", {"state": "first-pairing"}) in AUDIT, AUDIT)

    # 2. A device of its own: the shared key stops, in its own words.
    with Clock():
        dev, token, _ = pair()
    AUDIT.clear()
    with Clock():
        h = FakeHandler(token=SHARED, peer=MESH)
        check("once a device has its own key, the shared key is refused from the mesh",
              D.wrap_token_ok(Original())(h) is False)
        h._send(401, {"error": "bad or missing X-Jarvis-Token"})
        check("... with key: shared_first_pair_only",
              h.sent[-1][1].get("key") == "shared_first_pair_only", h.sent)
        check("... and that is written down too",
              ("devices.shared", {"state": "refused-first-pairing-done"}) in AUDIT, AUDIT)
        check("... this PC itself is never cut off",
              D.wrap_token_ok(Original())(FakeHandler(token=SHARED, peer="127.0.0.1")) is True)
        check("... nor is the device that has its own key",
              D.wrap_token_ok(Original())(FakeHandler(token=token, peer=MESH)) is True)
        check("... and the sentence says what to do instead",
              "QR code" in D.KEY_WORDS["shared_first_pair_only"]
              and "Settings, Devices" in D.KEY_WORDS["shared_first_pair_only"],
              D.KEY_WORDS["shared_first_pair_only"])

    # 3. The Devices page says it, in its own words, and does not offer a
    #    button that could not work.
    v = D.devices_view(you="pc", here=True)
    check("the shared row reports first_pair_only",
          v["shared"]["first_pair_only"] is True and v["shared"]["retired"] is False, v["shared"])
    check("... and Bring it back is not offered", v["shared"]["can_bring_back_here"] is False)
    code, out = D.shared({"retired": False}, you="pc", here=True)
    check("Bring it back while a device has its own key: refused, no card raised",
          code == 409 and out.get("first_pair_only") is True
          and out.get("error") == D.DEVICES_WORDS["unretire_first_pair"], out)

    # 4. The window opens again only when the PC has no device of its own -
    #    which is also what keeps the rule from ever locking anyone out.
    D.remove({"id": dev}, you="pc")
    with Clock():
        check("with every device removed, the first-pairing window is back",
              D.wrap_token_ok(Original())(FakeHandler(token=SHARED, peer=MESH)) is True)
        check("... and the row stops saying first_pair_only",
              D.devices_view(you="pc", here=True)["shared"]["first_pair_only"] is False)


def t_the_stream_guard():
    fresh()
    with Clock():
        dev, token, _ = pair()
    ok = D.wrap_token_ok(Original())
    h = FakeHandler(token=token, peer=MESH)
    raw = h.wfile
    ok(h)
    h.wfile.write(b"data: one\n\n")
    check("a write while paired goes through", raw.getvalue() == b"data: one\n\n")
    ok(h)
    check("the guard is not stacked twice on one handler", h.wfile._raw is raw)
    D.remove({"id": dev}, you="pc")
    try:
        h.wfile.write(b": keepalive\n\n")
        broke = False
    except BrokenPipeError:
        broke = True
    check("a write after Remove raises BrokenPipeError", broke)
    check("nothing more reached the stream", raw.getvalue() == b"data: one\n\n")
    check("flush and closed still pass through", h.wfile.closed is False and h.wfile.flush() is None)
    s = FakeHandler(token=SHARED, peer="127.0.0.1")
    ok(s)
    check("a shared-key request gets no guard", isinstance(s.wfile, io.BytesIO))


# ==========================================================================
#   3. The patch, on the stacked files
# ==========================================================================

def t_the_hunk_comes_before_every_token_ok():
    order = _stack.order()
    # Last but for patches whose context is ITS lines (apps-in-projects.patch
    # anchors on register_approval_key's risk line, 2026-09-29).
    after_it = order[order.index("devices.patch") + 1:] if "devices.patch" in order else None
    # inbox-tidy.patch goes last (2026-09-29): it leaves devices.patch's lines
    # alone (checked by the second condition), and apps-in-projects.patch's
    # hunks need the gate lists as they stand before it adds its own.
    # screen.patch goes after those two (2026-09-29): its startup block is
    # anchored on inbox-tidy.patch's own lines and it touches no gate list.
    # screen-picture.patch goes last of all (2026-09-29): its two gate hunks sit
    # on inbox-tidy.patch's own last lines and leave devices.patch's alone.
    # browser-engine.patch goes after those (2026-09-29): its gate hunks sit on
    # screen-picture.patch's own last lines and leave devices.patch's alone; its
    # startup block is anchored on screen.patch's own.
    check("devices.patch is in apply-patches.ps1's list, and only "
          "patches that leave its lines alone come after it",
          after_it is not None
          and set(after_it) <= {"apps-in-projects.patch", "inbox-tidy.patch", "screen.patch",
                                "screen-picture.patch", "browser-engine.patch",
                                "form-review.patch", "web-search-switch.patch", "quiz.patch",
                                "decks.patch", "spending.patch", "retirement.patch",
                                "progress.patch", "topics.patch", "referee.patch",
                                "tag-suggest.patch", "youtube.patch", "quiz-cloud.patch"}
          and not _stack.later_rewriting("devices.patch", "register_approval_key"), order[-3:])
    text, log = _stack.stand_in("jarvis_hud.py")
    check("the stacked jarvis_hud.py builds", text is not None, "\n".join(log[-3:]))
    if text is None:
        return
    check("devices.patch's hunk applied to real context (nothing materialised)",
          not any(l.startswith("devices.patch") for l in log), log)
    lines = text.splitlines()
    swap = [i for i, l in enumerate(lines) if "jarvis_devices.wrap_token_ok(_token_ok)" in l]
    handed = [i for i, l in enumerate(lines) if "token_ok=_token_ok" in l]
    check("exactly one place replaces _token_ok", len(swap) == 1, swap)
    check("... and it comes before every token_ok=_token_ok in the file",
          swap and handed and swap[0] < min(handed), (swap, handed[:3]))
    owner = [i for i, l in enumerate(lines) if "import jarvis_owner_check" in l]
    refuse = [i for i, l in enumerate(lines) if l.strip() == "_refuse_every_interface(bind)"]
    check("... after _refuse_every_interface(bind) and before owner-check's block",
          refuse and owner and refuse[-1] < swap[0] < owner[0], (refuse, swap, owner))
    check("it writes the module global, so the route code's own _token_ok(self) sees it",
          'globals()["_token_ok"] = jarvis_devices.wrap_token_ok(_token_ok)' in text)
    block = "\n".join(lines[swap[0] - 2:swap[0] + 6])
    check("a failure there leaves the old check in place and says so",
          "except Exception as exc:" in block and "only the shared key works" in block, block)


def t_the_patch_applies_and_reverses():
    git = shutil.which("git")
    if not git:
        return skip("git is not installed")
    order = _stack.order()
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        at = order.index("devices.patch")
        before, log = _stack.stand_in(target, order[:at])
        after, log2 = _stack.stand_in(target, order[:at + 1])
        check(f"{target}: the stack builds with and without it",
              before is not None and after is not None)
        if before is None or after is None:
            continue
        d = Path(tempfile.mkdtemp(prefix="jarvis-devices-patch-", dir=_TMP))
        (d / target).write_text(before, encoding="utf-8", newline="\n")
        hunks = "".join(h for h, _ in _stack.hunks(
            (HERE / "devices.patch").read_text(encoding="utf-8"), target))
        (d / "p.patch").write_text(f"--- a/{target}\n+++ b/{target}\n{hunks}",
                                   encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        check(f"{target}: devices.patch applies to the stack before it", r.returncode == 0,
              r.stderr)
        r = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                           text=True)
        check(f"{target}: ... and reverses cleanly",
              r.returncode == 0 and (d / target).read_text(encoding="utf-8") == before,
              r.stderr)


def t_the_gate_tables():
    text, log = _stack.stand_in("jarvis_gate.py")
    lines = text.splitlines()
    a = next(i for i, l in enumerate(lines) if l.startswith("_NO_RULE_FROM_DENIAL = frozenset("))
    b = next(i for i in range(a, len(lines)) if lines[i] == "})")
    listed = "\n".join(lines[a:b])
    for action in (D.ACTION, D.UNRETIRE_ACTION):
        check(f"{action}: a no is not a standing rule (_NO_RULE_FROM_DENIAL)",
              f'"{action}",' in listed)
        m = re.search(rf'^    "{action}":\s*(\(.*\)),\s*$', text, re.M)
        check(f"{action}: a _RISK line, local and reversible",
              m is not None and eval(m.group(1))[:2] == ("yes", "local"), m and m.group(1))
        check(f"{action}: approved on this PC only, always with Windows Hello",
              action in OC.PC_ONLY_ACTIONS)
    import jarvis_card_words as W
    check("the card title is the design's", W.title_for(D.ACTION) == D.CARD_TITLE,
          W.title_for(D.ACTION))
    check("the Bring back card has plain words", "old shared key" in W.title_for(D.UNRETIRE_ACTION))
    import jarvis_asks_first as AF
    ids = [x for _, rows in AF.GROUPS for x in rows]
    for action in (D.ACTION, D.UNRETIRE_ACTION):
        check(f"{action} is on the What asks first page, never loosened, must ask",
              action in ids and action in AF.HARD_LIMITS and action in AF.MUST_ASK
              and action not in AF.SWITCHABLE)
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("both ship as \"ask\" in jarvis-framework.toml",
          re.search(r'^pair_device\s*=\s*"ask"', toml, re.M) is not None
          and re.search(r'^unretire_shared_key\s*=\s*"ask"', toml, re.M) is not None)


def t_a_pairing_card_is_approved_on_the_pc_only_with_windows_hello():
    row = {"id": "r1", "action": D.ACTION, "risk": {"classified": True, "reach": "local",
                                                   "reversible": "yes"}, "raised": None}
    said = []
    OC.set_verifier(lambda m, t: (said.append(m), OC.CONFIRMED)[1])
    try:
        out = OC.approve_check({"id": "r1"}, peer=MESH, local="100.64.1.1",
                               pending=lambda: [row], own=())
        check("from the phone: refused (pc_only)", out and out[0] == 403
              and out[1]["owner_check"] == "pc_only", out)
        out = OC.approve_check({"id": "r1"}, peer="127.0.0.1", pending=lambda: [row], own=())
        check("from this PC: Windows Hello asked, although the card is not 'risky'",
              out is None and len(said) == 1, (out, said))
        OC.set_verifier(lambda m, t: OC.UNAVAILABLE)
        out = OC.approve_check({"id": "r1"}, peer="127.0.0.1", pending=lambda: [row], own=())
        check("no Windows Hello: refused with the owner's words", out and out[0] == 403
              and out[1]["error"] == OC.NOT_SET_UP, out)
    finally:
        OC.set_verifier(None)
        OC.take_stamp("r1", D.ACTION)


# ==========================================================================
#   4. Pairing
# ==========================================================================

def _start(**kw):
    return D.start({"address": "jarvis-pc.tail1234.ts.net", "port": 4719}, here=True,
                   armed=lambda: True, **kw)


def _claim_body(out, name="Pixel 9", method="qr", nonce=None, good=True):
    q = D.parse_qr(out["qr"])
    nonce = nonce or D._b64u(bytes(range(16)))
    k = q["secret"] if method == "qr" else D.code_key(D.normalise_code(out["code"]))
    t = D.transcript(method, q["pair_id"] if method == "qr" else "-", nonce, name)
    proof = D.claim_proof(k, t) if good else D.claim_proof(b"wrong" * 4, t)
    body = {"method": method, "phone_nonce": nonce, "name": name, "proof": proof}
    if method == "qr":
        body["pair_id"] = q["pair_id"]
    return body, k, nonce


def t_start_is_pc_only_and_checks_the_address():
    fresh()
    code, out = D.start({"address": "jarvis-pc.tail1234.ts.net"}, here=False, armed=lambda: True)
    check("start from another device: 403 pc_only",
          code == 403 and out == {"ok": False, "pc_only": True, "error": D.PC_ONLY}, out)
    sys.path.insert(0, str(REPO / "tools"))
    import gen_own_network_cases as ON
    check("the off-network sentence is the phone's own (gen_own_network_cases.PHONE_MESSAGE)",
          D.ADDRESS_OFF_NETWORK == ON.PHONE_MESSAGE)
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "data" / "PhoneAddress.kt").read_text(encoding="utf-8")
    joined = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', kt[kt.index("const val MESSAGE"):
                                                          kt.index("fun problem")]))
    check("the on-network sentence is PhoneAddress.MESSAGE, word for word",
          joined.replace("\\'", "'") == D.ADDRESS_NOT_A_NAME, joined)
    for address, want in (("jarvis-pc.tail1234.ts.net", "jarvis-pc.tail1234.ts.net"),
                          ("JARVIS-PC.tail1234.TS.NET.", "jarvis-pc.tail1234.ts.net"),
                          ("my-pc.nord", "my-pc.nord"),
                          ("192.168.1.20", None), ("100.101.2.3", None),
                          ("jarvis-pc.local", None), ("abc.ngrok-free.app", None),
                          ("ts.net", None), ("desktop.ts.net.evil.com", None),
                          ("me@x.ts.net", None), ("http://x.ts.net", None), ("", None)):
        check(f"address {address!r} -> {want!r}", D.phone_host(address) == want)
    code, out = D.start({"address": "192.168.1.20"}, here=True, armed=lambda: True)
    check("a home address: 400 address, the phone's own sentence",
          code == 400 and out["reason"] == "address"
          and out["error"] == D.ADDRESS_NOT_A_NAME.replace("{address}", "192.168.1.20"), out)
    code, out = D.start({"address": "evil.com"}, here=True, armed=lambda: True)
    check("an internet name: the off-network sentence",
          out["error"] == D.ADDRESS_OFF_NETWORK.replace("{address}", "evil.com"), out)
    code, out = D.start({"address": "x.ts.net", "port": 0}, here=True, armed=lambda: True)
    check("a bad port: 400", code == 400, out)
    code, out = D.start({"address": "x.ts.net", "port": True}, here=True, armed=lambda: True)
    check("a port that is true, not a number: 400", code == 400, out)
    code, out = D.start({"address": "x.ts.net", "port": 4719}, here=True, armed=lambda: False)
    check("no approval check on this PC: 503 with the sentence",
          code == 503 and out["error"] == D.DEVICES_WORDS["no_owner_check"], out)
    fw.action_tier = lambda a: "auto"
    code, out = D.start({"address": "x.ts.net", "port": 4719}, here=True, armed=lambda: True)
    check("pair_device not 'ask': 503", code == 503 and "ask" in out["error"], out)


def t_the_start_answer_and_the_session_view():
    fresh()
    with Clock():
        code, out = _start()
        check("200 with the design's fields",
              code == 200 and set(out) == {"ok", "pair_id", "qr", "code", "expires_in",
                                           "tries_left"}
              and out["expires_in"] == 600 and out["tries_left"] == 3, out)
        q = D.parse_qr(out["qr"])
        check("the QR text round-trips through the strict parser",
              q["host"] == "jarvis-pc.tail1234.ts.net" and q["port"] == 4719
              and q["pair_id"] == out["pair_id"] and len(q["secret"]) == 16
              and q["expires"] == 1_790_000_600, q)
        check("the code is shown XXXX-XXXX in Crockford's alphabet",
              re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}", out["code"]),
              out["code"])
        code, view = D.session_view(here=True)
        text = json.dumps(view)
        check("the session view: waiting_for_phone, 10 minutes, 3 tries",
              view["state"] == "waiting_for_phone" and view["expires_in"] == 600
              and view["tries_left"] == 3 and view["words"] is None
              and view["message"] == D.SESSION_WORDS["waiting_for_phone"], view)
        check("... and never the QR text, the secret or the code",
              out["qr"] not in text and out["qr"].split("/")[4] not in text
              and out["code"] not in text and out["code"].replace("-", "") not in text)
        check("the session view is PC only", D.session_view(here=False)[0] == 403)
        check("cancel is PC only", D.cancel(here=False)[0] == 403)


def t_claim_is_mesh_only():
    fresh()
    _code, out = _start()
    body, _k, _n = _claim_body(out)
    for peer, where in ((HOME, "not_mesh"), ("8.8.8.8", "not_mesh"), ("127.0.0.1", "this_pc"),
                        ("::1", "this_pc")):
        code, ans = D.claim(body, peer=peer, gate=Gate(), spawn=now_spawn)
        check(f"claim from {peer}: 403 not_mesh",
              code == 403 and ans["reason"] == "not_mesh"
              and ans["error"] == D.PHONE_WORDS[where], ans)
    code, ans = D.claim(body, peer=PC_MESH, local=PC_MESH, gate=Gate(), spawn=now_spawn)
    check("claim from this PC's own Tailscale address: refused as this PC",
          code == 403 and ans["error"] == D.PHONE_WORDS["this_pc"], ans)
    code, ans = D.collect({"pair_id": out["pair_id"], "proof": "x"}, peer=HOME)
    check("collect from the home network: 403 not_mesh", code == 403
          and ans["reason"] == "not_mesh", ans)
    check("none of those counted as a try", D.session_view(here=True)[1]["tries_left"] == 3)
    code, ans = D.claim(body, peer=MESH6, gate=Gate(), spawn=now_spawn)
    check("claim from Tailscale IPv6 is let in", code == 202, ans)


def t_three_wrong_tries_burn_it():
    fresh()
    _code, out = _start()
    gate = Gate()
    bad, _k, _n = _claim_body(out, good=False)
    code, ans = D.claim(bad, peer=MESH, gate=gate, spawn=now_spawn)
    check("a wrong proof: 403 wrong_proof, 2 tries left",
          code == 403 and ans["reason"] == "wrong_proof" and ans["tries_left"] == 2
          and ans["error"] == "That code is not right. 2 tries left.", ans)
    code, ans = D.collect({"pair_id": out["pair_id"], "proof": "nope"}, peer="100.100.1.1")
    check("a collect before any claim counts too", code == 403 and ans["tries_left"] == 1, ans)
    code, ans = D.claim(dict(bad, method="code", pair_id=None), peer=MESH, gate=gate,
                        spawn=now_spawn)
    check("a wrong typed code counts too, and the third burns it",
          code == 403 and ans["tries_left"] == 0, ans)
    good, _k, _n = _claim_body(out)
    code, ans = D.claim(good, peer=MESH, gate=gate, spawn=now_spawn)
    check("a 4th, RIGHT claim is refused: 410 gone, burnt",
          code == 410 and ans["reason"] == "gone" and ans["state"] == "burnt", ans)
    check("no card was ever raised", gate.cards == [])
    _c, view = D.session_view(here=True)
    check("the PC sees where the wrong tries came from",
          view["state"] == "burnt" and view["wrong_tries_from"] == [MESH, "100.100.1.1"]
          and view["message"] == D.SESSION_WORDS["burnt"], view)


def t_a_second_claim_counts_and_can_withdraw_the_card():
    fresh()
    _code, out = _start()
    good, _k, _n = _claim_body(out)
    held = []
    code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=held.append)
    check("the first good claim: 202", code == 202, ans)
    code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=now_spawn)
    check("a second claim says another device used the code",
          code == 403 and ans.get("claimed") is True and ans["tries_left"] == 2
          and ans["error"] == D.PHONE_WORDS["claimed"], ans)
    for i in range(2):
        code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=now_spawn)
    check("claiming again counts as wrong, and three burn it",
          code == 403 and ans["tries_left"] == 0, ans)
    held[0]()      # the card is approved only now
    check("the waiting card, approved late, made no key",
          D.session_view(here=True)[1]["state"] == "burnt" and not D.registry_path().exists())


def t_the_ten_minutes():
    fresh()
    with Clock() as c:
        _code, out = _start()
        c.tick(599)
        check("at 9:59 it is still waiting", D.session_view(here=True)[1]["state"]
              == "waiting_for_phone")
        c.tick(1)
        good, _k, _n = _claim_body(out)
        code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=now_spawn)
        check("at 10:00 a right claim is 410, expired",
              code == 410 and ans["state"] == "expired", ans)
        # approved but never collected
        _code, out = _start()
        good, k, nonce = _claim_body(out)
        D.claim(good, peer=MESH, gate=Gate(), spawn=now_spawn)
        check("approved", D.session_view(here=True)[1]["state"] == "approved")
        c.tick(601)
        code, ans = D.collect({"pair_id": out["pair_id"],
                               "proof": D.collect_proof(k, out["pair_id"], nonce)}, peer=MESH)
        check("collected after the 10 minutes: 410 expired, no key",
              code == 410 and ans["state"] == "expired" and not D.registry_path().exists(), ans)


def t_a_good_claim_raises_one_card():
    fresh()
    _code, out = _start()
    good, k, nonce = _claim_body(out, name="Émilie's phone")
    gate = Gate(verdict=TIMEOUT)
    held = []
    code, ans = D.claim(good, peer=MESH, gate=gate, spawn=held.append)
    check("202 with the design's fields",
          code == 202 and set(ans) == {"state", "pair_id", "pc_nonce", "pc_proof", "words",
                                       "expires_in"}, ans)
    t = D.transcript("qr", out["pair_id"], nonce, "Émilie's phone")
    check("pc_proof is the PC's proof over the same transcript",
          ans["pc_proof"] == D.pc_proof(k, t, ans["pc_nonce"]))
    check("the words are the four the phone works out itself",
          ans["words"] == D.words_for(D.word_numbers(k, t, ans["pc_nonce"])))
    held[0]()
    check("exactly one card, pair_device", [c[0] for c in gate.cards] == [D.ACTION], gate.cards)
    action, detail, prompt = gate.cards[0]
    check("its text names the phone and shows the four words",
          "\"Émilie's phone\" is asking for its own key" in detail["text"]
          and " · ".join(ans["words"]) in detail["text"] and prompt == detail["text"],
          detail["text"])
    check("and says to deny it if nobody pressed Pair a phone",
          "deny this" in detail["text"] and detail["leaves_this_pc"] is False)
    check("timed out: no key, the state says so",
          D.session_view(here=True)[1]["state"] == "timed_out" and not D.registry_path().exists())
    code, ans = D.collect({"pair_id": out["pair_id"],
                           "proof": D.collect_proof(k, out["pair_id"], nonce)}, peer=MESH)
    check("collect: 410 timed_out", code == 410 and ans["state"] == "timed_out", ans)


def t_denied_refused_cancelled_make_no_key():
    for verdict, state in ((DENY, "denied"), (Verdict(True, "auto", "approved"), "refused"),
                           (Verdict(False, "ask", "refused", "no queue"), "refused")):
        fresh()
        _code, out = _start()
        good, k, nonce = _claim_body(out)
        D.claim(good, peer=MESH, gate=Gate(verdict), spawn=now_spawn)
        code, ans = D.collect({"pair_id": out["pair_id"],
                               "proof": D.collect_proof(k, out["pair_id"], nonce)}, peer=MESH)
        view = D.session_view(here=True)[1]
        check(f"gate says {verdict.outcome!r} at tier {verdict.tier!r}: {state}, no key",
              view["state"] == state and not D.registry_path().exists(), view)
        if state == "denied":
            check("collect after a no: 403 denied",
                  code == 403 and ans["state"] == "denied"
                  and ans["error"] == D.PHONE_WORDS["denied"], ans)
        else:
            check("collect after a refusal: 410 refused", code == 410
                  and ans["state"] == "refused", ans)
    fresh()
    fw.action_tier = lambda a: "auto"
    _code, out = D.start({"address": "x.ts.net", "port": 1}, here=True, armed=lambda: True)
    check("with the tier set looser, pairing cannot even start", _code == 503)
    # tier changed after start: the card is refused before it is raised
    fresh()
    _code, out = _start()
    good, _k, _n = _claim_body(out)
    gate = Gate()
    fw.action_tier = lambda a: "notify"
    D.claim(good, peer=MESH, gate=gate, spawn=now_spawn)
    check("tier changed to notify meanwhile: refused, no card raised",
          gate.cards == [] and D.session_view(here=True)[1]["state"] == "refused")
    # cancelled while the card waits
    fresh()
    _code, out = _start()
    good, k, nonce = _claim_body(out)
    gate = Gate(verdict=lambda: (D.cancel(here=True), APPROVE)[1])
    D.claim(good, peer=MESH, gate=gate, spawn=now_spawn)
    view = D.session_view(here=True)[1]
    check("cancelled while the card waited: approving it made no key",
          view["state"] == "cancelled" and not D.registry_path().exists(), view)
    code, ans = D.collect({"pair_id": out["pair_id"],
                           "proof": D.collect_proof(k, out["pair_id"], nonce)}, peer=MESH)
    check("collect: 410 cancelled", code == 410 and ans["state"] == "cancelled", ans)
    # a gate that fails
    fresh()
    _code, out = _start()
    good, _k, _n = _claim_body(out)

    def broken(*a):
        raise RuntimeError("queue")
    D.claim(good, peer=MESH, gate=broken, spawn=now_spawn)
    check("a gate that fails: refused, no key",
          D.session_view(here=True)[1]["state"] == "refused" and not D.registry_path().exists())
    # the card thread cannot start
    fresh()
    _code, out = _start()
    good, _k, _n = _claim_body(out)

    def no_thread(fn):
        raise RuntimeError("no threads")
    code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=no_thread)
    check("no card could be raised: 503 card, and the code still works",
          code == 503 and ans["reason"] == "card"
          and D.session_view(here=True)[1]["state"] == "waiting_for_phone", ans)
    code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=now_spawn)
    check("... tried again: 202", code == 202, ans)


def t_approved_collect_gives_the_key_once():
    fresh()
    with Clock():
        _code, out = _start()
        good, k, nonce = _claim_body(out, method="code")
        held = []
        code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=held.append)
        check("the typed code claims too (202)", code == 202, ans)
        proof = D.collect_proof(k, out["pair_id"], nonce)
        code, ans = D.collect({"pair_id": out["pair_id"], "proof": proof}, peer=MESH)
        check("while the card waits: 202 waiting_for_card",
              code == 202 and ans["state"] == "waiting_for_card", ans)
        view = D.session_view(here=True)[1]
        check("the PC shows the name and the words while it waits",
              view["state"] == "waiting_for_card" and view["device_name"] == "Pixel 9"
              and len(view["words"]) == 4 and " · ".join(view["words"]) in view["message"],
              view)
        check("no key exists before the card is approved", not D.registry_path().exists())
        held[0]()
        code, ans = D.collect({"pair_id": out["pair_id"], "proof": "wrong"}, peer=MESH)
        check("a wrong collect proof counts", code == 403 and ans["tries_left"] == 2, ans)
        code, ans = D.collect({"pair_id": out["pair_id"], "proof": proof}, peer=MESH)
        check("approved: 200 with the device id and the key",
              code == 200 and set(ans) == {"state", "device_id", "token"}
              and ans["state"] == "approved" and ans["token"].startswith(f"jdk1.{ans['device_id']}."),
              ans)
        code, again = D.collect({"pair_id": out["pair_id"], "proof": proof}, peer=MESH)
        check("a second collect: 410 used", code == 410 and again["state"] == "used", again)
        check("the session says the phone is connected",
              D.session_view(here=True)[1]["message"] == "Pixel 9 is connected.")
        good2, _k, _n = _claim_body(out, method="code")
        code, ans2 = D.claim(good2, peer=MESH, gate=Gate(), spawn=now_spawn)
        check("claiming a used session: 410 used", code == 410 and ans2["state"] == "used", ans2)
        check("the new key works", D.wrap_token_ok(Original())(
            FakeHandler(token=ans["token"], peer=MESH)))


def t_a_new_start_withdraws_the_old_card():
    fresh()
    _code, out = _start()
    good, k, nonce = _claim_body(out)
    held = []
    D.claim(good, peer=MESH, gate=Gate(), spawn=held.append)
    code, out2 = _start()
    check("a new start: the old session is cancelled",
          code == 200 and out2["pair_id"] != out["pair_id"]
          and D.session_view(here=True)[1]["state"] == "waiting_for_phone")
    held[0]()
    check("the old card, approved afterwards, made no key and did not touch the new one",
          not D.registry_path().exists()
          and D.session_view(here=True)[1]["state"] == "waiting_for_phone")
    code, ans = D.collect({"pair_id": out["pair_id"],
                           "proof": D.collect_proof(k, out["pair_id"], nonce)}, peer=MESH)
    check("the old phone hears 410 cancelled", code == 410 and ans["state"] == "cancelled", ans)
    code, ans = D.claim(good, peer=MESH, gate=Gate(), spawn=now_spawn)
    check("the old QR claim: 410 cancelled", code == 410 and ans["state"] == "cancelled", ans)
    check("cancel says what it was", D.cancel(here=True) == (200, {"ok": True,
                                                                   "was": "waiting_for_phone"}))
    check("... and nothing was going on afterwards: was = cancelled",
          D.cancel(here=True)[1]["was"] == "cancelled")


def t_bad_requests():
    fresh()
    _code, out = _start()
    good, _k, _n = _claim_body(out)
    for label, body, reason in (
            ("not an object", ["x"], "bad_request"),
            ("no method", dict(good, method=None), "bad_request"),
            ("a short nonce", dict(good, phone_nonce="abc"), "bad_request"),
            ("a padded nonce", dict(good, phone_nonce=good["phone_nonce"] + "=="), "bad_request"),
            ("a name with a line break", dict(good, name="Pixel\n9"), "name"),
            ("a name with a right-to-left override", dict(good, name="Pixel‮9"), "name"),
            ("a 41-character name", dict(good, name="x" * 41), "name"),
            ("an empty name", dict(good, name=""), "name")):
        code, ans = D.claim(body, peer=MESH, gate=Gate(), spawn=now_spawn)
        check(f"claim with {label}: 400 {reason}", code == 400 and ans["reason"] == reason, ans)
    check("none of those counted", D.session_view(here=True)[1]["tries_left"] == 3)
    code, ans = D.claim(dict(good, pair_id="ffffffffffffffff"), peer=MESH, gate=Gate(),
                        spawn=now_spawn)
    check("another pair_id: 410 gone, none", code == 410 and ans["state"] == "none", ans)
    D._reset_for_tests()
    code, ans = D.claim(dict(good, method="code"), peer=MESH, gate=Gate(), spawn=now_spawn)
    check("no session at all: 410 none", code == 410 and ans["state"] == "none", ans)
    check("the session view with none: {state: none}", D.session_view(here=True)
          == (200, {"state": "none"}))


# ==========================================================================
#   5. The device list, Remove, Retire, Bring back
# ==========================================================================

def t_the_device_list():
    fresh()
    with Clock():
        dev, token, _ = pair()
        dev2, _t2, _ = pair(name="Tablet")
    v = D.devices_view(you=dev, here=False, armed=lambda: True)
    text = json.dumps(v)
    check("never a key, never a hash", token not in text and "sha256" not in text
          and hashlib.sha256(token.encode()).hexdigest() not in text)
    check("This PC first, not removable", v["devices"][0]["id"] == "pc"
          and v["devices"][0]["removable"] is False)
    mine = next(r for r in v["devices"] if r["id"] == dev)
    check("the caller's own row says this_device", mine["this_device"] is True
          and mine["approval_key"] is False and mine["removable"] is True, mine)
    check("you = the device id", v["you"] == dev)
    check("the shared key's row, and Bring back only here",
          v["shared"]["retired"] is False and v["shared"]["can_bring_back_here"] is False)
    check("pairing available", v["pairing"] == {"available": True, "why_not": None}, v["pairing"])
    D.remove({"id": dev2}, you=dev)
    v = D.devices_view(you="pc", here=True, armed=lambda: True)
    check("a removed device is not listed", [r["id"] for r in v["devices"]] == ["pc", dev])
    check("the PC's own row says this_device for the PC", v["devices"][0]["this_device"] is True)


def t_remove():
    fresh()
    with Clock():
        dev, token, _ = pair()
    for body, code, reason in (({"id": "pc"}, 400, "not_removable"),
                               ({"id": [dev]}, 400, "bad_request"),
                               ([dev], 400, "bad_request"),
                               ({"id": dev, "also": 1}, 400, "bad_request"),
                               ({"ids": [dev]}, 400, "bad_request"),
                               ({"id": "d00000000"}, 404, "no_such_device"),
                               ({"id": "shared"}, 404, "no_such_device")):
        got = D.remove(body, you="pc")
        check(f"remove {body!r}: {code} {reason}", got[0] == code
              and got[1].get("reason") == reason, got)
    EVENTS.clear()
    code, out = D.remove({"id": dev}, you=dev)
    check("remove one device: 200, and it says it was the caller",
          code == 200 and out == {"ok": True, "id": dev, "name": "Pixel 9",
                                  "was_this_device": True}, out)
    check("audit line devices.removed, the id only", ("devices.removed", {"id": dev}) in AUDIT)
    check("a devices event, {}", EVENTS == [("devices", {})], EVENTS)
    row = json.loads(D.registry_path().read_text(encoding="utf-8"))["devices"][0]
    check("the row stays, its hash emptied", row["token_sha256"] == "" and row["removed"])
    check("removing it again: 404", D.remove({"id": dev}, you="pc")[0] == 404)


def t_retire_cannot_cut_off_the_asker():
    fresh()
    code, out = D.shared({"retired": True}, you="shared", here=False)
    check("Retire asked with the shared key from another device: 409 uses_it_yourself",
          code == 409 and out["reason"] == "uses_it_yourself"
          and out["error"] == D.DEVICES_WORDS["uses_it_yourself"], out)
    with Clock():
        dev, _t, _ = pair()
    code, out = D.shared({"retired": True}, you=dev, here=False)
    check("from a phone with its own key: immediate", code == 200 and out["retired"] is True, out)
    for body in ({"retired": "yes"}, {"retired": True, "x": 1}, [], {}):
        check(f"shared {body!r}: 400", D.shared(body, you="pc", here=True)[0] == 400)


def t_bring_back():
    fresh()
    D.shared({"retired": True}, you="pc", here=True)
    code, out = D.shared({"retired": False}, you="shared", here=False, gate=Gate(),
                         spawn=now_spawn)
    check("Bring back from another device: 403 pc_only", code == 403 and out["pc_only"], out)
    keep = D._lockdown_on
    D._lockdown_on = lambda: True
    try:
        code, out = D.shared({"retired": False}, you="pc", here=True, gate=Gate(),
                             spawn=now_spawn)
        check("under Lockdown: 409", code == 409 and out["lockdown"] is True, out)
    finally:
        D._lockdown_on = keep
    gate = Gate(DENY)
    code, out = D.shared({"retired": False}, you="pc", here=True, gate=gate, spawn=now_spawn)
    check("from this PC: 202 waiting, one unretire_shared_key card",
          code == 202 and out["waiting"] is True
          and [c[0] for c in gate.cards] == [D.UNRETIRE_ACTION], (out, gate.cards))
    check("denied: still retired", D.load()[0]["shared"]["retired"] is True)
    held = []
    D.shared({"retired": False}, you="pc", here=True, gate=Gate(), spawn=held.append)
    code, out = D.shared({"retired": False}, you="pc", here=True, gate=Gate(), spawn=now_spawn)
    check("a second press while the card waits: 202, no second card", code == 202
          and len(held) == 1)
    D.shared({"retired": True}, you="pc", here=True)
    held[0]()
    check("retired again while the card waited: approving it changed nothing",
          D.load()[0]["shared"]["retired"] is True)
    D.shared({"retired": False}, you="pc", here=True, gate=Gate(), spawn=now_spawn)
    check("approved: the old shared key works for other devices again",
          D.load()[0]["shared"]["retired"] is False
          and D.wrap_token_ok(Original())(FakeHandler(token=SHARED, peer=MESH)) is True)
    fw.action_tier = lambda a: "auto"
    D.shared({"retired": True}, you="pc", here=True)
    code, out = D.shared({"retired": False}, you="pc", here=True, gate=Gate(), spawn=now_spawn)
    check("unretire_shared_key not 'ask': refused, stays retired",
          code == 503 and D.load()[0]["shared"]["retired"] is True, out)


# ==========================================================================
#   6. The routes, through a handler
# ==========================================================================

def t_the_routes():
    fresh()
    D._ARMED = False

    class H(FakeHandler):
        pass

    orig = Original()
    banner = D.install(H, origin_ok=lambda h: True, token_ok=orig,
                       read_body=lambda h: h.body)
    check("the banner line says pairing is on", "pairing by QR code on" in banner, banner)
    check("capabilities.pairing = {version: 1, signed_approvals: true}",
          D.capability() == {"version": 1, "signed_approvals": True})
    h = H("/api/other", token=SHARED)
    h.do_GET()
    check("another route goes to the original", h.sent == [("original GET", "/api/other")])
    h = H("/api/devices", token="bad")
    h.do_GET()
    check("GET /api/devices needs a key", h.sent and h.sent[-1][0] == 401, h.sent)
    h = H("/api/devices", token=SHARED, peer="127.0.0.1")
    h.do_GET()
    check("GET /api/devices from this PC: you = pc", h.sent[-1][0] == 200
          and h.sent[-1][1]["you"] == "pc", h.sent)
    h = H("/api/pair/start", token=SHARED, peer=MESH,
          body={"address": "jarvis-pc.tail1234.ts.net"})
    h.do_POST()
    check("POST /api/pair/start from a phone: 403 pc_only",
          h.sent[-1][0] == 403 and h.sent[-1][1]["pc_only"] is True, h.sent)
    keep = D._owner_check_armed
    D._owner_check_armed = lambda: True
    try:
        h = H("/api/pair/start", token=SHARED, peer="127.0.0.1",
              body={"address": "jarvis-pc.tail1234.ts.net"})
        h.do_POST()
        code, out = h.sent[-1]
        check("from this PC: 200, the port defaults to the server's own",
              code == 200 and D.parse_qr(out["qr"])["port"] == 4719, h.sent)
        good, k, nonce = _claim_body(out)
        h = H("/api/pair/claim", peer=MESH, body=good)       # no key at all
        keep_spawn, keep_gate = D._spawn, D._gate
        D._spawn, D._gate = now_spawn, Gate()
        try:
            h.do_POST()
        finally:
            D._spawn, D._gate = keep_spawn, keep_gate
        check("POST /api/pair/claim takes no key: 202", h.sent[-1][0] == 202, h.sent)
        h = H("/api/pair/collect", peer=MESH,
              body={"pair_id": out["pair_id"],
                    "proof": D.collect_proof(k, out["pair_id"], nonce)})
        h.do_POST()
        code, got = h.sent[-1]
        check("POST /api/pair/collect: 200 with the key", code == 200 and "token" in got, h.sent)
        token = got["token"]
        before = orig.calls
        h = H("/api/devices/remove", token=token, peer=MESH, body={"id": got["device_id"]})
        h.do_POST()
        check("a phone removing itself still gets its own answer",
              h.sent[-1][0] == 200 and h.sent[-1][1]["was_this_device"] is True, h.sent)
        h.wfile.write(b"{}")
        check("... its answer can still be written to the stream (the guard lets it out)",
              h._jarvis_guard_device is None)
        h2 = H("/api/devices", token=token, peer=MESH)
        h2.do_GET()
        check("afterwards its key is refused, and the 401 says device_removed",
              h2.sent[-1] == (401, {"error": "bad or missing X-Jarvis-Token",
                                    "key": "device_removed"}), h2.sent)
        check("the owner's check was never asked about a device key", orig.calls == before,
              (before, orig.calls))
        h = H("/api/pair/session", token=SHARED, peer="127.0.0.1")
        h.do_GET()
        check("GET /api/pair/session: done, named", h.sent[-1][1]["state"] == "done", h.sent)
    finally:
        D._owner_check_armed = keep
        D._ARMED = False
    try:
        import jarvis_events as E
    except ImportError:
        sys.path.append(str(HERE / "rebuilt"))
        import jarvis_events as E
    check("not installed: /api/version says pairing is false",
          E._capability_probe()["pairing"] is False)
    D._ARMED = True
    try:
        check("installed: {version: 1, signed_approvals: true}",
              E._capability_probe()["pairing"] == {"version": 1, "signed_approvals": True})
    finally:
        D._ARMED = False


# ==========================================================================
#   7. Backups, scrubbing, the log
# ==========================================================================

def t_the_registry_is_not_in_a_backup():
    cfg = fresh()
    with Clock():
        pair()
    (cfg / "manner.json").write_text("{}", encoding="utf-8")
    import jarvis_backup as B
    keep = B._config_dir
    B._config_dir = lambda: cfg
    try:
        blob = B.build_archive()
    finally:
        B._config_dir = keep
    data = blob[0] if isinstance(blob, tuple) else blob
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    check("the backup has the settings folder's own JSON (the test is real)",
          "settings/manner.json" in names, names)
    # The registry is the file that holds every device's pairing key, so it must
    # never travel in a backup. Match the FILE, not any name containing "devices"
    # or "registry": a backup now also carries the backend's own source as
    # source/*.py, and jarvis_devices.py / jarvis_settings_registry.py are
    # programs, not keys. The old substring test failed on those four names and
    # said the registry was exposed when it was not.
    check("... and not the device registry itself",
          not any(n.replace("\\", "/").rsplit("/", 1)[-1].lower() == "registry.json"
                  for n in names), names)


def t_the_scrubber_knows_the_key():
    import jarvis_scrub as S
    key = "jdk1.d3f9a1c2e." + "Ab_-0123456789abcdefghijklmnopqrstuvwxyzABC"
    for text in (key, f"X-Jarvis-Token: {key}", f"token={key}&x=1", f"saved {key}."):
        out = S.scrub_text(text)
        check(f"scrubbed: {text[:24]}...", key.split(".")[2] not in out and "[redacted" in out,
              out)
    check("a near miss is left alone", S.scrub_text("jdk1.d3f9a1c2e.short") ==
          "jdk1.d3f9a1c2e.short")


def t_nothing_secret_is_printed():
    fresh()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf), Clock():
        dev, token, (started, _c, _g) = pair()
        D.wrap_token_ok(Original())(FakeHandler(token=token, peer=MESH))
        D.remove({"id": dev}, you="pc")
    said = buf.getvalue() + json.dumps(AUDIT) + json.dumps(EVENTS)
    check("nothing printed, audited or published holds the key, the QR text or the code",
          all(x not in said for x in (token, token.split(".")[2], started["qr"],
                                       started["code"], started["qr"].split("/")[4])), said[:300])


def t_a_deeply_nested_registry_is_broken_too():
    # json raises RecursionError (not a ValueError) on a file this deep.
    fresh()
    with Clock():
        dev, token, _ = pair()
    D.registry_path().write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    check("load() calls it unreadable", D.load()[1].startswith("unreadable"), D.load())
    ok = D.wrap_token_ok(Original())
    check("a device key is refused", ok(FakeHandler(token=token, peer=MESH)) is False)
    check("the shared key is refused from another device",
          ok(FakeHandler(token=SHARED, peer=MESH)) is False)
    check("the shared key still works from this PC",
          ok(FakeHandler(token=SHARED, peer="127.0.0.1")) is True)


def t_an_error_inside_the_check_refuses_other_devices_only():
    fresh()
    ok = D.wrap_token_ok(Original())
    real = D.load

    def boom():
        raise RuntimeError("simulated")
    D.load = boom
    try:
        check("the shared key from another device is refused",
              ok(FakeHandler(token=SHARED, peer=MESH)) is False)
        check("the shared key from this PC still works",
              ok(FakeHandler(token=SHARED, peer="127.0.0.1")) is True)
    finally:
        D.load = real


def t_a_proof_that_is_not_ascii_is_just_wrong():
    fresh()
    _code, out = _start()
    good, _k, _n = _claim_body(out)
    code, ans = D.claim(dict(good, proof="é" * 43), peer=MESH, gate=Gate(), spawn=now_spawn)
    check("claim: 403 wrong_proof, not a crash",
          code == 403 and ans["reason"] == "wrong_proof" and not ans.get("claimed"), (code, ans))
    code, ans = D.collect({"pair_id": out["pair_id"], "proof": "é"}, peer=MESH)
    check("collect: 403 wrong_proof, not a crash", code == 403 and ans["reason"] == "wrong_proof",
          (code, ans))


def t_the_apps_know_the_first_pairing_state():
    """Both apps word the shared key's new state from the PC's own words.

    Neither app builds in this repository, so a sentence or a button that
    drifted from the PC would go unnoticed - the same reason the address test
    above reads `PhoneAddress.kt`. What this pins (2026-10-05):

      * the row's sentence is `DEVICES_WORDS["shared_first_pair_row"]`, word
        for word, in the phone and in the desktop;
      * the phone's `KeyRefusal` knows `shared_first_pair_only`, carries the
        PC's sentence, and reads it out of a 401;
      * the phone hides "Retire for other devices" in that state (it would
        change nothing), and the desktop offers neither Retire nor Bring it
        back.
    """
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" /
          "client" / "net" / "Devices.kt").read_text(encoding="utf-8")
    plate = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" /
             "client" / "ui" / "screens" / "DevicesPlate.kt").read_text(encoding="utf-8")
    js = (REPO / "jarvis-desktop" / "src" / "devices-words.js").read_text(encoding="utf-8")

    def quoted(src, start, end):
        i = src.index(start)
        return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', src[i:src.index(end, i)]))

    row = D.DEVICES_WORDS["shared_first_pair_row"]
    got = quoted(kt, "const val SHARED_FIRST_PAIR_ROW", "const val THIS_PHONE")
    check("the phone's row sentence is the PC's, word for word", got == row, got)
    check("... and the desktop's is too (SHARED_FIRST_PAIR_ROW)", row in js, row)
    check("the phone reads first_pair_only off the wire, an absent field as false",
          'firstPairOnly = it.bool("first_pair_only") == true' in kt
          and "val firstPairOnly: Boolean = false" in kt)
    refusal = D.KEY_WORDS["shared_first_pair_only"]
    got = quoted(kt, "const val SHARED_FIRST_PAIR_ONLY_WORDS", "private val _reason")
    check("the phone's refusal sentence is the PC's, word for word", got == refusal, got)
    check("... and the phone recognises it in a 401 (reasonIn, words, isWords)",
          "it == SHARED_FIRST_PAIR_ONLY }" in kt
          and "SHARED_FIRST_PAIR_ONLY -> SHARED_FIRST_PAIR_ONLY_WORDS" in kt
          and "text == SHARED_FIRST_PAIR_ONLY_WORDS" in kt
          and 'const val SHARED_FIRST_PAIR_ONLY = "shared_first_pair_only"' in kt)
    check("the phone hides Retire in that state - it would change nothing",
          "!shared.retired && !shared.firstPairOnly && v.usesOwnKey" in plate)
    check("the desktop offers neither button in that state",
          "s.first_pair_only === true" in js and "bringBack: false," in js)
    check("... and neither app offers a card for it (the PC refuses with words)",
          "unretire_first_pair" in D.DEVICES_WORDS)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
