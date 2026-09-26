"""jarvis_reach.py - "What can Jarvis reach right now?", written by CODE from
the PC's real settings, never by the AI model.

NEW MODULE, shipped whole. reach.patch adds `GET /api/reach` (both apps
show its list: the desktop in Settings, "What Jarvis can reach"; the phone
on Mind), and jarvis_quick.py answers "what can you reach?" / "what can
Jarvis access?" from sentence() below, without the model.

WHY (the Muse audit, docs/COMPETITORS-MUSE-2026-09-25.md, idea 1)
Meta's Muse described its own access wrongly, and its settings screen
disagreed with the user's choice. A model can say anything about itself;
this list cannot, because nothing in it is written by a model. Every line
is built here from the same settings the rest of Jarvis reads:
  * which tools the model is offered: `[tools].enabled` in
    jarvis-framework.toml, through jarvis_agent.offered_tools() - the list
    the chat's tool loop uses (read the way jarvis_briefing.py reads it);
  * whether each tool asks first: its gate action (jarvis_gate's own table
    when it is there, else the same names backend/README.md lists) and that
    action's tier in [autonomy.tiers]; the tools jarvis_agent.py only
    ever runs on a person's yes (NEEDS_A_PERSON) say "every time" whatever
    the tier;
  * which accounts are set up: the same environment variables each module
    reads (JARVIS_IMAP_HOST, JARVIS_CALDAV_URL, JARVIS_HOME_URL, ...);
  * web search: jarvis_search.settings() and whether a key is SAVED;
  * the cloud lanes: the chat route's own `_lane_names()` when this runs
    inside the server, else the same file it reads (litellm-proxy.yaml);
  * the second card and the big model: their switch files (read only -
    nothing is started, woken or probed).

WHAT IT NEVER SHOWS
No password, key, token, private calendar link, ntfy topic or full address.
"Where it goes" is a HOST name only ("imap.example.com", "calendar.google.com",
"this PC"). Whether a key is saved is yes or no. test_reach.py builds fake
secrets and checks none of them reaches the list, the sentence or the route.

IT READS, AND ONLY READS
No socket, no file written, no switch changed, nothing woken. Never raises:
a part that cannot be read says so on its own line.

ADDING A WAY OUT
One entry in KINDS below: an id and a function that returns one row. (The
email-sending row is `_email_send`.)

    python3 test_reach.py
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

PATH = "/api/reach"

#: The words both apps show above the list.
TITLE = "What Jarvis can reach"
DETAIL = ("Every way Jarvis can reach something outside itself, and whether each one is "
          "on right now. The PC writes this list from its own settings - the AI model does "
          "not write it, so it cannot be talked into saying something else. Passwords, keys "
          "and private links are never shown.")
MISSING = ("Your PC's Jarvis cannot list what it can reach yet - run apply-patches.ps1 on "
           "the PC.")
WHERE_LABEL = "Goes to"
ASKS_LABEL = "Asks you first"
TOOLS_TITLE = "Tools the AI model is offered"
TOOLS_NONE = "None: the AI model is offered no tools, so it can only write answers."
EVERYTHING_ELSE = "Anything not on this list stays on this PC."

#: How each state is shown.
STATE_WORDS = {
    "on": "On",
    "off": "Off",
    "not_set_up": "Not set up",
    "blocked": "Blocked by your settings",
}

ASK_EVERY = "Yes, every time"
ASK_NO = "No"
ASK_TOLD = "No - you are told afterwards"
ASK_NEVER = "Never allowed (your settings say never)"
ASK_NA = "-"

#: The tools, in plain words (jarvis_agent.TOOLS' names).
TOOL_NAMES = {
    "calculator": "Calculator",
    "memory_search": "Searching what it has learned about you",
    "file_read": "Reading files on this PC",
    "shell_exec": "Running commands on this PC",
    "control_computer": "Computer control",
    "control_phone": "Phone control",
    "browser_control": "Browser control",
    "github_search": "GitHub research",
    "web_search": "Web search",
    "send_email": "Send an email (one card each)",
    "calendar_read": "Reading your calendar",
    "email_check": "Reading your email",
    "notes_search": "Searching your notes",
    "my_files": "Finding and reading files in the folders you listed",
    "home_read": "Reading Home Assistant",
    "home_control": "Changing things in Home Assistant",
    "append_logseq_journal": "Adding to your Logseq journal",
    "append_obsidian_daily": "Adding to your Obsidian daily note",
    "create_joplin_note": "Making a Joplin note",
    "set_timer": "Timers",
    "set_reminder": "Reminders",
    "todo_add": "Adding to the to-do list",
    "todo_done": "Ticking off the to-do list",
    "coming_up": "Coming up (timers, alarms, reminders)",
}

#: A tool's gate lookup name -> the action it is decided under, as
#: backend/README.md lists it - used only when jarvis_gate (on the PC) cannot
#: be asked. jarvis_gate's own table wins when it is there.
_FALLBACK_ACTIONS = {
    "jarvis_ui_control_run": "control_computer",
    "jarvis_android_control_run": "control_phone",
    "jarvis_browser_control_run": "control_browser",
    "jarvis_research_run": "web_research",
    "jarvis_research_run_authenticated": "research_authenticated",
    "jarvis_calendar_read_run": "calendar_read",
    "jarvis_email_read_run": "email_read",
    "jarvis_notes_search_run": "notes_search",
    "jarvis_home_read_run": "home_read",
    "jarvis_home_control_run": "home_control",
    "shell_exec": "run_shell_on_host",
    "file_read": "read_files_readonly",
}

#: Tools jarvis_agent.py runs only on a person's yes, if it cannot be read.
_NEEDS_A_PERSON = frozenset({"github_search", "browser_control", "control_computer",
                             "control_phone", "shell_exec", "home_control",
                             "send_email"})
_NOTE_WRITES = frozenset({"append_logseq_journal", "append_obsidian_daily",
                          "create_joplin_note"})

# --------------------------------------------------------------------------
#   What is read, replaceable for the tests
# --------------------------------------------------------------------------


def _fw():
    try:
        import jarvis_framework as fw
        return fw
    except Exception:
        return None


def _tools_enabled() -> set:
    fw = _fw()
    try:
        cfg = fw.load_framework() if fw is not None else {}
        return set((cfg.get("tools") or {}).get("enabled") or [])
    except Exception:
        return set()


def _tier(action: str) -> str:
    fw = _fw()
    try:
        return str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"


def _env(name: str) -> str:
    return str(os.environ.get(name, "") or "").strip()


def _server_lanes() -> Optional[list]:
    """The chat route's own `_lane_names()`, when this runs inside the
    server (jarvis_hud.py); None otherwise."""
    for name in ("jarvis_hud", "__main__"):
        mod = sys.modules.get(name)
        fn = getattr(mod, "_lane_names", None) if mod is not None else None
        if callable(fn):
            try:
                return [str(x) for x in (fn() or [])]
            except Exception:
                return None
    return None


def _proxy_file() -> Optional[Path]:
    fw = _fw()
    try:
        base = Path(fw.CONFIG_DIR) if fw is not None else Path.home() / ".openjarvis"
    except Exception:
        return None
    return base / "litellm-proxy.yaml"


def _file_lanes(path: Optional[Path]) -> tuple:
    """([lane names], [providers]) from litellm-proxy.yaml, read as plain
    lines (no YAML library): `model_name:` lines, and the provider part of
    `model: provider/...` lines. ([], []) when there is no file."""
    if path is None or not path.is_file():
        return [], []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    names = re.findall(r"^\s*-?\s*model_name\s*:\s*[\"']?([^\"'#\s]+)", text, re.M)
    provs = re.findall(r"^\s*model\s*:\s*[\"']?([A-Za-z0-9_.-]+)/", text, re.M)
    return names, provs


@dataclass
class Ctx:
    """Everything a row reads. The tests and tools/gen_reach_cases.py build
    their own; the server uses the defaults."""
    enabled: set = field(default_factory=_tools_enabled)
    tier: Callable[[str], str] = _tier
    env: Callable[[str], str] = _env
    lanes: Optional[list] = None            # cloud lanes; None: read them
    providers: Optional[list] = None
    search: Optional[dict] = None           # {"provider", "searxng_url", "ask_every_time", "why"}
    key_saved: Optional[Callable[[str], Optional[bool]]] = None
    second_card: Optional[dict] = None      # {"master": bool, "features": {id: bool}}
    big_model: Optional[dict] = None        # {"master": bool, ...}
    gate_action: Optional[Callable[[str], Optional[str]]] = None
    # The plug-in programs (jarvis_mcp.reach_status): {"servers", "running",
    # "problem", "card_every_start"}; None: read them.
    plugins: Optional[dict] = None


def _gate_action(lookup: str) -> Optional[str]:
    try:
        import jarvis_gate
        action, _ = jarvis_gate.action_for_tool(lookup, {})
        return str(action) if action else None
    except Exception:
        return None


def _agent():
    try:
        import jarvis_agent
        return jarvis_agent
    except Exception:
        return None


def action_of(tool: str, ctx: Ctx) -> str:
    """The gate action `tool` is decided under."""
    ag = _agent()
    lookup = tool
    try:
        t = ag.TOOLS.get(tool) if ag is not None else None
        if t is not None and t.gate_lookup_name:
            lookup = str(t.gate_lookup_name({}))
    except Exception:
        pass
    got = (ctx.gate_action or _gate_action)(lookup)
    if got:
        return got
    return _FALLBACK_ACTIONS.get(lookup, lookup)


#: home_control while the owner's "Lights, plugs and fans without a card" is on.
ASK_LIGHTS = ("Yes, every time - except the lights, plugs and fans you name yourself "
              "(your setting)")


def _lights_on() -> bool:
    try:
        import jarvis_asks_first
        return bool(jarvis_asks_first.lights_on())
    except Exception:
        return False


def _needs_a_person(tool: str) -> bool:
    ag = _agent()
    try:
        return tool in ag.NEEDS_A_PERSON if ag is not None else tool in _NEEDS_A_PERSON
    except Exception:
        return tool in _NEEDS_A_PERSON


def asks(tool: str, ctx: Ctx, *, after_outside: bool = False) -> tuple:
    """(tier, words) for whether `tool` asks the owner first."""
    action = action_of(tool, ctx)
    try:
        tier = str(ctx.tier(action))
    except Exception:
        tier = "ask"
    if tier == "never":
        return tier, ASK_NEVER
    if tool == "home_control" and _lights_on():
        # "Lights, plugs and fans without a card" (jarvis_asks_first.py,
        # 2026-09-26): on, and off by default.
        return tier, ASK_LIGHTS
    if _needs_a_person(tool) or tier == "ask":
        return tier, ASK_EVERY
    if after_outside:
        return tier, ("No - but yes after Jarvis has read an email, a web page, a file "
                      "or other outside text")
    if tier == "notify":
        return tier, ASK_TOLD
    return tier, ASK_NO


def host_of(url) -> str:
    """The host alone - never a path, a query, a user or a password."""
    try:
        h = (urllib.parse.urlsplit(str(url or "").strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return h


def where_words(host: str) -> str:
    if not host:
        return ""
    if host in ("127.0.0.1", "localhost", "::1"):
        return "this PC"
    return host


def _row(id_: str, name: str, state: str, where: str, asks_words: str, line: str) -> dict:
    return {"id": id_, "name": name, "state": state, "on": state == "on",
            "state_words": STATE_WORDS.get(state, state), "where": where,
            "asks": asks_words, "line": line}


def _tool_row(id_: str, name: str, tool: str, ctx: Ctx, *, configured: bool,
              where: str, on_line: str, not_set_up: str, off_line: str,
              after_outside: bool = False) -> dict:
    """The common shape: on only when the model is offered the tool AND the
    account is set up; blocked when its tier is "never"."""
    tier, words = asks(tool, ctx, after_outside=after_outside)
    offered = tool in ctx.enabled
    if offered and configured and tier == "never":
        return _row(id_, name, "blocked", where, words,
                    "Set up and switched on, but your settings say never, so it never runs.")
    if offered and configured:
        return _row(id_, name, "on", where, words, on_line)
    if not configured:
        return _row(id_, name, "not_set_up", "", ASK_NA, not_set_up)
    return _row(id_, name, "off", "", ASK_NA, off_line)


def _enable_line(tool: str) -> str:
    return (f"Set up on this PC, but the AI model is not offered it: \"{tool}\" is not in "
            f"[tools].enabled in jarvis-framework.toml.")


def _off_line(tool: str) -> str:
    return f"Off: \"{tool}\" is not in [tools].enabled in jarvis-framework.toml."


def _join(items: list) -> str:
    items = [str(i) for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]

# --------------------------------------------------------------------------
#   The rows, one function each
# --------------------------------------------------------------------------


def _cloud_model(ctx: Ctx) -> dict:
    lanes, provs = ctx.lanes, ctx.providers
    if lanes is None:
        server = _server_lanes()
        f_lanes, f_provs = _file_lanes(_proxy_file())
        lanes = server if server is not None else f_lanes
        provs = f_provs if provs is None else provs
    lanes = [str(x)[:60] for x in (lanes or [])][:6]
    provs = sorted({str(p)[:40] for p in (provs or [])})
    name = "Cloud model"
    if not lanes:
        return _row("cloud_model", name, "not_set_up", "", ASK_NA,
                    "No cloud model is set up, so every answer is written on this PC.")
    where = ", ".join(provs) if provs else "the cloud service named in litellm-proxy.yaml"
    return _row("cloud_model", name, "on", where, "Yes, every question",
                f"Jarvis may offer to send one question to a cloud model ({', '.join(lanes)}). "
                f"It goes only if you say yes to that one question, and never with your "
                f"memory, a picture, or a conversation that has read private or outside text.")


def _search_where(provider: Optional[str], url: str) -> str:
    try:
        import jarvis_search as WS
        hosts = {"duckduckgo": WS.DDG_HOST, "exa": host_of(WS.EXA_URL),
                 "tavily": host_of(WS.TAVILY_URL), "brave": host_of(WS.BRAVE_URL)}
    except Exception:
        hosts = {}
    if provider == "searxng":
        w = where_words(host_of(url))
        return (f"{w} (SearXNG, which asks other search engines)" if w
                else "SearXNG (its address could not be read)")
    return hosts.get(provider or "", "")


def _web_search(ctx: Ctx) -> dict:
    name = "Web search"
    try:
        import jarvis_search as WS
    except Exception:
        return _row("web_search", name, "not_set_up", "", ASK_NA,
                    "Web search is not installed on this PC.")
    s = ctx.search if ctx.search is not None else WS.settings()
    provider = s.get("provider")
    if "web_search" not in ctx.enabled:
        return _row("web_search", name, "off", "", ASK_NA, _off_line("web_search"))
    if provider is None:
        return _row("web_search", name, "blocked", "", ASK_NA,
                    "Its settings file is damaged, so Jarvis searches nothing until it is "
                    "fixed in Settings, Web search.")
    label = WS.LABEL.get(provider, provider)
    key = ""
    if provider in WS.NEEDS_KEY:
        saved = (ctx.key_saved or WS.key_saved)(provider)
        key = (" A key is saved on this PC." if saved is True else
               " No key is saved yet, so searches fail until one is." if saved is False else
               " Whether a key is saved could not be checked.")
    if s.get("ask_every_time"):
        ask_words = "Yes, every search (you chose \"Ask before every web search\")"
    else:
        ask_words = ("Only when private things could slip in - after Jarvis has read email, "
                     "files, notes, saved memories or other outside text")
    return _row("web_search", name, "on", _search_where(provider, s.get("searxng_url") or ""),
                ask_words,
                f"Searches with {label}. Only the search words are sent, and never to "
                f"another search quietly.{key}")


def _calendar(ctx: Ctx) -> dict:
    ics = ctx.env("JARVIS_CALENDAR_ICS_SECRET_URL")
    caldav = ctx.env("JARVIS_CALDAV_URL")
    if ics:
        host = host_of(ics)
        where = where_words(host) or "the calendar's private link"
        what = ("your Google Calendar through its private link"
                if host in ("calendar.google.com", "www.google.com") else
                "your calendar through its private link")
    else:
        where = where_words(host_of(caldav))
        what = "your calendar (CalDAV)"
    return _tool_row(
        "calendar", "Calendar (reading)", "calendar_read", ctx, configured=bool(ics or caldav),
        where=where,
        on_line=(f"Reads {what}: events in the days asked for. It never changes an event. "
                 f"The morning briefing reads it too, when one is set up."),
        not_set_up="No calendar is set up on this PC.",
        off_line=_enable_line("calendar_read"))


def _email_read(ctx: Ctx) -> dict:
    host = ctx.env("JARVIS_IMAP_HOST")
    user = ctx.env("JARVIS_IMAP_USER")
    where = where_words(host_of("imap://" + host)) if host else ""
    if where and user:
        where = f"{where} (as {user[:80]})"
    return _tool_row(
        "email_read", "Email (reading)", "email_check", ctx, configured=bool(host),
        where=where,
        on_line=("Reads the sender, subject, date and a short preview of recent emails, with "
                 "one-time codes and sign-in links hidden. It never marks anything as read, "
                 "moves, deletes or sends anything. The morning briefing reads the count and "
                 "senders too, when one is set up."),
        not_set_up="No email account is set up on this PC.",
        off_line=_enable_line("email_check"))


def _email_send(ctx: Ctx) -> dict:
    """Sending email (jarvis_email_send.py): the same account as reading, the
    outgoing server named in JARVIS_SMTP_HOST or worked out from the reading
    one (imap.X -> smtp.X), and one approval card per email."""
    user = ctx.env("JARVIS_IMAP_USER")
    configured = bool(user) and bool(ctx.env("JARVIS_IMAP_PASSWORD"))
    host = ctx.env("JARVIS_SMTP_HOST").strip().lower().rstrip(".")
    if not host:
        try:
            import jarvis_email_send as ES
            host = ES._guess_smtp_host(ctx.env("JARVIS_IMAP_HOST"))
        except Exception:
            host = ""
    where = where_words(host)
    if where and user:
        where = f"{where} (as {user})"
    return _tool_row(
        "email_send", "Email (sending)", "send_email", ctx, configured=configured and bool(host),
        where=where,
        on_line=("Sends one email at a time from your own account, only after you approve "
                 "a card showing the recipients, the subject and every word. No attachments."),
        not_set_up="No email account is set up on this PC for sending.",
        off_line=_enable_line("send_email"))


def _home_read(ctx: Ctx) -> dict:
    url = ctx.env("JARVIS_HOME_URL")
    return _tool_row(
        "home_read", "Home Assistant (reading)", "home_read", ctx, configured=bool(url),
        where=where_words(host_of(url)),
        on_line=("Reads the state of things in your home (lights, sensors, locks), and the "
                 "weather forecast your Home Assistant already has. Changes nothing."),
        not_set_up="Home Assistant is not set up on this PC.",
        off_line=_enable_line("home_read"))


def _home_control(ctx: Ctx) -> dict:
    url = ctx.env("JARVIS_HOME_URL")
    return _tool_row(
        "home_control", "Home Assistant (changing things)", "home_control", ctx,
        configured=bool(url), where=where_words(host_of(url)),
        on_line="Can switch lights, locks and other things in your home - each change only "
                "after you say yes to it.",
        not_set_up="Home Assistant is not set up on this PC.",
        off_line=_enable_line("home_control"))


def _notes_where(ctx: Ctx) -> tuple:
    """(configured, where) for the notes Jarvis can read."""
    try:
        import jarvis_notes as N
        vault_ok = not N.vault_problem(N.obsidian_vault())
        joplin = bool(N.joplin_token())
        obsidian_api = bool(ctx.env(N.OBSIDIAN_KEY_ENV))
        places = []
        if vault_ok:
            places.append("this PC (your Obsidian vault folder)")
        if joplin:
            places.append(f"{where_words(host_of(N.joplin_base()))} (Joplin)")
        if obsidian_api:
            url = ctx.env(N.OBSIDIAN_URL_ENV) or N._DEFAULT_OBSIDIAN_URL
            places.append(f"{where_words(host_of(url))} (Obsidian)")
        return bool(places), ", ".join(places)
    except Exception:
        return False, ""


def _notes_read(ctx: Ctx) -> dict:
    configured, where = _notes_where(ctx)
    return _tool_row(
        "notes_read", "Notes (searching)", "notes_search", ctx, configured=configured,
        where=where,
        on_line="Searches your own notes (Obsidian, Logseq or Joplin) and reads short pieces "
                "of the ones it finds.",
        not_set_up="No notes are set up on this PC (Obsidian, Logseq or Joplin).",
        off_line=_enable_line("notes_search"))


def _notes_write(ctx: Ctx) -> dict:
    name = "Notes (writing)"
    on = [t for t in ("append_obsidian_daily", "append_logseq_journal", "create_joplin_note")
          if t in ctx.enabled]
    if not on:
        return _row("notes_write", name, "off", "", ASK_NA,
                    "The AI model is not offered any way to write notes.")
    tiers = [asks(t, ctx, after_outside=True) for t in on]
    if all(t == "never" for t, _ in tiers):
        return _row("notes_write", name, "blocked", "this PC", ASK_NEVER,
                    "Switched on, but your settings say never, so no note is written.")
    words = ASK_EVERY if any(w == ASK_EVERY for _, w in tiers) else tiers[0][1]
    what = {"append_obsidian_daily": "your Obsidian daily note",
            "append_logseq_journal": "your Logseq journal",
            "create_joplin_note": "new Joplin notes"}
    return _row("notes_write", name, "on", "this PC (your notes apps)", words,
                "Can write to " + _join([what[t] for t in on]) + ".")


def _github(ctx: Ctx) -> dict:
    name = "GitHub research"
    try:
        import jarvis_research as R
        token = R.authenticated()
    except Exception:
        token = bool(ctx.env("JARVIS_GITHUB_TOKEN"))
    if "github_search" not in ctx.enabled:
        return _row("github", name, "off", "", ASK_NA, _off_line("github_search"))
    tier, words = asks("github_search", ctx)
    if tier == "never":
        return _row("github", name, "blocked", "api.github.com", words,
                    "Switched on, but your settings say never, so it never runs.")
    return _row("github", name, "on", "api.github.com", words,
                "Searches GitHub for existing code libraries, with the search words shown "
                "on the card." + (" A GitHub token is saved on this PC." if token else
                                  " No GitHub token is set, so it searches without one."))


def _phone_push(ctx: Ctx) -> dict:
    name = "Phone notifications (ntfy)"
    topic = ctx.env("JARVIS_NTFY_TOPIC")
    if not topic:
        return _row("phone_push", name, "not_set_up", "", ASK_NA,
                    "Not set up: no ntfy topic is set, so nothing is pushed.")
    server = ctx.env("JARVIS_NTFY_SERVER") or "https://ntfy.sh"
    return _row("phone_push", name, "on", where_words(host_of(server)), ASK_NA,
                "When a card waits, it pushes \"Jarvis wants to ...\" to your phone - never the "
                "details, and never while the conversation holds private text.")


def _control(tool: str, id_: str, name: str, where: str, line: str):
    def row(ctx: Ctx) -> dict:
        if tool not in ctx.enabled:
            return _row(id_, name, "off", "", ASK_NA,
                        _off_line(tool))
        tier, words = asks(tool, ctx)
        if tier == "never":
            return _row(id_, name, "blocked", where, words,
                        "Switched on, but your settings say never, so it never runs.")
        return _row(id_, name, "on", where, words, line)
    return row


_computer = _control("control_computer", "computer", "Computer control",
                     "other programs on this PC",
                     "Can click and type in other programs on this PC, one approved plan at "
                     "a time. It never touches Jarvis's own windows.")
_phone = _control("control_phone", "phone_control", "Phone control",
                  "your phone, over adb",
                  "Can tap and type on your phone plugged into this PC, one approved plan at "
                  "a time. It stops while a Jarvis app is in front.")
_shell = _control("shell_exec", "shell", "Commands on this PC",
                  "this PC (a command can reach the internet)",
                  "Can run a command on this PC after you say yes to that exact command.")


def _browser(ctx: Ctx) -> dict:
    name = "Browser control"
    sw = ctx.second_card if ctx.second_card is not None else _second_card_switches()
    feats = sw.get("features") or {}
    lane_on = bool(sw.get("master") and feats.get("browser_control")
                   and feats.get("long_context"))
    if "browser_control" not in ctx.enabled:
        return _row("browser", name, "off", "", ASK_NA,
                    _off_line("browser_control"))
    if not lane_on:
        return _row("browser", name, "off", "", ASK_NA,
                    "Off: it also needs the second graphics card's \"Browser control\" switch, "
                    "which is off.")
    tier, words = asks("browser_control", ctx)
    if tier == "never":
        return _row("browser", name, "blocked", "websites", words,
                    "Switched on, but your settings say never, so it never runs.")
    return _row("browser", name, "on", "the websites on each approved plan", words,
                "Can work a web page in a browser, one approved step at a time - only while "
                "the second graphics card is working. What it types there reaches that website.")


def _second_card_switches() -> dict:
    try:
        import jarvis_second_card as SC
        return SC._read_switches()
    except Exception:
        return {"master": False, "features": {}}


def _big_model_switches() -> dict:
    try:
        import jarvis_big_model as BM
        return BM._read_switches()
    except Exception:
        return {"master": False}


def _second_card(ctx: Ctx) -> dict:
    name = "Second graphics card"
    sw = ctx.second_card if ctx.second_card is not None else _second_card_switches()
    if not sw.get("master"):
        return _row("second_card", name, "off", "", ASK_NA,
                    "Off. Switching it on asks you with an approval card.")
    try:
        import jarvis_second_card as SC
        names = {f["id"]: f["name"] for f in SC.FEATURES}
    except Exception:
        names = {}
    on = [names.get(k, k) for k, v in (sw.get("features") or {}).items() if v]
    what = ", ".join(on) if on else "no feature yet"
    return _row("second_card", name, "on", "this PC (a second copy of Ollama)", ASK_NA,
                f"Switched on for: {what}. It is a second model on this PC: nothing it "
                f"handles leaves the PC.")


def _big_model(ctx: Ctx) -> dict:
    name = "Big model (slow)"
    sw = ctx.big_model if ctx.big_model is not None else _big_model_switches()
    if not sw.get("master"):
        return _row("big_model", name, "off", "", ASK_NA,
                    "Off. Switching it on asks you with an approval card.")
    jobs = [j for j in ("wiki", "deep_questions") if sw.get(j)]
    words = {"wiki": "the wiki builder", "deep_questions": "deep questions"}
    what = ", ".join(words[j] for j in jobs) if jobs else "no job yet"
    return _row("big_model", name, "on", "this PC (colibri)", ASK_NA,
                f"Switched on for: {what}. It runs on this PC: nothing it handles leaves the PC.")


def _plugin_status() -> dict:
    try:
        import jarvis_mcp
        return jarvis_mcp.reach_status()
    except Exception:
        return {"servers": [], "running": [], "problem": "", "card_every_start": False,
                "missing": True}


def _plugins(ctx: Ctx) -> dict:
    """Plug-in programs (MCP, jarvis_mcp.py): programs on this PC the owner
    listed under [mcp]. Names only - never anything a program wrote."""
    name = "Plug-in programs (MCP)"
    st = ctx.plugins if ctx.plugins is not None else _plugin_status()
    servers = [str(n) for n in st.get("servers") or []]
    if st.get("problem"):
        return _row("plugins", name, "off", "", ASK_NA,
                    "Off: the [mcp] part of jarvis-framework.toml has a mistake - "
                    + str(st["problem"]))
    if not servers:
        return _row("plugins", name, "not_set_up", "", ASK_NA,
                    "Not set up: no plug-in programs are listed under [mcp] in "
                    "jarvis-framework.toml.")
    if not ctx.enabled:
        return _row("plugins", name, "off", "", ASK_NA,
                    "Off: the AI model is offered no tools, so it cannot ask for these.")
    running = [n for n in st.get("running") or [] if n in servers]
    start = ("Starting one asks you every time." if st.get("card_every_start") else
             "Starting one asks you when it is new or has changed.")
    return _row("plugins", name, "on", "programs on this PC: " + _join(servers),
                ASK_EVERY,
                "Read-only tools from programs on this PC that you listed. " + start
                + " Every use asks you, every time, and what they send back is treated as "
                  "outside text. The programs themselves run with your account's "
                  "permissions." + (f" Running now: {_join(running)}." if running else ""))


#: Every way Jarvis can reach something outside itself, in the order both
#: apps show them. A new way out is ONE entry here.
KINDS = (
    ("cloud_model", _cloud_model),
    ("web_search", _web_search),
    ("calendar", _calendar),
    ("email_read", _email_read),
    ("email_send", _email_send),
    ("home_read", _home_read),
    ("home_control", _home_control),
    ("notes_read", _notes_read),
    ("notes_write", _notes_write),
    ("github", _github),
    ("phone_push", _phone_push),
    ("computer", _computer),
    ("browser", _browser),
    ("phone_control", _phone),
    ("shell", _shell),
    ("plugins", _plugins),
    ("second_card", _second_card),
    ("big_model", _big_model),
)


def tools_offered(ctx: Ctx) -> list:
    """[{"id", "name"}] - the tools the model is offered, in TOOLS order."""
    ag = _agent()
    enabled = set(ctx.enabled)
    try:
        names = ag.offered_tools(enabled - {"browser_control"}) if ag is not None \
            else sorted(enabled)
    except Exception:
        names = sorted(enabled)
    names = list(names)
    browser = _browser(ctx)
    if browser["state"] == "on":
        names.append("browser_control")
    return [{"id": n, "name": TOOL_NAMES.get(n, n)} for n in names]


def view(ctx: Optional[Ctx] = None) -> dict:
    """GET /api/reach. Never raises: a row that cannot be read says so."""
    ctx = ctx or Ctx()
    rows = []
    for id_, fn in KINDS:
        try:
            r = fn(ctx)
        except Exception as exc:
            r = _row(id_, id_.replace("_", " ").capitalize(), "off", "", ASK_NA,
                     f"Could not be read ({type(exc).__name__}).")
        rows.append(r)
    try:
        tools = tools_offered(ctx)
    except Exception:
        tools = []
    return {"available": True, "title": TITLE, "detail": DETAIL, "rows": rows,
            "tools": tools, "tools_title": TOOLS_TITLE,
            "tools_none": TOOLS_NONE, "everything_else": EVERYTHING_ELSE,
            "where_label": WHERE_LABEL, "asks_label": ASKS_LABEL,
            "on": sum(1 for r in rows if r["on"]),
            "written_by": "code"}


def handle_get() -> tuple:
    return 200, view()


def sentence(v: Optional[dict] = None) -> str:
    """The same list, as a short answer for "what can you reach?"
    (jarvis_quick.py). Host names only - no account names."""
    v = v or view()
    on, off = [], []
    for r in v["rows"]:
        if r["on"]:
            where = r["where"].split(" (as ")[0]
            asks_ = r["asks"]
            bit = r["name"]
            if where:
                bit += f": {where}"
            if asks_.startswith("Yes"):
                bit += ", asking you first every time"
            elif asks_.startswith("Only when"):
                bit += ", asking first when private things could slip in"
            elif asks_.startswith("No - but yes after"):
                bit += ", asking first after outside text"
            on.append(bit)
        else:
            off.append(r["name"])
    head = ("Right now Jarvis can reach: " + "; ".join(on) + "." if on else
            "Right now Jarvis reaches nothing outside this PC.")
    tail = (" Off or not set up: " + ", ".join(off) + ".") if off else ""
    return (head + tail + " " + EVERYTHING_ELSE + " This list is written by the PC from "
            "its settings, not by the AI model - the full list is in Settings, "
            "\"What Jarvis can reach\" (Brain on the phone).")
