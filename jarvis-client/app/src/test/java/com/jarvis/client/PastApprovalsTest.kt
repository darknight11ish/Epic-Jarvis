package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.GateHistoryRead
import com.jarvis.client.net.GateHistoryItem
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PastApprovals
import com.jarvis.client.net.decodeGateHistoryRows
import com.jarvis.client.net.parseListBody
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Past approvals" - the phone's read-only list of cards already decided
 * (docs/JARVIS-API.md section 42), and the words its own screen shows.
 *
 * Pure JVM: [PastApprovals] and [decodeGateHistoryRows] have no Android in
 * them, so this is what proves the reading and the one rule (which filter
 * shows which outcome, newest decision first) on a machine with no Android
 * SDK. The Compose screen is read as text at the bottom, the way
 * MenuVisibilityTest reads the screens it cannot compile here.
 *
 * The rows are decoded from `/api/pending`'s `history` array, never from
 * `pending`: a decided card and a waiting one must never share a list, so the
 * test that asks for `history` BY NAME is not decoration - it is the half of
 * the job that stops a past card being offered as if it still waited.
 */
class PastApprovalsTest {

    private fun decode(text: String): GateHistoryRead =
        decodeGateHistoryRows((JarvisJson.parseToJsonElement(text) as JsonArray).toList())

    private fun item(
        id: String,
        state: String = "",
        decidedAt: Double? = null,
        createdAt: Double = 0.0,
        device: String? = null,
    ) = GateHistoryItem(
        id = id,
        createdAt = createdAt,
        decidedAt = decidedAt,
        state = state,
        device = device,
    )

    // ------------------------------------------------------------- the wires ----

    @Test
    fun `the three outcomes the backend records are the three words the owner reads`() {
        val read = decode(
            """
            [
              {"id": "a", "created": 1000, "decided_at": 1010, "state": "approved", "decided_by": "this PC"},
              {"id": "b", "created": 2000, "outcome": "denied", "device": "another device"},
              {"id": "c", "created": 3000, "state": "expired", "by": "this PC"},
              {"id": "d", "created": 4000, "outcome": "timed_out"}
            ]
            """.trimIndent(),
        )
        assertEquals(4, read.items.size)
        assertEquals(0, read.skipped)
        assertEquals("Approved", read.items[0].outcomeLabel)
        assertEquals("Denied", read.items[1].outcomeLabel)
        // approvals.state says "expired"; the gate's own Verdict says
        // "timed_out" for the same event - both are the same two words here.
        assertEquals("Timed out", read.items[2].outcomeLabel)
        assertEquals("Timed out", read.items[3].outcomeLabel)
    }

    @Test
    fun `an outcome this phone does not know is never guessed at`() {
        val read = decode("""[{"id": "a", "created": 1000, "state": "something newer"}]""")
        assertEquals("Not reported", read.items[0].outcomeLabel)
        // And it is offered no filter of its own: a chip for it would be a
        // fourth word no card can carry.
        assertFalse(PastApprovals.OUTCOME_WORDS.contains("Not reported"))
    }

    @Test
    fun `which device decided it comes from the row, and says nothing when the row is silent`() {
        val read = decode(
            """
            [
              {"id": "a", "created": 1, "state": "approved", "decided_by": "this PC"},
              {"id": "b", "created": 2, "state": "approved", "device": "another device"},
              {"id": "c", "created": 3, "state": "approved", "by": "this PC"},
              {"id": "d", "created": 4, "state": "approved"}
            ]
            """.trimIndent(),
        )
        assertEquals("this PC", read.items[0].device)
        assertEquals("another device", read.items[1].device)
        assertEquals("this PC", read.items[2].device)
        // No invented "this PC": a row that names no device says nothing.
        assertNull(read.items[3].device)
    }

    @Test
    fun `when to show is the decision time if there is one, else when it was raised`() {
        val read = decode(
            """
            [
              {"id": "a", "created": 1000, "decided_at": 1010, "state": "approved"},
              {"id": "b", "created": 2000, "state": "approved"}
            ]
            """.trimIndent(),
        )
        assertEquals(1010.0, read.items[0].whenAt, 0.001)
        assertEquals(2000.0, read.items[1].whenAt, 0.001)
    }

    @Test
    fun `a row with no id costs that row and nothing else`() {
        val read = decode(
            """
            [
              {"created": 1, "state": "approved"},
              {"id": "b", "created": 2, "state": "denied"}
            ]
            """.trimIndent(),
        )
        assertEquals(1, read.items.size)
        assertEquals(1, read.skipped)
        assertEquals("b", read.items[0].id)
    }

    @Test
    fun `the title is the PC's own, and never the payload`() {
        val read = decode(
            """
            [
              {"id": "a", "action": "send_email", "created": 1, "state": "approved",
               "notice": {"title": "Jarvis wants to send an email", "body": "to the doctor"}},
              {"id": "b", "action": "run_command", "created": 2, "state": "approved"}
            ]
            """.trimIndent(),
        )
        assertEquals("Jarvis wants to send an email", read.items[0].title)
        // The notice's one-line body is the summary when the row says no more.
        assertEquals("to the doctor", read.items[0].summary)
        // No notice: the same action-name fallback a live card with no notice
        // uses (CardWords.fallbackTitle) - which reads neither `detail` nor
        // `prompt`, the two columns a decided row never carries anyway.
        assertEquals("Jarvis wants your OK for \"run command\"", read.items[1].title)
    }

    // ------------------------------------------------------------- the rule ----

    @Test
    fun `a filter shows its own outcome only, newest decision first`() {
        val items = listOf(
            item("old", state = "approved", createdAt = 1000.0),
            item("new", state = "approved", decidedAt = 5000.0, createdAt = 4000.0),
            item("denied", state = "denied", createdAt = 3000.0),
            item("out", state = "expired", createdAt = 2000.0),
            item("unknown", state = "something newer", createdAt = 6000.0),
        )
        assertEquals(listOf("new", "old"), PastApprovals.rows(items, "approved").map { it.id })
        assertEquals(listOf("denied"), PastApprovals.rows(items, "denied").map { it.id })
        assertEquals(listOf("out"), PastApprovals.rows(items, "timed_out").map { it.id })
        // All is every row, newest decision first - including the one this
        // phone could not read an outcome for.
        assertEquals(
            listOf("unknown", "new", "denied", "out", "old"),
            PastApprovals.rows(items, PastApprovals.ALL).map { it.id },
        )
        // "Not reported" belongs to no outcome, so the three outcome filters
        // can never quietly claim it.
        for (chip in PastApprovals.FILTERS.filter { it.id != PastApprovals.ALL }) {
            assertFalse(chip.id, PastApprovals.rows(items, chip.id).any { it.id == "unknown" })
        }
    }

    @Test
    fun `a filter this phone does not know hides nothing`() {
        val items = listOf(item("a", state = "approved", createdAt = 1.0))
        assertEquals(listOf("a"), PastApprovals.rows(items, "a-filter-from-a-newer-app").map { it.id })
    }

    @Test
    fun `the chips are the desktop's four words`() {
        assertEquals(
            listOf("all", "approved", "denied", "timed_out"),
            PastApprovals.FILTERS.map { it.id },
        )
        assertEquals(listOf("All", "Approved", "Denied", "Timed out"), PastApprovals.FILTERS.map { it.label })
        // The three outcome chips are literally the words outcomeLabel makes,
        // so a chip can never offer an outcome no row can carry.
        assertEquals(PastApprovals.OUTCOME_WORDS, PastApprovals.FILTERS.drop(1).map { it.label })
        // ...and every outcome filter has its own "nothing here was ..." line.
        assertEquals(
            PastApprovals.FILTERS.filter { it.id != PastApprovals.ALL }.map { it.id }.toSet(),
            PastApprovals.NONE_THIS_WAY.keys,
        )
    }

    // ------------------------------------------------------------- the words ----

    @Test
    fun `the empty list says so in the desktop's own words`() {
        // jarvis-desktop/src/brain.js renderActivity's last argument. One
        // sentence for one thing, on both apps.
        assertEquals("Nothing decided yet.", PastApprovals.EMPTY)
        assertEquals("Past approvals", PastApprovals.TITLE)
        assertTrue(PastApprovals.LEAD.contains("Read-only"))
        assertTrue(PastApprovals.ENTRY_ABOUT.contains("read-only"))
    }

    // ------------------------------------------------------------ the source ----

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    @Test
    fun `the screen names nothing that could decide a card`() {
        // Read-only means the screen never reaches for the decision surface at
        // all: no approve/deny callback, no card, no runtime decision call, no
        // rush-latch clear. A button cannot be added here without failing this.
        val src = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ApprovalsScreen.kt",
        ).readText()
        for (name in listOf(
            "onApprove", "onDeny", "ApprovalCard", "decideDetached", "decisionBlocker",
            "approveItem", "clearRush", "pending(", "JarvisRuntime.decide",
        )) {
            assertFalse("ApprovalsScreen names $name", src.contains(name))
        }
        // It reads the list the same way everything else does - through the
        // callback the screen is handed, never a network call of its own.
        assertTrue(src.contains("onRead"))
    }

    @Test
    fun `the history half is asked for by name, so a decided card is never a waiting one`() {
        // The real `/api/pending` body carries both arrays. The reader that
        // feeds this screen names `history`; the positional fallback would
        // refuse it as an already-handled key and return nothing, which is the
        // correct failure - but naming it is what actually gets the rows.
        val body = """
            {"available": true,
             "pending": [{"id": "waiting", "title": "Still waiting"}],
             "history": [{"id": "decided", "state": "approved", "created": 1000}]}
        """.trimIndent()
        val read = parseListBody(
            body,
            ListSerializer(JsonElement.serializer()),
            listOf("history"),
        )
        val rows = (read as ApiResult.Ok).value
        assertEquals(1, rows.size)
        assertEquals("decided", decodeGateHistoryRows(rows).items[0].id)
        // And the queue's own reader still takes the other array, so the two
        // lists cannot swap places behind the same route.
        val queue = parseListBody(
            body,
            ListSerializer(JsonElement.serializer()),
            JarvisApi.PENDING_KEYS,
        )
        val pending = (queue as ApiResult.Ok).value
        assertEquals(1, pending.size)
        assertEquals("waiting", pending[0].jsonObject["id"]!!.jsonPrimitive.content)
    }
}
