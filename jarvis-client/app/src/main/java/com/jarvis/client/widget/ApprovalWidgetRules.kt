package com.jarvis.client.widget

/**
 * What the home-screen approval widget may show and do while App lock (or
 * "Hide memory lists and chat history") is on. Pure, so
 * ApprovalWidgetRulesTest can check it without a phone.
 *
 * The owner decided on 2026-09-28: "Under App lock, the widgets' buttons open
 * the locked app first, in both apps." The home screen is as public as a lock
 * screen, so with the lock on the widget shows only a short fixed title, and
 * Deny stops being a one-tap action - it opens the app, which asks for the
 * unlock. Approve already only ever opens the app.
 */
object ApprovalWidgetRules {

    /** The only words shown for a waiting approval while hidden. */
    const val HIDDEN_TITLE = "A decision is waiting"

    /** Fails closed: settings that could not be read count as hidden. */
    fun hidden(settingsKnown: Boolean, appLock: Boolean, privateLists: Boolean): Boolean =
        !settingsKnown || appLock || privateLists

    /** Deny may be a one-tap action only when nothing is hidden. */
    fun denyActsDirectly(hidden: Boolean, denyOk: Boolean): Boolean = !hidden && denyOk

    /** Whether to show a Deny button at all. */
    fun showsDeny(hidden: Boolean, denyOk: Boolean): Boolean = hidden || denyOk

    /**
     * Whether the last known queue can still carry a DENY. A stale-but-
     * connected link can: page 7's "refusing is never held" (2026-10-17). A
     * link that is not connected cannot deliver anything, and the widget says
     * so rather than drawing a button that would fail. App lock is unchanged:
     * [denyActsDirectly] still routes Deny through the app.
     */
    fun denyReachable(ready: Boolean, connected: Boolean): Boolean = ready && connected

    /**
     * The card's headline, under App lock and without it.
     *
     * `notice.title` first, `title` only as the fallback - the same order, and
     * for the same reason, as `ApprovalNotifier.textFor`: `title`/`risk.why`
     * are row prose and can carry text somebody else wrote, while `notice` is
     * the desktop's own wording for the same item. While hidden, neither may
     * appear at all: only [HIDDEN_TITLE].
     *
     * Lifted out of the composable so the App-lock promise is checked on the
     * JVM (`ApprovalWidgetRulesTest`) instead of only by reading the drawing
     * code - the home screen is as public as a lock screen.
     */
    fun cardTitle(hidden: Boolean, noticeTitle: String?, title: String): String =
        if (hidden) HIDDEN_TITLE else noticeTitle?.takeIf { it.isNotBlank() } ?: title

    /**
     * The card's second line, under the same rule as [cardTitle].
     *
     * Never `summary`: it carries the readable part of `detail`, and the home
     * screen is as public as a lock screen. While hidden the line is empty
     * rather than a redacted one - a row of "•••" would still tell a passer-by
     * that there is something to read.
     */
    fun cardDetail(hidden: Boolean, noticeBody: String?, riskWhy: String): String =
        if (hidden) "" else noticeBody?.takeIf { it.isNotBlank() } ?: riskWhy
}
