package com.jarvis.client.net

import android.content.Context
import android.os.Build
import com.jarvis.client.BuildConfig

/**
 * The phone's own facts, as ONE header value: `model=CPH2419;android=15;...`.
 *
 * WHY IT EXISTS (2026-11-15). The owner asked for answers that are *phone
 * specific*, not just aware that a phone is asking: "make sure jarvis can tell
 * when im messaging from the phone and be more phone specific in the answers".
 * `X-Jarvis-Surface: phone` already says a phone is asking - it is one word, so
 * the PC could not name the phone, could not size an answer to its screen, and
 * could not tell Android 15 from Android 17. This is the second half: the facts
 * themselves, small enough for a header, sent on every request beside it.
 *
 * WHAT IT IS NOT. It is not authentication and not a secret - the pairing token
 * is still the only credential, and the server treats this line as words. It
 * carries nothing about the owner, the conversation or the phone's contents:
 * five fields, all of them true of the device rather than of the person. There
 * is deliberately no identifier here, because an identifier would turn a
 * description of a phone into a way to follow one.
 *
 * BOUNDED AND CLEAN BY CONSTRUCTION. [line] keeps only letters, digits, spaces
 * and `. _ + -`, drops anything else (so no newline, brace or comma can reach
 * an HTTP header or a system prompt), caps each field, and caps the whole value
 * at [MAX_CHARS]. The server caps again at 240 and knows only these five keys,
 * so neither side trusts the other.
 *
 * WHEN IT IS EMPTY. Before [initialise] runs - in unit tests, and for the first
 * moments of a cold start - [headerValue] is "", and the request simply carries
 * no device header. That is exactly what an older client sends, so the server
 * falls back to the one sentence it has always used.
 */
object DeviceFacts {

    /**
     * Longest value this object will ever produce. The server's own cap is 240;
     * this is below it on purpose, so the app is the one that keeps it small.
     */
    const val MAX_CHARS = 200

    @Volatile
    private var value: String = ""

    /**
     * Read this phone's facts once. Called from the Application's own start, so
     * every request after it can carry them without touching a Context.
     */
    fun initialise(context: Context) {
        val metrics = context.resources.displayMetrics
        value = line(
            model = Build.MODEL,
            release = Build.VERSION.RELEASE,
            sdk = Build.VERSION.SDK_INT,
            screen = "${metrics.widthPixels}x${metrics.heightPixels}",
            app = BuildConfig.VERSION_NAME,
        )
    }

    /** The header value: "" until [initialise] has run, never longer than [MAX_CHARS]. */
    fun headerValue(): String = value

    /**
     * The value itself, from its parts. Pure, so a unit test can prove the
     * cleaning and the caps without an Android device.
     */
    fun line(model: String?, release: String?, sdk: Int, screen: String?, app: String?): String {
        val parts = mutableListOf<String>()
        clean(model, 28)?.let { parts += "model=$it" }
        clean(release, 8)?.let { parts += "android=$it" }
        if (sdk > 0) parts += "sdk=$sdk"
        clean(screen, 12)?.let { parts += "screen=$it" }
        clean(app, 18)?.let { parts += "app=$it" }
        return parts.joinToString(";").take(MAX_CHARS)
    }

    /**
     * One field's value, or null when it is blank. The allow-list is the point:
     * a model name from an unusual vendor ("POCO F5 (Pro)") loses its brackets
     * rather than escaping them, and a value that is only punctuation becomes
     * null instead of an empty pair.
     */
    private fun clean(raw: String?, max: Int): String? {
        if (raw.isNullOrBlank()) return null
        val kept = buildString {
            for (ch in raw) {
                val allowed = ch in 'a'..'z' || ch in 'A'..'Z' || ch in '0'..'9' ||
                    ch == ' ' || ch == '.' || ch == '_' || ch == '+' || ch == '-'
                if (allowed) append(ch)
            }
        }.trim()
        return kept.take(max).ifEmpty { null }
    }
}
