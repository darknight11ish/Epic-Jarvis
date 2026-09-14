package com.jarvis.client.ui.approval

import android.util.Log
import androidx.activity.ComponentActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.jarvis.client.net.PendingItem
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * A fingerprint instead of a tap, for the decisions that cannot be taken back.
 *
 * This is the one thing on the brief's list that a browser genuinely cannot do,
 * and it is worth having for a specific reason rather than because it is
 * available: the phone is the surface most likely to be handed to someone, left
 * unlocked on a desk, or tapped at from a notification shade. A biometric turns
 * "whoever is holding this" into "the owner" for the class of action where that
 * distinction matters.
 *
 * It is **not** a second authorisation layer and does not pretend to be. The
 * desktop's token is what authorises the request; this only decides whether the
 * person in front of the phone gets to send it.
 */
object BiometricGate {

    /** Which decisions are worth interrupting for. */
    fun required(item: PendingItem): Boolean {
        // Anything that leaves the machine or cannot be undone, plus anything
        // the server has not classified — which arrives as both by default.
        if (!item.risk.classified) return true
        if (item.risk.reach == "outbound") return true
        if (item.risk.reversible == "no") return true
        // A rush latch means outside text tried to hurry this decision. Slowing
        // it down is the entire response.
        if (item.raised != null) return true
        return false
    }

    enum class Outcome {
        /** The owner confirmed. */
        CONFIRMED,

        /** They dismissed it. Not an error — the decision simply is not taken. */
        CANCELLED,

        /**
         * No enrolled biometric, or the hardware is unavailable. The decision
         * proceeds: refusing to let the owner answer their own desktop because
         * they have no fingerprint enrolled would be a lock on the wrong door,
         * and the token already authorises the request.
         */
        UNAVAILABLE,
    }

    fun available(activity: ComponentActivity): Boolean =
        BiometricManager.from(activity).canAuthenticate(ALLOWED) ==
            BiometricManager.BIOMETRIC_SUCCESS

    suspend fun confirm(activity: ComponentActivity, item: PendingItem): Outcome {
        if (!available(activity)) return Outcome.UNAVAILABLE

        return suspendCancellableCoroutine { cont ->
            val prompt = BiometricPrompt(
                activity,
                ContextCompat.getMainExecutor(activity),
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(
                        result: BiometricPrompt.AuthenticationResult,
                    ) {
                        if (cont.isActive) cont.resume(Outcome.CONFIRMED)
                    }

                    override fun onAuthenticationError(code: Int, msg: CharSequence) {
                        Log.d(TAG, "biometric error $code: $msg")
                        if (!cont.isActive) return
                        // A device that cannot offer the prompt at all is
                        // "unavailable", not "refused" — the difference decides
                        // whether the user is stuck.
                        val outcome = when (code) {
                            BiometricPrompt.ERROR_HW_NOT_PRESENT,
                            BiometricPrompt.ERROR_HW_UNAVAILABLE,
                            BiometricPrompt.ERROR_NO_BIOMETRICS,
                            -> Outcome.UNAVAILABLE
                            else -> Outcome.CANCELLED
                        }
                        cont.resume(outcome)
                    }

                    override fun onAuthenticationFailed() {
                        // A finger that did not match. The prompt stays up for
                        // another try, so nothing is resumed here.
                    }
                },
            )

            val info = BiometricPrompt.PromptInfo.Builder()
                .setTitle(item.title)
                // The consequence, in the server's own words, on the prompt
                // itself — so the last thing seen before confirming is what
                // this costs if it is wrong.
                .setSubtitle(item.risk.why.ifBlank { item.summary })
                .setNegativeButtonText("Cancel")
                .setAllowedAuthenticators(ALLOWED)
                .setConfirmationRequired(true)
                .build()

            runCatching { prompt.authenticate(info) }
                .onFailure {
                    Log.w(TAG, "could not show the biometric prompt", it)
                    if (cont.isActive) cont.resume(Outcome.UNAVAILABLE)
                }

            cont.invokeOnCancellation { runCatching { prompt.cancelAuthentication() } }
        }
    }

    private const val TAG = "JarvisBiometric"

    /**
     * Weak biometrics are deliberately excluded. Face unlock on many devices
     * falls into that class and can be satisfied by a photograph; the whole
     * point here is the class of action that cannot be undone.
     */
    private const val ALLOWED = BiometricManager.Authenticators.BIOMETRIC_STRONG or
        BiometricManager.Authenticators.DEVICE_CREDENTIAL
}
