package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Which plates Brain's headings may draw when "Hide memory lists and chat
 * history" is ON - the one question the private-lists rule exists for.
 *
 * WHY THIS EXISTS (2026-10-11). Every heading hands its plates one rule,
 * `visible = ::plateDrawn`, and `plateDrawn` answers `false` for every name that
 * does not end in `-hidden`. That is right for a memory LIST and wrong for the
 * ~34 plates that are not memory at all (money, schedules, the PC, live state):
 * they were dropped before the list ever saw them, so an open heading drew its
 * heading and nothing under it, and "Written: 0" was the device's way of saying
 * so. The fix gives those plates `drawn = { true }`, one at a time, the way
 * `people-and-things` already had it.
 *
 * THE RISK GUARDED HERE is the other direction: `drawn = { true }` does not ADD
 * to the rule, it REPLACES it (`LazyPlateList.plate` is
 * `drawn?.invoke(key) ?: visible(key)`), so a plate given the override is drawn
 * with the lists hidden whatever `plateDrawn` would say. The mistake this file
 * makes impossible is a genuine memory plate quietly gaining one - a privacy
 * regression wearing a bug fix's clothes.
 *
 * WHAT IT IS, said plainly so it is not mistaken for more. It reads the two real
 * sources and computes the outcome for every declared plate: the hidden half of
 * the list from `BrainSections.kt`'s own `Plate` declarations (never a list typed
 * here), and the screen's own `plate(...)` call sites from `BrainScreen.kt`. It
 * does NOT instantiate `LazyPlateList`, because `BrainSections.kt` is Compose UI
 * and there is no Android SDK on this machine to compile it against (see
 * `docs/OFF-DEVICE-COMPILE.md`); `BrainListTest` drives the real list in CI. What
 * this file does about that is PIN the two lines it models - `plateDrawn`'s body
 * and `plateDecision`'s `val shown =` line - so it fails loudly rather than
 * modelling a mechanism the app no longer has.
 */
class BrainPlateVisibilityTest {

    /** What "Hide memory lists and chat history" ON means for this test. */
    private val hidden = true

    // ------------------------------------------------------- the two sources ---

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
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

    private val screen: String by lazy { code(repoFile(BRAIN).readText()) }
    private val sections: String by lazy { code(repoFile(BRAIN_SECTIONS).readText()) }

    // ------------------------------------------------------------ the pins ----

    /**
     * `plateDrawn`, mirrored - and held to the real thing first.
     *
     * The screen's own function is local to its composable, so it cannot be
     * called from here. What can be done is refuse to model anything but the rule
     * the file really contains: if the body stops asking about `-hidden`, or stops
     * asking about the hidden state, this fails before any conclusion is drawn
     * from it.
     */
    private fun assertRuleShapeThenRule(name: String): Boolean {
        val rule = screen.substringAfter("fun plateDrawn(").substringBefore("\n\n")
        assertTrue(
            "plateDrawn no longer answers from the hidden state, so the rule modelled " +
                "here is not the screen's:\n$rule",
            rule.contains("privateHidden"),
        )
        assertTrue(
            "plateDrawn no longer tells the halves apart (it must ask about \"-hidden\"):\n$rule",
            rule.contains("endsWith(\"-hidden\")"),
        )
        assertTrue(
            "plateDrawn's body is not the two-way shape this test mirrors:\n$rule",
            rule.contains("if (") && rule.contains("else"),
        )
        return if (name.endsWith("-hidden")) hidden else !hidden
    }

    /**
     * `LazyPlateList.plate`'s decision, mirrored - and held to the real thing.
     * This is the line that makes the override a REPLACEMENT rather than an
     * addition, so the whole risk in this file depends on it.
     */
    private fun assertOverrideComesFirst() {
        val line = sections.lineSequence().firstOrNull { it.contains("val shown =") }
            ?: error("LazyPlateList.plate no longer has a `val shown =` line")
        assertTrue(
            "the override is no longer tried before the heading's rule, so the reasoning " +
                "in this file is wrong:\n$line",
            line.replace(" ", "").contains("drawn?.invoke(key)?:visible(key)"),
        )
    }

    /** `shown = drawn?.invoke(key) ?: visible(key)`, with `visible` being the rule. */
    private fun shown(name: String, overrides: Set<String>): Boolean =
        if (name in overrides) true else assertRuleShapeThenRule(name)

    // -------------------------------------------------- the declarations -------

    /** One `Plate("name", ...)` as `BrainSections.kt` declares it. */
    data class Decl(val name: String, val guard: String, val drawnWith: String?)

    /**
     * Every declared plate, from `BrainSections.kt`'s own `Plate(...)` lines - so a
     * memory plate added tomorrow is covered on the day it is declared.
     */
    private fun declarations(): List<Decl> =
        Regex("""Plate\(\s*"([\w-]+)"([^)]*)\)""").findAll(sections).map { m ->
            val rest = m.groupValues[2]
            Decl(
                name = m.groupValues[1],
                guard = Regex("""guard\s*=\s*"([^"]+)"""").find(rest)?.groupValues?.get(1) ?: "",
                drawnWith = Regex("""drawnWith\s*=\s*"([\w-]+)"""").find(rest)?.groupValues?.get(1),
            )
        }.toList()

    /**
     * Whether a declared plate is part of the private lists - read from the
     * declaration, never typed here: a memory plate carries a `brain.memory.`
     * guard, and the halves of a pair name each other through `drawnWith`.
     */
    private fun isMemoryish(d: Decl): Boolean =
        d.guard.startsWith("brain.memory.") || d.drawnWith != null

    /** The one memory plate allowed to be drawn while hidden: it guards itself. */
    private val selfGuarding = "people-and-things"

    // --------------------------------------------- the screen's call sites -----

    /** Balanced-paren call spans, so an argument's own brackets cannot end a call early. */
    private fun callSpans(src: String, marker: String): List<IntRange> {
        val spans = ArrayList<IntRange>()
        var from = 0
        while (true) {
            val at = src.indexOf(marker, from)
            if (at < 0) break
            var depth = 0
            var end = -1
            for (i in src.indexOf("(", at) until src.length) {
                when (src[i]) {
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
            assertTrue("a $marker call in BrainScreen.kt is not closed", end > 0)
            spans.add(at..end)
            from = end
        }
        return spans
    }

    /** `plate("name")`, `plate("name", drawn = { true })`, or the pair form. */
    private fun callsIn(body: String): List<Pair<String, Boolean>> {
        val out = ArrayList<Pair<String, Boolean>>()
        for (span in callSpans(body, "plate(")) {
            if (span.first >= 1 && body[span.first - 1].isLetterOrDigit()) continue
            val args = body.substring(span.first + "plate(".length, span.last).trim()
            // A pair writes one half, chosen by the rule; both halves are named.
            val pair = Regex("""^if \(plateDrawn\("([\w-]+)"\)\) "([\w-]+)" else "([\w-]+)"""")
                .find(args)
            if (pair != null) {
                val first = pair.groupValues[1]
                val then = pair.groupValues[2]
                val otherwise = pair.groupValues[3]
                // The call NAMES both halves; exactly one is drawn for a given
                // state, and which one is the rule's answer for the first.
                assertTrue(
                    "the pair call for \"$first\" does not name both halves, so one of them " +
                        "is unreachable",
                    (if (assertRuleShapeThenRule(first)) then else otherwise) in listOf(then, otherwise),
                )
                out.add(then to false)
                out.add(otherwise to false)
                continue
            }
            val name = Regex("""^"([\w-]+)"""").find(args)?.groupValues?.get(1) ?: continue
            val override = Regex("""drawn\s*=\s*\{""").containsMatchIn(args)
            out.add(name to override)
        }
        return out
    }

    /** Every plate call the screen writes, across all headings. */
    private fun allCalls(): List<Pair<String, Boolean>> =
        callSpans(screen, "brainSection(").flatMap { callsIn(screen.substring(it)) }

    // ---------------------------------------------------------------- the tests ---

    @Test
    fun `no memory plate can be drawn while the private lists are hidden`() {
        assertOverrideComesFirst()
        val declared = declarations()
        assertTrue("no plates were found in BrainSections.kt - the parse is broken", declared.isNotEmpty())
        val calls = allCalls()
        val overrides = calls.filter { it.second }.map { it.first }.toSet()
        val written = calls.map { it.first }.toSet()

        // Every declared plate must have a call site, or the model below is blind
        // to it: a plate that is declared and never written is a different bug.
        for (d in declared) {
            assertTrue(
                "BrainSections.kt declares \"${d.name}\" and BrainScreen.kt writes no " +
                    "plate(\"${d.name}\") for it, so this test cannot see whether it is drawn",
                d.name in written,
            )
        }

        // 1. THE QUESTION. Every part of the private lists is dropped by the rule,
        //    except the `-hidden` halves (they ARE the prompt the pair draws) and
        //    the one plate that guards itself inside its own composable.
        for (d in declared.filter { isMemoryish(it) }) {
            val allowed = d.name.endsWith("-hidden") || d.name == selfGuarding
            if (allowed) {
                assertTrue(
                    "\"${d.name}\" must still be drawn while the lists are hidden (it is the " +
                        "half that draws the prompt, or it guards itself)",
                    shown(d.name, overrides),
                )
            } else {
                assertFalse(
                    "PRIVACY: \"${d.name}\" is a memory plate and would be drawn while " +
                        "\"Hide memory lists and chat history\" is ON. `drawn = { true }` " +
                        "REPLACES the heading's rule, it does not add to it: remove the " +
                        "override, or give the plate a guard of its own first.",
                    shown(d.name, overrides),
                )
            }
            if (d.name != selfGuarding) {
                assertFalse(
                    "PRIVACY: \"${d.name}\" is a memory plate and carries `drawn = { true }`: " +
                        "the override replaces `plateDrawn`, so nothing decides whether it is " +
                        "private any more. Only \"$selfGuarding\" may carry one, because it " +
                        "draws its own hidden prompt - and it must not GAIN one here either.",
                    d.name in overrides,
                )
            }
        }

        // 2. deep-questions by name. It is the one name at the revision the review
        //    read whose safety rested on this rule alone, and the one a fix written
        //    as "draw the plates with no -hidden twin" would draw first.
        assertFalse(
            "\"deep-questions\" must keep the rule: its questions and answers are the " +
                "owner's own words, and it must not gain an override as a side effect of " +
                "this fix",
            "deep-questions" in overrides || shown("deep-questions", overrides),
        )

        // 3. The bug itself: every plate that is NOT part of the private lists is
        //    drawn. A plate left dropped fails here rather than passing by being
        //    merely declared.
        for (d in declared.filterNot { isMemoryish(it) }) {
            assertTrue(
                "\"${d.name}\" is not memory, so it must draw while the private lists are " +
                    "hidden; it was dropped, which is the \"heading with nothing under it\" " +
                    "defect this fix is for",
                shown(d.name, overrides),
            )
        }

        // 4. And the override set is EXACTLY the non-memory plates plus the one
        //    self-guarding plate - so an override added anywhere else, now or later,
        //    fails here rather than shipping.
        val memoryish = declared.filter { isMemoryish(it) }.map { it.name }.toSet()
        val notMemory = declared.map { it.name }.filterNot { it in memoryish }.toSet()
        assertEquals(
            "the plates carrying `drawn = { true }` are not exactly the non-memory plates " +
                "plus \"$selfGuarding\": the override replaces the private-lists rule, so " +
                "anything else here needs its own reason and its own guard",
            notMemory + selfGuarding,
            overrides,
        )
    }

    @Test
    fun `each pair draws exactly one half, and the hidden half is the prompt`() {
        assertOverrideComesFirst()
        val pairs = declarations().filter { it.drawnWith != null }
        assertTrue("no pairs were found - the parse is broken", pairs.isNotEmpty())

        val calls = allCalls().map { it.first }.toSet()
        for (d in pairs) {
            val other = d.drawnWith!!
            assertTrue(
                "the pair ${d.name}/$other is declared but the screen writes no call naming " +
                    "either half",
                d.name in calls || other in calls,
            )
            assertTrue(
                "with the lists hidden, the \"-hidden\" half of ${d.name}/$other must be the " +
                    "one drawn - it draws the prompt the pair exists for",
                shown(d.name, emptySet()) != shown(other, emptySet()),
            )
        }
    }

    private companion object {
        const val BASE = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
        const val BRAIN = BASE + "BrainScreen.kt"
        const val BRAIN_SECTIONS = BASE + "BrainSections.kt"
    }
}
