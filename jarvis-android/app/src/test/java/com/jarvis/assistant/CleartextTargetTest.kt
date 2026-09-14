package com.jarvis.assistant

import com.jarvis.assistant.data.JarvisSettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pins the plaintext-target guard.
 *
 * Android's network security config cannot express 100.64.0.0/10, so this check
 * is the only thing standing between a mistyped address and the bearer token,
 * every approval and the microphone uplink going to a public host in the clear.
 * It is worth testing adversarially rather than only for the happy path.
 */
class CleartextTargetTest {

    @Test
    fun `userinfo cannot masquerade as the host`() {
        // The authority is 100.64.0.1:8080@evil.com. Splitting on ':' before '@'
        // reads the userinfo as the host and waves a public target through, while
        // OkHttp dials evil.com.
        assertEquals("evil.com", JarvisSettings.hostOf("ws://100.64.0.1:8080@evil.com/api/mobile/ws"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://100.64.0.1:8080@evil.com/api/mobile/ws"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://desktop.ts.net@evil.com/api/mobile/ws"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://10.0.0.1@evil.com/"))
    }

    @Test
    fun `private targets are still permitted`() {
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://100.64.0.1:4719/api/mobile/ws"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://100.127.255.254/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://10.0.0.5:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://192.168.1.20:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://172.16.0.1/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://127.0.0.1:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://localhost:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://desktop.tail1234.ts.net/api/mobile/ws"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://desktop.local/"))
    }

    @Test
    fun `public and near-miss targets are refused`() {
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://example.com/"))
        // Suffix matching without the dot: these are registrable public domains.
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://notmyts.net/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://ts.net/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://evil-local/"))
        // Outside the CGNAT block, which is 100.64/10 and not all of 100/8.
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://100.128.0.1/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://100.63.255.255/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://172.32.0.1/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://11.0.0.1/"))
    }

    @Test
    fun `tls targets are always permitted`() {
        assertTrue(JarvisSettings.isCleartextTargetPrivate("wss://example.com/api/mobile/ws"))
    }

    @Test
    fun `an unparseable target fails closed`() {
        assertNull(JarvisSettings.hostOf("not a url"))
        assertNull(JarvisSettings.hostOf("ws://"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws:// spaces /"))
    }

    @Test
    fun `ipv6 literals keep their brackets out of the host`() {
        assertEquals("::1", JarvisSettings.hostOf("ws://[::1]:4719/api/mobile/ws"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://[::1]:4719/api/mobile/ws"))
    }

    @Test
    fun `normalization appends the endpoint path only when absent`() {
        assertEquals(
            "ws://100.64.0.1:4719/api/mobile/ws",
            JarvisSettings.normalizeToWebSocketUrl("100.64.0.1:4719"),
        )
        assertEquals(
            "wss://desk.ts.net/api/mobile/ws",
            JarvisSettings.normalizeToWebSocketUrl("https://desk.ts.net"),
        )
        assertEquals(
            "ws://desk.ts.net/custom",
            JarvisSettings.normalizeToWebSocketUrl("ws://desk.ts.net/custom"),
        )
    }
}
