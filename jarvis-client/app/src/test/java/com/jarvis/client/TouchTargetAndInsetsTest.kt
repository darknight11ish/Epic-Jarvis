package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Two fixes that no JVM test can exercise on a phone, held to the source that
 * makes them true - the same shape `SettingsJumpTest` and `SpecDriftTest`
 * already use. CI is still the only place either is ever RUN on a device.
 *
 * - **A2, the keyboard covering text fields** (UI audit 2026-10-05): the root
 *   layout asked for the system bars only, while `enableEdgeToEdge` leaves the
 *   IME inset to the app - so on 11 of 14 screens the keyboard sat over the
 *   field being typed into. One `.imePadding()` on the root fixes every screen
 *   at once; this test fails if it is removed again.
 * - **A4, `Modifier.pressable` enforcing no 48dp minimum**: twelve of its
 *   call sites were too small, two of them about 19dp of text. The minimum
 *   lives inside the shared helper now, and the one call site that cannot fit
 *   it says so in words next to the opt-out.
 */
class TouchTargetAndInsetsTest {

    private fun repoFile(rel: String): File {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val parts = "jarvis-client/app/src/main/java/com/jarvis/client/ui/parts/Parts.kt"
    private val activity = "jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt"

    /**
     * Just the code: whole-line `//` comments and block comments dropped, so
     * an assertion on what a function DOES is never satisfied by the comment
     * above it that names the same thing on purpose.
     */
    private fun code(text: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in text.lines()) {
            val t = line.trimStart()
            // Comments become EMPTY LINES, not dropped ones: the call-site
            // search below reads code, and the reason it demands is written in
            // a comment - keeping the line count is what lets it look at the
            // same window in the raw text. Dropping them (as this did until
            // 2026-10-08) deleted the very explanation it then asked for.
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

    @Test
    fun `the shared root asks for the keyboard inset, so every screen gets it`() {
        val src = code(repoFile(activity).readText())
        val at = src.indexOf("val root = Modifier")
        assertTrue("the root modifier was not found", at >= 0)
        // The chain itself: up to `if (locked)` - the next statement in the
        // theme block, and the only marker around it that is not a comment.
        val chain = src.substring(at, src.indexOf("if (locked)", at))
        assertTrue("the root modifier was not found:\n$chain", chain.contains(".fillMaxSize()"))
        assertTrue("the root still asks for the system bars:\n$chain", chain.contains("windowInsetsPadding(WindowInsets.systemBars)"))
        assertTrue(
            "the keyboard inset has to be on the ROOT or the 11 screens that " +
                "never added one are covered again:\n$chain",
            chain.contains(".imePadding()"),
        )
        // The three screens that added their own keep theirs: one inset per
        // screen, and this fix does not reach into them.
        for (screen in listOf("HomeScreen", "LiveScreen", "HandoffScreen")) {
            val own = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/$screen.kt").readText()
            assertTrue("$screen keeps its own imePadding", own.contains("imePadding()"))
        }
    }

    @Test
    fun `pressable carries the 48dp minimum itself`() {
        // From the function's declaration onwards. The comments are already
        // gone, so the feature sitting at the top of the parameter list is the
        // first thing this finds - and the body is the first place either
        // string appears after it: a default value cannot contain `heightIn(`.
        val body = code(repoFile(parts).readText()).substringAfter("fun Modifier.pressable(")
        assertTrue("pressable must default to the 48dp Android minimum:\n$body", body.contains("minTouchTarget: Dp = 48.dp"))
        assertTrue("and apply it:\n$body", body.contains("heightIn(min = minTouchTarget)"))
        // Before `clickable`, so it grows the area that answers a tap (and the
        // press animation's centre) rather than a painted pill below it.
        val minAt = body.indexOf("heightIn(min = minTouchTarget)")
        val clickAt = body.indexOf(".clickable(")
        assertTrue("both are in pressable's body:\n$body", minAt >= 0 && clickAt >= 0)
        assertTrue("the minimum comes before clickable:\n$body", minAt < clickAt)
    }

    @Test
    fun `the one call site that opts out says why, and the text links do not`() {
        var optOuts = 0
        var calls = 0
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/LinkWords.kt").parentFile
            .walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .forEach { file ->
                val src = file.readText()
                val lines = code(src).lines()
                // The REASON is a comment and `code()` blanks comments, so the
                // window is read from the raw text. The line numbers are the
                // same, because `code()` now keeps every line (2026-10-08:
                // dropping them deleted the explanation this then asked for).
                val raw = src.lines()
                lines.forEachIndexed { i, line ->
                    // A call site, not the declaration itself - whose feature
                    // list is where the escape hatch is offered, not taken.
                    if (!line.contains(".pressable(") || line.trimStart().startsWith("fun ")) return@forEachIndexed
                    calls++
                    val window = raw.drop(i).take(12).joinToString("\n").trimEnd()
                    if (!window.contains("minTouchTarget")) return@forEachIndexed
                    optOuts++
                    // FaceEditor's palette swatches: a 48dp target there is a
                    // 48dp-tall rectangle in a 23-31dp-wide column, so the grid
                    // would grow from ~115dp to ~240dp. Reported, not forced.
                    assertTrue(
                        "an opt-out at ${file.name}:${i + 1} must say why, in words, " +
                            "next to itself:\n$window",
                        window.contains("48dp") && (window.contains("UI audit") || window.contains("face editor")),
                    )
                }
            }
        assertEquals("exactly one call site opts out today", 1, optOuts)
        assertTrue("pressable's call sites were not walked (found $calls)", calls > 25)

        // The audit's worst two, FaqScreen's GitHub link and third-party
        // notices, go back to about 19dp tall if either opts out - each of
        // those Text nodes would then be free to shrink below its own line.
        val faq = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FaqScreen.kt").readLines()
        for (lineNumber in listOf(444, 473)) {
            val window = faq.drop(lineNumber - 1).take(12).joinToString("\n")
            assertTrue("FaqScreen.kt:$lineNumber still pressable:\n$window", window.contains(".pressable("))
            assertFalse(
                "FaqScreen.kt:$lineNumber must keep the shared minimum - it is one of the " +
                    "two ~19dp text targets the audit named:\n$window",
                window.contains("minTouchTarget"),
            )
        }
    }
}
