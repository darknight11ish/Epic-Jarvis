package com.jarvis.client.data

import com.jarvis.client.net.PendingItem

/**
 * The phone's lock and fingerprint settings, and every decision made from
 * them - with no Android in this file, so the JVM tests can hold each rule.
 *
 * Saved on this phone only ([ClientSettings.security]), never sent to the PC:
 * they decide who may use THIS phone, not what Jarvis may do. The PC's own
 * permission gate is unchanged by any of it.
 *
 * Five settings, all off or at today's behaviour by default:
 *
 * - [Security.appLock]: opening Jarvis needs the fingerprint or phone PIN.
 * - [Security.relockAfter]: how long Jarvis may be away before it locks again.
 * - [Security.approvals]: which approvals need the fingerprint. Never fewer
 *   than today's rule ([SecurityRules.riskyByToday]).
 * - [Security.privateLists]: Mind's memory lists stay hidden behind a Show.
 * - [Security.method]: fingerprint or PIN, or fingerprint only.
 *
 * Loosening any of them needs a successful check first; tightening is
 * instant ([SecurityRules.loosens]). Denying an approval is never gated.
 */
data class Security(
    val appLock: Boolean = false,
    val relockAfter: RelockAfter = RelockAfter.ONE_MINUTE,
    val approvals: ApprovalCheck = ApprovalCheck.RISKY,
    val privateLists: Boolean = false,
    val method: CheckMethod = CheckMethod.FINGERPRINT_OR_PIN,
) {
    /**
     * True when the owner has asked for anything stricter than the defaults.
     * Then a phone with no way to check refuses what needed the check,
     * instead of letting it through the way the defaults always have.
     */
    val anyLockOn: Boolean
        get() = appLock || approvals == ApprovalCheck.EVERY || privateLists ||
            method == CheckMethod.FINGERPRINT_ONLY
}

/** How long Jarvis may be out of sight before opening it needs the check again. */
enum class RelockAfter(val wire: String, val ms: Long, val label: String) {
    NOW("now", 0L, "Straight away"),
    ONE_MINUTE("1m", 60_000L, "1 min"),
    FIVE_MINUTES("5m", 5 * 60_000L, "5 min"),
    FIFTEEN_MINUTES("15m", 15 * 60_000L, "15 min"),
    ;

    companion object {
        fun fromWire(s: String?): RelockAfter = entries.firstOrNull { it.wire == s } ?: ONE_MINUTE
    }
}

/** Which approvals ask for the fingerprint. */
enum class ApprovalCheck(val wire: String, val label: String) {
    /** Today's rule: outbound, cannot be undone, unclassified, or rushed. */
    RISKY("risky", "Risky only"),
    EVERY("every", "Every approval"),
    ;

    companion object {
        fun fromWire(s: String?): ApprovalCheck = entries.firstOrNull { it.wire == s } ?: RISKY
    }
}

/** What counts as "it is you". */
enum class CheckMethod(val wire: String, val label: String) {
    /** A strong fingerprint (or face, where Android rates it strong), or the phone's PIN. */
    FINGERPRINT_OR_PIN("fingerprint_or_pin", "Fingerprint or PIN"),

    /** A strong fingerprint (or strong face) only. No PIN. */
    FINGERPRINT_ONLY("fingerprint_only", "Fingerprint only"),
    ;

    companion object {
        fun fromWire(s: String?): CheckMethod = entries.firstOrNull { it.wire == s } ?: FINGERPRINT_OR_PIN
    }
}

/**
 * How one fingerprint or PIN check ended. Moved here from `BiometricGate`
 * so the rules below can be tested without Android.
 */
enum class CheckOutcome {
    /** The owner confirmed. */
    CONFIRMED,

    /** They dismissed it. Not an error - the thing simply is not done. */
    CANCELLED,

    /**
     * This phone has no way to check at all with the chosen method: nothing
     * set up (no fingerprint, and - for "Fingerprint or PIN" - no screen lock
     * either), or no hardware. What happens then is [SecurityRules]' call.
     */
    UNAVAILABLE,

    /**
     * The check exists but could not be shown just now (the sensor was busy,
     * or the prompt failed to open), even after one retry. Nothing is done.
     */
    FAILED,
}

/**
 * Whether this phone can check at all with a given method, asked before a
 * setting is tightened (so the owner cannot lock themselves out by choosing
 * something the phone cannot do).
 */
enum class CheckAvailability {
    READY,

    /** The hardware is there but nothing is set up: no fingerprint, or no screen lock. */
    NOT_SET_UP,

    /** This phone cannot do this kind of check at all. */
    NO_HARDWARE,

    /** Busy or unknown just now. */
    NOT_NOW,
}

object SecurityRules {

    /**
     * Today's rule, unchanged: anything that leaves the machine, cannot be
     * undone, or was not classified by the server (which arrives as both),
     * plus anything outside text tried to rush.
     */
    fun riskyByToday(item: PendingItem): Boolean {
        if (!item.risk.classified) return true
        if (item.risk.reach == "outbound") return true
        if (item.risk.reversible == "no") return true
        // A rush latch means outside text tried to hurry this decision.
        // Slowing it down is the entire response.
        if (item.raised != null) return true
        return false
    }

    /** Whether approving [item] asks for the check. Never less than [riskyByToday]. */
    fun approvalNeedsCheck(s: Security, item: PendingItem): Boolean =
        riskyByToday(item) || s.approvals == ApprovalCheck.EVERY

    /** What to do after a check. [Stop.say] is null when nothing needs saying. */
    sealed interface Verdict {
        data object Go : Verdict
        data class Stop(val say: String?) : Verdict
    }

    /**
     * After the check for an approval.
     *
     * UNAVAILABLE is the one that changed. With every setting at its default
     * it still lets the approval through, exactly as before: refusing to let
     * the owner answer their own PC because the phone has no fingerprint set
     * up would be a lock on the wrong door. Once the owner has turned any
     * lock on, it is refused, and the sentence says how to fix it.
     */
    fun afterApprovalCheck(s: Security, outcome: CheckOutcome): Verdict = when (outcome) {
        CheckOutcome.CONFIRMED -> Verdict.Go
        CheckOutcome.CANCELLED -> Verdict.Stop(null)
        CheckOutcome.FAILED -> Verdict.Stop(CHECK_NOT_SHOWN)
        CheckOutcome.UNAVAILABLE ->
            if (s.anyLockOn) Verdict.Stop(noCheckSentence(s.method, "Nothing was approved.")) else Verdict.Go
    }

    /**
     * After the check asked for before a loosening, or before Show or
     * Unlock. Only a real confirmation lets it through: a phone that cannot
     * check cannot loosen, or anyone holding it could turn the locks off
     * and then approve.
     */
    fun afterOwnerCheck(method: CheckMethod, outcome: CheckOutcome, what: String): Verdict = when (outcome) {
        CheckOutcome.CONFIRMED -> Verdict.Go
        CheckOutcome.CANCELLED -> Verdict.Stop(null)
        CheckOutcome.FAILED -> Verdict.Stop("The fingerprint or PIN check could not be shown just now, so $what. Try again in a moment.")
        CheckOutcome.UNAVAILABLE -> Verdict.Stop(noCheckSentence(method, what.replaceFirstChar { it.uppercase() } + "."))
    }

    /**
     * True when going from [from] to [to] weakens anything. Any one field is
     * enough: a change that tightens one thing and loosens another still
     * needs the check.
     */
    fun loosens(from: Security, to: Security): Boolean =
        (from.appLock && !to.appLock) ||
            to.relockAfter.ms > from.relockAfter.ms ||
            (from.approvals == ApprovalCheck.EVERY && to.approvals == ApprovalCheck.RISKY) ||
            (from.privateLists && !to.privateLists) ||
            (from.method == CheckMethod.FINGERPRINT_ONLY && to.method == CheckMethod.FINGERPRINT_OR_PIN)

    /**
     * Why a tightening cannot be taken, or null when it can. [availability]
     * is what the phone says about [to]'s method.
     *
     * Only a change that would lock the owner out is refused: turning
     * anything on when the phone has no way to check at all. Everything
     * else tightens at once.
     */
    fun refuseTightening(to: Security, availability: CheckAvailability): String? {
        if (!to.anyLockOn) return null
        return when (availability) {
            CheckAvailability.READY, CheckAvailability.NOT_NOW -> null
            CheckAvailability.NO_HARDWARE ->
                if (to.method == CheckMethod.FINGERPRINT_ONLY) {
                    "This phone has no fingerprint sensor that Android rates as strong, " +
                        "so Fingerprint only would lock you out. Nothing was changed."
                } else {
                    "This phone cannot check a fingerprint or PIN, so this lock would " +
                        "lock you out. Nothing was changed."
                }
            CheckAvailability.NOT_SET_UP ->
                if (to.method == CheckMethod.FINGERPRINT_ONLY) {
                    "Add a fingerprint in Android's Settings first (Security), then " +
                        "choose Fingerprint only. Nothing was changed."
                } else {
                    "Set a screen lock in Android's Settings first (Security, Screen lock), " +
                        "then turn this on. Nothing was changed."
                }
        }
    }

    /** The sentence for "the chosen method cannot check on this phone". */
    fun noCheckSentence(method: CheckMethod, lead: String): String =
        if (method == CheckMethod.FINGERPRINT_ONLY) {
            "$lead This phone has no fingerprint set up, and you chose Fingerprint only. " +
                "Add a fingerprint in Android's Settings (Security)."
        } else {
            "$lead This phone has no screen lock, so Jarvis cannot check it is you. " +
                "Set one in Android's Settings (Security, Screen lock)."
        }

    /** One line for the Security card on Checks. */
    fun summary(s: Security): String {
        if (!s.anyLockOn) return "Off. Your fingerprint or PIN is asked for risky approvals only."
        val parts = buildList {
            add(if (s.appLock) "App lock on (${s.relockAfter.label.lowercase()})" else "App lock off")
            add(if (s.approvals == ApprovalCheck.EVERY) "every approval asks" else "risky approvals ask")
            if (s.privateLists) add("memory lists hidden")
            if (s.method == CheckMethod.FINGERPRINT_ONLY) add("fingerprint only")
        }
        return parts.joinToString(", ").replaceFirstChar { it.uppercase() } + "."
    }

    const val CHECK_NOT_SHOWN =
        "The fingerprint or PIN check could not be shown just now, so nothing was sent. " +
            "Try again in a moment."

    // ------------------------------------------------------------ storage --

    /** The settings as the strings [ClientSettings] saves. Nothing here is secret. */
    fun toStored(s: Security): Map<String, String> = mapOf(
        KEY_APP_LOCK to s.appLock.toString(),
        KEY_RELOCK to s.relockAfter.wire,
        KEY_APPROVALS to s.approvals.wire,
        KEY_PRIVATE to s.privateLists.toString(),
        KEY_METHOD to s.method.wire,
    )

    /**
     * Back from storage. A value that cannot be read falls back to the
     * default for that one setting - which is today's behaviour, never
     * something looser than it.
     */
    fun fromStored(get: (String) -> String?): Security = Security(
        appLock = get(KEY_APP_LOCK) == "true",
        relockAfter = RelockAfter.fromWire(get(KEY_RELOCK)),
        approvals = ApprovalCheck.fromWire(get(KEY_APPROVALS)),
        privateLists = get(KEY_PRIVATE) == "true",
        method = CheckMethod.fromWire(get(KEY_METHOD)),
    )

    const val KEY_APP_LOCK = "security_app_lock"
    const val KEY_RELOCK = "security_relock_after"
    const val KEY_APPROVALS = "security_approvals"
    const val KEY_PRIVATE = "security_private_lists"
    const val KEY_METHOD = "security_method"
}

/**
 * The app lock's clock: whether Jarvis is unlocked right now, and whether
 * Mind's private lists are showing. One per process, fed monotonic times
 * (`SystemClock.elapsedRealtime`) by the activity. Nothing here is saved,
 * so a restarted app always starts locked.
 *
 * The one subtle part is the fingerprint or PIN check itself. Android's PIN
 * screen is a separate window, so asking for the PIN takes Jarvis out of
 * sight for a few seconds - which with "Straight away" would lock the app
 * the moment it had been unlocked. So an absence that happens during a
 * check is decided when the check ends: a confirmed check means the owner
 * is here and the absence does not count; anything else means it counts
 * from when they left.
 */
class LockSession {
    var unlocked: Boolean = false
        private set

    /** Mind's private lists are showing. Hidden again whenever the app relocks. */
    var privateShown: Boolean = false
        private set

    private var awayFrom: Long? = null
    private var awayBeforeCheck: Long? = null
    private var inSight = true
    private var checking = false

    /** Whether the whole app should be behind the lock screen now. */
    fun locked(s: Security): Boolean = s.appLock && !unlocked

    /** Whether Mind's private lists should be hidden now. */
    fun privateHidden(s: Security): Boolean = s.privateLists && !privateShown

    /** Jarvis went out of sight (not a rotation - the activity checks that). */
    fun left(nowMs: Long) {
        inSight = false
        if (awayFrom == null) awayFrom = nowMs
    }

    /** Jarvis is back in sight. */
    fun returned(nowMs: Long, s: Security) {
        inSight = true
        if (checking) return
        settle(nowMs, s)
    }

    fun beginCheck() {
        checking = true
        awayBeforeCheck = awayFrom
    }

    /** The check ended. [nowMs] and [s] decide an absence that happened during it. */
    fun endCheck(outcome: CheckOutcome, nowMs: Long, s: Security) {
        checking = false
        if (outcome == CheckOutcome.CONFIRMED) {
            // The owner just proved they are here, so an absence that began
            // during the check was the check (Android's PIN screen). Cleared
            // whether or not Jarvis is back in sight yet: the success can
            // arrive a moment before the activity is shown again. An absence
            // from before the check - there should not be one - still counts.
            awayFrom = awayBeforeCheck
            if (inSight) settle(nowMs, s)
            return
        }
        if (inSight) settle(nowMs, s)
    }

    fun unlock() {
        unlocked = true
    }

    fun showPrivate() {
        privateShown = true
    }

    /** Turning the app lock on: the owner is the one holding the phone, so stay open. */
    fun lockTurnedOn() {
        unlocked = true
    }

    private fun settle(nowMs: Long, s: Security) {
        val from = awayFrom ?: return
        awayFrom = null
        val away = nowMs - from
        // A clock that went backwards is treated as a long absence: the
        // safe direction.
        if (away < 0 || away >= s.relockAfter.ms) {
            unlocked = false
            privateShown = false
        }
    }
}
