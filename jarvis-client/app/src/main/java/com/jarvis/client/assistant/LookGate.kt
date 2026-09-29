package com.jarvis.client.assistant

import android.app.assist.AssistStructure
import android.content.Context
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.ScreenNever
import com.jarvis.client.net.ScreenText

/**
 * The gate for "Look at this" on the phone (the owner's decision of
 * 2026-09-28, docs/SCREEN-DESIGN.md section 3): what the assistant gesture
 * may read, decided BEFORE any word is kept.
 *
 * In this order (cheapest and strictest first):
 *  1. the setting "Let the assistant gesture read the screen" - OFF unless the
 *     owner turned it on (which asked for the fingerprint or PIN). Off, the
 *     gesture only opens Jarvis, exactly as before this feature;
 *  2. which app is in front: Jarvis itself, a password manager, a bank-looking
 *     app and anything on the owner's Never look at list are refused before
 *     the screen's words are read at all ([ScreenNever.blocked]); an app the
 *     system does not name is refused too ("cannot tell" is a pause);
 *  3. only then are the words flattened, password fields left out
 *     ([ScreenText]).
 * What comes out is the app's NAME (for the owner's own chip) and the words;
 * both are held in memory only ([com.jarvis.client.net.ScreenLook]).
 */
object LookGate {

    /** The outcome of one gesture. */
    sealed class Outcome {
        /** The owner's setting is off: just open Jarvis, as always. */
        object Off : Outcome()

        /** Not looked at, with the plain sentence saying why. */
        data class Refused(val said: String) : Outcome()

        /** Looked: the app's name and the words (possibly none). */
        data class Looked(val app: String, val words: ScreenText.Words) : Outcome()
    }

    /** Is the assistant gesture allowed to read the screen right now? */
    fun readingOn(): Boolean =
        JarvisRuntime.isInitialized && JarvisRuntime.settings.security.value.screenRead

    /** The owner's own Never look at apps. */
    private fun neverApps(): Set<String> =
        if (JarvisRuntime.isInitialized) JarvisRuntime.settings.security.value.neverApps else emptySet()

    /** Decides one gesture from what the system handed over. */
    fun decide(context: Context, structure: AssistStructure?): Outcome {
        if (!readingOn()) return Outcome.Off
        val pkg = AssistReader.packageOf(structure)
        val category = pkg?.let { categoryOf(context, it) }
        ScreenNever.blocked(pkg, neverApps(), category)?.let { return Outcome.Refused(ScreenNever.said(it)) }
        val words = ScreenText.flattenAll(AssistReader.nodes(structure))
        return Outcome.Looked(labelOf(context, pkg), words)
    }

    /** The app's declared Play Store category, or null. */
    fun categoryOf(context: Context, pkg: String): Int? = runCatching {
        context.packageManager.getApplicationInfo(pkg, 0).category
    }.getOrNull()

    /** The app's name as the owner knows it, or a plain word. */
    fun labelOf(context: Context, pkg: String?): String {
        if (pkg == null) return "your"
        return runCatching {
            val pm = context.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        }.getOrNull()?.trim()?.takeIf { it.isNotEmpty() && it.length <= 60 } ?: "an app"
    }
}
