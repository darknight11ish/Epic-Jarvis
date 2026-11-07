package com.jarvis.client.ui.parts

/**
 * What one press of the talk button means when it ends - pure, no Compose, no
 * Android, so a JVM test can hold it still.
 *
 * WHY THIS EXISTS. The owner reported on 2026-10-13: "the mic button in the
 * bottom right hand corner of the android app doesnt work if i tap it or hold
 * it down". The old [VoiceButton] keyed its `pointerInput` on
 * `(enabled, capturing)`. The moment `onBegin()` was called, `VoiceSession`
 * set its phase to CAPTURING (`voice/VoiceSession.kt`, `begin()`'s first
 * statement in the coroutine), which changed the `capturing` parameter within
 * a frame - and a key change RESTARTS the gesture coroutine. The restarted
 * gesture saw no release, ran its `finally`, and treated that as a teardown,
 * so every tap and every hold called `onCancel()` straight after `onBegin()`.
 * The button was not disabled; it was cancelling itself.
 *
 * THE FIX, in two parts:
 *  - [VoiceButton] keys its `pointerInput` on `enabled` only and reads
 *    `capturing` through `rememberUpdatedState`, so the capture state can
 *    change mid-gesture without restarting the gesture;
 *  - the release decision below is the one the gesture makes in its `finally`,
 *    named so the four cases are visible and testable instead of being four
 *    branches inside a coroutine.
 *
 * A THIRD PART, added 2026-11-06 for the owner's next report ("I'm holding
 * down the mic manual button and ... it keeps cutting me off ... even when I'm
 * still speaking"): [holdReached] says when the press has become a hold WHILE
 * THE FINGER IS STILL DOWN, and [VoiceButton]'s `onHoldStarted` tells the
 * session from that moment. Before it, hold-versus-tap was only decided when
 * the finger lifted, so a pause in a held sentence ended the clip as if the
 * finger had come off (the rule that consumes it is
 * [com.jarvis.client.voice.HoldEndRule]). Tap-to-talk never sets that flag and
 * keeps its pause auto-send exactly as it was.
 *
 * The rules are the ones the button has always documented: a tap starts a
 * recording that outlives the tap; a second tap while recording sends; a
 * sustained hold announces itself and then releases to send; sliding away
 * cancels; and a gesture torn down with no release at all (the pointerInput
 * being disposed, the parent leaving composition) cancels rather than sending.
 */
internal object VoicePress {

    /** A sustained press at least this long is a hold-to-talk, not a tap. */
    const val HOLD_THRESHOLD_MS: Long = 400L

    /** What the end of a press asks the session to do. */
    enum class Release {
        /** Send the clip now (a hold released, or the second tap of a tap-to-talk). */
        SEND,

        /**
         * Nothing to send yet: a quick first tap enters capturing mode and the
         * recording continues until the second tap or the Smart Turn pause.
         */
        KEEP,

        /** Throw the clip away (slid away, or the gesture was torn down). */
        CANCEL,
    }

    /**
     * Whether the press has become a HOLD - the finger is still down and the
     * press has lasted [HOLD_THRESHOLD_MS] - so the session can be told that
     * before the finger lifts.
     *
     * WHY THIS EXISTS. [release] above only decides at the END of a press. The
     * owner's report of 2026-11-06 - "I'm holding down the mic manual button
     * and ... it keeps cutting me off ... even when I'm still speaking" - is
     * what that gap costs: the session began the clip on press-down, then a
     * mid-sentence pause hit the Smart Turn end, and the clip was sent while
     * the finger was still on the button. The button must say "still holding"
     * while there is still time, and this is the predicate that says when.
     *
     * A slide-away before the threshold must never fire it ([cancelled]), and
     * neither must a press that somehow arrives here after its release was
     * seen ([released]) - so the owner is never told a hold that was already
     * over. [alreadyFired] is the "exactly once per gesture" half.
     *
     * The gesture itself is Compose-only; this predicate is pure so the three
     * ways a press can fail to become a hold are testable off-device.
     */
    fun holdReached(
        durationMs: Long,
        cancelled: Boolean,
        released: Boolean,
        alreadyFired: Boolean,
    ): Boolean =
        !alreadyFired && !cancelled && !released && durationMs >= HOLD_THRESHOLD_MS

    /**
     * What one press means, from what the gesture observed.
     *
     * @param wasCapturingAtDown whether a recording was already running when
     *   the finger went down - the second tap of tap-to-talk.
     * @param cancelled the finger slid far enough up to mean "cancel".
     * @param released the finger came up before the gesture was torn down.
     * @param durationMs how long the press lasted (only used for a first tap).
     */
    fun release(
        wasCapturingAtDown: Boolean,
        cancelled: Boolean,
        released: Boolean,
        durationMs: Long,
    ): Release = when {
        // Slid away: the owner changed their mind, whether or not a finger lift
        // was also seen.
        cancelled -> Release.CANCEL
        // Torn down without a release (composition disposed, parent gone):
        // never send words the owner did not finish.
        !released -> Release.CANCEL
        // Second tap while recording: stop and send.
        wasCapturingAtDown -> Release.SEND
        // Held down past the threshold: hold-to-talk, released to send.
        durationMs >= HOLD_THRESHOLD_MS -> Release.SEND
        // A quick first tap: the recording outlives it.
        else -> Release.KEEP
    }
}
