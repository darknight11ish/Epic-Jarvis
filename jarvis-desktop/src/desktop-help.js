/**
 * desktop-help.js - the questions ONLY the desktop answers.
 *
 * WHY THIS FILE EXISTS (the cohesiveness audit, folded properly; the owner
 * approved the move on 2026-10-08). Help used to live in three places, and the
 * Settings card "Help and FAQ" was the odd one out: its fifteen questions were
 * answered nowhere else, because they are about things the phone does not have
 * - Quiet against Standby, Alt+Space, "I closed the window but Jarvis is still
 * running", the pairing token, a lost phone. The audit's first suggestion was
 * to DELETE the card; that was refused, because those questions are the page
 * and only the desktop can answer them. So the card's CONTENT moved here, and
 * `tutorials.js` draws it in the one Help place both halves now share: the
 * Brain's "Tutorials and the FAQ" tab.
 *
 * WHAT IS *NOT* HERE. The questions BOTH apps answer stay where they were,
 * served by the backend (`GET /api/faq`, backend/jarvis_tutorials.py) - the
 * phone has no way to read this file, and the phone's Help must not lose a
 * single question to this move. `mergeQuestions` is what puts the two halves
 * on one screen, backend first.
 *
 * ONE OF THE FIFTEEN IS NOT TYPED HERE AT ALL: "What can I say?" is
 * `sayable.js`'s HELP_BODY (the same words `backend/jarvis_sayable.py` serves
 * to the Jarvis bar), imported rather than copied, so the two can never drift.
 *
 * NO PAGE, NO TAURI: node can import it, which is how tests/faq.mjs pins the
 * list without a browser.
 *
 * @module desktop-help
 */

import { HELP_BODY, HELP_TITLE } from "./sayable.js";

/**
 * The words on this half of the page. The heading names what the questions are
 * about, and the tag is the same fact the old card's own note carried: these
 * are answers for the program on this computer.
 */
export const WORDS = Object.freeze({
  heading: "On this computer",
  note: "Answers specific to this program, the one running on this computer. " +
    "The questions above are answered by both apps.",
});

/** The heading the merged list is drawn under, and the search box's own name. */
export const FAQ_HEADING = "Questions and answers";

/**
 * The fifteen questions the Settings card "Help and FAQ" held, in its own
 * order, moved here word for word on 2026-10-08.
 *
 * `where` is the breadcrumb the old card's prose already gave in passing ("Open
 * Shortcuts, further down this page"). The place it names did NOT move - every
 * one of them is a Settings card that is still exactly where it was - so only
 * the wording settled down ("further down this page" became a name the owner
 * can look for in the palette).
 */
export const DESKTOP_FAQ = Object.freeze([
  {
    id: "leaves-this-computer",
    q: "Does anything I say to Jarvis leave this computer?",
    a: "Only along a few named routes. Jarvis answers using a language model that " +
      "runs on this machine. It reaches the internet for a web search, and for your " +
      "own calendar, email and Home Assistant once you have set them up on this PC. " +
      "A search that comes straight from your own question goes without asking; " +
      "after Jarvis has read an email, a file or other outside text, or when the " +
      "search words would repeat something private, it shows you the exact words and " +
      "waits for your yes. Sending an email, or a question to a cloud model, always " +
      "asks first. \"What Jarvis can reach\" (Settings) lists which routes are on " +
      "right now, and this program never opens a public tunnel to itself.",
    where: "Settings → What Jarvis can reach",
  },
  {
    id: "approve-or-deny",
    q: "Where do I approve or deny what Jarvis wants to do?",
    a: "On a card. When Jarvis wants to do something that is not completely safe, it " +
      "stops, and a card waits for you in the Jarvis bar, on the widget, or on your " +
      "phone's Home screen (Alt+Space opens the Jarvis bar). For anything important " +
      "Windows also shows a notification. Press Approve or Deny on the card; the " +
      "notification can only Deny. Nothing runs until you decide, one thing at a " +
      "time. An email Jarvis wants to send is approved in the Jarvis bar, where you " +
      "can read all of it first.",
    where: "The Jarvis bar, the widget, or your phone",
  },
  {
    id: "jarvis-live",
    q: "What is Jarvis Live, and how do I end it?",
    a: "A back-and-forth voice conversation. Click Live in the Jarvis bar (or say " +
      "\"Hey Jarvis, let's talk\") and just talk: no \"Hey Jarvis\" before each " +
      "sentence. Every sentence is still checked for your voice on this PC before " +
      "any words are made of it, and a card that comes up still waits for your " +
      "click. A red dot on the tray icon and a small sign at the top of the screen " +
      "show while it is on. To end it, click End Live on the sign, say \"Okay " +
      "Jarvis, that's all for now\", or just stop talking for 90 seconds. Mic off " +
      "closes the microphone without ending it. Live needs your voice trained first " +
      "(Settings, then Voice).",
    where: "The Jarvis bar, and Settings → Voice",
  },
  {
    id: "no-approve-everything",
    q: "Why is there no \"approve everything\" button?",
    a: "On purpose. Anything Jarvis wants to do that is not completely safe stops and " +
      "asks first, one action at a time. A single button to wave all of those " +
      "through would undo that protection, so this program is built with no way to " +
      "add one, anywhere in it.",
    where: "",
  },
  {
    id: "alt-space",
    q: "My Alt+Space shortcut does not do anything.",
    a: "Something else on this computer has already claimed that combination - " +
      "usually PowerToys Run, or on recent Windows 11 builds, the Copilot app. Open " +
      "Shortcuts: a binding that is not working says in use there. Pick a different " +
      "combination and press Save shortcuts.",
    where: "Settings → Shortcuts",
  },
  {
    id: "what-can-i-say",
    // The words, and the id they are pinned under, come from sayable.js - the
    // same two constants backend/jarvis_sayable.py serves to the Jarvis bar.
    // Typing them a second time here is the drift this module exists to avoid.
    q: HELP_TITLE,
    a: HELP_BODY,
    where: "Ask \"what can you do?\" any time",
  },
  {
    id: "phone-talks",
    q: "Can my phone talk to Jarvis?",
    a: "Yes, over Tailscale or NordVPN Meshnet - a private network between only the " +
      "devices you own, never the open internet. Turn it on in Connection, under " +
      "\"Let my phone reach this\", by typing this computer's own address on that " +
      "network (the 100.x.x.x number). Then, on the phone, type this computer's " +
      "name, not the number: the Tailscale name ending in .ts.net, or the Meshnet " +
      "name ending in .nord (like my-pc.nord), followed by :4719. The phone also " +
      "needs the token: press Show the token for my phone in Connection. Leave the " +
      "box blank and nothing changes: Jarvis stays reachable from this computer " +
      "alone.",
    where: "Settings → Connection",
  },
  {
    id: "talking-to-jarvis",
    q: "How does talking to Jarvis work?",
    a: "Hold the microphone button in the Jarvis bar and speak, then let go to send. " +
      "With the button selected, holding Space or Enter works too. The microphone " +
      "button in the big HUD window opens the Jarvis bar with its microphone ready, " +
      "so both lead to the same place. The recording is made on this computer and " +
      "goes only to Jarvis on this computer - never to Microsoft, Google or anyone " +
      "else. Listening for \"hey Jarvis\", the button next to the microphone, is off " +
      "until you turn it on; the first time, it shows you an approval card instead " +
      "of listening. While it is on, what the microphone hears goes only to Jarvis " +
      "on this computer, which ignores anything that does not start with \"hey " +
      "Jarvis\". Windows dictation is not used, because it sends your voice to a " +
      "company's servers to turn it into text. To have Jarvis type what you say into " +
      "another program instead, turn on Talk-to-type in Voice, then hold Alt+Shift+T " +
      "and speak.",
    where: "The Jarvis bar, and Settings → Voice",
  },
  {
    id: "suddenly-slow",
    q: "Jarvis suddenly got slow. What happened?",
    a: "Open the Brain window, then Model, then Models. If the language model has " +
      "fallen off the graphics card onto the processor instead, there is a yellow " +
      "line at the top of that list saying so, with the percentage. That is almost " +
      "always the cause - a graphics card doing the work is fast, a processor doing " +
      "the same work is not.",
    where: "Brain → Model → Models",
  },
  {
    id: "quiet-and-standby",
    q: "What is the difference between Quiet and Standby?",
    a: "Both are ways for Jarvis to use less power while you are not using it. Quiet " +
      "stops the things Jarvis does on its own in the background, but keeps the " +
      "model loaded, so it still answers you instantly. Standby also unloads the " +
      "model from the graphics card - the real drop in power use - at the cost of a " +
      "slower first answer (five to fifteen seconds) after you wake it back up. To " +
      "switch, right-click the Jarvis icon in the taskbar corner and choose Change " +
      "power mode, or use the buttons on the phone's Brain screen. This needs the " +
      "backend's power-mode patch; without it, you are told so. Waking from Standby " +
      "loads the model again straight away, so the first answer after waking is " +
      "quick. To go on Standby every night and wake every morning, set up a Standby " +
      "schedule in the Brain, Work tab, under Coming up (the phone has it under " +
      "Coming up on its Brain screen); it is set up at once, with no approval card, " +
      "and deleting it is instant.",
    where: "The tray icon, or Brain → Work → Coming up",
  },
  {
    id: "updates-itself",
    q: "Will Jarvis update itself without asking?",
    // The old card swapped a live line in here ("Update checks are not set up
    // yet for this copy") from settings.js paintUpdate(). It is STATIC now, on
    // purpose: this answer lives in the Brain, which is a different window and
    // cannot see Settings' update state, and a sentence here that claimed to
    // know would be the kind of stale help this move exists to remove. The live
    // truth is where it always was - the Updates card, one jump away.
    a: "No. Jarvis only tells you a newer version exists. It never installs one on " +
      "its own. Installing is always the Install button, pressed by you. Whether " +
      "this copy can check for updates at all is said on the Updates card - a copy " +
      "built without a signing key says so there.",
    where: "Settings → Updates",
  },
  {
    id: "window-still-running",
    q: "I closed the window, but Jarvis is still running. Is that a bug?",
    a: "No - that is how this program is built. Closing any window, including the " +
      "main assistant window's own close button, just hides it; Jarvis keeps " +
      "running so it can still answer you instantly. To actually quit, use \"Quit\" " +
      "on the tray icon, near your clock.",
    where: "The tray icon, near your clock",
  },
  {
    id: "pairing-token",
    q: "Is my pairing token safe?",
    a: "It is kept in Windows Credential Manager, the part of Windows that holds " +
      "saved passwords - not in a plain-text file. This app sends it only to the " +
      "Jarvis address set here, and never writes it to its logs. Show the token for " +
      "my phone shows it for a minute so you can type it into the phone; there is no " +
      "Copy button, because anything copied stays in Windows' clipboard history. " +
      "Anyone signed in to this computer as you can read it, the same as your other " +
      "saved passwords, so keep your Windows account password-protected. One " +
      "exception: if the Token line in Connection says Jarvis's own token is still " +
      "in its old plain-text file, run apply-patches.ps1 to update the backend, " +
      "which moves it into Credential Manager.",
    where: "Settings → Connection",
  },
  {
    id: "how-to-update",
    q: "How do I update Jarvis?",
    a: "Three parts, in this order. Jarvis on this PC: stop it, then in PowerShell, " +
      "in your copy of the Jarvis files, get the newest files (git pull) and run " +
      "apply-patches.ps1 again - it keeps your settings file, backs up what it " +
      "replaces and saves a log of the run in _jarvis-logs in your Jarvis folder - " +
      "then start Jarvis again. This app: build and install it again (there is no " +
      "automatic update yet). The phone app: install the newest file from the " +
      "release page over the old one; it stays paired. docs/INSTALL.md, \"Updating " +
      "everything\", has each step as one line to copy.",
    where: "docs/INSTALL.md, \"Updating everything\"",
  },
  {
    id: "lost-phone",
    q: "I lost my phone. What do I do?",
    a: "Whoever has it unlocked could use Jarvis with the pairing key it holds. " +
      "First take the phone off your private network (Tailscale's admin page, " +
      "Machines, the phone, Remove - or remove it from your NordVPN Meshnet), so it " +
      "cannot reach this PC at all. Then make a new pairing key, which stops the old " +
      "one working: docs/INSTALL.md, \"If you lose your phone\", has the steps. Your " +
      "other devices then pair again with the new key.",
    where: "Settings → Devices",
  },
]);

/**
 * One screen's worth of questions: the backend's own list, then this file's.
 *
 * The backend answers the questions both apps ask (`GET /api/faq`); this file
 * answers the desktop's own. The order is deliberate - the shared answers first,
 * so the page still leads with what the phone also knows, and the desktop-only
 * ones sit under their own heading below.
 *
 * A backend that is not answering (or an older one with no `/api/faq`) is not an
 * error here: the desktop's own fifteen are still drawn, which is the whole
 * point of them being local.
 */
export function mergeQuestions(answer, local = DESKTOP_FAQ) {
  const shared = (answer && answer.questions) || [];
  return [...shared.map((q) => ({ ...q })), ...local.map((q) => ({ ...q }))];
}

/** The ids of this half, in order - what the merge is checked against. */
export function localIds() {
  return DESKTOP_FAQ.map((q) => q.id);
}
