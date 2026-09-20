package com.jarvis.client.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import androidx.core.content.edit
import java.security.KeyStore
import javax.crypto.AEADBadTagException
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
                // Cleared only when the key is genuinely gone.
                //
                // This used to clear on ANY throwable, which destroyed the only
                // copy of the token for reasons that had nothing to do with
                // invalidation. The common one: after a reboot, before the
                // first unlock, credential-encrypted Keystore entries are
                // simply unavailable — and BootReceiver starts the service in
                // exactly that window. `getEntry` threw, the token was deleted,
                // and the owner unlocked their phone five minutes later to find
                // themselves unpaired with no explanation.
                //
                // A bad tag or a corrupt blob means the ciphertext really
                // cannot be opened again. Anything else is treated as "not
                // right now": no token this time, blob left where it is.
                if (isPermanent(it)) {
                    Log.w(TAG, "stored token is unreadable for good; clearing", it)
                    clear()
                } else {
                    Log.w(TAG, "token temporarily unreadable; keeping it", it)
                }
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

    /**
     * Whether this failure means the ciphertext can never be opened again.
     *
     * Deliberately a small allow-list rather than "anything not on a deny
     * list": getting this wrong in the permissive direction silently unpairs
     * the phone, and getting it wrong the other way costs one failed request.
     */
    private fun isPermanent(t: Throwable): Boolean = when (t) {
        is AEADBadTagException -> true            // wrong key, or tampered blob
        is KeyPermanentlyInvalidatedException -> true // lock screen changed
        is IllegalArgumentException -> true       // not valid Base64 any more
        else -> false                             // locked, busy, absent, flaky
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
        // IV + at least the GCM tag. `> IV_BYTES` was one constant too loose:
        // it let a 13-byte blob through and handed the cipher a one-byte
        // "ciphertext", so a blob that can never be opened by ANY key failed
        // inside AndroidKeyStore instead of here.
        //
        // That distinction is the whole point. Where it fails decides whether
        // the token is kept or dropped: the exception AndroidKeyStore raises
        // for a too-short GCM input is provider-specific, and at least one of
        // the candidates is also what an unavailable key throws - so treating
        // it as permanent would reopen the bug where a reboot, before the
        // first unlock, silently unpaired the phone. Structural validity is
        // decidable here, without the Keystore and without guessing, and
        // `require` throws IllegalArgumentException, which is already on the
        // permanent list.
        require(packed.size >= IV_BYTES + TAG_BITS / 8) { "ciphertext too short" }
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
