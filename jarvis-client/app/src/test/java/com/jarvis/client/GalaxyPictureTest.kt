package com.jarvis.client

import com.jarvis.client.net.Entities
import com.jarvis.client.net.GalaxyPicture
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.math.sqrt

/**
 * The phone's Galaxy PICTURE - the pure half ([GalaxyPicture]); no Compose, no
 * emulator, no network.
 *
 * The picture is not a new picture. It is the desktop's Galaxy, drawn with the
 * desktop's own deterministic `zen-ring` layout: the best-known name at the
 * centre, the rest on R=108, and a list too large for that halo growing outward
 * at 24. `contract/galaxy-picture-cases.json` was written by
 * tools/gen_galaxy_picture_cases.py, which runs the REAL desktop modules
 * (`jarvis-desktop/src/galaxy-view.js` orderedEntities/buildEntityGraph and
 * `jarvis-desktop/src/galaxy-presets.js` layoutZenRing) and records the
 * positions, radii and links they compute. So the first test below is the one
 * that matters: it holds the Kotlin port to the JavaScript's own numbers - name
 * for name, link for link, position for position - not to "a layout that looks
 * reasonable".
 *
 * The rest pins what the picture promises around those numbers: the same list
 * always draws the same picture, whatever order the PC sent it in; 48 names are
 * drawn out of the real total; a fact naming more than
 * [Entities.MAX_NAMES_PER_FACT] names is a list, not a connection; a dot's
 * radius is the desktop's own weight-plus-share formula; and the canvas fit,
 * the hit test and the no-overlap fallback each behave the same way twice.
 *
 * Two more pin the PLATE's wiring against its own source, the way
 * `PhoneGalaxyTest` holds the read-only rule: the picture sits INSIDE the
 * hidden-lists gate (a hidden phone must not draw names) and above the band,
 * a past as-of date hides it with the band (whose counts are then that date's),
 * and it adds no control, write, route, drag or animation of its own.
 *
 * NOT-TESTABLE here (no emulator): what the picture actually looks like on a
 * phone, and how a tap feels. Those stay field-test rows - never a pass.
 */
class GalaxyPictureTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/galaxy-picture-cases.json")) {
            "contract/galaxy-picture-cases.json is missing - run tools/gen_galaxy_picture_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private val cases: List<JsonObject> = doc["cases"]!!.jsonArray.map { it.jsonObject }

    private fun caseName(case: JsonObject): String = case["name"]!!.jsonPrimitive.content

    private fun case(name: String): JsonObject =
        cases.firstOrNull { caseName(it) == name } ?: error("the fixture has no \"$name\" case")

    /**
     * The fixture's entities, read by the same parser the app reads its answer
     * with - so this also holds [Entities.parse] to the shape the fixture uses.
     */
    private fun entitiesOf(case: JsonObject): List<Entities.Entity> {
        val body = JsonObject(mapOf("entities" to case["entities"]!!))
        return requireNotNull(Entities.parse(body)) {
            "case \"${caseName(case)}\" entities do not parse"
        }
    }

    /** A screen dot with only the fields [GalaxyPicture.hit] reads. */
    private fun screenDot(id: String, x: Float, y: Float, r: Float) =
        GalaxyPicture.ScreenDot(
            id = id,
            name = id,
            group = "person",
            facts = 1,
            shared = 0,
            x = x,
            y = y,
            r = r,
        )

    // ------------------------------- the desktop's own numbers (the point) ---

    @Test
    fun everyCaseIsTheDesktopsOwnPicture() {
        assertEquals(listOf("names", "cap", "thirteen"), cases.map { caseName(it) })

        for (case in cases) {
            val name = caseName(case)
            val entities = entitiesOf(case)
            val picture = GalaxyPicture.build(entities)

            // The names drawn, in the desktop's order - the cap included.
            val orderedIds = case["ordered_ids"]!!.jsonArray.map { it.jsonPrimitive.content }
            assertEquals("$name: drawn names", orderedIds, picture.dots.map { it.id })
            assertEquals("$name: the real total", case["total"]!!.jsonPrimitive.int, picture.total)

            // The desktop's own positions and radii, one node per drawn name.
            val nodes = case["nodes"]!!.jsonArray.map { it.jsonObject }
            assertEquals("$name: one node per drawn name", orderedIds.size, nodes.size)
            for (i in nodes.indices) {
                val node = nodes[i]
                val dot = picture.dots[i]
                assertEquals("$name: node $i is the wrong name", node["id"]!!.jsonPrimitive.content, dot.id)
                assertEquals("$name: node $i x", node["x"]!!.jsonPrimitive.double, dot.x, 1e-6)
                assertEquals("$name: node $i y", node["y"]!!.jsonPrimitive.double, dot.y, 1e-6)
                assertEquals("$name: node $i radius", node["r"]!!.jsonPrimitive.double, dot.radius, 1e-6)
            }

            // The desktop's own links: the same pairs, at the same strength, in
            // the same order. A port that drew a reasonable picture but joined
            // the wrong names would still fail here.
            val links = case["links"]!!.jsonArray.map {
                val link = it.jsonObject
                Triple(
                    link["source"]!!.jsonPrimitive.content,
                    link["target"]!!.jsonPrimitive.content,
                    link["shared"]!!.jsonPrimitive.int,
                )
            }
            assertEquals(
                "$name: links",
                links,
                picture.edges.map { Triple(it.source, it.target, it.shared) },
            )
            assertEquals("$name: connections", links.size, picture.connections)
        }
    }

    @Test
    fun theSameListAlwaysDrawsTheSamePicture() {
        val entities = entitiesOf(case("names"))
        val once = GalaxyPicture.build(entities)

        // Twice is the same picture, exactly.
        val again = GalaxyPicture.build(entities)
        assertEquals(once.dots, again.dots)
        assertEquals(once.edges, again.edges)
        assertEquals(once.total, again.total)

        // And the order the PC happened to send does not decide it: the desktop
        // ranks by facts, then the newest fact, then the name, then the id.
        val reversed = GalaxyPicture.build(entities.reversed())
        assertEquals(once.dots, reversed.dots)
        assertEquals(once.edges, reversed.edges)
        assertEquals(once.total, reversed.total)

        val shuffled = GalaxyPicture.build(
            listOf(entities[2], entities[0], entities[3], entities[1]),
        )
        assertEquals(once.dots, shuffled.dots)
        assertEquals(once.edges, shuffled.edges)
    }

    @Test
    fun theCapKeepsFortyEightNamesAndTheRealTotal() {
        val case = case("cap")
        val entities = entitiesOf(case)
        assertEquals(60, entities.size)

        val picture = GalaxyPicture.build(entities)
        assertEquals(48, GalaxyPicture.MAX_NODES)
        assertEquals(48, picture.dots.size)
        assertEquals("the plate must be able to say \"Showing 48 of 60\"", 60, picture.total)

        // Every link joins two dots that are really drawn: a dropped name gets
        // no dot and no link.
        val drawn = picture.dots.map { it.id }.toSet()
        assertEquals(48, drawn.size)
        assertTrue("the cap case draws no links", picture.edges.isNotEmpty())
        for (edge in picture.edges) {
            assertTrue("an edge joins a dropped name: ${edge.source}", edge.source in drawn)
            assertTrue("an edge joins a dropped name: ${edge.target}", edge.target in drawn)
        }

        // And no name is drawn that the desktop's own cap did not keep.
        val orderedIds = case["ordered_ids"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(48, orderedIds.size)
        assertTrue("a drawn name is outside the desktop's kept order", orderedIds.containsAll(drawn))
    }

    @Test
    fun aFactNamingThirteenNamesJoinsNothing() {
        // The desktop's own number (`galaxy-view.js` MAX_NAMES_PER_FACT), held
        // equal on the phone so the two apps agree on what a connection is.
        assertEquals(12, Entities.MAX_NAMES_PER_FACT)

        fun inOneFact(count: Int, fact: Long): List<Entities.Entity> = (1..count).map {
            Entities.Entity(
                id = "e$it",
                name = "Name ${it.toString().padStart(2, '0')}",
                kind = "person",
                factIds = listOf(fact),
            )
        }

        // Twelve names in one fact is the last size that still connects: all
        // 66 pairs, each by the one fact they share.
        val twelve = GalaxyPicture.build(inOneFact(12, 500L))
        assertEquals(12, twelve.dots.size)
        assertEquals(12 * 11 / 2, twelve.edges.size)
        assertEquals(66, twelve.edges.size)
        assertTrue("every shared count is the one fact", twelve.edges.all { it.shared == 1 })

        // Thirteen is a list ("milk, eggs, bread"), not twelve connections.
        val thirteen = GalaxyPicture.build(inOneFact(13, 501L))
        assertEquals(13, thirteen.dots.size)
        assertTrue("a fact naming thirteen names joined them", thirteen.edges.isEmpty())
    }

    @Test
    fun theRadiusIsTheDesktopsWeightPlusShareRule() {
        val entities = entitiesOf(case("names"))
        val picture = GalaxyPicture.build(entities)

        val priya = picture.dots.first { it.id == "1" }
        assertEquals("Priya", priya.name)
        assertEquals("Priya is in four facts", 4, priya.facts)
        assertEquals("Priya shares a fact with two drawn names", 2, priya.shared)
        // `radiusOf` in the desktop's brain.js: 3 + min(9, sqrt(2 * facts + deg)):
        // 3 + sqrt(2 * 4 + 2) = 3 + sqrt(10).
        assertEquals(3.0 + sqrt(10.0), priya.radius, 1e-9)

        // `facts` is counted from the fact ids, never from a number a model said.
        for (dot in picture.dots) {
            val entity = entities.first { it.id == dot.id }
            assertEquals("${dot.name}: facts", entity.factIds.size, dot.facts)
        }
    }

    // ------------------------------------------------------- onto a canvas ---

    @Test
    fun fitKeepsEveryDotOnTheCanvas() {
        val picture = GalaxyPicture.build(entitiesOf(case("cap")))
        val width = 320f
        val height = 280f
        val padding = 16f

        val fitted = GalaxyPicture.fit(picture, width, height, padding)
        assertEquals(picture.dots.size, fitted.size)
        assertEquals(picture.dots.map { it.id }, fitted.map { it.id })
        for (dot in fitted) {
            assertTrue(
                "${dot.id} is off the canvas horizontally: x=${dot.x}",
                dot.x >= padding - 1e-3f && dot.x <= width - padding + 1e-3f,
            )
            assertTrue(
                "${dot.id} is off the canvas vertically: y=${dot.y}",
                dot.y >= padding - 1e-3f && dot.y <= height - padding + 1e-3f,
            )
            assertTrue("${dot.id} has no size", dot.r > 0f)
        }

        // The same picture on the same canvas is the same pixels, twice.
        assertEquals(fitted, GalaxyPicture.fit(picture, width, height, padding))

        // No canvas is nothing to draw, not a division by zero.
        assertTrue(GalaxyPicture.fit(picture, 0f, height, padding).isEmpty())
        assertTrue(GalaxyPicture.fit(GalaxyPicture.build(emptyList()), width, height, padding).isEmpty())
    }

    @Test
    fun aTwoNamePictureNeverGrowsPastTheScaleCap() {
        val two = listOf(
            Entities.Entity("a", "Ana", "person", listOf(1L)),
            Entities.Entity("b", "Ben", "person", listOf(1L)),
        )
        val picture = GalaxyPicture.build(two)
        assertEquals(2, picture.dots.size)

        // A canvas far larger than the picture: without MAX_SCALE it would be
        // grown until the two dots were two blobs.
        val fitted = GalaxyPicture.fit(picture, 1000f, 1000f, 16f)
        assertEquals(2, fitted.size)

        val dx = (fitted[0].x - fitted[1].x).toDouble()
        val dy = (fitted[0].y - fitted[1].y).toDouble()
        val apart = sqrt(dx * dx + dy * dy)
        // The widest a two-name layout can be is 2 * ZEN_RADIUS before scaling.
        assertTrue(
            "two dots $apart apart",
            apart <= 2.0 * GalaxyPicture.MAX_SCALE * GalaxyPicture.ZEN_RADIUS + 1e-3,
        )
        for (dot in fitted) {
            // The largest layout radius is 3 + 9; scaled, it is still a dot.
            assertTrue(
                "a dot of radius ${dot.r}",
                dot.r.toDouble() <= 12.0 * GalaxyPicture.MAX_SCALE + 1e-3,
            )
        }
    }

    @Test
    fun hitPicksTheNearestDotAndTheEarlierOneWinsATie() {
        val dots = listOf(
            screenDot("a", x = 0f, y = 0f, r = 10f),
            screenDot("b", x = 40f, y = 0f, r = 10f),
        )
        assertEquals("a", GalaxyPicture.hit(dots, 0f, 0f, 0f))
        assertEquals("b", GalaxyPicture.hit(dots, 40f, 0f, 0f))

        // A finger just outside the dot still hits it with slack, and misses
        // without it.
        assertEquals("a", GalaxyPicture.hit(dots, 14f, 0f, 5f))
        assertNull(GalaxyPicture.hit(dots, 14f, 0f, 0f))

        // Far away is a miss, slack or no slack.
        assertNull(GalaxyPicture.hit(dots, 100f, 100f, 0f))
        assertNull(GalaxyPicture.hit(dots, 100f, 100f, 5f))

        // Two overlapping dots: the nearer one wins, not the first one.
        val overlap = listOf(
            screenDot("left", x = 0f, y = 0f, r = 20f),
            screenDot("right", x = 10f, y = 0f, r = 20f),
        )
        assertEquals("left", GalaxyPicture.hit(overlap, 3f, 0f, 0f))
        assertEquals("right", GalaxyPicture.hit(overlap, 7f, 0f, 0f))

        // Exactly between two dots both are the same distance away, and the
        // documented rule is "the dot earlier in the list wins" - so the answer
        // is the same twice, and it follows the list, not the id.
        val tie = listOf(
            screenDot("z", x = -10f, y = 0f, r = 10f),
            screenDot("a", x = 10f, y = 0f, r = 10f),
        )
        assertEquals("z", GalaxyPicture.hit(tie, 0f, 0f, 0f))
        assertEquals("z", GalaxyPicture.hit(tie, 0f, 0f, 0f))
        assertEquals("a", GalaxyPicture.hit(tie.reversed(), 0f, 0f, 0f))
    }

    // ------------------------------------- the no-overlap fallback, twice ---

    @Test
    fun separatePushesOverlapsApartTheSameWayEveryTime() {
        fun threePoints() = mutableListOf(
            GalaxyPicture.Pt(0.0, 0.0),
            GalaxyPicture.Pt(0.0, 0.0),
            GalaxyPicture.Pt(10.0, 0.0),
        )

        val points = threePoints()
        GalaxyPicture.separate(points, 21.0)

        for (i in points.indices) {
            for (j in i + 1 until points.size) {
                val dx = points[j].x - points[i].x
                val dy = points[j].y - points[i].y
                val apart = sqrt(dx * dx + dy * dy)
                assertTrue(
                    "two points are $apart apart, under the 21 gap",
                    apart >= 21.0 - 1e-9,
                )
            }
        }

        // The same list separates to exactly the same points, twice: the
        // fallback is deterministic, never a random jitter.
        val again = threePoints()
        GalaxyPicture.separate(again, 21.0)
        assertEquals(points, again)
    }

    // -------------------------------- the ring numbers the 48 names rely on ---

    @Test
    fun theRingCapacitiesAreTheDesktopsNumbers() {
        // zen-ring's own values (`galaxy-presets.js` ZEN_RADIUS,
        // ZEN_RING_PITCH, ZEN_HALO_GAP), pinned so a "small improvement" cannot
        // quietly move the phone's picture off the desktop's.
        assertEquals(108.0, GalaxyPicture.ZEN_RADIUS, 0.0)
        assertEquals(24.0, GalaxyPicture.ZEN_RING_PITCH, 0.0)
        assertEquals(21.0, GalaxyPicture.ZEN_HALO_GAP, 0.0)
        assertEquals(2.0, GalaxyPicture.MAX_SCALE, 0.0)

        // The capacities the desktop's own formula gives: 8 on R=34, 17 on
        // R=68, 32 on the R=108 halo, 39 on the R=132 outward ring.
        assertEquals(8, GalaxyPicture.ringCapacity(34.0, 24.0))
        assertEquals(17, GalaxyPicture.ringCapacity(68.0, 24.0))
        assertEquals(32, GalaxyPicture.ringCapacity(108.0, GalaxyPicture.ZEN_HALO_GAP))
        assertEquals(39, GalaxyPicture.ringCapacity(132.0, GalaxyPicture.ZEN_HALO_GAP))

        // 48 is exactly centre + 32 + 15: one dot at the centre, a full halo,
        // and the first 15 places on the outward ring.
        assertEquals(GalaxyPicture.MAX_NODES, 1 + 32 + 15)

        val points = GalaxyPicture.layout(GalaxyPicture.MAX_NODES)
        assertEquals(48, points.size)
        // And the construction plus `separate` really keep the 21 air between
        // every pair at the cap - which is what makes 48 dots readable at
        // thumb width.
        for (i in points.indices) {
            for (j in i + 1 until points.size) {
                val dx = points[j].x - points[i].x
                val dy = points[j].y - points[i].y
                val apart = sqrt(dx * dx + dy * dy)
                assertTrue(
                    "dots $i and $j are $apart apart, under the 21 gap",
                    apart >= GalaxyPicture.ZEN_HALO_GAP,
                )
            }
        }
    }

    @Test
    fun groupsAndShapesMirrorTheDesktopsStyle() {
        // A filled disc for a person, a place or a project...
        for (kind in listOf("person", "place", "project")) {
            assertEquals(kind, GalaxyPicture.groupFor(kind))
            assertTrue("$kind should be a disc", GalaxyPicture.disc(GalaxyPicture.groupFor(kind)))
        }
        // ...a hollow ring for a pet, an organisation or a thing...
        for (kind in listOf("pet", "organisation", "thing")) {
            assertEquals(kind, GalaxyPicture.groupFor(kind))
            assertFalse("$kind should be a ring", GalaxyPicture.disc(GalaxyPicture.groupFor(kind)))
        }
        // ...and anything unknown, missing or differently cased is "other",
        // never an invented group.
        for (kind in listOf(null, "", "spaceship", "Person", " person")) {
            assertEquals("other", GalaxyPicture.groupFor(kind))
            assertFalse("other should be a ring", GalaxyPicture.disc(GalaxyPicture.groupFor(kind)))
        }
    }

    // ----------------------------------------- honest pins on the fixture ---

    @Test
    fun theFixtureIsTheGeneratorsThreeNamedCases() {
        assertEquals(listOf("names", "cap", "thirteen"), cases.map { caseName(it) })
        assertEquals(48, doc["max_nodes"]!!.jsonPrimitive.int)
        assertEquals(GalaxyPicture.MAX_NODES, doc["max_nodes"]!!.jsonPrimitive.int)

        // The fixture says who wrote it, and that tool is here and reads the
        // desktop's own two modules - so the numbers above can be traced back
        // to the JavaScript, not just to a JSON file that agrees with itself.
        assertTrue(
            "the fixture no longer names the tool that wrote it",
            doc["_comment"]!!.jsonPrimitive.content.contains("tools/gen_galaxy_picture_cases.py"),
        )
        val generator = repoFile("tools/gen_galaxy_picture_cases.py").readText()
        assertTrue(
            "the generator no longer runs the desktop layout module (galaxy-presets.js)",
            generator.contains("galaxy-presets.js"),
        )
        assertTrue(
            "the generator no longer runs the desktop graph module (galaxy-view.js)",
            generator.contains("galaxy-view.js"),
        )
    }

    // ------------------------------------------------ the plate's wiring ---

    @Test
    fun thePictureIsInsideTheHiddenGateAndAboveTheBand() {
        val plate = repoFile(main + "ui/screens/EntitiesPlate.kt").readText()

        // 1. The hidden-lists gate comes FIRST and returns to the locked
        // prompt. The picture is after it, so a phone with the memory lists
        // hidden never draws the names - it is not a way around the gate.
        val gateAt = plate.indexOf("if (privateHidden) {")
        assertTrue("the hidden-memory-lists gate is gone", gateAt >= 0)
        val pictureAt = plate.indexOf("GalaxyPicture(band")
        assertTrue("the plate no longer draws the picture", pictureAt >= 0)
        assertTrue(
            "the picture is drawn before the hidden-lists gate, so a hidden phone still draws names",
            pictureAt > gateAt,
        )
        assertTrue(
            "the hidden case must stop, not fall through to the picture",
            plate.substring(gateAt, minOf(plate.length, gateAt + 220)).contains("return"),
        )

        // 2. The picture is ABOVE the "at a glance" band, and the band is still
        // drawn: the picture is an addition, not a replacement.
        val bandAt = plate.indexOf("GalaxyBand(band)")
        assertTrue("the band under the picture is gone", bandAt >= 0)
        assertTrue("the picture must be above the band", bandAt > pictureAt)

        // 3. The as-of chips hide the picture WITH the band: both are inside
        // one branch guarded by `asOfEpoch == null`, so a past date - whose
        // counts are that date's, not today's - draws neither.
        val asOfAt = plate.indexOf("if (asOfEpoch == null")
        assertTrue(
            "the picture and band are not guarded by the as-of choice",
            asOfAt >= 0 && asOfAt < pictureAt,
        )
        val block = plate.substring(asOfAt, minOf(plate.length, bandAt + 40))
        assertTrue("the picture is outside the as-of guard", block.contains("GalaxyPicture(band"))
        assertTrue("the band is outside the as-of guard", block.contains("GalaxyBand(band)"))

        // 4. Exactly one call site, so no second picture can be added outside
        // the guarded branch later.
        assertEquals(1, Regex("GalaxyPicture\\(band").findAll(plate).count())

        // 5. A tap opens the name's EXISTING facts/connections panel - the same
        // `openId` the list rows set - instead of a new screen or a new card.
        assertTrue(
            "a dot does not open the name's existing facts view",
            plate.contains("GalaxyPicture(band, onOpen = { openId = it })"),
        )
        assertTrue(
            "the plate no longer draws the existing facts panel for the opened name",
            plate.contains("EntityFacts(open, shown, perFact)"),
        )
    }

    @Test
    fun thePictureAddsNoControlNoWriteAndNoRoute() {
        val plate = repoFile(main + "ui/screens/GalaxyPicturePlate.kt").readText()
        val data = repoFile(main + "net/GalaxyPicture.kt").readText()
        for (src in listOf(plate, data)) {
            // No route, no write and no second read: this picture is a view of
            // the list the plate already holds.
            assertFalse("the picture names a route", src.contains("\"/api/"))
            assertFalse("the picture posts", src.contains("api.post"))
            for (w in listOf(
                "forgetAutoFact", "eraseFact", "pinFact", "unpinFact",
                "memoryErase", "entitiesMerge", "entitiesRename", "entityForget",
            )) {
                assertFalse("the picture calls $w", src.contains(w))
            }
            // Deterministic means STATIC: no animation, no frame loop, no force
            // simulation on the phone (the desktop keeps those; the phone's
            // positions come from GalaxyPicture.layout).
            for (anim in listOf(
                "rememberInfiniteTransition", "withFrameNanos", "Animatable(",
                "LaunchedEffect", "animateFloatAsState", "repel", "velocity",
            )) {
                assertFalse("the picture animates or simulates ($anim)", src.contains(anim))
            }
        }

        // It has a TAP, and only a tap: no drag, and nothing that swallows the
        // finger before the Canvas sees it.
        assertTrue("the picture has no tap of its own", plate.contains("detectTapGestures"))
        assertFalse("the picture has a drag", plate.contains("detectDragGestures"))
        assertFalse("the picture has a clickable control", plate.contains("Modifier.clickable"))
        assertFalse("the picture adds a Quiet control", plate.contains("Quiet("))
        assertFalse("the picture adds a Pill label", plate.contains("Pill("))
        assertFalse("the picture adds a text field", plate.contains("TextInput("))
        assertFalse("the picture adds a button", plate.contains("Button("))

        // Every dot is a real TalkBack control that says the band's own line
        // and opens the name; the whole picture says what it is.
        assertTrue(
            "a dot does not announce the existing name line",
            plate.contains("Entities.galaxyNameLine(dot.name, dot.facts, dot.shared)"),
        )
        assertTrue(
            "the picture does not say what it is",
            plate.contains("Entities.pictureSaid(picture.dots.size, picture.connections)"),
        )
        assertTrue("a dot does not open its name from TalkBack", plate.contains("onOpen(dot.id)"))

        // The cap is honest: when the picture leaves names out, the plate says
        // so in the existing "Showing n of total" words rather than pretending
        // the picture is the whole list.
        assertEquals(48, GalaxyPicture.MAX_NODES)
        assertTrue(
            "the picture hides names without saying so",
            plate.contains("Entities.showingLine(picture.dots.size, picture.total)"),
        )
    }

    // ------------------------------------------------------------- helper ---

    /**
     * A path from this repository's root, found by walking up from the working
     * directory - the same helper `EntitiesTest` uses, so the test still finds
     * it whether Gradle runs from the app folder or from the repository root.
     */
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
