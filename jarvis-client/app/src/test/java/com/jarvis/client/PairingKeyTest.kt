package com.jarvis.client

import com.jarvis.client.data.PairingKey
import org.junit.Assert.assertEquals
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
}
