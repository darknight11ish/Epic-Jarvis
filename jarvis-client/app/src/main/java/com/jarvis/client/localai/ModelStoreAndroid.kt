package com.jarvis.client.localai

import android.content.Context
import java.io.File

/**
 * The one place that turns a `Context` into a [ModelStore].
 *
 * `getExternalFilesDir("models")` is the app's own folder on shared storage:
 * no permission, removed on uninstall, invisible to the gallery. It can be
 * null (a phone that has no shared storage mounted, which is rare but real),
 * and then the app's internal folder is used rather than failing: a model
 * copied there still works, it is simply not visible over USB. The screen
 * never shows the path, so the owner is not asked to care which one it was.
 *
 * Kept out of `ModelStore.kt` so that class stays pure Kotlin and its tests
 * need no Android at all.
 */
object ModelStoreAndroid {

    /** The store in `context.getExternalFilesDir("models")`, or an internal fallback. */
    fun forApp(context: Context): ModelStore {
        val external = context.getExternalFilesDir(ModelStore.FOLDER)
        val folder = external ?: File(context.filesDir, ModelStore.FOLDER)
        return ModelStore(folder)
    }
}
