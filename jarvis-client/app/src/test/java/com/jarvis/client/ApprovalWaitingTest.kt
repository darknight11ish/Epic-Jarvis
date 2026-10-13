package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * A card with NO deadline shows a waiting state - and no countdown.
 *
 * The owner's decision of 2026-10-10: the deliberate, hard-to-repeat cards
 * (pairing a phone, restoring a backup, forgetting a time frame, and every
 * settings change that loosens a rule) wait for him instead of lapsing, while
 * everything routine keeps the 180-second window it always had. The gate says
 * which is which by leaving `expires_in` OFF the deliberate card's row -
 * absent, never 0 ("expired now" to both clients) and never a very large
 * number (a countdown that never ends) - and `backend/test_gate_no_expiry.py`
 * is the other half of that promise on the PC. This file is the phone's.
 *
 * WHAT IS ALREADY TRUE, AND WHY THIS FILE IS MOSTLY ABOUT NOT BREAKING IT:
 * the phone never needed a new branch for this. [com.jarvis.client.net
 * .normalisePendingRow] computes `expires_at_ms` only from a real number, and
 * `ApprovalCard` draws the bar and the "EXPIRES IN 00:43" readout only when
 * there is a deadline - so a row with the field missing already arrives as
 * `expiresAtMs == null`, the card already shows nothing where the countdown
 * would be, and the decision blocker already refuses only on a real deadline.
 * The work was to be sure of that, and to hold it: the checks below are the
 * ones that fail if somebody later gives a missing expiry a default, or draws
 * the countdown unconditionally.
 *
 * The rows come from `contract/pending-rows.json`, which
 * `backend/test_approval_contract.py` generates from the real gate's own
 * `pending()` - including one deliberate card, `p7`, with no `expires_in` at
 * all. Nothing here was shaped to suit this test.
 *
 * The card itself is Compose, so the second half is a SOURCE check and says so
 * rather than pretending to render: `ApprovalCard.kt` is read and the guards
 * around the two countdown readers are checked, the same way
 * `ApprovalDecisionTest` holds its own finding. A JVM test cannot compose a
 * card; what it can do is refuse to let the guard be deleted.
 */
class ApprovalWaitingTest {

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/pending-rows.json")) {
            "contract/pending-rows.json is missing - run backend/test_approval_contract.py --write"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val nowMs = (fixture["now"]!!.jsonPrimitive.double * 1000).toLong()
    private val rows = (fixture["rows"] as JsonArray).toList()
    private val read = decodePendingRows(rows, nowMs)
    private fun byId(id: String): PendingItem = read.items.first { it.id == id }

    /** The card's own source, comments stripped so a mention cannot pass a check. */
    private fun cardSource(): String {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, "jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt")
            if (f.isFile) return f.readText()
            d = d.parentFile
        }
        error("ApprovalCard.kt not found above ${System.getProperty("user.dir")}")
    }

    private fun code(): String = cardSource()
        .replace(Regex("""/\*.*?\*/""", RegexOption.DOT_MATCHES_ALL), "")
        .lines().joinToString("\n") { if (it.trimStart().startsWith("//")) "" else it }

    @Test
    fun `a deliberate card arrives with no deadline, and a routine one with its own`() {
        // The pairing card the gate leaves the field off.
        val waiting = byId("p7")
        assertEquals("pair_device", waiting.action)
        assertNull("a deliberate card must have no deadline at all", waiting.expiresAtMs)
        // The routine card next to it, whose countdown is exactly as it was.
        val routine = byId("a1")
        assertEquals(nowMs + 150_000L, routine.expiresAtMs)
        // And the decision blocker has nothing to refuse it for.
        assertTrue(read.items.count { it.expiresAtMs == null } >= 2)
    }

    @Test
    fun `the absent field is not a zero in disguise`() {
        // 0 would give this phone a deadline in the past, and the card would
        // say "Timed out" over a request that is still perfectly answerable.
        val waiting = byId("p7")
        assertNull(waiting.expiresAtMs)
        assertFalse(waiting.expiresAtMs == 0L)
        // And the raw row really has no `expires_in` - the check above would
        // pass for the wrong reason if the fixture had a 0 in it.
        val raw = rows.first { (it as JsonObject)["id"]?.jsonPrimitive?.content == "p7" } as JsonObject
        assertFalse("the gate must leave the field off, not send 0", raw.containsKey("expires_in"))
    }

    @Test
    fun `no countdown is drawn without a deadline, and the countdown is untouched with one`() {
        val src = code()
        // The one thing that could go wrong on this screen: a reader that
        // forgot the guard, or a card that guessed a deadline.
        assertTrue(
            "ApprovalCard must draw the deadline bar only when there is an expiry",
            Regex("""if \(expiry != null && secondsLeft != null && !expired\) \{""").containsMatchIn(src)
        )
        assertTrue(
            "ApprovalCard must show the readout only when there is an expiry",
            Regex("""\} else if \(secondsLeft != null\) \{""").containsMatchIn(src)
        )
        assertTrue(
            "secondsLeft must be null when there is no expiry - it is what both readers key on",
            Regex("""val secondsLeft: State<Long>\? = if \(expiry != null\) rememberSecondsLeft\(expiry\) else null""")
                .containsMatchIn(src)
        )
        assertTrue(
            "a card with no deadline must not be treated as expired when it appears",
            Regex("""mutableStateOf\(expiry != null && System\.currentTimeMillis\(\) >= expiry\)""")
                .containsMatchIn(src)
        )
        // Nothing in the card may invent a deadline for a row that has none.
        assertFalse(
            "the card must not substitute a default expiry",
            Regex("""expiry \?:|expiresAtMs \?:""").containsMatchIn(src)
        )
        // And the countdown's own words are still there for the cards that do
        // expire: this test is about the waiting state, not about removing it.
        assertTrue("the countdown readout still exists", src.contains("EXPIRES IN"))
        assertTrue("the countdown still reads as a clock", src.contains("clockCountdown"))
    }
}
