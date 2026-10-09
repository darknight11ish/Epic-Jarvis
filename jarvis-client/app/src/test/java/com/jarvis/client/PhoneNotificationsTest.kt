package com.jarvis.client

import com.jarvis.client.net.PhoneNotifications
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The "Send test" button on Settings -> Phone notifications (Android audit
 * 2026-10-08): it reported success whatever happened, so it said the test had
 * been sent in exactly the state where `ScheduleNotifier.post` returns early
 * and every approval notification is dropped too.
 *
 * What this can hold: the words chosen for each answer, and that the failure
 * sends the owner to a button that is really on that row. What it cannot
 * hold: whether Compose draws them, or whether Android really posts a
 * notification - both need a device (no Android SDK, so CI's Gradle build is
 * the first compile). The Kotlin half of the fix is one expression in
 * `PhoneNotificationsPlate.kt`, and this file pins the shape of it.
 */
class PhoneNotificationsTest {

    private val plate: String = listOf(
        File("src/main/java/com/jarvis/client/ui/screens/PhoneNotificationsPlate.kt"),
        File("app/src/main/java/com/jarvis/client/ui/screens/PhoneNotificationsPlate.kt"),
    ).first { it.isFile }.readText()

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
        // How to unblock it, naming the button that is really on this row -
        // the one that opens Android's own app-notification settings.
        assertTrue(blocked.contains("Android notification settings"))
        assertTrue(plate.contains("Android notification settings"))
        assertTrue(plate.contains("Settings.ACTION_APP_NOTIFICATION_SETTINGS"))
    }

    @Test
    fun thePlateCannotClaimSuccessOnItsOwn() {
        // It used to: `testSent = true` was set by the tap itself, and the
        // green literal lived here. Neither may come back - the posted answer
        // chooses the words.
        assertFalse("the plate sets its own success flag again", plate.contains("testSent"))
        assertTrue(plate.contains("testPosted"))
        assertTrue(plate.contains("testWords(posted)"))
    }
}
