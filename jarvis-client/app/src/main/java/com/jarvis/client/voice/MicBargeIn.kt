package com.jarvis.client.voice

/**
 * "Stop speaking when I press the mic" - the owner's ask of 2026-11-13, and
 * THIS PHONE'S OWN SETTING, **ON by default**.
 *
 * The owner: *"when I use the top mic button in the android app and jarvis is
 * still speaking out from a previous response, I want it to interrupt its
 * response and process the new thing I said. also add this to the settings as
 * a changeable Default"*.
 *
 * WHAT IT CHANGES, measured on the code before it existed. A press of the
 * microphone while Jarvis was talking did NOTHING: while the reply was still
 * arriving both mic buttons were greyed out (`HomeScreen`, `enabled = ... &&
 * !state.streaming`), and once the reply had arrived but its last sentences
 * were still playing, `VoiceSession.begin` answered "Still finishing the last
 * one." and returned. ON (the default) the same press silences the reply at
 * once and then starts listening exactly as an ordinary press does. OFF is
 * that old behaviour, and its words here say so.
 *
 * THE SILENCE IS THE STOP WORD'S OWN. [press] is handed
 * [VoiceSession.stopSpeaking], the one function "stop" already calls, so there
 * is one "silence everything now" and not a second one that could drift from
 * it. Dropping the old turn is [VoiceSession.interruptForWake]'s half as well:
 * its `Turn.silenced` latch means the rest of a streamed reply is never asked
 * for or spoken (`SpeechAhead`), and a reply still arriving from the PC is
 * dropped on this phone.
 *
 * THE PHONE STILL DOES NO SPEECH-TO-TEXT. It stops sound it is making and
 * sends the new clip to the PC exactly as any other press does; the words are
 * heard by the PC's own voice route. This is the desktop's talk button
 * behaviour, not a new idea - `jarvis-desktop/src/main.js`'s `startPushToTalk`
 * calls `noteCutOff(); stopSpeaking();` with the comment "Barge-in: holding
 * the mic to talk again is as clear a signal as this app gets that whatever
 * Jarvis was saying is done mattering right now". The phone was the half that
 * did not have it, which is why this is a parity fix and not a new rule.
 *
 * Pure, no Android: `MicBargeInTest` drives [press] and holds the settings row
 * and the wiring it cannot reach.
 */
object MicBargeIn {

    /**
     * ON by default. The owner asked for the barge-in ("I want it to interrupt
     * its response and process the new thing I said") and for the setting to
     * exist as "a changeable Default" - so the default is the behaviour he
     * asked for, not the old one.
     */
    const val DEFAULT = true

    /** The switch's name, in the owner's own words. */
    const val NAME = "Stop speaking when I press the mic"

    /** One subtle line under the name, saying the default (the Q7 shape MemoryAloud uses). */
    const val SUBTITLE = "On by default — toggle off anytime"

    /** The button that turns it back on. */
    const val TURN_ON = "Stop speaking when I press the mic"

    /** The button that turns it off - the words say what happens then. */
    const val TURN_OFF = "Let Jarvis finish first"

    /**
     * The line under the switch, in its two states. ON describes exactly what
     * happens (stop, then listen, answer stays on screen); OFF describes today's
     * behaviour rather than a hope, because that is what the switch gives back.
     */
    fun describe(on: Boolean): String = if (on) {
        "On: while Jarvis is speaking, pressing the microphone stops the reply at once and " +
            "then listens for what you say next. The answer stays on your screen, and the part " +
            "you heard goes with your next question."
    } else {
        "Off: while Jarvis is speaking, a press of the microphone does nothing until it has " +
            "finished - nothing is recorded. Tap Stop, or wait, then talk."
    }

    /** The one line that says whose setting this is, and which one it is not. */
    const val NOTE =
        "This phone's own setting, and on by default. It is about the microphone BUTTON: " +
            "\"Interrupting Jarvis\" above is about this phone listening by itself while Jarvis " +
            "talks. Your PC's talk button already stops a reply when you press it; this switch " +
            "changes only this phone's microphone button."

    /** What a press means while a previous voice turn is still running. */
    enum class Press {
        /** Today's behaviour, kept for OFF: the reply is left alone and nothing is recorded. */
        REFUSED,

        /** Stop the reply now, drop the old turn, and start listening. */
        INTERRUPT,
    }

    /**
     * May a press of the microphone stop the reply right now?
     *
     * The ONE rule behind both halves: the press itself ([press]) and the
     * button's own enabled state on Home
     * ([com.jarvis.client.ui.screens.HomeState.micPressStopsSpeech]) - so a
     * button that looks pressable and a press that acts cannot disagree.
     *
     * @param on this phone's setting ([DEFAULT] on), read at the press.
     * @param speaking the reply on this phone is really making a sound right
     *   now (`VoiceSession.Phase.SPEAKING`). Thinking or verifying makes none,
     *   so there is nothing to interrupt and those keep today's refusal.
     */
    fun interrupts(on: Boolean, speaking: Boolean): Boolean = on && speaking

    /**
     * One press, while an earlier voice turn is still running.
     *
     * The whole decision is made in ONE call on purpose. A handler that
     * stopped the speech and then called [VoiceSession.begin] again would race
     * `begin`'s own "still finishing" guard - the old turn may not have
     * unwound yet - and the press would be intermittent instead of working
     * every time.
     *
     * @param on this phone's setting ([DEFAULT] on), read at the press, so a
     *   switch changed while Jarvis is talking applies to the very next press.
     * @param speaking the reply on this phone is really making a sound right
     *   now; see [interrupts].
     * @param stopSpeech silences the reply: the caller passes the stop word's
     *   own function (`VoiceSession.stopSpeaking`).
     * @param dropOldTurn cancels the old turn, the way
     *   `VoiceSession.interruptForWake` does, so no more of its reply is
     *   spoken and one still arriving from the PC is dropped on this phone.
     * @return [Press.INTERRUPT] when the press may go on to start listening -
     *   which the caller then does exactly as an ordinary press - or
     *   [Press.REFUSED] when it must not. Nothing is silenced on REFUSED.
     */
    fun press(
        on: Boolean,
        speaking: Boolean,
        stopSpeech: () -> Unit,
        dropOldTurn: () -> Unit,
    ): Press {
        if (!interrupts(on, speaking)) return Press.REFUSED
        // Silence FIRST, and on this thread: the owner hears the cut before the
        // new clip starts, and the stop lands before anything can re-arm the
        // speaker for the new turn (`Speaker.arm()` clears its stop flag, so a
        // stop arriving after it would silently mute the NEW reply).
        stopSpeech()
        dropOldTurn()
        return Press.INTERRUPT
    }
}
