package com.jarvis.client

import com.jarvis.client.net.Entities
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's read-only "Galaxy at a glance" band (the owner's choice,
 * 2026-10-23: a summary above the list, not a canvas).
 *
 * Everything here is the pure data half - no Compose host, no emulator - so a
 * JVM test can hold it. It proves:
 *
 *  * the ONE summary line counts names and facts in plain words, singulars
 *    included;
 *  * the "most connected" names are the same shared-fact rule the list rows
 *    already say in words ([Entities.sharedPartners]): ordered by how many
 *    names they share facts with, ties by fact count then name, so the order
 *    never depends on what order the PC sent; a name that shares nothing is
 *    not in the band, and the band is capped at eight;
 *  * a label never promises an edge that is not there ("shares facts with..."
 *    is left out at zero).
 *
 * The band reads nothing new and writes nothing: it works on the list the
 * plate has already fetched. The screen-reader order and the runtime look are
 * NOT-TESTABLE here (no emulator), so they stay a field-test row - never a pass.
 */
class GalaxyBandTest {

    private fun entity(id: String, name: String, kind: String?, vararg facts: Long) =
        Entities.Entity(id, name, kind, facts.toList())

    @Test
    fun theSummaryLineCountsNamesAndFactsInPlainWords() {
        assertEquals("32 names, 118 facts", Entities.galaxySummary(32, 118))
        assertEquals("1 name, 1 fact", Entities.galaxySummary(1, 1))
        assertEquals("2 names, 1 fact", Entities.galaxySummary(2, 1))
        assertEquals("1 name, 2 facts", Entities.galaxySummary(1, 2))
        assertEquals("0 names, 0 facts", Entities.galaxySummary(0, 0))
    }

    @Test
    fun totalFactsAddsEveryNameAndNothingElse() {
        val list = listOf(
            entity("a", "Ana", "person", 1, 2),
            entity("b", "Ben", "person", 1),
            entity("c", "Cara", null, 3, 4, 5),
        )
        assertEquals(6, Entities.totalFacts(list))
        assertEquals(0, Entities.totalFacts(emptyList()))
    }

    @Test
    fun theBandIsTheNamesThatShareFactsWithTheMostOthers() {
        val ana = entity("a", "Ana", "person", 1)
        val ben = entity("b", "Ben", "person", 1, 2)
        val cara = entity("c", "Cara", "person", 2, 3)
        val dan = entity("d", "Dan", "person", 3)
        val eve = entity("e", "Eve", "person", 99)   // shares no fact with anyone
        val band = Entities.mostConnected(listOf(ana, ben, cara, dan, eve))
        // Ben and Cara share with two names each; the tie goes to the name, then
        // Ana and Dan share with one each. Eve is not in the band at all.
        assertEquals(listOf("Ben", "Cara", "Ana", "Dan"), band.map { it.name })
    }

    @Test
    fun theOrderNeverDependsOnTheOrderThePcSent() {
        val list = listOf(
            entity("c", "Cara", "person", 2, 3),
            entity("a", "Ana", "person", 1),
            entity("d", "Dan", "person", 3),
            entity("b", "Ben", "person", 1, 2),
        )
        val once = Entities.mostConnected(list).map { it.id }
        val reversed = Entities.mostConnected(list.reversed()).map { it.id }
        assertEquals(once, reversed)
        assertEquals(listOf("b", "c", "a", "d"), once)
    }

    @Test
    fun theBandIsCappedAtEightAndCanBeShorter() {
        val many = (1..12).map { i ->
            // Every name shares the same fact, so all twelve are connected;
            // the cap must still hold to eight.
            entity("e$i", "Name ${i.toString().padStart(2, '0')}", "person", 7)
        }
        assertEquals(8, Entities.mostConnected(many).size)
        assertEquals(3, Entities.mostConnected(many, limit = 3).size)
        assertTrue(Entities.mostConnected(emptyList()).isEmpty())
        assertTrue(Entities.mostConnected(many, limit = 0).isEmpty())
    }

    @Test
    fun aLabelNeverPromisesAnEdgeThatIsNotThere() {
        val priya = entity("p", "Priya", "person", 1, 2, 3, 4)
        assertEquals("Priya, 4 facts", Entities.galaxyNameLine(priya, 0))
        assertEquals("Priya, 4 facts, shares facts with 1 name",
            Entities.galaxyNameLine(priya, 1))
        assertEquals("Priya, 4 facts, shares facts with 2 names",
            Entities.galaxyNameLine(priya, 2))
    }
}
