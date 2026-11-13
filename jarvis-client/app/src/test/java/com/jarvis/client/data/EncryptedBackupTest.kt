package com.jarvis.client.data

import com.jarvis.client.SourceFile
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * The encrypted phone-settings backup (2026-11-13, the copy-over wave).
 *
 * The container is adapted from Mobile-Harness's `BackupCrypto.kt` (MIT, see
 * the header of `EncryptedBackup.kt` and THIRD-PARTY-NOTICES.txt). Two things
 * are being held here, and they are not the same kind of claim:
 *
 *  1. THE CRYPTO AND THE FORMAT. A round trip keeps every value type; a wrong
 *     password, a tampered byte, a truncated file, a non-Jarvis file and a
 *     newer version all fail CLOSED, and none of them returns a partial
 *     plaintext for the app to apply. A newer SNAPSHOT inside a valid
 *     container is refused the same way.
 *
 *  2. THE SCOPE. This backup is settings only. The pairing token is not
 *     encrypted into it, not filtered out at the end, and not an input field:
 *     it lives in a preferences file that [SettingsBackup.FILES] does not
 *     name, and [SettingsBackup.snapshot] walks that list. The test builds a
 *     realistic map that DOES contain the token blob - the whole phone's
 *     preferences, as a careless caller might pass them - and proves the blob,
 *     its key name and its file name are absent from the plaintext, absent
 *     from the ciphertext, and impossible to name in a restored snapshot.
 *
 * Pure JVM: no Android and no emulator, on purpose - this is the logic where a
 * quiet mistake is unrecoverable (a lost token cannot be restored).
 */
class EncryptedBackupTest {

    private val password = "correct horse battery".toCharArray()

    /** A realistic token blob: the app stores base64 of IV+AES-GCM ciphertext. */
    private val tokenBlob = "q83vEjS8T5m1yXb0pQwErTyUiOpAsDfGhJkLzXcVbNm1234567890=="

    private val tokenMarker = tokenBlob.take(24)

    /**
     * The phone's preferences as they really are: settings stores, plus the
     * Keystore-backed token file and the caches a backup must not carry.
     */
    private fun realisticPrefs(): Map<String, Map<String, Any?>> = linkedMapOf(
        "jarvis_secure" to linkedMapOf("token_blob" to tokenBlob),
        "jarvis_client" to linkedMapOf(
            "host" to "jarvis-pc.owner-tailnet.ts.net",
            "interrupt" to "voice",
            "one_moment" to true,
            "heard_sound" to false,
            "read_memories_aloud" to true,
            "floating_avatar" to "bubble",
            "pip_mode" to "conversation",
            "screen_hz" to 120,
            "created_ms" to 1_700_000_000_000L,
            "face_scale" to 1.25f,
            "last_event_id" to "evt-1700000000-42",
            "update_newer_line" to "A newer build of this app is on GitHub (main, abc1234).",
        ),
        "jarvis_appearance" to linkedMapOf("theme" to "midnight", "accent" to "teal"),
        "jarvis_menus" to linkedMapOf("hidden" to setOf("settings.manner", "brain.skills")),
        "jarvis_models_cache" to linkedMapOf("models" to "[]"),
        "jarvis_pinned_chats" to linkedMapOf("pinned" to "chat-7"),
    )

    private fun snapshotJson(
        prefs: Map<String, Map<String, Any?>> = realisticPrefs(),
        createdAt: Long = 1_700_000_000_000L,
    ): ByteArray = SettingsBackup.snapshot(prefs, appVersionName = "0.2.448", createdAtMillis = createdAt)

    private fun seal(
        plain: ByteArray,
        pass: CharArray = password,
        iterations: Int = 2_000,
    ): ByteArray {
        val out = ByteArrayOutputStream()
        EncryptedBackup.openWriter(out, pass, iterations).use { it.write(plain) }
        return out.toByteArray()
    }

    private fun open(sealed: ByteArray, pass: CharArray = password): ByteArray =
        EncryptedBackup.readAll(ByteArrayInputStream(sealed), pass)

    // ------------------------------------------------------------ round trip

    @Test
    fun `a settings snapshot makes a byte-identical round trip`() {
        val json = snapshotJson()
        val opened = open(seal(json))
        assertTrue("the plaintext changed across the round trip", json.contentEquals(opened))
    }

    @Test
    fun `every value type survives a restore`() {
        val opened = open(seal(snapshotJson()))
        val restored = SettingsBackup.read(opened)
        val settings = requireNotNull(restored.files["jarvis_client"])
        assertEquals(SettingsBackup.Value.Text("jarvis-pc.owner-tailnet.ts.net"), settings["host"])
        assertEquals(SettingsBackup.Value.Flag(true), settings["one_moment"])
        assertEquals(SettingsBackup.Value.Flag(false), settings["heard_sound"])
        assertEquals(SettingsBackup.Value.Whole(120), settings["screen_hz"])
        assertEquals(SettingsBackup.Value.Big(1_700_000_000_000L), settings["created_ms"])
        assertEquals(SettingsBackup.Value.Real(1.25f), settings["face_scale"])
        assertEquals(
            SettingsBackup.Value.Texts(setOf("settings.manner", "brain.skills")),
            requireNotNull(restored.files["jarvis_menus"])["hidden"],
        )
        assertEquals("0.2.448", restored.appVersionName)
        assertEquals(1_700_000_000_000L, restored.createdAtMillis)
    }

    @Test
    fun `the phone's own state keys and caches are not carried`() {
        val restored = SettingsBackup.read(snapshotJson())
        val settings = requireNotNull(restored.files["jarvis_client"])
        assertFalse("a resume point is state, not a setting", "last_event_id" in settings)
        assertFalse("an update cache is state, not a setting", "update_newer_line" in settings)
        // The cache and chat stores are not settings files at all.
        assertFalse("jarvis_models_cache" in restored.files)
        assertFalse("jarvis_pinned_chats" in restored.files)
    }

    // --------------------------------------------------------- fail-closed

    @Test
    fun `a wrong password opens nothing`() {
        val sealed = seal(snapshotJson())
        try {
            open(sealed, "not the right password".toCharArray())
            fail("a wrong password was accepted")
        } catch (expected: WrongBackupPasswordException) {
            // The store turns this into SettingsBackup.WRONG_PASSWORD; the
            // important part is that no bytes were returned to apply.
        }
    }

    @Test
    fun `a tampered ciphertext is refused, never partially decrypted`() {
        val sealed = seal(snapshotJson())
        // The very last byte is inside the GCM tag: changing it cannot leave
        // the first segment authenticated.
        sealed[sealed.size - 1] = (sealed[sealed.size - 1].toInt() xor 0x01).toByte()
        try {
            open(sealed)
            fail("a tampered file decrypted")
        } catch (expected: WrongBackupPasswordException) {
            // GCM cannot tell a wrong key from a modified tag; the plain words
            // for both say "wrong password or damaged", and nothing was applied.
        }
    }

    @Test
    fun `a truncated file is refused`() {
        val sealed = seal(snapshotJson())
        val cut = sealed.copyOf(sealed.size - 8)
        try {
            open(cut)
            fail("a truncated file decrypted")
        } catch (expected: InvalidBackupException) {
            assertTrue(expected.message!!.isNotBlank())
        }
    }

    @Test
    fun `a payload bigger than the app will hold is refused, not read`() {
        val big = ByteArray(200_000) { (it % 97).toByte() }
        val sealed = seal(big)
        try {
            EncryptedBackup.readAll(ByteArrayInputStream(sealed), password, maxBytes = 1024)
            fail("an oversized payload was read into memory")
        } catch (expected: BackupTooLargeException) {
            assertEquals(SettingsBackup.TOO_BIG, expected.message)
        }
        // The app's own cap is generous for a settings snapshot and still
        // bounded, so a crafted file cannot exhaust the phone.
        assertEquals(4 * 1024 * 1024, SettingsBackup.MAX_SNAPSHOT_BYTES)
        // A payload inside the cap still reads normally.
        val small = ByteArray(512) { it.toByte() }
        assertEquals(512, EncryptedBackup.readAll(ByteArrayInputStream(seal(small)), password, maxBytes = 4096).size)
    }

    @Test
    fun `a file that is not a Jarvis backup is refused before any key work`() {
        val sealed = seal(snapshotJson())
        sealed[0] = 'X'.code.toByte()
        try {
            open(sealed)
            fail("a foreign file decrypted")
        } catch (expected: InvalidBackupException) {
            assertTrue(expected.message!!.contains("Jarvis", ignoreCase = true))
        }
    }

    @Test
    fun `an unencrypted file is refused`() {
        val sealed = seal(snapshotJson())
        // Byte 5 is the flags byte in this format: magic(4), version(1), flags(1).
        sealed[5] = 0
        try {
            open(sealed)
            fail("an unencrypted file was accepted")
        } catch (expected: InvalidBackupException) {
            assertTrue(expected.message!!.contains("not encrypted"))
        }
    }

    @Test
    fun `a newer container version is refused with its own reason`() {
        val sealed = seal(snapshotJson())
        sealed[4] = 2 // the format version byte
        try {
            open(sealed)
            fail("a newer container was accepted")
        } catch (expected: NewerBackupException) {
            // SettingsBackupStore maps this to SettingsBackup.NEWER.
        }
    }

    @Test
    fun `a newer snapshot inside a valid container is refused`() {
        val json = String(snapshotJson(), Charsets.UTF_8).replace("\"format\":1", "\"format\":2")
        try {
            SettingsBackup.read(json.toByteArray(Charsets.UTF_8))
            fail("a newer snapshot was accepted")
        } catch (expected: NewerBackupException) {
            // Same answer as the container: update the app first.
        }
    }

    @Test
    fun `a snapshot that names a file the app does not back up is refused whole`() {
        // A crafted or future backup naming the token's own store must not
        // restore it - even if it authenticated, which a real one never will.
        val crafted = """
            {"format":1,"appVersion":"9.9.9","createdAtMillis":1,
             "files":{"jarvis_secure":{"token_blob":{"t":"s","v":"$tokenBlob"}}}}
        """.trimIndent()
        try {
            SettingsBackup.read(crafted.toByteArray(Charsets.UTF_8))
            fail("a snapshot naming jarvis_secure was accepted")
        } catch (expected: InvalidBackupException) {
            assertTrue(expected.message!!.isNotBlank())
        }
    }

    @Test
    fun `an unknown value type is refused instead of guessed`() {
        val crafted = """
            {"format":1,"appVersion":"9.9.9","createdAtMillis":1,
             "files":{"jarvis_client":{"host":{"t":"q","v":"x"}}}}
        """.trimIndent()
        try {
            SettingsBackup.read(crafted.toByteArray(Charsets.UTF_8))
            fail("an unknown value type was accepted")
        } catch (expected: InvalidBackupException) {
            assertTrue(expected.message!!.isNotBlank())
        }
    }

    @Test
    fun `a password shorter than the minimum is refused for a new backup`() {
        assertNull(SettingsBackup.passwordProblem("12345678".toCharArray()))
        assertEquals(SettingsBackup.SHORT_PASSWORD, SettingsBackup.passwordProblem("1234567".toCharArray()))
        assertEquals(SettingsBackup.SHORT_PASSWORD, SettingsBackup.passwordProblem(CharArray(0)))
    }

    // ------------------------------------------------- the token is excluded

    @Test
    fun `the pairing token is absent from the plaintext, the ciphertext and the field list`() {
        val prefs = realisticPrefs()
        // The map really does contain it - this is what makes the assertion
        // below about the CODE, not about the fixture being tidy.
        assertEquals(tokenBlob, prefs.getValue("jarvis_secure").getValue("token_blob"))

        val plain = snapshotJson(prefs)
        val sealed = seal(plain)

        for (secret in listOf(tokenBlob, tokenMarker, "token_blob", "jarvis_secure")) {
            assertFalse("the plaintext carries '$secret'", contains(plain, secret))
            assertFalse("the ciphertext carries '$secret'", contains(sealed, secret))
        }
        // A real setting IS in both, so the search above is not passing
        // because the snapshot is empty.
        assertTrue(contains(plain, "jarvis-pc.owner-tailnet.ts.net"))
        assertFalse("the ciphertext is not plaintext at all", contains(sealed, "jarvis-pc.owner-tailnet.ts.net"))

        val restored = SettingsBackup.read(open(sealed))
        assertFalse("a restored snapshot names the token's file", "jarvis_secure" in restored.files)
        for (values in restored.files.values) {
            assertFalse("a restored snapshot carries a token key", "token_blob" in values)
        }
    }

    @Test
    fun `the token is not an input field of the backup format`() {
        // The promise is structural: the format's writer takes a map of the
        // phone's preference FILES and walks the allow-list. It has no token
        // parameter, and neither file that could write one mentions the token
        // store at all.
        val settings = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/data/SettingsBackup.kt")
        val container = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/data/EncryptedBackup.kt")
        assertFalse("SettingsBackup must not reach for TokenStore", settings.contains("TokenStore"))
        assertFalse("SettingsBackup must not name the token's key", settings.contains("token_blob"))
        assertFalse(
            "SettingsBackup must never open the token's file directly",
            settings.contains("getSharedPreferences(\"jarvis_secure\""),
        )
        assertFalse("jarvis_secure must not be one of the backed-up files", "jarvis_secure" in SettingsBackup.FILES)
        assertFalse("the container must not know about the token at all", container.contains("token", ignoreCase = true))
        // ...and the excluded file says WHY, in words the owner could read.
        val why = SettingsBackup.EXCLUDED_FILES.getValue("jarvis_secure")
        assertTrue(why.contains("pairing token"))
        assertTrue(why.contains("Keystore"))
        // The allow-list and the deny-list cannot overlap.
        assertTrue(SettingsBackup.FILES.keys.intersect(SettingsBackup.EXCLUDED_FILES.keys).isEmpty())
    }

    @Test
    fun `every preferences file the app stores has a decision`() {
        val known = listOf(
            "jarvis_client", "jarvis_appearance", "jarvis_menus", "jarvis_history_view",
            "jarvis_app_control", "jarvis_phone_notifications", "jarvis_secure",
            "jarvis_models_cache", "jarvis_captured_notifications", "jarvis_pinned_chats",
            "jarvis-crash-log",
        )
        for (name in known) {
            assertTrue("$name is neither backed up nor excluded with a reason",
                name in SettingsBackup.FILES || name in SettingsBackup.EXCLUDED_FILES)
        }
        // These literals must be the app's real names; a rename that only edits
        // one side would ship a backup that silently skips a store.
        val sources = listOf(
            "data/ClientSettings.kt", "data/TokenStore.kt", "data/AppearanceStore.kt",
            "data/MenuPrefs.kt", "data/HistoryViewPrefs.kt", "data/AppControlStore.kt",
            "data/NotificationAllowListStore.kt", "data/ModelsCacheStore.kt",
            "data/PinnedChatStore.kt", "data/CapturedNotifications.kt", "platform/CrashLog.kt",
        ).joinToString("\n") {
            SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/$it")
        }
        for (name in known) {
            assertTrue("no `const val PREFS = \"$name\"` in the app's sources", sources.contains("\"$name\""))
        }
    }

    @Test
    fun `nothing is written before the whole file has authenticated`() {
        // The Android half must not touch preferences while decrypting. Read
        // the source in order: the full read comes before the first edit().
        val store = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/data/SettingsBackup.kt")
        val read = store.indexOf("EncryptedBackup.readAll(input, password")
        val firstEdit = store.indexOf(".edit()")
        assertTrue("the store does not read the whole file first", read > 0)
        assertTrue("a preference write comes before the whole file is checked", read < firstEdit)
        // And a failed read returns a refusal rather than applying a partial map.
        assertTrue(store.contains("return Restored.Refused(SettingsBackup.WRONG_PASSWORD)"))
        // The read is bounded to the snapshot cap, so a crafted file cannot be
        // read into memory.
        assertTrue(
            store.contains("EncryptedBackup.readAll(input, password, SettingsBackup.MAX_SNAPSHOT_BYTES)"),
        )
        // The store never opens the token's file: it asks for FILES by name.
        assertTrue(store.contains("for (name in SettingsBackup.FILES.keys)"))
    }

    @Test
    fun `the date sentence is UTC and cannot be locale-shaped`() {
        assertEquals("2023-11-14", SettingsBackup.dateText(1_700_000_000_000L))
        assertEquals("an unknown date", SettingsBackup.dateText(0))
        assertEquals("1970-01-01", SettingsBackup.dateText(1))
    }

    // ---------------------------------------------------------------- helper

    /** Byte-level search, because the claim is about what is IN the bytes. */
    private fun contains(haystack: ByteArray, needle: String): Boolean {
        val n = needle.toByteArray(Charsets.UTF_8)
        if (n.isEmpty() || n.size > haystack.size) return false
        outer@ for (i in 0..haystack.size - n.size) {
            for (j in n.indices) if (haystack[i + j] != n[j]) continue@outer
            return true
        }
        return false
    }

    @Test
    fun `the suggested file name is the one the UI uses`() {
        assertTrue(SettingsBackup.SUGGESTED_FILE_NAME.endsWith(".jarvisbackup"))
        assertEquals(8, SettingsBackup.MIN_PASSWORD)
    }
}
