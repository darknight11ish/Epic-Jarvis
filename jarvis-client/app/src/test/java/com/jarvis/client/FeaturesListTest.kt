package com.jarvis.client

import com.jarvis.client.net.Features
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Everything Jarvis can do" (docs/FEATURES-LIST-DESIGN.md, the owner's request
 * of 2026-10-08).
 *
 * The list is one file - `features/features.json` - copied into this app's
 * assets and fetched by the desktop page. `tools/check_feature_list.py` (run by
 * `backend/run_suites.py test_feature_list.py` in CI) is the check that matters:
 * it proves every route section and menu id the two apps draw is either named
 * by an entry or in its INTERNAL allow-list. This suite is the phone's half:
 *
 *   - the asset really parses, with [Features.readOf] - the exact code the
 *     screen runs, not a copy of it;
 *   - every entry answers the three questions the page promises (what, where,
 *     asks), and its `limit` is a string (empty when there is none);
 *   - the grouping is stable: the nine groups in the fixed order, every entry
 *     drawn exactly once, this app's own features first inside a group with the
 *     desktop's marked "on your PC";
 *   - the screen's row count equals the file's - held to FeaturesScreen.kt's
 *     own source, because a JVM test cannot compose a screen (the same way
 *     MenuVisibilityTest holds the menu list to the real screens' text);
 *   - this app's copy and the desktop's copy are byte-identical, so the two
 *     apps can never disagree about what a feature does.
 *
 * Pure JVM: no Android, no emulator. CI's Gradle build is the first compiler of
 * the screen itself.
 */
class FeaturesListTest {

    /** The repository root, found by walking up from the test's working directory. */
    private val repo: File = run {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null && !File(dir, "features/features.json").isFile) dir = dir.parentFile
        requireNotNull(dir) { "features/features.json not found above ${System.getProperty("user.dir")}" }
        dir
    }

    private val asset: File = File(repo, "jarvis-client/app/src/main/assets/features.json")
    private val desktopCopy: File = File(repo, "jarvis-desktop/src/features.json")
    private val source: File = File(repo, "features/features.json")
    private val screen: String =
        File(repo, "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FeaturesScreen.kt").readText()

    private val entries: List<Features.Entry> by lazy { Features.readOf(asset.readText()) }

    @Test
    fun `the asset parses, and it is the whole list`() {
        assertTrue("the asset is missing: $asset", asset.isFile)
        assertTrue("no entries were read", entries.isNotEmpty())
        // A readable length, not one row per route (the design note's own rule).
        assertTrue("only ${entries.size} entries", entries.size >= 60)
        assertTrue("${entries.size} entries", entries.size <= 120)
        assertEquals("an entry id is used twice",
            entries.size, entries.map { it.id }.toSet().size)
    }

    @Test
    fun `every entry has the four fields the page promises`() {
        for (e in entries) {
            assertTrue("${e.id}: no title", e.title.isNotBlank())
            assertTrue("${e.id}: no `what`", e.what.isNotBlank())
            assertTrue("${e.id}: no `where`", e.where.isNotBlank())
            assertTrue("${e.id}: no `asks`", e.asks.isNotBlank())
            // `limit` may be empty - that is how a feature with no real limit
            // says so, and the page then draws no limit line at all.
            assertTrue("${e.id}: unknown surface `${e.surface}`",
                e.surface in listOf(Features.DESKTOP, Features.PHONE, Features.BOTH))
        }
    }

    @Test
    fun `the grouping is stable and nothing is dropped`() {
        val rows = Features.rows(entries)
        assertEquals("a row was dropped or duplicated",
            entries.size, Features.featureCount(rows))
        // The nine groups, in the design's order, and no others (the
        // completeness test fails the build if the file invents a tenth).
        assertEquals(Features.GROUPS, Features.rows(entries)
            .filterIsInstance<Features.Row.Heading>().map { it.title })
        // Each heading's own count is the number of features under it.
        for ((i, row) in rows.withIndex()) {
            if (row !is Features.Row.Heading) continue
            var seen = 0
            var j = i + 1
            while (j < rows.size && rows[j] is Features.Row.Feature) {
                seen++
                j++
            }
            assertEquals("${row.title}'s count", row.count, seen)
        }
        // Every entry appears exactly once, under its own group.
        for (e in entries) {
            val mine = rows.filterIsInstance<Features.Row.Feature>().filter { it.entry.id == e.id }
            assertEquals("${e.id} is drawn ${mine.size} times", 1, mine.size)
            assertEquals(e.group, mine[0].entry.group)
        }
    }

    @Test
    fun `this app's own features come first, and the PC's are marked`() {
        // Within one group, every feature that is the PC's alone comes after
        // every feature this phone has (the design note's "each app shows its
        // own surface's features first").
        val perGroup = LinkedHashMap<String, MutableList<String>>()
        var current: String? = null
        for (row in Features.rows(entries)) {
            when (row) {
                is Features.Row.Heading -> {
                    current = row.title
                    perGroup[current] = mutableListOf()
                }
                is Features.Row.Feature -> perGroup.getValue(current!!).add(row.entry.surface)
            }
        }
        for ((group, surfaces) in perGroup) {
            val firstThePcs = surfaces.indexOf(Features.DESKTOP)
            val lastPhones = surfaces.lastIndexOf(Features.PHONE)
            if (firstThePcs >= 0 && lastPhones >= 0) {
                assertTrue("$group: a PC-only feature comes before this phone's own",
                    lastPhones < firstThePcs)
            }
        }
        // The marker beside the other app's rows, and on nothing else: this
        // phone's own features (and the ones both apps have) carry none.
        for (e in entries) {
            when (e.surface) {
                Features.DESKTOP -> assertEquals("on your PC", e.otherAppTag)
                Features.PHONE -> assertFalse("${e.id}: this phone's own feature is marked",
                    e.otherAppTag.isNotEmpty())
                else -> assertFalse("${e.id}: a 'both' feature is marked", e.otherAppTag.isNotEmpty())
            }
        }
        assertTrue("nothing on this list belongs to the PC alone - check the sort",
            entries.any { it.surface == Features.DESKTOP })
    }

    @Test
    fun `the screen draws one row per feature, from the same file`() {
        // The screen must draw the rows [Features.rows] builds, in order, one
        // composable each - not a second list of its own that could drift.
        assertTrue("FeaturesScreen does not draw the rows Features.rows builds",
            screen.contains("items(drawn"))
        assertTrue("FeaturesScreen does not draw one card per Feature row",
            screen.contains("is Features.Row.Feature -> FeatureCard("))
        assertTrue("FeaturesScreen does not draw the group headings",
            screen.contains("is Features.Row.Heading -> FeatureHeading("))
        assertTrue("FeaturesScreen does not read the asset this test reads",
            screen.contains("Features.ASSET"))
        assertTrue("FeaturesScreen does not use the shared parser",
            screen.contains("Features.readOf(text)"))
        assertTrue("FeaturesScreen does not use the shared row builder",
            screen.contains("Features.rows(Features.readOf(text))"))
        // And a feature with no limit draws no limit line (featureCount above
        // is the file's own count, so a dropped or doubled row fails there).
        assertTrue("FeaturesScreen draws a limit line with no emptiness check",
            screen.contains("if (entry.limit.isNotEmpty()) FeatureField(\"One limit\""))
    }

    @Test
    fun `the phone's copy and the desktop's copy are one file`() {
        assertEquals("the asset and the source differ",
            source.readText(), asset.readText())
        assertEquals("the asset and the desktop's copy differ",
            desktopCopy.readText(), asset.readText())
    }
}
