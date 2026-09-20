package com.jarvis.client.net

import android.util.Log
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
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
        // A READ timeout, not a call timeout, and never zero again.
        //
        // Zero meant "wait for ever between bytes", and this client serves the
        // three slow POSTs — /api/chat, /api/voice/utterance, /api/voice/say.
        // A desktop that accepts the POST and then wedges (Whisper stuck, TTS
        // hung, Wi-Fi gone half-open so no FIN ever arrives) left the call
        // parked for the life of the process: an IO thread and a socket pinned,
        // and `ChatSession._streaming` stuck true, so the composer showed
        // "Stop" for ever with nothing to stop.
        //
        // It must be a read timeout because a read timeout measures SILENCE,
        // not duration. A chat reply that takes four minutes to write is
        // perfectly normal and a `callTimeout` — which bounds the whole call,
        // body included — would cut it off mid-sentence. This clock instead
        // restarts on every byte delivered, so a stream that is still producing
        // text is never killed and one that has gone quiet fails and unwinds.
        //
        // 120s is deliberately generous: a local model loading weights from
        // disk, or CPU Whisper chewing on a long utterance, can genuinely say
        // nothing for a minute before the first byte. Two full minutes of
        // silence is a wedge, not slowness.
        //
        // /api/events is NOT covered by this: [streamClient] overrides it with
        // the tighter keepalive-based 90s, and [shortCall] overrides it too.
        .readTimeout(120, TimeUnit.SECONDS)
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
     * and clears itself. This 90s is deliberately not applied to [client]:
     * `/api/chat` streams for as long as a reply takes and has no keepalive to
     * pace it, so it gets the looser 120s silence limit set above instead.
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
        header(TOKEN_HEADER, headerSafe(tokens.token()))
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

    // ----------------------------------------------------------- models ----

    /**
     * Which models the desktop has and which is running. Read only where the
     * handshake reports the `models` capability; the shape is the one the
     * desktop's own Brain pane reads, see [ModelsInfo].
     *
     * Through [probe], not a typed decode - [ModelsInfo] is deliberately a
     * plain class built by [ModelsInfo.from] from the raw object, for the
     * reason its own doc comment gives.
     */
    suspend fun models(): ApiResult<ModelsInfo> =
        when (val result = probe("/api/models")) {
            is ApiResult.Ok -> ApiResult.Ok(ModelsInfo.from(result.value))
            is ApiResult.Failed -> result
        }

    /**
     * `POST /api/models/switch {"ref": ...}` - the body the desktop's
     * `brain_model` command sends, copied rather than guessed. Tier `ask` on
     * the server, so success means "a decision card was raised".
     *
     * There is deliberately no `install` here. Downloading weights is the
     * model catalogue, which stays off the phone; a switch only ever chooses
     * between models the desktop already holds.
     */
    suspend fun switchModel(ref: String): ApiResult<Unit> =
        postJson("/api/models/switch", """{"ref":${quote(ref)}}""")

    /** `POST /api/models/rollback {}` - tier `auto`, never waits. */
    suspend fun rollbackModel(): ApiResult<Unit> = postJson("/api/models/rollback", "{}")

    // ------------------------------------------------- autonomy proposals --

    /**
     * A note sent before the first decision on a proposal -
     * `docs/AUTONOMY-PROPOSALS.md` §3b on the desktop branch. This is NOT a
     * decision and approves nothing; the expected result is a fresh set of
     * options for the same id, which arrives the normal way through the next
     * `/api/pending` read - this call does not wait for or apply it.
     *
     * **DRAFT.** `jarvis_gate.py`/`jarvis_hud.py` are not in either repo, so
     * neither this route nor its exact shape is confirmed - `POST
     * /api/pending/<id>/amend` is the design doc's own proposed name, the
     * same one the desktop's `amend_approval` Tauri command targets. A 404
     * here means this desktop build does not have the route yet, not a
     * wrong address, and [JarvisRuntime] reports it that way rather than
     * through the generic [ApiError.NotFound] wording.
     */
    suspend fun amend(id: String, note: String): ApiResult<Unit> {
        val encodedId = java.net.URLEncoder.encode(id, "UTF-8")
        return postJson("/api/pending/$encodedId/amend", """{"note":${quote(note)}}""")
    }

    /**
     * Pause, resume, stop, or add a note to whatever Jarvis is currently
     * running - `docs/AUTONOMY-PROPOSALS.md` §3d. None of the four names a
     * task id: the project's own rule (one human decision, one bounded
     * plan) means there is never more than one thing running that could
     * need one, the same reasoning the desktop's own client code gives for
     * its matching, argument-free calls.
     *
     * **DRAFT, same standing as [amend].** No route name for this is given
     * anywhere in the shared design doc - only the mechanism is specified
     * ("just another action against the running task's id, broadcast the
     * same way `approval-resolved` already is"). `/api/task/pause` and its
     * three siblings below follow this contract's own existing
     * domain/verb shape (`/api/models/switch`, `/api/attention/mute`,
     * `/api/voice/wake`) rather than inventing a new one, but are not
     * confirmed against `jarvis_hud.py` and may need renaming once they
     * are. Calling any of these against a backend that has not added them
     * fails honestly - a 404, surfaced as an error - rather than silently
     * doing nothing.
     */
    suspend fun pauseTask(): ApiResult<Unit> = postJson("/api/task/pause", "{}")

    suspend fun resumeTask(): ApiResult<Unit> = postJson("/api/task/resume", "{}")

    suspend fun stopTask(): ApiResult<Unit> = postJson("/api/task/stop", "{}")

    suspend fun injectTaskNote(note: String): ApiResult<Unit> =
        postJson("/api/task/note", """{"note":${quote(note)}}""")

    // ------------------------------------------------------- appearance ----

    /**
     * `GET /api/appearance` - the face and bindings document the owner's
     * other device may have written, per `docs/APPEARANCE-API.md`. Through
     * [probe]: `{"available": false}` when the capability is not installed
     * reads the same way every other absent capability does here, and the
     * document's own fields (`face`, `bindings`, `updated`) belong to
     * [com.jarvis.client.data.AppearanceStore], not this layer.
     */
    suspend fun getAppearance(): ApiResult<JsonObject> = probe("/api/appearance")

    /**
     * `POST /api/appearance`. `bodyJson` is
     * [com.jarvis.client.data.AppearanceStore.toSyncDocument] already
     * serialised - this layer never builds the document itself, the same
     * boundary [probe]'s callers keep. The server owns `updated` and stamps
     * it on write, so the client never sends one.
     */
    suspend fun postAppearance(bodyJson: String): ApiResult<Unit> =
        postJson("/api/appearance", bodyJson)

    // ----------------------------------------------------------- writes ----

    suspend fun approve(id: String): ApiResult<Unit> = decide("/api/approve", id)

    suspend fun deny(id: String): ApiResult<Unit> = decide("/api/deny", id)

    /**
     * The one state-changing thing a phone may drive, because it only ever
     * moves toward a state the owner already had.
     */
    suspend fun revert(id: String): ApiResult<Unit> = postId("/api/undo/revert", id)

    private suspend fun decide(path: String, id: String): ApiResult<Unit> = postId(path, id)

    /**
     * Keeps or discards ONE proposed fact from `/api/memory/pending` (the
     * same route [probe] reads that section from). One integer id, one
     * decision - the extractor fills this queue on its own and there is no
     * list form, matching the desktop's own `brain_memory_decide`: forgetting
     * is irreversible and a "keep all" would be an approve-all with another
     * name. This is the QUEUE, never the corpus - deciding a fact Jarvis
     * proposed is not the memory graph the phone is not meant to hold.
     */
    suspend fun decideMemory(id: Long, accept: Boolean): ApiResult<Unit> =
        postJson("/api/memory/decide", """{"id":$id,"accept":$accept}""")

    /**
     * "What did I believe as of this moment?" - `GET /api/memory/facts?known_at=`,
     * the exact route the desktop's 2026-09-18 feature audit named for this
     * (§3, "Memory consolidation", P3). Read-only, and still not the memory
     * graph: a fact list for one point in time, never a browsable graph -
     * that stays desktop-only by the contract's own instruction. Through
     * [probe], like every other route this contract does not give a field
     * list for.
     */
    suspend fun memoryFacts(knownAtEpochSeconds: Long): ApiResult<JsonObject> =
        probe("/api/memory/facts?known_at=$knownAtEpochSeconds")

    /**
     * Answers the daily "let Jarvis tidy its memory overnight?" card - see
     * `BrainSnapshot.memory`'s own `setup.sleep_time_offer`. This app's two
     * real actions ("enable" and "stop asking") each send exactly one of
     * [enabled]/[remind]; "not now" needs no call at all, since the card
     * already tracks "already offered today" itself
     * (`jarvis_sleep.py`'s own `_seen`), so a plain dismiss still does not
     * return until tomorrow. The server reports a write that failed to
     * persist as a non-2xx status, same as every other write here, so no
     * response body needs reading.
     */
    suspend fun setSleepTime(enabled: Boolean? = null, remind: Boolean? = null): ApiResult<Unit> {
        val fields = buildList {
            enabled?.let { add(""""enabled":$it""") }
            remind?.let { add(""""remind":$it""") }
        }
        return postJson("/api/memory/sleep_time", "{${fields.joinToString(",")}}")
    }

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
     * Uses the general [client], whose read timeout is the generous one rather
     * than [shortCall]'s 15s. Verification and transcription happen before the
     * response, and a few seconds of audio through a CPU Whisper is not a short
     * call. (This comment used to say "long-timeout client" while that client
     * had NO timeout at all — a stuck Whisper hung the call for ever.)
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
    suspend fun say(text: String): ApiResult<SaidAloud> = withContext(Dispatchers.IO) {
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
                    it.code == 503 -> {
                        // The permission, read rather than assumed. Absent is
                        // false: this decides whether the owner's reply gets
                        // handed to whatever TTS engine the handset defaults
                        // to, and on a stock phone that engine is Google's.
                        val obj = runCatching {
                            JarvisJson.parseToJsonElement(it.body?.string().orEmpty()) as? JsonObject
                        }.getOrNull()
                        ApiResult.Ok(
                            SaidAloud.NoEngine(
                                fallbackOk = (obj?.get("client_fallback_ok") as? JsonPrimitive)
                                    ?.booleanOrNull ?: false,
                                reason = (obj?.get("reason") as? JsonPrimitive)?.contentOrNull,
                            ),
                        )
                    }
                    it.isSuccessful -> {
                        val bytes = it.body?.bytes()
                        // A 200 carrying no audio is a server fault, not a
                        // licence to synthesise locally.
                        if (bytes == null || bytes.isEmpty()) {
                            ApiResult.Ok(SaidAloud.NoEngine(fallbackOk = false, reason = null))
                        } else {
                            ApiResult.Ok(SaidAloud.Audio(bytes))
                        }
                    }
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
     * Streams the reply as a chunked HTTP body — or as SSE; see
     * [ChatChunkParser]'s own doc for why both are real. The returned [Call]
     * is the interrupt: cancel it and generation stops.
     *
     * The body was `{"message": "<text>"}` here, and that was wrong - not a
     * simplification of the real shape, a different, unread one.
     * `jarvis-desktop/src-tauri/src/commands.rs:777-784` names the actual
     * contract, established against the real backend rather than guessed:
     * `jarvis_hud.py`'s `_build_payload` forwards only
     * `model / messages / stream / temperature / max_tokens` upstream, in the
     * OpenAI shape `/v1/chat/completions` expects. A bare `message` key is
     * not one of those, so the backend had nothing to read it as.
     *
     * `has_image` is always false here: this client has no screenshot
     * capture, so there is never an image to route the turn toward. `auto`
     * mirrors the desktop's own `true` - matched rather than guessed,
     * because the desktop side is the one already confirmed against the
     * backend.
     */
    fun chatCall(message: String): Call? {
        val target = url("/api/chat") ?: return null
        val body = """{"messages":[{"role":"user","content":${quote(message)}}],"has_image":false,"stream":true,"auto":true}"""
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
        // 503 is "that subsystem is not installed", which is a different
        // sentence from "the desktop is broken" and has a different remedy.
        // The voice routes answer it whenever the speech module is absent -
        // which is always, today - and it read as "The desktop answered 503."
        // `say` never reaches here; it needs the body and handles 503 itself.
        503 -> ApiError.NotAvailable
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
         * Strips anything OkHttp will not accept in a header value.
         *
         * This exists for ONE reason, and it is the standing rule "never log
         * the token". `Headers.Builder` validates every value and, on a bad
         * character, throws an `IllegalArgumentException` whose message is
         * `Unexpected char 0x0a at 12 in X-Jarvis-Token value: <the value>` -
         * OkHttp only withholds the value for headers it knows are sensitive,
         * and its list is `Authorization`, `Cookie`, `Proxy-Authorization`,
         * `Set-Cookie`. `X-Jarvis-Token` is not on it, and OkHttp has no way
         * to know that it should be. So the whole token went into the
         * exception message - which this app then logs with `Log.w` and, in
         * `ChatSession`, puts on screen as the error text.
         *
         * Not hypothetical: `setToken` trims the ends, so a pasted trailing
         * newline is handled, but a token pasted with a line break INSIDE it,
         * or one carrying a curly quote or a zero-width space from a chat app,
         * reaches here intact and trips exactly this.
         *
         * Stripping rather than throwing. The stripped token is wrong, so the
         * desktop answers 401 and the owner sees "The desktop refused that
         * token." - which is both true and the right next step (re-pair). A
         * thrown exception here would instead surface as a crash, on a code
         * path that runs for every single request.
         *
         * The kept range is the printable ASCII OkHttp allows in a value,
         * minus the space: a pairing token has no spaces in it, and keeping
         * them would let an invisible-looking one through.
         */
        fun headerSafe(token: String): String {
            val safe = token.filter { it.code in 0x21..0x7E }
            if (safe.length != token.length) {
                // The LENGTHS, never the value, and never the characters that
                // were removed - a token is short enough that naming its bad
                // characters narrows it.
                Log.w(
                    TAG,
                    "the stored token has characters that cannot go in an HTTP header; " +
                        "sending it without them (${token.length} -> ${safe.length} chars). " +
                        "The desktop will refuse this - re-pair to fix it.",
                )
            }
            return safe
        }

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
