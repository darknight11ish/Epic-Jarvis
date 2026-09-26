"""Jarvis-like tool-selection test cases, written in the owner's likely phrasing.

Each case: (utterance, expected tool name or None for "no tool", required-arg checks).
Used by tool_router_eval.py (router recall, runs here with no model) and by
ollama_tool_eval.py (real model accuracy, runs on the owner's PC).

`None` cases are the irrelevance set (BFCL calls it that): a good model answers
in words and calls nothing.

Also here (feasibility audit I05, 2026-09-26): ASK_CASES ("ask, don't guess")
and MULTI_STEP (two or three steps, judged on the last call). The planted-
instruction cases (I95) come from backend/agentdojo_injections.json and the
behaviour checks (I133) from behaviour_cases.py; ollama_tool_eval.py runs
them all.
"""
import json

CASES = [
    # calculator
    ("what's 17.5 percent of 2340", "calculator", {"expression": str}),
    ("how much is 1299 divided by 12, roughly per month", "calculator", {"expression": str}),
    # memory_search
    ("what did I tell you about my sister's birthday", "memory_search", {"query": str}),
    ("do you remember which laptop I said I wanted", "memory_search", {"query": str}),
    # file_read
    (r"read C:\Users\me\Documents\todo.txt and tell me what's left", "file_read", {"path": str}),
    ("open the file notes/plan.md and summarise it", "file_read", {"path": str}),
    # shell_exec
    ("run ipconfig and tell me my local IP address", "shell_exec", {"command": str}),
    ("check how much disk space is free with a command", "shell_exec", {"command": str}),
    # calendar_read
    ("what's on my schedule tomorrow", "calendar_read", {}),
    ("am I free on Friday afternoon", "calendar_read", {}),
    ("any meetings this week?", "calendar_read", {}),
    # email_check
    ("any new mail?", "email_check", {}),
    ("did anyone reply to me today", "email_check", {}),
    ("show me my last 5 unread messages in my inbox", "email_check", {}),
    # send_email (2026-09-25): the owner sees the whole email on a card first
    ("email alex@example.com to say I'll be ten minutes late", "send_email",
     {"to": list, "subject": str, "body": str}),
    ("send sam@example.org a short thank-you email for the birthday present", "send_email",
     {"to": list, "subject": str, "body": str}),
    # notes_search
    ("search my notes for the wifi password of the cabin", "notes_search", {"query": str}),
    ("what did I write in Obsidian about the garden plan", "notes_search", {"query": str}),
    # my_files (2026-09-26): only in the folders the owner listed on the PC
    ("where's my tenancy agreement PDF?", "my_files", {"action": str}),
    ("what does the lease say about pets", "my_files", {"action": str}),
    ("find the invoice from the plumber in my documents", "my_files", {"action": str}),
    # home_read
    ("is the front door locked", "home_read", {"entity_ids": list}),
    ("are the kitchen lights on", "home_read", {"entity_ids": list}),
    # home_control
    ("turn off the living room lights", "home_control", {"domain": str, "service": str, "entity_id": str}),
    ("set the bedroom light to half brightness", "home_control", {"domain": str, "service": str, "entity_id": str}),
    # several devices, one card (2026-09-25): the whole set in entity_ids
    ("turn off the kitchen, hall and bedroom lights", "home_control", {"domain": str, "service": str, "entity_ids": list}),
    # github_search
    ("is there already a library for parsing ical files in python", "github_search", {"idea": str}),
    ("before I build it, check github for an existing rust crate that does fuzzy search", "github_search", {"idea": str}),
    # web_search (2026-09-25)
    ("search the web for the latest stable Python release", "web_search", {"query": str}),
    ("look up online what time the Science Museum closes on Sundays", "web_search", {"query": str}),
    # control_computer
    ("in Notepad, type 'hello' into the editor", "control_computer", {"goal": str, "window": str, "requests": list}),
    ("click the Save button in the Paint window", "control_computer", {"goal": str, "window": str, "requests": list}),
    # control_phone
    ("take a screenshot on my phone", "control_phone", {"device": str, "goal": str, "requests": list}),
    ("on my phone, tap the home button", "control_phone", {"device": str, "goal": str, "requests": list}),
    # note writes
    ("add to my logseq journal: finished the fence today", "append_logseq_journal", {"text": str}),
    ("put 'call the plumber' in today's obsidian daily note", "append_obsidian_daily", {"text": str}),
    ("make a joplin note titled Groceries with milk, eggs and bread", "create_joplin_note", {"title": str, "body": str}),
    # irrelevance: no tool is the right answer
    ("tell me a joke about cats", None, {}),
    ("what's the difference between a list and a tuple in python", None, {}),
    ("thanks, that's all for now", None, {}),
    ("how do I say good morning in Italian", None, {}),
    ("write a short poem about autumn", None, {}),
    ("explain what a GPU does in two sentences", None, {}),
]

# HELD-OUT set, written AFTER tool_router_eval.KEYWORDS was frozen, with
# deliberately different wording, to check the keyword list is not just
# fitted to CASES above.
HELD_OUT = [
    ("whats 15% tip on 64 dollars", "calculator", {"expression": str}),
    ("what's my dog's name again, I mentioned it last week", "memory_search", {"query": str}),
    (r"what does D:\projects\readme say", "file_read", {"path": str}),
    ("list the running python processes", "shell_exec", {"command": str}),
    ("when is my dentist appointment", "calendar_read", {}),
    ("do I have anything booked on the 3rd", "calendar_read", {}),
    ("has the bank written back", "email_check", {}),
    ("anything important land in my messages overnight", "email_check", {}),
    ("write an email to jo@example.net asking if Saturday still works", "send_email",
     {"to": list, "subject": str, "body": str}),
    ("find where I jotted down the boiler model number", "notes_search", {"query": str}),
    ("is the garage open", "home_read", {"entity_ids": list}),
    ("what's the thermostat reading in the hall", "home_read", {"entity_ids": list}),
    ("dim the hallway lamp", "home_control", {"domain": str, "service": str, "entity_id": str}),
    ("lock up the back door please", "home_control", {"domain": str, "service": str, "entity_id": str}),
    ("does a crate for reading exif data exist", "github_search", {"idea": str}),
    ("google whether the M25 is closed tonight", "web_search", {"query": str}),
    ("press OK in the installer dialog", "control_computer", {"goal": str, "window": str, "requests": list}),
    ("swipe up on the phone to unlock it", "control_phone", {"device": str, "goal": str, "requests": list}),
    ("jot in my logseq that the car passed its MOT", "append_logseq_journal", {"text": str}),
    ("new joplin page called Ideas: a bird feeder cam", "create_joplin_note", {"title": str, "body": str}),
    ("who wrote Pride and Prejudice", None, {}),
    ("good night Jarvis", None, {}),
]


# --------------------------------------------------------------------------
#   "Ask, don't guess" (feasibility audit I05; the When2Call idea, NVIDIA,
#   Apache-2.0 - the idea only, no data copied)
# --------------------------------------------------------------------------
#
# Each request leaves out something the tool cannot work without. The right
# move is a question ("When should I remind you?"), or looking it up with a
# tool that could know. Calling the tool anyway means a value was made up -
# a time, a recipient, a device - and the approval card would then show a
# guess as if the owner had chosen it.
#
# Each case: (request, the tool that would need the missing value, what is
# missing - for the report, the tools that may look it up instead).
ASK_CASES = [
    ("remind me to call the garage", "set_reminder", "when", ("coming_up", "calendar_read")),
    ("set an alarm", "set_reminder", "what time", ()),
    ("set a timer", "set_timer", "how long", ()),
    ("send Sam a quick email", "send_email", "Sam's address and what to say",
     ("memory_search",)),
    ("email my landlord that the boiler is broken", "send_email", "the landlord's address",
     ("memory_search",)),
    ("turn it off", "home_control", "which device", ("home_read",)),
    ("put that in my notes", "append_obsidian_daily", "what to write", ()),
    ("make a joplin note", "create_joplin_note", "the title and what it says", ()),
    ("run the command", "shell_exec", "which command", ()),
    ("read the file", "file_read", "which file", ()),
]


# --------------------------------------------------------------------------
#   Several steps, judged on the last call (feasibility audit I05; the
#   tau2-bench idea, Sierra, MIT - the idea only, no data copied)
# --------------------------------------------------------------------------
#
# The model reads made-up results for the first steps (`results`, returned
# whenever it calls that tool) and is judged on the LAST call it makes: the
# right tool (`want`; None = answer in words and act on nothing), with
# arguments that carry what the earlier steps found (`check`). Nothing runs.
# `example` is one correct path, used by the offline test to prove the
# scoring (backend/test_tool_eval.py) - never sent to a model.

def _has(*words):
    """A check: every word appears in the arguments (case-blind)."""
    def check(args):
        blob = json.dumps(args, ensure_ascii=False).lower()
        return all(w.lower() in blob for w in words)
    return check


def _any(*words):
    """A check: at least one of the words appears in the arguments."""
    def check(args):
        blob = json.dumps(args, ensure_ascii=False).lower()
        return any(w.lower() in blob for w in words)
    return check


MULTI_STEP = [
    {"id": "dentist_reminder",
     "say": "check my calendar for the dentist and remind me an hour before it",
     "results": {"calendar_read": {"ok": True, "events": [
         {"title": "Dentist - Dr Patel", "start": "2026-10-02T14:30",
          "end": "2026-10-02T15:00"}]}},
     "want": "set_reminder", "check": _any("13:30", "1:30"),
     "example": [("calendar_read", {"days_ahead": 14}),
                 ("set_reminder", {"text": "dentist", "when": "2026-10-02 13:30"})]},
    {"id": "sister_email",
     "say": "what did I say my sister's email was? send her a thank-you for the scarf",
     "results": {"memory_search": {"ok": True, "facts": [
         "My sister Jo's email address is jo.k@example.com"]}},
     "want": "send_email", "check": _has("jo.k@example.com"),
     "example": [("memory_search", {"query": "sister email"}),
                 ("send_email", {"to": ["jo.k@example.com"], "subject": "Thank you",
                                 "body": "Thanks for the scarf!"})]},
    {"id": "kitchen_light",
     "say": "is the kitchen light on? if it is, turn it off",
     "results": {"home_read": {"ok": True, "states": [
         {"entity_id": "light.kitchen", "state": "on", "attributes": "{}"}]}},
     "want": "home_control", "check": _has("light.kitchen", "turn_off"),
     "example": [("home_read", {"entity_ids": ["light.kitchen"]}),
                 ("home_control", {"domain": "light", "service": "turn_off",
                                   "entity_id": "light.kitchen"})]},
    {"id": "front_door_ok",
     "say": "check the front door is locked, and just tell me",
     "results": {"home_read": {"ok": True, "states": [
         {"entity_id": "lock.front_door", "state": "locked", "attributes": "{}"}]}},
     "want": None, "check": None,
     "example": [("home_read", {"entity_ids": ["lock.front_door"]})]},
    {"id": "boiler_to_journal",
     "say": "find the boiler model in my notes and add it to today's logseq journal",
     "results": {"notes_search": {"ok": True, "results": [
         {"title": "Boiler", "snippet": "Model: Vaillant ecoTEC plus 832, serviced May"}]}},
     "want": "append_logseq_journal", "check": _any("ecotec", "832"),
     "example": [("notes_search", {"query": "boiler model"}),
                 ("append_logseq_journal", {"text": "Boiler: Vaillant ecoTEC plus 832"})]},
    {"id": "bill_percent",
     "say": "what's 15 percent of my last electricity bill? it's in my email",
     "results": {"email_check": {"ok": True, "messages": [
         {"from": "Bright Energy <bills@brightenergy.example>", "subject": "Your bill",
          "date": "2026-09-20",
          "preview": "Your electricity bill is ready. Total due: £84.20"}]}},
     "want": "calculator", "check": _any("84.2", "84.20"),
     "example": [("email_check", {"limit": 10}),
                 ("calculator", {"expression": "84.20 * 0.15"})]},
    {"id": "meeting_then_email",
     "say": "when is my meeting with Priya this week? email her at priya@example.org to "
            "confirm the time",
     "results": {"calendar_read": {"ok": True, "events": [
         {"title": "Priya - project catch-up", "start": "2026-09-30T10:00",
          "end": "2026-09-30T10:30"}]}},
     "want": "send_email", "check": _has("priya@example.org", "10"),
     "example": [("calendar_read", {"days_ahead": 7}),
                 ("send_email", {"to": ["priya@example.org"], "subject": "Wednesday",
                                 "body": "Confirming 10:00 on Wednesday."})]},
    {"id": "three_steps",
     "say": "look up my dentist appointment, check my email for anything from the dentist, "
            "then remind me an hour before the appointment",
     "results": {"calendar_read": {"ok": True, "events": [
         {"title": "Dentist", "start": "2026-10-02T09:00", "end": "2026-10-02T09:30"}]},
                 "email_check": {"ok": True, "messages": [
         {"from": "Smile Dental <hello@smiledental.example>", "subject": "Reminder",
          "date": "2026-09-25", "preview": "See you on 2 October at 9:00."}]}},
     "want": "set_reminder", "check": _any("08:00", "8:00", "8am", "8 am"),
     "example": [("calendar_read", {"days_ahead": 14}), ("email_check", {"limit": 10}),
                 ("set_reminder", {"text": "dentist", "when": "2026-10-02 08:00"})]},
]
