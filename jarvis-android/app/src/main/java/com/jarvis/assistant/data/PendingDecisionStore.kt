package com.jarvis.assistant.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.assistant.network.ApprovalDecisionMessage
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Signed approval decisions that have not reached the desktop yet.
 *
 * This exists for one sequence: the process is not running, the user taps Approve
 * on the lock screen, the receiver initialises the runtime and submits — but the
 * dial is asynchronous, so the send fails, and once `onReceive` returns the
 * receiver's importance boost lapses and the process can be reaped before the
 * handshake completes. An in-memory queue loses the decision there with no trace,
 * which is the worst possible failure for the one interaction the whole app exists
 * to serve: the user believes they approved something and the desktop is still
 * waiting.
 *
 * A decision is already signed when it lands here, and the signature covers the
 * nonce and `decided_at_ms`, so replaying it later cannot change what was agreed
 * to — and the desktop's replay cache means sending it twice is harmless.
 *
 * Rows are written with `commit` rather than `apply`: `apply` is asynchronous and
 * the whole point of this class is the case where the process does not survive
 * long enough for an asynchronous write to land.
 */
class PendingDecisionStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val serializer = ListSerializer(ApprovalDecisionMessage.serializer())

    private var pending: List<ApprovalDecisionMessage> = load()

    @Synchronized
    fun add(decision: ApprovalDecisionMessage) {
        // Keyed on id: a second decision for the same request supersedes the first
        // rather than queueing both, so a double tap cannot send approve and deny.
        val next = (pending.filterNot { it.id == decision.id } + decision).takeLast(CAPACITY)
        persist(next)
    }

    @Synchronized
    fun snapshot(): List<ApprovalDecisionMessage> = pending

    @Synchronized
    fun remove(decision: ApprovalDecisionMessage) {
        persist(pending.filterNot { it.id == decision.id && it.nonce == decision.nonce })
    }

    @Synchronized
    fun contains(requestId: String): Boolean = pending.any { it.id == requestId }

    private fun persist(decisions: List<ApprovalDecisionMessage>) {
        pending = decisions
        prefs.edit(commit = true) {
            putString(KEY_QUEUE, json.encodeToString(serializer, decisions))
        }
    }

    private fun load(): List<ApprovalDecisionMessage> {
        val raw = prefs.getString(KEY_QUEUE, null) ?: return emptyList()
        return runCatching { json.decodeFromString(serializer, raw) }.getOrDefault(emptyList())
    }

    companion object {
        private const val PREFS = "jarvis_pending_decisions"
        private const val KEY_QUEUE = "queue"

        /** Far more than a human can generate; a bound only so nothing grows forever. */
        const val CAPACITY = 50
    }
}
