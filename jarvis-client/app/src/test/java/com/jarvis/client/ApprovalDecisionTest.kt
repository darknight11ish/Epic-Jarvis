package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * A Deny that never leaves the phone (Android audit 2026-10-08).
 *
 * `ApprovalCard` greys both buttons and the swipe out the moment a decision is
 * sent, and only the `onReset` closure it passes in clears that again. The
 * approve path honoured the closure; the deny path took it and never called
 * it, so a deny refused before it was sent - the link gone stale, the card
 * expired, one already on its way, the PC unreachable - left the card
 * undecidable until the owner left Home and came back.
 *
 * This is deliberately a SOURCE test, and it says so rather than pretending
 * otherwise: `decided` is Compose state inside `ApprovalCard`, and reaching
 * the failing answer needs a paired phone whose desktop does not answer - no
 * JVM test can run that. What this holds is the shape that makes the fix
 * true, the same thing `TouchTargetAndInsetsTest` and `SettingsJumpTest` do
 * for their own findings. CI's Gradle build is the first compile; a real
 * phone is the first run.
 */
class ApprovalDecisionTest {

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
     * Comments become empty lines, so no assertion below can be satisfied by a
     * comment that names the same thing on purpose.
     */
    private fun code(text: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in text.lines()) {
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

    @Test
    fun `a deny that never reaches the PC clears the decided flag`() {
        val src = code(
            repoFile("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt").readText(),
        )
        val at = src.indexOf("onDenyWithReset = {")
        assertTrue("the deny handler is gone", at >= 0)
        // Just the deny branch: up to the next named argument in the same call,
        // so the approve branch's own reset can never satisfy this.
        val branch = src.substring(at, src.indexOf("onReconnect", at))
        assertTrue(
            "the deny must await its own answer:\n$branch",
            branch.contains("denyItem(item)"),
        )
        assertTrue(
            "and hand the card's reset back when nothing was sent:\n$branch",
            branch.contains("if (!sent)") && branch.contains("onReset()"),
        )
        assertTrue(
            "the wait outlives the screen, like every other decision:\n$branch",
            branch.contains("launchDetached"),
        )
        assertFalse(
            "fire-and-forget again, with the reset never called:\n$branch",
            branch.contains("decideDetached(item, approve = false)"),
        )
        // The helper: the awaited call's own answer is what decides.
        val helper = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
            .readText()
            .substringAfter("private suspend fun denyItem(item: PendingItem): Boolean")
            .take(400)
        assertTrue(
            "denyItem must read the call's answer:\n$helper",
            helper.contains("JarvisRuntime.decide(item, approve = false) is ApiResult.Ok"),
        )
    }
}
