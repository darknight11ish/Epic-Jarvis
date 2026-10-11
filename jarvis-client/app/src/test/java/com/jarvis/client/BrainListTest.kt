package com.jarvis.client

import androidx.compose.foundation.lazy.LazyItemScope
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.runtime.Composable
import com.jarvis.client.ui.screens.BrainSections
import com.jarvis.client.ui.screens.PlateList
import com.jarvis.client.ui.screens.brainSection
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The three promises Brain's headings make when the owner taps one, held on a
 * plain JVM against the REAL list the screen builds:
 *
 *  1. **Two items in one list never share a key.** A LazyColumn with a repeated
 *     key throws - `Key "doing" was already used` - and on 2026-10-10 that
 *     killed the app on two of the seven headings. 2,108 green tests did not
 *     catch it, because every one of them read the screen's text instead of
 *     building its list. This one builds the list.
 *  2. **A heading's plates are drawn between it and the next heading.** The
 *     first build put them at the bottom of the list, under "Jarvis on your PC",
 *     however far down the tapped heading was.
 *  3. **"N inside" is what the tap will show.** The first build showed the length
 *     of a declared list, so "Money and time" said 6 and drew 5.
 *
 * None of that is checked against a hand-written copy of the screen's items.
 * [brainSection] is the screen's own function, called here with the keys the
 * screen's own `plate("...")` lines write; [FakeList] is the only thing standing
 * in for the lazy list, and it records rather than draws. `BrainSectionsTest`
 * holds those `plate("...")` lines to this file's declared lists, so the two
 * halves meet: the keys are the screen's, and the list is the list.
 */
class BrainListTest {

    // ------------------------------------------------------------- the keys ---

    /**
     * The whole list, built the way the screen builds it: section after section,
     * each heading followed by its own plates while it is open, then the items
     * that live outside every heading.
     */
    private fun brainList(open: String? = null, allOpen: Boolean = false): FakeList {
        val list = FakeList()
        // The recorder is proved to receive items before it is trusted to say
        // anything about them: a fake that silently swallowed every key would
        // make every assertion below pass on a broken screen.
        list.scope.item("RECORDER-SELFTEST") {}
        assertEquals(
            "the test's own LazyListScope does not receive item keys, so nothing below is evidence",
            listOf("RECORDER-SELFTEST"),
            list.keys(),
        )
        list.reset()
        val drewWhat = LinkedHashMap<String, List<String>>()
        for (section in BrainSections.SECTIONS) {
            val isOpen = allOpen || section.key == open
            val drawn = ArrayList<String>()
            list.scope.brainSection(
                section = section,
                open = isOpen,
                onToggle = {},
                plates = { if (isOpen) declaredPlates(section.key) },
                drawn = drawn,
            )
            drewWhat[section.key] = drawn
        }
        for (key in BrainSections.ALWAYS_DRAWN) list.scope.item(key = key) {}
        // THE list, whole, and first: a key used twice is the crash itself,
        // whether the two items are a heading and its own plate (which is what
        // happened on 2026-10-10) or a plate and a plate. Checked before anything
        // about any one plate, because the collision is the thing that killed the
        // app and the thing this file exists to catch.
        val seenKeys = HashSet<String>()
        val twice = list.keys().filter { !seenKeys.add(it) }.distinct()
        assertTrue(
            "two items of one LazyColumn share a key: $twice - this is the exception " +
                "(java.lang.IllegalArgumentException: Key \"doing\" was already used) that killed " +
                "the app on 2026-10-10",
            twice.isEmpty(),
        )
        // Then, per heading: a shut one draws nothing (which is what makes the
        // screen seven rows) and an open one draws exactly what it declares -
        // which is also what catches a plate that escaped into the enclosing list
        // instead of being drawn, `drawn` being what was written and the recorder
        // what was placed.
        for (section in BrainSections.SECTIONS) {
            val isOpen = allOpen || section.key == open
            assertEquals(
                "${section.key} drew the wrong plates (open=$isOpen)",
                if (isOpen) BrainSections.platesOf(section.key).map { it.key } else emptyList(),
                drewWhat.getValue(section.key),
            )
        }
        // And every plate reached the list under the key the screen's own
        // `plateKeyAt` looks up: a plate drawn under a key nothing can find is a
        // plate no link, no jump and no walk ever lands on.
        for (section in BrainSections.SECTIONS.filter { allOpen || it.key == open }) {
            for (plate in section.plateKeys) {
                val key = PlateList.PLATE_PREFIX + plate
                assertTrue(
                    "the plate \"$plate\" was not drawn under \"$key\" (${section.key} was open); " +
                        "the list holds ${list.keys()}",
                    key in list.keys(),
                )
            }
        }
        return list
    }

    /**
     * The plates one heading draws, written the way `BrainScreen` writes them: one
     * `plate("...")` per declared plate, in the declared order.
     *
     * This is the ONLY thing this test file puts in for the screen's own plate
     * lines, and `BrainSectionsTest` holds those two lists equal - every declared
     * key must have a `plate("...")` line in the screen, in this order.
     */
    private fun PlateList.declaredPlates(section: String) {
        for (plate in BrainSections.platesOf(section)) plate(plate.key) {}
    }

    // -------------------------------------------- 1. no two keys are the same ---

    @Test
    fun `no two items of Brain's list share a key, however many headings are open`() {
        // First and on its own, with every heading open: the state in which a
        // plate's key and its own heading's would meet. `brainList` checks the
        // whole list for a repeated key as it builds, so this call is the crash
        // check - and it is made before the per-heading states below, so a
        // screen with two items sharing a key reports the collision and not
        // something else about the same broken screen.
        val all = brainList(allOpen = true).keys()
        val seen = HashSet<String>()
        val twice = all.filter { !seen.add(it) }.distinct()
        assertTrue(
            "two items of one LazyColumn share a key with every heading open: $twice - this is the " +
                "exception (java.lang.IllegalArgumentException: Key \"doing\" was already used) that " +
                "killed the app on 2026-10-10",
            twice.isEmpty(),
        )
        // Every heading shut, and then each one alone - the two states the owner
        // meets on a cold start and on a tap.
        for (state in listOf<Pair<String?, Boolean>>(null to false) +
            BrainSections.SECTIONS.map { it.key to false }) {
            val (open, allOpen) = state
            val keys = brainList(open, allOpen).keys()
            assertEquals(
                "the count of keys is not the count of items",
                BrainSections.SECTIONS.size + BrainSections.ALWAYS_DRAWN.size +
                    (if (open != null) BrainSections.platesOf(open).size else 0),
                keys.size,
            )
        }
    }

    @Test
    fun `a heading's key can never be a plate's key`() {
        // The crash was one heading whose key equalled its first plate's key. The
        // two namespaces are what stop it coming back, so they are pinned: every
        // heading is drawn under a prefixed key, every plate under another, and
        // no declared plate may be named like a heading.
        val drawing = code(source(BRAIN_SECTIONS))
        assertTrue(
            "the heading row is not drawn under its own namespaced key",
            drawing.contains("item(key = BrainSections.headingKey(section))"),
        )
        assertTrue(
            "the plates are not emitted through the one recorder",
            drawing.contains("internal fun LazyListScope.brainSection(") &&
                drawing.contains("plateList.emit(plates, drawn)"),
        )
        for (section in BrainSections.SECTIONS) {
            val heading = BrainSections.headingKey(section)
            assertTrue("$heading is not a prefixed heading key", heading.startsWith(BrainSections.HEADING_PREFIX))
            for (key in section.plateKeys) {
                val plate = PlateList.PLATE_PREFIX + key
                assertFalse("$heading and $plate are the same key", heading == plate)
            }
        }
        // A plate named like a heading is refused at the door, not renamed later.
        assertThrows(IllegalArgumentException::class.java) {
            BrainSections.checkPlateName(BrainSections.HEADING_PREFIX + "impostor")
        }
        // ...and an ordinary plate name is not refused, so the rule is the
        // namespace and not "nothing may be called doing".
        BrainSections.checkPlateName("doing")
    }

    // ------------------------------------- 2. plates open under their heading ---

    @Test
    fun `every plate under a heading is drawn between it and the next heading`() {
        val keys = brainList(allOpen = true).keys()
        val headingAt = BrainSections.SECTIONS.map { BrainSections.headingKey(it) }
            .associateWith { keys.indexOf(it) }
        for (section in BrainSections.SECTIONS) {
            val at = headingAt.getValue(BrainSections.headingKey(section))
            assertTrue("${section.key} was not drawn", at >= 0)
            for (plate in section.plateKeys) {
                val plateAt = keys.indexOf(PlateList.PLATE_PREFIX + plate)
                assertTrue("$plate was not drawn at all", plateAt >= 0)
                assertTrue(
                    "$plate is drawn ABOVE its own heading (${section.key})",
                    plateAt > at,
                )
                val next = keys.drop(at + 1).firstOrNull { it in headingAt.keys }
                if (next != null) {
                    assertTrue(
                        "$plate is drawn outside its heading: it sits at $plateAt, past $next at " +
                            "${keys.indexOf(next)}. The first build put every plate at the BOTTOM of the " +
                            "list, under the last heading, which is this failure.",
                        plateAt < keys.indexOf(next),
                    )
                }
            }
            // And a shut heading draws no plates at all.
            val shut = brainList(open = null).keys()
            for (plate in section.plateKeys) {
                assertFalse(
                    "$plate is drawn while every heading is shut",
                    shut.contains(PlateList.PLATE_PREFIX + plate),
                )
            }
        }
    }

    // ------------------------------------------------ 3. the count is the truth ---

    @Test
    fun `a heading's N inside is the number of plates it really emits`() {
        // The screen's own count: what brainSection returns is the size of the
        // `drawn` list it filled, and the heading is handed the count the
        // recorder holds - never a declared list's length.
        val drawing = code(source(BRAIN_SECTIONS))
        assertTrue(
            "the heading is no longer given the count of what was emitted",
            drawing.contains("inside = plateList.keys.size"),
        )
        for (banned in listOf("inside = measured.size", "inside = section.plates.size")) {
            assertFalse(
                "the heading is drawn with $banned again: a declared list, or a count taken " +
                    "before the plates were written, is the number that lied",
                drawing.contains(banned),
            )
        }
        // And the number is the one the plates add up to, per heading - and it is
        // the SAME number whether the heading is open or shut, which is what the
        // count is for: a shut heading draws no plates, so a count taken only
        // while it was open would be zero on the very screen it exists for.
        for (section in BrainSections.SECTIONS) {
            val open = ArrayList<String>()
            val counted = FakeList().scope.brainSection(
                section = section,
                open = true,
                onToggle = {},
                plates = { declaredPlates(section.key) },
                drawn = open,
            )
            val plates = BrainSections.platesOf(section.key).map { it.key }
            assertEquals("${section.key}: what it counted is not what it drew", plates, open)
            assertEquals("${section.key}: the count and the drawn plates disagree", plates.size, counted)
            val shut = ArrayList<String>()
            val countedShut = FakeList().scope.brainSection(
                section = section,
                open = false,
                onToggle = {},
                plates = { declaredPlates(section.key) },
                drawn = shut,
            )
            assertEquals("${section.key}: a shut heading drew something", emptyList<String>(), shut)
            assertEquals("${section.key}: a shut heading returned a count of what it drew", 0, countedShut)
        }
        // The heading that lied on the phone: "6 inside" over five plates. Its
        // declared list is still six - the screen's items are unchanged - but the
        // number drawn comes from what is emitted, so it cannot be six again
        // while a pair of plates draws one of itself.
        assertEquals(
            "Money and time's plates changed; the count must still be measured, not declared",
            6, BrainSections.platesOf("money-time").size,
        )
        // The count is worked out whether the heading is OPEN or SHUT, and this
        // is the second half of the rule - it was added because the PHONE caught
        // the first version of this fix: it measured the plates only while the
        // heading was open, so every shut heading drew a count of ZERO, which is
        // the one number the count exists for. A heading that is shut draws no
        // plates, so the measure pass may not be behind `if (open)`.
        assertTrue(
            "the plates are no longer written before the heading's own row, so a shut heading " +
                "cannot know its count and will draw \"0 inside\"",
            drawing.contains("plateList.write(plates)"),
        )
        assertFalse(
            "the count is worked out behind a condition again: a shut heading draws no plates, " +
                "so it would show \"0 inside\" - which is what the phone caught",
            Regex("if \\(open\\)[^\\n]*plateList\\.write").containsMatchIn(drawing) ||
                Regex("plateList\\.write\\(plates\\)[^\\n]*else").containsMatchIn(drawing),
        )
        assertTrue(
            "the heading is not handed the recorder's own count",
            drawing.contains("inside = plateList.keys.size"),
        )
        // And the number a shut heading shows is the number its plates add up to,
        // which is the same number its open state draws - checked by writing the
        // screen's own plates and reading the recorder back.
        for (section in BrainSections.SECTIONS) {
            val open = ArrayList<String>()
            FakeList().scope.brainSection(
                section = section,
                open = true,
                onToggle = {},
                plates = { declaredPlates(section.key) },
                drawn = open,
            )
            assertEquals(
                "${section.key}: what the screen writes for it is not what it declares",
                section.plateKeys, open,
            )
            assertTrue("${section.key} would draw no count", section.plateKeys.isNotEmpty())
        }
    }

    // ------------------------------------------- 4. outside every heading, always ---

    @Test
    fun `every always-drawn id is outside every heading, in every state of the screen`() {
        for (open in listOf<String?>(null) + BrainSections.SECTIONS.map { it.key }) {
            val keys = brainList(open = open).keys()
            val headingKeys = BrainSections.SECTIONS.map { BrainSections.headingKey(it) }
            val lastHeading = keys.indexOfLast { it in headingKeys }
            for (key in BrainSections.ALWAYS_DRAWN) {
                assertTrue("$key is not drawn at all", key in keys)
                assertTrue(
                    "$key is drawn INSIDE a heading: it sits at ${keys.indexOf(key)}, before the " +
                        "last heading at $lastHeading. Its menu can never be hidden or folded, so it " +
                        "may not be behind a heading that can be shut.",
                    keys.indexOf(key) > lastHeading,
                )
                assertFalse("$key is a heading of its own", key in headingKeys)
            }
            // The attention budget, named: the one that was inside "What Jarvis
            // is doing" - one of the two headings that crashed - and so was both
            // missing from the shut screen and unreachable. Its key carries the
            // plates' namespace, like every line outside a heading since
            // 2026-10-11, because the walk a link into Brain runs looks a key up
            // by exact equality and cannot find a bare one.
            val attention = PlateList.PLATE_PREFIX + "attention"
            assertTrue("the attention budget is gone from Brain", attention in keys)
            assertEquals("the attention budget is drawn twice", 1, keys.count { it == attention })
        }
        // It has no menu check, which is why it cannot be put behind one.
        val screen = code(source(BRAIN))
        assertFalse(
            "the attention budget is behind a hideable menu again",
            screen.contains("menus.shows(\"brain.now.budget\")"),
        )
    }

    /**
     * The screen's OWN list: the always-drawn ids are emitted at the top level of
     * it, and every heading and plate lives inside a `brainSection(...)` call.
     *
     * This is the source half of the test above. It has to be here as well as
     * there because the driver can only record the plates the screen is DECLARED
     * to draw: put `plate("attention")` back inside "What Jarvis is doing" and the
     * driver would still emit its own correct list, while the screen quietly
     * stopped drawing the budget at the top. Reading the screen's own text is what
     * catches that, and it is checked by character offset, so a wider
     * `brainSetting(` or a shorter one cannot make the check pass by accident.
     */
    @Test
    fun `the screen emits the always-drawn ids outside its heading calls`() {
        // CODE, not the raw text: a plate name quoted in a comment - the pair
        // spelling in BrainScreen's own notes - would otherwise read as a plate
        // drawn inside a heading.
        val screen = code(source(BRAIN))
        val calls = sectionCalls(screen)
        assertEquals("BrainScreen's heading calls moved", BrainSections.SECTIONS.size, calls.size)
        for (key in BrainSections.ALWAYS_DRAWN) {
            // The key is the FULL item key (`brain-plate:<name>`), and this is
            // the line the owner's defect came from: while the screen drew a bare
            // `item(key = "attention")` and the walk looked up
            // `brain-plate:attention`, "Attention budget" in Find anything found
            // nothing. A bare key is therefore not accepted here.
            val name = key.removePrefix(PlateList.PLATE_PREFIX)
            assertTrue(
                "no item(key = plateKeyAt(\"$name\")) of its own in BrainScreen.kt, so nothing " +
                    "can find the line the list holds as \"$key\"",
                screen.contains("item(key = plateKeyAt(\"$name\"))"),
            )
            assertFalse(
                "the plate \"$name\" was put under a heading: always-drawn ids may not be inside a " +
                    "brainSection( call, because a heading can be shut. attention was inside " +
                    "\"What Jarvis is doing\" on 2026-10-10, and that heading was one of the two " +
                    "that crashed when tapped.",
                calls.any { call -> screen.substring(call.first, call.last).contains("plate(\"$name\")") },
            )
        }
        // The other way: every plate really is inside a heading's call, so no
        // plate can fall out of one and float at the top of the list either.
        for (section in BrainSections.SECTIONS) {
            for (plate in section.plateKeys) {
                // A pair is written as one plate that names both halves, so the
                // half that is not named first may not appear as `plate("...")`.
                val at = listOf("plate(\"$plate\")", "plateDrawn(\"$plate\")", "\"$plate\"")
                    .map { screen.indexOf(it) }.firstOrNull { it > 0 } ?: -1
                assertTrue("$plate is not drawn", at > 0)
                assertTrue(
                    "$plate is drawn outside every heading's call",
                    calls.any { call -> at > call.first && at < call.last },
                )
            }
        }
    }

    // ------------------------------------------ the screen's lines and the spec ---

    /**
     * Every `plate(...)` written in [body], in source order: the plate names it
     * covers, and the text that decides it (its own line, and the line before it,
     * where an `if (menus.shows("id"))` lives).
     *
     * The names are read from the plate's OWN block - from its `plate(` to the
     * brace that closes its body - so the three PAIRS come out as the two names
     * they are. `wiki` and `wiki-hidden` (and `memory`, and `memory-as-of`) are
     * ONE plate with two names, because exactly one of them is ever drawn:
     *
     * ```
     * plate("wiki") {
     *     if (privateHidden) { the hidden line } else { the wiki }
     * }
     * ```
     *
     * and it names the other half through `plateDrawn`, the same rule the heading
     * is handed - so a shut heading's count can never promise a plate the open
     * state does not draw.
     */
    private fun plateLines(body: String): List<Pair<Set<String>, String>> {
        val lines = body.lines()
        val out = ArrayList<Pair<Set<String>, String>>()
        var i = 0
        while (i < lines.size) {
            // A lone plate is `plate("name")`; the three PAIRS are one plate that
            // names both halves, `plate(if (plateDrawn("wiki")) "wiki" else
            // "wiki-hidden")`, so both spellings start a plate.
            val direct = Regex("\\bplate\\(\"([\\w-]+)\"\\)").find(lines[i])
            val paired = Regex("\\bplate\\(if \\(plateDrawn\\(\"([\\w-]+)\"\\)\\) \"([\\w-]+)\" else \"([\\w-]+)\"\\)")
                .find(lines[i])
            if (direct == null && paired == null) {
                i++
                continue
            }
            // The plate's own block, by brace depth, so the pair's `plateDrawn`
            // and its hidden name are read and the NEXT plate's are not.
            val block = StringBuilder(lines[i])
            var depth = lines[i].count { it == '{' } - lines[i].count { it == '}' }
            var j = i
            while (depth > 0 && j + 1 < lines.size) {
                j++
                block.append('\n').append(lines[j])
                depth += lines[j].count { it == '{' } - lines[j].count { it == '}' }
            }
            val text = block.toString()
            val names = linkedSetOf<String>()
            if (paired != null) {
                names.add(paired.groupValues[2])
                names.add(paired.groupValues[3])
            } else {
                names.add(direct!!.groupValues[1])
            }
            // The other half of a pair, where the plate names it inside its body.
            Regex("\"([\\w-]+)-hidden\"").findAll(text).forEach { names.add("${it.groupValues[1]}-hidden") }
            Regex("plateDrawn\\(\"([\\w-]+)\"\\)").findAll(text).forEach { names.add(it.groupValues[1]) }
            val guard = (if (i > 0) lines[i - 1] + "\n" else "") + lines[i]
            out.add(names to guard)
            i = j + 1
        }
        return out
    }

    @Test
    fun `the screen draws exactly the plates each heading declares, in order`() {
        // CODE, not the raw text: the pair spelling is quoted in the screen's own
        // comments, and reading those as code counted each pair twice.
        val screen = code(source(BRAIN))
        for (section in BrainSections.SECTIONS) {
            val body = sectionBody(screen, section)
            // One plate per NAME, in the order the names are written: a pair is two
            // names carried by one plate, and both are declared, so both appear in
            // the order the spec has them.
            val drawn = plateLines(body).flatMap { (names, _) ->
                names.filter { it in section.plateKeys }.sortedBy { section.plateKeys.indexOf(it) }
            }
            assertEquals(
                "${section.key}: the plates the screen draws are not the ones declared for it",
                section.plateKeys, drawn,
            )
        }
    }

    @Test
    fun `every declared plate is drawn only when the menu it names is shown`() {
        // A declared guard is a promise about the screen: the plate is behind
        // exactly that `menus.shows(...)`. The pairs are the exception: their two
        // halves share ONE guard, which sits on the plate that names them both.
        val screen = code(source(BRAIN))
        for (section in BrainSections.SECTIONS) {
            val body = sectionBody(screen, section)
            val written = plateLines(body)
            for (plate in section.plates) {
                val call = written.filter { plate.key in it.first }
                assertEquals("${plate.key} is drawn more than once", 1, call.size)
                val text = call.single().second
                val paired = PAIRS.any { (a, b) -> a in call.single().first && b in call.single().first }
                if (plate.guard != null && !paired) {
                    assertTrue(
                        "${plate.key} is no longer behind menus.shows(\"${plate.guard}\")",
                        text.contains("menus.shows(\"${plate.guard}\")"),
                    )
                }
                if (plate.guard == null && !paired) {
                    assertFalse(
                        "${plate.key} declares no menu, but the screen hides it behind one",
                        text.contains("menus.shows("),
                    )
                }
            }
        }
    }

    @Test
    fun `the screen says which of a pair it draws, so a count can be right`() {
        // The three pairs, and the reason this test exists: the phone read
        // "10 inside" over a heading that draws 7, because a shut heading counted
        // BOTH of every pair. A pair is ONE plate that names both of its names and
        // chooses with `plateDrawn` - the same rule the heading is handed.
        val screen = code(source(BRAIN))
        for ((a, b) in PAIRS) {
            val pairs = plateLines(screen).filter { a in it.first && b in it.first }
            assertEquals("$a and $b are not one plate that names both halves", 1, pairs.size)
            assertEquals(
                "$a's plate does not name both halves, so a count cannot know which is drawn",
                setOf(a, b), pairs.single().first,
            )
            assertTrue(
                "$a no longer asks plateDrawn, so nothing decides which half is drawn",
                pairs.single().second.contains("plateDrawn("),
            )
            assertTrue(
                "$a and $b must be one heading's two plates",
                BrainSections.SECTIONS.any { a in it.plateKeys && b in it.plateKeys },
            )
        }
        // EVERY heading hands the pair rule in - including the ones with no pair,
        // so there is one rule on the screen and not a special case per heading.
        assertEquals(
            "not every heading is given the pair rule",
            BrainSections.SECTIONS.size,
            Regex("visible = ::plateDrawn").findAll(screen).count(),
        )
        // And `plateDrawn` answers for a pair: the hidden half is drawn exactly
        // when the lists are hidden.
        val rule = screen.substringAfter("fun plateDrawn(").take(200)
        assertTrue("plateDrawn no longer answers from the hidden state", rule.contains("privateHidden"))
        assertTrue("plateDrawn no longer tells the halves apart", rule.contains("-hidden"))
    }
    // ------------------------------------------------------------------ helpers ---

    /**
     * A `LazyListScope` that records the keys it is given instead of drawing
     * them. Every plate key on the screen comes through `LazyListScope.item`
     * inside `brainSection`, so this is where a repeated key - the crash - is
     * visible without a device.
     */
    /**
     * A `LazyListScope` that records the keys it is given instead of drawing
     * them. Every plate key on the screen comes through `LazyListScope.item`
     * inside `brainSection`, so this is where a repeated key - the crash - is
     * visible without a device.
     *
     * BOTH `item` overloads record. With a null `contentType` the compiler
     * resolves `item(key) { ... }` to the three-argument one, and a recorder that
     * filled in only the other would silently swallow every key - which is why
     * `brainList` proves the recorder receives one before trusting it.
     */
    private class FakeList {
        val scope: LazyListScope = object : LazyListScope {
            override fun item(
                key: Any?,
                contentType: Any?,
                content: @Composable LazyItemScope.() -> Unit,
            ) {
                recorded.add(key.toString())
            }

            @Deprecated("the two-argument form; the screen uses the three-argument one")
            override fun item(key: Any?, content: @Composable LazyItemScope.() -> Unit) {
                recorded.add(key.toString())
            }
        }
        private val recorded = ArrayList<String>()

        fun keys(): List<String> = recorded

        fun reset() = recorded.clear()
    }

    /**
     * The offset of every `brainSection(` call in [screen], matched by brackets
     * from its `(` - so a `)` inside the block (a call, a lambda, a string) is
     * stepped over rather than ending the call early. Each entry is the call's
     * whole span, first character to its closing paren.
     */
    private fun sectionCalls(screen: String): List<IntRange> {
        val calls = ArrayList<IntRange>()
        var from = 0
        while (true) {
            val at = screen.indexOf("brainSection(", from)
            if (at < 0) break
            var depth = 0
            var end = -1
            for (i in screen.indexOf("(", at) until screen.length) {
                when (screen[i]) {
                    '(' -> depth++
                    ')' -> {
                        depth--
                        if (depth == 0) {
                            end = i
                            break
                        }
                    }
                }
            }
            assertTrue("a brainSection( call in BrainScreen.kt is not closed", end > 0)
            calls.add(at..end)
            from = end
        }
        return calls
    }

    /** The `brainSection(...)` call for [section], from its first line to its closing paren. */
    private fun sectionBody(screen: String, section: BrainSections.Section): String {
        val calls = sectionCalls(screen)
        assertEquals(
            "BrainScreen does not draw one call per heading, in the list's own order",
            BrainSections.SECTIONS.indices.toList(),
            calls.map { r -> SECTION_INDEX.find(screen.substring(r.first, r.first + 60))?.groupValues?.get(1)?.toInt() },
        )
        val r = calls[BrainSections.SECTIONS.indexOf(section)]
        return screen.substring(r.first, r.last + 1)
    }

    /** The file's text, with whole-line comments and block comments blanked. */
    private fun code(src: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in src.lines()) {
            val t = line.trimStart()
            if (inBlock) {
                if (t.contains("*/")) inBlock = false
                out.add("")
                continue
            }
            if (t.startsWith("/*")) {
                if (!t.contains("*/")) inBlock = true
                out.add("")
                continue
            }
            if (t.startsWith("//")) {
                out.add("")
                continue
            }
            out.add(line)
        }
        return out.joinToString("\n")
    }

    private fun source(rel: String): String = repoFile(rel).readText()

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private companion object {
        const val BASE = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
        const val BRAIN = BASE + "BrainScreen.kt"
        const val BRAIN_SECTIONS = BASE + "BrainSections.kt"

        /** `brainSection(\n BrainSections.SECTIONS[3]` - the heading a call draws. */
        val SECTION_INDEX = Regex("BrainSections\\.SECTIONS\\[(\\d+)]")

        /**
         * The plates that come in two halves, of which exactly one is drawn. Read
         * from the declaration itself (`Plate.drawnWith`), so this list cannot
         * drift from what the screen is told to draw.
         */
        val PAIRS: List<Pair<String, String>> get() = BrainSections.PAIRS
    }
}
