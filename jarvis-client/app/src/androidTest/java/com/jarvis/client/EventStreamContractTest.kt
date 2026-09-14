package com.jarvis.client

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.EventStream
import com.jarvis.client.net.JarvisApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Collections
import java.util.concurrent.TimeUnit

/**
 * The event stream against a server that speaks SSE.
 *
 * This is the part of the protocol with no coverage at all and the most places
 * to be quietly wrong. Two of the defects found by review this week lived
 * here: keepalives were parsed and then dropped, so an idle desktop looked
 * dead after 70 seconds and every approval was refused; and the socket could
 * go half-open with nothing left to close it, which condemned the link until
 * the app was reopened. Both were found by reading. Neither had a test that
 * could have failed.
 *
 * What is asserted here is mostly what the CLIENT sends and how it behaves
 * across a reconnect, because that is the half a server cannot correct for.
 */
@RunWith(AndroidJUnit4::class)
class EventStreamContractTest {

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()

    private lateinit var server: MockWebServer
    private lateinit var settings: ClientSettings
    private lateinit var tokens: TokenStore
    private lateinit var stream: EventStream

    /** Set before connecting to make /api/events hold its body open. */
    @Volatile private var holdBodyOpen = false

    @Before
    fun start() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                if (request.path?.startsWith("/api/events") != true) {
                    return MockResponse().setResponseCode(404).setBody("{}")
                }
                val resp = MockResponse()
                    .setResponseCode(200)
                    .setHeader("Content-Type", "text/event-stream")
                    .setBody(FRAMES)
                // Headers now, body much later: the socket stays open and the
                // client parks in its blocking read, which is the only state
                // in which "does cancelling close it" means anything.
                if (holdBodyOpen) resp.setBodyDelay(60, TimeUnit.SECONDS)
                return resp
            }
        }
        server.start()

        settings = ClientSettings(context)
        settings.setHost("${server.hostName}:${server.port}")
        settings.clearResumePoint()
        tokens = TokenStore(context)
        tokens.setToken("jarvis_pair_contract_test")
        stream = EventStream(JarvisApi(settings, tokens))
    }

    @After
    fun stop() {
        tokens.clear()
        settings.setHost("")
        settings.clearResumePoint()
        server.shutdown()
    }

    /**
     * Open, keepalive and event all reach the collector.
     *
     * The keepalive is the one that had regressed: `SseParser` recognised the
     * comment frame and then `continue`d without telling anyone, under a
     * comment claiming the caller watched the gap. The caller could not — so
     * the watchdog was timing between EVENTS, and a quiet desktop was declared
     * stale while it was answering perfectly.
     */
    @Test
    fun openKeepaliveAndEventAllReachTheCollector() = runBlocking {
        val seen = Collections.synchronizedList(mutableListOf<EventStream.Signal>())
        val resumed = Collections.synchronizedList(mutableListOf<String>())

        val collector = CoroutineScope(Dispatchers.IO).launch {
            stream.connect(lastEventId = null, onResumePoint = { resumed += it })
                .collect { seen += it }
        }
        try {
            val got = waitFor {
                seen.any { it is EventStream.Signal.Open } &&
                    seen.any { it === EventStream.Signal.Alive } &&
                    seen.any { it is EventStream.Signal.Event }
            }
            assertTrue("never saw open + keepalive + event; got $seen", got)

            val event = seen.filterIsInstance<EventStream.Signal.Event>().first()
            assertEquals("activity", event.event.kind)
            assertTrue("the resume point never advanced", resumed.contains("e1"))
        } finally {
            collector.cancel()
        }
    }

    /**
     * §3: a reconnect resumes rather than restarting.
     *
     * Without the header the server replays from the top of its ring buffer or
     * not at all, and an approval that arrived during the gap is either shown
     * twice or never. The id has to survive the socket dying, which is why it
     * is asserted on the SECOND request rather than on a field.
     */
    @Test
    fun aReconnectAsksToResumeFromTheLastEventItAccepted() = runBlocking {
        val collector = CoroutineScope(Dispatchers.IO).launch {
            stream.connect(lastEventId = null, onResumePoint = {}).collect { }
        }
        try {
            val first = server.takeRequest(20, TimeUnit.SECONDS)
            assertNotNull("the stream never connected", first)
            assertEquals("text/event-stream", first!!.getHeader("Accept"))
            assertEquals(
                "the first connection should not claim a resume point",
                null, first.getHeader("Last-Event-ID"),
            )

            // The body ends, which the client treats as a short stream and
            // retries after its backoff floor. 25s covers that with room.
            val second = server.takeRequest(25, TimeUnit.SECONDS)
            assertNotNull("the stream never reconnected", second)
            assertEquals(
                "the reconnect did not ask to resume",
                "e1", second!!.getHeader("Last-Event-ID"),
            )
        } finally {
            collector.cancel()
        }
    }

    /**
     * Cancelling the collector must actually close the socket.
     *
     * `SseParser.parse` is a blocking readLine with no cancellation check, so
     * for a while nothing did: the close lived in an `awaitClose` placed after
     * a loop that could only end once the read had already returned. A
     * stop-then-start inside that window opened a SECOND live connection, both
     * writing the resume point.
     */
    @Test
    fun cancellingTheCollectorEndsTheConnection() = runBlocking {
        // Without this the mock body arrives at once and the read returns on
        // its own, so the test would pass whether or not cancellation closes
        // anything. Held open, the only way out is the close.
        holdBodyOpen = true
        val collector = CoroutineScope(Dispatchers.IO).launch {
            stream.connect(lastEventId = null, onResumePoint = {}).collect { }
        }
        assertNotNull("the stream never connected", server.takeRequest(20, TimeUnit.SECONDS))
        collector.cancel()

        val endedInTime = withTimeoutOrNull(15_000) {
            collector.join()
            true
        }
        assertTrue("cancelling left the stream coroutine running", endedInTime == true)

        // And having stopped, it must not come back: a torn-down stream that
        // keeps reconnecting is the double-connection bug in slow motion.
        val afterCancel = server.takeRequest(8, TimeUnit.SECONDS)
        assertEquals("a cancelled stream reconnected anyway", null, afterCancel)
    }

    private suspend fun waitFor(timeoutMs: Long = 20_000, cond: () -> Boolean): Boolean =
        withTimeoutOrNull(timeoutMs) {
            while (!cond()) delay(50)
            true
        } == true

    private companion object {
        /** A keepalive, a hello, and one identified event. */
        val FRAMES = buildString {
            append(": keepalive\n\n")
            append("event: hello\n")
            append("data: {\"stale\":false}\n\n")
            append("id: e1\n")
            append("event: activity\n")
            append("data: {\"activity\":\"thinking\"}\n\n")
        }
    }
}
