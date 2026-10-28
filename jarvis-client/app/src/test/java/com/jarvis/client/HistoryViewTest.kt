package com.jarvis.client

import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.ChatTags
import com.jarvis.client.net.HistoryView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The DeepSeek-shaped History list's pure rules (the owner's ask of
 * 2026-10-27): Pinned first, one section per tag, Untagged last; a pinned
 * chat appears once; sort orders; the age words; "Show N more"; and the row
 * overflow menu. Everything here is JVM-only - no Android types.
 */
class HistoryViewTest {

    private fun row(
        id: String,
        title: String = id,
        updated: Long = 1_000L,
        tagId: Int? = null,
        pinned: Boolean = false,
        pinnedAt: Long? = null,
        kind: String = "chat",
        started: Long? = null,
    ) = ChatLog.Summary(
        id = id,
        title = title,
        started = started,
        updated = updated,
        turns = 2,
        device = "phone",
        hasVoice = false,
        tainted = false,
        kind = kind,
        tagId = tagId,
        pinned = pinned,
        pinnedAt = pinnedAt,
    )

    private val work = ChatTags.Tag(1, "Work", 0, "briefcase", 0, count = 3)
    private val learning = ChatTags.Tag(2, "Learning", 1, "book", 1, count = 1)

    // --------------------------------------------------------- sections ---

    @Test
    fun `Pinned comes first, a pinned chat appears once, and Untagged is last`() {
        val rows = listOf(
            row("u1", tagId = null, updated = 10),
            row("w1", tagId = 1, updated = 20, pinned = true),
            row("w2", tagId = 1, updated = 30),
            row("w3", tagId = 1, updated = 40),
            row("l1", tagId = 2, updated = 50),
        )
        val sections = HistoryView.sections(rows, listOf(work, learning), untagged = 1)
        assertEquals(listOf("Pinned", "Work", "Learning", "Untagged"), sections.map { it.title })
        assertEquals(listOf("pinned", "t1", "t2", "untagged"), sections.map { it.id })
        // Pinned holds only the pinned row, and it is not repeated below.
        assertEquals(listOf("w1"), sections[0].rows.map { it.id })
        assertEquals(listOf("w3", "w2"), sections[1].rows.map { it.id })
        assertEquals(listOf("l1"), sections[2].rows.map { it.id })
        assertEquals(listOf("u1"), sections[3].rows.map { it.id })
        val seen = sections.flatMap { s -> s.rows.map { it.id } }
        assertEquals(seen.size, seen.toSet().size)
        // The PC's Work count (3) has the loaded pinned Work chat taken off it.
        assertEquals(1, sections[0].count)
        assertEquals(2, sections[1].count)
        assertEquals(1, sections[2].count)
        assertEquals(1, sections[3].count)
    }

    @Test
    fun `with no tags there is one Chats section, plus Pinned when anything is pinned`() {
        val rows = listOf(row("a", updated = 2), row("b", updated = 1), row("p", pinned = true))
        val sections = HistoryView.sections(rows, emptyList(), untagged = 0)
        assertEquals(listOf("Pinned", HistoryView.CHATS), sections.map { it.title })
        assertEquals(listOf("pinned", "untagged"), sections.map { it.id })
        assertEquals(listOf("p"), sections[0].rows.map { it.id })
        assertEquals(listOf("a", "b"), sections[1].rows.map { it.id })
        assertEquals(2, sections[1].count)
    }

    @Test
    fun `a tag filter narrows the sections and keeps Pinned inside the filter`() {
        val rows = listOf(
            row("w1", tagId = 1, pinned = true),
            row("w2", tagId = 1),
            row("l1", tagId = 2),
        )
        val onlyWork = HistoryView.sections(rows, listOf(work, learning), untagged = 0, only = 1)
        assertEquals(listOf("Pinned", "Work"), onlyWork.map { it.title })
        assertEquals(listOf("w1"), onlyWork[0].rows.map { it.id })
        val onlyUntagged = HistoryView.sections(rows, listOf(work, learning), untagged = 0, only = ChatTags.UNTAGGED_KEY)
        assertTrue("nothing loose in this example", onlyUntagged.isEmpty())
    }

    @Test
    fun `a narrowed list counts the rows shown, not the PC's whole number`() {
        val rows = listOf(row("w1", tagId = 1), row("w2", tagId = 1))
        val sections = HistoryView.sections(rows, listOf(work, learning), untagged = 0, exact = false)
        assertEquals(listOf("Work"), sections.map { it.title })
        assertEquals(2, sections[0].count)
    }

    @Test
    fun `a tag with no loaded rows still says how many the PC has`() {
        val sections = HistoryView.sections(listOf(row("w1", tagId = 1)), listOf(work, learning), untagged = 0)
        assertEquals(listOf("Work", "Learning"), sections.map { it.title })
        assertEquals(3, sections[0].count)
        assertEquals(1, sections[1].count)
        assertTrue(sections[1].rows.isEmpty())
    }

    @Test
    fun `Pinned is ordered by the pin moment, not by the sort control`() {
        // The chat pinned LATER was updated EARLIER: the pin's own moment is
        // the order (docs/JARVIS-API.md section 18.3: `pinned_at DESC,
        // updated_at DESC`), whatever Newest/Oldest/Title says.
        val rows = listOf(
            row("chat-newer", updated = 900, pinned = true, pinnedAt = 100),
            row("chat-older", updated = 100, pinned = true, pinnedAt = 500),
            row("loose", updated = 950),
        )
        for (sort in HistoryView.Sort.values()) {
            val pinned = HistoryView.sections(rows, emptyList(), untagged = 0, sort = sort)[0]
            assertEquals(sort.name, listOf("chat-older", "chat-newer"), pinned.rows.map { it.id })
        }
        // Two pins in the same second: the newer chat first, as the contract says.
        val sameMoment = listOf(
            row("b", updated = 20, pinned = true, pinnedAt = 500),
            row("a", updated = 10, pinned = true, pinnedAt = 500),
        )
        assertEquals(listOf("b", "a"), HistoryView.pinnedRows(sameMoment).map { it.id })
        // An older PC sends no moment: that pin cannot claim to be the newest.
        val olderPc = listOf(
            row("no-moment", updated = 9_999, pinned = true),
            row("dated", updated = 1, pinned = true, pinnedAt = 1),
        )
        assertEquals(listOf("dated", "no-moment"), HistoryView.pinnedRows(olderPc).map { it.id })
    }

    // ------------------------------------------------------------ sort ---

    @Test
    fun `sort orders the rows inside each section`() {
        val rows = listOf(
            row("b", title = "Beta", updated = 200),
            row("a", title = "Alpha", updated = 100),
            row("c", title = "Gamma", updated = 300),
        )
        assertEquals(listOf("c", "b", "a"), HistoryView.sortRows(rows, HistoryView.Sort.NEWEST).map { it.id })
        assertEquals(listOf("a", "b", "c"), HistoryView.sortRows(rows, HistoryView.Sort.OLDEST).map { it.id })
        assertEquals(listOf("a", "b", "c"), HistoryView.sortRows(rows, HistoryView.Sort.TITLE).map { it.id })
        // A row with no time is last in both time orders, never first.
        val undated = rows + row("d", title = "Delta", updated = 0).copy(updated = null, started = null)
        assertEquals("d", HistoryView.sortRows(undated, HistoryView.Sort.NEWEST).last().id)
        assertEquals("d", HistoryView.sortRows(undated, HistoryView.Sort.OLDEST).last().id)
    }

    @Test
    fun `the sort control cycles Newest, Oldest, Title and falls back safely`() {
        assertEquals(HistoryView.Sort.NEWEST, HistoryView.sortOf(null))
        assertEquals(HistoryView.Sort.NEWEST, HistoryView.sortOf("banana"))
        assertEquals(HistoryView.Sort.OLDEST, HistoryView.sortOf("oldest"))
        assertEquals(HistoryView.Sort.TITLE, HistoryView.nextSort(HistoryView.Sort.OLDEST))
        assertEquals(HistoryView.Sort.NEWEST, HistoryView.nextSort(HistoryView.Sort.TITLE))
        assertEquals("Sort: Newest first. Tap to change.", HistoryView.sortTitle(HistoryView.Sort.NEWEST))
    }

    // ------------------------------------------------------------- age ---

    @Test
    fun `a row's age is the short form DeepSeek shows`() {
        val now = 2_000_000_000L
        assertEquals("", HistoryView.age(null, now))
        assertEquals("now", HistoryView.age(now - 0, now))
        assertEquals("now", HistoryView.age(now - 59, now))
        assertEquals("1min", HistoryView.age(now - 60, now))
        assertEquals("25min", HistoryView.age(now - 25 * 60, now))
        assertEquals("59min", HistoryView.age(now - 3_599, now))
        assertEquals("1h", HistoryView.age(now - 3_600, now))
        assertEquals("23h", HistoryView.age(now - 86_399, now))
        assertEquals("1d", HistoryView.age(now - 86_400, now))
        assertEquals("6d", HistoryView.age(now - 6 * 86_400, now))
        assertEquals("1w", HistoryView.age(now - 7 * 86_400, now))
        assertEquals("4w", HistoryView.age(now - 29 * 86_400, now))
        assertEquals("1mo", HistoryView.age(now - 30 * 86_400, now))
        assertEquals("12mo", HistoryView.age(now - 364 * 86_400, now))
        assertEquals("1y", HistoryView.age(now - 365 * 86_400, now))
        // A phone clock behind the PC's never shows a negative age.
        assertEquals("now", HistoryView.age(now + 500, now))
    }

    @Test
    fun `a row's age uses its last change, or its start when that is all there is`() {
        assertEquals("1d", HistoryView.rowAge(row("a", updated = 100_000), 100_000 + 86_400))
        assertEquals("2d", HistoryView.rowAge(row("a").copy(updated = null, started = 100_000), 100_000 + 2 * 86_400))
    }

    // ------------------------------------------------------ show more ---

    @Test
    fun `a long section shows five rows and says how many more it has loaded`() {
        val rows = (1..7).map { row("c$it", updated = it.toLong()) }
        val section = HistoryView.sections(rows, emptyList(), untagged = 0).first()
        assertEquals(7, section.rows.size)
        assertEquals(5, HistoryView.shown(section, revealed = false).size)
        assertEquals(2, HistoryView.hidden(section, revealed = false))
        assertEquals("Show 2 more", HistoryView.showMore(HistoryView.hidden(section, revealed = false)))
        assertEquals(7, HistoryView.shown(section, revealed = true).size)
        assertEquals(0, HistoryView.hidden(section, revealed = true))
        assertEquals("Show 2 more in Chats", HistoryView.showMoreTitle(HistoryView.CHATS, 2))
    }

    @Test
    fun `a short section has no Show more, and a custom limit works`() {
        val rows = (1..5).map { row("c$it") }
        val section = HistoryView.sections(rows, emptyList(), untagged = 0).first()
        assertEquals(0, HistoryView.hidden(section, revealed = false))
        assertTrue(HistoryView.isShort(section, revealed = false))
        assertEquals(3, HistoryView.shown(section, revealed = false, limit = 3).size)
        assertEquals(2, HistoryView.hidden(section, revealed = false, limit = 3))
    }

    // ------------------------------------------------------------ menu ---

    @Test
    fun `the overflow menu is Open, Pin or Unpin, Move when there are tags, Delete`() {
        assertEquals(
            listOf(HistoryView.Action.OPEN, HistoryView.Action.PIN, HistoryView.Action.DELETE),
            HistoryView.menu(emptyList(), filing = false),
        )
        assertEquals(
            listOf(
                HistoryView.Action.OPEN, HistoryView.Action.PIN,
                HistoryView.Action.MOVE, HistoryView.Action.DELETE,
            ),
            HistoryView.menu(listOf(work), filing = false),
        )
        assertTrue(HistoryView.menu(listOf(work), filing = true).isEmpty())

        assertEquals("Pin to top", HistoryView.actionLabel(HistoryView.Action.PIN, pinned = false))
        assertEquals("Unpin", HistoryView.actionLabel(HistoryView.Action.PIN, pinned = true))
        assertEquals("Move to", HistoryView.actionLabel(HistoryView.Action.MOVE, pinned = false))
        assertEquals("Delete", HistoryView.actionLabel(HistoryView.Action.DELETE, pinned = false))
        assertEquals("Chat actions for Dentist", HistoryView.actionsFor("Dentist"))
    }

    // ------------------------------------------------- section prefs ---

    @Test
    fun `each section folds under its own stored key`() {
        val rows = listOf(row("w", tagId = 1, pinned = true), row("loose", tagId = null))
        val sections = HistoryView.sections(rows, listOf(work, learning), untagged = 1)
        assertEquals(listOf("Pinned", "Work", "Learning", "Untagged"), sections.map { it.title })
        assertEquals(HistoryView.PINNED_KEY, HistoryView.prefsKey(sections[0]))
        assertEquals(1, HistoryView.prefsKey(sections[1]))
        assertEquals(2, HistoryView.prefsKey(sections[2]))
        assertEquals(ChatTags.UNTAGGED_KEY, HistoryView.prefsKey(sections[3]))
    }

    @Test
    fun `the Pinned header says its count and its folded state`() {
        assertEquals("Pinned (3)", HistoryView.pinnedHeader(3))
        assertEquals("Pinned, 3 chats, expanded", HistoryView.pinnedHeaderSpoken(3, expanded = true))
        assertEquals("Pinned, 1 chat, collapsed", HistoryView.pinnedHeaderSpoken(1, expanded = false))
    }

    // ------------------------------------------------------ pin moving ---

    @Test
    fun `only the PC's yes moves a pin in the list or in the search results`() {
        val rows = listOf(row("a"), row("b"))
        val pinned = HistoryView.withPin(rows, "a", pinned = true, at = 700)
        assertTrue(pinned.first { it.id == "a" }.pinned)
        assertEquals("the PC's pin moment goes on the row", 700L, pinned.first { it.id == "a" }.pinnedAt)
        assertFalse(pinned.first { it.id == "b" }.pinned)
        val unpinned = HistoryView.withPin(pinned, "a", pinned = false)
        assertFalse("unpinning works too", unpinned.first { it.id == "a" }.pinned)
        assertNull("and drops the pin moment", unpinned.first { it.id == "a" }.pinnedAt)

        val hit = ChatLog.Found(
            row("z"),
            hits = 2,
            snippet = ChatLog.Snippet("user", cutBefore = false, cutAfter = false, parts = listOf(ChatLog.Part("z", false))),
        )
        val search = ChatLog.Search(
            queryOk = true, why = null, whyNot = null,
            found = listOf(hit), more = false, partial = false, searched = 1,
        )
        assertTrue(HistoryView.withPin(search, "z", pinned = true, at = 900).found.single().row.pinned)
        assertEquals(900L, HistoryView.withPin(search, "z", pinned = true, at = 900).found.single().row.pinnedAt)
        assertFalse(HistoryView.withPin(search, "other", pinned = true).found.single().row.pinned)
    }

    @Test
    fun `the pin's success sentences are the two plain ones`() {
        assertEquals("Pinned to the top.", HistoryView.pinSaid(true))
        assertEquals("Pin taken off.", HistoryView.pinSaid(false))
        assertEquals("Pinned", HistoryView.PINNED_MARK)
        assertEquals("You're here", HistoryView.CURRENT)
    }

    @Test
    fun `each conversation kind has a spoken name, and an unknown one is a chat`() {
        assertEquals("Chat", HistoryView.kindSpoken("chat"))
        assertEquals("Live session", HistoryView.kindSpoken("live"))
        assertEquals("Support chat", HistoryView.kindSpoken("support"))
        assertEquals("Chat with another AI", HistoryView.kindSpoken("chatbot"))
        assertEquals("Comparison", HistoryView.kindSpoken("compare"))
        assertEquals("Chat", HistoryView.kindSpoken("something-new"))
    }

    @Test
    fun `a pinned row keeps its tag when it moves to Pinned`() {
        val rows = listOf(row("w1", tagId = 1, pinned = true), row("w2", tagId = 1))
        val sections = HistoryView.sections(rows, listOf(work), untagged = 0)
        assertEquals(1, sections[0].rows.single().tagId)
        assertEquals(1, sections[1].rows.single().tagId)
    }
}
