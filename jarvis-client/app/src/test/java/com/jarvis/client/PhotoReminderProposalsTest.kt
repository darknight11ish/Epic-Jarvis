package com.jarvis.client

import com.jarvis.client.net.PhotoReminder
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Photo to reminder" - a picture with SEVERAL dates (2026-10-16;
 * net/PhotoReminder.kt, PhotoReminderDialog.kt).
 *
 * One tap sets ONE reminder. The dialog therefore keeps every proposal the
 * PC offered and marks the one that was added, instead of replacing the whole
 * proposal with the PC's sentence and taking the other dates off the screen.
 * This is the phone's half of the same fix on the PC
 * (jarvis-desktop/tests/photo-reminder-many.mjs).
 */
class PhotoReminderProposalsTest {
    private fun found(title: String, date: String, time: String) = PhotoReminder.Found(
        title = title,
        date = date,
        time = time,
        timeFound = true,
        passed = false,
        whenWords = "",
    )

    private val first = found("Summer fair", "2026-10-12", "14:00")
    private val second = found("Bake sale", "2026-10-19", "11:00")
    private val third = found("Quiz night", "2026-10-24", "19:30")
    private val scan = PhotoReminder.Scan(listOf(first, second, third), "the words", "said")

    @Test
    fun aProposalReadsAsItsDateAndTimeAndTitle() {
        assertEquals("2026-10-12 14:00 - Summer fair", PhotoReminder.label(first))
        assertEquals("2026-10-19 11:00", PhotoReminder.label(found("", "2026-10-19", "11:00")))
    }

    @Test
    fun theKeyIsTheDateAndTimeWithTheTimePadded() {
        assertEquals("2026-10-12 14:00", PhotoReminder.key("2026-10-12", "14:00"))
        assertEquals("2026-10-12 09:05", PhotoReminder.key(" 2026-10-12 ", "9:05"))
    }

    @Test
    fun oneAddLeavesTheOtherDatesInTheList() {
        val added = setOf(PhotoReminder.key(first.date, first.time))
        val shown = PhotoReminder.proposals(scan, added)
        assertEquals("one add must not hide the other dates", 3, shown.size)
        assertTrue("the added one reads as added", shown[0].added)
        assertFalse(shown[1].added)
        assertFalse(shown[2].added)
        // The ones still to add keep the words they had.
        assertEquals(PhotoReminder.label(second), shown[1].label)
        assertEquals(PhotoReminder.label(third), shown[2].label)
    }

    @Test
    fun everyDateCanBeAddedOneAtATime() {
        var added = setOf<String>()
        added = added + PhotoReminder.key(first.date, first.time)
        added = added + PhotoReminder.key(third.date, third.time)
        val shown = PhotoReminder.proposals(scan, added)
        assertTrue(shown[0].added)
        assertFalse("the second one is still there to add", shown[1].added)
        assertTrue(shown[2].added)
        assertEquals(3, shown.size)
    }

    @Test
    fun theAddedOneSaysSoInTheSameWordsAsThePc() {
        assertEquals("Monday 12 October at 14:00 (added)",
            PhotoReminder.addedWords("Monday 12 October at 14:00"))
        // Exactly what the dialog draws for the added proposal.
        val shown = PhotoReminder.proposals(scan, setOf(PhotoReminder.key(first.date, first.time)))
        assertEquals("2026-10-12 14:00 - Summer fair (added)",
            PhotoReminder.addedWords(shown[0].label))
    }
}
