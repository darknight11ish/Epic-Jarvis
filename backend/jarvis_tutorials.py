#!/usr/bin/env python3
"""Tutorials and the FAQ, for both apps, with the owner's progress.

WHAT THIS IS

The owner asked (2026-10-05) for a skippable comprehensive intro tutorial and a
tutorial for each major part of Jarvis, on the desktop program and the Android
app, with the progress of tutorial completion recorded and the ability to quit
a specific tutorial and resume it later - the same tutorials on both apps, but
with a section for the desktop program and a section for the Android app. Plus
an FAQ with well-thought-out questions and answers. The design is
`docs/TUTORIALS-DESIGN.md`.

The content lives HERE, in the backend, and not in the two apps: written twice
it would drift, and the phone and the PC would teach different things. Both
apps read this catalogue and both apps write their progress back to the PC, so
finishing "Memory" on the phone ticks it on the PC.

* `GET  /api/tutorials`          the catalogue, each with the owner's progress
* `POST /api/tutorials/progress` {id, state, step} - what the owner has read
* `GET  /api/faq`                the questions and answers

WHAT IT DOES NOT DO

It writes one small JSON file in the config folder (`tutorials.json`) and
nothing else. It never raises an approval card and never touches the owner's
`jarvis-framework.toml`: a card per "Next" would be absurd, and this is the
owner marking their own reading. It reads no file but its own, and it makes no
network call. `backend/test_tutorials.py` proves each of those.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit  # parsing a path, not a network call

try:  # the framework module, when it is there (the real backend, not a suite)
    import jarvis_framework as fw
except Exception:  # pragma: no cover - a suite sets the environment instead
    fw = None

PATH = "/api/tutorials"
PROGRESS_PATH = "/api/tutorials/progress"
FAQ_PATH = "/api/faq"
PROGRESS_NAME = "tutorials.json"

#: What the install block below answers. Everything else goes to the server's own
#: handler untouched, which is what keeps this module from standing in front of
#: anything else.
_ROUTES_GET = (PATH, FAQ_PATH)
_ROUTES_POST = (PROGRESS_PATH,)

#: The states a record may hold. No record at all means "not started", which is
#: not the same as skipped - a tutorial nobody opened was not turned down.
STATES = ("in_progress", "done", "skipped")

#: "both" shows in each app's own list; the other two are the two sections the
#: owner asked for.
SECTIONS = ("pc", "phone", "both")
SECTION_TITLES = {"pc": "On this PC", "phone": "On your phone"}

INTRO_ID = "intro"

#: Every tutorial, in the order the apps list them. `version` goes up when the
#: steps change, so a tutorial the owner finished on older words is offered
#: again instead of being counted done - the same reason
#: jarvis-desktop/src-tauri/src/commands.rs versions its onboarding marker.
CATALOGUE = (
    {
        "id": "intro",
        "version": 1,
        "section": "both",
        "title": "What Jarvis is",
        "why": "Two minutes, and everything else makes more sense afterwards.",
        "minutes": 2,
        "steps": (
            {"title": "It runs on your PC",
             "body": "The assistant itself, the AI model and everything it "
                     "remembers live on this PC. The phone app is a window onto "
                     "it, not a second Jarvis: it talks to this PC over "
                     "Tailscale or NordVPN Meshnet, both private networks "
                     "between your own devices.",
             "where": "The tray icon, or the Jarvis bar on the PC"},
            {"title": "Your private things never leave it",
             "body": "Email, files, passwords and saved memory are only ever "
                     "read by the model on this PC. A few named things do go "
                     "out - web search, the chatbot driver, online weather - "
                     "and each one asks you first. Web search can be your own "
                     "SearXNG, running on this PC.",
             "where": "Brain → What asks first"},
            {"title": "It asks before it acts",
             "body": "Anything that changes something shows you a card first: "
                     "what it will do, and what it will touch. You decide with "
                     "a tap or a click - never by voice. Risky approvals also "
                     "ask for Windows Hello on the PC, or your screen lock on "
                     "the phone.",
             "where": "The card, wherever you are"},
            {"title": "Things you can ask for today",
             "body": "Timers and reminders, notes and your Obsidian wiki, "
                     "reading a document or a screenshot, focus sessions, "
                     "projects, the morning briefing, web search, home "
                     "control, and a voice conversation you can interrupt.",
             "where": "Type or press the talk button - that is the quickest way "
                      "to see"},
            {"title": "Five rules it will not break",
             "body": "Nothing private goes to the cloud. It never opens a "
                     "public tunnel. An API key goes only to the one service it "
                     "belongs to. It never approves anything by itself. It is "
                     "yours alone - sideloaded, never sold.",
             "where": "Brain → About, and docs/ARCHITECTURE.md for the long "
                      "version"},
        ),
    },
    {
        "id": "talking",
        "version": 1,
        "section": "both",
        "title": "Talking to it",
        "why": "The three ways in, and what the voice check actually does.",
        "minutes": 2,
        "steps": (
            {"title": "The talk button",
             "body": "Press and hold, speak, let go. This is the way that always "
                     "works, and it is trusted by default.",
             "where": "The talk button on the PC's Jarvis bar, or the phone's Home"},
            {"title": "\"Hey Jarvis\"",
             "body": "Hands-free: say the words, then speak. A voice setting can "
                     "make hands-free stricter than the talk button - under the "
                     "stricter choice, a turn started by \"Hey Jarvis\" cannot "
                     "save facts without a card.",
             "where": "Brain → Voice → Hands-free (\"Hey Jarvis\")"},
            {"title": "What the voice check does - and does not - prove",
             "body": "Every clip is checked against your voice print before it "
                     "is used. It is honest about its limit: it cannot tell a "
                     "recording or a copy from the real you, and it says so.",
             "where": "Brain → Voice → Your voice print"},
            {"title": "Jarvis Live",
             "body": "A back-and-forth conversation with no wake word between "
                     "turns, which you can interrupt. It pauses during a phone "
                     "or video call, and nothing is approved by voice in it "
                     "either.",
             "where": "The Live button, on both apps"},
            {"title": "Read aloud, and when it stays on screen",
             "body": "Answers that used web search, weather or home status are "
                     "read out. Answers that used email, files, notes, memory or "
                     "the screen stay on screen by default - and a sensitive "
                     "fact always keeps an answer on screen.",
             "where": "Brain → How Jarvis talks"},
        ),
    },
    {
        "id": "asks-first",
        "version": 1,
        "section": "both",
        "title": "What asks first",
        "why": "The one page that answers \"why did it ask me that?\"",
        "minutes": 2,
        "steps": (
            {"title": "Every card says what it will do",
             "body": "The card names the action, what it will touch, and whether "
                     "the turn had read outside text (an email, a page, a file). "
                     "If it came from reading something else, the card says so.",
             "where": "Any approval card"},
            {"title": "The list, in plain words",
             "body": "Both apps have one page listing every action and whether it "
                     "asks, with a switch to make any of them stricter. That page "
                     "is the rulebook - not this tutorial.",
             "where": "Brain → What asks first"},
            {"title": "Loosening asks, tightening does not",
             "body": "Making something stricter happens at once. Loosening a rule "
                     "asks once, on the PC, with Windows Hello. The phone cannot "
                     "loosen the PC's rules by itself.",
             "where": "Brain → What asks first → the switches"},
            {"title": "Some things never ask",
             "body": "Timers, one-off reminders, alarms, the standby schedule and "
                     "a plain \"from now on...\" take effect at once, with Undo. "
                     "They change nothing outside your PC.",
             "where": "Just ask for one"},
            {"title": "Voice never approves",
             "body": "You can start things by voice, but a card is always decided "
                     "by tapping or clicking it. That is deliberate: a recording "
                     "of your voice must not be able to approve anything.",
             "where": "Any approval card"},
        ),
    },
    {
        "id": "memory",
        "version": 1,
        "section": "both",
        "title": "What Jarvis remembers",
        "why": "What it learns, what waits for a yes, and how to take it back.",
        "minutes": 3,
        "steps": (
            {"title": "Facts, from your own words only",
             "body": "It learns things about you from what you type or say. Never "
                     "from web pages, emails, documents, notes or tool output - "
                     "those are outside text, and outside text is never learned "
                     "from.",
             "where": "Brain → Memory"},
            {"title": "Some things wait for your yes",
             "body": "Health, money, passwords and account details, and private "
                     "details about other people, are only saved when you say so. "
                     "A setting can save health and money automatically; "
                     "passwords, PINs and ID numbers always ask.",
             "where": "Brain → Memory → Sensitive topics"},
            {"title": "Forget, and Erase the words",
             "body": "Forget hides a fact and keeps its history. Erase the words "
                     "wipes the fact's text and its search entry for good - only "
                     "the dates stay, so the history shows something was erased. "
                     "Both ask \"are you sure?\" first.",
             "where": "Brain → Memory → the fact's own menu"},
            {"title": "Erasing does not reach into backups",
             "body": "The delete dialogs say it plainly: erased facts stay in "
                     "older backups until those age out. That is a limit, not a "
                     "bug, and it is worth knowing before you rely on it.",
             "where": "Brain → Memory, and Brain → Backup"},
            {"title": "Where the numbers came from",
             "body": "Every learned fact has a \"true from\" date, so older news "
                     "never replaces newer, and a correction card is offered when "
                     "you say something is wrong.",
             "where": "Brain → Memory → a fact"},
        ),
    },
    {
        "id": "records",
        "version": 1,
        "section": "both",
        "title": "Records, history and what is kept",
        "why": "What is written down, where, and how to see or remove it.",
        "minutes": 2,
        "steps": (
            {"title": "Chat history is kept, encrypted, on the PC",
             "body": "Your typed and spoken turns are kept so History works, and "
                     "a switch turns that off. Temporary chats are not kept at "
                     "all. Crisis chats are kept but titled \"A difficult "
                     "moment\", never with your words.",
             "where": "History, and Brain → Privacy"},
            {"title": "The approval list is read-only",
             "body": "Every card you decided - approved, denied or timed out - is "
                     "listed with when it happened and which device asked.",
             "where": "History → Approvals"},
            {"title": "Forget a time frame",
             "body": "Ask to forget last week, or a range of dates. Both apps show "
                     "every fact and chat from that time, each ticked, and you can "
                     "untick any. One card decides it, and there are ten minutes "
                     "of Undo.",
             "where": "Brain → Memory → Forget a time frame"},
            {"title": "The audit log",
             "body": "On the PC, a plain log records what Jarvis did and when. It "
                     "is there so you can check, not so anyone else can.",
             "where": "The log folder in Brain → About"},
        ),
    },
    {
        "id": "pc-at-a-glance",
        "version": 1,
        "section": "pc",
        "title": "The desktop at a glance",
        "why": "Which window is which, and the key that stops everything.",
        "minutes": 2,
        "steps": (
            {"title": "The HUD",
             "body": "The face and the status: whether Jarvis is connected, "
                     "listening, thinking or waiting on you. An error is a still "
                     "mark, not a mood; the Zs mean standby, not a fault.",
             "where": "The HUD window"},
            {"title": "The Jarvis bar",
             "body": "The one chat box on the PC: type or talk, see the answer, "
                     "and reach History and the settings. The HUD's own chat box "
                     "opens this one, so there is only ever one conversation.",
             "where": "The Jarvis bar"},
            {"title": "Approval cards and the widget",
             "body": "A card appears over whatever you are doing, and the small "
                     "widget shows the same decision. While App lock is on, the "
                     "widget shows only a short title and its Approve opens the "
                     "locked app.",
             "where": "The card, or the widget"},
            {"title": "Stop everything",
             "body": "One hotkey halts anything Jarvis is doing on the screen. "
                     "Choose your own key in Settings; it is off until you do.",
             "where": "Settings → Stop everything"},
            {"title": "Brain",
             "body": "Every setting, the memory lists, \"What asks first\", the "
                     "faces and the backups live in one place. If you cannot find "
                     "something, it is almost certainly in here.",
             "where": "Brain, from the tray or the bar"},
        ),
    },
    {
        "id": "phone-pairing",
        "version": 1,
        "section": "phone",
        "title": "Pairing your phone",
        "why": "How the phone gets its own key, and what it can and cannot do.",
        "minutes": 3,
        "steps": (
            {"title": "Both devices on the same private network",
             "body": "The phone reaches this PC over Tailscale or NordVPN Meshnet "
                     "only. A home Wi-Fi address is refused on purpose: the "
                     "pairing key would travel unscrambled over it.",
             "where": "The phone's setup screen, and Brain → Phone on the PC"},
            {"title": "Scan the code, or type the short one",
             "body": "The PC shows a QR code and a short typed code as the backup. "
                     "Either way the PC raises one card, and no key is handed over "
                     "until you approve it there.",
             "where": "Brain → Phone → Pair a device"},
            {"title": "One key per device",
             "body": "Each device gets its own key, so you can see which device "
                     "did what - in the approval list, and in the log - and you "
                     "can revoke one device without touching the others.",
             "where": "Brain → Phone → Devices"},
            {"title": "What the phone does not do",
             "body": "It never does speech-to-text itself, and it never keeps the "
                     "model or your memory. It sends your voice to the PC, where "
                     "the voice check and the model actually are.",
             "where": "Nothing to change - this is how it is built"},
        ),
    },
)

#: The FAQ. Written from what the app really does, in the owner's words, with a
#: "where" line wherever there is something they can change. Kept here so both
#: apps say the same thing.
FAQ = (
    {"q": "Does Jarvis send my things anywhere?",
     "a": "Email, files, credentials and saved memory are only ever read by the "
          "model on this PC. Web search, the chatbot driver and online weather "
          "are the named exceptions, each asks first, and web search can be your "
          "own SearXNG on this PC.",
     "where": "Brain → What asks first"},
    {"q": "Will it open a tunnel so I can reach it from anywhere?",
     "a": "No. The phone reaches the PC over Tailscale or NordVPN Meshnet, both "
          "device-to-device. A public address is refused with a message saying "
          "why, and while one is saved the desktop does nothing over the "
          "network.",
     "where": "Brain → Phone"},
    {"q": "Where do my API keys go?",
     "a": "Only to the one service each key belongs to. They are never logged "
          "and never written to disk in plain text.",
     "where": "Brain → API keys and services"},
    {"q": "Can it act without asking me?",
     "a": "Only where you have said so. Risky approvals need Windows Hello on "
          "the PC or your screen lock on the phone, and it stops acting when the "
          "event stream is stale.",
     "where": "Brain → What asks first"},
    {"q": "How do I start talking to it?",
     "a": "The talk button, \"Hey Jarvis\", or the phone's tile. A voice setting "
          "can make \"Hey Jarvis\" stricter than the button.",
     "where": "Brain → Voice"},
    {"q": "Why did it keep an answer on screen instead of reading it out?",
     "a": "It used a sensitive fact, or a reading tool such as email, files, "
          "notes or memory, or your hands-free setting is strict. A voice setting "
          "lets it read those aloud, and turning that on asks first.",
     "where": "Brain → How Jarvis talks"},
    {"q": "What does it remember about me?",
     "a": "Facts learned from your own words, plus the chat history you have not "
          "turned off. Health, money, passwords and other people's private "
          "details wait for your yes.",
     "where": "Brain → Memory"},
    {"q": "How do I make it forget something?",
     "a": "\"Forget\" hides a fact and keeps its history; \"Erase the words\" "
          "wipes the text for good and keeps only the dates; \"Forget a time "
          "frame\" lists everything from a period for you to untick, with ten "
          "minutes of Undo.",
     "where": "Brain → Memory"},
    {"q": "Does deleting a chat delete what it learned?",
     "a": "No. Facts learned earlier stay until you Forget or Erase them. The "
          "delete dialog says so, and backups keep a copy until they age out.",
     "where": "History, and Brain → Memory"},
    {"q": "What happens if I lose my backup recovery code?",
     "a": "The backup is useless, and nobody can open it - including Jarvis. "
          "That is what the code is for.",
     "where": "Brain → Backup"},
    {"q": "It says \"Jarvis isn't connected\".",
     "a": "The PC's backend is not answering: usually the app is closed, the PC "
          "is asleep, or the model is loading. The tray icon says the same "
          "thing.",
     "where": "The tray icon, and Brain → About"},
    {"q": "How do I stop it mid-action?",
     "a": "The stop-everything hotkey on the PC, the phone's Stop, or ending a "
          "Live session. Nothing is ever approved by voice.",
     "where": "Settings → Stop everything"},
    {"q": "The model is slow, or asleep.",
     "a": "Simple things like timers and one-off reminders are answered without "
          "the model, so they keep working while it loads or sleeps.",
     "where": "Nothing to change - just ask for the timer"},
    {"q": "What if I say something about self-harm?",
     "a": "Jarvis answers with the crisis helplines (988 and 911 in the United "
          "States), in its plain voice. That turn is never learned from, never "
          "counted, and not kept in the chat thread.",
     "where": "Nothing to change - this is how it is built"},
    {"q": "A picture could not be read.",
     "a": "It says so on the card and does not send the picture on blindly. "
          "Reading the words in a picture needs Windows' own text recognition, "
          "and the words are marked as outside text.",
     "where": "Nothing to change - send it again after a screenshot"},
    {"q": "How do I update Jarvis?",
     "a": "Pull the repository and run scripts/apply-patches.ps1, then restart. "
          "The patcher leaves your own jarvis-framework.toml alone.",
     "where": "docs/ARCHITECTURE.md, and README.md"},
    {"q": "Do I need the second graphics card?",
     "a": "No. Picture understanding and the long-context lane wait for it; "
          "everything else runs on the card you have. Nothing switches to it "
          "until it is installed and measured.",
     "where": "Brain → Your second graphics card"},
    {"q": "How do I see what it has been doing?",
     "a": "History (with continued chats marked), the read-only approval list, "
          "and the audit log on the PC.",
     "where": "History, and the log folder in Brain → About"},
    {"q": "Why does an option say it will ask for Windows Hello?",
     "a": "Anything that loosens a rule asks once, on the PC, with Windows "
          "Hello. That is the guardrail working, not a fault.",
     "where": "Brain → What asks first"},
    {"q": "How do I get a tutorial back?",
     "a": "Open Tutorials and choose \"Show this one again\" on any finished "
          "one. A tutorial whose steps changed is offered again by itself.",
     "where": "Tutorials, on either app"},
)


def _config_dir() -> Path:
    """Where the owner's own state lives - never a repository folder."""
    if fw is not None and getattr(fw, "CONFIG_DIR", None):
        return Path(fw.CONFIG_DIR)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def _state_path() -> Path:
    """The reading progress. Never the owner's toml: no route may write that."""
    return _config_dir() / PROGRESS_NAME


def _load() -> dict:
    """The records, or {} - a missing or broken file is not an error here."""
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(records: dict) -> bool:
    """Write the records, atomically. True when they are on disk."""
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tutorials-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(records, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _by_id(tid: str) -> Optional[dict]:
    return next((t for t in CATALOGUE if t["id"] == tid), None)


def _record(records: dict, tid: str) -> Optional[dict]:
    rec = records.get(tid)
    return rec if isinstance(rec, dict) else None


def one(tutorial: dict, records: dict) -> dict:
    """One tutorial as an app sees it: the steps, and where the owner is."""
    rec = _record(records, tutorial["id"])
    state = str(rec.get("state")) if rec and rec.get("state") in STATES else ""
    step = int(rec.get("step") or 0) if rec else 0
    steps = len(tutorial["steps"])
    step = max(0, min(step, steps))
    # Due again when there is no record at all, or when the steps themselves
    # changed since it was recorded: being marked done on words the owner never
    # saw is worse than asking once more.
    changed = bool(rec) and int(rec.get("version") or 0) < int(tutorial["version"])
    return {"id": tutorial["id"], "section": tutorial["section"],
            "title": tutorial["title"], "why": tutorial["why"],
            "minutes": tutorial["minutes"], "steps": list(tutorial["steps"]),
            "state": state or "not_started", "step": step, "steps_total": steps,
            "done": state == "done" and not changed,
            "resume_at": step if state == "in_progress" and step else None,
            "due": (not rec) or changed,
            "changed_since": changed}


def read(section: str = "", records: Optional[dict] = None) -> dict:
    """GET /api/tutorials: both sections, each tutorial with its progress."""
    recs = _load() if records is None else records
    want = section if section in SECTIONS else ""
    items = [one(t, recs) for t in CATALOGUE
             if not want or t["section"] in (want, "both")]
    return {"ok": True,
            "sections": [{"id": s, "title": SECTION_TITLES[s]} for s in ("pc", "phone")],
            "tutorials": items,
            "counts": {"done": sum(1 for i in items if i["done"]),
                       "due": sum(1 for i in items if i["due"]),
                       "total": len(items)},
            "note": ("Progress is kept on this PC and shared by both apps. "
                     "Nothing here is sent anywhere.")}


def progress(records: Optional[dict] = None) -> dict:
    """GET /api/tutorials/progress: just the records."""
    recs = _load() if records is None else records
    return {"ok": True, "records": recs}


def mark(tid: str, state: str, step: int = 0,
         records: Optional[dict] = None) -> tuple:
    """One tutorial's progress. (status, body) for the POST route.

    A card is deliberately not raised: this is the owner marking their own
    reading, it changes nothing outside this file, and a card per "Next" would
    be absurd. Everything is validated, and it never raises.
    """
    try:
        # A request that does not say WHICH tutorial is malformed (400); a
        # request that names one that does not exist is not found (404). The
        # apps treat the two differently, so they are not conflated.
        if not isinstance(tid, str) or not tid.strip():
            return 400, {"ok": False, "error": "say which tutorial"}
        tutorial = _by_id(tid.strip())
        if tutorial is None:
            return 404, {"ok": False, "error": "there is no tutorial called that"}
        if state == "not_started":
            # "Show this one again": the record is removed, so the tutorial is
            # offered as it would be to someone who had never opened it. The
            # same value the apps show for a tutorial with no record.
            recs = _load() if records is None else dict(records)
            recs.pop(tutorial["id"], None)
            if not _save(recs) and records is None:
                return 500, {"ok": False, "error": "the progress could not be saved"}
            return 200, {"ok": True, "id": tutorial["id"], "state": "not_started",
                         "step": 0, "steps_total": len(tutorial["steps"]), "done": False}
        if state not in STATES:
            return 400, {"ok": False, "error": "state must be one of " + ", ".join(STATES)}
        try:
            step = int(step or 0)
        except (TypeError, ValueError):
            return 400, {"ok": False, "error": "step must be a whole number"}
        steps = len(tutorial["steps"])
        if step < 0 or step > steps:
            return 400, {"ok": False, "error": f"step must be between 0 and {steps}"}
        recs = _load() if records is None else dict(records)
        recs[tutorial["id"]] = {"state": state, "step": step,
                                "version": int(tutorial["version"]),
                                "at": round(time.time(), 3)}
        if not _save(recs) and records is None:
            return 500, {"ok": False, "error": "the progress could not be saved"}
        return 200, {"ok": True, "id": tutorial["id"], "state": state, "step": step,
                     "steps_total": steps, "done": state == "done"}
    except Exception as exc:  # never raises to the route
        return 500, {"ok": False, "error": type(exc).__name__}


def faq() -> dict:
    """GET /api/faq: the questions and answers, in the order written."""
    return {"ok": True,
            "questions": [dict(item) for item in FAQ],
            "count": len(FAQ),
            "note": "Written from how Jarvis behaves today, in plain words."}


def _query_section(query: str) -> str:
    """`section=pc` out of a query string, or ""."""
    for part in str(query or "").split("&"):
        key, _, value = part.partition("=")
        if key == "section" and value in SECTIONS:
            return value
    return ""


def handle_get(query: str = "") -> tuple:
    """(status, body) for GET /api/tutorials."""
    try:
        return 200, read(_query_section(query))
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}


def handle_post(payload: Optional[dict] = None) -> tuple:
    """(status, body) for POST /api/tutorials/progress."""
    try:
        body = payload if isinstance(payload, dict) else {}
        return mark(body.get("id", ""), body.get("state", ""), body.get("step", 0))
    except Exception as exc:
        return 500, {"ok": False, "error": type(exc).__name__}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap do_GET and do_POST so the tutorial and FAQ routes are answered here,
    after the server's own origin and token checks. Every other request goes
    straight to the original. Returns the banner line.

    Called from jarvis_hud.py by `tutorials.patch`, in the same shape as
    jarvis_retirement.install and the other route-adding modules.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_tutorials", False):
        return "  tutorials  Tutorials and the FAQ (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        split = urlsplit(str(getattr(self, "path", "") or ""))
        if split.path.rstrip("/") not in _ROUTES_GET:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            if split.path.rstrip("/") == FAQ_PATH:
                code, out = 200, faq()
            else:
                code, out = handle_get(split.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        split = urlsplit(str(getattr(self, "path", "") or ""))
        if split.path.rstrip("/") not in _ROUTES_POST:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = {}
        try:
            code, out = handle_post(body)
        except Exception as exc:
            code, out = 500, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_tutorials = True      # so a second install() is a no-op
    do_POST._jarvis_tutorials = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  tutorials  Tutorials and the FAQ "
            "(GET /api/tutorials, POST /api/tutorials/progress, GET /api/faq)")
