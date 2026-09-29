package com.jarvis.client.net

/**
 * Small pieces of plain text and one filter that the phone's screen plates
 * (Home's "Jarvis is watching" sign, the app pickers, the Look and picture
 * mode plates) share. No Android in this file, so the JVM tests hold it
 * ([com.jarvis.client.ScreenPlateTextTest]).
 *
 * These are phone-only lines. The shared sign words stay in [ScreenRules],
 * which is pinned to the desktop.
 */
object ScreenPlateText {
    /** Shown when "Stop watching" could not reach the PC. The sign is NOT marked off then. */
    const val STOP_FAILED = "Could not reach your PC to stop it. Try again, or press Stop " +
        "everything on the PC."

    /** Second line of the PC's sign, so it is clear which screen is meant. */
    const val PC_SCREEN = "Your PC's screen"

    /** Added to an "Ending soon" line: only the PC can extend a watch. */
    const val EXTEND_ON_PC = "Extend it on the PC."

    /** Under a switch that is greyed because the link to the PC is stale or unread. */
    const val WAITING_LINK = "Waiting for the connection to your PC."

    /** Under "Watch this phone with me" when Jarvis is not the phone's assistant app. */
    const val ASSISTANT_HINT = "To ask about the screen, set Jarvis as your phone's assistant " +
        "app: Android Settings, Default apps, Digital assistant app."

    /** Pointers between the two places the screen settings live. */
    const val PICTURE_POINTER = "This also needs the Looking at your screen switch on the " +
        "Security screen."
    const val LOOK_POINTER = "Picture mode is under Settings."

    /** The PC's sign detail, with the extend hint added when it says "Ending soon". */
    fun withExtendHint(detail: String): String =
        if (detail.contains("Ending soon")) "$detail. $EXTEND_ON_PC" else detail

    /** "Remove Chrome" / "Add Chrome": what TalkBack reads for an app row's button. */
    fun removeLabel(app: String): String = "Remove $app"
    fun addLabel(app: String): String = "Add $app"

    /**
     * Keeps the apps whose name (or, failing that, package name) contains
     * [query], ignoring case and surrounding spaces. A blank query keeps all.
     */
    fun <T> filterApps(apps: List<T>, query: String, label: (T) -> String, pkg: (T) -> String): List<T> {
        val q = query.trim()
        if (q.isEmpty()) return apps
        return apps.filter { label(it).contains(q, ignoreCase = true) || pkg(it).contains(q, ignoreCase = true) }
    }
}
