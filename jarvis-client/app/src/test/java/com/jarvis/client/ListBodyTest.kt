package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.net.parseListBody
import kotlinx.serialization.builtins.ListSerializer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wrappers the server actually uses.
 *
 * Every shape below was copied out of `jarvis_hud.py`, not out of the prose.
 * The prose is what produced the bug: the API doc shows `/api/pending` as a
 * bare array in one place and wrapped in another, so this client accepted both
 * and guessed `items` for the wrapper — a key that route does not use. Live,
 * that would have rendered every arriving approval as "nothing waiting".
 */
class ListBodyTest {

    private fun pending(text: String) =
        parseListBody(text, ListSerializer(PendingItem.serializer()), JarvisApi.PENDING_KEYS)

    @Test
    fun `pending comes back under 'pending', which is what the server sends`() {
        val body = """
            {"available": true,
             "pending": [{"id": "a1", "title": "Send the email"}],
             "history": [{"id": "old"}]}
        """.trimIndent()
        val out = pending(body)
        assertTrue("the real server shape did not parse", out is ApiResult.Ok)
        val items = (out as ApiResult.Ok).value
        assertEquals(1, items.size)
        assertEquals("a1", items[0].id)
        assertEquals("Send the email", items[0].title)
    }

    @Test
    fun `history is not mistaken for the queue`() {
        // Both are arrays and `history` is the decided ones. Taking the wrong
        // array would offer the user decisions they have already made.
        val body = """{"available": true, "history": [{"id": "old"}], "pending": [{"id": "a1"}]}"""
        val items = (pending(body) as ApiResult.Ok).value
        assertEquals(1, items.size)
        assertEquals("a1", items[0].id)
    }

    @Test
    fun `a bare array still works`() {
        val items = (pending("""[{"id": "a1"}]""") as ApiResult.Ok).value
        assertEquals("a1", items[0].id)
    }

    @Test
    fun `an unknown wrapper key still finds the list`() {
        // The point of the fallback: a route that renames its key degrades to
        // working rather than to empty.
        val items = (pending("""{"available": true, "queue": [{"id": "a1"}]}""") as ApiResult.Ok).value
        assertEquals("a1", items[0].id)
    }

    @Test
    fun `available false is not an empty queue`() {
        // Gating switched off. "There is no approval queue here" and "the
        // approval queue is empty" are different sentences and only one of
        // them is reassuring.
        val out = pending("""{"available": false, "pending": []}""")
        assertTrue(out is ApiResult.Failed)
        assertEquals(ApiError.NotAvailable, (out as ApiResult.Failed).error)
    }

    @Test
    fun `the other three routes use three more keys`() {
        val digest = parseListBody(
            """{"available": true, "digest": [{"id": "d1"}]}""",
            ListSerializer(DigestItem.serializer()), JarvisApi.DIGEST_KEYS,
        )
        assertEquals("d1", (digest as ApiResult.Ok).value[0].id)

        val undo = parseListBody(
            """{"available": true, "shelf": [{"id": "u1"}], "status": {"count": 1}}""",
            ListSerializer(UndoEntry.serializer()), JarvisApi.UNDO_KEYS,
        )
        assertEquals("u1", (undo as ApiResult.Ok).value[0].id)

        val jobs = parseListBody(
            """{"available": true, "jobs": [{"id": "j1"}], "status": {"running": 1}}""",
            ListSerializer(JobRecord.serializer()), JarvisApi.JOB_KEYS,
        )
        assertEquals("j1", (jobs as ApiResult.Ok).value[0].id)
    }

    @Test
    fun `an unknown field does not break the parse`() {
        // The three clients ship on different schedules; a field this build
        // has never heard of must not turn into "the backend stopped working".
        val items = (pending("""{"available": true, "pending": [{"id": "a1", "invented": 7}]}""")
            as ApiResult.Ok).value
        assertEquals("a1", items[0].id)
    }

    /**
     * The exact shape `/api/pending` sends, with an empty list omitted.
     *
     * The positional fallback used to take the first array it met, so `history`
     * was handed back as the pending queue: items already decided, shown as
     * waiting for a decision, and approving one would post a verdict on a
     * request closed days ago. It decodes cleanly because PendingItem needs
     * only an id, so nothing downstream could tell.
     */
    @Test
    fun `history is never mistaken for pending`() {
        val body = """
            {"available": true,
             "history": [{"id": "a1", "title": "Sent the email to Dana"}]}
        """.trimIndent()
        val r = parseListBody(body, ListSerializer(PendingItem.serializer()), JarvisApi.PENDING_KEYS)
        assertTrue(
            "an object with only a history array must not be read as the pending queue",
            r is ApiResult.Failed,
        )
    }

    /** Two arrays and neither is a known key: there is no principled choice. */
    @Test
    fun `an ambiguous object is refused rather than guessed`() {
        val body = """{"history": [{"id": "a"}], "archive": [{"id": "b"}]}"""
        val r = parseListBody(body, ListSerializer(PendingItem.serializer()), JarvisApi.PENDING_KEYS)
        assertTrue(r is ApiResult.Failed)
    }

    /**
     * The same rule, on a different name, so the guard is a set and not one
     * special case. `history` was the shape the server actually sends; these
     * are the names that mean the same thing and would decode just as cleanly.
     */
    @Test
    fun `a lone settled-records array is refused whatever it is called`() {
        for (key in listOf("archive", "archived", "done", "completed", "handled", "past")) {
            val body = """{"available": true, "$key": [{"id": "a1"}]}"""
            val r = parseListBody(
                body, ListSerializer(PendingItem.serializer()), JarvisApi.PENDING_KEYS,
            )
            assertTrue("`$key` alone must not be read as the pending queue", r is ApiResult.Failed)
        }
    }

    /** One unrecognised array is still unambiguous, so it is still accepted. */
    @Test
    fun `a single array under an unknown key is still read`() {
        val body = """{"available": true, "queue": [{"id": "a1"}]}"""
        val r = parseListBody(body, ListSerializer(PendingItem.serializer()), JarvisApi.PENDING_KEYS)
        assertTrue(r is ApiResult.Ok)
        assertEquals(1, (r as ApiResult.Ok).value.size)
    }

    /** A named key wins even when other arrays are present. */
    @Test
    fun `the named key beats any other array`() {
        val body = """
            {"available": true,
             "history": [{"id": "old"}],
             "pending": [{"id": "new"}]}
        """.trimIndent()
        val r = parseListBody(body, ListSerializer(PendingItem.serializer()), JarvisApi.PENDING_KEYS)
        assertTrue(r is ApiResult.Ok)
        assertEquals("new", (r as ApiResult.Ok).value.single().id)
    }

    /**
     * `available:false` must be seen even on a route whose model defaults every
     * field — which is all of them. The check used to run only after the direct
     * decode failed, and for a fully-defaulted model it never fails, so
     * `/api/attention` answering `{"available": false}` produced an all-zero
     * budget and the UI read "0 of 0 spoken interruptions left today".
     */
    @Test
    fun `available false is seen even when the model would decode anyway`() {
        val r = parseListBody(
            """{"available": false}""",
            ListSerializer(PendingItem.serializer()),
            JarvisApi.PENDING_KEYS,
        )
        assertTrue(r is ApiResult.Failed)
        assertEquals(ApiError.NotAvailable, (r as ApiResult.Failed).error)
    }
}
