package com.jarvis.client.net

import java.io.BufferedReader

/**
 * The SSE frame parser, pulled out of [EventStream] so it can be tested against
 * a string rather than a socket.
 *
 * It is thirty lines because the format is thirty lines' worth: `field: value`
 * until a blank line, then dispatch. The parts worth being careful about are
 * the ones a library would hide — comment lines (which carry the keepalive),
 * multi-line `data`, and an `id` that must survive to the caller even on a
 * frame whose body does not parse.
 */
object SseParser {

    /**
     * Reads until the stream ends, calling [onEvent] per frame.
     *
     * `id` is deliberately sticky across frames, per the SSE spec: a frame with
     * no `id:` keeps the last one, so a resume point is never lost by a server
     * that only stamps some of its events.
     */
    fun parse(reader: BufferedReader, onEvent: (SseEvent) -> Unit) {
        var id: String? = null
        var kind = "message"
        var retry: Long? = null
        val data = StringBuilder()

        while (true) {
            val line = reader.readLine() ?: return

            if (line.isEmpty()) {
                if (data.isNotEmpty() || retry != null) {
                    val parsed = runCatching {
                        JarvisJson.parseToJsonElement(data.toString())
                    }.getOrNull()
                    onEvent(SseEvent(id, kind, parsed, retry))
                }
                kind = "message"
                data.setLength(0)
                retry = null
                continue
            }

            // A comment. `: keepalive` arrives every ~20s and is skipped — but
            // its absence is the only sign of a connection the socket has not
            // yet noticed is dead, which is why the caller watches the gap.
            if (line.startsWith(":")) continue

            val colon = line.indexOf(':')
            val field = if (colon >= 0) line.substring(0, colon) else line
            val value = if (colon >= 0) line.substring(colon + 1).removePrefix(" ") else ""

            when (field) {
                "id" -> id = value
                "event" -> kind = value
                "retry" -> retry = value.toLongOrNull()
                "data" -> {
                    if (data.isNotEmpty()) data.append('\n')
                    data.append(value)
                }
            }
        }
    }
}
