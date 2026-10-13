package com.jarvis.client

import com.jarvis.client.ui.SettingsJump
import com.jarvis.client.ui.SettingsSearch
import com.jarvis.client.ui.SettingsSearchWords
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The search box at the top of Settings (2026-10-09) - the phone's half of the
 * desktop's search (`jarvis-desktop/src/settings-search.js`;
 * `docs/SETTINGS-UX-DESIGN.md`).
 *
 * Three things it holds that would otherwise drift, and the third is the one
 * this repository has already been bitten by once (the open-chat phrase list
 * was two separately-maintained copies):
 *
 *  1. every section on the screen can be found;
 *  2. the words in the index are really the words the app uses;
 *  3. the two apps describe the same box in the same words.
 */
class SettingsSearchTest {

    /**
     * The screen's `item(key = ...)` rows, in order: a quoted string, or a
     * `SettingsJump` constant (the search box names `SettingsJump.SEARCH_KEY`,
     * so the screen and these tests cannot disagree about it). Same reader as
     * `SettingsJumpTest`'s, kept here so this file depends on nothing else.
     */
    private fun rows(): List<String> {
        val src = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val jump = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt"
        ).readText()
        val constant = { name: String ->
            Regex("const val $name = \"([\\w.-]+)\"").find(jump)?.groupValues?.get(1)
                ?: error("SettingsJump has no const val $name")
        }
        return Regex("item\\(key\\s*=\\s*(?:\"([\\w.-]+)\"|SettingsJump\\.(\\w+))").findAll(src)
            .map { it.groupValues[1].ifEmpty { constant(it.groupValues[2]) } }
            .toList()
    }

    @Test
    fun `every Settings section can be searched, in screen order`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val rows = rows()
        // The search box is a ROW of the screen but not a SECTION: it is the
        // control that does the filtering, so it is never one of the things
        // filtered. It is still in `ROWS`, so that the screen's searchable
        // rows and the index are one list.
        val sections = rows.filter {
            it != SettingsJump.LIST_KEY && it != SettingsJump.TAIL_KEY && it != SettingsJump.SEARCH_KEY
        }
        assertEquals(
            "SettingsSearch.ROWS must be every searchable row of the screen, in order",
            sections + SettingsJump.SEARCH_KEY,
            SettingsSearch.ROWS.map { it.key },
        )
        assertEquals("no key is listed twice", sections.size, sections.toSet().size)
    }

    /**
     * The bug this holds shut, found during the rebase of 2026-10-09: being in
     * [SettingsSearch.ROWS] is not the same as being filtered. Four rows -
     * `jarvis-notify`, `handoff-front`, `limits` and `idle-new` - joined the
     * index without the `if (drawn("<key>"))` guard every other row carries,
     * so on the phone a search hid the other twenty cards and left those four
     * on screen, while the desktop hid every one. The index above cannot see
     * that: it lists a section's words whether or not the row is guarded, so
     * this is the assertion that makes the two different things one.
     */
    @Test
    fun `every indexed section is really filtered by the search box`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val unfiltered = mutableListOf<String>()
        var checked = 0
        // The guard sits on the row's own line, beside its `item(key = ...)` -
        // the shape every guarded row on this screen has (`drawn` is
        // SettingsScreen's own lambda; a row with no guard is composed even
        // while a search is on). The line is read rather than a fixed window,
        // because a hideable row's guard chain is longer than any window that
        // has to stop short of the row above it.
        for (row in Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(screen)) {
            val key = row.groupValues[1]
            if (key !in SettingsSearch.SECTION_KEYS) continue
            checked += 1
            val line = screen.substring(screen.lastIndexOf('\n', row.range.first) + 1, row.range.first)
            if (!line.contains("drawn(\"$key\")")) unfiltered += key
        }
        assertEquals(
            "every section SettingsSearch.ROWS lists must be a row of the screen, or " +
                "this test is checking fewer rows than the search indexes",
            SettingsSearch.SECTION_KEYS.size,
            checked,
        )
        assertTrue(
            "these rows carry no `if (drawn(\"<key>\"))` guard, so a search hides every " +
                "card but these: $unfiltered",
            unfiltered.isEmpty(),
        )
    }

    @Test
    fun `the search box is a row of its own, above the jump list`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val rows = rows()
        assertEquals("the box comes first", SettingsJump.SEARCH_KEY, rows.first())
        assertEquals(SettingsJump.LIST_KEY, rows[1])
        // ...and it is a control, never a section a search can hide.
        assertFalse(SettingsJump.SEARCH_KEY in SettingsJump.ENTRIES.map { it.key })
        assertFalse(SettingsJump.SEARCH_KEY in SettingsSearch.SECTION_KEYS)
        // ...and the jump list is not drawn while a search is on, because it
        // maps a screen that is not whole any more.
        assertTrue(
            "the jump list must stand down while searching",
            screen.contains("if (!searching) item(key = SettingsJump.LIST_KEY)"),
        )
    }

    @Test
    fun `every row carries a searchable index entry`() {
        for (key in SettingsSearch.SECTION_KEYS) {
            val row = SettingsSearch.row(key)
            assertTrue("$key has no words", row != null && SettingsSearch.wordsFor(key).length > 20)
        }
        assertEquals(
            "wordsFor of an unknown key is empty, not a crash",
            "",
            SettingsSearch.wordsFor("no-such-section"),
        )
    }

    @Test
    fun `the index quotes the app's own words`() {
        val client = "jarvis-client/app/src/main/java/com/jarvis/client/"
        for (row in SettingsSearch.ROWS) {
            val sources = row.source.joinToString("\n") { file ->
                wordsOf(repoFile(client + file).readText())
            }
            for (quote in row.quotes) {
                assertTrue(
                    "${row.key}: nothing in ${row.source} says \"$quote\" - the index is " +
                        "describing a screen that has changed",
                    sources.contains(quote),
                )
            }
        }
    }

    @Test
    fun `a sentence the app folds across two literals still counts`() {
        // The mismatch that made this file red on main on 2026-10-10: the
        // Limits screen says one sentence, and writes it as two literals. The
        // index quotes the sentence, which is right; reading the raw file for
        // it is what was wrong.
        val folded = "\"Turning something up asks you on the PC first, and \" +\n" +
            "                \"nothing changes until you answer there.\""
        val words = "Turning something up asks you on the PC first, and nothing changes until you answer there."
        assertFalse(
            "the raw file must NOT contain it, or this test proves nothing",
            folded.contains(words),
        )
        assertTrue(
            "a quote spanning a folded literal is the app's own words, and must be found",
            wordsOf(folded).contains(words),
        )
    }

    @Test
    fun `a search finds a section by its heading and by its own words`() {
        // The heading.
        assertTrue(SettingsSearch.matches("voice", "voice"))
        assertTrue(SettingsSearch.matches("web-search", "search"))
        assertEquals(listOf("voice"), SettingsSearch.matching("voice"))
        // The words of a control inside it.
        assertTrue(SettingsSearch.matches("folders", "obsidian"))
        assertEquals(listOf("folders"), SettingsSearch.matching("logseq"))
        // Case and accents, the same folding the desktop does.
        assertTrue(SettingsSearch.matches("voice", "VOICE"))
        assertTrue(SettingsSearch.matches("menu-visibility", "menü"))
        assertTrue(SettingsSearch.matches("voice", "jarvis's"))
        // Nothing typed is nothing matched - the screen shows everything then.
        assertFalse(SettingsSearch.matches("voice", "   "))
        assertEquals(emptyList<String>(), SettingsSearch.matching(""))
        assertEquals(emptyList<String>(), SettingsSearch.matching("zzzz"))
    }

    // ---- The typo contract (2026-10-13) --------------------------------
    //
    // The box used to be one strict substring test, so ONE typo found
    // nothing. These six hold the replacement rule, and each one was watched
    // failing against the strict matcher before it was kept: a test that
    // cannot fail is not a test. The desktop's `rank`
    // (`jarvis-desktop/src/settings-search.js`) is being changed to the same
    // rule in a separate PR, so the two apps cannot drift.

    @Test
    fun `one typo still finds the section`() {
        // "notifcation" is one deleted letter from "notifications", which is
        // the word the notification sections are about - all three of them,
        // so the row that must be found is asserted by name rather than by
        // count. Four to seven letters buys one edit.
        assertTrue(SettingsSearch.matching("notifcation").contains("jarvis-notify"))
        // "securty" is one deleted letter from the heading "Security".
        assertTrue(SettingsSearch.matching("securty").contains("security"))
        // The word typed right still finds exactly its own section, so the
        // fuzzy step has not loosened an exact search.
        assertEquals(listOf("security"), SettingsSearch.matching("security"))
    }

    @Test
    fun `a transposition still finds the section`() {
        // "securtiy" is "security" with the "ti" the wrong way round. A
        // swapped pair is ONE edit, not two, or this would need a tolerance
        // the length table does not give an eight-letter word.
        assertTrue(SettingsSearch.matching("securtiy").contains("security"))
        assertTrue(
            "a swapped pair is one mistake",
            SettingsSearch.wordMatches("vocie", "voice"),
        )
    }

    @Test
    fun `a too-short token does not fuzzy-match a longer word`() {
        // "cat" must never find "chat": one edit in a three-letter word turns
        // it into a different word. No setting says "chat", so this asks the
        // rule about the two words directly (the same rule `rank` runs).
        assertTrue("an exact word still matches", SettingsSearch.wordMatches("cat", "cat"))
        assertTrue(
            "a word merely started still matches",
            SettingsSearch.wordMatches("cat", "category"),
        )
        assertFalse(
            "a 3-letter token must not lose a letter to match a 4-letter word",
            SettingsSearch.wordMatches("cat", "chat"),
        )
    }

    @Test
    fun `a mistyped word does not match unrelated ones`() {
        // The two-character prefix guard, seen on the real screen: "packup"
        // is one substitution away from the heading "Backups", but the first
        // letters are wrong, so the fuzzy step must not take it. The same
        // word with the right first two letters IS found (the "one typo"
        // test above proves that side).
        assertFalse(
            "a word must not fuzzy-match one that starts with different letters",
            SettingsSearch.matching("packup").contains("backup"),
        )
        // ...and a real word keeps matching exactly, once more, so this test
        // cannot pass by the matcher simply refusing everything.
        assertEquals(listOf("backup"), SettingsSearch.matching("backup"))
    }

    @Test
    fun `two words must both match - AND, not OR`() {
        // "strict" lives only in the Voice section's words, "voice" in its
        // heading - together they need the row whose words carry BOTH.
        assertEquals(listOf("voice"), SettingsSearch.matching("voice strict"))
        // One real word plus one nobody typed right matches nothing: OR would
        // have answered with every "voice" section on the screen.
        assertEquals(emptyList<String>(), SettingsSearch.matching("voice zzzz"))
        // ...and the same two words in the other order agree.
        assertEquals(listOf("voice"), SettingsSearch.matching("strict voice"))
    }

    @Test
    fun `a title match still beats a body-only match`() {
        // "security" is in the Security row's HEADING; "strict" is not in that
        // heading at all, it is in the Voice row's own words. Every word must
        // be found, so the Security row is not a match: its body may not stand
        // in for its heading, which is what makes a heading hit stronger than
        // a body hit.
        assertTrue(SettingsSearch.matching("security").contains("security"))
        assertFalse(
            "the Security row must not match on its body when its heading is " +
                "missing one of the words typed",
            SettingsSearch.matching("security strict").contains("security"),
        )
        // "strict" alone is a body-only word, and it does find the Voice row.
        assertTrue(SettingsSearch.matching("strict").contains("voice"))
    }

    @Test
    fun `normalise folds the way the desktop folds`() {
        assertEquals("wi fi", SettingsSearch.normalise("Wi-Fi"))
        assertEquals("jarvis s voice", SettingsSearch.normalise("Jarvis's voice"))
        assertEquals("cafe", SettingsSearch.normalise("café"))
        assertEquals("a b", SettingsSearch.normalise("  A   B  "))
        assertEquals("", SettingsSearch.normalise("---"))
    }

    @Test
    fun `the two apps say the same words about the same box`() {
        val js = repoFile("jarvis-desktop/src/settings-search.js").readText()
        for ((kotlinName, jsName) in listOf(
            SettingsSearchWords.LABEL to "SEARCH_LABEL",
            SettingsSearchWords.PLACEHOLDER to "SEARCH_PLACEHOLDER",
            SettingsSearchWords.CLEAR to "SEARCH_CLEAR",
            SettingsSearchWords.HINT to "SEARCH_HINT",
            SettingsSearchWords.NONE to "SEARCH_NONE",
            SettingsSearchWords.NONE_BACK to "SEARCH_NONE_BACK",
            SettingsSearchWords.ONE to "SEARCH_ONE",
            SettingsSearchWords.MANY to "SEARCH_MANY",
        )) {
            val quoted = "\"${kotlinName.replace("\"", "\\\"")}\""
            assertTrue(
                "the desktop has no `export const $jsName = $quoted;` - the two apps " +
                    "would describe the same box differently",
                js.contains("export const $jsName = $quoted;"),
            )
        }
    }

    @Test
    fun `the line under the box says what the search found`() {
        assertEquals(SettingsSearchWords.HINT, SettingsSearchWords.line("", 20))
        assertEquals(SettingsSearchWords.ONE, SettingsSearchWords.line("voice", 1))
        assertEquals("3 settings match.", SettingsSearchWords.line("voice", 3))
        assertEquals("", SettingsSearchWords.line("zzzz", 0))
        assertEquals(
            "Nothing here matches “zzzz”.",
            SettingsSearchWords.none("  zzzz  "),
        )
    }

    /**
     * The index map counts the search box as the first row.
     */
    @Test
    fun `the index map counts the search box as the first row`() {
        val screen = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
        ).readText()
        val map = screen
            .substringAfter("SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(")
            .substringBefore("\n)")
        assertTrue(
            "the search box must be in SETTINGS_ITEM_INDEX at 0 (SettingsJumpTest holds " +
                "every other number to the screen)",
            map.contains("\"search\" to SettingsJump.SEARCH_KEY_INDEX"),
        )
    }

    /**
     * THE SHARED CROSS-APP FIXTURE. `jarvis-desktop/tests/fixtures/settings-search-cases.json`
     * is generated from the desktop engine (`jarvis-desktop/src/settings-search.js`) by
     * `tools/gen-settings-search-cases.mjs`, and BOTH apps read it - so this is
     * the check that the two matching RULES agree, not just the eight words
     * they print.
     *
     * Only `hits` is asserted. `ranks` is deliberately ignored: those numbers
     * are the desktop's tiers (exact 4 / prefix 3 / fuzzy 2 / detail 1), and
     * this app's own `rank` returns the same numbers today, but neither app
     * ORDERS results by the number - both only ask whether it is above zero
     * (the desktop's `apply()` uses `rank > 0`). The numbers are therefore not
     * a contract, and asserting them here would pin this app to a detail of
     * the desktop that nothing depends on.
     *
     * The fixture lives on the desktop branch (PR #350) until that lands, so
     * on a tree without it this test SKIPS WITH A REASON rather than passing
     * quietly - a check that cannot run must say so, never read as green.
     */
    @Test
    fun `the shared cross-app fixture matches this engine`() {
        val fixture = File(
            repoRoot(),
            "jarvis-desktop/tests/fixtures/settings-search-cases.json",
        )
        if (!fixture.isFile) {
            System.out.println(
                "SKIPPED: ${fixture.path} is not on this branch yet (it arrives with the " +
                    "desktop half, PR #350) - the cross-app rule check will assert once both " +
                    "halves have merged.",
            )
            return
        }
        val root = parseJson(fixture.readText()) as? Map<*, *>
            ?: error("the fixture is not a JSON object")
        val partEntries = (root["parts"] as? Map<*, *>)?.entries
            ?.map { entry ->
                val part = entry.value as Map<*, *>
                entry.key.toString() to (part["label"].toString() to part["text"].toString())
            }
            ?: error("the fixture has no `parts`")
        val cases = root["cases"] as? List<*>
            ?: error("the fixture has no `cases`")
        val mismatches = mutableListOf<String>()
        for (case in cases) {
            val entry = case as Map<*, *>
            val query = entry["query"].toString()
            val want = (entry["hits"] as? List<*>)
                ?.map { it.toString() }?.sorted() ?: emptyList<String>()
            val got = partEntries
                .filter { (_, words) ->
                    SettingsSearch.rankPart(words.first, words.second, query) > 0
                }
                .map { it.first }
                .sorted()
            if (got != want) mismatches += "  \"$query\": expected $want, got $got"
        }
        assertTrue(
            "the phone's engine disagrees with the shared fixture on ${mismatches.size} of " +
                "${cases.size} cases:\n" + mismatches.joinToString("\n"),
            mismatches.isEmpty(),
        )
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoRoot(): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            if (File(dir, "jarvis-desktop").isDirectory) return dir
            dir = dir.parentFile
        }
        error("the repository root is not above ${System.getProperty("user.dir")}")
    }

    /**
     * A small reader for the fixture's JSON - objects, arrays, strings and
     * numbers, which is all the generator writes (no escapes, no nested
     * surprises). Written here rather than pulled in as a dependency because
     * the only thing it has to read is one generated file, and the test fails
     * loudly instead of quietly if that file ever grows a shape it cannot
     * read.
     */
    private fun parseJson(text: String): Any? {
        var at = 0
        fun skip() {
            while (at < text.length && text[at].isWhitespace()) at += 1
        }
        fun parseString(): String {
            require(text[at] == '"') { "expected a string at $at" }
            at += 1
            val out = StringBuilder()
            while (at < text.length && text[at] != '"') {
                val ch = text[at]
                if (ch == '\\') {
                    at += 1
                    when (val esc = text[at]) {
                        'n' -> out.append('\n')
                        't' -> out.append('\t')
                        'r' -> out.append('\r')
                        else -> out.append(esc)
                    }
                } else {
                    out.append(ch)
                }
                at += 1
            }
            at += 1
            return out.toString()
        }
        fun parseValue(): Any? {
            skip()
            return when (text[at]) {
                '{' -> {
                    at += 1
                    val map = LinkedHashMap<String, Any?>()
                    skip()
                    if (text[at] == '}') { at += 1; return map }
                    while (true) {
                        skip()
                        val key = parseString()
                        skip()
                        require(text[at] == ':') { "expected ':' at $at" }
                        at += 1
                        map[key] = parseValue()
                        skip()
                        when (text[at]) {
                            ',' -> at += 1
                            '}' -> { at += 1; return map }
                            else -> error("expected ',' or '}' at $at")
                        }
                    }
                }
                '[' -> {
                    at += 1
                    val list = mutableListOf<Any?>()
                    skip()
                    if (text[at] == ']') { at += 1; return list }
                    while (true) {
                        list += parseValue()
                        skip()
                        when (text[at]) {
                            ',' -> at += 1
                            ']' -> { at += 1; return list }
                            else -> error("expected ',' or ']' at $at")
                        }
                    }
                }
                '"' -> parseString()
                't' -> { at += 4; true }
                'f' -> { at += 5; false }
                'n' -> { at += 4; null }
                else -> {
                    val start = at
                    while (at < text.length && (text[at].isDigit() || text[at] == '-' ||
                            text[at] == '.' || text[at] == 'e' || text[at] == 'E')) at += 1
                    text.substring(start, at).toLongOrNull() ?: text.substring(start, at).toDouble()
                }
            }
        }
        return parseValue()
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /**
     * A source file's words as the app really says them.
     *
     * The app folds a long sentence across two literals — `"one " + "two"` — so
     * the sentence a screen shows is not a contiguous run of characters in the
     * file it is written in. Reading the file raw for a quote therefore fails
     * on the `" + "` in the middle, which says nothing about whether the screen
     * still says it: that is a reader artefact, not drift. Joining adjacent
     * literals first is what makes the check mean what its name says.
     *
     * (Measured 2026-10-10: this made the `limits` row red on `main` while the
     * Limits screen still carried the sentence word for word.)
     */
    private fun wordsOf(source: String): String = source.replace(Regex("\"\\s*\\+\\s*\""), "")
}
