package com.jarvis.client

import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import com.jarvis.client.ui.SettingsJump
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The jump list at the top of Settings (settings audit, 2026-09-30) is held to
 * the screen's real rows: every section on the screen is in the list, in the
 * same order, and the list scrolls to the position the screen really has.
 *
 * UI audit 2026-10-05, finding A3: it scrolled by `SETTINGS_ITEM_INDEX`
 * positions instead, so a row that was not drawn - `settings.voice` is
 * hideable - moved every row below it and the tap landed on a DIFFERENT
 * panel, silently. The tests below hold the jump to the KEY the screen draws
 * and compute the position a hidden menu would really give, which is the
 * number the old code used and got wrong.
 */
class SettingsJumpTest {

    private val dir = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"

    /** The screen's `item(key = "...")` rows, in the order they are drawn. */
    private fun rows(file: String): List<String> =
        // Quoted keys only: a comment that says `item(key = ...)` is not a row.
        Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(repoFile(dir + file).readText())
            .map { it.groupValues[1] }.toList()

    /**
     * The rows the screen really draws when [hidden] menus are hidden, in
     * order: a row whose own `menus.shows("<id>")` guard is false is not
     * drawn at all. Read from the source next to each `item(key = ...)`, so
     * this follows the screen rather than a second hand-kept list.
     */
    private fun drawnRows(hidden: Set<String>): List<String> {
        val src = repoFile(dir + "SettingsScreen.kt").readText()
        val at = Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(src).map { it.range.first to it.groupValues[1] }
        return at.map { (start, key) ->
            // The guard sits just before the row; the `if` nearest to it is the one that decides.
            val before = src.substring(maxOf(0, start - 90), start)
            val guards = Regex("menus\\.shows\\(\"([\\w.-]+)\"\\)").findAll(before).map { it.groupValues[1] }.toList()
            key to guards.none { it in hidden }
        }.filter { it.second }.map { it.first }.toList()
    }

    @Test
    fun `every Settings section is in the jump list, in screen order`() {
        val real = rows("SettingsScreen.kt")
        assertEquals("jump-list", SettingsJump.LIST_KEY)
        assertTrue("SettingsScreen.kt's rows were not found", real.size > 10)
        // The search box (2026-10-09) is a row of the screen but not a
        // SECTION: it is a control, and it is never hidden by its own search
        // or listed as somewhere to jump to (SettingsSearchTest holds that).
        assertEquals("the search box is the first row", SettingsJump.SEARCH_KEY, real.first())
        val sections = real.filter {
            it != SettingsJump.LIST_KEY && it != SettingsJump.TAIL_KEY && it != SettingsJump.SEARCH_KEY
        }
        assertEquals(sections, SettingsJump.ENTRIES.map { it.key })
        assertEquals("no label is listed twice", SettingsJump.ENTRIES.size, SettingsJump.ENTRIES.map { it.label }.toSet().size)
    }

    @Test
    fun `the jump list is right below the search box, and Voice holds the hey Jarvis switches`() {
        val src = repoFile(dir + "SettingsScreen.kt").readText()
        val real = rows("SettingsScreen.kt")
        assertEquals("the jump list comes second, under the search box", SettingsJump.LIST_KEY, real[1])
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

    @Test
    fun `a hidden menu moves the screen, and the jump goes to the key not the number`() {
        val name = "settings.voice"
        assertTrue(
            "the bug's own menu must still be hideable for this test to mean anything",
            MenuLogic.menu(name)?.hide == true,
        )
        val hidden = setOf(name)
        val state = MenuState(hidden = hidden)
        // What the screen draws for real once Voice is hidden. Its own guard is
        // `menus.shows(name)`, so this is the same decision the screen makes.
        assertFalse(MenuView(state).shows(name))
        val drawn = drawnRows(hidden)
        assertEquals("one row fewer, and it is the hidden one", rows("SettingsScreen.kt").size - 1, drawn.size)
        assertFalse("Voice is not drawn", drawn.contains("voice"))
        assertTrue("the row below it still is", drawn.contains("security"))

        // Which row really MOVED, and by how much - which is what this test is
        // about: a fixed number handed to `animateScrollToItem` no longer names
        // the row it used to.
        //
        // The two lists are compared directly, because a menu id and a row key
        // are different namespaces: a row's own guard names the MENU. The first
        // two versions of this check assumed otherwise and compared the wrong
        // row - first one ABOVE the hidden menu (which never moves), then, when
        // the menu id was looked up in the row-key list, the hidden row itself
        // ("voice is still on the screen", 2026-10-08).
        val full = rows("SettingsScreen.kt")
        val firstGone = full.indexOfFirst { it !in drawn }
        assertTrue("hiding $name has to remove its own row", firstGone >= 0)
        val gone = full.count { it !in drawn }
        // The first row that SURVIVES the hiding, which is the one whose
        // position moved. Indexed rather than `getOrNull`, so it is a plain
        // String for `indexOf` below.
        assertTrue("a row has to survive hiding $name", firstGone + gone < full.size)
        val wasAt = firstGone + gone
        val row = full[wasAt]
        val nowAt = drawn.indexOf(row)
        assertEquals("$row moves up by $gone when $name is hidden", wasAt - gone, nowAt)
        assertTrue(
            "the old number ($wasAt) now names ${full.getOrNull(nowAt)} rather than $row",
            wasAt != nowAt,
        )
        assertFalse("the hidden key is not drawn anywhere", drawn.contains(name))

        // The fix: the tap hands over the KEY the screen draws, so what is
        // looked up cannot drift when a row above it disappears.
        val src = repoFile(dir + "SettingsScreen.kt").readText()
        val handler = code(src.substringAfter("SettingsJumpList { key ->").substringBefore("\n                }"))
        assertTrue("the tap sets the key itself:\n$handler", handler.contains("jumpTo = key"))
        assertFalse(
            "the tap must not go through a position any more:\n$handler",
            handler.contains("jumpIndex") || handler.contains("animateScrollToItem"),
        )
    }

    @Test
    fun `the scroll-by-key helper can be asked for the same row twice`() {
        val src = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/parts/ScrollToKey.kt").readText()
        // Tapping "Voice" again, from the bottom of the screen, has to scroll
        // again: the effect is keyed on the tick as well as the key.
        assertTrue("ScrollToKeyOnce takes a tick", src.contains("fun ScrollToKeyOnce(state: LazyListState, key: String?, tick: Int = 0, onDone: () -> Unit)"))
        assertTrue("and the effect re-runs for it", src.contains("LaunchedEffect(key, tick)"))
        val screen = repoFile(dir + "SettingsScreen.kt").readText()
        assertTrue("Settings bumps the tick on every tap", screen.contains("jumpTick += 1"))
        assertTrue("and hands it over", screen.contains("ScrollToKeyOnce(listState, jumpTo, tick = jumpTick)"))
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

    /**
     * Just the code, with whole-line `//` comments dropped - so an assertion
     * on what the handler DOES cannot be satisfied, or broken, by the comment
     * above it that names the old call on purpose.
     */
    private fun code(text: String): String =
        text.lines().filterNot { it.trimStart().startsWith("//") }.joinToString("\n")
}
