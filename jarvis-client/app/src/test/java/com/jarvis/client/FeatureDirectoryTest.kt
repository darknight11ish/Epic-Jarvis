package com.jarvis.client

import com.jarvis.client.net.FeatureDirectory
import com.jarvis.client.net.FeatureSearch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Android "All features and abilities" directory, held to the merged PC
 * data: all 139 rows, exactly the five approved labels, honest examples and
 * screen paths for every non-toggle row, no fake controls, and every row
 * findable by its own words.
 */
class FeatureDirectoryTest {

    private val rows = FeatureDirectory.ROWS

    @Test
    fun `all 139 features are present, each once, with a real id and name`() {
        assertEquals(139, rows.size)
        assertEquals("the generated artifact says the same count", 139, FeatureDirectory.COUNT)
        assertEquals("ids are unique", rows.size, rows.map { it.id }.toSet().size)
        assertTrue("names are not blank", rows.all { it.name.isNotBlank() })
        assertTrue("groups are not blank", rows.all { it.group.isNotBlank() })
    }

    @Test
    fun `exactly the five approved labels, and every row uses one`() {
        assertEquals(5, FeatureDirectory.LABELS.size)
        assertEquals(rows.map { it.label }.toSet(), FeatureDirectory.LABELS.toSet())
        val expectedPrefixes = listOf(
            "Switchable / Adjustable (Typed & Settings)",
            "Settings-Only (By Design",
            "PC-Only Setting (Honest Refusal on Phone)",
            "Command-Only (Runs When You Ask",
            "Always On (Core Safety Rule",
        )
        for (label in FeatureDirectory.LABELS) {
            assertTrue("unapproved label: $label",
                expectedPrefixes.any { label.startsWith(it) })
        }
        // The counts the PC sends (labels 40/2/16/69/12; corrected 2026-10-23 by
        // the adjustment-truth pass), so a wrong label is caught.
        assertEquals(40, rows.count { it.label.startsWith("Switchable / Adjustable") })
        assertEquals(2, rows.count { it.label.startsWith("Settings-Only") })
        assertEquals(16, rows.count { it.label.startsWith("PC-Only Setting") })
        assertEquals(69, rows.count { it.label.startsWith("Command-Only") })
        assertEquals(12, rows.count { it.label.startsWith("Always On") })
    }

    @Test
    fun `Settings-Only is exactly Accounts and Restore backup`() {
        val ids = rows.filter { it.label.startsWith("Settings-Only") }.map { it.id }.sorted()
        assertEquals(listOf("accounts", "backup"), ids)
    }

    @Test
    fun `a non-toggle row carries an honest example and screen path, and no switch is faked`() {
        // The directory draws NO toggles, so "no fake control" is a data rule:
        // a setting key may only appear on a Switchable row, and a row the
        // contract marks as a toggle must name it. A Switchable row can carry
        // keys without being a one-tap toggle (it may be a choice or a title),
        // which is exactly why the UI receives data and never draws a switch.
        for (row in rows) {
            if (row.switchKeys.isNotEmpty()) {
                assertTrue("only a Switchable row may name a setting: ${row.id}",
                    row.label.startsWith("Switchable / Adjustable"))
            }
            if (row.isToggle) {
                assertTrue("a toggle row must be Switchable: ${row.id}",
                    row.label.startsWith("Switchable / Adjustable"))
                assertTrue("a toggle row names a switch: ${row.id}", row.switchKeys.isNotEmpty())
            }
            if (row.label.startsWith("Command-Only")) {
                assertTrue("a command row has an example: ${row.id}",
                    row.examplePhrase.isNotBlank())
            }
            assertTrue("every row has a screen path: ${row.id}", row.settingsPath.isNotBlank())
        }
    }

    @Test
    fun `an Always-On row owns no switch keys`() {
        val always = rows.filter { it.label.startsWith("Always On") }
        assertEquals(12, always.size)
        assertTrue("Always On may not own a switch", always.all { it.switchKeys.isEmpty() })
        assertTrue("Always On is never a toggle", always.none { it.isToggle })
    }

    @Test
    fun `every row is findable by its own name`() {
        for (row in rows) {
            val found = FeatureSearch.search(row.name)
            assertTrue("not found by name: ${row.id} (${row.name})",
                found.any { it.id == row.id })
        }
        // A mid-word from the why/example finds it too, and punctuation/case do not matter.
        assertTrue(FeatureSearch.search("WEATHER").any { it.id == "typing" })
        assertTrue(FeatureSearch.search("prompt, coach!").any { it.id == "prompt-coach" })
        assertEquals("an empty query returns the directory", rows.size, FeatureSearch.search("").size)
    }

    @Test
    fun `no row reaches the phone as a fake control`() {
        // A PC-Only row is shown with its honest refusal, never as a switch.
        val pcOnly = rows.filter { it.label.startsWith("PC-Only Setting") }
        assertEquals(16, pcOnly.size)
        assertTrue("a PC-Only row never offers a phone switch",
            pcOnly.all { it.switchKeys.isEmpty() && !it.isToggle })
    }

    @Test
    fun `the switches with no Settings row of their own are still findable`() {
        // These are the BOOL_SETTINGS names the phone has no Settings row for
        // (Brain, a plate, or the PC changes them). The directory is the answer
        // that search points at, so every one must find at least one row.
        val names = listOf(
            "background learning", "sensitive topics", "ask before every search",
            "sandbox", "media index", "pictures", "briefing senders", "big coder",
            "big model", "alarm sounds", "reminder sounds", "briefing notification",
            "handoff notification", "quiet hours", "voice follows the face",
            "better voice", "write like me", "second card",
        )
        for (name in names) {
            assertTrue("the directory cannot answer: $name",
                FeatureSearch.search(name).isNotEmpty())
        }
    }
}
