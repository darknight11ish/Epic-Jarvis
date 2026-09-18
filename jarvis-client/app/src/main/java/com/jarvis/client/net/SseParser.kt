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
    fun parse(
        reader: BufferedReader,
        /**
         * Called for a `:` comment line, which is how the server says it is
         * still there during a quiet hour.
         *
         * This used to be a bare `continue`, under a comment claiming the
         * caller watched the gap between keepalives. It could not: nothing left
         * this function when one arrived, so the watchdog upstream was timing
         * the gap between *events* and calling a perfectly healthy idle link
         * dead after 70 seconds.
         */
        onAlive: () -> Unit = {},
        /**
         * Called with a `retry:` value the moment the field is read, rather
         * than when a frame is dispatched.
         *
         * Per the spec `retry` re-times reconnection immediately and is not
         * itself a reason to dispatch anything, and a server is free to send it
         * on its own before any data. Reporting it here is what lets the
         * dispatch below insist on real data without losing the value.
         */
        onRetry: (Long) -> Unit = {},
        onEvent: (SseEvent) -> Unit,
    ) {
        var id: String? = null
        var kind = "message"
        var retry: Long? = null
        val data = StringBuilder()
        // Whether a `data:` field appeared at all, which is not the same as
        // whether it had content. Per the spec a frame dispatches if it carried
        // any data field, empty included.
        var sawData = false

        while (true) {
            val line = reader.readLine() ?: return

            if (line.isEmpty()) {
                // `sawData`, not `data.isNotEmpty()`. A minimal doorbell —
                //     id: 4471
                //     event: attention
                //     data:
                // — is exactly how this server signals "go and re-read the
                // budget", and it was dropped whole: no refresh, no `id`
                // advance, and the keepalive watchdog counted a live frame as
                // silence.
                // `sawData` alone. A lone `retry:` frame is NOT a dispatch
                // trigger in the spec, and treating it as one invented an
                // event: no data, so `kind` stayed at its default "message",
                // and `id` is sticky, so the synthetic frame carried the
                // PREVIOUS frame's id — which downstream logged as an
                // unhandled event kind and could re-persist an old resume
                // point. The value itself is not lost: [onRetry] has already
                // reported it.
                if (sawData) {
                    val parsed = runCatching {
                        JarvisJson.parseToJsonElement(data.toString())
                    }.getOrNull()
                    onEvent(SseEvent(id, kind, parsed, retry))
                }
                kind = "message"
                data.setLength(0)
                sawData = false
                retry = null
                continue
            }

            // A comment. `: keepalive` arrives every ~20s. Its absence is the
            // only sign of a connection the socket has not yet noticed is dead,
            // so it is reported rather than dropped — see [onAlive].
            if (line.startsWith(":")) { onAlive(); continue }

            val colon = line.indexOf(':')
            val field = if (colon >= 0) line.substring(0, colon) else line
            val value = if (colon >= 0) line.substring(colon + 1).removePrefix(" ") else ""

            when (field) {
                "id" -> id = value
                "event" -> kind = value
                // Reported as soon as it is read, because a `retry:` that
                // shares a frame with no data still has to reach the backoff.
                "retry" -> {
                    retry = value.toLongOrNull()
                    retry?.let(onRetry)
                }
                "data" -> {
                    if (sawData) data.append('\n')
                    sawData = true
                    data.append(value)
                }
            }
        }
    }
}
