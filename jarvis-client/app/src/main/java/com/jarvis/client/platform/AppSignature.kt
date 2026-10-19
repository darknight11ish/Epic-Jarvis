package com.jarvis.client.platform

import android.content.Context
import android.content.pm.PackageManager
import java.security.MessageDigest

/**
 * The signing certificate the RUNNING app actually has (apps security audit
 * H1; Gemini's release-safety ruling of 2026-10-18).
 *
 * The update body and the release page name the published APK's certificate
 * SHA-256; this is the phone's own answer to "what signed the copy I am
 * holding", so a whole release-key rotation becomes visible in Settings ->
 * About instead of being invisible until an update refuses. It reads Android's
 * own `PackageManager` signatures - no new permission, nothing sent anywhere,
 * and no key material: a certificate digest is public (it is in every APK).
 *
 * The SHA-256 helper and the 8-16 character shortening are plain Kotlin so
 * [com.jarvis.client.AppSignatureTest] runs on the JVM; only [installed] needs
 * Android.
 */
object AppSignature {

    /** The plain label beside the short digest. */
    const val LABEL = "Signed by"

    /** How many hex characters the settings line shows: enough to compare, short enough to read. */
    const val SHORT_CHARS = 12

    /** SHA-256 over the DER certificate, lowercase 64-hex, or null when there is none. */
    fun sha256(certDer: ByteArray?): String? {
        if (certDer == null || certDer.isEmpty()) return null
        return MessageDigest.getInstance("SHA-256")
            .digest(certDer)
            .joinToString("") { "%02x".format(it) }
    }

    /**
     * The first [chars] (8..16) lowercase hex characters of [fingerprint], or
     * null when it is missing or not a hex digest. The range is enforced so a
     * future caller cannot show a 4-character "signature" that matches
     * everything.
     */
    fun short(fingerprint: String?, chars: Int = SHORT_CHARS): String? {
        if (fingerprint.isNullOrBlank()) return null
        val clean = fingerprint.trim().lowercase()
        if (!clean.matches(Regex("^[0-9a-f]+$"))) return null
        return clean.take(chars.coerceIn(8, 16))
    }

    /** "Signed by abc123def456" for Settings, or null when it cannot be read. */
    fun line(fingerprint: String?, chars: Int = SHORT_CHARS): String? =
        short(fingerprint, chars)?.let { "$LABEL $it" }

    /** The running APK's signing-certificate SHA-256, or null when Android cannot say. */
    fun installed(context: Context): String? = runCatching {
        val app = context.applicationContext
        val info = app.packageManager.getPackageInfo(
            app.packageName,
            PackageManager.GET_SIGNING_CERTIFICATES,
        )
        val signing = info.signingInfo ?: return@runCatching null
        val cert = (
            if (signing.hasMultipleSigners()) {
                signing.apkContentsSigners
            } else {
                signing.signingCertificateHistory
            }
            )?.firstOrNull() ?: return@runCatching null
        sha256(cert.toByteArray())
    }.getOrNull()
}
