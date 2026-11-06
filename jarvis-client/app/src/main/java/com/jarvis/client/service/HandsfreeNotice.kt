package com.jarvis.client.service

import com.jarvis.client.net.CardWords
import com.jarvis.client.net.Handsfree
import com.jarvis.client.net.SmsSend

/**
 * The words a hands-free notification may carry, once the app's ONE redaction
 * rule has been applied.
 *
 * WHY THIS IS ITS OWN, PURE OBJECT. [HandsfreeService] is an Android `Service`:
 * a JVM test cannot build one, so a rule that lived only inside its `post()`
 * could be deleted by a later edit with nothing failing - which is exactly how
 * the leak this fixes got in. Every branch below is reachable from
 * `HandsfreeNoticeTest`, on the JVM, in CI's required `phone-unit-tests` job.
 *
 * WHAT IS AT STAKE, said plainly. The waiting card's body is the PC's own `say`
 * - a whole sentence that can name a person, a file or a message - and a text
 * message's receipt carries the recipient's name and the words sent. With App
 * lock on, or "Hide memory lists and chat history", or a phone whose own lock
 * screen is not secure, none of that may be drawn anywhere a stranger can read
 * it. `data/Security.kt`'s [com.jarvis.client.data.SecurityRules.notificationsLocked]
 * is the rule, and [LOCKED] is what such a phone gets instead.
 *
 * [PUBLIC] is the SECOND half of the same promise: the notification itself
 * always carries `VISIBILITY_PRIVATE` and this redacted public version, so the
 * lock screen never draws the real body even on a phone whose settings say the
 * words are fine. That is the shape `ApprovalNotifier` already uses for every
 * approval notification (its `redacted()` copy), and a waiting hands-free card
 * IS an approval waiting - which is why the sentence is that notifier's own
 * [ApprovalNotificationPolicy.PUBLIC_WORDS] rather than a second dialect of it.
 */
object HandsfreeNotice {

    /** One notification's title and body, after redaction. Both are never blank. */
    data class Words(val title: String, val body: String)

    /**
     * What a locked or private phone shows: no card words, no text message, no
     * name. The same sentence the approval notifier's locked copy uses
     * (`R.string.approval_locked`), so the screen cannot show two dialects of
     * the same fact - and `HandsfreeNoticeTest` holds the two together.
     */
    val LOCKED = Words("Jarvis", "A decision is waiting. Unlock to see it.")

    /**
     * The lock screen's PUBLIC copy, on every notification: the approval
     * notifier's own redacted line and nothing else.
     */
    const val PUBLIC = ApprovalNotificationPolicy.PUBLIC_WORDS

    /**
     * The waiting card's words: its SHORT title (the same [CardWords] every
     * other card surface uses) and the PC's own sentence, or, once the PC has
     * answered, the one line it decided with.
     *
     * The number beside the card is the ANSWER WINDOW, not the card's own
     * deadline (docs/JARVIS-API.md section 191.4: `expires_in_sec` is how long
     * a spoken answer is open, and the card's own `expires_in` is a different
     * field the phone does not get from this event). It used to read "60s
     * left", which claimed the card would expire - so it now says "to answer".
     *
     * @param locked true when [com.jarvis.client.data.SecurityRules.notificationsLocked]
     *   says the words may not be drawn; then nothing below is even built.
     * @param line the PC's decision, once there is one, or null while it waits.
     * @param waiting the generic "a card is waiting" used when the PC gave no
     *   sentence at all.
     */
    fun card(locked: Boolean, card: Handsfree.Card, line: String?, waiting: String): Words {
        // The redaction comes FIRST, before any of the card's words are read:
        // a body that is built and then thrown away is one refactor away from
        // being built and then NOT thrown away.
        if (locked) return LOCKED
        val title = CardWords.fallbackTitle(card.action.ifBlank { card.say })
            .ifBlank { CardWords.NO_ACTION }
        val answerBy = if (card.expiresInSec > 0) "${card.expiresInSec}s to answer" else null
        val body = line ?: listOfNotNull(
            card.say.trim().takeIf { it.isNotEmpty() }?.let { SmsSend.shortText(it, 90) },
            answerBy,
        ).joinToString(" · ").ifEmpty { waiting }
        return Words(title, body)
    }

    /**
     * A text message's own notification.
     *
     * [title] is the generic "Text message" every state shares; [line] is the
     * receipt, and it is the half that names the recipient and quotes what was
     * sent ([SmsSend.sentLine]).
     */
    fun sms(locked: Boolean, title: String, line: String): Words =
        if (locked) LOCKED else Words(title, line)
}
