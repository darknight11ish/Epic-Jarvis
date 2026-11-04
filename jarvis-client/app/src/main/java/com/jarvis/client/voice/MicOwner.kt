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
