package com.jarvis.client

import com.jarvis.client.voice.LiveMicGate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's microphone precheck before Jarvis Live starts (LM-3A; the Pixel
 * 9 failure of 2026-10-18 where RECORD_AUDIO was not granted and Live died
 * instantly with no explanation while the owner was away from adb).
 *
 * The decision is pure, so every branch runs on the JVM with no device: what
 * starts, what the card says, and which of the two honest routes is offered
 * (Android's own runtime ask where it would still show; the app's settings
 * page always, for a "don't ask again" / USER_SET).
 */
class LiveMicGateTest {
    @Test
    fun grantedStartsAndShowsNothing() {
        val d = LiveMicGate.decide(granted = true, rationale = false, askedBefore = true)
        assertTrue("a held permission starts Live", d.start)
        assertEquals("no banner", "", d.banner)
        assertFalse(d.offerAllow)
        assertFalse(d.offerSettings)
    }

    @Test
    fun missingWithRationaleOffersBothHonestRoutesAndDoesNotStart() {
        val d = LiveMicGate.decide(granted = false, rationale = true, askedBefore = false)
        assertFalse("a missing microphone never starts Live", d.start)
        assertEquals(LiveMicGate.NEED, d.banner)
        assertTrue("Android would still show the dialog", d.offerAllow)
        assertTrue("the settings page is always offered", d.offerSettings)
    }

    @Test
    fun neverAskedOffersTheRuntimeAskEvenWithoutRationale() {
        // Before the first ask Android's rationale is false too; that must not
        // be mistaken for "don't ask again" or the owner would see Settings only.
        val d = LiveMicGate.decide(granted = false, rationale = false, askedBefore = false)
        assertFalse(d.start)
        assertTrue(d.offerAllow)
        assertTrue(d.offerSettings)
    }

    @Test
    fun dontAskAgainOffersSettingsOnlyBecauseAllowWouldBeSilent() {
        val d = LiveMicGate.decide(granted = false, rationale = false, askedBefore = true)
        assertFalse(d.start)
        assertFalse("Android would not show the dialog", d.offerAllow)
        assertTrue("settings is the only route left", d.offerSettings)
        assertEquals(LiveMicGate.NEED, d.banner)
    }

    @Test
    fun autoRevokedPermissionIsTreatedExactlyLikeNeverGranted() {
        // Android 17 can auto-revoke while the app sits unused: the same start
        // reads the platform afresh, so the second answer is the missing one.
        val beforeRevoke = LiveMicGate.decide(granted = true, rationale = false, askedBefore = true)
        assertTrue(beforeRevoke.start)
        val afterRevoke = LiveMicGate.decide(granted = false, rationale = false, askedBefore = true)
        assertFalse("a revoked permission must not start Live", afterRevoke.start)
        assertEquals(LiveMicGate.NEED, afterRevoke.banner)
        assertTrue(afterRevoke.offerSettings)
    }

    @Test
    fun noCombinationStartsWithoutThePermission() {
        for (rationale in listOf(false, true)) {
            for (askedBefore in listOf(false, true)) {
                val d = LiveMicGate.decide(granted = false, rationale = rationale, askedBefore = askedBefore)
                assertFalse("started without the microphone ($rationale/$askedBefore)", d.start)
                assertEquals(LiveMicGate.NEED, d.banner)
                assertTrue("settings is always offered ($rationale/$askedBefore)", d.offerSettings)
            }
        }
    }

    @Test
    fun theWordsAreTheOnesTheCardShows() {
        assertEquals("Jarvis Live needs Microphone permission on this phone.", LiveMicGate.NEED)
        assertEquals("Allow microphone", LiveMicGate.ALLOW)
        assertEquals("Open app permission settings", LiveMicGate.OPEN_SETTINGS)
    }
}
