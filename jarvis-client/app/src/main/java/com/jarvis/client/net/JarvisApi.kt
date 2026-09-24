package com.jarvis.client.net

import android.util.Log
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonElement
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
        // A chat turn waiting on an approval card can hold for three minutes
        // (the gate's own timeout) before a word is written. That no longer
        // trips this: the desktop sends a keepalive line every 10 seconds of
        // silence (`backend/chat-stream.patch`), and each one restarts this
        // clock. On a desktop without that patch it still would.
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
     * `/api/chat` streams for as long as a reply takes, with a keepalive only
     * every 10s of silence (and none at all from a desktop without
     * chat-stream.patch), so it gets the looser 120s silence limit set above.
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

    suspend fun pending(): ApiResult<List<PendingItem>> = pendingRead().map { it.items }

    /**
     * `/api/pending`, row by row: the list is found as raw JSON, then each row
     * is read on its own (see [decodePendingRows]), so one row in an
     * unexpected shape costs that row - counted in [PendingRead.skipped] -
     * rather than the whole queue.
     */
    suspend fun pendingRead(): ApiResult<PendingRead> =
        get("/api/pending", ListSerializer(JsonElement.serializer()), PENDING_KEYS)
            .map { decodePendingRows(it) }

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
     */
    suspend fun switchModel(ref: String): ApiResult<Unit> =
        postJson("/api/models/switch", """{"ref":${quote(ref)}}""")

    /** `POST /api/models/rollback {}` - tier `auto`, never waits. */
    suspend fun rollbackModel(): ApiResult<Unit> = postJson("/api/models/rollback", "{}")

    /**
     * `POST /api/models/install {"ref": ...}` - same body shape as
     * [switchModel], same `brain_model` command on the desktop side, same
     * tier `ask`: a 2xx means a decision card was raised, not that anything
     * downloaded. The owner types `ref` in, the same as at a terminal or in
     * `ollama pull <ref>` - there is still no on-phone BROWSING of what is
     * installable, only of what already is (`models()`, above). CLAUDE.md's
     * 2026-09-20 amendment is the record of this being allowed; see it for
     * why a typed name and not a catalogue.
     */
    suspend fun installModel(ref: String): ApiResult<Unit> =
        postJson("/api/models/install", """{"ref":${quote(ref)}}""")

    // ------------------------------------------------- autonomy proposals --

    /**
     * A note sent before the first decision on a proposal -
     * `docs/AUTONOMY-PROPOSALS.md` §3b. This is NOT a decision and approves
     * nothing. The desktop keeps the note with the card (the card itself
     * does not change) and hands it to the model together with the owner's
     * answer, whichever answer that is.
     *
     * Served by the desktop's `backend/task-control.patch`. A 404 means that
     * patch is not applied there, and [JarvisRuntime] says so; a 409 means
     * the card is no longer waiting.
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
     * Served by the desktop's `backend/task-control.patch`, under exactly
     * these names. Stop and Pause need no approval card; Resume raises one
     * listing the steps that are left and runs nothing until it is
     * approved. A 409 means there was nothing to act on (nothing running or
     * paused); a 404 means the patch is not applied - see [TaskControl].
     */
    suspend fun pauseTask(): ApiResult<Unit> = postJson("/api/task/pause", "{}")

    suspend fun resumeTask(): ApiResult<Unit> = postJson("/api/task/resume", "{}")

    suspend fun stopTask(): ApiResult<Unit> = postJson("/api/task/stop", "{}")

    suspend fun injectTaskNote(note: String): ApiResult<Unit> =
        postJson("/api/task/note", """{"note":${quote(note)}}""")

    // ------------------------------------------------------------ notes ----

    /**
     * Files the owner's own words in Logseq, Joplin or Obsidian - [NoteCapture]. The
     * answer is the desktop's job record, 200 when finished and 202 while an
     * approval card waits. A refusal the desktop explained (no Logseq
     * folder, no Joplin token, "you said no") also comes back as a job, with
     * `state: "not_filed"` and the reason, so the phone can show that
     * sentence rather than a status code.
     */
    suspend fun captureNote(target: String, text: String): ApiResult<JsonObject> {
        val body = NoteCapture.body(target, text)
            ?: return ApiResult.Failed(ApiError.Malformed("the note is empty"))
        return postForJob(NoteCapture.PATH, body)
    }

    /** How a note filed with [captureNote] ended. Never carries its text. */
    suspend fun noteStatus(id: String): ApiResult<JsonObject> = probe(NoteCapture.statusPath(id))

    /**
     * Which note apps the desktop is set up for: the same path with no id,
     * answering `{"ok": true, "targets": [...]}` - names only. Read it with
     * [NoteCapture.targets].
     */
    suspend fun noteTargets(): ApiResult<JsonObject> = probe(NoteCapture.PATH)

    // ------------------------------------------------------------- wiki ----

    /**
     * The wiki builder's documents and whether it can run - [Wiki.read].
     * Names, states and reasons only: the phone never reads a page.
     */
    suspend fun wiki(): ApiResult<JsonObject> = probe(Wiki.PATH)

    /**
     * "Add to wiki" for one document in the desktop's `Jarvis Wiki/Sources`.
     * Answers the job (202, `state: "reading"`), or a refusal the desktop
     * explained (`state: "refused"` with `error`) - both as [ApiResult.Ok],
     * for [Wiki.describe]. Nothing is written until the card it raises is
     * approved.
     */
    suspend fun wikiIngest(source: String): ApiResult<JsonObject> {
        val body = Wiki.body(source)
            ?: return ApiResult.Failed(ApiError.Malformed("no document named"))
        return postForJob(Wiki.INGEST_PATH, body)
    }

    /** How one "Add to wiki" is going. Never carries a page's text. */
    suspend fun wikiJob(id: String): ApiResult<JsonObject> = probe(Wiki.statusPath(id))

    private suspend fun postForJob(path: String, json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                ApiError.Unreachable("No desktop address set"),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    when {
                        resp.isSuccessful && obj != null -> ApiResult.Ok(obj)
                        resp.isSuccessful -> ApiResult.Failed(ApiError.Malformed("not a job record"))
                        // An explained refusal is an answer, not a transport error.
                        obj != null && obj.containsKey("state") -> ApiResult.Ok(obj)
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 -> ApiResult.Failed(ApiError.NotFound)
                        resp.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, text.take(200)))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
        }

    // ------------------------------------------------------------ power ----

    /**
     * Active, Quiet or Standby - the desktop's `POST /api/power`
     * (`backend/power-mode.patch`). The desktop decides through its approval
     * gate as `power_manage`; the answer carries its own sentence in
     * `message`, and `waiting: true` while a card is up. The mode shown on
     * screen still comes from `/api/status` and the `power` event, never
     * from this call.
     */
    suspend fun setPower(mode: String): ApiResult<JsonObject> =
        postForJob("/api/power", "{\"mode\":${quote(mode)}}")

    // ------------------------------------------------------ second card ----

    /**
     * `GET /api/second-card` - what the PC found and each switch's state
     * ([SecondCard.parse]). A 404 is an older backend and a 503 a module that
     * did not load; [SecondCard.readOf] turns both into sentences.
     */
    suspend fun secondCard(): ApiResult<JsonObject> = probe(SecondCard.PATH)

    /**
     * One second-card switch on or off. ON raises one approval card on the PC
     * and changes nothing until it is approved; OFF is immediate. So a success
     * never means "it is on" - re-read [secondCard] for that. See
     * [SecondCard.classifyPost] for which answers come back as sentences.
     */
    suspend fun setSecondCard(feature: String, enabled: Boolean): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(SecondCard.PATH) ?: return@withContext ApiResult.Failed(
                ApiError.Unreachable("No desktop address set"),
            )
            val body = SecondCard.postBody(feature, enabled)
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    SecondCard.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
        }

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
     * The third answer on a correction card, "Both are true": keep the new
     * fact AND keep the old one - nothing is retired (`memory-intake.patch`).
     * One PROPOSAL id, one decision, like [decideMemory]; no list form.
     *
     * The backend answers 409 for a card that has no old fact to keep (and
     * for a "stop using this fact?" card), which [postJson] reports as
     * [ApiError.AlreadyHandled]; 404 when the card was already decided. The
     * screen only offers this where the row's own `keep_both_ok` is true,
     * so on a backend without the route the button never appears.
     */
    suspend fun keepBothMemory(id: Long): ApiResult<Unit> =
        postJson(MemoryCards.KEEP_BOTH_PATH, MemoryCards.keepBothBody(id))

    /**
     * The owner's right/wrong mark on ONE answer - `POST /api/feedback/mark`
     * (`feedback.patch`). [AnswerMark.NONE] takes a mark back. One id per
     * call and no list form: the backend refuses a list, because a "mark
     * all" would move every fact's counter at once on one tap.
     *
     * A mark never changes memory. At most it makes the desktop queue ONE
     * "stop using this fact?" card, which the owner still has to answer.
     */
    suspend fun markAnswer(turnId: String, mark: AnswerMark): ApiResult<Unit> {
        val body = Feedback.markBody(turnId, mark)
            ?: return ApiResult.Failed(ApiError.Malformed("not an answer id"))
        return postJson(Feedback.MARK_PATH, body)
    }

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
     * Answers the daily overnight-tidy card (not built yet) - see
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
     * The handle comes from the undo shelf (`GET /api/undo`), the same list
     * the desktop's Brain window takes it from: an entry with `category:
     * "hold"` and `detail.handle` - see [UndoEntry.holdHandle]. No
     * `GET /api/holds` was invented for it (an earlier draft did, and it was
     * rightly removed).
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
        // mic=phone: the PC checks the clip against this phone's own voice
        // print when there is one (a PC older than 2026-09-24 ignores it).
        val target = url("/api/voice/utterance?source=$source&mic=$MIC_PHONE") ?: return@withContext ApiResult.Failed(
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
     * Asks the desktop to turn the wake word on or off. ON raises an
     * approval card on the desktop and changes nothing until it is approved;
     * OFF is immediate (backend/jarvis_speech.py `set_wake_enabled`).
     *
     * Gated as a config change server-side, and **approval means approved, not
     * already live** — the value lives in the TOML. So a success here does not
     * mean the wake word is on; re-read [voiceStatus] for that.
     */
    suspend fun setWakeWord(enabled: Boolean): ApiResult<Unit> =
        postJson("/api/voice/wake", """{"enabled":$enabled}""")

    /**
     * "Train my voice": sends the owner's recorded clips to the desktop.
     *
     * A 202 means **a card was raised**, not that anything was learned - the
     * desktop enrols the voice only once that card is approved, and throws
     * the clips away either way. So this never reports "trained"; re-read
     * [voiceStatus] for that.
     *
     * A refusal the desktop explains (400 a bad clip, 409 a card already
     * waiting, 503 not installed) comes back as `Ok` with [VoiceTrainingReply.error]
     * set, because those sentences are written for the owner and are the
     * most useful thing to show. 401/403/404 stay failures: a bad token and
     * "this desktop has no such route" are not the desktop's words to relay.
     *
     * Uses the general [client]: a few megabytes over Tailscale is not a
     * short call. Nothing here is logged - the body is the owner's voice.
     */
    suspend fun enrollVoice(clips: List<ByteArray>, mic: String? = null): ApiResult<VoiceTrainingReply> =
        postTraining(enrollRequestBody(clips, mic = mic))

    /**
     * Proposes a new bar for the owner's voice on [mic] - the PC raises an
     * approval card and changes nothing until it is approved. The same
     * route and answer shape as [enrollVoice].
     */
    suspend fun proposeVoiceThreshold(value: Double, mic: String): ApiResult<VoiceTrainingReply> =
        postTraining(thresholdRequestBody(value, mic))

    /**
     * The "someone else" check: another person's clips, scored against the
     * owner's print on the PC and thrown away. Changes nothing, raises no
     * card. **Only after [VoiceTrainingState.calibrate]** - see its doc for
     * why an older PC must never be sent this.
     */
    suspend fun calibrateVoice(clips: List<ByteArray>, mic: String): ApiResult<VoiceCalibration> =
        withContext(Dispatchers.IO) {
            val target = url("/api/voice/enroll") ?: return@withContext ApiResult.Failed(
                ApiError.Unreachable("No desktop address set"),
            )
            val body = enrollRequestBody(clips, mic = mic, mode = "calibrate")
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                client.newCall(req).execute().use {
                    when (it.code) {
                        401, 403, 404 -> ApiResult.Failed(errorFor(it))
                        else -> {
                            val text = it.body?.string().orEmpty()
                            val reply = runCatching {
                                JarvisJson.decodeFromString(VoiceCalibration.serializer(), text)
                            }.getOrNull()
                            when {
                                reply != null && (it.isSuccessful || reply.error.isNotBlank()) ->
                                    ApiResult.Ok(reply)
                                it.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                                else -> ApiResult.Failed(ApiError.Server(it.code, ""))
                            }
                        }
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
        }

    private suspend fun postTraining(json: String): ApiResult<VoiceTrainingReply> =
        withContext(Dispatchers.IO) {
            val target = url("/api/voice/enroll") ?: return@withContext ApiResult.Failed(
                ApiError.Unreachable("No desktop address set"),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                client.newCall(req).execute().use {
                    when (it.code) {
                        401, 403, 404 -> ApiResult.Failed(errorFor(it))
                        else -> {
                            val text = it.body?.string().orEmpty()
                            val reply = runCatching {
                                JarvisJson.decodeFromString(VoiceTrainingReply.serializer(), text)
                            }.getOrNull()
                            when {
                                reply != null && (it.isSuccessful || reply.error.isNotBlank()) ->
                                    ApiResult.Ok(reply)
                                it.isSuccessful ->
                                    ApiResult.Failed(ApiError.Malformed("unreadable training reply"))
                                it.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                                else -> ApiResult.Failed(ApiError.Server(it.code, ""))
                            }
                        }
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage())) }
        }

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
     * `has_image` is true only with a [picture] - a photo the owner picked,
     * sent only while the PC's second-card Pictures feature works (see
     * [ChatPicture]). `auto` mirrors the desktop's own `true` - matched
     * rather than guessed, because the desktop side is the one already
     * confirmed against the backend.
     *
     * [history] is the conversation so far - earlier questions and the
     * answers to them, already trimmed to fit - sent ahead of [message] so a
     * follow-up is understood. Only one user turn used to go, and every
     * follow-up started from nothing. See [ChatHistory] for what is kept,
     * how much, and why.
     */
    fun chatCall(
        message: String,
        history: List<ChatHistory.Exchange> = emptyList(),
        picture: String? = null,
    ): Call? {
        val target = url("/api/chat") ?: return null
        val body = ChatHistory.requestBody(history, message, picture)
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

        /** Which microphone this app's clips come from - the PC keeps a voice print per microphone. */
        const val MIC_PHONE = "phone"

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
