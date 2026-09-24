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
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.Call
import okhttp3.Response

/**
 * One turn of conversation at a time, sent with the conversation so far
 * ([history]; see [ChatHistory]).
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

    private val _waiting = MutableStateFlow<String?>(null)

    /**
     * What the answer on its way is waiting on, in words, or null.
     *
     * "Waiting for your approval…" while an approval card is up on the
     * desktop - the desktop says so in the stream (`: jarvis-status approval`,
     * `backend/chat-stream.patch`). Before that, a tool turn showed "…" for up
     * to three minutes and then "timeout". Cleared as soon as words arrive.
     */
    val waiting: StateFlow<String?> = _waiting.asStateFlow()

    private val _answerNote = MutableStateFlow<String?>(null)

    /**
     * One line to show under the answer, or null: that it was cut short at
     * the length limit (it used to look finished), and/or that a cloud model
     * wrote it rather than this user's PC, or that the PC's second graphics
     * card did (both read from `X-Jarvis-Route`).
     */
    val answerNote: StateFlow<String?> = _answerNote.asStateFlow()

    private val _history = MutableStateFlow<List<ChatHistory.Exchange>>(emptyList())

    /**
     * The conversation so far - finished questions and their answers, oldest
     * first, already trimmed to what the desktop's model has room for. Sent
     * ahead of every new question, so a follow-up is understood; see
     * [ChatHistory] for the limits and why.
     *
     * Memory only, like [question]: never written anywhere, gone with the
     * process or on [newConversation]. A question that failed, was stopped,
     * or came back empty is not added - replaying half an answer as if it
     * were the whole one would mislead the model on every later turn.
     */
    val history: StateFlow<List<ChatHistory.Exchange>> = _history.asStateFlow()

    /**
     * Which conversation a [send] belongs to. [newConversation] moves it on,
     * so an answer that finishes AFTER the owner started afresh is not
     * written into the new, empty conversation.
     */
    @Volatile private var conversation = 0

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
     *
     * [onRoute], if given, gets this call's `X-Jarvis-Route` header (or null
     * when the PC sent none) once, as the headers arrive and before the
     * first word - call-local, like [onDelta].
     *
     * [picture], when given, is a `data:image/jpeg;base64,` URI ([ChatPicture])
     * sent inside this one question. It is not kept: only the words join
     * [history], so it is never sent again with a later question.
     */
    suspend fun send(
        message: String,
        onDelta: ((String) -> Unit)? = null,
        picture: String? = null,
        onRoute: ((String?) -> Unit)? = null,
    ): String? {
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
        _waiting.value = null
        _answerNote.value = null

        // Captured before the request goes, and the same list that is sent:
        // what this question was asked in the light of.
        val earlier = _history.value
        val askedIn = conversation
        val c = api.chatCall(message, earlier, picture)
        if (c == null) {
            _error.value = "No desktop address set"
            return null
        }
        call = c
        _streaming.value = true

        var mine: String? = null
        // An SSE-framed answer (`data:` lines) says when it has finished -
        // `[DONE]` or a `finish_reason`. One that stops without saying so was
        // cut off: shown as it is, returned as it is, but not added to the
        // conversation, where it would be replayed as a whole answer on every
        // later turn. The HUD page draws the same line. A plain-text upstream
        // has no end marker, so for it the end of the body is the end.
        var cutShort = false
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
                        // A 404 WITH a sentence is the desktop passing on
                        // what the model server said - a model that is not
                        // installed, say - not a missing route. It used to
                        // read "This server has no chat endpoint." either way.
                        val generic = when (resp.code) {
                            401, 403 -> "The desktop refused that token."
                            404 -> if (detail == null) "This server has no chat endpoint." else ""
                            else -> if (detail == null) "The desktop answered ${resp.code}." else ""
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
                                // The desktop's own sentence says what is wrong
                                // and what to do; a status number in front of it
                                // adds nothing the owner can act on.
                                else -> detail
                            },
                        )
                        return@use
                    }
                    // The answer's id, from the headers, which arrive before
                    // the first word. Same identity guard as every other
                    // write to the shared flows: a cancelled call unwinding
                    // late must not put its id beside the new answer.
                    val routeHeader = resp.header(Feedback.ROUTE_HEADER)
                    val tid = Feedback.turnIdFromRouteHeader(routeHeader)
                    if (call === c) _turnId.value = tid
                    // The whole header, to THIS call's own caller - the voice
                    // loop decides from it whether a private answer may be
                    // read aloud (voice/PrivateAloud.kt). Before any word, and
                    // unguarded like `onDelta`: it belongs to this call alone.
                    onRoute?.invoke(routeHeader)
                    // Where it was made. Only a cloud answer gets a line: an
                    // answer from this user's own PC is the normal case.
                    val cloud = ChatChunkParser.whereFromRouteHeader(routeHeader) == "cloud"
                    // Or the second graphics card (`second_card` in the same
                    // header, second-card.patch): still this PC, but not the
                    // everyday model, so it gets a line of its own.
                    val secondCard = SecondCard.routeFromHeader(routeHeader)
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
                    var framed = false
                    var ended = false
                    var cutShortAtLimit = false

                    /** @return true when the caller should stop reading. */
                    fun handle(line: String): Boolean {
                        if (line.trimStart().startsWith("data:")) framed = true
                        return when (val result = ChatChunkParser.consume(line)) {
                            is ChatChunkParser.Result.Text -> {
                                if (call === c) _waiting.value = null
                                if (result.cutShort) cutShortAtLimit = true
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
                                if (result.terminal) ended = true
                                result.terminal
                            }
                            ChatChunkParser.Result.Terminal -> {
                                ended = true
                                true
                            }
                            ChatChunkParser.Result.CutShort -> {
                                ended = true
                                cutShortAtLimit = true
                                true
                            }
                            is ChatChunkParser.Result.Status -> {
                                // Only before the first words: after them, the
                                // words are the progress.
                                if (call === c && acc.isEmpty()) {
                                    _waiting.value = WAITING[result.word]
                                }
                                false
                            }
                            is ChatChunkParser.Result.Failed -> {
                                failWith(result.message)
                                failed = true
                                true
                            }
                            ChatChunkParser.Result.Ignored -> false
                        }
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
                        cutShort = framed && !ended
                    }
                    if (call === c) {
                        _waiting.value = null
                        _answerNote.value = listOfNotNull(
                            if (cutShortAtLimit && !failed && acc.isNotBlank()) {
                                "Cut short: it reached the length limit. Ask \"go on\" for the rest."
                            } else {
                                null
                            },
                            if (cloud && !failed) "Answered by a cloud model, not on your PC." else null,
                            if (secondCard != null && !cloud && !failed) SecondCard.routeNote(secondCard) else null,
                        ).joinToString(" ").ifEmpty { null }
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
                    _waiting.value = null
                    call = null
                }
            }
        }
        // Only a finished, non-empty answer joins the conversation, and only
        // the conversation it was asked in. `update` rather than building
        // on `earlier`: a call that finished in the meantime has already
        // added its own pair, and this one goes after it.
        val answer = mine
        if (answer != null && answer.isNotBlank() && !cutShort && conversation == askedIn) {
            _history.update { ChatHistory.commit(it, message, answer) }
        }
        return mine
    }

    /** Interrupts generation. Safe to call when nothing is in flight. */
    fun cancel() {
        call?.cancel()
        call = null
        _streaming.value = false
    }

    /**
     * Starts afresh: stops any answer still arriving, forgets the
     * conversation, and clears the question and answer on screen. The next
     * question goes to the desktop on its own, as the very first one did.
     *
     * Only the phone's copy is forgotten. Nothing in this repository shows
     * the desktop keeping a copy of its own between requests; what it has
     * LEARNED (memory, and cards waiting for review) is a different thing,
     * kept on the desktop, and this does not touch it.
     */
    fun newConversation() {
        conversation++
        cancel()
        _history.value = emptyList()
        _reply.value = ""
        _question.value = null
        _turnId.value = null
        _error.value = null
        _waiting.value = null
        _answerNote.value = null
    }

    private companion object {
        const val TAG = "JarvisChat"

        /** What each `: jarvis-status` word means on screen. */
        val WAITING = mapOf(
            "approval" to "Waiting for your approval…",
            "working" to "Working…",
        )

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
