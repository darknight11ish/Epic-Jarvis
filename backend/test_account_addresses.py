"""test_account_addresses.py - the ADDRESSES of the owner's accounts, and the
one settings file they live in (accounts.patch; jarvis_accounts.py; the
owner's decision of 2026-10-06, CLAUDE.md: "anything needing a key or a
sign-in should be settable in the Jarvis app itself, desktop only, stored
under rule 3").

    python3 backend/test_account_addresses.py

WHAT THIS PROVES, and why each check is here:

  - the EIGHT, in one place: imap_host, imap_port, imap_mailbox, smtp_host,
    smtp_port, smtp_tls, home_url, caldav_url - and that the four SECRETS
    (the IMAP username, the IMAP password, the private iCal link, the Home
    Assistant token) are NOT among them and never reach this file;
  - accounts.json sits BESIDE web-search.json in the config folder - the same
    shape as the SearXNG address, which is the code-proven model for "an
    address or a choice", and deliberately NOT Credential Manager (a
    store-sourced value is redacted by exact value by jarvis_scrub, which
    would swallow harmless surrounding text such as a host name; see
    test_account_secrets.py's own first bullet);
  - the ENVIRONMENT VARIABLE STILL WINS, on every read, in every reader -
    jarvis_email, jarvis_email_send, jarvis_email_draft, jarvis_home,
    jarvis_calendar and jarvis_reach - so an installation that already sets
    one keeps working exactly as it did;
  - the FILE IS THE FALLBACK, in each of those readers, which is the whole
    point: email can be read and sent, Home Assistant and the calendar can be
    reached, and "What Jarvis can reach" stops saying "not set up";
  - the ROUTE REFUSES A SECRET by name, in the same shape
    test_web_search.py's "the settings route takes no key" already checks for
    the SearXNG route: 400, the value nowhere in the answer, and NOTHING
    written;
  - one change per request, and a value of the wrong shape refused with the
    plain sentence (a port that is not a port, a mode that is not one of the
    three, a plain http:// address off the owner's own networks);
  - accounts.patch applies to what web-search.patch wrote, reverses cleanly,
    checks origin and token on both routes, and its blocks RUN - the GET
    answers the eight, the POST saves one, a key is refused, and there is no
    route that takes a key;
  - the desktop really calls it (src-tauri/src/account_addresses.rs names
    both paths), and the two shipped-module lists name jarvis_accounts.py.

Nothing here opens a socket, and nothing here needs the owner's PC.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-accounts-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_accounts.py", "jarvis_email.py", "jarvis_email_send.py",
                "jarvis_email_draft.py", "jarvis_home.py", "jarvis_calendar.py",
                "jarvis_reach.py", "jarvis_search.py", "jarvis_local_http.py")

import jarvis_accounts as ACC  # noqa: E402
import jarvis_calendar as CAL  # noqa: E402
import jarvis_email as EMAIL  # noqa: E402
import jarvis_email_draft as DRAFT  # noqa: E402
import jarvis_email_send as SEND  # noqa: E402
import jarvis_home as HOME  # noqa: E402
import jarvis_reach as REACH  # noqa: E402
import jarvis_search as WS  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: A fake secret, built by concatenation so nothing here is shaped like a
#: real one.
FAKE_PASSWORD = "hu" + "nter" + "2" + "hunter" + "2"
FAKE_TOKEN = "ey" + "Jfake" + "homeassistant" + "token"
FAKE_TAVILY = "tv" + "ly-" + "fake" + "0123456789ab"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


#: Every environment variable any of the eight is read under, so a check can
#: be sure the environment is not quietly supplying the answer it is testing.
def clear_env():
    for name in set(list(ACC.ENV.values()) + list(ACC.ENV)
                    + [EMAIL.USER_ENV, EMAIL.PASSWORD_ENV,
                       CAL.ICS_URL_ENV, CAL.USER_ENV, CAL.PASSWORD_ENV,
                       HOME.TOKEN_ENV]):
        os.environ.pop(name, None)


def reset(**saved):
    """No file (or exactly `saved` in it), and no environment variable from
    the eight."""
    clear_env()
    path = ACC.addresses_path()
    if path.exists():
        path.unlink()
    if saved:
        ACC._save(**saved)


# --------------------------------------------------------------------------
#   1. The eight, and the four that are not among them
# --------------------------------------------------------------------------

def t_the_eight_and_the_secrets():
    check("the eight are the addresses and the one choice the card collects",
          ACC.FIELDS == ("imap_host", "imap_port", "imap_mailbox",
                         "smtp_host", "smtp_port", "smtp_tls",
                         "home_url", "caldav_url"), ACC.FIELDS)
    check("each has the environment variable it has always been read under",
          ACC.ENV == {"imap_host": "JARVIS_IMAP_HOST",
                      "imap_port": "JARVIS_IMAP_PORT",
                      "imap_mailbox": "JARVIS_IMAP_MAILBOX",
                      "smtp_host": "JARVIS_SMTP_HOST",
                      "smtp_port": "JARVIS_SMTP_PORT",
                      "smtp_tls": "JARVIS_SMTP_TLS",
                      "home_url": "JARVIS_HOME_URL",
                      "caldav_url": "JARVIS_CALDAV_URL"}, ACC.ENV)
    for name in (EMAIL.USER_ENV, EMAIL.PASSWORD_ENV, CAL.ICS_URL_ENV,
                 HOME.TOKEN_ENV):
        check(f"{name} is not one of the eight (rule 3: a secret is never here)",
              name not in ACC.ENV.values())
    check("... nor does any field name a key, a password, a token or a link",
          not [f for f in ACC.FIELDS
               if re.search(r"key|password|token|secret|ics", f)])
    src = Path(ACC.__file__).read_text(encoding="utf-8")
    check("the module never names the secrets' own environment variables",
          not [v for v in (EMAIL.USER_ENV, EMAIL.PASSWORD_ENV, CAL.ICS_URL_ENV,
                           HOME.TOKEN_ENV) if v in src])
    check("the three TLS modes are jarvis_email_send's own list, not a copy "
          "that can drift",
          ACC.TLS_MODES == SEND.TLS_MODES, (ACC.TLS_MODES, SEND.TLS_MODES))


# --------------------------------------------------------------------------
#   2. The file: beside web-search.json, holding addresses only
# --------------------------------------------------------------------------

def t_the_file():
    reset()
    check("accounts.json sits beside web-search.json in the config folder",
          ACC.addresses_path().parent == WS.settings_path().parent
          and ACC.addresses_path().name == "accounts.json",
          (ACC.addresses_path(), WS.settings_path()))
    got = ACC.addresses()
    check("no file: all eight are empty, and nothing is wrong",
          all(got[f] == "" for f in ACC.FIELDS) and got["why"] == "", got)
    code, out = ACC.handle_get()
    check("GET answers the eight, in order, with each one's environment "
          "variable and whether it is set",
          code == 200 and [f["name"] for f in out["fields"]] == list(ACC.FIELDS)
          and all(f["env"] == ACC.ENV[f["name"]] and f["env_set"] is False
                  for f in out["fields"]), out)
    code, out = ACC.handle_settings({"imap_host": "imap.gmail.com"})
    check("one address saves, at once, and is said back in the PC's words",
          code == 200 and out["ok"] and ACC.addresses()["imap_host"] == "imap.gmail.com"
          and "imap.gmail.com" in out["said"], (code, out))
    on_disk = json.loads(ACC.addresses_path().read_text(encoding="utf-8"))
    check("the file is plain JSON with only the eight and a timestamp",
          set(on_disk) == set(ACC.FIELDS) | {"changed"}, sorted(on_disk))
    check("the answer repeats no more than the eight - never a secret",
          set(json.loads(json.dumps(out))["fields"][0]) ==
          {"name", "env", "env_set", "value"})
    reset(imap_host="x.example.com")
    ACC.addresses_path().write_text("{not json", encoding="utf-8")
    got = ACC.addresses()
    check("a damaged file fails SAFE: the eight read empty and it says so",
          all(got[f] == "" for f in ACC.FIELDS) and got["why"]
          and "could not be read" in got["why"], got)
    check("... and nothing is invented from it (no address is guessed at)",
          ACC.value("imap_host") == "")


# --------------------------------------------------------------------------
#   3. The environment variable still wins, everywhere
# --------------------------------------------------------------------------

def t_the_environment_wins():
    reset(imap_host="from-file.example.com", imap_port="1143",
          imap_mailbox="FromFile", smtp_host="smtp-file.example.com",
          smtp_port="1587", smtp_tls="starttls", home_url="https://file.example",
          caldav_url="https://file.example/dav")
    os.environ["JARVIS_IMAP_HOST"] = "from-env.example.com"
    os.environ["JARVIS_HOME_URL"] = "https://env.example"
    check("jarvis_accounts.value() reads the environment variable first",
          ACC.value("imap_host") == "from-env.example.com"
          and ACC.value("home_url") == "https://env.example")
    check("... and env_set() says so, without ever the value",
          ACC.env_set("imap_host") is True and ACC.env_set("imap_port") is False)
    code, out = ACC.handle_get()
    field = next(f for f in out["fields"] if f["name"] == "imap_host")
    check("... GET says the variable wins AND still shows what is saved here",
          field["env_set"] is True and field["value"] == "from-file.example.com",
          field)
    check("jarvis_email reads the variable, exactly as before",
          EMAIL._configured() and EMAIL.plan().host == "from-env.example.com")
    check("jarvis_home reads the variable, exactly as before",
          HOME._base_url() == "https://env.example")
    check("jarvis_reach reads the variable, exactly as before",
          REACH._env("JARVIS_IMAP_HOST") == "from-env.example.com"
          and REACH._env("JARVIS_HOME_URL") == "https://env.example")
    check("saving here never touches the environment variable it loses to",
          ACC.handle_settings({"imap_host": "another.example.com"})[0] == 200
          and os.environ["JARVIS_IMAP_HOST"] == "from-env.example.com"
          and EMAIL.plan().host == "from-env.example.com")
    check("... and an empty value here clears only the file, never the variable",
          ACC.handle_settings({"smtp_host": "smtp-file.example.com"})[0] == 200
          and ACC.handle_settings({"smtp_host": ""})[0] == 200
          and ACC.addresses()["smtp_host"] == "")
    check("the environment is checked even if jarvis_accounts.py is not there",
          re.search(r"os\.environ\.get\(env_name", Path(EMAIL.__file__)
                    .read_text(encoding="utf-8")) is not None
          and re.search(r"os\.environ\.get\(URL_ENV", Path(HOME.__file__)
                        .read_text(encoding="utf-8")) is not None)


# --------------------------------------------------------------------------
#   4. The file is the fallback, in every reader
# --------------------------------------------------------------------------

def t_the_file_is_the_fallback():
    reset(imap_host="imap.gmail.com", imap_port="1993", imap_mailbox="Chats",
          smtp_host="smtp.office365.com", smtp_port="1587", smtp_tls="starttls",
          home_url="http://192.168.1.5:8123", caldav_url="https://cal.example/dav")
    check("the environment is empty, so anything read now comes from the file",
          not ACC.env_set("imap_host"))
    p = EMAIL.plan(5)
    check("jarvis_email reads host, port and mailbox from the file",
          p.host == "imap.gmail.com" and p.port == 1993 and p.mailbox == "Chats"
          and p.configured, p)
    s = SEND.settings()
    check("jarvis_email_send reads the sending server from the file",
          s.host == "smtp.office365.com" and s.port == 1587 and s.tls == "starttls",
          s)
    reset(imap_host="imap.gmail.com")
    check("... and still works the sending server out from the reading one when "
          "only that one is saved (imap.X -> smtp.X)",
          SEND.settings().host == "smtp.gmail.com" and SEND.settings().host_guessed)
    d = DRAFT.settings()
    check("jarvis_email_draft reads the same account from the file",
          d.host == "imap.gmail.com" and d.port == EMAIL._DEFAULT_PORT, d)
    # A fresh file with the other four, so each reader is asked about its own
    # - `reset` writes ONLY what it is given.
    reset(imap_host="imap.gmail.com", home_url="http://192.168.1.5:8123",
          caldav_url="https://cal.example/dav")
    check("jarvis_home reads its address from the file",
          HOME._base_url() == "http://192.168.1.5:8123" and HOME._configured(),
          repr(HOME._base_url()))
    check("... and a Home Assistant plan is built against it",
          HOME.plan_states(["light.kitchen"]).queries
          and all("http://192.168.1.5:8123" in q.url
                  for q in HOME.plan_states(["light.kitchen"]).queries),
          HOME.plan_states(["light.kitchen"]).reason_empty)
    check("jarvis_calendar reads its CalDAV address from the file",
          CAL._base_url() == "https://cal.example/dav" and CAL._configured()
          and CAL.source() == "caldav",
          (repr(CAL._base_url()), CAL.source()))
    os.environ[CAL.ICS_URL_ENV] = "https://calendar.google.com/private/basic.ics"
    check("... and the private iCal link still wins over it when both are set",
          CAL.source() == "ics")
    clear_env()
    check("... and a CalDAV address alone is still a calendar to read",
          CAL.source() == "caldav" and CAL.plan(3).query is not None)
    reset(imap_host="imap.gmail.com", home_url="http://192.168.1.5:8123")
    check("jarvis_reach answers the file's addresses, so its rows stop saying "
          "\"not set up\"",
          REACH._env("JARVIS_IMAP_HOST") == "imap.gmail.com"
          and REACH._env("JARVIS_HOME_URL") == "http://192.168.1.5:8123"
          and REACH._env("JARVIS_IMAP_MAILBOX") == "")
    # `enabled` is set here, not read, so the check does not depend on which
    # tools this machine's settings file happens to offer the model: what is
    # being asked is whether the ADDRESS made the row "set up".
    ctx = REACH.Ctx(enabled={"email_check", "home_read"})
    rows = {r["id"]: r for r in REACH.view(ctx)["rows"]}
    check("... and \"What Jarvis can reach\" shows both as on, at that host",
          rows["email_read"]["state"] != "not_set_up"
          and "imap.gmail.com" in rows["email_read"]["where"]
          and rows["home_read"]["state"] != "not_set_up"
          and "192.168.1.5" in rows["home_read"]["where"],
          {k: rows[k] for k in ("email_read", "home_read")})
    # ... and with the tools not offered at all, the row is still *set up*
    # rather than "not set up" - which is the sentence this feature removes.
    plain = {r["id"]: r for r in REACH.view(REACH.Ctx(enabled=set()))["rows"]}
    check("... and with no tool offered, the row still says it is set up",
          plain["email_read"]["state"] == "off" and plain["home_read"]["state"] == "off",
          (plain["email_read"], plain["home_read"]))
    check("a SECRET's own name is never answered from the file",
          REACH._env("JARVIS_HOME_TOKEN") == ""
          and REACH._env("JARVIS_CALENDAR_ICS_SECRET_URL") == ""
          and REACH._env("JARVIS_IMAP_PASSWORD") == ""
          and REACH._env("SOMETHING_ELSE") == "")


# --------------------------------------------------------------------------
#   5. A key, a password or a token is refused - and nothing is written
# --------------------------------------------------------------------------

def t_a_secret_is_refused():
    reset(imap_host="imap.gmail.com")
    before = ACC.addresses_path().read_text(encoding="utf-8")
    for name, value in (("imap_password", FAKE_PASSWORD),
                        ("imap_user", "someone@example.com"),
                        ("home_token", FAKE_TOKEN),
                        ("calendar_ics_url", "https://calendar.google.com/x"),
                        ("tavily_key", FAKE_TAVILY),
                        ("exa_key", "exa-fake"),
                        ("brave_key", "BSAfake"),
                        ("password", FAKE_PASSWORD),
                        ("token", FAKE_TOKEN),
                        # A value no sentence of ours can contain by accident,
                        # so "the value was echoed back" is a real question.
                        ("anything_at_all", "zz-must-never-be-echoed-zz")):
        code, out = ACC.handle_settings({name: value})
        said = json.dumps(out)
        check(f"the route takes no {name}", code == 400 and value not in said,
              (name, code, out))
    check("... and NOTHING was written by any of them",
          ACC.addresses_path().read_text(encoding="utf-8") == before
          and ACC.addresses()["imap_host"] == "imap.gmail.com")
    code, out = ACC.handle_settings({"imap_password": FAKE_PASSWORD})
    check("the refusal says plainly that a secret is never sent here",
          code == 400 and "Credential Manager" in out["error"]
          and "ADDRESS" in out["error"] and FAKE_PASSWORD not in json.dumps(out))
    reset()
    ACC.handle_settings({"home_token": FAKE_TOKEN})
    check("a secret sent to a PC with no file yet does not create one",
          not ACC.addresses_path().exists())
    check("one change per request",
          ACC.handle_settings({"imap_host": "a.example.com",
                               "smtp_host": "b.example.com"})[0] == 400
          and ACC.handle_settings({})[0] == 400
          and ACC.handle_settings({"imap_host": "a.example.com"})[0] == 200)
    for body, why in (({"imap_port": "not a port"}, "port"),
                      ({"imap_port": "70000"}, "65535"),
                      ({"smtp_tls": "plain"}, "ssl, starttls, off"),
                      ({"imap_host": "http://imap.gmail.com:993/"}, "plain mail server"),
                      ({"home_url": "ftp://home"}, "http://"),
                      ({"home_url": "http://evil.example.com"}, "not this PC"),
                      ({"caldav_url": "https://"}, "host name"),
                      ({"imap_host": "x" * 201}, "too long")):
        code, out = ACC.handle_settings(dict(body))
        check(f"a value of the wrong shape is refused: {sorted(body)[0]} = "
              f"{str(list(body.values())[0])[:24]!r}",
              code == 400 and why in out["error"], (code, out))
    check("a plain http:// address on the owner's own networks IS allowed",
          ACC.handle_settings({"home_url": "http://homeassistant.local:8123"})[0] == 200
          and ACC.handle_settings({"caldav_url": "http://192.168.1.9:5232/"})[0] == 200)
    check("an https:// address anywhere is allowed (it is encrypted)",
          ACC.handle_settings({"caldav_url": "https://caldav.fastmail.com/dav/"})[0] == 200)
    check("the eight are the only names this route knows",
          ACC.handle_settings({"imap_hosts": "x"})[0] == 400)
    reset()
    check("nothing was left set by the refusals",
          ACC.addresses()["caldav_url"] == "" and ACC.addresses()["imap_port"] == "")


# --------------------------------------------------------------------------
#   6. accounts.patch
# --------------------------------------------------------------------------

def _rehearse():
    order = _stack.order()
    if "accounts.patch" not in order:
        return False, "accounts.patch is not in apply-patches.ps1's list", {}
    before = order[:order.index("accounts.patch")]
    patch = (HERE / "accounts.patch").read_text(encoding="utf-8")
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-acc-patch-"))
    try:
        text, log = _stack.stand_in("jarvis_hud.py", before)
        if text is None:
            return False, "; ".join(log), {}
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "--include", "jarvis_hud.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            return False, f"jarvis_hud.py: {r.stderr}", {}
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "--include", "jarvis_hud.py", "p.patch"],
                           cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, f"jarvis_hud.py: does not reverse cleanly: {r.stderr}", {}
        return True, "", {"jarvis_hud.py": after}
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)
        return self.sent


def t_the_patch():
    patch = (HERE / "accounts.patch").read_text(encoding="utf-8")
    check("accounts.patch adds no route that takes a key, a password or a token",
          not re.search(r'/api/accounts/(key|secret|password|token)\b', patch))
    if not shutil.which("git"):
        skip("git is not installed, so the patch cannot be rehearsed")
        return
    ok, why, after = _rehearse()
    check("accounts.patch applies to what web-search.patch wrote, and reverses",
          ok, why)
    if not ok:
        return
    hud = after["jarvis_hud.py"]
    i = hud.index('        if path == "/api/accounts/addresses":')
    get_blk = hud[i:hud.index('        if path == "/api/schedule":', i)]
    i = hud.index('        if route == "/api/accounts/addresses":')
    post_blk = hud[i:hud.index('\n\n', i)]
    for name, b in (("GET", get_blk), ("POST", post_blk)):
        check(f"{name} checks origin and token",
              "_origin_ok(self)" in b and "_token_ok(self)" in b)
    def code_only(block):
        """The block's REAL lines - its own comments say why a secret is not
        here, which is the opposite of carrying one."""
        return "\n".join(l for l in block.split("\n")
                         if not l.strip().startswith("#"))

    check("neither block names a secret in its own code (comments excluded)",
          not re.search(r"imap_password|home_token|ics_secret|token_store|Credential",
                        code_only(get_blk) + code_only(post_blk)))

    reset()
    ns = {}
    exec(compile("def f(self, path, _origin_ok, _token_ok):\n" + get_blk,
                 "<GET>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/accounts/addresses", lambda s: True, lambda s: True)
    check("GET runs and answers the eight addresses",
          h.sent[0] == 200 and [f["name"] for f in h.sent[1]["fields"]] == list(ACC.FIELDS),
          h.sent)
    ns["f"](h, "/api/accounts/addresses", lambda s: True, lambda s: False)
    check("... 401 without the token", h.sent[0] == 401)
    ns["f"](h, "/api/accounts/addresses", lambda s: False, lambda s: True)
    check("... 403 from another origin", h.sent[0] == 403)

    ns = {"json": json}
    exec(compile("def f(self, route, _origin_ok, _token_ok, _read_body):\n" + post_blk,
                 "<POST>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/accounts/addresses", lambda s: True, lambda s: True,
            lambda s: b'{"imap_host": "imap.gmail.com"}')
    check("POST runs: one address saves, at once",
          h.sent[0] == 200 and ACC.addresses()["imap_host"] == "imap.gmail.com",
          h.sent)
    ns["f"](h, "/api/accounts/addresses", lambda s: True, lambda s: True,
            lambda s: json.dumps({"imap_password": FAKE_PASSWORD}).encode())
    check("... and a key is refused by the route itself, never echoed",
          h.sent[0] == 400 and FAKE_PASSWORD not in json.dumps(h.sent[1]), h.sent)
    ns["f"](h, "/api/accounts/addresses", lambda s: True, lambda s: True,
            lambda s: b"{nope")
    check("... not JSON is 400", h.sent[0] == 400)
    ns["f"](h, "/api/accounts/addresses", lambda s: True, lambda s: False,
            lambda s: b"{}")
    check("... 401 without the token", h.sent[0] == 401)

    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies accounts.patch after web-search.patch",
          all(names.index(p) < names.index("accounts.patch")
              for p in ("web-search.patch", "schedule.patch", "hardware.patch")))
    check("... and ships jarvis_accounts.py, which the route imports",
          "'jarvis_accounts.py'" in ps1
          and "jarvis_accounts.py" in (HERE / "_where.py").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
#   7. The desktop really calls the route, and the route never carries a secret
# --------------------------------------------------------------------------

def t_the_desktop_calls_it():
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src"
          / "account_addresses.rs").read_text(encoding="utf-8")
    # The shipped half only: the `#[cfg(test)]` block below it names the four
    # secrets on purpose, to prove each one is refused.
    code = rs[:rs.index("#[cfg(test)]")]
    for bit in ("/api/accounts/addresses", "get_account_addresses",
                "save_account_address", "FIELDS"):
        check(f"account_addresses.rs names {bit}", bit in code or bit in rs)
    check("... and its shipped code never names one of the four secrets",
          not re.search(r"imap_password|imap_user\b|home_token|calendar_ics_url", code))
    check("... while its own tests refuse all four before a request is built",
          all(f'"{name}"' in rs for name in
              ("imap_password", "imap_user", "home_token", "calendar_ics_url")))
    ui = (REPO / "jarvis-desktop" / "src" / "account-secrets.js").read_text(encoding="utf-8")
    check("the card's own words carry the eight, and none of the four secrets "
          "among them",
          "ADDRESSES" in ui and "imap_host" in ui and "caldav_url" in ui)
    check("the phone has no such page (one-sided on purpose, ARCHITECTURE 8)",
          "accounts/addresses" not in
          "\n".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in (REPO / "jarvis-client").rglob("*.kt")))


if __name__ == "__main__":
    for fn in (t_the_eight_and_the_secrets, t_the_file, t_the_environment_wins,
               t_the_file_is_the_fallback, t_a_secret_is_refused, t_the_patch,
               t_the_desktop_calls_it):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
