package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * One notification [PhoneNotificationListenerService] kept - ALREADY
 * redacted before it ever reached this class (CLAUDE.md: "one-time codes
 * hidden before anything reaches the model" - this file never sees the
 * unredacted text at all, since [NotificationRedactor] runs in the
 * listener, before this class's [CapturedNotifications.add] is called).
 */
data class CapturedNotification(
    val id: String,
    val packageName: String,
    val appLabel: String,
    val title: String,
    val text: String,
    val postedAtMs: Long,
)

/**
 * The phone's own local store of captured notifications - NEVER sent
 * anywhere on its own (CLAUDE.md, 2026-09-26: "nothing leaves the owner's
 * own devices... shown or summarised only when the owner asks"). Kept on
 * this phone only, in a private `SharedPreferences` file, the same
 * mechanism [ModelsCacheStore] and [NotificationAllowListStore] already
 * use - never synced, never backed up ([android:allowBackup="false"] on
 * this whole app already covers that).
 *
 * A CAP ON BOTH COUNT AND AGE, so this can never grow into a second,
 * unbounded copy of the phone's whole notification history: at most
 * [MAX_KEPT] rows, and nothing older than [MAX_AGE_MS], both enforced on
 * every write.
 *
 * [sharedText] is the ONLY door from here back into a chat - the exact
 * mechanism the Share sheet and the desktop's clipboard hotkey already
 * use (`docs/JARVIS-API.md` §18, `ChatSession.send`'s own `shared`
 * parameter): the owner presses "Attach recent notifications" themselves,
 * the text goes in as its OWN message tagged `shared`, and the backend's
 * existing outside-text rule (only `typed` and `voice` are the owner's
 * own words) marks it as outside text on its own - no new backend
 * plumbing, and Jarvis never reads a captured notification any other way.
 */
class CapturedNotifications(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** Adds one, already-redacted notification, then trims to the caps. */
    fun add(n: CapturedNotification) {
        val kept = (load() + n)
            .filter { it.postedAtMs >= System.currentTimeMillis() - MAX_AGE_MS }
            .sortedByDescending { it.postedAtMs }
            .take(MAX_KEPT)
        save(kept)
    }

    /** Newest first, already capped by [add]. */
    fun recent(limit: Int = MAX_KEPT): List<CapturedNotification> = load().take(limit)

    fun clear() = prefs.edit { remove(KEY_ITEMS) }

    /**
     * The text to attach to ONE chat question, or null when there is
     * nothing to attach - never built or sent automatically. Capped at
     * [maxItems] notifications, newest first, and each notification's own
     * text is already the redacted copy [add] was given; nothing here
     * re-reads or re-redacts anything.
     */
    fun sharedText(maxItems: Int = SHARE_MAX): String? {
        val items = recent(maxItems)
        if (items.isEmpty()) return null
        val lines = items.joinToString("\n") { n ->
            "- ${n.appLabel}, ${relativeAge(n.postedAtMs)}: \"${oneLine(n.title, n.text)}\""
        }
        return "Recent phone notifications (I'm asking about these; you cannot act on them):\n$lines"
    }

    private fun oneLine(title: String, text: String): String {
        val joined = listOf(title, text).filter { it.isNotBlank() }.joinToString(" - ")
        return joined.replace('\n', ' ').take(SNIPPET_MAX)
    }

    private fun relativeAge(atMs: Long): String {
        val mins = ((System.currentTimeMillis() - atMs) / 60_000L).coerceAtLeast(0)
        return when {
            mins < 1L -> "just now"
            mins < 60L -> "$mins minute${if (mins == 1L) "" else "s"} ago"
            mins < 60L * 24L -> {
                val hrs = mins / 60L
                "$hrs hour${if (hrs == 1L) "" else "s"} ago"
            }
            else -> {
                val days = mins / (60L * 24L)
                "$days day${if (days == 1L) "" else "s"} ago"
            }
        }
    }

    private fun load(): List<CapturedNotification> {
        val raw = prefs.getString(KEY_ITEMS, null) ?: return emptyList()
        return runCatching {
            (JarvisJson.parseToJsonElement(raw) as JsonArray).mapNotNull(::fromJson)
        }.getOrDefault(emptyList())
    }

    private fun save(items: List<CapturedNotification>) {
        // `this.add` (never bare `add`): this class has its own public
        // `add(CapturedNotification)`, which an unqualified call inside
        // this lambda could otherwise be mistaken for at a glance.
        val arr = buildJsonArray { items.forEach { this.add(it.toJson()) } }
        prefs.edit { putString(KEY_ITEMS, arr.toString()) }
    }

    private fun CapturedNotification.toJson(): JsonObject = buildJsonObject {
        put("id", id)
        put("pkg", packageName)
        put("label", appLabel)
        put("title", title)
        put("text", text)
        put("at", postedAtMs)
    }

    private fun fromJson(el: JsonElement): CapturedNotification? {
        val o = el as? JsonObject ?: return null
        val id = (o["id"] as? JsonPrimitive)?.contentOrNull ?: return null
        val pkg = (o["pkg"] as? JsonPrimitive)?.contentOrNull ?: return null
        val label = (o["label"] as? JsonPrimitive)?.contentOrNull ?: pkg
        val title = (o["title"] as? JsonPrimitive)?.contentOrNull ?: ""
        val text = (o["text"] as? JsonPrimitive)?.contentOrNull ?: ""
        val at = (o["at"] as? JsonPrimitive)?.longOrNull ?: return null
        return CapturedNotification(id, pkg, label, title, text, at)
    }

    private companion object {
        const val PREFS = "jarvis_captured_notifications"
        const val KEY_ITEMS = "items"

        /** At most this many kept, whatever else clears the older ones out first. */
        const val MAX_KEPT = 200

        /** Nothing older than this survives a write (7 days). */
        const val MAX_AGE_MS = 7L * 24L * 60L * 60L * 1000L

        /** At most this many go into one "attach" - a long list is not a summary. */
        const val SHARE_MAX = 20

        /** One notification's line is capped too, so one huge text does not
         * crowd out the rest of the attached list. */
        const val SNIPPET_MAX = 200
    }
}
