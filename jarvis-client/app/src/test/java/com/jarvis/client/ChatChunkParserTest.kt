package com.jarvis.client

import com.jarvis.client.net.ChatChunkParser
import com.jarvis.client.net.JarvisApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `/api/chat` is the one route whose framing this app cannot pin down in
 * advance: the server copies the upstream `Content-Type` verbatim, so the same
 * endpoint answers in SSE on one model and in raw tokens on another
 * (`docs/API-DISAGREEMENTS.md` §4). Every case below is a shape that reached
 * the owner's screen wrong at some point, so each one is a regression test
 * rather than a tour of the parser.
 */
class ChatChunkParserTest {

    private fun text(line: String): String {
        val r = ChatChunkParser.consume(line)
        assertTrue("expected text from: $line, got $r", r is ChatChunkParser.Result.Text)
        return (r as ChatChunkParser.Result.Text).delta
    }

    private fun failure(line: String): String {
        val r = ChatChunkParser.consume(line)
        assertTrue("expected a failure from: $line, got $r", r is ChatChunkParser.Result.Failed)
        return (r as ChatChunkParser.Result.Failed).message
    }

    // ------------------------------------------------------------ shapes ---

    @Test
    fun `an SSE delta chunk yields its content`() {
        assertEquals(
            "hi",
            text("""data: {"choices":[{"delta":{"content":"hi"}}]}"""),
        )
    }

    @Test
    fun `DONE ends the stream`() {
        assertEquals(ChatChunkParser.Result.Terminal, ChatChunkParser.consume("data: [DONE]"))
    }

    @Test
    fun `a final word and a finish reason in one chunk give both`() {
        val r = ChatChunkParser.consume(
            """data: {"choices":[{"delta":{"content":"."},"finish_reason":"stop"}]}""",
        )
        assertEquals(ChatChunkParser.Result.Text(".", terminal = true), r)
    }

    /**
     * The lenient-JSON bug. `JarvisJson` sets `isLenient = true`, and lenient
     * mode parses a bare word as a non-string primitive - so `Done` parsed
     * successfully, failed the `isString` test, fell through the `!is
     * JsonObject` line and was discarded. A model whose whole reply was one
     * plain token rendered nothing, while `Yes, I did.` rendered fine, because
     * the space makes it invalid even leniently.
     */
    @Test
    fun `a bare token that happens to look like a JSON literal is still text`() {
        assertEquals("Done", text("Done"))
        assertEquals("Yes", text("Yes"))
        assertEquals("Yes, I did.", text("Yes, I did."))
    }

    // ------------------------------------------------------------ errors ---

    @Test
    fun `an error string is reported`() {
        assertEquals("model not loaded", failure("""{"error":"model not loaded"}"""))
    }

    @Test
    fun `an error object is reported by its message`() {
        assertEquals(
            "context length exceeded",
            failure("""{"error":{"message":"context length exceeded","code":400}}"""),
        )
    }

    /**
     * The silent one. An error with no message returned null, null meant "not
     * an error", and the chunk came back `Ignored` - so the stream ran on to a
     * closed socket and `send` returned an empty reply with no error set. On
     * screen that is a question that visibly did nothing.
     */
    @Test
    fun `an error with nothing readable in it is still an error`() {
        assertTrue(failure("""{"error":{}}""").isNotBlank())
        assertTrue(failure("""{"error":[]}""").isNotBlank())
        // A type or a detail is worth showing when there is no message.
        assertEquals("overloaded", failure("""{"error":{"type":"overloaded"}}"""))
        assertEquals("no model", failure("""{"error":{"detail":"no model"}}"""))
    }

    /**
     * The other half of the same function. The old comment claimed `false` and
     * `0` were read as "no error"; they were rendered as the strings "false"
     * and "0", both non-blank, so a chunk that said there was NO error was
     * shown to the owner as an error called "false".
     */
    @Test
    fun `a falsy error field is not an error`() {
        assertEquals(ChatChunkParser.Result.Ignored, ChatChunkParser.consume("""{"error":false}"""))
        assertEquals(ChatChunkParser.Result.Ignored, ChatChunkParser.consume("""{"error":0}"""))
        assertEquals(ChatChunkParser.Result.Ignored, ChatChunkParser.consume("""{"error":null}"""))
        assertEquals(ChatChunkParser.Result.Ignored, ChatChunkParser.consume("""{"error":""}"""))
    }

    @Test
    fun `an error alongside text still fails rather than rendering the text`() {
        assertEquals(
            "boom",
            failure("""{"error":{"message":"boom"},"choices":[{"delta":{"content":"hi"}}]}"""),
        )
    }

    // ------------------------------------------------------------- token ---

    /**
     * Not the parser, but the same request path and a standing rule: never log
     * the token. OkHttp validates header values and, on a bad character,
     * throws with the value in the exception message - it withholds values only
     * for the four headers it knows are sensitive, and `X-Jarvis-Token` is not
     * one of them. That message is logged and, in `ChatSession`, shown on
     * screen.
     */
    @Test
    fun `a token with characters illegal in a header is stripped, not thrown`() {
        assertEquals("abc123", JarvisApi.headerSafe("abc123"))
        assertEquals("abc123", JarvisApi.headerSafe("abc\n123"))
        assertEquals("abc123", JarvisApi.headerSafe("abc 123"))
        assertEquals("abc123", JarvisApi.headerSafe("abc​123"))
        assertEquals("abc123", JarvisApi.headerSafe("abc’123"))
        // Everything printable and non-space survives untouched: a pairing
        // token is base64url or hex, and stripping any of that would turn a
        // working pairing into a 401 nobody could explain.
        val real = "aB3-_.~+/=abcdefghijklmnopqrstuvwxyz0123456789"
        assertEquals(real, JarvisApi.headerSafe(real))
        assertFalse(JarvisApi.headerSafe("abc\n123").contains('\n'))
    }
}
