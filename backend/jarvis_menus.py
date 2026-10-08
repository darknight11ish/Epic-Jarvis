"""jarvis_menus.py - "Show or hide menus": the ONE list of menus both apps may
hide or fold away, the feature groups, the never-hideable list, the words, and
a small reference state machine (docs/MENU-VISIBILITY-DESIGN.md, the owner's
decision of 2026-09-30; docs/JARVIS-API.md section 109).

NEW MODULE, shipped whole, NO PATCH and NO ROUTE. Hiding is per device: each app
keeps its own set of hidden and folded ids (the desktop in localStorage, the
phone in SharedPreferences). Nothing about menus is sent anywhere, so there is
no HTTP route, no approval card and nothing on jarvis_gate.py. This module is
read by exactly two things:

  * jarvis_quick.py - "hide the finance menu" / "show the quiz menu" / "collapse
    the goals menu" / "show everything", answered with no model. The reply is the
    same for every device (the backend does not know which app asked), and the
    answer's X-Jarvis-Route carries `menu_visibility: {"action", "target"}` so
    each app that hears it applies it to itself.
  * tools/gen_menu_cases.py - writes the shared fixture menu-cases.json for the
    desktop and the phone (ids, groups, never-hideable list, words, defaults,
    migration rules, worked cases of the state machine below), so neither app
    can carry a different list.

WHAT HIDING IS: hiding only tidies. Nothing is turned off; the feature still
works when the owner asks Jarvis. A menu has two independent states -
HIDDEN (gone from the rail / list / jump links) and COLLAPSED (header stays,
body folds to a line).

IDS (design section 5): stable, lower-case, never reused, never renamed. The
design wrote "dot-free" and then gave dotted examples (`settings.voice`,
`brain.work.quiz`, `group.study`); the examples are followed, because the
desktop already carries `data-menu-id="brain.memory.topics"`,
`"brain.work.retirement"` and `"brain.projects.progress"`. ONE id means ONE
feature: where both apps have the feature it has the same id, even if the phone
draws it somewhere else (the phone's Second graphics card is a Brain plate but
keeps the id `settings.second-card`); `apps` says which app has it.

NEVER HIDEABLE (design section 5, the fixed list): approvals; security, App
lock; "What asks first"; the connection and the stale-link banner (rule 4);
crisis help; Stop everything; Settings and Help themselves; the "Show or hide
menus" control; Trust and Watch on the Brain rail. A few more are kept visible
because hiding them could strand something (Devices - removing a lost phone;
the Undo shelf - its 10-minute Undo; Coming up - a due reminder; facts waiting
for a yes). Every one is in NEVER_HIDE with its reason, and a test in each app
fails the build if one is ever put on the hideable list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Optional

VERSION = 1

#: The two apps. "both" is written as ("desktop", "phone").
DESKTOP = "desktop"
PHONE = "phone"
BOTH = (DESKTOP, PHONE)


@dataclass(frozen=True)
class Menu:
    id: str
    title: str                      # the words in the Show-or-hide list
    about: str                      # one line under the title
    apps: tuple = BOTH
    area: str = "settings"          # settings | brain | entry | safety
    view: str = ""                  # for area "brain": the desktop rail view (memory, work ...)
    group: Optional[str] = None     # a feature group id, without the "group." prefix
    parent: Optional[str] = None    # a menu that contains this one (hidden with it)
    hide: bool = True               # False: never hideable (then `why` says why)
    collapse: bool = True           # False: cannot be folded (its body may hold a warning)
    why: str = ""                   # the reason, for a menu that stays visible
    names: tuple = ()               # what the owner may call it ("the quiz menu")
    kind: str = "card"              # card | tab | plate | row | entry | answer


@dataclass(frozen=True)
class Group:
    id: str                         # without the "group." prefix
    title: str
    about: str
    names: tuple = ()


def _m(id, title, about, apps=BOTH, **kw) -> Menu:
    return Menu(id=id, title=title, about=about, apps=tuple(apps), **kw)


# --------------------------------------------------------------------------
#   The groups (design section 4). Members are the menus whose `group` names
#   it. A group with no member in an app is not listed there; one with no
#   member anywhere ("home" today) answers "There is no ... menu yet."
# --------------------------------------------------------------------------
GROUPS: tuple = (
    Group("study", "Study", "Quiz and Review decks.", ("study", "studying")),
    Group("goals-projects", "Goals and projects", "Goals, Projects and Progress.",
          ("goals and projects", "goals & projects", "projects and goals")),
    Group("graphics-cards", "Graphics cards",
          "Hardware, the second card's switches and the big model.",
          ("graphics cards", "graphics card", "gpu", "gpus")),
    Group("chatbots", "Chatbots", "Talk to a chatbot for me, and customer-support chats.",
          ("chatbots", "chatbot")),
    Group("finance", "Finance", "Spending summaries and the retirement what-if.",
          ("finance", "finances", "money and spending")),
    Group("home", "Home", "Home status and smart-home settings.", ("home", "smart home")),
)

# --------------------------------------------------------------------------
#   The menus. Order is the order the Show-or-hide list draws them.
#   "settings.*"  - Settings cards (desktop) / Settings rows (phone), and the
#                   phone's Brain plates for the same features (see module doc)
#   "brain.tab.*" - the desktop's Brain rail
#   "brain.<view>.*" - Brain cards / plates
#   "entry.*"     - a button or row that only leads to another screen
# --------------------------------------------------------------------------
MENUS: tuple = (
    # ---- Settings ------------------------------------------------------
    _m("settings.connection", "Connection",
       "The pairing key, the server address and the link status.",
       hide=False, collapse=False, kind="card",
       why="Acting is blocked when the link is stale (rule 4), so its status is always visible.",
       names=("connection", "connection settings", "pairing", "the server address")),
    _m("settings.devices", "Devices", "Every paired device with its own key.",
       hide=False, kind="card", names=("devices", "paired devices"),
       why="Removing a lost phone must stay reachable."),
    # "settings.faq" ("Help and FAQ") lived here until 2026-10-08. It was NOT a
    # duplicate way in - it held the fifteen questions only the desktop answers
    # (Quiet against Standby, Alt+Space, "I closed the window but Jarvis is
    # still running", the pairing token, a lost phone), it was the palette's
    # only Help destination, and it was the only non-tray way in to "Everything
    # Jarvis can do". So the owner chose to fold it properly rather than delete
    # it: the questions moved to the desktop's own half of the Brain's
    # "Tutorials and the FAQ" (jarvis-desktop/src/desktop-help.js), the button
    # moved with them, and Help itself now names that place - which is what
    # `entry.help` below points at. One Help place, not two.
    _m("settings.appearance-card", "Appearance", "Theme, faces and how it all looks.",
       names=("appearance", "the theme", "themes", "faces")),
    _m("settings.animal-options", "Animal options",
       "Every animal-face option in one place.", (DESKTOP,),
       names=("animal options", "animal settings")),
    _m("settings.voice", "Voice", "Talk, read aloud, hands-free and sounds.",
       names=("voice", "voice settings")),
    _m("settings.manner", "How Jarvis talks", "Warm and brief, or plain.",
       names=("how jarvis talks", "manner")),
    _m("settings.briefing-settings", "Morning briefing settings",
       "What the morning briefing includes.", (DESKTOP,),
       names=("briefing settings", "morning briefing settings")),
    _m("settings.shortcuts", "Shortcuts", "Keyboard shortcuts.", (DESKTOP,),
       names=("shortcuts", "keyboard shortcuts", "hotkeys")),
    _m("settings.security", "Security", "App lock and Windows Hello or the screen lock.",
       hide=False, collapse=False, kind="card",
       why="Safety: the lock and fingerprint settings must always be reachable.",
       names=("security", "security settings", "app lock", "windows hello")),
    _m("settings.voices", "Jarvis's voice", "Custom voices and the voice pack.", (DESKTOP,),
       names=("jarvis's voice", "jarvis's voices", "custom voices")),
    _m("settings.web-search", "Web search", "Which search provider Jarvis uses.",
       names=("web search", "search settings", "the search provider")),
    _m("settings.account-secrets", "Accounts", "Keys and account details kept on this PC.",
       (DESKTOP,), names=("accounts", "account secrets", "credentials")),
    # "Chatbot API keys" (docs/ACCOUNT-KEYS-DESIGN.md steps 1-2, 2026-10-06):
    # the six API services the chatbot driver can use. Each key is typed on
    # the PC and written straight into Windows Credential Manager - the phone
    # is never asked for an account secret, so this is a desktop card.
    _m("settings.chatbot-api-keys", "Chatbot API keys",
       "The six chatbot services' API keys, kept on this PC.",
       (DESKTOP,), names=("chatbot api keys", "the api keys", "chatbot keys")),
    _m("settings.hardware", "Hardware and models", "Your graphics cards and the three setups.",
       group="graphics-cards", names=("hardware", "hardware and models")),
    _m("settings.second-card", "Second graphics card",
       "The second card's switches and its own copy of Ollama.", group="graphics-cards",
       names=("second graphics card", "second card", "second gpu")),
    _m("settings.second-card.study-helper", "Study helper (second card switch)",
       "One row inside the second graphics card.", group="graphics-cards",
       parent="settings.second-card", kind="row",
       names=("study helper", "the study helper switch")),
    _m("settings.second-card.referee", "Referee suggestions (second card switch)",
       "One row inside the second graphics card.", group="graphics-cards",
       parent="settings.second-card", kind="row",
       names=("referee", "referee suggestions", "the referee switch")),
    _m("settings.second-card.third-card", "Third graphics card",
       "The section for a third card, when one is capable.", group="graphics-cards",
       parent="settings.second-card", kind="row",
       names=("third graphics card", "third card")),
    # "Everyday chat runs on" (the owner's decision, 2026-10-05): which
    # graphics card runs everyday chat - Ollama's own choice by default, or
    # one the owner pins (one approval card).
    _m("settings.second-card.chat-card", "Everyday chat runs on",
       "One row inside the second graphics card.", group="graphics-cards",
       parent="settings.second-card", kind="row",
       names=("everyday chat runs on", "which card runs chat", "the chat card",
              "leave it to ollama", "pin everyday chat")),
    _m("settings.big-model", "Big model (slow)", "One bigger model split across both cards.",
       group="graphics-cards", names=("big model", "the big model")),
    _m("settings.folders", "Folders Jarvis may look in", "The folders and the Notion export.",
       names=("folders", "folders jarvis may look in")),
    _m("settings.spending", "Spending", "Spending summaries from a bank file you drop in.",
       group="finance", names=("spending", "spending summaries")),
    _m("settings.screen-look", "Look at this and Watch with me",
       "The screen feature's lists and picture mode.",
       names=("look at this", "watch with me", "screen settings")),
    _m("settings.browser-engine", "Browser without a window",
       "Which browser Jarvis uses for plain reading.",
       names=("browser without a window", "headless browser", "browser settings")),
    _m("settings.backup", "Backups", "One locked backup file into a folder you pick.",
       names=("backups", "backup settings")),
    _m("settings.updates", "Updates", "New versions of this app.", (DESKTOP,),
       names=("updates", "app updates")),
    _m("settings.tool-updates", "Check for tool updates", "Outdated packages and tools.",
       (DESKTOP,), names=("tool updates",)),
    _m("settings.more-options", "More options", "Startup, logs and crash notes.", (DESKTOP,),
       hide=False, collapse=False, kind="card",
       why="Already a fold of its own; it stays where it is."),
    _m("settings.asks-first", "What asks first", "Every action and whether it asks.",
       hide=False, collapse=False, kind="card",
       why="Safety: what asks first must always be reachable.",
       names=("what asks first", "asks first", "what asks first settings")),
    _m("settings.reach", "What Jarvis can reach", "Which tools Jarvis may use.",
       names=("what jarvis can reach", "reach")),
    _m("settings.email-sending", "Sending email", "Sending email, one card per email.",
       names=("sending email", "email sending")),
    _m("settings.about", "About Jarvis", "Version, licences and credits.", (DESKTOP,),
       names=("about jarvis", "about")),
    _m("settings.backend-supports", "What this backend supports",
       "The capability list the app branches on.",
       names=("what this backend supports", "backend capabilities", "this backend")),
    _m("settings.watch-notify", "Smartwatch notifications",
       "Whether notifications show on a watch.", (PHONE,),
       names=("smartwatch notifications", "watch notifications")),
    _m("settings.phone-notify", "Phone notifications",
       "Reading phone notifications, and the apps allowed.", (PHONE,),
       names=("phone notifications",)),
    _m("settings.floating-avatar", "Floating Jarvis", "The floating face or bubble.", (PHONE,),
       names=("floating jarvis", "floating face", "the bubble")),
    _m("settings.quick-tiles", "Quick Settings tiles", "The tiles in the phone's quick panel.",
       (PHONE,), names=("quick settings tiles", "quick tiles")),
    _m("settings.menu-visibility", "Show or hide menus",
       "The list you are looking at.", kind="card",
       hide=False, collapse=False,
       why="Otherwise nothing hidden could be shown again.",
       names=("show or hide menus", "menus", "the menu list")),
    # The big "Jarvis" window (the owner's request of 2026-10-06): its own chat
    # box, and the one switch for whether the "Open the Jarvis bar" button is
    # drawn beside it. Desktop only, like the card itself.
    _m("settings.hud-window", "The big HUD window",
       "Its own chat box, and the button that opens the Jarvis bar.", (DESKTOP,),
       names=("the big hud window", "big hud window", "the hud window", "hud window",
              "the big jarvis window", "big jarvis window")),

    # ---- Brain: the desktop's rail ------------------------------------
    _m("brain.tab.memory", "Memory", "What Jarvis knows and how it learns.", (DESKTOP,),
       area="brain", view="memory", kind="tab", names=("memory",)),
    _m("brain.tab.history", "History", "Your past chats.", (DESKTOP,),
       area="brain", view="history", kind="tab", names=("history", "chat history")),
    _m("brain.tab.faculties", "Model", "The models, compute and skills.", (DESKTOP,),
       area="brain", view="faculties", kind="tab", names=("model",)),
    _m("brain.tab.work", "Work", "Focus, chatbots, today, goals, quiz and the rest.", (DESKTOP,),
       area="brain", view="work", kind="tab", names=("work",)),
    _m("brain.tab.projects", "Projects", "Projects, their notes and benchmarks.",
       area="brain", view="projects", kind="tab", group="goals-projects", names=("projects",)),
    _m("brain.tab.tutorials", "Tutorials and the FAQ",
       "How Jarvis works, step by step, and the answers to the usual questions.",
       (DESKTOP,), area="brain", view="tutorials", kind="tab",
       # "faq", "the faq" and "frequently asked questions" moved here from the
       # Settings card "Help and FAQ" on 2026-10-08: they are the names the
       # owner already says for Help, and the place those names now answer with
       # is this one. Nothing else in the catalogue claims them.
       names=("tutorials", "tutorials and the faq", "faq", "the faq",
              "frequently asked questions")),
    _m("brain.tab.galaxy", "Galaxy", "The map of what Jarvis knows.", (DESKTOP,),
       area="brain", view="galaxy", kind="tab", names=("galaxy",)),
    _m("brain.tab.now", "Now", "What Jarvis is doing right now.", (DESKTOP,),
       area="brain", view="now", kind="tab", names=("now",)),
    _m("brain.tab.trust", "Trust", "Content risk and the audit chain.",
       (DESKTOP,), area="brain", view="trust", kind="tab", hide=False,
       why="It holds pending attention, so it can never be hidden."),
    _m("brain.tab.watch", "Watch", "The GitHub watchlist and what needs you.",
       (DESKTOP,), area="brain", view="watch", kind="tab", hide=False,
       why="It holds pending attention, so it can never be hidden."),

    # ---- Brain: Memory -------------------------------------------------
    _m("brain.memory.learning", "Learning", "How much Jarvis remembers and whether it learns.",
       area="brain", view="memory", names=("learning", "memory counts")),
    _m("brain.memory.history-import", "Bring in old chats", "Import chats from another AI.",
       (DESKTOP,), area="brain", view="memory", names=("bring in old chats", "history import")),
    _m("brain.memory.topics", "Topics", "A mode for each topic of what Jarvis learns.",
       area="brain", view="memory", names=("topics",)),
    _m("brain.memory.auto", "Saved automatically", "Facts Jarvis saved without asking.",
       area="brain", view="memory", names=("saved automatically",)),
    _m("brain.memory.profile", "Always keep in mind", "Facts pinned to every answer.",
       area="brain", view="memory", names=("always keep in mind", "pinned facts")),
    _m("brain.memory.between-us", "Between us", "Inside jokes and shared references.",
       area="brain", view="memory", names=("between us", "inside jokes")),
    _m("brain.memory.people-things", "People and things",
       "The people and things Jarvis has heard about.", (PHONE,), area="brain", view="memory",
       names=("people and things", "people")),
    _m("brain.memory.waiting", "Waiting for you", "Facts waiting for your yes.",
       area="brain", view="memory", hide=False, kind="card",
       why="Something is waiting on you; it must not be hidden away."),
    _m("brain.memory.known", "What Jarvis knows about you", "The facts, by topic.",
       (DESKTOP,), area="brain", view="memory", names=("what jarvis knows about you",)),
    _m("brain.memory.wiki", "Wiki", "The wiki Jarvis builds from your notes.",
       area="brain", view="memory", names=("wiki", "the wiki")),
    _m("brain.memory.deep", "Deep questions", "Slow questions and their answers.",
       area="brain", view="memory", names=("deep questions",)),
    _m("brain.memory.as-of", "What did I believe on this date?",
       "Ask what a fact said on a past day.", (PHONE,), area="brain", view="memory",
       names=("what did i believe", "as of a date")),

    # ---- Brain: History ------------------------------------------------
    _m("brain.history.conversations", "Chat history and conversations",
       "The list of your past chats and how long they are kept.", (DESKTOP,),
       area="brain", view="history", names=("conversations", "past chats")),
    _m("brain.history.tags", "Chat tags", "The tag chips and the tag editor.", (DESKTOP,),
       area="brain", view="history", names=("chat tags", "tags")),
    _m("brain.history.tag-suggestions", "Suggest tags overnight",
       "The overnight tag suggestions switch.", area="brain", view="history",
       parent="brain.history.tags", kind="row",
       names=("tag suggestions", "suggest tags overnight")),
    _m("brain.history.forget-range", "Forget a time frame",
       "Pick days, tick what to forget, one card, 10 minutes to undo.",
       area="brain", view="history", names=("forget a time frame",)),

    # ---- Brain: Model --------------------------------------------------
    _m("brain.model.models", "Models", "The models Jarvis can use.",
       area="brain", view="faculties", names=("models list", "model list")),
    _m("brain.model.compute", "Compute", "The graphics card plan.",
       area="brain", view="faculties", names=("compute",)),
    _m("brain.model.skills", "Skills", "Installed skills with scan verdicts.",
       area="brain", view="faculties", names=("skills",)),
    _m("brain.model.memory", "Memory (model view)", "The memory summary on the Model page.",
       (DESKTOP,), area="brain", view="faculties", names=("model memory",)),
    _m("brain.model.pc-help", "PC help", "Five plain answers about the PC.", (PHONE,),
       area="brain", view="faculties", names=("pc help",)),
    # Tutorials and the FAQ (the owner's request of 2026-10-05; JARVIS-API
    # section 114, docs/TUTORIALS-DESIGN.md). One catalogue for BOTH apps and
    # the owner's reading progress, kept on the PC: an intro, a tutorial for
    # each major part, and the questions and answers.
    #
    # The desktop draws them as its own "Tutorials" rail tab
    # (`brain.tab.tutorials`); the phone draws the same catalogue as a plate
    # inside its Model view, and this is that plate. Its title names the FAQ
    # it also holds, because only one menu may answer to a spoken name and the
    # rail tab has it: the backend does not know which app asked, so two menus
    # both called "Tutorials" could not be told apart (test_menu_visibility.py
    # "no spoken name means two things"). It is the phone's alone now - the
    # desktop has no Model-view tutorials card, only the tab.
    _m("brain.model.tutorials", "Tutorials and the FAQ",
       "The intro, a tutorial for each part, and the answers to the usual questions.",
       (PHONE,), area="brain", view="tutorials",
       names=("tutorials and the faq", "tutorial")),

    # ---- Brain: Work ---------------------------------------------------
    _m("brain.work.focus", "Focus session", "Start and stop a focus session.",
       area="brain", view="work", names=("focus", "focus session")),
    _m("brain.work.chatbot", "Talk to a chatbot for me",
       "Jarvis holds a conversation with another AI for you.", area="brain", view="work",
       group="chatbots", names=("chatbot driver", "talk to a chatbot")),
    _m("brain.work.support", "Chat with customer support for me",
       "Customer-support chats, one card per offer.", area="brain", view="work",
       group="chatbots", names=("customer support", "support chats")),
    _m("brain.work.today", "Today", "Your own cards for the day.", area="brain", view="work",
       names=("today",)),
    _m("brain.work.widgets", "Widgets", "Widgets you described.", area="brain", view="work",
       names=("widgets",)),
    _m("brain.work.coming-up", "Coming up", "Reminders, alarms, timers and repeating jobs.",
       area="brain", view="work", hide=False,
       why="A reminder that is due shows here; it must stay reachable.",
       names=("coming up",)),
    _m("brain.work.goals", "Goals", "Plans you edit, with a weekly check-in.",
       area="brain", view="work", group="goals-projects", names=("goals",)),
    _m("brain.work.quiz", "Quiz me on a text", "Questions on a text you paste or a YouTube link.",
       area="brain", view="work", group="study", names=("quiz", "quizzes")),
    _m("brain.work.quiz.youtube", "Quiz from a YouTube link",
       "The YouTube link box inside the quiz.", area="brain", view="work", group="study",
       parent="brain.work.quiz", kind="row", names=("youtube link", "quiz youtube link")),
    _m("brain.work.decks", "My study decks", "Questions kept to study again.",
       area="brain", view="work", group="study", names=("decks", "review decks", "study decks")),
    _m("brain.work.retirement", "Retirement what-if", "A simple what-if from numbers you typed.",
       area="brain", view="work", group="finance", names=("retirement", "retirement what-if")),
    _m("brain.work.briefing", "Morning briefing", "What the morning briefing said.",
       area="brain", view="work", names=("morning briefing", "briefing")),
    _m("brain.work.jobs", "Background jobs", "Long jobs Jarvis is running.",
       area="brain", view="work", names=("background jobs", "background work")),
    _m("brain.work.undo", "Undo shelf", "Changes you can still undo.", (DESKTOP,),
       area="brain", view="work", hide=False,
       why="Undo is a safety net; hiding it could strand a 10-minute Undo."),
    _m("brain.work.activity", "Activity", "What Jarvis did lately.", (DESKTOP,),
       area="brain", view="work", names=("activity",)),

    # ---- Brain: Projects -----------------------------------------------
    _m("brain.projects.progress", "Progress", "The activity heatmap and balance chart.",
       area="brain", view="projects", group="goals-projects", names=("progress", "heatmap")),

    # ---- Brain: Now, Trust, Watch --------------------------------------
    _m("brain.now.right-now", "Right now", "What Jarvis is doing and its power state.",
       area="brain", view="now", names=("right now",)),
    _m("brain.now.budget", "Attention budget", "How many interruptions are left.",
       area="brain", view="now", hide=False, kind="card",
       why="Pending attention is counted here, so it stays visible."),
    _m("brain.now.trace", "What Jarvis is doing", "The tool steps, newest last.",
       area="brain", view="now", names=("trace", "what jarvis is doing")),
    _m("brain.now.findings", "Findings", "What Jarvis noticed on its own.", (PHONE,),
       area="brain", view="now", names=("findings",)),
    _m("brain.trust.rush-latch", "Rush latch banner", "Outside text that tried to raise the tier.",
       (PHONE,), area="brain", view="trust", hide=False, collapse=False, kind="answer",
       why="Safety: it must never vanish from the screen."),
    _m("brain.trust.content-risk", "Content risk", "Read-only content risk.", (DESKTOP,),
       area="brain", view="trust", hide=False,
       why="Inside Trust, which can never be hidden."),
    _m("brain.trust.ledger", "Audit chain", "The ledger's chain status.",
       area="brain", view="trust", hide=False,
       why="Inside Trust, which can never be hidden."),
    _m("brain.watch.watchlist", "GitHub watchlist", "The repos Jarvis watches.",
       area="brain", view="watch", hide=False,
       why="Inside Watch, which can never be hidden."),

    # ---- Entry points (a button or row that only leads to a screen) ----
    _m("entry.appearance", "Appearance button on Home", "The Appearance button in Home's row.",
       (PHONE,), area="entry", kind="entry", names=("appearance button",)),
    _m("entry.voices", "Jarvis's voice row", "The row that opens Jarvis's voice.", (PHONE,),
       area="entry", kind="entry", names=("voices row",)),
    _m("entry.voice-check", "Voice check row", "The row that opens the voice check.", (PHONE,),
       area="entry", kind="entry", names=("voice check", "voice check row")),
    _m("entry.history", "History entry in Brain", "The row that opens your past chats.", (PHONE,),
       area="entry", kind="entry", names=("history entry",)),
    _m("entry.checks", "Connection status line", "The status line that opens Platform checks.",
       (PHONE,), area="safety", kind="entry", hide=False, collapse=False,
       why="It is the connection status (rule 4)."),
    _m("entry.help", "Help",
       "The Help entry: the Brain's \"Tutorials and the FAQ\".",
       area="brain", view="tutorials", kind="entry",
       hide=False, collapse=False, why="Settings and Help themselves always stay reachable.",
       names=("help", "the help button")),
    _m("entry.settings", "Settings", "The Settings entry.", area="safety", kind="entry",
       hide=False, collapse=False, why="Settings and Help themselves always stay reachable.",
       names=("settings", "the settings button")),

    # ---- Safety areas that are not menus but are listed so nobody hides them
    _m("safety.approvals", "Approvals", "Approval cards, the widget, the notification.",
       area="safety", kind="answer", hide=False, collapse=False,
       why="Approvals must always be reachable.", names=("approvals", "the inbox", "inbox")),
    _m("safety.stale-link", "Stale-link banner", "The warning that the link is old.",
       area="safety", kind="answer", hide=False, collapse=False,
       why="Rule 4: acting is blocked when the event stream is stale."),
    _m("safety.crisis-help", "Crisis help", "The help line shown in an answer.",
       area="safety", kind="answer", hide=False, collapse=False,
       why="It lives in the answer itself and is never a menu.", names=("crisis help",)),
    _m("safety.stop-everything", "Stop everything", "The hotkey, tray entry and phone control.",
       area="safety", kind="answer", hide=False, collapse=False,
       why="Stop must always work.", names=("stop everything",)),
    _m("safety.live-stop", "Stop button in Jarvis Live", "End Live.", (PHONE,),
       area="safety", kind="answer", hide=False, collapse=False,
       why="Stop must always work."),
)

# A card inside a Brain view is contained by that view's tab (hidden with it); a
# tab, a row and an entry cannot be folded (nothing to fold).
_VIEW_TAB = {"memory": "brain.tab.memory", "history": "brain.tab.history",
             "faculties": "brain.tab.faculties", "work": "brain.tab.work",
             "projects": "brain.tab.projects", "galaxy": "brain.tab.galaxy",
             "now": "brain.tab.now", "trust": "brain.tab.trust", "watch": "brain.tab.watch"}


def _finish(m: Menu) -> Menu:
    parent = m.parent
    if parent is None and m.area == "brain" and m.kind != "tab" and m.view in _VIEW_TAB:
        parent = _VIEW_TAB[m.view]
    collapse = m.collapse and m.kind in ("card", "plate")
    return replace(m, parent=parent, collapse=collapse)


MENUS = tuple(_finish(m) for m in MENUS)

# --------------------------------------------------------------------------
#   Look-ups
# --------------------------------------------------------------------------
_BY_ID = {m.id: m for m in MENUS}
_GROUP_BY_ID = {g.id: g for g in GROUPS}
GROUP_PREFIX = "group."

#: The fixed never-hideable list: (id, reason), in menu order.
NEVER_HIDE: tuple = tuple((m.id, m.why) for m in MENUS if not m.hide)

#: The ids a person may hide, in list order.
HIDEABLE: tuple = tuple(m.id for m in MENUS if m.hide)


def menu(id_: str) -> Optional[Menu]:
    return _BY_ID.get(id_)


def group(id_: str) -> Optional[Group]:
    """A group by its id, with or without the "group." prefix."""
    if id_.startswith(GROUP_PREFIX):
        id_ = id_[len(GROUP_PREFIX):]
    return _GROUP_BY_ID.get(id_)


def group_id(g: Group) -> str:
    return GROUP_PREFIX + g.id


def members(group_: str, app: Optional[str] = None) -> tuple:
    """The menu ids in a group (with or without the prefix), for one app or all."""
    gid = group_[len(GROUP_PREFIX):] if group_.startswith(GROUP_PREFIX) else group_
    return tuple(m.id for m in MENUS
                 if m.group == gid and (app is None or app in m.apps))


def is_group_id(id_: str) -> bool:
    return id_.startswith(GROUP_PREFIX) and id_[len(GROUP_PREFIX):] in _GROUP_BY_ID


def children(id_: str) -> tuple:
    return tuple(m.id for m in MENUS if m.parent == id_)


def ancestors(id_: str) -> tuple:
    """The chain of parents, nearest first."""
    out = []
    m = _BY_ID.get(id_)
    while m is not None and m.parent:
        out.append(m.parent)
        m = _BY_ID.get(m.parent)
    return tuple(out)


def known(id_: str, app: Optional[str] = None) -> bool:
    """Is `id_` a menu or a group this app can act on?"""
    if is_group_id(id_):
        return bool(members(id_, app))
    m = _BY_ID.get(id_)
    return m is not None and (app is None or app in m.apps)


# --------------------------------------------------------------------------
#   Words (both apps show these, word for word; the fixture carries them)
# --------------------------------------------------------------------------
WORDS: dict = {
    "title": "Show or hide menus",
    "device_note": "This hides menus on this device only.",
    "help": ("Hiding a menu only tidies it away. Nothing is turned off, and Jarvis can still "
             "do it when you ask. Asking Jarvis to hide or show a menu changes every device "
             "that hears it."),
    "never_note": ("Some things always stay visible: approvals, security, What asks first, "
                   "and the connection status."),
    "tray_note": "The system-tray menu is not affected.",
    "none_hidden": "Nothing is hidden.",
    "hidden_line_one": "1 hidden - Show",
    "hidden_line_many": "{n} hidden - Show",
    "hidden_speech_one": "1 menu hidden. Show or hide menus.",
    "hidden_speech_many": "{n} menus hidden. Show or hide menus.",
    "show_everything": "Show everything",
    "visit_banner": "Shown for now.",
    "visit_keep": "Keep it visible",
    "visit_again": "Hide again",
    "state_expanded": "Expanded",
    "state_collapsed": "Collapsed",
    "hide_switch": "Hide {title}",
    "group_hides": "Hides {members}",
    "collapse": "Fold",
    "expand": "Open",
    "folded_line": "Folded. Tap Open to see it.",
}

#: What Jarvis says (jarvis_quick.py). The same for every device: the backend
#: does not know which app asked, so the words say "on the devices that are open".
REPLIES: dict = {
    "hide": "Done. On the devices that are open, the {title} menu is hidden. Nothing is turned "
            "off. Say \"show the {title} menu\" to bring it back.",
    "show": "Done. On the devices that are open, the {title} menu is showing.",
    "collapse": "Done. On the devices that are open, the {title} menu is folded to one line.",
    "expand": "Done. On the devices that are open, the {title} menu is open.",
    "reset": "Done. On the devices that are open, every menu is showing again.",
    "unknown": "I don't know a menu called that.",
    "never": "That one stays visible so you can always reach it.",
    "empty": "There is no {title} menu yet.",
    "cannot_collapse": "That menu cannot be folded.",
    "always": "That one is always visible.",
}

ACTIONS = ("hide", "show", "collapse", "expand", "reset")

#: Ids that are never hideable have a refusal name too, so "hide the security menu"
#: is answered plainly instead of falling through to the model.
_NAME_SUFFIX = re.compile(r"\s+(?:menus?|sections?)$")
_NAME_PREFIX = re.compile(r"^(?:the|my|all\s+of\s+the|all\s+of\s+my)\s+")


def normalise_name(text: str) -> str:
    s = " ".join(str(text or "").lower().replace("’", "'").replace("‘", "'").split())
    s = s.strip(" .,!?")
    for _ in range(3):
        n = _NAME_PREFIX.sub("", s)
        n = _NAME_SUFFIX.sub("", n)
        if n == s:
            break
        s = n
    return s.strip()


def _alias_table() -> dict:
    table: dict = {}
    for g in GROUPS:
        for name in (g.title.lower(),) + tuple(g.names):
            table.setdefault(normalise_name(name), GROUP_PREFIX + g.id)
    for m in MENUS:
        for name in (m.title.lower(),) + tuple(m.names):
            table.setdefault(normalise_name(name), m.id)
    return table


_ALIASES = _alias_table()

#: Names that only make sense as a menu (not as a bare phrase) never appear here.
ALL_MENUS_PHRASES = re.compile(
    r"(?:show|unhide)\s+(?:me\s+)?everything"
    r"|(?:show|unhide|restore|reset)\s+(?:me\s+)?(?:all|every)(?:\s+of)?"
    r"(?:\s+(?:my|the))?(?:\s+(?:hidden|folded|collapsed))?\s+menus?"
    r"|show\s+(?:me\s+)?(?:my\s+)?hidden\s+menus"
    r"|(?:unhide|reset)\s+(?:my\s+)?menus")


def aliases() -> dict:
    """name -> menu id or group id, every name Jarvis understands."""
    return dict(_ALIASES)


def resolve(name: str) -> Optional[str]:
    """A spoken menu name -> a menu id or "group.<id>", or None (never guess)."""
    return _ALIASES.get(normalise_name(name))


def title_of(id_: str) -> str:
    g = group(id_) if is_group_id(id_) else None
    if g is not None:
        return g.title
    m = _BY_ID.get(id_)
    return m.title if m else id_


# --------------------------------------------------------------------------
#   The reference state machine. The desktop's menu-visibility.js and the
#   phone's MenuState.kt do exactly this; the fixture carries worked cases so
#   neither can drift. `state` = {"hidden": [...], "collapsed": [...]}.
# --------------------------------------------------------------------------
@dataclass
class State:
    hidden: set = field(default_factory=set)
    collapsed: set = field(default_factory=set)

    def as_dict(self) -> dict:
        return {"hidden": sorted(self.hidden), "collapsed": sorted(self.collapsed)}

    @staticmethod
    def of(d: Optional[dict]) -> "State":
        d = d or {}
        return State(set(d.get("hidden") or ()), set(d.get("collapsed") or ()))


def sanitize(state: State, app: Optional[str] = None) -> State:
    """Drop stale ids: unknown ids, ids from another app, and any never-hideable id
    (a stored id that no longer exists is ignored, silently, and dropped on the next save)."""
    hidden = set()
    for i in state.hidden:
        if is_group_id(i):
            if members(i, app):
                hidden.add(i)
        else:
            m = _BY_ID.get(i)
            if m is not None and m.hide and (app is None or app in m.apps):
                hidden.add(i)
    collapsed = set()
    for i in state.collapsed:
        m = _BY_ID.get(i)
        if m is not None and m.collapse and (app is None or app in m.apps):
            collapsed.add(i)
    return State(hidden, collapsed)


def is_hidden(state: State, id_: str, visit: frozenset = frozenset()) -> bool:
    """Is this menu hidden right now? A never-hideable menu never is. A menu in `visit`
    (opened for one visit by a link) is shown. A menu is hidden when its own id, its
    group's id, or a parent's id is hidden."""
    m = _BY_ID.get(id_)
    if m is None or not m.hide:
        return False
    if id_ in visit:
        return False
    if id_ in state.hidden:
        return True
    if m.group and (GROUP_PREFIX + m.group) in state.hidden:
        return True
    return bool(m.parent) and is_hidden(state, m.parent, visit)


def is_collapsed(state: State, id_: str, visit: frozenset = frozenset()) -> bool:
    m = _BY_ID.get(id_)
    return bool(m and m.collapse and id_ in state.collapsed and id_ not in visit)


def hidden_count(state: State, app: str) -> int:
    """The N in "N hidden - Show": a hidden group is ONE switch (its members are not
    counted again), and a menu hidden under a hidden parent is not counted again."""
    n = 0
    for g in GROUPS:
        if (GROUP_PREFIX + g.id) in state.hidden and members(g.id, app):
            n += 1
    for m in MENUS:
        if app not in m.apps or not m.hide:
            continue
        if m.id not in state.hidden:
            continue
        if m.group and (GROUP_PREFIX + m.group) in state.hidden:
            continue
        if m.parent and (is_hidden(state, m.parent)):
            continue
        n += 1
    return n


def _all_members_of(cover: str) -> tuple:
    return members(cover) if is_group_id(cover) else children(cover)


def hide(state: State, id_: str, app: Optional[str] = None) -> str:
    """"ok" | "never" | "unknown"."""
    if is_group_id(id_):
        if not members(id_, app):
            return "unknown"
        state.hidden.add(id_)
        state.hidden.difference_update(members(id_))
        return "ok"
    m = _BY_ID.get(id_)
    if m is None or (app is not None and app not in m.apps):
        return "unknown"
    if not m.hide:
        return "never"
    state.hidden.add(id_)
    return "ok"


def show(state: State, id_: str, app: Optional[str] = None) -> str:
    """Showing a group clears the group id and its members. Showing one menu whose group
    or parent is hidden shows ONLY that menu: the cover's id is cleared and its other
    members are hidden one by one instead."""
    if is_group_id(id_):
        if not members(id_, app):
            return "unknown"
        state.hidden.discard(id_)
        state.hidden.difference_update(members(id_))
        return "ok"
    m = _BY_ID.get(id_)
    if m is None or (app is not None and app not in m.apps):
        return "unknown"
    state.hidden.discard(id_)
    covers = ([GROUP_PREFIX + m.group] if m.group else []) + list(ancestors(id_))
    for cover in covers:
        if cover in state.hidden:
            state.hidden.discard(cover)
            for other in _all_members_of(cover):
                if (other != id_ and other not in ancestors(id_)
                        and id_ not in ancestors(other) and _BY_ID[other].hide):
                    state.hidden.add(other)
    return "ok"


def collapse(state: State, id_: str, app: Optional[str] = None) -> str:
    """"ok" | "unknown" | "cannot"."""
    if is_group_id(id_):
        ids = [i for i in members(id_, app) if _BY_ID[i].collapse]
        if not members(id_, app):
            return "unknown"
        if not ids:
            return "cannot"
        state.collapsed.update(ids)
        return "ok"
    m = _BY_ID.get(id_)
    if m is None or (app is not None and app not in m.apps):
        return "unknown"
    if not m.collapse:
        return "cannot"
    state.collapsed.add(id_)
    return "ok"


def expand(state: State, id_: str, app: Optional[str] = None) -> str:
    if is_group_id(id_):
        if not members(id_, app):
            return "unknown"
        state.collapsed.difference_update(members(id_))
        return "ok"
    m = _BY_ID.get(id_)
    if m is None or (app is not None and app not in m.apps):
        return "unknown"
    state.collapsed.discard(id_)
    return "ok"


def reset(state: State) -> str:
    state.hidden.clear()
    state.collapsed.clear()
    return "ok"


def apply(state: State, action: str, id_: str = "", app: Optional[str] = None) -> str:
    if action == "hide":
        return hide(state, id_, app)
    if action == "show":
        return show(state, id_, app)
    if action == "collapse":
        return collapse(state, id_, app)
    if action == "expand":
        return expand(state, id_, app)
    if action == "reset":
        return reset(state)
    return "unknown"


def visit_set(id_: str) -> frozenset:
    """A link to a hidden menu shows THAT menu (and what contains it) for the visit
    only - not stored, and its group stays hidden."""
    if id_ not in _BY_ID:
        return frozenset()
    return frozenset((id_,) + ancestors(id_))


# --------------------------------------------------------------------------
#   Asking Jarvis (jarvis_quick.py calls these; no model)
# --------------------------------------------------------------------------
def voice_change(action: str, name: str) -> tuple:
    """(reply, route) for "hide the finance menu". `route` is None when nothing is to
    be applied (unknown, refused, empty): `{"action", "target"}` otherwise."""
    if action == "reset":
        return REPLIES["reset"], {"action": "reset", "target": "all"}
    target = resolve(name)
    if target is None:
        return REPLIES["unknown"], None
    # The owner's own word for it ("quiz"), not the long card title.
    spoken = normalise_name(name)
    spoken = spoken[:1].upper() + spoken[1:] if spoken else title_of(target)
    if is_group_id(target):
        if not members(target):
            return REPLIES["empty"].format(title=spoken), None
        if action == "hide" and not all(_BY_ID[i].hide for i in members(target)):
            return REPLIES["never"], None
        if action == "collapse" and not any(_BY_ID[i].collapse for i in members(target)):
            return REPLIES["cannot_collapse"], None
    else:
        m = _BY_ID[target]
        if action == "hide" and not m.hide:
            return REPLIES["never"], None
        if action == "show" and not m.hide:
            return REPLIES["always"], None
        if action == "collapse" and not m.collapse:
            return (REPLIES["never"] if not m.hide else REPLIES["cannot_collapse"]), None
        if action == "expand" and not m.collapse:
            return REPLIES["always"], None
    return (REPLIES[action].format(title=spoken),
            {"action": action, "target": target})


def route_ok(route) -> bool:
    """Is `route` a well-formed `menu_visibility` value? (For tests and readers.)"""
    if not isinstance(route, dict) or route.get("action") not in ACTIONS:
        return False
    t = route.get("target")
    if route["action"] == "reset":
        return t == "all"
    return isinstance(t, str) and (t in _BY_ID or is_group_id(t))
