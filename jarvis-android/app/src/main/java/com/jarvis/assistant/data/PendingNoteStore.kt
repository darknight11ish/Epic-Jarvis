package com.jarvis.assistant.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.assistant.network.QuickNoteMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Notes captured while the socket was down, replayed on reconnect.
 *
 * Backed by SharedPreferences rather than Room or DataStore: the payload is a
 * handful of short strings, and the app already keeps its settings here. Room
 * would add KSP codegen and a schema directory to the build for a queue that is
 * almost always empty and never exceeds [CAPACITY] rows.
 *
 * The in-memory outbox in JarvisRuntime is not enough on its own — it dies with
 * the process, and a note captured from the Quick Settings tile with no desktop
 * reachable is exactly the case where the process is short-lived.
 */
class PendingNoteStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val serializer = ListSerializer(QuickNoteMessage.serializer())

    private val _pending = MutableStateFlow(load())

    private val _pendingCount = MutableStateFlow(_pending.value.size)

    /** Count only: the HUD shows a backlog badge, not the note contents. */
    val pendingCount: StateFlow<Int> = _pendingCount.asStateFlow()

    @Synchronized
    fun add(note: QuickNoteMessage) {
        // Drop the oldest rather than the newest: a note the user just wrote is
        // the one they still remember and would notice losing.
        val next = (_pending.value + note).takeLast(CAPACITY)
        persist(next)
    }

    @Synchronized
    fun snapshot(): List<QuickNoteMessage> = _pending.value

    @Synchronized
    fun remove(note: QuickNoteMessage) {
        val next = _pending.value.toMutableList()
        next.remove(note)
        persist(next)
    }

    @Synchronized
    fun clear() = persist(emptyList())

    private fun persist(notes: List<QuickNoteMessage>) {
        _pending.value = notes
        _pendingCount.value = notes.size
        prefs.edit { putString(KEY_QUEUE, json.encodeToString(serializer, notes)) }
    }

    private fun load(): List<QuickNoteMessage> {
        val raw = prefs.getString(KEY_QUEUE, null) ?: return emptyList()
        return runCatching { json.decodeFromString(serializer, raw) }.getOrDefault(emptyList())
    }

    companion object {
        private const val PREFS = "jarvis_pending_notes"
        private const val KEY_QUEUE = "queue"
        const val CAPACITY = 200
    }
}
