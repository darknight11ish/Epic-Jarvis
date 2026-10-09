package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * A decision that never reaches the PC leaves the card stuck (Android audit
 * 2026-10-08).
 *
 * `ApprovalCard` greys both buttons and the swipe out the moment a decision is
 * sent, and only the `onReset` closure it passes in clears that again. The
 * approve path honoured the closure; the deny path took it and never called
 * it, so a deny refused before it was sent - the link gone stale, the card
 * expired, one already on its way, the PC unreachable - left the card
 * undecidable until the owner left Home and came back.
 *
 * The approve path's PLAIN branch had the other half of the same freeze: it
 * dispatched the decision with `decideDetached` and answered `true` straight
 * away, so the answer the card resets on was "true" whatever the PC did - a
 * failed approve POST left the card's `decided` flag set, and Approve, Deny
 * and the swipe stayed dead until the owner left Home and came back. That is
 * the path a person uses far more often than Deny.
 *
 * The risk this fix runs against is the opposite one, and it is why the
 * dispatch did not simply move into the screen's scope: a rotation cancels a
 * screen's coroutines, and a POST already on its way must not be cancelled
 * with them. So both decisions are launched on the runtime's own scope (one
 * that outlives every screen) and only the card's reset comes back to the
 * screen's - see `decideAndReset` in MainActivity, and
 * `JarvisRuntime.decideDetached`'s own doc comment for why that scope exists.
 *
 * This is deliberately a SOURCE test, and it says so rather than pretending
 * otherwise: `decided` is Compose state inside `ApprovalCard`, and reaching
 * the failing answer needs a paired phone whose desktop does not answer - no
 * JVM test can run that. What this holds is the shape that makes the fix
 * true, the same thing `TouchTargetAndInsetsTest` and `SettingsJumpTest` do
 * for their own findings.
 *
 * Run for real before it was committed, not just reasoned about: the Kotlin
 * 2.4.20 compiler this project pins is in the local Gradle cache, so this file
 * was compiled off-device and run under JUnit against MainActivity.kt as text.
 * The negative control is the point: run against `origin/main`'s
 * MainActivity.kt the deny test PASSES and the approve test FAILS, which is
 * what shows the new test has teeth on the code that had the bug. CI's Gradle
 * build is still the first compile of the app itself; a real phone is the
 * first run.
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

    private fun mainActivity(): String =
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt").readText()

    /** Comments stripped, but line numbers kept, so a failure points at real code. */
    private fun codeLines(text: String): List<String> {
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
        return out
    }

    /**
     * Comments become empty lines, so no assertion below can be satisfied by a
     * comment that names the same thing on purpose.
     */
    private fun code(text: String): String = codeLines(text).joinToString("\n")

    /**
     * The code of one function, from its `private` declaration to the next
     * one at the same indentation - so an assertion about a helper can never
     * be satisfied by a different helper's body.
     */
    private fun body(text: String, declaration: String): String {
        val from = text.indexOf(declaration)
        assertTrue("'$declaration' is gone", from >= 0)
        val next = text.indexOf("\n    private ", from + declaration.length)
        return if (next < 0) text.substring(from) else text.substring(from, next)
    }

    @Test
    fun `a deny that never reaches the PC clears the decided flag`() {
        val src = code(mainActivity())
        val at = src.indexOf("onDenyWithReset = {")
        assertTrue("the deny handler is gone", at >= 0)
        // Just the deny branch: up to the next named argument in the same call,
        // so the approve branch's own reset can never satisfy this.
        val branch = src.substring(at, src.indexOf("onReconnect", at))
        // Either shape is the fix, and each was run as itself: the awaited
        // helper `denyItem` called here, or the shared `decideAndReset` both
        // decisions now go through. What is refused is the shape that was
        // broken - dispatch the POST detached and return as if it had landed.
        val awaited = branch.contains("denyItem(item)") &&
            branch.contains("if (!sent)") && branch.contains("onReset()") &&
            branch.contains("launchDetached")
        val shared = branch.contains("decideAndReset(item, approve = false") &&
            branch.contains("onReset")
        assertTrue(
            "the deny must await its own answer, or share the function that does:\n$branch",
            awaited || shared,
        )
        assertFalse(
            "fire-and-forget again, with the reset never called:\n$branch",
            branch.contains("decideDetached(item, approve = false)"),
        )
        // The deny helper: the awaited call's own answer is what decides.
        val helper = body(mainActivity(), "private suspend fun denyItem(item: PendingItem): Boolean")
        assertTrue(
            "denyItem must read the call's answer:\n$helper",
            helper.contains("JarvisRuntime.decide(item, approve = false) is ApiResult.Ok"),
        )
    }

    /**
     * The approve path, plain branch: the same freeze, on the path a person
     * uses far more often (Android audit 2026-10-08). A failed approve POST
     * used to leave the card's `decided` flag set for the rest of its life.
     */
    @Test
    fun `an approve that never reaches the PC clears the decided flag`() {
        val src = code(mainActivity())
        val at = src.indexOf("onApproveWithReset = {")
        assertTrue("the approve handler is gone", at >= 0)
        // Up to `onDenyWithReset`, so the deny branch cannot satisfy this.
        val branch = src.substring(at, src.indexOf("onDenyWithReset", at))
        // The card's reset must reach this branch at all: either the shared
        // function both decisions use, or the awaited helper called here with
        // the card's own reset. The old code had neither - `scope.launch { if
        // (!sent) onReset() }` around a helper that could only ever answer
        // `true` on this branch.
        val shared = branch.contains("decideAndReset(item, approve = true") &&
            branch.contains("onReset")
        val awaited = branch.contains("approveItem(item)") &&
            branch.contains("if (!sent)") && branch.contains("onReset()") &&
            branch.contains("launchDetached")
        assertTrue(
            "the approve must answer through the shared decision function, or await its own answer:\n$branch",
            shared || awaited,
        )
        // The plain branch of the approve helper must await its own answer: a
        // POST the PC refused or never took has to come back as "not sent".
        val plain = body(mainActivity(), "private suspend fun approveItem(item: PendingItem): Boolean")
            .substringAfter("SignedApproval.Path.PLAIN ->")
            .substringBefore("SignedApproval.Path.SIGNED ->")
        assertTrue(
            "the plain approve must read the call's answer:\n$plain",
            plain.contains("JarvisRuntime.decide(item, approve = true) is ApiResult.Ok"),
        )
        assertFalse(
            "dispatched and called sent anyway:\n$plain",
            plain.contains("JarvisRuntime.decideDetached(item, approve = true)"),
        )
    }

    /**
     * Both paths share one function, and that function is what guarantees the
     * two halves of the fix: the POST outlives the screen, and the reset comes
     * back on the screen's scope when - and only when - nothing was sent.
     */
    @Test
    fun `both decisions share one helper that outlives the screen and resets on a real failure`() {
        val text = mainActivity()
        val src = code(text)
        assertTrue(
            "the approve and the deny must go through the same function:\n$src",
            src.contains("decideAndReset(item, approve = true") &&
                src.contains("decideAndReset(item, approve = false"),
        )
        val helper = body(text, "private fun decideAndReset(")
        assertTrue(
            "the wait must outlive the screen, like every other decision:\n$helper",
            helper.contains("JarvisRuntime.launchDetached"),
        )
        assertTrue(
            "the reset is launched on the screen's own scope, because it writes Compose state:\n$helper",
            helper.contains("scope.launch { onReset() }"),
        )
        assertTrue(
            "the reset happens only when nothing was sent:\n$helper",
            helper.contains("if (!sent)"),
        )
        assertFalse(
            "a helper that decides for itself, or that could report a refusal as success:\n$helper",
            helper.contains("return true"),
        )
    }
}
