package com.jarvis.client.net

/**
 * "Past approvals" - the words and the one rule of the phone's read-only list
 * of cards already decided (the owner's decision, 2026-09-27: "A read-only list
 * of past approvals (title, Approved / Denied / Timed out, when, which
 * device)"; docs/JARVIS-API.md section 42).
 *
 * The rows themselves are [GateHistoryItem]s, read by [JarvisApi.gateHistoryRead]
 * from the `history` half of `/api/pending` - no new route, no new gate action,
 * nothing this file can decide. It holds the words and [rows], which is the one
 * piece of behaviour worth a unit test on a machine with no Android SDK: which
 * filter shows which outcome, newest decision first.
 *
 * The three outcome words are NOT written here. They are
 * [GateHistoryItem.outcomeLabel]'s, because those are exactly the words the
 * backend records (`approved`, `denied`, `expired`/`timed_out`) and the ones
 * the desktop's Activity pane shows - so the phone and the PC agree by reading
 * the same mapping rather than by two lists of words that can drift apart. The
 * filter labels below are held to it by PastApprovalsTest.
 *
 * There are deliberately no action words in this file: no Approve, Deny,
 * Cancel, Clear, Retry-a-card or Open-again. The screen that draws this list
 * draws no button on a row at all - a decided card is a record, not a question.
 */
object PastApprovals {

    /** The screen's own title, and what the Inbox calls the row that opens it. */
    const val TITLE = "Past approvals"

    /**
     * The one plain line under the title. The desktop's Activity pane says the
     * same thing in its own note (`jarvis-desktop/src/brain.html`): what each
     * card was, how it ended, when, which device - and that nothing here can
     * be undone or reopened.
     */
    const val LEAD = "Cards you have already decided. Read-only: nothing here " +
        "can be approved, undone or reopened."

    /**
     * No history at all. The desktop's own words for the same empty pane
     * (`renderActivity`'s last argument), kept letter for letter so the phone
     * and the PC say the same thing.
     */
    const val EMPTY = "Nothing decided yet."

    /** The Inbox row's second line - what is behind it, and that it decides nothing. */
    const val ENTRY_ABOUT = "Approved, denied and timed out cards - read-only."

    /** The Inbox row's action, and the screen's Refresh. */
    const val OPEN = "Open"

    /** Before the first answer, on this run of the app. */
    const val READING = "Reading…"

    /** A read that failed, in the same shape the Inbox's own lists use. */
    fun failed(why: String): String = "Could not read past approvals: $why"

    /** A re-read that failed while older rows are still on screen below. */
    fun failedAgain(why: String): String = "Could not read past approvals again: $why"

    /** This desktop has no approval history to read (404 or 503). No Retry. */
    const val NOT_HERE = "Past approvals: not on this backend."

    /** The sentence under a failed read whose rows from the last read stay below. */
    const val SHOWING_OLD = "What is shown below is from the last read that worked."

    /** The filter's own id for "show everything". */
    const val ALL = "all"

    /**
     * One filter chip: [id] as stored on screen, [label] as the owner reads it.
     * The labels are the desktop's four (`renderActivity`'s own list) and the
     * three outcomes are [GateHistoryItem.outcomeLabel]'s words.
     */
    data class Filter(val id: String, val label: String)

    /** All, then the three outcomes in the order the desktop lists them. */
    val FILTERS: List<Filter> = listOf(
        Filter(ALL, "All"),
        Filter("approved", "Approved"),
        Filter("denied", "Denied"),
        Filter("timed_out", "Timed out"),
    )

    /**
     * What to say when the chosen filter has no rows but the list itself is not
     * empty: one sentence per outcome, so an empty page under a chip cannot
     * read as a broken chip. Keyed by [FILTERS]'s own ids - PastApprovalsTest
     * holds the keys to them, so a fifth chip cannot be added without one.
     */
    val NONE_THIS_WAY: Map<String, String> = mapOf(
        "approved" to "Nothing here was approved.",
        "denied" to "Nothing here was denied.",
        "timed_out" to "Nothing here timed out.",
    )

    /** [NONE_THIS_WAY] for [id], or [EMPTY] for a filter that cannot be empty. */
    fun noneThisWay(id: String): String = NONE_THIS_WAY[id] ?: EMPTY

    /**
     * The rows to draw for [filter]: only that outcome, newest decision first.
     *
     * An unrecognised [filter] shows everything, which is also what the
     * screen's own state starts as - a filter that is not one of the four
     * cannot hide a row the owner asked to see.
     *
     * A row whose outcome the phone could not recognise reads "Not reported"
     * ([GateHistoryItem.outcomeLabel]) and so appears under All and under
     * none of the three: it is not a guess at approved, denied or timed out,
     * and the filter must not turn it into one.
     */
    fun rows(items: List<GateHistoryItem>, filter: String): List<GateHistoryItem> {
        val wanted = FILTERS.firstOrNull { it.id == filter && it.id != ALL }?.label
        return items
            .filter { wanted == null || it.outcomeLabel == wanted }
            .sortedByDescending { it.whenAt }
    }

    /**
     * The three outcome words, in the filter's own order. They are the same
     * words [GateHistoryItem.outcomeLabel] produces for `approved`, `denied`
     * and `expired`/`timed_out` (its fourth, "Not reported", is deliberately
     * not here - it is what a row the phone cannot read says, not an outcome a
     * chip may offer). The test holds them together, so a chip can never say
     * something no row can carry.
     */
    val OUTCOME_WORDS: List<String> = FILTERS.filter { it.id != ALL }.map { it.label }
}
