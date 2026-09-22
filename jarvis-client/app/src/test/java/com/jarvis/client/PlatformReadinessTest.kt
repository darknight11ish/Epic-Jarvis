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
 * beneath it, and nothing else. `nord` is the same rule for NordVPN Meshnet's
 * own Nord Name. The screen this feeds exists to make that policy legible, so a
 * predicate that disagrees with it is worse than no screen at all.
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
    fun `nordvpn meshnet nord names are permitted`() {
        assertTrue(PlatformReadiness.cleartextPermitted("secret.meerkat-andes.nord"))
        assertTrue(PlatformReadiness.cleartextPermitted("desk.nord"))
        assertTrue(PlatformReadiness.cleartextPermitted("nord"))
    }

    @Test
    fun `a suffix that is not a subdomain is refused`() {
        // These are registrable public domains. A bare "ts.net" entry tested with
        // endsWith reported them permitted.
        assertFalse(PlatformReadiness.cleartextPermitted("notmyts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("evilts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("mylocalhost"))
        assertFalse(PlatformReadiness.cleartextPermitted("not127.0.0.1"))
        // Same shape of false positive, for the newer suffix: "mynord.com" and
        // "anordable.net" contain "nord" but are not the "nord" TLD or a label
        // beneath it.
        assertFalse(PlatformReadiness.cleartextPermitted("mynord.com"))
        assertFalse(PlatformReadiness.cleartextPermitted("anordable.net"))
    }

    @Test
    fun `bare mesh addresses are refused, because the config cannot express a CIDR range`() {
        // Tailscale and NordVPN Meshnet both hand out addresses from the same
        // CGNAT block, so one pair of cases covers both products.
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

    /**
     * The form the pairing screen's own helper text produces, and the one that
     * was reported as a problem when it is not one.
     *
     * `ClientSettings.baseUrl()` accepts a host with the scheme already typed
     * in. The old check took `substringBefore(':')`, which reduced
     * `http://desktop.ts.net:4719` to the string `"http"` — so the readiness
     * screen told the owner their perfectly good MagicDNS name was NOT
     * permitted in cleartext, and to go and find the MagicDNS name they had
     * just typed. A false alarm on the one screen that exists to stop people
     * chasing network faults that are really policy.
     */
    @Test
    fun `a host with the scheme typed in is still permitted`() {
        assertTrue(PlatformReadiness.cleartextPermitted("http://desktop.tail1234.ts.net:4719"))
        assertTrue(PlatformReadiness.cleartextPermitted("http://desk.ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("HTTP://Desk.TS.NET"))
        assertTrue(PlatformReadiness.cleartextPermitted("desktop.tail1234.ts.net:4719"))
    }

    /** https is not cleartext, so the policy does not apply and must not warn. */
    @Test
    fun `https never warns about cleartext`() {
        assertTrue(PlatformReadiness.cleartextPermitted("https://desktop.tail1234.ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("https://example.com"))
    }

    /**
     * The shape of the other app's worst bug, in the check that cites it.
     *
     * OkHttp parses `foo.ts.net:8080@evil.com` as userinfo plus the host
     * `evil.com`, and `evil.com/foo.ts.net` as `evil.com` with a path. Splitting
     * on the first colon saw `.ts.net` in both and reported permitted. The
     * platform would still refuse the connection, so this failed safe — but the
     * screen was stating the opposite of the truth about where the request goes.
     */
    @Test
    fun `userinfo and path cannot smuggle a permitted name past the check`() {
        assertFalse(PlatformReadiness.cleartextPermitted("foo.ts.net:8080@evil.com"))
        assertFalse(PlatformReadiness.cleartextPermitted("http://foo.ts.net:8080@evil.com"))
        assertFalse(PlatformReadiness.cleartextPermitted("evil.com/foo.ts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("http://evil.com/foo.ts.net"))
    }

    /** Nonsense must be refused rather than throwing or being waved through. */
    @Test
    fun `unparseable input is refused`() {
        assertFalse(PlatformReadiness.cleartextPermitted(""))
        assertFalse(PlatformReadiness.cleartextPermitted("   "))
        assertFalse(PlatformReadiness.cleartextPermitted("::::"))
        assertFalse(PlatformReadiness.cleartextPermitted("http://"))
    }
}
