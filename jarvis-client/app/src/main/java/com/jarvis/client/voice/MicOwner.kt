package com.jarvis.client.voice

/**
 * ONE microphone, five things that want it: the arbitration point.
 *
 * The phone has one microphone and this app has five capture paths - Jarvis
 * Live (`service/LiveService.kt`), "hey Jarvis" (`service/WakeWordService.kt`),
 * the talk button (`audio/Recorder.kt`), call recording
 * (`service/CallRecordService.kt`), and the hands-free answer window
 * (`service/HandsfreeService.kt`, 2026-11-04). Android does not hand out two:
 * the second `AudioRecord` opened on a phone generally gets silence, or the
 * first one starts returning zeros. Until this file existed, nothing decided
 * who owned it - each path opened the microphone when it felt like it, and the
 * listening loop's own "may I listen" checks were written per service, so a
 * fifth path could not be added without reading three others.
 *
 * So there is ONE answer to "may this path open the microphone now?", and it
 * is here, pure, with `MicOwnerTest` running it on the JVM.
 *
 * THE RULE, IN ORDER. Call recording outranks everything, before and during a
 * call, because it is the only path whose whole reason is a moment that will
 * not come back:
 *  - **armed** (the owner said "record call", no call yet): the other paths
 *    keep the microphone CLOSED, so the moment a call starts nothing else is
 *    holding it. They are asked to close, not killed: pausing is what can be
 *    undone. Stopping Live's or the wake word's service would be worse than
 *    useless, because Android 14+ refuses to START a microphone foreground
 *    service from the background - so a service stopped while the owner is on
 *    a call could not be started again until the app was in front, and "paused
 *    and restored" would quietly become "off until the owner notices";
 *  - **recording**: the same, plus call recording itself must not be asked to
 *    give way by anything.
 *
 * Below call recording, the two paths that hold a recorder for a moment whose
 * sound belongs to them alone - the talk button and the hands-free answer
 * window - exclude each other. Neither may open a recorder over the other's
 * sentence: the talk button is refused in [LISTENING], the answer window in
 * [TALKING], and neither ever steals the microphone (a refused open changes
 * nothing). Live and the wake word hold nothing and yield to both: they ask
 * before opening and while reading, close their recorder when the answer is
 * no, and open it again when it is free.
 *
 * WHAT A PATH DOES WITH IT. Each capture path asks before opening and after
 * every read loop (Live already re-asks every window and every few steps;
 * `WakeWordService` re-asks on its own loop), so a paused path closes its
 * recorder - Android's microphone sign goes off - and opens it again when the
 * owner disarms. Restoring is therefore free and needs no restart of anything.
 *
 * Pure Kotlin: no Android types, no AudioRecord, no coroutines. The live
 * holder of [State] is `MicNow`, and the only thing that mutates it is the
 * service that owns the path.
 */
object MicOwner {

    /** The five capture paths. [CALL_RECORD] outranks the rest. */
    enum class Use(val words: String) {
        LIVE("Jarvis Live"),
        WAKE("\"hey Jarvis\""),
        TALK("the talk button, a voice check or a training clip"),
        HANDSFREE("the hands-free answer window"),
        CALL_RECORD("call recording"),
    }

    /**
     * Who wants the microphone. [armed] is call recording waiting for a call
     * (it holds nothing yet); [capturing] is the path with a recorder open
     * right now; [heldBy] is the path that has claimed it, armed or recording.
     */
    data class State(
        val armed: Boolean = false,
        val capturing: Use? = null,
        val heldBy: Use? = null,
    )

    /**
     * The answer to "may this path open the microphone?".
     *
     * [close] is true when a DIFFERENT path is recording and must be told to
     * close now (only ever set for [Use.CALL_RECORD], which preempts); [why]
     * is the one plain sentence shown when the answer is no, so every screen
     * says the same thing about the same cause.
     */
    data class Decision(val allowed: Boolean, val why: String = "", val close: Boolean = false)

    /** The armed line, shown when a path is refused because a call is waiting to be recorded. */
    const val ARMED_REFUSAL = "Call recording is armed, so this phone is not using the microphone until you disarm it."

    /** The refusal while a call is actually being recorded. */
    const val RECORDING_REFUSAL = "A call is being recorded, so the microphone is not available."

    /**
     * The hands-free answer window's sentence when the talk button holds the
     * microphone: the card was read out, but no window was opened over a
     * sentence the owner is already speaking.
     */
    const val TALKING = "You were talking to Jarvis, so the card was not read out."

    /**
     * The talk button's sentence while the answer window holds it - and the
     * one Live and the wake word are paused with. Short on purpose: the window
     * is ten seconds at most, so "try again" is true.
     */
    const val LISTENING = "Jarvis is listening for your answer to a card, " +
        "so the microphone is busy. Try again in a moment."

    /**
     * May [use] open the microphone, given [state]?
     *
     * Call recording is always allowed (it preempts, and [Decision.close] says
     * whoever holds the microphone now must let go); everything else is
     * refused while call recording is armed or recording. Below that, the talk
     * button and the hands-free answer window exclude each other, and the two
     * always-on listeners yield to both - see the file comment.
     */
    fun mayOpen(state: State, use: Use): Decision {
        if (use == Use.CALL_RECORD) {
            return Decision(allowed = true, close = state.capturing != null && state.capturing != Use.CALL_RECORD)
        }
        // Recording is the narrower, louder case: it is checked first so the
        // sentence names what is actually happening rather than the arming
        // that came before it.
        if (state.capturing == Use.CALL_RECORD) return Decision(allowed = false, why = RECORDING_REFUSAL)
        if (state.armed) return Decision(allowed = false, why = ARMED_REFUSAL)
        if (state.heldBy == Use.CALL_RECORD) return Decision(allowed = false, why = ARMED_REFUSAL)

        // The two paths that really hold a recorder for a moment of their own:
        // neither may open one over the other's sentence.
        if (use == Use.TALK && state.capturing == Use.HANDSFREE) {
            return Decision(allowed = false, why = LISTENING)
        }
        if (use == Use.HANDSFREE && state.capturing == Use.TALK) {
            return Decision(allowed = false, why = TALKING)
        }
        // Live and "hey Jarvis" hold nothing: they pause for either of the two
        // above and open again when it is over. Asked of those two only - a
        // holder asking again must never be refused by its own claim.
        if ((use == Use.LIVE || use == Use.WAKE) &&
            (state.capturing == Use.HANDSFREE || state.capturing == Use.TALK)
        ) {
            return Decision(allowed = false, why = LISTENING)
        }
        return Decision(allowed = true)
    }

    /** Call recording is armed: it holds the microphone from now on, and nothing else may open it. */
    fun arm(state: State): State = state.copy(armed = true, heldBy = Use.CALL_RECORD)

    /** Disarmed, and it is recording nothing: the other paths may open it again. */
    fun disarm(state: State): State = State(armed = false, capturing = null, heldBy = null)

    /**
     * [use] has opened the microphone. Call recording preempts: the other
     * path's [capturing] is replaced rather than shared, because on a phone
     * they cannot both be recording.
     */
    fun opened(state: State, use: Use): State = state.copy(capturing = use, heldBy = if (use == Use.CALL_RECORD) use else state.heldBy)

    /** [use] has closed its recorder. Only the path that had it is cleared. */
    fun closed(state: State, use: Use): State =
        if (state.capturing == use) state.copy(capturing = null) else state

    /**
     * Is call recording in the way? The one predicate the other three paths
     * need where they cannot act on a refusal (a loop that is already
     * running): Live's `stillOpen` and the wake word's read loop ask this, and
     * a true answer closes their recorder.
     */
    fun callRecordingHolds(state: State): Boolean =
        state.armed || state.heldBy == Use.CALL_RECORD || state.capturing == Use.CALL_RECORD
}
