package com.jarvis.client

import com.jarvis.client.data.NotificationAllowList
import com.jarvis.client.data.NotificationAllowList.AddResult
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `data/NotificationAllowList.kt` - the empty-by-default per-app list, and
 * the one place a banking or SMS/Messages app is refused outright
 * (CLAUDE.md: "only apps the owner chooses (never banking)"; "Never text
 * messages (SMS)... even if the owner tries to add the Messages app").
 * Pure logic, no Android import, so this needs no device or emulator.
 */
class NotificationAllowListTest {

    // --------------------------------------------------------------- banking

    @Test
    fun `a well-known banking package name is refused`() {
        for (pkg in listOf(
            "com.chase.sig.android",
            "com.paypal.android.p2pmobile",
            "com.coinbase.android",
            "com.wf.wellsfargomobile",
            "com.konylabs.capitalone",
        )) {
            assertTrue(pkg, NotificationAllowList.looksLikeBanking(pkg))
        }
    }

    @Test
    fun `the play store CATEGORY_FINANCE flag alone is enough, whatever the name is`() {
        assertTrue(
            NotificationAllowList.looksLikeBanking(
                "com.example.totallyordinaryname",
                category = NotificationAllowList.CATEGORY_FINANCE,
            ),
        )
    }

    @Test
    fun `an ordinary app with no finance category and no matching name is not banking`() {
        assertFalse(NotificationAllowList.looksLikeBanking("com.whatsapp"))
        assertFalse(NotificationAllowList.looksLikeBanking("com.spotify.music"))
    }

    @Test
    fun `the banking check is case-insensitive`() {
        assertTrue(NotificationAllowList.looksLikeBanking("com.CHASE.mobile"))
    }

    @Test
    fun `honestly, a bank not on the list and not categorised is not caught - the documented limit`() {
        // This is the class doc's own admitted gap, proved rather than
        // merely claimed: a small regional bank's package, whose name
        // matches nothing on the curated list and declares no store
        // category, is NOT refused by this half of the check.
        assertFalse(NotificationAllowList.looksLikeBanking("com.regionalcu.mobileapp"))
    }

    // --------------------------------------------------------------- SMS

    @Test
    fun `known default SMS apps are refused by the static list alone`() {
        for (pkg in listOf(
            "com.google.android.apps.messaging",
            "com.android.mms",
            "com.samsung.android.messaging",
        )) {
            assertTrue(pkg, NotificationAllowList.isSmsPackage(pkg))
        }
    }

    @Test
    fun `whatever the OS reports as the SMS role holder is refused, name unknown to the static list`() {
        val obscureOemMessagingApp = "com.somefork.oem.textmessenger"
        assertFalse(NotificationAllowList.isSmsPackage(obscureOemMessagingApp)) // not on the static list alone
        assertTrue(
            NotificationAllowList.isSmsPackage(obscureOemMessagingApp, smsRoleHolders = setOf(obscureOemMessagingApp)),
        )
    }

    @Test
    fun `an ordinary chat app is not treated as SMS`() {
        assertFalse(NotificationAllowList.isSmsPackage("com.whatsapp"))
        assertFalse(NotificationAllowList.isSmsPackage("com.slack"))
    }

    // --------------------------------------------------------------- evaluateAdd

    @Test
    fun `an ordinary app not already on the list is added`() {
        val r = NotificationAllowList.evaluateAdd("com.whatsapp", current = emptySet())
        assertEquals(AddResult.Added("com.whatsapp"), r)
    }

    @Test
    fun `a banking app is blocked, never added`() {
        val r = NotificationAllowList.evaluateAdd("com.chase.sig.android", current = emptySet())
        assertEquals(AddResult.BlockedBanking("com.chase.sig.android"), r)
    }

    @Test
    fun `an sms app is blocked, never added, even with a finance category set (sms wins)`() {
        val r = NotificationAllowList.evaluateAdd(
            "com.android.mms",
            current = emptySet(),
            category = NotificationAllowList.CATEGORY_FINANCE,
        )
        assertEquals(AddResult.BlockedSms("com.android.mms"), r)
    }

    @Test
    fun `sms is checked before banking - the stricter rule wins when both could apply`() {
        // A package that is BOTH the SMS role holder AND looks like a bank by
        // name: CLAUDE.md's hard SMS rule must not be softened by the banking
        // branch running first and returning a different (still-blocked, but
        // differently worded) result.
        val pkg = "com.somebank.messaging"
        val r = NotificationAllowList.evaluateAdd(pkg, current = emptySet(), smsRoleHolders = setOf(pkg))
        assertEquals(AddResult.BlockedSms(pkg), r)
    }

    @Test
    fun `an app already on the list is reported as already added, not added twice`() {
        val r = NotificationAllowList.evaluateAdd("com.whatsapp", current = setOf("com.whatsapp"))
        assertEquals(AddResult.AlreadyAdded("com.whatsapp"), r)
    }

    @Test
    fun `the current list is untouched by evaluateAdd itself - it only says what WOULD happen`() {
        val current = setOf("com.whatsapp")
        NotificationAllowList.evaluateAdd("com.slack", current = current)
        assertEquals(setOf("com.whatsapp"), current)
    }
}
