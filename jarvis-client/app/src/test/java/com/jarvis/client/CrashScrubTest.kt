package com.jarvis.client

import com.jarvis.client.platform.CrashScrub
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The crash file's two safety rules (apps security audit L5/L6): what it may
 * never carry, and how long it is kept. Pure Kotlin, so this runs without a
 * device (platform/CrashScrub.kt; CrashLog.kt only adds the Android file half).
 */
class CrashScrubTest {

    private val token = "Zk3qN8xYv2Lr9Tt6Wm1Hc4-_abcdefghijklmnopqrs"

    @Test
    fun `the pairing token is never in the trace`() {
        val body = "java.io.IOException: bad answer for $token at desk.nord:4719"
        val safe = CrashScrub.scrub(body, token)
        assertFalse(safe, token in safe)
        assertTrue(safe, "«token»" in safe)
    }

    @Test
    fun `the header and the per-device key shape are scrubbed even without the token`() {
        val key = "jdk1.d0123abcd." + "A".repeat(43)
        val body = "X-Jarvis-Token: $token\nkey=$key\nok"
        val safe = CrashScrub.scrub(body, null)
        assertFalse(safe, token in safe)
        assertFalse(safe, key in safe)
        assertTrue(safe, "X-Jarvis-Token: «token»" in safe)
        assertTrue(safe, "ok" in safe)
    }

    @Test
    fun `a web address is scrubbed because its host is the owner's private PC`() {
        val body = "GET http://desk.nord:4719/api/version failed\nhttps://desktop.tail1234.ts.net/x"
        val safe = CrashScrub.scrub(body, null)
        assertFalse(safe, "desk.nord" in safe)
        assertFalse(safe, "desktop.tail1234.ts.net" in safe)
        assertTrue(safe, "«address»" in safe)
        // The rest of the line is still useful.
        assertTrue(safe, "GET " in safe)
        assertTrue(safe, "failed" in safe)
    }

    @Test
    fun `nothing private is left in a normal-looking fixture`() {
        val body = """
            Jarvis client crashed at 2026-10-18 12:00:00
            version: 1.0 (12)
            thread: main
            java.io.IOException: unexpected end of stream
                at com.jarvis.client.net.JarvisApi.call(JarvisApi.kt:100)
        """.trimIndent()
        val safe = CrashScrub.scrub(body, null)
        assertEquals(body, safe)
    }

    @Test
    fun `a crash file expires after fourteen days`() {
        val now = 1_760_000_000_000L
        assertFalse(CrashScrub.isExpired(now, now - 13L * 24 * 60 * 60 * 1000))
        assertFalse(CrashScrub.isExpired(now, now - CrashScrub.MAX_AGE_MS))
        assertTrue(CrashScrub.isExpired(now, now - CrashScrub.MAX_AGE_MS - 1))
    }

    @Test
    fun `an unknown or backwards clock counts as expired - the safe direction`() {
        assertTrue(CrashScrub.isExpired(1_760_000_000_000L, 0L))
        assertTrue(CrashScrub.isExpired(1_760_000_000_000L, 1_760_000_000_001L))
        // And the boundary is exactly the stated age, not one millisecond less.
        assertEquals(14L * 24 * 60 * 60 * 1000, CrashScrub.MAX_AGE_MS)
    }
}
