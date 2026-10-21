package com.jarvis.client.net

/**
 * The two mechanical guards against blind / stacked approvals (review ruling
 * 8.2, 2026-10-20) - the PHONE half, as far as the decision logic goes.
 *
 * The owner's incident: one "approve all" click approved three backup restores,
 * two imports and a device-key registration. The cards that REPLACE what is
 * already on the PC must therefore be told apart from ordinary cards and take
 * a second, explicit confirmation, so a single tap (or a swipe, which is the
 * gesture people make without reading) cannot restore a backup or forget a
 * range of memory.
 *
 * WHERE THE ANSWER COMES FROM. The PC marks every waiting row with `replaces`
 * (`jarvis_gate.pending()`; `backend/gate-touches.patch` carries it), so the
 * desktop, the HUD and this phone agree about the set and this file does not
 * invent a list the backend does not recognise. The three action names below
 * are the fallback for a PC too old to send the field; they are the REAL names
 * (`restore_backup`, not the review's `backup_restore`), and the voice-training
 * clear needs the PC's mark because it shares `change_own_config` with the
 * ordinary voice-settings cards.
 *
 * WHAT THE SCREEN DOES WITH IT ([com.jarvis.client.ui.approval.ApprovalCard]):
 * a plain "REPLACES CURRENT DATA" heading, and Approve takes two presses - the
 * first arms it and sends nothing, the second sends. Deny and a left swipe are
 * untouched: refusing is always the safe direction.
 */
object ReplaceConfirm {
    /** The plain heading. Words, never colour alone. */
    const val WARNING = "REPLACES CURRENT DATA"

    /** What the first press says, before anything is sent. */
    const val NOTE = "Approving this replaces what is there now. Press Approve again to confirm."

    /** The Approve button's words between the two presses. */
    const val CONFIRM_LABEL = "Confirm replace"

    /** The fallback for a PC too old to send `replaces` - real action names. */
    private val FALLBACK_ACTIONS = setOf(
        "restore_backup",
        "register_approval_key",
        "memory_forget_range",
    )

    /**
     * Does deciding this card replace or delete what is already on the PC?
     *
     * `replaces` from the PC always wins. Without it (an older backend) the
     * three real action names are recognised here. Anything else - including a
     * missing or unknown card - is an ORDINARY card, exactly as it was before
     * this guard existed: nothing is guessed in the dangerous direction.
     */
    fun applies(item: PendingItem?): Boolean {
        if (item == null) return false
        if (item.replaces) return true
        return item.action in FALLBACK_ACTIONS
    }
}
