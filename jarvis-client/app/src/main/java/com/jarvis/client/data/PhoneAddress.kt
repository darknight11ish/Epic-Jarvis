package com.jarvis.client.data

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Can THIS PHONE use the saved desktop address? Two checks, and both must
 * pass before anything is sent (docs/ARCHITECTURE.md §2, "Which addresses
 * the phone can use"):
 *
 * 1. [OwnNetwork] - the backend's own rule, shared with the desktop: this
 *    PC, the home network, Tailscale or NordVPN Meshnet, never the open
 *    internet.
 * 2. Android's own list of names this app may send plain http:// to,
 *    `res/xml/network_security_config.xml`. An address that passes (1) but
 *    is not on that list - a home-network number like 192.168.1.20, a
 *    `.local` name, or a Tailscale/Meshnet number like 100.64.1.5 - is
 *    refused HERE, up front, in [MESSAGE], which says to type the PC's
 *    Tailscale or Meshnet name instead.
 *
 * Before this check the app accepted such an address, OkHttp then refused
 * every request ("CLEARTEXT communication ... not permitted by network
 * security policy"), and the owner was told "The connection to your PC
 * dropped. Try again." - untrue, and trying again could never work.
 *
 * This does not loosen anything. The config file still decides on its own,
 * inside OkHttp, for every request; this only makes the app's judgment
 * agree with it, so the two never disagree about what is sent. Why the
 * config is not widened to take those addresses is written at the top of
 * the config file and in ARCHITECTURE.md §2 (in short: the PC's Jarvis only
 * listens on its Tailscale/Meshnet address, and on a phone that moves
 * between networks a number or a `.local` name can reach a stranger's
 * device, where a mesh name cannot).
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object PhoneAddress {

    /**
     * Every `<domain>` in network_security_config.xml's one
     * `cleartextTrafficPermitted="true"` block, as (name, includeSubdomains).
     * [PhoneAddressTest] reads the real XML file and fails when this list and
     * the file differ, so it cannot be "kept in step by hand" and drift.
     */
    internal val CLEARTEXT_DOMAINS: List<Pair<String, Boolean>> = listOf(
        "ts.net" to true,
        "nord" to true,
        "localhost" to true,
        "127.0.0.1" to false,
    )

    /**
     * What the owner sees when an address on their own network cannot be used
     * from this phone - one sentence, like [OwnNetwork.MESSAGE]. `{address}`
     * is the address as saved.
     */
    const val MESSAGE =
        "Jarvis's address {address} is on your own network, but this phone can only reach " +
            "your PC by its Tailscale name (ending in .ts.net) or its NordVPN Meshnet name " +
            "(ending in .nord), not by a number or a home-network name: type the name the " +
            "Tailscale or NordVPN app shows for your PC."

    /**
     * Null when this phone may use [base] (a whole address with its scheme,
     * as [BaseUrl.normalise] makes it), else the one sentence saying why not:
     * [OwnNetwork]'s when it is off the owner's own networks, [MESSAGE] when
     * it is on them but Android would refuse plain http:// to it.
     */
    fun problem(base: String): String? = OwnNetwork.problem(base) ?: cleartextProblem(base)

    /**
     * [MESSAGE] for an http:// address whose host the config file does not
     * list. https:// is not plain http://, so the config's cleartext rule
     * does not apply to it (the same answer [com.jarvis.client.platform.PlatformReadiness]
     * gives).
     *
     * The host is the one OkHttp parses - exactly the string OkHttp hands to
     * Android's `NetworkSecurityPolicy.isCleartextTrafficPermitted` before it
     * opens a plain connection (OkHttp 4.12, `RealConnection.connect`:
     * `route.address.url.host`). An address OkHttp cannot parse is refused.
     */
    internal fun cleartextProblem(base: String): String? {
        val b = base.trim().trimEnd('/')
        val url = runCatching { b.toHttpUrlOrNull() }.getOrNull() ?: return message(b)
        if (url.isHttps) return null
        return if (cleartextPermitted(url.host)) null else message(b)
    }

    /**
     * Would network_security_config.xml let this app send plain http:// to
     * [host]? The matching Android itself does (AOSP
     * `android.security.net.config.ApplicationConfig.getConfigForHostname`):
     * lower case, one trailing dot dropped, then either the exact name or -
     * where includeSubdomains is on - a name ending in "." plus it. Plain
     * text only: no address ranges, no wildcards, nothing looked up.
     */
    fun cleartextPermitted(host: String): Boolean {
        var h = host.trim().lowercase()
        if (h.isEmpty() || h.startsWith(".")) return false
        if (h.endsWith(".")) h = h.dropLast(1)
        if (h.isEmpty()) return false
        return CLEARTEXT_DOMAINS.any { (domain, subdomains) ->
            h == domain || (subdomains && h.endsWith(".$domain"))
        }
    }

    /**
     * [MESSAGE] for [base], shown as written - unless it holds something that
     * must not be repeated back (a user name or password, a space), the same
     * rule as [OwnNetwork.message].
     */
    fun message(base: String): String {
        val unshown = base.isEmpty() || base.any { it == '@' || it.isWhitespace() || it.isISOControl() }
        return if (unshown) MESSAGE.replace("{address} ", "") else MESSAGE.replace("{address}", base)
    }
}
