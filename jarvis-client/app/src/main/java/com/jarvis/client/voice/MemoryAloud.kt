package com.jarvis.client.voice

/**
 * "Read out answers that use what Jarvis remembers" - the owner's setting of
 * 2026-11-05, and THIS PHONE'S OWN.
 *
 * Why it exists. The talk button deliberately runs no voice check (the
 * owner's request of 2026-11-02), so his PC answers `memory_aloud: false` for
 * every talk-button question, whatever its own settings say. On 2026-11-05 he
 * asked a spoken question about his notes, got a text answer that used three
 * remembered facts, and his phone said only "It's on your screen." He chose a
 * setting on the PHONE for it: "read them aloud on my unlocked phone".
 *
 * What it does and does not do, and this is the half that matters:
 *  - it is ON by default ([PrivateAloud.MEMORY_ALOUD_DEFAULT]) since the
 *    owner's decision of 2026-11-07 ("i wanted to read everything out loud ...
 *    unless it's extremely sensitive information it's okay"); it is a promise
 *    this phone makes about its own answers, and he can turn it off any time;
 *  - it covers EVERY voice answer on THIS phone - the mic press, "hey Jarvis"
 *    and Jarvis Live - plus a TYPED answer read aloud on this phone while it is
 *    unlocked (the owner's decision of 2026-11-06);
 *  - a sensitive saved fact, an answer about his screen and a private tool
 *    still always stay on screen (`PrivateAloud`); the one exception the owner
 *    makes himself, per answer, is the one-off "Read it aloud anyway" action
 *    (`ReadAloud.ANYWAY`), which is his own tap and not this setting. Nothing
 *    about the 2026-09-24 sensitive-fact rule is loosened;
 *  - it uses the existing `/api/voice/say` and the existing answer. The PC now
 *    has its own read-aloud switch too (`GET/POST /api/read-aloud`, Wave 9);
 *    that is the PC's rule for what IT reads, and this phone setting changes
 *    nothing there. The two are separate on purpose (`docs/ARCHITECTURE.md`
 *    section 8).
 *
 * The words here are the settings row's, in the app's plain-words style and
 * beside the other phone-only voice switches (`ui/screens/VoiceSwitchesPlate.kt`).
 * Pure, no Android: `MemoryAloudTest`.
 */
object MemoryAloud {

    /** The switch's name, in the owner's own words. */
    const val NAME = "Read out answers that use what Jarvis remembers"

    /**
     * Q7 (the owner's ruling, 2026-11-08): one subtle line under the switch's
     * name, while the default is ON - so the row says the default without a
     * banner and without a second card. Exactly his approved wording.
     */
    const val SUBTITLE = "On by default — toggle off anytime"

    /**
     * The line under the switch, in its two states. ON is the default since the
     * owner's decision of 2026-11-07 ("i wanted to read everything out loud ...
     * unless it's extremely sensitive information it's okay"), and it covers
     * every voice answer on this phone - the mic press, "hey Jarvis" and Jarvis
     * Live. A TYPED answer is silent unless he taps Read aloud, and an extremely
     * sensitive saved fact always stays on screen.
     */
    fun describe(on: Boolean): String = if (on) {
        "On by default, on this phone. A voice answer that uses what Jarvis remembers is " +
            "read out - the mic, \"hey Jarvis\" and Jarvis Live. A typed answer is read " +
            "only when you tap Read aloud. An extremely sensitive saved fact (health, " +
            "money, passwords, other people's private details), a private tool and an " +
            "answer about your screen still always stay on your screen."
    } else {
        "Off: an answer that uses what Jarvis remembers stays on your screen, and says so. " +
            "Say \"read everything out loud\" in the chat to turn it back on, or use the " +
            "button below. An extremely sensitive saved fact and a private tool still stay " +
            "on your screen."
    }

    /**
     * The one line that says whose setting this is. The PC's own `memory_aloud`
     * still decides what the PC reads (and the PC has its own automatic
     * read-aloud switch); this row changes nothing there.
     */
    const val NOTE =
        "This phone's own setting, for its voice answers and its Read aloud controls. " +
            "Your PC has its own rule for what it reads out, and turning this on changes " +
            "nothing on the PC. The chat can change it too: say \"stop reading remembered " +
            "answers out loud\" or \"read everything out loud\"."

    /** The button that turns it on. */
    const val TURN_ON = "Read them out"

    /** The button that turns it back off - the words say what happens. */
    const val TURN_OFF = "Keep them on my screen"
}
