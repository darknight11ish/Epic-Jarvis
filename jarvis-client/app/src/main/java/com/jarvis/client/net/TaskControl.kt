package com.jarvis.client.net

/**
 * The words the phone shows for Pause, Resume, Stop, a task note and a note
 * on an approval card - `backend/task-control.patch` on the desktop branch.
 *
 * Kept apart from [com.jarvis.client.JarvisRuntime] so they can be unit
 * tested without a running app, and so what each button claims is written
 * down in one place next to what the server actually does:
 *
 * - **Stop** and **Pause** take effect at the task's next step. No approval
 *   card. Nothing here says "stopped" or "paused": the screen changes only
 *   when the desktop reports it (`activity: "paused"`), never on a click.
 * - **Resume** does not carry on. The desktop raises one approval card
 *   listing the steps that are left, and runs them only if it is approved.
 * - A **note** never approves, denies or changes a step.
 */
object TaskControl {
    /** After a Resume request lands: nothing has run yet. */
    const val RESUME_ASKED =
        "Resume asks first: approve the card that lists the steps left. Nothing has run yet."

    /** After a note lands on an approval card. */
    const val NOTE_KEPT =
        "Note kept with this card. Nothing was approved or denied - Jarvis reads it with your answer. To have it plan differently, deny the card."

    /** Resume on a link that cannot be confirmed live - rule 4. */
    const val RESUME_WHILE_STALE =
        "Not connected to the desktop, so resuming waits until the link is back. Stop still works."

    /**
     * What a failed task request means, where the generic wording would be
     * wrong. `null` means "use the generic sentence".
     *
     * A 409 from these routes is not "already handled elsewhere" (what it
     * means on approve/deny): it means there was nothing to act on - nothing
     * running, nothing paused, or a resume card already waiting. A 404 means
     * the desktop's backend does not have the task routes installed.
     */
    fun failure(e: ApiError, amend: Boolean = false): String? = when (e) {
        ApiError.NotFound ->
            "This desktop does not support that yet - its backend needs the task-control patch."
        ApiError.AlreadyHandled ->
            if (amend) "That card is no longer waiting - it was answered or it expired."
            else "Nothing to act on: nothing is running or paused right now, or that was already asked for."
        else -> null
    }
}
