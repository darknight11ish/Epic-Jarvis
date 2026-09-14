package com.jarvis.client.net

import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import okhttp3.Call

/**
 * One turn of conversation.
 *
 * `POST /api/chat` streams its reply as a **chunked HTTP body**, not SSE - the
 * doc calls this out twice because the shape invites the wrong guess. So there
 * are no `data:` prefixes to strip and no frames to assemble: bytes arrive and
 * are appended.
 *
 * Interruption is the cancellation of the HTTP call itself. There is no
 * "stop" endpoint, and inventing one client-side by ignoring the rest of the
 * stream would leave the desktop generating into nothing.
 */
class ChatSession(private val api: JarvisApi) {

    private val _reply = MutableStateFlow("")

    /** The reply so far. Grows as chunks land. */
    val reply: StateFlow<String> = _reply.asStateFlow()

    private val _streaming = MutableStateFlow(false)
    val streaming: StateFlow<Boolean> = _streaming.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

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
     */
    suspend fun send(message: String): String? {
        cancel()
        _reply.value = ""
        _error.value = null

        val c = api.chatCall(message)
        if (c == null) {
            _error.value = "No desktop address set"
            return null
        }
        call = c
        _streaming.value = true

        var mine: String? = null
        withContext(Dispatchers.IO) {
            try {
                c.execute().use { resp ->
                    if (!resp.isSuccessful) {
                        _error.value = when (resp.code) {
                            401, 403 -> "The desktop refused that token."
                            404 -> "This server has no chat endpoint."
                            else -> "The desktop answered ${resp.code}."
                        }
                        return@use
                    }
                    val source = resp.body?.source() ?: return@use
                    val buf = okio.Buffer()
                    while (!source.exhausted()) {
                        val n = source.read(buf, CHUNK)
                        if (n <= 0) break
                        // Appended as it arrives rather than accumulated and
                        // shown at the end - the whole reason the body is
                        // chunked is so the reply appears as it is written.
                        _reply.value += buf.readUtf8()
                    }
                    // Captured before anything else can replace the shared
                    // flow, so the caller gets its own answer rather than
                    // whatever is in there when it happens to look.
                    mine = _reply.value
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
                    _error.value = t.message ?: "The reply stopped unexpectedly."
                }
            } finally {
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
        const val CHUNK = 8L * 1024L
    }
}
