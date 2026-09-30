package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit

/**
 * Which History sections are folded shut, remembered on this phone
 * (docs/CHAT-TAGS-DESIGN.md sections 6 and 10: "the open/closed state is
 * remembered per device, a harmless view preference, not chat content").
 *
 * ONLY flags are kept: a set of tag ids (or -1 for Untagged) that are shut.
 * Never a tag name, never a chat id, never a word of a chat. A section is
 * open unless its id is in the set, so a new tag starts open and a deleted
 * tag's id sitting here does nothing.
 *
 * Reads and writes are guarded: a preference file that cannot be opened
 * leaves every section open and never crashes History.
 */
class HistoryViewPrefs(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** The ids of the sections folded shut. */
    fun closed(): Set<Int> = runCatching {
        prefs.getStringSet(KEY_CLOSED, emptySet()).orEmpty().mapNotNull { it.toIntOrNull() }.toSet()
    }.getOrDefault(emptySet())

    fun saveClosed(ids: Set<Int>) {
        runCatching { prefs.edit { putStringSet(KEY_CLOSED, ids.map { it.toString() }.toSet()) } }
    }

    private companion object {
        const val PREFS = "jarvis_history_view"
        const val KEY_CLOSED = "closed_sections"
    }
}
