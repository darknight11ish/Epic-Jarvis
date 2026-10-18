package com.jarvis.client.data

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * The pairing token as the owner types it, made ready to store.
 *
 * The desktop shows the token in groups of four ("abcd efgh ...") so it is
 * easier to read out and type (ease-of-use audit #18, `settings.js`
 * `groupInFours`). Those spaces are display only: a real token is
 * `secrets.token_urlsafe(32)` - letters, digits, `-` and `_`, never a space.
 * Typing exactly what the PC shows used to store the spaces too, and the PC
 * then refused the token with no hint why (studio newcomer play test,
 * 2026-09-27). So every space, tab or line break is dropped here.
 */
object PairingKey {
    fun clean(typed: String): String = typed.filterNot { it.isWhitespace() }

    /**
     * What the owner is told when a re-pair points at a DIFFERENT desktop with
     * the token field left blank. A stored token belongs to the desktop it was
     * paired with; sending it to another host would hand that host the old
     * device key. One plain sentence, shown beside the token box and used as
     * the refusal if a caller slips past the screen.
     */
    const val FRESH_TOKEN_REQUIRED =
        "The desktop's address changed, so type its token again. A stored token is used only " +
            "for the desktop it was paired with."

    /**
     * True when [savedHost] and [typedHost] name the same desktop address.
     *
     * Both go through [BaseUrl.normalise], so "desk.nord" and "DESK.nord:4719/"
     * are the same address (the default port and a trailing slash are not a
     * change). An empty or unparseable side is never the same - the safe
     * direction, because the caller may then still ask for a fresh token.
     */
    fun sameDesktop(savedHost: String, typedHost: String): Boolean {
        val saved = addressKey(savedHost) ?: return false
        val typed = addressKey(typedHost) ?: return false
        return saved == typed
    }

    /**
     * One desktop address reduced to scheme + lower-case host + port + path.
     * [BaseUrl.normalise] fills in Jarvis's default port and trims a trailing
     * slash; OkHttp then lower-cases the host and gives us the port as a
     * number, so "DESK.nord:4719/" and "desk.nord" are the same key.
     */
    private fun addressKey(raw: String): String? {
        val url = BaseUrl.normalise(raw)?.toHttpUrlOrNull() ?: return null
        return "${url.scheme}://${url.host}:${url.port}${url.encodedPath.trimEnd('/')}"
    }

    /**
     * True when the owner must type a token before Connect: a token is stored
     * and the address is not the one it was paired with. A blank field must
     * never reuse the stored device key for a changed host.
     */
    fun freshTokenRequired(hasToken: Boolean, savedHost: String, typedHost: String): Boolean =
        hasToken && !sameDesktop(savedHost, typedHost)
}
