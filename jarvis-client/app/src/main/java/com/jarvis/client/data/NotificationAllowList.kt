package com.jarvis.client.data

/**
 * Which apps' notifications Jarvis may capture on this phone - EMPTY by
 * default (CLAUDE.md, 2026-09-26: "only apps the owner chooses"), and the
 * one place that refuses a banking app or the phone's own SMS/Messages
 * app before it can ever be added, whatever the owner taps.
 *
 * PURE LOGIC ONLY - no Android import, so this is unit-testable without a
 * device or an emulator ([NotificationAllowListTest]). The Android-backed
 * half ([NotificationAllowListStore]) reads the two live signals this
 * object cannot read for itself (a package's declared store category, and
 * the OS's own default-SMS-app answer) and passes them in.
 *
 * BANKING: BLOCKED OUTRIGHT, NOT JUST DISCOURAGED IN WORDS. The owner's
 * task brief allowed either a heuristic block or, if that felt too
 * unreliable, strong wording alone; this module blocks, because a real,
 * if imperfect, signal was available on both counts:
 *   - Android's own Play Store category for the app (`CATEGORY_FINANCE`,
 *     `ApplicationInfo.category` since API 26) - set by the app's own
 *     developer when they published it, so it is Android's classification,
 *     not a guess from a name; and
 *   - a short, curated list of well-known banking, brokerage and payment
 *     package-name substrings ([BANKING_SUBSTRINGS]), for the (very
 *     common) case of a sideloaded APK or an old build with no category
 *     set at all.
 * SAID PLAINLY: this is still a heuristic, not a guarantee. A banking app
 * whose category is unset AND whose package name matches nothing on the
 * list will not be caught here - the card and the allow-list screen both
 * say so, and the owner is asked not to add one regardless.
 *
 * SMS/MESSAGES: BLOCKED BY WHAT THE PHONE ITSELF SAYS IS ITS SMS APP, NOT
 * A NAME GUESS. The stronger of the two signals: Android's own
 * `RoleManager.ROLE_SMS` names whichever package the phone currently uses
 * to send and receive text messages - whatever it is called, including a
 * third-party SMS app, an OEM's own Messages app, or a rebrand this list
 * has never heard of. [KNOWN_SMS_PACKAGES] is kept only as a second,
 * static line of defence for a phone where that role cannot be read.
 */
object NotificationAllowList {

    /**
     * Mirrors `android.content.pm.ApplicationInfo.CATEGORY_FINANCE`'s real
     * value (stable since API 26) so this pure file needs no Android
     * import. [NotificationAllowListStore] is the one place that reads the
     * real constant and the real category and passes both kinds of int
     * here - never re-declares its own copy of the number.
     */
    const val CATEGORY_FINANCE = 6

    /**
     * Package-name substrings for well-known banks, brokerages and payment
     * apps (English-market names only - said plainly, not exhaustive, and
     * checked case-insensitively against the WHOLE package name, e.g.
     * "com.chase.sig.android" contains "chase"). A real bank whose name is
     * not on this list, or a bank outside these markets, is not caught by
     * this half of the check - only by [CATEGORY_FINANCE] above, if the
     * app declared it.
     */
    private val BANKING_SUBSTRINGS = listOf(
        "bank", "chase", "wellsfargo", "citibank", "usbank", "bankofamerica",
        "paypal", "venmo", "revolut", "chime", "cashapp", "cash.app",
        "coinbase", "robinhood", "fidelity", "schwab", "vanguard",
        "americanexpress", "discover.card", "capitalone", "ally.bank",
        "sofi", "affirm", "klarna", "creditkarma", "creditunion",
        "n26.com", "monzo", "transferwise", "wise.money", "zellepay",
        "hsbc", "barclays", "natwest", "lloydsbank", "santander",
    )

    /**
     * Best-effort SECOND line of defence, for a phone where
     * `RoleManager.ROLE_SMS` cannot be read (an old Android version, or the
     * call failing for any reason). NOT exhaustive on its own - an OEM's
     * differently-named Messages app, or a third-party SMS app, is caught
     * only by the role check above, never by this static list alone.
     */
    private val KNOWN_SMS_PACKAGES = setOf(
        "com.google.android.apps.messaging",
        "com.android.mms",
        "com.android.messaging",
        "com.samsung.android.messaging",
        "com.sonyericsson.conversations",
        "com.motorola.messaging",
        "com.htc.sense.mms",
    )

    sealed class AddResult {
        /** Added to the list, this call. */
        data class Added(val packageName: String) : AddResult()

        /** Already on the list; nothing changed. */
        data class AlreadyAdded(val packageName: String) : AddResult()

        /** Refused: this looks like a banking or payment app. */
        data class BlockedBanking(val packageName: String) : AddResult()

        /** Refused: this is (or claims to be) the phone's SMS/Messages app. */
        data class BlockedSms(val packageName: String) : AddResult()
    }

    /**
     * True when [packageName] looks like a banking, brokerage or payment
     * app - by its declared store category ([CATEGORY_FINANCE]) or by a
     * name on [BANKING_SUBSTRINGS]. [category] is `ApplicationInfo
     * .category` (or null when the app declared none, or the caller could
     * not read it).
     */
    fun looksLikeBanking(packageName: String, category: Int? = null): Boolean {
        if (category == CATEGORY_FINANCE) return true
        val p = packageName.lowercase()
        return BANKING_SUBSTRINGS.any { p.contains(it) }
    }

    /**
     * True when [packageName] is the phone's SMS/Messages app - because the
     * OS itself says so ([smsRoleHolders], from `RoleManager.ROLE_SMS`), or
     * because it is on the static fallback list.
     */
    fun isSmsPackage(packageName: String, smsRoleHolders: Set<String> = emptySet()): Boolean =
        packageName in smsRoleHolders || packageName in KNOWN_SMS_PACKAGES

    /**
     * What adding [packageName] to [current] (the list already saved)
     * would do - checked BEFORE anything is written, in this order: SMS
     * first (CLAUDE.md's hard "never text messages" rule, so it wins even
     * over a banking-looking name), then banking, then whether it is
     * already there.
     */
    fun evaluateAdd(
        packageName: String,
        current: Set<String>,
        category: Int? = null,
        smsRoleHolders: Set<String> = emptySet(),
    ): AddResult = when {
        isSmsPackage(packageName, smsRoleHolders) -> AddResult.BlockedSms(packageName)
        looksLikeBanking(packageName, category) -> AddResult.BlockedBanking(packageName)
        packageName in current -> AddResult.AlreadyAdded(packageName)
        else -> AddResult.Added(packageName)
    }
}
