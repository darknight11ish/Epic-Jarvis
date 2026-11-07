package com.jarvis.client.voice

/**
 * The one decision the talk-button capture loop makes about ending an
 * utterance: a held button owns the end, a tap does not.
 *
 * WHY THIS EXISTS. The owner reported on 2026-11-06: "in the latest Android
 * jarvis app I'm holding down the mic manual button and for whatever reason it
 * keeps cutting me off and acting like I took my finger off of the mic button
 * even when I'm still speaking sometimes." The talk button is tap-to-talk OR
 * hold-to-talk, and its end used to be decided in two places that never spoke:
 *
 *  - `ui/parts/VoiceButton.kt` decided hold vs tap only when the finger LIFTED
 *    (`ui/parts/VoicePress.kt`, [VoicePress.HOLD_THRESHOLD_MS] = 400 ms). It
 *    never told the session that the finger was still down.
 *  - [VoiceSession]'s capture loop ended the clip the moment [TurnEnd.push]
 *    said END - the Smart Turn model answering "finished", or
 *    [TurnEnd.MAX_PAUSE] of quiet, or the hard cap - which is exactly right for
 *    a tap (nothing else would end it) and exactly wrong for a hold, where a
 *    mid-sentence pause is the owner thinking, not the owner finishing.
 *
 * So a held press was ended by a pause and sent while the finger was still on
 * the button. This object is the missing sentence between those two places,
 * pure and without Android so a JVM test can hold it still: while the press is
 * a hold and the finger has not been released, a pause that would end a tap
 * does not end a hold. The Smart Turn ASK is skipped for the same reason - it
 * is only ever asked in order to end the clip on the pause.
 *
 * WHAT IS DELIBERATELY NOT HERE:
 *  - The hard time cap. `Recorder.record` stops at its own `maxSeconds` read
 *    loop, so a held capture still ends at the server's cap even when this says
 *    CONTINUE. That is the safety stop, and it is not the pause rule.
 *  - Live/handsfree. They build their own [TurnEnd] (`service/LiveService.kt`,
 *    `service/HandsfreeService.kt`, `service/WakeWordService.kt`) and there is
 *    no button to hold there, so their pause-based end is unchanged.
 */
internal object HoldEndRule {

    /** What the capture loop should do with one [TurnEnd] step. */
    enum class Move {
        /** Keep recording. */
        CONTINUE,

        /** Ask the Smart Turn model whether the sentence ended (model in use). */
        ASK,

        /** Stop the recorder and deliver the clip. */
        STOP,
    }

    /**
     * @param holdStarted the press became a hold and the finger has not been
     *   released since ([VoiceButton]'s `onHoldStarted`, one call per gesture).
     * @param releaseRequested the finger was lifted, or the button was slid
     *   away ([VoiceSession.release]/[VoiceSession.cancel]) - the owner is no
     *   longer holding, so the capture ends exactly as it always did.
     * @param step this buffer's [TurnEnd] answer.
     */
    fun move(
        holdStarted: Boolean,
        releaseRequested: Boolean,
        step: TurnEnd.Step,
    ): Move = when {
        // A release always wins: whatever the model or the pause thought, the
        // finger is off the button and the clip goes now (as it did before).
        releaseRequested -> Move.STOP
        // The pause that ends a tap: while the button is held it is only the
        // owner thinking. Keep capturing.
        step == TurnEnd.Step.END -> if (holdStarted) Move.CONTINUE else Move.STOP
        // Asked in order to end the clip on the pause. While held there is no
        // pause ending to ask about, so do not spend the model on it.
        step == TurnEnd.Step.ASK -> if (holdStarted) Move.CONTINUE else Move.ASK
        else -> Move.CONTINUE
    }
}
