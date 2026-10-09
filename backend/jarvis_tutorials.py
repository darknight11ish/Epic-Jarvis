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
             "where": "Settings → Voice → Your voice"},
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
             "where": "Brain → Memory → Learning"},
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
             "where": "Brain → History"},
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
        "id": "when-something-is-wrong",
        "version": 1,
        "section": "both",
        "title": "When something is wrong",
        "why": "The three things you will see, and what to do about each one.",
        "minutes": 2,
        "steps": (
            {"title": "An error is a still mark, not a mood",
             "body": "When something fails, the face shows a thin ring with a "
                     "gap at the bottom and stops moving. It is drawn on "
                     "purpose to look different from the waiting-on-you clock "
                     "and the not-connected ring, so you can tell at a glance "
                     "which of the three you are looking at.",
             "where": "The HUD, or the phone's Home screen"},
            {"title": "\"Jarvis isn't connected\"",
             "body": "This means the PC's Jarvis is not answering. Usually the "
                     "app is closed, the PC is asleep, or the model is still "
                     "loading. The tray icon says the same thing, and the "
                     "phone's connection line says it too.",
             "where": "The tray icon, and Brain → About"},
            {"title": "The model is slow, or asleep",
             "body": "While the model loads, the simple things keep working: "
                     "timers, one-off reminders and alarms are answered without "
                     "it. Everything else waits, and says so, rather than "
                     "guessing at an answer.",
             "where": "Nothing to change - just ask for the timer"},
            {"title": "Stopping Jarvis mid-action",
             "body": "One key halts anything Jarvis is doing on the screen, "
                     "before its next step. Steps already done stay done, so it "
                     "stops rather than undoes. Pick your own key in Settings; "
                     "it is off until you do.",
             "where": "Settings → Shortcuts → Stop everything"},
            {"title": "If you say something about self-harm",
             "body": "Jarvis answers with the crisis helplines - 988 and 911 in "
                     "the United States - in its plain voice, not the animal "
                     "voice. It does not learn from that turn, does not count "
                     "it, and does not keep it in the chat thread.",
             "where": "Nothing to change - this is how it is built"},
        ),
    },
    {
        "id": "brain",
        "version": 1,
        "section": "pc",
        "title": "Brain, the one settings place",
        "why": "Where every switch, list and report lives, and how to find one.",
        "minutes": 2,
        "steps": (
            {"title": "It is a set of pages, not a list of switches",
             "body": "Brain is one window with a row of pages down the side: "
                     "Memory, History, Model, Work, Projects, Tutorials, "
                     "Galaxy, Now, Trust and Watch. Each page is about one "
                     "subject, so nothing is buried under anything else.",
             "where": "Brain, from the tray or the Jarvis bar"},
            {"title": "Where your memory lives",
             "body": "The Memory page holds what Jarvis has learned: the facts "
                     "it saved on its own, the ones pinned to every answer, the "
                     "ones still waiting for your yes, and the wiki it builds "
                     "from your notes. Each one can be forgotten from its own "
                     "row.",
             "where": "Brain → Memory"},
            {"title": "Where your rules live",
             "body": "\"What asks first\" is the page listing every action and "
                     "whether it asks you first. It is the rulebook: if you "
                     "wonder why Jarvis asked, or want it to ask more often, "
                     "that page is the answer.",
             "where": "Brain → What asks first"},
            {"title": "Where the work lives",
             "body": "The Work page holds focus sessions, timers, reminders and "
                     "alarms, Today's cards, goals, background jobs, the undo "
                     "shelf, and what Jarvis did lately. Projects has its own "
                     "page beside it.",
             "where": "Brain → Work"},
            {"title": "The settings window is separate",
             "body": "Ordinary settings - voice, hardware, backups, folders, "
                     "security - are in the Settings window, not in Brain. "
                     "\"Show or hide menus\" in Settings also lists every one by "
                     "name, which is the quickest way to find one.",
             "where": "Settings, and Settings → Show or hide menus"},
        ),
    },
    {
        "id": "focus-sessions",
        "version": 1,
        "section": "pc",
        "title": "Focus sessions",
        "why": "A timer plus Quiet, and the one thing it watches - and never keeps.",
        "minutes": 2,
        "steps": (
            {"title": "It is a timer plus Quiet",
             "body": "A focus session is a countdown while Jarvis stays quiet. "
                     "It is off until you start one, and it ends when the "
                     "countdown does or when you stop it.",
             "where": "Brain → Work → Focus session"},
            {"title": "What it watches - and what it never stores",
             "body": "On this PC only, Jarvis notices which app or site is in "
                     "front and names a drift out loud - \"Instagram can wait\" "
                     "- on this PC's speakers. It keeps counts, never the name "
                     "of what it saw, and nothing about it leaves the PC.",
             "where": "Brain → Work → Focus session, while one runs"},
            {"title": "The controls during a session",
             "body": "Pause and Resume stop and restart the countdown. \"+10 "
                     "minutes\" extends it. Stop ends it. Snooze and \"I'm doing "
                     "research\" are there for the moments when the drift is "
                     "not really a drift.",
             "where": "Brain → Work → Focus session, and the small desktop counter"},
            {"title": "Saying it out loud instead",
             "body": "You can start, pause, extend and stop a focus session by "
                     "voice, the same as by the buttons. Like everything else, "
                     "your voice can start things but never approves anything.",
             "where": "Just say \"start a focus session for 25 minutes\""},
            {"title": "How it ends",
             "body": "When the countdown finishes, Jarvis shows a report card of "
                     "the session and then goes back to normal. The card is a "
                     "plain summary, not a score, and there is no streak line.",
             "where": "Brain → Work → Focus session, at the end"},
        ),
    },
    {
        "id": "timers-reminders",
        "version": 1,
        "section": "pc",
        "title": "Timers, reminders and the schedule",
        "why": "What goes off, what it costs you, and what needs no card at all.",
        "minutes": 2,
        "steps": (
            {"title": "One list, called Coming up",
             "body": "Every timer, reminder, alarm and repeating job lives on "
                     "one page, in time order, with the next time each one will "
                     "go off. \"Just went off\" shows the ones from the last "
                     "hour, with Snooze.",
             "where": "Brain → Work → Coming up"},
            {"title": "Most of it needs no card",
             "body": "A plain timer, a one-off reminder, an alarm and the "
                     "standby schedule take effect at once - no approval card. "
                     "Only your own words can set one, and deleting one is "
                     "instant. That is why they do not need to ask.",
             "where": "Just ask for one"},
            {"title": "What still asks once",
             "body": "Two things read something outside this PC and so keep "
                     "their one card: the morning briefing and \"tell me when\", "
                     "because both read your email or your calendar. The card "
                     "shows what will be read.",
             "where": "Brain → Work → Coming up → Tell me when"},
            {"title": "A late alarm does not pretend",
             "body": "If the phone or this PC hears about an alarm more than ten "
                     "minutes late - it was out of reach, or restarted - it shows "
                     "a silent notification saying when it was missed instead of "
                     "ringing as if it were happening now.",
             "where": "The phone's notifications, and the PC's own"},
            {"title": "The standby schedule is not the same as Standby",
             "body": "The schedule puts Jarvis on standby at a set time and "
                     "wakes it in the morning - but only if the schedule was "
                     "what put it there. If you chose Standby yourself, it stays "
                     "on until you choose Active.",
             "where": "Brain → Work → Coming up → Standby schedule"},
        ),
    },
    {
        "id": "projects",
        "version": 1,
        "section": "pc",
        "title": "Projects, goals and benchmarks",
        "why": "One place for what you are working on and the numbers you track.",
        "minutes": 3,
        "steps": (
            {"title": "What a project is",
             "body": "A project has a name, its own instructions, its own files "
                     "and chats, and the numbers you want to watch. A coding "
                     "project tracks test and speed scores; a life project "
                     "tracks numbers you type in yourself, like a 5k time.",
             "where": "Brain → Projects"},
            {"title": "Benchmarks are the numbers it keeps",
             "body": "A benchmark is one number tracked over time, shown as a "
                     "chart. Log a new one and the chart adds a point. A number "
                     "you mark private is never read aloud: logging it says only "
                     "\"Logged.\"",
             "where": "Brain → Projects → a project → its benchmarks"},
            {"title": "Goals are the plans",
             "body": "A goal is a plan you edit, with a weekly check-in. Goals "
                     "are their own page, and a project can use them rather than "
                     "keeping a second set of plans of its own.",
             "where": "Brain → Work → Goals"},
            {"title": "The Shareable switch, off by default",
             "body": "A project can be marked Shareable, and only then may a "
                     "short piece of its files go to a web search or the chatbot "
                     "driver - shown word for word on a card first. Health and "
                     "money numbers, memory, email and credentials never go, "
                     "even then.",
             "where": "Brain → Projects → a project → Shareable"},
            {"title": "What is ready, and what is still coming",
             "body": "Projects, goals, benchmarks, charts and running tests all "
                     "work today. Jarvis writing code by itself is still "
                     "coming: it waits for the second graphics card to be "
                     "measured, so do not expect that half yet.",
             "where": "Brain → Projects, and Settings → Second graphics card"},
        ),
    },
    {
        "id": "notes-and-wiki",
        "version": 1,
        "section": "pc",
        "title": "Notes and the wiki",
        "why": "Where a quick note goes, and what the wiki builds from your files.",
        "minutes": 2,
        "steps": (
            {"title": "The three note apps",
             "body": "Jarvis can file a note into Logseq, Joplin or Obsidian - "
                     "whichever you already use. Each one is set up once, and the "
                     "small note buttons in the Jarvis bar pick between them.",
             "where": "The widget's note buttons, and Settings → Accounts"},
            {"title": "When a note asks first",
             "body": "In a turn where Jarvis has read an email, a web page, a "
                     "file or other tool output - or the conversation is marked "
                     "as having read outside text - writing a note raises an "
                     "approval card. Otherwise the note is filed straight away.",
             "where": "The card, in the Jarvis bar"},
            {"title": "The wiki reads one folder",
             "body": "Drop .md or .txt files into Jarvis Wiki/Sources inside your "
                     "Obsidian vault. The wiki page lists each one and turns it "
                     "into linked pages in Jarvis Wiki/Pages. Each document is "
                     "one job with its own card before anything is written.",
             "where": "Brain → Memory → Wiki"},
            {"title": "What the wiki needs to run",
             "body": "Building the wiki uses the model on the second graphics "
                     "card. The wiki page says plainly, in the PC's own words, "
                     "whether it can run right now and why not, rather than "
                     "failing quietly.",
             "where": "Brain → Memory → Wiki, the state line at the top"},
        ),
    },
    {
        "id": "documents-and-search",
        "version": 1,
        "section": "pc",
        "title": "Documents, folders and search",
        "why": "Which folders Jarvis may read, and what it does with them.",
        "minutes": 2,
        "steps": (
            {"title": "You choose the folders",
             "body": "Jarvis cannot see your disk. It only reads the folders you "
                     "add here, one at a time, and adding one raises a single "
                     "approval card. Removing a folder is instant.",
             "where": "Settings → Folders Jarvis may look in"},
            {"title": "Asking about a document",
             "body": "Once a folder is added you can ask about what is in it - a "
                     "PDF, a Word file, a text file - and Jarvis reads it to "
                     "answer. What it reads is outside text, so it is never "
                     "learned from as a fact.",
             "where": "Type your question in the Jarvis bar"},
            {"title": "Bringing in a Notion export",
             "body": "The same page takes the .zip Notion makes. Jarvis unzips "
                     "it into a new folder inside a folder you choose, and the "
                     "pages land as Markdown and CSV you can ask about. No card "
                     "is needed: you picked the file and the folder yourself.",
             "where": "Settings → Folders Jarvis may look in → the .zip button"},
            {"title": "A note written after reading asks first",
             "body": "Because imported notes are outside text, any note Jarvis "
                     "writes after reading them waits for your yes on a card. "
                     "That is the same rule as for email and web pages, not a "
                     "fault in the import.",
             "where": "The card, in the Jarvis bar"},
        ),
    },
    {
        "id": "screens-and-pictures",
        "version": 1,
        "section": "pc",
        "title": "Screens and pictures",
        "why": "Two ways to show Jarvis your screen, and what is kept afterwards.",
        "minutes": 3,
        "steps": (
            {"title": "\"Look at this\" is one look",
             "body": "\"Look at this\" takes a single look at your screen when "
                     "you ask, and answers your question about it. Nothing is "
                     "saved. On the PC it is a key you pick; on the phone it is "
                     "the assistant gesture.",
             "where": "Settings → Shortcuts → Look at this"},
            {"title": "\"Watch with me\" is a session",
             "body": "\"Watch with me\" is a live session you start and stop. "
                     "While it runs, a visible \"Jarvis is watching\" sign sits "
                     "in the Jarvis bar the whole time, and the sign goes away "
                     "when you stop.",
             "where": "The Jarvis bar, and Settings → Look at this and Watch with me"},
            {"title": "Where it pauses and what it skips",
             "body": "It pauses on password fields, and it skips the apps you "
                     "have excluded - banking, for instance. You choose that "
                     "list here. Nothing it sees is saved.",
             "where": "Settings → Look at this and Watch with me → the lists"},
            {"title": "What is kept, and what is not",
             "body": "Your question and Jarvis's answer are kept in your chat "
                     "history like any chat. The picture and the screen's own "
                     "words never are. What it sees counts as outside text, so "
                     "it is never learned from as a fact.",
             "where": "History, for the answer; Brain → Memory for the facts"},
            {"title": "Reading pictures, and picture mode",
             "body": "Reading the words on a screenshot works today and needs "
                     "Windows' own text recognition; if that is missing, Jarvis "
                     "says so instead of guessing. Picture mode is a slow "
                     "picture reader on the processor, meant for a PC with one "
                     "graphics card, and it is off by default. The fuller picture "
                     "understanding is still coming, and waits for the second "
                     "card to be measured.",
             "where": "Settings → Look at this and Watch with me → Picture mode"},
        ),
    },
    {
        "id": "home-calendar-email",
        "version": 1,
        "section": "pc",
        "title": "Home, calendar and email",
        "why": "What Jarvis may read for you, and the one thing that always asks.",
        "minutes": 3,
        "steps": (
            {"title": "Your calendar, read-only",
             "body": "Jarvis reads Google Calendar through its private link - the "
                     "\"Secret address in iCal format\". It is read-only, it is "
                     "set on this PC only, and the link is kept as carefully as "
                     "a password.",
             "where": "Settings → Accounts"},
            {"title": "Your home, through your own Home Assistant",
             "body": "Home status comes from your own Home Assistant on your own "
                     "network. Plain unscrambled http:// is allowed only inside "
                     "your own networks - this PC, your home addresses and "
                     ".local names, Tailscale and NordVPN Meshnet - and refused "
                     "to anything on the open internet.",
             "where": "Settings → What Jarvis can reach"},
            {"title": "Reading email, and sending it",
             "body": "Reading email is one of the tools you can switch on here, "
                     "each with a card. Sending is separate and always asks: one "
                     "card per email, showing the exact recipients, subject and "
                     "full text, with no \"always allow\".",
             "where": "Settings → What Jarvis can reach, and Settings → Sending email"},
            {"title": "The card says when it read something",
             "body": "If a turn has read an email, a page or a file, the approval "
                     "card says so in plain words. That is how you know a "
                     "decision was shaped by outside text rather than by what "
                     "you just said.",
             "where": "Any approval card"},
            {"title": "The morning briefing",
             "body": "The briefing shows the number of new emails and who they "
                     "are from, with a setting to show the count only. Its "
                     "weather can come from your own Home Assistant, so nothing "
                     "leaves the house to tell you whether to take a coat.",
             "where": "Brain → Work → Morning briefing"},
        ),
    },
    {
        "id": "faces",
        "version": 1,
        "section": "pc",
        "title": "The faces",
        "why": "Choosing how Jarvis looks, and what the expressions mean.",
        "minutes": 2,
        "steps": (
            {"title": "Four animals and a robot",
             "body": "You can pick a red panda, a pygmy owl, a sea otter, a "
                     "monkey, or a small robot. Each is drawn by the app from "
                     "its own parts - nothing is downloaded - and each sits in "
                     "the HUD, the widget and the phone.",
             "where": "Settings → Appearance → Faces"},
            {"title": "What the expressions mean",
             "body": "The face shows the state: listening, thinking, waiting on "
                     "you, asleep, an error, or not connected. An error is a "
                     "still mark with a gap at the bottom. A hollow ring means "
                     "not connected, and rising Zs mean standby.",
             "where": "The HUD, and Settings → Appearance"},
            {"title": "A voice for each face, if you want one",
             "body": "The first time you pick an animal it asks once whether to "
                     "use that animal's own voice. A face never changes your "
                     "voice by itself, and the question is remembered per face.",
             "where": "Settings → Appearance, and Settings → Jarvis's voice"},
            {"title": "Animal options in one place",
             "body": "Still, sun and moon, weather and its source, and the small "
                     "idle moments all live in Animal options. Look-and-behaviour "
                     "choices are shared between the PC and the phone; sharpness "
                     "and frame rate are per device.",
             "where": "Settings → Animal options"},
            {"title": "Serious moments stay plain",
             "body": "An approval gets an attentive look, not a wave. An error "
                     "gets a still, concerned mark. A crisis-help answer uses a "
                     "neutral pose and Jarvis's plain voice, never the animal "
                     "voice.",
             "where": "Nothing to change - this is how it behaves"},
        ),
    },
    {
        "id": "backups",
        "version": 1,
        "section": "pc",
        "title": "Backups and recovery",
        "why": "One locked file, one recovery code, and what losing it means.",
        "minutes": 3,
        "steps": (
            {"title": "One locked backup file",
             "body": "A backup is a single locked file holding your memory and "
                     "chat history. You choose the folder it goes into with "
                     "\"Choose a folder…\", and a cloud-synced folder such as a "
                     "NordLocker one is fine. Jarvis keeps only the last few.",
             "where": "Settings → Backups"},
            {"title": "The recovery code is shown once",
             "body": "When a backup is made, Jarvis shows you a recovery code "
                     "once. Write it down or save it somewhere safe there and "
                     "then. Jarvis keeps no copy of it.",
             "where": "Settings → Backups, when you make one"},
            {"title": "What a lost code means",
             "body": "If you lose the code, that backup is useless and nobody can "
                     "open it - including Jarvis. That is the point of the code, "
                     "and the page says so plainly rather than letting you find "
                     "out later.",
             "where": "Settings → Backups"},
            {"title": "Restoring, and the preview",
             "body": "Restoring takes the code and a preview first, so you can "
                     "see what is in the file before anything is put back. The "
                     "restore itself is one card, like any other change.",
             "where": "Settings → Backups → Restore"},
            {"title": "A limit worth knowing",
             "body": "Erased facts stay in older backups until those backups age "
                     "out. The delete dialogs say this too. It is a real limit, "
                     "not a bug, and it is better to know it before you rely on "
                     "an erase.",
             "where": "Settings → Backups, and Brain → Memory"},
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
             "body": "The main chat box on the PC: type or talk, see the "
                     "answer, and reach History and the settings. The big HUD "
                     "window has its own box too, with its own conversation, and "
                     "the \"Open the Jarvis bar\" button is still there beside it.",
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
        "id": "phone-talking",
        "version": 1,
        "section": "phone",
        "title": "Talking on the phone",
        "why": "How to speak, how to stop, and where the words are worked out.",
        "minutes": 2,
        "steps": (
            {"title": "Hold the button and speak",
             "body": "Press and hold the talk button on Home, speak, and let go. "
                     "While the button is down the microphone is open; when it is "
                     "not, it is not. That is deliberate on a phone, which "
                     "travels into pockets, cars and other people's houses.",
             "where": "The talk button on the phone's Home screen"},
            {"title": "Slide away to cancel",
             "body": "A hold is easy to start by accident, and once the PC has "
                     "checked a clip it cannot be unsent. So sliding your finger "
                     "off the button before you let go throws the recording away "
                     "without sending it.",
             "where": "The talk button on the phone's Home screen"},
            {"title": "The words are worked out on the PC",
             "body": "Your voice is sent to this PC, where the voice check runs "
                     "and the model makes the words. The phone never turns speech "
                     "into text itself, and it never keeps the model or your "
                     "memory.",
             "where": "Nothing to change - this is how it is built"},
            {"title": "Stopping it",
             "body": "There is a Stop control while an answer is coming, and "
                     "ending a Live session stops that. Nothing is ever approved "
                     "by voice, on the phone or anywhere else.",
             "where": "The phone's Home screen, and Settings → Stop everything"},
            {"title": "It still needs the link",
             "body": "The phone reaches the PC over Tailscale or NordVPN Meshnet "
                     "only, so if the link is down the phone says so plainly "
                     "instead of pretending to send anything. A home Wi-Fi "
                     "address is refused on purpose.",
             "where": "The connection line on the phone's Home screen"},
        ),
    },
    {
        "id": "phone-approvals",
        "version": 1,
        "section": "phone",
        "title": "Approval cards on the phone",
        "why": "Deciding a card here, and the two ways to decide it.",
        "minutes": 2,
        "steps": (
            {"title": "The card comes to Home",
             "body": "When Jarvis needs your yes, the card appears on the phone's "
                     "Home screen, over the conversation. It names the action, "
                     "what it will touch, and whether the turn had read "
                     "something outside this PC.",
             "where": "The phone's Home screen"},
            {"title": "Buttons, or a swipe",
             "body": "Every card can be decided with its own Approve and Deny "
                     "buttons. Swiping is a setting, on by default, that lets a "
                     "swipe decide instead. Turn it off and every card is decided "
                     "with buttons only.",
             "where": "Settings → Security → Swipe to approve or deny"},
            {"title": "The fingerprint for risky ones",
             "body": "A risky approval - one that loosens a rule or cannot be "
                     "undone - needs your screen lock as well. On a phone with no "
                     "screen lock set up, Jarvis refuses it and tells you how to "
                     "set one, rather than letting it through.",
             "where": "Settings → Security"},
            {"title": "Nothing is decided for you",
             "body": "Jarvis never approves anything by itself, and a card is "
                     "never approved by voice - a recording of your voice must not "
                     "be able to decide something. If the link to the PC is old, "
                     "acting is blocked until it is fresh again.",
             "where": "Any approval card, and the stale-link warning"},
            {"title": "Turning the swipe setting back on",
             "body": "Turning swiping off is instant. Turning it back on asks for "
                     "your fingerprint or PIN, because it is the looser of the "
                     "two. That is the same shape as every other loosening.",
             "where": "Settings → Security → Swipe to approve or deny"},
        ),
    },
    {
        "id": "phone-notifications",
        "version": 1,
        "section": "phone",
        "title": "Notifications and alerts",
        "why": "What rings, what waits quietly, and where each switch is.",
        "minutes": 2,
        "steps": (
            {"title": "An approval arrives as a notification",
             "body": "When a card is raised while you are not looking at the "
                     "phone, Jarvis sends a notification for it. Tapping the "
                     "notification opens the card, so you can decide from there.",
             "where": "The phone's notification shade"},
            {"title": "Urgent alerts keep ringing",
             "body": "\"Tell me when\" can watch for one thing you name - a "
                     "sender's email, a device change. A match only ever "
                     "notifies. An urgent one is a notification that keeps "
                     "ringing until you have seen it.",
             "where": "Brain → Work → Coming up → Tell me when"},
            {"title": "A late alarm does not pretend",
             "body": "If the phone hears about an alarm more than ten minutes "
                     "late, it does not ring as though it were happening now. It "
                     "shows a silent notification saying when it was missed.",
             "where": "The phone's notifications"},
            {"title": "Showing them on a watch",
             "body": "By default every notification stays on the phone, even if "
                     "you have a smartwatch. A setting lets them all show on a "
                     "compatible watch; turning it on raises a card, and turning "
                     "it off is instant.",
             "where": "Settings → Smartwatch notifications"},
            {"title": "Letting Jarvis read your notifications",
             "body": "This is a separate setting, off by default. You choose "
                     "which apps it may read - never banking - one-time codes are "
                     "hidden before anything reaches the model, and it never "
                     "replies or sends. Text messages are never read.",
             "where": "Settings → Phone notifications"},
        ),
    },
    {
        "id": "phone-stays-on-pc",
        "version": 1,
        "section": "phone",
        "title": "What stays on the PC",
        "why": "What the phone deliberately does not do, and why that is the point.",
        "minutes": 2,
        "steps": (
            {"title": "The phone is a window, not a second Jarvis",
             "body": "The assistant, the model and everything it remembers live "
                     "on this PC. The phone shows you them and sends your words "
                     "there. Nothing on the phone keeps a copy of your memory.",
             "where": "Nothing to change - this is how it is built"},
            {"title": "Speech-to-text stays on the PC",
             "body": "The phone never turns your speech into text itself. It "
                     "sends the clip to the PC, where the voice check runs and "
                     "the model works out the words. A client is not allowed to "
                     "do that step.",
             "where": "Nothing to change - this is how it is built"},
            {"title": "Your voice print stays on the PC",
             "body": "Training your voice and checking a clip against it happen "
                     "on the PC. The phone holds no voice print, so losing the "
                     "phone does not hand anyone your voice.",
             "where": "Settings → Voice, and the PC's Brain → Voice"},
            {"title": "Screenshots are blocked when they should be",
             "body": "While App lock is on, or while \"Hide memory lists and chat "
                     "history\" is on, the phone blocks screenshots. That is why "
                     "it can look blank in a screen recorder rather than showing "
                     "your facts.",
             "where": "Settings → Security"},
            {"title": "Nothing leaves your own devices",
             "body": "The phone talks to the PC over Tailscale or NordVPN "
                     "Meshnet, both private networks between your own devices. "
                     "Nothing here opens a public tunnel, and there is no setting "
                     "that would.",
             "where": "Settings → Connection"},
        ),
    },
    {
        "id": "phone-live",
        "version": 1,
        "section": "phone",
        "title": "Live on the phone",
        "why": "The back-and-forth conversation, the tile, and how to end it.",
        "minutes": 2,
        "steps": (
            {"title": "What Live is",
             "body": "Live is a back-and-forth voice conversation: you speak, "
                     "Jarvis answers, and you can talk over it without saying a "
                     "wake word between turns. You start it and you end it. It "
                     "is not full duplex, so Jarvis listens for a beat after you "
                     "stop - about a fifth of a second, or up to three seconds "
                     "when the sentence only paused.",
             "where": "The Live button on the phone's Home screen"},
            {"title": "The Quick Settings tile",
             "body": "A tile in the phone's quick panel starts Live and ends it, "
                     "and shows how many minutes are left. Where you put it is "
                     "this phone's own choice.",
             "where": "Settings → Quick Settings tiles"},
            {"title": "The headset button",
             "body": "With a Bluetooth headset, pressing its button stops Jarvis "
                     "talking, and holding it turns the microphone off or on. It "
                     "never approves anything. On some phones holding it opens "
                     "the phone's own assistant instead - Mic off is on the Live "
                     "screen and in the notification too.",
             "where": "The Live screen, and its notification"},
            {"title": "The controls on the Live screen",
             "body": "End Live stops the session. Stop talking stops the current "
                     "answer without ending it. Mic off and Mic on control the "
                     "microphone, \"20 more minutes\" extends the session, and a "
                     "card waiting pauses Live until you decide it.",
             "where": "The Live screen"},
            {"title": "Ending, and coming back",
             "body": "After Live ends, a notification offers Resume for ten "
                     "minutes, so a session ended by accident is one tap away. If "
                     "Temporary is on, the Live screen says plainly that the "
                     "session will not be kept in History.",
             "where": "The notification \"Jarvis Live ended\", and the Live screen"},
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
             "where": "The phone's setup screen, and Settings → Connection"},
            {"title": "Scan the code, or type the short one",
             "body": "The PC shows a QR code and a short typed code as the backup. "
                     "Either way the PC raises one card, and no key is handed over "
                     "until you approve it there.",
             "where": "Settings → Devices"},
            {"title": "One key per device",
             "body": "Each device gets its own key, so you can see which device "
                     "did what - in the approval list, and in the log - and you "
                     "can revoke one device without touching the others.",
             "where": "Settings → Devices"},
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
     "where": "Settings → Connection"},
    {"q": "Where do my API keys go?",
     "a": "Only to the one service each key belongs to. They are never logged "
          "and never written to disk in plain text.",
     "where": "Settings → Accounts"},
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
     "where": "Settings → Second graphics card"},
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
