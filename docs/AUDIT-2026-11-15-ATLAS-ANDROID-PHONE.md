# Audit: the Atlas app on the OnePlus phone, 2026-11-15

Written after driving the app itself over `adb` on the connected phone, not by
reading the source. Every finding below is something the app **drew on the
screen** or **answered in chat**; the raw captures are listed at the end so each
one can be checked.

- Phone: OnePlus CPH2419, Android 15 (SDK 35).
- App: `com.jarvis.client`, displayed name **Atlas**, version **0.2.4295**
  (`versionCode` 1000004295), installed 2026-11-15 12:08 from CI's newest
  `client-latest` build.
- Method: `uiautomator dump` after each navigation, so the text below is the
  text the app actually renders. Screenshots are black (the app sets
  `FLAG_SECURE`), so the dump is the instrument, not a picture.

## Status, later the same day

This is the audit as it was measured. What has moved since:

- **Section 5, phone-awareness: built and re-driven.** The app now sends the
  phone's own facts with every message (`X-Jarvis-Device`), and the PC tells the
  model to answer for a phone screen. On build 0.2.4331 the question this audit
  recorded as failing - *"what model of phone am I using right now"* - answers
  **"You're using a CPH2419 running Android 15, app version 0.2.4331."**
- **Section 3, the command the phone cannot run, and section 4.1, the Android 17
  caveat on an Android 15 phone: fixed.** The command sits behind one tap with
  its pointer line always visible, and the slider paragraph is drawn only from
  API 37.
- **Section 4.3, the Measure block against its own dated lines: fixed.** The line
  no longer claims that every number above is calculated.

Still open, exactly as written below: the wordiness of the ten presets
(section 2), the duplicate controls (section 3), and section 4.2's disagreement
about which card runs the model.

## 1. Is the app up to date?

**Yes.** 0.2.4295 is the newest build CI has published; it was installed today
at 12:08 and is the build audited here. Nothing on the phone is older than
`client-latest`.

## 2. The descriptions are the biggest problem

Across 16 screens the app draws **801 distinct labelled rows**, and **52,367
characters** of words. Of those rows:

| Length | Rows |
|---|---|
| more than 120 characters | 126 |
| more than 200 characters | 60 |
| more than 300 characters | 22 |

The worst offenders, measured on the running app:

| Characters | Where | First words |
|---|---|---|
| **1,026** | Settings, "Prompt coach" | "Off (the default): nothing is read and there is no Coach this button…" |
| **959** | Brain → Focus presets, Coding | "HEAVY MODE: it fills ALL THREE GPUs (16.17 GiB of video memory here…" |
| **565** | Brain → Hardware, "The one command" | `[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', …` |
| 461 | Settings, one-tap egress lockdown | "One tap makes every way out of this PC ask you first, or stop…" |
| 444 | Help, "About Jarvis" | "A thin client to the Jarvis brain running on your own desktop…" |
| 415 | Settings, search without a card | "A search straight from your own question runs without a card…" |
| 402 | Jarvis Live | "Jarvis listens after every answer until you end it, say…" |
| 401 | Brain → Focus presets, Coding | "Applying it makes it the model chat uses, so the Fast/Live…" |

Two shapes recur, and they are what make the wall of text:

- **A setting explained by its off-case, then its on-case, then its caveat.**
  The 1,026-character Prompt coach block is three paragraphs where one line and
  a "What this does" tap would do.
- **A preset explained five times.** Each of the ten presets carries a tagline,
  a paragraph, a card-fit line, a "What it is for:" block and a "What it is
  worse at:" block. The Coding preset alone prints ~2,000 characters.

The app already has the right pattern for this - Help's "See every feature"
door says *"in plain words … one real limit"* - so the fix is to apply the same
discipline here: one line per row visible, the detail behind a tap.

## 3. Redundant and overlapping surfaces

| What is duplicated | Where it appears |
|---|---|
| Spoken-interruption count | Brain ("3 of 3 spoken interruptions left today") **and** Inbox ("3 of 3 spoken interruptions left.") - with a mute on one and a stepper on the other |
| How to interrupt Jarvis | "Interrupt by voice (recommended)", "Stop speaking when I press the mic", "Let Jarvis finish first" - three controls, one behaviour |
| Voice check | "Only check my voice on a locked phone" and "Check it on my unlocked phone too" - the same switch stated from opposite ends |
| Notifications | "Smartwatch notifications", "Phone notifications", "Notifications from Jarvis" |
| Backups | "Backups" and "Phone settings backup" |
| The model | **60 labelled rows mention "model"** - Models, Big model (slow), The local model, On-device AI model, Everyday chat runs on, Hardware and models, Second graphics card, Third graphics card, Compute, and the ten preset rows |
| Voice | 24 rows mention "voice" |
| Approvals | 13 rows mention "approval" |

Two Home doors - "Presets →" and "Model →" - open the same Brain plate the
Settings rows already reach, so the Home shortcut and the Settings row are two
names for one place (that is fine as a shortcut, but the Settings row should say
it is a shortcut rather than reading like a second control).

**One surface cannot work on this device at all:** "The one command" prints 565
characters of PowerShell on the phone and then says *"This line is for your PC.
Read it here; to run it, use the Copy button in the desktop app"*. A command the
phone cannot run, shown in full on the phone, is the clearest example of content
that should be a one-line pointer instead.

## 4. Out-of-date and self-contradicting content

1. **Android 17 copy on an Android 15 phone.** Settings: *"On Android 17 and
   later, Jarvis's spoken answers have their own volume slider for assistants in
   the phone's volume panel, apart from music…"* The phone reports Android 15
   (SDK 35), so the thing described cannot exist here. A caveat whose condition
   is false on this phone should not be drawn on this phone.
2. **The same screen disagrees about which card runs the model.** Brain →
   Hardware prints *"Found 3 graphics cards; Ollama can use 1: the NVIDIA GeForce
   RTX 2080 SUPER"* and marks the 2060 *"- not used by Ollama"*, while the preset
   rows immediately above say *"qwen3.5:9b on RTX 2060 (the long-context card),
   196,608 tokens"*. On the PC, `nvidia-smi` lists three cards (2060 12 GB, and
   two 2080 SUPER 8 GB) and two `llama-server` processes are resident, one on the
   2060 and one on a 2080 SUPER. So the card list is right and one of the two
   sentences on the phone is stale - but the phone shows both as current fact.
3. **"Every number is calculated" under numbers that say "Measured".** The
   Measure block ends *"Not measured yet: every number above is calculated"*,
   while the preset blocks above it say *"Measured 2026-10-18: cold load
   18.5-20.5 s, 45.6 tokens a second at 8k"*. Both cannot be true of the same
   screen.

## 5. Does Jarvis know it is being messaged from the phone?

**Partly - it knows "phone", and nothing more.** Measured in chat, on this
phone:

> **You:** am i talking to you from my phone or my pc
> **Jarvis:** You're talking to me from your Android phone.

> **You:** what phone model am I using
> **Jarvis:** I don't have access to your phone's specific details from here.
> You might need to check your device settings for that information.

So there is a coarse hint that the caller is a phone, and it is used. What is
missing, and what the owner asked for:

- **which** phone (CPH2419, Android 15, the screen size it is answering into);
- what the phone can do that the PC cannot (camera, calls, alarms, notifications,
  the on-phone model);
- when to answer short because the answer is being read on a phone;
- when to say "I can't do that from here" instead of offering a PC-only step.

## 6. The on-phone model, from the app's own screen

The Local AI screen (19 labelled rows) shows what is on the phone - model name,
size, *"Fits on this phone: about 1.0 GB of memory, at 4,096 tokens of context"*
- plus Load, Unload, Delete and Import. It draws **no** statement of what the
model can and cannot do, and its speed line reads *"Speed: not measured"*.

Nothing on the PC side knows any of it: the phone's model is not mentioned in
chat or in Jarvis Live, and the chat has no way to reach it. That is the subject
of the separate directive of 2026-11-14 and is recorded here only so the audit
is complete.

## 7. What this audit could NOT reach

Written as NOT-TESTABLE, not as a pass:

- **Memory lists and past approvals** sit behind *"Confirm it is you"* - a
  fingerprint prompt. Driving them needs the owner's finger.
- **The Galaxy picture** is drawn on a canvas, so `uiautomator` reads no names
  from it; only the text around it can be audited this way.
- **Anything spoken** - Voice check, Jarvis Live, read-aloud, "hey Jarvis" - was
  not driven: it needs audio in and out, which `adb` cannot supply.
- **A populated approvals queue** was not seen; the queue was empty.
- **An end-to-end tool action** (a card raised, approved, receipt shown) was not
  driven; it needs a real action to approve.

## 8. What I would fix, in this order

1. **Phone-awareness** - send the phone's facts with each message and tell the
   model what they mean, including the on-phone model's limits. Biggest gain per
   line changed, and it is the owner's ask.
2. **Wordiness** - one line per setting and per preset, detail behind a tap;
   target under 150 characters visible per row (the app already does this in
   Help).
3. **The duplicate controls** - one home for interruptions, one for voice check,
   one for notifications, one for backups.
4. **The three contradictions** in section 4.
5. **On-phone model awareness and control** from chat and Jarvis Live.

## Evidence

Raw dumps of every screen, as the app drew them, in `D:\jarvis-wt\_phone\`:
`01-chat-home`, `02-history`, `03-brain`, `04-inbox`, `05-live`, `06-reminders`,
`07-help`, `08-settings`, `09-settings-tail`, `10-home-deck`, `11-home-tray`,
`12-more-menu`, `13-local-ai`, `14-galaxy`, `15-presets`, `15b-presets-tail`,
`16-approvals`.
