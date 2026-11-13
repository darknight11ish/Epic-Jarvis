package com.jarvis.client.localai

import android.content.Context

/**
 * The tiny key/value seam between the Local AI switch and where it is saved.
 *
 * An interface rather than `SharedPreferences` directly so `LocalAiSettings`
 * can be tested on a JVM with a map: the rule that matters - **the switch
 * ships OFF** - is then a one-line assertion, not a claim about an Android
 * object nobody in the test can see.
 */
interface LocalAiFlagStore {

    fun readBoolean(key: String, fallback: Boolean): Boolean

    fun writeBoolean(key: String, value: Boolean)
}

/**
 * The one persistent setting the on-device engine has: whether the owner has
 * turned the Local AI screen on.
 *
 * **It ships OFF** ([DEFAULT_ENABLED]) and is read with `false` as the
 * fallback, so a fresh install, a cleared data directory, an unreadable
 * preference and a prefs file that never carried the key all answer the same
 * thing: off. There is no code path that turns it on except the owner tapping
 * the switch.
 *
 * The switch is stored on this phone only. It is not the PC's setting, it is
 * never sent anywhere, and it does not gate the rest of Jarvis: the ordinary
 * chat that uses the PC works exactly as before whether this is on or off.
 */
class LocalAiSettings(private val store: LocalAiFlagStore) {

    /** Whether the owner has turned on-device models on, on this phone. */
    val enabled: Boolean
        get() = store.readBoolean(KEY_ENABLED, DEFAULT_ENABLED)

    /** Writes the owner's choice. Nothing else changes here. */
    fun setEnabled(on: Boolean) {
        store.writeBoolean(KEY_ENABLED, on)
    }

    companion object {

        /** The preference file's name. */
        const val PREFS = "local_ai"

        /** The one key in it. */
        const val KEY_ENABLED = "enabled"

        /** OFF, always, until the owner taps. The whole feature ships dark. */
        const val DEFAULT_ENABLED = false
    }
}

/** The real store: one boolean in this app's private SharedPreferences. */
class SharedPrefsLocalAiFlags(context: Context) : LocalAiFlagStore {

    private val prefs = context.applicationContext
        .getSharedPreferences(LocalAiSettings.PREFS, Context.MODE_PRIVATE)

    override fun readBoolean(key: String, fallback: Boolean): Boolean =
        prefs.getBoolean(key, fallback)

    override fun writeBoolean(key: String, value: Boolean) {
        prefs.edit().putBoolean(key, value).apply()
    }
}
