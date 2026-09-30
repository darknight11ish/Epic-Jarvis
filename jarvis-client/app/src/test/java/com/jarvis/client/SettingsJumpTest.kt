package com.jarvis.client

import com.jarvis.client.ui.SettingsJump
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The jump list at the top of Settings (settings audit, 2026-09-30) is held to
 * the screen's real rows: every section on the screen is in the list, in the
 * same order, and the list scrolls to the position the screen really has.
 */
class SettingsJumpTest {

    private val dir = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"

    /** The screen's `item(key = "...")` rows, in the order they are drawn. */
    private fun rows(file: String): List<String> =
        // Quoted keys only: a comment that says `item(key = ...)` is not a row.
        Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(repoFile(dir + file).readText())
            .map { it.groupValues[1] }.toList()

    @Test
    fun `every Settings section is in the jump list, in screen order`() {
        val real = rows("SettingsScreen.kt")
        assertEquals("jump-list", SettingsJump.LIST_KEY)
        assertTrue("SettingsScreen.kt's rows were not found", real.size > 10)
        val sections = real.filter { it != SettingsJump.LIST_KEY && it != SettingsJump.TAIL_KEY }
        assertEquals(sections, SettingsJump.ENTRIES.map { it.key })
        assertEquals("no label is listed twice", SettingsJump.ENTRIES.size, SettingsJump.ENTRIES.map { it.label }.toSet().size)
    }

    @Test
    fun `the jump list is the first row, and Voice holds the hey Jarvis switches`() {
        val src = repoFile(dir + "SettingsScreen.kt").readText()
        val real = rows("SettingsScreen.kt")
        assertEquals("the jump list comes first", SettingsJump.LIST_KEY, real.first())
        assertTrue("Voice draws the switches slot", src.contains("voiceSwitches?.let"))
        assertTrue("Picture mode gets the Look-switch button", src.contains("onOpenLookSwitch = onOpenLookSwitch"))
    }

    @Test
    fun `the index map matches the screen, item by item`() {
        val src = repoFile(dir + "SettingsScreen.kt").readText()
        val map = src.substringAfter("SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(").substringBefore("\n)")
        val declared = Regex("\"([\\w-]+)\" to (\\d+)").findAll(map).associate { it.groupValues[1] to it.groupValues[2].toInt() }
        val real = rows("SettingsScreen.kt")
        assertTrue(declared.isNotEmpty())
        for ((key, index) in declared) {
            val row = if (key == "appearance-card" || key == "animal-options") "appearance" else key
            assertEquals("$key", real.indexOf(row), index)
        }
    }

    @Test
    fun `Security's Look switch is where the button sends you`() {
        val real = rows("SecurityScreen.kt")
        // The rows that are always above "look": app-lock, live-end, approvals, private.
        assertEquals(listOf("app-lock", "live-end", "approvals", "private", "look"),
            real.filter { it in setOf("app-lock", "live-end", "approvals", "private", "look") })
        val src = repoFile(dir + "SecurityScreen.kt").readText()
        assertTrue(src.contains("4 + (if (notice != null) 1 else 0) + (if (showNoCheck) 1 else 0)"))
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
