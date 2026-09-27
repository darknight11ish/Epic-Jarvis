package com.jarvis.client

/**
 * What the phone says about a link to the PC that cannot be acted on, and
 * when coming back to the app should reconnect by itself. Pure, so
 * `LinkWordsTest` can hold it to rule 4 without a phone.
 *
 * Two different states used to share one sentence (phone walk-through,
 * 2026-09-27): "Not connected to the desktop, so this decision cannot be
 * delivered." was shown on an approval card both when the PC really was
 * out of reach AND when the link was up but "catching up" - updates had
 * stopped for a while, so Jarvis could not be sure the card was still the
 * latest. The second is not "not connected", and Home's own status line was
 * saying "Catching up…" at the same moment. Now each state has its own
 * words, and the gate itself is exactly as strict as before: either state
 * still blocks the decision (rule 4).
 */
object LinkWords {

    /**
     * The one word for a link that is up but not trusted yet, in both apps
     * (jarvis-link.js `linkWords`, held there by tests/continuity.mjs). Home's
     * status line and the Checks screen's Connection card both say it - the
     * Connection card used to say "Stale" for the same state.
     */
    const val CATCHING_UP = "Catching up…"

    /** A decision refused because the PC cannot be reached at all. */
    const val DECISION_NOT_CONNECTED = "Not connected to the desktop, so this decision cannot be delivered."

    /**
     * A decision refused because the link is catching up. Says what is
     * happening and that the decision is only waiting, not lost.
     */
    const val DECISION_CATCHING_UP =
        "Jarvis is catching up with your PC to make sure it has the latest, so this decision " +
            "waits until then."

    /**
     * Why a decision (Approve, Deny's cousins on the memory queue, the
     * overnight-tidy card) cannot be sent right now, or null when it can.
     * Non-null whenever [stale] is true or the link is not [LinkState.CONNECTED],
     * exactly the test every caller used before - only the words differ.
     */
    fun decisionBlocked(link: LinkState, stale: Boolean): String? = when {
        link != LinkState.CONNECTED -> DECISION_NOT_CONNECTED
        stale -> DECISION_CATCHING_UP
        else -> null
    }

    /**
     * Whether the app coming back into view should force a fresh
     * connection, the same one Home's Retry makes. True only for a link that
     * is "catching up" for a known reason ([reason], the runtime's
     * `linkDetail`: "No keepalive for 75s", or a queue that could not be
     * re-read). After the phone slept that socket is often half-dead, and it
     * would otherwise sit there until a 90 second read timeout noticed.
     *
     * A connection that has only just opened is also connected and not yet
     * trusted - for the few seconds its first read takes - but it has no
     * reason set (`onOpen` clears it). Forcing then would tear down a
     * healthy new connection, so a null [reason] never forces.
     *
     * False while a connection attempt is already under way
     * ([LinkState.RECONNECTING]) - forcing then would only throw that
     * attempt away. False when offline too, on purpose: that link is already
     * retrying on its own schedule, Home offers Retry for it, and whether the
     * link runs at all is the owner's choice (Checks, "Start link") - this
     * must not quietly start it on every return to the app.
     */
    fun reconnectOnReturn(link: LinkState, stale: Boolean, reason: String?): Boolean =
        link == LinkState.CONNECTED && stale && !reason.isNullOrBlank()
}
