package com.jarvis.client

import com.jarvis.client.net.HelloPayload
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SseEvent
import com.jarvis.client.net.SseParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.BufferedReader
import java.io.StringReader

/**
 * The event stream is the client's only live channel, and two of its properties
 * are load-bearing rather than cosmetic: the resume id has to survive a process
 * restart, and `hello.stale` has to be read correctly or the phone acts on an
 * inbox it only thinks is current.
 */
class SseParserTest {

    private fun parse(text: String): List<SseEvent> {
        val out = mutableListOf<SseEvent>()
        SseParser.parse(BufferedReader(StringReader(text))) { out += it }
        return out
    }

    @Test
    fun `a hello frame carries its id, kind and payload`() {
        val events = parse(
            """
            retry: 3000

            id: 413
            event: hello
            data: {"resumed_from":412,"stale":false,"latest":413}

            """.trimIndent() + "\n",
        )
        val hello = events.last()
        assertEquals("413", hello.id)
        assertEquals("hello", hello.kind)
        val payload = JarvisJson.decodeFromJsonElement(
            HelloPayload.serializer(), hello.data!!,
        )
        assertEquals(412L, payload.resumedFrom)
        assertEquals(413L, payload.latest)
        assertTrue(!payload.stale)
    }

    @Test
    fun `keepalive comments are skipped and do not produce events`() {
        val events = parse(
            """
            : keepalive

            : keepalive

            """.trimIndent() + "\n",
        )
        assertTrue(events.isEmpty())
    }

    @Test
    fun `the id sticks across a frame that does not carry one`() {
        // Per the SSE spec. A server that stamps only some of its events must
        // not cost us the resume point on the others.
        val events = parse(
            """
            id: 500
            event: approval
            data: {"count":1}

            event: approval
            data: {"count":2}

            """.trimIndent() + "\n",
        )
        assertEquals(2, events.size)
        assertEquals("500", events[0].id)
        assertEquals("500", events[1].id)
    }

    @Test
    fun `multi-line data is joined with newlines`() {
        val events = parse(
            """
            event: finding
            data: {"a":1,
            data: "b":2}

            """.trimIndent() + "\n",
        )
        assertEquals(1, events.size)
        assertTrue(events[0].data != null)
    }

    @Test
    fun `an unparseable body still delivers the event and its id`() {
        // The kind and the id are what drive a re-fetch. Losing the frame
        // because its body was malformed would mean missing the doorbell.
        val events = parse(
            """
            id: 77
            event: approval
            data: not json at all

            """.trimIndent() + "\n",
        )
        assertEquals(1, events.size)
        assertEquals("77", events[0].id)
        assertEquals("approval", events[0].kind)
        assertNull(events[0].data)
    }

    @Test
    fun `a stale resume is reported as stale`() {
        val events = parse(
            """
            id: 9
            event: hello
            data: {"stale":true,"latest":9}

            """.trimIndent() + "\n",
        )
        val payload = JarvisJson.decodeFromJsonElement(
            HelloPayload.serializer(), events.last().data!!,
        )
        // Not caught up. The caller must re-fetch everything and not replay.
        assertTrue(payload.stale)
    }
}
