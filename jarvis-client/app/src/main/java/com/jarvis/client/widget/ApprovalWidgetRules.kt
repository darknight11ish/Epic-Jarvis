package com.jarvis.client.widget

/**
 * What the home-screen approval widget may show and do while App lock (or
 * "Hide memory lists and chat history") is on. Pure, so
 * ApprovalWidgetRulesTest can check it without a phone.
 *
 * The owner decided on 2026-09-28: "Under App lock, the widgets' buttons open
 * the locked app first, in both apps." The home screen is as public as a lock
 * screen, so with the lock on the widget shows only a short fixed title, and
 * Deny stops being a one-tap action. Approve already only ever opens the app.
 *
 * The owner KEPT that rule on 2026-10-28, after a field test: on a locked
 * phone they tapped a button labelled "Deny" and it only opened the app. The
 * rule was right and the LABEL was the bug, so a hidden card now draws no Deny
 * at all - one button, [UNLOCK_LABEL], which opens the app and asks for the
 * unlock. A button's words are a promise about what the tap does; [cardButtons]
 * is where that promise is kept for both shapes.
 */
object ApprovalWidgetRules {

    /** The only words shown for a waiting approval while hidden. */
    const val HIDDEN_TITLE = "A decision is waiting"

    /** The locked card's one button. It opens the app, so it says so. */
    const val UNLOCK_LABEL = "Unlock to review"

    /** The unlocked card's two words, in the order every card draws them. */
    const val DENY_LABEL = "Deny"
    const val REVIEW_LABEL = "Review"

    /** What a tap on a card button does. */
    enum class Tap {
        /** Deny now, from the widget itself - the one direct decision it makes. */
        DENY_NOW,

        /** Open the app: the real card, and the unlock, decide there. */
        OPEN_APP,
    }

    /** One button the card draws: its words, and what a tap really does. */
    data class Button(val label: String, val tap: Tap)

    /** Fails closed: settings that could not be read count as hidden. */
    fun hidden(settingsKnown: Boolean, appLock: Boolean, privateLists: Boolean): Boolean =
        !settingsKnown || appLock || privateLists

    /**
     * Deny may be a one-tap action only when nothing is hidden AND the desktop
     * marked the item safe to refuse unread. That is now also the whole of "is
     * a Deny button drawn at all": the old `showsDeny = hidden || denyOk` was
     * what let a locked card promise a Deny it could not perform (2026-10-28).
     */
    fun denyActsDirectly(hidden: Boolean, denyOk: Boolean): Boolean = !hidden && denyOk

    /**
     * The buttons the card draws, left to right - the ONE place their shape is
     * decided, so a JVM test checks that the words match the tap instead of a
     * reader having to believe the drawing code.
     *
     *  - hidden: one button, [UNLOCK_LABEL], which opens the app. Deliberately
     *    no "Deny": under App lock a refusal cannot happen without the unlock,
     *    and a label promising one is the 2026-10-28 bug.
     *  - visible, and `deny_ok` is not false: Deny (the one direct decision),
     *    then Review ([denyActsDirectly]).
     *  - visible, `deny_ok: false`: Review only - the same "no one-tap deny on
     *    an item the PC marked unsafe to refuse unread" rule `ApprovalNotifier`
     *    already runs on, so the two surfaces agree.
     */
    fun cardButtons(hidden: Boolean, denyOk: Boolean): List<Button> = when {
        hidden -> listOf(Button(UNLOCK_LABEL, Tap.OPEN_APP))
        denyActsDirectly(hidden, denyOk) ->
            listOf(Button(DENY_LABEL, Tap.DENY_NOW), Button(REVIEW_LABEL, Tap.OPEN_APP))
        else -> listOf(Button(REVIEW_LABEL, Tap.OPEN_APP))
    }

    /**
     * Whether the last known queue can still carry a DENY. A stale-but-
     * connected link can: page 7's "refusing is never held" (2026-10-17). A
     * link that is not connected cannot deliver anything, and the widget says
     * so rather than drawing a button that would fail. App lock is unchanged:
     * a hidden card draws no direct Deny at all ([cardButtons]).
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
