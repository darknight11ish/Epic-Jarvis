package com.jarvis.client.net

/**
 * Writing a text message to a contact for the owner - the one thing the phone
 * does with `phone_command kind=send_sms` (owner's request, 2026-11-04: in
 * hands-free mode he wants Jarvis to WRITE TEXT MESSAGES to contacts for him).
 *
 * WHY THE PHONE RESOLVES THE NAME. The PC has no address book and is never
 * given one: the phone looks the name up in ITS OWN contacts and sends the
 * message itself - `SEND_SMS` is Android's, not the PC's. The PC names the
 * person in the owner's words ("Alex"); everything below turns that into
 * exactly one number or into a refusal.
 *
 * THE RULE, and it is deliberately the strict one:
 *
 *  - an EXACT match on the whole name, ignoring case and runs of spaces, and
 *    only that: "alex" finds "Alex", and it does not find "Alexandra";
 *  - a name that matches more than one NUMBER is AMBIGUOUS and nothing is
 *    sent. A wrong recipient is the one failure of this feature that cannot
 *    be taken back, so two matching numbers are a refusal with the count in
 *    words - never a guess, never the first one;
 *  - the same number twice (two address-book entries, one phone) is ONE
 *    match, because it is one place to send to;
 *  - a bare phone number typed by the owner is used as it is: it is already
 *    exact, and it is what he said;
 *  - no match, or an empty name, is a refusal.
 *
 * NOTHING HERE IS STORED. This object resolves, and hands back a number for the
 * one caller ([com.jarvis.client.service.HandsfreeService]) to send to in the
 * next second. No contact, number or message is written to disk, to a log or
 * to the app's settings, and none is kept after the result has been posted.
 *
 * Pure - no Android - so `SmsSendTest` holds every branch on the JVM.
 */
object SmsSend {

    /**
     * One row of the phone's address book, as the caller read it.
     *
     * @param name the contact's display name, as Android has it.
     * @param number the dialable number. Blank rows are ignored rather than
     *   resolving to nothing.
     */
    data class Contact(val name: String, val number: String)

    /** What a contact name resolved to. */
    sealed interface Resolved {
        /** Exactly one number: the message may be sent to it. */
        data class One(val number: String, val name: String) : Resolved

        /**
         * More than one number matches the name. Nothing is sent.
         *
         * @param howMany how many different numbers matched - said in words,
         *   never as a list of numbers (the owner is told to send it himself,
         *   not shown a stranger's digits in a notification).
         */
        data class Ambiguous(val howMany: Int) : Resolved

        /** Nothing in the address book has that name. */
        data object NotFound : Resolved

        /** The command carried no name at all. */
        data object NoName : Resolved
    }

    /** What the owner is told when nothing was sent. All of these are shown. */
    const val AMBIGUOUS = "More than one contact has that name, so nothing was sent."
    const val NOT_FOUND = "No contact on this phone has that name, so nothing was sent."
    const val NO_NAME = "That message did not name a contact, so nothing was sent."
    const val NO_PERMISSION = "Jarvis may not send text messages on this phone yet."
    const val NO_CONTACTS_PERMISSION =
        "Jarvis may not read your contacts on this phone, so it could not look that name up."
    const val NO_LINK = "Your PC could not be reached, so nothing was sent."
    const val EMPTY_TEXT = "That message had no words in it, so nothing was sent."
    const val NO_NUMBER = "That contact has no phone number saved, so nothing was sent."

    /** Said in the notification, in place of "Sent". */
    const val NOT_SENT = "Not sent"

    /**
     * Looks [contact] up in [known] - the rows the caller read from Android.
     *
     * The order is the rule above, and it is written here rather than left to
     * be inferred from the tests: a name that matches nothing is [Resolved.NotFound],
     * a name that matches two different numbers is [Resolved.Ambiguous] even
     * when one of those rows is a duplicate, and only one distinct number ever
     * comes back as [Resolved.One].
     */
    fun resolve(contact: String, known: List<Contact>): Resolved {
        val want = fold(contact)
        if (want.isEmpty()) return Resolved.NoName
        // A number the owner said is already exact. It is never looked up: a
        // contact whose name happens to be digits is not the thing he named.
        numberOf(contact)?.let { return Resolved.One(it, contact.trim()) }
        val numbers = known.asSequence()
            .filter { it.number.isNotBlank() && fold(it.name) == want }
            .map { dialable(it.number) }
            .filter { it.isNotEmpty() }
            .distinct()
            .toList()
        return when (numbers.size) {
            0 -> Resolved.NotFound
            1 -> Resolved.One(numbers[0], known.first { fold(it.name) == want }.name.trim())
            else -> Resolved.Ambiguous(numbers.size)
        }
    }

    /** The refusal's own sentence for a resolution that is not [Resolved.One]. */
    fun refusedSentence(r: Resolved): String = when (r) {
        is Resolved.One -> ""
        is Resolved.Ambiguous -> AMBIGUOUS
        Resolved.NotFound -> NOT_FOUND
        Resolved.NoName -> NO_NAME
    }

    /**
     * Whether this phone may send at all, and why not - the second gate, before
     * a name is even looked up.
     *
     * Never a yes on a guess: [permission] is what Android answered THIS
     * moment, and [connected] is the live stream the result has to be posted
     * on. A send whose result could not be reported would leave the PC
     * believing nothing happened, and a message with no PC behind it is not
     * hands-free mode - so both are required, and both are said in words.
     */
    fun gate(hasSmsPermission: Boolean, hasContactsPermission: Boolean, connected: Boolean): String? =
        when {
            !connected -> NO_LINK
            !hasSmsPermission -> NO_PERMISSION
            !hasContactsPermission -> NO_CONTACTS_PERMISSION
            else -> null
        }

    /**
     * Whether a name lookup on this phone is needed for [contact].
     *
     * False for a number the owner said: that is already exact, and asking for
     * `READ_CONTACTS` to send to a number he read out would be a permission
     * this path does not need.
     */
    fun needsContacts(contact: String): Boolean = numberOf(contact) == null

    /** The receipt token posted back for a send Android accepted. */
    const val RECEIPT_SENT = "sms_sent:RESULT_OK"

    /** ...and for one that was never attempted (a refusal, before any send). */
    const val RECEIPT_REFUSED = "sms_sent:not_attempted"

    /** ...and for one it refused, with the platform's own error in the token. */
    fun receiptFailed(platformCode: Int): String = "sms_sent:RESULT_$platformCode"

    /**
     * The plain sentence for a platform failure code - Android's own
     * `SmsManager` result codes, said the way the owner would say them.
     *
     * Never "sent", and never a guess at the cause: the codes below are the
     * ones Android documents (`RESULT_ERROR_GENERIC_FAILURE` and its
     * neighbours), and anything else is reported as an unknown failure rather
     * than described.
     */
    fun sendFailure(platformCode: Int): String = when (platformCode) {
        // android.telephony.SmsManager / Activity result codes, by value so
        // this file stays free of Android imports and testable on the JVM.
        1 -> "Your phone's network would not take the message (no signal or no credit)."
        2 -> "Your phone's radio refused the message."
        3 -> "Your phone could not hold the message, so it was not sent."
        4 -> "The message was refused as not allowed."
        -2 -> "Your phone never said whether the message went, so it is not being called sent."
        else -> "Your phone could not send the message."
    }

    /** A short, safe name for the notification: never the whole message. */
    fun shortText(text: String, max: Int = 60): String {
        val flat = text.replace(Regex("\\s+"), " ").trim()
        return if (flat.length <= max) flat else flat.take(max - 1).trimEnd() + "…"
    }

    /** The notification's one line, naming the contact and the words. */
    fun sentLine(name: String, text: String): String = "Sent to $name: \"${shortText(text)}\""

    /** ...and the line when nothing was sent, which never claims otherwise. */
    fun failedLine(name: String, why: String): String =
        "$NOT_SENT${if (name.isBlank()) "" else " to $name"}: $why"

    // ------------------------------------------------------------ helpers ----

    /** Case and spacing folded, so " Alex  Smith " and "alex smith" are one name. */
    private fun fold(s: String): String =
        s.trim().lowercase().replace(Regex("\\s+"), " ")

    /** The digits of a number, with a leading + when it was written one. */
    private fun dialable(number: String): String {
        val t = number.trim()
        val international = t.startsWith("+") || t.startsWith("00")
        val digits = t.filter { it.isDigit() }
        if (digits.isEmpty()) return ""
        // "00" is the other way of writing "+", and only that prefix is
        // rewritten: a national number keeps the leading zero that makes it
        // dialable from inside the country.
        val body = if (t.startsWith("00") && !t.startsWith("+")) digits.drop(2) else digits
        if (body.isEmpty()) return ""
        return (if (international) "+" else "") + body
    }

    /**
     * [contact] as a dialable number, or null when it is a name.
     *
     * A phone number is what has at least five digits and nothing but digits,
     * spaces, dashes, brackets, dots and one optional leading +. That is
     * deliberately strict: "Alex 2" is a name, and "Room 12" is a name.
     */
    private fun numberOf(contact: String): String? {
        val t = contact.trim()
        if (!t.matches(Regex("^\\+?[0-9 ()\\-.]+$"))) return null
        if (t.count { it.isDigit() } < 5) return null
        return dialable(t).ifEmpty { null }
    }
}
