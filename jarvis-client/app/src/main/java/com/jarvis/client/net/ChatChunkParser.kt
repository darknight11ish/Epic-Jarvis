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
 * Not ported: `routeFromPayload`/`applyRoute`, the tier/model badge the
 * desktop shows next to a reply - this app has no UI slot for it, and
 * adding one is a feature, not a protocol fix.
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
         */
        data class Text(val delta: String, val terminal: Boolean = false) : Result

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

        /** The chunk itself reported failure - `{"error": …}`. */
        data class Failed(val message: String) : Result
    }

    private val FIELD_ONLY = Regex("^(event|id|retry):", RegexOption.IGNORE_CASE)

    /**
     * Strict, deliberately NOT the shared [JarvisJson].
     *
     * `JarvisJson` sets `isLenient = true` for the typed REST models, and
     * lenient mode parses a bare unquoted word as a JSON literal. So
     * `parseToJsonElement("Done")` SUCCEEDED, returning a `JsonPrimitive`
     * whose `isString` is false - which failed the string test below, fell
     * through to the `!is JsonObject` line, and was thrown away as carrying
     * nothing. A plain-token upstream emitting `Yes.` or `Done` rendered
     * nothing at all, while `Yes, I did.` (a space makes it invalid even
     * leniently) rendered fine, so the loss looked like dropped words rather
     * than a parser bug.
     *
     * `main.js` uses `JSON.parse`, which is strict and throws on exactly
     * these, reaching its raw-token fallback. Matching it is the whole point
     * of this file, so this instance matches it.
     */
    private val StrictJson = Json { isLenient = false; ignoreUnknownKeys = true }

    fun consume(rawLine: String): Result {
        var line = rawLine.trim()
        if (line.isEmpty()) return Result.Ignored
        // SSE comment / heartbeat.
        if (line.startsWith(":")) return Result.Ignored
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

        if (chunk is JsonPrimitive && chunk.isString) {
            val text = chunk.content
            return if (text.isEmpty()) Result.Ignored else Result.Text(text)
        }
        if (chunk !is JsonObject) {
            // A bare number/bool/null chunk. `deltaFromChunk` treats any
            // non-object, non-string chunk as carrying nothing.
            return Result.Ignored
        }

        errorMessage(chunk)?.let { return Result.Failed(it) }

        val choice = (chunk["choices"] as? JsonArray)?.firstOrNull() as? JsonObject
        val delta = deltaText(chunk, choice)
        val terminal = isTerminal(chunk, choice)

        return when {
            delta.isNotEmpty() -> Result.Text(delta, terminal)
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

    private fun isTerminal(chunk: JsonObject, choice: JsonObject?): Boolean {
        val done = (chunk["done"] as? JsonPrimitive)?.booleanOrNull == true
        val finished = (chunk["finished"] as? JsonPrimitive)?.booleanOrNull == true
        val eventDone = chunk.stringField("event") == "done"
        val finishReason = (choice?.get("finish_reason") as? JsonPrimitive)?.contentOrNull
        return done || finished || eventDone || !finishReason.isNullOrEmpty()
    }
}
