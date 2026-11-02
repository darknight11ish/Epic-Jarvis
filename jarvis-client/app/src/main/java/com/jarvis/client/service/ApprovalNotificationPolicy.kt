package com.jarvis.client.service

import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.PendingItem

/**
 * What one approval notification may offer, decided as data so the JVM tests
 * can hold every branch without a phone.
 *
 * The owner's ask of 2026-11-02: *"make sure i can approve jarvis cards
 * through an android notification with a deny or approve button or tap too
 * see more button if the summary that's short enough to fit into an android
 * notification isn't long enough."*
 *
 * Gemini's security envelope for it is binding, and this object is its one
 * reading:
 *
 *  1. Deny is always safe, so it may run from the lock screen.
 *  2. Approve needs the device unlocked: [Offered.requiresUnlock] is true for
 *     every approve action, and the notifier puts that on the action itself
 *     (`setAuthenticationRequired(true)`), so Android will not deliver it
 *     while the phone is locked - no Jarvis code runs to enforce it.
 *  3. A small read-only card (the same [SecurityRules.isSmall] exemption the
 *     owner asked for on 2026-11-01, `approve = false` still) may submit
 *     directly from the notification. EVERY other card opens Jarvis and runs
 *     the same `BiometricPrompt` the card's own Approve runs -
 *     [notificationApproveNeedsCheck] is why a write card asks even when the
 *     owner's setting would not ask on the card itself.
 *  4. A card whose own words are longer than [MAX_SHOWN_CHARS] is never
 *     approved sight-unseen: its Approve is replaced by Review in Jarvis.
 *  5. A redacted notification ([locked]) offers Review and Deny, and no
 *     Approve: approving words the owner cannot see is exactly the blind
 *     approval (4) forbids. With App lock on - the default - that is what the
 *     approval notification offers until the owner turns it off; the app lock
 *     is the owner's own rule, and this file does not weaken it.
 *
 * It also answers the lifecycle half: [cleared] names the approval ids whose
 * notification must go because `/api/pending` no longer carries the card.
 *
 * The notification text itself is NOT chosen here. [ApprovalNotifier.textFor]
 * decides it, from the desktop's `notice` and nothing composed on the phone;
 * this file only decides which buttons may sit under it.
 */
object ApprovalNotificationPolicy {

    /**
     * What a notification body can show before it stops being something the
     * owner can read in the shade. Gemini's ruling puts the line at 240
     * characters; above it the Approve button becomes Review in Jarvis, so a
     * clipped filename or command is never approved sight-unseen.
     */
    const val MAX_SHOWN_CHARS = 240

    /**
     * The lock screen's version of an approval notification. Redacted by
     * construction - no card title, no summary, no action name - and the one
     * sentence the owner asked to see there.
     */
    const val PUBLIC_WORDS = "Jarvis: 1 approval waiting"

    /** One button a notification may carry. */
    enum class Action {
        /** Refusing without reading is safe, so this needs no unlock. */
        DENY,

        /** Small read-only card: the tap itself may send the decision. */
        APPROVE_DIRECT,

        /** Everything else: open Jarvis on this card and run its own gate. */
        APPROVE_IN_APP,

        /** The words do not fit (or cannot be approved here): open the card. */
        REVIEW,
    }

    /** One button, and whether Android must see an unlocked device first. */
    data class Offered(val action: Action, val requiresUnlock: Boolean)

    data class Plan(val actions: List<Offered>) {
        fun offers(action: Action): Boolean = actions.any { it.action == action }
    }

    /**
     * The text a notification shows, title and body together, the way the
     * expanded `BigTextStyle` would read it. Kept here so the 240-character
     * rule is one rule, not a number copied into the notifier.
     */
    fun shownText(title: String, body: String): String =
        if (title.isBlank()) body else "$title\n$body"

    /**
     * The buttons for [item] right now.
     *
     * @param locked [SecurityRules.notificationsLocked]'s answer: App lock,
     *   hidden lists, or a phone with no secure lock screen. Redacted words
     *   never carry an Approve.
     */
    fun plan(
        item: PendingItem,
        security: Security,
        locked: Boolean,
        title: String,
        body: String,
    ): Plan {
        val tooLong = shownText(title, body).trim().length > MAX_SHOWN_CHARS
        // The only cards this surface may approve at all: the words fit, the
        // owner can see them, and neither "only the PC may approve this" nor
        // "which plan did you mean" applies.
        val mayOfferApprove = !locked && !tooLong && !item.pcOnly && !item.needsChoice
        val direct = mayOfferApprove &&
            SecurityRules.isSmall(item) &&
            !SecurityRules.approvalNeedsCheck(security, item)
        val inApp = mayOfferApprove && !direct
        // A redacted card gets Review, never Approve: the owner can still be
        // taken to the card, where the app lock and the card's own gate apply,
        // but nothing is approved from words the notification did not show.
        val review = locked || tooLong || item.pcOnly || item.needsChoice

        val offered = buildList {
            when {
                direct -> add(Offered(Action.APPROVE_DIRECT, requiresUnlock = true))
                inApp -> add(Offered(Action.APPROVE_IN_APP, requiresUnlock = true))
                review -> add(Offered(Action.REVIEW, requiresUnlock = false))
            }
            // `notice.deny_ok == false` is the desktop saying refusing without
            // reading is not safe for this one. Absent notice (an older PC)
            // keeps today's Deny.
            if (item.notice?.denyOk != false) {
                add(Offered(Action.DENY, requiresUnlock = false))
            }
        }
        return Plan(offered)
    }

    /**
     * Whether an Approve that came from a notification must run the card's
     * own check even where the owner's setting would not ask for one.
     *
     * True for every card that is not [SecurityRules.isSmall] - the write,
     * config, send-file and phone-app cards in Gemini's ruling - and for a
     * small card when the owner has chosen to check every approval. The
     * notification is a surface where the card was not read on screen, so
     * "the app would not have asked" is not a reason to wave it through.
     */
    fun notificationApproveNeedsCheck(item: PendingItem, security: Security): Boolean =
        !SecurityRules.isSmall(item) || SecurityRules.approvalNeedsCheck(security, item)

    /**
     * The approval ids whose notifications must be cancelled because the
     * phone's live queue no longer carries them.
     *
     * `Assigned` is the notifier's own id map; an id that is gone from
     * [pending] has been answered on either app or has expired, and a
     * notification that outlives its card is a trap: its buttons point at a
     * decision nothing can deliver.
     */
    fun cleared(assigned: Collection<String>, pending: Collection<PendingItem>): Set<String> {
        val live = pending.mapTo(HashSet()) { it.id }
        return assigned.filterTo(LinkedHashSet()) { it !in live }
    }
}
