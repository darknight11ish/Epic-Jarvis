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
 * What it does NOT do, and this is the half that matters:
 *  - it is OFF until he turns it on ([PrivateAloud.MEMORY_ALOUD_DEFAULT]); it
 *    is a promise this phone makes about its own button and its own "Read
 *    aloud" tap, never a new default;
 *  - it only ever covers the talk button on THIS phone while it was unlocked
 *    when he pressed it, or a TYPED answer read aloud on this phone while it is
 *    unlocked (the owner's decision of 2026-11-06) - not "hey Jarvis", not
 *    Jarvis Live;
 *  - a sensitive saved fact, an answer about his screen and a private tool
 *    still always stay on screen (`PrivateAloud`); the one exception the owner
 *    makes himself, per answer, is the one-off "Read it aloud anyway" action
 *    (`ReadAloud.ANYWAY`), which is his own tap and not this setting. Nothing
 *    about the 2026-09-24 sensitive-fact rule is loosened;
 *  - it uses the existing `/api/voice/say` and the existing answer. There is
 *    no new route, no new field and no PC setting: the desktop has no
 *    matching switch on purpose (`docs/ARCHITECTURE.md` section 8).
 *
 * The words here are the settings row's, in the app's plain-words style and
 * beside the other phone-only voice switches (`ui/screens/VoiceSwitchesPlate.kt`).
 * Pure, no Android: `MemoryAloudTest`.
 */
object MemoryAloud {

    /** The switch's name, in the owner's own words. */
    const val NAME = "Read out answers that use what Jarvis remembers"

    /**
     * The line under the switch, in its two states. The OFF sentence says
     * "Off by default", because that is the owner's own framing of this
     * setting: a choice he makes, not a behaviour he is given.
     */
    fun describe(on: Boolean): String = if (on) {
        "On, on this phone: when you press the mic while it is unlocked, an answer that " +
            "uses what Jarvis remembers is read out. The same goes for a typed answer when " +
            "you tap Read aloud on this unlocked phone. A sensitive saved fact and a private " +
            "tool still stay on your screen; an answer about your screen is read out only " +
            "when you tap Read it aloud anyway."
    } else {
        "Off by default: an answer that uses what Jarvis remembers stays on your screen, and " +
            "says so. Turning it on covers the mic and the Read aloud control on this phone " +
            "while it is unlocked - not \"hey Jarvis\", and not Jarvis Live. A sensitive saved " +
            "fact and a private tool still stay on your screen."
    }

    /**
     * The one line that says whose setting this is. Two apps, two switches:
     * the PC's own `memory_aloud` still decides what the PC reads, and this
     * row changes nothing there.
     */
    const val NOTE =
        "This phone's own setting, for its mic and its Read aloud control. Your PC has its " +
            "own rule for what it reads out, and turning this on changes nothing on the PC."

    /** The button that turns it on. */
    const val TURN_ON = "Read them out"

    /** The button that turns it back off - the words say what happens. */
    const val TURN_OFF = "Keep them on my screen"
}
