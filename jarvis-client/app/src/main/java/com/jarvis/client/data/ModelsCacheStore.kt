package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.client.net.CachedModels
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject

/**
 * The phone's own last successful `GET /api/models` read, held on disk so
 * Brain -> Model has something to show when the desktop cannot be reached -
 * `docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`.
 *
 * One row, not a history, like [ClientSettings.lastEventId]: there is only
 * ever one "last models read" worth keeping, never a log of past ones. This
 * is a separate small file rather than another key on [ClientSettings] only
 * because the value is a whole JSON document rather than one primitive -
 * the storage mechanism (a private `SharedPreferences` file, written and
 * read through [androidx.core.content.edit]) is the exact same one every
 * other local store in this package already uses.
 *
 * Written only as a side effect of an ordinary, already-happening live read
 * succeeding ([com.jarvis.client.JarvisRuntime.refreshModels]) - never
 * fetched specially, per the design doc's section 4 ("do not have the phone
 * try to 'sync' or 'refresh' the cache on demand"). Nothing here is a live
 * disk read either: this phone has no access to the PC's disk at all, and
 * everything on [CachedModels] is exactly what the PC already told it, once.
 */
class ModelsCacheStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun save(models: CachedModels) {
        prefs.edit { putString(KEY_MODELS, models.toJson().toString()) }
    }

    /**
     * The last successful read, or null on a fresh install, or before the
     * first one has ever succeeded. Anything unreadable - a corrupt
     * preference, a shape from some future version of this class - reads
     * as null too, the same "fall back rather than throw" rule every other
     * local store in this package follows.
     */
    fun load(): CachedModels? {
        val raw = prefs.getString(KEY_MODELS, null) ?: return null
        return runCatching {
            CachedModels.fromJson(JarvisJson.parseToJsonElement(raw) as JsonObject)
        }.getOrNull()
    }

    private companion object {
        const val PREFS = "jarvis_models_cache"
        const val KEY_MODELS = "models"
    }
}
