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
    /**
     * "Swipe to approve or deny" on the phone's approval cards (the owner,
     * 2026-09-28: a setting that can be turned off). On by default - the
     * behaviour before the setting existed. Off, every card is decided with
     * its buttons only, even one the PC marks `risk.swipe_ok`. Turning it off
     * is stricter, so instant; turning it back on loosens, so it needs the
     * check ([SecurityRules.loosens]).
     */
    val swipeDecides: Boolean = true,
    /**
     * "End Live when" (the owner's decision of 2026-09-28, the Jarvis Live
     * extras: the same setting as the PC's). With App lock on, Jarvis Live
     * on this phone ends when App lock would ask again (the default, as
     * before), or - looser, so it asks for the fingerprint or PIN - only
     * when the phone's own screen lock comes on ([SecurityRules.liveEndsNow]).
     * With App lock off neither ends it. Back to the default is instant.
     */
    val liveEnd: LiveEnd = LiveEnd.APP_LOCK,
    /**
     * "Let the assistant gesture read the screen" (the owner's decision of
     * 2026-09-28, docs/SCREEN-DESIGN.md section 3): OFF by default. Turning
     * it on lets Jarvis read the words on the phone's screen when the owner
     * invokes the assistant, so it LOOSENS what Jarvis may see and asks for
     * the fingerprint or PIN ([SecurityRules.loosens]); off is instant.
     */
    val screenRead: Boolean = false,
    /**
     * The apps the owner never wants looked at, on top of the built-in ones
     * ([ScreenNever]: Jarvis itself, password managers, bank-looking apps).
     * Adding is stricter, so instant; taking one off loosens, so it asks for
     * the fingerprint or PIN.
     */
    val neverApps: Set<String> = emptySet(),
) {
    /**
     * True when the owner has asked for anything stricter than the defaults.
     * Then a phone with no way to check also keeps the app lock and hidden
     * lists shut, and refuses every approval that needed the check. (A risky
     * approval is refused on such a phone either way - the owner's "no lock,
     * no risky approval", 2026-09-25.)
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

/**
 * When App lock ends Jarvis Live on this phone - the same setting as the PC's
 * (`live_end`: "When App lock would ask again" / "Only when Windows locks").
 */
enum class LiveEnd(val wire: String, val label: String) {
    /** The default, strict: when App lock would lock Jarvis again ("Lock again after"). */
    APP_LOCK("app_lock", "When App lock would ask again"),

    /** Looser: only when the phone's own screen lock comes on. */
    SCREEN_LOCK("screen_lock", "Only when the phone's screen locks"),
    ;

    companion object {
        /** Missing or unreadable reads as the strict default, never the looser one. */
        fun fromWire(s: String?): LiveEnd = entries.firstOrNull { it.wire == s } ?: APP_LOCK
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

    /**
     * What to do after a check. [Stop.say] is null when nothing needs saying.
     * [Stop.offerLockSettings]: the fix is in Android's own settings, so the
     * message comes with a button that opens them ([OPEN_LOCK_SETTINGS]).
     */
    sealed interface Verdict {
        data object Go : Verdict
        data class Stop(val say: String?, val offerLockSettings: Boolean = false) : Verdict
    }

    /**
     * After the check for an approval. Only a confirmed check lets it through.
     *
     * UNAVAILABLE - this phone has no way to check - refuses, whatever the
     * settings say: the owner's "no lock, no risky approval" (2026-09-25).
     * With no lock turned on only a risky approval comes here
     * ([approvalNeedsCheck]), and it used to go through without a check; a
     * phone anyone can pick up and unlock was a way round the one check that
     * matters. The sentence says how to fix it, with a button that opens
     * Android's settings. The PC says the same about Windows Hello
     * (lock/rules.rs `NO_HELLO_NO_RISKY`, jarvis_owner_check.NOT_SET_UP).
     */
    fun afterApprovalCheck(s: Security, outcome: CheckOutcome): Verdict = when (outcome) {
        CheckOutcome.CONFIRMED -> Verdict.Go
        CheckOutcome.CANCELLED -> Verdict.Stop(null)
        CheckOutcome.FAILED -> Verdict.Stop(CHECK_NOT_SHOWN)
        CheckOutcome.UNAVAILABLE ->
            if (s.anyLockOn) {
                Verdict.Stop(noCheckSentence(s.method, APPROVAL_LEAD), offerLockSettings = true)
            } else {
                Verdict.Stop(NO_SCREEN_LOCK, offerLockSettings = true)
            }
    }

    /**
     * True when [text] is one of [afterApprovalCheck]'s "this phone cannot
     * check" sentences, so the notice that shows it offers
     * [OPEN_LOCK_SETTINGS]. Matched on the whole sentence: nothing else the
     * app says gets the button.
     */
    fun offersLockSettings(text: String?): Boolean =
        text != null && (
            text == NO_SCREEN_LOCK ||
                CheckMethod.entries.any { text == noCheckSentence(it, APPROVAL_LEAD) }
            )

    /**
     * The warning on the Security screen while this phone cannot check.
     * [Security.anyLockOn] decides what it covers: with no lock on, only risky
     * approvals are held.
     */
    fun noCheckWarning(s: Security): String =
        if (s.anyLockOn) {
            noCheckSentence(
                s.method,
                "Approvals that need the check are refused for now, and the app " +
                    "lock and hidden lists stay shut.",
            )
        } else {
            noCheckSentence(s.method, "Risky approvals are refused for now.")
        }

    /**
     * What "Hide memory lists and chat history" hides - the SAME sentence as
     * the desktop's `PRIVATE_HIDES` (security-settings.js; continuity audit
     * 2026-09-26, #1). SecurityRulesTest and the desktop's tests/security.mjs
     * check each other's copy.
     */
    const val PRIVATE_HIDES = "Your memory lists, chat history and deep questions, the " +
        "words of your timers, reminders and lists, the morning briefing's lines and what a " +
        "focus session is on stay hidden until you confirm it is you. Their notifications say " +
        "only what kind of thing is due."

    private const val APPROVAL_LEAD = "Nothing was approved."

    /**
     * A risky approval on a phone with no screen lock and no lock turned on
     * in Jarvis (the owner's decision, 2026-09-25). The PC's words for
     * Windows Hello have the same shape.
     */
    const val NO_SCREEN_LOCK =
        "Nothing was approved. This phone has no screen lock, so Jarvis cannot check it is you, " +
            "and risky approvals are refused until it has one. Set a screen lock in Android's " +
            "Settings (Security, Screen lock) to approve risky actions."

    /** The button beside a "this phone cannot check" notice. */
    const val OPEN_LOCK_SETTINGS = "Open screen-lock settings"

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
     * True when screenshots, screen recording and casting of Jarvis are
     * blocked (Android's FLAG_SECURE, set in MainActivity; apps security
     * audit L5, the owner's decision 2026-09-25). On while App lock or "Hide
     * memory lists and chat history" is on: both say the owner does not want
     * what Jarvis shows seen by someone else, and a screenshot, a recording
     * or a cast screen is another way to see it. The whole app, not chosen
     * screens: memory, history and answers are on most of them. Off with
     * both off, so nothing changes for an owner who asked for neither. The
     * recent-apps picture is blank under the same rule.
     *
     * [keyShown]: the pairing token is shown in plain letters on the pairing
     * screen ("Show token", phone walk-through C8, 2026-09-27). While it is,
     * the screen cannot be captured whatever the settings say - the token is
     * the one secret that opens Jarvis - and the rule falls back to the
     * settings the moment it is hidden again.
     *
     * [handoffShown]: "Solve it here" shows a live picture of the PC's
     * browser window (the owner's decision of 2026-09-28: never saved on
     * either side), so it cannot be captured either while it shows.
     */
    fun blockScreenCapture(s: Security, keyShown: Boolean = false, handoffShown: Boolean = false): Boolean =
        s.appLock || s.privateLists || keyShown || handoffShown

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
            (from.method == CheckMethod.FINGERPRINT_ONLY && to.method == CheckMethod.FINGERPRINT_OR_PIN) ||
            (!from.swipeDecides && to.swipeDecides) ||
            (from.liveEnd == LiveEnd.APP_LOCK && to.liveEnd == LiveEnd.SCREEN_LOCK) ||
            (!from.screenRead && to.screenRead) ||
            ScreenNever.removes(from.neverApps, to.neverApps)

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
        val swipeOff = (if (s.swipeDecides) "" else " $SWIPE_OFF_SUMMARY") +
            (if (s.appLock && s.liveEnd == LiveEnd.SCREEN_LOCK) " $LIVE_END_SUMMARY" else "")
        if (!s.anyLockOn) return "Off. Your fingerprint or PIN is asked for risky approvals only.$swipeOff"
        val parts = buildList {
            add(if (s.appLock) "App lock on (${s.relockAfter.label.lowercase()})" else "App lock off")
            add(if (s.approvals == ApprovalCheck.EVERY) "every approval asks" else "risky approvals ask")
            if (s.privateLists) add("memory lists hidden")
            if (s.method == CheckMethod.FINGERPRINT_ONLY) add("fingerprint only")
        }
        return parts.joinToString(", ").replaceFirstChar { it.uppercase() } + "." + swipeOff
    }

    /**
     * Does Jarvis Live on this phone end now, and why ("app_lock" or
     * "screen_lock", the PC's end reasons) - or null. [appLockWouldLock]:
     * App lock would lock Jarvis now ([LockSession.wouldLock]);
     * [screenLocked]: the phone's own screen lock is on (Android's
     * KeyguardManager.isDeviceLocked). With App lock off, nothing here ends
     * Live - as before the setting existed.
     */
    fun liveEndsNow(s: Security, appLockWouldLock: Boolean, screenLocked: Boolean): String? {
        if (!s.appLock) return null
        return when (s.liveEnd) {
            LiveEnd.APP_LOCK -> if (appLockWouldLock) "app_lock" else null
            LiveEnd.SCREEN_LOCK -> if (screenLocked) "screen_lock" else null
        }
    }

    /** The Security screen's "End Live when" setting, and what it does. */
    const val LIVE_END_TITLE = "End Live when"
    const val LIVE_END_DETAIL =
        "While App lock is on. \"When App lock would ask again\" ends Jarvis Live after " +
            "\"Lock again after\" away from Jarvis. \"Only when the phone's screen locks\" lets " +
            "you use other apps while you talk, and ends Live when the phone locks. Choosing " +
            "that asks for your fingerprint or PIN."

    /** Said on Checks' Security line when Live ends only at the screen lock. */
    const val LIVE_END_SUMMARY = "Live ends only when the phone's screen locks."

    /** Said on Checks' Security line when swiping is off. */
    const val SWIPE_OFF_SUMMARY = "Swiping to decide is off."

    /** The Security screen's switch, and what it does. */
    const val SWIPE_TITLE = "Swipe to approve or deny"
    const val SWIPE_DETAIL =
        "On cards your PC marks as safe for a quick gesture, swipe right to approve " +
            "and left to deny. Off, every card is decided with its buttons only. " +
            "Turning it back on asks for your fingerprint or PIN."

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
        KEY_SWIPE to s.swipeDecides.toString(),
        KEY_LIVE_END to s.liveEnd.wire,
        KEY_SCREEN_READ to s.screenRead.toString(),
        KEY_NEVER_APPS to ScreenNever.toStored(s.neverApps),
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
        // Missing or unreadable reads as on: the behaviour before the
        // setting existed, never something looser than it.
        swipeDecides = get(KEY_SWIPE) != "false",
        liveEnd = LiveEnd.fromWire(get(KEY_LIVE_END)),
        // Missing or unreadable reads as OFF: the stricter reading.
        screenRead = get(KEY_SCREEN_READ) == "true",
        neverApps = ScreenNever.fromStored(get(KEY_NEVER_APPS)),
    )

    const val KEY_APP_LOCK = "security_app_lock"
    const val KEY_RELOCK = "security_relock_after"
    const val KEY_APPROVALS = "security_approvals"
    const val KEY_PRIVATE = "security_private_lists"
    const val KEY_METHOD = "security_method"
    const val KEY_SWIPE = "security_swipe_decides"
    const val KEY_LIVE_END = "security_live_end"
    const val KEY_SCREEN_READ = "security_screen_read"
    const val KEY_NEVER_APPS = "security_never_apps"
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

    /**
     * Whether App lock WOULD lock Jarvis now, were it brought back in sight:
     * locked already, or out of sight for "Lock again after" or longer (a
     * fingerprint or PIN check under way does not count). Asks nothing and
     * changes nothing. Jarvis Live on this phone ends then.
     */
    fun wouldLock(nowMs: Long, s: Security): Boolean {
        if (!s.appLock) return false
        if (!unlocked) return true
        if (checking) return false
        val from = awayFrom ?: return false
        val away = nowMs - from
        return away < 0 || away >= s.relockAfter.ms
    }

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
