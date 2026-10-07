"""test_chatbot_keys.py - the six chatbot API keys: ONE list of Windows
Credential Manager names, owned by the Python side, and the desktop's own
table pinned against it.

    python backend/test_chatbot_keys.py

WHY THIS TEST IS THE LOAD-BEARING ONE
`docs/ACCOUNT-KEYS-DESIGN.md` sections 6 and 8 (steps 1-2). The desktop's
Settings page writes each key straight into Credential Manager from Rust, and
the backend reads it later by asking `jarvis_chatbot_api.KEY_TARGETS`. The two
names are therefore built in two languages, and if they ever disagree the
failure is silent and ugly: the page says "Saved" under a name the backend
never reads, and the only symptom is "no key saved" forever after.

So the names are generated from the Python side into one fixture both langs
point at (`tools/gen_chatbot_key_targets.py`), and BOTH ends are pinned here
or beside it:

  * this file regenerates the fixture's exact text and compares it with the
    committed copy, and checks every target against `KEY_TARGETS` itself -
    so a Python-side change that was not regenerated fails HERE;
  * `token_store.rs`'s `the_six_chatbot_targets_are_the_python_sides_own`
    `include_str!`s the desktop copy and compares it with the Rust table - so
    a desktop-side drift fails at `cargo test`.

WHAT ELSE THIS PROVES (the rules from CLAUDE.md, quoted in the design note
section 6)
  * Rule 3 - "never logged, sent only to the one service it authenticates
    against, and kept out of anything the app writes to disk in plain text":
    the key is written to Credential Manager and NOWHERE ELSE. Checked by
    reading the real desktop source: the two commands that save and remove a
    key name no HTTP client, no file write and no log at all.
  * The negative test the task asks for - the new route takes no key: there
    is no backend route for a chatbot API key and there must not be one.
    Checked three ways - the module's own tables, the saved route list, and
    the desktop's own Rust, which talks to the backend for nothing here.
  * The phone is never asked for an account secret: neither Android app
    names a chatbot key target or one of the new commands.
  * The key shown back to the owner is never the key: the status answer is
    "is one saved", and the save answer is words.
  * `jarvis_chatbot_api.py` itself: the six presets, the one-line rule its
    `KEY_TARGETS` is built by, and the fact that no environment variable is
    read for any of them.

Pure Python, no network, no Credential Manager, no model.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

import jarvis_chatbot_api as API  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   The fixture: one list, generated from the Python side
# --------------------------------------------------------------------------

FIXTURE = HERE / "tests" / "fixtures" / "chatbot-api-key-targets.json"
DESKTOP_FIXTURE = REPO / "jarvis-desktop" / "tests" / "fixtures" / "chatbot-api-key-targets.json"
GENERATOR = REPO / "tools" / "gen_chatbot_key_targets.py"


def t_the_generator_agrees_with_the_committed_fixture():
    """Byte for byte. This is what makes the fixture trustworthy: it is not a
    hand-typed list, it is `PRESETS`' own output."""
    sys.path.insert(0, str(REPO / "tools"))
    import gen_chatbot_key_targets as G  # noqa: E402

    want = G.canonical()
    have = FIXTURE.read_text(encoding="utf-8")
    check("the committed fixture is exactly what the Python side generates", have == want,
          "run: python tools/gen_chatbot_key_targets.py")
    check("the generator itself refuses to guess if KEY_TARGETS' rule is ever broken",
          "will not guess" in GENERATOR.read_text(encoding="utf-8"))


def t_every_target_is_the_python_sides_own():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    check("it names the expression the targets come from",
          doc.get("source") == "jarvis_chatbot_api.KEY_TARGETS", doc.get("source"))
    check("it names the one-line rule they are built by",
          doc.get("rule") == "Jarvis Backend/{company} API key", doc.get("rule"))
    rows = doc["targets"]
    check("all six presets are listed", len(rows) == len(API.PRESETS) == 6,
          f"{len(rows)} rows, {len(API.PRESETS)} presets")
    check("every listed id is a real preset",
          all(r["id"] in API.PRESETS for r in rows),
          [r["id"] for r in rows if r["id"] not in API.PRESETS])
    for row in rows:
        p = API.PRESETS[row["id"]]
        check(f"{row['short']}: the fixture's target is the live KEY_TARGETS value",
              row["target"] == API.KEY_TARGETS[row["id"]] == f"Jarvis Backend/{p.company} API key",
              f"{row['target']!r} vs {API.KEY_TARGETS[row['id']]!r}")
        check(f"{row['short']}: the company, short name and key page are the preset's own",
              (row["company"], row["short"], row["key_where"])
              == (p.company, p.short, p.key_where))
    check("every short name the owner types is covered",
          sorted(r["short"] for r in rows) == sorted(API.BY_SHORT),
          sorted(r["short"] for r in rows))
    check("no two services share one Credential Manager name",
          len({r["target"] for r in rows}) == len(rows))
    check("every name is a \"Jarvis Backend/... API key\" entry",
          all(r["target"].startswith("Jarvis Backend/") and r["target"].endswith(" API key")
              for r in rows))


def t_the_two_copies_of_the_fixture_are_identical():
    """The desktop's own `cargo test` reads the other copy; a fix applied to
    one and not the other would leave one end pinned against a stale list."""
    check("jarvis-desktop's copy is byte-identical to the backend's",
          DESKTOP_FIXTURE.exists()
          and DESKTOP_FIXTURE.read_text(encoding="utf-8")
          == FIXTURE.read_text(encoding="utf-8"),
          str(DESKTOP_FIXTURE))


def t_the_fixture_matches_the_desktop_table_by_name():
    """The desktop's table, read out of its own Rust. Kept deliberately dumb -
    `cargo test` proves the same thing properly; this is so a desktop-side
    drift is named by name (and in CI, which runs the Python suites) even
    when nobody ran `cargo test`."""
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "token_store.rs").read_text(
        encoding="utf-8")
    block = rs[rs.index("pub const CHATBOT_API_KEY_TARGETS"):]
    block = block[:block.index("];")]
    pairs = dict(re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', block))
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    want = {r["short"]: r["company"] for r in doc["targets"]}
    check("token_store.rs's CHATBOT_API_KEY_TARGETS names the same six services",
          set(pairs) == set(want), f"rust {sorted(pairs)} vs python {sorted(want)}")
    check("and the same company for each",
          pairs == want,
          {k: (pairs.get(k), want.get(k)) for k in set(pairs) | set(want)
           if pairs.get(k) != want.get(k)})
    check("it is the desktop's own table, not a second hand-typed list elsewhere",
          "CHATBOT_API_KEY_TARGETS" in rs and "ACCOUNT_SECRET_TARGETS" in rs)


# --------------------------------------------------------------------------
#   Rule 3: Credential Manager and nowhere else
# --------------------------------------------------------------------------

def _rust_fn(src: str, name: str) -> str:
    """A Rust function's own body, braces counted: `pub async fn` or plain
    `fn`, from the opening brace to the one that closes it.

    Brace-counted rather than cut at the first `\\n}\\n`: a function whose own
    body is indented one level (every one of these) closes its inner blocks
    with `\\n        }\\n`, so a naive cut ends before the function does.
    """
    m = re.search(
        rf"\b(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+{re.escape(name)}\s*[(<]", src
    )
    if m is None:
        raise AssertionError(f"{name} is not in this file")
    start = m.start()
    i = src.index("{", m.end())
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start : j + 1]
    raise AssertionError(f"{name} has no closing brace")


def t_the_key_never_travels_over_http_and_never_touches_a_file():
    """THE NEGATIVE TEST the task asks for: the new path takes no key over
    HTTP. It is made of two halves, both read from the real source:

      * the desktop: the two commands that handle a key value call the
        Credential Manager functions and nothing else - no HTTP client, no
        file write, no log line;
      * the backend: there is no route that accepts a key at all.
    """
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "account_secrets.rs").read_text(
        encoding="utf-8")
    transport = ("jarvis_client", "reqwest", "http::", "JARVIS_URL", "jarvis_base",
                 "jarvis_headers", "fs::write", "File::create", "println!", "log::",
                 "eprintln!", "tracing::")
    for name in ("save_chatbot_api_key", "forget_chatbot_api_key", "get_chatbot_api_keys"):
        body = _rust_fn(rs, name)
        found = [t for t in transport if t in body]
        check(f"{name} sends the key nowhere and writes it nowhere", not found, found)
    save = _rust_fn(rs, "save_chatbot_api_key")
    check("save_chatbot_api_key writes through the token store",
          "write_chatbot_api_key" in save and "chatbot_api_key_problem" in save)
    check("save_chatbot_api_key's answer is words, never the key",
          "value" not in save[save.index("Ok(serde_json::json!"):])
    check("forget_chatbot_api_key removes through the token store",
          "delete_chatbot_api_key" in _rust_fn(rs, "forget_chatbot_api_key"))
    status = _rust_fn(rs, "get_chatbot_api_keys") + _rust_fn(rs, "chatbot_status")
    check("get_chatbot_api_keys reads only whether one is saved, never it",
          "chatbot_api_key_saved" in status
          and "chatbot_api_key_problem" not in status
          and "write_chatbot_api_key" not in status
          and re.search(r'serde_json::json!\(\{\s*"services"', status) is not None)


def t_the_backend_has_no_route_that_takes_a_key():
    """The other half: `save_key` says so itself, and no saved route list
    names one. A route would be a second path for a secret to travel, which
    rule 3 and the design note both forbid."""
    module = (HERE / "jarvis_chatbot_api.py").read_text(encoding="utf-8")
    fn = module[module.index("def save_key("):]
    fn = fn[:fn.index("\ndef ", 1)]
    check("jarvis_chatbot_api.save_key is the command line's own, and says so",
          "NO route for it" in fn, "its own docstring must still name the rule")
    for name, path in (("jarvis_hud.py", HERE / "jarvis_hud.py"),
                       ("jarvis_chatbot_routes.py", HERE / "jarvis_chatbot_routes.py")):
        if not path.exists():
            print(f"skip  {name} is not in this repository (patched onto the PC)")
            continue
        src = path.read_text(encoding="utf-8")
        for route in ("/api/chatbot/key", "/api/chatbot/keys", "save_key", "forget_key",
                      "KEY_TARGETS"):
            check(f"{name} has no route or call named {route}", route not in src)
    spec = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("the API reference still says keys are added on the PC, not over a route",
          "jarvis_chatbot_api.py key openai" in spec)


# --------------------------------------------------------------------------
#   The module's own rules (the same shape as the web-search keys')
# --------------------------------------------------------------------------

def t_no_environment_variable_is_read_for_any_chatbot_key():
    """Unlike the four account secrets, these have never had an environment
    variable path. The desktop table must therefore carry no env column, and
    the module must not read one - finding a key in the environment is
    exactly the plain-text-on-disk habit rule 3 exists to stop."""
    module = (HERE / "jarvis_chatbot_api.py").read_text(encoding="utf-8")
    check("the module reads no environment variable for a key",
          not re.search(r"environ[^\n]*KEY_TARGETS|getenv\([^\n]*KEY_TARGETS", module))
    check("its own docstring says there is no environment variable and no file",
          "No\n    environment variable, no file, no new store." in module
          or "no\n    environment variable, no file, no new store." in module
          or "environment variable, no file, no new store" in module)
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "token_store.rs").read_text(
        encoding="utf-8")
    block = rs[rs.index("pub const CHATBOT_API_KEY_TARGETS"):]
    block = block[:block.index("];")]
    check("the desktop table has no environment-variable column of its own",
          "JARVIS_" not in block, block)


def t_the_desktop_rule_is_the_backends_own_rule():
    """8 to 300 plain characters, no spaces (`jarvis_chatbot_api.key_problem`);
    the Rust copy is the same rule, so the page cannot accept a key the
    backend then refuses."""
    good = "k" * 8
    check("the backend accepts the shortest allowed key", API.key_problem(good) == "")
    check("the backend accepts the longest allowed key", API.key_problem("k" * 300) == "")
    check("the backend refuses a key that is too short", API.key_problem("k" * 7) != "")
    check("the backend refuses a key that is too long", API.key_problem("k" * 301) != "")
    check("the backend refuses a key with a space", API.key_problem("has a space") != "")
    check("the backend refuses an empty key", API.key_problem("") != "")
    check("the reason never quotes the key",
          "sk-live-nobody-should-see" not in API.key_problem("sk-live-nobody-should-see a"))
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "token_store.rs").read_text(
        encoding="utf-8")
    fn = rs[rs.index("pub fn chatbot_api_key_problem"):]
    fn = fn[:fn.index("\n}\n")]
    check("the desktop's own rule is the same 8 to 300, no spaces",
          "k.len() < 8" in fn and "k.len() > 300" in fn and "0x21..=0x7e" in fn)


# --------------------------------------------------------------------------
#   The phone is never asked for an account secret
# --------------------------------------------------------------------------

def t_neither_android_app_knows_these_commands_or_targets():
    roots = [REPO / "jarvis-client", REPO / "jarvis-android"]
    patterns = ("chatbot_api_key", "CHATBOT_API_KEY_TARGETS", "get_chatbot_api_keys",
                "Jarvis Backend/OpenAI API key", "save_chatbot_api_key")
    hits = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in (".kt", ".kts", ".java", ".xml", ".json"):
                continue
            if any(part in {"build", ".gradle", ".git"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for p in patterns:
                if p in text:
                    hits.append(f"{path.relative_to(REPO)}: {p}")
    check("neither Android app names a chatbot key target or one of the new commands",
          not hits, hits)


def t_the_new_settings_card_is_registered_where_the_tests_look():
    """A new Settings card has to be in the three registries or
    `test_settings_registry.py` fails. Checked here too so this suite's own
    failure names it (`docs/ACCOUNT-KEYS-DESIGN.md` section 9)."""
    section_id = "chatbot-api-keys"
    html = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    check("settings.html carries the card", f'id="{section_id}"' in html)
    registry = (HERE / "jarvis_settings_registry.py").read_text(encoding="utf-8")
    check("jarvis_settings_registry.py lists the section",
          f'Section("{section_id}"' in registry)
    check("the registry marks it desktop only (the phone is never asked for a key)",
          re.search(rf'Section\("{section_id}",\s*\([^)]*\),\s*app="desktop"', registry) is not None)
    menus = (HERE / "jarvis_menus.py").read_text(encoding="utf-8")
    check("jarvis_menus.py lists the menu", f'"settings.{section_id}"' in menus)
    open_place = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
                  / "client" / "ui" / "OpenPlace.kt").read_text(encoding="utf-8")
    check("OpenPlace.PC_ONLY lists it, so the phone answers \"only on your PC\"",
          f'"{section_id}"' in open_place)


if __name__ == "__main__":
    for fn in (t_the_generator_agrees_with_the_committed_fixture,
               t_every_target_is_the_python_sides_own,
               t_the_two_copies_of_the_fixture_are_identical,
               t_the_fixture_matches_the_desktop_table_by_name,
               t_the_key_never_travels_over_http_and_never_touches_a_file,
               t_the_backend_has_no_route_that_takes_a_key,
               t_no_environment_variable_is_read_for_any_chatbot_key,
               t_the_desktop_rule_is_the_backends_own_rule,
               t_neither_android_app_knows_these_commands_or_targets,
               t_the_new_settings_card_is_registered_where_the_tests_look):
        try:
            fn()
        except Exception as exc:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} RAISED {type(exc).__name__}: {exc}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
