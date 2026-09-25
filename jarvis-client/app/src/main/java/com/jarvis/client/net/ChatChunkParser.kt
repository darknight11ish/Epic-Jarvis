package com.jarvis.client.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Turns one line of `/api/chat`'s response body into something to show, or a
 * reason to stop.
 *
 * `docs/API-DISAGREEMENTS.md` §4: despite `JARVIS-API.md` calling this route
 * "not SSE", the server copies the upstream `Content-Type` verbatim, and an
 * upstream that streams SSE produces `data:`-framed chunks on this route
 * too. Before this existed, [ChatSession] displayed whatever bytes arrived
 * as literal chat text - a `data: {"choices":[{"delta":{"content":"hi"}}]}`
 * line would have shown up in the transcript exactly like that, as if it
 * were the reply.
 *
 * Ported from `jarvis-desktop/src/main.js`'s `consumeLine`/`deltaFromChunk`/
 * `isTerminal` - the same fallback chain, in the same order, not a
 * paraphrase - because that shape was earned against the real backend over
 * several rounds (see that file's own comments on `images`/`note_target`,
 * fields that were invented and never read), not guessed from this side.
 * Not ported: `routeFromPayload`, the desktop's guess at the lane from each
 * chunk's `model` name - a guess that labelled every answer "Local". Where an
 * answer was made is read from the `X-Jarvis-Route` header instead
 * ([whereFromRouteHeader]), and Home says so under an answer from a cloud model.
 *
 * Checked against what the desktop really sends by `ChatStreamContractTest`,
 * whose cases are written by running the backend's producer.
 *
 * A pure function of one line, so it can be driven by a string in a test
 * the same way [SseParser] is - it does not read or write [ChatSession]'s
 * state.
 */
object ChatChunkParser {

    sealed interface Result {
        /**
         * Text to append to the reply so far.
         *
         * @param terminal Set when this same chunk ALSO signals the end of
         *   the stream - a chunk can carry a final word and `finish_reason`
         *   together. The caller appends the text and then stops, in that
         *   order; that is why this is a flag on [Text] and not a separate
         *   case.
         * @param cutShort That end was the length limit
         *   (`finish_reason: "length"`): the answer is not whole.
         */
        data class Text(
            val delta: String,
            val terminal: Boolean = false,
            val cutShort: Boolean = false,
        ) : Result

        /**
         * `: jarvis-status <word>` - an SSE comment the desktop sends
         * (`backend/chat-stream.patch`) to say what the turn is waiting on:
         * "approval" while an approval card is up, "working" while a tool
         * runs, "thinking" otherwise. Any other SSE reader skips it; this one
         * lets the chat say "Waiting for your approval…" instead of "…".
         */
        data class Status(val word: String) : Result

        /**
         * The stream ended at the length limit with no text of its own - the
         * shape Ollama sends: a finish chunk with an empty delta and
         * `finish_reason: "length"`. Stop, like [Terminal], and say the
         * answer was cut short.
         */
        data object CutShort : Result

        /** A blank line, an SSE comment, or a field (`event:`/`id:`/`retry:`)
         *  this route never carries anything worth rendering in. */
        data object Ignored : Result

        /**
         * The stream is over and said so - `[DONE]`, or a chunk carrying
         * `done`/`finished`/`finish_reason` with no text of its own.
         *
         * Stop reading and cancel the call rather than wait for the socket
         * to close on its own: `main.js`'s own history records a version
         * that only acted on the socket closing, and a reply that ended
         * with its own `data: [DONE]` - which every reply does, the server
         * proxies OpenAI-style - left the UI stuck "streaming" until the
         * Stop button was pressed by hand.
         */
        data object Terminal : Result

        /**
         * The chunk itself reported failure - `{"error": …}`. [code] is the
         * PC's short name for one of its own failures (`error.code`, e.g.
         * "model_missing" - jarvis_agent.ERROR_CODES), which PlainErrors
         * turns into the shared plain words; null when there is none.
         */
        data class Failed(val message: String, val code: String? = null) : Result
    }

    private val FIELD_ONLY = Regex("^(event|id|retry):", RegexOption.IGNORE_CASE)

    private val STATUS = Regex("^:\\s*jarvis-status\\s+(\\w+)")

    /**
     * Strict, deliberately NOT the shared [JarvisJson], which sets
     * `isLenient = true` for the typed REST models. It rejects what
     * `JSON.parse` rejects and this app's own lenient instance does not:
     * unquoted object keys, single quotes, a trailing comma.
     *
     * It does NOT rescue a bare word, and a previous version of this comment
     * claimed it did. `parseToJsonElement` reads an unquoted token through
     * `consumeStringLenient` whatever `isLenient` is set to, so
     * `parseToJsonElement("Done")` succeeds either way and returns a
     * `JsonPrimitive` whose `isString` is false. That is handled below,
     * where the value is, rather than here.
     */
    private val StrictJson = Json { isLenient = false; ignoreUnknownKeys = true }

    /**
     * The JSON literals a bare token could legitimately be.
     *
     * Anything else that parses as a non-string primitive is a plain word the
     * parser accepted too readily, and belongs in the reply.
     */
    private val JSON_LITERALS = setOf("true", "false", "null")

    fun consume(rawLine: String): Result {
        var line = rawLine.trim()
        if (line.isEmpty()) return Result.Ignored
        // SSE comment / heartbeat - or the one comment that says what the
        // turn is waiting on.
        if (line.startsWith(":")) {
            val word = STATUS.find(line)?.groupValues?.get(1)
            return if (word != null) Result.Status(word) else Result.Ignored
        }
        // SSE fields other than `data:` carry nothing this route renders.
        if (FIELD_ONLY.containsMatchIn(line)) return Result.Ignored

        if (line.startsWith("data:", ignoreCase = true)) {
            line = line.removePrefix(line.substring(0, 5)).trim()
        }
        if (line.isEmpty()) return Result.Ignored
        if (line == "[DONE]") return Result.Terminal

        val chunk = runCatching { StrictJson.parseToJsonElement(line) }.getOrNull()
            ?: // Not JSON - a raw token, the shape a plain (non-SSE) text
            // stream produces. Same fallback `consumeLine` uses.
            return Result.Text(line)

        if (chunk is JsonPrimitive) {
            val text = chunk.content
            if (chunk.isString) {
                return if (text.isEmpty()) Result.Ignored else Result.Text(text)
            }
            // A bare token the parser accepted as a JSON literal when
            // `JSON.parse` would have thrown.
            //
            // This is where the text loss actually lived, and it survived one
            // attempt to fix it upstream of here. `parseToJsonElement` reads
            // an unquoted token through `consumeStringLenient` regardless of
            // the `isLenient` setting, so `Done` and `Yes` PARSE - as
            // primitives whose `isString` is false, which then fell straight
            // into the "carries nothing" branch below. A model whose whole
            // reply was one plain word rendered nothing at all, while
            // `Yes, I did.` rendered fine, because the space leaves trailing
            // input and makes the parse fail for real. The loss looked like
            // dropped words rather than a parser bug.
            //
            // So the test is on the VALUE. Only the three literals and a
            // number are things `JSON.parse` would also have produced; every
            // other bare token is prose, and gets the same raw-token
            // treatment an unparseable line does.
            return when {
                text in JSON_LITERALS -> Result.Ignored
                text.toDoubleOrNull() != null -> Result.Ignored
                text.isEmpty() -> Result.Ignored
                else -> Result.Text(text)
            }
        }
        if (chunk !is JsonObject) {
            // A top-level array. `deltaFromChunk` treats any non-object,
            // non-string chunk as carrying nothing.
            return Result.Ignored
        }

        errorMessage(chunk)?.let {
            val code = ((chunk["error"] as? JsonObject)?.get("code") as? JsonPrimitive)
                ?.takeIf { c -> c.isString }?.contentOrNull
            return Result.Failed(it, code)
        }

        val choice = (chunk["choices"] as? JsonArray)?.firstOrNull() as? JsonObject
        val delta = deltaText(chunk, choice)
        val terminal = isTerminal(chunk, choice)
        val cutShort = (choice?.get("finish_reason") as? JsonPrimitive)?.contentOrNull == "length"

        return when {
            delta.isNotEmpty() -> Result.Text(delta, terminal, cutShort)
            cutShort -> Result.CutShort
            terminal -> Result.Terminal
            else -> Result.Ignored
        }
    }

    /**
     * Said plainly when the chunk carries one: the fallback below is what
     * `Failed` shows when the server reports an error with nothing readable
     * attached. It is worse than the server's own words and better than
     * silence, which is what used to happen.
     */
    private const val UNNAMED_ERROR = "The desktop reported an error without saying what."

    /**
     * `chunk.error` in the source, and now the falsy cases that comment
     * claimed were handled and were not.
     *
     * The bug this fixes: an error with no readable message - `{"error": {}}`,
     * or the shape a proxy emits, `{"error": {"type": "overloaded", "code":
     * 503}}` - returned null here. Null means "not an error", so the chunk
     * fell through to [deltaText] (empty) and [isTerminal] (false) and came
     * back [Result.Ignored]. The stream then sat there until the socket closed
     * and `send` returned an empty reply with no error set: a question that
     * visibly did nothing. An error object is an error whether or not it
     * bothered to explain itself, so its PRESENCE is now what decides, and the
     * message is only what gets shown.
     *
     * The falsy guard is also real now. The old comment said `false` and `0`
     * were read as "no error"; `contentOrNull` renders them as the strings
     * "false" and "0", both non-blank, so `{"error": false}` was reported as a
     * failure whose message was the word "false". Those two are now checked
     * before anything is rendered.
     */
    private fun errorMessage(chunk: JsonObject): String? {
        val error = chunk["error"] ?: return null
        return when (error) {
            is JsonPrimitive -> {
                // JsonNull is a JsonPrimitive whose content is the literal
                // "null", so it has to be caught by this and not by the `?:`
                // above, which only sees an absent key.
                val text = error.contentOrNull ?: return null
                if (!error.isString && (text == "false" || text.toDoubleOrNull() == 0.0)) {
                    return null
                }
                // `""` is falsy in the source too, so a blank string here is
                // "no error" rather than an unnamed one. An error OBJECT is
                // different: `{}` is truthy in JS, and it is what a proxy
                // emits when it has a status and no prose.
                text.takeIf { it.isNotBlank() } ?: return null
            }
            is JsonObject -> {
                val message = (error["message"] as? JsonPrimitive)?.contentOrNull
                    ?: (error["detail"] as? JsonPrimitive)?.contentOrNull
                    ?: (error["type"] as? JsonPrimitive)?.contentOrNull
                message?.takeIf { it.isNotBlank() } ?: UNNAMED_ERROR
            }
            // An array, or anything else. Truthy in the source, so an error.
            else -> UNNAMED_ERROR
        }
    }

    private fun JsonObject.stringField(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull

    private fun deltaText(chunk: JsonObject, choice: JsonObject?): String {
        val fromChoice = choice?.let {
            (it["delta"] as? JsonObject)?.stringField("content")
                ?: (it["message"] as? JsonObject)?.stringField("content")
                ?: it.stringField("text")
        }
        val topDelta = chunk["delta"]
        val fromDelta = when {
            topDelta is JsonPrimitive && topDelta.isString -> topDelta.content
            topDelta is JsonObject -> topDelta.stringField("content")
            else -> null
        }
        return fromChoice
            ?: (chunk["message"] as? JsonObject)?.stringField("content")
            ?: chunk.stringField("response")
            ?: fromDelta
            ?: chunk.stringField("token")
            ?: chunk.stringField("content")
            ?: chunk.stringField("text")
            ?: ""
    }

    /**
     * Where the answer was made, from the `X-Jarvis-Route` response header:
     * "local" (this user's PC) or "cloud", or null when there is no header
     * to read. `where` is the desktop's own word for it
     * (`backend/chat-stream.patch`); an older desktop without it is read by
     * its `gate` - "escalate" is the only gate that picks a cloud lane.
     */
    fun whereFromRouteHeader(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val obj = runCatching { StrictJson.parseToJsonElement(header.trim()) as? JsonObject }
            .getOrNull() ?: return null
        val where = obj.stringField("where")
        if (where == "local" || where == "cloud") return where
        return if (obj.stringField("gate") == "escalate") "cloud" else "local"
    }

    private fun isTerminal(chunk: JsonObject, choice: JsonObject?): Boolean {
        val done = (chunk["done"] as? JsonPrimitive)?.booleanOrNull == true
        val finished = (chunk["finished"] as? JsonPrimitive)?.booleanOrNull == true
        val eventDone = chunk.stringField("event") == "done"
        val finishReason = (choice?.get("finish_reason") as? JsonPrimitive)?.contentOrNull
        return done || finished || eventDone || !finishReason.isNullOrEmpty()
    }
}
