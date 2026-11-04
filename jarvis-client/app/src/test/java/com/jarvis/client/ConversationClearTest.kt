package com.jarvis.client

import com.jarvis.client.net.Approvals
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F6, 2026-11-03 - conversation clearing is two-phase and per item.
 *
 * The phone asks the PC to clear ONE conversation, naming its exact id. The PC
 * raises ONE approval card naming that conversation, saying it cannot be
 * undone and that the facts learned from it are kept. Nothing is deleted until
 * the owner answers that card.
 *
 * The defect this file exists to prevent is small and sharp: a waiting answer
 * (202 / `waiting: true`) read as "deleted", so the row vanished from the phone
 * while the conversation was still on the PC - and, worse, the owner was told
 * their chat was gone when the card was still waiting for an answer. So every
 * waiting spelling is asserted as NOT gone, exactly as every real answer is.
 */
class ConversationClearTest {

    private fun obj(text: String): JsonObject = JarvisJson.parseToJsonElement(text) as JsonObject

    // -------------------------------------------------------- the waiting shape ---

    @Test
    fun `a waiting answer is never read as deleted`() {
        // 202 is the status the PC's other two-phase routes use; `waiting` the
        // boolean; `asking` the third spelling the backend uses elsewhere.
        for ((code, body) in listOf(
            202 to null,
            202 to """{"ok":true}""",
            200 to """{"ok":true,"waiting":true}""",
            200 to """{"ok":true,"asking":true}""",
        )) {
            val reply = ChatLog.deleteReply(code, body?.let(::obj))
            assertFalse("$code $body: a waiting answer claimed the chat was deleted", reply.gone)
            assertTrue("$code $body: a waiting answer was not reported as waiting", reply.waiting)
            assertEquals("$code $body: wrong sentence", ChatLog.DELETE_WAITING, reply.said)
        }
    }

    @Test
    fun `the waiting sentence says the card is needed and what is kept`() {
        val said = ChatLog.DELETE_WAITING
        // A card, on the phone as well as the PC, and nothing yet.
        assertTrue(said.contains(Approvals.WHERE))
        assertTrue(said.contains("Nothing is deleted until you do"))
        // The same words every other delete uses, so the phone and the PC's
        // card cannot disagree about what is kept.
        assertTrue(said.contains(ChatLog.DELETE_STAYS))
        assertTrue(said.contains("Facts Jarvis learned"))
        // Never an instruction to approve in bulk, and never "cannot be undone"
        // without the kept-facts half.
        assertFalse(said.contains("all conversations", ignoreCase = true))
    }

    @Test
    fun `ticked facts are honestly left alone while the card waits`() {
        val said = ChatLog.DELETE_WAITING_TICKED
        assertTrue(said.contains("NOT been forgotten"))
        assertTrue(said.contains("Memory"))
        assertTrue(said.contains(Approvals.WHERE))
    }

    // --------------------------------------------------------- the real answers ---

    @Test
    fun `a normal answer from a PC without cards still deletes`() {
        val reply = ChatLog.deleteReply(200, obj("""{"ok":true}"""))
        assertTrue(reply.gone)
        assertFalse(reply.waiting)
        assertEquals("Deleted from your PC.", reply.said)

        val withWords = ChatLog.deleteReply(200, obj("""{"ok":true,"message":"deleted"}"""))
        assertTrue(withWords.gone)
        assertEquals("Deleted.", withWords.said)
    }

    @Test
    fun `a refusal in the PC's own words is not a delete`() {
        val reply = ChatLog.deleteReply(200, obj("""{"ok":false,"error":"the history store is locked"}"""))
        assertFalse(reply.gone)
        assertFalse(reply.waiting)
        assertEquals("Not deleted. The history store is locked.", reply.said)
        val bare = ChatLog.deleteReply(200, obj("""{"ok":false}"""))
        assertEquals("Not deleted. Your PC said no, without a reason.", bare.said)
    }

    @Test
    fun `an already-deleted conversation is gone, including a 404 that explains itself`() {
        assertTrue(ChatLog.deleteReply(404, null).gone)
        assertEquals(ChatLog.ALREADY_GONE, ChatLog.deleteReply(404, null).said)
        // A newer PC may say WHY in the body; the row is gone either way.
        assertTrue(ChatLog.deleteReply(404, obj("""{"ok":false,"error":"not_found"}""")).gone)
    }

    @Test
    fun `any other answer leaves the row and says why`() {
        val refusedToken = ChatLog.deleteReply(401, null)
        assertFalse(refusedToken.gone)
        assertTrue(refusedToken.said.contains("pairing token"))

        val odd = ChatLog.deleteReply(500, obj("""{"error":"the database is busy"}"""))
        assertFalse(odd.gone)
        assertTrue(odd.said.startsWith("Not deleted."))
        assertTrue(odd.said.contains("The database is busy."))
    }

    // ------------------------------------------------------------ per item, always ---

    @Test
    fun `the request carries exactly one id and nothing else`() {
        val body = obj(ChatLog.deleteBody("abcd1234"))
        assertEquals(setOf("id"), body.keys)
        assertEquals("abcd1234", body["id"].toString().trim('"'))
    }

    /**
     * The wire and the screen are pinned by source text because a pure test
     * cannot send a request or compose the History screen: the API must return
     * the status (or a 202 waiting would be invisible), the runtime must read
     * the waiting half, and the screen must keep the row until the PC says it
     * is really gone.
     */
    @Test
    fun `the two-phase wiring is still in place`() {
        val api = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt",
        )
        val apiCall = api.indexOf("suspend fun deleteHistory(")
        assertTrue("the per-conversation delete route is gone", apiCall > 0)
        assertTrue(
            "deleteHistory must return the status: a 202 waiting is not visible from the body alone",
            api.substring(apiCall, apiCall + 500).contains("ApiResult<Pair<Int, JsonObject?>>"),
        )
        assertTrue(
            "deleteHistory must be sent as one id - historyWrite carries the id body",
            api.substring(apiCall, apiCall + 500).contains("ChatLog.DELETE_PATH"),
        )

        val runtime = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
        )
        val fn = runtime.indexOf("suspend fun deleteHistory(")
        assertTrue("the runtime's delete is gone", fn > 0)
        val body = runtime.substring(fn, fn + 1600)
        assertTrue("the runtime no longer reads the waiting half", body.contains("words.deleteReply("))
        assertTrue("chatsGone must run only once the PC says it is gone", body.contains("if (reply.gone) chatsGone(listOf(id))"))
        assertTrue("a raised card must appear on the phone", body.contains("refreshPending()"))
        assertFalse(
            "a waiting answer must not remove the chat Home is in",
            body.contains("if (reply.waiting) chatsGone"),
        )

        val screen = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt",
        )
        assertTrue("the row goes only after the PC says it is gone", screen.contains("val reply = JarvisRuntime.deleteHistory(row.id)"))
        assertTrue("a waiting answer must keep the row", screen.contains("if (reply.waiting) {"))
        assertTrue("the list must read itself again after the card is answered", screen.contains("LaunchedEffect(pendingIds, clearWatch)"))
        assertTrue("the watch must be the actual card ids", screen.contains("clearWatch = JarvisRuntime.pending.value"))
        // No bulk control and no "all" request from the phone, per RESEARCH F8.
        assertFalse("a bulk delete control was added to History", screen.contains("Delete all conversations"))
        assertFalse("a bulk delete control was added to History", screen.contains("Yes, delete all"))
    }
}
