package com.jarvis.client

import com.jarvis.client.net.Approvals
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F6, 2026-11-03 - conversation clearing is two-phase and per item. DEF-047
 * (2026-11-15) is the half that was missing: the phone's Delete posted the
 * older UNcarded route, so the card this file talks about was never raised and
 * a conversation could be deleted with no approval at all.
 *
 * The phone asks the PC to clear ONE conversation, naming its exact id, at the
 * CARDED route `POST /api/conversations/clear`. The PC raises ONE
 * `conversation_clear` card naming that conversation, saying it cannot be
 * undone and that the facts learned from it are kept. Nothing is deleted until
 * the owner answers that card.
 *
 * The defects this file exists to prevent are small and sharp:
 * - a waiting answer (202 / `waiting: true`) read as "deleted", so the row
 *   vanished from the phone while the conversation was still on the PC - and,
 *   worse, the owner was told their chat was gone when the card was still
 *   waiting for an answer;
 * - the request going to a route that never raises that card (DEF-047).
 */
class ConversationClearTest {

    private fun obj(text: String): JsonObject = JarvisJson.parseToJsonElement(text) as JsonObject

    // -------------------------------------------------------- the waiting shape ---

    @Test
    fun `a waiting answer is never read as deleted`() {
        // 202 is the status the carded route answers; `waiting` the boolean;
        // `asking` the third spelling the backend uses elsewhere.
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

    /**
     * The exact phase-one answer `jarvis_self_portrait.clear_request` returns
     * (jarvis-backend/jarvis_self_portrait.py:1400-1403): 202, ok, waiting,
     * the id, the title, the message count, the action and one sentence saying
     * nothing is deleted unless the card is approved. This is the answer the
     * phone's Delete must read as "a card is waiting", and the field that
     * matters is `waiting` - the status alone is also enough.
     */
    @Test
    fun `the route's own 202 waiting answer is read as a card, not a delete`() {
        val body = obj(
            """{"ok":true,"waiting":true,"id":"abcd1234","title":"Boiler","messages":2,""" +
                """"action":"conversation_clear","message":"Waiting for your approval. Nothing is """ +
                """deleted unless you approve the card."}""",
        )
        val reply = ChatLog.deleteReply(202, body)
        assertFalse("the carded route's 202 was read as a delete", reply.gone)
        assertTrue("the carded route's 202 was not read as waiting", reply.waiting)
        assertEquals(ChatLog.DELETE_WAITING, reply.said)
        assertTrue("the waiting sentence must say where the card is answered", reply.said.contains(Approvals.WHERE))
        assertTrue(reply.said.contains("Nothing is deleted until you do"))
    }

    @Test
    fun `a waiting answer leaves the list unchanged`() {
        // The History screen's own rule, modelled: rows are removed only in the
        // `reply.gone` branch (HistoryScreen.kt deleteChat). Drive the pure
        // answer through it and the list must be exactly what it was.
        val rows = listOf("abcd1234", "efgh5678", "ijkl9012")
        fun after(reply: ChatLog.Delete, goneId: String): List<String> =
            if (reply.gone) rows.filterNot { it == goneId } else rows

        val waiting = ChatLog.deleteReply(202, obj("""{"ok":true,"waiting":true}"""))
        assertEquals("a waiting answer removed a row", rows, after(waiting, "abcd1234"))

        // A refusal leaves it there too, in the PC's own words.
        val refused = ChatLog.deleteReply(
            409,
            obj("""{"ok":false,"error":"A card for clearing a conversation is already waiting - answer it first."}"""),
        )
        assertFalse(refused.gone)
        assertEquals(rows, after(refused, "abcd1234"))

        // Only the PC's own "the conversation is not there" removes it.
        val gone = ChatLog.deleteReply(404, obj("""{"ok":false,"error":"no such conversation - it may already have been deleted"}"""))
        assertTrue(gone.gone)
        assertEquals(listOf("efgh5678", "ijkl9012"), after(gone, "abcd1234"))
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
        // ...and after an approval the PC's card keeps them, so the phone says
        // the same thing rather than claiming a Forget that never happened.
        val gone = ChatLog.CARD_ANSWERED_GONE_TICKED
        assertTrue(gone.contains("NOT forgotten"))
        assertTrue(gone.contains("Memory"))
        assertTrue(gone.startsWith("Deleted from your PC."))
    }

    // --------------------------------------------------------- the real answers ---

    @Test
    fun `a 2xx that is not a waiting answer is the PC saying it deleted it`() {
        // The carded route has no such answer today (its only 2xx is the 202
        // waiting one); this pins that an unknown success is never read as a
        // refusal, so a future shape cannot strand a conversation.
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
    fun `the carded route's own refusals are not deletes`() {
        // jarvis_self_portrait.clear_request's four `ok: false` answers, in its
        // own words (jarvis-backend/jarvis_self_portrait.py:1347-1398).
        for ((code, error) in listOf(
            400 to """Send exactly {"id": "<conversation id>"} - one conversation per request. There is no bulk clear.""",
            409 to "A card for clearing a conversation is already waiting - answer it first.",
            423 to """Hidden while App lock or "Hide memory lists and chat history" is on.""",
            503 to "chat history is not available on this PC",
        )) {
            val body = buildJsonObject {
                put("ok", JsonPrimitive(false))
                put("error", JsonPrimitive(error))
            }
            val reply = ChatLog.deleteReply(code, body)
            assertFalse("$code was read as a delete", reply.gone)
            assertFalse("$code was read as waiting", reply.waiting)
            assertTrue("$code did not start with Not deleted.", reply.said.startsWith("Not deleted."))
            // DesktopWrite.asSentence capitalises the first letter and adds a
            // full stop, so compare from the second character on.
            assertTrue("$code lost the PC's own words", reply.said.contains(error.drop(1).take(19)))
        }
    }

    /**
     * DEF-047's second half: an older PC has no `/api/conversations/clear`, and
     * the API reads that as [com.jarvis.client.net.ApiError.NotFound] (a 404
     * with no `ok` body) - which is NOT "already gone". The phone must not fall
     * back to the uncarded route and must not remove the row.
     */
    @Test
    fun `an older PC without the carded route deletes nothing and says so`() {
        val said = ChatLog.CLEAR_OLD_PC
        assertTrue("must say nothing was deleted", said.startsWith("Nothing was deleted"))
        assertTrue("must say the PC is older", said.contains("older"))
        assertTrue("must name the way to fix it", said.contains("apply-patches.ps1"))

        val runtime = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
        )
        val fn = runtime.indexOf("suspend fun deleteHistory(id: String)")
        assertTrue("the runtime's delete is gone", fn > 0)
        val body = runtime.substring(fn, fn + 1500)
        assertTrue("a 404 with no route must be read as an older PC", body.contains("r.error == ApiError.NotFound"))
        assertTrue("an older PC must say nothing was deleted", body.contains("words.CLEAR_OLD_PC"))
        assertFalse("an older PC must never be read as already gone", body.contains("words.ALREADY_GONE"))
        assertFalse("the uncarded route must never be called", body.contains("/api/history/delete"))
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
     * DEF-047: the phone must post the CARDED route, and the uncarded one must
     * not be reachable from the phone's own sources at all. Pinned as source
     * text because a JVM test cannot send a request.
     */
    @Test
    fun `the phone posts to the carded route and never the uncarded one`() {
        assertEquals("/api/conversations/clear", ChatLog.CLEAR_PATH)
        val chatLog = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/net/ChatLog.kt",
        )
        assertTrue(
            "the carded route is not the one Delete posts",
            chatLog.contains("CLEAR_PATH = \"/api/conversations/clear\""),
        )
        assertFalse("the uncarded route is still named in ChatLog.kt", chatLog.contains("/api/history/delete"))

        val api = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt",
        )
        val apiCall = api.indexOf("suspend fun deleteHistory(")
        assertTrue("the per-conversation delete call is gone", apiCall > 0)
        val call = api.substring(apiCall, apiCall + 700)
        assertTrue(
            "deleteHistory must post the carded route",
            call.contains("historyWrite(ChatLog.CLEAR_PATH, ChatLog.deleteBody(id))"),
        )
        assertFalse("deleteHistory still names the uncarded path constant", call.contains("DELETE_PATH"))
        assertFalse("deleteHistory still names the uncarded route", call.contains("/api/history/delete"))
    }

    /** The sentence beside the button must match what happens: a card comes first. */
    @Test
    fun `the confirm says the card comes before anything is deleted`() {
        val said = ChatLog.DELETE_CONFIRM
        assertTrue("the confirm does not mention the card", said.contains("approve the card"))
        assertTrue("the confirm must still say it cannot be undone", said.contains("cannot be undone"))
        assertTrue("the confirm lost the kept-facts half", said.contains(ChatLog.DELETE_KEEPS_FACTS))
    }

    /**
     * The wire and the screen are pinned by source text because a pure test
     * cannot send a request or compose the History screen: the API must return
     * the status (or a 202 waiting would be invisible), the runtime must read
     * the waiting half, and the screen must keep the row until the PC's own
     * list says it is really gone - and then say which answer it was.
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
            "deleteHistory must post the carded route",
            api.substring(apiCall, apiCall + 500).contains("ChatLog.CLEAR_PATH"),
        )

        val runtime = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
        )
        val fn = runtime.indexOf("suspend fun deleteHistory(id: String)")
        assertTrue("the runtime's delete is gone", fn > 0)
        val body = runtime.substring(fn, fn + 1500)
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
        // ...and it says which answer it was, from the PC's own list.
        assertTrue("the list does not say the card's answer", screen.contains("ChatLog.CARD_ANSWERED_KEPT"))
        assertTrue("the list does not say the delete the PC confirmed", screen.contains("ChatLog.CARD_ANSWERED_GONE"))
        assertTrue("the watch does not remember which chat it was about", screen.contains("clearAskedFor = row.id"))
        // No bulk control and no "all" request from the phone, per RESEARCH F8.
        assertFalse("a bulk delete control was added to History", screen.contains("Delete all conversations"))
        assertFalse("a bulk delete control was added to History", screen.contains("Yes, delete all"))
    }
}
