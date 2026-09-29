package com.jarvis.client

import com.jarvis.client.data.ScreenNever
import com.jarvis.client.data.ScreenNever.Why
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's "Never look at" list and the setting that lets the assistant
 * gesture read the screen (the owner's decision of 2026-09-28,
 * docs/SCREEN-DESIGN.md sections 3 and 4): what is refused whatever the owner
 * added, that turning the reading ON and taking an app OFF the list loosen
 * (and so ask for the fingerprint or PIN), and that adding and turning off
 * are instant.
 */
class ScreenNeverTest {

    @Test
    fun `Jarvis, password managers and bank-looking apps are never looked at`() {
        assertEquals(Why.JARVIS, ScreenNever.blocked("com.jarvis.client", emptySet()))
        assertEquals(Why.PASSWORD_MANAGER, ScreenNever.blocked("com.x8bit.bitwarden", emptySet()))
        assertEquals(Why.PASSWORD_MANAGER, ScreenNever.blocked("keepass2android.keepass2android", emptySet()))
        assertEquals(Why.BANKING, ScreenNever.blocked("com.chase.sig.android", emptySet()))
        assertEquals(Why.BANKING, ScreenNever.blocked("com.example.notabank", emptySet(), category = 6))
        assertEquals(Why.BANKING, ScreenNever.blocked("com.paypal.android.p2pmobile", emptySet()))
    }

    @Test
    fun `the owner's own apps are refused, and an ordinary app is not`() {
        assertEquals(Why.OWNER, ScreenNever.blocked("com.somechat.example", setOf("com.somechat.example")))
        assertNull(ScreenNever.blocked("com.android.chrome", setOf("com.somechat.example")))
        assertNull(ScreenNever.blocked("org.mozilla.firefox", emptySet()))
    }

    @Test
    fun `an app the system does not name is a pause, never a look`() {
        assertEquals(Why.UNKNOWN_APP, ScreenNever.blocked(null, emptySet()))
        assertEquals(Why.UNKNOWN_APP, ScreenNever.blocked("  ", emptySet()))
    }

    @Test
    fun `the sentence says why, in fixed words, never the app's name`() {
        for (why in Why.entries) {
            val said = ScreenNever.said(why)
            assertTrue(said.endsWith("so I'm not looking."))
            assertFalse(said.contains("com."))
        }
        assertEquals("That's a password manager, so I'm not looking.", ScreenNever.said(Why.PASSWORD_MANAGER))
    }

    @Test
    fun `the list is stored as plain package names, only valid ones`() {
        val stored = ScreenNever.toStored(setOf("com.b.app", "com.a.app", "not a package", "x"))
        assertEquals("com.a.app,com.b.app", stored)
        assertEquals(setOf("com.a.app", "com.b.app"), ScreenNever.fromStored(stored))
        assertEquals(emptySet<String>(), ScreenNever.fromStored(null))
        assertEquals(emptySet<String>(), ScreenNever.fromStored("garbage, , 12,\n"))
        val many = (1..500).joinToString(",") { "com.app$it.x" }
        assertEquals(ScreenNever.MAX_APPS, ScreenNever.fromStored(many).size)
    }

    @Test
    fun `reading the screen is off by default, and turning it on or taking an app off asks`() {
        assertFalse(Security().screenRead)
        assertTrue(Security().neverApps.isEmpty())
        val on = Security(screenRead = true)
        assertTrue("turning it on loosens", SecurityRules.loosens(Security(), on))
        assertFalse("turning it off is instant", SecurityRules.loosens(on, Security()))
        val two = Security(neverApps = setOf("com.a.app", "com.b.app"))
        assertFalse("adding an app is instant", SecurityRules.loosens(Security(), two))
        assertTrue("taking one off loosens", SecurityRules.loosens(two, Security(neverApps = setOf("com.a.app"))))
        assertTrue("taking all off loosens", SecurityRules.loosens(two, Security()))
        assertFalse("the same list is no change", SecurityRules.loosens(two, two.copy()))
    }

    @Test
    fun `both settings are saved and come back, and a broken value reads as the stricter one`() {
        val s = Security(screenRead = true, neverApps = setOf("com.a.app"))
        val stored = SecurityRules.toStored(s)
        assertEquals("true", stored[SecurityRules.KEY_SCREEN_READ])
        assertEquals("com.a.app", stored[SecurityRules.KEY_NEVER_APPS])
        val back = SecurityRules.fromStored { stored[it] }
        assertTrue(back.screenRead)
        assertEquals(setOf("com.a.app"), back.neverApps)
        assertFalse(SecurityRules.fromStored { null }.screenRead)
        assertFalse(SecurityRules.fromStored { if (it == SecurityRules.KEY_SCREEN_READ) "maybe" else null }.screenRead)
    }
}
