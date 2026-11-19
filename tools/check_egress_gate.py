#!/usr/bin/env python3
"""Every path to an outbound host must name the egress gate.

    py -3 tools/check_egress_gate.py [-v]

WHAT THIS IS, IN PLAIN WORDS
Jarvis is local-first, but it is not local-only: many features reach a company's
service on the internet. Until 2026-11-16 there was no single place that decided
whether a request may leave. That place is `backend/jarvis_egress_gate.py`; a
sender asks it by calling `check_egress(...)` before it opens a socket.

WHAT IT CHECKS
Every `.py` under `backend/`, `jarvis-backend/` and `tools/` that names one of
the outbound hosts in HOSTS **in real code** is either:

  * a file whose real code also names `check_egress` - the sender has the gate
    in it; or
  * a file in ALLOWED below, with a one-line reason saying why its host name is
    not a way out of this PC that skips the gate.

WHAT COUNTS AS A MENTION: THE CODE, NOT THE TEXT (2026-11-18)
Until 2026-11-18 this walked the raw file text, so it flagged prose as well: a
new module's docstring showed `api.deepseek.com` as an example, the gate failed
`backend/test_chatbot_api.py` and the lane's fix was to DELETE the example. A
gate that trains an author to remove documentation is teaching the wrong lesson
- the honest fix is to read the program, not the writing about it - so an
external review ruled that docstrings and `#` comments must not count.

The walk is over `ast` now. A mention is one of the HOSTS named in a string
literal that is part of the code, and it is NOT counted when it is:

  * a docstring - the literal `ast.get_docstring` returns for a module, class,
    function or method; or
  * any other bare string expression statement - a literal evaluated and thrown
    away can only be documentation; and
  * a `#` comment - comments never enter the AST at all, so the walk cannot see
    them and no new way of hiding one is needed to ignore them.

Literal-only expressions are folded into the string they build: an f-string
whose substituted values are themselves literals, and a `+` chain or adjacent
literals, are one value. So a host split over two literals - adjacent, as in
`"https://api." "deepseek.com"`, or joined with `+` - is still the mention the
program ends up with. The raw-text scan could not see either; this walk is
stricter there, not looser.

The wiring half is code too: a file names the gate when the program refers to
`check_egress` as a name, as an attribute, or in an import. A docstring or a
comment saying "this asks check_egress" is not a call, but the old text check
counted it as one - `backend/test_web_search.py` was green that way.

THE LIST IS A CENSUS NOW, NOT A SIX-HOST NET (2026-11-16)
The first shape of this check named the six chatbot API hosts
(`api.openai.com` and its five neighbours). The 2026-11-16 outbound audit
measured 25 outbound paths in 24 files and
showed that a green run on six hosts means "nothing among six hosts", not
"nothing leaves": the browser chatbot sites (`chat.deepseek.com` and eight more),
the web-search providers (`api.tavily.com`, `api.exa.ai`,
`api.search.brave.com`), `api.github.com`, Google's calendar hosts,
`api.open-meteo.com`, `pypi.org`, `crates.io`, `huggingface.co` and the map
services were all invisible. HOSTS is now that census.

WHY AN UNLISTED HIT IS A FAILURE, NOT A WARNING
This program's whole promise is that nothing leaves unless something decided it
could. A warning is a line a fast reader scrolls past; a new sender that does
not ask the gate would then arrive silently, ship, and look exactly like every
green run before it. So a new host name with no gate and no entry here fails the
run, with the file and line printed, and the fix is deliberate - wire the gate,
or add an entry with the reason the name cannot send anything.

WHAT IT CANNOT DECIDE, SAID OUT LOUD
This is a SYNTAX check. It proves `check_egress` is referred to in code in the
same file as the host; it cannot prove every branch calls it, and it cannot see
a host built at runtime. HOSTS is also a closed census of the outbound hosts
the audit found, not a promise to recognise every address in the world: a host
that is not in HOSTS is not a mention here until a person adds it, which is how
the 2026-11-16 audit grew the list from six to the census below. The audit's
own list of what it could not see is still true: the HUD relays to an address it
is handed at runtime (no host literal), the mail sender and the mail reader take
an SMTP/IMAP host from settings, `jarvis_home.py` takes a base URL from
settings, an f-string may interpolate the name, and DuckDuckGo goes through the
`ddgs` package's own sockets - none of those spell a host this file can search
for. The suites that drive the wired senders prove the call actually refuses and
actually allows; this file's job is to keep the list of names complete and
deliberate.

WHY THE ALLOW-LIST IS THIS SHAPE
Each key is the exact repository path, never a glob, and each value is one
line. A new hit has to be added by a person who wrote down why. The list is
checked both ways: an entry whose file has gone, or which no longer names a
host in code, is reported too, so the reasons cannot quietly stop being true -
that is why the 2026-11-18 walk removed every entry whose host name lived only
in a comment or a docstring: prose is not a mention, so those entries no longer
described a hit (their files still open no socket; they are simply not in the
census).

One derived entry, stated rather than hidden: a shipped module has two copies,
`backend/<name>.py` and its byte-identical `jarvis-backend/<name>.py` base. The
list names the `backend/` one, and the base's copy shares that reason only
while the two files are byte-identical - measured here, not assumed - because
then it names exactly the same hosts. A copy that has drifted gets no entry and
is reported like any other file.
"""
from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOTS = ("backend", "jarvis-backend", "tools")

#: Every outbound host the audit found, grouped by what it is. The first six
#: are the chatbot API services (`docs/ARCHITECTURE.md` section 4's list). The
#: rest are the browser chatbot sites, their shared sign-in host, the web-search
#: providers, GitHub, Google's calendar and sign-in APIs, and the public
#: services the readers use.
HOSTS = (
    # the six chatbot API services
    "api.openai.com",
    "api.deepseek.com",
    "api.mistral.ai",
    "openrouter.ai",
    "api.groq.com",
    "api.x.ai",
    # the nine browser chatbot sites (jarvis_chatbot_<site>.py) and the sign-in
    # page their site files name
    "chat.deepseek.com",
    "chatgpt.com",
    "claude.ai",
    "copilot.microsoft.com",
    "gemini.google.com",
    "grok.com",
    "chat.mistral.ai",
    "www.meta.ai",
    "www.perplexity.ai",
    "accounts.google.com",
    # the keyed web-search providers (jarvis_search.py)
    "api.tavily.com",
    "api.exa.ai",
    "api.search.brave.com",
    # GitHub reads, account checks, research and watching (one API host)
    "api.github.com",
    # Google Calendar: the API, the OAuth token endpoint, and the calendar feeds
    "www.googleapis.com",
    "oauth2.googleapis.com",
    "calendar.google.com",
    # the public services the readers and checkers use
    "api.open-meteo.com",
    "pypi.org",
    "crates.io",
    "huggingface.co",
    "services.arcgis.com",
    "overpass-api.de",
    "nominatim.openstreetmap.org",
    "www.youtube.com",
    "www.google.com",
)

#: What a wired sender names. Kept as one constant so this file and its own
#: docstring use the same spelling.
GATE = "check_egress"

#: path -> one-line reason its host name is not a way out that skips the gate.
#: Every entry is an EXACT path. A suite is listed because its host strings are
#: fixtures and its transport is replaced; a production sender the audit found
#: is listed only with the honest reason that it is not wired yet.
ALLOWED = {
    # A SUITE, not a sender (2026-11-17). test_speed_record.py builds a fake
    # usage record in order to price one answer: the host and url are fixture
    # STRINGS that are never opened, and the request itself is stubbed. #1337
    # added them after this census landed, which is why main went red.
    "backend/test_speed_record.py":
        "a suite; its host and URL are fixture strings on a fake usage record, and no "
        "socket is opened",
    # ------------------------------------------------------------------
    # Production senders the audit found and this round did NOT wire.
    # Each waits for the lane that owns it, and says so plainly: a "not
    # wired yet" reason is the one kind of allow-list entry that can never
    # be mistaken for "this file is harmless".
    # ------------------------------------------------------------------
    "backend/jarvis_calendar.py":
        "the calendar reader (CalDAV and ICS feeds, a https address from settings)"
        " - NOT wired by this round; listed for the next egress lane",
    "backend/jarvis_connect_account.py":
        "the account-connection sender (its GitHub user check carries the token) -"
        " rule 1 territory, NOT wired by this round; for the credentials lane",
    "backend/jarvis_github.py":
        "the GitHub sender: every request carries the saved token - rule 1 territory,"
        " NOT wired by this round; listed for the credentials lane",
    "backend/jarvis_google_calendar.py":
        "the Google Calendar sender (OAuth token and the owner's calendar data) -"
        " rule 1 territory, NOT wired by this round",
    "backend/jarvis_hf_inspect.py":
        "the Hugging Face listing reader - NOT wired by this round; listed for the"
        " next egress lane",
    "backend/jarvis_parking.py":
        "the parking reader (three map services) - NOT wired by this round; listed"
        " for the next egress lane",
    "backend/jarvis_price_radar.py":
        "the price radar, whose one request is Google's flights page - NOT wired by"
        " this round; listed for the next egress lane",
    "backend/jarvis_price_sources.py":
        "the price-page reader - NOT wired by this round; listed for the next egress"
        " lane",
    "backend/jarvis_quick.py":
        "the update check lives in jarvis_quick.py, which this round must not edit -"
        " NOT wired; listed for the lane that owns that file",
    "backend/jarvis_research.py":
        "the research reader (GitHub's API) - NOT wired by this round; listed for"
        " the next egress lane",
    "backend/jarvis_sky.py":
        "the weather reader (open-meteo) - NOT wired by this round; listed for the"
        " next egress lane",
    "backend/jarvis_tellme.py":
        "the mail and page watcher (a hand-written IMAP socket and page reads) - rule"
        " 1 territory, NOT wired by this round",
    "backend/jarvis_tool_updates.py":
        "the update checker (PyPI, crates.io and GitHub releases) - NOT wired by this"
        " round; listed for the next egress lane",
    "backend/jarvis_watch.py":
        "the repo/CI watcher (GitHub's API) - NOT wired by this round; listed for the"
        " next egress lane",
    "jarvis-backend/jarvis_models.py":
        "the published base's model catalogue reader (Hugging Face and Ollama"
        " listings) - a base file this round must not edit, and NOT wired",
    "jarvis-backend/jarvis_gate.py":
        "the published base's gate module: the host is in one action's description,"
        " and its own request is the owner's ntfy push to a server in settings -"
        " NOT wired by this round",

    # ------------------------------------------------------------------
    # Production files that name a host but open no socket at all. The
    # claim is about THIS file only, which is what the check measures.
    # ------------------------------------------------------------------
    "backend/grade-peers.py":
        "a desk-side script: the host is in the line it prints telling the owner"
        " to fetch it on another machine; it opens no socket",
    "backend/import_history.py":
        "an import tool: the host is in a comment and in the --claude help text,"
        " and it opens no socket",
    "backend/jarvis_asks_first.py":
        "names the host in the switch descriptions it shows the owner; it opens no"
        " socket",
    "backend/jarvis_browser_control.py":
        "names the host in its list of sign-in pages; it opens no socket",
    "backend/jarvis_chatbot.py":
        "the driver lists the sites in its adapter TABLE rows; every website send"
        " goes through jarvis_chatbot_web.py, which asks the gate",
    "backend/jarvis_chatbot_chatgpt.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_claude.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_copilot.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_deepseek.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_gemini.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_grok.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_lechat.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_chatbot_metaai.py":
        "a thin site file: it names the site's own address; the shared adapter in"
        " jarvis_chatbot_web.py asks the gate, and this file opens no socket",
    "backend/jarvis_chatbot_perplexity.py":
        "a thin site file: it names the site's own address and the sign-in host; the"
        " shared adapter in jarvis_chatbot_web.py asks the gate, and this file opens"
        " no socket",
    "backend/jarvis_feature_catalogue.py":
        "names the host in the feature card text it shows; it opens no socket",
    "backend/jarvis_feature_guide.py":
        "names the host in the guide text it shows; it opens no socket",
    "backend/jarvis_model_recommendations.py":
        "builds and compares the public listing addresses in code; its own fetch"
        " happens in jarvis_hf_inspect.py, not here, so it opens no socket",
    "backend/jarvis_reach.py":
        "the reach register: the hosts are row data in a table of what can be"
        " reached; it opens no socket",
    "backend/jarvis_tool_profiles.py":
        "names the host in the card text it shows the owner; it opens no socket",
    "backend/jarvis_youtube.py":
        "builds and checks YouTube watch addresses; it opens no socket (the page"
        " itself is read by jarvis_readpage)",

    # ------------------------------------------------------------------
    # Suites. A suite is not a sender Jarvis runs; the host is fixture
    # data, an expected value, or a URL whose transport is replaced.
    # ------------------------------------------------------------------
    "backend/test_account_addresses.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_account_secrets.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_briefing.py":
        "a suite; the host is fixture data and its socket guard refuses every"
        " connection",
    "backend/test_calendar.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_calendar_answer.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_calendar_link.py":
        "a suite; the hosts are fixture data and this file opens no socket",
    "backend/test_chatbot.py":
        "a suite; the host is a driver-table fixture row, and its socket guard"
        " refuses every connection",
    "backend/test_chatbot_gemini.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_cloud_honesty_state.py":
        "a suite; the host is an expected value in an assertion on the driver's words",
    "backend/test_cloud_spend.py":
        "a suite; the host is in a fixture row whose transport is replaced",
    "backend/test_connect_account.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_connect_account_chat.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_egress_gate_checker.py":
        "this checker's own suite: the hosts are fixture source it writes into a"
        " temporary tree, and it opens no socket",
    "backend/test_focus.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_front.py":
        "a suite; the host is an expected value in an assertion, and this file"
        " opens no socket",
    "backend/test_github_authoring.py":
        "a suite; the host is fixture data and its socket guard refuses every"
        " connection",
    "backend/test_github_ci_count.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_github_parity.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_github_robustness.py":
        "a suite; the host is fixture data and every request goes through a replaced"
        " fetch function",
    "backend/test_github_tools.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_google_calendar.py":
        "a suite; the host is an expected value and every request goes to a fake"
        " server on 127.0.0.1",
    "backend/test_handoff.py":
        "a suite; the hosts are fixture data and this file opens no socket",
    "backend/test_handoff_mode.py":
        "a suite; the hosts are fixture data and this file opens no socket",
    "backend/test_hf_inspect.py":
        "a suite; the host is an expected value and the fetch function is replaced",
    "backend/test_mail_mask.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_model_recommendations.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_ollama_direct.py":
        "a suite; the host is the refused URL it checks is never the one sent",
    "backend/test_optin_models.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_options_understanding.py":
        "a suite; hosts are preset fixtures and expected copy",
    "backend/test_presets_cloud.py":
        "a suite; the host is in the card text it asserts",
    "backend/test_presets_owner_ui.py":
        "a suite; the host is in a preset fixture row",
    "backend/test_price_radar.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_price_sources.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_reach.py":
        "a suite; the hosts are reach-register and site fixture rows",
    "backend/test_read_link.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_reasoning_fallback.py":
        "a suite; the host is in a fake cloud request row whose transport is replaced",
    "backend/test_research.py":
        "a suite; the host is an expected value and its opener is replaced",
    "backend/test_security_pc.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_sky.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_tellme_price_radar.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_tellme_watches.py":
        "a suite; the host is in a request object that is never opened (a"
        " redirect-refusal test)",
    "backend/test_tool_updates.py":
        "a suite; the hosts are expected values and this file opens no socket",
    "backend/test_vault.py":
        "a suite; the hosts are expected handles and its own banned-call list refuses"
        " sockets",
    "backend/test_watch_repos.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_web_search.py":
        "a suite; the hosts are fixture and expected values in its fake-transport"
        " rows, and the real send for every one of them is jarvis_search.py, which"
        " asks the gate before the key is resolved",
    "backend/test_youtube.py":
        "a suite; the host is an expected value and its own banned-call list refuses"
        " sockets",

    # ------------------------------------------------------------------
    # Desk-side tools. They run at a desk, not on the owner's PC as part of
    # Jarvis; the ones that do send read public release data.
    # ------------------------------------------------------------------
    "tools/check_egress_gate.py":
        "this checker itself: it names the outbound hosts only in order to search"
        " for them",
    "tools/check_field_test_binaries.py":
        "a desk-side checker: it reads a release list over GitHub's API for a binary"
        " inventory, and is not part of the app",
    "tools/check_python_advisories.py":
        "a desk-side checker: it reads PyPI's advisory data, and is not part of the"
        " app",
    "tools/check_readme_truth.py":
        "a desk-side doc checker: the address is in a sentence it checks for, not in"
        " a request",
    "tools/gen_chatbot_cases.py":
        "generates recorded chatbot cases; the hosts are fixture data and it opens"
        " no socket",
    "tools/gen_handoff_cases.py":
        "generates recorded handoff cases; the hosts are fixture data and it opens"
        " no socket",
    "tools/gen_notices.py":
        "a desk-side generator: it reads release data from PyPI and crates.io to"
        " build the notices file, and is not part of the app",
    "tools/gen_quiz_cloud_cases.py":
        "generates the recorded quiz-cloud cases; its host fields are fixture data"
        " and it opens no socket",
    "tools/gen_reach_cases.py":
        "generates the reach register's fixture rows; it opens no socket",
    "tools/gen_youtube_cases.py":
        "generates recorded YouTube cases; the host is fixture data and it opens no"
        " socket",
    "tools/smoke_airgap_boot.py":
        "a desk-side smoke script: it fetches a release list to prove the app boots"
        " airgapped, and is not part of the app",
    "tools/test_smoke_airgap_boot.py":
        "a suite for the desk-side smoke script; the host is fixture data",
}

SKIP_DIRS = {"__pycache__", ".git"}


def python_files(root: Path) -> list[Path]:
    """Every .py file under the three roots of `root`, sorted, no build residue."""
    out: list[Path] = []
    for name in ROOTS:
        for path in sorted((root / name).rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            out.append(path)
    return out


# ---------------------------------------------------------------------------
# What counts as a mention: the code, not the text (2026-11-18).
# ---------------------------------------------------------------------------

def _documentation_ids(tree: ast.AST) -> set[int]:
    """ids of the string literals that are documentation, not code.

    Two shapes. `ast.get_docstring` names the first: the literal at the top of a
    module, class or function. The second is any other bare string expression
    statement - a literal evaluated and its value thrown away can only be
    documentation (`ast.get_docstring` does not call a section string further
    down a long function a docstring, but it is just as much writing rather than
    code).
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", ())
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and ast.get_docstring(node) is not None):
                ids.add(id(body[0].value))
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            ids.add(id(node.value))
    return ids


def _literal_value(node: ast.AST) -> str | None:
    """The string a literal-only expression builds, or None if it needs a name.

    Folding these is what lets the walk see a host the raw-text scan could not:
    `"https://api." "deepseek.com"` (the parser joins adjacent literals),
    `"https://api." + "deepseek.com"` (a `+` chain of literals) and an f-string
    whose substituted values are themselves literals all name the host the
    program ends up with. An f-string that interpolates a real variable returns
    None here - its literal parts are still visited on their own, which catches
    a host spelled contiguously there.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                inner = _literal_value(value.value)
                if inner is None:
                    return None
                parts.append(inner)
            else:
                return None
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_value(node.left)
        right = _literal_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _hosts_in(value: str) -> list[str]:
    """Every HOSTS entry named by `value`, in census order."""
    low = value.lower()
    return [host for host in HOSTS if host in low]


def code_host_mentions(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, host) for every HOSTS host named in real CODE in `tree`.

    Documentation is skipped: a docstring or any other bare string statement is
    not code, and `#` comments never reach the AST at all, so no comment
    stripping is needed. `ast.get_docstring` is the authority for the first
    kind; `_documentation_ids` also knows the bare-string kind.
    """
    documentation = _documentation_ids(tree)
    seen: set[tuple[int, str]] = set()
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if id(node) in documentation:
            continue
        value = _literal_value(node)
        if value is None:
            continue
        for host in _hosts_in(value):
            hit = (node.lineno, host)
            if hit not in seen:
                seen.add(hit)
                out.append(hit)
    return out


def _comment_tokens(text: str) -> list[tokenize.TokenInfo]:
    """Every `#` comment token, or none where the file's tokenizer gives up.

    Only used to count what the walk ignored; a tokenizer that cannot read the
    file changes nothing about the verdict (the AST parse is what decides, and
    `main` rejects a file the AST cannot read before this is reached).
    """
    try:
        return [tok for tok in tokenize.generate_tokens(io.StringIO(text).readline)
                if tok.type == tokenize.COMMENT]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []


def documentation_host_mentions(tree: ast.AST, text: str) -> list[tuple[int, str]]:
    """(line, host) for the host names the walk ignored as documentation.

    These are the mentions the 2026-11-18 ruling took out of the census: the
    same host named in a docstring, in another bare string statement, or in a
    `#` comment. They are counted and printed, never used to pass or fail.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            out.extend((node.value.lineno, host)
                       for host in _hosts_in(node.value.value))
    for tok in _comment_tokens(text):
        out.extend((tok.start[0], host) for host in _hosts_in(tok.string))
    return out


def code_names_gate(tree: ast.AST) -> bool:
    """True when real CODE refers to the gate - a docstring or comment is not it.

    Names, attributes and imports count; a string that merely spells the word is
    not a call, so it does not. `backend/test_web_search.py` used to pass this
    half on its own docstring, which said the gate is asked; the suite asks
    nothing itself, so it is now on the allow-list for the reason that IS true.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == GATE:
            return True
        if isinstance(node, ast.Attribute) and node.attr == GATE:
            return True
        if isinstance(node, ast.alias):
            if GATE in (getattr(node, "name", "") or "",
                        getattr(node, "asname", "") or ""):
                return True
    return False


def _allowed_reason(rel: str, path: Path, root: Path,
                    allowed: dict[str, str]) -> str:
    """The written reason for `rel`, or "".

    A shipped module has two copies: `backend/<name>.py` and its base,
    `jarvis-backend/<name>.py`. The list names the `backend/` one, and the
    base's copy shares that reason only while the two files are byte-identical
    (measured here, not assumed): then it names exactly the same hosts. A copy
    that has drifted - `backend/_where.py` carries the base's trailer - needs
    its own entry, so a drifted copy cannot inherit a reason it may not deserve.
    """
    if rel in allowed:
        return allowed[rel]
    if rel.startswith("jarvis-backend/"):
        twin = "backend/" + rel[len("jarvis-backend/"):]
        if twin in allowed:
            try:
                if path.read_bytes() == (root / twin).read_bytes():
                    return allowed[twin]
            except OSError:
                return ""
    return ""


def main(argv: list[str] | None = None, repo: Path | None = None,
         allowed: dict[str, str] | None = None, say=print) -> int:
    """Run the walk and return the exit code; arguments exist for the suite.

    `argv`, `repo` and `allowed` default to the real ones, so the command line
    behaviour is unchanged. The suite passes a fixture tree and a fixture
    allow-list so every rule can be proved on text it wrote, not on the repo's
    own files, and then runs the default form on this checkout.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    verbose = "-v" in args
    root = REPO if repo is None else Path(repo)
    allow = ALLOWED if allowed is None else allowed
    seen_allowed: set[str] = set()
    wired: list[str] = []
    allowlisted: list[str] = []
    violations: list[tuple[str, int, str]] = []
    problems: list[str] = []
    real_mentions = 0
    prose_mentions = 0

    for path in python_files(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as exc:
            problems.append(f"{rel} is not valid Python ({exc.msg} at line "
                            f"{exc.lineno}), so its host mentions cannot be "
                            f"read - fix the file")
            continue
        hits = code_host_mentions(tree)
        prose_mentions += len(documentation_host_mentions(tree, text))
        if not hits:
            continue
        real_mentions += len(hits)
        reason = _allowed_reason(rel, path, root, allow)
        if reason:
            allowlisted.append(rel)
            if rel in allow:
                seen_allowed.add(rel)
            continue
        if code_names_gate(tree):
            wired.append(rel)
            continue
        violations.extend((rel, line, host) for line, host in hits)

    for rel in allow:
        if not (root / rel).is_file():
            problems.append(f"{rel} is on the allow-list but is not in this checkout "
                            f"- remove the entry or restore the file")
        elif rel not in seen_allowed:
            problems.append(f"{rel} is on the allow-list but no longer names a "
                            f"cloud host in code - remove the entry, it is no "
                            f"longer true")

    if violations:
        say("::error::an outbound host is named in real code by a file that "
            f"does not name {GATE} in code - wire the gate or add the file to "
            "ALLOWED with a reason:",)
        for rel, line, host in violations:
            say(f"  {rel}:{line}: {host}")
    for problem in problems:
        say(f"::error::{problem}")

    if violations or problems:
        say(f"\nFAIL  {len(violations)} unaccounted host mention(s), "
            f"{len(problems)} stale allow-list entr(ies).")
        return 1

    say(f"{len(wired) + len(allowlisted)} file(s) name one of the {len(HOSTS)} "
        f"outbound hosts in real code: {len(wired)} name {GATE} in code, "
        f"{len(allowlisted)} are on the allow-list with a reason.")
    say(f"The allow-list is {len(allow)} exact path(s), each of which also covers "
        f"its byte-identical base copy; an unlisted host name would fail this run.")
    say(f"The walk counted {real_mentions} host mention(s) in real code and "
        f"ignored {prose_mentions} that are documentation only - a docstring, "
        f"another bare string statement, or a # comment - which the old text "
        f"scan used to count.")
    if verbose:
        for rel in sorted(allowlisted):
            say(f"  allowed  {rel}")
            say(f"           {allow.get(rel) or _allowed_reason(rel, root / rel, root, allow)}")
        for rel in sorted(wired):
            say(f"  wired    {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
