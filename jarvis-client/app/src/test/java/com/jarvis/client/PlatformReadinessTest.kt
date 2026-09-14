package com.jarvis.client

import com.jarvis.client.platform.PlatformReadiness
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pins the cleartext predicate against the network security config it claims to
 * mirror.
 *
 * `<domain includeSubdomains="true">ts.net</domain>` matches `ts.net` and labels
 * beneath it, and nothing else. The screen this feeds exists to make that policy
 * legible, so a predicate that disagrees with it is worse than no screen at all.
 */
class PlatformReadinessTest {

    @Test
    fun `tailscale magicdns names are permitted`() {
        assertTrue(PlatformReadiness.cleartextPermitted("desktop.tail1234.ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("desk.ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("localhost"))
        assertTrue(PlatformReadiness.cleartextPermitted("127.0.0.1"))
    }

    @Test
    fun `a suffix that is not a subdomain is refused`() {
        // These are registrable public domains. A bare "ts.net" entry tested with
        // endsWith reported them permitted.
        assertFalse(PlatformReadiness.cleartextPermitted("notmyts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("evilts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("mylocalhost"))
        assertFalse(PlatformReadiness.cleartextPermitted("not127.0.0.1"))
    }

    @Test
    fun `bare tailscale addresses are refused, because the config cannot express a CIDR range`() {
        assertFalse(PlatformReadiness.cleartextPermitted("100.64.0.1"))
        assertFalse(PlatformReadiness.cleartextPermitted("100.101.102.103"))
    }

    @Test
    fun `ports and stray slashes do not change the verdict`() {
        assertTrue(PlatformReadiness.cleartextPermitted("desk.ts.net:8080"))
        assertTrue(PlatformReadiness.cleartextPermitted("/desk.ts.net/"))
        assertTrue(PlatformReadiness.cleartextPermitted("  DESK.TS.NET  "))
        assertFalse(PlatformReadiness.cleartextPermitted(""))
        assertFalse(PlatformReadiness.cleartextPermitted("   "))
    }

    @Test
    fun `public hosts are refused`() {
        assertFalse(PlatformReadiness.cleartextPermitted("example.com"))
        assertFalse(PlatformReadiness.cleartextPermitted("jarvis.example.com"))
    }
}
