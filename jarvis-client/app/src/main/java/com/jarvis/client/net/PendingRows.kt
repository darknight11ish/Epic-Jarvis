package com.jarvis.client.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * What one read of `/api/pending` produced: the rows this phone could read,
 * and how many it could not.
 *
 * [skipped] is not an error to hide. A row that could not be read is still a
 * decision waiting on the desktop, so the runtime says so in words rather
 * than showing a shorter list as if it were the whole queue.
 */
data class PendingRead(val items: List<PendingItem>, val skipped: Int)

/**
 * Reads `/api/pending` rows ONE AT A TIME.
 *
 * The list used to be decoded in one go, so a single row in a shape this phone
 * did not expect - `detail` as an object where it expected a string, `raised`
 * as `true` or as a JSON string - failed the WHOLE read. Every refresh then
 * failed, the stream went stale, and the phone sat on "Could not re-read what
 * is waiting" with no way out while the desktop was fine. The backend's own
 * fixtures disagree about those shapes (`detail` is a dict in
 * backend/test_gate_egress.py and a JSON string in
 * backend/test_extraction_wiring.py), and the gate that produces them lives
 * on the owner's PC, not in this repo - so this side accepts every shape it
 * knows of, and skips-and-counts a row it still cannot read.
 */
internal fun decodePendingRows(
    rows: List<JsonElement>,
    nowMs: Long = System.currentTimeMillis(),
): PendingRead {
    val items = ArrayList<PendingItem>(rows.size)
    var skipped = 0
    for (row in rows) {
        val item = runCatching {
            normalisePendingRow(row, nowMs)
                ?.let { JarvisJson.decodeFromJsonElement(PendingItem.serializer(), it) }
        }.getOrNull()
        if (item == null) skipped++ else items += item
    }
    return PendingRead(items, skipped)
}

private val PrettyJson = Json { prettyPrint = true }

/** Keys of a `detail` object that hold the text a person should read, in order. */
private val DETAIL_TEXT_KEYS = listOf("diff", "command", "cmd", "preview", "content", "body", "text", "summary")

/**
 * One wire row, rewritten into the shape [PendingItem] decodes. Null when the
 * row has no usable id - an item that cannot be named cannot be decided.
 *
 * What it settles, each the way the desktop's `normaliseApproval`
 * (jarvis-desktop/src/jarvis-link.js) already does or safer:
 *
 * - `id`: a string, or a number turned into one.
 * - `title`: what Jarvis wants to do, from `notice.title` (built by the
 *   PC from its own tables, backend/jarvis_card_words.py) or else the PC's
 *   fallback built from the action's name ([CardWords.fallbackTitle]). The server sends
 *   no `title`; this used to default to "Approval required" on every card and
 *   on the fingerprint prompt, so the phone never said what it was asking.
 *   Never from `prompt` or `detail`: the title is also a notification's title.
 * - `summary`: what the card shows under the title - the readable part of
 *   `detail` (a command, a diff, a plan's text), else `prompt`. It can carry
 *   text somebody else wrote, so ApprovalNotifier and the widget never use it.
 * - `detail`: a string or an object, shown under "Show detail" as text -
 *   dropped when it would only repeat `summary`.
 * - `raised`: an object, or `true`, or a JSON string of an object. Anything
 *   truthy that is not an object becomes an empty raise, never "not raised":
 *   the raise is what takes an item out of every quick gesture, so an
 *   unreadable one must fail toward caution.
 * - `risk`, `notice`, `options`: kept only in the shape they are declared in.
 * - `expires_at_ms`: kept if sent (the old WebSocket server), else computed
 *   from `expires_in` (seconds left, sent by approval-expiry.patch) against
 *   this phone's clock at the moment of the read - so the two machines'
 *   clocks never have to agree.
 */
internal fun normalisePendingRow(row: JsonElement, nowMs: Long): JsonObject? {
    val obj = row as? JsonObject ?: return null
    val id = idOf(obj["id"]) ?: return null
    val out = obj.toMutableMap()
    out["id"] = JsonPrimitive(id)

    val action = textOf(obj["action"])
    if (action == null) out.remove("action") else out["action"] = JsonPrimitive(action)
    out["tier"] = JsonPrimitive(textOf(obj["tier"]) ?: "ask")

    // --- detail and summary
    val rawDetail = obj["detail"]
    val detailObj: JsonObject? = when (rawDetail) {
        is JsonObject -> rawDetail
        is JsonPrimitive -> if (rawDetail.isString) parseObject(rawDetail.content) else null
        else -> null
    }
    val detailText: String? = when {
        detailObj != null -> PrettyJson.encodeToString(JsonObject.serializer(), detailObj)
        rawDetail is JsonPrimitive && rawDetail !is JsonNull -> rawDetail.content.takeIf { it.isNotBlank() }
        rawDetail is JsonArray -> PrettyJson.encodeToString(JsonArray.serializer(), rawDetail)
        else -> null
    }
    val previewKey = detailObj?.let { d -> DETAIL_TEXT_KEYS.firstOrNull { textOf(d[it]) != null } }
    val preview: String? = when {
        detailObj != null -> previewKey?.let { textOf(detailObj[it]) }
        else -> detailText
    }
    val summary = textOf(obj["summary"]) ?: preview ?: textOf(obj["prompt"]) ?: ""
    out["summary"] = JsonPrimitive(summary)
    // Show detail only when it adds something to what the card already shows.
    val detailRepeats = preview != null && preview == summary &&
        (detailObj == null || detailObj.keys == setOf(previewKey))
    if (detailText == null || detailRepeats) out.remove("detail") else out["detail"] = JsonPrimitive(detailText)

    // --- the shapes that must be objects or arrays, or not be there at all
    if (obj["risk"] !is JsonObject) out.remove("risk")
    val notice = obj["notice"] as? JsonObject
    if (notice == null) out.remove("notice")
    val options = obj["options"] as? JsonArray
    if (options == null) out.remove("options") else out["options"] = JsonArray(options.filterIsInstance<JsonObject>())

    // --- title: never from row prose
    val title = notice?.let { textOf(it["title"]) } ?: titleForAction(action)
    out["title"] = JsonPrimitive(title)

    // --- raised: fail toward caution
    val raised = raisedOf(obj["raised"])
    if (raised == null) out.remove("raised") else out["raised"] = raised

    // --- expiry
    val expiresAtMs = (obj["expires_at_ms"] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
    val expiresIn = (obj["expires_in"] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
    when {
        expiresAtMs != null && expiresAtMs.isFinite() -> out["expires_at_ms"] = JsonPrimitive(expiresAtMs.toLong())
        expiresIn != null && expiresIn.isFinite() && expiresIn >= 0 && expiresIn <= MAX_EXPIRES_IN_S ->
            out["expires_at_ms"] = JsonPrimitive(nowMs + (expiresIn * 1000).toLong())
        else -> out.remove("expires_at_ms")
    }
    return JsonObject(out)
}

/**
 * Anything longer than a day is not a gate timeout this phone should count
 * down from - the shipped one is 180 s - so it is read as "not known".
 */
private const val MAX_EXPIRES_IN_S = 24 * 3600.0

/**
 * The title of a row with no notice: the PC's own fallback, built from the
 * action's name ([CardWords.fallbackTitle]) - the same words the desktop
 * shows for the same row.
 */
internal fun titleForAction(action: String?): String = CardWords.fallbackTitle(action)

private fun idOf(el: JsonElement?): String? {
    val p = el as? JsonPrimitive ?: return null
    if (p is JsonNull) return null
    if (p.isString) return p.content.trim().takeIf { it.isNotEmpty() }
    // A number. A whole one is written without a fraction, so id 12 is "12".
    val d = p.doubleOrNull ?: return null
    return if (d.isFinite() && d == Math.floor(d) && Math.abs(d) < 1e15) d.toLong().toString() else p.content
}

private fun textOf(el: JsonElement?): String? =
    (el as? JsonPrimitive)?.takeIf { it.isString }?.content?.takeIf { it.isNotBlank() }

private fun parseObject(text: String): JsonObject? =
    runCatching { JarvisJson.parseToJsonElement(text) as? JsonObject }.getOrNull()

/** An empty raise: the chip's own default wording, and every quick gesture refused. */
private val GENERIC_RAISE = JsonObject(mapOf("code" to JsonPrimitive("rushed")))

private fun raisedOf(el: JsonElement?): JsonObject? = when (el) {
    null, JsonNull -> null
    // Any object, even an empty one - the same as the desktop's
    // normaliseApproval. Toward caution: an empty raise still refuses swipes.
    is JsonObject -> el
    is JsonArray -> if (el.isEmpty()) null else GENERIC_RAISE
    is JsonPrimitive -> when {
        el.isString -> {
            val t = el.content.trim()
            when {
                t.isEmpty() || t.equals("false", true) || t.equals("null", true) ||
                    t == "0" -> null
                // Parsed, never shown as text: an unknown string here may be
                // the very words that tried to rush the reader.
                else -> parseObject(t) ?: GENERIC_RAISE
            }
        }
        el.booleanOrNull != null -> if (el.booleanOrNull == true) GENERIC_RAISE else null
        else -> if ((el.doubleOrNull ?: 0.0) != 0.0) GENERIC_RAISE else null
    }
}
