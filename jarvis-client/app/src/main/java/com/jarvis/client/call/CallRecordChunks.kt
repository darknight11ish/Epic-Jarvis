package com.jarvis.client.call

import com.jarvis.client.net.CallRecordWire
import kotlinx.serialization.json.JsonObject

/**
 * Sending ONE recording's chunks, including the retry that a crash needs.
 *
 * This is the loop that used to live inside `service/CallRecordService.kt`.
 * It is here, as pure Kotlin with no Android type and no `JarvisRuntime`, so a
 * plain JVM test can drive the exact sequence that bricked a recording:
 *
 *   1. the phone posts chunk 1; the PC answers 200 and writes it;
 *   2. the app is killed BEFORE it appends "1" to `sent.txt`;
 *   3. the phone restarts, asks for the first unsent chunk - and gets 1 again;
 *   4. it posts 1 again. The PC already has it, so it answers 409 with
 *      `expected` = the number it really wants next (2, or 3 if chunk 2 had
 *      also landed before the crash);
 *   5. a loop that ignores `expected` retries 1 for ever: the audio is never
 *      sent, the plate only offers "Send it now" (the same seq), and there is
 *      nothing the owner can do. That was the audit's D3.
 *
 * So a 409 that names `expected` is READ: every chunk below that number is
 * marked sent (the PC said it has them), and the loop picks the next real gap
 * instead of retrying the same number. A 409 WITHOUT `expected` (the start
 * card is still waiting, the recording was refused, the feature is off) is a
 * different failure: nothing is marked, and the same number is retried after
 * the backoff, exactly as the frozen contract says.
 *
 * A chunk is only marked sent after the PC's `ok: true`, never on a guess, so
 * a dropped connection still loses nothing.
 */
internal object CallRecordChunks {

    /**
     * Send every chunk the PC does not have, in `seq` order.
     *
     * [post] is the one network call (`ApiResult.Ok.body` or null); [pause] is
     * the backoff, injected so a test runs instantly. True means nothing is
     * left unsent; false means the PC could not be reached (or refused) and
     * the audio stays on this phone, exactly where it is.
     */
    suspend fun send(
        session: CallRecordStore.Session,
        attempts: Int,
        post: suspend (seq: Int, pcm: ByteArray) -> JsonObject?,
        pause: suspend (tries: Int) -> Unit = {},
    ): Boolean {
        val tries = attempts.coerceAtLeast(1)
        while (true) {
            val chunk = session.nextUnsent() ?: return true
            var attempt = 0
            var sent = false
            var recovered = false
            while (!sent && attempt < tries) {
                val body = post(chunk.seq, chunk.read())
                if (body != null && CallRecordWire.ok(body)) {
                    sent = true
                    break
                }
                // A 409 that names `expected`: the PC already holds every seq
                // below it, so record that and re-pick from what is really
                // unsent. (No progress - no number to add - and the same seq
                // is simply retried, which is right for every other refusal.)
                val expected = CallRecordWire.expected(body)
                if (expected != null && session.markSentBelow(expected) > 0) {
                    recovered = true
                    break
                }
                attempt++
                if (attempt < tries) pause(attempt)
            }
            if (!sent) {
                if (recovered) continue
                return false
            }
            session.markSent(chunk.seq)
        }
    }
}
