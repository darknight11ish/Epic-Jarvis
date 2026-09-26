"""Four account secrets, moved off plain-text Windows environment variables
into Windows Credential Manager (ease-of-use audit row 15, "Security G3"):
the IMAP username and password (jarvis_email.py), the private calendar link
(jarvis_calendar.py) and the Home Assistant token (jarvis_home.py).

    python3 test_account_secrets.py

WHAT THIS PROVES
  - jarvis_token_store.resolve_secret(), the generalized mechanism every one
    of the four calls into (the same shape jarvis_search.py's KEY_TARGETS
    already uses for the Exa/Tavily/Brave keys, factored so a secret that
    has always lived in an environment variable - not a file - can also come
    from Credential Manager without a bespoke copy per secret):
      * the environment variable wins when the owner set one, unchanged -
        BACKWARD COMPATIBILITY: an installation that already relies on the
        variable keeps working exactly as before, and Credential Manager is
        never even asked;
      * otherwise Credential Manager, under the secret's own named target;
      * otherwise "" - simply not configured, never made up, never a
        "this run only" placeholder (unlike the pairing token, none of
        these four is required for the backend to run at all);
      * a store that cannot be reached, refuses, or is not there at all
        (this dev box, not Windows) is treated as empty, never raises;
      * only a value that came from Credential Manager is registered with
        jarvis_scrub - an env-sourced value is left to jarvis_scrub's own
        existing name-based scan, so a secret that is only sometimes in the
        environment is not remembered as "known" (and so redacted by exact
        value, swallowing surrounding harmless text like a host name) for
        the rest of the process's life once it briefly passed through.
  - jarvis_email.imap_user() / imap_password(), jarvis_calendar._feed_url()
    and jarvis_home._token() each resolve through the mechanism above, under
    their own Credential Manager target, and each target's text matches
    what jarvis-desktop/src-tauri/src/token_store.rs writes under (so a
    value the owner types into Settings is the value the backend reads).
  - default_store(target) is parametrized (a decision-only refactor to serve
    more than one target) and the pairing token's own resolve() is
    unaffected: default_store() with no argument still opens the pairing
    token's own target.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_token_store as TS  # noqa: E402
import jarvis_email as EMAIL  # noqa: E402
import jarvis_calendar as CAL  # noqa: E402
import jarvis_home as HOME  # noqa: E402
import jarvis_scrub as SCRUB  # noqa: E402

REPO = HERE.parent

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class FakeStore:
    """Credential Manager, in memory - the same shape test_token_store.py's
    own FakeStore uses."""

    def __init__(self, value=None, refuse_read=False):
        self.value, self.refuse_read = value, refuse_read

    def read(self):
        if self.refuse_read:
            raise TS.StoreError("reading failed (Windows error 1312)")
        return self.value

    def write(self, token):
        self.value = token

    def delete(self):
        had, self.value = self.value is not None, None
        return had


# --------------------------------------------------------------------------
#   jarvis_token_store.resolve_secret - the mechanism itself
# --------------------------------------------------------------------------

def t_env_wins_when_set():
    got = TS.resolve_secret("X_ENV", "X Target", environ={"X_ENV": "  from-env  "},
                            store=FakeStore("from-store"))
    check("the environment variable wins, trimmed", got == "from-env")


def t_falls_back_to_the_store():
    got = TS.resolve_secret("X_ENV", "X Target", environ={}, store=FakeStore(" from-store "))
    check("no environment variable: Credential Manager is read", got == "from-store")


def t_blank_env_falls_through():
    got = TS.resolve_secret("X_ENV", "X Target", environ={"X_ENV": "   "},
                            store=FakeStore("from-store"))
    check("an all-whitespace variable is not treated as set", got == "from-store")


def t_nothing_anywhere_is_simply_unconfigured():
    got = TS.resolve_secret("X_ENV", "X Target", environ={}, store=FakeStore(None))
    check("neither source: \"\", not made up, not \"this run only\"", got == "")


def t_a_broken_store_is_treated_as_empty_never_raises():
    for store in (FakeStore(refuse_read=True), TS.Unavailable("no store on this system")):
        got = TS.resolve_secret("X_ENV", "X Target", environ={}, store=store)
        check(f"a store that cannot be read ({store}): treated as empty", got == "")


def t_default_store_is_asked_when_none_is_passed(monkeypatch=None):
    # No `store=` at all: resolve_secret must ask default_store(target) -
    # which, off Windows (this dev box), is Unavailable - so the result is
    # still "" rather than raising.
    got = TS.resolve_secret("JARVIS_DOES_NOT_EXIST_XYZ", "Some Target/for real", environ={})
    check("no store injected, off Windows: still \"\", never raises", got == "")


def t_default_store_is_parametrized_and_the_pairing_token_is_unaffected():
    check("default_store() with no argument still opens the pairing token's own name",
          isinstance(TS.default_store(), (TS.WindowsStore, TS.StoreError)))
    d = TS.default_store("Some Other Target")
    check("default_store(target) opens THAT target, off Windows this is still Unavailable",
          isinstance(d, TS.StoreError))
    factory_calls = []
    TS._STORE_FACTORY = lambda target: factory_calls.append(target) or FakeStore("x")
    try:
        TS.default_store("Whichever Target")
    finally:
        TS._STORE_FACTORY = None
    check("tests may replace _STORE_FACTORY with a stand-in, keyed by target",
          factory_calls == ["Whichever Target"])


def t_only_a_store_sourced_value_is_registered_with_the_scrubber():
    # An env-sourced value is NOT registered here - jarvis_scrub already
    # finds it by the environment variable's own NAME, scanned fresh each
    # time. Registering it too would make jarvis_scrub remember it as
    # "known" for the rest of the process's life even after the variable is
    # unset, which would then swallow harmless surrounding text (a host
    # name) that the shape-based rule alone would have let through - the
    # exact regression this test pins.
    SCRUB._REGISTERED.clear()
    TS.resolve_secret("SOME_ENV_NOT_SET_XYZ", "Whichever Target",
                      environ={"SOME_ENV_NOT_SET_XYZ": "env-value-12345678"},
                      store=FakeStore("unused"))
    check("an env-sourced value is left unregistered",
          "env-value-12345678" not in SCRUB._REGISTERED)
    SCRUB._REGISTERED.clear()
    TS.resolve_secret("SOME_ENV_NOT_SET_XYZ", "Whichever Target", environ={},
                      store=FakeStore("store-value-12345678"))
    check("a store-sourced value IS registered (there is no env NAME to catch it by)",
          "store-value-12345678" in SCRUB._REGISTERED)
    SCRUB._REGISTERED.discard("store-value-12345678")


# --------------------------------------------------------------------------
#   The four modules: each resolves through the mechanism, under its own name
# --------------------------------------------------------------------------

def t_imap_credentials():
    import os
    saved = {k: os.environ.get(k) for k in (EMAIL.USER_ENV, EMAIL.PASSWORD_ENV)}
    try:
        os.environ.pop(EMAIL.USER_ENV, None)
        os.environ.pop(EMAIL.PASSWORD_ENV, None)
        TS._STORE_FACTORY = lambda target: {
            EMAIL.IMAP_USER_TARGET: FakeStore("owner@example.com"),
            EMAIL.IMAP_PASSWORD_TARGET: FakeStore("hunter2hunter2"),
        }.get(target, FakeStore(None))
        check("imap_user() falls back to Credential Manager",
              EMAIL.imap_user() == "owner@example.com")
        check("imap_password() falls back to Credential Manager",
              EMAIL.imap_password() == "hunter2hunter2")
        check("authenticated() follows imap_user()", EMAIL.authenticated() is True)
        os.environ[EMAIL.USER_ENV] = "set-by-hand@example.com"
        check("the environment variable still wins over Credential Manager",
              EMAIL.imap_user() == "set-by-hand@example.com")
    finally:
        TS._STORE_FACTORY = None
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def t_calendar_ics_link():
    import os
    saved = os.environ.get(CAL.ICS_URL_ENV)
    try:
        os.environ.pop(CAL.ICS_URL_ENV, None)
        TS._STORE_FACTORY = lambda target: (
            FakeStore("https://calendar.google.com/private-abc123.ics")
            if target == CAL.ICS_URL_TARGET else FakeStore(None))
        check("_feed_url() falls back to Credential Manager",
              CAL._feed_url() == "https://calendar.google.com/private-abc123.ics")
        check("source() reports \"ics\" from the Credential-Manager-held link",
              CAL.source() == "ics")
        os.environ[CAL.ICS_URL_ENV] = "https://calendar.google.com/private-set-by-hand.ics"
        check("the environment variable still wins",
              CAL._feed_url() == "https://calendar.google.com/private-set-by-hand.ics")
    finally:
        TS._STORE_FACTORY = None
        if saved is None:
            os.environ.pop(CAL.ICS_URL_ENV, None)
        else:
            os.environ[CAL.ICS_URL_ENV] = saved


def t_home_assistant_token():
    import os
    saved = os.environ.get(HOME.TOKEN_ENV)
    try:
        os.environ.pop(HOME.TOKEN_ENV, None)
        TS._STORE_FACTORY = lambda target: (
            FakeStore("ha-long-lived-token-abc") if target == HOME.TOKEN_TARGET
            else FakeStore(None))
        check("_token() falls back to Credential Manager", HOME._token() == "ha-long-lived-token-abc")
        check("authenticated() follows _token()", HOME.authenticated() is True)
        os.environ[HOME.TOKEN_ENV] = "set-by-hand"
        check("the environment variable still wins", HOME._token() == "set-by-hand")
    finally:
        TS._STORE_FACTORY = None
        if saved is None:
            os.environ.pop(HOME.TOKEN_ENV, None)
        else:
            os.environ[HOME.TOKEN_ENV] = saved


def t_no_secret_ever_appears_in_an_error_message():
    """Same rule test_token_store.py checks for the pairing token: every
    raise in jarvis_token_store.py names a Windows error or a reason, never
    a value. resolve_secret adds no new raise site."""
    src = (HERE / "jarvis_token_store.py").read_text(encoding="utf-8")
    fn = src[src.index("def resolve_secret"):]
    fn = fn[:fn.index("\ndef ", 1)]
    check("resolve_secret raises nothing of its own (StoreError is only caught)",
          "raise " not in fn)


# --------------------------------------------------------------------------
#   The backend and the desktop agree on every target's name
# --------------------------------------------------------------------------

def t_the_desktop_writes_under_the_same_four_names():
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "token_store.rs").read_text(encoding="utf-8")
    pairs = {
        "JARVIS_IMAP_USER": EMAIL.IMAP_USER_TARGET,
        "JARVIS_IMAP_PASSWORD": EMAIL.IMAP_PASSWORD_TARGET,
        "JARVIS_CALENDAR_ICS_SECRET_URL": CAL.ICS_URL_TARGET,
        "JARVIS_HOME_TOKEN": HOME.TOKEN_TARGET,
    }
    for env_name, target in pairs.items():
        check(f"token_store.rs writes {env_name}'s secret under the backend's own name",
              f'"{target}"' in rs, target)
    check("the four names are only ever the desktop's ACCOUNT_SECRET_TARGETS table",
          "ACCOUNT_SECRET_TARGETS" in rs)


# --------------------------------------------------------------------------
#   Live, on real Windows only (CI's "credential-manager" job)
# --------------------------------------------------------------------------

def t_live_windows_round_trip():
    """The real ctypes calls `resolve_secret` makes when no stand-in store is
    injected - write, read back, delete - under a throwaway target name,
    never one of the four real ones. Skipped everywhere but Windows, exactly
    like test_token_store.py's own live test."""
    import os
    import secrets

    if os.name != "nt":
        print("skip  live Credential Manager round trip (not Windows)")
        return
    target = f"Jarvis Backend/test account secret {secrets.token_hex(6)}"
    env_name = f"JARVIS_TEST_DOES_NOT_EXIST_{secrets.token_hex(4)}"
    store = TS.WindowsStore(target)
    try:
        check("live: nothing there to begin with",
              TS.resolve_secret(env_name, target, store=store) == "")
        value = secrets.token_urlsafe(24)
        store.write(value)
        check("live: read back through resolve_secret",
              TS.resolve_secret(env_name, target, store=store) == value)
        check("live: an explicit environment variable still wins over it",
              TS.resolve_secret(env_name, target, environ={env_name: "hand-set"},
                                store=store) == "hand-set")
    finally:
        try:
            store.delete()
        except TS.StoreError:
            pass


if __name__ == "__main__":
    for fn in (t_env_wins_when_set, t_falls_back_to_the_store, t_blank_env_falls_through,
               t_nothing_anywhere_is_simply_unconfigured,
               t_a_broken_store_is_treated_as_empty_never_raises,
               t_default_store_is_asked_when_none_is_passed,
               t_default_store_is_parametrized_and_the_pairing_token_is_unaffected,
               t_only_a_store_sourced_value_is_registered_with_the_scrubber,
               t_imap_credentials, t_calendar_ics_link, t_home_assistant_token,
               t_no_secret_ever_appears_in_an_error_message,
               t_the_desktop_writes_under_the_same_four_names,
               t_live_windows_round_trip):
        try:
            fn()
        except Exception as exc:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} RAISED {type(exc).__name__}: {exc}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
