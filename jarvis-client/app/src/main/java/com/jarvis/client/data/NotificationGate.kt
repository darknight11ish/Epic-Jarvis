package com.jarvis.client.data

/**
 * The on-device gate every notification passes BEFORE a single word of it is
 * stored (and so before anything could ever be transmitted to the PC).
 *
 * The 2026-10-20 Android audit (Gemini, Area 10A) found the listener's own
 * checks were SMS-only, had no `VISIBILITY_SECRET` refusal, and no banking
 * refusal - a banking app the owner added would have had its title/text kept
 * and shown. This object holds those decisions as PURE functions so the JVM
 * suite can drive every branch without an emulator, and the listener only
 * reads text AFTER the cheap refusals have passed:
 *
 *   1. `visibility == VISIBILITY_SECRET` - a notification Android itself marks
 *      secret is never read or kept, whatever app posted it (lock-screen
 *      "show sensitive content" is off);
 *   2. the phone's own SMS/Messages app (the OS's default-SMS answer, or the
 *      static fallback list) - CLAUDE.md's hard "never text messages" rule;
 *   3. a banking, brokerage or payment package - refused whole, like adding
 *      one to the allow-list already is;
 *   4. otherwise the title and text go through [NotificationRedactor] TOGETHER
 *      before they are returned for storage: a 4-8 digit code with a trigger
 *      word in either field is masked, so it can never reach the PC later.
 *
 * What this deliberately does NOT do, said plainly: it is a heuristic, not a
 * guarantee (see [NotificationRedactor]'s own limits), and it does not decide
 * the PC's master switch or the owner's allow-list - those stay in the
 * listener and in [NotificationAllowList]. The SMS/banking checks are repeated
 * here, on every posted notification, as defence in depth in case a package
 * reached the allow-list by another route.
 */
object NotificationGate {

    /** Android's `Notification.VISIBILITY_SECRET` (its value is -1; kept here
     * so the JVM tests do not compile against an Android constant). */
    const val VISIBILITY_SECRET = -1

    /** Why a notification is dropped - named, so the listener's intent is clear. */
    enum class Skip { SECRET, SMS, BANKING }

    /** What the gate decided for one posted notification. */
    sealed interface Verdict {
        /** Read nothing, keep nothing. */
        data class SkipIt(val reason: Skip) : Verdict

        /** Keep these (already redacted) words. */
        data class Capture(val title: String, val text: String) : Verdict
    }

    /** True for Android's "this notification is secret" visibility. */
    fun isSecret(visibility: Int): Boolean = visibility == VISIBILITY_SECRET

    /**
     * The app-level refusals, in audit order: SMS/Messages first (the hard
     * rule), then a banking/payment package. [category] is
     * `ApplicationInfo.category`, or null when unknown.
     */
    fun packageSkip(
        packageName: String,
        smsRoleHolders: Set<String> = emptySet(),
        category: Int? = null,
    ): Skip? = when {
        NotificationAllowList.isSmsPackage(packageName, smsRoleHolders) -> Skip.SMS
        NotificationAllowList.looksLikeBanking(packageName, category) -> Skip.BANKING
        else -> null
    }

    /**
     * The whole decision for one notification, given the words already read
     * out of it. The listener reads those words ONLY after the cheap checks
     * have passed, but this function is still complete on its own so the JVM
     * suite can prove the scrubbing order.
     */
    fun capture(
        packageName: String,
        visibility: Int,
        rawTitle: String,
        rawText: String,
        smsRoleHolders: Set<String> = emptySet(),
        category: Int? = null,
    ): Verdict {
        if (isSecret(visibility)) return Verdict.SkipIt(Skip.SECRET)
        packageSkip(packageName, smsRoleHolders, category)?.let { return Verdict.SkipIt(it) }
        val (title, text) = NotificationRedactor.redactBoth(rawTitle, rawText)
        return Verdict.Capture(title, text)
    }
}
