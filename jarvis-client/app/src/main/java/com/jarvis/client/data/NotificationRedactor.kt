package com.jarvis.client.data

/**
 * Blanks out anything that looks like a one-time code, BEFORE a captured
 * notification's title or text is ever written to disk (CLAUDE.md,
 * 2026-09-26: "one-time codes hidden before anything reaches the model" -
 * applied here to storage itself, stricter than the decision literally
 * asked for, because a code that never reaches disk cannot leak from a
 * lost phone or a phone backup either, and there is no second place in
 * this app that could still show the unredacted text later).
 *
 * A REGEX HEURISTIC, SAID PLAINLY - it is a good-faith reduction of risk,
 * never a guarantee. What it catches:
 *   - a plain run of 4 to 8 digits ("482913", "2026") anywhere in a
 *     notification whose title OR text carries a trigger word: in English
 *     ("code", "otp", "verification", "passcode", "PIN", "authenticat...",
 *     "2fa", "log in"/"login", "sign in", "one-time"/"one time"...), or the
 *     word for "code" in Spanish/Portuguese ("código"), Italian ("codice"),
 *     Polish/Turkish ("kod") and Russian ("код"). Title and text are
 *     checked TOGETHER: a title "Verification code" over a text "Use 482913
 *     to sign in" hides the code in the text (the 2026-09-28 audits found
 *     the two checked apart let exactly that through);
 *   - the common "NNN NNN" / "NNN-NNN" six-digit grouping (Google's,
 *     Microsoft's and Apple's own display style for a 6-digit code), with
 *     or without a trigger word - but never a group that is part of a
 *     longer run of groups, such as a phone number "555-123-4567";
 *   - a run of 4 to 8 digits, with an optional single leading letter and
 *     dash (Google's "G-123456" shape), when it is the ENTIRE notification
 *     text on its own (nothing else but ordinary trailing punctuation) -
 *     the common shape for a bank's or carrier's own bare-OTP
 *     notification, which often carries no trigger word at all.
 *
 * What it deliberately does NOT catch, said honestly rather than left to
 * be discovered later:
 *   - a code that is not made of plain digits (a word-based code, a code
 *     in a non-Latin script, or one with letters mixed all through it
 *     rather than one leading letter);
 *   - a bare digit run with NO trigger word, embedded in a longer
 *     sentence - "call me at 482913 today" cannot be told apart from a
 *     real code without one, so it is left alone;
 *   - a trigger word in a language the list does not know (it knows
 *     English and the few words for "code" above, no more - the same
 *     limit this project's other pattern checks already state;
 *     `jarvis_mail_mask.py`'s own docstring says the same of its list);
 *   - a code split some OTHER way than "NNN NNN"/"NNN-NNN" (three groups,
 *     an odd split, digits interleaved with letters);
 *   - a code that is genuinely longer than 8 digits or shorter than 4.
 *
 * On purpose, this prefers to OVER-redact (blanking a 4-8 digit year, a
 * reference number, or a short price next to the word "code" by mistake)
 * rather than under-redact - a real code reaching storage unredacted would
 * be the real privacy failure this class exists to prevent, and losing a
 * few characters of an otherwise-summarised notification costs nothing by
 * comparison.
 */
object NotificationRedactor {

    const val MASK = "[hidden code]"

    // (?iu): case-insensitive, and for letters outside plain English too
    // ("CÓDIGO", "КОД") - RegexOption.IGNORE_CASE alone only folds ASCII.
    private val TRIGGER = Regex(
        "(?iu)code|otp|one[- ]time|passcode|verification|verify|authenticat|2fa|" +
            "security code|access code|login code|confirmation code|" +
            "\\bpin\\b|\\blog[- ]?in|\\bsign[- ]?in|two[- ]factor|2-step|" +
            "c[oó]digo|codice|\\bkod\\b|код",
    )

    /**
     * A plain run of 4-8 digits, OR the common "NNN NNN"/"NNN-NNN" six-digit
     * grouping. `\b` on both ends means a 9-or-more-digit run (a phone
     * number, an account number) never matches at all: there is no word
     * boundary anywhere inside a longer, unbroken digit run for the
     * quantifier to land on - see the class doc's own worked example in
     * `NotificationRedactorTest`.
     */
    private val CODE = Regex("""\b\d{3}[- ]\d{3}\b|\b\d{4,8}\b""")

    /**
     * The "NNN NNN" / "NNN-NNN" grouping on its own - hidden even with no
     * trigger word. Not when it is part of a longer run of groups (the
     * lookarounds): "555-123-4567" is a phone number, not a code.
     */
    private val GROUPED = Regex("""(?<!\d[- ])(?<!\d)\d{3}[- ]\d{3}(?!\d)(?![- ]\d)""")

    /** [text] with anything that looks like a one-time code blanked out. */
    fun redact(text: String): String = redact(text, triggered = TRIGGER.containsMatchIn(text))

    private fun redact(text: String, triggered: Boolean): String {
        if (text.isBlank()) return text
        if (triggered || isBareCode(text)) return CODE.replace(text) { MASK }
        return GROUPED.replace(text) { MASK }
    }

    /**
     * [title] and [text] redacted TOGETHER: a trigger word in either one
     * counts for both, because a code often sits in the text while the
     * word that marks it ("Verification code") is only in the title.
     */
    fun redactBoth(title: String, text: String): Pair<String, String> {
        val triggered = TRIGGER.containsMatchIn(title) || TRIGGER.containsMatchIn(text)
        return redact(title, triggered) to redact(text, triggered)
    }

    /**
     * True when [text], once a leading single-letter-and-dash prefix
     * ("G-") and ordinary trailing punctuation are stripped, is NOTHING
     * BUT 4 to 8 digits (optionally grouped by a space or dash) - the
     * shape a bank's or carrier's own bare-OTP notification usually takes,
     * often with no trigger word in it at all.
     */
    private fun isBareCode(text: String): Boolean {
        var s = text.trim()
        if (s.length >= 3 && s[1] == '-' && s[0].isLetter()) s = s.substring(2)
        s = s.trimEnd('.', '!', ':', ' ')
        if (s.isEmpty()) return false
        if (s.any { !(it.isDigit() || it == ' ' || it == '-') }) return false
        val digits = s.count { it.isDigit() }
        return digits in 4..8
    }
}
