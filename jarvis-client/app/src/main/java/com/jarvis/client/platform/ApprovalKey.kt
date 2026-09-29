package com.jarvis.client.platform

import android.content.Context
import android.content.pm.PackageManager
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import com.jarvis.client.net.SignedApproval
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.ProviderException
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * This phone's approval key (docs/PAIRING-DESIGN.md §11.1): an EC P-256 key in
 * the Android Keystore that can only sign right after a fresh fingerprint or
 * PIN, one signature per check. The private half never leaves the phone's
 * security chip; the PC gets the public half only.
 *
 * Made only when the owner taps "Turn on signed approvals". Android throws
 * the key away when a new fingerprint is added or the screen lock is removed;
 * [state] then says [SignedApproval.Local.NONE] (gone) or
 * [SignedApproval.Local.INVALID] (kept but dead), and the app offers to turn
 * signed approvals on again.
 *
 * minSdk is 33, so the API 30 calls below need no older fallback.
 * Nothing here is logged: no key, no signature.
 */
object ApprovalKey {

    /** Fixed: one approval key per phone. */
    const val ALIAS = "jarvis_approval_key_v1"

    private const val PROVIDER = "AndroidKeyStore"
    private const val ALGORITHM = "SHA256withECDSA"

    private fun store(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    /** What the Keystore holds now. */
    fun state(): SignedApproval.Local = try {
        val key = store().getKey(ALIAS, null) as? PrivateKey
        if (key == null) {
            SignedApproval.Local.NONE
        } else {
            try {
                Signature.getInstance(ALGORITHM).initSign(key)
                SignedApproval.Local.READY
            } catch (e: KeyPermanentlyInvalidatedException) {
                SignedApproval.Local.INVALID
            }
        }
    } catch (e: Exception) {
        SignedApproval.Local.INVALID
    }

    /**
     * Makes a fresh key (replacing any old one) and returns its public half,
     * SPKI DER. Uses StrongBox when the phone has it, else the normal secure
     * area. Throws when Android cannot make the key (for example no screen lock).
     */
    fun create(context: Context): ByteArray {
        delete()
        val strongBox = context.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)
        val pair = try {
            generate(strongBox)
        } catch (e: ProviderException) {
            // StrongBoxUnavailableException is one of these: fall back once.
            if (!strongBox) throw e
            generate(false)
        }
        return pair.public.encoded
    }

    private fun generate(strongBox: Boolean): java.security.KeyPair {
        val builder = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)
            // 0 = a fresh check for every single use.
            .setUserAuthenticationParameters(
                0,
                KeyProperties.AUTH_BIOMETRIC_STRONG or KeyProperties.AUTH_DEVICE_CREDENTIAL,
            )
            .setInvalidatedByBiometricEnrollment(true)
        if (strongBox) builder.setIsStrongBoxBacked(true)
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, PROVIDER)
        generator.initialize(builder.build())
        return generator.generateKeyPair()
    }

    /** Deletes the key. Quiet when there is none. */
    fun delete() {
        runCatching { store().deleteEntry(ALIAS) }
    }

    /**
     * A signature ready for `BiometricPrompt.CryptoObject`. Throws
     * [KeyPermanentlyInvalidatedException] when Android has killed the key,
     * and another exception when there is none.
     */
    fun newSignature(): Signature {
        val key = store().getKey(ALIAS, null) as? PrivateKey
            ?: throw java.security.KeyStoreException("no approval key")
        return Signature.getInstance(ALGORITHM).apply { initSign(key) }
    }
}
