package com.jarvis.client

import com.jarvis.client.data.PairingKey
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The token typed on the phone, as the desktop shows it (data/PairingKey.kt). */
class PairingKeyTest {

    @Test
    fun `the desktop's groups of four are typed without their spaces`() {
        assertEquals(
            "abcdEFGH12-_wxyz",
            PairingKey.clean("abcd EFGH 12-_ wxyz"),
        )
    }

    @Test
    fun `tabs, line breaks and a stray space at either end go too`() {
        assertEquals("abcdefgh", PairingKey.clean(" abcd\tefgh\n"))
    }

    @Test
    fun `a token typed without spaces is left exactly as it is`() {
        val raw = "Zk3qN8xYv2Lr9Tt6Wm1Hc4-_abcdefghijklmnopqrs"
        assertEquals(raw, PairingKey.clean(raw))
    }

    @Test
    fun `a blank field stays blank, so a stored token is kept`() {
        assertEquals("", PairingKey.clean("   "))
    }

    // ------------------------------------------------ the changed address ----
    // M11: a stored device key belongs to ONE desktop. A re-pair to a different
    // host with the token field blank must ask for a fresh token.

    @Test
    fun `the same desktop is recognised through its default port and a slash`() {
        assertTrue(PairingKey.sameDesktop("desk.nord", "desk.nord:4719"))
        assertTrue(PairingKey.sameDesktop("desk.nord:4719", "DESK.nord:4719/"))
        assertTrue(
            PairingKey.sameDesktop(
                "desktop.tail1234.ts.net",
                "desktop.tail1234.ts.net:4719/",
            ),
        )
    }

    @Test
    fun `a different host is a different desktop`() {
        assertFalse(PairingKey.sameDesktop("desk.nord", "other.nord"))
        assertFalse(PairingKey.sameDesktop("desk.tail1234.ts.net", "desk.nord"))
        assertFalse(PairingKey.sameDesktop("desk.nord:4719", "desk.nord:9999"))
        // Nothing saved yet, or an address that cannot be parsed, is never
        // treated as "the same" - the safe direction.
        assertFalse(PairingKey.sameDesktop("", "desk.nord"))
        assertFalse(PairingKey.sameDesktop("desk.nord", ""))
        assertFalse(PairingKey.sameDesktop(":::", "desk.nord"))
    }

    @Test
    fun `a stored token is only reused for the desktop it was paired with`() {
        // Same address: blank token is allowed to keep the stored one.
        assertFalse(PairingKey.freshTokenRequired(hasToken = true, "desk.nord", "desk.nord:4719"))
        // Address changed: a freshly typed token is required.
        assertTrue(PairingKey.freshTokenRequired(hasToken = true, "desk.nord", "other.nord"))
        // Nothing stored: there is nothing to reuse, so this rule is silent and
        // the screen's normal "a token is required" state applies.
        assertFalse(PairingKey.freshTokenRequired(hasToken = false, "", "other.nord"))
        // The refusal sentence says what to do.
        assertTrue(PairingKey.FRESH_TOKEN_REQUIRED.startsWith("The desktop's address changed"))
        assertTrue(PairingKey.FRESH_TOKEN_REQUIRED.contains("type its token again"))
    }
}
