package com.jarvis.client

import com.jarvis.client.net.Entities
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The Galaxy on the phone: what the owner asked for, and the two rules that
 * make it safe to have.
 *
 * The owner's words (2026-10-11): "can i see the galaxy on the android phone?
 * I should be able to see it". Offered a choice, he picked a light, read-only
 * version built for the phone. The Galaxy is "the map of what Jarvis knows" -
 * the people and things his saved facts mention - so the phone's version has
 * to show the same information the desktop's map carries, and it has to stay
 * read-only, which `CLAUDE.md`'s "do not build ... the memory graph ... on the
 * phone" forbids unless he says otherwise. He has now said otherwise for this
 * one screen, and no further.
 *
 * Four things are held here, in the two house styles:
 *
 *  * **Reachable** ([thePlateIsUnderAHeadingAndTwoTapsFromTheTop]): the plate
 *    is drawn, the heading that holds it is the one that fits, and the app's
 *    own menu registry knows it - so a hidden-menu test and the "N inside"
 *    count on the heading both keep working. A plate with no heading is a
 *    plate nobody can find.
 *  * **Honest when empty** ([anEmptyGalaxySaysSoInsteadOfDrawingNothing]): a
 *    fresh Jarvis must say it has nothing here, in words that cannot be read
 *    as "you have no memories".
 *  * **Draws what it was given** ([aPopulatedGalaxyDrawsTheNamesItWasGiven],
 *    [connectionsAreTheDesktopsEdgesInWords]): the names come from the read,
 *    and the connections are the desktop map's own rule - one fact naming both
 *    names - worked out from that same read.
 *  * **Never writes** ([nothingInThisPlateWrites]): no Forget, Erase, Pin,
 *    merge, rename or drag, and no route that could carry one. This is the
 *    test to read first if someone later wonders whether the read-only rule is
 *    really enforced or merely intended: it reads the shipped source and fails
 *    on the write, not on the intention.
 *
 * No unit test can press a button on a Compose screen, so the reachability and
 * read-only halves are held against the real sources - the same approach
 * `BrainSectionsTest` and `EntitiesTest` already take.
 */
class PhoneGalaxyTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private val plate: String = repoFile(main + "ui/screens/EntitiesPlate.kt").readText()
    private val entities: String = repoFile(main + "net/Entities.kt").readText()
    private val screen: String = repoFile(main + "ui/screens/BrainScreen.kt").readText()
    private val menus: String = repoFile(main + "ui/MenuPlaces.kt").readText()

    /** The same one-line reader `EntitiesTest` uses. */
    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    /** The body of a top-level function: its `fun` line to the line closing it. */
    private fun functionBody(src: String, marker: String): String {
        val at = src.indexOf(marker)
        assertTrue("$marker is gone", at >= 0)
        val rest = src.substring(at)
        val end = rest.indexOf("\n}\n")
        return if (end > 0) rest.substring(0, end) else rest
    }

    // ------------------------------------------------------- reachable ---

    @Test
    fun thePlateIsUnderAHeadingAndTwoTapsFromTheTop() {
        // Drawn at all, under the item key the heading list knows by name.
        assertTrue(
            "the Galaxy plate is not drawn on Brain",
            screen.contains("item(key = \"people-and-things\")"),
        )

        // Under a heading - and the heading that fits. "What Jarvis knows about
        // you" is where the saved facts themselves live, so the names those
        // facts mention belong there with them: one tap to open the heading,
        // one to reach the plate.
        val heading = com.jarvis.client.ui.screens.BrainSections.sectionOf("people-and-things")
        assertTrue("no heading holds the Galaxy plate, so nothing can reach it", heading != null)
        assertEquals("knows", heading!!.key)
        assertEquals("What Jarvis knows about you", heading.title)

        // The heading is drawn by the screen, so the plate is not placed under
        // a heading that does not exist.
        assertTrue(
            "the screen does not ask this file which heading holds a plate",
            screen.contains("BrainSections.sectionOf("),
        )

        // The app's own menu registry knows the plate, so the Settings list can
        // still hide it and put it back, and the heading's "N inside" count is
        // the truth. A plate drawn but unregistered is one the owner cannot
        // reach once any menu is hidden.
        assertTrue(
            "the Galaxy plate is not in the menu registry",
            menus.contains("\"people-and-things\" to \"brain.memory.people-things\""),
        )

        // Two taps: the heading is shut on arrival (BrainSectionsTest holds the
        // open/shut rule), and opening it puts the plate in the list. Its key
        // is not one of the lines that are always drawn, which is what would
        // make it visible without the heading.
        assertFalse(
            "the plate must be inside the heading, not always drawn",
            com.jarvis.client.ui.screens.BrainSections.ALWAYS_DRAWN.contains("people-and-things"),
        )
    }

    // ----------------------------------------------------------- empty ---

    @Test
    fun anEmptyGalaxySaysSoInsteadOfDrawingNothing() {
        // A fresh Jarvis has no names, and the screen says so in words rather
        // than drawing an empty list that reads like a fault. The empty branch
        // must really be there, not merely referenced: reading the source for
        // the check and the line that answers it, in that order.
        val body = functionBody(plate, "internal fun PeopleAndThingsSection(")
        val emptyAt = body.indexOf("shown.isEmpty()")
        assertTrue("the plate has no empty case at all", emptyAt >= 0)
        val branch = body.substring(emptyAt, minOf(body.length, emptyAt + 400))
        assertTrue("the empty case draws no words, so an empty memory is a blank void", branch.contains("Entities.EMPTY"))
        assertTrue("the empty message is blank", Entities.EMPTY.isNotBlank())

        // The words must not claim the owner has no memories: this list holds
        // only the names saved facts mention, so a Jarvis that knows plenty but
        // has never saved a fact naming anyone is empty here too.
        assertFalse(
            "the empty state must not say the owner has no memories: ${Entities.EMPTY}",
            Entities.EMPTY.contains("no memories", ignoreCase = true),
        )
        assertTrue(
            "the empty state should say what will fill it in: ${Entities.EMPTY}",
            Entities.EMPTY.contains("fact", ignoreCase = true),
        )
        // It is a line of text, never a colour, an icon or a zero.
        assertTrue("the empty line is not drawn as text", branch.contains("Text(Entities.EMPTY"))
    }

    // -------------------------------------------------------- populated ---

    @Test
    fun aPopulatedGalaxyDrawsTheNamesItWasGiven() {
        val list = Entities.parse(obj(entitiesBody()))!!
        // Every name read is drawn, grouped, with its own count - the same
        // grouping the list already used, now the screen the owner asked for.
        assertEquals(listOf("Priya", "Biscuit", "Garage", "Dan"), list.map { it.name })
        assertEquals(
            listOf("People", "Pets", "Projects"),
            Entities.groups(list).map { it.title },
        )
        // Biggest first within a group, then by name: Priya and Dan are both in
        // four facts, so Dan's name settles it.
        assertEquals(
            listOf(listOf("Dan", "Priya"), listOf("Biscuit"), listOf("Garage")),
            Entities.groups(list).map { g -> g.entities.map { it.name } },
        )

        // The screen really draws those names and their counts. Read through
        // the pure helper the plate draws from, so this fails if the plate
        // stops drawing the grouped names rather than merely if a word
        // disappears from the source.
        val drawn = Entities.drawnLines(list)
        for (title in listOf("People", "Pets", "Projects")) {
            assertTrue("the group heading \"$title\" is not drawn", drawn.contains(title))
        }
        for (name in listOf("Dan", "Priya", "Biscuit", "Garage")) {
            assertTrue("the name \"$name\" is not drawn", drawn.any { it.startsWith("$name,") })
        }
        assertTrue("a row does not say how many facts name it", drawn.any { it == "Dan, 4 facts" })

        val body = functionBody(plate, "internal fun PeopleAndThingsSection(")
        assertTrue("the grouped names are not drawn", body.contains("Entities.groups(shown)"))
        assertTrue("a row's words are not drawn", body.contains("Entities.rowLine(e)"))
        assertTrue("a row cannot be opened", body.contains("onClick = { openId = e.id }"))
    }

    @Test
    fun connectionsAreTheDesktopsEdgesInWords() {
        val list = Entities.parse(obj(entitiesBody()))!!
        val perFact = Entities.namesPerFact(list)
        val priya = list.first { it.name == "Priya" }
        val dan = list.first { it.name == "Dan" }

        // Priya is in fact 5 with Dan and in fact 3 with Garage, so her
        // connections are Dan and Garage - one shared fact each, in name order
        // because the counts tie.
        assertEquals(
            listOf("Dan", "Garage"),
            Entities.connections(priya, list, perFact).map { it.entity.name },
        )
        // Dan's own list is the same two names from his side: fact 5 names
        // Priya, fact 3 names Garage. One shared fact each, so the tie is
        // settled by name. Symmetric, as an edge must be.
        assertEquals(
            listOf("Priya", "Garage"),
            Entities.connections(dan, list, perFact).map { it.entity.name },
        )

        // The line reads as the desktop's edge does: the name, and how strong
        // the line is, in words. A name with nothing in common is left out
        // entirely rather than drawn as "0 shared facts" - held below.
        assertEquals("1 shared fact", Entities.sharedWords(1))
        assertEquals("4 shared facts", Entities.sharedWords(4))
        assertEquals("Dan, 1 shared fact", Entities.connectionLine(Entities.Connection(dan, 1)))

        // Most shared facts first, so the strongest line is the first one read.
        val many = Entities.parse(obj("""{"entities": [
                {"id": 1, "name": "Ann", "kind": "person", "fact_ids": [1, 2, 3]},
                {"id": 2, "name": "Bob", "kind": "person", "fact_ids": [1, 2, 3]},
                {"id": 3, "name": "Cat", "kind": "person", "fact_ids": [1]},
                {"id": 4, "name": "Dog", "kind": "pet", "fact_ids": [9]}
            ]}"""))!!
        assertEquals(
            listOf("Bob", "Cat"),
            Entities.connections(many.first(), many).map { it.entity.name },
        )
        assertEquals(3, Entities.connections(many.first(), many).first().shared)
        // A name sharing nothing is left out, and never drawn as a zero line.
        assertTrue(Entities.connections(many.first { it.name == "Dog" }, many).isEmpty())

        // The desktop's own rule: a fact naming more than twelve names is a
        // list, not a connection, so it joins nothing. Two apps drawing "who is
        // connected to whom" must not disagree.
        assertEquals(12, Entities.MAX_NAMES_PER_FACT)
        val many12 = (1..12).joinToString(",") { "{\"id\": $it, \"name\": \"N$it\", \"kind\": \"person\", \"fact_ids\": [500]}" }
        val many13 = (1..13).joinToString(",") { "{\"id\": $it, \"name\": \"N$it\", \"kind\": \"person\", \"fact_ids\": [501]}" }
        val twelve = Entities.parse(obj("""{"entities": [$many12]}"""))!!
        val thirteen = Entities.parse(obj("""{"entities": [$many13]}"""))!!
        assertEquals(11, Entities.connections(twelve.first(), twelve).size)
        assertTrue(
            "a fact naming 13 names is a list and must join nothing",
            Entities.connections(thirteen.first(), thirteen).isEmpty(),
        )

        // The connections are worked out from the names already read, so they
        // survive a failure to read the facts' words - which is the one thing
        // on this panel that is always right.
        val body = functionBody(plate, "private fun EntityFacts(")
        assertTrue("the connections are not drawn", body.contains("Entities.connections("))
        assertTrue("a connection is not drawn", body.contains("Entities.connectionLine(c)"))
        assertTrue("a name with no connections says nothing", body.contains("Entities.ALONE"))

        // Read-only showing: the control that draws a connection is plain text,
        // with no tap of its own. `Quiet` - this file's action - carries a 48dp
        // touch target and a button's own announcement, so a column of them
        // would tell TalkBack "button" about nine things that do nothing.
        val drawnAt = body.indexOf("Entities.connectionLine(c)")
        assertTrue("a connection is not drawn", drawnAt > 0)
        val call = body.substring(drawnAt, minOf(body.length, drawnAt + 240))
        assertFalse("a connection row is a control that does nothing", call.contains("onClick"))
        assertFalse("a connection row is a button", call.contains("Quiet("))
    }

    // ------------------------------------------------------- read-only ---

    @Test
    fun nothingInThisPlateWrites() {
        // The owner narrowed the standing rule for a read-only view, and the
        // read-only half is the half that must not drift. Every way this app
        // changes a saved fact or a name, checked in the shipped source: a
        // write added here fails, rather than being noticed later.
        val writes = listOf(
            "forgetAutoFact", "eraseFact", "pinFact", "unpinFact",
            "markShared", "unmarkShared", "forgetRange", "memoryErase",
            "entitiesMerge", "entitiesRename", "entitiesForget", "entityForget",
            "linkEntities", "mergeEntities", "renameEntity", "forgetEntity",
        )
        for (w in writes) {
            assertFalse("the Galaxy plate calls $w", plate.contains(w))
            assertFalse("the Galaxy's reader calls $w", entities.contains(w))
        }

        // The plate itself names no route at all: a screen that can build a
        // path can post to one, and the point is that this one cannot. Its
        // reader names exactly the one route the Galaxy is allowed - the names;
        // the facts' words come through the shared `MemoryUsed` reader below.
        assertFalse("the Galaxy plate names a route", plate.contains("\"/api/"))
        assertFalse("the Galaxy plate posts", plate.contains("api.post"))
        assertTrue(
            "the Galaxy's reader must read the names",
            entities.contains("const val PATH = \"/api/memory/entities\""),
        )
        for (route in Regex("\"/api/[a-z_/]*").findAll(entities).map { it.value }.toSet()) {
            assertTrue(
                "the Galaxy's reader may read only /api/memory/entities, not $route",
                route == "\"/api/memory/entities",
            )
        }
        // `/api/graph` is the route that matters most here: it is what the
        // desktop's map used to draw, it is off the phone "by rule"
        // (JARVIS-API section 6), and its fact dots were not hidden while the
        // memory lists were - the privacy finding that moved the desktop onto
        // `/api/memory/entities`. The reader may *name* it in a comment saying
        // it is deliberately not used; it must never be a path this app can
        // build, so the check is for a route, not for the word.
        assertFalse(
            "the Galaxy must not be able to read the graph",
            entities.contains("\"/api/graph"),
        )
        // The facts' words come through the shared `MemoryUsed` reader, which
        // is itself the route hidden under "Hide memory lists".
        assertTrue(entities.contains("MemoryUsed"))

        // The connections list carries no tap handler of its own: read-only
        // showing, not a dead control. `connectionsAreTheDesktopsEdgesInWords`
        // reads the call itself and holds that it is plain text.
    }

    @Test
    fun theHiddenMenuRuleStillCoversTheGalaxy() {
        // The names are a memory list, so "Hide memory lists and chat history"
        // replaces the whole screen - the panel included, and therefore the
        // connections too. That is what makes a read-only list safe to put on a
        // phone that can be picked up by someone else.
        //
        // Held on the gate itself, not on the mere presence of the words: a
        // `HiddenSection` that is built but never reachable ("if (false)") would
        // pass a search for the string and still show the owner's names to
        // whoever picked the phone up.
        val body = functionBody(plate, "internal fun PeopleAndThingsSection(")
        assertTrue(
            "the plate is not gated on the hidden-memory-lists setting",
            body.contains("if (privateHidden) {"),
        )
        assertTrue(
            "the hidden case does not replace the whole plate",
            body.contains("HiddenSection(Entities.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)"),
        )
        // The gate must come first, and return: otherwise the names are read
        // and drawn below it anyway. `EntityFacts` is a separate function, so
        // the ordering that matters here is the gate against the read and
        // against the call that draws a name's facts.
        val gateAt = body.indexOf("if (privateHidden) {")
        val readAt = body.indexOf("JarvisRuntime.memoryEntities()")
        val openAt = body.indexOf("EntityFacts(open, shown, perFact)")
        assertTrue("the gate must be before the read", gateAt in 1 until readAt)
        assertTrue("the gate must be before the panel is opened", gateAt in 1 until openAt)
        assertTrue(
            "the hidden case must stop, not fall through to the list",
            body.substring(gateAt, minOf(body.length, gateAt + 220)).contains("return"),
        )
    }

    // ---------------------------------------------------- accessible ----

    @Test
    fun nothingIsClippedAndNothingIsSaidOnlyInColour() {
        // A clipped name is a hidden name, and on a phone at the largest font
        // setting a clipped heading is the likeliest failure of all. The plate
        // sets no maxLines and no overflow anywhere.
        assertFalse("the Galaxy plate clips text", plate.contains("maxLines"))
        assertFalse("the Galaxy plate clips text", plate.contains("TextOverflow"))

        // The section is a real labelled section, so TalkBack's "navigate by
        // headings" reaches it, and a name is a row under a heading rather than
        // an unlabelled blob.
        assertTrue("the plate has no section label", plate.contains("Section(Entities.TITLE"))
        // Each group's heading is announced as a heading, not skipped over as
        // one more line of body text.
        val body = functionBody(plate, "internal fun PeopleAndThingsSection(")
        assertTrue("a group heading is not a heading", body.contains("Kicker(group.title)"))

        // No meaning rests on colour alone: the two states a connection can be
        // in are both words. `Entities.ALONE` is a sentence, and a connection
        // reads "Dan, 1 shared fact" - a number, not a shade. Colour is set on
        // these lines, but nothing is decided BY it: both states are drawn with
        // the same shapes and the same kind of text.
        assertTrue(Entities.ALONE.isNotBlank())
        assertTrue(Entities.WITH.isNotBlank())
        assertTrue(Entities.ALONE_WHY.isNotBlank())
        assertTrue(
            Entities.connectionLine(Entities.Connection(Entities.Entity("d", "Dan", "person", listOf(1L)), 1))
                .contains("1 shared fact"),
        )
        // Both states are drawn as plain text - no icon, no coloured dot, no
        // bar whose length carries the meaning. `Dot` and `Meter` are what that
        // would look like, and neither is used here.
        assertFalse("a connection's meaning is a coloured dot", plate.contains("Dot("))
        assertFalse("a connection's meaning is a bar", plate.contains("Meter("))

        // And the count on a name is a number in words, never a bar or a size.
        assertTrue(plate.contains("Entities.rowLine(e)"))
        assertTrue(plate.contains("Entities.heading(entity.count)"))
    }

    private fun entitiesBody() = """{"entities": [
        {"id": 1, "name": "Priya", "kind": "person", "also": [], "aliases": ["sister"],
         "fact_ids": [9, 7, 5, 3], "facts": 4},
        {"id": 2, "name": "Biscuit", "kind": "pet", "fact_ids": [8], "facts": 1},
        {"id": 3, "name": "Garage", "kind": "project", "fact_ids": [5, 3], "facts": 2},
        {"id": 4, "name": "Dan", "kind": "person", "fact_ids": [9, 12, 11, 5], "facts": 4}
    ], "count": 4, "limit": 500}"""

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
