package com.jarvis.client.net

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

        val chunk = runCatching { JarvisJson.parseToJsonElement(line) }.getOrNull()
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
     * `chunk.error` in the source. Not full JS truthiness - `false`, `0` and
     * `""` are still read as "no error" here, which covers every real error
     * shape (a string, or `{"message": …}`) without chasing every falsy
     * edge case JS has and Kotlin does not.
     */
    private fun errorMessage(chunk: JsonObject): String? {
        val error = chunk["error"] ?: return null
        val message = when (error) {
            is JsonPrimitive -> error.contentOrNull
            is JsonObject -> (error["message"] as? JsonPrimitive)?.contentOrNull
            else -> null
        }
        return message?.takeIf { it.isNotBlank() }
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
