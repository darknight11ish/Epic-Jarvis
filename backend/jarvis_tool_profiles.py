"""jarvis_tool_profiles.py - Jarvis's own dossier on every tool it has.

WHAT THIS IS
    One hand-written, code-verified page per tool in `jarvis_agent.TOOLS` (the
    real dict, read from that file - not guessed), plus one page per capability
    family, plus the small pure functions that turn a question into either a
    deterministic plain answer or a compact context block for the language
    model. The point is that Jarvis can hold a FULL conversation about its own
    abilities - what a thing is in beginner words, what it really lets the owner
    do, what it touches, what it refuses, what it pairs with, how to switch it
    on, and which files prove each claim - instead of reading out one catalogue
    row.

THE DOSSIERS ARE DATA; BEHAVIOUR IS IN THE TOOLS' OWN MODULES
    Nothing here runs a tool, changes a setting, opens a file or touches the
    network. Every `sources` entry names the module the claim was checked
    against, and `backend/test_tool_profiles.py` re-checks the load-bearing
    ones against that source (the shipped `[tools].enabled` list, the
    asks-first tiers, the REA hard-deny list, the sandbox default, the phone
    allow-list, and so on). If a future change makes a sentence here untrue,
    that test is what catches it - so a sentence that cannot be backed is
    written as a limit, not as a promise.

WHAT IS DELIBERATELY NOT CLAIMED
    * The gate itself (`jarvis_gate.py`) is NOT in this repository: the owner's
      live backend holds it, and this repository holds the patches against it.
      So no profile claims a runtime approval outcome; it names the ACTION a
      tool is decided under and the tier that action has in the shipped
      `jarvis-framework.toml`, which is what this tree can prove.
    * A capability a module does not implement is never described as if it
      did. Where the code only proves "read", the dossier says read.

HOW A QUESTION IS ANSWERED
    `answer_about(text)` returns a plain deterministic answer when a tool or a
    family is clearly named, and None when it is not (so the model answers).
    `context_for(text)` returns the same match as a short context block
    (<= CONTEXT_LIMIT characters) to append to a system prompt, so the model can
    discuss that tool in depth without inventing anything.
"""

import re

__all__ = [
    "PROFILES", "FAMILIES", "TIER_VALUES", "ALLOWED_TOUCH", "CONTEXT_LIMIT",
    "names", "profile", "answer_about", "context_for",
]

#: The four switch states a tool can be in, and what each one MEANS here.
#: Decided from the shipped config path, never from taste:
#:   always-available - offered with no owner action, because it is in the
#:                      shipped `[tools].enabled` list (or rides with a tool
#:                      that is: the two web-search approval tools).
#:   switchable       - a real in-app Settings switch (jarvis_asks_first
#:                      TIER_A / TIER_B). Off until the owner turns it on.
#:   settings-file    - no in-app switch: the owner adds its name to
#:                      `[tools].enabled` by hand in jarvis-framework.toml.
#:   off-by-default   - its own module switch ships OFF and decides whether the
#:                      tool is offered at all, whatever the tool list says.
TIER_VALUES = ("switchable", "settings-file", "always-available", "off-by-default")

#: What a profile may say it TOUCHES. A small closed vocabulary, so the test can
#: check a claim against the module instead of accepting any prose. A tool that
#: reaches more than one reads as a comma-separated list ("files, phone"), and
#: every token in it must be one of these words; "none" stands alone.
ALLOWED_TOUCH = frozenset({
    "none", "files", "screen", "phone", "network service", "process",
    "memory", "settings",
})

#: `context_for` never returns more than this many characters.
CONTEXT_LIMIT = 1200

#: One entry per name in `jarvis_agent.TOOLS` (51 tools on this branch), in the
#: same order that dict declares them. Every field is prose for a beginner
#: developer; `sources` is the repository file(s) the claim was checked against.
PROFILES: dict = {

    "calculator": {
        "id": "calculator",
        "title": "Calculator (exact arithmetic)",
        "what": "A small arithmetic calculator. You give it one expression - "
                "18 * 4.5 + 12 - and it returns one number worked out by code. "
                "It exists so a figure Jarvis uses is computed rather than "
                "guessed at by the language model.",
        "gives": [
            "Work out a sum, a percentage or an average exactly, instead of "
            "letting the model estimate it",
            "Check a number Jarvis quoted, with a second and separate calculation",
            "Turn one figure into another - a discount off a price, a monthly "
            "share of a yearly cost",
            "Do a quick what-if on numbers you are reading from a bill or a table",
        ],
        "touches": "none",
        "limits": [
            "Arithmetic only: numbers, brackets and + - * / with a capped power. "
            "There are no named functions at all - no round(), no min() - so say "
            "how you want a figure rounded and the model will phrase it",
            "No algebra, no script, no unit or currency conversion",
            "It computes and returns; it stores nothing and cannot see the rest "
            "of the conversation",
        ],
        "combines": {
            "run_data_script": "When the sum needs the whole file rather than "
                               "numbers you are reading, run_data_script adds it "
                               "up in a sandbox and the calculator checks the total.",
            "my_spending": "my_spending totals your bank export by category; the "
                           "calculator then works out a separate what-if on the "
                           "figures it printed.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is already in the shipped "
                       "`[tools].enabled` list and needs nothing configured.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/rebuilt/jarvis-framework.toml",
                    "backend/jarvis_asks_first.py"],
    },

    "memory_search": {
        "id": "memory_search",
        "title": "Memory search (what Jarvis has learned about you)",
        "what": "Searches the facts Jarvis has learned about the owner from the "
                "owner's own words - a preference, a name, a project detail, "
                "something they once said. It is the same recall a chat turn "
                "uses, including the people layer, so \"my sister\" can find the "
                "person's real name.",
        "gives": [
            "Answer \"what do you remember about me?\" from stored facts instead "
            "of from the model's imagination",
            "Find whether the owner ever mentioned something, and when they said it",
            "Look a fact up by a name the owner uses rather than a keyword",
            "Keep an answer consistent with what the owner already told Jarvis",
        ],
        "touches": "memory",
        "limits": [
            "Only facts learned from the owner's own words. Web pages, emails, "
            "documents, notes and tool output are never learning sources",
            "A \"between us\" joke fact is withheld in a Plain-manner turn, even "
            "through this tool",
            "Empty or unrelated memory returns nothing - it will not improvise a "
            "fact to be helpful",
            "At most 20 facts come back in one call (5 by default)",
        ],
        "combines": {
            "self_portrait": "self_portrait says what the memory store is made of "
                             "on this PC; memory_search reads the facts inside it.",
            "conversation_find": "Find the fact first, then find the conversation "
                                 "where the owner actually said it.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/rebuilt/jarvis_memory.py",
                    "backend/jarvis_past.py",
                    "backend/jarvis_auto_learn.py"],
    },

    "file_read": {
        "id": "file_read",
        "title": "Read one text file",
        "what": "Opens one plain-text file at a path the owner gives it and "
                "returns the words inside. It is the simplest reading door "
                "Jarvis has, and its action name is also the one the folder "
                "tools are decided under.",
        "gives": [
            "Read a configuration file, a log or a CSV as text and quote it back",
            "Check what a file actually says instead of assuming",
            "Read a note that lives as a plain file on the PC",
        ],
        "touches": "files",
        "limits": [
            "One file per call, and only a path the owner named",
            "Plain text only - a PDF, Word, Excel or PowerPoint file is refused "
            "here and needs my_files instead",
            "Reading only: it never writes, moves or deletes anything",
            "Not in the shipped `[tools].enabled` list, so it is offered only "
            "after the owner adds it",
        ],
        "combines": {
            "my_files": "my_files finds a file in the folders the owner listed "
                        "and reads the office formats; file_read reads the plain "
                        "text one in the same folder.",
            "send_file_to_phone": "Read a text file on the PC, then send that same "
                                  "file to the phone app after one card.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"file_read\" to the [tools].enabled list in "
                       "jarvis-framework.toml. There is no in-app switch for it.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/jarvis_asks_first.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "run_data_script": {
        "id": "run_data_script",
        "title": "Small Python script (sandboxed data and maths)",
        "what": "Runs a short Python script for data or maths in a sealed "
                "sandbox: add up a CSV, take an average, work out a percentage, "
                "draw a simple chart. The sandbox has no network, writes "
                "nothing, and can read only the files it was handed.",
        "gives": [
            "Add up a whole CSV or spreadsheet export rather than a few figures "
            "the model can see",
            "Get an average, a percentage or a total that is computed exactly",
            "Produce a small chart from the file's own numbers",
            "Answer a data question from a real file, reproducibly",
        ],
        "touches": "files",
        "limits": [
            "Its own switch ships OFF and it is not a line in `[tools].enabled` "
            "at all: until that switch is on, the tool is not even offered",
            "No network, writes nothing, no imports beyond a fixed list (math, "
            "statistics, decimal, fractions, datetime, collections, itertools, "
            "re, json, csv), and a timeout and memory cap apply",
            "Reading an owner file needs the file inside \"Folders Jarvis may "
            "look in\" and puts that run on its own approval card showing the "
            "code and the resolved file names",
        ],
        "combines": {
            "my_files": "my_files finds and identifies the export; "
                        "run_data_script then computes over it.",
            "calculator": "The script computes over the file, the calculator "
                          "checks one headline figure a second way.",
            "my_spending": "my_spending already understands a bank layout; a "
                           "script is for a file it has no layout for.",
        },
        "tier": "off-by-default",
        "enable_hint": "Turn on the sandbox switch in Settings (the module keeps "
                       "`sandbox_exec_enabled` in sandbox.json, default off). "
                       "Adding it to the tool list does nothing by itself.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/jarvis_sandbox_exec.py",
                    "backend/jarvis_documents.py"],
    },

    "shell_exec": {
        "id": "shell_exec",
        "title": "Run one shell command",
        "what": "Runs one command line on this PC and returns what it printed. "
                "It is the door to every tool that already exists on the "
                "machine - git, pip, a build script, a CLI utility - and the "
                "most powerful thing Jarvis can be given.",
        "gives": [
            "Run an installed program or a build tool and read its output",
            "Check a repository's state (git status, git diff)",
            "Install a Python package or a CLI tool the owner named",
            "Do a one-off job the GUI would take many clicks",
        ],
        "touches": "process, files, network service",
        "limits": [
            "Every run is decided under the `run_shell_on_host` action, which "
            "ships as tier \"ask\": a person approves the exact command each time",
            "The command runs with an allow-listed environment, not Jarvis's own, "
            "so service passwords and the pairing token are not passed to it",
            "One command per call, with a timeout clamped between 1 and 120 "
            "seconds; only the tail of the output comes back",
            "Not in the shipped `[tools].enabled` list - the owner has to add it",
        ],
        "combines": {
            "run_data_script": "shell_exec runs a real installed program; "
                               "run_data_script does small data maths with no "
                               "network at all. Use whichever the job allows.",
            "github_search": "github_search says which library to use; an "
                             "approved shell command clones or installs it.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"shell_exec\" to [tools].enabled in "
                       "jarvis-framework.toml. Each command still asks on its own "
                       "card at the \"ask\" tier.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/jarvis_child_env.py",
                    "backend/rebuilt/jarvis-framework.toml",
                    "backend/jarvis_asks_first.py"],
    },

    "control_computer": {
        "id": "control_computer",
        "title": "Click and type in another Windows program",
        "what": "Drives another Windows program by naming its on-screen "
                "controls - the button called \"Save\", the text box called "
                "\"Search\" - instead of guessing pixel positions. It reads the "
                "window's accessibility tree, which is the list Windows itself "
                "keeps of every control on screen.",
        "gives": [
            "Fill in and submit a form in a program that has no API",
            "Press a named button or menu item in a window",
            "Read a label or a field's value out of another program",
            "Do a repetitive click-and-type job while the owner watches the card",
        ],
        "touches": "screen",
        "limits": [
            "One named window per plan, and every step is printed on ONE card "
            "before anything is clicked",
            "A control it cannot find, or two that match, is reported as a "
            "refusal - never guessed at",
            "It runs the steps a person approved; it does not loop and decide "
            "what to click next on its own",
            "A program on the \"Protected from Jarvis\" list is refused, and it "
            "needs its name in `[tools].enabled` (tier \"ask\")",
        ],
        "combines": {
            "browser_control": "Same one-card, named-element shape, but aimed at a "
                               "browser tab instead of a native window.",
            "protect_from_jarvis": "A program the owner protects is refused here "
                                   "before any click, so the two are the brake and "
                                   "the pedal on the same road.",
            "propose_plan": "A multi-step job can put one window's steps in a "
                            "plan card, with a risky step asking again.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"control_computer\" to [tools].enabled; its tier is "
                       "\"ask\", so every plan still needs a person's yes.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/jarvis_ui_control.py",
                    "backend/jarvis_protection.py",
                    "backend/jarvis_asks_first.py"],
    },

    "control_phone": {
        "id": "control_phone",
        "title": "Tap, type and screenshot on the paired phone",
        "what": "Sends individual adb commands to the owner's paired Android "
                "phone - a tap, a swipe, a key, typed words, a screenshot, or "
                "the phone's own UI listing. It deliberately does not open a live "
                "mirrored session, because one card cannot authorise whatever a "
                "live session does later.",
        "gives": [
            "Open one of the apps on the owner's own allow-list on the phone",
            "Tap, swipe, type or press a key on the phone from the PC",
            "Take a screenshot or read the phone's UI tree to see what is on it",
            "Start an allowed app and search for something in it",
        ],
        "touches": "phone",
        "limits": [
            "Only apps on the `[phone_apps]` list - and that table ships EMPTY, "
            "so nothing is allowed until the owner fills it in",
            "App search only works for apps Jarvis has a search address for; "
            "today that is YouTube Music, and other apps can be opened but not "
            "asked to search",
            "Exactly one phone must be connected over adb; zero or several "
            "connected phones is a plain refusal, never a guess",
            "One card per plan, printed as the exact adb commands, and not in "
            "the shipped `[tools].enabled` list",
        ],
        "combines": {
            "phone_apps": "phone_apps writes the allow-list control_phone obeys - "
                          "without it the phone tool can open nothing.",
            "send_file_to_phone": "control_phone drives the phone; "
                                  "send_file_to_phone puts a file from the PC onto "
                                  "the Jarvis phone app.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"control_phone\" to [tools].enabled and add the apps "
                       "you allow to the [phone_apps] table (or ask Jarvis to add "
                       "them). Its tier is \"ask\".",
        "sources": ["backend/jarvis_agent.py",
                    "backend/jarvis_android_control.py",
                    "backend/jarvis_phone_apps.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "phone_apps": {
        "id": "phone_apps",
        "title": "Which apps Jarvis may use on the phone",
        "what": "Reads and edits the `[phone_apps]` table - the friendly name and "
                "Android package of each app Jarvis is allowed to open on the "
                "owner's phone. It is the one way to fill that list by talking, "
                "instead of hand-editing a settings file.",
        "gives": [
            "List which phone apps Jarvis is allowed to open, in the owner's own names",
            "Allow a new app by name and package, after one card",
            "Remove an app from the list, after one card",
            "Keep the phone permission in one place instead of scattered settings",
        ],
        "touches": "settings",
        "limits": [
            "One app per card - it never adds several at once",
            "It needs the Android package name (e.g. com.example.maps); it cannot "
            "discover or search for a package on the phone",
            "It manages the list only: it does not open, search or control any app",
            "The list ships empty, which means nothing is allowed",
        ],
        "combines": {
            "control_phone": "phone_apps decides what is allowed; control_phone is "
                             "what actually opens and drives it.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` "
                       "list, and the list it edits starts empty.",
        "sources": ["backend/jarvis_agent.py",
                    "backend/jarvis_phone_apps.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "plugin_list": {
        "id": "plugin_list",
        "title": "List Jarvis's drop-in plugins",
        "what": "Lists every plugin folder beside Jarvis, says whether each one "
                "is on, and gives the reason when one is off - switched off, "
                "failed to load, a broken plugin.json, or added after Jarvis "
                "started. Read-only: it lists the folder and changes nothing.",
        "gives": [
            "See which optional features are installed as plugins",
            "Find out why a plugin is not working, in plain words",
            "Know whether a plugin needs a restart to be noticed",
        ],
        "touches": "files",
        "limits": [
            "Read-only, so it raises no approval card",
            "It reports only what is in the plugins folder - it cannot install, "
            "download or repair a plugin",
            "A plugin dropped in after start-up shows as added-after-start, not "
            "as working",
        ],
        "combines": {
            "plugin_switch": "plugin_list says what there is and what is wrong; "
                             "plugin_switch turns one on or off.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_plugins.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "plugin_switch": {
        "id": "plugin_switch",
        "title": "Turn one plugin on or off",
        "what": "Switches ONE drop-in plugin by the name plugin_list shows. "
                "Turning it off is instant and needs no card; turning it on "
                "raises one approval card, because a plugin is program code that "
                "will run inside Jarvis.",
        "gives": [
            "Enable a plugin the owner added, after one card",
            "Disable a plugin instantly, with no card and no waiting",
            "Keep optional features under the same one-per-change card every other "
            "change uses",
        ],
        "touches": "files",
        "limits": [
            "One plugin per call, and only a name plugin_list really shows - it "
            "never invents, deletes or moves one",
            "Either change takes effect the NEXT time Jarvis starts; it never "
            "offers to restart Jarvis itself",
            "\"on\" is the carded half (modify_own_code); \"off\" is immediate",
        ],
        "combines": {
            "plugin_list": "List first to get the exact name and the reason, then "
                           "switch that one plugin.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_plugins.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "browser_control": {
        "id": "browser_control",
        "title": "Drive one browser tab, one step at a time",
        "what": "Works a web page the way control_computer works a window: each "
                "step names an element by its role and accessible name (a "
                "button called \"Send\", a textbox called \"Email\"), and every "
                "step is printed on one card before it runs.",
        "gives": [
            "Fill in and submit a web form or a support widget that has no API",
            "Click through a page step by step, with a person approving the steps",
            "Read a chat's new messages, or the main text of a page, in pieces",
            "Sign in on a visible window when a task needs it",
        ],
        "touches": "network service, screen",
        "limits": [
            "It ships NOT offered, for two reasons: its name must be in "
            "`[tools].enabled`, AND either the second card's \"Browser control\" "
            "lane or the headless browser engine must be on",
            "One tab only: it stops if the page leaves the allowed sites or opens "
            "another tab",
            "A missing or ambiguous element is reported, never guessed; the click "
            "that submits a form must be marked as the final one",
            "Visible mode needs Playwright installed; headless mode is a separate "
            "engine with its own switch and one approval card",
        ],
        "combines": {
            "read_web_page": "read_web_page reads the words of one address; "
                             "browser_control is for pages you must click and type on.",
            "control_computer": "The same named-element shape, for a native "
                                "Windows program instead of a tab.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"browser_control\" to [tools].enabled, then turn on "
                       "the second card's Browser control lane or the headless "
                       "browser engine. It is not an in-app switch.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_browser_control.py",
                    "backend/jarvis_browser_engine.py",
                    "backend/jarvis_second_card.py",
                    "backend/jarvis_asks_first.py"],
    },

    "github_search": {
        "id": "github_search",
        "title": "Has someone already built this? (GitHub research)",
        "what": "Asks GitHub whether an existing library already does the coding "
                "idea, then grades what comes back by how well maintained it is "
                "and what licence it carries. The answer is a recommendation per "
                "capability: adopt the existing library, fork and extend one, or "
                "build it custom.",
        "gives": [
            "Avoid rebuilding something that already exists and is maintained",
            "Get a per-capability verdict: ADOPT, FORK or BUILD",
            "See a project's licence before any code is used",
            "See whether a project looks abandoned",
        ],
        "touches": "network service",
        "limits": [
            "It must never run without a person's yes: an approved plan is the "
            "permission, whatever tier the action has",
            "A token is optional. Without one the search is anonymous and "
            "rate-limited; with `JARVIS_GITHUB_TOKEN` it is its own, separately "
            "tiered action",
            "Public repositories only - it never touches the owner's own account "
            "content",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "shell_exec": "github_search picks the library; an approved command "
                          "clones or installs it.",
            "web_search": "web_search is for general outside information; "
                          "github_search is specifically for grading code.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on \"GitHub research\" in Settings (it is an in-app "
                       "switch), or add \"github_search\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_research.py",
                    "backend/jarvis_asks_first.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "web_search": {
        "id": "web_search",
        "title": "Search the public web",
        "what": "Searches the public web through the search provider the owner "
                "chose - SearXNG running on this PC by default - and returns up "
                "to five results as a title, a link and a short snippet. It "
                "never silently switches to a different provider.",
        "gives": [
            "Answer something that needs current or outside information",
            "Find the address of a page worth reading in full",
            "Check a fact that is not in the owner's own notes or memory",
        ],
        "touches": "network service",
        "limits": [
            "Five results, and only title, link and snippet - not the page text",
            "The search words leave this PC, so private details must never go in them",
            "Switching web search off in Settings does not merely refuse it: the "
            "model is never offered the tool at all",
            "It must never claim a search that did not run",
        ],
        "combines": {
            "read_web_page": "Search finds the address; read_web_page fetches that "
                             "one page's words after its own card.",
            "approve_web_search_for_conversation": "For a research session, one "
                                                   "card can let searches run for "
                                                   "the rest of that conversation.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` "
                       "list. Its provider and its own on/off switch live in "
                       "Settings, Web search.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_search.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "read_web_page": {
        "id": "read_web_page",
        "title": "Read one web page out loud",
        "what": "Fetches ONE web page whose address the owner named and returns "
                "the words a reader would actually see, so Jarvis can read them "
                "out or answer from them. The owner sees the exact address on a "
                "card before anything is fetched.",
        "gives": [
            "Have an article or a page read to you, in the page's own words",
            "Answer a question from a page the owner handed over",
            "Carry on through a long page in pieces rather than losing it",
        ],
        "touches": "network service",
        "limits": [
            "One address per card, raised BEFORE the fetch - a way out of this PC "
            "cannot be taken back, so it asks every single time",
            "It never follows a link on the page and never fetches a second page",
            "What comes back is outside text: never treated as instructions, "
            "never learned as a fact",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "web_search": "Search first to find the address, then read that one "
                          "page in full.",
            "browser_control": "A page you only need to read uses this; a page you "
                               "must click and type on needs browser_control.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"read_web_page\" to [tools].enabled. Every fetch still "
                       "raises its own card (tier \"ask\").",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_readpage.py",
                    "backend/jarvis_asks_first.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "calendar_read": {
        "id": "calendar_read",
        "title": "Read your calendar",
        "what": "Reads the owner's own calendar events for the next N days and "
                "returns what is on. It only reads: nothing in this tool creates, "
                "moves or cancels an event.",
        "gives": [
            "Answer \"what's on this week?\" from the real calendar",
            "Find a free day or check for a clash before suggesting a time",
            "Prepare for a meeting by seeing what it is and when",
        ],
        "touches": "network service",
        "limits": [
            "Read-only. Writing the calendar is a different, carded action and not "
            "this tool",
            "It needs a calendar it can reach: CalDAV with the owner's own "
            "username and password, or the Google sign-in set up separately",
            "7 days by default and 90 days at most in one call",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "email_check": "Read the calendar for when, the inbox for the message "
                           "that goes with it.",
            "set_reminder": "See an event coming, then set a reminder before it.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on calendar reading in Settings (it is an in-app "
                       "switch), or add \"calendar_read\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_calendar.py",
                    "backend/jarvis_google_calendar.py",
                    "backend/jarvis_asks_first.py"],
    },

    "email_check": {
        "id": "email_check",
        "title": "Read your inbox",
        "what": "Lists recent inbox messages - sender, subject, date and a short "
                "preview - over IMAP, the standard way to read mail with a "
                "username and password. It reads and nothing more.",
        "gives": [
            "See what has arrived, unread only by default",
            "Find one message from a sender or a subject",
            "Have Jarvis summarise the state of the inbox",
        ],
        "touches": "network service",
        "limits": [
            "Read-only, on purpose: it never marks a message read, moves it, "
            "deletes it or replies. Those are separate, carded tools",
            "Needs an IMAP username and password the owner set up; there is no "
            "Google or Microsoft sign-in in this reader",
            "10 messages by default, 25 at most, and only a preview - not the "
            "whole body",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "tidy_inbox": "Read to see what is there, then tidy the messages the "
                          "owner names on one card.",
            "send_email": "Read the message, then send a reply as its own email.",
            "draft_email": "Read the message, then save a draft to answer later.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on email in Settings under \"Connected accounts & "
                       "home\", or add \"email_check\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_email.py",
                    "backend/jarvis_asks_first.py"],
    },

    "send_email": {
        "id": "send_email",
        "title": "Send one email",
        "what": "Sends one plain-text email from the owner's own account, after "
                "the owner has read all of it - every recipient, the subject and "
                "every word - on an approval card.",
        "gives": [
            "Send a message the owner dictated or approved",
            "Answer an email by sending a separate one",
            "Get something out to someone without opening a mail program",
        ],
        "touches": "network service",
        "limits": [
            "One email per card, and only a person's yes sends it - there is no "
            "always-allow",
            "No attachments, and plain text only",
            "It runs on the local model only: on a model that is not on this PC "
            "the tool is refused outright before it prepares anything",
            "\"Delete\"-style mistakes are impossible to undo here: sending is a "
            "named way out of the PC and cannot be recalled",
        ],
        "combines": {
            "email_check": "Read the inbox first, then send the reply.",
            "draft_email": "Save it as a draft when the owner wants to check it in "
                           "their own mail program before anything is mailed.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on sending in Settings under \"Connected accounts & "
                       "home\", or add \"send_email\" to [tools].enabled. Its tier "
                       "must stay \"ask\".",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_email_send.py",
                    "backend/jarvis_asks_first.py"],
    },

    "draft_email": {
        "id": "draft_email",
        "title": "Save one email draft",
        "what": "Saves one plain-text draft into the owner's own Drafts folder, "
                "after the owner has read all of it on a card. It never sends "
                "anything: a draft waits until the owner opens it themselves.",
        "gives": [
            "Compose now and send later, from the owner's own mail program",
            "Write a draft even when the recipient is not settled yet",
            "Keep a half-finished answer out of the sent folder",
        ],
        "touches": "network service",
        "limits": [
            "It never sends. Mailing it is the owner's own act in their own program",
            "The recipient may be left out or incomplete - that is what a draft is for",
            "No attachments, plain text only, and a person's yes saves it",
            "It runs on the local model only",
        ],
        "combines": {
            "send_email": "Draft when the owner wants to check it first; send when "
                          "they want it gone now.",
            "email_check": "Read the message that needs an answer, then save the draft.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on drafts in Settings under \"Connected accounts & "
                       "home\", or add \"draft_email\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_email_draft.py",
                    "backend/jarvis_asks_first.py"],
    },

    "tidy_inbox": {
        "id": "tidy_inbox",
        "title": "Tidy the inbox",
        "what": "Archives, stars, marks as read, or moves to Trash a checked list "
                "of emails. One approval card lists every email it will touch, "
                "and afterwards the owner has ten minutes to undo it.",
        "gives": [
            "Clear out newsletters and bulk mail in one approved step",
            "Star or mark read a batch the owner describes in plain words",
            "Get a noisy inbox quieter without deleting anything for good",
        ],
        "touches": "network service",
        "limits": [
            "\"Trash\" only ever moves a message to Trash - there is no permanent "
            "delete anywhere in it",
            "The card lists every email and must be approved on screen; ten "
            "minutes of Undo follow",
            "It needs email reading to work, because the card has to show the messages",
            "A person's yes is required every time whatever the tier says",
        ],
        "combines": {
            "email_check": "Read the inbox to find the messages, then tidy that "
                           "exact list.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on inbox tidy in Settings under \"Connected accounts & "
                       "home\", or add \"tidy_inbox\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_inbox_tidy.py",
                    "backend/jarvis_asks_first.py"],
    },

    "notes_search": {
        "id": "notes_search",
        "title": "Search your own notes",
        "what": "Searches the owner's own notes in Obsidian or Joplin - both run a "
                "REST server on this PC that a local token unlocks - and returns "
                "matching notes. It reads and nothing else.",
        "gives": [
            "Find a note by the words inside it",
            "Quote the owner's own written words rather than paraphrasing",
            "Answer from the owner's notes instead of from the public web",
        ],
        "touches": "files, network service",
        "limits": [
            "Read-only - it never creates, edits or deletes a note",
            "One backend at a time: whichever of Joplin or Obsidian the owner has "
            "actually set up (an Obsidian vault folder also works as a plain folder)",
            "10 results by default, 20 at most",
            "It needs that app's own local token or vault path configured",
        ],
        "combines": {
            "create_joplin_note": "Search what is already written, then add one new "
                                  "note beside it.",
            "append_obsidian_daily": "Find the note, then add today's line to the "
                                     "daily note.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on notes search in Settings, or add \"notes_search\" "
                       "to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_notes.py",
                    "backend/jarvis_asks_first.py"],
    },

    "my_files": {
        "id": "my_files",
        "title": "Find and read your own files",
        "what": "Finds and reads the owner's own files, only inside the folders "
                "the owner listed. It reads PDFs, Word, Excel, PowerPoint, "
                "Markdown, plain text and CSV one part at a time, and can search "
                "the words of recordings the media index has stored.",
        "gives": [
            "Find a file by words in its name",
            "Search the text inside notes and text files",
            "Read one part of a big PDF or a spreadsheet without losing the thread",
            "Search what was said in recordings, and read one recording's words",
        ],
        "touches": "files",
        "limits": [
            "Only inside \"Folders Jarvis may look in\". With no folder listed the "
            "tool is not offered at all",
            "One part of one file per call - a long document comes back in pieces",
            "Reading only: it never writes, renames, moves or deletes a file",
            "A file or folder on the \"Protected from Jarvis\" list is refused "
            "before it is opened",
        ],
        "combines": {
            "send_file_to_phone": "Find the file on the PC, then send that one file "
                                  "to the phone app after a card.",
            "run_data_script": "Find the export, then compute over it in the sandbox.",
            "file_read": "The plain-text twin: my_files finds and reads the office "
                         "formats, file_read reads a plain text file.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` "
                       "list, but it only appears once at least one folder is "
                       "listed in Settings.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_documents.py",
                    "backend/jarvis_media_index.py",
                    "backend/jarvis_protection.py"],
    },

    "send_file_to_phone": {
        "id": "send_file_to_phone",
        "title": "Send one file to your phone",
        "what": "Sends ONE file from the owner's own listed folders to the Jarvis "
                "app on the phone, after one card that shows the filename, the "
                "folder and the size. The phone gets an opaque id, never a raw "
                "path, and nothing is fetchable until the owner approves.",
        "gives": [
            "Have a document from the PC on the phone to read or download",
            "Move one file across without a cable, a cloud drive or an email to "
            "yourself",
            "Know exactly which file and how big, before it is sent",
        ],
        "touches": "files, phone",
        "limits": [
            "One file, at most 10 MiB, from a listed folder only",
            "One approval card shows the exact filename, folder and size, and "
            "nothing is fetchable until the owner approves it",
            "The id it hands the phone is random, single-use and lasts ten minutes",
            "It never takes a path from the phone's side of the route",
        ],
        "combines": {
            "my_files": "my_files finds the file; send_file_to_phone puts that one "
                        "file on the phone.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on \"send a file to the phone\" in Settings, or add "
                       "\"send_file_to_phone\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_send_file.py",
                    "backend/jarvis_asks_first.py"],
    },

    "protect_from_jarvis": {
        "id": "protect_from_jarvis",
        "title": "Protect something from Jarvis",
        "what": "Adds a folder, a file or a program to the owner's \"Protected "
                "from Jarvis\" list, either blocked entirely or read-only. Every "
                "other module asks this one check before it reads, writes, opens "
                "or controls anything.",
        "gives": [
            "Stop Jarvis reading or writing a folder or file at all",
            "Let Jarvis see a program but never click, type in or control it",
            "Keep a credentials store, a browser profile or a private folder out "
            "of reach of every other tool",
        ],
        "touches": "settings",
        "limits": [
            "It only adds or updates one entry per card; it does not encrypt, "
            "hide or back anything up",
            "Protection is a rule Jarvis obeys, not a Windows permission: it does "
            "not stop any other program on the PC",
            "\"Read only\" for a program means its title or a screenshot may be "
            "read; clicking, typing, opening or controlling it is refused",
            "A path has to be listed for the rule to bite - nothing is protected "
            "by default",
        ],
        "combines": {
            "my_files": "my_files asks this check before it opens anything, so a "
                        "protected folder simply never appears in a read.",
            "control_computer": "A protected program is refused before any click, "
                                "and its window is not screen-captured.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on protection in Settings (\"Safety and sharing\"), "
                       "or add \"protect_from_jarvis\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_protection.py",
                    "backend/jarvis_asks_first.py"],
    },

    "my_spending": {
        "id": "my_spending",
        "title": "Add up your spending",
        "what": "Adds up and audits spending from a bank export the owner dropped "
                "into a folder Jarvis may look in. It can summarise by category "
                "and month, suggest categories for shops it does not recognise, "
                "and find recurring charges, price rises and double charges.",
        "gives": [
            "Answer \"how much did I spend on food last month?\" from the real file",
            "See spending by category, by month, or both",
            "Spot subscriptions, a price rise, or the same charge taken twice",
            "Give the uncategorised shops a category once, and keep it",
        ],
        "touches": "files",
        "limits": [
            "Every number comes from the file and from this code - the model may "
            "put one short sentence round the table, and it is thrown away unless "
            "every number in it appears in the table",
            "It reads a file the owner exported; there is no bank connection and "
            "nothing is fetched from a bank",
            "The file has to be inside a listed folder, and a saved layout is what "
            "lets one file be understood",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "calculator": "The table gives the figures; the calculator works out a "
                          "what-if on them.",
            "run_data_script": "For a bank file with no saved layout, a small "
                               "script can compute over it in the sandbox.",
            "my_files": "Find the exported file first if Jarvis does not already "
                        "know which one it is.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on spending in Settings under \"Connected accounts & "
                       "home\", or add \"my_spending\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_spending.py",
                    "backend/jarvis_money_parse.py",
                    "backend/jarvis_asks_first.py"],
    },

    "retirement_whatif": {
        "id": "retirement_whatif",
        "title": "Retirement what-if (ranges, never one number)",
        "what": "Takes a few numbers the owner types and plays out ten thousand "
                "made-up futures with the same fixed random seed, then answers "
                "only as ranges - \"in about 78 of 100 simulated futures the "
                "money lasts to age 95\".",
        "gives": [
            "See roughly how long savings might last, as a range rather than a "
            "false single answer",
            "Compare two plans - retire earlier, save more - side by side",
            "Understand the effect of one changed number on the whole picture",
        ],
        "touches": "none",
        "limits": [
            "It reads nothing, writes nothing and opens no connection: the "
            "numbers are all it knows",
            "It never gives one exact figure, and every answer carries \"This is a "
            "simplified what-if, not financial advice\" - added by the code, not "
            "left to the model",
            "It is a simplified model in today's money, not a forecast",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "calculator": "The simulation gives ranges; the calculator does plain "
                          "arithmetic on the numbers behind them.",
            "my_spending": "What the owner actually spends is the input worth "
                           "checking before a what-if.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on the retirement what-if in Settings under "
                       "\"Connected accounts & home\", or add \"retirement_whatif\" "
                       "to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_retirement.py",
                    "backend/jarvis_asks_first.py"],
    },

    "home_read": {
        "id": "home_read",
        "title": "Read your home's state",
        "what": "Reads the state of named Home Assistant entities - is the "
                "kitchen light on, is the back door locked, what does a sensor "
                "say - through Home Assistant's own REST API and the owner's own "
                "long-lived token.",
        "gives": [
            "Answer \"is the garage door open?\" from the real sensor",
            "Check several devices' states in one call (up to 20)",
            "See the state before deciding to change anything",
        ],
        "touches": "network service",
        "limits": [
            "Read-only - changing anything is home_control and gets its own card",
            "It needs a Home Assistant address and a long-lived access token the "
            "owner generates themselves; there is no cloud account",
            "Only entities the owner names are read, at most 20 in one call",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "home_control": "Read the state, then call a service to change it.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on home in Settings under \"Connected accounts & "
                       "home\", or add \"home_read\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_home.py",
                    "backend/jarvis_asks_first.py"],
    },

    "home_control": {
        "id": "home_control",
        "title": "Change something in your home",
        "what": "Calls one Home Assistant service on one entity, or on up to ten "
                "entities of the same kind, after one card. That is how a light "
                "goes on, a brightness is set or a scene runs.",
        "gives": [
            "Turn lights, switches or a scene on or off by asking",
            "Set a value - brightness, colour, a thermostat set point",
            "Change several devices of the same kind with one approved step",
        ],
        "touches": "network service",
        "limits": [
            "Locks, alarms, doors and covers are one entity per call - never batched",
            "Every call is one approval card, and its tier is \"ask\"",
            "It needs the Home Assistant address and token, the same as home_read",
            "It calls a service the owner's own Home Assistant exposes; it cannot "
            "invent a device that is not there",
        ],
        "combines": {
            "home_read": "Check the state first, then change it.",
            "propose_plan": "A plan can carry a home step, and a risky one still "
                            "gets its own card mid-run.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on home control in Settings under \"Connected accounts "
                       "& home\", or add \"home_control\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_home.py",
                    "backend/jarvis_asks_first.py"],
    },

    "append_logseq_journal": {
        "id": "append_logseq_journal",
        "title": "Add a line to today's Logseq journal",
        "what": "Adds one entry to today's journal page in the owner's Logseq "
                "graph, in the owner's own words. It only ever adds.",
        "gives": [
            "Capture a thought or a decision into the journal without opening Logseq",
            "Log something as it happens, by voice or by typing",
            "Keep the daily journal as the one place the day is recorded",
        ],
        "touches": "files",
        "limits": [
            "It only adds - it never edits an existing entry or deletes one",
            "Today's page only; it does not open another date or another page",
            "A note write in a turn shaped by outside text (a page or an email was "
            "just read) changes nothing; the owner can type or say it instead",
            "It needs a Logseq graph configured, and its name in `[tools].enabled`",
        ],
        "combines": {
            "append_obsidian_daily": "The same add-only write for the other app's "
                                     "daily note - the owner's own choice of where "
                                     "the day lives.",
            "notes_search": "Search what is already written, then add today's line.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on note writing in Settings, or add "
                       "\"append_logseq_journal\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_note_capture.py",
                    "backend/rebuilt/jarvis-framework.toml",
                    "backend/jarvis_asks_first.py"],
    },

    "append_obsidian_daily": {
        "id": "append_obsidian_daily",
        "title": "Add a line to today's Obsidian daily note",
        "what": "Adds one entry to today's daily note in the owner's Obsidian "
                "vault, in the owner's own words. It only ever adds.",
        "gives": [
            "Add to the daily note from chat or voice, without opening Obsidian",
            "Keep a running log in the note the owner already reads each day",
            "Capture something quickly and have it in the vault straight away",
        ],
        "touches": "files",
        "limits": [
            "It only adds - it never edits or removes an existing line",
            "Today's daily note only",
            "A note write in a turn shaped by outside text changes nothing",
            "It needs the Obsidian vault configured, and its name in `[tools].enabled`",
        ],
        "combines": {
            "create_joplin_note": "A daily line goes here; a separate note with its "
                                  "own title goes to Joplin.",
            "notes_search": "Find what is written, then add today's line.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on note writing in Settings, or add "
                       "\"append_obsidian_daily\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_note_capture.py",
                    "backend/rebuilt/jarvis-framework.toml",
                    "backend/jarvis_asks_first.py"],
    },

    "create_joplin_note": {
        "id": "create_joplin_note",
        "title": "Create one new Joplin note",
        "what": "Creates one new note in Joplin with a title, a body and, if the "
                "owner names one, an existing notebook to file it in.",
        "gives": [
            "Keep a note with its own title rather than a line in a daily page",
            "File a note into a notebook the owner already has",
            "Turn something said in chat into a real, findable note",
        ],
        "touches": "network service",
        "limits": [
            "It never edits an existing note and never creates a notebook",
            "One note per call, and a notebook has to already exist by its exact name",
            "A note write in a turn shaped by outside text changes nothing",
            "It needs Joplin's Web Clipper token, and its name in `[tools].enabled`",
        ],
        "combines": {
            "notes_search": "Search the existing notes, then create the new one "
                            "beside them.",
            "append_obsidian_daily": "A titled note goes here; a line in today's "
                                     "page goes to the daily note.",
        },
        "tier": "switchable",
        "enable_hint": "Turn on note writing in Settings, or add "
                       "\"create_joplin_note\" to [tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_note_capture.py",
                    "backend/rebuilt/jarvis-framework.toml",
                    "backend/jarvis_asks_first.py"],
    },

    "propose_plan": {
        "id": "propose_plan",
        "title": "One card, several steps",
        "what": "Proposes a short plan of up to eight steps that use Jarvis's "
                "other tools, and shows the whole sequence on ONE approval card. "
                "A step the model marks risky, or a step that depends on an "
                "earlier step's result, gets its own separate card as well.",
        "gives": [
            "Approve a multi-step job once, after reading every step on one card",
            "Chain a job: use one step's result in a later step",
            "See exactly what would run, in order, before anything runs",
        ],
        "touches": "settings",
        "limits": [
            "It ships OFF until a real, recent run of the tool evaluation on the "
            "current everyday model has cleared the module's two safety bars - "
            "until then the tool is refused before it even prepares",
            "Send email, save a draft, and set timers, reminders or to-do items can "
            "never be steps of a plan",
            "A plan is built only from the owner's own words, never after reading "
            "outside text",
            "The approving card is `run_plan` at tier \"ask\", and each risky step "
            "then asks again on its own card",
        ],
        "combines": {
            "control_computer": "One window's steps can be planned together, with a "
                                "risky click asking again mid-run.",
            "my_files": "A plan can find the file in one step and read it in the next.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"propose_plan\" to [tools].enabled, and the plan "
                       "module's own measured gate must have passed on the model "
                       "you use now.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_plan.py",
                    "backend/jarvis_asks_first.py",
                    "tools/tool_eval/ollama_tool_eval.py"],
    },

    "set_timer": {
        "id": "set_timer",
        "title": "Start a countdown timer",
        "what": "Starts a countdown timer on this PC, with an optional short "
                "label like \"pasta\". Jarvis usually answers a plain timer from "
                "the owner's own words before any model is asked; this tool is "
                "for the phrasings that small grammar does not understand.",
        "gives": [
            "Have a timer started and announced without touching a phone",
            "Time something with a label so the alert means something",
            "Set a short timer in seconds (0.5 minutes is 30 seconds)",
        ],
        "touches": "settings",
        "limits": [
            "It runs on this PC's clock: with the PC asleep or off, the timer "
            "does not fire on time",
            "The tool is not put to the approval gate: a plain timer needs no card, "
            "because it changes nothing Jarvis holds",
            "In a turn shaped by outside text (a page or an email was read) it "
            "sets nothing, so a web page cannot set an alarm",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "coming_up": "Set one, then read back everything pending in one list.",
            "set_reminder": "A timer counts down; a reminder is tied to a clock time "
                            "or repeats.",
        },
        "tier": "switchable",
        "enable_hint": "Turn timers on in Settings, or add \"set_timer\" to "
                       "[tools].enabled. A plain timer needs no card.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_schedule.py",
                    "backend/jarvis_quick.py", "backend/jarvis_asks_first.py"],
    },

    "set_reminder": {
        "id": "set_reminder",
        "title": "Set a reminder or an alarm",
        "what": "Sets a reminder or a wake-up alarm on this PC, once or "
                "repeating, from plain English - \"tomorrow at 6pm\", \"in 20 "
                "minutes\", or \"every weekday at 7\".",
        "gives": [
            "Be reminded of something at a real time, without a phone app",
            "Set a repeating alarm for a fixed time on chosen weekdays",
            "Have the answer say the next few times, so a repeat is checkable",
        ],
        "touches": "settings",
        "limits": [
            "It runs on this PC's clock, so a reminder cannot fire while the PC is "
            "off",
            "A plain one-time or repeating reminder needs no approval card; only "
            "the repeats that read email or the calendar raise the scheduler's card",
            "In a turn shaped by outside text it sets nothing",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "calendar_read": "See the event, then set a reminder a little before it.",
            "coming_up": "Read everything pending back in one list.",
            "set_timer": "A countdown for now; a reminder for a clock time.",
        },
        "tier": "switchable",
        "enable_hint": "Turn reminders on in Settings, or add \"set_reminder\" to "
                       "[tools].enabled. A plain reminder needs no card.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_schedule.py",
                    "backend/jarvis_asks_first.py"],
    },

    "todo_add": {
        "id": "todo_add",
        "title": "Add one item to the to-do list",
        "what": "Adds one item to the owner's to-do list on this PC, in their own "
                "words. The list is theirs: nothing here decides what should be "
                "on it.",
        "gives": [
            "Capture a task the moment it is mentioned",
            "Keep one list instead of sticky notes in three places",
            "Add something from a conversation without leaving it",
        ],
        "touches": "settings",
        "limits": [
            "It only adds; deleting and clearing are the owner's own screen, not a tool",
            "The list lives on this PC, so it is not on the phone when the PC is off",
            "In a turn shaped by outside text it adds nothing",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "todo_done": "Add a task now, mark it done when it is done.",
            "coming_up": "Add one, then read the whole list back.",
        },
        "tier": "switchable",
        "enable_hint": "Turn the to-do list on in Settings, or add \"todo_add\" to "
                       "[tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_schedule.py",
                    "backend/jarvis_asks_first.py"],
    },

    "todo_done": {
        "id": "todo_done",
        "title": "Mark a to-do item done",
        "what": "Marks one item on the owner's to-do list as done, matched by its "
                "own words or enough of them to pick it out.",
        "gives": [
            "Close a task by saying it is done",
            "Keep the list honest without opening anything",
            "Mark something done from the middle of another job",
        ],
        "touches": "settings",
        "limits": [
            "One item per call, and the words have to pick out an existing item",
            "Marking done only makes things quieter - it deletes nothing",
            "In a turn shaped by outside text it changes nothing",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "todo_add": "The other half of the same list.",
            "coming_up": "Read the list, then close the item that is finished.",
        },
        "tier": "switchable",
        "enable_hint": "Turn the to-do list on in Settings, or add \"todo_done\" to "
                       "[tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_schedule.py",
                    "backend/jarvis_asks_first.py"],
    },

    "coming_up": {
        "id": "coming_up",
        "title": "What is coming up",
        "what": "Lists the owner's timers, alarms, reminders and to-do list on "
                "this PC in one place - the same \"Coming up\" they see on screen.",
        "gives": [
            "Ask what is pending and get one real list",
            "Check a reminder landed before relying on it",
            "See the day's commitments that Jarvis itself is holding",
        ],
        "touches": "settings",
        "limits": [
            "It reads only what Jarvis holds on this PC - not the calendar and not "
            "the phone's alarms",
            "Read-only: it changes nothing",
            "In a turn shaped by outside text it still reads, but sets nothing",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "set_reminder": "Set it, then read it back to be sure.",
            "goals_list": "The day's items from here, the longer-term goals from "
                          "goals_list.",
        },
        "tier": "switchable",
        "enable_hint": "Turn it on in Settings, or add \"coming_up\" to "
                       "[tools].enabled.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_schedule.py",
                    "backend/jarvis_asks_first.py"],
    },

    "goals_list": {
        "id": "goals_list",
        "title": "List your goals",
        "what": "Lists the owner's goals on this PC, each with its newest "
                "progress lines, and can include the ones already done or "
                "stopped.",
        "gives": [
            "Ask what goals are open and see them with their latest progress",
            "Look back at a goal that was finished or stopped",
            "Keep progress and the goal in the same place",
        ],
        "touches": "settings",
        "limits": [
            "Read-only: it changes no goal",
            "It shows the goals Jarvis holds on this PC, not anything from a "
            "calendar or a project tool",
            "Done and stopped goals are left out unless they are asked for",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "goal_progress": "See the goal, then record today's progress on it.",
            "goal_add": "Read what is already there, then add a new goal.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"goals_list\" to [tools].enabled. The goals tools have "
                       "no in-app switch.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_goals.py",
                    "backend/jarvis_asks_first.py"],
    },

    "goal_add": {
        "id": "goal_add",
        "title": "Add a goal",
        "what": "Adds one goal in the owner's own words, with an optional target "
                "like \"100 km\" and an optional longer note. The goal is open "
                "straight away.",
        "gives": [
            "Write down something worth working towards, in one sentence",
            "Attach a measurable target to it",
            "Start tracking progress without setting up a project",
        ],
        "touches": "settings",
        "limits": [
            "One goal per call, in the owner's words - it does not invent or "
            "reword the goal",
            "There is deliberately no tool that deletes a goal: the owner's own "
            "screen has Remove",
            "It changes nothing in a turn shaped by outside text",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "goal_progress": "Add the goal, then record the first progress line.",
            "goals_list": "Add it, then read the list back.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"goal_add\" to [tools].enabled. The goals tools have "
                       "no in-app switch.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_goals.py",
                    "backend/jarvis_asks_first.py"],
    },

    "goal_progress": {
        "id": "goal_progress",
        "title": "Record progress on a goal",
        "what": "Adds one progress line to one of the owner's goals, with an "
                "optional number and date. A progress line is added to the log "
                "and never replaces an earlier one.",
        "gives": [
            "Say what happened today and have it land on the right goal",
            "Record a number against a target (5 km, 3 chapters)",
            "Build a real history instead of a single status",
        ],
        "touches": "settings",
        "limits": [
            "It appends: an earlier progress line is never replaced or deleted",
            "The goal has to be matched by its words, and the words have to pick "
            "out one existing goal",
            "It changes nothing in a turn shaped by outside text",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "goals_list": "Read the goal and its newest lines, then add today's.",
            "goal_done": "Record the last progress, then close the goal - which "
                         "keeps the log.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"goal_progress\" to [tools].enabled. The goals tools "
                       "have no in-app switch.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_goals.py",
                    "backend/jarvis_asks_first.py"],
    },

    "goal_done": {
        "id": "goal_done",
        "title": "Mark a goal done",
        "what": "Marks one of the owner's goals as done. The goal is kept, with "
                "its whole progress log - nothing is deleted.",
        "gives": [
            "Close a goal by saying it is finished",
            "Keep the record of how it went, not just whether it ended",
            "Retire a goal without losing what was written along the way",
        ],
        "touches": "settings",
        "limits": [
            "It closes, it never deletes: the goal and its progress stay",
            "The goal has to be matched by its own words",
            "It changes nothing in a turn shaped by outside text",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "goal_progress": "Record the final progress, then close the goal.",
            "goals_list": "See the open goals, then close the finished one.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"goal_done\" to [tools].enabled. The goals tools have "
                       "no in-app switch.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_goals.py",
                    "backend/jarvis_asks_first.py"],
    },

    "change_setting": {
        "id": "change_setting",
        "title": "Change one of Jarvis's own settings",
        "what": "Changes one setting by the name the owner uses - a switch on or "
                "off, a setting with named choices like faster/normal/headless, "
                "the wake word, or which browser Jarvis uses.",
        "gives": [
            "Turn a feature on or off by talking, without hunting for the screen",
            "Change a mode or a choice without editing a file",
            "Change the wake word or the browser Jarvis drives",
        ],
        "touches": "settings",
        "limits": [
            "The setting's OWN setter is the gate: a cosmetic change applies at "
            "once, and anything that loosens a rule, reads or reaches more, or "
            "touches privacy raises its own approval card - one change, never two "
            "cards",
            "A turn shaped by outside text changes nothing here",
            "An unknown or ambiguous setting name is answered in words with no "
            "card, because there is nothing to approve",
            "A change still waiting on a card is reported as waiting, never as done",
        ],
        "combines": {
            "feature_guide": "Find out what a feature is and where it lives, then "
                             "change the setting itself.",
            "setup_quiz": "The quiz works out which settings suit the owner; this "
                          "applies one for certain.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` "
                       "list. The change itself follows the setting's own rules.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_settings_registry.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "feature_guide": {
        "id": "feature_guide",
        "title": "Explain one of Jarvis's features",
        "what": "Answers \"what is this feature?\", \"where is it?\" and \"is it "
                "on?\" from the owner's own feature list - 140 rows turned into a "
                "shipped module - rather than from a guess.",
        "gives": [
            "Explain what a feature is and where it is switched on, in the owner's "
            "own words",
            "Say whether a feature is currently on",
            "List the feature groups when the owner is not sure what to call one",
        ],
        "touches": "none",
        "limits": [
            "Read-only, so it raises no card",
            "It reports only what is written down in that list - it will not guess "
            "about a feature the list does not hold",
            "It explains and reports; it never switches anything",
        ],
        "combines": {
            "change_setting": "Understand the feature first, then change its setting.",
            "self_portrait": "The portrait says what is installed here; the guide "
                             "says what each named feature does.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_feature_guide.py",
                    "backend/jarvis_feature_catalogue.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "setup_quiz": {
        "id": "setup_quiz",
        "title": "Explain the Personalize Jarvis quiz",
        "what": "Explains the questions in the \"Personalize Jarvis\" questionnaire "
                "- 25 questions in seven sections - and can record ONE answer as a "
                "draft of the owner's choice. It records the draft; it never "
                "applies a setting.",
        "gives": [
            "Have a quiz question explained before answering it",
            "See the options for one question and what each one means",
            "Say the choice out loud and have it saved as a draft to confirm on "
            "the screen",
        ],
        "touches": "files",
        "limits": [
            "It never applies a setting: it records the choice as a DRAFT through "
            "the questionnaire's own cardless progress route, and applying it is "
            "the owner's next step",
            "One question and at most one option per call",
            "Every question maps to a setter that already exists - there is no "
            "quiz-only setting and no new gate action",
            "Leaving the answer out just lists the sections and questions",
        ],
        "combines": {
            "change_setting": "Stage the choice in the quiz, or change that one "
                              "setting directly - both end in the same setter.",
            "feature_guide": "Understand a feature, then answer the question about it.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"setup_quiz\" to [tools].enabled. The quiz's own card "
                       "in the apps is the normal way in.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_setup.py",
                    "backend/jarvis_asks_first.py"],
    },

    "refresh_abilities": {
        "id": "refresh_abilities",
        "title": "Re-read what Jarvis can do",
        "what": "Tells Jarvis to re-read its own list of abilities from what is "
                "actually on this PC, so the next answer is built from the current "
                "code rather than from a list read at start-up. It refreshes the "
                "stored self-portrait and hands back its one-sentence summary.",
        "gives": [
            "Pick up a change that landed while Jarvis was running",
            "Stop answering from an out-of-date idea of what it can do",
            "Have the next answer use the real set of abilities",
        ],
        "touches": "files",
        "limits": [
            "Read-only on this PC: it re-reads the portrait's own state file, "
            "writes nothing and raises no approval card",
            "It re-reads what is on disk; it cannot make a missing module appear",
            "It changes no setting and installs nothing",
        ],
        "combines": {
            "self_portrait": "Refresh the list, then read the portrait built from it.",
            "feature_guide": "Refresh what exists, then explain a named feature.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_feature_guide.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "self_portrait": {
        "id": "self_portrait",
        "title": "What Jarvis is made of on this PC",
        "what": "Reports what Jarvis is made of right now - the settings cards, the "
                "menu areas and the abilities that are really installed - by "
                "importing the two registries that already exist, so it cannot "
                "describe a place the apps do not have.",
        "gives": [
            "Say which Settings areas and menus exist on this PC",
            "Say what is installed and what is missing, in plain words",
            "Answer \"what are you made of?\" without inventing a component",
        ],
        "touches": "files",
        "limits": [
            "Read-only on this PC - it reads its own portrait state file and the "
            "chat log's location, writes nothing, and raises no card",
            "Every place it names comes from jarvis_settings_registry.SECTIONS or "
            "jarvis_menus.MENUS - never a hand-written fourth list",
            "It describes; it does not open, change or switch anything",
        ],
        "combines": {
            "conversation_find": "See what Jarvis is made of, then find the chat "
                                 "where it was discussed.",
            "refresh_abilities": "Re-read the abilities first, then read the portrait.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_self_portrait.py",
                    "backend/jarvis_settings_registry.py", "backend/jarvis_menus.py"],
    },

    "conversation_find": {
        "id": "conversation_find",
        "title": "Find an old conversation",
        "what": "Finds conversations kept on this PC by words they were about, or "
                "lists the newest ones. History is kept encrypted on the PC by "
                "default, with a switch to turn it off.",
        "gives": [
            "Find the chat where something was decided",
            "Look back at what was said about a subject, in the owner's own words",
            "List the newest conversations when the words are not remembered",
        ],
        "touches": "files",
        "limits": [
            "Only conversations kept on this PC - with history switched off there "
            "is nothing to find beyond the live turns held in memory",
            "Read-only: it never deletes, edits or clears anything",
            "Clearing a kept conversation is not a tool at all: it is a route and a "
            "shortcut behind its own card",
        ],
        "combines": {
            "conversation_open": "Find the conversation by its words, then open it.",
            "memory_search": "Find the fact in memory, then find where it was said.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` "
                       "list; what it can find depends on the history switch.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_chat_log.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "conversation_open": {
        "id": "conversation_open",
        "title": "Open an old conversation",
        "what": "Opens one kept conversation by the id conversation_find returned, "
                "so Jarvis can read what was actually said in it.",
        "gives": [
            "Read a past conversation instead of guessing what was said",
            "Quote the owner's own earlier words",
            "Carry a decision from an old chat into the current one",
        ],
        "touches": "files",
        "limits": [
            "It needs the id conversation_find gave - it will not invent one",
            "Read-only: it cannot clear, delete or change a conversation",
            "Only conversations this PC kept",
        ],
        "combines": {
            "conversation_find": "The other half of the same job: find, then open.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is in the shipped `[tools].enabled` list.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_chat_log.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "connect_account": {
        "id": "connect_account",
        "title": "Connect an account",
        "what": "Raises ONE card that takes a password or a token and puts it "
                "straight into Windows Credential Manager, then runs one real test "
                "against that service. It is how \"connect my calendar\" becomes a "
                "working connection instead of a set of instructions.",
        "gives": [
            "Connect a calendar, a CalDAV server or GitHub by talking, not by "
            "editing files",
            "Keep the secret in Credential Manager instead of a text file",
            "Know the connection really works, because one real test runs",
        ],
        "touches": "network service, settings",
        "limits": [
            "The secret is typed by the OWNER on the card, never by the model - the "
            "tool raises the card and never reads the value",
            "Three services only: calendar, caldav, github",
            "A failed test changes nothing and says why",
            "Not in the shipped `[tools].enabled` list",
        ],
        "combines": {
            "calendar_read": "Connect the calendar, then read it.",
            "github_search": "Connect GitHub, then run the authenticated, separately "
                             "tiered research action.",
        },
        "tier": "settings-file",
        "enable_hint": "Add \"connect_account\" to [tools].enabled. Its card is the "
                       "only way a secret is entered.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_connect_account.py",
                    "backend/jarvis_asks_first.py"],
    },

    "rea_investigate": {
        "id": "rea_investigate",
        "title": "Inspect a program, app or binary (reverse engineering)",
        "what": "REA stands for \"Reverse Engineer Anything\", a real tool server "
                "(pinned at npm rea-agents 6.7.0, MIT) with 207 tools of its own. "
                "Jarvis exposes ONE tool with eight actions over it, so the owner "
                "can statically inspect a program, an Android app, a captured "
                "session or a database - what it is built from, without running it.",
        "gives": [
            "See what a JavaScript or Electron program is made of",
            "Inspect an APK, or open a native binary and read its overview",
            "Read a stored web capture (HAR or SAZ) or a SQLite database",
            "List a binary's strings, cross-references or one function",
            "Ask the doctor action what this PC is actually able to inspect",
        ],
        "touches": "files",
        "limits": [
            "Its own switch ships OFF (`[rea] enabled = false`), its name must "
            "also be in `[tools].enabled`, and every call is ONE approved card "
            "(its action resolves to `run_shell_on_host`, tier \"ask\") - nothing "
            "is inspected before a person's yes",
            "It NEVER attaches to a running program: the four live capture tools "
            "are refused by name before a session can start, and so are the six "
            "adb device mutators, every debugger session and script export",
            "Targets must be inside \"Folders Jarvis may look in\" and must not be "
            "a private place - a credentials store, a browser profile or Jarvis's "
            "own data folder is refused",
            "The pinned REA package is a one-time hand install at exactly 6.7.0 "
            "with Node 22.19 or newer; APK and native decompilation also need JADX "
            "or Ghidra, which the owner supplies",
        ],
        "combines": {
            "my_files": "Find the APK or the binary in the folders you listed, then "
                        "inspect that exact file.",
        },
        "tier": "off-by-default",
        "enable_hint": "Turn on the REA switch in Settings (it is `[rea] enabled = "
                       "true` in jarvis-framework.toml) AND add \"rea_investigate\" "
                       "to [tools].enabled. Installing REA itself is a separate, "
                       "one-time hand install of the pinned package.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_rea.py",
                    "backend/rebuilt/jarvis-framework.toml",
                    "jarvis-backend/jarvis_gate.py", "backend/jarvis_documents.py"],
    },

    "approve_web_search_for_conversation": {
        "id": "approve_web_search_for_conversation",
        "title": "Approve web search for this conversation",
        "what": "Asks the owner, once, to let web searches run for the rest of this "
                "conversation without a card for every search. It raises the card; "
                "the person's yes is the permission.",
        "gives": [
            "Do a research session without a card per search",
            "Answer a natural \"you have my approval to search the web\" with a real "
            "card instead of a claim",
            "Keep the approval bounded to the conversation it was given in",
        ],
        "touches": "settings",
        "limits": [
            "It grants nothing by itself - it only raises ONE card, and a person's "
            "yes is what actually permits the searches",
            "The approval is conversation-scoped: a new chat starts without it",
            "It has no Settings switch of its own; it rides with web search, and "
            "turning web search off takes it too",
        ],
        "combines": {
            "web_search": "Approve once, then search several times in that conversation.",
            "stop_web_search_approval": "The approval has an instant stop beside it.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is offered whenever web search is, "
                       "because the ask is part of that ability, not a feature of "
                       "its own.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_asks_first.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },

    "stop_web_search_approval": {
        "id": "stop_web_search_approval",
        "title": "Stop web search approval",
        "what": "Instantly takes away the conversation's web-search approval, so "
                "the next search has to ask again. It only ever takes permission "
                "away, so it needs no card.",
        "gives": [
            "Stop the searching now, in one sentence",
            "Take back an approval without waiting for the chat to end",
            "Keep the owner in charge of a long research session",
        ],
        "touches": "settings",
        "limits": [
            "It only removes permission - it can never grant anything",
            "It raises no card, because nothing it does can loosen a rule",
            "It affects this conversation's approval, not the web search switch itself",
        ],
        "combines": {
            "web_search": "Stop the standing approval; each later search asks again.",
            "approve_web_search_for_conversation": "The grant and its stop, in one place.",
        },
        "tier": "always-available",
        "enable_hint": "Always available - it is offered whenever web search is.",
        "sources": ["backend/jarvis_agent.py", "backend/jarvis_asks_first.py",
                    "backend/rebuilt/jarvis-framework.toml"],
    },
}


#: Capability families. Every tool in `PROFILES` belongs to exactly one, which
#: `backend/test_tool_profiles.py` enforces - so "the family owns it" is never a
#: claim without a home.
FAMILIES: dict = {

    "memory": {
        "title": "Memory - what Jarvis has learned about you",
        "what": "The facts Jarvis has picked up from the owner's own words: names, "
                "preferences, projects, how they like things done. This family is "
                "the read side of that store.",
        "tools": ["memory_search"],
        "impact": "Without it Jarvis can only answer from the current conversation "
                  "and the model's general knowledge. With it, an answer can be "
                  "built on something the owner said weeks ago - their sister's "
                  "name, the model they prefer, a decision already made - so the "
                  "owner stops repeating themselves. It is also what keeps answers "
                  "consistent: the same fact comes back the same way.",
        "limits": ["Learning happens from the owner's own words only - never from a "
                   "page, an email, a document, a note or tool output",
                   "Sensitive topics wait for the owner's yes unless they turned "
                   "that on",
                   "A fact can be forgotten, and forgetting cannot be undone"],
    },

    "files": {
        "title": "Files and documents",
        "what": "Finding the owner's own files, reading them in the formats they "
                "actually use, computing over one, and sending one to the phone. "
                "Everything here is bounded by the folder list the owner sets.",
        "tools": ["my_files", "file_read", "run_data_script", "send_file_to_phone"],
        "impact": "This is the difference between Jarvis talking about documents and "
                  "Jarvis using them: it can find the right PDF, read one part of a "
                  "long report, add up a CSV exactly, and put the finished file on "
                  "the phone. In practice that removes the copy-paste step - the "
                  "owner asks a question and the answer comes from the file itself.",
        "limits": ["Only inside \"Folders Jarvis may look in\"; a protected item is "
                   "refused before it is opened",
                   "Reading is read-only, and the script sandbox has no network and "
                   "writes nothing",
                   "One part of one file per call - a long document arrives in pieces"],
    },

    "web": {
        "title": "The web - searching it and reading it",
        "what": "Searching the public web through the provider the owner chose, "
                "reading the words of one page they named, and the two tools that "
                "grant and withdraw a conversation's search approval.",
        "tools": ["web_search", "read_web_page",
                  "approve_web_search_for_conversation",
                  "stop_web_search_approval"],
        "impact": "It lets Jarvis answer something it cannot know from the PC - a "
                  "current version, a price, a fact from outside. The split matters: "
                  "a search is cheap and returns snippets, while reading a whole page "
                  "is a named way out of the PC and asks every time. Because the "
                  "provider is fixed and SearXNG can run on this PC, the owner can "
                  "keep the search itself on their own machine.",
        "limits": ["A search returns five results - title, link and snippet, never "
                   "the page text",
                   "Fetched page words are outside text: never instructions, never "
                   "learned as a fact",
                   "Switching web search off means the model is not offered the "
                   "tool at all, not merely refused"],
    },

    "email-and-calendar": {
        "title": "Email and calendar",
        "what": "Reading the inbox and the calendar, sending one email, saving one "
                "draft, tidying a checked list of messages, and the one card that "
                "connects an account.",
        "tools": ["calendar_read", "email_check", "send_email", "draft_email",
                  "tidy_inbox", "connect_account"],
        "impact": "This is where Jarvis stops being a chat window: it can tell the "
                  "owner what arrived and what is on, then act on it - answer a "
                  "message, save a draft they can check in their own mail program, "
                  "or quieten a noisy inbox. Every write is one card that shows the "
                  "whole email or every message it will touch, so the owner's yes is "
                  "informed rather than hopeful.",
        "limits": ["Reading is read-only; nothing marks, moves or deletes a message "
                   "behind the owner's back",
                   "\"Trash\" only ever means Trash, with ten minutes of Undo - "
                   "there is no permanent delete",
                   "Sending and tidying run on the local model only, and a person's "
                   "yes is required every time"],
    },

    "home-and-phone": {
        "title": "Your home and your phone",
        "what": "Reading and changing Home Assistant devices, driving the paired "
                "Android phone with individual adb commands, and managing the list "
                "of apps Jarvis may open there.",
        "tools": ["home_read", "home_control", "control_phone", "phone_apps"],
        "impact": "It extends Jarvis past the PC into the two places the owner "
                  "actually lives: the house and the phone in their pocket. Asking "
                  "whether the back door is locked, turning a light off, or opening "
                  "an allowed app on the phone all become one sentence - each one "
                  "behind a card that prints exactly the service call or the exact "
                  "adb command.",
        "limits": ["The phone allow-list ships empty, so nothing on the phone is "
                   "reachable until the owner fills it in",
                   "Locks, alarms, doors and covers are one entity per call, never batched",
                   "No live mirrored phone session: a card can only authorise steps "
                   "that are already listed"],
    },

    "computer-control": {
        "title": "Controlling programs and browser pages",
        "what": "Clicking and typing in another Windows program, and driving one "
                "browser tab - both by naming an element rather than guessing a "
                "screen position, and both planned fully before anything happens.",
        "tools": ["control_computer", "browser_control"],
        "impact": "This is what lets Jarvis finish a job that has no API: a form in "
                  "a desktop program, a support widget on a web page. Because the "
                  "whole plan is printed on one card and a missing element is "
                  "reported rather than guessed, the owner can see the job before it "
                  "runs - which is the difference between automation and a standing "
                  "grant.",
        "limits": ["One window or one tab per plan, with every step on one card",
                   "No perceive-act loop: it runs the approved steps and stops",
                   "Both ship off - one needs the second card's browser lane or the "
                   "headless engine, the other needs its name in the tool list"],
    },

    "notes": {
        "title": "Notes - Obsidian, Joplin and Logseq",
        "what": "Searching the owner's own notes, and the three add-only writes: "
                "today's Logseq journal, today's Obsidian daily note, and a new "
                "Joplin note.",
        "tools": ["notes_search", "append_logseq_journal", "append_obsidian_daily",
                  "create_joplin_note"],
        "impact": "It makes the owner's notes a place Jarvis can read from and write "
                  "to, without becoming a second notebook. An answer can quote what "
                  "the owner actually wrote, and a thought can be captured into the "
                  "vault they already read each day - with the writes deliberately "
                  "one-way, so Jarvis can add but never rewrite history.",
        "limits": ["Search is read-only; the writes only ever add",
                   "One backend at a time - Joplin or Obsidian - and it needs that "
                   "app's own local token or vault path",
                   "In a turn shaped by outside text, note writes change nothing"],
    },

    "routines-and-goals": {
        "title": "Timers, reminders, to-dos and goals",
        "what": "The small structures that hold a day: countdown timers, alarms, "
                "one-time and repeating reminders, one to-do list, one \"Coming up\" "
                "view, and goals with a progress log.",
        "tools": ["set_timer", "set_reminder", "todo_add", "todo_done", "coming_up",
                  "goals_list", "goal_add", "goal_progress", "goal_done"],
        "impact": "This is the family that makes Jarvis useful when nothing is "
                  "happening: it remembers the thing at 6pm, keeps the list, and "
                  "keeps a goal's history so progress is visible rather than felt. "
                  "Most of it needs no approval card at all, because it changes "
                  "nothing Jarvis holds - and none of it can delete what the owner "
                  "wrote.",
        "limits": ["Everything here runs on this PC's clock, so nothing fires while "
                   "the PC is off",
                   "A turn shaped by outside text sets nothing, so a web page cannot "
                   "set an alarm",
                   "There is deliberately no tool that deletes a goal or a progress line"],
    },

    "money": {
        "title": "Money - spending, what-ifs and arithmetic",
        "what": "Adding up a bank export the owner provided, a retirement what-if "
                "played out as ranges, and the exact calculator both of them lean on.",
        "tools": ["calculator", "my_spending", "retirement_whatif"],
        "impact": "It turns a bank file into an answer the owner can act on - a "
                  "monthly total by category, a subscription that quietly went up, "
                  "the same charge taken twice - and lets them ask \"what if I retire "
                  "at 62?\" without pretending a single number is the truth. Every "
                  "figure is computed by code, so the model can describe the answer "
                  "but cannot invent one.",
        "limits": ["There is no bank connection: it reads a file the owner exported",
                   "Figures come from the file and the code; a sentence from the "
                   "model is dropped unless every number in it is in the table",
                   "The retirement answer is a simplified what-if in today's money, "
                   "never financial advice, and never one exact number"],
    },

    "coding": {
        "title": "Coding, development and inspecting a program",
        "what": "Checking GitHub for an existing library before building one, "
                "running a real command on this PC, planning several steps as one "
                "card, and statically inspecting a program, APK, capture or database.",
        "tools": ["github_search", "shell_exec", "propose_plan", "rea_investigate"],
        "impact": "This is the family the owner uses to actually build things with "
                  "Jarvis: it answers \"has someone already built this?\" with a "
                  "graded verdict, runs the installer or the build, and can inspect "
                  "a binary or an APK to see what it is made of. The plan card is "
                  "what makes a multi-step job approvable in one read instead of ten "
                  "separate clicks.",
        "limits": ["Every way out of the PC here is carded: shell commands always "
                   "ask, GitHub research needs an approved plan, and a plan's risky "
                   "step asks again",
                   "REA refuses live process capture, device changes and debugger "
                   "sessions by name, and the plan module ships off until a "
                   "measured evaluation passes",
                   "A plan can never contain email sending or scheduling steps"],
    },

    "self-knowledge": {
        "title": "Jarvis about itself, and what it may not touch",
        "what": "Explaining its own features and quiz, reporting what it is made of "
                "and what is installed, reading old conversations, listing and "
                "switching plugins, changing one of its own settings, and the "
                "\"Protected from Jarvis\" list.",
        "tools": ["plugin_list", "plugin_switch", "change_setting", "feature_guide",
                  "setup_quiz", "refresh_abilities", "self_portrait",
                  "conversation_find", "conversation_open", "protect_from_jarvis"],
        "impact": "It is what lets the owner change Jarvis by talking to Jarvis: to "
                  "understand a feature, find the setting, switch it, and see the "
                  "difference - and to look back at what was said last month. The "
                  "protection half is the counterweight: the owner can fence off a "
                  "folder or a program, and every other family asks that one check "
                  "before it reads or acts.",
        "limits": ["Almost all of it is read-only and raises no card; the two writes "
                   "are a plugin switch and a protection entry",
                   "It reports only what is written down in the real registries - it "
                   "cannot name a screen the apps do not have",
                   "Clearing a conversation is not in here: it is a route and a "
                   "shortcut behind its own card"],
    },
}


# --------------------------------------------------------------------------
#   Turning a question into an answer
# --------------------------------------------------------------------------
# Matching is deliberately dumb and deterministic: whole words only, longest
# phrase first, and an explicit tool id beats a nickname, which beats a family
# word. If nothing matches, the answer is None and the model answers - this
# module never guesses that a question was about a tool.

_TIER_SENTENCE = {
    "always-available": "On by default.",
    "switchable": "Off until you switch it on in the app.",
    "settings-file": "Off until you add it to the settings file yourself.",
    "off-by-default": "Off until you turn on its own switch.",
}

#: Nicknames the owner actually uses, mapped to the real tool id.
_ALIASES = (
    ("calculator", ("calculator", "arithmetic", "maths", "math", "sum")),
    ("memory_search", ("what do you know about me", "what you know about me",
                       "what do you remember", "do you remember", "memory",
                       "memories", "remember")),
    ("file_read", ("read a file", "read file", "text file")),
    ("run_data_script", ("run code", "data script", "python script", "sandbox",
                         "script")),
    ("shell_exec", ("run a command", "command line", "powershell", "terminal",
                    "shell", "command")),
    ("control_computer", ("screen control", "control the screen", "screen tool",
                          "my screen", "desktop program", "click", "screen")),
    ("control_phone", ("phone control", "control the phone", "my phone", "phone")),
    ("phone_apps", ("phone apps", "apps on my phone", "phone app list")),
    ("plugin_list", ("plugin list", "plugins", "plugin")),
    ("plugin_switch", ("turn on a plugin", "switch a plugin", "plugin switch")),
    ("browser_control", ("browser control", "browser tool", "browser")),
    ("github_search", ("github search", "github tool", "git hub", "github")),
    ("web_search", ("search the web", "search online", "web search", "internet",
                    "web")),
    ("read_web_page", ("read me this page", "read this page", "read a web page",
                       "read a page", "read page", "web page")),
    ("calendar_read", ("calendar read", "my calendar", "calendar")),
    ("email_check", ("read my email", "check email", "email check", "inbox",
                     "my email")),
    ("send_email", ("send email", "send an email")),
    ("draft_email", ("email draft", "draft email", "draft")),
    ("tidy_inbox", ("tidy inbox", "clean inbox", "tidy", "archive")),
    ("notes_search", ("search notes", "my notes", "obsidian", "joplin", "notes")),
    ("my_files", ("find a file", "find files", "my files", "documents",
                  "folders")),
    ("send_file_to_phone", ("send to phone", "file to phone", "send a file",
                            "send file")),
    ("protect_from_jarvis", ("block from jarvis", "protected", "protection",
                             "protect", "keep out")),
    ("my_spending", ("expenses", "budget", "bank", "money", "spending")),
    ("retirement_whatif", ("retirement", "pension", "retire")),
    ("home_read", ("home assistant", "home read", "read my home")),
    ("home_control", ("home control", "turn on the lights", "thermostat",
                      "lights", "light")),
    ("append_logseq_journal", ("logseq journal", "logseq", "journal")),
    ("append_obsidian_daily", ("obsidian daily", "daily note", "daily")),
    ("create_joplin_note", ("joplin note", "create a note", "new note")),
    ("propose_plan", ("plan card", "multi step", "several steps", "plan")),
    ("set_timer", ("countdown", "stopwatch", "timer")),
    ("set_reminder", ("remind me", "reminder", "alarm")),
    ("todo_add", ("add a task", "task list", "to do", "todo")),
    ("todo_done", ("to do done", "mark done", "finish a task")),
    ("coming_up", ("coming up", "what is pending", "my list")),
    ("goals_list", ("my goals", "goal list", "goals")),
    ("goal_add", ("add a goal", "new goal")),
    ("goal_progress", ("goal progress", "progress on a goal")),
    ("goal_done", ("goal done", "finish a goal")),
    ("change_setting", ("change a setting", "turn on a feature", "settings",
                        "setting")),
    ("feature_guide", ("feature guide", "explain a feature", "what is this feature")),
    ("setup_quiz", ("setup quiz", "questionnaire", "personalize", "quiz")),
    ("refresh_abilities", ("refresh abilities", "re read abilities")),
    ("self_portrait", ("self portrait", "what are you made of", "your parts")),
    ("conversation_find", ("find a conversation", "old conversation",
                           "past conversation", "chat history", "conversations")),
    ("conversation_open", ("open a conversation", "open conversation")),
    ("connect_account", ("connect my calendar", "set up github", "connect github",
                         "connect account", "connect an account")),
    ("rea_investigate", ("reverse engineering", "reverse engineer", "rea investigate",
                         "inspect a program", "inspect an app", "binary", "apk",
                         "rea")),
    ("approve_web_search_for_conversation", ("approve web search",
                                             "web search approval",
                                             "approve searching")),
    ("stop_web_search_approval", ("stop the search approval", "stop web search",
                                  "stop searching")),
)

#: Words that name a whole capability family rather than one tool.
_FAMILY_CUES = {
    "memory": ("memory", "memories", "remembering"),
    "files": ("document", "folder", "folders"),
    "web": ("internet", "online", "website", "web"),
    "email-and-calendar": ("email", "emails", "mail", "calendar"),
    "home-and-phone": ("house", "home", "devices"),
    "computer-control": ("computer", "pc", "desktop"),
    "notes": ("note", "notes", "journal"),
    "routines-and-goals": ("routines", "routine", "reminders", "goals"),
    "money": ("money", "finances", "savings"),
    "coding": ("coding", "programming", "development", "code"),
    "self-knowledge": ("yourself", "your abilities", "your features",
                       "your settings", "about yourself"),
}


def _norm(text) -> str:
    """Lower-case words only, so punctuation and spacing cannot change a match."""
    return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))


def _padded(text: str) -> str:
    return " " + text + " "


def _pairs() -> tuple:
    """Every (phrase, kind, id), longest phrase first - the matching order."""
    found = []
    for family_id, cues in _FAMILY_CUES.items():
        for cue in cues:
            found.append((_norm(cue), "family", family_id))
    for tool_id, aliases in _ALIASES:
        for alias in aliases:
            found.append((_norm(alias), "tool", tool_id))
    for tool_id in PROFILES:
        found.append((_norm(tool_id), "tool", tool_id))
    for family_id in FAMILIES:
        found.append((_norm(family_id), "family", family_id))
    # Longest phrase first, then tool before family, then the name itself, so
    # "screen control" beats "screen" and an exact id beats a family word.
    found.sort(key=lambda item: (-len(item[0]), 0 if item[1] == "tool" else 1,
                                 item[0]))
    return tuple(found)


_PAIRS = _pairs()


def _match(text):
    """(kind, id) for the clearest tool or family named, or (None, None)."""
    words = _padded(_norm(text))
    if not words.strip():
        return None, None
    for phrase, kind, name in _PAIRS:
        if _padded(phrase) in words:
            return kind, name
    return None, None


def names() -> list:
    """Every tool id and family id this module knows, sorted."""
    return sorted(list(PROFILES) + list(FAMILIES))


def profile(name):
    """The dossier for one tool id (or, failing that, one family id), or None."""
    if not isinstance(name, str):
        return None
    return PROFILES.get(name) or FAMILIES.get(name)


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > 40:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "..."


def _combos_in_family(family) -> list:
    """Real pairs THIS family contains, from the members' own `combines`.

    A pair is listed once whichever member declares it, in TOOLS order, so the
    same family always renders the same way."""
    inside = list(family["tools"])
    pairs = []
    seen = set()
    for tool in inside:
        for partner, why in PROFILES[tool]["combines"].items():
            if partner not in inside:
                continue
            key = tuple(sorted((tool, partner)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((tool, partner, why))
    return pairs


def _tool_answer(item) -> str:
    bits = ["%s (%s)." % (item["title"], item["id"]), item["what"]]
    bits.append("That gives you: " + "; ".join(item["gives"]) + ".")
    combos = item["combines"]
    if combos:
        bits.append("It works with other tools - " + " ".join(
            "%s: %s" % (other, why) for other, why in combos.items()))
    bits.append("Its honest limits: " + "; ".join(item["limits"]) + ".")
    bits.append(_TIER_SENTENCE[item["tier"]] + " " + item["enable_hint"])
    return " ".join(bits)


def _family_answer(item) -> str:
    members = ", ".join("%s (%s)" % (PROFILES[t]["title"], t)
                        for t in item["tools"])
    bits = ["%s." % item["title"], item["what"], "The tools in it are " + members + "."]
    pairs = _combos_in_family(item)
    if pairs:
        bits.append("They work together like this - " + " ".join(
            "%s + %s: %s" % (a, b, why) for a, b, why in pairs[:3]))
    bits.append("What it changes for you: " + item["impact"])
    bits.append("Watch for: " + "; ".join(item["limits"]) + ".")
    return " ".join(bits)


def answer_about(text):
    """A plain, deterministic answer about the tool or family `text` names.

    Returns None when no tool or family is clearly named, so the caller lets
    the model answer instead of putting words in its mouth."""
    kind, name = _match(text)
    if kind == "tool":
        return _tool_answer(PROFILES[name])
    if kind == "family":
        return _family_answer(FAMILIES[name])
    return None


def _tool_block(item, what, gives, limits, combos) -> str:
    lines = [
        "TOOL DOSSIER - %s (%s). %s" % (item["title"], item["id"],
                                        _TIER_SENTENCE[item["tier"]]),
        "Turn it on: %s" % item["enable_hint"],
        "What it is: %s" % what,
        "It lets you:",
    ]
    lines.extend("- " + g for g in gives)
    if limits:
        lines.append("It will not / cannot:")
        lines.extend("- " + l for l in limits)
    if combos:
        lines.append("Works with:")
        lines.extend("- %s: %s" % (other, why) for other, why in combos)
    lines.append("Checked against: " + ", ".join(item["sources"]))
    return "\n".join(lines)


def _family_block(item, what, limits, pairs) -> str:
    lines = [
        "CAPABILITY FAMILY - %s" % item["title"],
        "What it is: %s" % what,
        "Tools (all in this family): " + ", ".join(item["tools"]),
        "What it changes for you: %s" % item["impact"],
    ]
    if limits:
        lines.append("Limits:")
        lines.extend("- " + l for l in limits)
    if pairs:
        lines.append("Real combinations inside it:")
        lines.extend("- %s + %s: %s" % (a, b, why) for a, b, why in pairs)
    return "\n".join(lines)


def _hard_cut(text: str) -> str:
    if len(text) <= CONTEXT_LIMIT:
        return text
    return text[:CONTEXT_LIMIT]


def context_for(text):
    """`answer_about`'s match as a compact block for a system prompt, or None.

    Never longer than CONTEXT_LIMIT characters: the fields are shortened in a
    fixed order (the prose first, then the extra list items) so the same
    question always produces the same block."""
    kind, name = _match(text)
    if kind == "tool":
        item = PROFILES[name]
        what = item["what"]
        gives = list(item["gives"])
        limits = list(item["limits"])
        combos = list(item["combines"].items())
        while True:
            block = _tool_block(item, what, gives, limits, combos)
            if len(block) <= CONTEXT_LIMIT:
                return block
            if len(what) > 200:
                what = _shorten(what, 200)
                continue
            if len(limits) > 2:
                limits.pop()
                continue
            if len(combos) > 1:
                combos.pop()
                continue
            if len(gives) > 2:
                gives.pop()
                continue
            if len(what) > 110:
                what = _shorten(what, 110)
                continue
            if len(limits) > 1:
                limits.pop()
                continue
            if len(gives) > 1:
                gives.pop()
                continue
            return _hard_cut(block)
    if kind == "family":
        item = FAMILIES[name]
        what = item["what"]
        limits = list(item["limits"])
        pairs = _combos_in_family(item)
        while True:
            block = _family_block(item, what, limits, pairs)
            if len(block) <= CONTEXT_LIMIT:
                return block
            if len(what) > 200:
                what = _shorten(what, 200)
                continue
            if len(pairs) > 2:
                pairs.pop()
                continue
            if len(limits) > 2:
                limits.pop()
                continue
            if len(what) > 110:
                what = _shorten(what, 110)
                continue
            if len(pairs) > 1:
                pairs.pop()
                continue
            if len(limits) > 1:
                limits.pop()
                continue
            return _hard_cut(block)
    return None
