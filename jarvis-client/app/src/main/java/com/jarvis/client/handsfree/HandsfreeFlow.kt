package com.jarvis.client.handsfree

import com.jarvis.client.net.Handsfree

/**
 * The hands-free state machine: one card, read out, answered by voice, decided.
 *
 * ```
 *   Idle --card--> Reading --the sound ended--> Listening --the window ended--> Uploading
 *                     |                             |                              |
 *                     |                             +-- nothing heard ------------> Failed
 *                     +-- not allowed / no voice ---> Failed                         |
 *                                                                             Settled / Failed
 * ```
 *
 * WHAT IT IS FOR. Every other moving part of this feature is Android - a
 * speaker, a microphone, a notification, a socket - and none of them can be
 * held still in a JVM test. This class is the sequence those parts follow, with
 * no Android in it at all, so the SEQUENCE is what `HandsfreeFlowTest` holds:
 * that a card starts a read-out, that the listening window opens only after the
 * read-out finished, that nothing is uploaded unless a window was open, that a
 * second card cannot interrupt one being handled, and that a card whose own
 * `expires_in_sec` has passed is never answered.
 *
 * THE ONE INVARIANT THE OWNER ASKED FOR, and it lives here: **nothing records
 * while no card is waiting.** [State.Listening] is the only state in which the
 * service opens the microphone, and the only way into it is a card that
 * arrived, was read out, and has not expired. There is no path to it from Idle.
 *
 * PURE: the clock is a parameter on every call rather than `System.currentTimeMillis`,
 * so an expiry and a ten-second window are tested in microseconds. Nothing here
 * touches the network, the file system or the hardware.
 *
 * NOT THREAD-SAFE, and deliberately so: the service drives it from one
 * coroutine, and a lock here would only hide a second driver. `@Synchronized`
 * on every move is the alternative, and it would make the sequence untestable
 * at the moment it matters.
 */
class HandsfreeFlow(private val listenMs: Long = LISTEN_MS) {

    /** Where the flow is. Each state names the card it is about, except Idle. */
    sealed interface State {
        /** Nothing is being handled. The microphone is shut. */
        data object Idle : State

        /** The card's words are being played and nothing is recorded yet. */
        data class Reading(val card: Handsfree.Card) : State

        /**
         * The answer window. The microphone is open, and it closes at [until]
         * whatever happens - a mumble must not keep it open.
         */
        data class Listening(val card: Handsfree.Card, val until: Long) : State

        /** The clip has gone to the PC and the PC is deciding. Microphone shut. */
        data class Uploading(val card: Handsfree.Card) : State

        /**
         * The PC answered. [approved] is true for a yes, false for a no, and
         * null when nothing was decided - which is not a failure to report, it
         * is a card still waiting, and [line] says so in the PC's words.
         */
        data class Settled(
            val card: Handsfree.Card,
            val line: String,
            val approved: Boolean? = null,
        ) : State

        /** It stopped, and [why] is the sentence for the owner. */
        data class Failed(val card: Handsfree.Card?, val why: String) : State
    }

    /** Why a move did nothing. Every one of these leaves the state untouched. */
    enum class Refusal {
        /** Another card is being handled; one card at a time. */
        BUSY,

        /** The same card arrived twice (a reconnect re-sends it): already handled. */
        ALREADY,

        /** Nothing was being read out, so there is no listening window to open. */
        NOT_READING,

        /** No window was open, so there is nothing to close. */
        NOT_LISTENING,

        /** No clip was uploaded, so there is no answer to read. */
        NOT_UPLOADING,

        /** The card's own `expires_in_sec` has passed. */
        EXPIRED,
    }

    /** What a move did: went somewhere, or was refused and stayed put. */
    sealed interface Moved {
        data class To(val state: State) : Moved
        data class No(val why: Refusal) : Moved
    }

    var state: State = State.Idle
        private set

    /**
     * When this card's own window runs out, or 0 when the PC did not say.
     * Absolute milliseconds on the clock the caller passes in.
     */
    var deadline: Long = 0L
        private set

    /** True only while the answer window is open - the one "may record" flag. */
    val listening: Boolean get() = state is State.Listening

    /**
     * A card arrived.
     *
     * The same card twice is refused as [Refusal.ALREADY] rather than restarted:
     * the PC re-sends a card on reconnect, and re-reading one already being
     * answered would cut the owner's answer in half. A DIFFERENT card while one
     * is being handled is [Refusal.BUSY] - two read-outs at once are two voices
     * over each other, and the PC's own contract raises one card at a time.
     */
    fun onCard(card: Handsfree.Card, now: Long): Moved {
        if (!card.answerable) return Moved.No(Refusal.ALREADY)
        return when (val s = state) {
            // A card that is being handled - read out, listened for, or on its
            // way back - is never restarted, and never replaced.
            is State.Reading -> Moved.No(sameOrBusy(s.card, card))
            is State.Listening -> Moved.No(sameOrBusy(s.card, card))
            is State.Uploading -> Moved.No(sameOrBusy(s.card, card))
            is State.Idle, is State.Settled, is State.Failed -> {
                deadline = if (card.expiresInSec > 0) now + card.expiresInSec * 1000L else 0L
                move(State.Reading(card))
            }
        }
    }

    private fun sameOrBusy(current: Handsfree.Card, arriving: Handsfree.Card): Refusal =
        if (current.cardId == arriving.cardId) Refusal.ALREADY else Refusal.BUSY

    /**
     * The card has been read out (or could not be, which the caller reports as
     * a failure itself). Opens the window.
     *
     * A card whose own time is up does not open one: the PC would refuse the
     * answer anyway, and a microphone opened for a card nobody can answer is
     * exactly the thing this state machine exists to prevent.
     */
    fun onSpoken(now: Long): Moved {
        val reading = state as? State.Reading ?: return Moved.No(Refusal.NOT_READING)
        if (expired(now)) {
            return move(
                State.Failed(
                    reading.card,
                    "That card had expired before Jarvis could read it out, so nothing was asked.",
                ),
            )
        }
        return move(State.Listening(reading.card, until = now + listenMs))
    }

    /**
     * The window closed. [clip] is the WAV that will be uploaded, or null when
     * what was recorded was too short to be a word - which is NOT uploaded:
     * [Handsfree.NOTHING_HEARD] says the same thing without a round trip.
     */
    fun onWindowClosed(clip: ByteArray?, now: Long): Moved {
        val listening = state as? State.Listening ?: return Moved.No(Refusal.NOT_LISTENING)
        if (clip == null || clip.isEmpty()) {
            return move(State.Failed(listening.card, Handsfree.NOTHING_HEARD))
        }
        return move(State.Uploading(listening.card))
    }

    /**
     * The PC answered the clip.
     *
     * [why] is set when the answer never arrived - no link, a refused token, a
     * 404 from a PC that does not have the route - and is shown as it is: the
     * app never invents an outcome for an upload that failed.
     */
    fun onAnswer(answer: Handsfree.Answer?, why: String?, now: Long): Moved {
        val uploading = state as? State.Uploading ?: return Moved.No(Refusal.NOT_UPLOADING)
        if (answer == null) {
            return move(
                State.Failed(
                    uploading.card,
                    why?.takeIf { it.isNotBlank() } ?: Handsfree.CARD_GONE,
                ),
            )
        }
        val decision = answer.decision?.trim()?.lowercase().orEmpty()
        val approved = when {
            decision in Handsfree.APPROVE -> true
            decision in Handsfree.DENY -> false
            else -> null
        }
        return move(State.Settled(uploading.card, Handsfree.answerWords(answer), approved))
    }

    /** True when the answer window has run out and the service should close it. */
    fun windowOver(now: Long): Boolean {
        val listening = state as? State.Listening ?: return false
        return now >= listening.until
    }

    /**
     * Stops the card being handled, with [why] as the sentence for the owner,
     * and frees the state machine for the next one.
     *
     * This is the caller's way out of a card that was read out but could never
     * be ANSWERED - the owner was on a call, the PC's voice engine was
     * unavailable, or the talk button already had the microphone. Those three
     * are not failures of the machine's own order, so they are not a move
     * between its states; without this a card that could not be read out left
     * the flow in [State.Reading] for ever, and EVERY later card was refused as
     * BUSY - which would have looked like the mode quietly stopping after one
     * silent card.
     */
    fun fail(why: String): Moved {
        val card = when (val s = state) {
            is State.Reading -> s.card
            is State.Listening -> s.card
            is State.Uploading -> s.card
            is State.Settled -> s.card
            is State.Failed -> s.card
            is State.Idle -> null
        }
        deadline = 0L
        return move(State.Failed(card, why))
    }

    /** True when this card's own time is up. Nothing claims anything when the PC said nothing. */
    fun expired(now: Long): Boolean = deadline > 0 && now >= deadline

    /** The state a surface draws, in one line, or null when there is nothing to say. */
    fun line(): String? = when (val s = state) {
        is State.Idle -> null
        is State.Reading -> Handsfree.READING
        is State.Listening -> Handsfree.LISTENING
        is State.Uploading -> Handsfree.SENDING
        is State.Settled -> s.line
        is State.Failed -> s.why
    }

    /**
     * Back to Idle, and nothing is claimed about the card that was being
     * handled: turning the mode off, or losing the link, is not an answer.
     */
    fun reset(): State {
        deadline = 0L
        state = State.Idle
        return state
    }

    private fun move(to: State): Moved {
        state = to
        return Moved.To(to)
    }

    companion object {
        /** The answer window: the owner's own "ten seconds", in milliseconds. */
        const val LISTEN_MS = 10_000L
    }
}
