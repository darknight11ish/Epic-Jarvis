package com.jarvis.client.net

/**
 * The words on the phone's screen, as the assistant gesture hands them over
 * (the owner's decision of 2026-09-28, docs/SCREEN-DESIGN.md section 3;
 * docs/JARVIS-API.md sections 62 and 96) - flattened, with every password
 * field left out, and never more than [MAX_CHARS].
 *
 * NO ANDROID IN THIS FILE, on purpose: [Node] is a plain copy of the few
 * things Android's `AssistStructure.ViewNode` says about one view, made by
 * `assistant/AssistReader.kt`, so the JVM tests can hold every rule with a
 * made-up screen ([com.jarvis.client.ScreenTextTest]).
 *
 * WHAT IS LEFT OUT, and why each rule exists (fail safe: a doubt drops the
 * field, never keeps it):
 *  - a password field: its input type says password (text, visible-password,
 *    web-password or number-password), or its autofill hints say password,
 *    or a credit card number, security code or expiry, or its own name or
 *    hint says so ("password", "passcode", "CVV", "PIN" as a word). The
 *    words INSIDE such a field, and every field inside it, are never read;
 *  - text that is only dots or stars (a masked box an app did not mark);
 *  - a view that is not visible, and everything under it;
 *  - a view whose app said it must not be read ([Node.blocked]).
 * SAID PLAINLY in the app: an app that does not mark its password fields and
 * shows the words as they are typed cannot be told apart from any other text
 * here - the phone cannot know. That is what the "Never look at" list is for.
 *
 * Nothing here is stored or sent: the caller holds the result in memory
 * ([ScreenLook]) and the PC labels it as outside text.
 */
object ScreenText {
    /** The PC caps the same words again ([jarvis_screen.UI_MAX_CHARS]). */
    const val MAX_CHARS = 3000

    /** Views read at most, so a giant list cannot make the gesture slow. */
    const val MAX_NODES = 2500

    /** How deep a view tree is walked. */
    const val MAX_DEPTH = 40

    // android.text.InputType, copied so this file needs no Android.
    const val TYPE_MASK_CLASS = 0x0000000f
    const val TYPE_MASK_VARIATION = 0x00000ff0
    const val TYPE_CLASS_TEXT = 0x00000001
    const val TYPE_CLASS_NUMBER = 0x00000002
    const val TEXT_VARIATION_PASSWORD = 0x00000080
    const val TEXT_VARIATION_VISIBLE_PASSWORD = 0x00000090
    const val TEXT_VARIATION_WEB_PASSWORD = 0x000000e0
    const val NUMBER_VARIATION_PASSWORD = 0x00000010

    /** One view, as much as the rules need. */
    data class Node(
        val text: String? = null,
        val hint: String? = null,
        val idName: String? = null,
        val inputType: Int = 0,
        val autofillHints: List<String> = emptyList(),
        val visible: Boolean = true,
        val blocked: Boolean = false,
        val children: List<Node> = emptyList(),
    )

    /** What one flattening found: the words, how much was cut, how many boxes were skipped. */
    data class Words(val text: String, val leftOut: Int, val skippedPasswordBoxes: Int)

    private val WORDY = Regex("(?i)(pass\\s?word|passcode|passwd|\\bcvv2?\\b|\\bcvc2?\\b|security\\s?code|\\bpin\\b|one[- ]time)")

    /** Only dots, stars, bullets and spaces: a masked box. */
    private val MASKED = Regex("^[\\s\\u2022\\u25CF\\u25CB\\u00B7*.\\u2217\\u2731-]+$")

    /** Autofill hints (View.AUTOFILL_HINT_*) that mean a secret or a card. */
    private val SECRET_HINTS = listOf("password", "newpassword", "creditcard", "smsotpcode", "sms_otp")

    /** Is this view a password (or card, or one-time code) field? Fail safe. */
    fun isSecretField(n: Node): Boolean {
        val cls = n.inputType and TYPE_MASK_CLASS
        val variation = n.inputType and TYPE_MASK_VARIATION
        if (cls == TYPE_CLASS_TEXT && (variation == TEXT_VARIATION_PASSWORD ||
                variation == TEXT_VARIATION_VISIBLE_PASSWORD || variation == TEXT_VARIATION_WEB_PASSWORD)
        ) return true
        if (cls == TYPE_CLASS_NUMBER && variation == NUMBER_VARIATION_PASSWORD) return true
        if (n.autofillHints.any { h ->
                val low = h.lowercase()
                SECRET_HINTS.any { low.startsWith(it) }
            }
        ) return true
        val name = listOfNotNull(n.idName, n.hint).joinToString(" ")
        return name.isNotEmpty() && WORDY.containsMatchIn(name)
    }

    private class Walk {
        var budget = MAX_NODES
        var skipped = 0
        val lines = ArrayList<String>()
    }

    private fun walk(n: Node, depth: Int, w: Walk) {
        if (depth > MAX_DEPTH || w.budget <= 0) return
        w.budget -= 1
        if (!n.visible || n.blocked) return
        if (isSecretField(n)) {
            w.skipped += 1
            return                       // nothing in it, nothing under it
        }
        val text = n.text?.replace('\u0000', ' ')?.trim().orEmpty()
        val words = text.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (words.isNotEmpty() && !MASKED.matches(words) && (w.lines.isEmpty() || w.lines.last() != words)) {
            w.lines += words
        }
        for (c in n.children) walk(c, depth + 1, w)
    }

    /** The words on the screen, in reading order, password fields skipped. */
    fun flatten(root: Node?, max: Int = MAX_CHARS): Words {
        if (root == null) return Words("", 0, 0)
        val w = Walk()
        walk(root, 0, w)
        val joined = w.lines.joinToString("\n").trim()
        if (joined.length <= max) return Words(joined, 0, w.skipped)
        return Words(joined.substring(0, max).trimEnd(), joined.length - max, w.skipped)
    }

    /** Several windows' trees (an assist structure can hold more than one), one after another. */
    fun flattenAll(roots: List<Node>, max: Int = MAX_CHARS): Words {
        val parts = roots.map { flatten(it, Int.MAX_VALUE) }
        val joined = parts.map { it.text }.filter { it.isNotEmpty() }.joinToString("\n").trim()
        val skipped = parts.sumOf { it.skippedPasswordBoxes }
        if (joined.length <= max) return Words(joined, 0, skipped)
        return Words(joined.substring(0, max).trimEnd(), joined.length - max, skipped)
    }
}
