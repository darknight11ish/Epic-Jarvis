package com.jarvis.client.ui.approval

import android.util.Log
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.jarvis.client.net.PendingItem
import kotlin.coroutines.resume
import kotlinx.coroutines.delay
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
         * This phone has no way to check at all: nothing enrolled - no
         * fingerprint and no screen-lock PIN - or no hardware. The decision
         * proceeds: refusing to let the owner answer their own desktop because
         * they have no fingerprint enrolled would be a lock on the wrong door,
         * and the token already authorises the request. (The owner's decision.)
         */
        UNAVAILABLE,

        /**
         * The check exists but could not be shown just now - the sensor was
         * busy or reported itself unavailable, or the prompt failed to open -
         * even after one retry. Nothing is sent.
         *
         * This used to be folded into [UNAVAILABLE], which lets the decision
         * through. `ERROR_HW_UNAVAILABLE` is often temporary (another app
         * holding the sensor, a moment after unlocking), so a passing glitch
         * waved a heavy approval through with no check at all.
         */
        FAILED,
    }

    /** One attempt's result: an [Outcome], or "try once more". */
    private sealed interface Attempt {
        data class Done(val outcome: Outcome) : Attempt
        data object Transient : Attempt
    }

    fun available(activity: FragmentActivity): Boolean =
        BiometricManager.from(activity).canAuthenticate(ALLOWED) ==
            BiometricManager.BIOMETRIC_SUCCESS

    /**
     * What `canAuthenticate` says before any prompt, or null when the prompt
     * should be shown. Only "nothing enrolled" and "no hardware at all" pass
     * without a check; every other not-now answer is treated as temporary.
     */
    private fun beforePrompt(status: Int): Attempt? = when (status) {
        BiometricManager.BIOMETRIC_SUCCESS -> null
        BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED,
        BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE,
        // This Android cannot offer this kind of check at all - permanent,
        // like having no hardware.
        BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED,
        -> Attempt.Done(Outcome.UNAVAILABLE)
        else -> Attempt.Transient
    }

    suspend fun confirm(activity: FragmentActivity, item: PendingItem): Outcome {
        // At most two tries, and only for the temporary failures: a person
        // dismissing the prompt is an answer and is never asked again.
        for (attempt in 0 until 2) {
            if (attempt > 0) delay(RETRY_DELAY_MS)
            val status = BiometricManager.from(activity).canAuthenticate(ALLOWED)
            val result = beforePrompt(status) ?: promptOnce(activity, item)
            if (result is Attempt.Done) return result.outcome
            Log.w(TAG, "biometric check not available right now (attempt ${attempt + 1}, status $status)")
        }
        return Outcome.FAILED
    }

    private suspend fun promptOnce(activity: FragmentActivity, item: PendingItem): Attempt =
        suspendCancellableCoroutine { cont ->
            val prompt = BiometricPrompt(
                activity,
                ContextCompat.getMainExecutor(activity),
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(
                        result: BiometricPrompt.AuthenticationResult,
                    ) {
                        if (cont.isActive) cont.resume(Attempt.Done(Outcome.CONFIRMED))
                    }

                    override fun onAuthenticationError(code: Int, msg: CharSequence) {
                        Log.d(TAG, "biometric error $code: $msg")
                        if (!cont.isActive) return
                        // A device that cannot offer the prompt at all is
                        // "unavailable", not "refused" — the difference decides
                        // whether the user is stuck. A sensor that is busy
                        // right now is neither: it is tried once more, and
                        // then the decision is held, not waved through.
                        val outcome = when (code) {
                            BiometricPrompt.ERROR_HW_NOT_PRESENT,
                            BiometricPrompt.ERROR_NO_BIOMETRICS,
                            BiometricPrompt.ERROR_NO_DEVICE_CREDENTIAL,
                            -> Attempt.Done(Outcome.UNAVAILABLE)
                            BiometricPrompt.ERROR_HW_UNAVAILABLE -> Attempt.Transient
                            else -> Attempt.Done(Outcome.CANCELLED)
                        }
                        cont.resume(outcome)
                    }

                    override fun onAuthenticationFailed() {
                        // A finger that did not match. The prompt stays up for
                        // another try, so nothing is resumed here.
                    }
                },
            )

            // No negative button, and that is not a style choice.
            // PromptInfo.Builder.build() THROWS IllegalArgumentException when a
            // negative button is set alongside DEVICE_CREDENTIAL — the system
            // supplies its own "Use PIN" affordance and the two cannot
            // coexist. This had both, and build() sat outside the runCatching
            // below, so the most important safety control in the app threw on
            // every single use, on exactly the devices that have a fingerprint
            // enrolled. canAuthenticate() reports SUCCESS first, so the guard
            // above waved it straight through to the throw.
            //
            // Cancelling is still possible: the system prompt has its own
            // dismiss, and a dismissal arrives as ERROR_USER_CANCELED, which
            // is already handled as CANCELLED.
            runCatching {
                val info = BiometricPrompt.PromptInfo.Builder()
                    .setTitle(item.title)
                    // The consequence, in the server's own words, on the
                    // prompt itself — so the last thing seen before confirming
                    // is what this costs if it is wrong.
                    .setSubtitle(item.risk.why.ifBlank { "Check the card before you confirm." })
                    .setAllowedAuthenticators(ALLOWED)
                    .setConfirmationRequired(true)
                    .build()
                prompt.authenticate(info)
            }.onFailure {
                // Not CANCELLED - the owner refused nothing - and no longer
                // UNAVAILABLE either, which let the decision through with no
                // check at all. Tried once more; if it fails again the
                // decision is held with a plain message (MainActivity), and
                // the card is still there to try again.
                Log.w(TAG, "could not show the biometric prompt", it)
                if (cont.isActive) cont.resume(Attempt.Transient)
            }

            cont.invokeOnCancellation { runCatching { prompt.cancelAuthentication() } }
        }

    private const val TAG = "JarvisBiometric"

    /** Long enough for a sensor another app was holding to be let go. */
    private const val RETRY_DELAY_MS = 600L

    /**
     * Weak biometrics are deliberately excluded. Face unlock on many devices
     * falls into that class and can be satisfied by a photograph; the whole
     * point here is the class of action that cannot be undone.
     */
    private const val ALLOWED = BiometricManager.Authenticators.BIOMETRIC_STRONG or
        BiometricManager.Authenticators.DEVICE_CREDENTIAL

    /**
     * DEVICE_CREDENTIAL stays in deliberately. Without it, a phone with no
     * enrolled fingerprint reports the gate unavailable, and an unavailable
     * gate lets the decision through — so removing the PIN fallback in the
     * name of strictness would wave through exactly the devices with the
     * weakest possession factor.
     */
}
