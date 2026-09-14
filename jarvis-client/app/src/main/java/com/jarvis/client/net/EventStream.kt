package com.jarvis.client.net

import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.Request
import okhttp3.Response
import java.util.concurrent.atomic.AtomicReference
import kotlin.coroutines.coroutineContext
import kotlin.math.min

/**
 * The one Server-Sent Events stream, and the thing that replaces all polling.
 *
 * Hand-parsed rather than pulled from okhttp-sse. The frame format is
 * line-oriented text and the parser below is thirty lines; the library would be
 * a dependency for that, and it hides the two things this client has to get
 * exactly right — the `id:` bookkeeping that survives a process restart, and
 * the keepalive gap that means a dead connection the socket has not noticed.
 */
class EventStream(private val api: JarvisApi) {

    sealed interface Signal {
        /** The stream is open and the server has answered. */
        data class Open(val hello: HelloPayload?) : Signal

        data class Event(val event: SseEvent) : Signal

        /**
         * A `: keepalive` comment. Carries nothing and means everything: it is
         * the only proof a quiet connection is still alive, and the staleness
         * watchdog exists to count the time since the last one.
         */
        data object Alive : Signal

        /**
         * Not connected. [attempt] counts consecutive failures so the UI can
         * distinguish a blip from a desktop that is genuinely gone.
         */
        data class Down(val reason: String, val attempt: Int) : Signal
    }

    /**
     * Runs until cancelled, reconnecting with backoff. Emits [Signal.Open] on
     * every successful connect, so a caller that re-fetches state on open gets
     * it right after a reconnect as well as on first launch.
     *
     * @param lastEventId the resume point, or null to start from the live edge.
     * @param onResumePoint called with each event id as it arrives, so the
     *   caller can persist it. Called from the stream thread; keep it cheap.
     */
    fun connect(
        lastEventId: String?,
        onResumePoint: (String) -> Unit,
    ): Flow<Signal> = callbackFlow {
        var resumeFrom = lastEventId
        var attempt = 0
        var retryMs = DEFAULT_RETRY_MS

        // Held so a cancellation can shut the socket. `SseParser.parse` is a
        // blocking readLine loop with no cancellation check, so cancelling this
        // flow did not stop it: the coroutine stayed parked on the socket until
        // the server next wrote. A stop-then-start inside that window passed
        // the `isActive` guard upstream and opened a SECOND live /api/events
        // connection, with both writing `lastEventId` — so the persisted resume
        // point could go backwards.
        //
        // The close has to come from a coroutine that is NOT the one parked on
        // the socket, and that is what was missing. `awaitClose` below sits
        // after the reconnect loop, and the loop only ends when `isActive` is
        // read at the top — which cannot happen until the blocking read returns
        // on its own. So the close that was meant to unblock the read was
        // reachable only after the read had already unblocked, and by then the
        // `finally` had cleared the handle. It was a no-op in every path.
        //
        // A child coroutine is cancelled the instant its parent is, whatever
        // the parent is doing, so this one is not parked on anything and can do
        // the close that makes the read throw.
        val live = AtomicReference<Response?>(null)
        launch(Dispatchers.IO) {
            try {
                awaitCancellation()
            } finally {
                runCatching { live.getAndSet(null)?.close() }
            }
        }

        while (coroutineContext.isActive) {
            val base = api.baseUrl()
            if (base == null) {
                trySend(Signal.Down("No desktop address set", attempt))
                delay(RETRY_NO_HOST_MS)
                continue
            }

            var response: Response? = null
            try {
                val req = with(api) {
                    Request.Builder()
                        .url(base + "/api/events")
                        .get()
                        .authed()
                        .header("Accept", "text/event-stream")
                        // Resume by header; ?since= is the documented
                        // alternative and this is the one the doc leads with.
                        .apply { resumeFrom?.let { header("Last-Event-ID", it) } }
                        .build()
                }
                response = api.streamClient.newCall(req).execute()
                live.set(response)

                if (!response.isSuccessful) {
                    val reason = when (response.code) {
                        401, 403 -> "Token refused"
                        404 -> "This server has no event stream"
                        else -> "Server said ${response.code}"
                    }
                    attempt += 1
                    trySend(Signal.Down(reason, attempt))
                    response.close()
                    delay(backoff(attempt, retryMs))
                    continue
                }

                val body = response.body ?: run {
                    attempt += 1
                    trySend(Signal.Down("Empty response", attempt))
                    response.close()
                    delay(backoff(attempt, retryMs))
                    continue
                }

                attempt = 0
                val openedAt = SystemClock.elapsedRealtime()

                // Open is announced on CONNECT, not on the first frame.
                //
                // It used to be emitted from inside the frame callback, so a
                // desktop that had nothing to say announced nothing: at 3am, on
                // an idle machine sending only keepalives, `onOpen` never ran,
                // the link stayed RECONNECTING over a healthy socket, `_stale`
                // was never cleared and every approval button was refused —
                // for as long as the desktop stayed quiet.
                trySend(Signal.Open(null))

                body.charStream().buffered().use { reader ->
                    SseParser.parse(reader, onAlive = { trySend(Signal.Alive) }) { event ->
                        // Clamped. `retry` comes straight off the wire and was
                        // used unchecked: 0 removed the backoff entirely, a
                        // negative walked `delay` backwards, and a huge value
                        // overflowed Long when shifted and came out negative —
                        // so a field meant to SLOW reconnection produced the
                        // fastest possible loop.
                        event.retryMs?.let { retryMs = it.coerceIn(MIN_RETRY_MS, MAX_BACKOFF_MS) }
                        if (event.kind == "hello") {
                            val hello = event.data?.let {
                                runCatching {
                                    JarvisJson.decodeFromJsonElement(
                                        HelloPayload.serializer(), it,
                                    )
                                }.getOrNull()
                            }
                            trySend(Signal.Open(hello))
                        }
                        // The resume point advances only for frames the
                        // collector actually accepted. `trySend` drops silently
                        // when the 64-deep buffer is full — which happens on a
                        // replay after time offline, because each event costs
                        // the collector an HTTP round trip — and advancing the
                        // id past a dropped frame made it unrecoverable on
                        // every future resume.
                        if (trySend(Signal.Event(event)).isSuccess) {
                            event.id?.let { id ->
                                resumeFrom = id
                                onResumePoint(id)
                            }
                        }
                    }
                }

                // The body ended. The server closes the stream after about an
                // hour by design, so a long-lived one is normal and reconnects
                // at once. A SHORT one is not: a proxy or a misconfigured
                // desktop answering 200 with an empty body would end the body
                // immediately, and with no backoff and `attempt` pinned at 0
                // this was an unbounded tight loop issuing hundreds of requests
                // a second from a phone, for ever, while the UI cheerfully said
                // "reconnecting".
                val lived = SystemClock.elapsedRealtime() - openedAt
                if (lived < MIN_HEALTHY_STREAM_MS) {
                    attempt += 1
                    trySend(Signal.Down("Stream ended after ${lived}ms", attempt))
                    delay(backoff(attempt, retryMs))
                } else {
                    trySend(Signal.Down("Stream ended", 0))
                }
            } catch (ce: CancellationException) {
                throw ce
            } catch (t: Throwable) {
                attempt += 1
                Log.w(TAG, "event stream failed", t)
                trySend(Signal.Down(t.message ?: "Connection lost", attempt))
                delay(backoff(attempt, retryMs))
            } finally {
                runCatching { response?.close() }
                live.set(null)
            }
        }

        awaitClose { runCatching { live.getAndSet(null)?.close() } }
    }

    /** Saturating, so a large `retry` cannot overflow into a negative delay. */
    private fun backoff(attempt: Int, retryMs: Long): Long {
        val base = retryMs.coerceIn(MIN_RETRY_MS, MAX_BACKOFF_MS)
        val shift = min(attempt - 1, 5).coerceAtLeast(0)
        val scaled = if (base > MAX_BACKOFF_MS shr shift) MAX_BACKOFF_MS else base shl shift
        return min(scaled, MAX_BACKOFF_MS)
    }

    private companion object {
        const val TAG = "JarvisSSE"
        const val DEFAULT_RETRY_MS = 3_000L
        const val MAX_BACKOFF_MS = 30_000L

        /** Floor for a server-supplied `retry`, so it cannot remove the backoff. */
        const val MIN_RETRY_MS = 500L

        /**
         * Below this, a stream that ended is treated as a failure rather than
         * the server's routine hourly recycle.
         */
        const val MIN_HEALTHY_STREAM_MS = 10_000L
        const val RETRY_NO_HOST_MS = 5_000L
    }
}
