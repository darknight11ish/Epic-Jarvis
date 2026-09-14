package com.jarvis.client.net

import android.util.Log
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit

/** What went wrong, in terms the UI can say out loud rather than a stack trace. */
sealed interface ApiError {
    /** No host, or nothing listening there. */
    data class Unreachable(val detail: String) : ApiError

    /** 401/403. The token is wrong or missing — the one failure worth naming precisely. */
    data object BadToken : ApiError

    /** 409 on approve/deny: the item was decided elsewhere. Routine, not an error. */
    data object AlreadyHandled : ApiError

    /** The endpoint is not on this server. Usually means a capability is off. */
    data object NotFound : ApiError

    /**
     * The route answered, and said the subsystem behind it is not running —
     * gating switched off, no job runner, no ledger. Distinct from an empty
     * list on purpose: "there is no approval queue here" and "the approval
     * queue is empty" are different sentences and only one of them is
     * reassuring.
     */
    data object NotAvailable : ApiError

    data class Server(val code: Int, val body: String) : ApiError
    data class Malformed(val detail: String) : ApiError
}

sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>
    data class Failed(val error: ApiError) : ApiResult<Nothing>
}

inline fun <T> ApiResult<T>.onOk(block: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Ok) block(value)
    return this
}

/**
 * Turns a wire shape into the shape the app wants, leaving failures untouched.
 * The two are not always the same class — see [AttentionResponse].
 */
inline fun <T, R> ApiResult<T>.map(block: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Ok -> ApiResult.Ok(block(value))
    is ApiResult.Failed -> this
}

/**
 * Finds the list in the body, without requiring a particular key.
 *
 * This was wrong, and wrong in the way that matters most. The doc shows
 * `/api/pending` as a bare array in one place and wrapped in another, so the
 * client accepted both and guessed `items` for the wrapper. The server does
 * neither: reading `jarvis_hud.py`, `/api/pending` answers
 * `{"available": true, "pending": [...], "history": [...]}`, and four of the
 * five list routes use a different key each — `pending`, `digest`, `shelf`,
 * `jobs`. Only `/api/initiative`, which this client does not read as a list,
 * uses `items`.
 *
 * So approvals would have arrived and the phone would have said nothing was
 * waiting. That is the single worst way to be wrong about this endpoint and it
 * would have looked exactly like a quiet backend.
 *
 * The fix is not a better guess. A bare array still works; otherwise the
 * preferred keys are tried in order and, failing those, the object's single
 * array-valued property is used — **only when there is exactly one**.
 *
 * That last clause is load-bearing and was missing. `/api/pending` answers
 * `{"available", "pending", "history"}`, and a server that omits an empty
 * `pending` leaves `history` as the first array the scan meets. It decodes
 * cleanly, because `PendingItem` needs only an `id`, so the phone would show
 * items *already decided* as waiting for a decision, and approving one would
 * post a verdict on a request closed days ago. That is worse than the bug this
 * function was written to fix: the original produced an empty list, which is
 * visibly wrong; this produced a full and plausible one.
 *
 * Top-level and internal so a test can reach it. The reason this shipped is
 * that the guess lived inside a class needing a Context and a socket, so
 * nothing cheap could ever have contradicted it.
 */
/**
 * Keys whose array is, by name, a record of things already dealt with.
 *
 * The positional fallback exists so a route that renames its key degrades to
 * working rather than to empty. These names say the opposite: they are not the
 * route's list under a new name, they are a different list that happens to be
 * the only one present. Guessing here is worse than failing, because every list
 * model in this file defaults its fields and so decodes whatever it is handed.
 */
private val ALREADY_HANDLED_KEYS =
    setOf("history", "archive", "archived", "done", "completed", "handled", "past")

internal fun <T> parseListBody(
    text: String,
    serializer: KSerializer<T>,
    unwrap: List<String>,
): ApiResult<T> {
    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()

    // Checked BEFORE the direct decode, not after.
    //
    // `available: false` means the subsystem behind the route is not running —
    // gating switched off, no job runner. That is not an empty list and must
    // not read as one: "there is no approval queue here" and "the approval
    // queue is empty" are different sentences, and only one is reassuring.
    //
    // It used to be checked only if the direct decode had already failed. Every
    // non-list model defaults every field, so the direct decode never fails for
    // them and the check was dead code: `/api/attention` answering
    // `{"available": false}` decoded to an all-zero budget and the UI read
    // "0 of 0 spoken interruptions left today" — the one thing ApiModels says
    // it must never say by accident.
    if ((obj?.get("available") as? JsonPrimitive)?.booleanOrNull == false) {
        return ApiResult.Failed(ApiError.NotAvailable)
    }

    val direct = runCatching { JarvisJson.decodeFromString(serializer, text) }
    if (direct.isSuccess) return ApiResult.Ok(direct.getOrThrow())

    if (obj != null) {
        for (key in unwrap) {
            val named = obj[key] ?: continue
            val nested = runCatching { JarvisJson.decodeFromJsonElement(serializer, named) }
            if (nested.isSuccess) return ApiResult.Ok(nested.getOrThrow())
        }
        // The positional fallback, and only when it cannot be ambiguous. With
        // two arrays present there is no principled way to choose, and choosing
        // wrong here means showing the wrong list as if it were the right one.
        //
        // "Unambiguous" is not the same as "the only array". A body carrying
        // just `history` has exactly one array and is still the wrong answer:
        // `PendingItem` needs only an id, so a list of already-decided requests
        // decodes cleanly and is indistinguishable downstream from a live
        // queue. The owner would be shown items settled days ago as if they
        // were waiting, and approving one would post a verdict on a closed
        // request. Counting the arrays caught the two-array case and let this
        // one straight through.
        //
        // A route whose list genuinely is called `history` names it in its own
        // `unwrap` list, and the loop above takes it before this is reached.
        val arrays = obj.entries.filter { it.value is JsonArray }
        val only = arrays.singleOrNull()
        if (only != null && only.key.lowercase() !in ALREADY_HANDLED_KEYS) {
            val nested = runCatching { JarvisJson.decodeFromJsonElement(serializer, only.value) }
            if (nested.isSuccess) return ApiResult.Ok(nested.getOrThrow())
        }
    }
    return ApiResult.Failed(
        ApiError.Malformed(direct.exceptionOrNull()?.message ?: "unrecognised response"),
    )
}

/**
 * The REST half of the contract. The SSE half is [EventStream].
 *
 * One OkHttp client for both, so the connection pool and the tailnet route are
 * shared. Read timeout is deliberately generous on the streaming paths and
 * normal elsewhere.
 */
class JarvisApi(
    private val settings: ClientSettings,
    private val tokens: TokenStore,
) {

    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        // No global read timeout: /api/events is held open for up to an hour and
        // /api/chat streams for as long as the reply takes. The per-call
        // timeouts below cover the ordinary endpoints.
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .retryOnConnectionFailure(true)
        .build()

    /**
     * The client `/api/events` is read on. Everything else about it is [client].
     *
     * A stream with no read timeout cannot fail. That is fine while the peer is
     * alive and fatal when it is not: a phone that loses its radio mid-stream
     * leaves TCP half-open, no FIN ever arrives, and the blocking read parks for
     * ever. The watchdog upstream notices the silence and latches the link
     * stale, which refuses every approval — but nothing tears the socket down,
     * so no reconnect is attempted, and the only thing that clears staleness is
     * a frame that can no longer arrive. The link was condemned until the app
     * was reopened, and the phone reported "Not connected" while sitting on a
     * socket it believed was fine.
     *
     * 90s is four missed keepalives at the server's ~20s cadence, so a desktop
     * with nothing to say is never mistaken for a dead one, while a genuinely
     * dead socket now fails its read, reconnects through the normal backoff,
     * and clears itself. Deliberately not applied to [client]: `/api/chat`
     * streams for as long as a reply takes and has no keepalive to pace it.
     */
    val streamClient: OkHttpClient = client.newBuilder()
        .readTimeout(90, TimeUnit.SECONDS)
        .build()

    private val shortCall: OkHttpClient = client.newBuilder()
        .readTimeout(15, TimeUnit.SECONDS)
        .callTimeout(20, TimeUnit.SECONDS)
        .build()

    fun baseUrl(): String? = settings.baseUrl()

    /**
     * Every request carries the token. `X-Jarvis-Client` rides along too: the
     * server's origin check requires it on a request with no `Origin`, and a
     * native client sends none. It is *not* authentication — §1 says so
     * plainly, and it proves nothing coming from an app with no CORS — but
     * without it the server answers 403 before it ever looks at the token.
     */
    fun Request.Builder.authed(): Request.Builder = apply {
        header(TOKEN_HEADER, tokens.token())
        header(CLIENT_HEADER, CLIENT_VALUE)
        header("Accept", "application/json")
    }

    private fun url(path: String): String? = baseUrl()?.let { it + path }

    // ------------------------------------------------------------ reads ----

    suspend fun version(): ApiResult<VersionInfo> =
        get("/api/version", VersionInfo.serializer())

    suspend fun status(): ApiResult<StatusInfo> =
        get("/api/status", StatusInfo.serializer())

    suspend fun pending(): ApiResult<List<PendingItem>> =
        get("/api/pending", ListSerializer(PendingItem.serializer()), PENDING_KEYS)

    suspend fun attention(): ApiResult<Attention> =
        get("/api/attention", AttentionResponse.serializer()).map { it.flatten() }

    suspend fun digest(): ApiResult<List<DigestItem>> =
        get("/api/digest", ListSerializer(DigestItem.serializer()), DIGEST_KEYS)

    suspend fun undo(): ApiResult<List<UndoEntry>> =
        get("/api/undo", ListSerializer(UndoEntry.serializer()), UNDO_KEYS)

    suspend fun jobs(): ApiResult<List<JobRecord>> =
        get("/api/jobs", ListSerializer(JobRecord.serializer()), JOB_KEYS)

    // ----------------------------------------------------------- writes ----

    suspend fun approve(id: String): ApiResult<Unit> = decide("/api/approve", id)

    suspend fun deny(id: String): ApiResult<Unit> = decide("/api/deny", id)

    /**
     * The one state-changing thing a phone may drive, because it only ever
     * moves toward a state the owner already had.
     */
    suspend fun revert(id: String): ApiResult<Unit> = postId("/api/undo/revert", id)

    private suspend fun decide(path: String, id: String): ApiResult<Unit> = postId(path, id)

    suspend fun cancelJob(id: String): ApiResult<Unit> = postId("/api/jobs/cancel", id)

    /**
     * Stops a message inside its send window. 409 once released — there is no
     * unsend after that, and a client that reported success anyway would be
     * telling exactly the lie this feature exists to avoid.
     *
     * **Currently unreachable, and left here deliberately.** The contract has
     * this route but nothing that *lists* holds, so a phone has no way to learn
     * a handle. An earlier draft of this file invented `GET /api/holds` to fill
     * the gap — which is the exact mistake that produced `jarvis-android`'s
     * protocol, so it was removed rather than kept behind a 404. When something
     * serves handles (a `hold` event, or a field on a pending item), this is
     * ready.
     */
    suspend fun cancelHold(handle: String): ApiResult<Unit> =
        postJson("/api/holds/cancel", """{"handle":${quote(handle)}}""")

    /** Mutes spoken interruptions until tomorrow. There is no "mute forever". */
    suspend fun mute(): ApiResult<Unit> = postJson("/api/attention/mute", "{}")

    suspend fun unmute(): ApiResult<Unit> = postJson("/api/attention/unmute", "{}")

    /**
     * Marks the brief read. Marking read is **not** approving anything in it —
     * the digest lists approvals and cannot decide them.
     */
    suspend fun digestSeen(ids: List<String>? = null): ApiResult<Unit> {
        val body = if (ids == null) "{}" else {
            """{"ids":[${ids.joinToString(",") { quote(it) }}]}"""
        }
        return postJson("/api/digest/seen", body)
    }

    private suspend fun postId(path: String, id: String): ApiResult<Unit> =
        postJson(path, """{"id":${quote(id)}}""")

    private suspend fun postJson(path: String, json: String): ApiResult<Unit> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                ApiError.Unreachable("No desktop address set"),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use {
                    when {
                        it.isSuccessful -> ApiResult.Ok(Unit)
                        // Routine whenever the desktop and the phone are
                        // both open, so it is a named outcome rather than
                        // a generic failure the UI would render as red.
                        it.code == 409 -> ApiResult.Failed(ApiError.AlreadyHandled)
                        else -> ApiResult.Failed(errorFor(it))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
        }

    /**
     * Reads a route whose *shape* the contract does not document.
     *
     * §4 lists `/api/compute`, `/api/memory/pending`, `/api/ledger`,
     * `/api/skills` and `/api/initiative` with one line of description each and
     * no field names — "GPU/VRAM plan", "Audit-chain status: entry count, last
     * verified point, anchors". Writing a data class against that would mean
     * inventing the keys, which is exactly the mistake that produced the other
     * client's protocol: it fails silently, as an empty panel that looks built.
     *
     * So these come back as raw JSON and the screen renders whatever keys are
     * actually there. It cannot be wrong about a field name because it does not
     * know any. When the contract grows the shapes, these become real models.
     */
    suspend fun probe(path: String): ApiResult<JsonObject> = withContext(Dispatchers.IO) {
        val target = url(path) ?: return@withContext ApiResult.Failed(
            ApiError.Unreachable("No desktop address set"),
        )
        val req = Request.Builder().url(target).get().authed().build()
        runCatching {
            shortCall.newCall(req).execute().use {
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val text = it.body?.string().orEmpty()
                runCatching {
                    when (val el = JarvisJson.parseToJsonElement(text)) {
                        is JsonObject -> ApiResult.Ok(el)
                        // A bare array is still worth showing; wrap it so
                        // one renderer handles both.
                        else -> ApiResult.Ok(JsonObject(mapOf("items" to el)))
                    }
                }.getOrElse { ApiResult.Failed(ApiError.Malformed(it.message ?: "bad json")) }
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
    }

    // ------------------------------------------------------------ voice ----

    /**
     * Call before offering a microphone button. §4.1.
     *
     * Returns the *refusing* defaults on any failure, so a backend that cannot
     * answer leaves the button hidden rather than showing one that posts audio
     * into a 404.
     */
    suspend fun voiceStatus(): ApiResult<VoiceStatus> =
        get("/api/voice/status", VoiceStatus.serializer())

    /**
     * One complete utterance in, one verdict out.
     *
     * The only route on this server whose body is not JSON. The audio is
     * already 16 kHz 16-bit mono PCM in a WAV container — resampled on this
     * device, because the server refuses anything else rather than carrying a
     * resampler in the most exposed code it has: these are bytes from the
     * network arriving *before* the gate.
     *
     * Uses the long-timeout client. Verification and transcription happen
     * before the response, and a few seconds of audio through a CPU Whisper is
     * not a short call.
     */
    suspend fun utterance(
        wav: ByteArray,
        source: String = SOURCE_PUSH_TO_TALK,
    ): ApiResult<Heard> = withContext(Dispatchers.IO) {
        val target = url("/api/voice/utterance?source=$source") ?: return@withContext ApiResult.Failed(
            ApiError.Unreachable("No desktop address set"),
        )
        val body = wav.toRequestBody("audio/wav".toMediaType())
        val req = Request.Builder().url(target).post(body).authed().build()
        runCatching {
            client.newCall(req).execute().use {
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val text = it.body?.string().orEmpty()
                runCatching { JarvisJson.decodeFromString(Heard.serializer(), text) }
                    .fold(
                        { h -> ApiResult.Ok(h) },
                        { e -> ApiResult.Failed(ApiError.Malformed(e.message ?: "bad verdict")) },
                    )
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
    }

    /**
     * Text to speech on the desktop, or null when there is no engine there.
     *
     * A **503 is a legitimate answer**, not a failure: speaking text the client
     * already holds reveals nothing and skips no check, so this is the half of
     * the voice path that is allowed to be missing. Null means "use your own
     * voice", and the caller does.
     */
    suspend fun say(text: String): ApiResult<ByteArray?> = withContext(Dispatchers.IO) {
        val target = url("/api/voice/say") ?: return@withContext ApiResult.Failed(
            ApiError.Unreachable("No desktop address set"),
        )
        val body = """{"text":${quote(text)}}""".toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url(target).post(body).authed()
            .header("Accept", "audio/wav")
            .build()
        runCatching {
            client.newCall(req).execute().use {
                when {
                    it.code == 503 -> ApiResult.Ok(null)
                    it.isSuccessful -> ApiResult.Ok(it.body?.bytes())
                    else -> ApiResult.Failed(errorFor(it))
                }
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
    }

    /**
     * Asks the desktop to turn the wake word on or off.
     *
     * Gated as a config change server-side, and **approval means approved, not
     * already live** — the value lives in the TOML. So a success here does not
     * mean the wake word is on; re-read [voiceStatus] for that.
     */
    suspend fun setWakeWord(enabled: Boolean): ApiResult<Unit> =
        postJson("/api/voice/wake", """{"enabled":$enabled}""")

    // ------------------------------------------------------------- chat ----

    /**
     * Streams the reply as a chunked HTTP body — **not** SSE, whatever the
     * shape suggests. The returned [Call] is the interrupt: cancel it and
     * generation stops.
     */
    fun chatCall(message: String): Call? {
        val target = url("/api/chat") ?: return null
        val body = """{"message":${quote(message)}}"""
            .toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url(target).post(body).authed().build()
        return client.newCall(req)
    }

    // ----------------------------------------------------------- plumbing --

    private suspend fun <T> get(
        path: String,
        serializer: KSerializer<T>,
        unwrap: List<String> = emptyList(),
    ): ApiResult<T> = withContext(Dispatchers.IO) {
        val target = url(path) ?: return@withContext ApiResult.Failed(
            ApiError.Unreachable("No desktop address set"),
        )
        val req = Request.Builder().url(target).get().authed().build()
        runCatching {
            shortCall.newCall(req).execute().use {
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val text = it.body?.string().orEmpty()
                parse(text, serializer, unwrap)
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
    }

    private fun <T> parse(
        text: String,
        serializer: KSerializer<T>,
        unwrap: List<String>,
    ): ApiResult<T> = parseListBody(text, serializer, unwrap)

    private fun errorFor(resp: Response): ApiError = when (resp.code) {
        401, 403 -> ApiError.BadToken
        404 -> ApiError.NotFound
        else -> ApiError.Server(resp.code, resp.body?.string().orEmpty().take(200))
    }

    companion object {
        private const val TAG = "JarvisApi"

        /**
         * The keys each list route actually uses, read from `jarvis_hud.py`
         * rather than from the prose. Tried in order; if none is present the
         * parser falls back to the first array in the object, so a route that
         * renames its key degrades to working rather than to empty.
         */
        val PENDING_KEYS = listOf("pending", "items")
        val DIGEST_KEYS = listOf("digest", "items", "entries")
        val UNDO_KEYS = listOf("shelf", "undo", "items")
        val JOB_KEYS = listOf("jobs", "items")

        const val SOURCE_PUSH_TO_TALK = "push_to_talk"
        const val SOURCE_WAKE_WORD = "wake_word"

        const val TOKEN_HEADER = "X-Jarvis-Token"
        const val CLIENT_HEADER = "X-Jarvis-Client"

        /**
         * The server compares this against the literal string "hud" for a
         * request with no Origin, and does it *before* it checks the token — so
         * a token-only native client is answered 403 by a check that, for us,
         * proves nothing. Sent to get past it, never relied on.
         */
        const val CLIENT_VALUE = "hud"

        /** JSON-quotes and escapes, so a message body cannot break out of its field. */
        fun quote(s: String): String = JarvisJson.encodeToString(String.serializer(), s)
    }
}

private fun Throwable.readableMessage(): String = when (this) {
    is IOException -> message ?: this::class.java.simpleName
    else -> message ?: this::class.java.simpleName
}
