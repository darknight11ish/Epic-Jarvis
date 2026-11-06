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
 *    is a promise this phone makes about its own button, never a new default;
 *  - it only ever covers the talk button on THIS phone while it was unlocked
 *    when he pressed it - not "hey Jarvis", not Jarvis Live;
 *  - a sensitive saved fact, an answer about his screen and a private tool
 *    still always stay on screen (`PrivateAloud`). Nothing about the
 *    2026-09-24 sensitive-fact rule is loosened;
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
            "uses what Jarvis remembers is read out. A sensitive saved fact, a private tool " +
            "and an answer about your screen still stay on your screen."
    } else {
        "Off by default: an answer that uses what Jarvis remembers stays on your screen. " +
            "Turning it on covers only the mic on this phone while it is unlocked - not " +
            "\"hey Jarvis\", and not Jarvis Live."
    }

    /**
     * The one line that says whose setting this is. Two apps, two switches:
     * the PC's own `memory_aloud` still decides what the PC reads, and this
     * row changes nothing there.
     */
    const val NOTE =
        "This phone's own setting. Your PC has its own rule for what it reads out, and " +
            "turning this on changes nothing on the PC."

    /** The button that turns it on. */
    const val TURN_ON = "Read them out"

    /** The button that turns it back off - the words say what happens. */
    const val TURN_OFF = "Keep them on my screen"
}
