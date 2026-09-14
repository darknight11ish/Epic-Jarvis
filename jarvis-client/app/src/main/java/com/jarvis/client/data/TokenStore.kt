package com.jarvis.client.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import androidx.core.content.edit
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * The pairing token, encrypted with a key that never leaves the Android
 * Keystore.
 *
 * `JARVIS-API.md` §1 is blunt about why this matters: for a native client the
 * token is the *only* thing protecting the backend. There is no CORS, no origin
 * check that means anything, and `X-Jarvis-Client` is a formality. So it goes
 * in hardware-backed storage, never in plain preferences.
 *
 * Hand-rolled against the Keystore rather than `EncryptedSharedPreferences`,
 * which the brief offers as the alternative. That library pulls in Tink, and
 * its 1.0.0 line has a long tail of device-specific corruption reports on key
 * rotation; this is sixty lines doing exactly one thing with no dependency.
 *
 * Failure is treated as "no token", never as a crash: a phone whose Keystore
 * entry was invalidated (a changed lock screen, a restored backup) should ask
 * for the token again, not refuse to start.
 */
class TokenStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun hasToken(): Boolean = !prefs.getString(KEY_BLOB, null).isNullOrEmpty()

    /** The plaintext token, or empty when there is none or it cannot be read. */
    fun token(): String {
        val blob = prefs.getString(KEY_BLOB, null) ?: return ""
        return runCatching { decrypt(blob) }
            .onFailure {
                // Invalidated key, restored backup, cleared Keystore. Drop the
                // unreadable blob so the UI asks for the token rather than
                // failing every request with a value it cannot produce.
                Log.w(TAG, "stored token unreadable; clearing", it)
                clear()
            }
            .getOrDefault("")
    }

    fun setToken(value: String) {
        val trimmed = value.trim()
        if (trimmed.isEmpty()) {
            clear()
            return
        }
        runCatching { encrypt(trimmed) }
            .onSuccess { blob -> prefs.edit { putString(KEY_BLOB, blob) } }
            .onFailure { Log.e(TAG, "could not encrypt token", it) }
    }

    fun clear() = prefs.edit { remove(KEY_BLOB) }

    // --------------------------------------------------------------------

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
                // Deliberately not setUserAuthenticationRequired: the event
                // stream has to reconnect with the screen off, and a token the
                // foreground service cannot read is a link that dies at the
                // lock screen. Biometrics gate the ask-tier *decision* instead,
                // which is where the brief puts them.
                .build(),
        )
        return gen.generateKey()
    }

    private fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val body = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        // IV is prefixed rather than stored separately: one value to write, and
        // no way for the two halves to drift apart.
        val packed = cipher.iv + body
        return Base64.encodeToString(packed, Base64.NO_WRAP)
    }

    private fun decrypt(blob: String): String {
        val packed = Base64.decode(blob, Base64.NO_WRAP)
        require(packed.size > IV_BYTES) { "ciphertext too short" }
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(
            Cipher.DECRYPT_MODE,
            secretKey(),
            GCMParameterSpec(TAG_BITS, packed, 0, IV_BYTES),
        )
        val plain = cipher.doFinal(packed, IV_BYTES, packed.size - IV_BYTES)
        return String(plain, Charsets.UTF_8)
    }

    private companion object {
        const val TAG = "JarvisTokenStore"
        const val PREFS = "jarvis_secure"
        const val KEY_BLOB = "token_blob"
        const val KEY_ALIAS = "jarvis_token_key"
        const val PROVIDER = "AndroidKeyStore"
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
    }
}
