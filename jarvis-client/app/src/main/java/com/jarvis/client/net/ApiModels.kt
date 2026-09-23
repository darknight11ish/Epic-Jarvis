package com.jarvis.client.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
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
    /**
     * What Jarvis is doing right now, in words - "Step 2/3: click 'Send'".
     *
     * Proposed by `docs/AUTONOMY-PROPOSALS.md` §3c on the desktop branch as an
     * additive sibling of `activity`: the sentence the backend's `announce()`
     * already produces per step, capped and never persisted. Optional here
     * because no backend sends it yet; absent means there is nothing to say,
     * and the phone shows nothing.
     */
    @SerialName("activity_detail") val activityDetail: String? = null,
)

// --------------------------------------------------------------- models ----

/**
 * `GET /api/models`, read the way the desktop's Brain pane reads it
 * (`brain.js renderModels`): `current` or `active` for the running model,
 * `previous` for the one a rollback returns to, `installed` as either bare
 * strings or objects with `ref`/`name`/`model`, and `offload` saying whether
 * the model is actually on the graphics card.
 *
 * Read from the raw [JsonObject] rather than through a `@Serializable` data
 * class - deliberately, matching [JarvisApi.probe]'s own reasoning: the
 * contract documents this route by one consumer's behaviour and nothing
 * else, so a typed decode would mean inventing keys, and `installed` mixes
 * bare strings with objects in the one shape that consumer actually reads.
 * A `List<JsonElement>` property has no precedent anywhere in this codebase
 * inside a class the serialization compiler plugin generates code for -
 * every other raw-JSON field here (`BrainSnapshot`'s) sits on a PLAIN data
 * class assigned to directly, never decoded - so this does the same thing
 * `BrainScreen.kt`'s own `flatten()`/`str()` helpers do: read the object by
 * hand.
 */
data class ModelsInfo(
    val currentRef: String?,
    val previous: String?,
    val entries: List<ModelEntry>,
    val offload: ModelOffload?,
    /** `speed-record.patch`'s `speed` block, or null on a backend without it. */
    val speed: ModelSpeed? = null,
) {
    companion object {
        fun from(json: JsonObject): ModelsInfo {
            val current = json.str("current") ?: json.str("active")
            val previous = json.str("previous")
            val installed = (json["installed"] as? JsonArray).orEmpty()
            val listed = installed.mapNotNull { el ->
                when (el) {
                    is JsonPrimitive -> el.content.takeIf { it.isNotBlank() }?.let { ModelEntry(it) }
                    is JsonObject -> {
                        val ref = listOf("ref", "name", "model")
                            .firstNotNullOfOrNull { k -> el.str(k) }
                        ref?.let {
                            ModelEntry(
                                ref = it,
                                sizeBytes = el.str("size")?.toLongOrNull(),
                                family = el.str("family"),
                            )
                        }
                    }
                    else -> null
                }
            }
            // Falls back to the current model alone when nothing was listed,
            // so a backend that only ever reports what is running still
            // shows one row rather than an empty section.
            val entries = listed.ifEmpty { listOfNotNull(current?.let { ModelEntry(it) }) }
            val offload = (json["offload"] as? JsonObject)?.let {
                ModelOffload(status = it.str("status"), note = it.str("note"))
            }
            val speed = ModelSpeed.from(json["speed"] as? JsonObject, current)
            return ModelsInfo(
                currentRef = current,
                previous = previous,
                entries = entries,
                offload = offload,
                speed = speed,
            )
        }

        private fun JsonObject.str(key: String): String? =
            (this[key] as? JsonPrimitive)?.content?.takeIf { it.isNotBlank() }
    }
}

data class ModelEntry(
    val ref: String,
    val sizeBytes: Long? = null,
    val family: String? = null,
)

/** Whether the model is on the GPU. `status` is `gpu` | `partial` | `cpu` | `unknown`. */
data class ModelOffload(
    val status: String? = null,
    val note: String? = null,
) {
    val bad: Boolean get() = status == "cpu" || status == "partial"
}

/**
 * How fast recent answers were - `speed-record.patch`, item 11 of
 * docs/LEARNING-RESEARCH-2026-09-23.md. Numbers only: nothing in the block is
 * conversation text. docs/JARVIS-API.md says how to show it, and this follows
 * that: one line for the running model, the backend's `note` as a warning
 * only when `slowdown.slower` is true, and `last_switch_note` word for word
 * when there has been a switch.
 */
data class ModelSpeed(
    /** "Recent answers: about 14 words a second, first word after 0.8 s." Null: no answers yet. */
    val currentLine: String?,
    /** The backend's own "got slower" sentence, or null when nothing slowed down. */
    val slowdownNote: String?,
    /** The backend's own old-vs-new sentence from the last model switch, or null. */
    val lastSwitchNote: String?,
) {
    val isEmpty: Boolean get() = currentLine == null && slowdownNote == null && lastSwitchNote == null

    companion object {
        fun from(speed: JsonObject?, current: String?): ModelSpeed? {
            if (speed == null) return null
            if ((speed["available"] as? JsonPrimitive)?.booleanOrNull == false) return null
            val byModel = speed["by_model"] as? JsonObject
            val mine = current?.let { cur ->
                (byModel?.get(cur) as? JsonObject)
                    ?: byModel?.entries?.firstOrNull { (k, _) -> sameModel(k, cur) }?.value as? JsonObject
            }
            val slower = ((speed["slowdown"] as? JsonObject)?.get("slower") as? JsonPrimitive)
                ?.booleanOrNull == true
            val switched = speed["last_switch"] is JsonObject
            val out = ModelSpeed(
                currentLine = mine?.let { line(it) },
                slowdownNote = if (slower) speed.text("note") else null,
                lastSwitchNote = if (switched) speed.text("last_switch_note") else null,
            )
            return out.takeUnless { it.isEmpty }
        }

        /** "qwen3:8b" and "qwen3:8b:latest"/"qwen3" + ":latest" name the same model. */
        private fun sameModel(a: String, b: String): Boolean =
            a.removeSuffix(":latest") == b.removeSuffix(":latest")

        private fun line(m: JsonObject): String? {
            val wps = m.num("median_words_per_s")
            val firstMs = m.num("median_first_word_ms")
            val parts = buildList {
                if (wps != null) add("about ${Math.round(wps)} words a second")
                if (firstMs != null) {
                    val tenths = Math.round(firstMs / 100.0)
                    add("first word after ${tenths / 10}.${tenths % 10} s")
                }
            }
            if (parts.isEmpty()) return null
            val n = m.num("answers")?.let { Math.round(it) }
            val over = if (n != null && n > 0) " (middle of the last $n answers)" else ""
            return "Recent answers: " + parts.joinToString(", ") + over + "."
        }

        private fun JsonObject.num(key: String): Double? =
            (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }
                ?.content?.toDoubleOrNull()?.takeIf { it.isFinite() && it >= 0.0 }

        private fun JsonObject.text(key: String): String? =
            (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.takeIf { it.isNotBlank() }
    }
}

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

/**
 * The only prose on an approval row that is safe by construction.
 *
 * The desktop generates it from two things: the action name, and whether
 * `raised` is truthy. It reads no `detail`, no `prompt`, and nothing inside
 * `raised`, so every word comes from tables on that side rather than from
 * anything a stranger wrote. That is what makes it the right text for a
 * notification, where a leak is least recoverable.
 *
 * Every other string on a `PendingItem` - `summary` included - can carry text
 * somebody else wrote. This client composed its notification body from
 * `summary` and `risk.why` before this existed, which is the hole the field
 * closes.
 *
 * Absent on an older desktop, hence nullable: the notifier falls back to what
 * it did before rather than posting nothing.
 */
@Serializable
data class Notice(
    val title: String = "",
    val body: String = "",
    /**
     * `heavy` | `normal`. Heavy is earned by any of three things on the
     * desktop side: the action cannot be undone, it leaves that machine, or
     * outside text pushed the tier up.
     *
     * Read with [PendingItem.shouldInterrupt], never on its own. The third
     * reason is set by text an attacker wrote, and this phone deliberately
     * does not let that reason alone make a sound.
     */
    val weight: String = "normal",
    @SerialName("deny_ok") val denyOk: Boolean = true,
    /**
     * Always false, and this client would ignore it if it were not: approving
     * from a notification is refused here on its own terms, not on the
     * server's say-so. See ApprovalNotifier.
     */
    @SerialName("approve_ok") val approveOk: Boolean = false,
)

/**
 * One of several complete, independently bounded plans a proposal offers.
 *
 * From `docs/AUTONOMY-PROPOSALS.md` §3a on the desktop branch. Each option is
 * a whole plan, never a checkbox that mutates one - a plan whose shape can
 * change after being shown is what "fully enumerated ahead of time" forbids.
 */
@Serializable
data class ProposalOption(
    val id: String = "",
    val label: String = "",
    val summary: String = "",
    /** `heavy` | `normal` - whether any step is irreversible or leaves the machine. */
    val weight: String = "",
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
    val notice: Notice? = null,
    @SerialName("expires_at_ms") val expiresAtMs: Long? = null,
    /**
     * Additive: absent or a single entry means the card behaves exactly as it
     * always has. Two or more mean the desktop is asking WHICH plan, and a
     * bare approve no longer names one - see [needsChoice].
     */
    val options: List<ProposalOption> = emptyList(),
) {
    /**
     * Whether approving needs an option named alongside it.
     *
     * The phone's approve route today (`/api/approve` with an id) carries no
     * option, so an item with several cannot be approved from here until the
     * decide route in AUTONOMY-PROPOSALS §3b exists. Denying needs no option
     * and stays available: refusing is always the safe direction.
     */
    val needsChoice: Boolean get() = options.size > 1

    /**
     * Whether a swipe may decide this item.
     *
     * `swipe_ok` and nothing else — except that an item carrying [raised] is
     * never swipeable even when the server says it would be. The point of a
     * raise is that this particular moment is not one to decide quickly in, and
     * a swipe is the gesture people make without reading.
     */
    val swipeable: Boolean get() = risk.swipeOk && raised == null

    /**
     * Whether this approval may make a sound and appear over what you are
     * doing, rather than waiting in the drawer to be found.
     *
     * The owner's rule, which is the desktop's `heavy` minus one of its three
     * reasons: interrupt when the action cannot be undone or when it leaves
     * the desktop, but NOT when the only thing that made it heavy is that
     * outside text tried to rush the reader.
     *
     * The reason for the exception is that the first two are facts about what
     * Jarvis is about to do and the third is a property of words a stranger
     * wrote. Honouring the third would let anyone who puts "URGENT" in an
     * email decide whether this phone interrupts its owner, and doing it
     * repeatedly is how an alert becomes background noise. A raise still
     * posts, still says something tried to hurry you, and still refuses every
     * quick gesture - see [swipeable]. It just does not shout.
     *
     * Written as "heavy unless the raise is the ONLY reason" rather than
     * "irreversible or outbound", so it fails toward interrupting. If the
     * desktop grows a fourth reason for heavy that these two fields do not
     * describe, this still makes a sound instead of silently swallowing it.
     *
     * Null notice - an older desktop - keeps the previous behaviour, which was
     * that everything interrupts. Degrading to silence on an unknown server
     * would be the wrong direction for the one notification that matters.
     */
    val shouldInterrupt: Boolean
        get() {
            val n = notice ?: return true
            if (!n.weight.equals("heavy", ignoreCase = true)) return false
            val raisedIsTheOnlyReason =
                raised != null && risk.reversible != "no" && risk.reach == "local"
            return !raisedIsTheOnlyReason
        }
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
