package com.jarvis.client.data

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
}
