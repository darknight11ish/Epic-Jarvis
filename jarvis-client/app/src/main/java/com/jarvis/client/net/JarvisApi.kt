package com.jarvis.client.net

import android.util.Log
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
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
        get("/api/pending", ListSerializer(PendingItem.serializer()), unwrap = "items")

    suspend fun attention(): ApiResult<Attention> =
        get("/api/attention", Attention.serializer())

    suspend fun digest(): ApiResult<List<DigestItem>> =
        get("/api/digest", ListSerializer(DigestItem.serializer()), unwrap = "items")

    suspend fun undo(): ApiResult<List<UndoEntry>> =
        get("/api/undo", ListSerializer(UndoEntry.serializer()), unwrap = "items")

    suspend fun jobs(): ApiResult<List<JobRecord>> =
        get("/api/jobs", ListSerializer(JobRecord.serializer()), unwrap = "items")

    suspend fun holds(): ApiResult<List<HoldRecord>> =
        get("/api/holds", ListSerializer(HoldRecord.serializer()), unwrap = "items")

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
            runCatching { shortCall.newCall(req).execute() }
                .fold(
                    onSuccess = { resp ->
                        resp.use {
                            when {
                                it.isSuccessful -> ApiResult.Ok(Unit)
                                // Routine whenever the desktop and the phone are
                                // both open, so it is a named outcome rather than
                                // a generic failure the UI would render as red.
                                it.code == 409 -> ApiResult.Failed(ApiError.AlreadyHandled)
                                else -> ApiResult.Failed(errorFor(it))
                            }
                        }
                    },
                    onFailure = { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) },
                )
        }

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
        unwrap: String? = null,
    ): ApiResult<T> = withContext(Dispatchers.IO) {
        val target = url(path) ?: return@withContext ApiResult.Failed(
            ApiError.Unreachable("No desktop address set"),
        )
        val req = Request.Builder().url(target).get().authed().build()
        runCatching { shortCall.newCall(req).execute() }
            .fold(
                onSuccess = { resp ->
                    resp.use {
                        if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                        val text = it.body?.string().orEmpty()
                        parse(text, serializer, unwrap)
                    }
                },
                onFailure = { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) },
            )
    }

    /**
     * Accepts either a bare array or an object carrying it under [unwrap].
     * The doc shows `/api/pending` both ways in different places, and a client
     * that guesses wrong reports "no approvals" — the most dangerous possible
     * way to be wrong about this particular endpoint.
     */
    private fun <T> parse(text: String, serializer: KSerializer<T>, unwrap: String?): ApiResult<T> {
        val direct = runCatching { JarvisJson.decodeFromString(serializer, text) }
        if (direct.isSuccess) return ApiResult.Ok(direct.getOrThrow())
        if (unwrap != null) {
            val nested = runCatching {
                val obj = JarvisJson.parseToJsonElement(text)
                val inner = (obj as? kotlinx.serialization.json.JsonObject)?.get(unwrap)
                    ?: error("no '$unwrap' key")
                JarvisJson.decodeFromJsonElement(serializer, inner)
            }
            if (nested.isSuccess) return ApiResult.Ok(nested.getOrThrow())
        }
        Log.w(TAG, "unparseable body: ${text.take(200)}")
        return ApiResult.Failed(
            ApiError.Malformed(direct.exceptionOrNull()?.message ?: "unrecognised response"),
        )
    }

    private fun errorFor(resp: Response): ApiError = when (resp.code) {
        401, 403 -> ApiError.BadToken
        404 -> ApiError.NotFound
        else -> ApiError.Server(resp.code, resp.body?.string().orEmpty().take(200))
    }

    companion object {
        private const val TAG = "JarvisApi"

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
