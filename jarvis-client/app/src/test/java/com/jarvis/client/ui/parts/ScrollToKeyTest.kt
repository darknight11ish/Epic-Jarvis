package com.jarvis.client.ui.parts

import com.jarvis.client.ui.screens.BrainSections
import com.jarvis.client.ui.screens.PlateList
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The walk that carries a link into a long screen to the thing it named
 * ([ScrollToKeyOnce], [scrollToKey], [walkStep]).
 *
 * It is here because of a REAL device defect (2026-10-11): Home's new "The
 * Galaxy →" button opened the Brain and left it at the top - "Everything Jarvis
 * can do" and the attention budget, no Galaxy, and no hidden-lists prompt
 * either. The walked-to item is a plate inside a heading, so it is not in the
 * list until the composition after the heading is opened; the old walk stopped
 * the moment it could not move, one frame before the item existed, and returned
 * without scrolling. Every test that only read the button's source passed.
 *
 * The rule is pure ([walkStep]) so a JVM test can drive a list it controls:
 * WAIT while the list is still laying out, scroll a screenful while there is
 * room, and give up only after [WAIT_FRAMES] frames of nothing.
 */
class ScrollToKeyTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    /**
     * A stand-in for a lazy list: a window of visible items and a total count,
     * which a "composition" can extend - exactly what opening a heading does to
     * Brain's list.
     */
    private class FakeList(
        val keys: List<String>,
        var total: Int,
        var window: IntRange,
    ) {
        val firstVisibleIndex: Int get() = window.first
        override fun toString() = "keys=$keys total=$total window=$window"
    }

    /**
     * Runs [walkStep] frame by frame over [list] and returns (final index, the
     * decisions, whether the walk stopped early).
     */
    private fun walk(
        list: FakeList,
        key: String,
        onFrame: (Int, FakeList) -> Unit = { _, _ -> },
    ): Triple<Int?, List<Walk>, Boolean> {
        var index: Int? = null
        var steps = 0
        var waited = 0
        val decisions = ArrayList<Walk>()
        var frame = 0
        while (steps < 60 && frame < 200) {
            onFrame(frame, list)
            val window = list.window.intersect(0 until list.total)
            val decision = walkStep(
                key = key,
                firstVisibleIndex = list.firstVisibleIndex,
                totalItemsCount = list.total,
                visibleKeys = window.map { list.keys[it] },
                visibleIndexes = window.toList(),
                waited = waited,
            )
            decisions.add(decision)
            frame++
            when (decision) {
                Walk.Found -> {
                    index = window.first { list.keys[it] == key }
                    return Triple(index, decisions, false)
                }
                is Walk.Step -> {
                    waited = 0
                    steps++
                    list.window = (decision.index..(decision.index + list.window.count() - 1))
                }
                Walk.Wait -> waited++
                Walk.GiveUp -> return Triple(null, decisions, true)
            }
        }
        return Triple(index, decisions, true)
    }

    @Test
    fun `the walk waits for an item the next composition adds, instead of giving up`() {
        // The real shape: a short list today, and the plate added when the
        // heading opens. The old walk ended on the frame before that.
        val keys = ArrayList(listOf("head-a", "plate-a", "head-b", "tail"))
        val list = FakeList(keys, total = 4, window = 0..3)
        val (found, decisions, gaveUp) = walk(list, "brain-plate:people-and-things") { frame, l ->
            if (frame == 2) {
                // Opening the heading: the plate appears, and the count grows.
                @Suppress("UNCHECKED_CAST")
                (l.keys as ArrayList<String>).add("brain-plate:people-and-things")
                l.total = 5
            }
        }
        assertFalse("the walk gave up while the item was still coming: $decisions", gaveUp)
        assertEquals("the walk did not land on the item", 4, found)
        assertEquals(
            "the walk landed on the wrong item",
            "brain-plate:people-and-things",
            list.keys[found!!],
        )
    }

    @Test
    fun `the walk still ends when the item is genuinely not there`() {
        val keys = listOf("head-a", "plate-a", "head-b", "tail")
        val list = FakeList(keys, total = 4, window = 0..3)
        val (found, decisions, gaveUp) = walk(list, "brain-plate:not-here")
        assertEquals(null, found)
        assertTrue("the walk never gave up on an item that does not exist", gaveUp)
        assertTrue("it should have waited first: $decisions", decisions.count { it is Walk.Wait } in 1..40)
        assertTrue(
            "it gave up without waiting the frames a composition needs",
            decisions.count { it is Walk.Wait } >= 1,
        )
    }

    @Test
    fun `a list with nothing laid out yet waits rather than guessing`() {
        // `totalItemsCount` is positive a frame or two before the first row is
        // visible; the old walk ended right there, with no scroll at all.
        val empty = walkStep(
            key = "brain-plate:people-and-things",
            firstVisibleIndex = 0,
            totalItemsCount = 12,
            visibleKeys = emptyList(),
            visibleIndexes = emptyList(),
            waited = 0,
        )
        assertEquals(Walk.Wait, empty)
        // And it does eventually stop, so a screen that never lays out does not
        // spin for ever.
        assertEquals(
            Walk.GiveUp,
            walkStep(
                key = "brain-plate:people-and-things",
                firstVisibleIndex = 0,
                totalItemsCount = 12,
                visibleKeys = emptyList(),
                visibleIndexes = emptyList(),
                waited = 30,
            ),
        )
    }

    @Test
    fun `the walk scrolls a screenful while there is room and finds the key`() {
        val keys = (0 until 40).map { "row-$it" }
        val list = FakeList(keys, total = 40, window = 0..5)
        val (found, _, gaveUp) = walk(list, "row-30")
        assertFalse("the walk gave up before the end of the list: window=${list.window}", gaveUp)
        assertEquals(30, found)
    }

    // ------------------- the jump really names the plate ----------------
    // The assertion whose absence let the device defect through: the tests
    // before this one proved the BUTTON existed and that the Brain draws the
    // plate, and nothing proved the jump looked for the plate's own key.

    @Test
    fun `the Galaxy button's jump names the same key the plate is drawn under`() {
        val activity = repoFile(main + "MainActivity.kt").readText()
        val screen = repoFile(main + "ui/screens/BrainScreen.kt").readText()

        // What Home's Galaxy button asks for.
        val asked = activity.substringAfter("onOpenGalaxy = {").substringBefore("},")
        val section = Regex("pendingSection = \"([\\w-]+)\"")
            .find(asked)?.groupValues?.get(1)
        assertEquals("the Galaxy button does not name a section", "people-and-things", section)
        assertTrue(
            "the Galaxy button does not go to the Brain",
            asked.contains("Screen.BRAIN"),
        )

        // What the Brain will look for: the plate's own key, in the plate
        // namespace - the same string `PlateList.emit` writes as
        // `item(key = ...)`, and the same one `ScrollToKeyOnce` is handed.
        val jumpKey = PlateList.PLATE_PREFIX + section!!
        assertEquals("brain-plate:people-and-things", jumpKey)
        assertTrue(
            "BrainScreen does not look for the plate's own key",
            screen.contains("initialSection?.let { plateKeyAt(it) }"),
        )
        assertTrue(
            "BrainScreen's plateKeyAt does not use the plate namespace",
            screen.contains("fun plateKeyAt(name: String): String = PlateList.PLATE_PREFIX + name"),
        )

        // And the plate really is drawn under that key, from the menu guard -
        // so the jump has something to land on whenever the plate exists.
        assertTrue(
            "the Galaxy plate is not drawn, so the jump has nowhere to land",
            Regex("""if \(menus\.shows\("brain\.memory\.people-things"\)\) plate\("people-and-things"\)""")
                .containsMatchIn(screen),
        )

        // The heading that holds it is a real one, and one `toOpen` finds -
        // which is what turns the asked-for name into the heading to open.
        val heading = BrainSections.sectionOf(section)
        assertTrue("no heading holds the Galaxy plate, so nothing can open for it", heading != null)
        val key = BrainSections.toOpen(section)
        assertEquals("the heading that holds the plate is not the one that opens", heading!!.key, key)
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): java.io.File {
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = java.io.File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
