package com.jarvis.client

import com.jarvis.client.ui.OpenPlace
import com.jarvis.client.ui.Screen
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * [OpenPlace]: where "open <a settings section>" goes on the phone (phone
 * walk-through, 2026-09-27 - "open help" and friends used to land at the
 * top of Settings, which has none of them).
 */
class OpenPlaceTest {

    @Test
    fun `the places the walk-through named go to their own screens`() {
        assertEquals(OpenPlace.Where.Go(Screen.FAQ, null), OpenPlace.whereFor("faq"))
        assertEquals(OpenPlace.Where.Go(Screen.FAQ, "about"), OpenPlace.whereFor("about"))
        assertEquals(OpenPlace.Where.Go(Screen.CHECKS, "connection"), OpenPlace.whereFor("connection"))
        assertEquals(OpenPlace.Where.Go(Screen.BRAIN, "briefing"), OpenPlace.whereFor("briefing-settings"))
        assertEquals(OpenPlace.Where.Go(Screen.VOICES, null), OpenPlace.whereFor("voices"))
    }

    @Test
    fun `Settings rows still go to Settings, by the same id`() {
        for (id in listOf("voice", "security", "manner", "web-search", "backup", "watch-notify", "devices", "quick-tiles")) {
            assertEquals(id, OpenPlace.Where.Go(Screen.SETTINGS, id), OpenPlace.whereFor(id))
        }
    }

    @Test
    fun `a place only the PC has says so instead of opening a screen`() {
        for (id in listOf("shortcuts", "account-secrets", "tool-updates", "more-options", "start-jarvis", "crash-notes")) {
            assertEquals(id, OpenPlace.Where.OnPc(OpenPlace.ON_PC), OpenPlace.whereFor(id))
        }
        assertTrue(OpenPlace.ON_PC.contains("your PC"))
    }

    @Test
    fun `an id newer than this app still just opens Settings`() {
        assertEquals(OpenPlace.Where.Go(Screen.SETTINGS, "something-new"), OpenPlace.whereFor("something-new"))
    }

    /**
     * Every section the backend can name (jarvis_settings_registry.py's
     * `SECTIONS`, read as text) has a decision here - so one added there
     * without a phone decision fails this test rather than quietly landing
     * at the top of Settings again.
     */
    @Test
    fun `every section in the registry has a phone decision`() {
        val py = repoFile("backend/jarvis_settings_registry.py").readText()
        val block = py.substringAfter("SECTIONS: tuple = (").substringBefore("\n)\n")
        val ids = Regex("Section\\(\"([\\w-]+)\"").findAll(block).map { it.groupValues[1] }.toList()
        assertTrue("no Section(...) ids found - did this test's own extraction break?", ids.size > 10)
        val missing = ids.filter { it !in OpenPlace.KNOWN }
        assertTrue("no phone decision in OpenPlace.kt for: $missing", missing.isEmpty())
    }

    /** Every Settings target is a key SettingsScreen.kt can actually scroll to. */
    @Test
    fun `every Settings target is in SettingsScreen's own index map`() {
        val kt = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt").readText()
        val map = kt.substringAfter("SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(").substringBefore("\n)")
        val keys = Regex("\"([\\w-]+)\" to \\d+").findAll(map).map { it.groupValues[1] }.toSet()
        assertTrue("SETTINGS_ITEM_INDEX not found", keys.isNotEmpty())
        for (id in OpenPlace.KNOWN) {
            val where = OpenPlace.whereFor(id)
            if (where is OpenPlace.Where.Go && where.screen == Screen.SETTINGS) {
                assertTrue("$id goes to Settings, which has no row keyed ${where.section}", where.section in keys)
            }
        }
    }

    /** Every Brain, Help and Checks target is a real `item(key = ...)` on that screen. */
    @Test
    fun `every other target is a real item key on its screen`() {
        val dir = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
        val files = mapOf(
            Screen.BRAIN to "BrainScreen.kt",
            Screen.FAQ to "FaqScreen.kt",
            Screen.CHECKS to "ReadinessScreen.kt",
        )
        for (id in OpenPlace.KNOWN) {
            val where = OpenPlace.whereFor(id) as? OpenPlace.Where.Go ?: continue
            val section = where.section ?: continue
            val file = files[where.screen] ?: continue
            val src = repoFile(dir + file).readText()
            assertTrue("$id: $file has no item(key = \"$section\")", src.contains("item(key = \"$section\")"))
        }
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
