package com.jarvis.client.service

import android.content.Context
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.AppControl
import com.jarvis.client.data.AppControlStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/**
 * Runs ONE carded step. This is the ONLY thing that ever drives
 * [JarvisAccessibilityService] to act, and it acts only on a step the PC's
 * `/api/app-control/step` route returned.
 *
 * It never plans: the plan comes from the PC (the chat tool that will call
 * [start] is the next slice - see the app-control report). It never retries a
 * changed screen, never picks another control and never auto-approves: the PC
 * raises ONE approval card and nothing runs until the owner says yes. The
 * allow-list is enforced here before the request leaves the phone, and again by
 * the PC, and the phone's option and Android's own accessibility switch are
 * both checked first.
 *
 * NOTHING about a screen or typed text is logged. A successful [Reply.Done]
 * means "the approved action was performed", never a claim about what the app
 * then did.
 */
object AppControlExecutor {

    /** What one run came to, in plain words for the screen. */
    sealed interface Reply {
        /** The approved step was performed and the PC was told so. */
        data class Done(val sentence: String) : Reply

        /** Nothing ran, or the run stopped; [sentence] says why. */
        data class Stopped(val sentence: String) : Reply

        /** Nothing ran, and the reason is one of the fixed refusals. */
        data class Refused(val sentence: String) : Reply
    }

    /** Asked of every poll; set by [stop] and never cleared, so a stop is final for that run. */
    @Volatile
    private var stopRequested: Boolean = false

    /** The phone's own Stop. A stop is the safe direction, so it needs no card from the PC. */
    fun stop() {
        stopRequested = true
    }

    /**
     * Asks the PC to act once, waits for the owner's card, performs the ONE
     * approved step and reports the result. The caller supplies the plan the
     * PC's chat proposed; nothing here invents one.
     */
    suspend fun start(
        context: Context,
        plan: AppControl.Step,
        why: String = "",
    ): Reply {
        stopRequested = false
        val store = AppControlStore(context)
        val service = JarvisAccessibilityService.instance()

        // The phone's own checks, before anything is read or sent.
        val foreground = withContext(Dispatchers.Main.immediate) {
            service?.snapshot()?.app.orEmpty()
        }
        val refusal = AppControl.whyNotAllowed(
            optionOn = store.optionOn(),
            android = store.androidState(),
            allowed = store.entries(),
            foreground = foreground,
            stale = JarvisRuntime.stale.value,
            serviceConnected = service != null,
        )
        if (refusal != null) return Reply.Refused(AppControl.said(refusal))
        if (!AppControl.ACTIONS.contains(plan.action)) {
            return Reply.Refused(AppControl.said(AppControl.Why.VERB))
        }
        if (plan.action == "type" && plan.text.isNullOrEmpty()) {
            return Reply.Refused(AppControl.said(AppControl.Why.VERB))
        }
        if (plan.target?.id.isNullOrBlank() && plan.target?.text.isNullOrBlank() &&
            plan.action != "back" && plan.action != "home"
        ) {
            return Reply.Refused(AppControl.said(AppControl.Why.VERB))
        }
        // Checked BEFORE the plan is sent, so the PC never raises a card for a
        // step it would have to refuse.
        if (looksLikePasswordTarget(plan)) {
            return Reply.Refused(AppControl.said(AppControl.Why.PASSWORD))
        }

        val snapshot = withContext(Dispatchers.Main.immediate) { service?.snapshot() }
            ?: return Reply.Refused(AppControl.SNAPSHOT_EMPTY)
        val app = snapshot.app
        if (!store.isAllowed(app)) return Reply.Refused(AppControl.said(AppControl.Why.NOT_LISTED))
        val appName = store.entries().firstOrNull { it.packageName == app }?.label ?: store.labelOf(app)
        val body = AppControl.runBody(store.entries(), app, appName, plan, snapshot)

        val (runStatus, runBody) = JarvisRuntime.api.appControlRun(body)
        val first = AppControl.parseRun(runStatus, runBody)
        val run = when (first) {
            is AppControl.RunReply.Pending -> first
            is AppControl.RunReply.Off ->
                return Reply.Refused(first.sentence.ifBlank { AppControl.said(AppControl.Why.OPTION_OFF) })
            is AppControl.RunReply.Refused -> return Reply.Refused(first.sentence)
            is AppControl.RunReply.Failed -> return Reply.Refused(first.sentence)
            AppControl.RunReply.RouteMissing -> return Reply.Refused(AppControl.NO_ROUTE)
            AppControl.RunReply.Unknown -> return Reply.Refused(AppControl.NO_ANSWER)
        }

        val deadline = System.currentTimeMillis() + CARD_WAIT_MS
        while (true) {
            if (stopRequested) {
                bestEffortStop(run.runId)
                return Reply.Stopped("Stopped. Nothing more will run.")
            }
            if (JarvisRuntime.stale.value) {
                bestEffortStop(run.runId)
                return Reply.Stopped(AppControl.said(AppControl.Why.STALE))
            }
            if (System.currentTimeMillis() > deadline) {
                bestEffortStop(run.runId)
                return Reply.Stopped(
                    "Your PC is still waiting for you to answer the card, so the run was " +
                        "stopped. Nothing ran. Ask again when you are ready to decide.",
                )
            }
            delay(POLL_MS)
            val fresh = withContext(Dispatchers.Main.immediate) { service?.snapshot() }
            val (stepStatus, stepBody) = if (fresh == null) {
                // The screen went away (locked, another window): ask without a snapshot.
                0 to null
            } else {
                JarvisRuntime.api.appControlStep(AppControl.stepBody(run.runId, fresh))
            }
            when (val reply = AppControl.parseStep(stepStatus, stepBody)) {
                AppControl.StepReply.Pending -> continue
                AppControl.StepReply.RouteMissing -> return Reply.Refused(AppControl.NO_ROUTE)
                AppControl.StepReply.Unknown -> {
                    if (fresh == null) {
                        // No snapshot to send: treat as a changed screen and stop.
                        bestEffortStop(run.runId)
                        return Reply.Stopped(AppControl.said(AppControl.Why.TARGET_CHANGED))
                    }
                    continue
                }
                is AppControl.StepReply.Failed -> return Reply.Stopped(reply.sentence)
                is AppControl.StepReply.Stopped -> return Reply.Stopped(reply.sentence)
                is AppControl.StepReply.Ended -> return Reply.Stopped(reply.sentence.ifBlank { stoppedWords(reply.status) })
                is AppControl.StepReply.Delivered ->
                    return Reply.Stopped(if (reply.sentence.isBlank()) "That run already ran its one step." else reply.sentence)
                is AppControl.StepReply.Step -> {
                    // The ONE step the PC approved must be the one we asked for;
                    // anything else is refused, never adapted.
                    if (!AppControl.matches(plan, reply.step)) {
                        bestEffortStop(run.runId)
                        return Reply.Refused(AppControl.said(AppControl.Why.NOT_PLANNED))
                    }
                    val outcome = withContext(Dispatchers.Main.immediate) {
                        JarvisAccessibilityService.instance()?.performStep(reply.step, app)
                    } ?: JarvisAccessibilityService.Outcome.Refused(
                        AppControl.said(AppControl.Why.NO_SERVICE),
                    )
                    when (outcome) {
                        JarvisAccessibilityService.Outcome.Done -> {
                            reportResult(run.runId, failed = false)
                            return Reply.Done("Done. That was the one step you approved.")
                        }
                        is JarvisAccessibilityService.Outcome.Refused -> {
                            reportResult(run.runId, failed = true)
                            return Reply.Refused(outcome.sentence)
                        }
                    }
                }
            }
        }
    }

    /**
     * A password target is refused before the card is raised: the step names a
     * field, and either the target's own words say password/one-time code or
     * the action on it is `type`. `type` alone is not enough to call it a
     * password field - a NON-password text field is exactly what `type` is for
     * - so this is a word check plus the field's own words, and the service
     * checks Android's own `isPassword` flag again immediately before acting.
     */
    private fun looksLikePasswordTarget(plan: AppControl.Step): Boolean {
        val words = buildString {
            append(plan.target?.text.orEmpty()); append(' ')
            append(plan.target?.id.orEmpty())
        }.lowercase()
        return PASSWORD_WORDS.any { words.contains(it) }
    }

    private suspend fun bestEffortStop(runId: String) {
        runCatching { JarvisRuntime.api.appControlStep(AppControl.stopBody(runId)) }
    }

    private suspend fun reportResult(runId: String, failed: Boolean) {
        runCatching { JarvisRuntime.api.appControlStep(AppControl.resultBody(runId, failed)) }
    }

    private fun stoppedWords(status: String): String = when (status) {
        "denied" -> "You said no, so nothing ran."
        "timed_out" -> "The card timed out, so nothing ran."
        "refused" -> "Your PC refused that step, so nothing ran."
        "failed" -> "The step failed, and nothing else will run."
        else -> "The run is over. Nothing else will run."
    }

    /** After this long waiting for the card, the run is stopped rather than left hanging. */
    private const val CARD_WAIT_MS = 240_000L

    /** How often the phone asks for the ONE step while the card waits. */
    private const val POLL_MS = 1_500L

    private val PASSWORD_WORDS = listOf(
        "password", "passcode", "passphrase", "credential", "verification code",
        "one-time code", "one time code", "otp", "2fa", "two-factor", "two factor",
    )
}
