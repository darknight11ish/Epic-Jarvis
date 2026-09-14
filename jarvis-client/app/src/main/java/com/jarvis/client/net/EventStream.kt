package com.jarvis.client.net

import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.isActive
import okhttp3.Request
import okhttp3.Response
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
                response = api.client.newCall(req).execute()

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
                var announcedOpen = false

                body.charStream().buffered().use { reader ->
                    SseParser.parse(reader, onAlive = { trySend(Signal.Alive) }) { event ->
                        event.retryMs?.let { retryMs = it }
                        event.id?.let { id ->
                            resumeFrom = id
                            onResumePoint(id)
                        }
                        if (event.kind == "hello") {
                            val hello = event.data?.let {
                                runCatching {
                                    JarvisJson.decodeFromJsonElement(
                                        HelloPayload.serializer(), it,
                                    )
                                }.getOrNull()
                            }
                            announcedOpen = true
                            trySend(Signal.Open(hello))
                        } else if (!announcedOpen) {
                            // A server that does not lead with hello still
                            // counts as open the moment it says anything.
                            announcedOpen = true
                            trySend(Signal.Open(null))
                        }
                        trySend(Signal.Event(event))
                    }
                }

                // The body ended. The server closes the stream after about an
                // hour by design, so this is normal: reconnect immediately
                // rather than backing off, because nothing went wrong.
                trySend(Signal.Down("Stream ended", 0))
            } catch (ce: CancellationException) {
                throw ce
            } catch (t: Throwable) {
                attempt += 1
                Log.w(TAG, "event stream failed", t)
                trySend(Signal.Down(t.message ?: "Connection lost", attempt))
                delay(backoff(attempt, retryMs))
            } finally {
                runCatching { response?.close() }
            }
        }

        awaitClose { }
    }

    private fun backoff(attempt: Int, retryMs: Long): Long =
        min(retryMs * (1L shl min(attempt - 1, 5).coerceAtLeast(0)), MAX_BACKOFF_MS)

    private companion object {
        const val TAG = "JarvisSSE"
        const val DEFAULT_RETRY_MS = 3_000L
        const val MAX_BACKOFF_MS = 30_000L
        const val RETRY_NO_HOST_MS = 5_000L
    }
}
