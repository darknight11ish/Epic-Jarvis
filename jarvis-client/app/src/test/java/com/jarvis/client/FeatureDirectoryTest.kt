package com.jarvis.client

import com.jarvis.client.net.FeatureDirectory
import com.jarvis.client.net.FeatureSearch
import com.jarvis.client.net.JarvisJson
import java.io.File
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Android "All features and abilities" directory, held to the merged PC
 * data: every row, exactly the five approved labels, honest examples and
 * screen paths for every non-toggle row, no fake controls, and every row
 * findable by its own words.
 */
class FeatureDirectoryTest {

    private val rows = FeatureDirectory.ROWS

    /**
     * The PC's own contract - the file this directory is GENERATED from.
     *
     * Reading it is the point. The counts below used to be typed into this
     * test, and they went 26 features stale between 2026-10-28 and 2026-11-02
     * without one assertion failing: the directory shipped 142 of the
     * contract's 168 rows and still told the owner "Appearance on Home" after
     * that button was removed (DEF-027). Comparing the generated rows against
     * the contract's own `feature_count` and `label_counts` makes the two
     * artifacts prove each other, so the next stale regeneration fails here
     * instead of reaching the phone.
     */
    private val contract by lazy {
        JarvisJson.parseToJsonElement(
            repoFile("contract/feature-controls.json").readText()).jsonObject
    }

    /** The contract's own count for the one label starting with [prefix]. */
    private fun contractCount(prefix: String): Int =
        contract["label_counts"]!!.jsonObject.entries
            .first { it.key.startsWith(prefix) }.value.jsonPrimitive.int

    /** The directory under test is generated, so its source lives above the test's working dir. */
    private fun repoFile(rel: String): File {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    @Test
    fun `every feature is present, each once, with a real id and name`() {
        // COUNT is generated from the same rows (len(rows) in
        // jarvis-client/tools/gen_feature_directory.py), so this holds the two
        // generated halves together instead of typing the total here.
        assertEquals("the generated artifact's COUNT matches its own rows",
            rows.size, FeatureDirectory.COUNT)
        assertEquals("the generated rows are the contract's feature count",
            contract["feature_count"]!!.jsonPrimitive.int, rows.size)
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
        // The counts cross-check the generated rows against the PC's own
        // contract, the file they are generated from, instead of numbers
        // typed here. On 2026-11-02 the typed pins read 42/2/15/71/12 while
        // the contract said 43/2/16/95/12 - 26 features had been missing from
        // the phone's directory since 2026-10-28 and every assertion passed
        // (DEF-027). A stale regeneration now fails on the first mismatch.
        for ((label, expected) in contract["label_counts"]!!.jsonObject) {
            assertEquals("rows in $label", expected.jsonPrimitive.int,
                rows.count { it.label == label })
        }
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
        assertEquals(contractCount("Always On"), always.size)
        assertTrue("Always On may not own a switch", always.all { it.switchKeys.isEmpty() })
        assertTrue("Always On is never a toggle", always.none { it.isToggle })
    }

    @Test
    fun `the phone's document and Notion doors are in the directory`() {
        // 2026-11-06: the two doors the phone grew on 2026-11-05 were missing
        // from the feature list, so Jarvis told the owner it could not import a
        // document from the phone at all. The generated directory must carry
        // them, and the Notion row must say BOTH apps (its old desktop-only
        // words said the phone had no Notion-import screen - false).
        val document = rows.firstOrNull { it.id == "document-from-phone" }
        assertTrue("the phone's document door is not in the directory", document != null)
        if (document != null) {
            assertEquals("Send a document from your phone", document.name)
            assertEquals("both", document.surface)
            assertTrue("the document row must be Command-Only",
                document.label.startsWith("Command-Only"))
            assertTrue("the document door is not a switch", !document.isToggle)
            assertTrue("the document row must offer no phone switch",
                document.switchKeys.isEmpty())
            assertTrue("the row does not name the phone's own button: ${document.why}",
                document.why.contains("Send a document"))
            assertTrue("the row does not say where the file lands: ${document.why}",
                document.why.contains("From my phone"))
            assertTrue("the row does not name the phone's Settings row: ${document.why}",
                document.why.contains("Folders Jarvis may look in"))
        }
        val notion = rows.firstOrNull { it.id == "notion-import" }
        assertTrue("the Notion row is missing from the directory", notion != null)
        if (notion != null) {
            assertEquals("the Notion door is on BOTH apps now", "both", notion.surface)
            assertTrue("the Notion row must name the phone's Bring in a Notion export door: ${notion.why}",
                notion.why.contains("Bring in a Notion export"))
            assertFalse("a both-apps row must not be prefixed as the PC's own place",
                notion.why.startsWith("On your PC: "))
        }
        // The contract the directory is generated from says the same thing, so
        // a regeneration cannot quietly put the stale words back.
        val features = contract["features"]!!.jsonArray
        val contractNotion = features.first { it.jsonObject["id"]!!.jsonPrimitive.content == "notion-import" }
        assertEquals("both", contractNotion.jsonObject["surface"]!!.jsonPrimitive.content)
        val contractDocument = features.first { it.jsonObject["id"]!!.jsonPrimitive.content == "document-from-phone" }
        assertEquals("both", contractDocument.jsonObject["surface"]!!.jsonPrimitive.content)
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
    fun `a row the PC alone has names whose place it is`() {
        // The settings wrong-app audit (2026-10-29, findings 1 and 2): 17 rows
        // whose words are the PC's place - "Settings, Accounts", "Settings,
        // Shortcuts", "Brain, Memory" - reached the phone with no qualifier and
        // dead-ended, because the phone has none of those sections. The
        // generator now puts "On your PC: " in front of a `desktop`-surface
        // row's words unless the contract's own sentence already says the PC.
        val desktopOnly = rows.filter { it.surface == "desktop" }
        assertTrue("no desktop-only rows were found at all", desktopOnly.size >= 15)
        for (row in desktopOnly) {
            assertTrue(
                "a desktop-only row does not say whose place it names: ${row.id} (${row.why})",
                row.why.startsWith("On your PC: ") ||
                    row.why.startsWith("PC:") || row.why.contains("on the PC")
            )
        }
    }

    @Test
    fun `no row reaches the phone as a fake control`() {
        // A PC-Only row is shown with its honest refusal, never as a switch.
        val pcOnly = rows.filter { it.label.startsWith("PC-Only Setting") }
        assertEquals(contractCount("PC-Only Setting"), pcOnly.size)
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
