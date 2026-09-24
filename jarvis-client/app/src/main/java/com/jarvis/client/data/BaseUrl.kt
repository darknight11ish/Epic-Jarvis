package com.jarvis.client.data

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * What the owner typed as the desktop's address, made into the base URL every
 * request is built from.
 *
 * **A bare name now gets Jarvis's port.** `marioirelan11-alps.nord` used to
 * become `http://marioirelan11-alps.nord` - port 80, where nothing listens -
 * with no warning, and the pairing screen's Meshnet hint did not even mention
 * `:4719`. The backend's port is 4719 unless someone changed it
 * (`JARVIS_HUD_PORT`, the desktop's `DEFAULT_BASE`), so an address with no
 * port gets 4719. A port the owner typed is always kept.
 *
 * Only for plain `http` (and a bare name, which is http): an `https://`
 * address with no port means 443 on purpose - something in front of Jarvis
 * is answering there - and is left alone.
 *
 * The host always comes from OkHttp's own parser, the one the request uses
 * (see [com.jarvis.client.platform.PlatformReadiness]'s note on why
 * hand-splitting URLs went wrong four times). The only thing read by hand is
 * whether a port was written at all, because a parsed URL cannot say.
 */
object BaseUrl {
    /** `JARVIS_HUD_PORT`'s default in jarvis_hud.py, and the desktop's. */
    const val DEFAULT_PORT = 4719

    fun normalise(raw: String): String? {
        val t = raw.trim().trimEnd('/')
        if (t.isEmpty()) return null
        val https = t.startsWith("https://", ignoreCase = true)
        val hasScheme = https || t.startsWith("http://", ignoreCase = true)
        val withScheme = if (hasScheme) t else "http://$t"
        // Unparseable: pass it through as before and let the request fail
        // with its own, specific error.
        val url = withScheme.toHttpUrlOrNull() ?: return withScheme
        if (https || hasExplicitPort(withScheme)) return withScheme
        return url.newBuilder().port(DEFAULT_PORT).build().toString().trimEnd('/')
    }

    /** Whether the address names a port, e.g. `name.nord:4719` or `[fd7a::1]:4719`. */
    internal fun hasExplicitPort(withScheme: String): Boolean {
        val authority = withScheme.substringAfter("://")
            .takeWhile { it != '/' && it != '?' && it != '#' }
            .substringAfterLast('@')
        return if (authority.startsWith("[")) {
            authority.substringAfter("]").startsWith(":")
        } else {
            authority.contains(':')
        }
    }
}
