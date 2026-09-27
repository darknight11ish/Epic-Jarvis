package com.jarvis.client.net

/**
 * "Things you can say" - about 5-8 real sentences Jarvis already answers
 * WITHOUT the AI model. Already approved as feasibility idea I116 ("Served
 * by the PC; fills the box, never sends") and picked up by the ease-of-use
 * audit's own do-first table, row 4 (docs/EASE-OF-USE-AUDIT-2026-09-27.md):
 * "They replace the 10 shortcut rows in the empty Jarvis bar, with one line
 * 'More: right-click the Jarvis icon by the clock.' Also one 'what can you
 * do?' command answered from the same list, 3 examples on walkthrough
 * screen 2, and a Help answer in both apps. Tapping a line fills the box
 * and never sends."
 *
 * The words are `backend/jarvis_sayable.py`'s - the same "one source, both
 * apps read it" pattern `Manner.kt` and `CardWords.kt` use. Unlike a live,
 * per-PC settings list (`Reach.kt`), this list is fixed text with no
 * settings behind it, so it is a plain, hardcoded copy here rather than
 * fetched: this list has to be shown before the app has connected to
 * anything - on the input's own hint, and, on the desktop's side, in the
 * empty Jarvis bar, which is the FIRST thing painted. SayableContractTest
 * holds every word here to `contract/sayable-cases.json`, which
 * tools/gen_sayable_cases.py makes from the backend - the desktop's
 * tests/sayable.mjs reads the same file, so the two apps cannot carry a
 * different list.
 *
 * The phone has no 3-screen walkthrough to put 3 examples on (see
 * docs/ARCHITECTURE.md §8, "One-sided on purpose": the phone's pairing flow
 * is one screen, not a tour) - [WALKTHROUGH_EXAMPLES] exists so a future
 * screen, and today's contract test, both have the same 3 to work from.
 * FaqScreen.kt uses [HELP_TITLE] / [HELP_BODY] for the phone's own
 * "What can I say?" answer.
 */
object Sayable {
    /** The words above the list. */
    const val TITLE: String = "Things you can say"
    const val DETAIL: String = "Real sentences Jarvis already answers without the AI model. " +
        "Tap one to put it in the box - it does not send."

    /** The line replacing the bar's old shortcut rows on the desktop, pointing at
     *  Settings -> Shortcuts, where the rebindable hotkeys live now. Kept here too
     *  so the phone's own "What can I say?" answer can quote it. */
    const val FOOTER: String = "More: right-click the Jarvis icon by the clock."

    /** The list itself, in the order it is shown - jarvis_sayable.SENTENCES, word
     *  for word (backend/test_sayable.py proves every one really works). */
    val SENTENCES: List<String> = listOf(
        "Set a timer for 10 minutes.",
        "What did I miss?",
        "Tell me when an email from Alex arrives.",
        "Focus for 30 minutes.",
        "Remind me to call Mom at 6pm.",
        "Add milk to the shopping list.",
        "Brief me now.",
    )

    /** Three of the list, for a walkthrough screen 2 - jarvis_sayable.WALKTHROUGH_EXAMPLES.
     *  See the class doc for why the phone has none to put them on today. */
    val WALKTHROUGH_EXAMPLES: List<String> = listOf(
        "Set a timer for 10 minutes.",
        "What did I miss?",
        "Remind me to call Mom at 6pm.",
    )

    /** The Help/FAQ answer - jarvis_sayable.HELP_TITLE / HELP_BODY. */
    const val HELP_TITLE: String = "What can I say?"
    val HELP_BODY: String = "Jarvis answers some sentences straight away, without the AI " +
        "model - so they work even when the model is slow, unloaded or asleep. A few real " +
        "ones: " + SENTENCES.joinToString(" ") + " Type \"what can you do?\" any time to see " +
        "this list again. Anything else goes to the AI model as before."
}
