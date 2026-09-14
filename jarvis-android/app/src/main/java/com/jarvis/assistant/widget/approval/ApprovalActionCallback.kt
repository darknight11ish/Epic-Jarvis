package com.jarvis.assistant.widget.approval

import android.content.Context
import androidx.glance.GlanceId
import androidx.glance.action.ActionParameters
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.updateAll
import com.jarvis.assistant.JarvisRuntime

/**
 * Home-screen decisions go through the same signing path as every other surface.
 *
 * This deliberately does not build its own HMAC. A second signing implementation
 * is a second thing to keep in step with the desktop's verifier, and the one in
 * [JarvisRuntime.submitApprovalDecision] is already fail-closed, nonce-bearing,
 * queued when offline, and pinned by unit tests.
 */
class ApprovalActionCallback : ActionCallback {

    override suspend fun onAction(
        context: Context,
        glanceId: GlanceId,
        parameters: ActionParameters,
    ) {
        val id = parameters[PARAM_ID] ?: return
        val approved = parameters[PARAM_DECISION] ?: return

        // The callback is already suspending and the system holds a wakelock for
        // its duration. Detaching onto a bare CoroutineScope here would let the
        // process be reaped mid-send, losing the decision.
        JarvisRuntime.initialize(context)
        JarvisRuntime.submitApprovalDecision(id, approved)

        // submitApprovalDecision leaves the request pending when it cannot sign,
        // so redraw either way: the widget shows the next item, or the reason.
        ApprovalWidget().updateAll(context)
    }

    companion object {
        val PARAM_ID = ActionParameters.Key<String>("approval_id")
        val PARAM_DECISION = ActionParameters.Key<Boolean>("approval_decision")
    }
}
