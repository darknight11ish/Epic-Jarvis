package com.jarvis.client

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

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

    /**
     * The extra line under a link that is down when this phone has no VPN
     * running at all (phone walk-through N1, 2026-09-27). The phone reaches
     * the PC only through Tailscale or NordVPN Meshnet, and both run as a
     * VPN on the phone - so "no VPN at all" is the most common reason the
     * link is down, and the one the owner can fix in one tap.
     */
    const val VPN_OFF = "Tailscale (or Meshnet) is off on this phone"

    /**
     * [VPN_OFF] when it is worth saying, else null. All three must hold:
     *
     * - the link is not up. A connected link is proof enough; the line never
     *   argues with it.
     * - [vpnUp] is false: Android said this phone's default network has no
     *   VPN on it (NetworkCapabilities.TRANSPORT_VPN). Null - not known yet,
     *   or no network at all - says nothing, because "Tailscale is off" on a
     *   phone in flight mode would send the owner to the wrong fix.
     * - the saved address [host] is a Tailscale or Meshnet one (a `.ts.net`
     *   or `.nord` name, or a 100.64.0.0/10 number). An address the phone can
     *   reach without either - `localhost` on the test emulator - never gets
     *   the line.
     *
     * Only a hint. Another VPN app being on hides it (the phone cannot tell
     * whose VPN it is), which is the safe direction to be wrong in.
     */
    fun vpnOffLine(host: String, link: LinkState, vpnUp: Boolean?): String? {
        if (link == LinkState.CONNECTED || vpnUp != false) return null
        return if (meshAddress(host)) VPN_OFF else null
    }

    /** Whether [raw] (the address as saved) is reached through Tailscale or Meshnet. */
    internal fun meshAddress(raw: String): Boolean {
        val base = com.jarvis.client.data.BaseUrl.normalise(raw) ?: return false
        val host = runCatching { base.toHttpUrlOrNull()?.host }.getOrNull()
            ?.lowercase()?.trimEnd('.') ?: return false
        if (host.endsWith(".ts.net") || host.endsWith(".nord")) return true
        val parts = host.split('.')
        if (parts.size != 4) return false
        val n = parts.map { it.toIntOrNull() ?: -1 }
        return n[0] == 100 && n[1] in 64..127 && n[2] in 0..255 && n[3] in 0..255
    }

    /**
     * What the network watch ([com.jarvis.client.platform.NetworkWatch]) saw
     * last, and whether a new report from Android is a real change of
     * network - Wi-Fi to mobile data, Tailscale switched on or off - that
     * should replace the connection at once instead of waiting for it to
     * time out.
     *
     * [handle] is Android's number for the phone's default network (null:
     * none yet). [transports] are its kinds - Wi-Fi, mobile, VPN... - or null
     * until Android has said. Kinds matter because under a VPN that is always
     * on, the default network stays the same VPN while what it runs over
     * changes, and Android reports that as new kinds, not a new network.
     * [lost]: Android said the network went away and nothing has replaced it.
     */
    data class NetworkSeen(val handle: Long?, val transports: Set<Int>?, val lost: Boolean = false) {

        /**
         * Whether a report about network [handle] (with its [kinds], when the
         * report carries them) is a change. The report Android sends as soon
         * as the watch starts - about the network the phone already has - is
         * not one: it matches what was seen when the watch started. A network
         * coming back after being lost is one, even under the same number.
         */
        fun changedBy(handle: Long, kinds: Set<Int>?): Boolean =
            lost || handle != this.handle ||
                (kinds != null && transports != null && kinds != transports)

        /** What is seen after that report. A new network's kinds start fresh. */
        fun after(handle: Long, kinds: Set<Int>?): NetworkSeen =
            NetworkSeen(handle, if (handle == this.handle) kinds ?: transports else kinds, lost = false)

        /** After Android said network [handle] was lost; another network's loss changes nothing. */
        fun lostNetwork(handle: Long): NetworkSeen = if (handle == this.handle) copy(lost = true) else this
    }
}
