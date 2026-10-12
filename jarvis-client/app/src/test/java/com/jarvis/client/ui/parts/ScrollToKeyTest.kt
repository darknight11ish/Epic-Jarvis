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
     * A stand-in for a `LazyListState` - and it has to model the part that
     * caused the 2026-10-11 defect: **`totalItemsCount` is what the list has
     * COMPOSED, not how long it is.**
     *
     * [rows] is the whole list. [composedTo] is the last index the list knows
     * about; a real list grows it when it is scrolled past, so [window]'s own
     * movement does the same here. A fake with a fixed `total` cannot tell a
     * walk that reached the END OF THE LIST from one that reached the end of
     * what had been composed - which is the entire defect, so the fake has to
     * be able to represent it.
     */
    private class FakeList(
        val keys: List<String>,
        var composedTo: Int = 0,
        var window: IntRange = 0..0,
        /** How far past the viewport the list composes ahead of it. */
        val buffer: Int = 4,
    ) {
        val firstVisibleIndex: Int get() = window.first
        /** What the list reports it knows about, exactly like `totalItemsCount`. */
        val total: Int get() = (composedTo + 1).coerceAtMost(keys.size)
        /** Whether the whole list is composed - the only state where "the end" is the end. */
        val everythingComposed: Boolean get() = total >= keys.size
        /** The list composes more as its window moves down - and never forgets. */
        fun composedOnWindow() {
            composedTo = maxOf(composedTo, window.last + buffer).coerceAtMost(keys.size - 1)
        }
        override fun toString() = "keys=${keys.size} composed=$total window=$window"
    }

    /**
     * Runs [walkStep] frame by frame over [list] and returns (final index, the
     * decisions, whether the walk stopped early).
     *
     * It moves the window the way the real walk does, and lets the fake list
     * compose ahead of it - so a test can assert about a walk on a list that is
     * still growing, which is the case the device hit.
     */
    private fun walk(
        list: FakeList,
        key: String,
        onFrame: (Int, FakeList) -> Unit = { _, _ -> },
    ): Triple<Int?, List<Walk>, Boolean> {
        var index: Int? = null
        var steps = 0
        var waited = 0
        var advances = 0
        var lastTotal = -1
        val decisions = ArrayList<Walk>()
        var frame = 0
        while (steps < 60 && frame < 400) {
            onFrame(frame, list)
            if (list.total != lastTotal) {
                lastTotal = list.total
                advances = 0
            }
            val window = list.window.intersect(0 until list.total)
            val decision = walkStep(
                key = key,
                firstVisibleIndex = list.firstVisibleIndex,
                totalItemsCount = list.total,
                visibleKeys = window.map { list.keys[it] },
                visibleIndexes = window.toList(),
                waited = waited,
                advances = advances,
                listSize = list.keys.size,
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
                    list.composedOnWindow()
                }
                Walk.Wait -> waited++
                Walk.Advance -> {
                    advances++
                    waited = 0
                    val next = (list.window.last + 1).coerceAtMost(list.keys.size - 1)
                    list.window = (next..(next + list.window.count() - 1))
                        .let { it.first..it.last.coerceAtMost(list.keys.size - 1) }
                    list.composedOnWindow()
                }
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
        val list = FakeList(keys, composedTo = keys.size - 1, window = 0..3)
        val (found, decisions, gaveUp) = walk(list, "brain-plate:people-and-things") { frame, l ->
            if (frame == 2) {
                // Opening the heading: the plate appears, and the count grows.
                @Suppress("UNCHECKED_CAST")
                (l.keys as ArrayList<String>).add("brain-plate:people-and-things")
                l.composedTo = keys.size - 1
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
        val list = FakeList(keys, composedTo = keys.size - 1, window = 0..3)
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
        val list = FakeList(keys, composedTo = keys.size - 1, window = 0..5)
        val (found, _, gaveUp) = walk(list, "row-30")
        assertFalse("the walk gave up before the end of the list: window=${list.window}", gaveUp)
        assertEquals(30, found)
    }

    @Test
    fun `a walk that misses on the first pass finds the item on the second`() {
        // The device's own shape, on a list this test controls: the first pass
        // runs while the holder is still SHUT, so it walks to the bottom and
        // misses. `ScrollToKeyOnce` then opens the holder once more, goes back
        // to the top and walks again - and only that second pass has the plate
        // in it. This is the half a green suite could not see: "opened" and
        // "laid out" are different frames (2026-10-11).
        val keys = ArrayList(listOf("head-a", "head-b", "tail"))
        val list = FakeList(keys, composedTo = keys.size - 1, window = 0..2)

        val first = walk(list, "brain-plate:people-and-things")
        assertTrue("the first pass was expected to miss: $first", first.third)
        assertEquals(null, first.first)

        // The retry: the holder opens, the plate is added, the list is walked
        // again from the top.
        @Suppress("UNCHECKED_CAST")
        (list.keys as ArrayList<String>).add("brain-plate:people-and-things")
        list.composedTo = keys.size - 1
        list.window = 0..2
        val second = walk(list, "brain-plate:people-and-things")
        assertFalse("the retry did not find the plate: $second", second.third)
        assertEquals(3, second.first)
        assertEquals("brain-plate:people-and-things", list.keys[second.first!!])
    }

    @Test
    fun `a plate the screen never draws lands the jump on its heading instead of the bottom`() {
        // The other half of the device's question: when the plate is genuinely
        // not in the list - its menu hidden by the owner, or the other of a
        // pair - no amount of walking puts it there. The walk for the plate
        // ends at the bottom, and the HEADING, which is drawn either way, is
        // what the jump must land on. Without it the screen was left on the
        // attention budget, the last item in Brain's list.
        val keys = listOf("brain-heading:waiting", "brain-plate:memory", "brain-heading:knows", "brain-plate:attention", "brain-plate:tail")
        val list = FakeList(keys, composedTo = keys.size - 1, window = 0..2)

        // The plate is nowhere in this list, so its own walk has nothing to find.
        val miss = walk(list, "brain-plate:people-and-things")
        assertTrue(
            "the plate's walk was expected to miss, and it did not: $miss",
            miss.first == null,
        )

        // The fallback: walk the heading that holds it, from the top.
        // A FRESH list for the heading walk: the first `walk` moved this one's
        // window and made it compose, so walking the same instance again starts
        // from wherever the failed search stopped - which is precisely the state
        // a fallback must not be tested from.
        val forHeading = FakeList(keys, composedTo = keys.size - 1, window = 0..2)
        val (found, _, gaveUp) = walk(forHeading, "brain-heading:knows")
        assertFalse("the heading was not found either: $gaveUp", gaveUp)
        assertEquals(2, found)
        assertEquals("brain-heading:knows", list.keys[found!!])
    }

    @Test
    fun `a walk reaches an item the list has not composed yet`() {
        // THE DEVICE DEFECT OF 2026-10-11, and the one the old fake could not
        // express. The trace read `first=6 last=10 composed=11 walk=Wait` on
        // fourteen consecutive frames and then `GiveUp`: the walk saw
        // `last >= composed - 1`, called it the end of the list, and waited for
        // ever - because a `LazyList` only composes more when it is SCROLLED, and
        // nothing had asked it to. The item was several sections further down.
        //
        // The baseline line proved it: `composed=11` before AND after, while the
        // window moved six rows. A real end of list does not let you scroll past
        // it.
        //
        // Forty rows, only the first six composed, and the item at index 30.
        val keys = (0 until 40).map { "row-$it" }
        val list = FakeList(keys, composedTo = 5, window = 0..5)

        val (found, decisions, gaveUp) = walk(list, "row-30")
        assertFalse(
            "the walk gave up on a list it had never asked to compose more of: " +
                "decisions=${decisions.takeLast(5)}",
            gaveUp,
        )
        assertEquals("the walk landed on the wrong row", 30, found)
        assertTrue(
            "the walk never asked the list for more rows, so it could only have been lucky: " +
                "decisions=$decisions",
            decisions.contains(Walk.Advance),
        )
    }

    @Test
    fun `a jump that knows what holds its item asks to land on the holder first`() {
        // THE DEVICE'S FOURTH VARIANT (2026-10-11, found by the lead on build
        // 0.2.1232). The log said `initiallyOpen=money-time openKey=money-time`:
        // the holder was ALREADY OPEN, so opening it did nothing, and the item
        // inside it was never reached. The walk that followed looked at the rows
        // composed when it ran - and the section's plates were still being
        // composed, so every row added ABOVE the item moved it further down and
        // the index aimed at was the one from before those rows existed.
        //
        // The rule that removes the whole class is a PURE one, so it is tested
        // here rather than described: a jump that knows of a holder lands on the
        // holder FIRST, whatever state the list is in. Anchoring stops the rows
        // above the item from growing, so the walk that follows runs against a
        // list that no longer moves under it.
        //
        // This is the assertion whose absence let the defect through: the tests
        // before it proved a SHUT holder is opened, and nothing proved anything
        // about an OPEN one.
        assertEquals(
            "a jump with a holder must land on the holder first, open or shut",
            "brain-heading:money-time",
            landingOrder(target = "brain-plate:coming-up", holder = "brain-heading:money-time").first(),
        )
        assertEquals(
            "the item itself is still what the jump is for",
            "brain-plate:coming-up",
            landingOrder(target = "brain-plate:coming-up", holder = "brain-heading:money-time").last(),
        )
        // With no holder known, the item is the only stop - the shape every
        // screen without headings uses.
        assertEquals(
            listOf("brain-plate:coming-up"),
            landingOrder(target = "brain-plate:coming-up", holder = null),
        )
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
        // so the jump has something to land on whenever the plate exists. It
        // asks to be drawn whatever the private-lists rule says too: with the
        // lists hidden, the heading's own rule would drop it, and "drawn
        // somewhere the walk can find" is exactly what the walk needs.
        val call = screen.substringAfter("""if (menus.shows("brain.memory.people-things"))""")
        assertTrue(
            "the Galaxy plate is not drawn, so the jump has nowhere to land",
            Regex("""\bplate\(\s*"people-and-things"\s*[,)]""").containsMatchIn(call),
        )
        assertTrue(
            "the Galaxy plate is dropped when the lists are hidden, so the walk finds no item",
            call.substringBefore(") {").contains("drawn = { true }"),
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


