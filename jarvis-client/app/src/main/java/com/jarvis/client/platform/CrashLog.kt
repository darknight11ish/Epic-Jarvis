package com.jarvis.client.platform

import android.content.Context
import android.util.Log
import com.jarvis.client.BuildConfig
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Keeps the last crash so the next launch can show it.
 *
 * This exists because "the app closes immediately after opening" is the most
 * expensive error message there is: it is the one failure that carries no
 * information at all, and getting the real one needs `adb logcat` on a machine
 * that is not the phone. A startup crash in a sideloaded app is otherwise a
 * conversation rather than a diagnosis.
 *
 * It does not swallow anything. The trace is written and then handed to the
 * handler that was already installed, so the process still dies exactly as it
 * would have and the system's own report is unaffected.
 */
object CrashLog {

    private const val FILE = "last-crash.txt"

    /** `X-Jarvis-Token: ...` however it appears in a trace or an OkHttp message. */
    private val TOKEN_HEADER =
        Regex("(X-Jarvis-Token[ :=]+)([A-Za-z0-9._~+/=-]+)", RegexOption.IGNORE_CASE)
    private const val TAG = "JarvisCrash"

    /** Installed once, from Application.onCreate, before anything else runs. */
    fun install(context: Context, redact: () -> String?) {
        val app = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            // Every step guarded: a crash handler that throws replaces a
            // legible failure with an illegible one.
            runCatching { write(app, thread, error, redact) }
                .onFailure { Log.e(TAG, "could not record the crash", it) }
            previous?.uncaughtException(thread, error)
        }
    }

    private fun write(context: Context, thread: Thread, error: Throwable, redact: () -> String?) {
        val trace = StringWriter().also { error.printStackTrace(PrintWriter(it)) }.toString()
        val when_ = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
        val body = buildString {
            appendLine("Jarvis client crashed at $when_")
            // The one line this file existed to add and never had: which
            // build produced this. Without it, a trace pasted back has no
            // way to say whether it is still reproducible on what's
            // installed now, or was already fixed two versions ago.
            appendLine("version: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
            appendLine("thread: ${thread.name}")
            appendLine()
            append(trace)
        }
        // The one thing that must never reach a file: the pairing token. It
        // should not be in a stack trace, but "should not" is not a guarantee,
        // and this file is meant to be read aloud and pasted into a chat.
        // Two passes, because the first one is not guaranteed to run.
        //
        // `redact()` reads the token, and the token is exactly what is
        // unavailable when the Keystore is unhappy - so the moment this file
        // was most likely to need redacting was the moment the substitution
        // silently did nothing and the trace was written anyway. This file is
        // meant to be read aloud and pasted into a chat.
        val secret = runCatching { redact() }.getOrNull()
        var safe = if (!secret.isNullOrBlank()) body.replace(secret, "«token»") else body
        // And a belt: anything shaped like the header goes, whatever the
        // token store had to say about itself.
        safe = TOKEN_HEADER.replace(safe, "$1«token»")
        File(context.filesDir, FILE).writeText(safe)
    }

    /** The last crash, or null. */
    fun read(context: Context): String? = runCatching {
        val f = File(context.applicationContext.filesDir, FILE)
        if (f.exists()) f.readText().takeIf { it.isNotBlank() } else null
    }.getOrNull()

    fun clear(context: Context) {
        runCatching { File(context.applicationContext.filesDir, FILE).delete() }
    }
}
