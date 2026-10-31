package com.jarvis.client

import com.jarvis.client.net.Calendar
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * DEF-025: the phone's calendar drew "(hidden)" while the accessibility tree
 * still carried the full event title (field-test pass 9, section P8, node 49
 * in `p9-cal-saved.xml`).
 *
 * ROOT CAUSE, found here by following that node rather than guessing at the
 * row: the extra node was the PC's OWN confirmation sentence, drawn under the
 * screen (`CalendarPlate.kt`'s `write` -> `said`). `jarvis_local_calendar`'s
 * `_said()` builds it as `"<title>, Saturday 31 October at 09:00."`, so it
 * contains the title - and the phone showed it verbatim with "Hide memory
 * lists and chat history" ON, which both puts it on screen and hands it to
 * TalkBack (the row itself was already right).
 *
 * THE FIX, proved here: [Calendar.displaySaid] is the only way a write's
 * sentence reaches the screen. While titles are hidden it never returns the
 * PC's words; the plate also clears the semantics of both the hidden title and
 * that line to the withholding words, so no title can sit in `text`,
 * `contentDescription`, or any other property of a semantic node.
 */
class CalendarHiddenA11yTest {

    /** The exact sentence the field test's accessibility dump carried. */
    private val leaked = "ZZ field test delete me, Saturday 31 October at 09:00."

    @Test
    fun `the PC's title-bearing sentence is never shown while titles are hidden`() {
        // Visible titles: the PC's own sentence, unchanged, exactly as before.
        assertEquals(leaked,
            Calendar.displaySaid(ok = true, deleted = false, hidden = false, sentence = leaked))
        // Hidden: one fixed title-free line, and NO part of the title in it.
        val hiddenSave = Calendar.displaySaid(true, deleted = false, hidden = true, sentence = leaked)
        assertEquals(Calendar.HIDDEN_SAVED, hiddenSave)
        val hiddenDelete = Calendar.displaySaid(true, deleted = true, hidden = true, sentence = leaked)
        assertEquals(Calendar.HIDDEN_DELETED, hiddenDelete)
        val hiddenFailure = Calendar.displaySaid(false, deleted = false, hidden = true, sentence = leaked)
        assertEquals(Calendar.HIDDEN_NOT_SAVED, hiddenFailure)
        for (line in listOf(hiddenSave, hiddenDelete, hiddenFailure)) {
            assertFalse("a hidden line leaked the event name: $line", line.contains("ZZ field test"))
            assertFalse("a hidden line leaked the day: $line", line.contains("Saturday"))
            assertFalse("a hidden line leaked the time", line.contains("09:00"))
        }
        // ...and the words the screen still draws are unchanged.
        assertEquals("(hidden)", Calendar.HIDDEN_TITLE)
    }

    @Test
    fun `one guard sits between every write and the screen, and a delete is told apart`() {
        val plate = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/CalendarPlate.kt")
        // Every write goes through displaySaid: the PC's sentence cannot be
        // assigned to `said` directly any more (that was the leak).
        assertTrue(plate.contains("said = Calendar.displaySaid(ok, deleted, privateHidden, sentence)"))
        assertFalse("a write still assigns the PC's sentence unguarded", plate.contains("said = sentence"))
        // The delete calls the guard with deleted = true.
        assertTrue(plate.contains("write(deleted = true) { JarvisRuntime.calendarDelete(victim.id) }"))
        // Add and update keep the default (not a delete).
        assertTrue(plate.contains("write {"))
    }

    @Test
    fun `the hidden title node carries only the withholding word`() {
        val plate = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/CalendarPlate.kt")
        // The row still draws "(hidden)", and its node's ONLY accessibility
        // word is that same word - the title is never attached to it.
        assertTrue(plate.contains("if (hidden) Calendar.HIDDEN_TITLE else event.title"))
        assertTrue(plate.contains("Modifier.clearAndSetSemantics { contentDescription = Calendar.HIDDEN_TITLE }"))
        // Place and recurrence stay suppressed while hidden, as they were.
        assertTrue(plate.contains("if (!hidden) {"))
    }

    @Test
    fun `the hidden confirmation line's semantics are cleared to its own safe sentence`() {
        val plate = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/CalendarPlate.kt")
        assertTrue(plate.contains("Modifier.clearAndSetSemantics { contentDescription = it }"))
        // ...and the delete dialog hides the title too (it already did; kept).
        assertTrue(plate.contains("if (privateHidden) {"))
        assertTrue(plate.contains("\"One event on your PC. This cannot be undone.\""))
    }

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun file(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
