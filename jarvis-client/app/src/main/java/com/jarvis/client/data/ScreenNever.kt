package com.jarvis.client.data

/**
 * The phone's "Never look at" list for "Look at this" and "Watch with me"
 * (the owner's decision of 2026-09-28, docs/SCREEN-DESIGN.md sections 3 and
 * 4): the apps Jarvis pauses on. The PC keeps its own list of programs and
 * websites; the phone's holds Android apps, on the phone.
 *
 * Three things are never looked at, whatever the owner has or has not added:
 *  - Jarvis itself (its own screen is what it would read back);
 *  - a password manager (the built-in list below);
 *  - a banking, brokerage or payment app, by the same two signals the phone
 *    notifications feature uses ([NotificationAllowList.looksLikeBanking]:
 *    the app's own Play Store category, and a list of well-known names).
 *    SAID PLAINLY in the app: a heuristic, not a guarantee - a bank neither
 *    signal catches is caught only by the owner adding it.
 * and everything the owner added ([Security.neverApps]).
 *
 * ADDING is stricter, so instant. TAKING ONE OFF loosens what Jarvis may
 * see, so it asks for the fingerprint or PIN first, like every other
 * loosening on the Security screen ([SecurityRules.loosens]). The built-in
 * entries cannot be taken off.
 *
 * No Android in this file: the Android-backed half (the app's category, and
 * the foreground app) passes what it read in, so the JVM tests hold every
 * rule ([com.jarvis.client.ScreenNeverTest]).
 */
object ScreenNever {
    /** This app. Its own screen is never read back to it. */
    const val JARVIS = "com.jarvis.client"

    /** Well-known password managers, by package. Never removable. */
    val PASSWORD_MANAGERS: Set<String> = setOf(
        "com.x8bit.bitwarden",
        "com.x8bit.bitwarden.beta",
        "com.bitwarden.authenticator",
        "com.agilebits.onepassword",
        "com.onepassword.android",
        "com.lastpass.lpandroid",
        "com.dashlane",
        "keepass2android.keepass2android",
        "keepass2android.keepass2android_nonet",
        "com.kunzisoft.keepass.free",
        "com.kunzisoft.keepass.pro",
        "org.keepassxc",
        "com.nordpass.android.app.password.manager",
        "me.proton.android.pass",
        "com.enpass.enpass",
        "com.keepersecurity.passwordmanager",
        "com.roboform.android",
        "com.stickypassword.android",
        "com.google.android.apps.authenticator2",
        "com.azure.authenticator",
        "com.authy.authy",
    )

    /** Why a look was refused for an app - a fixed list, never the app's name. */
    enum class Why(val wire: String, val words: String) {
        JARVIS("jarvis", "one of Jarvis's own screens"),
        PASSWORD_MANAGER("password_manager", "a password manager"),
        BANKING("banking", "an app that looks like a bank or payment app"),
        OWNER("never_look", "an app on your Never look at list"),
        UNKNOWN_APP("unknown_app", "a screen Jarvis cannot tell the app of"),
    }

    /**
     * Why [packageName] must not be looked at, or null when it may. [owner]
     * is the owner's own list; [category] is the app's declared Play Store
     * category (`ApplicationInfo.category`), null when unknown. A missing
     * package name is a refusal ("cannot tell" is a pause, never a look).
     */
    fun blocked(packageName: String?, owner: Set<String>, category: Int? = null): Why? {
        val p = packageName?.trim().orEmpty()
        if (p.isEmpty()) return Why.UNKNOWN_APP
        if (p == JARVIS) return Why.JARVIS
        if (p in PASSWORD_MANAGERS) return Why.PASSWORD_MANAGER
        if (NotificationAllowList.looksLikeBanking(p, category)) return Why.BANKING
        if (p in owner) return Why.OWNER
        return null
    }

    // The words on the Security screen (LookPlate), fixed here so they can be
    // held by a test and are the same wherever they are shown.
    const val SETTING_TITLE = "Let the assistant gesture read this screen"
    const val SETTING_DETAIL =
        "Off by default. When on, pressing and holding Home (or your phone's assistant " +
            "gesture) lets Jarvis read the WORDS on the screen in front, for your next " +
            "question. No picture is taken, nothing is saved, and the words go only to " +
            "your PC, over your private link. This works only when Jarvis is set as your " +
            "phone's assistant app. Turning it on asks for your fingerprint or PIN."
    const val LIST_TITLE = "Never look at these apps"
    const val LIST_DETAIL =
        "Jarvis never looks at itself, at a password manager, or at an app that looks like " +
            "a bank or payment app. That last check is a guess from the app's name and " +
            "category, not a promise, so add any app you want left alone. Password boxes " +
            "are left out of what is read, but Android does not always mark them, so add " +
            "an app here if it shows private numbers. Taking an app off this list asks " +
            "for your fingerprint or PIN."
    const val LIST_EMPTY = "You have not added any apps."

    /** What Jarvis says when it did not look. */
    fun said(why: Why): String = when (why) {
        Why.UNKNOWN_APP -> "I can't tell which app this is, so I'm not looking."
        else -> "That's ${why.words}, so I'm not looking."
    }

    private val PACKAGE = Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+$")

    /** A package name the list may hold. */
    fun validPackage(p: String): Boolean = p.length <= 200 && PACKAGE.matches(p)

    /** The owner's list as one stored string (no secrets in it). */
    fun toStored(apps: Set<String>): String = apps.filter(::validPackage).sorted().joinToString(",")

    /** Back from storage: only valid names, never more than [MAX_APPS]. */
    fun fromStored(s: String?): Set<String> =
        s.orEmpty().split(',').map { it.trim() }.filter(::validPackage).take(MAX_APPS).toSet()

    const val MAX_APPS = 200

    /** Does going from [from] to [to] take an entry off (a loosening)? */
    fun removes(from: Set<String>, to: Set<String>): Boolean = !to.containsAll(from)
}
