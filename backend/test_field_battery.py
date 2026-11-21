"""test_field_battery.py - the promoted field battery's own offline checks.

What this proves, with NO HUD, NO network and NO token:

1. `tools/field_battery.py --self-test` runs in a fresh process and exits 0,
   reporting all 30 cases as expected. That self-test is the battery's own
   negative control: it feeds the exact honest answers the build gives AND
   wrong shapes (an invented PR number, a claim with no PR, a wrong defect
   count) and requires the wrong ones to FAIL.
2. The two-address preflight's decision is a pure function and it fails when a
   configured non-loopback address answers nothing - the row that would have
   caught the two phone outages - while it is "off" when remote access is not
   configured, and "ok" when both addresses answer.
3. `remote_bind()` reads the same two places the HUD reads and never treats
   loopback as a phone-facing bind.
4. `address_answers()` distinguishes "a listener answered" from "nothing is
   there", using a real socket on loopback only.
5. `read_project_rows()` is read-only and honest about a missing store.
6. The recorder's own contract: a true check is a PASS, a false check is a
   FAIL (so a section cannot quietly pass everything).

Run: python3 backend/test_field_battery.py
"""
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import field_battery as F  # noqa: E402

PASSED, FAILED = [], []
BASE = Path(tempfile.mkdtemp(prefix="jarvis-field-battery-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_the_offline_self_test_runs_and_passes():
    proc = subprocess.run([sys.executable, str(HERE.parent / "tools" / "field_battery.py"),
                           "--self-test"], capture_output=True, text=True, timeout=300,
                          cwd=str(BASE), env={**os.environ, "JARVIS_BACKEND": "",
                                              "OLLAMA_URL": ""})
    out = (proc.stdout or "") + (proc.stderr or "")
    check("--self-test exits 0 in a fresh process", proc.returncode == 0, out[-800:])
    check("... and reports all 30 cases as expected", "30/30 self-test cases as expected" in out,
          out[-400:])
    check("... with its explicit PASS result line",
          "RESULT: PASS" in out and "wrong answers still refused" in out, out[-300:])


def t_the_two_address_verdict_is_real():
    ok, probs = F.two_address_verdict("", 403, 0)
    check("remote access off -> the row is off, not broken", ok == "off" and probs == [],
          (ok, probs))
    ok, probs = F.two_address_verdict("100.75.21.228", 403, 403)
    check("both addresses answering -> ok", ok == "ok" and probs == [], (ok, probs))
    ok, probs = F.two_address_verdict("100.75.21.228", 403, 0)
    check("a configured address that answers nothing -> broken", ok == "broken", (ok, probs))
    check("... and the problem names the phone-facing address",
          any("100.75.21.228" in p and "offline" in p for p in probs), probs)
    ok, probs = F.two_address_verdict("100.75.21.228", 0, 403)
    check("localhost answering nothing is also a problem", ok == "broken"
          and any("127.0.0.1" in p for p in probs), (ok, probs))


def t_remote_bind_reads_the_environment_and_never_loopback():
    old = os.environ.get("JARVIS_HUD_BIND")
    try:
        os.environ.pop("JARVIS_HUD_BIND", None)
        # With the shipped settings the bind is loopback (or absent) -> off.
        check("no environment bind and the shipped settings -> no phone address",
              F.remote_bind() == "", repr(F.remote_bind()))
        os.environ["JARVIS_HUD_BIND"] = "127.0.0.1"
        check("a loopback environment bind is not a phone-facing address",
              F.remote_bind() == "", repr(F.remote_bind()))
        os.environ["JARVIS_HUD_BIND"] = "100.75.21.228"
        check("a mesh environment bind is read", F.remote_bind() == "100.75.21.228",
              repr(F.remote_bind()))
    finally:
        if old is None:
            os.environ.pop("JARVIS_HUD_BIND", None)
        else:
            os.environ["JARVIS_HUD_BIND"] = old


def t_remote_bind_reads_the_settings_file():
    toml = BASE / "framework.toml"
    toml.write_text("[security]\nrequire_server_auth_key = true\n"
                    "bind_address = \"100.64.0.9\"\n", encoding="utf-8")
    old_file, old_env = F.REMOTE_BIND_FILE, os.environ.pop("JARVIS_HUD_BIND", None)
    try:
        F.REMOTE_BIND_FILE = toml
        check("a non-loopback bind_address is read from the settings",
              F.remote_bind() == "100.64.0.9", repr(F.remote_bind()))
        toml.write_text("[security]\nbind_address = \"127.0.0.1\"\n", encoding="utf-8")
        check("a loopback bind_address is not a phone-facing address",
              F.remote_bind() == "", repr(F.remote_bind()))
    finally:
        F.REMOTE_BIND_FILE = old_file
        if old_env is not None:
            os.environ["JARVIS_HUD_BIND"] = old_env


def t_address_answers_sees_a_listener_and_its_absence():
    # A real listener on loopback only: no foreign address is ever bound.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def answer():
        try:
            conn, _ = server.accept()
            conn.recv(1024)
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            conn.close()
        except Exception:
            pass

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    try:
        got = F.address_answers("127.0.0.1", port)
        check("a listener that answers 403 counts as answering", got == 403, got)
    finally:
        server.close()
    check("a port with no listener answers 0",
          F.address_answers("127.0.0.1", port) == 0)


def t_read_project_rows_is_read_only_and_honest():
    missing = BASE / "nope.db"
    check("a missing store is (0, [])", F.read_project_rows(missing) == (0, []),
          F.read_project_rows(missing))
    db = BASE / "projects.db"
    con = sqlite3.connect(db)
    con.execute("create table projects (id text primary key, name text, created real)")
    con.executemany("insert into projects values (?,?,?)",
                    [("a" * 32, "One", 1.0), ("b" * 32, "Two", 2.0)])
    con.commit()
    con.close()
    before = db.read_bytes()
    count, rows = F.read_project_rows(db)
    check("a two-project store reads two rows", count == 2
          and [r["name"] for r in rows] == ["One", "Two"], (count, rows))
    check("... and reading it changed nothing", db.read_bytes() == before)


def t_the_recorder_cannot_pass_a_false_check():
    rec = F.Recorder()
    rec.header("T", "a test section")
    true_ok = rec.expect("a true check passes", True)
    false_ok = rec.expect("a false check fails", False, "this must never count as a pass")
    rec.end("PASS", "the section itself claimed PASS")
    row = rec.rows[-1]
    check("a true check returns True", true_ok is True)
    check("a false check returns False", false_ok is False)
    check("... and the failed check is counted on the section's row",
          row["fail"] == 1 and row["pass"] == 1, row)


def t_phone_listener_field_is_the_preflight_s_authority():
    """Ruling 5.1: PREFLIGHT reads /api/status's `phone_listener`, when it exists.

    The listener is a second HUD process started in the DESKTOP's environment;
    this battery cannot see that environment, so the HUD's own field is the only
    honest word. Fake payloads drive the pure decision, then the preflight block
    is checked to read the field BEFORE its settings fallback.
    """
    absent, probs = F.phone_listener_verdict(None)
    check("no phone_listener field -> absent (an older HUD, never a guess)",
          absent == "absent" and probs == [], (absent, probs))
    absent, _p = F.phone_listener_verdict("not an object either")
    check("... and a non-object field is absent too", absent == "absent", absent)

    off, probs = F.phone_listener_verdict(
        {"configured": False, "listening": False, "bind_address": None})
    check("configured false -> off (an honest SKIP, not a failure)",
          off == "off" and probs == [], (off, probs))

    ok, probs = F.phone_listener_verdict(
        {"configured": True, "listening": True,
         "bind_address": "100.75.21.228:4719"})
    check("configured and listening -> ok", ok == "ok" and probs == [], (ok, probs))

    broken, probs = F.phone_listener_verdict(
        {"configured": True, "listening": False,
         "bind_address": "100.75.21.228:4719"})
    check("configured but not listening -> broken, never ok",
          broken == "broken", (broken, probs))
    check("... and the problem NAMES the address the phone cannot reach",
          probs and "100.75.21.228:4719" in probs[0]
          and "offline" in probs[0], probs)
    broken, probs = F.phone_listener_verdict(
        {"configured": True, "listening": False, "bind_address": None})
    check("... with no address, it still FAILS and names the port",
          broken == "broken" and any("4719" in p for p in probs), probs)

    # The section itself must READ the field, before the settings fallback.
    source = Path(F.__file__).read_text(encoding="utf-8")
    start = source.index("def section_preflight(")
    end = source.index("\ndef ", start + 1)
    block = source[start:end]
    check("PREFLIGHT asks /api/status for the field", '"/api/status"' in block
          and '.get("phone_listener")' in block)
    check("... and decides with phone_listener_verdict()", "phone_listener_verdict(" in block)
    check("... and a broken field is an EXPECT (FAIL), not an info line",
          "REC.expect(\"the phone-facing listener configured on this PC answers\",\n"
          "                   False" in block, block[:400])
    check("... the settings-based two-address check remains the absent-field fallback",
          "two_address_verdict(bind" in block
          and block.index("phone_listener_verdict(") < block.index("two_address_verdict(bind"))


def t_the_stale_cloud_override_is_stamped_and_never_rescues_an_unknown():
    verdict, sentence = F.stale_decision("FRESH", False)
    check("a current build is a plain pass", verdict == "pass", (verdict, sentence))
    verdict, sentence = F.stale_decision("STALE", False)
    check("a stale build skips the money rows by default", verdict == "skip"
          and "STALE BUILD" in sentence, (verdict, sentence))
    verdict, sentence = F.stale_decision("STALE", True)
    check("--allow-stale-cloud runs them and stamps the sentence",
          verdict == "override" and "STALE BUILD (override)" in sentence, (verdict, sentence))
    verdict, sentence = F.stale_decision("UNPROVEN", True)
    check("an unproven identity is never rescued by the override",
          verdict == "fail" and "unproven" in sentence, (verdict, sentence))

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
