package com.jarvis.client.platform

/**
 * The two launderings the crash file gets before it can ever be read aloud or
 * pasted into a chat (apps security audit L5/L6):
 *
 *  - **scrub** removes the pairing token itself, the `X-Jarvis-Token` header
 *    however it appears, the per-device `jdk1.…` key shape, and a whole
 *    `http(s)://…` address (the desktop's name is private too). It is plain
 *    Kotlin so the JVM test can prove every rule.
 *  - **expire** keeps the file from becoming a permanent copy of an old crash
 *    and its context: older than [MAX_AGE_MS] (or an unreadable timestamp) is
 *    deleted when it is next read, rather than shown.
 *
 * [CrashLog] does the Android-file half around these; nothing here touches
 * `Context`, a file, or the Keystore.
 */
object CrashScrub {

    /** Fourteen days. A crash that old is being reported, not diagnosed. */
    const val MAX_AGE_MS: Long = 14L * 24 * 60 * 60 * 1000

    /** `X-Jarvis-Token: ...` however it appears in a trace or an OkHttp message. */
    private val TOKEN_HEADER =
        Regex("(X-Jarvis-Token[ :=]+)([A-Za-z0-9._~+/=-]+)", RegexOption.IGNORE_CASE)

    /** A whole web address, because its host is the owner's private PC. */
    private val URL = Regex("""https?://[^\s"'<>]+""", RegexOption.IGNORE_CASE)

    /**
     * [body] with every known secret and private address replaced. [token] is
     * the pairing token when it can be read; null/blank is fine - the header
     * and device-key shapes are still removed.
     */
    fun scrub(body: String, token: String?): String {
        var safe = if (!token.isNullOrBlank()) body.replace(token, "«token»") else body
        safe = TOKEN_HEADER.replace(safe, "$1«token»")
        safe = com.jarvis.client.net.DeviceKey.scrub(safe, "«token»")
        return URL.replace(safe, "«address»")
    }

    /**
     * Whether a crash file written at [writtenMs] must be deleted instead of
     * shown at [nowMs]. A clock that went backwards, or an unknown timestamp,
     * also counts as expired: the safe direction for a file that can quote a
     * chat or a stack trace.
     */
    fun isExpired(nowMs: Long, writtenMs: Long, maxAgeMs: Long = MAX_AGE_MS): Boolean =
        writtenMs <= 0L || nowMs < writtenMs || nowMs - writtenMs > maxAgeMs
}
