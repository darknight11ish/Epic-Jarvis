package com.jarvis.client

/**
 * What the Appearance screen says about the part it shares with the desktop
 * (the face and the state colours), and what it must not say.
 *
 * UI audit 2026-10-05, finding A1 - "the project's worst case: a claim that is
 * not true". The screen said of the face and colours "are sent to your
 * desktop" whenever the backend had the `appearance` capability, and
 * `JarvisRuntime.pushAppearance` called `api.postAppearance(...)` without
 * ever reading the `ApiResult` it got back. So a phone on a dead or catching-up
 * link, or a POST the PC refused, told the owner its colours were on the
 * desktop when nothing had been sent and nothing had arrived.
 *
 * The test that holds this: `AppearanceSharedTest`. [Status.SENT] is the ONLY
 * status whose words may contain "are sent" - the claim - and the other three
 * each say, in the app's own plain words, that the desktop does not have it.
 * If the capability flag is ever used on its own to pick the message again,
 * the flag has no words here: a caller that has only the flag must report
 * [Status.MAYBE_NEXT] or [Status.UNSUPPORTED], never [Status.SENT].
 *
 * Pure - no Android - so the JVM tests can hold it without a phone.
 */
object AppearanceShared {

    /**
     * What is known about the shared face and state colours.
     *
     * There is no "the desktop might have it": this phone can only report what
     * it saw, and "I do not know" is said out loud ([Status.MAYBE_NEXT])
     * rather than rounded up to a yes.
     */
    enum class Status {
        /**
         * No send has been attempted yet on this visit - a fresh app, or an
         * edit not made yet, while the link is up. The words promise the send,
         * not its result.
         */
        MAYBE_NEXT,

        /** `POST /api/appearance` answered OK: the desktop has it, or is about to. */
        SENT,

        /**
         * The send was attempted and did not succeed - no link, a refusal, a
         * server error. The owner's change is on this phone only.
         */
        NOT_SENT,

        /**
         * The backend has no `appearance` route at all, so nothing is shared in
         * either direction yet. A capability answer, not a send result.
         */
        UNSUPPORTED,
    }

    /**
     * The "Shared with your desktop" group's own words. [SENT] describes both
     * directions, because the sync is two-way; the other three say plainly
     * that the desktop does not have the change.
     */
    fun groupWords(status: Status): String = when (status) {
        Status.SENT ->
            "The face and the state colours are sent to your desktop, and a " +
                "change made there shows up here too. The animal options are kept " +
                "on your PC and shared the same way - except sharpness and frame " +
                "rate, which stay on this phone. Nothing else on this screen " +
                "leaves the phone."
        Status.NOT_SENT ->
            "Not sent to your desktop - Jarvis could not reach it, so for now " +
                "the face and the state colours are on this phone only. They are " +
                "sent again the next time a change is made with the link up. " +
                "Nothing else on this screen leaves the phone."
        Status.MAYBE_NEXT ->
            "Not sent yet: the face and the state colours are shared with your " +
                "desktop, and a change made here goes over the next time the " +
                "link is up. Nothing else on this screen leaves the phone."
        Status.UNSUPPORTED ->
            "Not synced: your desktop doesn't support it yet. For now the face " +
                "and the state colours stay on this phone."
    }

    /**
     * The extra half-sentence under Randomise's and Reset's Undo line, so the
     * owner knows the roll reaches the desktop once the Undo window closes.
     * Null when there is nothing true to add - and deliberately silent after a
     * failed send: the group's own line above already says it did not go, and
     * a second sentence repeating that is noise. Never says a send happened.
     */
    fun undoLineSuffix(status: Status): String? = when (status) {
        Status.SENT -> " Sent to your desktop when this goes away."
        Status.MAYBE_NEXT -> " Saved here now; sent to your desktop when this goes away."
        Status.NOT_SENT, Status.UNSUPPORTED -> null
    }

    /**
     * What is known, from the capability flag and the result of the last send
     * this phone made. [sendOk] is null while no send has been attempted.
     *
     * [capability] alone never yields [SENT]: that was finding A1 exactly.
     */
    fun statusOf(capability: Boolean, sendOk: Boolean?): Status = when {
        !capability -> Status.UNSUPPORTED
        sendOk == true -> Status.SENT
        sendOk == false -> Status.NOT_SENT
        else -> Status.MAYBE_NEXT
    }

    /**
     * Whether the desktop takes the shared part at all - the `appearance`
     * capability, said by a [Status] rather than kept as a second, separately
     * read flag that could disagree with it.
     *
     * [Status.NOT_SENT] is the one that cannot answer: a route that refused a
     * send and no route at all look the same from here, and the safe direction
     * is "no" - the same direction the group's own words keep on an unknown.
     */
    fun capabilityOf(status: Status): Boolean = when (status) {
        Status.SENT, Status.MAYBE_NEXT -> true
        Status.NOT_SENT, Status.UNSUPPORTED -> false
    }
}
