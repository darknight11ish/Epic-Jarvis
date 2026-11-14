# Owner click-through — what only you can test (2026-11-03)

**What this is.** Every feature was checked by a read-only probe on this PC, but a probe cannot say
whether the thing *feels* right. That check needs your voice, your thumb or your eyes. This page is
the shortest list of those, in an order that takes about 25 minutes, plus the ones that need special
hardware or a wait.

**Who drives it (2026-11-03, 14:05 PT).** At the owner's request this testing was handed to the
parallel DeepSeek session — both Part A and Part B. The rows, pass bars and record rules below are
unchanged; only who asks the questions changed.

**Evening update (2026-11-03).** The owner then delegated the driving to the paired session, which
drove every row it could; those results are in `AGENT-DRIVEN-RESULTS.md` and `PHONE-DRIVE.md` and
are recorded in `MATRIX.md` / `MATRIX-F5.md` as **AGENT-DRIVEN** (evidence, never an owner PASS).
Rows that only the owner can close stay BLOCKED below. Where the fast path does not yet accept a
natural sentence, this page now gives the phrasing that works today and marks the natural form as
pending the widening.

**Two rules, and they are the whole point:**

1. **Nothing here counts as a pass until you drive it.** A row we could not reach is written
   **BLOCKED** — never "probably fine" (that rule is `docs/FIELD-TEST-MATRIX-2026-10-11.md`).
2. **A FAIL is useful, not bad news.** It becomes a defect with your words as the evidence.

**How to tell me the result.** For each number, say one word — `PASS`, `FAIL` or `BLOCKED` — and for a
FAIL one sentence about what you saw. I write it into the matrix next to the feature's row and the
probe evidence that already exists. You do not have to remember any of this page while we talk.

---

## Part A — ready to test now (the F4 build is deployed: backend, desktop 0.2.410, phone 0.2.3635)

### On the PC, by typing in the chat

1. **Self-explain: which model is answering.** Accepted today (verified 2026-11-03): *"which model
   are you using"*. Natural form: *"which model is answering me, and why that one?"* — being added
   by the fast-path widening, **NOT live yet**. You should hear/see the current model named from the
   real `/api/models` read (probe says `current=qwen3.5:9b`, `previous=qwen3:8b`, 15 installed), and
   the reason for choosing it. **Row F4-05B.**
2. **Self-explain: the app allow-list.** Accepted today (verified): *"what can you open on my
   phone"*. Natural form: *"which apps on my phone may you open?"* — widening pending, **NOT live
   yet**. You should get the allow-list explained — and a refusal to guess an app that is not on it.
   **Row F4-04B.**
3. **Self-explain: the price radar.** Accepted today (verified): *"what is the price radar
   showing"*. The longer form on this page is **not verified** by today's run. It should say the
   radar exists and is honestly empty (`decks=0 radar=0`), not invent prices. **Row F4-06B.**
4. **Plugins by chat.** Accepted today (verified, list half): *"what plugins do you have"*. Natural
   form: *"list my plugins"* — widening pending, **NOT live yet**. The switch half still needs one
   card per change: turn one off in words, then turn it back on. You should get the real list, then
   exactly **one approval card per change**, and nothing changes until you say yes.
   **Row F4-07B.**
5. **Goals progress.** Add a real progress line to a goal, then ask it to read the log back.
   **Row F4-09B.**
6. **Habits and mood, by thumb on the phone** (Part B, steps 9–11) — this one is phone-first.
   **Already answered as BLOCKED-no-UI-in-this-build:** build 0.2.3635 has no Habits screen and no
   Mood section or chart, so there is nothing to drive yet; see those rows above.

### On the phone

7. **Approve one card with your fingerprint.** Ask for something carded in the phone chat, then
   approve it with the phone's fingerprint. **Row F4-12B.**
8. **Wake word.** Say "Hey Jarvis" with the phone screen off/idle and see whether it wakes. (The
   probe says the phrase is `hey_jarvis` and the switch is currently **off** — so first check the
   phone's setting, and if it is off, set it on and count that as the test.)
   **Row F4-10B.**
9. **A habit check-in.** **Already answered as BLOCKED-no-UI-in-this-build:** build 0.2.3635 has no
   Habits screen / no Mood section or chart / no Week-in-review screen (weekly filing off), so there
   is nothing for the owner to drive. Recorded in `MATRIX.md`; this is not a pass. Kept as context:
   on the Reminders screen, make a habit ("walk three times a week"), then tick it once. One tap
   should record it, and the tick should be what the chart reads back. **Row F4-01B.**
10. **A mood entry.** **Already answered as BLOCKED-no-UI-in-this-build:** build 0.2.3635 has no
    Habits screen / no Mood section or chart / no Week-in-review screen (weekly filing off), so there
    is nothing for the owner to drive. Recorded in `MATRIX.md`; this is not a pass. Kept as context:
    on the Reminders screen, tap one 1–5 value, optionally add words, then open the history chart.
    **Row F4-02B.**
11. **Week in review.** **Already answered as BLOCKED-no-UI-in-this-build:** build 0.2.3635 has no
    Habits screen / no Mood section or chart / no Week-in-review screen (weekly filing off), so there
    is nothing for the owner to drive. Recorded in `MATRIX.md`; this is not a pass. Kept as context:
    open it and read the counts of the week that passed. If no week has passed since the feature
    landed, mark it **BLOCKED — not enough time yet**, not a pass. **Row F4-03B.**
12. **Live voice check — once per session, not every sentence.** Start Live by voice (not by tapping
    Start), and watch whether it asks you to say the check phrase again. **Row F4-11B.**

### On both, the wording question

13. **DEF-028.** **Already measured FAIL on the phone (2026-11-03 evening):** the LIVE screen in
    build 0.2.3635 still promises every sentence is voice-checked while Settings > "What asks first"
    has the corrected once-per-session line; the two screens contradict each other (DEF-028 phone
    half). Recorded in `MATRIX.md`; no need to re-read unless you want to see it. Read the Live line
    on the phone and the same line in the desktop Help. It must no longer promise that *every*
    sentence is voice-checked (the probe found the old promise still live on the F3 build; the F4 fix
    should have replaced it). **Row F4-08B.**

---

## Part B — F5 is deployed now (2026-11-03 12:47 PT): these are ready

PR #1112 merged at 12:41 PT and the backend deployed at 12:47 with every runbook gate passed, so every
step below is live. The probes came back 14 PASS / 0 FAIL / 5 BLOCKED — the blocked ones need a `POST`
or a card, which is exactly why they are yours:

14. **Explain a setting.** Accepted today (verified): *"how do i change the weather source"*. Natural
    form: *"where do I change the weather source, and what is it set to?"* — widening pending,
    **NOT live yet**. You should get four facts: what it is, where it lives, its **current** value,
    and the exact phrase that changes it. **Row F5-01B.**
15. **The current value is real, not a default.** Ask about three different settings and compare each
    spoken value with what the Settings page shows. Verified accepted forms (2026-11-03): *"what is
    the anti-slop filter set to"*, *"how do i change the personality"*, *"how do i change the sun and
    moon"*, *"how do i change the jarvis live timeout"*. Six readers are already proven live by probe
    (anti-slop mode, personality, focus preset, sky-show, weather source, the seven animal switches);
    this step tests the *sentence*, not the reader. **Rows F5-02B, F5-03B.**
16. **Never a default dressed up as the value.** With one part stopped, ask for that setting and hear
    *"I could not read its current value on this PC, so I will not guess."* This needs me to stop a
    module for a minute — say when, and I will do it; the sentence is the whole test.
    **Row F5-04B.**
17. **A change, then "undo".** Say *"turn off the sun and moon"*, then say *"undo"*. One receipt
    should appear and the change should reverse. Then say *"undo"* again: the second must refuse and
    change nothing. **Rows F5-05B, F5-06B.** **Do not use Anti-Slop for this test:** it is a cardless
    change that writes NO settings receipt, so a following undo says "There is nothing here for me
    to take back." That is an open finding (2026-11-03), not a pass. The sun-and-moon change did
    write its receipt and undo reversed it.
18. **A carded setting change in Live.** Ask for a change that raises a card: exactly one card, Live
    pauses, one calm spoken line, and it never speaks the approval itself. **Row F5-07B.**
19. **Read a link.** Paste a real link (and a YouTube link) in chat: exactly one card per link, and a
    non-link should be refused rather than treated as a page. **Row F5-08B.** **Approved spec, NOT
    live yet (owner rulings, 2026-11-03):** today a bare pasted URL is not read. The approved spec is
    that a bare pasted URL (or URL + question when it is not a setting/reminder/watch command) routes
    through the fast-path reader, raises ONE card naming the URL, prints the canonical URL on the
    first line of the answer so both apps make it tappable with no UI change, records the source, and
    caches one page per conversation for 900 s. Do not record a FAIL for a bare URL today; the
    explicit "read a link" path and the non-link refusal are what exists now.
20. **The page reader stays unswitchable.** **Already answered on the phone (2026-11-03 evening):**
    Settings > "What asks first" shows the page-reader row as text only, `checkable=false`,
    `clickable=false`, with no switch anywhere near it; recorded as AGENT-PASS (screen + API) in
    `MATRIX-F5.md`. No owner action needed. Kept as context: open Settings → "What asks first" on the
    PC and the phone: there must be **no switch** for the page-reading tool. That absence is your
    2026-11-03 decision still holding. **Row F5-09B.**
21. **A setting outside the registry is refused.** Ask for a setting that does not exist: an honest
    refusal, and **no card**. **Row F5-10B.**

---

## Part C — needs special setup, so these stay BLOCKED until we schedule them

22. **Car Bluetooth microphone** (2017 Chevy Bolt). The fix is merged; it needs one real drive:
    connect the phone to the car, start Live, and speak one sentence. What to listen for: whether
    your voice is recognised, or the mic stays dead. **BLOCKED — needs the car.**
23. **Photo and document analysis.** Send a photo of a page of text and ask what it says. The
    attachment path was fixed (#1084), but the *right answer* was never proven, so this is the row
    that finally shows whether it reads text correctly. **BLOCKED — needs a photo you choose.**
24. **Direct in-app control of Android apps.** Ask Jarvis to do something *inside* an allowed app
    (not just open it). Only opening apps is proven; deeper control is the open question.
    **BLOCKED — needs an app and a task you choose.**
25. **Live's second answer feels slow.** Start a Live conversation and give two answers in a row.
    This is about *latency*, not correctness: is the second reply noticeably late compared with the
    first? No fix was found, so honesty here is the deliverable. **BLOCKED — needs Live on the car
    or at the desk.**

---

## Part D — questions with no test, only your sentence (answer any time)

26. **The serious Android bug you saw.** Which screen was it on, and what happened? A screenshot is
    ideal; one sentence is enough. No defect can be opened without this.
27. **The window that stays on top.** Tell me the window's name (the program title) and I can find
    out why it is pinned there.
28. **Speaking feature and capability answers aloud — already decided, nothing to do.** You answered yes on
    2026-11-02, and the answer is recorded on `main`
    (`decisions.d/2026-11-02-speak-capability-answers.md`), so Jarvis says capability answers out loud.
    No re-decision needed.
29. **The phones' voice after a reset.** #1076 fixed the reset losing your chosen voice. If you have
    not reset the app since, that row is **BLOCKED**, not fixed — say the word and we test it without
    losing your real settings.

---

**Where the evidence lives.** The probe side of every row above is in
[`MATRIX.md`](MATRIX.md) (F4) and [`MATRIX-F5.md`](MATRIX-F5.md) (F5), with their captured probe
output next to them. The rule that BLOCKED is never a pass is
`docs/FIELD-TEST-MATRIX-2026-10-11.md`. This page is the owner half only; it adds no claim that a
probe could make.

## Evening update — what changed since this page was written (2026-11-03)

- **Four natural sentences are pending a fast-path widening; they do NOT work yet:** *"which model is
  answering me, and why that one?"*, *"which apps on my phone may you open?"*, *"list my plugins"*,
  and *"where do I change <setting>, and what is it set to?"*. Use the accepted phrasings above until
  the widening is live.
- **The phone lane answered some rows:** F4-01B, F4-02B and F4-03B have no screen in build 0.2.3635;
  F4-08B is a measured FAIL (the Live screen still makes the old promise); F5-09B is answered by the
  screen itself (text only, no switch).
- **The approved read-a-link spec is not live yet.** A bare pasted URL is still not read today; only
  the explicit "read a link" path and the non-link refusal exist.
- **Deploy staging:** F6-A is backend + HUD (#1116, #1118, #1120, #1121) and F6-B is desktop (#1115,
  #1117, #1119). Nothing on this page should be treated as live merely because it merged — the
  deployed build is what counts.

AGENT-DRIVEN results are evidence, never an owner PASS; the rows only the owner can close stay
BLOCKED.
