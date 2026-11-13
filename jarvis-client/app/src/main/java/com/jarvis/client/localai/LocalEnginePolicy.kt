package com.jarvis.client.localai

/**
 * A clock in milliseconds. The app passes the system's; a test passes a
 * number it can move by hand, so the 5-second and 180-second rules are
 * checked exactly rather than by sleeping and hoping.
 */
fun interface LocalClock {
    fun nowMillis(): Long
}

/**
 * The two time rules that keep a model from holding a phone's memory or a
 * generation from running forever.
 *
 * ## The rules
 *
 * 1. **5 seconds with nothing asked unloads the model.** Loading a GGUF costs
 *    hundreds of megabytes of resident memory; leaving it resident while the
 *    owner reads the screen is how the next app gets killed. The window is
 *    [IDLE_UNLOAD_MILLIS].
 * 2. **One generation is hard-capped at 180 seconds.** At every token the
 *    native loop asks [TokenSink.stopped]; this class is what answers yes
 *    when the cap has passed (through the controller). The cap is
 *    [HARD_CAP_MILLIS].
 *
 * These are the policy PrivateLM applies around its engine: it unloads when
 * idle and puts a 180-second floor under a single generation. This port fixes
 * the idle window at 5 seconds as the project plan states; PrivateLM's own
 * token-stall timer is 30 seconds, and this file does not claim to be that
 * timer. The cap is deliberately NOT scaled by the token budget here, because
 * the plan says "180 s hard" and a rule that quietly becomes 2,048 seconds is
 * not a hard cap.
 *
 * ## Why it is a class with no Android and no coroutines
 *
 * Time is the only input and the answer is one of three values, so the whole
 * rule is a pure function of a clock. `LocalEnginePolicyTest` drives it at
 * 4,999 ms, 5,000 ms, 179,999 ms and 180,000 ms with no sleeps. The
 * controller's one-second tick and its generation watchdog are the only
 * callers.
 */
class LocalEnginePolicy(
    private val clock: LocalClock = LocalClock { System.nanoTime() / 1_000_000L },
    val idleMillis: Long = IDLE_UNLOAD_MILLIS,
    val hardCapMillis: Long = HARD_CAP_MILLIS,
) {

    init {
        require(idleMillis > 0L) { "idleMillis must be positive" }
        require(hardCapMillis > 0L) { "hardCapMillis must be positive" }
    }

    /** When the last request (a load or a generation) started, or null. */
    private var lastRequestAt: Long? = null

    /** When the running generation started, or null when none is running. */
    private var generationStartedAt: Long? = null

    /** What a [decide] call says to do next. */
    sealed interface Decision {

        data object Nothing : Decision

        /** Nothing has been asked for [idleMillis]: free the model. */
        data object UnloadAfterIdle : Decision

        /** This generation has run for [hardCapMillis]: stop it at the next token. */
        data object StopAtHardCap : Decision
    }

    /** Records a request now - a model load, or the start of a generation. */
    fun requested() = requestedAt(clock.nowMillis())

    /** [requested] with the time supplied, for tests and for the controller's one clock. */
    fun requestedAt(now: Long) {
        lastRequestAt = now
    }

    /** A generation has started now. It also counts as a request. */
    fun generationStarted() = generationStartedAt(clock.nowMillis())

    fun generationStartedAt(now: Long) {
        lastRequestAt = now
        generationStartedAt = now
    }

    /**
     * The generation finished (answered, failed or was stopped). The idle
     * window starts again from now, not from when the generation started: a
     * reply that took 170 seconds must not unload the model the instant it
     * lands.
     */
    fun generationFinished() = generationFinishedAt(clock.nowMillis())

    fun generationFinishedAt(now: Long) {
        generationStartedAt = null
        lastRequestAt = now
    }

    /** Something happened that is not a request (the owner typed). */
    fun touched() = requestedAt(clock.nowMillis())

    fun isGenerating(): Boolean = generationStartedAt != null

    /** True when a model is loaded, nothing is running, and the window has passed. */
    fun idleDue(now: Long = clock.nowMillis()): Boolean {
        if (isGenerating()) return false
        val last = lastRequestAt ?: return false
        return now - last >= idleMillis
    }

    /** True when the running generation has reached the hard cap. */
    fun hardCapDue(now: Long = clock.nowMillis()): Boolean {
        val started = generationStartedAt ?: return false
        return now - started >= hardCapMillis
    }

    /** When the running generation must stop, or null when none is running. */
    fun hardDeadline(): Long? = generationStartedAt?.plus(hardCapMillis)

    /** The one question the controller asks on its tick. */
    fun decide(now: Long = clock.nowMillis()): Decision = when {
        hardCapDue(now) -> Decision.StopAtHardCap
        idleDue(now) -> Decision.UnloadAfterIdle
        else -> Decision.Nothing
    }

    /**
     * Forgets the model's history. Called when a model is unloaded or the
     * switch goes off, so the next load starts a fresh 5-second window rather
     * than inheriting an old one.
     */
    fun reset() {
        lastRequestAt = null
        generationStartedAt = null
    }

    companion object {

        /** 5 seconds with no request unloads the model. */
        const val IDLE_UNLOAD_MILLIS: Long = 5_000L

        /** One reply is hard-capped at 180 seconds. */
        const val HARD_CAP_MILLIS: Long = 180_000L
    }
}
