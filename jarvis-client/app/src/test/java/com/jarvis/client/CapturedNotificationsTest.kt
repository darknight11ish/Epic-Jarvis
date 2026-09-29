package com.jarvis.client

import com.jarvis.client.data.CapturedNotification
import com.jarvis.client.data.CapturedRows
import com.jarvis.client.net.PhoneNotifications
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The captured-notification store's list rules (audit 2026-09-28, A3 and
 * A8) and the "Delete captured notifications" words.
 */
class CapturedNotificationsTest {

    private val day = 24L * 60L * 60L * 1000L
    private val now = 100L * day

    private fun row(id: String, pkg: String = "com.chat", at: Long = now, text: String = "hi") =
        CapturedNotification(id, pkg, pkg, "Title", text, at)

    @Test
    fun anUpdatedNotificationReplacesItsRowInsteadOfRepeatingIt() {
        val first = listOf(row("com.chat:k:1", text = "one"))
        val after = CapturedRows.added(first, row("com.chat:k:1", text = "one, two"), now, 7 * day, 200)
        assertEquals(1, after.size)
        assertEquals("one, two", after[0].text)
    }

    @Test
    fun rowsAreCappedByAgeAndCountNewestFirst() {
        val old = row("a", at = now - 8 * day)
        val mid = row("b", at = now - day)
        val out = CapturedRows.added(listOf(old, mid), row("c", at = now), now, 7 * day, 200)
        assertEquals(listOf("c", "b"), out.map { it.id })
        val capped = CapturedRows.added(listOf(mid), row("c", at = now), now, 7 * day, 1)
        assertEquals(listOf("c"), capped.map { it.id })
    }

    @Test
    fun removingAnAppDropsWhatWasCapturedFromIt() {
        val rows = listOf(row("a", pkg = "com.chat"), row("b", pkg = "com.mail"), row("c", pkg = "com.chat"))
        assertEquals(listOf("b"), CapturedRows.withoutApp(rows, "com.chat").map { it.id })
        assertEquals(3, CapturedRows.withoutApp(rows, "com.other").size)
    }

    @Test
    fun deletingAsksFirstAndSaysItCannotBeUndone() {
        assertEquals(
            "Delete the 3 captured notifications kept on this phone? This cannot be undone.",
            PhoneNotifications.deleteQuestion(3),
        )
        assertTrue(PhoneNotifications.deleteQuestion(1).startsWith("Delete the 1 captured notification kept"))
        assertEquals(PhoneNotifications.NONE_KEPT, PhoneNotifications.keptLine(0))
        assertTrue(PhoneNotifications.keptLine(1).startsWith("1 captured notification is kept"))
        assertTrue(PhoneNotifications.keptLine(2).contains("Turning the switch off deletes them."))
    }
}
