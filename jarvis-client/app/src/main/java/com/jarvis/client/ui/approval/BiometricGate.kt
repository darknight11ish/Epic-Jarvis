package com.jarvis.client.ui.approval

import android.content.Context
import android.util.Log
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.jarvis.client.data.CheckAvailability
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.CheckOutcome
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
 *
 * Which approvals ask, and what happens when the phone cannot check, are
 * decided in `data/Security.kt` (`SecurityRules`) from the owner's Security
 * settings. This file only shows the system's prompt and reports how it
 * ended ([CheckOutcome]). The same prompt also unlocks the app, shows Mind's
 * private lists, and confirms a loosened setting - see [check].
 */
object BiometricGate {

    /** One attempt's result: an outcome, or "try once more". */
    private sealed interface Attempt {
        data class Done(val outcome: CheckOutcome) : Attempt
        data object Transient : Attempt
    }

    /**
     * Whether this phone can check with [method] at all. Asked before a
     * setting is tightened, so the owner cannot lock themselves out.
     */
    fun availability(context: Context, method: CheckMethod): CheckAvailability =
        when (BiometricManager.from(context).canAuthenticate(allowed(method))) {
            BiometricManager.BIOMETRIC_SUCCESS -> CheckAvailability.READY
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> CheckAvailability.NOT_SET_UP
            // With the PIN allowed, "no hardware" still has a fix: a screen
            // lock. With fingerprint only, it has none.
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE ->
                if (method == CheckMethod.FINGERPRINT_OR_PIN) {
                    CheckAvailability.NOT_SET_UP
                } else {
                    CheckAvailability.NO_HARDWARE
                }
            BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED -> CheckAvailability.NO_HARDWARE
            else -> CheckAvailability.NOT_NOW
        }

    /**
     * What `canAuthenticate` says before any prompt, or null when the prompt
     * should be shown. Only "nothing enrolled" and "no hardware at all" are
     * reported as unavailable; every other not-now answer is treated as
     * temporary.
     */
    private fun beforePrompt(status: Int): Attempt? = when (status) {
        BiometricManager.BIOMETRIC_SUCCESS -> null
        BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED,
        BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE,
        // This Android cannot offer this kind of check at all - permanent,
        // like having no hardware.
        BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED,
        -> Attempt.Done(CheckOutcome.UNAVAILABLE)
        else -> Attempt.Transient
    }

    /** The check before approving [item], with its consequence on the prompt. */
    suspend fun confirm(activity: FragmentActivity, item: PendingItem, method: CheckMethod): CheckOutcome =
        check(
            activity,
            title = item.title,
            // The consequence, in the server's own words, on the prompt
            // itself - so the last thing seen before confirming is what this
            // costs if it is wrong.
            subtitle = item.risk.why.ifBlank { "Check the card before you confirm." },
            method = method,
        )

    /**
     * One fingerprint or PIN check, for anything: an approval, opening the
     * app, showing Mind's private lists, or loosening a setting.
     */
    suspend fun check(
        activity: FragmentActivity,
        title: String,
        subtitle: String,
        method: CheckMethod,
    ): CheckOutcome {
        val allowed = allowed(method)
        // At most two tries, and only for the temporary failures: a person
        // dismissing the prompt is an answer and is never asked again.
        for (attempt in 0 until 2) {
            if (attempt > 0) delay(RETRY_DELAY_MS)
            val status = BiometricManager.from(activity).canAuthenticate(allowed)
            val result = beforePrompt(status) ?: promptOnce(activity, title, subtitle, method)
            if (result is Attempt.Done) return result.outcome
            Log.w(TAG, "biometric check not available right now (attempt ${attempt + 1}, status $status)")
        }
        return CheckOutcome.FAILED
    }

    private suspend fun promptOnce(
        activity: FragmentActivity,
        title: String,
        subtitle: String,
        method: CheckMethod,
    ): Attempt =
        suspendCancellableCoroutine { cont ->
            val prompt = BiometricPrompt(
                activity,
                ContextCompat.getMainExecutor(activity),
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(
                        result: BiometricPrompt.AuthenticationResult,
                    ) {
                        if (cont.isActive) cont.resume(Attempt.Done(CheckOutcome.CONFIRMED))
                    }

                    override fun onAuthenticationError(code: Int, msg: CharSequence) {
                        Log.d(TAG, "biometric error $code: $msg")
                        if (!cont.isActive) return
                        // A device that cannot offer the prompt at all is
                        // "unavailable", not "refused" — the difference decides
                        // whether the user is stuck. A sensor that is busy
                        // right now is neither: it is tried once more, and
                        // then the decision is held, not waved through.
                        // "Cancel" on a Fingerprint-only prompt
                        // (ERROR_NEGATIVE_BUTTON) is CANCELLED, like any
                        // other dismissal.
                        val outcome = when (code) {
                            BiometricPrompt.ERROR_HW_NOT_PRESENT,
                            BiometricPrompt.ERROR_NO_BIOMETRICS,
                            BiometricPrompt.ERROR_NO_DEVICE_CREDENTIAL,
                            -> Attempt.Done(CheckOutcome.UNAVAILABLE)
                            BiometricPrompt.ERROR_HW_UNAVAILABLE -> Attempt.Transient
                            else -> Attempt.Done(CheckOutcome.CANCELLED)
                        }
                        cont.resume(outcome)
                    }

                    override fun onAuthenticationFailed() {
                        // A finger that did not match. The prompt stays up for
                        // another try, so nothing is resumed here.
                    }
                },
            )

            // No negative button with the PIN allowed, and that is not a
            // style choice. PromptInfo.Builder.build() THROWS
            // IllegalArgumentException when a negative button is set
            // alongside DEVICE_CREDENTIAL — the system supplies its own "Use
            // PIN" affordance and the two cannot coexist. This had both, and
            // build() sat outside the runCatching below, so the most
            // important safety control in the app threw on every single use,
            // on exactly the devices that have a fingerprint enrolled.
            // canAuthenticate() reports SUCCESS first, so the guard above
            // waved it straight through to the throw.
            //
            // Cancelling is still possible: the system prompt has its own
            // dismiss, and a dismissal arrives as ERROR_USER_CANCELED, which
            // is already handled as CANCELLED.
            //
            // "Fingerprint only" is the one case that NEEDS a negative
            // button, for the mirror-image reason: without DEVICE_CREDENTIAL
            // there is no system "Use PIN", and build() throws when the
            // negative text is missing.
            runCatching {
                val builder = BiometricPrompt.PromptInfo.Builder()
                    .setTitle(title)
                    .setSubtitle(subtitle)
                    .setAllowedAuthenticators(allowed(method))
                    .setConfirmationRequired(true)
                if (method == CheckMethod.FINGERPRINT_ONLY) builder.setNegativeButtonText("Cancel")
                prompt.authenticate(builder.build())
            }.onFailure {
                // Not CANCELLED - the owner refused nothing - and not
                // UNAVAILABLE either, which with every setting at its
                // default lets the decision through with no check at all.
                // Tried once more; if it fails again the decision is held
                // with a plain message (MainActivity), and the card is still
                // there to try again.
                Log.w(TAG, "could not show the biometric prompt", it)
                if (cont.isActive) cont.resume(Attempt.Transient)
            }

            cont.invokeOnCancellation { runCatching { prompt.cancelAuthentication() } }
        }

    private const val TAG = "JarvisBiometric"

    /** Long enough for a sensor another app was holding to be let go. */
    private const val RETRY_DELAY_MS = 600L

    /**
     * Weak biometrics are deliberately excluded in both methods. Face unlock
     * on many devices falls into that class and can be satisfied by a
     * photograph; the whole point here is the class of action that cannot
     * be undone. "Fingerprint only" also drops the PIN.
     *
     * DEVICE_CREDENTIAL stays in by default, deliberately. Without it, a
     * phone with no enrolled fingerprint reports the gate unavailable, and
     * with every setting at its default an unavailable gate lets the
     * decision through - so dropping the PIN in the name of strictness would
     * wave through exactly the devices with the weakest possession factor.
     * "Fingerprint only" is safe to offer because choosing it counts as
     * turning a lock on, and then an unavailable gate refuses instead
     * (`SecurityRules.afterApprovalCheck`).
     */
    private fun allowed(method: CheckMethod): Int = when (method) {
        CheckMethod.FINGERPRINT_OR_PIN ->
            BiometricManager.Authenticators.BIOMETRIC_STRONG or
                BiometricManager.Authenticators.DEVICE_CREDENTIAL
        CheckMethod.FINGERPRINT_ONLY -> BiometricManager.Authenticators.BIOMETRIC_STRONG
    }
}
