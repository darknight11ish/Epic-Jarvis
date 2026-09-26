"""Jarvis-like tool-selection test cases, written in the owner's likely phrasing.

Each case: (utterance, expected tool name or None for "no tool", required-arg checks).
Used by tool_router_eval.py (router recall, runs here with no model) and by
ollama_tool_eval.py (real model accuracy, runs on the owner's PC).

`None` cases are the irrelevance set (BFCL calls it that): a good model answers
in words and calls nothing.
"""

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
