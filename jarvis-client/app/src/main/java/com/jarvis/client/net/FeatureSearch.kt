package com.jarvis.client.net

/**
 * The phone's "All features and abilities" search - pure rules, tested on a
 * plain JVM (the screen supplies the drawing; this file supplies the matching).
 *
 * Every one of the 140 rows is searchable by its own words: its name, what it
 * is for, the example phrase the PC wrote, and its screen path. The match is
 * tokenised (as SettingsSearch is, 2026-10-13) so one typo-free extra word
 * still finds the row, and every word typed must appear somewhere.
 *
 * It changes nothing, opens nothing and has no Android dependency.
 */
object FeatureSearch {

    /** The rows matching this query, in directory order; all rows for "". */
    fun search(query: String, rows: List<FeatureDirectory.Row> = FeatureDirectory.ROWS): List<FeatureDirectory.Row> {
        val words = tokens(query)
        if (words.isEmpty()) return rows
        return rows.filter { row -> words.all { it in haystack(row) } }
    }

    /** One row's searchable words, lower case. */
    fun haystack(row: FeatureDirectory.Row): String = buildString {
        append(row.name).append(' ')
        append(row.group).append(' ')
        append(row.why).append(' ')
        append(row.examplePhrase).append(' ')
        append(row.settingsPath).append(' ')
        append(row.label).append(' ')
        append(row.plannedWords).append(' ')
        append(row.switchKeys.joinToString(" ")).append(' ')
        append(row.typedControls.joinToString(" "))
    }.lowercase()

    /** The query as its words; punctuation and case do not matter. */
    fun tokens(query: String): List<String> =
        query.lowercase().split(Regex("[^a-z0-9]+")).filter { it.isNotEmpty() }
}
