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
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit

/** What went wrong, in terms the UI can say out loud rather than a stack trace. */
sealed interface ApiError {
    /**
     * No host, or nothing listening there. [network] is the failure's kind
     * in the plain-words contract's terms ("refused", "connect_timeout",
     * "unknown_host", "read_timeout", ... - PlainErrors.networkKind), or
     * "not_paired" when no address is saved; "" when [detail] is this app's
     * own sentence (a blocker), shown as it is.
     */
    data class Unreachable(val detail: String, val network: String = "") : ApiError

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
        // Never follow a redirect (apps security audit L1). Every request
        // here carries X-Jarvis-Token, and a followed redirect would carry it
        // to wherever it pointed: OkHttp strips only Authorization when a
        // redirect changes host. The desktop's clients refuse redirects too,
        // and so does UpdateChecker. A 3xx from the PC now comes back as the
        // failure it is. [streamClient] and [shortCall] inherit both.
        .followRedirects(false)
        .followSslRedirects(false)
        // Straight to the PC, never through the phone's HTTP proxy (audit
        // L2). The link is plain HTTP inside Tailscale or NordVPN Meshnet,
        // so a proxy set in the Wi-Fi settings, or installed by a work
        // profile, would see the token in the clear. The desktop's clients
        // use no proxy either (`.no_proxy()`).
        .proxy(java.net.Proxy.NO_PROXY)
        // Why a key was refused (docs/PAIRING-DESIGN.md §5.3): a 401 may
        // carry `"key": "device_removed"` or `"shared_retired"`, which
        // [KeyRefusal] keeps - the reason word only, never the body - so the
        // places that already say "your PC did not accept this phone's key"
        // can say which. Every request made WITH a key that is answered
        // without a 401 clears it. [streamClient] and [shortCall] inherit
        // this, so the event stream's refusal is read too. The two no-key
        // pairing routes carry no key and are left alone.
        .addInterceptor { chain ->
            val response = chain.proceed(chain.request())
            if (chain.request().header(TOKEN_HEADER) != null) {
                if (response.code == 401) {
                    KeyRefusal.note(runCatching { response.peekBody(2_048L).string() }.getOrNull())
                } else {
                    KeyRefusal.clear()
                }
            }
            response
        }
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

    /** Why the saved address is refused (off the owner's own networks), or null. */
    fun baseProblem(): String? = settings.baseProblem()

    /**
     * Why a request has no address to go to. A saved address off the owner's
     * own networks ([com.jarvis.client.data.OwnNetwork]) is never used, and
     * says so in its own sentence - shown as it is, the way PlainErrors shows
     * this app's own words - rather than "not paired", which would be untrue.
     * With nothing saved at all, [network] says how to classify it.
     */
    private fun noAddress(network: String = PlainErrors.NOT_PAIRED): ApiError =
        baseProblem()?.let { ApiError.Unreachable(it) }
            ?: ApiError.Unreachable("No desktop address set", network)

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

    /**
     * Past approvals - "Activity" (ease-of-use audit, 2026-09-27, row 11):
     * the SAME `/api/pending` response's `history` array, asked for BY NAME
     * rather than found by the positional fallback [parseListBody] uses for
     * `pending` - the exact thing [ALREADY_HANDLED_KEYS] exists to refuse
     * when a caller has not named the key it wants. This one has.
     *
     * Read-only, and never merged into [pending]: a decided card and a
     * waiting one must never share a list (see [ALREADY_HANDLED_KEYS]'s own
     * comment for why that specific mistake is worse than an empty queue).
     */
    suspend fun gateHistoryRead(): ApiResult<GateHistoryRead> =
        get("/api/pending", ListSerializer(JsonElement.serializer()), listOf("history"))
            .map { decodeGateHistoryRows(it) }

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

    /**
     * "Stop everything" - `backend/jarvis_stop_all.py`. The PC's answer is
     * `{"ok", "stopped": [sentences], "problems", "message"}`; see
     * [StopEverything]. Never a card, never gated on a stale link.
     */
    suspend fun stopEverything(): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url("/api/stop_all") ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = "{}".toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    when {
                        resp.isSuccessful -> ApiResult.Ok(obj ?: JsonObject(emptyMap()))
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 -> ApiResult.Failed(ApiError.NotFound)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, text.take(200)))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

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

    // ------------------------------------------------------------ watch ----

    /** `GET /api/watch` - the topics being watched ([Watch.read]). */
    suspend fun watch(): ApiResult<JsonObject> = probe(Watch.PATH)

    /** `GET /api/watch/report` - what is new. A peek: reading it marks nothing read. */
    suspend fun watchReport(): ApiResult<JsonObject> = probe(Watch.REPORT_PATH)

    /** Watch a topic. [body] is [Watch.addBody]'s. */
    suspend fun watchAdd(body: String): ApiResult<DesktopWrite.Outcome> = postWrite(Watch.ADD_PATH, body)

    /** Forget a topic and everything remembered about it. */
    suspend fun watchRemove(name: String): ApiResult<DesktopWrite.Outcome> =
        postWrite(Watch.REMOVE_PATH, Watch.removeBody(name))

    /** Mark everything new as read - the consume, where [watchReport] is the peek. */
    suspend fun watchSeen(): ApiResult<DesktopWrite.Outcome> = postWrite(Watch.SEEN_PATH, Watch.SEEN_BODY)

    // ----------------------------------------------------------- skills ----

    /**
     * Removes one skill: `{"name": ..., "remove": true}`, as the desktop sends
     * it. Removal only - there is no route that installs a skill, because
     * installing runs the scanner and the gate on the PC.
     */
    suspend fun removeSkill(name: String): ApiResult<DesktopWrite.Outcome> =
        postWrite(Skills.DECIDE_PATH, Skills.removeBody(name))

    /** The learning switch - see [MemoryCounts]. ON answers 202 waiting while a card is up. */
    suspend fun setLearning(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(MemoryCounts.LEARNING_WRITE_PATH, MemoryCounts.learningBody(on))

    // ------------------------------------------------ automatic learning ----
    // docs/JARVIS-API.md section 19 (2026-09-24). See [AutoLearn] for the
    // shapes, the words and the rules; these only carry them.

    /** `GET /api/memory/learning`: the two automatic-learning switches and their cards. */
    suspend fun autoLearnSettings(): ApiResult<JsonObject> = probeKeeping503(AutoLearn.SETTINGS_PATH)

    /**
     * One switch. ON answers 202 waiting while its approval card is up; OFF is
     * immediate, and withdraws an ON card still waiting.
     */
    suspend fun setAutoLearn(which: AutoLearn.Which, on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(which.path, AutoLearn.enabledBody(on))

    /** `GET /api/memory/auto`: one page of the facts saved without a card, newest first. */
    suspend fun autoFacts(before: Double? = null, limit: Int = AutoLearn.PAGE): ApiResult<JsonObject> =
        probeKeeping503(AutoLearn.listPath(before, limit))

    // ------------------------------------------------- smartwatch notifications ----
    // docs/JARVIS-API.md; see [WatchNotify] for the shapes and words.

    /** `GET /api/notifications/watch`: `{"enabled", "waiting", "last", "why"}`. */
    suspend fun watchNotifySettings(): ApiResult<JsonObject> = probe(WatchNotify.PATH)

    /**
     * The switch. ON answers 202 waiting while its approval card is up; OFF
     * is immediate, and withdraws an ON card still waiting.
     */
    suspend fun setWatchNotify(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(WatchNotify.PATH, WatchNotify.enabledBody(on))

    // ------------------------------------------------- picture mode for the screen ----
    // docs/JARVIS-API.md section 96.1; see [ScreenPicture] for the shapes and
    // words. Decided on the PC like every other approval-card switch here.

    /** `GET /api/screen/picture`: `{"enabled", "waiting", "line", "measured_words", "install_line", ...}`. */
    suspend fun screenPictureSettings(): ApiResult<JsonObject> = probe(ScreenPicture.PATH)

    /**
     * The switch. ON answers 202 waiting while its approval card is up; OFF is
     * immediate, and withdraws an ON card still waiting.
     */
    suspend fun setScreenPicture(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(ScreenPicture.PATH, ScreenPicture.enabledBody(on))

    // ------------------------------------------------- the headless browser ----
    // docs/JARVIS-API.md section 97; see [BrowserEngine] for the shapes and
    // words. Decided on the PC like every other approval-card switch here.

    /** `GET /api/browser/engine`: `{"obscura", "waiting", "mode", "line", "status_line", "install_line", ...}`. */
    suspend fun browserEngineSettings(): ApiResult<JsonObject> = probe(BrowserEngine.PATH)

    /**
     * The switch. ON answers 202 waiting while its approval card is up; OFF is
     * immediate, and withdraws an ON card still waiting.
     */
    suspend fun setBrowserEngine(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(BrowserEngine.PATH, BrowserEngine.enabledBody(on))

    /**
     * Which browser Jarvis uses by default. At once, no card. Nothing but a
     * body [BrowserEngine.modeBody] made is sent.
     */
    suspend fun setBrowserEngineMode(body: String): ApiResult<DesktopWrite.Outcome> =
        postWrite(BrowserEngine.PATH, body)

    // ------------------------------------------------- pairing and devices ----
    // docs/PAIRING-DESIGN.md §6.2 and §6.4.

    /**
     * One of the two pairing routes that take NO key (`/api/pair/claim`,
     * `/api/pair/collect`): the phone has none yet, and the sums in the body
     * are what prove it may ask. Sent to [base] - the PC named by the QR code
     * or the typed name, never the saved address - and deliberately not
     * [authed]: no `X-Jarvis-Token`. It still sends `X-Jarvis-Client: hud`,
     * which the PC's origin check requires of every request. Status 0 means
     * nothing answered. Nothing about the request or its answer is logged.
     */
    suspend fun pairPost(base: String, path: String, json: String): Pair<Int, JsonObject?> =
        withContext(Dispatchers.IO) {
            if (path != Pairing.CLAIM_PATH && path != Pairing.COLLECT_PATH) return@withContext 0 to null
            val target = runCatching { (base.trimEnd('/') + path).toHttpUrlOrNull() }.getOrNull()
                ?: return@withContext 0 to null
            val req = Request.Builder()
                .url(target)
                .post(json.toRequestBody("application/json".toMediaType()))
                .header(CLIENT_HEADER, CLIENT_VALUE)
                .header("Accept", "application/json")
                .build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    resp.code to runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                }
            }.getOrElse { 0 to null }
        }

    /** `GET /api/devices`: every device with its own key, and the old shared key's state. */
    suspend fun devices(): ApiResult<JsonObject> = probe(Devices.PATH)

    /**
     * `POST /api/devices/remove` or `/api/devices/shared`: the status and the
     * body come back together ([Devices.removeSaid], [Devices.retireSaid]),
     * so the PC's reason is shown. A 401 is a refused key.
     */
    suspend fun devicesPost(path: String, json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            if (path != Devices.REMOVE_PATH && path != Devices.SHARED_PATH) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a devices route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    if (resp.code == 401) ApiResult.Failed(ApiError.BadToken) else ApiResult.Ok(resp.code to obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    // ------------------------------------------------- reading phone notifications ----
    // docs/JARVIS-API.md §61; see [PhoneNotifications] for the shapes and
    // words. This switch is decided on the PC, the same as every other one
    // here, even though only this phone ever acts on it (ARCHITECTURE §8).

    /** `GET /api/notifications/phone`: `{"enabled", "waiting", "last", "why"}`. */
    suspend fun phoneNotificationsSettings(): ApiResult<JsonObject> = probe(PhoneNotifications.PATH)

    /**
     * Whether the PC is watching its own screen ("Watch with me",
     * docs/JARVIS-API.md section 62): `{on, state, left_s, ...}` and never a
     * word from the screen. Read to show the sign on this phone too.
     */
    suspend fun screenWatch(): ApiResult<JsonObject> = probe(ScreenRules.PATH)

    /**
     * Ends the PC's watching. The one thing the phone may send to that route:
     * a stop is accepted from anywhere, while starting or asking is refused
     * unless the request comes from the PC itself. Never a card.
     */
    suspend fun stopScreenWatch(): ApiResult<Unit> = postJson(ScreenRules.PATH, ScreenRules.STOP_BODY)

    /**
     * The switch. ON answers 202 waiting while its approval card is up; OFF
     * is immediate, and withdraws an ON card still waiting.
     */
    suspend fun setPhoneNotifications(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(PhoneNotifications.PATH, PhoneNotifications.enabledBody(on))

    /**
     * [probe], except that a 503 keeps its body: `ApiError.Server(503, body)`
     * instead of [ApiError.NotAvailable], so the PC's own `error` ("automatic
     * learning is not installed on this PC, ...") reaches the owner
     * ([AutoLearn.readFailure]). Only the automatic-learning reads use it;
     * every other route's 503 is unchanged.
     */
    private suspend fun probeKeeping503(path: String): ApiResult<JsonObject> = withContext(Dispatchers.IO) {
        val target = url(path) ?: return@withContext ApiResult.Failed(
            noAddress(),
        )
        val req = Request.Builder().url(target).get().authed().build()
        runCatching {
            shortCall.newCall(req).execute().use {
                if (it.code == 503) {
                    return@use ApiResult.Failed(ApiError.Server(503, it.body?.string().orEmpty().take(2000)))
                }
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val text = it.body?.string().orEmpty()
                runCatching {
                    when (val el = JarvisJson.parseToJsonElement(text)) {
                        is JsonObject -> ApiResult.Ok(el)
                        else -> ApiResult.Failed(ApiError.Malformed("not a JSON object"))
                    }
                }.getOrElse { ApiResult.Failed(ApiError.Malformed(it.message ?: "bad json")) }
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
    }

    /**
     * `POST /api/memory/forget`: ONE fact, retired rather than deleted. The
     * same route as the desktop's Forget; the phone sends no `valid_to`
     * ("stopped being true just now", the usual case). A 404 - no such fact -
     * comes back as [ApiError.NotFound].
     */
    suspend fun forgetFact(id: Long): ApiResult<JsonObject> =
        postForJob(AutoLearn.FORGET_PATH, AutoLearn.forgetBody(id))

    /**
     * `POST /api/memory/erase`: "Erase the words" of ONE fact - its words
     * wiped from the PC for good, its dates kept (the owner's decision,
     * 2026-09-24). `alsoDeleteConversation` (2026-09-27): "Also delete the
     * chat it came from" - off unless the owner checks the box. The status
     * and body come back whole ([MemoryErase.Reply]):
     * a 404 that says "no such fact" and a 404 from a PC without the route
     * must read differently, and [postForJob] would make both [ApiError.NotFound].
     * [MemoryErase.said] reads it.
     */
    suspend fun eraseFact(id: Long, alsoDeleteConversation: Boolean = false): ApiResult<MemoryErase.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(MemoryErase.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = MemoryErase.body(id, alsoDeleteConversation)
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(MemoryErase.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/memory/profile`: "Always keep in mind" - the facts the owner
     * pinned, and how many of the list's characters they use
     * ([MemoryProfile.parse]). A 404 or 501 is a PC without the list
     * ([MemoryProfile.missing]).
     */
    suspend fun memoryProfile(): ApiResult<JsonObject> = probe(MemoryProfile.PATH)

    /**
     * `GET /api/memory/shared`: "Between us" - the facts the owner tagged
     * as a shared joke or nickname ([MemoryShared.parse]). A 404 or 501 is
     * a PC without the list ([MemoryShared.missing]).
     */
    suspend fun memoryShared(): ApiResult<JsonObject> = probe(MemoryShared.PATH)

    /**
     * `GET /api/memory/entities`: "People and things" - the names saved facts
     * are linked to, with the fact ids behind each and no words
     * ([Entities.parse]). The words come from [memoryUsed]. A read.
     */
    suspend fun memoryEntities(): ApiResult<JsonObject> = probe(Entities.PATH)

    /**
     * `GET /api/schedule`: "Coming up" - the timers, alarms, reminders and
     * the to-do list ([Schedule.parse]). A 404 or 501 is a PC without the
     * scheduler ([Schedule.missing]). A read.
     */
    suspend fun schedule(): ApiResult<JsonObject> = probe(Schedule.PATH)

    /**
     * `GET /api/schedule?id=`: ONE job, also one that went off in the last
     * day - how a notification gets its words, since the `schedule` event
     * carries the id and the kind only ([Schedule.parseOne]). A read.
     */
    suspend fun scheduleJob(id: String): ApiResult<JsonObject> {
        if (!Schedule.validId(id)) return ApiResult.Failed(ApiError.Malformed("not a job id"))
        return probe(Schedule.PATH + "?id=" + id)
    }

    /**
     * `GET /api/briefing`: the latest morning briefing, the briefing jobs and
     * what a briefing includes ([Briefing.parse]). A 404 or 501 is a PC
     * without it ([Briefing.missing]). A read.
     */
    suspend fun briefing(): ApiResult<JsonObject> = probe(Briefing.PATH)

    /**
     * `POST /api/briefing/senders`: "Show who new emails are from". OFF is
     * done at once; ON is 202 while ONE approval card waits on the PC.
     */
    suspend fun setBriefingSenders(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(Briefing.SENDERS_PATH, Briefing.sendersBody(on))

    /** Windows gets 30 seconds to read the words in one picture (backend jarvis_ocr.TIMEOUT_S). */
    private val photoCall: OkHttpClient by lazy {
        client.newBuilder()
            .readTimeout(45, TimeUnit.SECONDS)
            .callTimeout(50, TimeUnit.SECONDS)
            .build()
    }

    /**
     * `POST /api/photo/scan` ("Photo to reminder", JARVIS-API.md section 83):
     * the PC reads the dates in one picture and PROPOSES a reminder
     * ([PhotoReminder.parse] reads the answer). It sets nothing up, so it is
     * not held on a stale link, like every read. The body is
     * [PhotoReminder.scanBody]'s: a `data:image/` picture only.
     */
    suspend fun photoScan(json: String): ApiResult<Pair<Int, JsonObject?>> = withContext(Dispatchers.IO) {
        val target = url(PhotoReminder.SCAN_PATH) ?: return@withContext ApiResult.Failed(noAddress())
        val body = json.toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url(target).post(body).authed().build()
        runCatching {
            photoCall.newCall(req).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                if (resp.code == 401 || resp.code == 403) {
                    ApiResult.Failed(ApiError.BadToken)
                } else {
                    ApiResult.Ok(resp.code to obj)
                }
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
    }

    /** A widget preview waits for the PC's AI model: it gets 40 seconds there. */
    private val widgetDraftCall: OkHttpClient by lazy {
        client.newBuilder()
            .readTimeout(60, TimeUnit.SECONDS)
            .callTimeout(65, TimeUnit.SECONDS)
            .build()
    }

    /** `GET /api/widgets` - the saved widgets, the previews and the menu ([JarvisWidgets]). A read. */
    suspend fun widgets(): ApiResult<JsonObject> = probe(JarvisWidgets.LIST_PATH)

    /** `GET /api/widgets/show?id=` - one widget, filled in now on the PC. A read. */
    suspend fun widgetShow(id: String): ApiResult<JsonObject> {
        if (!JarvisWidgets.validId(id)) return ApiResult.Failed(ApiError.Malformed("not a widget id"))
        return probe(JarvisWidgets.SHOW_PATH + "?id=" + id)
    }

    /**
     * One of the widget POSTs ([JarvisWidgets.POST_PATHS]) - anything else is
     * refused here, before anything is sent. The answer's status and body
     * come back together, so the PC's own sentence is shown for a refusal.
     */
    suspend fun widgetPost(path: String, json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            if (path !in JarvisWidgets.POST_PATHS) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a widget route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            val caller = if (path == JarvisWidgets.DRAFT_PATH) widgetDraftCall else shortCall
            runCatching {
                caller.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(resp.code to obj)
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /** "Brief me now" can wait for a slow calendar or mail server: the PC gives them 25 seconds. */
    private val briefingCall: OkHttpClient by lazy {
        client.newBuilder()
            .readTimeout(45, TimeUnit.SECONDS)
            .callTimeout(50, TimeUnit.SECONDS)
            .build()
    }

    /**
     * `POST /api/briefing/now`: put one together now ([Briefing.parse] reads
     * the answer). It only READS on the PC - no card, nothing changes - so
     * it is not held on a stale link, like every read.
     */
    suspend fun briefingNow(missed: Boolean = false): ApiResult<JsonObject> = withContext(Dispatchers.IO) {
        val target = url(Briefing.NOW_PATH) ?: return@withContext ApiResult.Failed(
            noAddress(),
        )
        // {"missed": true}: "What did I miss?" (2026-09-25) - the same route.
        val body = if (missed) Briefing.MISSED_BODY else "{}"
        val req = Request.Builder().url(target)
            .post(body.toRequestBody("application/json".toMediaType())).authed().build()
        runCatching {
            briefingCall.newCall(req).execute().use {
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val text = it.body?.string().orEmpty()
                runCatching {
                    when (val el = JarvisJson.parseToJsonElement(text)) {
                        is JsonObject -> ApiResult.Ok(el)
                        else -> ApiResult.Failed(ApiError.Malformed("not a JSON object"))
                    }
                }.getOrElse { ApiResult.Failed(ApiError.Malformed(it.message ?: "bad json")) }
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
    }

    /**
     * `POST /api/schedule/act` (ONE job: pause, resume, delete, done) or
     * `POST /api/schedule/add` (one to-do item). The status and body come
     * back whole ([Schedule.Reply]), like [pinFact]: a 404 that says "no such
     * job" and a 404 from a PC without the route must read differently.
     */
    suspend fun scheduleWrite(path: String, json: String): ApiResult<Schedule.Reply> =
        withContext(Dispatchers.IO) {
            if (path != Schedule.ACT_PATH && path != Schedule.ADD_PATH) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a schedule route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Schedule.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/goals`: every goal, draft or active or stopped ([Goals.parse]).
     * A 404 or 501 is a PC without Goals ([Goals.missing]). A read.
     */
    suspend fun goals(): ApiResult<JsonObject> = probe(Goals.PATH)

    /** `GET /api/goals/<id>`: one goal ([Goals.parseOne]). A read. */
    suspend fun goal(id: String): ApiResult<JsonObject> {
        if (!Goals.validId(id)) return ApiResult.Failed(ApiError.Malformed("not a goal id"))
        return probe("${Goals.PATH}/$id")
    }

    /**
     * `POST /api/goals` (a new draft), `.../accept`, `.../step` or
     * `.../stop`. The status and body come back whole ([Goals.Reply]), like
     * [scheduleWrite]: a 404 that says "no such goal" and a 404 from a PC
     * without Goals at all must read differently ([Goals.createdSaid] /
     * [Goals.acceptedSaid] / [Goals.changedSaid]).
     */
    suspend fun goalsWrite(path: String, json: String): ApiResult<Goals.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Goals.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * The quiz calls wait for the PC's local model (writing questions,
     * marking an answer), so they get the long client's time. Lazy, like the
     * other longer clients here.
     */
    private val quizCallClient: OkHttpClient by lazy {
        client.newBuilder()
            .readTimeout(120, TimeUnit.SECONDS)
            .callTimeout(130, TimeUnit.SECONDS)
            .build()
    }

    /**
     * Every "Quiz me on a text" call (`/api/quiz`, docs/STUDY-FROM-TEXT-DESIGN.md
     * section 11): [json] null makes it a GET, otherwise a POST. The status and
     * body come back whole ([Quiz.Reply]) because the PC's error CODE (not the
     * status alone) says what went wrong. The pasted text and the answers are
     * in the request body only - never in a URL, never logged.
     */
    suspend fun quizCall(path: String, json: String?): ApiResult<Quiz.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val builder = Request.Builder().url(target)
            if (json == null) {
                builder.get()
            } else {
                builder.post(json.toRequestBody("application/json".toMediaType()))
            }
            val req = builder.authed().build()
            runCatching {
                quizCallClient.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Quiz.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * Every "My study decks" call (`/api/decks...`, `/api/review...`;
     * docs/QUIZ-DECKS-DESIGN.md, contract C4): [json] null makes it a GET,
     * otherwise a POST. The status and body come back whole ([Decks.Reply])
     * because the PC's error code and its own `message` are what the screen
     * shows. Card words travel in the request body only - never in a URL,
     * never logged. Reviewing calls no model, so the short client is enough.
     */
    suspend fun decksCall(path: String, json: String?): ApiResult<Decks.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val builder = Request.Builder().url(target)
            if (json == null) {
                builder.get()
            } else {
                builder.post(json.toRequestBody("application/json".toMediaType()))
            }
            val req = builder.authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Decks.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/memory/used?ids=`: the words of the few facts an answer used
     * (its `X-Jarvis-Route` names them by id only), or that automatic
     * learning just saved (the `memory_saved` event's ids) - the owner's
     * decision of 2026-09-25. [MemoryUsed.parse] reads it. A read.
     */
    suspend fun memoryUsed(ids: List<Long>): ApiResult<JsonObject> {
        val path = MemoryUsed.path(ids)
            ?: return ApiResult.Failed(ApiError.Malformed("no fact ids to read"))
        return probe(path)
    }

    /**
     * `GET /api/chat/sources?turn_id=`: this answer's own reading-tool
     * receipts (a note, a wiki page, a web result, a file - by reference
     * only) and its quote check - feasibility I42/I132, the same `turn_id`
     * [Feedback] and [MemoryUsed] already use. [ChatSources.parse] reads
     * it. A read.
     */
    suspend fun chatSources(turnId: String?): ApiResult<JsonObject> {
        val path = ChatSources.path(turnId)
            ?: return ApiResult.Failed(ApiError.Malformed("no answer id to read"))
        return probe(path)
    }

    /**
     * `GET /api/chat/table?id=` - the spending table a chat answer announced
     * with `: jarvis-table <id>` in its stream (docs/JARVIS-API.md section
     * 100.2). `X-Jarvis-Token` and `X-Jarvis-Client: hud` ride along like on
     * every request ([authed]); the token is never logged. The id is checked
     * to be exactly 32 lowercase hex characters before it goes into the URL
     * ([Spending.tablePath]). A read. A 404 is "gone"
     * ([Spending.gone]): the PC keeps a table two hours, in memory only.
     */
    suspend fun chatTable(id: String?): ApiResult<JsonObject> {
        val path = Spending.tablePath(id)
            ?: return ApiResult.Failed(ApiError.Malformed("no table id to read"))
        return probe(path)
    }

    /**
     * `GET /api/spending` - the bank layouts, categories and waiting files,
     * read-only on the phone ([Spending.parseView]). Any device may read it. A read.
     */
    suspend fun spending(): ApiResult<JsonObject> = probe(Spending.VIEW_PATH)

    /**
     * `GET /api/retirement/defaults` - the Retirement what-if form: fields,
     * limits, units, the made-up default figures and the PC's words
     * ([Retirement.parseDefaults]). Any device may read it. A read.
     */
    suspend fun retirementDefaults(): ApiResult<JsonObject> = probe("/api/retirement/defaults")

    /** A run can take up to 30 seconds on the PC (its own cap), so this waits a little longer. */
    private val retirementClient: OkHttpClient by lazy {
        client.newBuilder()
            .readTimeout(40, TimeUnit.SECONDS)
            .callTimeout(45, TimeUnit.SECONDS)
            .build()
    }

    /**
     * `POST /api/retirement/run` - the typed boxes ([Retirement.requestBody])
     * in, the status and JSON body back whole ([Retirement.Reply]) because the
     * PC's error code and its own message say what to show. `X-Jarvis-Client:
     * hud` and the token ride along like on every request ([authed]); the
     * body is the owner's money and is never logged or kept.
     */
    suspend fun retirementRun(json: String): ApiResult<Retirement.Reply> =
        withContext(Dispatchers.IO) {
            val target = url("/api/retirement/run") ?: return@withContext ApiResult.Failed(noAddress())
            val req = Request.Builder().url(target)
                .post(json.toRequestBody("application/json".toMediaType())).authed().build()
            runCatching {
                retirementClient.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Retirement.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `POST /api/memory/profile`: pin or unpin ONE fact (the owner's
     * decision, 2026-09-24). The status and body come back whole
     * ([MemoryProfile.Reply]), like [eraseFact]: a 404 that says "no such
     * fact" and a 404 from a PC without the route must read differently, and
     * a 409 carries the PC's own sentence. [MemoryProfile.said] reads it.
     */
    suspend fun pinFact(id: Long, pinned: Boolean): ApiResult<MemoryProfile.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(MemoryProfile.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = MemoryProfile.body(id, pinned).toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(MemoryProfile.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * "Forget a time frame" (docs/JARVIS-API.md section 64): a read (`json`
     * null, a GET - the status or the list for some days) or ONE change (a
     * POST of `json` - "Forget these", which makes the PC raise ONE card, or
     * Undo). The path comes from [ForgetRange] and nothing outside
     * `/api/memory/forget_range` is sent. The status and body come back
     * whole ([ForgetRange.Reply]): a 404 the PC sent itself and a 404 from a
     * PC without the routes read differently.
     */
    suspend fun forgetRangeCall(path: String, json: String?): ApiResult<ForgetRange.Reply> =
        withContext(Dispatchers.IO) {
            if (path != ForgetRange.PATH && !path.startsWith(ForgetRange.PATH + "/")) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a forget-range route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val builder = Request.Builder().url(target)
            if (json == null) {
                builder.get()
            } else {
                builder.post(json.toRequestBody("application/json".toMediaType()))
            }
            val req = builder.authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(ForgetRange.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * Topic controls (docs/JARVIS-API.md section 107): a read (`json` null,
     * a GET - the list, a preview, a review batch, "Show them") or ONE change
     * (a POST of `json`). The path comes from [Topics] and nothing outside
     * `/api/topics` is sent. The status and body come back whole
     * ([Topics.Reply]): a 202 (a card was raised), a 404 the PC sent itself
     * ("that topic is not there any more") and a 404 from a PC without the
     * routes all read differently. Carries the pairing token and
     * `X-Jarvis-Client: hud` like every call ([authed]); neither is logged.
     */
    suspend fun topicsCall(path: String, json: String?): ApiResult<Topics.Reply> =
        withContext(Dispatchers.IO) {
            if (path != Topics.TOPICS_PATH && !path.startsWith(Topics.TOPICS_PATH + "/") &&
                !path.startsWith(Topics.TOPICS_PATH + "?")
            ) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a topics route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val builder = Request.Builder().url(target)
            if (json == null) {
                builder.get()
            } else {
                builder.post(json.toRequestBody("application/json".toMediaType()))
            }
            val req = builder.authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Topics.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * "Inbox tidy by voice" (docs/JARVIS-API.md section 95): the status (a
     * GET of [InboxTidy.PATH] - counts and the PC's own words, never a sender
     * or a subject) or Undo (a POST of an empty object to
     * [InboxTidy.UNDO_PATH], no card). Nothing else is sent: the tidy itself
     * is asked for in chat, and the PC raises the one approval card. The
     * status and body come back whole ([InboxTidy.Reply]): a 404 the PC sent
     * itself and a 404 from a PC without the routes read differently.
     */
    suspend fun inboxTidyCall(undo: Boolean): ApiResult<InboxTidy.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(if (undo) InboxTidy.UNDO_PATH else InboxTidy.PATH)
                ?: return@withContext ApiResult.Failed(noAddress())
            val builder = Request.Builder().url(target)
            if (undo) {
                builder.post("{}".toRequestBody("application/json".toMediaType()))
            } else {
                builder.get()
            }
            val req = builder.authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(InboxTidy.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * Projects (docs/JARVIS-API.md section 88): a read (`json` null, a GET)
     * or ONE change (a POST of `json`). The path comes from [Projects] -
     * [Projects.PATH], [Projects.projectPath], [Projects.benchPath] or
     * [Projects.writePath] - and nothing outside `/api/projects` is sent.
     * The status and body come back whole ([Projects.Reply]): a 404 that
     * says "no such project" and a 404 from a PC without Projects read
     * differently, and a 403 that carries `pc_only` is the PC saying "on the
     * PC only", not a bad token.
     */
    suspend fun projectsCall(path: String, json: String?): ApiResult<Projects.Reply> =
        withContext(Dispatchers.IO) {
            if (path != Projects.PATH && !path.startsWith(Projects.PATH + "/")) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a projects route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val builder = Request.Builder().url(target)
            if (json == null) {
                builder.get()
            } else {
                builder.post(json.toRequestBody("application/json".toMediaType()))
            }
            val req = builder.authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    val pcOnly = (obj?.get("pc_only") as? JsonPrimitive)?.booleanOrNull == true
                    if (resp.code == 401 || (resp.code == 403 && !pcOnly)) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Projects.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * The activity heatmap (docs/JARVIS-API.md section 105.1): a GET of
     * `/api/progress/activity`, [weeks] kept to 4..26. The status and body come
     * back whole ([Progress.Reply]) - a 404 from a PC without the route means
     * "draw nothing". A read; nothing is kept.
     */
    suspend fun progressActivity(weeks: Int): ApiResult<Progress.Reply> =
        progressCall("/api/progress/activity?weeks=" + weeks.coerceIn(4, 26), null)

    /** The balance chart and its picker (section 105.2): a GET of `/api/progress/balance`. */
    suspend fun progressBalance(): ApiResult<Progress.Reply> =
        progressCall("/api/progress/balance", null)

    /**
     * Replaces the balance chart's areas (section 105.3): a POST of
     * `/api/progress/balance` with [Progress.saveBody]. No card. A refusal comes
     * back as a 400 whose sentence is shown as sent.
     */
    suspend fun progressBalanceSave(json: String): ApiResult<Progress.Reply> =
        progressCall("/api/progress/balance", json)

    private suspend fun progressCall(path: String, json: String?): ApiResult<Progress.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val builder = Request.Builder().url(target)
            if (json == null) {
                builder.get()
            } else {
                builder.post(json.toRequestBody("application/json".toMediaType()))
            }
            val req = builder.authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Progress.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `POST /api/memory/shared`: tag or untag ONE fact "Between us" (the
     * owner's decision, 2026-09-27). The status and body come back whole
     * ([MemoryShared.Reply]), like [pinFact]: a 404 that says "no such
     * fact" and a 404 from a PC without the route must read differently, and
     * a 409 carries the PC's own sentence. [MemoryShared.said] reads it.
     */
    suspend fun setShared(id: Long, shared: Boolean): ApiResult<MemoryShared.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(MemoryShared.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = MemoryShared.body(id, shared).toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(MemoryShared.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * A POST whose answer's shape is not written down - read by
     * [DesktopWrite.classify], which uses no field it has not seen the
     * server's other routes use.
     */
    private suspend fun postWrite(path: String, json: String): ApiResult<DesktopWrite.Outcome> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    DesktopWrite.classify(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    private suspend fun postForJob(path: String, json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
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
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    // ----------------------------------------------------- chat history ----
    // docs/JARVIS-API.md section 18 (2026-09-24). See [ChatLog] for the
    // shapes, the words and the rules; these only carry them.

    /** `GET /api/history`: the switch and one page of conversations, newest first. */
    suspend fun history(before: Long? = null, kind: String? = null, tag: String? = null): ApiResult<JsonObject> =
        probe(ChatLog.listPath(before, kind = kind, tag = tag))

    /**
     * `GET /api/history/tags` (docs/CHAT-TAGS-DESIGN.md section 10): the
     * owner's tags with a count each. A read; a PC without tags answers 404,
     * which comes back as [ApiError.NotFound].
     */
    suspend fun historyTags(): ApiResult<JsonObject> = probe("/api/history/tags")

    /**
     * `POST /api/history/tags` (add, rename, style, move, delete) or
     * `POST /api/history/tag` (file one chat): the status and body come back
     * whole, so a refusal ({"ok": false, "error", "message"}) reaches the
     * owner as the PC wrote it. [path] is one of the two, nothing else is
     * sent. A 404 without `ok` in the body is a PC without the routes.
     */
    suspend fun tagsPost(path: String, json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            if (path != ChatTags.TAGS_PATH && path != ChatTags.TAG_PATH) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a tags route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    when {
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 && obj?.containsKey("ok") != true -> ApiResult.Failed(ApiError.NotFound)
                        obj != null -> ApiResult.Ok(resp.code to obj)
                        resp.isSuccessful -> ApiResult.Ok(resp.code to null)
                        resp.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, ""))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `POST /api/history/fork` (docs/JARVIS-API.md section 110): [json] is
     * [ChatFork.body], exactly `{"id", "upto"}`. The status and body come back
     * whole, so a refusal ({"ok": false, "error", "message"}) reaches the owner
     * as the PC wrote it. Sent with the pairing token and `X-Jarvis-Client:
     * hud` like every call ([authed]); the token is never logged. A 404
     * without `ok` in the body is a PC without the route.
     */
    suspend fun forkPost(json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            val target = url("/api/history/fork") ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    when {
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 && obj?.containsKey("ok") != true -> ApiResult.Failed(ApiError.NotFound)
                        obj != null -> ApiResult.Ok(resp.code to obj)
                        resp.isSuccessful -> ApiResult.Ok(resp.code to null)
                        resp.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, ""))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `POST /api/history/mark` ("New section here", docs/JARVIS-API.md section
     * 106): [json] is [ChatMark.body], exactly `{"id", "idx", "on"}`. The
     * status and body come back whole so a refusal reaches the owner as the PC
     * wrote it. Same shape and rules as [forkPost]; the token is never logged.
     */
    suspend fun markPost(json: String): ApiResult<Pair<Int, JsonObject?>> = historyWrite(ChatMark.MARK_PATH, json)

    /**
     * `GET /api/history/tags/suggest` (section 104): a read of the "Suggest
     * tags overnight" switch. Never held on a stale link. A 404 is a PC
     * without the route.
     */
    suspend fun tagSuggestState(): ApiResult<JsonObject> = probe(TagSuggest.PATH)

    /** `POST /api/history/tags/suggest`: [json] is [TagSuggest.body], exactly `{"enabled": bool}`. */
    suspend fun tagSuggestPost(json: String): ApiResult<Pair<Int, JsonObject?>> = historyWrite(TagSuggest.PATH, json)

    /** One JSON POST to a History route, the answer whole (status and body), like [forkPost]. */
    private suspend fun historyWrite(path: String, json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    when {
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 && obj?.containsKey("ok") != true -> ApiResult.Failed(ApiError.NotFound)
                        obj != null -> ApiResult.Ok(resp.code to obj)
                        resp.isSuccessful -> ApiResult.Ok(resp.code to null)
                        resp.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, ""))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/memory/fact-chat?id=` (the chat audit, 2026-09-28): which chat
     * a fact came from - its title and when - so "Also delete the chat it
     * came from" names it first. A read; it deletes nothing.
     */
    suspend fun factChat(path: String): ApiResult<JsonObject> = probe(path)

    /** `GET /api/history/conversation`: one conversation, read-only. 404 when it is gone. */
    suspend fun historyConversation(id: String): ApiResult<JsonObject> = probe(ChatLog.conversationPath(id))

    /**
     * `GET /api/history/search` (section 71): the kept conversations whose
     * words hold every search word, with a snippet each. The PC opens each
     * kept turn in memory for this one search and keeps nothing; neither
     * does this. [path] is [ChatLog.searchPath]'s.
     */
    suspend fun historySearch(path: String): ApiResult<JsonObject> = probe(path)

    /**
     * `GET /api/memory/conversation-facts` (section 79, 2026-09-28): the facts
     * still in use ONE conversation taught, for History's Delete to offer
     * forgetting them. A read; nothing is forgotten here. [path] is
     * [ChatLog.factsPath]'s.
     */
    suspend fun conversationFacts(path: String): ApiResult<JsonObject> = probe(path)

    /**
     * `POST /api/history/delete`: ONE conversation. No route deletes them
     * all, on purpose. A 404 - already gone - comes back as
     * [ApiError.NotFound] whatever its body says ([ChatLog.deleteSaid]).
     */
    suspend fun deleteHistory(id: String): ApiResult<JsonObject> =
        postForJob(ChatLog.DELETE_PATH, ChatLog.deleteBody(id))

    /** The switch. ON answers 202 waiting while its approval card is up; OFF is immediate. */
    suspend fun setHistory(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(ChatLog.SETTINGS_PATH, ChatLog.enabledBody(on))

    /** How long conversations are kept. The whole answer comes back: it says how many went. */
    suspend fun setHistoryKeepDays(body: String): ApiResult<JsonObject> =
        postForJob(ChatLog.SETTINGS_PATH, body)

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
                noAddress(),
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
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * Moving one of the second card's own switches onto a third, capable
     * graphics card, or moving it back off (2026-09-28). Assigning a
     * feature id raises one approval card and changes nothing until it is
     * approved; `assign = null` unassigns at once. See
     * [SecondCard.classifyPost] for which answers come back as sentences.
     */
    suspend fun setThirdCard(assign: String?): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(SecondCard.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = SecondCard.postThirdBody(assign)
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    SecondCard.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * "When to suggest the bigger model" - one signal on or off. NO approval
     * card either way (see [SecondCard.Suggest]'s own doc): re-read
     * [secondCard] to show the new state, the same as [setSecondCard].
     */
    suspend fun setSecondCardSuggest(signal: String, enabled: Boolean): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(SecondCard.SUGGEST_PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = SecondCard.postSuggestBody(signal, enabled)
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    SecondCard.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    // --------------------------------------------------------- hardware ----

    /**
     * `GET /api/search` - web search's five providers with the PC's own "why
     * use this one" lines, which is chosen, and its settings ([WebSearch.parse]).
     * A read. A 404 is an older backend ([WebSearch.missing]).
     */
    suspend fun webSearch(): ApiResult<JsonObject> = probe(WebSearch.PATH)

    /**
     * `GET /api/reach` - "What Jarvis can reach": every way Jarvis can reach
     * something outside itself, written by the PC from its settings
     * ([Reach.parse]). A read. A 404 is an older backend ([Reach.missing]).
     */
    suspend fun reach(): ApiResult<JsonObject> = probe(Reach.PATH)

    /**
     * `GET /api/backup` - "Backups": read-only on the phone
     * ([Backup.parse]); the full flow (choosing a folder, backing up,
     * restoring) is the PC's alone. A read. A 404 is an older backend
     * ([Backup.missing]).
     */
    suspend fun backup(): ApiResult<JsonObject> = probe(Backup.PATH)

    /**
     * `GET /api/asks_first` - "What asks first": every action and whether it
     * asks, in the PC's words ([AsksFirst.parse]). A read. A 404 is an older
     * backend ([AsksFirst.missing]).
     */
    suspend fun asksFirst(): ApiResult<JsonObject> = probe(AsksFirst.PATH)

    /**
     * `POST /api/asks_first/tier {"action", "ask": true}` - make ONE action of
     * the short safe list ask first. At once, no card. The phone sends only
     * this direction: loosening is the PC's alone ([AsksFirst]).
     */
    suspend fun makeAskFirst(action: String): ApiResult<DesktopWrite.Outcome> {
        val body = AsksFirst.stricterBody(action)
            ?: return ApiResult.Failed(ApiError.Unreachable("That cannot be changed from the phone."))
        return postWrite(AsksFirst.TIER_PATH, body)
    }

    /**
     * `POST /api/asks_first/lights {"enabled"}` - "Lights, plugs and fans
     * without a card". OFF is done at once; ON is 202 while ONE approval card
     * waits on the PC.
     */
    suspend fun setLightsWithoutCard(on: Boolean): ApiResult<DesktopWrite.Outcome> =
        postWrite(AsksFirst.LIGHTS_PATH, AsksFirst.lightsBody(on))

    /**
     * `POST /api/asks_first/tier {"action": "lockdown", "ask": true}` - turn
     * Lockdown ON (2026-09-28). At once, no card. The phone never sends the
     * other direction: turning it off is the PC's alone ([AsksFirst]).
     */
    suspend fun lockdownOn(): ApiResult<DesktopWrite.Outcome> =
        postWrite(AsksFirst.TIER_PATH, AsksFirst.lockdownBody())

    /** `GET /api/media` - what is playing on the PC, in its own sentence ([PcMedia]). */
    suspend fun pcMedia(): ApiResult<JsonObject> = probeKeeping503(PcMedia.PATH)

    /**
     * `POST /api/media/control {"action"}` - ONE of play, pause, next,
     * previous ([PcMedia]). No card. The PC answers its own sentence on a
     * 200 and on a 503 ("Nothing seems to be playing right now."), so both
     * come back as [ApiResult.Ok] with that body; anything else fails.
     */
    suspend fun pcMediaControl(action: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val json = PcMedia.body(action)
                ?: return@withContext ApiResult.Failed(ApiError.Unreachable("That is not a media button."))
            val target = url(PcMedia.CONTROL_PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    when {
                        (resp.isSuccessful || resp.code == 503) && PcMedia.said(obj) != null ->
                            ApiResult.Ok(obj!!)
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 -> ApiResult.Failed(ApiError.NotFound)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, text.take(200)))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/email/sending` - whether sending email is set up, from which
     * address and through which server, in the PC's own words
     * ([EmailSending.parse]). A read; never the password. A 404 or 503 is a
     * PC without it ([EmailSending.missing]).
     */
    suspend fun emailSending(): ApiResult<JsonObject> = probe(EmailSending.PATH)

    /**
     * `GET /api/folders` - "Folders Jarvis may look in": the list, in the PC's
     * own words ([Folders.parse]). A read. A 404 is a PC without it
     * ([Folders.missing]).
     */
    suspend fun folders(): ApiResult<JsonObject> = probe(Folders.PATH)

    /**
     * `POST /api/folders/remove {"path"}` - take ONE folder off the list. At
     * once, no card. The phone never adds one: that is the PC's alone.
     */
    suspend fun removeFolder(path: String): ApiResult<DesktopWrite.Outcome> =
        postWrite(Folders.REMOVE_PATH, Folders.removeBody(path))

    /**
     * `GET /api/focus`: the focus session - its countdown, booleans and counts
     * and the last report card ([Focus.parse]). Never what was in front on
     * the PC: the PC does not send it. A read.
     */
    suspend fun focus(): ApiResult<JsonObject> = probe(Focus.PATH)

    /**
     * `POST /api/focus/start` or `/api/focus/act`, with a body made by
     * [Focus.startBody] or [Focus.actBody]. Any other path is refused here,
     * before anything is sent. The status and body come back whole
     * ([Focus.Reply]): a 409 carries the PC's own sentence.
     */
    suspend fun focusWrite(path: String, json: String): ApiResult<Focus.Reply> =
        withContext(Dispatchers.IO) {
            if (path != Focus.START_PATH && path != Focus.ACT_PATH) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a focus route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Focus.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/voice/live`: the Jarvis Live session - fixed words and
     * numbers only, never anything said ([com.jarvis.client.voice.LiveRules]).
     * A read: never held.
     */
    suspend fun liveStatus(): ApiResult<JsonObject> = probe(LIVE_PATH)

    /**
     * `POST /api/voice/live` with a body made by
     * [com.jarvis.client.voice.LiveRules] (`startBody`, `stopBody`...). The
     * code and body come back whole: a 409 carries the PC's own sentence
     * ("Jarvis Live needs your voice trained first...").
     */
    suspend fun liveWrite(json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            val target = url(LIVE_PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    when (resp.code) {
                        401, 403 -> ApiResult.Failed(ApiError.BadToken)
                        404 -> ApiResult.Failed(ApiError.NotFound)
                        else -> ApiResult.Ok(resp.code to obj)
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/chatbot/status`, for the conversation [id] names or, with
     * none, the latest one still going ([Chatbot.parse]) - and likewise the
     * comparison [compare] names ("Ask several and compare"). A read.
     */
    suspend fun chatbotStatus(id: String?, compare: String? = null): ApiResult<JsonObject> =
        probe(
            when {
                compare != null && Chatbot.validCompareId(compare) ->
                    "${Chatbot.STATUS_PATH}?compare=$compare"
                id != null && Chatbot.validId(id) -> "${Chatbot.STATUS_PATH}?id=$id"
                else -> Chatbot.STATUS_PATH
            },
        )

    /**
     * `POST /api/chatbot/start`, `/stop`, `/limits`, `/compare/start` or
     * `/compare/stop`, with a body made by [Chatbot.startBody],
     * [Chatbot.stopBody], [Chatbot.limitsBody], [Chatbot.compareBody] or
     * [Chatbot.compareStopBody]. Any
     * other path is refused here, before anything is sent. The status and
     * body come back whole ([Chatbot.Reply]): a 400 or 409 carries the PC's
     * own sentence (why a goal cannot be sent, another conversation going).
     */
    suspend fun chatbotWrite(path: String, json: String): ApiResult<Chatbot.Reply> =
        withContext(Dispatchers.IO) {
            if (path !in Chatbot.WRITE_PATHS) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a chatbot route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Chatbot.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/chatbot/status?support=`, for the support chat [id] names or,
     * with none, the latest one still going ([Support.parse]). A read.
     */
    suspend fun supportStatus(id: String?): ApiResult<JsonObject> =
        probe(if (id != null && Support.validId(id)) "${Support.STATUS_PATH}?support=$id" else Support.STATUS_PATH)

    /**
     * `POST /api/chatbot/support/start`, `/stop`, `/takeover` or `/answer`,
     * with a body made by [Support.startBody], [Support.idBody] or
     * [Support.answerBody]. Any other path is refused here, before anything
     * is sent. The status and body come back whole ([Chatbot.Reply]): a 400
     * or 409 carries the PC's own sentence.
     */
    suspend fun supportWrite(path: String, json: String): ApiResult<Chatbot.Reply> {
        if (path !in Support.WRITE_PATHS) {
            return ApiResult.Failed(ApiError.Malformed("not a support chat route"))
        }
        return rawPost(path, json)
    }

    /**
     * "Solve it here" (JARVIS-API §87.8): `POST /api/chatbot/handoff/start`,
     * `/input` or `/end`, with a body made by [Handoff.startBody],
     * [Handoff.tapBody] and the rest, or [Handoff.endBody]. Any other path is
     * refused here, before anything is sent. The status and body come back
     * whole: a 410 says the hand-off ended, and why.
     */
    suspend fun handoffWrite(path: String, json: String): ApiResult<Chatbot.Reply> {
        if (path !in Handoff.WRITE_PATHS) {
            return ApiResult.Failed(ApiError.Malformed("not a hand-off route"))
        }
        return rawPost(path, json)
    }

    /**
     * `GET /api/chatbot/handoff/frame?h=` - ONE picture of the paused browser
     * window, as the PC's JSON (a base64 JPEG). Held in memory by the screen
     * that asked, never written anywhere. The status and body come back whole
     * (a 429 "too soon", a 410 "ended").
     */
    suspend fun handoffFrame(h: String): ApiResult<Chatbot.Reply> =
        withContext(Dispatchers.IO) {
            if (!Handoff.validHid(h)) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a hand-off"))
            }
            val target = url("${Handoff.FRAME_PATH}?h=$h") ?: return@withContext ApiResult.Failed(noAddress())
            val req = Request.Builder().url(target).get().authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    when (resp.code) {
                        401, 403 -> ApiResult.Failed(ApiError.BadToken)
                        404 -> ApiResult.Failed(ApiError.NotFound)
                        else -> ApiResult.Ok(Chatbot.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/form-review/picture?id=` - the screenshot of a web form Jarvis
     * filled in, for the card that asks to submit it (FormReview). A read: not
     * held on a stale link. The token and the base64 are never logged. A 404
     * (the card is decided or gone) comes back as [ApiError.NotFound].
     */
    suspend fun formPicture(id: String): ApiResult<Chatbot.Reply> =
        withContext(Dispatchers.IO) {
            val path = FormReview.pathFor(id)
                ?: return@withContext ApiResult.Failed(ApiError.Malformed("not a form picture"))
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val req = Request.Builder().url(target).get().authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    when (resp.code) {
                        401, 403 -> ApiResult.Failed(ApiError.BadToken)
                        404 -> ApiResult.Failed(ApiError.NotFound)
                        else -> ApiResult.Ok(Chatbot.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /** One POST whose status and body come back whole - for [supportWrite]. */
    private suspend fun rawPost(path: String, json: String): ApiResult<Chatbot.Reply> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    if (resp.code == 401 || resp.code == 403) {
                        ApiResult.Failed(ApiError.BadToken)
                    } else {
                        ApiResult.Ok(Chatbot.Reply(resp.code, obj))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /** A test search waits for the provider (up to 15 seconds on the PC). */
    private val webSearchTestCall: OkHttpClient by lazy {
        client.newBuilder()
            .readTimeout(40, TimeUnit.SECONDS)
            .callTimeout(45, TimeUnit.SECONDS)
            .build()
    }

    /**
     * One of web search's two POSTs: ONE setting ([WebSearch.SETTINGS_PATH],
     * a body made by [WebSearch.providerBody], [WebSearch.addressBody],
     * [WebSearch.askBody] or [WebSearch.enabledBody]) or a test search ([WebSearch.TEST_PATH]). Anything
     * else is refused here, before anything is sent - there is no route for a
     * key, and this phone never sends one (CLAUDE.md rule 3).
     */
    suspend fun webSearchPost(path: String, json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            if (path != WebSearch.SETTINGS_PATH && path != WebSearch.TEST_PATH) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a web search route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            val caller = if (path == WebSearch.TEST_PATH) webSearchTestCall else shortCall
            runCatching {
                caller.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    WebSearch.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/manner` - "How Jarvis talks": warm and brief, or plain, with
     * the PC's own words for both ([Manner.parse]). A read.
     */
    suspend fun manner(): ApiResult<JsonObject> = probe(Manner.PATH)

    /**
     * `POST /api/manner` with ONE change ([Manner.body]): at once, no card
     * either way - it changes only how answers are worded. Nothing but a
     * body [Manner.body] made is sent.
     */
    suspend fun mannerPost(json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(Manner.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    WebSearch.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/thinking` - Per-model thinking levels (Section 5.5; [Thinking.parse]). A read.
     */
    suspend fun thinking(): ApiResult<JsonObject> = probe(Thinking.PATH)

    /**
     * `POST /api/thinking` with ONE change ([Thinking.bodyString]): at once, no card
     * either way.
     */
    suspend fun thinkingPost(json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(Thinking.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    WebSearch.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/sky` - the sun, moon and weather behind the animal faces
     * ([SkySettings.parse]): whether they show, the town as the PC's list
     * names it and its position rounded to 0.1 degree, the weather now as
     * five numbers, and the PC's own words. A read; the PC reads the weather
     * (at most every 20 minutes) only while an app asks.
     */
    suspend fun sky(): ApiResult<JsonObject> = probe(SkySettings.PATH)

    /**
     * `POST /api/sky` with ONE change made by [SkySettings] (show on or off,
     * forget the town, a weather source) - never a town: that is typed on the
     * PC only. Open-Meteo ON approves nothing here: the PC raises ONE card.
     */
    suspend fun skyPost(json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(SkySettings.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    WebSearch.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/animal` - "Keep the animal still" and the animal's behaviour
     * switches, shared with the desktop, with the PC's own words
     * ([AnimalOptions.parse]). A read. 404: an older PC.
     */
    suspend fun animal(): ApiResult<JsonObject> = probe(AnimalOptions.PATH)

    /**
     * `POST /api/animal` with ONE change made by [AnimalOptions.body]. No card
     * either way - these only change how the animal moves.
     */
    suspend fun animalPost(json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(AnimalOptions.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    WebSearch.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `GET /api/hardware` - the cards, what runs now, the three setups the PC
     * worked out for its own cards ([Hardware.parse]). Reads only. A 404 is
     * an older backend and a 503 a module that did not load.
     */
    suspend fun hardware(): ApiResult<JsonObject> = probe(Hardware.PATH)

    /**
     * `GET /api/pc/help` (section 84) - five plain answers about the PC
     * ([PcHelp.parse]). Reads only. A 404 is an older backend, a 503 one
     * whose jarvis_pc_help.py did not load.
     */
    suspend fun pcHelp(): ApiResult<JsonObject> = probe(PcHelp.PATH)

    /**
     * `GET /api/tutorials` (section 114) - one catalogue for both apps and
     * where the owner has read to ([Tutorials.parse]). Reads only: a 404 is an
     * older backend, and nothing here is held on a stale link.
     */
    suspend fun tutorials(): ApiResult<JsonObject> = probe(Tutorials.PATH)

    /** `GET /api/faq` (section 114) - the questions and answers, in the PC's own order. */
    suspend fun faq(): ApiResult<JsonObject> = probe(Tutorials.FAQ_PATH)

    /**
     * `POST /api/tutorials/progress` (section 114) - record where the owner has
     * read to. NO card and NOT held while the event stream is stale: it is the
     * owner marking their own reading and it acts on nothing.
     */
    suspend fun markTutorial(bodyJson: String): ApiResult<JsonObject> =
        postForJob(Tutorials.PROGRESS_PATH, bodyJson)

    /**
     * One of the hardware POSTs: choosing a setup ([Hardware.APPLY_PATH]),
     * measuring ([Hardware.MEASURE_PATH]), or ONE step of the chosen setup -
     * a route read from the PC's own answer, one of [Hardware.STEP_ROUTES]
     * ([Hardware.stepRequest]). Anything else is refused here, before
     * anything is sent. Each step raises its own approval card on the PC; a
     * success never means it is done - re-read [hardware] for that.
     */
    suspend fun hardwarePost(path: String, json: String): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            if (path != Hardware.APPLY_PATH && path != Hardware.MEASURE_PATH &&
                path !in Hardware.STEP_ROUTES
            ) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a hardware route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    Hardware.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    // --------------------------------------------------------- big model ----

    /**
     * `GET /api/big-model` - what the PC found for the big model (slow) and
     * each switch's state ([BigModel.parse]). Starts nothing on the PC. A 404
     * is an older backend and a 503 a module that did not load;
     * [BigModel.readOf] turns both into sentences.
     */
    suspend fun bigModel(): ApiResult<JsonObject> = probe(BigModel.PATH)

    /**
     * One big-model switch on or off: `{"switch": ..., "enabled": ...}`. ON
     * raises one approval card on the PC and changes nothing until it is
     * approved; OFF is immediate. So a success never means "it is on" -
     * re-read [bigModel] for that. [BigModel.classifyPost] says which answers
     * come back as sentences.
     */
    suspend fun setBigModel(switch: String, enabled: Boolean): ApiResult<JsonObject> =
        withContext(Dispatchers.IO) {
            val target = url(BigModel.PATH) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = BigModel.postBody(switch, enabled)
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }
                        .getOrNull()
                    BigModel.classifyPost(resp.code, obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /** `GET /api/deep` - the deep questions and their answers, newest first ([BigModel.parseDeep]). */
    suspend fun deep(): ApiResult<JsonObject> = probe(BigModel.DEEP_PATH)

    /**
     * Queues one deep question. Answers 202 with the job, or a refusal the
     * PC explained (`state: "refused"` with `error`) - both as
     * [ApiResult.Ok], for [BigModel.askReply]. No approval card per
     * question: the switch was approved with one.
     */
    suspend fun deepAsk(question: String): ApiResult<JsonObject> {
        val body = BigModel.askBody(question)
            ?: return ApiResult.Failed(ApiError.Malformed("the question is empty"))
        return postForJob(BigModel.ASK_PATH, body)
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

    /**
     * `POST /api/approve`. With a [signature] (a risky approval from a phone
     * that has signed approvals on, docs/PAIRING-DESIGN.md §11) the body
     * carries it. A 403 whose body names one of the three signature refusals
     * is kept in [ApprovalRefusal] for [com.jarvis.client.JarvisRuntime.decide]
     * to explain, so it is not taken for a refused key.
     */
    suspend fun approve(id: String, signature: SignedApproval.Signature? = null): ApiResult<Unit> =
        withContext(Dispatchers.IO) {
            ApprovalRefusal.clear()
            val target = url(SignedApproval.APPROVE_PATH) ?: return@withContext ApiResult.Failed(noAddress())
            val body = SignedApproval.approveBody(id, signature).toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use {
                    when {
                        it.isSuccessful -> ApiResult.Ok(Unit)
                        it.code == 409 -> ApiResult.Failed(ApiError.AlreadyHandled)
                        else -> {
                            if (it.code == 403) {
                                ApprovalRefusal.note(runCatching { it.peekBody(2_048L).string() }.getOrNull())
                            }
                            ApiResult.Failed(errorFor(it))
                        }
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * `POST /api/approve/challenge` or `/api/devices/approval-key`: the status
     * and the body come back together ([SignedApproval.challengeAnswer],
     * [SignedApproval.registerAnswer]). A 401 is a refused key. Neither the
     * request nor the answer is logged: a nonce and a public key are in them.
     */
    suspend fun approvalPost(path: String, json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            if (path != SignedApproval.KEY_PATH && path != SignedApproval.CHALLENGE_PATH) {
                return@withContext ApiResult.Failed(ApiError.Malformed("not a signed-approval route"))
            }
            val target = url(path) ?: return@withContext ApiResult.Failed(noAddress())
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                shortCall.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    if (resp.code == 401) ApiResult.Failed(ApiError.BadToken) else ApiResult.Ok(resp.code to obj)
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

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
     * Answers the daily overnight-tidy card, and turns the tidy off again
     * (since 2026-09-28 it runs: review cards only, backend/jarvis_tidy.py) - see
     * `BrainSnapshot.memory`'s own `setup.sleep_time_offer`. Each of its
     * three actions sends exactly one field: "enable" [enabled], "stop
     * asking" [remind] false, and "not now" [notNow] (since 2026-09-25,
     * jarvis_backoff.py: the PC then keeps the offer quiet for a day, then
     * a week, then a month; an older PC answers it with nothing written).
     * The server reports a write that failed to persist as a non-2xx status,
     * same as every other write here, so no response body needs reading.
     */
    suspend fun setSleepTime(
        enabled: Boolean? = null,
        remind: Boolean? = null,
        notNow: Boolean = false,
    ): ApiResult<Unit> {
        val fields = buildList {
            enabled?.let { add(""""enabled":$it""") }
            remind?.let { add(""""remind":$it""") }
            if (notNow && enabled == null && remind == null) add(""""not_now":true""")
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
                noAddress(),
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
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
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
            noAddress(),
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
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
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
        voiceStatusRead().map { it.first }

    /**
     * `/api/voice/status`, read ONCE into both halves: the [VoiceStatus]
     * the talk button has always read, and the stricter voice check
     * ([VoiceStrict.View] - the two settings, training in rounds, the
     * repeat numbers), which is read field by field so that nothing in it
     * can hide the talk button. See [VoiceStrict.read].
     */
    suspend fun voiceStatusRead(): ApiResult<Pair<VoiceStatus, VoiceStrict.View>> =
        when (val r = probe("/api/voice/status")) {
            is ApiResult.Ok -> VoiceStrict.read(r.value)
            is ApiResult.Failed -> r
        }

    /**
     * `POST /api/voice/enroll` with a body built by [VoiceStrict] or
     * [com.jarvis.client.voice.VoiceRounds]: a training round, a cancel, a
     * setting or the guided test. Every explained answer comes back as an
     * [VoiceStrict.Answer] - the refusals are sentences for the owner.
     * Nothing here is logged: a round's body is the owner's voice.
     */
    suspend fun voiceEnroll(json: String): ApiResult<VoiceStrict.Answer> =
        postVoice("/api/voice/enroll", json).map { (code, body) -> VoiceStrict.answer(code, body) }

    /** `GET /api/voice/voices` - custom voices. Loads nothing on the PC. */
    suspend fun customVoices(): ApiResult<JsonObject> = probe(CustomVoices.PATH)

    /**
     * One of the custom-voice POSTs ([CustomVoices.CREATE_PATH] and the
     * rest). A create carries a recording of up to 2.9 MB, so this is the
     * general client, not the short one - and its body is never logged.
     */
    suspend fun customVoicePost(path: String, json: String): ApiResult<CustomVoices.Answer> =
        postVoice(path, json).map { (code, body) -> CustomVoices.answer(code, body) }

    /**
     * "Try it" for one animal's voice ([CustomVoices.ANIMAL_TRY_PATH]): the
     * PC says one fixed line of its own in that voice and sends the WAV,
     * like `/api/voice/say`. A refusal (400/503 with `error`) is the PC's
     * own sentence; a 404 is a PC too old to have it. Nothing is logged.
     */
    suspend fun voiceAnimalTry(face: String): ApiResult<CustomVoices.Tried> =
        voiceSound(CustomVoices.ANIMAL_TRY_PATH, CustomVoices.animalTryBody(face))

    /**
     * "Hear it" for one built-in voice ([CustomVoices.SAMPLE_PATH]): the PC
     * says one fixed line of its own in that voice, by name, and sends the
     * WAV - exactly like [voiceAnimalTry], and it changes nothing on the PC.
     */
    suspend fun voiceSample(voice: String): ApiResult<CustomVoices.Tried> =
        voiceSound(CustomVoices.SAMPLE_PATH, CustomVoices.sampleBody(voice))

    /** The one request "Try it" and "Hear it" both make: a POST that answers a WAV or the PC's sentence. */
    private suspend fun voiceSound(path: String, json: String): ApiResult<CustomVoices.Tried> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed()
                .header("Accept", "audio/wav")
                .build()
            runCatching {
                client.newCall(req).execute().use { resp ->
                    val type = resp.header("Content-Type").orEmpty()
                    when {
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.isSuccessful && type.startsWith("audio/") -> {
                            val bytes = resp.body?.bytes()
                            if (bytes == null || bytes.isEmpty()) {
                                ApiResult.Ok(CustomVoices.Tried.Refused("Your PC sent no sound."))
                            } else {
                                ApiResult.Ok(CustomVoices.Tried.Sound(bytes))
                            }
                        }
                        else -> {
                            val text = resp.body?.string().orEmpty()
                            val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                            val why = (obj?.get("error") as? JsonPrimitive)?.takeIf { it.isString }?.content.orEmpty()
                            when {
                                resp.code == 404 && obj?.containsKey("ok") != true -> ApiResult.Failed(ApiError.NotFound)
                                why.isNotBlank() -> ApiResult.Ok(CustomVoices.Tried.Refused(CustomVoices.sentence(why)))
                                else -> ApiResult.Failed(ApiError.Server(resp.code, ""))
                            }
                        }
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * A voice POST whose refusals carry the PC's own sentence: (status,
     * body) for any answer with a JSON object in it, so a 400/409/503 with
     * `error` reaches the owner as it was written. A 404 is "this PC has no
     * such route" unless the body is the voice module's own (`ok` in it -
     * "there is no voice with that id"). 401/403 stay failures: a bad token
     * is not the PC's sentence to relay.
     */
    private suspend fun postVoice(path: String, json: String): ApiResult<Pair<Int, JsonObject?>> =
        withContext(Dispatchers.IO) {
            val target = url(path) ?: return@withContext ApiResult.Failed(
                noAddress(),
            )
            val body = json.toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(target).post(body).authed().build()
            runCatching {
                client.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    val obj = runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()
                    when {
                        resp.code == 401 || resp.code == 403 -> ApiResult.Failed(ApiError.BadToken)
                        resp.code == 404 && obj?.containsKey("ok") != true -> ApiResult.Failed(ApiError.NotFound)
                        obj != null -> ApiResult.Ok(resp.code to obj)
                        resp.isSuccessful -> ApiResult.Ok(resp.code to null)
                        resp.code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
                        else -> ApiResult.Failed(ApiError.Server(resp.code, ""))
                    }
                }
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    /**
     * One complete utterance in, one verdict out.
     *
     * The only route on this server whose body is not JSON. The audio is
     * 16 kHz 16-bit mono PCM in a WAV container, resampled on this device
     * (Recorder.kt). That is the format the server asks for (`audio_in` in
     * /api/voice/status), and the desktop sends the same since 2026-09-24.
     * The server does still accept another rate or stereo: it averages the
     * channels and hands the real rate to its speech models, which resample.
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
        waitedMs: Long? = null,
    ): ApiResult<Heard> = withContext(Dispatchers.IO) {
        // mic=phone: the PC checks the clip against this phone's own voice
        // print when there is one (a PC older than 2026-09-24 ignores it).
        // waited_ms (docs/JARVIS-API.md section 17, 2): how long it had been
        // quiet when the clip was sent - a number for the PC's delay table,
        // ignored by a PC without voice-flow.patch.
        val waited = waitedMs?.let { "&waited_ms=${it.coerceIn(0L, 60_000L)}" }.orEmpty()
        val target = url("/api/voice/utterance?source=$source&mic=$MIC_PHONE$waited") ?: return@withContext ApiResult.Failed(
            noAddress(),
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
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
    }

    /**
     * Interrupting Jarvis by talking (docs/JARVIS-API.md section 17, 1): about
     * two seconds of what the microphone heard over a reply, and ONE question
     * back - should Jarvis stop? The PC never transcribes it. Send it only
     * while Jarvis is speaking and [VoiceStatus.bargeInUsable] is true: an
     * older PC treats an unknown `source` as push-to-talk and would
     * transcribe the clip. Anything but a readable answer is "carry on"
     * ([com.jarvis.client.voice.BargeVerdict.FAILED]). The body is the
     * owner's voice, and is never logged.
     */
    suspend fun bargeIn(wav: ByteArray): com.jarvis.client.voice.BargeVerdict = withContext(Dispatchers.IO) {
        val failed = com.jarvis.client.voice.BargeVerdict.FAILED
        val target = url("/api/voice/utterance?source=$SOURCE_BARGE_IN&mic=$MIC_PHONE")
            ?: return@withContext failed
        val body = wav.toRequestBody("audio/wav".toMediaType())
        val req = Request.Builder().url(target).post(body).authed().build()
        runCatching {
            shortCall.newCall(req).execute().use {
                if (!it.isSuccessful) return@use failed
                val obj = runCatching {
                    JarvisJson.parseToJsonElement(it.body?.string().orEmpty()) as? JsonObject
                }.getOrNull()
                com.jarvis.client.voice.BargeVerdict.read(obj)
            }
        }.getOrElse { failed }
    }

    /**
     * The "One moment." clip (docs/JARVIS-API.md section 17, 3): a WAV in the
     * voice Jarvis speaks in now. Fetched when `flow.moment.key` changes, and
     * kept. A 503 is the PC's "none right now" - a failure here, not an error
     * to show: the clip is a courtesy.
     */
    suspend fun voiceMoment(): ApiResult<ByteArray> = withContext(Dispatchers.IO) {
        val target = url("/api/voice/moment") ?: return@withContext ApiResult.Failed(
            noAddress(),
        )
        val req = Request.Builder().url(target).get().authed().header("Accept", "audio/wav").build()
        runCatching {
            shortCall.newCall(req).execute().use {
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val bytes = it.body?.bytes()
                if (bytes == null || bytes.isEmpty()) {
                    ApiResult.Failed(ApiError.NotAvailable)
                } else {
                    ApiResult.Ok(bytes)
                }
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
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
            noAddress(),
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
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
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
                noAddress(),
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
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
        }

    private suspend fun postTraining(json: String): ApiResult<VoiceTrainingReply> =
        withContext(Dispatchers.IO) {
            val target = url("/api/voice/enroll") ?: return@withContext ApiResult.Failed(
                noAddress(),
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
            }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
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
     * answers to them, already trimmed to fit - sent ahead of [asking] so a
     * follow-up is understood. Only one user turn used to go, and every
     * follow-up started from nothing. See [ChatHistory] for what is kept,
     * how much, and why.
     *
     * [asking] is the new question's user message(s), each with where it
     * came from ([ChatHistory.asking]), and [conversationId] the chat it
     * belongs to - both for the PC's chat history (docs/JARVIS-API.md
     * section 18, 2026-09-24).
     */
    fun chatCall(
        asking: List<ChatHistory.UserTurn>,
        history: List<ChatHistory.Exchange> = emptyList(),
        picture: String? = null,
        conversationId: String? = null,
        interrupted: String? = null,
        temporary: Boolean = false,
        /** See [ChatHistory.requestBody]'s own doc on this same parameter. */
        cloudYes: Boolean = false,
        live: Boolean = false,
        /** The look at the phone's own screen this question carries ([ScreenLook]). */
        screen: ScreenLook.Attach? = null,
    ): Call? {
        val target = url("/api/chat") ?: return null
        val body = ChatHistory.requestBody(
            history, asking, picture, conversationId,
            interrupted = interrupted, temporary = temporary, cloudYes = cloudYes, live = live,
            screen = screen,
        )
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
            noAddress(),
        )
        val req = Request.Builder().url(target).get().authed().build()
        runCatching {
            shortCall.newCall(req).execute().use {
                if (!it.isSuccessful) return@use ApiResult.Failed(errorFor(it))
                val text = it.body?.string().orEmpty()
                parse(text, serializer, unwrap)
            }
        }.getOrElse { ApiResult.Failed(ApiError.Unreachable(it.readableMessage(), PlainErrors.networkKind(it))) }
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

        /** A Jarvis Live clip (docs/LIVE-DESIGN.md): no wake word, the voice checked first as ever. */
        const val SOURCE_LIVE = "live"

        /** Jarvis Live's one route: GET the session, POST start/stop/extend/resume/mute/unmute. */
        const val LIVE_PATH = "/api/voice/live"

        /** Interrupting by talking: "should Jarvis stop?", never transcribed (section 17). */
        const val SOURCE_BARGE_IN = "barge_in"

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
