package com.jarvis.client

import com.jarvis.client.net.PhoneNotifications
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The "Send test" button, now "Send test notification" on the phone's
 * Notifications card (Android audit 2026-10-08; moved 2026-10-10, parity audit
 * GAP 1-6): it reported success whatever happened, so it said the test had been
 * sent in exactly the state where `ScheduleNotifier.post` returns early and
 * every approval notification is dropped too.
 *
 * What this can hold: the words chosen for each answer, that the failure sends
 * the owner to a button that is really on that row, and that the CONTROL that
 * presses it lives in the card the desktop's own Test button belongs to
 * (`PcNotifyPlate.kt`) rather than in two places at once. What it cannot hold:
 * whether Compose draws them, or whether Android really posts a notification -
 * both need a device (no Android SDK, so CI's Gradle build is the first
 * compile).
 */
class PhoneNotificationsTest {

    private fun source(path: String): String = listOf(
        File("src/main/java/com/jarvis/client/ui/screens/$path"),
        File("app/src/main/java/com/jarvis/client/ui/screens/$path"),
    ).first { it.isFile }.readText()

    /** "Phone notifications": the phone's own alerts and Android's own screen. */
    private val plate: String = source("PhoneNotificationsPlate.kt")

    /** The PC's Notifications card on the phone, where the Test button now is. */
    private val card: String = source("PcNotifyPlate.kt")

    @Test
    fun theSuccessLineIsOnlyForANotificationThatWasReallyPosted() {
        assertTrue(PhoneNotifications.testWords(posted = true), PhoneNotifications.testWords(true).contains("sent"))
        // The refusal never reads as the success line, and never claims the
        // test went out.
        assertNotEquals(PhoneNotifications.TEST_SENT, PhoneNotifications.testWords(posted = false))
        assertTrue(PhoneNotifications.testWords(false).startsWith("Nothing was sent"))
        assertFalse(PhoneNotifications.testWords(false).contains(PhoneNotifications.TEST_SENT))
    }

    @Test
    fun theRefusalSaysWhatIsLostAndWhereToUnblockIt() {
        val blocked = PhoneNotifications.testWords(posted = false)
        // What it costs: the approval alerts rule 4 depends on, not only the
        // test notification.
        assertTrue(blocked.contains("approval alert"))
        // How to unblock it, naming the button that is really on this phone's
        // other notification row - the one that opens Android's own
        // app-notification settings, in "Phone notifications" above the card.
        assertTrue(blocked.contains("Android notification settings"))
        assertTrue(plate.contains("Android notification settings"))
        assertTrue(plate.contains("Settings.ACTION_APP_NOTIFICATION_SETTINGS"))
    }

    @Test
    fun thePlateCannotClaimSuccessOnItsOwn() {
        // It used to: `testSent = true` was set by the tap itself, and the
        // green literal lived here. Neither may come back - the posted answer
        // chooses the words - and the control that presses it is the card's,
        // once, not a second copy on the phone-notifications row.
        assertFalse("the card sets its own success flag again", card.contains("testSent"))
        assertTrue(card.contains("testPosted"))
        assertTrue(card.contains("testWords(posted)"))
        assertTrue("the card really posts on the phone", card.contains("ScheduleNotifier.post("))
        assertFalse("the old row must not keep its own copy of the button", plate.contains("testPosted"))
    }
}
