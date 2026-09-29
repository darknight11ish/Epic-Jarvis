package com.jarvis.client.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One pairing attempt at a time, from "Connect" to the key in hand
 * (docs/PAIRING-DESIGN.md §3 and §7.2). Lives for the process, not for a
 * screen, so turning the phone mid-pairing does not drop an attempt whose
 * card the owner is about to approve - and it is never saved anywhere: the
 * secret, the nonce and the key live only in memory, and only until the
 * attempt ends or the key is taken.
 *
 * It does not save the key itself. On [State.Approved] the pairing screen
 * takes it ([takeKey]) and hands it to the same "save, shake hands, and only
 * then drop the old key" code the old token form uses (MainActivity's
 * pairing branch), so a failed handshake keeps the phone on its old key.
 */
class PairingFlow(
    private val scope: CoroutineScope,
    private val transport: PairTransport,
    /** The 1,296 words, or null when the list cannot be read. */
    private val wordList: () -> List<String>?,
    /** For tests: how long between collects. */
    private val everyMs: Long = Pairing.COLLECT_EVERY_MS,
) {

    sealed interface State {
        data object Idle : State
        /** The claim is on its way. */
        data class Asking(val address: String) : State
        /** The card is up on the PC; these are the words, worked out on this phone. */
        data class Words(val address: String, val words: List<String>) : State
        /** The PC approved. [token] is taken once, by [takeKey]. */
        class Approved(val address: String, internal val token: String) : State
        data class Ended(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    private var job: Job? = null

    /** Starts pairing with [target] under [name]. Ends any attempt already running. */
    fun start(target: Pairing.Target, name: String) {
        job?.cancel()
        Pairing.nameProblem(name)?.let {
            _state.value = State.Ended(it)
            return
        }
        val words = wordList()
        if (words == null) {
            _state.value = State.Ended(Pairing.BAD_REQUEST)
            return
        }
        _state.value = State.Asking(target.host)
        job = scope.launch {
            val attempt = PairAttempt(target, name, transport)
            val claimed = attempt.claim(words)
            if (claimed !is Pairing.Claimed.CardUp) {
                _state.value = State.Ended((claimed as Pairing.Claimed.Refused).message)
                return@launch
            }
            _state.value = State.Words(target.host, claimed.words)
            // The session lasts at most 10 minutes (design §3); the card
            // itself 180 s. A few seconds more, in case the clocks differ.
            val waitMs = ((claimed.expiresIn ?: 600).coerceIn(1, 600) + 15) * 1000L
            var waited = 0L
            while (true) {
                delay(everyMs)
                waited += everyMs
                when (val c = attempt.collect()) {
                    Pairing.Collected.Waiting, Pairing.Collected.NoAnswer -> {
                        if (waited >= waitMs) {
                            _state.value = State.Ended(Pairing.WAITED_TOO_LONG)
                            return@launch
                        }
                    }
                    is Pairing.Collected.Approved -> {
                        _state.value = State.Approved(target.address, c.token)
                        return@launch
                    }
                    is Pairing.Collected.Ended -> {
                        _state.value = State.Ended(c.message)
                        return@launch
                    }
                }
            }
        }
    }

    /**
     * The approved key and the address to save with it, handed over once:
     * afterwards this flow holds neither, and is back to [State.Idle].
     */
    fun takeKey(): Pair<String, String>? {
        val s = _state.value as? State.Approved ?: return null
        _state.value = State.Idle
        return s.address to s.token
    }

    /** Stops asking. On the PC the card simply runs out; nothing is saved here. */
    fun cancel() {
        job?.cancel()
        job = null
        _state.value = State.Idle
    }
}
