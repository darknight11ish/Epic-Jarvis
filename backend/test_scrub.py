"""jarvis_scrub.py and log-scrub.patch: passwords, keys and the pairing token
do not reach backend.log - and ordinary text that only LOOKS like them is
left alone.

Built from the extraction research's own tests (Module 1), plus the two
things that research found wrong with its design, each proven here:
  - a logger made BEFORE the scrubber starts is covered too
    (t_a_logger_made_early_is_covered);
  - a private-key line with no END line no longer silences the rest of the
    log (t_an_unended_key_does_not_silence_the_log).

No network, nothing on this machine is read except a temporary folder.

    python3 test_scrub.py
"""
import ast
import base64
import io
import logging
import os
import socket
import sys
import tempfile
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_scrub.py", "rebuilt/jarvis_router.py")
# The router sits in rebuilt/ in this repository and beside the others on
# the PC (and in run_suites' staged copy). Appended, so a backend's own copy
# wins.
sys.path.append(str(HERE / "rebuilt"))
import jarvis_scrub as S  # noqa: E402
import jarvis_router as R  # noqa: E402
import _stack  # noqa: E402

FAILED, PASSED = [], []

# The real streams, put back after every test that installs the scrubber.
REAL_OUT, REAL_ERR = sys.stdout, sys.stderr


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""),
          file=REAL_OUT)


class NoNetwork:
    """Any socket at all, in this block, is a failure."""

    def __enter__(self):
        self.real = socket.socket.connect

        def boom(*a, **k):
            raise AssertionError("a socket was opened")

        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


class Env:
    """Set environment variables for one block, restore after."""

    def __init__(self, **kv):
        self.kv = kv

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.kv}
        for k, v in self.kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


# Fake credentials, each in its provider's published format.
ANTHROPIC = "sk-ant-api03-" + "Ab3dE5gH7jK9mN1pQ3sT5vX7zB9cD1fG3hJ5kL7" + "-xyzAA"
OPENAI_PROJ = "sk-proj-" + "Q1w2E3r4T5y6U7i8O9p0A1s2D3f4G5h6J7k8L9z0"
OPENAI_OLD = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4"
GH_CLASSIC = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
GH_FINE = "github_pat_11ABCDEFG0" + "a1b2c3d4e5f6g7h8i9j0_k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6A7B8C9D0E1F2"
AWS = "AKIA" + "IOSFODNN7EXAMPLE"
AWS_TEMP = "ASIA" + "IOSFODNN7EXAMPLE"
GOOGLE = "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"
SLACK = "xoxb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
STRIPE = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"
GITLAB = "glpat-" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn"
HF = "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz01234567"
JWT = ("eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "."
       + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
PAIRING = "Zr8-qW3_xT1vL9mN0pK2sD4fG6hJ8kL0aS2dF4gH6jK"   # token_urlsafe(32) shape
PEM = ("-----BEGIN OPENSSH PRIVATE KEY-----\n"
       "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
       "QyNTUxOQAAACBx3E8m9mQ9sVn0mB3kL7sXw0q1b2c3d4e5f6g7h8i9jAAAAJgAAAAAAAAA\n"
       "-----END OPENSSH PRIVATE KEY-----")
KEY_BODY = ("b3BlbnNzaC1rZXkt", "QyNTUxOQ")


# -- every shape is caught, and the log still says what it was ---------------

def t_shapes():
    cases = [
        ("Anthropic key", f"key is {ANTHROPIC} ok", ANTHROPIC, "API key"),
        ("OpenAI project key", f"export X={OPENAI_PROJ}", OPENAI_PROJ, "API key"),
        ("OpenAI classic key", OPENAI_OLD, OPENAI_OLD, "API key"),
        ("GitHub classic token", f"push with {GH_CLASSIC}", GH_CLASSIC, "GitHub token"),
        ("GitHub fine-grained token", f"t {GH_FINE}", GH_FINE, "GitHub token"),
        ("AWS key", f"aws {AWS} here", AWS, "AWS access key"),
        ("AWS temporary key", f"aws {AWS_TEMP} here", AWS_TEMP, "AWS access key"),
        ("Google key", f"?q=1 {GOOGLE}", GOOGLE, "Google API key"),
        ("Slack token", SLACK, SLACK, "Slack token"),
        ("Stripe key", STRIPE, STRIPE, "Stripe key"),
        ("GitLab token", GITLAB, GITLAB, "GitLab token"),
        ("Hugging Face token", HF, HF, "Hugging Face token"),
        ("JWT", f"cookie-less {JWT}", JWT, "JSON web token"),
    ]
    for name, text, secret, label in cases:
        out = S.scrub_text(text)
        check(f"{name}: the value is gone", secret not in out, out)
        check(f"{name}: the log still says what it was", label in out, out)

    out = S.scrub_text("Authorization: Bearer abcdefghijklmnop1234567890")
    check("a bearer header keeps its name and loses its value",
          out.startswith("Authorization: Bearer [redacted") and "1234567890" not in out, out)
    out = S.scrub_text("X-Jarvis-Token: " + PAIRING)
    check("the Jarvis header loses its value by shape, as CrashLog.kt does on Android",
          PAIRING not in out and "X-Jarvis-Token:" in out, out)
    out = S.scrub_text("could not reach postgres://jarvis:hunter2hunter2@db.local:5432/x")
    check("a password inside a URL is removed, the host is kept",
          "hunter2hunter2" not in out and "db.local:5432" in out, out)
    out = S.scrub_text("https://owner:pw@192.168.1.20:8123/api")
    check("a short password inside a URL is removed too", ":pw@" not in out, out)
    out = S.scrub_text("GET http://127.0.0.1:41184/search?query=tax&token=abc123def456 failed")
    check("a token in a query string is removed, the query is kept",
          "abc123def456" not in out and "query=tax" in out and "&token=" in out, out)
    for text, secret in [('PASSWORD="hunter22"', "hunter22"),
                         ("password=hunter22", "hunter22"),
                         ('{"api_key": "abcd1234efgh"}', "abcd1234efgh"),
                         ("IMAP_PASSWORD: correcthorse", "correcthorse"),
                         ("Set-Cookie: session=abc123; HttpOnly", "abc123")]:
        out = S.scrub_text(text)
        check(f"a labelled secret is caught: {text[:22]}", secret not in out, out)
    out = S.scrub_text("before\n" + PEM + "\nafter")
    check("a private key loses its body, not only its header line",
          not any(b in out for b in KEY_BODY), out)
    check("CONTROL: the text around the key survives", "before" in out and "after" in out, out)


def t_the_router_table_is_the_one_used():
    """One table for 'a key was pasted' (the router's gate 3) and 'a key is in
    the log' - so a key shape added to one is in the other."""
    ours = [p for _k, p in S._router_shapes()]
    theirs = [p for _k, p in R._SECRET_PATTERNS]
    check("the scrubber uses jarvis_router._SECRET_PATTERNS itself", ours == theirs,
          f"{len(ours)} vs {len(theirs)}")
    for key in (ANTHROPIC, OPENAI_PROJ, GH_FINE, AWS_TEMP, GITLAB, STRIPE):
        check(f"the router's own check sees {key[:12]}...",
              R.looks_like_a_secret(f"my key is {key}") is not None)


# -- identifiers --------------------------------------------------------------

def t_identifiers():
    out = S.scrub_text("mail from dr.okafor@clinic.example failed")
    check("an e-mail address is removed", "okafor" not in out, out)
    out = S.scrub_text(r"C:\Users\pcadmin\Documents\Claude\Open jarvis files\x.py")
    check("the Windows user name is removed from a path",
          "pcadmin" not in out and r"\Documents\Claude" in out, out)
    out = S.scrub_text("/home/mario/.env and C:/Users/Mario Rossi/AppData")
    check("POSIX home and forward-slash Windows paths too",
          "mario" not in out and "Rossi" not in out and "AppData" in out, out)
    out = S.scrub_text(r"C:\Users\Public\Desktop")
    check("CONTROL: C:\\Users\\Public is not a person and stays", "Public" in out, out)
    out = S.scrub_text("call +44 20 7946 0958 now")
    check("a +-prefixed phone number is removed", "7946" not in out, out)
    out = S.scrub_text("mail dr.okafor@clinic.example", identifiers=False)
    check("identifiers=False keeps the address", "okafor" in out, out)


def t_leaves_ordinary_text_alone():
    plain = [
        "created 1758585600 and 2026-09-23T12:00:00Z",
        "max_tokens=4096 token_count=12 prompt_tokens: 88",
        "commit 3f786850e387550fdab836ed7e6dc881de23001b",
        "bind 100.101.102.103:8765 over Tailscale",
        "Basic authentication failed (401)",
        "the token was refused",
        "diff +123 -45",
        "sk-short",
        "  open  ->   http://localhost:4719",
        "GET /api/pending HTTP/1.1 200",
    ]
    for text in plain:
        out = S.scrub_text(text)
        check(f"left alone: {text[:40]}", out == text, f"became {out!r}")


# -- the values this process holds ------------------------------------------

def t_known_values():
    with Env(HUD_TOKEN=PAIRING):
        out = S.scrub_text(f"paired with {PAIRING}.")
    check("the pairing token in HUD_TOKEN is removed by VALUE", PAIRING not in out, out)
    check("CONTROL: the shapes alone miss it - only its value can catch it",
          PAIRING in S._apply_shapes(f"paired with {PAIRING}.")[0])

    joplin = "0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a/+="
    with Env(JOPLIN_TOKEN=joplin):
        quoted = urllib.parse.quote(joplin, safe="")
        out = S.scrub_text(f"unknown url type: 'localhost/search?q={quoted}'")
    check("the URL-quoted form jarvis_notes.py sends is removed too", quoted not in out, out)

    with Env(OPENAI_API_KEY="plain-looking-value-99", JARVIS_MEMORY_K="12345678"):
        out = S.scrub_text("value plain-looking-value-99 and k 12345678")
    check("any *_API_KEY variable counts", "plain-looking-value-99" not in out, out)
    check("CONTROL: a variable not named like a secret does not", "12345678" in out, out)

    with Env(JARVIS_CALDAV_USER="mario", JARVIS_CALDAV_PASSWORD="dav-pass-1234"):
        blob = base64.b64encode(b"mario:dav-pass-1234").decode()
        out = S.scrub_text(f"sent {blob}")
    check("the CalDAV Basic-auth blob jarvis_calendar.py builds is removed", blob not in out, out)

    import jarvis_framework as fw
    tmp = Path(tempfile.mkdtemp(prefix="scrubtest-"))
    real_dir = fw.CONFIG_DIR
    fw.CONFIG_DIR = tmp
    try:
        (tmp / "token").write_text("file-token-" + "q" * 32 + "\n", encoding="utf-8")
        out = S.scrub_text("x file-token-" + "q" * 32 + " y")
        check("an old token FILE that token-store could not move is still removed",
              "q" * 32 not in out, out)
    finally:
        fw.CONFIG_DIR = real_dir

    S.register_secret("registered-secret-value")
    S.register_secret("short")
    out = S.scrub_text("a registered-secret-value and a short word")
    check("register_secret() values are removed", "registered-secret-value" not in out, out)
    check("CONTROL: a value under 8 characters is not replaced everywhere", "short" in out, out)


def t_the_joplin_error_is_scrubbed():
    """jarvis_notes.py appends ?token=<Joplin token> to the URL. Set
    JARVIS_JOPLIN_URL without "http://" and urllib raises
    ValueError("unknown url type: '<whole URL>'") - token included. If that
    ever reaches the log, it goes without the token."""
    token = "joplinTOKEN" + "7" * 40
    url = f"localhost/search?query=x&token={urllib.parse.quote(token, safe='')}"
    with NoNetwork():
        try:
            urllib.request.build_opener().open(urllib.request.Request(url), timeout=1)
            exc = None
        except Exception as e:
            exc = e
    raw = f"{type(exc).__name__}: {exc}" if exc else ""
    check("CONTROL: the unscrubbed error really does carry the token", token in raw, raw)
    out = S.scrub_text(raw)
    check("scrubbed, by shape, even with no variable set", token not in out, out)
    check("the error's type is kept", out.startswith("ValueError:"), out)


# -- private keys --------------------------------------------------------------

def t_an_unended_key_does_not_silence_the_log():
    """The research printed a BEGIN line with no END and watched every later
    line of the log disappear. Now only what looks like key material goes."""
    text = ("start\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA1b2c3d4e5f6g7h8i9j0\n"
            "AAAA+/==\nTraceback (most recent call last):\n  the next log line\n")
    out = S.scrub_text(text)
    check("scrub_text: the key lines go", "MIIEow" not in out and "AAAA+/==" not in out, out)
    check("scrub_text: the lines after them stay",
          "Traceback (most recent call last)" in out and "the next log line" in out, out)

    sink = io.StringIO()
    w = S._ScrubbingStream(sink)
    for line in text.splitlines(keepends=True):
        w.write(line)
    w.write("much later, an ordinary line\n")
    got = sink.getvalue()
    check("the log: the key lines go", "MIIEow" not in got and "AAAA+/==" not in got, got)
    check("the log: the lines after an unended key are written again",
          "Traceback" in got and "much later, an ordinary line" in got, got)

    sink = io.StringIO()
    w = S._ScrubbingStream(sink)
    w.write("-----BEGIN PRIVATE KEY-----\n")
    for _ in range(S._KEY_MAX_LINES + 20):
        w.write("QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE9\n")
    w.write("the log goes on\n")
    check("a key block is hidden for at most a key's worth of lines",
          "the log goes on" in sink.getvalue(), sink.getvalue()[-200:])
    check(f"... {S._KEY_MAX_LINES} lines, then the log is written again",
          sink.getvalue().count("QUE9\n") == 20, str(sink.getvalue().count("QUE9\n")))

    one_line = '{"key": "' + PEM.replace("\n", "\\n") + '", "next": "field"}'
    out = S.scrub_text(one_line)
    check("a key inside a JSON string (\\n written out) is removed too",
          not any(b in out for b in KEY_BODY) and '"next": "field"' in out, out)


# -- never raises, never fails open -------------------------------------------

def t_fails_closed():
    class Nasty:
        def __str__(self):
            raise RuntimeError("secret-in-the-exception " + GH_CLASSIC)
    out = S.scrub_text(Nasty())
    check("an object whose str() raises is withheld, not passed through",
          out.startswith("[redacted") and GH_CLASSIC not in out, out)

    real = S._CONTEXT_SHAPES
    S._CONTEXT_SHAPES = None   # forces an internal TypeError
    try:
        out = S.scrub_text("text with " + GH_CLASSIC)
        found = S.find_secret("plain words")
    finally:
        S._CONTEXT_SHAPES = real
    check("an internal failure withholds the text rather than returning it",
          GH_CLASSIC not in out and "withheld" in out, out)
    check("find_secret fails towards 'secret', never towards 'clean'", found is not None, found)


def t_idempotent():
    text = (f"{ANTHROPIC} Bearer {'z' * 30} password=hunter22 "
            f"postgres://u:pw123456@h/x ?token=abc123 dr@x.example C:\\Users\\bob\\x")
    once = S.scrub_text(text)
    check("scrubbing twice gives the same text as once", S.scrub_text(once) == once,
          f"\n  once:  {once}\n  twice: {S.scrub_text(once)}")


def t_find_secret():
    k = S.find_secret(f"here is my key {ANTHROPIC}")
    check("find_secret names the kind", k and "API key" in k, k)
    check("find_secret never returns the value", k and ANTHROPIC[:12] not in k, k)
    check("find_secret: ordinary text is None", S.find_secret("what's the weather") is None)
    check("find_secret: an e-mail address alone is not a secret",
          S.find_secret("mail bob@example.com") is None)
    check("find_secret: a private key", S.find_secret(PEM) == "a private key")
    with Env(JARVIS_HOME_TOKEN="ha-long-lived-" + "x" * 30):
        k = S.find_secret("pasted ha-long-lived-" + "x" * 30)
    check("find_secret sees a held credential that has no shape",
          k and "JARVIS_HOME_TOKEN" in k and "xxxx" not in k, k)


# -- backend.log: the streams ------------------------------------------------

def t_stream():
    sink = io.StringIO()
    w = S._ScrubbingStream(sink)
    for part in ("Authorization: Bearer", " ", "abcdefghij", "klmnop123456", "\n"):
        w.write(part)
    check("a secret split across write() calls is still caught",
          "abcdefghijklmnop123456" not in sink.getvalue(), sink.getvalue())
    w.write("no newline yet " + GH_CLASSIC)
    check("nothing is written before the line is complete", GH_CLASSIC not in sink.getvalue()
          and "no newline yet" not in sink.getvalue())
    w.flush()
    check("flush() writes the partial line, scrubbed",
          "no newline yet" in sink.getvalue() and GH_CLASSIC not in sink.getvalue(), sink.getvalue())

    sink2 = io.StringIO()
    w2 = S._ScrubbingStream(sink2)
    for line in ("start\n" + PEM + "\nend\n").splitlines(keepends=True):
        w2.write(line)
    got = sink2.getvalue()
    check("a key block written line by line loses every body line",
          not any(b in got for b in KEY_BODY), got)
    check("CONTROL: lines after the key block are written again", "end" in got, got)

    sink3 = io.StringIO()
    sys.stderr = S._ScrubbingStream(sink3)
    try:
        try:
            raise ValueError("unknown url type: 'localhost/x?token=abcdef123456'")
        except ValueError:
            sys.__excepthook__(*sys.exc_info())
        sys.stderr.flush()
    finally:
        sys.stderr = REAL_ERR
    check("an uncaught traceback reaches the log scrubbed",
          "abcdef123456" not in sink3.getvalue() and "ValueError" in sink3.getvalue(),
          sink3.getvalue())
    check("everything else is the real stream's", w.closed is False)


class Installed:
    """install() with sys.stdout and sys.stderr standing in as StringIO, and
    everything put back after - the logging record factory included."""

    def __init__(self, token=None):
        self.token = token

    def __enter__(self):
        self.out, self.err = io.StringIO(), io.StringIO()
        self.factory = logging.getLogRecordFactory()
        self.done = S._LOGGING_DONE
        S._LOGGING_DONE = False
        sys.stdout, sys.stderr = self.out, self.err
        self.result = S.install(self.token)
        return self

    def text(self) -> str:
        for s in (sys.stdout, sys.stderr):
            try:
                s.flush()
            except Exception:
                pass
        return self.out.getvalue() + self.err.getvalue()

    def __exit__(self, *a):
        self.text()
        sys.stdout, sys.stderr = REAL_OUT, REAL_ERR
        logging.setLogRecordFactory(self.factory)
        S._LOGGING_DONE = self.done
        return False


def t_install_wraps_both_streams_once():
    with Installed() as inst:
        first = (sys.stdout, sys.stderr)
        check("install() wraps stdout and stderr", inst.result
              and getattr(sys.stdout, "_jarvis_scrub", False)
              and getattr(sys.stderr, "_jarvis_scrub", False))
        S.install()
        check("calling it twice does not wrap twice", (sys.stdout, sys.stderr) == first)
        print("printed", GH_CLASSIC)
        text = inst.text()
    check("a print() after install() is scrubbed", GH_CLASSIC not in text and "printed" in text,
          text)


def t_install_registers_the_pairing_token():
    token = "Q" + PAIRING[1:]   # not in the environment: only install() knows it
    with Env(HUD_TOKEN=None):
        with Installed(token) as inst:
            print(f"the phone sent {token}")
            text = inst.text()
    check("the token handed to install() never reaches the log", token not in text, text)


def t_a_logger_made_early_is_covered():
    """The research's own finding: a logger set up before the scrubber
    started still wrote an OpenAI key in clear text."""
    stand_in_err = io.StringIO()
    sys.stderr = stand_in_err
    early = logging.getLogger("jarvis_scrub_test.early")
    early.propagate = False
    handler = logging.StreamHandler()          # holds THIS sys.stderr, made now
    early.addHandler(handler)
    tmp = Path(tempfile.mkdtemp(prefix="scrublog-")) / "early.log"
    file_handler = logging.FileHandler(tmp, encoding="utf-8")
    early.addHandler(file_handler)
    sys.stderr = REAL_ERR
    try:
        stand_in_out = io.StringIO()
        factory = logging.getLogRecordFactory()
        done = S._LOGGING_DONE
        S._LOGGING_DONE = False
        sys.stdout, sys.stderr = stand_in_out, stand_in_err
        try:
            S.install()
            early.warning("calling with %s", OPENAI_PROJ)
            try:
                raise RuntimeError(f"bad key {GH_CLASSIC}")
            except RuntimeError:
                early.exception("it failed")
            late = logging.getLogger("jarvis_scrub_test.late")
            late.propagate = False
            late_file = Path(str(tmp) + ".late")
            late.addHandler(logging.FileHandler(late_file, encoding="utf-8"))
            late.error("late logger, %s", ANTHROPIC)
            for h in early.handlers + late.handlers:
                h.flush()
            sys.stderr.flush()
        finally:
            sys.stdout, sys.stderr = REAL_OUT, REAL_ERR
            logging.setLogRecordFactory(factory)
            S._LOGGING_DONE = done
        text = stand_in_err.getvalue()
        check("a StreamHandler made before install() is re-pointed at the scrubbed stream",
              getattr(handler.stream, "_jarvis_scrub", False), repr(handler.stream))
        check("... and its output carries no key", OPENAI_PROJ not in text and
              "calling with" in text, text)
        check("... nor a key inside a traceback it logs", GH_CLASSIC not in text and
              "RuntimeError" in text, text)
        on_disk = tmp.read_text(encoding="utf-8")
        check("a FileHandler made before install() writes no key either",
              OPENAI_PROJ not in on_disk and GH_CLASSIC not in on_disk
              and "calling with" in on_disk, on_disk)
        late_text = late_file.read_text(encoding="utf-8")
        check("a logger made after install() is covered too",
              ANTHROPIC not in late_text and "late logger" in late_text, late_text)
    finally:
        for h in list(early.handlers):
            early.removeHandler(h)
            h.close()
        for h in list(logging.getLogger("jarvis_scrub_test.late").handlers):
            logging.getLogger("jarvis_scrub_test.late").removeHandler(h)
            h.close()


def t_it_never_says_what_it_removed():
    """Nothing in the module prints or logs, and scrubbing writes nothing
    anywhere: the only output is the returned text, and in it only a kind."""
    out, err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = out, err
    try:
        with Env(HUD_TOKEN=PAIRING):
            S.scrub_text(f"{PAIRING} {GH_CLASSIC} password=hunter22")
            S.find_secret(f"{PAIRING} {GH_CLASSIC}")
    finally:
        sys.stdout, sys.stderr = REAL_OUT, REAL_ERR
    check("scrubbing writes nothing to stdout or stderr", out.getvalue() + err.getvalue() == "",
          out.getvalue() + err.getvalue())
    code = _code_only()
    for bad in ("print(", "logging.info", "logging.warning", "logging.error", ".write_text(",
                "open("):
        check(f"the module never calls {bad}", bad not in code)
    with Env(HUD_TOKEN=PAIRING):
        out = S.scrub_text(f"t={PAIRING}")
    check("a replacement names the kind, never a piece of the value",
          PAIRING[:6] not in out and PAIRING[-6:] not in out and "HUD_TOKEN" in out, out)


def _code_only() -> str:
    src = (HERE / "jarvis_scrub.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant):
            body[0].value.value = ""
    return ast.unparse(tree)


def t_no_switch_and_no_network():
    code = _code_only()
    check("it reads no setting - nothing can turn it off",
          "load_framework" not in code and "redact_private_content_in_logs" not in code
          and "action_tier" not in code)
    for bad in ("urlopen", "socket", "requests", "http.client", "subprocess"):
        check(f"it does not use {bad}", bad not in code)


# -- log-scrub.patch ------------------------------------------------------------

def t_the_patch_installs_it_right_after_the_token():
    src, log = _stack.stand_in("jarvis_hud.py")
    check("log-scrub.patch applies over the whole patch stack", src is not None, str(log)[-400:])
    if src is None:
        return
    check("... onto lines earlier patches wrote, not onto guessed ones",
          not any(l.startswith("log-scrub.patch") for l in log),
          [l for l in log if l.startswith("log-scrub.patch")])
    lines = src.splitlines()
    at = lines.index("HUD_TOKEN = _resolve_token()")
    block = "\n".join(lines[at:at + 14])
    check("install(HUD_TOKEN) comes right after the token is resolved",
          "jarvis_scrub.install(HUD_TOKEN)" in block, block)
    banner = _stack.fragment_with(src, "if _SCRUBBING_LOG:") or []
    check("the banner says so, only when it is really on",
          any("kept out of this log" in l for l in banner), banner)

    start = next(i for i in range(at, at + 14) if lines[i] == "try:")
    snippet = "\n".join(lines[start:start + 5]) + "\n"
    # Run the patch's own lines: with the module, and without it.
    with Installed() as inst:
        ns = {"HUD_TOKEN": "patched-token-" + "p" * 20}
        exec(compile(snippet, "<log-scrub.patch>", "exec"), ns)
        print("sent patched-token-" + "p" * 20)
        text = inst.text()
    check("the patch's lines turn it on and hand over the token",
          ns.get("_SCRUBBING_LOG") is True and "p" * 20 not in text, text)
    real = sys.modules.get("jarvis_scrub")
    sys.modules["jarvis_scrub"] = None       # "import jarvis_scrub" now raises
    try:
        ns = {"HUD_TOKEN": "x"}
        exec(compile(snippet, "<log-scrub.patch>", "exec"), ns)
    finally:
        sys.modules["jarvis_scrub"] = real
    check("without jarvis_scrub.py the backend still starts, and says nothing",
          ns.get("_SCRUBBING_LOG") is False)


if __name__ == "__main__":
    for fn in (t_shapes, t_the_router_table_is_the_one_used, t_identifiers,
               t_leaves_ordinary_text_alone, t_known_values, t_the_joplin_error_is_scrubbed,
               t_an_unended_key_does_not_silence_the_log, t_fails_closed, t_idempotent,
               t_find_secret, t_stream, t_install_wraps_both_streams_once,
               t_install_registers_the_pairing_token, t_a_logger_made_early_is_covered,
               t_it_never_says_what_it_removed, t_no_switch_and_no_network,
               t_the_patch_installs_it_right_after_the_token):
        print(f"\n--- {fn.__name__} ---", file=REAL_OUT)
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            sys.stdout, sys.stderr = REAL_OUT, REAL_ERR
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
