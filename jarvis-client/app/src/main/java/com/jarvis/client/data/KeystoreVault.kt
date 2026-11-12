package com.jarvis.client.data

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Hardware-backed cryptographic vault for Android (inspired by Mobile-Harness Keystore isolation).
 *
 * Enforces Rule 3 (credentials stay local):
 * - Key material never leaves AndroidKeyStore (hardware TEE/StrongBox when supported).
 * - AES-256-GCM authenticated encryption with a unique 12-byte IV per encryption.
 * - Standardized Base64 packaging: [12-byte IV] + [Ciphertext + 16-byte Auth Tag].
 * - Graceful degradation: corrupted or permanently invalidated blobs return null or fallback
 *   instead of crashing the runtime.
 */
object KeystoreVault {

    private const val TAG = "JarvisKeystoreVault"
    private const val PROVIDER = "AndroidKeyStore"
    private const val KEY_ALIAS = "jarvis_vault_master_key"
    private const val TRANSFORM = "AES/GCM/NoPadding"
    private const val IV_BYTES = 12
    private const val TAG_BITS = 128

    @Synchronized
    private fun getOrCreateKey(): SecretKey {
        val ks = KeyStore.getInstance(PROVIDER).apply { load(null) }
        val existing = (ks.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)?.secretKey
        if (existing != null) return existing

        val keyGen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()

        keyGen.init(spec)
        return keyGen.generateKey()
    }

    /**
     * Encrypts plaintext bytes using hardware-backed AES-256-GCM.
     * Returns [12-byte IV] + [Ciphertext with GCM auth tag].
     */
    fun encryptBytes(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val ciphertext = cipher.doFinal(plain)
        return cipher.iv + ciphertext
    }

    /**
     * Decrypts [12-byte IV] + [Ciphertext with GCM tag]. Returns null on tampered/invalid data.
     */
    fun decryptBytes(packed: ByteArray): ByteArray? {
        if (packed.size < IV_BYTES + (TAG_BITS / 8)) return null
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORM)
            val spec = GCMParameterSpec(TAG_BITS, packed, 0, IV_BYTES)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), spec)
            cipher.doFinal(packed, IV_BYTES, packed.size - IV_BYTES)
        }.getOrNull()
    }

    /**
     * Encrypts a UTF-8 string into a Base64-encoded ciphertext blob.
     */
    fun encryptString(plain: String): String {
        val bytes = plain.toByteArray(Charsets.UTF_8)
        val encrypted = encryptBytes(bytes)
        return Base64.encodeToString(encrypted, Base64.NO_WRAP)
    }

    /**
     * Decrypts a Base64-encoded ciphertext blob into a UTF-8 string, or null on failure.
     */
    fun decryptString(blob: String): String? {
        if (blob.isBlank()) return null
        return runCatching {
            val packed = Base64.decode(blob, Base64.NO_WRAP)
            decryptBytes(packed)?.let { String(it, Charsets.UTF_8) }
        }.onFailure {
            Log.w(TAG, "Failed to decrypt vault blob: ${it.message}")
        }.getOrNull()
    }
}
