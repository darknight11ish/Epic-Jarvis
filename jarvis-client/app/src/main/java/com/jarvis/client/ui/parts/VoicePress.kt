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
 * The rules are the ones the button has always documented: a tap starts a
 * recording that outlives the tap; a second tap while recording sends; a
 * sustained hold releases to send; sliding away cancels; and a gesture torn
 * down with no release at all (the pointerInput being disposed, the parent
 * leaving composition) cancels rather than sending.
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
