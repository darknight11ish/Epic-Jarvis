package com.jarvis.client.net

/**
 * Whether an approval card actually says WHAT it is asking the owner to agree to.
 *
 * THE HOLE THIS CLOSES, measured on the owner's phone on 2026-11-18. Two
 * `change_own_config` cards were waiting - one asking to change his cloud
 * settings - and one of them drew **no detail at all** while still drawing a
 * normal Approve. Pressing it would have agreed to a change nobody could see: a
 * blank cheque. The backend had sent the detail for both; the phone dropped it
 * on the way to the screen (see `normalisePendingRow`'s own comment and
 * `ApprovalCard`'s use of [CardSummary.shown]). That drop is fixed at its
 * cause; this object is the rule that makes the failure safe if it ever
 * happens again, because a card nobody can read must not be approvable.
 *
 * THE RULE, in one place so the composable and the JVM test cannot disagree:
 *
 *  - the detail is READABLE when [words] can say it in words a person reads -
 *    the same [CardBodyWords] reading the card's body already uses, so a
 *    command, a diff or a sentence is readable word for word, and machine JSON
 *    with nothing sayable in it (or nothing at all) is not;
 *  - readable: the card offers **Approve** exactly as it always did;
 *  - not readable: the card offers **Refresh** in Approve's place and keeps
 *    **Deny**, and says [MISSING_LINE] in plain words. Approve is NOT drawn
 *    disabled - a faded control captioned by a line nobody connects to it does
 *    not read as "you cannot act" (the same lesson DEF-010 taught for expired
 *    cards), so the button is replaced rather than dimmed.
 *
 * WHY THE DETAIL AND NOT THE PC'S NOTICE. `notice.summary`/`notice.full` are
 * built from the ACTION NAME and the risk table, never from the payload
 * (`jarvis_gate.notice_for`), so they can say "Jarvis wants to change one of its
 * settings" but they cannot say WHICH setting or to what - that sentence is the
 * row's `detail`. A card whose notice is readable but whose detail is not still
 * cannot be judged, which is exactly the measured cloud card: its notice read
 * "change one of its settings" while the actual change lived in the detail that
 * was dropped.
 *
 * Pure Kotlin, no Android types, so a plain JVM test holds every rule.
 */
object CardDetail {

    /**
     * What the card says instead of a body when the detail did not arrive.
     *
     * The owner's words for this shape, in the brief that asked for the fix:
     * *"Jarvis did not describe this change. Refresh, or deny it and ask
     * again."* - the PC's [CardWords.NO_DETAIL], so the desktop says the same
     * sentence. It names both honest ways out - re-read the queue, or refuse and
     * ask again - and it never pretends the missing detail is not missing.
     */
    const val MISSING_LINE: String = CardWords.NO_DETAIL

    /** The action drawn in Approve's place on a card with no readable detail. */
    const val REFRESH: String = CardWords.REFRESH

    /**
     * A card's `detail` as words a person reads: a command, a diff or a
     * sentence word for word; a JSON object said in plain words; machine text
     * with nothing sayable in it as "". Never raw JSON.
     */
    fun words(detail: String?): String = CardBodyWords.words(detail)

    /** True when this card really says what it would change. */
    fun readable(detail: String?): Boolean = words(detail).isNotBlank()

    /**
     * What a card with this `detail` may offer.
     *
     * **Deny is always kept**: refusing is the safe direction and needs no
     * reading (the gate and every client already say so - `notice.deny_ok`).
     * [approve] and [refresh] are the two ways the card can read differently:
     * a described card approves, and an undescribed one refreshes.
     */
    data class Actions(val approve: Boolean, val refresh: Boolean, val deny: Boolean)

    fun actions(detail: String?): Actions =
        if (readable(detail)) {
            Actions(approve = true, refresh = false, deny = true)
        } else {
            Actions(approve = false, refresh = true, deny = true)
        }
}
