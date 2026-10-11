package com.jarvis.client

import com.jarvis.client.ui.screens.BrainSections
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Brain's headings, and the promise they have to keep: every plate is still
 * there (owner, 2026-10-10: "the brain on jarvis on the android phone is way
 * too long of a menu. Put different section headers, with a secondary menu
 * that opens for that item if i click on it").
 *
 * A heading that hides plates is the one change on this screen that can make
 * something *unreachable* rather than merely tidier, and no unit test can press
 * a button on a Compose screen. So this test does the next best thing, and does
 * it against the real sources rather than against a copy:
 *
 *  * [BrainSections.SECTIONS] is held to `BrainScreen.kt` both ways - every key
 *    it places is drawn by the screen, and every key the screen draws is either
 *    placed under a heading or is one of the few that must never be shut away
 *    ([BrainSections.ALWAYS_DRAWN]). A new plate added to the screen but not to
 *    a heading fails here, which is what "still reachable" means in practice.
 *  * the heading control itself is read for the three things requirement 4
 *    asks for: a real heading for a screen reader, the state in words, and no
 *    clipping ([maxLines] would cut a heading's count off on a narrow phone).
 *  * [BrainSections.Open] - the tap rule - is pinned, because "a section opens
 *    and closes" is the whole feature and its only JVM-testable half.
 */
class BrainSectionsTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"

    private val screen: String = repoFile(screens + "BrainScreen.kt").readText()

    /** The file the heading itself, and the rule that draws one, live in. */
    private val sections: String = repoFile(screens + "BrainSections.kt").readText()

    /** Every `item(key = "...")` the screen draws at the top level of its list. */
    private val itemKeys: Set<String> =
        Regex("item\\(key = \"([\\w-]+)\"\\)").findAll(screen).map { it.groupValues[1] }.toSet()

    /** Every `plate("...")` the screen draws inside a heading. */
    private val plateNames: Set<String> =
        Regex("\\bplate\\(\"([\\w-]+)\"\\)").findAll(screen).map { it.groupValues[1] }.toSet()

    // ------------------------------------------------------- the headings ---

    @Test
    fun `the headings exist, are unique, and are the ones the owner reads`() {
        val sections = BrainSections.SECTIONS
        assertTrue("Brain needs headings to be short: found ${sections.size}", sections.size in 4..8)
        assertEquals("a heading key is used twice", sections.size, sections.map { it.key }.toSet().size)
        assertEquals("a heading title is used twice", sections.size, sections.map { it.title }.toSet().size)
        for (s in sections) {
            assertTrue("${s.key} has no title", s.title.isNotBlank())
            assertTrue("${s.key} holds nothing", s.plates.isNotEmpty())
            // A heading is a phrase, not a sentence, and never jargon.
            assertTrue("${s.title} is too long for a heading", s.title.length <= 32)
        }
        // The order is the owner's: what waits on them, then what Jarvis knows,
        // then what it is doing, then money and time, then their own work, what
        // they are studying, then the machine. Pinned because the screen draws
        // them in this order by index (BrainSections.SECTIONS[i]), so a reorder
        // here must be a deliberate edit and not a silent swap.
        assertEquals(
            listOf("waiting", "knows", "doing", "money-time", "projects", "learning", "pc"),
            sections.map { it.key },
        )
    }

    @Test
    fun `every heading the section list names is drawn as an item on the screen`() {
        // Every index on the list is drawn, once each, and the screen draws
        // them in the list's own order. The screen reads
        // `BrainSections.SECTIONS[i]` and draws that heading, so a heading
        // added to the list but not drawn fails here.
        val drawn = Regex("brainSection\\(\\s*BrainSections\\.SECTIONS\\[(\\d+)\\]")
            .findAll(screen).map { it.groupValues[1].toInt() }.toList()
        assertEquals(
            "BrainScreen must draw each heading once, in the list's own order",
            BrainSections.SECTIONS.indices.toList(),
            drawn,
        )
        assertEquals("a heading is drawn twice", drawn.size, drawn.toSet().size)
        // ...and the screen asks this file which heading holds a key, rather
        // than carrying a second copy of the grouping of its own.
        assertTrue("the screen does not look a key's heading up", screen.contains("BrainSections.sectionOf("))
    }

    // ------------------------------------------------- every plate is there ---

    @Test
    fun `every plate still has a heading, and every heading names a real plate`() {
        val placed = BrainSections.allPlateKeys().toSet()
        assertEquals("a plate is placed under two headings", BrainSections.allPlateKeys().size, placed.size)

        // One way: a key a heading claims must really be drawn by the screen.
        // 2026-10-10: the screen draws its plates through `plate("...")` now, not
        // `item(key = "...")` - the crash was a plate key equal to its heading's,
        // and one receiver for both is what stops it - so the plate's own name is
        // what is looked for. `BrainListTest` holds those two lists equal, in
        // order, one for one.
        for (key in placed) {
            assertTrue("no plate(\"$key\") in BrainScreen.kt", key in plateNames)
        }

        // The other way: nothing the screen draws is left out of the headings,
        // except the few lines that must never be shut away.
        val always = BrainSections.ALWAYS_DRAWN.toSet()
        val unplaced = plateNames - placed
        assertTrue("Brain plates under no heading at all: $unplaced", unplaced.isEmpty())
        val unowned = itemKeys - always
        assertTrue("Brain items under no heading at all: $unowned", unowned.isEmpty())

        // Each key is counted once, so the "N inside" on a heading is the truth.
        for (s in BrainSections.SECTIONS) {
            assertEquals("${s.key} lists a key twice", s.plateKeys.size, s.plateKeys.toSet().size)
        }
    }

    @Test
    fun `the plates that must never be shut away are drawn outside every heading`() {
        // The rush latch is about outside text that tried to raise the tier: it
        // is the one adversarial thing on this screen and it may not be behind a
        // tap. The freshness line decides whether anything else can be trusted.
        // Both are drawn before the first heading... and the attention budget,
        // which cannot be hidden or folded at all, after the last one.
        val firstHeading = screen.indexOf("brainSection(")
        assertTrue("the first heading is not drawn", firstHeading > 0)
        for (key in listOf("rush", "freshness")) {
            val at = screen.indexOf("item(key = \"$key\")")
            assertTrue("$key is not drawn", at > 0)
            assertTrue("$key is inside the headings", at < firstHeading)
        }
        // The hidden-menus line, and the attention budget with it, are outside
        // them too - and, since 2026-10-10, at the BOTTOM of the list rather
        // than among the headings, so the collapsed screen is the seven headings
        // and then the two lines that must always be there.
        for (key in listOf("menus-hidden", "attention")) {
            val at = screen.indexOf("item(key = \"$key\")")
            assertTrue("$key is not drawn", at > 0)
            assertTrue(
                "$key must not be inside a heading",
                at > screen.lastIndexOf("brainSection("),
            )
        }
        // The attention budget cannot be put inside one at all: its menu can
        // never be hidden or folded, and AttentionSettingsTest asserts the
        // screen draws it with no `menus.shows` check.
        assertTrue(screen.contains("item(key = \"menus-hidden\")"))
        assertEquals(
            listOf("rush", "freshness", "notice", "attention", "menus-hidden", "tail"),
            BrainSections.ALWAYS_DRAWN,
        )
    }

    // ------------------------------------------------------- open and shut ---

    @Test
    fun `a heading opens when tapped and closes when tapped again`() {
        val open = BrainSections.Open()
        assertFalse("every heading starts shut", open.isOpen("knows"))
        assertNull("nothing is open to begin with", open.key)

        // Tap: it opens.
        open.toggle("knows")
        assertTrue("the tapped heading did not open", open.isOpen("knows"))
        assertEquals("knows", open.key)
        assertTrue("the tap was not remembered", open.seen)

        // Tap the same one again: it closes. This is the "closes" half, and
        // without it a heading could only ever be opened.
        open.toggle("knows")
        assertFalse("the heading did not close", open.isOpen("knows"))
        assertNull("closing must leave nothing open", open.key)

        // Tap a different one: the first closes, so the screen cannot grow back
        // into the long scroll the owner asked to be rid of.
        open.toggle("knows")
        open.toggle("pc")
        assertTrue(open.isOpen("pc"))
        assertFalse("the heading above stayed open too", open.isOpen("knows"))
    }

    @Test
    fun `a link into Brain opens the heading it lands in`() {
        // "open the morning briefing", "open the hardware" and the rest come in
        // as an item key (BrainScreen's `initialSection`). The heading holding
        // that key must start open, or the walk to the key would never find it -
        // the plate is not in the list while its heading is shut.
        for (key in listOf("briefing", "hardware", "second-card", "big-model", "capabilities", "spending", "topics", "forget-range")) {
            val section = BrainSections.sectionOf(key)
            assertTrue("no heading holds $key, so its link lands nowhere", section != null)
            assertEquals("$key's link would not open its heading", section!!.key, BrainSections.toOpen(key))
        }
        assertNull("no link asks for anything, so nothing opens", BrainSections.toOpen(null))
        assertNull("a key no heading holds opens nothing", BrainSections.toOpen("no-such-plate"))

        // Opening by a link is not a toggle: it never closes what is open.
        val open = BrainSections.Open()
        open.toggle("knows")
        open.open("pc")
        assertTrue("the link did not open its heading", open.isOpen("pc"))

        // And the screen really wires the link to it. The key it looks up carries
        // the plates' namespace (PlateList.PLATE_PREFIX): a plate's item key is
        // no longer the bare name, and a walk that looks a key up by equality has
        // to name the key the list really holds.
        assertTrue(
            "the screen does not open a heading for a link",
            screen.contains("ScrollToKeyOnce(") && screen.contains("initialSection?.let { plateKeyAt(it) }"),
        )
        // A jump from a link INSIDE a heading goes the same way: the "facts
        // kept, hidden" link under Saved automatically jumps to Topics.
        assertTrue(
            "a jump inside Brain does not open the heading it lands in",
            screen.contains("BrainSections.sectionOf(key)") &&
                screen.contains("ScrollToKeyOnce(listState, jumpTo?.let { plateKeyAt(it) }, onOpen ="),
        )
    }

    // --------------------------------------------- heading, and its state ---

    @Test
    fun `a heading is a real heading and says whether it is open in words`() {
        val body = functionBody(sections, "private fun BrainGroupHeading(")
        assertTrue("the heading is not announced as a heading", body.contains("heading()"))
        assertTrue(
            "the open or shut state is not in words",
            body.contains("stateDescription = if (open) \"Expanded\" else \"Collapsed\""),
        )
        // The state is drawn as a word as well, so it is not left to the
        // chevron's direction or to a colour.
        assertTrue("no word for open", body.contains("\"Fold\""))
        assertTrue("no word for shut", body.contains("\"Open\""))
        // The whole row is the target, at the 48dp minimum this app keeps.
        assertTrue("the heading row has no 48dp minimum", body.contains("heightIn(min = 48.dp)"))
        assertTrue("the heading row is not tappable", body.contains("pressable(onClick = onToggle)"))
        // And the chevron moves in the draw phase only, as every other
        // open/close mark in this app does (the FAQ's own note).
        assertTrue("the chevron does not turn", body.contains("animateFloatAsState("))
        assertTrue("the chevron is animated per frame", body.contains("graphicsLayer { rotationZ = turn }"))
    }

    @Test
    fun `no heading is clipped and the count is shown while it is shut`() {
        val body = functionBody(sections, "private fun BrainGroupHeading(")
        // A clipped label is a hidden label: the phone's largest font must be
        // able to wrap a heading rather than cut it off.
        assertFalse("a heading can be clipped", body.contains("maxLines"))
        assertFalse("a heading can be clipped", body.contains("TextOverflow"))
        assertTrue(
            "the count of what is inside is not drawn while the heading is shut",
            body.contains("if (!open && inside > 1)"),
        )
        assertTrue("the count is not said in words", body.contains("inside\""))
        // The count drawn is the count of what was emitted, never the length of
        // the declared list - the number that said "6 inside" over five plates.
        assertTrue("the count is not the measured one", body.contains("\"\$inside inside\""))
        assertFalse("the declared list's length is back on the heading", body.contains("plates.size"))
        // The heading's own hint is drawn only when it has one.
        assertTrue("the hint has no empty check", body.contains("section.hint.isNotEmpty()"))
    }

    /** The body of a top-level function, from its `fun` line to the line that closes it. */
    private fun functionBody(src: String, marker: String): String {
        val at = src.indexOf(marker)
        assertTrue("$marker is gone", at >= 0)
        val rest = src.substring(at)
        val end = rest.indexOf("\n}\n")
        return if (end > 0) rest.substring(0, end) else rest
    }

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
