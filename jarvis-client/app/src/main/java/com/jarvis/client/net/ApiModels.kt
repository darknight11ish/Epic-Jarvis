package com.jarvis.client.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull

/**
 * The wire shapes from JARVIS-API.md.
 *
 * Every field has a default and unknown keys are ignored, because the three
 * clients ship on different schedules and §0 is explicit that the backend must
 * not care which is calling. A required field here would turn "the desktop
 * added something" into "the phone stopped working".
 */
val JarvisJson = Json {
    ignoreUnknownKeys = true
    isLenient = true
    encodeDefaults = true
    explicitNulls = false
}

/**
 * Reads a capability entry as present-or-not.
 *
 * The doc shows both shapes: `approvals: true` and `voice: {...}`. A sub-object
 * means the capability exists and carries detail, so an empty one is the only
 * object that counts as absent. Anything unrecognised is false, which is the
 * fail-closed direction: a client that hides a feature it could have shown is a
 * smaller failure than one that offers a button that 404s.
 */
private fun JsonElement.asCapabilityFlag(): Boolean = when (this) {
    is JsonPrimitive -> booleanOrNull ?: (isString && content.isNotEmpty() && content != "false")
    is JsonObject -> isNotEmpty()
    else -> false
}

// ------------------------------------------------------------- handshake ----

@Serializable
data class VersionInfo(
    val api: Int = 0,
    val server: String = "",
    val auth: AuthInfo = AuthInfo(),
    val events: EventsInfo = EventsInfo(),
    val capabilities: JsonObject = JsonObject(emptyMap()),
) {
    /**
     * A capability reporting false means hide the UI for it, not show a button
     * that 404s (§2). Anything absent is also false: a server that predates a
     * feature does not report it at all.
     */
    fun can(name: String): Boolean = capabilities[name]?.asCapabilityFlag() ?: false

    /** The sub-object for a capability that reports detail rather than a flag. */
    fun detail(name: String): JsonObject? = capabilities[name] as? JsonObject
}

@Serializable
data class AuthInfo(
    @SerialName("token_required") val tokenRequired: Boolean = true,
    val header: String = JarvisApi.TOKEN_HEADER,
    val note: String = "",
)

@Serializable
data class EventsInfo(
    val path: String = "/api/events",
    @SerialName("resume_header") val resumeHeader: String = "Last-Event-ID",
    @SerialName("resume_query") val resumeQuery: String = "since",
)

// --------------------------------------------------------------- status ----

@Serializable
data class StatusInfo(
    val lane: String? = null,
    val model: String? = null,
    val power: String? = null,
    val activity: String? = null,
    val held: Boolean = false,
)

// ------------------------------------------------------------ approvals ----

/**
 * What happens if the human answers *wrongly* — a different question from
 * whether Jarvis had to ask at all (§4).
 */
@Serializable
data class Risk(
    /** `yes` | `hard` | `no`. */
    val reversible: String = "no",
    /** `local` | `outbound`. */
    val reach: String = "outbound",
    /**
     * The only field a gesture may branch on. Never re-derive it from the two
     * above, never cache it against an id: it is computed server-side when the
     * list is read, so refining the classification improves every pending item
     * at once — including ones queued before the refinement existed.
     */
    @SerialName("swipe_ok") val swipeOk: Boolean = false,
    /** One plain sentence. Shown either way, so a card explains rather than merely refuses. */
    val why: String = "",
    val classified: Boolean = false,
)

/**
 * Why this is being asked about at all. Usually null; when it is not, outside
 * text tried to rush the reader and the tier was raised because of it.
 */
@Serializable
data class Raised(
    val code: String = "",
    val text: String = "",
    /** The attacker's own words. Showing them is the entire point. */
    val quote: String = "",
    /** Page or document text — behind a tap, never shown unasked. */
    val context: String = "",
    /** Named, never quoted. */
    val source: String = "",
    @SerialName("from_tier") val fromTier: String = "",
    @SerialName("to_tier") val toTier: String = "",
    @SerialName("count_today") val countToday: Int = 0,
)

@Serializable
data class PendingItem(
    val id: String,
    val title: String = "Approval required",
    val summary: String = "",
    val tier: String = "ask",
    val detail: String? = null,
    val action: String? = null,
    val risk: Risk = Risk(),
    val raised: Raised? = null,
    @SerialName("expires_at_ms") val expiresAtMs: Long? = null,
) {
    /**
     * Whether a swipe may decide this item.
     *
     * `swipe_ok` and nothing else — except that an item carrying [raised] is
     * never swipeable even when the server says it would be. The point of a
     * raise is that this particular moment is not one to decide quickly in, and
     * a swipe is the gesture people make without reading.
     */
    val swipeable: Boolean get() = risk.swipeOk && raised == null
}

// -------------------------------------------------------------- digest -----

@Serializable
data class DigestItem(
    val id: String,
    val title: String = "",
    val summary: String = "",
    val kind: String = "",
    @SerialName("opens_card") val opensCard: Boolean = false,
)

// ------------------------------------------------------------ attention ----

/**
 * The interruption budget as the UI needs it: flat.
 *
 * Deliberately NOT the wire shape. `GET /api/attention` nests the budget one
 * level down and the `attention` *event* publishes the same numbers flat, so a
 * single class modelling both is a class that is wrong for one of them. It was
 * wrong for the route: every field but `pending` and `banked` sat at the top
 * level here, defaulted, and `ignoreUnknownKeys` meant the parse succeeded and
 * quietly returned 0 of 0 for ever. A budget line that always reads "0 of 0
 * spoken interruptions left today" says the budget is exhausted, which is the
 * one thing it must never say by accident.
 */
data class Attention(
    val remaining: Int = 0,
    val limit: Int = 0,
    val spent: Int = 0,
    /**
     * Non-null when the budget is zero regardless of the count — Quiet,
     * Standby, a locked session, or muted.
     */
    val blockedBy: String? = null,
    /** Its own fact, not a value of [blockedBy]. */
    val muted: Boolean = false,
    /** The notch count for the reactor's rim ring. */
    val pending: Int = 0,
    val banked: Boolean = false,
)

/** The nested wire shape of `GET /api/attention`. */
@Serializable
data class AttentionBudget(
    val limit: Int = 0,
    val spent: Int = 0,
    val remaining: Int = 0,
    @SerialName("blocked_by") val blockedBy: String? = null,
    val muted: Boolean = false,
)

@Serializable
data class AttentionResponse(
    val budget: AttentionBudget = AttentionBudget(),
    val pending: Int = 0,
    val banked: Boolean = false,
    @SerialName("digest_hour") val digestHour: Int? = null,
    @SerialName("digest_due") val digestDue: Boolean = false,
) {
    fun flatten(): Attention = Attention(
        remaining = budget.remaining,
        limit = budget.limit,
        spent = budget.spent,
        blockedBy = budget.blockedBy,
        muted = budget.muted,
        pending = pending,
        banked = banked,
    )
}

// ----------------------------------------------------------------- undo ----

@Serializable
data class UndoEntry(
    val id: String,
    val label: String = "",
    val what: String = "",
    val reversible: Boolean = false,
    /** Present when it cannot be undone. Listed anyway — see JARVIS-EXPLAINED §3. */
    val reason: String? = null,
    @SerialName("at_ms") val atMs: Long = 0,
)

@Serializable
data class JobRecord(
    val id: String,
    val label: String = "",
    val state: String = "",
    /** 0..1 where the server knows; absent for open-ended work. */
    val progress: Float? = null,
    /**
     * The permissions the job was approved with, frozen for its life. A job can
     * never gain more while it runs: approving something on Tuesday is not
     * approving it on Wednesday.
     */
    val capabilities: List<String> = emptyList(),
    val private: Boolean = false,
)

/**
 * What `/api/voice/say` came back with.
 *
 * The 503 is not a failure - the desktop's speech module is optional - but it
 * is also not permission to speak the text ourselves. Whether this device may
 * substitute its own voice is the SERVER's call, carried in
 * `client_fallback_ok`, and absent means no. It used to be assumed.
 */
sealed interface SaidAloud {
    /** The desktop synthesised it; play these samples and nothing else. */
    class Audio(val wav: ByteArray) : SaidAloud

    /**
     * The desktop has no engine. [fallbackOk] is the server's answer to "may
     * this device speak it instead?" - never defaulted to true.
     */
    data class NoEngine(val fallbackOk: Boolean, val reason: String?) : SaidAloud
}

/** A message inside its send window. The only honest "unsend" there is. */
@Serializable
data class HoldRecord(
    val handle: String,
    val label: String = "",
    @SerialName("releases_at_ms") val releasesAtMs: Long? = null,
)

// ---------------------------------------------------------------- events ---

/**
 * One frame off the SSE stream.
 *
 * An event says *something changed*, not *here is the state* (§3). The payload
 * is kept as raw JSON deliberately: every consumer re-fetches the real endpoint,
 * so parsing the body into typed state would invite treating the bus as a
 * database. `hello` and `activity` are the two exceptions, and they are read
 * with explicit accessors rather than by deserialising the whole frame.
 */
data class SseEvent(
    val id: String?,
    val kind: String,
    val data: JsonElement?,
    val retryMs: Long?,
)

@Serializable
data class HelloPayload(
    @SerialName("resumed_from") val resumedFrom: Long? = null,
    /**
     * True means this client fell off the back of the 512-event ring buffer and
     * is NOT caught up. Re-fetch everything; do not replay. A phone asleep for
     * an hour will hit this.
     */
    val stale: Boolean = false,
    val latest: Long? = null,
    @SerialName("retry_ms") val retryMs: Long? = null,
    /**
     * The current activity, because a client that connects mid-turn has no
     * other way to learn it. After a reconnect take the state from here rather
     * than assuming idle.
     */
    val activity: String? = null,
    val power: String? = null,
)
