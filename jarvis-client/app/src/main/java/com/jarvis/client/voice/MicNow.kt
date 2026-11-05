package com.jarvis.client.voice

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The ONE live record of who has this phone's microphone - [MicOwner]'s rules,
 * with the state that every capture path reads.
 *
 * Pure decisions live in [MicOwner] (and are tested on the JVM); this object
 * is only the place they are held, so Live, the wake word, the talk button and
 * call recording all ask the same question instead of each keeping its own
 * opinion. Writes are synchronized: the service loops are on different
 * threads, and a lost "recording" claim would be a microphone opened on top of
 * another.
 *
 * Deliberately NO Android types: it is imported by `CallRecordNow` (the
 * recorder's own state), by `LiveService` and by `WakeWordService`, and it
 * must not drag anything into a JVM test.
 */
object MicNow {

    private val _state = MutableStateFlow(MicOwner.State())

    /** Who wants the microphone now: read by each capture path before it opens one. */
    val state: StateFlow<MicOwner.State> = _state.asStateFlow()

    /** Call recording is armed: it claims the microphone, and the other paths close theirs. */
    @Synchronized
    fun arm() {
        _state.value = MicOwner.arm(_state.value)
    }

    /** Call recording is over or cancelled: everything may use the microphone again. */
    @Synchronized
    fun disarm() {
        _state.value = MicOwner.disarm(_state.value)
    }

    /** May [use] open the microphone now? */
    @Synchronized
    fun mayOpen(use: MicOwner.Use): MicOwner.Decision = MicOwner.mayOpen(_state.value, use)

    /** [use] has opened its recorder. */
    @Synchronized
    fun opened(use: MicOwner.Use) {
        _state.value = MicOwner.opened(_state.value, use)
    }

    /** [use] has closed its recorder. */
    @Synchronized
    fun closed(use: MicOwner.Use) {
        _state.value = MicOwner.closed(_state.value, use)
    }

    /**
     * Is call recording in the way? For a loop that is already running and
     * cannot act on a refusal: a true answer closes its recorder and it asks
     * again next time round.
     */
    fun callRecordingHolds(): Boolean = MicOwner.callRecordingHolds(_state.value)
}
