package com.jarvis.client.voice

/**
 * The one point that decides WHICH part of this app may have the microphone.
 *
 * THE PROBLEM IT SOLVES, measured. On this phone the microphone already has
 * three users, and each of them opens its own `AudioRecord`:
 *
 *  - the talk button (`VoiceSession`, `Recorder`), while a finger or a tap
 *    holds a turn;
 *  - Jarvis Live (`LiveService`), while Live is on on this phone;
 *  - "hey Jarvis" (`WakeWordService`), while listening is on.
 *
 * Two `AudioRecord`s open at once is not a crash: Android mixes them and both
 * hear the same room. It is worse than a crash in one specific way - both
 * believe they heard the owner, so a "confirm" said to a card would also be a
 * wake word, and the phone would answer the same ten seconds twice.
 *
 * Before hands-free, those three avoided each other by reading each other's
 * state (`voice.phase.value == CAPTURING`, `JarvisRuntime.liveOnHere()`, the
 * Live card). That works while every user is one of the three. The hands-free
 * answer window is a FOURTH user, it is not a "turn" anybody can see in
 * `VoiceSession`'s phase, and it opens by itself when a card arrives. Adding a
 * fourth pair of checks to a fourth file is how the fifth one is forgotten.
 *
 * So this is one small ledger instead. It says who holds the microphone RIGHT
 * NOW, and nothing else:
 *
 *  - the hands-free window [HANDSFREE] ACQUIRES it while it records, and
 *    releases it the moment it closes;
 *  - the talk button [TALK] ACQUIRES it too (`audio/Recorder.kt`), before it
 *    opens its own `AudioRecord` and gives it back in a `finally`. It used to
 *    be a fourth part that only READ the other three - which is why the answer
 *    window's refusal could never fire: nothing but the window ever held it, so
 *    a second recorder over a held press was exactly what the ledger was built
 *    to stop and could not. Both sides now go through [MicClaim], which owns
 *    the sentences a refusal is shown in;
 *  - the two always-on listeners never hold it - they ask [freeFor] before they
 *    open their recorder and while they read, and when the answer is no they
 *    close the recorder and wait, which is what "pause and resume" means here.
 *    (`LiveService.listen` and `WakeWordService.listen` already have exactly
 *    that shape for each other; one condition each is all this adds.)
 *
 * WHY A CLASS AND AN OBJECT. The rules are worth a test, and a test needs a
 * fresh ledger; the app needs one shared one. [MicLedger] is the rules,
 * [MicOwner] is the instance every caller uses - the same split `VoicePress`
 * and the button use.
 *
 * It is NOT a mutex and it never blocks: a listener that is refused a
 * microphone goes round its loop and asks again a fifth of a second later,
 * which is what it already does for the two reasons it already pauses. Nothing
 * here reads or writes audio, and nothing here knows what the microphone is
 * for.
 */
open class MicLedger {

    @Volatile
    private var heldBy: String? = null

    /**
     * Take the microphone for [owner].
     *
     * True when this owner now holds it - including when it already did, so a
     * double acquire is harmless. False when someone else holds it, and then
     * NOTHING changes: a refused acquire never steals the microphone, because
     * the one case that matters is the answer window opening while the owner is
     * mid-sentence to the talk button, and cutting that sentence off would lose
     * what he said.
     */
    @Synchronized
    fun acquire(owner: String): Boolean {
        val holder = heldBy
        if (holder != null && holder != owner) return false
        heldBy = owner
        return true
    }

    /**
     * Give it back - only if this owner really has it.
     *
     * A release from a part that does not hold it is a no-op, NOT a free: the
     * likely caller of this method is a `finally` block in a service that just
     * shut down, and one of those freeing the microphone another part is
     * holding would let a third part in. The bug that produces is two
     * recorders, which is the whole thing this class exists to stop.
     */
    @Synchronized
    fun release(owner: String) {
        if (heldBy == owner) heldBy = null
    }

    /** Who holds it, or null when nobody does. For words on a screen, never a decision. */
    @Synchronized
    fun holder(): String? = heldBy

    /**
     * May [owner] open its recorder now?
     *
     * True when nobody holds the microphone, or when this owner does. Every
     * always-on listener asks this and nothing else; it is deliberately a
     * question about this moment, because a listener that cached the answer
     * would be exactly the stale copy this class replaces.
     */
    @Synchronized
    fun freeFor(owner: String): Boolean {
        val holder = heldBy
        return holder == null || holder == owner
    }
}

/**
 * The app's one microphone ledger. See [MicLedger].
 *
 * The four owners are named here rather than spelled as strings at each call
 * site, so two parts cannot disagree about their own name - and a test can walk
 * [ALL] and prove every one of them is distinct.
 */
object MicOwner : MicLedger() {
    /** The hands-free answer window: the only part that HOLDS the microphone. */
    const val HANDSFREE = "handsfree"

    /** Jarvis Live's recorder (`LiveService`). */
    const val LIVE = "live"

    /** The "hey Jarvis" spotter (`WakeWordService`). */
    const val WAKE = "wake"

    /** The talk button (`VoiceSession` / `Recorder`). */
    const val TALK = "talk"

    /** Every owner this app uses, for the test that they cannot collide. */
    val ALL = listOf(HANDSFREE, LIVE, WAKE, TALK)
}

/**
 * One claim on the microphone, and the words a part says when it is refused.
 *
 * [MicLedger] decides who holds it; this is what the two parts that really take
 * it do with that decision, so both sides are written one way instead of each
 * file inventing its own:
 *
 *  - the talk button (`audio/Recorder.kt`) takes [MicOwner.TALK] before it
 *    opens its `AudioRecord`, and gives it back in a `finally`;
 *  - the hands-free answer window (`service/HandsfreeService.kt`) takes
 *    [MicOwner.HANDSFREE] before its ten seconds, and gives it back when the
 *    window closes.
 *
 * WHY IT IS A SEPARATE OBJECT RATHER THAN ONE LINE IN EACH FILE. Neither side
 * can be built in a JVM test - one needs an Android `Service`, the other an
 * `AudioRecord` - so "the second recorder never opens" would otherwise rest on
 * code no test reaches. [take] and [free] take the ledger as a parameter, so a
 * test can drive both directions with a fresh [MicLedger] and hold the two
 * sentences too.
 *
 * A REFUSAL IS ALWAYS IN WORDS. It is never a silent return: the owner pressed
 * the button, or a card arrived, and something must say why nothing was
 * recorded.
 */
object MicClaim {

    /** What a part may do now. */
    sealed interface Now {
        /** The microphone is this part's, and it may open its recorder. */
        data object Open : Now

        /** Someone else has it. [why] is a whole sentence the owner is shown. */
        data class Busy(val why: String) : Now
    }

    /**
     * The hands-free window's sentence when the talk button holds the
     * microphone: the card was read out, but no window was opened over a
     * sentence the owner is already speaking.
     */
    const val TALKING = "You were talking to Jarvis, so the card was not read out."

    /**
     * The talk button's sentence while the answer window holds it. Short on
     * purpose: the window is ten seconds at most, so "try again" is true.
     */
    const val LISTENING = "Jarvis is listening for your answer to a card, " +
        "so the microphone is busy. Try again in a moment."

    /** Neither of the two above - a holder this app does not name today. */
    const val BUSY = "The microphone is busy. Try again in a moment."

    /**
     * Take the microphone for [owner], or say in words why not.
     *
     * Nothing is stolen: a refused claim leaves the holder exactly as it was,
     * which is [MicLedger.acquire]'s own rule and the reason the sentence is a
     * refusal rather than a takeover.
     */
    fun take(owner: String, ledger: MicLedger = MicOwner): Now =
        if (ledger.acquire(owner)) Now.Open else Now.Busy(busy(owner, ledger))

    /**
     * Give it back - only if this owner really has it. A no-op otherwise, so a
     * `finally` in a part that was never granted it cannot free another part's.
     */
    fun free(owner: String, ledger: MicLedger = MicOwner) = ledger.release(owner)

    /** The sentence for a refusal, named by the part that was asked. */
    fun busy(owner: String, ledger: MicLedger = MicOwner): String =
        when (ledger.holder()) {
            MicOwner.TALK -> if (owner == MicOwner.HANDSFREE) TALKING else BUSY
            MicOwner.HANDSFREE -> if (owner == MicOwner.TALK) LISTENING else BUSY
            else -> BUSY
        }
}
