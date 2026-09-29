package com.jarvis.client.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import androidx.core.content.edit
import java.security.KeyStore
import android.security.keystore.KeyPermanentlyInvalidatedException
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
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
 * this phone only, in a private `SharedPreferences` file, encrypted with a key
 * that never leaves the Android Keystore (as the pairing token is), the same
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

    init {
        // One-time move of rows an older build stored as plain text.
        synchronized(LOCK) {
            if (prefs.contains(KEY_ITEMS) && !prefs.contains(KEY_ENC)) loadOrNull()?.let { save(it) }
        }
    }

    /** Adds one, already-redacted notification, then trims to the caps. */
    fun add(n: CapturedNotification) = synchronized(LOCK) {
        // When the saved list cannot be opened right now (before the first unlock
        // after a reboot, say) this row is dropped rather than written over it:
        // the old rows are still there once the phone can open them again.
        val current = loadOrNull() ?: return@synchronized
        save(CapturedRows.added(current, n, System.currentTimeMillis(), MAX_AGE_MS, MAX_KEPT))
    }

    /** Newest first, already capped by [add]. */
    fun recent(limit: Int = MAX_KEPT): List<CapturedNotification> = load().take(limit)

    /** How many are kept on this phone right now. */
    fun count(): Int = load().size

    /**
     * Deletes every captured notification on this phone, for good. Called
     * when the "read notifications" switch reads as off (turning it off is
     * immediate - nothing captured stays behind), and by the plate's own
     * "Delete captured notifications" after "are you sure?".
     */
    fun clear() = synchronized(LOCK) { prefs.edit { remove(KEY_ITEMS).remove(KEY_ENC) } }

    /** Deletes what was captured from one app - when it leaves the allow list. */
    fun removeApp(packageName: String) = synchronized(LOCK) {
        val all = loadOrNull() ?: return@synchronized
        val kept = CapturedRows.withoutApp(all, packageName)
        if (kept.size != all.size) save(kept)
    }

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

    private fun load(): List<CapturedNotification> = loadOrNull() ?: emptyList()

    /**
     * The saved rows; empty when there are none; null when they exist but
     * cannot be opened RIGHT NOW (writers must not overwrite them then). A blob
     * that can never be opened again (its key is gone) is deleted and reads as
     * empty, like TokenStore's rule for the token.
     */
    private fun loadOrNull(): List<CapturedNotification>? {
        val enc = prefs.getString(KEY_ENC, null)
        val raw = if (enc != null) {
            try {
                decrypt(enc)
            } catch (t: Throwable) {
                if (t is AEADBadTagException || t is KeyPermanentlyInvalidatedException ||
                    t is IllegalArgumentException
                ) {
                    Log.w(TAG, "captured notifications unreadable for good; clearing", t)
                    prefs.edit { remove(KEY_ENC) }
                    return emptyList()
                }
                Log.w(TAG, "captured notifications unreadable for now", t)
                return null
            }
        } else {
            // Rows written by an older build, before they were encrypted.
            // Read once here; the next save() rewrites them encrypted and
            // removes this plain copy.
            prefs.getString(KEY_ITEMS, null) ?: return emptyList()
        }
        return runCatching {
            (JarvisJson.parseToJsonElement(raw) as JsonArray).mapNotNull(::fromJson)
        }.getOrDefault(emptyList())
    }

    private fun save(items: List<CapturedNotification>) {
        // `this.add` (never bare `add`): this class has its own public
        // `add(CapturedNotification)`, which an unqualified call inside
        // this lambda could otherwise be mistaken for at a glance.
        val arr = buildJsonArray { items.forEach { this.add(it.toJson()) } }
        val blob = runCatching { encrypt(arr.toString()) }.getOrNull()
        if (blob == null) {
            // Never fall back to plain text: better to lose this row.
            // Any old plain copy goes too, so nothing readable stays behind.
            Log.w(TAG, "could not encrypt captured notifications; not saving")
            prefs.edit { remove(KEY_ITEMS) }
            return
        }
        prefs.edit { putString(KEY_ENC, blob).remove(KEY_ITEMS) }
    }

    private fun secretKey(): SecretKey {
        val ks = KeyStore.getInstance(PROVIDER).apply { load(null) }
        (ks.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
        gen.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                // Not setUserAuthenticationRequired: the listener stores
                // notifications while the screen is off.
                .build(),
        )
        return gen.generateKey()
    }

    private fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val body = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(cipher.iv + body, Base64.NO_WRAP)
    }

    private fun decrypt(blob: String): String {
        val packed = Base64.decode(blob, Base64.NO_WRAP)
        require(packed.size >= IV_BYTES + TAG_BITS / 8) { "ciphertext too short" }
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(TAG_BITS, packed, 0, IV_BYTES))
        return String(cipher.doFinal(packed, IV_BYTES, packed.size - IV_BYTES), Charsets.UTF_8)
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
        const val KEY_ITEMS = "items" // old plain-text rows; read once, then removed
        const val KEY_ENC = "items_enc"
        const val TAG = "CapturedNotifications"
        const val KEY_ALIAS = "jarvis_captured_notifications_key"
        const val PROVIDER = "AndroidKeyStore"
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128

        /**
         * One lock for every instance: the listener's store, the switch-off
         * clear and the plate's delete each build their own
         * [CapturedNotifications] over the same preferences file, and
         * [add] reads the whole list then writes it back - two at once
         * lost a row, and a clear could land between an add's read and its
         * write and leave the row behind (bug audit 2026-09-29).
         */
        val LOCK = Any()

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

/**
 * The store's list rules, without Android, so the JVM tests run them.
 */
internal object CapturedRows {
    /**
     * [existing] plus [n], newest first, capped by age and count. A row
     * with the same id is replaced, not repeated: a notification updated in
     * place usually keeps its post time, so its id repeats (audit A8).
     */
    fun added(
        existing: List<CapturedNotification>,
        n: CapturedNotification,
        nowMs: Long,
        maxAgeMs: Long,
        maxKept: Int,
    ): List<CapturedNotification> =
        (existing.filter { it.id != n.id } + n)
            .filter { it.postedAtMs >= nowMs - maxAgeMs }
            .sortedByDescending { it.postedAtMs }
            .take(maxKept)

    /** Every row except [packageName]'s. */
    fun withoutApp(existing: List<CapturedNotification>, packageName: String): List<CapturedNotification> =
        existing.filter { it.packageName != packageName }
}
