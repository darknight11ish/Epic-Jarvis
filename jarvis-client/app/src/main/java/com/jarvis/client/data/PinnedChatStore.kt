package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit

/**
 * The phone's own list of pinned chat messages, held on disk so it is still
 * there after a restart - the owner's request of 2026-10-27 ("pins the message
 * and remembers it and can be found easily in a new menu").
 *
 * The same mechanism every other local store in this package uses: a private
 * [android.content.SharedPreferences] file, written and read through
 * [androidx.core.content.edit]. One key holds the whole list as the JSON
 * [ChatPins.toJson] writes; the rules about what may be pinned, the cap, the
 * order and what a corrupt row reads as are all in [ChatPins], which is pure
 * Kotlin and is what the JVM tests prove.
 *
 * [host] is the PC this phone is paired with, kept beside the list so a phone
 * re-paired to a different PC never shows the old PC's pinned messages as if
 * they were the new one's - the same stamp [ModelsCacheStore] uses and for the
 * same reason. A list written before the stamp existed (empty saved host)
 * still loads once, until the next pin stamps it.
 *
 * Nothing here is ever sent anywhere: there is no route, and no request is
 * made by pinning or unpinning. "Hide memory lists and chat history" is
 * enforced by the screens that DRAW these rows (`PinnedScreen` shows
 * [com.jarvis.client.ui.screens.HiddenSection] until Show is confirmed) - the
 * store itself is not a gate, and it is not asked to be one.
 */
class PinnedChatStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /**
     * The pinned messages, newest first. Empty on a fresh install, on a list
     * written for another PC, and on anything unreadable - a preference file
     * that cannot be opened must never crash Home.
     */
    fun load(host: String = ""): List<PinnedMessage> = runCatching {
        val raw = prefs.getString(KEY_PINS, null)
        val savedHost = prefs.getString(KEY_HOST, "") ?: ""
        val anotherPc = host.isNotEmpty() && savedHost.isNotEmpty() && savedHost != host
        if (raw == null || anotherPc) emptyList() else ChatPins.fromJson(raw)
    }.getOrDefault(emptyList())

    /** Replaces the list - every change goes through here, so disk and screen never disagree. */
    fun save(rows: List<PinnedMessage>, host: String = "") {
        runCatching {
            prefs.edit {
                putString(KEY_PINS, ChatPins.toJson(rows))
                putString(KEY_HOST, host)
            }
        }
    }

    private companion object {
        const val PREFS = "jarvis_pinned_chats"
        const val KEY_PINS = "pins"
        const val KEY_HOST = "host"
    }
}
