package com.jarvis.client.widget

/**
 * What the home-screen approval widget may show and do while App lock (or
 * "Hide memory lists and chat history") is on. Pure, so
 * `ApprovalWidgetRulesTest`, `DenyNotHeldTest` and `WidgetStatesTest` can check
 * it without a phone.
 *
 * TWO QUESTIONS, AND ONLY THE SECOND ONE MOVES THE BUTTONS (owner,
 * 2026-10-28):
 *
 * > "tapping deny on the widget should deny it, except in cases of needing
 * > extra approval like a finger print or a confirm deny or approve for extra
 * > important decisions."
 *
 * So a refusal is a real refusal whenever the CARD allows an unread one -
 * **including while the widget is hidden under App lock**. The field evidence
 * is why this changed: on CI APK v0.2.2979 (main after #908), with the phone
 * in App lock / private view, the card said "Needs your OK / A decision is
 * waiting" with Deny and Review, the owner tapped **Deny**, and it only
 * **opened the app**. The old rule (`denyActsDirectly(hidden, denyOk) =
 * !hidden && denyOk`) made hiding the card's words also drop its one safe
 * action. Those are two different things: [cardTitle] hides WORDS, and a
 * denial is the direction that cannot approve anything.
 *
 * The one card that still opens the app is the one that says so itself:
 * `notice.denyOk == false` - the desktop asking for the denial to be confirmed
 * (a fingerprint, a PC-only check, or another step the server added). Then
 * [buttons] draws a single app-opening action and **never a bare "Deny"**: a
 * button must not promise a refusal it will not perform.
 *
 * PC-only cards are deliberately NOT in that set on their own. The phone's
 * `JarvisRuntime.decide` gates only `approve && item.pcOnly`, and this
 * project's own contract says the same thing ("Deny may be a notification
 * action. Approve may not" - `docs/ARCHITECTURE.md` §"The notification
 * contract"), so a PC-only card's deny really does go through from the phone.
 * Only the server's `deny_ok: false` moves Deny into the app.
 */
object ApprovalWidgetRules {

    /** The only words shown for a waiting approval while hidden. */
    const val HIDDEN_TITLE = "A decision is waiting"

    /** A button the card may draw. */
    enum class WidgetButton {
        /** Sends the refusal now - the only decision this widget makes itself. */
        DENY,

        /** Opens the app. Never approves anything by itself. */
        REVIEW,
    }

    /** One button to draw: which one it is, and the word on it. */
    data class WidgetButtonPlan(val button: WidgetButton, val label: String)

    /** Fails closed: settings that could not be read count as hidden. */
    fun hidden(settingsKnown: Boolean, appLock: Boolean, privateLists: Boolean): Boolean =
        !settingsKnown || appLock || privateLists

    /**
     * Deny acts directly whenever the card allows an unread deny.
     *
     * `hidden` is deliberately **not** a parameter (owner, 2026-10-28). It
     * used to read `!hidden && denyOk`, and that `!hidden` is exactly what
     * turned the owner's tapped Deny under App lock into "open the app".
     *
     * The call site passes `notice?.denyOk != false`: a row with no `notice`
     * at all (an older desktop) keeps the one-tap deny it has always had, and
     * only a card the server marked `deny_ok: false` routes into the app.
     */
    fun denyActsDirectly(denyOk: Boolean): Boolean = denyOk

    /**
     * Which buttons to draw, and the word on each, in drawing order.
     *
     * [denyActsDirectly] is the only thing that changes the **set**: a card
     * that allows an unread deny gets Deny and Review; a card that says the
     * denial needs the app gets the single app-opening action and no Deny at
     * all.
     *
     * `hidden` changes only that single action's **word**, because the two
     * cards promise different things. Unhidden, the card names where Deny went
     * ("Deny in app"), so a tap cannot be mistaken for a denial that has
     * already happened. Hidden, the card keeps to the one public word it has
     * always used ("Review") and says nothing about what kind of decision is
     * waiting - the same reason [cardTitle] and [cardDetail] are blank there.
     */
    fun buttons(hidden: Boolean, denyOk: Boolean): List<WidgetButtonPlan> {
        val deny = WidgetButtonPlan(WidgetButton.DENY, label = "Deny")
        val review = WidgetButtonPlan(
            WidgetButton.REVIEW,
            label = if (denyActsDirectly(denyOk) || hidden) "Review" else "Deny in app",
        )
        return if (denyActsDirectly(denyOk)) listOf(deny, review) else listOf(review)
    }

    /**
     * Whether the last known queue can still carry a DENY. A stale-but-
     * connected link can: page 7's "refusing is never held" (2026-10-17). A
     * link that is not connected cannot deliver anything, and the widget says
     * so rather than drawing a button that would fail.
     *
     * This is about the LINK, not the card and not the lock: App lock no
     * longer affects a denial at all - see [denyActsDirectly].
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
