package com.jarvis.client

import com.jarvis.client.ui.SettingsJump
import com.jarvis.client.ui.SettingsSearch
import com.jarvis.client.ui.SettingsSearchWords
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The search box at the top of Settings (2026-10-09) - the phone's half of the
 * desktop's search (`jarvis-desktop/src/settings-search.js`;
 * `docs/SETTINGS-UX-DESIGN.md`).
 *
 * Three things it holds that would otherwise drift, and the third is the one
 * this repository has already been bitten by once (the open-chat phrase list
 * was two separately-maintained copies):
 *
 *  1. every section on the screen can be found;
 *  2. the words in the index are really the words the app uses;
 *  3. the two apps describe the same box in the same words.
 */
class SettingsSearchTest {

    @Test
    fun `every Settings section can be searched, in screen order`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val rows = Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(screen)
            .map { it.groupValues[1] }.toList()
        val sections = rows.filter { it != SettingsJump.LIST_KEY && it != SettingsJump.TAIL_KEY }
        assertEquals(
            "SettingsSearch.ROWS must be the screen's own rows, in order",
            sections,
            SettingsSearch.ROWS.map { it.key },
        )
        assertEquals("no key is listed twice", sections.size, sections.toSet().size)
    }

    @Test
    fun `the search box is a row of its own, above the jump list`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val rows = Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(screen)
            .map { it.groupValues[1] }.toList()
        assertEquals("the box comes first", SettingsJump.SEARCH_KEY, rows.first())
        assertEquals(SettingsJump.LIST_KEY, rows[1])
        // ...and it is a control, never a section a search can hide.
        assertFalse(SettingsJump.SEARCH_KEY in SettingsJump.ENTRIES.map { it.key })
        assertFalse(SettingsJump.SEARCH_KEY in SettingsSearch.SECTION_KEYS)
        // ...and the jump list is not drawn while a search is on, because it
        // maps a screen that is not whole any more.
        assertTrue(
            "the jump list must stand down while searching",
            screen.contains("if (!searching) item(key = SettingsJump.LIST_KEY)"),
        )
    }

    @Test
    fun `every row carries a searchable index entry`() {
        for (key in SettingsSearch.SECTION_KEYS) {
            val row = SettingsSearch.row(key)
            assertTrue("$key has no words", row != null && SettingsSearch.wordsFor(key).length > 20)
        }
        assertEquals(
            "wordsFor of an unknown key is empty, not a crash",
            "",
            SettingsSearch.wordsFor("no-such-section"),
        )
    }

    @Test
    fun `the index quotes the app's own words`() {
        val client = "jarvis-client/app/src/main/java/com/jarvis/client/"
        for (row in SettingsSearch.ROWS) {
            val sources = row.source.joinToString("\n") { file -> repoFile(client + file).readText() }
            for (quote in row.quotes) {
                assertTrue(
                    "${row.key}: nothing in ${row.source} says \"$quote\" - the index is " +
                        "describing a screen that has changed",
                    sources.contains(quote),
                )
            }
        }
    }

    @Test
    fun `a search finds a section by its heading and by its own words`() {
        // The heading.
        assertTrue(SettingsSearch.matches("voice", "voice"))
        assertTrue(SettingsSearch.matches("web-search", "search"))
        assertEquals(listOf("voice"), SettingsSearch.matching("voice"))
        // The words of a control inside it.
        assertTrue(SettingsSearch.matches("folders", "obsidian"))
        assertEquals(listOf("folders"), SettingsSearch.matching("logseq"))
        // Case and accents, the same folding the desktop does.
        assertTrue(SettingsSearch.matches("voice", "VOICE"))
        assertTrue(SettingsSearch.matches("menu-visibility", "menü"))
        assertTrue(SettingsSearch.matches("voice", "jarvis's"))
        // Nothing typed is nothing matched - the screen shows everything then.
        assertFalse(SettingsSearch.matches("voice", "   "))
        assertEquals(emptyList<String>(), SettingsSearch.matching(""))
        assertEquals(emptyList<String>(), SettingsSearch.matching("zzzz"))
    }

    @Test
    fun `normalise folds the way the desktop folds`() {
        assertEquals("wi fi", SettingsSearch.normalise("Wi-Fi"))
        assertEquals("jarvis s voice", SettingsSearch.normalise("Jarvis's voice"))
        assertEquals("cafe", SettingsSearch.normalise("café"))
        assertEquals("a b", SettingsSearch.normalise("  A   B  "))
        assertEquals("", SettingsSearch.normalise("---"))
    }

    @Test
    fun `the two apps say the same words about the same box`() {
        val js = repoFile("jarvis-desktop/src/settings-search.js").readText()
        for ((kotlinName, jsName) in listOf(
            SettingsSearchWords.LABEL to "SEARCH_LABEL",
            SettingsSearchWords.PLACEHOLDER to "SEARCH_PLACEHOLDER",
            SettingsSearchWords.CLEAR to "SEARCH_CLEAR",
            SettingsSearchWords.HINT to "SEARCH_HINT",
            SettingsSearchWords.NONE to "SEARCH_NONE",
            SettingsSearchWords.NONE_BACK to "SEARCH_NONE_BACK",
            SettingsSearchWords.ONE to "SEARCH_ONE",
            SettingsSearchWords.MANY to "SEARCH_MANY",
        )) {
            val quoted = "\"${kotlinName.replace("\"", "\\\"")}\""
            assertTrue(
                "the desktop has no `export const $jsName = $quoted;` - the two apps " +
                    "would describe the same box differently",
                js.contains("export const $jsName = $quoted;"),
            )
        }
    }

    @Test
    fun `the line under the box says what the search found`() {
        assertEquals(SettingsSearchWords.HINT, SettingsSearchWords.line("", 20))
        assertEquals(SettingsSearchWords.ONE, SettingsSearchWords.line("voice", 1))
        assertEquals("3 settings match.", SettingsSearchWords.line("voice", 3))
        assertEquals("", SettingsSearchWords.line("zzzz", 0))
        assertEquals(
            "Nothing here matches “zzzz”.",
            SettingsSearchWords.none("  zzzz  "),
        )
    }

    @Test
    fun `the index map counts the search box as the first row`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val map = screen
            .substringAfter("SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(")
            .substringBefore("\n)")
        assertTrue(
            "the search box must be in SETTINGS_ITEM_INDEX at 0 (SettingsJumpTest holds " +
                "every other number to the screen)",
            map.contains("\"search\" to SettingsJump.SEARCH_KEY_INDEX"),
        )
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
