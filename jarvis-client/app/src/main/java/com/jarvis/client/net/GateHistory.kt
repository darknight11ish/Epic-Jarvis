package com.jarvis.client.net

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull

/**
 * One past approval card - "Activity" (the ease-of-use audit's 2026-09-27
 * item 11, docs/EASE-OF-USE-AUDIT-2026-09-27.md row 11): read-only, title,
 * outcome, when, and which device.
 *
 * Built from one row of `/api/pending`'s `history` array
 * (docs/JARVIS-API.md section 3). Two things about that array are
 * confirmed against this repository's own tests, not guessed:
 *
 * - it exists and is sent today (`docs/JARVIS-API.md` names it in the same
 *   sentence as `pending`, and [ALREADY_HANDLED_KEYS] in JarvisApi.kt has
 *   refused to let it pass for a live queue since the bug that made that
 *   necessary);
 * - `jarvis_gate.history()` never selects `detail` or `prompt`
 *   (`backend/test_gate_egress.py`'s `t_site_4_history_never_reads_it`) -
 *   the same two columns `decide()` NULLs once a card is answered
 *   (`t_site_3_deciding_erases_it`), so a row here was never going to carry
 *   the command, the recipient or the body text a pending card does.
 *
 * Everything else - whether a row also carries `notice` (as `pending()`
 * rows do, `d["notice"] = notice_for(d)`) or `decided_by` (a real column:
 * `gate-outcome.patch` reads `row["decided_by"]` when auditing a decided
 * row) - could NOT be verified: `jarvis_gate.py` itself is not in this
 * repository (backend/ holds only patches against it). So every field
 * below is optional and every accessor degrades to a plain, honest word
 * rather than a guess: a title with no `notice.title` falls back to
 * [CardWords.fallbackTitle], the same table a live card with no notice
 * uses; a state this phone does not recognise reads "Not reported" rather
 * than a made-up outcome; a row naming no device says nothing about one.
 */
data class GateHistoryItem(
    val id: String,
    val action: String? = null,
    val tier: String = "ask",
    /** Seconds since epoch. 0 when the row said nothing. */
    val createdAt: Double = 0.0,
    /** Seconds since epoch, when the row says when it was decided. */
    val decidedAt: Double? = null,
    /** The row's own word for how it ended - `state` or `outcome` - lowercased. */
    val state: String = "",
    /**
     * "This PC" or "another device", the two words every other
     * approval-adjacent route in this codebase already uses
     * (`backend/focus.patch`, `power-mode.patch`, `task-control.patch`,
     * `note-capture.patch`: `by = "this PC" if host in (...) else "another
     * device"`) - assumed for the gate's own history rows too, since
     * nothing in this repository confirms or denies it. Read from
     * `decided_by` (the DB column named in `gate-outcome.patch`), else
     * `device`, else `by`; null when the row carries none of the three.
     */
    val device: String? = null,
    val notice: Notice? = null,
) {
    /** What the card was, safe for a lock screen - same rule as a live card. */
    val title: String
        get() = notice?.title?.takeIf { it.isNotBlank() } ?: CardWords.fallbackTitle(action)

    /** "Approved" / "Denied" / "Timed out" / "Not reported". */
    val outcomeLabel: String
        get() = when (state.lowercase()) {
            "approved" -> "Approved"
            "denied" -> "Denied"
            // approvals.state uses "expired" (backend/test_gate_outcome.py's
            // docstring: "approvals.state is pending|approved|denied|expired");
            // Verdict.outcome uses "timed_out" for the same event. history()
            // reads the table directly, so "expired" is the likelier of the
            // two - both are accepted since which one the row carries was not
            // possible to confirm here.
            "expired", "timed_out" -> "Timed out"
            else -> "Not reported"
        }

    /** When to show: the decision time if the row has one, else when it was raised. */
    val whenAt: Double
        get() = decidedAt ?: createdAt
}

data class GateHistoryRead(val items: List<GateHistoryItem>, val skipped: Int)

/**
 * Reads `/api/pending`'s `history` rows one at a time, the same defensive
 * way [decodePendingRows] reads `pending` - a row this phone cannot make
 * sense of costs that ROW, not the whole list, because the exact shape of
 * `jarvis_gate.history()` is not verified (see [GateHistoryItem]).
 */
internal fun decodeGateHistoryRows(rows: List<JsonElement>): GateHistoryRead {
    val items = ArrayList<GateHistoryItem>(rows.size)
    var skipped = 0
    for (row in rows) {
        val item = runCatching { normaliseGateHistoryRow(row) }.getOrNull()
        if (item == null) skipped++ else items += item
    }
    return GateHistoryRead(items, skipped)
}

private fun doubleOf(el: JsonElement?): Double? =
    (el as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull

private fun normaliseGateHistoryRow(row: JsonElement): GateHistoryItem? {
    val obj = row as? JsonObject ?: return null
    // No id, no way to key a row in a list - the same rule pending rows use.
    val id = idOf(obj["id"]) ?: return null
    val action = textOf(obj["action"])
    val tier = textOf(obj["tier"]) ?: "ask"
    val created = doubleOf(obj["created"]) ?: 0.0
    val decidedAt = doubleOf(obj["decided_at"])
    val state = (textOf(obj["state"]) ?: textOf(obj["outcome"]) ?: "").lowercase()
    val device = textOf(obj["decided_by"]) ?: textOf(obj["device"]) ?: textOf(obj["by"])
    val notice = (obj["notice"] as? JsonObject)?.let {
        runCatching { JarvisJson.decodeFromJsonElement(Notice.serializer(), it) }.getOrNull()
    }
    return GateHistoryItem(
        id = id,
        action = action,
        tier = tier,
        createdAt = created,
        decidedAt = decidedAt,
        state = state,
        device = device,
        notice = notice,
    )
}
