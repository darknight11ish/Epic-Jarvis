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
}
