/*
 * Adapted for Jarvis from Mobile-Harness's backup format:
 *   app/src/main/java/com/jarves/mh/backup/BackupCrypto.kt
 *   app/src/main/java/com/jarves/mh/backup/BackupManager.kt
 *   Copyright (c) 2026 Mobile Harness Contributors
 *   https://github.com/techjarves/Mobile-Harness  (MIT License)
 *
 * Licensed under the MIT License. The full notice and licence text travel with
 * this app: THIRD-PARTY-NOTICES.txt at the top of the repository, and
 * jarvis-client/app/src/main/assets/licenses/NOTICES.txt inside the APK.
 *
 * The idea taken from BackupManager is the one that matters: a backup is a
 * SNAPSHOT of named stores with an explicit version, not "copy the data
 * directory". Jarvis's snapshot is much smaller on purpose - SETTINGS ONLY.
 *
 * WHAT IS IN IT, and what is not, is [FILES] and [EXCLUDED_FILES] below. The
 * pairing token is not merely filtered out of the payload: it lives in a
 * different preferences file (`jarvis_secure`), that file is not on the list,
 * and [snapshot] can only walk the listed files. So there is no code path
 * here that reads the token, and no field in the format that could carry it.
 * `SettingsBackupTest` proves this with a realistic settings map that DOES
 * contain the token blob - it cannot reach the plaintext, the ciphertext, or
 * the format's own field list.
 *
 * The snapshot itself is JSON: every value is a typed value, not a bare
 * string, so a boolean stays a boolean and a string set stays a string set
 * when it is restored. The JSON is then sealed by [EncryptedBackup].
 */

package com.jarvis.client.data

import android.content.Context
import com.jarvis.client.BuildConfig
import java.io.InputStream
import java.io.OutputStream
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

/** The phone has no saved settings yet, so a backup would restore nothing. */
class NothingToBackUpException : java.io.IOException(SettingsBackup.NOTHING_TO_BACK_UP)

/**
 * Phone settings, as one typed snapshot that [EncryptedBackup] can seal and
 * [SettingsBackupStore] can apply.
 *
 * Pure: no `android.*` in this object, so the JVM tests hold every rule.
 */
object SettingsBackup {

    /** The snapshot's own shape. A newer one is refused rather than guessed at. */
    const val FORMAT_VERSION = 1

    /** The most plaintext this will read. A settings snapshot is a few kilobytes. */
    const val MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024

    /** What the file picker suggests. It is not a security boundary - only the header is. */
    const val SUGGESTED_FILE_NAME = "jarvis-settings.jarvisbackup"

    /** The shortest password [save] will accept. Restore accepts any non-empty one. */
    const val MIN_PASSWORD = 8

    /**
     * The preferences files a backup carries, with the reason each is a
     * SETTING rather than state, content or a secret. Only these are read.
     *
     * A new settings store belongs on this list when it is added; the list is
     * explicit so a store that holds something private cannot join it by
     * accident. `SettingsBackupTest` pins every name against the app's own
     * `const val PREFS` declarations, so a renamed file fails a test instead of
     * silently vanishing from every backup.
     */
    val FILES: Map<String, String> = linkedMapOf(
        "jarvis_client" to "this phone's own settings: voice, display and update switches",
        "jarvis_appearance" to "the face, colours and theme",
        "jarvis_menus" to "which menus are shown",
        "jarvis_history_view" to "how the chat history list is sorted and filtered",
        "jarvis_app_control" to "which apps Jarvis may open, and the screen-watch switches",
        "jarvis_phone_notifications" to "which apps may tell Jarvis about a notification",
    )

    /**
     * Preferences files a backup must NEVER carry, with the reason - the
     * section of `jarvis_secure` is the one this whole feature is built
     * around.
     */
    val EXCLUDED_FILES: Map<String, String> = linkedMapOf(
        "jarvis_secure" to "holds the pairing token behind the Android Keystore, and a restored phone must pair again",
        "jarvis_models_cache" to "a cache of what the PC said about its models, rebuilt on the next read",
        "jarvis_captured_notifications" to "the words of the owner's own notifications, not a setting",
        "jarvis_pinned_chats" to "chat data, not a setting",
        "jarvis-crash-log" to "logs",
    )

    /**
     * Keys inside a listed file that a backup does not carry. Most are STATE
     * rather than a preference: a resume point and update caches belong to the
     * phone that made the backup, and the one-time offer flags must be allowed
     * to happen on a fresh install.
     *
     * `host` is the exception, and it protects a credential. The pairing token
     * lives in `jarvis_secure`, which no backup touches, so writing a restored
     * address over the stored one would send the token the phone already holds
     * to whatever desktop the backup names.
     */
    val EXCLUDED_KEYS: Map<String, Set<String>> = mapOf(
        "jarvis_client" to setOf(
            // Never restored: a restore must not re-point a credential the
            // phone already holds. The address is typed again when the phone
            // pairs, exactly as after a reinstall.
            "host",
            "last_event_id",
            "update_last_try_ms",
            "update_newer_line",
            "update_newer_line_version",
            "update_problem",
            "phone_listening_wanted",
            "keep_alive_offered",
            "keep_alive_pending",
        ),
    )

    /** One preferences value, with its type kept. */
    sealed interface Value {
        data class Text(val value: String) : Value
        data class Flag(val value: Boolean) : Value
        data class Whole(val value: Int) : Value
        data class Big(val value: Long) : Value

        /** Stored as `Float.toString()` so a round trip cannot drift on JSON's number formatting. */
        data class Real(val value: Float) : Value
        data class Texts(val value: Set<String>) : Value
    }

    /** A decoded backup: what it was made with, when, and the settings themselves. */
    data class Snapshot(
        val appVersionName: String,
        val createdAtMillis: Long,
        val files: Map<String, Map<String, Value>>,
    ) {
        val settingCount: Int get() = files.values.sumOf { it.size }
    }

    // ------------------------------------------------------------ plain words
    // Failures are sentences the owner can act on. Every READ failure ends the
    // same way - nothing on this phone was changed - because that is the
    // property a failed restore has to have. WRITE_FAILED is the one sentence
    // that cannot promise it: the settings files are written one at a time, so
    // an earlier file may already have been replaced when a later one fails.

    const val WRONG_PASSWORD =
        "Either the password is wrong or this file has been damaged. It was not opened, and " +
            "nothing on this phone was changed."

    const val NEWER =
        "This backup was made by a newer version of the Jarvis app. Update the app on this phone " +
            "first; nothing on this phone was changed."

    const val DAMAGED =
        "This file is not a Jarvis settings backup, or it is damaged. Nothing on this phone was changed."

    const val WRONG_FILE = "Choose a .jarvisbackup file to restore."

    const val SHORT_PASSWORD =
        "Choose a password of at least $MIN_PASSWORD characters. It is the only thing that opens this backup."

    const val NOTHING_TO_BACK_UP =
        "There are no settings on this phone to back up yet."

    const val WRITE_FAILED =
        "The settings could not all be written on this phone. Some settings may already have " +
            "been restored, and the rest were not."

    const val SAVE_FAILED =
        "The backup file could not be written, so nothing was saved. Nothing on this phone was changed."

    const val TOO_BIG =
        "This backup is larger than this app will restore. Nothing on this phone was changed."

    /** What a finished restore says. */
    fun doneLine(snapshot: Snapshot): String =
        "Restored ${snapshot.settingCount} settings from a backup made on " +
            "${dateText(snapshot.createdAtMillis)} with version ${snapshot.appVersionName}. " +
            "Close and reopen Jarvis so every screen picks them up."

    /**
     * Why [password] cannot be used to SAVE a backup, or null when it can.
     * Restoring accepts any non-empty password: an old backup's password is
     * whatever it is, and refusing it here would make a valid file unopenable.
     */
    fun passwordProblem(password: CharArray): String? =
        if (password.size < MIN_PASSWORD) SHORT_PASSWORD else null

    /** "2026-11-13", in UTC - no locale or time zone to argue about. */
    internal fun dateText(millis: Long): String {
        if (millis <= 0) return "an unknown date"
        val days = millis / 86_400_000L
        // Civil-from-days, Howard Hinnant's algorithm: no java.time on old
        // Androids, and this is one date for one sentence.
        val z = days + 719_468L
        val era = (if (z >= 0) z else z - 146_096L) / 146_097L
        val doe = z - era * 146_097L
        val yoe = (doe - doe / 1_460L + doe / 36_524L - doe / 146_096L) / 365L
        val y = yoe + era * 400L
        val doy = doe - (365L * yoe + yoe / 4L - yoe / 100L)
        val mp = (5L * doy + 2L) / 153L
        val d = doy - (153L * mp + 2L) / 5L + 1L
        val m = if (mp < 10L) mp + 3L else mp - 9L
        val yy = if (m <= 2L) y + 1L else y
        return "%04d-%02d-%02d".format(yy, m, d)
    }

    // ---------------------------------------------------------------- encode
    /**
     * Builds the snapshot JSON from preferences contents.
     *
     * [files] may be the phone's complete set of preferences files - anything
     * not in [FILES] is ignored, and keys in [EXCLUDED_KEYS] are skipped. That
     * is what makes "the token cannot be in a backup" true even if a later
     * caller hands this everything it has.
     */
    fun snapshot(
        files: Map<String, Map<String, Any?>>,
        appVersionName: String,
        createdAtMillis: Long,
    ): ByteArray {
        val root = buildJsonObject {
            put("format", FORMAT_VERSION)
            put("appVersion", appVersionName)
            put("createdAtMillis", createdAtMillis)
            putJsonObject("files") {
                for (name in FILES.keys) {
                    val values = files[name] ?: continue
                    val keep = values
                        .filterKeys { it !in EXCLUDED_KEYS[name].orEmpty() }
                        .filterValues { it != null }
                    if (keep.isEmpty()) continue
                    putJsonObject(name) {
                        for ((key, value) in keep) putJsonObject(key) { putValue(value!!) }
                    }
                }
            }
        }
        return root.toString().toByteArray(Charsets.UTF_8)
    }

    private fun kotlinx.serialization.json.JsonObjectBuilder.putValue(value: Any) {
        when (value) {
            is String -> {
                put("t", "s")
                put("v", value)
            }
            is Boolean -> {
                put("t", "b")
                put("v", value)
            }
            is Int -> {
                put("t", "i")
                put("v", value)
            }
            is Long -> {
                put("t", "l")
                put("v", value)
            }
            is Float -> {
                put("t", "f")
                // A string, not a number: "-0.0", "1.0E-5" and a provider's
                // own float formatting must all round-trip through toFloat().
                put("v", value.toString())
            }
            is Set<*> -> {
                put("t", "set")
                put(
                    "v",
                    buildJsonArray {
                        for (item in value) if (item is String) add(JsonPrimitive(item))
                    },
                )
            }
            // SharedPreferences holds nothing else. If this ever fires, it is
            // a bug here and not a file to write half of.
            else -> throw IllegalArgumentException("unsupported settings value: ${value::class}")
        }
    }

    // ---------------------------------------------------------------- decode
    /**
     * Parses and validates a snapshot. STRICT on purpose: an unknown file name,
     * an unknown type tag or a newer format refuses the whole backup instead of
     * applying the parts this build happens to understand.
     */
    fun read(bytes: ByteArray): Snapshot {
        if (bytes.size > MAX_SNAPSHOT_BYTES) throw InvalidBackupException(DAMAGED)
        val root = try {
            Json.parseToJsonElement(String(bytes, Charsets.UTF_8)) as? JsonObject
                ?: throw InvalidBackupException(DAMAGED)
        } catch (_: Exception) {
            throw InvalidBackupException(DAMAGED)
        }
        val format = root["format"]?.jsonPrimitive?.intOrNull ?: throw InvalidBackupException(DAMAGED)
        if (format > FORMAT_VERSION) throw NewerBackupException()
        val appVersion = root["appVersion"]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }
            ?: throw InvalidBackupException(DAMAGED)
        val created = root["createdAtMillis"]?.jsonPrimitive?.longOrNull
            ?: throw InvalidBackupException(DAMAGED)
        val filesObject = root["files"] as? JsonObject ?: throw InvalidBackupException(DAMAGED)
        val files = LinkedHashMap<String, Map<String, Value>>()
        for ((name, fileValue) in filesObject) {
            // A crafted or future backup naming a file this build does not
            // know is refused - above all, `jarvis_secure`.
            if (name !in FILES) throw InvalidBackupException(DAMAGED)
            val entries = fileValue as? JsonObject ?: throw InvalidBackupException(DAMAGED)
            val values = LinkedHashMap<String, Value>()
            for ((key, valueObject) in entries) {
                if (key in EXCLUDED_KEYS[name].orEmpty()) continue
                values[key] = readValue(valueObject as? JsonObject ?: throw InvalidBackupException(DAMAGED))
            }
            if (values.isNotEmpty()) files[name] = values
        }
        return Snapshot(appVersion, created, files)
    }

    private fun readValue(obj: JsonObject): Value {
        val type = obj["t"]?.jsonPrimitive?.contentOrNull ?: throw InvalidBackupException(DAMAGED)
        val v = obj["v"] ?: throw InvalidBackupException(DAMAGED)
        return when (type) {
            "s" -> Value.Text(v.jsonPrimitive.content)
            "b" -> Value.Flag(v.jsonPrimitive.booleanOrNull ?: throw InvalidBackupException(DAMAGED))
            "i" -> Value.Whole(v.jsonPrimitive.intOrNull ?: throw InvalidBackupException(DAMAGED))
            "l" -> Value.Big(v.jsonPrimitive.longOrNull ?: throw InvalidBackupException(DAMAGED))
            "f" -> Value.Real(
                v.jsonPrimitive.contentOrNull?.toFloatOrNull() ?: throw InvalidBackupException(DAMAGED),
            )
            "set" -> {
                val array = v as? JsonArray ?: throw InvalidBackupException(DAMAGED)
                val set = LinkedHashSet<String>()
                for (item in array) {
                    val text = item.jsonPrimitive.contentOrNull ?: throw InvalidBackupException(DAMAGED)
                    set.add(text)
                }
                Value.Texts(set)
            }
            else -> throw InvalidBackupException(DAMAGED)
        }
    }
}

/**
 * The Android half: reads the phone's settings files, and applies a decoded
 * snapshot back to them.
 *
 * It never opens `jarvis_secure`. That is not an optimisation - it is the
 * feature's promise, and it is why this class asks for the files by name
 * instead of walking `data/data/.../shared_prefs`.
 */
object SettingsBackupStore {

    /** The files this phone will hand to [SettingsBackup.snapshot], and nothing else. */
    fun read(context: Context): Map<String, Map<String, Any?>> {
        val app = context.applicationContext
        val out = LinkedHashMap<String, Map<String, Any?>>()
        for (name in SettingsBackup.FILES.keys) {
            out[name] = app.getSharedPreferences(name, Context.MODE_PRIVATE).all
        }
        return out
    }

    /**
     * Writes a sealed snapshot to [output] and returns how many settings it
     * carries. The caller owns (and closes) [output]; the stream this opens
     * for the container closes it too, whichever happens first.
     *
     * Throws [NothingToBackUpException] BEFORE writing anything when the phone
     * has no saved settings yet, so a "backup" is never a file that restores
     * nothing.
     */
    fun save(context: Context, password: CharArray, output: OutputStream): Int {
        val files = read(context)
        val json = SettingsBackup.snapshot(
            files = files,
            appVersionName = BuildConfig.VERSION_NAME,
            createdAtMillis = System.currentTimeMillis(),
        )
        val count = SettingsBackup.read(json).settingCount
        if (count == 0) throw NothingToBackUpException()
        EncryptedBackup.openWriter(output, password).use { it.write(json) }
        return count
    }

    /** What a restore came to. One of these is always shown to the owner. */
    sealed interface Restored {
        data class Done(val line: String) : Restored
        data class Refused(val words: String) : Restored
    }

    /**
     * Decrypts and applies a backup. Nothing is written to the preferences
     * until the WHOLE file has authenticated ([EncryptedBackup.readAll]) and
     * parsed, so a wrong password, a tampered byte or a newer file leaves the
     * phone exactly as it was.
     */
    fun restore(context: Context, password: CharArray, input: InputStream): Restored {
        val bytes = try {
            // The cap is a refusal, not a hint: a crafted file must not be able
            // to make the app hold more than a settings snapshot in memory.
            EncryptedBackup.readAll(input, password, SettingsBackup.MAX_SNAPSHOT_BYTES)
        } catch (_: BackupTooLargeException) {
            return Restored.Refused(SettingsBackup.TOO_BIG)
        } catch (_: WrongBackupPasswordException) {
            return Restored.Refused(SettingsBackup.WRONG_PASSWORD)
        } catch (_: NewerBackupException) {
            return Restored.Refused(SettingsBackup.NEWER)
        } catch (_: InvalidBackupException) {
            return Restored.Refused(SettingsBackup.DAMAGED)
        } catch (_: Exception) {
            // Any other read failure (a provider that cut the file short, a
            // cipher provider that is not there) is the same answer: nothing
            // was applied.
            return Restored.Refused(SettingsBackup.DAMAGED)
        }
        if (bytes.isEmpty()) return Restored.Refused(SettingsBackup.DAMAGED)
        val snapshot = try {
            SettingsBackup.read(bytes)
        } catch (_: NewerBackupException) {
            return Restored.Refused(SettingsBackup.NEWER)
        } catch (_: Exception) {
            return Restored.Refused(SettingsBackup.DAMAGED)
        }
        val app = context.applicationContext
        for ((name, values) in snapshot.files) {
            // `read` only ever returns names from SettingsBackup.FILES.
            val editor = app.getSharedPreferences(name, Context.MODE_PRIVATE).edit()
            editor.clear()
            for ((key, value) in values) {
                when (value) {
                    is SettingsBackup.Value.Text -> editor.putString(key, value.value)
                    is SettingsBackup.Value.Flag -> editor.putBoolean(key, value.value)
                    is SettingsBackup.Value.Whole -> editor.putInt(key, value.value)
                    is SettingsBackup.Value.Big -> editor.putLong(key, value.value)
                    is SettingsBackup.Value.Real -> editor.putFloat(key, value.value)
                    is SettingsBackup.Value.Texts -> editor.putStringSet(key, value.value)
                }
            }
            // commit(), not apply(): each file is written as one transaction,
            // and a restore that fails to write says so instead of pretending.
            if (!editor.commit()) return Restored.Refused(SettingsBackup.WRITE_FAILED)
        }
        return Restored.Done(SettingsBackup.doneLine(snapshot))
    }
}
