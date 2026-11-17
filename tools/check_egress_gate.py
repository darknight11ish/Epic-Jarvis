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
the outbound hosts in HOSTS is either:

  * a file that also names `check_egress` in the same file - the sender has the
    gate in it; or
  * a file in ALLOWED below, with a one-line reason saying why its host name is
    not a way out of this PC that skips the gate.

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
This is a TEXT check. It proves `check_egress` is named in the same file as the
host; it cannot prove every branch calls it, and it cannot see a host built at
runtime. The audit's own list of what it could not see is still true here: the
HUD relays to an address it is handed at runtime (no host literal), the mail
sender and the mail reader take an SMTP/IMAP host from settings, `jarvis_home.py`
takes a base URL from settings, and DuckDuckGo goes through the `ddgs` package's
own sockets - none of those spell a host this file can search for. The suites
that drive the wired senders prove the call actually refuses and actually
allows; this file's job is to keep the list of names complete and deliberate.

WHY THE ALLOW-LIST IS THIS SHAPE
Each key is the exact repository path, never a glob, and each value is one
line. A new hit has to be added by a person who wrote down why. The list is
checked both ways: an entry whose file has gone, or which no longer names a
host, is reported too, so the reasons cannot quietly stop being true.

One derived entry, stated rather than hidden: a shipped module has two copies,
`backend/<name>.py` and its byte-identical `jarvis-backend/<name>.py` base. The
list names the `backend/` one, and the base's copy shares that reason only
while the two files are byte-identical - measured here, not assumed - because
then it names exactly the same hosts. A copy that has drifted gets no entry and
is reported like any other file.
"""
from __future__ import annotations

import sys
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
    "backend/_where.py":
        "the shipped-module list: both hosts are in comments about where a module"
        " came from, and this file opens no socket",
    "backend/grade-peers.py":
        "a desk-side script: the host is in its own explanation of what it refuses,"
        " and it opens no socket",
    "backend/import_history.py":
        "an import tool: the host is in a comment about the export it was tested"
        " against, and it opens no socket",
    "backend/jarvis_agent.py":
        "names the host in tool descriptions; its own request goes to this PC's local"
        " HTTP service",
    "backend/jarvis_asks_first.py":
        "names the host in the switch descriptions it shows the owner; it opens no"
        " socket",
    "backend/jarvis_browser_control.py":
        "names the host in its list of sign-in pages; it opens no socket",
    "backend/jarvis_chatbot.py":
        "the driver names the sites in its adapter notes; every website send goes"
        " through jarvis_chatbot_web.py, which asks the gate",
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
    "backend/jarvis_front.py":
        "names the host in a comment about how host names are compared; it opens no"
        " socket",
    "backend/jarvis_mail_mask.py":
        "names the sign-in host in its link-masking rules; it opens no socket",
    "backend/jarvis_model_recommendations.py":
        "names the public listing addresses in its docstring; the fetch happens in"
        " jarvis_hf_inspect.py, not here",
    "backend/jarvis_reach.py":
        "the reach register: the hosts are row data in a table of what can be"
        " reached; it opens no socket",
    "backend/jarvis_scrub.py":
        "names the host in the example address its scrubber hides; it opens no socket",
    "backend/jarvis_second_card.py":
        "names the host in a comment; its own sockets go to Ollama on this PC",
    "backend/jarvis_tool_profiles.py":
        "names the host in a comment about a read; it opens no socket",
    "backend/jarvis_vault.py":
        "names the host in the docstring's example request; it opens no socket",
    "backend/jarvis_youtube.py":
        "builds and checks YouTube watch addresses; it opens no socket (the page"
        " itself is read by jarvis_readpage)",
    "backend/rebuilt/jarvis_framework.py":
        "names the host in a comment about what a package is not; it opens no socket",
    "jarvis-backend/jarvis_framework.py":
        "the base's copy of the rebuilt framework: the host is in the same comment,"
        " and this file opens no socket",
    "jarvis-backend/_where.py":
        "the base's copy of the shipped-module list: both hosts are in comments, and"
        " this file opens no socket (it carries the base trailer, so it is not"
        " byte-identical to backend/_where.py)",

    # ------------------------------------------------------------------
    # Suites. A suite is not a sender Jarvis runs; the host is fixture
    # data, an expected value, or a URL whose transport is replaced.
    # ------------------------------------------------------------------
    "backend/test_account_addresses.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_account_secrets.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_agent.py":
        "a suite; the hosts are in comments and fixture rows, and this file opens no"
        " socket",
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
        "a suite; the host is in the driver's adapter notes, and its socket guard"
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
    "backend/test_focus.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_front.py":
        "a suite; the host is in a docstring/comment, and this file opens no socket",
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
    "backend/test_quick_wins.py":
        "a suite; the host is fixture data and its socket guard refuses every"
        " connection",
    "backend/test_reach.py":
        "a suite; the hosts are reach-register and site fixture rows",
    "backend/test_read_link.py":
        "a suite; the host is fixture data and this file opens no socket",
    "backend/test_reasoning_fallback.py":
        "a suite; the host is in a fake cloud request row whose transport is replaced",
    "backend/test_research.py":
        "a suite; the host is an expected value and its opener is replaced",
    "backend/test_runtime_identity.py":
        "a suite; the host appears in a comment about the cloud preset",
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


def python_files() -> list[Path]:
    """Every .py file under the three roots, sorted, with no build residue."""
    out: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            out.append(path)
    return out


def host_lines(text: str) -> list[tuple[int, str]]:
    """(line number, host) for every line that names one of the outbound hosts."""
    out: list[tuple[int, str]] = []
    low = text.lower()
    for host in HOSTS:
        start = 0
        while True:
            at = low.find(host, start)
            if at < 0:
                break
            out.append((low[:at].count("\n") + 1, host))
            start = at + len(host)
    return out


def _allowed_reason(rel: str, path: Path) -> str:
    """The written reason for `rel`, or "".

    A shipped module has two copies: `backend/<name>.py` and its base,
    `jarvis-backend/<name>.py`. The list names the `backend/` one, and the
    base's copy shares that reason only while the two files are byte-identical
    (measured here, not assumed): then it names exactly the same hosts. A copy
    that has drifted - `backend/_where.py` carries the base's trailer - needs
    its own entry, so a drifted copy cannot inherit a reason it may not deserve.
    """
    if rel in ALLOWED:
        return ALLOWED[rel]
    if rel.startswith("jarvis-backend/"):
        twin = "backend/" + rel[len("jarvis-backend/"):]
        if twin in ALLOWED:
            try:
                if path.read_bytes() == (REPO / twin).read_bytes():
                    return ALLOWED[twin]
            except OSError:
                return ""
    return ""


def main() -> int:
    verbose = "-v" in sys.argv
    seen_allowed: set[str] = set()
    wired: list[str] = []
    allowed: list[str] = []
    violations: list[tuple[str, int, str]] = []

    for path in python_files():
        rel = path.relative_to(REPO).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = host_lines(text)
        if not hits:
            continue
        reason = _allowed_reason(rel, path)
        if reason:
            allowed.append(rel)
            if rel in ALLOWED:
                seen_allowed.add(rel)
            continue
        if GATE in text:
            wired.append(rel)
            continue
        violations.extend((rel, line, host) for line, host in hits)

    problems: list[str] = []
    for rel in ALLOWED:
        if not (REPO / rel).is_file():
            problems.append(f"{rel} is on the allow-list but is not in this checkout "
                            f"- remove the entry or restore the file")
        elif rel not in seen_allowed:
            problems.append(f"{rel} is on the allow-list but no longer names a cloud host "
                            f"- remove the entry, it is no longer true")

    if violations:
        print("::error::an outbound host is named by a file that does not name "
              f"{GATE} - wire the gate or add the file to ALLOWED with a reason:",)
        for rel, line, host in violations:
            print(f"  {rel}:{line}: {host}")
    for problem in problems:
        print(f"::error::{problem}")

    if violations or problems:
        print(f"\nFAIL  {len(violations)} unaccounted host mention(s), "
              f"{len(problems)} stale allow-list entr(ies).")
        return 1

    print(f"{len(wired) + len(allowed)} file(s) name one of the {len(HOSTS)} outbound "
          f"hosts: {len(wired)} name {GATE}, {len(allowed)} are on the allow-list "
          f"with a reason.")
    print(f"The allow-list is {len(ALLOWED)} exact path(s), each of which also covers "
          f"its byte-identical base copy; an unlisted host name would fail this run.")
    if verbose:
        for rel in sorted(allowed):
            print(f"  allowed  {rel}")
            print(f"           {ALLOWED.get(rel) or _allowed_reason(rel, REPO / rel)}")
        for rel in sorted(wired):
            print(f"  wired    {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
