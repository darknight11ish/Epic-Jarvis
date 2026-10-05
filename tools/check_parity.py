#!/usr/bin/env python3
"""Compare what the desktop can do against what the phone can do, and fail
when the answer has changed without anyone deciding about it.

    python3 tools/check_parity.py

The two apps are both clients of the same Python backend, so the set of
`/api/...` routes each one calls is a fair, machine-readable proxy for its
feature surface. That is the whole idea here: parity as a check rather than a
promise. A document saying "the phone is up to date" is worth nothing a week
later; this fails the build. CI runs it on every push (.github/workflows/ci.yml).

What it reads - all from THIS checkout:

  desktop  jarvis-desktop/src-tauri/src/**/*.rs   the Rust side
           jarvis-desktop/src/**/*.{js,mjs,html}   the windows, which call
                                                   routes themselves too
  phone    jarvis-client/app/src/main/java/**/*.kt

Comments are stripped before routes are collected, so a route a file only
TALKS about (a KDoc line, a "// /api/graph is desktop-only" note) does not
count as a call.

A route with an id in it is kept whole. `/api/pending/{encoded}/amend` (Rust),
`/api/pending/$encodedId/amend` (Kotlin) and `/api/pending/${id}/amend`
(JavaScript) all become `/api/pending/{id}/amend` - not `/api/pending`, which
is a different route that both apps also call.

An allow-list is not a call. The Brain window's read allow-list
(jarvis-desktop/src-tauri/src/brain/routes.rs, READ_ROUTES) names every
route that window MAY read, by a section name. An entry counts as a call only
when a desktop window that calls `brain_read` asks for that section name.
Entries no window asks for are printed on their own, and are not counted.
The rest of that file (its tests list write routes) is not read at all.

It used to read the desktop from a separate branch (claude/jarvis-desktop-
tauri-vey6bc, last touched 19 Sep) and only its Rust, so it checked a desktop
that no longer existed, missed every route the JavaScript calls, and still
called the model routes out of scope after the owner allowed them on the
phone (18 and 20 Sep).

Failures - each one means a decision is missing or has gone stale:

  1. The desktop calls a route that is not classified below.
  2. A route classified `ported` is not called by the phone.
  3. A route classified `deliberate` (kept OFF the phone) IS called by the
     phone. Either a rule was broken or the decision changed; say which.
  4. A classified route the desktop no longer calls.

  5. The phone calls a route the desktop does not, and PHONE_ONLY below does
     not classify it. Parity runs both ways.
  6. A route in PHONE_ONLY that the phone no longer calls, or that the
     desktop now calls too (move it to CLASSIFICATION).

A route marked `todo` that the phone has started calling is a warning, not
a failure: it means "reclassify as ported", which is good news.

A route marked `planned` is built on the backend and neither app calls it
yet (the backend is written first, then each app builds against it). It is
exempt from rule 4. The moment the desktop calls it, a warning says to
reclassify it (`ported` once the phone calls it too, else `todo`).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP_DIRS = [
    ("jarvis-desktop/src-tauri/src", (".rs",)),
    ("jarvis-desktop/src", (".js", ".mjs", ".html")),
]
PHONE_DIRS = [("jarvis-client/app/src/main/java", (".kt",))]

# One path segment: a literal word, or a placeholder for an id - Rust's
# `{encoded}` / `{}`, JavaScript's `${...}`, Kotlin's `$encodedId` / `${...}`.
# The first segment after /api/ must be literal: `/api/{endpoint}` names no
# route this tool can classify (commands.rs builds /api/approve and /api/deny
# that way; both are also written out in full elsewhere).
_LIT = r"[A-Za-z0-9_-]+"
_PH = r"(?:\$\{[^}\n]*\}|\{[^}/\"\n]*\}|\$[A-Za-z_][A-Za-z0-9_]*)"
ROUTE = re.compile(rf"/api/{_LIT}(?:/(?:{_LIT}|{_PH}))*/?")
_IS_PH = re.compile(rf"^{_PH}$")

# Allow-lists: files whose routes are a list of what a window MAY read, not
# calls. {file: (the constant holding the list, the command that reads it)}.
ALLOWLISTS = {
    "jarvis-desktop/src-tauri/src/brain/routes.rs": ("READ_ROUTES", "brain_read"),
}

# Every route the desktop calls, and what the phone does about it.
#
# "ported"       - the phone calls it too; checked
# "deliberate"   - a decision was made NOT to port it; the reason is the
#                  point, and the phone calling it is a failure
# "todo"         - portable and wanted, nobody has done it yet
# "not-backend"  - not a Jarvis route at all: the desktop calls Ollama's own
#                  API on loopback under the same /api/ prefix
# "planned"      - on the backend, for both apps, and neither calls it yet
CLASSIFICATION = {
    "/api/appearance": ("ported", ""),
    "/api/big-model": ("ported", "The big model (slow) with colibri: what was found and its three switches, each ON an approval card (backend/big-model.patch, 2026-09-24). Desktop: Settings, Big model (slow) (get_big_model / set_big_model, settings window only). Phone: Brain, Big model (slow) (BigModelPlate.kt)."),
    "/api/hardware": ("ported", "The graphics cards and the three setups for them (backend/hardware.patch, docs/HARDWARE-PROFILES.md, 2026-09-25). Desktop: Settings, Hardware and models (hardware.rs get_hardware, settings window only). Phone: Brain, Hardware (HardwarePlate.kt, net/Hardware.kt): names and memory, what runs now, the three setups as the PC's words - never a model list or a picker (CLAUDE.md)."),
    "/api/tutorials": ("ported", "\"Tutorials and the FAQ\" (the owner's request of 2026-10-05; docs/TUTORIALS-DESIGN.md, docs/JARVIS-API.md section 114; backend/tutorials.patch, jarvis_tutorials.py): one catalogue for BOTH apps - an intro and a tutorial for each major part, and the questions and answers - with the owner's reading progress kept on the PC and shared between them. The catalogue itself is read-only and not held on a stale link. Desktop: Brain, Tutorials (tutorials.rs get_tutorials, src/tutorials.js). Phone: Brain, Tutorials (TutorialsPlate.kt, net/Tutorials.kt)."),
    "/api/tutorials/progress": ("ported", "Where the owner has read to: {id, state, step} - one record per tutorial in tutorials.json in the PC's config folder. state is in_progress, done or skipped, or not_started, which CLEARS the record and is what \"Show this one again\" posts; a tutorial whose steps changed (a higher version) is offered again by itself. NO card and NOT held on a stale link: it is the owner marking their own reading and it acts on nothing. Both apps: mark_tutorial (src/tutorials.js) and JarvisRuntime.markTutorial (TutorialsPlate.kt)."),
    "/api/faq": ("ported", "The FAQ: twenty questions and answers written from how the app behaves, each with a `where` line naming the screen where the owner can see or change the thing. Read-only, no card, not held on a stale link. Desktop: the same Brain panel (tutorials.rs get_faq, src/tutorials.js). Phone: the same panel (TutorialsPlate.kt, net/Tutorials.kt)."),
    "/api/pc/help": ("ported", "\"PC help\" (the owner's choice of 2026-09-28, the research audit's idea 12; docs/JARVIS-API.md section 84; backend jarvis_pc_help.py, routed by jarvis_brain_reads.py): five plain answers about the PC - why it is slow, how full its drives are, what is using the graphics card, how hot it is, when it last restarted. Read-only, no card, not held on a stale link; asked only on \"Check now\". Desktop: Settings, Hardware and models, PC help (hardware.rs get_pc_help, pc-help.js). Phone: Brain, PC help under Hardware (PcHelpPlate.kt, net/PcHelp.kt). The same five questions are answered in chat by jarvis_quick.py in both apps."),
    "/api/hardware/apply": ("ported", "Choose a setup, or forget the choice. Changes no model and no setting by itself: it lists the steps. Both apps hold choosing on a stale link; forgetting is not held."),
    "/api/hardware/create": ("ported", "One step of a chosen setup: make jarvis-chat / jarvis-long / jarvis-vision. ONE approval card (models_create, tier ask). Both apps post it only as a step read from the PC's own GET answer, and only the next step (hardware.rs step_request, Hardware.stepRequest)."),
    "/api/hardware/measure": ("ported", "Time each model of the setup on this PC and check it is all on the card. Both apps: one button, held on a stale link."),
    "/api/schedule": ("ported", "Coming up: timers, alarms, reminders, repeating jobs with their next time, and the to-do list (backend/schedule.patch, the owner's decisions of 2026-09-25; JARVIS-API section 21). Desktop: the Brain's Work tab (brain/schedule.rs brain_schedule, Brain only; the words taken out in Rust while the private lists are hidden) and the toast when a job goes off (stream.rs -> toast_fired, `?id=`). Phone: Brain, Coming up (ComingUpPlate.kt, net/Schedule.kt) and the notification when a job goes off (JarvisRuntime.onScheduleEvent -> ScheduleNotifier, `?id=`)."),
    "/api/schedule/act": ("ported", "ONE job: pause, resume, delete, done, and (2026-09-25) Snooze 10 minutes on something that just went off - the same buttons in both apps (adding time to a timer is said or typed to Jarvis); the phone's notification and the Windows toast carry Snooze too. No card. The one list form, also since 2026-09-25: clearing ONE named list after \"are you sure?\", with the count the app showed (brain_schedule_clear_list, JarvisRuntime.clearList). Both apps hold every one on a stale link (brain_schedule_act, JarvisRuntime.scheduleAct)."),
    "/api/briefing": ("ported", "The morning briefing (backend/briefing.patch, the owner's decisions of 2026-09-25; JARVIS-API section 22): the latest one, the briefing jobs and what a briefing includes. Desktop: Brain -> Work (brain/briefing.rs brain_briefing; the lines taken out in Rust while the private lists are hidden) and Settings -> Morning briefing (get_briefing_setup, the briefing itself taken out). Phone: Brain -> Morning briefing (BriefingPlate.kt, net/Briefing.kt). Setting one up and stopping one use /api/schedule/add and /act with kind \"briefing\" in both apps (set_briefing / stop_briefing, JarvisRuntime.setBriefing / stopBriefing), held on a stale link."),
    "/api/briefing/senders": ("ported", "\"Show who new emails are from\" in the morning briefing (on by default, the owner's decision of 2026-09-25): OFF is immediate, ON is ONE approval card on the PC (change_own_config). Desktop: Settings -> Morning briefing (brain/briefing.rs set_briefing_senders). Phone: Brain -> Morning briefing (BriefingPlate.kt, JarvisRuntime.setBriefingSenders). Both hold ON on a stale link and let OFF through; its state rides on GET /api/briefing."),
    "/api/briefing/now": ("ported", "\"Brief me now\": one put together on the PC without the model; with {\"missed\": true} (2026-09-25) \"What did I miss?\" - the same builder since the owner last talked to Jarvis. Reads in both apps, so not held on a stale link (brain_briefing_now, JarvisRuntime.briefingNow / briefingMissed)."),
    "/api/schedule/add": ("ported", "One to-do item, in the owner's own words - on a named list (\"shopping\") from that list's own Add box since 2026-09-25 - or one morning briefing that repeats (since 2026-09-25). Both apps add only these two here (brain_schedule_add_todo and Settings' set_briefing; JarvisRuntime.addTodo and setBriefing), held on a stale link; timers, reminders and tell-me-whens (kind tellme, since 2026-09-25) are set by saying or typing them to Jarvis, and a repeating job's approval card is raised by the PC."),
    "/api/search": ("ported", "Web search (backend/web-search.patch, the owner's decisions of 2026-09-25; JARVIS-API section 23): the five providers with the PC's own \"why use this one\" lines, which is chosen, whether each is ready, the SearXNG address, \"Ask before every web search\" and Whoogle's reason for being left out. Desktop: Settings, Web search (web_search.rs get_web_search, settings window only). Phone: Settings, Web search (WebSearchPlate.kt, net/WebSearch.kt). An Exa, Tavily or Brave key is typed on the desktop only, straight into Credential Manager - there is no route for one (ARCHITECTURE section 8)."),
    "/api/email/sending": ("ported", "Sending email (backend/email-send.patch, the owner's decision of 2026-09-25 after the Muse audit; JARVIS-API section 26): whether sending is set up, from which address, through which server - the PC's own line, never the password. Desktop: Settings, Sending email (email_sending.rs get_email_sending, settings window only). Phone: Settings, Sending email (EmailSendingPlate.kt, net/EmailSending.kt). Each email itself is an ordinary approval card in both apps (/api/pending), shown in full; the desktop's widget sends an email's Approve to the Jarvis bar."),
    "/api/search/settings": ("ported", "ONE web search setting per request: the provider or the SearXNG address (at once), \"Ask before every web search\" on (at once) or off (ONE approval card, stop_asking_before_every_web_search). Both apps hold it on a stale link (set_web_search, JarvisRuntime.setWebSearch)."),
    "/api/email/tidy": ("ported", "\"Inbox tidy by voice\" (backend/inbox-tidy.patch, jarvis_inbox_tidy.py; the owner's decision of 2026-09-28; JARVIS-API section 95): archive, star, mark as read or move to Trash a checked list of emails. The tidy itself is asked for in chat and decided on ONE ordinary approval card that lists every email (/api/pending; shown verbatim, and the desktop's widget sends its Approve to the Jarvis bar). This route is the status: whether a tidy is open to Undo, as counts and the PC's own words - never a sender or a subject. A read, not held on a stale link. Desktop: the Undo strip under the Jarvis bar's input (brain/inbox_tidy.rs inbox_tidy_read, inbox-tidy.js; the words taken out in Rust while Jarvis is locked or the lists are hidden). Phone: the Undo strip on Home (net/InboxTidy.kt, HomeScreen.kt InboxTidyPlate, JarvisRuntime.refreshInboxTidy)."),
    "/api/email/tidy/undo": ("ported", "Inbox tidy: Undo within 10 minutes - one tap, no card; it puts back exactly what the last tidy changed. Held on a stale link and while the words are hidden, in both apps (the button greyed, and the desktop's Rust and the phone's runtime refuse too). Desktop: brain/inbox_tidy.rs inbox_tidy_undo. Phone: JarvisRuntime.inboxTidyUndo."),
    "/api/reach": ("ported", "\"What Jarvis can reach\" (backend/reach.patch, jarvis_reach.py; the Muse audit, 2026-09-25; JARVIS-API section 24): every way Jarvis can reach something outside itself, whether each is on, where it goes (a host only) and whether it asks first, written by the PC from its settings - never by the model. A read, not held on a stale link. Desktop: Settings, What Jarvis can reach (reach.rs get_reach, settings window only). Phone: Settings, What Jarvis can reach (ReachPlate.kt, net/Reach.kt)."),
    "/api/asks_first": ("ported", "\"What asks first\" (backend/asks-first.patch, jarvis_asks_first.py; the owner's decisions of 2026-09-26 after the approvals audit; JARVIS-API section 32): every action and whether it asks first, grouped, in the PC's words, the lights setting, and whether this request may loosen (only one from the PC). A read, not held on a stale link. Desktop: Settings, What asks first (asks_first.rs get_asks_first, settings window only). Phone: Settings, What asks first (AsksFirstPlate.kt, net/AsksFirst.kt)."),
    "/api/asks_first/tier": ("ported", "\"Ask me first\" on ONE action of the short safe list (four reads, three note writes). Stricter ({\"ask\": true}) at once, no card, never held - both apps. Looser ({\"ask\": false}) is the desktop's only: one loosen_what_asks_first card that needs Windows Hello on the PC, held on a stale link (set_asks_first); the phone never sends it (AsksFirst.stricterBody) and the PC refuses it from any device but itself, and refuses the card's approval from any other device too (jarvis_owner_check.PC_ONLY_ACTIONS; ARCHITECTURE section 8)."),
    "/api/asks_first/lights": ("ported", "\"Lights, plugs and fans without a card\" (off by default): ON is ONE approval card on the PC (change_own_config), OFF is immediate. Both apps hold ON on a stale link and let OFF through (set_lights_without_card, JarvisRuntime.setLightsWithoutCard); its state rides on GET /api/asks_first."),
    "/api/asks_first/tools": ("deliberate", "\"Offer this to the AI model\" on the four reading tools (the owner's answer of 2026-09-27, ease-of-use audit): a DIFFERENT thing from /api/asks_first/tier - whether a tool is offered to the model AT ALL ([tools].enabled), never whether it asks first. {\"enabled\": true} is the desktop's only: one enable_reading_tool card that needs Windows Hello on the PC, held on a stale link (set_tool_enabled); the PC refuses it from any device but itself, and refuses the card's approval from any other device too (jarvis_owner_check.PC_ONLY_ACTIONS). {\"enabled\": false} is instant, but is still desktop-only by CLAUDE.md's standing rule against deep config editing on the phone - its state rides on GET /api/asks_first's new \"tools\" key, which the phone simply does not read. ARCHITECTURE section 8."),
    "/api/folders": ("ported", "\"Folders Jarvis may look in\" (backend/documents.patch, jarvis_documents.py; the owner's decisions of 2026-09-26: asking about PDFs and Word files, and the Notion import; JARVIS-API section 35): the list, in the PC's words, whether this request may add (only one from the PC), a waiting card, and whether PDF and Word reading is installed. A read, not held on a stale link. Desktop: Settings, Folders Jarvis may look in (folders.rs get_folders, settings window only). Phone: Settings, Folders Jarvis may look in (FoldersPlate.kt, net/Folders.kt). Asking about the files is ordinary chat from either app (the my_files tool runs on the PC)."),
    "/api/folders/remove": ("ported", "Take ONE folder off the list: at once, no card, never held on a stale link - it only lets Jarvis see less. Desktop: remove_folder (folders.rs). Phone: Remove on each folder (JarvisRuntime.removeFolder)."),
    "/api/folders/add": ("deliberate", "Adding a folder is the PC's alone (the owner's decisions of 2026-09-26; the feasibility audit's guardrail 1: \"one folder list, PC only\"): the desktop opens the Windows folder picker in Rust and the PC raises ONE approval card; the PC refuses the route from any other device (jarvis_owner_check.from_this_pc). A phone has no view of the PC's folders to pick from. ARCHITECTURE.md section 8."),
    "/api/memory/import_chats": ("deliberate", "\"Bring in chats from ChatGPT, Claude, Gemini or DeepSeek\" (the owner's choice of 2026-09-28, the research audit's idea 13; docs/JARVIS-API.md section 85; backend jarvis_history_import.py, import_history.py, history-import.patch): where a run on the PC is, as counts. The PC's alone: the export is a file on the PC, picked with the Windows file picker in Rust (brain/history_import.rs), and the run is started only from the PC. The phone shows what it makes - one card per possible fact - in its review queue, like any other card. ARCHITECTURE.md section 8."),
    "/api/memory/import_chats/start": ("deliberate", "Start reading an export on the PC (this PC only; the PC refuses any other device with 403): it only PROPOSES - every fact waits for its own yes, nothing is saved by itself. Held on a stale link. The phone has no file on the PC to choose. ARCHITECTURE.md section 8."),
    "/api/memory/import_chats/cancel": ("deliberate", "Stop an import after the chat being read; never held (it only does less). Only the desktop starts one, so only the desktop shows Stop. ARCHITECTURE.md section 8."),
    "/api/folders/import": ("deliberate", "Bringing in a Notion export is the PC's alone: the .zip is a file on the PC, picked with the Windows file picker in Rust and unzipped into a listed folder there; the PC refuses the route from any other device. ARCHITECTURE.md section 8."),
    "/api/sky": ("ported","The sun, the moon and the weather behind the animal faces and the robot (backend/sky.patch, jarvis_sky.py; the owner's decisions of 2026-09-28; JARVIS-API section 89). GET reads the settings and the weather now as five numbers, with the PC's own words; the phone and the desktop each work the sun and moon out themselves (sky.js / face/Sky.kt, held equal by sky-golden.json). POST is ONE change: show on or off and forget the town at once from either app; the weather source (off and Home Assistant at once, Open-Meteo ONE approval card). The town itself is typed on the PC only - the backend refuses it from any other device, and the phone has no field for it (docs/ARCHITECTURE.md section 8). Desktop: Settings, Animal options, Sun, moon and weather (sky.rs get_sky/set_sky; the Widget and the floating face read it too, sky-feed.js). Phone: Appearance, Animal options, Sun, moon and weather (SkyPlate.kt, net/SkySettings.kt)."),
    "/api/animal": ("ported","Animal options (backend/animal.patch, jarvis_animal.py; the owner's decisions of 2026-09-28, JARVIS-API section 93): \"Keep the animal still\" and the animal's behaviour switches (listening nods, focus buddy, small acknowledgements, petting, cute idle moments, seasonal touches; for every character face, the robot included), kept on the PC and shared by both apps - GET reads every switch with the PC's words; POST is ONE switch, at once, no card either way (turning one on waits for a live link). The same values ride in GET /api/appearance as `animal`, so the appearance event both apps follow repaints every face. Sharpness and frame rate stay per device (never sent). Desktop: Settings, Animal options (animal.rs get_animal/set_animal/migrate_animal_still, animal-settings.js; jarvis-link.js keeps the values for the face frames). Phone: Appearance, Animal options (AnimalOptionsPlate.kt, net/AnimalOptions.kt; JarvisRuntime.animalOptions/setAnimalOption)."),
    "/api/manner": ("ported","How Jarvis talks (backend/manner.patch, the owner's decision of 2026-09-25; JARVIS-API section 27): warm and brief (the default) or plain, with the PC's own words. GET reads it; POST is ONE change, at once, with no approval card either way - it changes only how answers are worded. Both apps hold the change on a stale link. Desktop: Settings, How Jarvis talks (plain_errors.rs get_manner/set_manner, settings window only). Phone: Settings, How Jarvis talks (MannerPlate.kt, net/Manner.kt)."),
    "/api/thinking": ("ported", "Per-model thinking levels (backend/thinking.patch, jarvis_thinking.py, Section 5.5): off, quick, deep, or auto per running model. GET reads running models and their supported levels; POST is ONE change with no approval card. Both apps hold the change on a stale link. Desktop: Settings, Thinking levels (plain_errors.rs get_thinking/set_thinking, thinking-settings.js). Phone: Settings, Thinking levels (ThinkingPlate.kt, net/Thinking.kt)."),
    "/api/voice/live": ("ported", "Jarvis Live (backend/live.patch, jarvis_live.py; the owner's decision and answers of 2026-09-28; docs/LIVE-DESIGN.md; JARVIS-API section 63): a back-and-forth voice conversation - GET the session (fixed words and numbers, never anything said), POST start (no card; held on a stale link; refused until the owner's voice is trained), stop (never held), extend, resume, mute/unmute. Desktop: the Jarvis bar's Live button and sign, the always-on-top badge and the tray row (live.rs, live-rules.js). Phone: Live screen, the Live microphone service and its notification (LiveScreen.kt, service/LiveService.kt, voice/LiveRules.kt)."),
    "/api/screen": ("ported", "\"Look at this\" and \"Watch with me\" (backend/screen.patch, jarvis_screen.py, jarvis_screen_win.py; the owner's decision of 2026-09-28; docs/SCREEN-DESIGN.md; JARVIS-API sections 62 and 96): GET the session (fixed words and minutes, never a program, a site, a title or a word from the screen), POST look, ask, start and extend - refused from any machine but the PC itself (a look is at the screen of the PC Jarvis runs on) - and stop and drop from anywhere (they only make Jarvis look less). Desktop: the Look at this key, the Jarvis bar's Watch button and strip, the always-on-top badge and the tray row (look.rs, look-rules.js). Phone: reads it (GET, and the screen_watch event) to say on Home when Jarvis is watching the PC, with Stop (POST stop, never held on a stale link); it never asks the PC to look or start - the PC refuses that from a phone - and its own looks at the phone's screen go through /api/chat (a screen_text part or a marked picture, JARVIS-API section 62.6), not through this route (HomeScreen.kt PcWatchingPlate, net/ScreenRules.kt)."),
    "/api/screen/picture": ("ported", "Picture mode for \"Look at this\" and \"Watch with me\" (backend/jarvis_screen_picture.py, answered by jarvis_screen.install; screen-picture.patch adds the gate lines; the owner's decision of 2026-09-29; docs/SCREEN-DESIGN.md; JARVIS-API section 96.1): a slow picture model on the PC's PROCESSOR that also looks at the picture of the screen on a one-card PC. GET reads the setting (on or off, whether it would work now, the measured seconds per look - never a guess - and the one PowerShell line that installs and measures the model); POST {\"enabled\"} turns it on (ONE approval card, screen_picture_enable, tier ask - nothing changes until a person says yes) or off (at once). Decided on the PC like every other approval-card switch, so both apps read and set it: the desktop in Settings, Look at this and Watch with me (look.rs screen_picture, look-settings.js, look-rules.js); the phone in Settings, Looking at your screen: pictures (net/ScreenPicture.kt, ScreenPicturePlate.kt). Neither app ever handles a picture for it."),
    "/api/browser/engine": ("ported", "The headless browser, Obscura (backend/browser-engine.patch, jarvis_browser_engine.py and jarvis_obscura.py; the owner's decision of 2026-09-29; JARVIS-API section 97): a browser with no window that Jarvis may choose, per task, instead of the visible one for plain web reading, always with stealth on; it never types a password and stops at a captcha or a sign-in page it recognises. GET reads the setting (on or off, which browser Jarvis uses by default, the install status in words, and the one PowerShell line that downloads one named release of Obscura and prints its checksums, without running it); POST {\"obscura\"} turns it on (ONE approval card, obscura_enable, tier ask - nothing changes until a person says yes) or off (at once, and it stops the program); POST {\"mode\"} picks Automatic, Visible or Headless at once. Decided on the PC like every other approval-card switch, so both apps read and set it: the desktop in Settings, Headless browser (browser_engine.rs, browser-engine.js, browser-engine-rules.js); the phone in Settings, Headless browser (net/BrowserEngine.kt, BrowserEnginePlate.kt). Neither app runs a browser, sees a web page or holds a proxy or an address for it."),
    "/api/form-review/picture": ("ported", "The picture on the SECOND card of a browser plan that ends in a form-sending click (backend/form-review.patch, jarvis_form_review.py; the owner's decision of 2026-09-30; docs/FORM-REVIEW-DESIGN.md): GET ?id= returns {\"ok\": true, \"jpeg\": <base64>, \"width\", \"height\"} for the `detail.picture` id of a browser_form_submit card that still waits, else 404 {\"ok\": false}. A read, so never held on a stale link. Both apps fetch it when the card carries `detail.picture` and show it only inside the unlocked app, in full view; neither keeps it (the desktop: brain/form_review.rs, form-review.js; the phone: net/FormReview.kt). Not on the widget, a notification or the home-screen widget, which stay title-only."),
    "/api/screen/never-look": ("deliberate", "The Never look at list (backend/screen.patch, jarvis_screen.py; the owner's decision of 2026-09-28): programs and websites Jarvis never looks at on THIS PC. The desktop reads it, adds to it at once (stricter) and asks to take an entry off (ONE approval card on the PC, because it loosens what Jarvis may see); the PC refuses the route from any other device, and a phone has no view of the PC's programs to pick from. The phone keeps its OWN list of apps, on the phone (net/ScreenNever.kt). ARCHITECTURE.md section 8."),
    "/api/focus": ("ported", "Focus sessions (backend/focus.patch, jarvis_focus.py; the owner's decision of 2026-09-25; JARVIS-API section 31): the countdown, booleans and counts, and the last report card - never what was in front on the PC. A read, not held on a stale link. Desktop: Brain -> Work -> Focus session and the widget's countdown that tints on a drift (brain/focus.rs focus_status). Phone: Brain, Focus session (FocusPlate.kt, net/Focus.kt)."),
    "/api/chatbot/status": ("ported", "\"Talk to a chatbot for me\" (backend/chatbot-routes.patch, jarvis_chatbot_routes.py over jarvis_chatbot.py; the owner's decisions of 2026-09-27 and 2026-09-28; JARVIS-API section 87): the chatbots (Gemini listed, not built yet), which version runs (one card or two), and one conversation with its transcript - the chatbot's words and the summary marked outside text, never read aloud. A read, not held on a stale link. Desktop: Brain -> Work (brain/chatbot.rs chatbot_status; the goal and the transcript taken out in Rust while the private lists are hidden). Phone: Brain, Talk to a chatbot for me (ChatbotPlate.kt, net/Chatbot.kt) and the ongoing notification (JarvisRuntime.watchChatbot -> ChatbotNotifier). Signing in to the chatbot's account is on the PC only (ARCHITECTURE section 8)."),
    "/api/chatbot/start": ("ported", "Ask for a conversation: ONE approval card on the PC (gate action chatbot_session, tier ask, a risky approval); nothing is sent before a yes. Both apps hold it on a stale link (chatbot_start, JarvisRuntime.chatbotStart)."),
    "/api/chatbot/stop": ("ported", "Stop one conversation. Never a card, never held on a stale link - it only makes Jarvis do less. Both apps (chatbot_stop, JarvisRuntime.chatbotStop), and the phone's ongoing notification's Stop (EventService ACTION_CHATBOT_STOP). Pause and Resume are /api/task/pause and /api/task/resume, already ported."),
    "/api/chatbot/compare/start": ("ported", "\"Ask several and compare\" (jarvis_chatbot_compare.py through jarvis_chatbot_routes.py; the owner's decision of 2026-09-28): two or more chatbots asked the same goal, ONE approval card (gate action chatbot_session, a risky approval) listing every chatbot by name and address, one conversation each, one after another, ONE summary at the end (agree, disagree - who said what -, sources not checked by Jarvis, who dropped out), outside text. Both apps hold it on a stale link (chatbot_compare_start, JarvisRuntime.chatbotCompareStart). The comparison rides on GET /api/chatbot/status (`compare`, `?compare=`)."),
    "/api/chatbot/compare/stop": ("ported", "Stop the whole comparison. Never a card, never held on a stale link. Both apps (chatbot_compare_stop, JarvisRuntime.chatbotCompareStop), and the phone's ongoing notification's Stop carries the comparison's id (EventService ACTION_CHATBOT_STOP). Pause and Resume are /api/task/*, acting on the whole comparison."),
    "/api/chatbot/limits": ("ported","New limits for a running or paused conversation: a NEW card; nothing changes unless a person says yes. Both apps hold it on a stale link (chatbot_limits, JarvisRuntime.chatbotLimits) and change the same three things: the most messages, the most minutes and the never-send words."),
    "/api/chatbot/support/start": ("ported", "\"Chat with customer support for me\" (jarvis_support.py through jarvis_chatbot_routes.py; the owner's decisions of 2026-09-28; JARVIS-API section 65): ONE approval card on the PC (gate action support_chat, a risky approval) listing the company and every detail Jarvis may give, word for word; nothing is sent before a yes. Both apps hold it on a stale link (support_start, JarvisRuntime.supportStart). The chat rides on GET /api/chatbot/status (`support`, `companies`, `support_tier`, `?support=`), already ported: Desktop Brain -> Work (brain/support.rs support_status), Phone Brain (SupportPlate.kt, net/Support.kt) and the ongoing notification (ChatbotNotifier.postSupport)."),
    "/api/chatbot/support/stop": ("ported", "Stop a support chat. Never a card, never held on a stale link. Both apps (support_stop, JarvisRuntime.supportStop), and the phone's ongoing notification's Stop carries the support chat's id (EventService ACTION_CHATBOT_STOP). Resume is /api/task/resume (its own card), already ported."),
    "/api/chatbot/support/takeover": ("ported", "Take over: Jarvis stops sending and the owner types in the chat window on the PC. Never a card, never held. Both apps (support_takeover, JarvisRuntime.supportTakeover)."),
    "/api/chatbot/support/answer": ("ported", "The owner's choice about a waiting offer OTHER than accepting (accepting is only ever the offer's own card, support_offer): Decline, Say something else (through the same last check), or Take over. Both apps; Decline and Say are held on a stale link, Take over is not (support_answer, JarvisRuntime.supportAnswer)."),
    "/api/chatbot/support/export": ("deliberate", "\"Export transcript\" is the PC's alone (docs/CHATBOT-DRIVER-DESIGN.md \"Customer-support chats\" section 6: \"the owner's tap on the PC, to a folder they pick\"): the desktop reads the plain text and saves it with the Windows \"Save as\" dialog in Rust (brain/support.rs support_export). The file is not encrypted, and a phone has no folder on the PC to put it in; the phone says \"Export transcript is on the PC only.\" ARCHITECTURE.md section 8."),
    "/api/media": ("ported", "\"Playing on your PC\" on the phone's Home (2026-09-28; backend jarvis_media.py, media.patch): what is playing on the PC, in its own sentence (net/PcMedia.kt). Since 2026-09-28 (\"Widgets you describe\", JARVIS-API.md section 86) the desktop reads it too, ONLY to decide play or pause for a widget's \"Play/pause PC\" button (brain/widgets.rs widget_board_action) - the same rule as the phone's tile (QuickTiles.playPauseAction). The desktop still shows no \"what's playing\" of its own: Windows' media controls are right there."),
    "/api/media/control": ("ported", "Play or pause on the PC, ONE action per tap, no card (the owner's decision of 2026-09-27). Phone: Home's media buttons and the Play/pause tile (JarvisRuntime.pcMediaControl). Desktop: only a widget's \"Play/pause PC\" button (brain/widgets.rs widget_board_action, 2026-09-28). Both held on a stale link."),
    "/api/widgets": ("ported", "\"Widgets you describe\" (the owner's choice of 2026-09-28, the SAFE version; docs/JARVIS-API.md section 86; backend jarvis_widgets.py): the saved widgets, the previews and the menu. A read. Desktop: Brain, Work, Widgets (brain/widgets.rs brain_widgets) and the widget window's picker (widget_board). Phone: Brain, Widgets (WidgetsPlate.kt). Names and parts hidden with the private lists."),
    "/api/widgets/show": ("ported", "One widget filled in now (section 86). Desktop: the widget window draws it in place of the face (brain/widgets.rs widget_board, widget-board.js). Phone: the home-screen \"Jarvis widget\" 1-3 (widget/JarvisBoardWidget.kt). Both draw only the five block kinds and the five tile buttons, and hide private words under App lock or \"Hide memory lists\"."),
    "/api/widgets/draft": ("ported", "A PREVIEW from the owner's own typed words: the PC's AI model makes a small JSON description from a fixed menu, and the PC checks it with plain code (section 86). Nothing is added. Desktop: brain_widgets_draft (pasted words are sent as pasted, which the PC refuses). Phone: JarvisRuntime.widgetDraft. Not held on a stale link."),
    "/api/widgets/add": ("ported", "Keep ONE preview exactly as shown (section 86). No approval card: a widget only shows what the apps show and its buttons are the Quick Settings tile actions. Held on a stale link in both apps (brain_widgets_add, JarvisRuntime.widgetAdd)."),
    "/api/widgets/discard": ("ported", "Drop ONE preview (section 86). Not held: it only drops (brain_widgets_discard, JarvisRuntime.widgetDiscard)."),
    "/api/widgets/delete": ("ported", "Delete ONE widget, at once, no are-you-sure (section 86). Held on a stale link in both apps (brain_widgets_delete, JarvisRuntime.widgetDelete)."),
    "/api/focus/start": ("ported", "Start a focus session (minutes, and optionally what it is on). No approval card (jarvis_focus.py, WHY THERE IS NO APPROVAL CARD). Both apps hold it on a stale link (focus_start, JarvisRuntime.focusStart)."),
    "/api/focus/act": ("ported", "ONE thing to the running session: pause, resume, +10 minutes, stop (both apps), and lock - the widget's Lock on, desktop only because it is about the PC's own screen. Both apps hold resume/extend (and the desktop lock) on a stale link and let pause and stop through (focus_act, JarvisRuntime.focusAct)."),
    "/api/focus/callout": ("deliberate", "The focus session's spoken line (\"YouTube can wait.\") names what was in front on the PC, so it stays on the PC: the backend refuses it to any address but this PC's own (loopback), and the desktop's Rust fetches it as sound to play (brain/focus.rs play_callout). The phone shows the countdown and the counts; watching and speaking are PC-only (the owner's decision: \"ON THE PC ONLY ... Nothing leaves the PC\"; ARCHITECTURE section 8)."),
    "/api/search/test": ("ported", "Test search: one search for a fixed harmless word through the chosen provider, and what happened in words - never another provider. Both apps hold it on a stale link (test_web_search, JarvisRuntime.testWebSearch)."),
    "/api/deep": ("ported", "Deep questions and their answers, newest first (backend/big-model.patch). Desktop: the Brain's Memory tab, Deep questions (get_deep). Phone: Brain, Deep questions. Both read it again on the `deep` event."),
    "/api/deep/ask": ("ported", "Queue one deep question for the big model; no card per question, the switch was approved (backend/big-model.patch). Desktop: the Brain's \"Ask slowly\" (ask_deep). Phone: the Brain's \"Ask slowly\". Both hold it on a stale link."),
    "/api/approve": ("ported", ""),
    "/api/attention": ("ported", ""),
    "/api/attention/mute": ("ported", ""),
    "/api/attention/unmute": ("ported", ""),
    "/api/chat": ("ported", ""),
    "/api/compute": ("ported", "Brain screen, read-only."),
    # /api/config is NOT here: it is only in the Brain's read allow-list
    # (brain/routes.rs, section "config") and no window asks for it, so the
    # desktop does not call it. If the phone ever calls it, rule 5 fails -
    # and it should stay off: deep config editing on the phone is out of
    # scope (CLAUDE.md).
    "/api/content-risk": ("ported", "Brain screen, read-only."),
    "/api/deny": ("ported", ""),
    "/api/digest": ("ported", ""),
    "/api/digest/seen": ("ported", ""),
    "/api/events": ("ported", ""),
    "/api/feedback/mark": ("ported", ""),
    "/api/graph": ("deliberate", "The memory graph is explicitly out of scope on the phone (CLAUDE.md)."),
    "/api/holds/cancel": ("ported", ""),
    "/api/initiative": ("ported", "Brain screen, read-only."),
    "/api/jobs": ("ported", ""),
    "/api/jobs/cancel": ("ported", ""),
    "/api/ledger": ("ported", "Brain screen, read-only."),
    "/api/memory/decide": ("ported", "The review queue: one card, one decision."),
    "/api/memory/edit": ("deliberate", "Rewording stored facts is deep memory editing; it stays on the desktop's Memory tab."),
    "/api/memory/entities": ("ported", "\"People and things\" (owner, 2026-09-30, docs/GALAXY-PANEL-DESIGN.md option B): the phone gets a plain grouped LIST of the names saved facts are linked to and the facts behind each (Brain, read-only, net/Entities.kt and ui/screens/EntitiesPlate.kt), hidden under Hide memory lists and chat history. Not the Galaxy or any map or links: the picture, the names under each fact, About <name> and the \"are these the same?\" merge card stay the desktop's. Backend: memory-entities.patch."),
    "/api/memory/export": ("deliberate", "A copy of everything Jarvis knows does not belong on a phone that can be lost."),
    "/api/memory/facts": ("ported", ""),
    "/api/memory/forget": ("ported", "Forget ONE fact (retired, not deleted; no undo). Desktop: Brain, Memory, every fact (brain_memory_forget, with an optional date). Phone, since automatic learning (owner, 2026-09-24: every auto-saved fact is listed in both apps with a one-tap Forget): Brain, Saved automatically, auto-saved facts only (AutoLearnPlate.kt, JarvisApi.forgetFact). Both ask first and hold it on a stale link. Rewording (/api/memory/edit) stays desktop-only."),
    "/api/memory/erase": ("ported", "\"Erase the words\" (owner, 2026-09-24): ONE fact's words wiped from the PC for good, its dates kept (backend/memory-erase.patch, rebuilt/jarvis_memory.py erase()). Offered wherever Forget is. Desktop: Brain, Memory, Saved automatically and every fact in What Jarvis knows about you, forgotten ones too (brain_memory_erase). Phone: Brain, Saved automatically (AutoLearnPlate.kt, JarvisApi.eraseFact). Both ask first in the same words and hold it on a stale link. Erasing a fact that was already forgotten, or never saved automatically, is desktop-only, like Forget of one (ARCHITECTURE.md section 8)."),
    "/api/memory/keep_both": ("ported", ""),
    "/api/memory/fact-history": ("deliberate", "\"History of this fact\" (the owner's choice of 2026-09-28; docs/JARVIS-API.md section 71; backend/brain-reads.patch, rebuilt/jarvis_memory.py fact_history_view()): every earlier and later wording of one fact, with the changed words marked - an erased version never with its words. Desktop: Brain -> Memory, on each fact in \"What Jarvis knows about you\" that has more than one version (brain/fact_history.rs, fact-history.js), hidden like every memory list. Kept off the phone (ARCHITECTURE.md section 8): the phone lists only facts saved automatically that are still in use, which are never corrections, and a view that brings back retired wordings of any fact is the deep memory editing that stays on the desktop."),
    "/api/memory/used": ("ported", "\"Used in this answer\" and \"Jarvis remembered N things\" (owner, 2026-09-25; backend/temporary-chat.patch, rebuilt/jarvis_memory.py used_view()): the words of the few facts an answer used (X-Jarvis-Route's injected_ids) or automatic learning just saved (the memory_saved event's ids), read by id only when the owner opens the line. A read, hidden like every memory list. Desktop: the quickbar under an answer, and the Brain's \"Jarvis remembered N things\" (brain/used.rs memory_used, answer-memory.js, brain.js), with Forget and Erase on each. Phone: Home under an answer, and the Brain's \"Jarvis remembered N things\" (UsedMemoriesPlate.kt, net/MemoryUsed.kt), with Forget on each; Erase stays in Saved automatically on the phone (ARCHITECTURE.md section 8)."),
    "/api/chat/sources": ("ported", "\"Where this came from\" (feasibility I42/I132, 2026-09-27; backend/answer-sources.patch, jarvis_sources.py): the notes, wiki pages, web results and files a reading tool actually returned this turn, by reference only, plus the quote check, read by the SAME turn_id \"Used in this answer\" and the right/wrong mark already use, once the answer finishes. A read, hidden under the exact same gate as \"Used in this answer\", not a second one. Desktop: the quickbar under an answer (brain/sources.rs chat_sources, answer-memory.js/memory-used.js extended). Phone: Home under an answer (net/ChatSources.kt, UsedMemoriesPlate.kt's ChatSourcesList), reusing ChatSession.turnId already tracked for the right/wrong mark."),
    # "Spending summaries" (2026-09-30; backend jarvis_spending.py, spending.patch;
    # JARVIS-API section 100, docs/FINANCE-DESIGN.md "Slice contract (frozen)").
    # Built on the backend first; each app builds against the frozen contract.
    "/api/chat/table": ("ported", "The spending table a chat answer announced with `: jarvis-table <id>` in its stream (or `jarvis_table` on a stream:false body): title, columns, sections, caveats, kept two hours in memory only, never in chat history. Both apps draw it natively in the chat; hidden under \"Hide memory lists and chat history\" and, on the desktop, while App lock is on; phone screenshots blocked in those two states. A read, not held on a stale link."),
    "/api/spending": ("ported", "Spending settings: the saved bank-file layouts (names and choices only), the categories, the files waiting for their columns to be checked, and whether this request may edit (only the PC). A read. Desktop: Settings, Spending. Phone: the categories read-only, and \"set up on the PC\" (ARCHITECTURE section 8, one-sided on purpose)."),
    "/api/spending/profile": ("deliberate", "GET: the proposal for a bank file's columns (the first five rows, hidden; PC only); with &again=1 a fresh proposal with the saved choices filled in - nothing is deleted. POST: save the columns the owner confirmed, or with preview:true count what the choices would do before saving (PC only, no card: the owner's own tap on their own file). Desktop only, on purpose: bank files live on the PC, adding a folder is PC-only, and a phone screen is a poor place to map columns (ARCHITECTURE section 8)."),
    "/api/spending/profile/delete": ("deliberate", "Forget a saved layout (PC only). Desktop only, like the layout box (ARCHITECTURE section 8)."),
    "/api/spending/categories": ("deliberate", "Save or reset the category words (PC only; editing re-runs the totals at once; no card). Desktop only: the phone shows the list read-only (no deep config editing on the phone)."),
    "/api/spending/suggest": ("deliberate", "Category proposals for shop names no rule catches, from the local model (PC only). Nothing is saved until the owner taps Add these rules. Desktop only, like the categories editor."),
    # "Retirement what-if" (2026-09-30; backend jarvis_retirement.py, retirement.patch;
    # JARVIS-API section 103, docs/FINANCE-DESIGN.md "Retirement contract (frozen)").
    "/api/retirement/defaults": ("ported", "The Retirement what-if form: its fields, limits, units, the made-up default figures marked as placeholders, the fixed disclaimer and the words. A read, any paired device. Both apps draw the same form from it (desktop: Brain -> Work, Retirement; phone: Brain, Retirement)."),
    "/api/retirement/run": ("ported", "Play out the what-if from the numbers typed in the form: the answer only as ranges, with the sentence \"This is a simplified what-if, not financial advice.\" added by the backend. Nothing is computed or stored on the phone, and the backend stores nothing either; screen only, never read aloud, hidden under \"Hide memory lists and chat history\". Both apps."),
    # "Activity heatmap and balance chart" (2026-09-30; backend jarvis_progress.py, progress.patch;
    # JARVIS-API section 105, docs/GOALS-PROGRESS-DESIGN.md "Progress contract (frozen)").
    # Both apps build in Brain -> Projects (desktop brain/progress.rs + projects-panel.js; phone
    # net/Progress.kt + ProjectsPlate.kt). Flip these to "ported" when each app calls them.
    "/api/progress/activity": ("ported", "The activity heatmap: the last 4 to 26 weeks (12 by default) of days, each with a count and a shade level, Monday first, none in the future, and the one line \"Last 12 weeks: 23 things on 14 days.\" A count is steps ticked plus numbers logged; a health or money number shades its day and is never named (`keep_on_screen`). No streak, no percentage, no red. Screen only; hidden under \"Hide memory lists and chat history\". A read. Both apps, in Brain -> Projects."),
    "/api/progress/balance": ("ported", "The balance chart: GET the 3 to 8 areas the owner picked (each a number or goal against its own target, with the value printed and no overall score) and what can be picked; POST replaces the whole pick (or clears it) - no card, the owner's own display choice. Screen only; a private area is flagged and hidden under \"Hide memory lists and chat history\". Both apps, in Brain -> Projects."),
    "/api/memory/profile": ("ported", "\"Always keep in mind\" (owner, 2026-09-24; backend/memory-profile.patch, rebuilt/jarvis_memory.py pin()): the facts Jarvis reads with every question, word for word, at most 1,200 characters. GET lists them, POST pins or unpins ONE fact - no card, held on a stale link. Desktop: Brain, Memory - its own section, and Pin / Unpin on every current fact in Saved automatically and What Jarvis knows about you (brain/profile.rs). Phone: Brain - its own section with Unpin, and Pin / Unpin in Saved automatically, the one list of current facts the phone shows (ProfilePlate.kt, AutoLearnPlate.kt, net/MemoryProfile.kt); pinning a fact that was not saved automatically is desktop-only, like Forget of one (ARCHITECTURE.md section 8)."),
    "/api/memory/shared": ("ported", "\"Between us\" (owner, 2026-09-27; backend/memory-shared.patch, rebuilt/jarvis_memory.py shared()): facts tagged as a shared joke or nickname (meta.kind = \"shared\"), a label, never a new way to save a fact. GET lists them, POST tags or untags ONE fact - no card, held on a stale link. Desktop: Brain, Memory - its own section with \"Not between us\" and Forget, and a \"Between us\" toggle on every current fact in Saved automatically and What Jarvis knows about you (brain/shared.rs). Phone: Brain - its own section with \"Not between us\" and Forget, and the same toggle in Saved automatically, the one list of current facts the phone shows (SharedPlate.kt, AutoLearnPlate.kt, net/MemoryShared.kt); tagging a fact that was not saved automatically is desktop-only, like Pin of one (ARCHITECTURE.md section 8)."),
    # Automatic learning (docs/JARVIS-API.md section 19, 2026-09-24): built
    # on the backend and both apps at once. Desktop: Brain, Memory
    # (brain/auto_learn.rs); phone: Brain, What Jarvis remembers and Saved
    # automatically (net/AutoLearn.kt, AutoLearnPlate.kt).
    "/api/memory/learning/auto": ("ported", "\"Learn automatically\": ON is one approval card (learning_auto_enable), OFF is immediate. Both apps hold ON on a stale link and say \"waiting\" while the card is in the queue, wherever it was raised. Its state rides on GET /api/memory/learning."),
    "/api/memory/learning/sensitive": ("ported", "\"Also remember sensitive topics automatically\" (off by default): ON is one approval card (learning_sensitive_enable), OFF is immediate. The same holds as the other switch. Both apps say, in the same words, that passwords, PINs, account and ID numbers, birthdays, phone numbers and email addresses always wait for a yes (the PC enforces it)."),
    "/api/memory/auto": ("ported", "\"Saved automatically\": the facts saved without a card, newest first, with Load older, a \"said aloud\" mark for voice, \"said again N times\", \"true from <date>\" (one shared wording fixture, contract/memory-words-cases.json) and a Forget on each. Both apps read it again on the memory_saved event (ids only, never the text) and hide it under the phone's \"Hide memory lists and chat history\"."),
    "/api/memory/learning": ("ported", "The learning on/off switch on the phone's Brain screen (MemoryCountsSection). Turning learning ON raises an approval card on the PC (learning-asks.patch, 2026-09-24): the phone says \"waiting\" while a learning_enable card is in the queue, and holds ON on a stale link; OFF is immediate. GET /api/memory/learning (auto-learn.patch, planned for both apps) reads both switches and whether a card for either is waiting."),
    "/api/memory/pending": ("ported", "The review queue."),
    "/api/memory/sleep_time": ("ported", ""),
    "/api/memory/status": ("ported", "Memory counts, whether search-by-meaning is on, the re-ranker's state and \"said again\", read-only, in one set of words (memory-words.js / MemoryWords.kt, one shared fixture). Phone: Brain, What Jarvis remembers (MemoryCountsPlate.kt, net/MemoryCounts.kt)."),
    "/api/models": ("ported", "Allowed by the owner 2026-09-18: the installed list, not a catalogue."),
    "/api/models/install": ("ported", "Allowed by the owner 2026-09-20: a typed name, raising an approval card."),
    "/api/models/rollback": ("ported", ""),
    "/api/models/switch": ("ported", "Allowed by the owner 2026-09-18, raising an approval card."),
    "/api/notes/capture": ("ported", ""),
    "/api/pending": ("ported", ""),
    "/api/pending/{id}/amend": ("ported", "A note on one waiting approval card; approves nothing (backend/task-control.patch). Desktop: amend_approval (commands.rs). Phone: JarvisApi.amend."),
    "/api/power": ("ported", ""),
    "/api/second-card": ("ported", "The second graphics card's switches (backend/second-card.patch, 2026-09-24). Desktop: Settings, Second graphics card (vision.rs reads it for pictures). Phone: Brain screen's Second graphics card plate, and chat's photo button. What was found plus one switch at a time; each ON is an approval card."),
    "/api/second-card/suggest": ("ported", "\"When to suggest the bigger model\" (backend/second-card-suggest.patch, jarvis_second_card.py/jarvis_agent.py, 2026-09-27): the two settings that decide whether Jarvis may OFFER \"One bigger model on both cards\" on its own - NO approval card either way, unlike every switch above. Desktop: Settings, Second graphics card, same section (commands.rs set_second_card_suggest, settings window only). Phone: Brain screen's Second graphics card plate, the same rows as the switches above (SecondCardPlate.kt, net/SecondCard.kt)."),
    "/api/retrieve": ("todo", "The HUD's retrieval trace (which facts an answer reached for). Not in JARVIS-API.md yet; decide what it should show before porting."),
    "/api/show": ("not-backend", "Ollama's /api/show on loopback: does the model take pictures (vision.rs)."),
    "/api/shutdown": ("deliberate", "Shutting the backend down from a phone is a foot-gun: the phone would then have nothing to reach and no way to undo it."),
    "/api/skills": ("ported", "Brain screen, read-only."),
    "/api/skills/decide": ("ported", "Removing a skill, after an are-you-sure, as on the desktop (Brain, Model, Skills). Phone: Brain, Skills (SkillsPlate.kt, net/Skills.kt). Never held on a stale link; a card the PC raises is shown as waiting. Removal only - no app can install a skill."),
    "/api/status": ("ported", ""),
    "/api/tags": ("not-backend", "Ollama's /api/tags on loopback: the installed model list (commands.rs). Not a Jarvis route."),
    "/api/task": ("deliberate", "\"Jarvis is working on your screen, 0:42 - Stop\" (the owner's choice of 2026-09-28, the research audit's idea 17): the desktop widget reads which task runs to show a line with a clock while a Windows screen-control plan (control_computer) is moving the mouse and typing on the PC, and its Stop is the Stop everything hotkey (screen_work.rs). It is about the PC's own screen, seen by whoever sits at it; the phone already has Stop everything and the task Pause/Stop, driven by the event stream's activity, and needs no second poll. ARCHITECTURE section 8."),
    "/api/task/note": ("ported", ""),
    "/api/task/pause": ("ported", ""),
    "/api/task/resume": ("ported", ""),
    "/api/task/stop": ("ported", ""),
    "/api/tool_updates": ("deliberate", "\"Check for tool updates\" (the owner's own request, made directly; backend/jarvis_tool_updates.py, tool-updates.patch; JARVIS-API.md section 48): whether the owner has ever approved a check, whether one is running now, the last card's outcome, and the last finished report of outdated Python packages, Rust crates and pinned GitHub tools. PC-only (ARCHITECTURE.md section 8): checking dependency versions is developer/maintenance tooling, the same reasoning that keeps deep config editing and the model catalogue off the phone. Desktop: Settings, \"Check for tool updates\" (tool_updates.rs get_tool_updates, settings window only)."),
    "/api/tool_updates/check": ("deliberate", "Starts the check (or raises the one-time approval card) and returns at once - never blocks on the check itself, which can take a few minutes. Report only: it never installs, upgrades or changes a file - only the exact command to run yourself. Desktop-only for the same reason as the row above (tool_updates.rs check_tool_updates)."),
    "/api/stop_all": ("ported", "\"Stop everything\" (2026-09-25, backend/jarvis_stop_all.py). Desktop: the Alt+Shift+X hotkey (commands.rs stop_everything_now), which stops the desktop's speech first. Phone: Home's \"Stop everything\" button, shown while Jarvis is busy, which stops the phone's speech first. Neither is held on a stale link."),
    "/api/undo": ("ported", ""),
    "/api/undo/revert": ("ported", ""),
    "/api/version": ("ported", "The handshake. Both apps also list its capabilities by name: desktop Settings, \"What this backend supports\" (its own card, after About) (get_backend_capabilities); phone, \"This backend\"."),
    "/api/visual-spec": ("deliberate", "The phone bundles its own copy of the spec and checks it in a unit test (SpecDriftTest); JARVIS-API.md: the phone never fetches it."),
    "/api/voice/say": ("ported", ""),
    "/api/voice/status": ("ported", "What the PC's voice can do. Desktop: \"hey Jarvis\" listening reads it (voice.rs), and Settings, Voice shows it, with training, how strict, private answers and the guided test drawn from it (get_voice_status, voice-panel.js). Phone: Platform checks, Your voice and the wake-word card."),
    "/api/voice/enroll": ("ported", "\"Train my voice\" (backend/voice-enroll.patch) and, since 2026-09-24, its other modes (docs/JARVIS-API.md section 16): training in rounds, strictness, private answers, the guided test. Desktop: Settings, Voice, for this PC's microphone (mic=desktop; voice_training.rs send_voice_training, set_voice_setting, measure_voice, cancel_voice_training). Phone: Train my voice (JarvisApi.enrollVoice and the calibrate / threshold modes)."),
    "/api/voice/turn": ("deliberate", "Smart Turn, 'finished or only paused?'. The phone runs the same model "
                        "itself (assets/turn/, voice/SmartTurn.kt), so its audio never leaves it to ask; "
                        "the desktop asks its own PC over loopback."),
    "/api/voice/utterance": ("ported", ""),
    # Custom voices (backend/voices.patch, 2026-09-24): built on the backend
    # first (docs/JARVIS-API.md section 15). Both apps call all five since
    # 2026-09-24: desktop Settings, Jarvis's voice (voice_training.rs,
    # voice-panel.js); phone Platform checks -> Jarvis's voice
    # (ui/screens/VoicesScreen.kt, net/CustomVoices.kt).
    "/api/voice/voices": ("ported", "Custom voices: the list, which one Jarvis speaks in and why the built-in voice is used instead, the better voice's state, and say() timings (docs/JARVIS-API.md section 15). Desktop: Settings, Jarvis's voice (get_custom_voices). Phone: Platform checks, Jarvis's voice (VoicesScreen.kt), re-read on the `voices` event."),
    "/api/voice/voices/create": ("ported", "Add a custom voice: a recording and its exact words. One approval card (custom_voice); a voice that sounds like the owner's is refused. Desktop: create_custom_voice (the sentence shown, or a WAV file and typed words). Phone: record a sentence it shows (the words are that sentence - no speech-to-text) or pick a WAV and type its words; held on a stale link."),
    "/api/voice/voices/active": ("ported", "Speak in a custom voice (one approval card) or back in the built-in one (immediate). Desktop: set_active_voice. Phone: the custom voice is held on a stale link, the built-in one always goes."),
    "/api/voice/voices/delete": ("ported", "Delete a custom voice. Immediate; the built-in voice comes back if it was the one in use. Desktop: delete_custom_voice, after an are-you-sure. Phone: asks first on the phone, never held."),
    "/api/voice/voices/speed": ("ported", "How fast Jarvis speaks: Slower, Normal or Faster, the PC's own choices and words (GET /api/voice/voices `speed`). No card either way; held on a stale link like every change. Desktop: set_voice_speed (Settings, Jarvis's voice). Phone: the Voices screen's speed chips (JarvisRuntime.setVoiceSpeed)."),
    # Which of Kokoro's own voices speaks (2026-09-27, ease-of-use audit row
    # 13): the exact same shape as speed above, right next to it.
    "/api/voice/voices/speaker": ("ported", "Jarvis's built-in voice: which of Kokoro's own voices, the PC's own choices and words (GET /api/voice/voices `speaker`). No card either way; held on a stale link like every change. Desktop: set_voice_speaker (Settings, Jarvis's voice). Phone: the Voices screen's voice chips (JarvisRuntime.setVoiceSpeaker)."),
    # The voice follows the face (2026-09-27): an animal face speaks in its
    # own built-in voice - an on/off switch, the same no-card shape.
    "/api/voice/voices/face": ("ported", "Voice follows the face: with an animal face showing, the built-in voice becomes that animal's (GET /api/voice/voices `face_voice`, the PC's own words and line). An on/off switch, OFF by default (the owner, 2026-09-28; the one-time question below turns it on); no card either way; held on a stale link like every change. Desktop: set_voice_face (Settings, Jarvis's voice). Phone: the Voices screen's switch (JarvisRuntime.setVoiceFace)."),
    # Each animal's own voice (2026-09-28): under "Voice follows the face",
    # a built-in voice, a pitch and a pace per animal - the same no-card
    # shape - and "Try it", which plays one fixed line and changes nothing.
    "/api/voice/voices/face_offer": ("ported", "The one-time animal voice question (the owner, 2026-09-28): the first time an animal face is picked, GET /api/voice/voices `face_voice.offer` is {\"face\", \"question\": \"The Red Panda has its own voice. Use it?\", \"use\": \"Use it\", \"keep\": \"Keep my voice\"} (null otherwise - not an animal, or that animal already answered; asked whether the switch is on or off); this route takes the answer, \"use\" or \"keep\", kept per animal (an animal speaks as itself only with the switch on and its answer \"use\"). No card either way; held on a stale link. Desktop: answer_face_voice_offer (the Faces window after Use this face, and Settings under \"Voice follows the face\"). Phone: Appearance under the face picker and Voices above the switch (JarvisRuntime.answerFaceVoiceOffer)."),
    "/api/voice/voices/face_animal": ("ported", "Each animal's voice: for the red panda, pygmy owl, sea otter, monkey and robot, one of the built-in voices, a pitch (3 steps deeper to 4 higher, in half steps) and a pace (GET /api/voice/voices `face_voice.animals`, the PC's own choices and words), and \"Reset to its own voice\". No card either way; held on a stale link like every change. Desktop: set_voice_animal / reset_voice_animal (Settings, Jarvis's voice - a slider for the pitch). Phone: the Voices screen's animal plate (JarvisRuntime.setVoiceAnimal - Deeper/Higher buttons for the pitch)."),
    "/api/voice/voices/sample": ("ported", "\"Hear it\" for one built-in voice, by name (Kokoro v1.0, 2026-09-29): the PC says one fixed line of its own in that voice and sends the WAV; no setting, card, event or log line, never a recorded voice, so it is not held on a stale link. A button on every voice row in both apps, the same words (\"Hear it\", \"Playing American (female) - Bella.\", \"That was American (female) - Bella.\"); refused while Jarvis is talking or listening, while the talk button or Jarvis Live has the microphone and while App lock would ask again, and stopped the moment a question or an answer starts. One at a time on the PC (429 in words). Desktop: hear_voice_sample (Settings, Jarvis's voice, played in the Settings window like Try it). Phone: the Voices screen's Hear it (VoiceSession.hearVoiceSample; JarvisRuntime.hearVoice adds the App lock check; VoiceSession.voiceBusy now also counts Jarvis Live)."),
    "/api/voice/voices/face_animal/try": ("ported", "\"Try it\" for one animal's voice: the PC says one fixed line of its own in that voice and sends the WAV; nothing is changed or kept, so it is not held on a stale link. The same words in both apps (\"Asking the PC for the sound…\", \"Playing the Red Panda's voice.\", \"That was the Red Panda's voice.\"); refused while Jarvis is talking or listening, and stopped the moment a question or an answer starts, so the microphone never hears it. One at a time on the PC (429 in words). Desktop: try_voice_animal (Settings, Jarvis's voice - played in the Settings window, so the faces in the other windows do not move with it; refused while the talk button records, and told by the voice-capture-started, voice-speech-started, voice-heard, face-voice and stop-everything events). Phone: the Voices screen's Try it (VoiceSession.tryAnimalVoice, stopped by VoiceSession.turnStarting from the talk button, \"hey Jarvis\" and Train my voice)."),
    "/api/voice/voices/better": ("ported","The better voice (F5-TTS on the second graphics card): ON is one approval card (better_voice_enable), OFF is immediate. Desktop: set_better_voice, offered only with a capable second card. Phone: offered only when a capable second card is there; ON held on a stale link, OFF always goes."),
    # The voice flow (backend/voice-flow.patch, 2026-09-24): built on the
    # backend first, in both apps since 2026-09-25. Its other parts are on
    # routes both apps already call - `?source=barge_in` / `&waited_ms=` on
    # /api/voice/utterance and the `flow` block of /api/voice/status - so
    # only this one is new.
    "/api/voice/moment": ("ported", "The \"One moment.\" clip, a WAV in the voice Jarvis speaks in now (made once per voice, kept in memory). Both apps fetch it when flow.moment.key changes and play it once per spoken question when a tool starts, before the answer makes a sound, never over it (docs/JARVIS-API.md section 17). Desktop: voice_flow.rs get_voice_moment, main.js. Phone: JarvisApi.voiceMoment, VoiceSession.toolStarted."),
    "/api/voice/wake": ("ported", "The wake-word switch; turning it on raises an approval card, turning it off is immediate. Both apps can do both: desktop Settings, Voice (set_wake_word; ON also from the Jarvis bar's listen button), phone Platform checks."),
    "/api/watch": ("ported", "Watches - the GitHub topics Jarvis keeps an eye on. Desktop: Brain, Watch tab. Phone: Brain, Watches (WatchPlate.kt, net/Watch.kt)."),
    "/api/watch/add": ("ported", "Watch a topic. The phone holds it on a stale link (it turns something on) and shows a card if the PC raises one."),
    "/api/watch/remove": ("ported", "Forget a topic, after a warning. Never held on a stale link."),
    "/api/watch/report": ("ported", "What is new - a peek that marks nothing read."),
    "/api/watch/seen": ("ported", "Mark these read - a POST on purpose, so opening a link cannot clear the list."),
    # Chat history on the PC (docs/JARVIS-API.md section 18, 2026-09-24):
    # built on the backend and both apps at once.
    "/api/history": ("ported", "Chat history kept on the PC, encrypted (docs/JARVIS-API.md section 18): the switch, why nothing is being kept (if so), how long it is kept, and conversations newest first with Load older. Since the chat audit (2026-09-28) each row carries its kind (chat, live, support, chatbot, compare) and `?kind=` narrows the list (\"Show\": Live only and the rest). Desktop: the Brain's History tab (brain_history_list). Phone: Brain, Chat history (HistoryScreen.kt, net/ChatLog.kt)."),
    "/api/history/conversation": ("ported", "One conversation, read-only, with where each of the owner's messages came from (shared, pasted, from clipboard). Since the chat audit (2026-09-28) it says its kind and whether it can be carried on (\"Continue this chat\": a chat or a Live session - never a support, chatbot or comparison record, each saying why). Desktop: History, Open (brain_history_open); the Jarvis bar reads the one chat it carries on (chat_continue_open, also for Live's \"Move it here\"). Phone: History screen; JarvisRuntime.continueChat carries it on on Home."),
    "/api/memory/fact-chat": ("ported", "\"Which chat did this fact come from?\" (the chat audit, 2026-09-28; docs/JARVIS-API.md section 79.4; jarvis_brain_reads.fact_chat): its title and when, so \"Erase the words\" with \"Also delete the chat it came from\" names the chat first, and says plainly when none is on record. A read; it deletes nothing. Desktop: brain/history.rs brain_fact_chat (the title taken out while the private lists are hidden), brain.js eraseFact and the bar's answer-memory.js. Phone: AutoLearnPlate.kt's erase confirm, JarvisRuntime.factChat, net/ChatLog.kt."),
    "/api/memory/conversation-facts": ("ported", "\"Facts this chat taught\" (the owner's choice of 2026-09-28; docs/JARVIS-API.md section 79; jarvis_brain_reads.py, rebuilt/jarvis_memory.py conversation_facts_view()): deleting a chat in History lists the facts still in use that it taught, each with a tick box, NONE ticked, then the usual \"are you sure?\"; each ticked fact is forgotten through the ordinary /api/memory/forget, one fact per call - there is no list form of Forget. Desktop: brain/conversation_facts.rs brain_conversation_facts (the facts taken out while the memory lists are hidden), brain.js deleteConversation. Phone: HistoryScreen.kt's Conversation, JarvisRuntime.chatFacts, net/ChatLog.kt (History is hidden with the memory lists under \"Hide memory lists and chat history\")."),
    "/api/photo/scan": ("ported", "\"Photo to reminder\" (the owner's choice of 2026-09-28; docs/JARVIS-API.md section 83; backend/photo-reminder.patch, jarvis_photo_remind.py): the PC reads the words in one picture with Windows' own text recognition, finds a date, time and title with plain code, and PROPOSES a reminder - it sets nothing up. The words are outside text. Desktop: \"Find a date in it\" on the Jarvis bar's screen capture, and \"Choose a picture...\" in the Brain's Coming up (brain/photo_reminder.rs photo_scan). Phone: \"Find a date in it\" under a picture shared to Jarvis (JarvisRuntime.scanPhotoForDate, PhotoReminderDialog). The owner's tap adds ONE reminder through /api/schedule/add (no card); the phone also offers \"Also on my phone\" (its own calendar)."),
    "/api/history/search": ("ported", "\"Search what was said\" in the kept chats, not just their titles (the owner's choice of 2026-09-28; docs/JARVIS-API.md section 71; backend/brain-reads.patch, jarvis_chat_log.ChatLog.search): each kept turn opened IN MEMORY for that one search - no index, nothing written, nothing handed to the AI model - with a short snippet per conversation. Desktop: the Brain's History search box (brain/history.rs brain_history_search, refused while the private lists are hidden). Phone: the History screen's search box (HistoryScreen.kt, net/ChatLog.kt), hidden with the list under \"Hide memory lists and chat history\". \"Find in this chat\" is client-side in both, over the conversation already open."),
    "/api/history/delete": ("ported", "Delete ONE conversation, after a confirm. There is no delete-all route, on purpose. Both apps hold it on a stale link (it cannot be undone), like Forget on the desktop."),
    "/api/history/tags": ("ported", "Chat tags (the owner's decision of 2026-09-30; docs/JARVIS-API.md section 99; jarvis_chat_log.py, chat-history.patch): GET reads the tag list with counts; POST adds, renames, restyles, reorders and deletes tags. No card; every write is held on a stale link. Tag names are sealed on the PC and hidden with the titles under \"Hide memory lists and chat history\"."),
    "/api/history/tag": ("ported", "File one chat under a tag, or unfile it (section 99). No card; held on a stale link. Also what tapping a row does after \"label my chat about the boiler as Home\" (X-Jarvis-Route file_under)."),
    "/api/history/fork": ("ported", "\"Fork from here\" (the owner's choice of 2026-09-30; docs/JARVIS-API.md section 110, docs/CHAT-TAGS-DESIGN.md \"Fork contract\"): copies the first turns of a kept chat, up to the message the owner picked, into a NEW chat titled \"Fork of ...\" (same tag, outside-text marks copied, never a crisis, support, chatbot or comparison chat). No card; held on a stale link; hidden with the memory lists. Desktop: brain/history.rs (brain_history_fork), brain.js History. Phone: net/ChatLog.kt, HistoryScreen.kt, JarvisRuntime.forkChat."),
    "/api/history/tags/suggest": ("ported", "\"Suggest tags overnight\" (the owner's decision of 2026-09-30; docs/JARVIS-API.md section 104, docs/OVERNIGHT-TAGS-DESIGN.md; jarvis_tag_suggest.py, tag-suggest.patch, chat-history.patch): GET reads {enabled, paused, waiting, last_day}; POST {\"enabled\": bool} turns it on with ONE approval card (chat_tags_suggest_on) or off at once. Each suggestion is its own card (chat_tag_suggest) in the ordinary approvals flow; nothing is filed without a tap. Both apps show the switch row in History -> Tags (desktop: brain/history.rs brain_history_tag_suggest, brain.js, history-tags.js; phone: net/TagSuggest.kt, HistoryTags.kt SuggestTagsRow). The suggestion card shows text_hidden while the private lists are hidden (desktop: stream.rs hide_private_cards; phone: PendingRows.kt). Held on a stale link."),
    "/api/history/mark": ("ported", "\"New section here\" (the owner's decision of 2026-09-30; docs/JARVIS-API.md section 106, docs/OVERNIGHT-TAGS-DESIGN.md section 5; jarvis_chat_log.py, chat-history.patch): a view-only divider above one of the owner's messages in a long chat (10+ turns, up to 20 per chat); the conversation read gains marks, markable and mark_why. No card. Both apps draw the button and the divider (desktop: brain/history.rs brain_history_mark, history-view.js, brain.js; phone: net/ChatMark.kt, HistoryScreen.kt). Held on a stale link."),
    "/api/history/settings": ("ported", "\"Keep chat history on this PC\": ON is one approval card (history_enable), OFF is immediate; and \"Delete conversations older than\" (keep_days). Both apps hold ON and every keep change on a stale link; OFF is never held."),
    "/api/wiki": ("ported", "The wiki builder's documents and their state (backend/wiki.patch, 2026-09-24). Both apps list them; neither browses files or reads pages - the vault reaches the phone through Syncthing."),
    "/api/wiki/ingest": ("ported", "\"Add to wiki\" for one document, then its job. Raises one approval card (wiki_update); nothing is written before it is answered."),
    # Backups (backend/jarvis_backup.py, backup.patch; the owner's decision
    # of 2026-09-27; JARVIS-API.md section 44): one locked backup file with
    # a recovery code shown once. GET /api/backup carries only
    # `last_backup_at` off the PC (the phone's "last backup: ...") but the
    # full status (the folder, waiting cards, counts) with `here: true` -
    # one route, two depths, like /api/folders. Setting the folder, backing
    # up, listing, previewing and restoring are the PC's alone.
    "/api/backup": ("ported", "\"Backups\": the folder, whether a card is waiting, the last backup and the last restore's outcome (a one-time recovery code included exactly once). Desktop: Settings, Backups (backup.rs get_backup, settings window only), the full view. Phone: Brain, \"Last backup: ...\" only (docs/ARCHITECTURE.md section 8) - it reads the same route and shows nothing else from it."),
    "/api/backup/folder": ("deliberate", "Setting the backup folder is the PC's alone: the desktop opens the Windows folder picker in Rust (the same one \"Folders Jarvis may look in\" uses) and the PC raises ONE approval card (change_own_config); the PC refuses the route from any other device (jarvis_owner_check.from_this_pc). A phone has no view of the PC's folders to pick from. ARCHITECTURE.md section 8."),
    "/api/backup/now": ("deliberate", "\"Back up now\" writes one file into a folder already on this PC; no card, but still refused from any device but the PC. A phone backing up the PC's own files makes no sense. ARCHITECTURE.md section 8."),
    "/api/backup/list": ("deliberate", "The kept backup files, by name and date - PC-only, the same reason as the folder above: a phone has nothing to do with a list of files on the PC's disk. ARCHITECTURE.md section 8."),
    "/api/backup/restore/preview": ("deliberate", "Decrypts a backup to show counts and a date, PC-only - the backup file is on the PC's disk, and the recovery code is typed there. ARCHITECTURE.md section 8."),
    "/api/backup/restore": ("deliberate", "Restoring replaces memory, chat history, review decks, settings and notes with an older backup: PC-only, ONE approval card that always needs Windows Hello (jarvis_owner_check.PC_ONLY_ACTIONS refuses its approval from any other device too, whatever the gate's own risk table says). ARCHITECTURE.md section 8."),
    "/api/backup/delete-older": ("deliberate", "Deleting older backups makes one fresh locked backup and removes older files from the PC's disk: PC-only (POST /api/backup/delete-older), raises ONE change_own_config approval card on the PC. The phone shows the read-only notice that copies in older backups stay until they age out. ARCHITECTURE.md section 8."),
    # Goals: a plan the owner edits, one card per acting step (the owner's
    # "build it now", 2026-09-27; JARVIS-API.md section 59; backend
    # jarvis_goals.py). Both apps: the desktop's Brain -> Work -> Goals
    # (brain/goals.rs) and the phone's Brain -> Goals (net/Goals.kt).
    "/api/goals": ("ported", "The list of goals, plus the PC's own limits (steps per plan, open goals, text lengths). A read. Desktop: Brain -> Work -> Goals (brain/goals.rs brain_goals). Phone: net/Goals.kt."),
    "/api/goals/{id}/accept": ("ported", "The owner's edited plan (or the draft as it stood) is kept, and the goal becomes active. The ONE place this feature can raise a card - the backend's own weekly-check-in `schedule_repeat` card (the same one a repeating reminder or the morning briefing already raises), approving nothing that acts. Held on a stale link (brain_goals_accept)."),
    "/api/goals/{id}/step": ("ported", "Marks one step done or not - no card, the same shape as ticking off a to-do item. Held on a stale link (brain_goals_step)."),
    "/api/goals/{id}/stop": ("ported", "Stops tracking the goal and deletes its check-in job on the PC - no card, immediate, the same rule every \"stop tracking this\" control in this project follows. Held on a stale link (brain_goals_stop)."),
    # Quiz me on a text (the owner's decision of 2026-09-30; JARVIS-API.md
    # section 98; backend jarvis_quiz.py, quiz.patch). Both apps: the desktop's
    # Brain -> Quiz (brain/quiz.rs) and the phone's Brain -> Quiz (net/Quiz.kt).
    "/api/quiz": ("ported", "Start a quiz: the owner's pasted text (200-20000 characters) and a question count go to the local model, which writes the questions; kept in memory only, no card, never learned from. Desktop: brain/quiz.rs. Phone: net/Quiz.kt."),
    "/api/quiz/{id}": ("ported", "Read one open quiz (the questions, the marks so far; a question's source passage only once it is answered). Held on a stale link (not_found). Desktop: brain/quiz.rs. Phone: net/Quiz.kt."),
    "/api/quiz/{id}/answer": ("ported", "Mark one typed answer against that question's passage only (Got it / Partly / Not yet plus one sentence); no card. Desktop: brain/quiz.rs. Phone: net/Quiz.kt."),
    "/api/quiz/{id}/finish": ("ported", "End the quiz with the short \"look at these again\" summary; the quiz is forgotten. Desktop: brain/quiz.rs. Phone: net/Quiz.kt."),
    "/api/quiz/{id}/stop": ("ported", "Stop and forget the quiz at once, no summary. Desktop: brain/quiz.rs. Phone: net/Quiz.kt."),
    "/api/youtube": ("ported", "\"Quiz me on a YouTube video\" (the owner's decision of 2026-09-30; backend/jarvis_youtube.py, backend/youtube.patch; docs/JARVIS-API.md section 112; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 14). GET: whether the PC has the feature, its fixed words and limits, and the newest request (or null). A read; also how an app finds out the PC does not have it yet (a 404). Desktop: brain/youtube.rs (brain_youtube_info). Phone: net/Youtube.kt."),
    "/api/youtube/quiz": ("ported", "\"Quiz me on a YouTube video\" (the owner's decision of 2026-09-30; backend/jarvis_youtube.py, backend/youtube.patch; docs/JARVIS-API.md section 112; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 14). POST {url, count?, title?, language?}: checks the link's shape, raises ONE approval card for that link (gate action youtube_captions_read, tier ask, a risky approval; it breaks YouTube's terms and may be blocked), and answers 202 with a request. Nothing is fetched before a yes. Held on a stale link in both apps. Desktop: brain/youtube.rs (brain_youtube_start). Phone: net/Youtube.kt."),
    "/api/youtube/{id}": ("ported", "\"Quiz me on a YouTube video\" (the owner's decision of 2026-09-30; backend/jarvis_youtube.py, backend/youtube.patch; docs/JARVIS-API.md section 112; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 14). GET one request: waiting / fetching / writing / ready (with the ordinary quiz, marked provenance outside) / denied / timed_out / withdrawn / refused / failed (with a plain message). Polled about every 2 seconds while the card is open. A read, not held on a stale link. Desktop: brain/youtube.rs (brain_youtube_get). Phone: net/Youtube.kt."),
    "/api/youtube/{id}/cancel": ("ported", "\"Quiz me on a YouTube video\" (the owner's decision of 2026-09-30; backend/jarvis_youtube.py, backend/youtube.patch; docs/JARVIS-API.md section 112; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 14). POST: withdraw a request whose card has not been answered; a yes that arrives later fetches nothing. Refused once the captions are being read. Not held on a stale link (it only ever makes things safer). Desktop: brain/youtube.rs (brain_youtube_cancel). Phone: net/Youtube.kt."),
    '/api/quiz-cloud': ("ported", '"Grade this better" (the owner\'s decision of 2026-09-30; backend/jarvis_quiz_cloud.py, backend/quiz-cloud.patch; docs/JARVIS-API.md section 113; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 15). GET: whether the PC has the feature, its fixed words, which cloud services are set up (no key), and the newest request (or null). A read; a 404 means the PC does not have it yet. Desktop: brain/quiz_cloud.rs (brain_quiz_cloud_info). Phone: net/QuizCloud.kt.'),
    '/api/quiz-cloud/grade': ("ported", '"Grade this better" (the owner\'s decision of 2026-09-30; backend/jarvis_quiz_cloud.py, backend/quiz-cloud.patch; docs/JARVIS-API.md section 113; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 15). POST {quiz_id, service?}: checks the quiz (text quiz, answered, no crisis answer, nothing private), picks the cheapest set-up cloud service and raises ONE approval card (gate action quiz_cloud_grade, tier ask, a risky approval) listing exactly what would leave the PC; answers 202 with a request. Nothing is sent before a yes. Held on a stale link in both apps. Desktop: brain/quiz_cloud.rs (brain_quiz_cloud_start). Phone: net/QuizCloud.kt.'),
    '/api/quiz-cloud/{id}': ("ported", '"Grade this better" (the owner\'s decision of 2026-09-30; backend/jarvis_quiz_cloud.py, backend/quiz-cloud.patch; docs/JARVIS-API.md section 113; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 15). GET one request: waiting / sending / ready (with the new marks and the quiz) / denied / timed_out / withdrawn / refused / failed (with a plain message). Polled about every 2 seconds while the card is open. A read, not held on a stale link. Desktop: brain/quiz_cloud.rs (brain_quiz_cloud_get). Phone: net/QuizCloud.kt.'),
    '/api/quiz-cloud/{id}/cancel': ("ported", '"Grade this better" (the owner\'s decision of 2026-09-30; backend/jarvis_quiz_cloud.py, backend/quiz-cloud.patch; docs/JARVIS-API.md section 113; the frozen contract is docs/STUDY-FROM-TEXT-DESIGN.md section 15). POST: withdraw a request whose card has not been answered; a yes that arrives later sends nothing. Refused once it is being sent. Not held on a stale link. Desktop: brain/quiz_cloud.rs (brain_quiz_cloud_cancel). Phone: net/QuizCloud.kt.'),
    # Review decks and typed Spanish practice (the owner's decision of
    # 2026-09-30; JARVIS-API.md section 102; backend jarvis_decks.py,
    # decks.patch; docs/QUIZ-DECKS-DESIGN.md). Both apps: "My study decks"
    # beside the quiz in Brain (desktop brain/decks.rs, phone net/Decks.kt and
    # ui/screens/DecksPlate.kt). The optional `keep` body of
    # /api/quiz/{id}/finish is a field, not a route. The one desktop-only
    # item, the later unencrypted export (a file dialog), is not built.
    "/api/decks": ("ported", "The deck list (name, cards, ready, paused), the day's counts and the plain \"N cards ready\" line (GET); a new empty deck (POST). No card: the owner's own tap saves the owner's own words, sealed on the PC. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/decks/settings": ("ported", "New cards a day, 0 to 20 (default 5). A setting the owner changes; no card. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/decks/{id}/act": ("ported", "Rename, pause, resume or delete one deck; delete asks \"are you sure?\" in the app and is immediate. No card. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/decks/{id}/cards": ("ported", "One deck's cards (front, back, passage) for managing them; hidden by both apps under Hide memory lists and chat history. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/decks/{id}/cards/{id}/act": ("ported", "Edit a card's front or back, or delete the card (\"are you sure?\" in the app). No card. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/review": ("ported", "The next card to review, the ready count and the run's progress (at most 20 at a time). Reviewing calls no model. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/review/reveal": ("ported", "Show a card's back (the answer and its source passage, with the label for a model-written key). A card can be rated only after this. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/review/rate": ("ported", "The owner's own rating (Didn't remember / Remembered, with effort / Remembered / Easy); py-fsrs works out when the card comes back. Held on a stale link. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    "/api/review/more": ("ported", "\"Do 10 more\": raises the current run's limit of 20 by 10. Desktop: brain/decks.rs. Phone: net/Decks.kt."),
    # Topic controls (the owner's decision of 2026-09-30; JARVIS-API.md section
    # 107; backend jarvis_topics.py, topics.patch, rebuilt/jarvis_memory.py;
    # docs/TOPIC-CONTROLS-DESIGN.md, "Slice contract (frozen)"). Built on the
    # backend first; both apps get Brain -> Memory -> Topics. `planned` until
    # each app calls it. Deliberately one-sided when built (ARCHITECTURE.md
    # section 8): the phone does not edit a topic's keywords (typing long lists
    # is deep configuration) and has no Galaxy; every route below is still
    # called by both apps.
    "/api/topics": ("ported", "GET: the topics with counts, modes, unchecked labels and the week's skip counts. POST {op: add|rename|style|move|words|private|delete}: the owner's own topic list. Turning off / marking private is at once; clearing the private mark or deleting a private topic into a looser home is ONE card (topic_loosen). Held on a stale link. Hidden names under Hide memory lists."),
    "/api/topics/mode": ("ported", "POST {id, mode}: Learn and use / Use but don't learn / Learn but don't use / Off. Stricter is at once; a private topic turned back on is 202 waiting with ONE card (topic_loosen). Held on a stale link."),
    "/api/topics/preview": ("ported", "GET ?id=&mode=: what the change would do, in numbers and a plain line (the picker shows it); never any fact words."),
    "/api/topics/review": ("ported", "GET ?after=&limit=: the facts Jarvis sorted by guessing and the owner has not checked, in batches of 10 grouped by topic. A memory list: hidden under Hide memory lists."),
    "/api/topics/file": ("ported", "POST {ids, topic_id} files facts by the owner's tap; POST {ids, confirm: true} is \"These are right\". A batch out of a private topic into a looser one is ONE card."),
    "/api/topics/hidden": ("ported", "GET ?id=: the facts of an Off topic (\"Show them\"). A memory list: hidden under Hide memory lists."),
    "/api/topics/settings": ("ported", "POST {model_help}: let the local model suggest a topic for a few Unsorted facts a night (off to start; no card - it reads the owner's own facts with the local model, as the learner already does)."),
    # Projects (the owner's decision of 2026-09-28; backend/jarvis_projects.py,
    # projects.patch; JARVIS-API section 88). Both apps since build step 3:
    # desktop Brain -> Projects (brain/projects.rs projects_read /
    # projects_write / projects_choose_folder, Brain window only;
    # projects.js, projects-panel.js), phone Brain -> Projects
    # (ProjectsPlate.kt, net/Projects.kt, JarvisRuntime.projectsRead /
    # projectsWrite). Choosing a coding project's folder and writing a
    # benchmark's command are fields of a body, not routes: the phone never
    # sends them and shows "Set on your PC", and the PC refuses them from any
    # other device (ARCHITECTURE section 8). Every change is held on a stale
    # link in both apps except Shareable OFF.
    # "Forget a time frame" (the owner's decision of 2026-09-28;
    # backend/jarvis_forget_range.py, forget-range.patch; JARVIS-API section
    # 64). Both apps: the desktop's Brain -> History, the phone's Brain.
    "/api/memory/forget_range": ("ported", "Forget a time frame: the status (GET - a card waiting, the 10-minute Undo, the days a spoken request filled in) and \"Forget these\" (POST - the ticked ids; the PC raises ONE approval card listing every item). Both apps; held on a stale link and refused while the list is hidden."),
    "/api/memory/forget_range/preview": ("ported", "Forget a time frame: the facts saved and the chats from some days, each with its words (GET). Both apps; the words hidden with the private lists."),
    "/api/memory/forget_range/undo": ("ported", "Forget a time frame: Undo within 10 minutes of the card's approval - one tap, no card, never held on a stale link. Both apps."),
    "/api/projects": ("ported", "Projects: the list (GET) and creating one (POST). Both apps; the phone creates life projects only (a coding project's folder, and an app Jarvis builds - new or adopted from the list's unlinked_apps - are set up on the PC: nothing on the phone can fill an app, ARCHITECTURE section 8)."),
    "/api/projects/{id}": ("ported", "One project: read it (GET) or change what the owner typed (POST) - instructions, notes, and clearing the folder. Both apps; choosing the folder is the desktop's (the Windows picker, projects_choose_folder)."),
    "/api/projects/{id}/delete": ("ported", "Delete one project after \"are you sure?\". Both apps."),
    "/api/projects/{id}/shareable": ("ported", "The Shareable switch: ON is one approval card on the PC, OFF is instant and never held on a stale link. Both apps."),
    # An app inside a project (docs/APPS-IN-PROJECTS-DESIGN.md, JARVIS-API section 92).
    "/api/projects/{id}/app/tasks": ("deliberate", "Start a task in an app project (POST): an empty copy of the app to work in, no card. The desktop's (New task on a project's page). The phone reads an app's open tasks from the project itself and can look at, merge and discard them, but starts none: with no way to paste a change in (deep editing stays off the phone) an empty task has nothing to offer there. The backend would take it from either app. ARCHITECTURE section 8."),
    "/api/projects/{id}/app/tasks/{id}": ("ported", "Read one task of an app: its files and the whole comparison (GET). Both apps show the whole change before Merge; the phone pages it and opens Merge only on the last page."),
    "/api/projects/{id}/app/tasks/{id}/files": ("deliberate", "Paste a change into a task (POST, `<<<FILE>>>` blocks). The PC only (403 pc_only): a paste of code is deep editing, which stays off the phone (CLAUDE.md standing rule), and it lands only in the task's own copy - the merge card decides. The desktop's paste box. ARCHITECTURE section 8."),
    "/api/projects/{id}/app/tasks/{id}/merge": ("ported", "Merge a task into its app: raises ONE risky approval card (app_merge_change) with every file and the whole change, approved on either device (Windows Hello on the PC, the screen lock on the phone; never from a widget or notification). Both apps; held on a stale link."),
    "/api/projects/{id}/app/tasks/{id}/discard": ("ported", "Throw a task away after \"are you sure?\"; a card waiting for it is withdrawn. Both apps; held on a stale link."),
    "/api/projects/{id}/benchmarks": ("ported", "Define a benchmark. Both apps for a number; a coding command is the desktop's (the PC refuses it from anywhere else)."),
    "/api/projects/{id}/benchmarks/{id}": ("ported", "One benchmark: its chart points (GET) or a change (POST) - both apps use it for \"Mark private\"."),
    "/api/projects/{id}/benchmarks/{id}/delete": ("ported", "Delete one benchmark after \"are you sure?\". Both apps."),
    "/api/projects/{id}/benchmarks/{id}/log": ("ported", "Log one number, the owner's own tap, no card. Both apps; a private number's answer stays out of anything spoken."),
    "/api/projects/{id}/benchmarks/{id}/results/{id}/delete": ("ported", "Remove one logged number (a typo). Both apps."),
    "/api/projects/{id}/benchmarks/{id}/unmark": ("ported", "Take a private mark off a benchmark (the owner, 2026-09-28): the owner's own mark at once; a mark Jarvis made from the name raises ONE change_own_config card. Both apps."),
    # Pairing a phone by QR code, with a key per device (docs/PAIRING-DESIGN.md
    # phase 1, docs/JARVIS-API.md section 90; backend/jarvis_devices.py).
    "/api/devices": ("ported", "The device list (docs/JARVIS-API.md section 90.4): This PC, every paired device with its own Remove, and the old shared key's row - never a key or a hash. Desktop: Settings, Devices. Phone: Settings, Devices (DevicesPlate.kt)."),
    "/api/devices/remove": ("ported", "Remove ONE device, immediate, no card (it only takes access away, like Forget); a list is refused. Both apps ask \"Remove <name>?\" first."),
    "/api/devices/shared": ("ported", "Retire the old shared key for other devices ({\"retired\": true}): immediate, from either app; refused (409 uses_it_yourself) when the request itself used the shared key from another device. Bring it back ({\"retired\": false}) is the desktop's only: PC only, ONE unretire_shared_key card with Windows Hello, refused under Lockdown - the phone never sends it (docs/PAIRING-DESIGN.md 7.2, ARCHITECTURE section 8)."),
    "/api/pair/start": ("deliberate", "Starting a pairing is the PC's alone (docs/PAIRING-DESIGN.md 6.1 and section 12): the QR code and the typed code are shown on the PC and the pair_device card is approved there with Windows Hello; the backend refuses the route from any other device (403 pc_only). ARCHITECTURE section 8."),
    "/api/pair/session": ("deliberate", "Watching a pairing is the PC's alone: the Devices panel that shows the QR code reads it every 2 s; PC only on the backend (403 pc_only). ARCHITECTURE section 8."),
    "/api/pair/cancel": ("deliberate", "Cancelling a pairing is the PC's alone (the panel's Cancel); PC only on the backend. ARCHITECTURE section 8."),
}
STATUSES = {"ported", "deliberate", "todo", "not-backend", "planned"}

# Every route the PHONE calls that the desktop does not - parity the other way.
#
# "phone-only"    - kept off the desktop on purpose; the reason is the point
# "desktop-todo"  - the desktop should have it too, and nobody has built it
PHONE_ONLY = {
    "/api/notifications/watch": ("phone-only", "The smartwatch notification setting (the owner's decision, 2026-09-25, reconfirmed 2026-09-27, Q17). A smartwatch pairs with a phone, never a Windows PC; the setting still lives on the PC, like every other approval-card switch, but only the phone ever reads or writes it (docs/ARCHITECTURE.md §8)."),
    # "Solve it here" (the owner's decision of 2026-09-28): a captcha or
    # sign-in page handed to the owner's PHONE. On the PC the browser window
    # is right there; the desktop shows the same alert (handoff.js, from
    # /api/chatbot/status) and never pictures or relays anything.
    "/api/chatbot/handoff/start": ("phone-only", "\"Solve it here\" (the owner's decision, 2026-09-28): a captcha or sign-in page handed to the phone. On the PC the window is right there; the desktop shows the same alert from /api/chatbot/status and points at it (docs/ARCHITECTURE.md §8)."),
    "/api/chatbot/handoff/frame": ("phone-only", "One picture of the paused browser window, for the phone's Solve it here screen. The PC shows the real window (docs/ARCHITECTURE.md §8)."),
    "/api/chatbot/handoff/input": ("phone-only", "The owner's taps and typing from the phone, to the paused window only. On the PC the owner uses the window itself (docs/ARCHITECTURE.md §8)."),
    "/api/chatbot/handoff/end": ("phone-only", "Ends the phone's hand-off. The desktop never starts one (docs/ARCHITECTURE.md §8)."),
    "/api/pair/claim": ("phone-only", "The phone's half of pairing (docs/PAIRING-DESIGN.md 6.2): the phone that scanned the QR code or typed the code asks for its own key, with no key of its own yet; mesh only on the backend, and refused from the PC itself (\"this PC already has its own key\"). ARCHITECTURE section 8."),
    "/api/pair/collect": ("phone-only", "The phone collects its new key, once, after the pair_device card was approved on the PC (docs/PAIRING-DESIGN.md 6.2); mesh only, refused from the PC itself. ARCHITECTURE section 8."),
    "/api/devices/approval-key": ("phone-only", "The phone turns on signed approvals (docs/PAIRING-DESIGN.md 11.2, docs/JARVIS-API.md section 91): it sends its Keystore public key, and ONE register_approval_key card is approved on the PC with Windows Hello. The desktop is the PC - it holds the shared key and approves risky cards with Windows Hello itself - so it has no signing key to register and only READS the result (`approval_key` in the device list). ARCHITECTURE section 8."),
    "/api/approve/challenge": ("phone-only", "The phone asks for a one-use challenge before signing a risky approval with its fingerprint or PIN (docs/PAIRING-DESIGN.md 11.3, docs/JARVIS-API.md section 91). The desktop's own risky approvals are checked by Windows Hello on the PC, not by a signature, so it never calls this. ARCHITECTURE section 8."),
    "/api/notifications/phone": ("phone-only", "Reading phone notifications (the owner's decision, CLAUDE.md 2026-09-26; built 2026-09-28; docs/JARVIS-API.md §61). A Windows desktop has no equivalent to \"which app posted a notification\" - NotificationListenerService is Android-only. The setting still lives on the PC, like every other approval-card switch, but only the phone ever reads or acts on it (docs/ARCHITECTURE.md §8)."),
}
PHONE_STATUSES = {"phone-only", "desktop-todo"}

_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_HTML = re.compile(r"<!--.*?-->", re.S)
# `//` at the start of a line, or after whitespace - never the `//` inside
# "http://", which has a colon before it.
_LINE = re.compile(r"(^|\s)//.*$", re.M)


def strip_comments(text: str, ext: str) -> str:
    if ext == ".html":
        text = _HTML.sub("", text)
    return _LINE.sub(r"\1", _BLOCK.sub("", text))


def normalise(route: str) -> str:
    """`/api/pending/$encodedId/amend` -> `/api/pending/{id}/amend`."""
    segs = route.rstrip("/").split("/")
    return "/".join("{id}" if _IS_PH.match(seg) else seg for seg in segs)


def routes_in(text):
    return {normalise(m) for m in ROUTE.findall(text)}


_ENTRY = re.compile(r'\(\s*"([A-Za-z0-9_]+)"\s*,\s*"(/api/[^"?]+)')


def allowlist_entries(text: str, const: str):
    """(section, route) pairs from `const NAME: ... = &[ ... ];`."""
    m = re.search(rf"\b{const}\b[^=]*=\s*&\[(.*?)\];", text, re.S)
    if not m:
        return None
    return [(sec, normalise(route)) for sec, route in _ENTRY.findall(m.group(1))]


def scan(dirs, allow=None):
    """{route: {files}} for every call. With `allow` (a dict), allow-list
    files are not scanned for calls; their entries go into allow[file] as
    (section, route) pairs instead."""
    found = {}
    for rel, exts in dirs:
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            print(f"::error::{rel} is not in this checkout; has it moved?")
            sys.exit(2)
        for dirpath, _, names in os.walk(base):
            if "node_modules" in dirpath:
                continue
            for n in names:
                ext = os.path.splitext(n)[1]
                if ext not in exts:
                    continue
                path = os.path.join(dirpath, n)
                rel_path = os.path.relpath(path, ROOT).replace(os.sep, "/")
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = strip_comments(fh.read(), ext)
                if allow is not None and rel_path in ALLOWLISTS:
                    const = ALLOWLISTS[rel_path][0]
                    entries = allowlist_entries(text, const)
                    if entries is None:
                        print(f"::error::{rel_path} has no {const} list any more; "
                              "update ALLOWLISTS in tools/check_parity.py.")
                        sys.exit(2)
                    allow[rel_path] = entries
                    continue
                for r in routes_in(text):
                    found.setdefault(r, set()).add(rel_path)
    return found


def sections_asked(command):
    """Every quoted word in a desktop window file that calls `command`."""
    words = set()
    for rel, _ in DESKTOP_DIRS:
        for dirpath, _, names in os.walk(os.path.join(ROOT, rel)):
            if "node_modules" in dirpath:
                continue
            for n in names:
                ext = os.path.splitext(n)[1]
                if ext not in (".js", ".mjs", ".html"):
                    continue
                with open(os.path.join(dirpath, n), encoding="utf-8", errors="replace") as fh:
                    text = strip_comments(fh.read(), ext)
                if command in text:
                    words |= set(re.findall(r"[\"']([A-Za-z0-9_]+)[\"']", text))
    return words


def apply_allowlists(found, allow):
    """Count the allow-list entries a window asks for as calls. Returns the
    (file, section, route) entries no window asks for."""
    unused = []
    for rel, entries in sorted(allow.items()):
        asked = sections_asked(ALLOWLISTS[rel][1])
        for sec, route in entries:
            if sec in asked:
                found.setdefault(route, set()).add(rel)
            else:
                unused.append((rel, sec, route))
    return unused


# X-Jarvis-Route FIELDS the apps read (not HTTP routes: the scan above cannot see
# them). name -> (desktop status, phone status, why). "ported": the app's source must
# mention the field. "planned": built on the backend, not in that app yet; a warning
# says to reclassify it once the app reads it.
ROUTE_FIELDS = {
    "menu_visibility": (
        "ported", "ported",
        "\"Show or hide menus\" by asking Jarvis (2026-09-30; JARVIS-API section 109; "
        "backend jarvis_menus.py + jarvis_quick.py; docs/MENU-VISIBILITY-DESIGN.md). "
        "{\"action\", \"target\"}: each app applies it to its OWN per-device list - there is "
        "no HTTP route and no card. Phone: net/MenuVisibility.kt, ChatSession. Desktop: "
        "menu-visibility.js, settings.js, brain.js, main.js."),
}


def _mentions(dirs, word):
    for rel, exts in dirs:
        base = os.path.join(ROOT, rel)
        for dirpath, _, names in os.walk(base):
            if "node_modules" in dirpath:
                continue
            for n in names:
                if os.path.splitext(n)[1] not in exts:
                    continue
                with open(os.path.join(dirpath, n), encoding="utf-8", errors="replace") as fh:
                    if word in strip_comments(fh.read(), os.path.splitext(n)[1]):
                        return True
    return False


# Routes the phone builds from a constant (`"${Youtube.PATH}/${cur.id}"`), so no
# full `/api/...` literal exists for `scan` to find. Each is counted as called by
# the phone ONLY while the named file still contains the named text; delete the
# entry if the call goes.
PHONE_BUILT_ROUTES = {
    "/api/youtube/{id}": ("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
                          '"${com.jarvis.client.net.Youtube.PATH}/${cur.id}"'),
    "/api/youtube/{id}/cancel": ("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
                                 '"${com.jarvis.client.net.Youtube.PATH}/${cur.id}/cancel"'),
    "/api/quiz-cloud/{id}": ("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
                             '"${com.jarvis.client.net.QuizCloud.PATH}/${cur.id}"'),
    "/api/quiz-cloud/{id}/cancel": ("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
                                    '"${com.jarvis.client.net.QuizCloud.PATH}/${cur.id}/cancel"'),
}


def phone_built_routes():
    found = {}
    for route, (rel, needle) in PHONE_BUILT_ROUTES.items():
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
                if needle in strip_comments(fh.read(), os.path.splitext(rel)[1]):
                    found[route] = {rel}
        except OSError:
            pass
    return found


def check_route_fields(problems, warnings):
    for name, (d_status, p_status, _) in ROUTE_FIELDS.items():
        in_desk = _mentions(DESKTOP_DIRS, name)
        in_phone = _mentions(PHONE_DIRS, name)
        if p_status == "ported" and not in_phone:
            problems.append(f"route field {name} is classified 'ported' on the phone but no "
                            "phone source mentions it.")
        if d_status == "ported" and not in_desk:
            problems.append(f"route field {name} is classified 'ported' on the desktop but no "
                            "desktop source mentions it.")
        if d_status == "planned" and in_desk:
            warnings.append(f"route field {name} is 'planned' for the desktop but its sources "
                            "now mention it - reclassify it as 'ported'.")


def main():
    allow = {}
    desk_at = scan(DESKTOP_DIRS, allow)
    unused_allow = apply_allowlists(desk_at, allow)
    phone_at = scan(PHONE_DIRS)
    for route, files in phone_built_routes().items():
        phone_at.setdefault(route, set()).update(files)
    desk, phone = set(desk_at), set(phone_at)
    problems, warnings = [], []

    for r, (s, _) in CLASSIFICATION.items():
        if s not in STATUSES:
            problems.append(f"{r} has an unknown status {s!r}.")
    for r, (s, _) in PHONE_ONLY.items():
        if s not in PHONE_STATUSES:
            problems.append(f"{r} has an unknown phone-only status {s!r}.")
        if r in CLASSIFICATION:
            problems.append(f"{r} is in both CLASSIFICATION and PHONE_ONLY; keep one.")

    for r in sorted(desk - set(CLASSIFICATION)):
        problems.append(
            f"{r} is called by the desktop ({', '.join(sorted(desk_at[r]))}) and is not "
            "classified in tools/check_parity.py. Someone added a feature; decide whether "
            "the phone should have it.")

    by = lambda st: {r for r, (s, _) in CLASSIFICATION.items() if s == st}  # noqa: E731
    for r in sorted(by("ported") - phone):
        problems.append(
            f"{r} is classified 'ported' but the phone does not call it. "
            "The classification has drifted from the code.")
    for r in sorted(by("deliberate") & phone):
        problems.append(
            f"{r} is classified 'deliberate' (kept off the phone: {CLASSIFICATION[r][1]}) "
            f"but the phone calls it ({', '.join(sorted(phone_at[r]))}).")
    for r in sorted(by("todo") & phone):
        warnings.append(f"{r} is 'todo' but the phone now calls it - reclassify it as 'ported'.")
    for r in sorted(by("planned") & desk):
        warnings.append(f"{r} is 'planned' but the desktop now calls it - reclassify it as "
                        f"'ported' (if the phone calls it too) or 'todo'.")
    for r in sorted(by("planned") & phone - desk):
        warnings.append(f"{r} is 'planned' and the phone calls it; the desktop does not yet.")
    for r in sorted(set(CLASSIFICATION) - desk - by("planned")):
        problems.append(
            f"{r} is classified here but the desktop no longer calls it. "
            "Remove it, or find out where it went.")

    for r in sorted(phone - desk - set(PHONE_ONLY) - set(CLASSIFICATION)):
        problems.append(
            f"{r} is called by the phone ({', '.join(sorted(phone_at[r]))}) and not by the "
            "desktop, and PHONE_ONLY in tools/check_parity.py does not classify it. Decide "
            "whether the desktop should have it.")
    for r in sorted(set(PHONE_ONLY) - phone):
        problems.append(
            f"{r} is in PHONE_ONLY but the phone no longer calls it. "
            "Remove it, or find out where it went.")
    for r in sorted(set(PHONE_ONLY) & desk):
        problems.append(
            f"{r} is in PHONE_ONLY but the desktop calls it now "
            f"({', '.join(sorted(desk_at[r]))}). Move it to CLASSIFICATION.")

    check_route_fields(problems, warnings)

    todo, no = sorted(by("todo")), sorted(by("deliberate"))
    print(f"desktop: {len(desk)} routes   phone: {len(phone)}   "
          f"ported: {len(by('ported'))}   not porting: {len(no)}   still to port: {len(todo)}   "
          f"not the backend's: {len(by('not-backend'))}   "
          f"planned (backend first): {len(by('planned'))}")
    if todo:
        print("\nStill to port:")
        for r in todo:
            print(f"  {r:<26} {CLASSIFICATION[r][1]}")
    ahead = sorted(phone - desk)
    if ahead:
        print("\nOn the phone and not the desktop (parity runs both ways):")
        for r in ahead:
            st, why = PHONE_ONLY.get(r, ("UNCLASSIFIED", ""))
            print(f"  {r:<26} {st}: {why}" if why else f"  {r:<26} {st}")
    if unused_allow:
        print("\nIn an allow-list, asked for by no window (not counted as calls):")
        for rel, sec, route in unused_allow:
            print(f"  {route:<26} section {sec!r} in {rel}")
    for w in warnings:
        print(f"::warning::{w}")
    if problems:
        print("\n" + "=" * 60)
        for p in problems:
            print(f"::error::{p}")
        return 1
    print("\nNo undecided drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
