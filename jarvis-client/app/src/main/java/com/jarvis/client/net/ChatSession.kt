package com.jarvis.client.net

import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.Call
import okhttp3.Response

/**
 * One turn of conversation.
 *
 * `POST /api/chat` streams its reply as a **chunked HTTP body** whose framing
 * depends on the upstream model in use: the server copies the upstream
 * `Content-Type` verbatim, so a plain-text upstream produces raw tokens but an
 * OpenAI-style upstream produces `data:`-framed SSE lines on this same route
 * (`docs/API-DISAGREEMENTS.md` §4). [ChatChunkParser] handles both shapes;
 * bytes are decoded to characters, split into lines, and each line is routed
 * through it rather than appended to the reply as-is.
 *
 * Interruption is the cancellation of the HTTP call itself. There is no
 * "stop" endpoint, and inventing one client-side by ignoring the rest of the
 * stream would leave the desktop generating into nothing. The same cancel
 * also runs proactively once a line reports the stream is over, rather than
 * waiting for the socket to close on its own - see [ChatChunkParser.Result.Terminal].
 */
class ChatSession(private val api: JarvisApi) {

    private val _reply = MutableStateFlow("")

    /** The reply so far. Grows as chunks land. */
    val reply: StateFlow<String> = _reply.asStateFlow()

    private val _streaming = MutableStateFlow(false)
    val streaming: StateFlow<Boolean> = _streaming.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _question = MutableStateFlow<String?>(null)

    /**
     * The owner's last question, as sent - null until the first one.
     *
     * Home shows it as a "You" line above [reply]: the composer is cleared on
     * send, so an answer used to sit on screen with nothing to say what it
     * answered. Held in memory only, in this one field, and never written
     * anywhere - a question can be about email, files or memory, and rule 1
     * keeps those on this phone and the desktop and nowhere else. Gone when
     * the process is.
     */
    val question: StateFlow<String?> = _question.asStateFlow()

    private val _turnId = MutableStateFlow<String?>(null)

    /**
     * The id the desktop gave the answer now on screen, or null.
     *
     * Read from the answer's `X-Jarvis-Route` response header, where
     * `feedback.patch` puts it as `turn_id`, so the owner can mark THIS answer
     * right or wrong. Null until the headers of the current answer arrive,
     * and null for good on a backend that does not send one - Home then shows
     * no mark buttons at all. Memory only, like [question]: an id and nothing
     * else, and never written anywhere.
     */
    val turnId: StateFlow<String?> = _turnId.asStateFlow()

    @Volatile private var call: Call? = null

    /**
     * Sends a turn and returns the reply **this** call produced, or null if it
     * did not finish.
     *
     * The return value exists because the voice loop used to read
     * `chat.reply.value` after `send` came back, and there is only one shared
     * `_reply`. A typed message sent while a spoken one was still streaming
     * cancels the voice call — so the read picked up the *typed* question's
     * half-streamed answer, and Jarvis spoke it aloud as the answer to
     * something else entirely.
     *
     * [onDelta], if given, is called with the reply text accumulated SO FAR
     * every time this call publishes to [reply] - same throttling, same
     * accumulator, just handed to a caller-local callback instead of only the
     * shared flow. This is deliberately NOT "subscribe to `reply`": a second
     * subscriber reading the shared flow is exactly the hazard the paragraph
     * above describes, reopened one layer up. A callback scoped to THIS one
     * call cannot observe a different call's text, whatever else is running
     * concurrently - the voice loop's own sentence-streaming TTS uses this to
     * start speaking before the answer has finished arriving, without ever
     * touching [reply] itself.
     */
    suspend fun send(message: String, onDelta: ((String) -> Unit)? = null): String? {
        cancel()
        _reply.value = ""
        _error.value = null
        // Set as the old reply is cleared, before anything can fail below:
        // a question that got no answer is still what the owner asked, and
        // the screen should not go on showing the one before it.
        _question.value = message
        // The previous answer's id goes with the previous answer: a mark
        // tapped now must never land on the answer that is being replaced.
        _turnId.value = null

        val c = api.chatCall(message)
        if (c == null) {
            _error.value = "No desktop address set"
            return null
        }
        call = c
        _streaming.value = true

        var mine: String? = null
        withContext(Dispatchers.IO) {
            // Cancelling this coroutine has to cancel the HTTP call, and only a
            // coroutine that is NOT parked on the socket can do it.
            //
            // The read loop below is blocking okio/IO with no suspension point,
            // so cancellation alone reached nothing: leaving the screen
            // cancelled the coroutine while the socket kept streaming and
            // `_reply` kept being written for a screen that no longer existed,
            // with the desktop generating into it. This is the same failure
            // [EventStream] fixes with the same shape (see the note on `live`
            // there): `Call.cancel()` is the one OkHttp operation documented as
            // safe from any thread, and it fails an in-flight read at once,
            // where closing the body promises nothing to a read already blocked
            // on it. A child coroutine is cancelled the instant its parent is,
            // whatever the parent's thread is doing, so this one is always free
            // to run that cancel. It is cancelled again in the `finally` below
            // on the normal path, where cancelling a finished call is a no-op.
            val closer = launch {
                try {
                    awaitCancellation()
                } finally {
                    runCatching { c.cancel() }
                }
            }
            // The scope is captured rather than used implicitly, so the
            // `ensureActive()` inside the read loop cannot bind to anything but
            // this coroutine.
            val io = this
            // Every write to the SHARED flows goes through one of these two.
            //
            // The `finally` below already refuses to clear `_streaming` and
            // `call` unless this call is still the current one, and gives the
            // reason: `send` starts by cancelling the previous call, and the
            // loser unwinds through this same block afterwards. The flows the
            // loser writes on its way out needed the identical guard and did
            // not have it. `send` #2 sets `_error.value = null` and
            // `_reply.value = ""`; call #1, failing for a real reason at that
            // same moment, then wrote its error over the clean slate and its
            // last half-line of text over the empty reply - so the new question
            // appeared on screen already carrying the old one's error, or the
            // old one's tail.
            fun failWith(message: String) {
                if (call === c) _error.value = message
            }
            try {
                c.execute().use { resp ->
                    if (!resp.isSuccessful) {
                        // The server's own words first, when it has any.
                        //
                        // "The desktop answered 503." is true and useless. The
                        // backend returns 503 with a body that says WHICH thing
                        // is not up and usually what to do about it - the model
                        // is still loading, Ollama is not running - and that
                        // sentence was being thrown away in favour of a number,
                        // leaving the owner to go and read a log to learn
                        // something the reply already contained.
                        val detail = serverDetail(resp)
                        val generic = when (resp.code) {
                            401, 403 -> "The desktop refused that token."
                            404 -> "This server has no chat endpoint."
                            else -> "The desktop answered ${resp.code}."
                        }
                        // The token is in the REQUEST, never in the response, so
                        // there is nothing of the token to leak here. 401/403
                        // still lead with our own sentence: a server saying
                        // "invalid bearer" adds nothing to "refused that token"
                        // and reads worse.
                        failWith(
                            when {
                                detail == null -> generic
                                resp.code == 401 || resp.code == 403 -> "$generic ($detail)"
                                else -> "$generic $detail"
                            },
                        )
                        return@use
                    }
                    // The answer's id, from the headers, which arrive before
                    // the first word. Same identity guard as every other
                    // write to the shared flows: a cancelled call unwinding
                    // late must not put its id beside the new answer.
                    val tid = Feedback.turnIdFromRouteHeader(resp.header(Feedback.ROUTE_HEADER))
                    if (call === c) _turnId.value = tid
                    // Decoded as CHARACTERS, not as whatever bytes happened
                    // to be buffered.
                    //
                    // The old loop read bytes into an okio.Buffer and called
                    // `readUtf8()` on whatever was in it. A UTF-8 character
                    // split across two TCP segments - and every emoji, curly
                    // quote and accented letter is multi-byte - was decoded
                    // half at a time: the first half became U+FFFD and the
                    // continuation bytes were eaten, so the owner saw "?" in
                    // place of the character at every chunk boundary.
                    //
                    // `charStream()` is an InputStreamReader, which keeps the
                    // trailing incomplete byte sequence and finishes decoding
                    // it when the rest of it arrives. It still streams: its
                    // `read` returns as soon as it has at least one character
                    // rather than waiting for the array to fill.
                    val reader = resp.body?.charStream() ?: return@use
                    val chunk = CharArray(CHUNK)
                    // Accumulated in a StringBuilder rather than with
                    // `_reply.value += ...`. That `+=` copied the entire reply
                    // so far for every token that arrived - quadratic in the
                    // length of the answer - and woke a Compose recomposition
                    // on each one. A long reply spent most of its time copying
                    // itself.
                    val acc = StringBuilder()
                    // A partial line carried over between reads - `chunk` is
                    // filled at socket granularity, not line granularity, so a
                    // line almost never ends exactly at its boundary.
                    val lineBuf = StringBuilder()
                    var shownAt = 0L

                    fun publish(force: Boolean) {
                        val now = SystemClock.elapsedRealtime()
                        if (!force && now - shownAt < PUBLISH_MS) return
                        shownAt = now
                        val text = acc.toString()
                        // Same identity guard as `failWith`, for the same
                        // reason. `onDelta` is NOT guarded: it belongs to this
                        // call alone - that is the whole point of it existing
                        // rather than a second subscriber to `reply` - so it
                        // still gets every delta it was promised even once a
                        // newer call owns the shared flow.
                        if (call === c) _reply.value = text
                        onDelta?.invoke(text)
                    }

                    var failed = false

                    /** @return true when the caller should stop reading. */
                    fun handle(line: String): Boolean =
                        when (val result = ChatChunkParser.consume(line)) {
                            is ChatChunkParser.Result.Text -> {
                                acc.append(result.delta)
                                // Published as it arrives - the whole reason
                                // the body is chunked is so the reply appears
                                // as it is written - but at most every
                                // PUBLISH_MS. Token-by-token that is still
                                // ~20 updates a second, which reads as smooth
                                // typing, while a burst of tiny lines no
                                // longer costs one full string copy and one
                                // recomposition each.
                                publish(force = false)
                                result.terminal
                            }
                            ChatChunkParser.Result.Terminal -> true
                            is ChatChunkParser.Result.Failed -> {
                                failWith(result.message)
                                failed = true
                                true
                            }
                            ChatChunkParser.Result.Ignored -> false
                        }

                    readLoop@ while (true) {
                        // Blocking reads never suspend, so nothing here would
                        // otherwise notice that the coroutine is gone. `closer`
                        // above makes the read itself fail on cancellation;
                        // this catches the case where cancellation lands
                        // between two reads, before another byte is written
                        // into a reply nobody is waiting for.
                        io.ensureActive()
                        val n = reader.read(chunk)
                        if (n < 0) {
                            // A final line with no trailing newline is still a
                            // line, and dropping it was not a tail-end nicety:
                            // `main.js`'s own loop ends with
                            // `if (pending.trim()) consumeLine(pending)` and
                            // this port left it out. Against the plain-token
                            // (non-SSE) upstream this file's own header
                            // describes - one that streams words with no
                            // newlines at all - EVERY token landed in
                            // `lineBuf`, `acc` stayed empty, and `send`
                            // returned "" with no error: a blank reply on
                            // screen and a voice loop that said nothing.
                            if (lineBuf.isNotEmpty()) handle(lineBuf.toString())
                            break
                        }
                        if (n == 0) continue
                        var start = 0
                        for (i in 0 until n) {
                            if (chunk[i] != '\n') continue
                            lineBuf.append(chunk, start, i - start)
                            start = i + 1
                            val line = lineBuf.toString()
                            lineBuf.setLength(0)
                            if (handle(line)) break@readLoop
                        }
                        if (start < n) lineBuf.append(chunk, start, n - start)
                    }
                    // The last line is almost always inside the throttle
                    // window, so without this the tail of every reply would be
                    // missing from the screen until the next message.
                    publish(force = true)
                    // Captured before anything else can replace the shared
                    // flow, so the caller gets its own answer rather than
                    // whatever is in there when it happens to look. Not set on
                    // [ChatChunkParser.Result.Failed]: that is an in-band error
                    // from the chunk itself, the same kind of failure the
                    // 401/403/404 branch above reports by leaving `mine` null.
                    if (!failed) {
                        mine = acc.toString()
                    }
                }
            } catch (ce: CancellationException) {
                throw ce
            } catch (t: Throwable) {
                // A cancelled call lands here too. That is the interrupt
                // working, not a failure, so it is not reported as one.
                if (c.isCanceled()) {
                    Log.d(TAG, "chat interrupted by the user")
                } else {
                    Log.w(TAG, "chat failed", t)
                    failWith(t.message ?: "The reply stopped unexpectedly.")
                }
            } finally {
                // Nothing left to cancel on; the read is over either way.
                closer.cancel()
                // Only when this call is still the current one.
                //
                // `send` begins by cancelling the previous call, and the loser
                // then unwinds into THIS block. Without the identity check it
                // cleared the WINNER's handle and streaming flag on its way
                // out: the new reply streamed in with the composer showing
                // "Send" rather than "Stop", the voice button re-enabled
                // mid-generation, and `cancel()` had a null handle — so the
                // generation could no longer be interrupted at all.
                if (call === c) {
                    _streaming.value = false
                    call = null
                }
            }
        }
        return mine
    }

    /** Interrupts generation. Safe to call when nothing is in flight. */
    fun cancel() {
        call?.cancel()
        call = null
        _streaming.value = false
    }

    private companion object {
        const val TAG = "JarvisChat"

        /**
         * How much of a failed response body to look at, in bytes.
         *
         * A backend error is a sentence. Anything larger than this is a stack
         * trace or an HTML error page from something in between, neither of
         * which belongs on a phone screen - and reading it in full would mean
         * buffering an unbounded body to render one line of it.
         */
        const val ERROR_BODY_MAX = 4L * 1024

        /** Longest server sentence shown, in characters. */
        const val ERROR_DETAIL_MAX = 300

        /**
         * The one useful sentence out of a failed response, or null.
         *
         * `peekBody` rather than `body.string()`: it copies out of the buffer
         * and leaves the body itself untouched, so this cannot interfere with
         * anything downstream that still expects to read it.
         *
         * FastAPI's own error shape is `{"detail": "..."}`, so that is tried
         * first; `error` and `message` cover the rest of what this backend and
         * its proxies emit. A body that is not JSON is used as-is, which is
         * what a plain-text 503 from a reverse proxy looks like. HTML is
         * dropped outright - a whole error PAGE has no sentence in it worth
         * pulling out by hand.
         */
        fun serverDetail(resp: Response): String? {
            val raw = runCatching { resp.peekBody(ERROR_BODY_MAX).string() }
                .getOrNull()?.trim().orEmpty()
            if (raw.isEmpty() || raw.startsWith("<")) return null

            val fromJson = runCatching {
                val obj = Json.parseToJsonElement(raw) as? JsonObject
                obj?.let {
                    (it["detail"] as? JsonPrimitive)?.contentOrNull
                        ?: (it["message"] as? JsonPrimitive)?.contentOrNull
                        ?: ((it["error"] as? JsonObject)?.get("message") as? JsonPrimitive)
                            ?.contentOrNull
                        ?: (it["error"] as? JsonPrimitive)?.contentOrNull
                }
            }.getOrNull()

            val text = (fromJson ?: raw).replace(Regex("\\s+"), " ").trim()
            if (text.isEmpty()) return null
            return if (text.length <= ERROR_DETAIL_MAX) {
                text
            } else {
                text.take(ERROR_DETAIL_MAX - 1).trimEnd() + "…"
            }
        }

        /** Characters per read now, not bytes - see the decode note in [send]. */
        const val CHUNK = 8 * 1024

        /**
         * Slowest the reply is allowed to visibly grow, in milliseconds. Small
         * enough that generation still looks like typing; large enough that a
         * fast local model cannot make the UI publish a fresh copy of the whole
         * reply for every token.
         */
        const val PUBLISH_MS = 50L
    }
}
