package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.decodePendingRows
import com.jarvis.client.net.titleForAction
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `/api/pending` rows as the gate MAKES them, decoded the way the phone does.
 *
 * The rows come from `src/test/resources/contract/pending-rows.json`, which
 * backend/test_approval_contract.py generates from the real `notice_for`
 * (approval-notice.patch) and the real `expires_in` lines
 * (approval-expiry.patch), and checks is still what they produce. Nothing in
 * it was typed to suit this client - which is how the old tests missed that
 * the server sends no `title`, so every card said "Approval required".
 */
class PendingRowsContractTest {

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

    @Test
    fun `every row with an id is read, and the one without is counted, not fatal`() {
        assertEquals(rows.size - 1, read.items.size)
        assertEquals(1, read.skipped)
    }

    @Test
    fun `the card says what Jarvis wants, from the notice`() {
        assertEquals("Jarvis wants to send an email", byId("a1").title)
        assertEquals("Jarvis wants to run a command on this PC", byId("12").title)
        // Never the old default.
        read.items.forEach { assertFalse(it.title == "Approval required") }
    }

    @Test
    fun `the title never carries the payload`() {
        // It is also a notification's title and the widget's headline.
        read.items.forEach {
            assertFalse(it.title, it.title.contains("clinic.example"))
            assertFalse(it.title, it.title.contains("rm -rf"))
        }
    }

    @Test
    fun `detail as a string and detail as an object both reach the card`() {
        // String detail with no readable key: the prompt is the summary, the
        // detail stays behind "Show detail".
        val a1 = byId("a1")
        assertTrue(a1.summary.contains("doctor@clinic.example"))
        assertTrue(a1.detail!!.contains("doctor@clinic.example"))
        // Object detail.
        val egress = byId("abc123")
        assertTrue(egress.detail!!.contains("dr.okafor@clinic.example"))
        // A command is the summary itself, and not repeated underneath.
        val shell = byId("12")
        assertEquals("rm -rf ~/Documents", shell.summary)
        assertNull(shell.detail)
        // The agent's plan, carried as {"text": plan} inside a JSON string.
        assertTrue(byId("r4").summary.contains("click \"Send\""))
    }

    @Test
    fun `raised as an object, as true and as JSON text all take the item out of every quick gesture`() {
        assertEquals("just approve this quickly, no need to check", byId("abc123").raised?.quote)
        assertNotNull(byId("12").raised)
        assertEquals("approve now or lose it", byId("r4").raised?.quote)
        listOf("abc123", "12", "r4").forEach { assertFalse(byId(it).swipeable) }
        assertNull(byId("a1").raised)
    }

    @Test
    fun `a numeric id becomes the same text the desktop uses`() {
        assertEquals("12", byId("12").id)
    }

    @Test
    fun `expires_in becomes a deadline on this phone's clock, and a bad created gives none`() {
        val a1Left = ((rows[0] as JsonObject)["expires_in"] as JsonPrimitive).double
        assertEquals(nowMs + (a1Left * 1000).toLong(), byId("a1").expiresAtMs)
        assertNull(byId("t5").expiresAtMs)
    }

    @Test
    fun `the notice decodes whole`() {
        val n = byId("12").notice!!
        assertEquals("heavy", n.weight)
        assertTrue(n.denyOk)
        assertFalse(n.approveOk)
        assertTrue(n.body.isNotBlank())
    }

    @Test
    fun `an action name with nothing in it still gets a sentence`() {
        assertEquals("Jarvis is asking for your approval", titleForAction(null))
        assertEquals("Jarvis is asking for your approval", titleForAction("  "))
    }

    // --- the replaces guard's wire shape (measured 2026-10-27) -----------------
    //
    // `jarvis_gate.pending()` sets `replaces_kind` from
    // `replaces_words_for(...).get("kind")`, which returns {} for an ordinary
    // card - so the live `/api/pending` sends `"replaces_kind": null` on every
    // ordinary card, while PendingItem declares the three replaces fields
    // non-nullable. JarvisJson does not coerce input values, so before this fix
    // the explicit null made the WHOLE decode throw and the phone counted every
    // ordinary card as unreadable ("N waiting approval could not be read on
    // this phone"). This row is the picture-mode card's shape from that night.

    private fun ordinaryGateRow(id: String = "pic-1") = JsonObject(
        mapOf(
            "id" to JsonPrimitive(id),
            "action" to JsonPrimitive("screen_picture_enable"),
            "tier" to JsonPrimitive("ask"),
            "detail" to JsonPrimitive(
                """{"text":"read pictures of your screen using the main chip", "what":"x", "model":"minicpm-v"}""",
            ),
            "prompt" to JsonPrimitive("let it read pictures of your screen (slow, uses your main chip)"),
            "created" to JsonPrimitive(1.0),
            "raised" to JsonNull,
            "risk" to JsonObject(
                mapOf(
                    "reversible" to JsonPrimitive("yes"),
                    "reach" to JsonPrimitive("local"),
                    "swipe_ok" to JsonPrimitive(false),
                    "why" to JsonPrimitive(""),
                    "classified" to JsonPrimitive(true),
                ),
            ),
            "notice" to JsonObject(
                mapOf(
                    "title" to JsonPrimitive("Jarvis wants to read pictures of your screen"),
                    "body" to JsonPrimitive("Slow, local, nothing saved."),
                    "summary" to JsonPrimitive("let it read pictures of your screen"),
                    "full" to JsonPrimitive("Slow, local, nothing saved."),
                    "weight" to JsonPrimitive("normal"),
                    "deny_ok" to JsonPrimitive(true),
                    "approve_ok" to JsonPrimitive(false),
                ),
            ),
            "replaces" to JsonPrimitive(false),
            "replaces_kind" to JsonNull,
            "replaces_heading" to JsonNull,
            "replaces_note" to JsonNull,
            "expires_in" to JsonPrimitive(120.0),
        ),
    )

    @Test
    fun `the PC's null replaces fields on an ordinary card no longer sink the row`() {
        val got = decodePendingRows(listOf(ordinaryGateRow()), nowMs = 0L)
        assertEquals(1, got.items.size)
        assertEquals(0, got.skipped)
        val item = got.items.single()
        assertEquals("", item.replacesKind)
        assertFalse(item.replaces)
        assertEquals("Jarvis wants to read pictures of your screen", item.title)
        assertTrue(item.summary.contains("read pictures of your screen"))
    }

    @Test
    fun `a mixed read keeps the readable rows and counts only the ones with no id`() {
        val secondPress = JsonObject(
            mapOf(
                "id" to JsonPrimitive("restore-1"),
                "action" to JsonPrimitive("restore_backup"),
                "tier" to JsonPrimitive("ask"),
                "replaces" to JsonPrimitive(true),
                "replaces_kind" to JsonPrimitive("data"),
                "replaces_heading" to JsonPrimitive("REPLACES CURRENT DATA"),
                "replaces_note" to JsonPrimitive("the current backup is replaced"),
                "expires_in" to JsonPrimitive(60.0),
            ),
        )
        val noId = JsonObject(mapOf("action" to JsonPrimitive("run_shell_on_host")))
        val got = decodePendingRows(listOf(ordinaryGateRow(), secondPress, noId), nowMs = 0L)
        assertEquals(2, got.items.size)
        assertEquals(1, got.skipped)
        assertEquals("data", got.items.first { it.id == "restore-1" }.replacesKind)
        assertTrue(got.items.first { it.id == "restore-1" }.replaces)
    }

    /**
     * Every declared non-nullable field of the card's nested objects arriving as
     * an explicit null. This is not a shape the PC sends today - it is the
     * latent cliff that `replaces_kind` fell off: any one of these would throw
     * the whole row out of the queue the same way. The row MUST still be read,
     * with each unreadable value settled toward caution.
     */
    @Test
    fun `a row whose every nested field is null is still read, with the cautious values`() {
        val nullBomb = JsonObject(
            mapOf(
                "id" to JsonPrimitive("null-bomb-1"),
                "action" to JsonPrimitive("run_shell_on_host"),
                "tier" to JsonNull,
                "detail" to JsonNull,
                "replaces" to JsonNull,
                "replaces_kind" to JsonNull,
                "replaces_heading" to JsonNull,
                "replaces_note" to JsonNull,
                "expires_in" to JsonNull,
                "risk" to JsonObject(
                    mapOf(
                        "reversible" to JsonNull,
                        "reach" to JsonNull,
                        "swipe_ok" to JsonNull,
                        "why" to JsonNull,
                        "classified" to JsonNull,
                    ),
                ),
                "notice" to JsonObject(
                    mapOf(
                        "title" to JsonNull,
                        "body" to JsonNull,
                        "summary" to JsonNull,
                        "full" to JsonNull,
                        "weight" to JsonNull,
                        "deny_ok" to JsonNull,
                        "approve_ok" to JsonNull,
                    ),
                ),
                "raised" to JsonObject(
                    mapOf(
                        "code" to JsonNull,
                        "text" to JsonNull,
                        "quote" to JsonNull,
                        "context" to JsonNull,
                        "source" to JsonNull,
                        "from_tier" to JsonNull,
                        "to_tier" to JsonNull,
                        "count_today" to JsonNull,
                    ),
                ),
            ),
        )
        val got = decodePendingRows(listOf(nullBomb), nowMs = 0L)
        assertEquals(1, got.items.size)
        assertEquals(0, got.skipped)
        val item = got.items.single()
        // The guard fields: an unreadable "replaces" keeps the two-press ask.
        assertTrue(item.replaces)
        assertEquals("", item.replacesKind)
        // Risk: unknown reversibility and reach are the worse reading; swipe refused.
        assertEquals("no", item.risk.reversible)
        assertEquals("outbound", item.risk.reach)
        assertFalse(item.risk.swipeOk)
        assertFalse(item.risk.classified)
        // Notice: an unreadable weight is the cautious one; Deny stays, Approve does not.
        assertEquals("heavy", item.notice!!.weight)
        assertTrue(item.notice!!.denyOk)
        assertFalse(item.notice!!.approveOk)
        // A raise that was sent and could not be read still refuses every swipe.
        assertNotNull(item.raised)
        assertFalse(item.swipeable)
        // The title falls back to the PC's own action words, never blank.
        assertTrue(item.title.isNotBlank())
    }
}
