package com.jarvis.client

import com.jarvis.client.net.ContentRisk
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The desktop's Content risk panel on the phone (the parity audit of
 * 2026-10-10, GAP 7): the phone read `/api/content-risk` for its rush banner
 * and drew nothing else of it, so the flagged-text list could not be read
 * anywhere on the phone.
 *
 * What this holds, in the audit's own three questions plus the fourth that
 * matters as much:
 *
 *  * the list draws when there is one;
 *  * it is hidden under "Hide memory lists and chat history";
 *  * an empty list says so rather than drawing a blank block;
 *  * the words are the DESKTOP's own (`brain.html`'s card, `brain.js`'s
 *    renderer), so the two apps cannot describe the same panel differently.
 *
 * Pure JVM: the plate's drawing is held to its source text and every decision
 * is held through [ContentRisk.body], because there is no Android SDK here and
 * CI's Gradle build is the first compiler.
 */
class ContentRiskTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val brainHtml: String =
        repoFile("jarvis-desktop/src/brain.html").readText().replace(Regex("\\s+"), " ")

    private val brainJs: String = repoFile("jarvis-desktop/src/brain.js").readText()

    private val plate: String =
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ContentRiskPlate.kt").readText()

    private val host: String =
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ApprovalsScreen.kt").readText()

    private val runtime: String =
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt").readText()

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    /** The route's own answer, in the shape `jarvis_content_risk.status` sends. */
    private val answered: JsonObject = obj(
        """
        {"rush":{"until":1790000000,"source":"web:example.com","phrase":"approve this now",
                 "context":"...","count_today":3,"set":1789999000},
         "pins":[{"kind":"skill","key":"summarise","sha":"0123456789abcdef0123","first":1789000000,
                  "last":1789900000,"approvals":2,"cumulative_drift":0.01},
                 {"kind":"mcp","key":"fake/inject","sha":"fedcba9876543210fedc","first":1789500000,
                  "last":1789950000,"approvals":1,"cumulative_drift":0.0}],
         "config":{"rush_latch_minutes":10,"rush_raises_to":"ask","full_reread_drift":0.35}}
        """.trimIndent(),
    )

    // ------------------------------------------------ 1. the list draws ----

    @Test
    fun `the list draws when there is one`() {
        val body = ContentRisk.body(answered, SectionRead.Read, hidden = false)
        assertTrue("the panel did not come back ready: $body", body is ContentRisk.Body.Ready)
        val ready = body as ContentRisk.Body.Ready
        assertEquals(listOf("summarise", "fake/inject"), ready.pins.map { it.title })
        assertEquals(listOf("skill", "mcp"), ready.pins.map { it.kind })
        assertEquals(2, ready.pins.first().approvals)
        // The digest is the PC's sha, shortened the way the desktop shortens it,
        // and the time is that row's own approval time (seconds -> millis).
        assertEquals("0123456789ab", ready.pins.first().digest)
        assertEquals(1789900000L * 1000L, ready.pins.first().atMs)
        assertNull("a non-empty list must not draw the empty line", ContentRisk.pinnedSummary(ready.pins))
    }

    @Test
    fun `the latch is drawn in the desktop's own three parts`() {
        val ready = ContentRisk.body(answered, SectionRead.Read, hidden = false) as ContentRisk.Body.Ready
        val rush = ready.rush
        assertTrue("the latch was dropped", rush != null)
        assertEquals(ContentRisk.RUSH_ON, rush!!.text)
        assertEquals("approve this now", rush.phrase)
        assertEquals(3, rush.countToday)
        // Named, and counted - never quoted twice.
        assertEquals("from web:example.com · 3 times today", ContentRisk.rushSourceLine(rush))
    }

    @Test
    fun `a clear answer says no latch rather than nothing`() {
        val clear = obj("""{"rush":null,"pins":[],"config":{}}""")
        val ready = ContentRisk.body(clear, SectionRead.Read, hidden = false) as ContentRisk.Body.Ready
        assertNull("no latch must be null, not an empty latch", ready.rush)
        assertTrue("a clear panel draws no pins", ready.pins.isEmpty())
    }

    @Test
    fun `the two names the desktop reads are read here too`() {
        // The desktop's renderer reads `phrase || quote`, `name || source`,
        // `at`, and `digest`; the route really sends `phrase`, `key`, `last`
        // and `sha`. Both shapes must land, or one side of the pair goes blank
        // whenever the PC and the phone ship on different schedules.
        val other = obj(
            """
            {"rush":{"quote":"do it now","source":"email"},
             "pins":[{"source":"a page","at":1789,"digest":"aaaaabbbbbcccc"}]}
            """.trimIndent(),
        )
        val ready = ContentRisk.body(other, SectionRead.Read, hidden = false) as ContentRisk.Body.Ready
        assertEquals("do it now", ready.rush!!.phrase)
        assertEquals("a page", ready.pins.single().title)
        assertEquals("aaaaabbbbbcc", ready.pins.single().digest)
        assertEquals(1789L * 1000L, ready.pins.single().atMs)
        // A pin with no name at all is still a pin: a row that vanished from a
        // read-only record would be a lie about what is pinned.
        val bare = obj("""{"pins":[{}]}""")
        val one = (ContentRisk.body(bare, SectionRead.Read, hidden = false) as ContentRisk.Body.Ready).pins
        assertEquals("(pinned)", one.single().title)
    }

    // --------------------------------------------- 2. it hides properly ----

    @Test
    fun `it is hidden under Hide memory lists and chat history, whatever was read`() {
        // The owner's setting wins over every read state: a panel that leaked
        // through a timed-out read would be the exact bug the hide exists for.
        assertEquals(
            ContentRisk.Body.Hidden,
            ContentRisk.body(answered, SectionRead.Read, hidden = true),
        )
        assertEquals(
            ContentRisk.Body.Hidden,
            ContentRisk.body(answered, SectionRead.Reading, hidden = true),
        )
        assertEquals(
            ContentRisk.Body.Hidden,
            ContentRisk.body(answered, SectionRead.Absent, hidden = true),
        )
        assertEquals(
            ContentRisk.Body.Hidden,
            ContentRisk.body(null, SectionRead.Failed("timeout"), hidden = true),
        )
    }

    @Test
    fun `the plate draws the hidden line in place, and never reads while hidden`() {
        // Nothing of the list is composed while hidden - it is the same
        // [HiddenSection] the screen's own record uses, with a Show that asks
        // for the fingerprint or PIN.
        assertTrue(plate.contains("ContentRisk.Body.Hidden -> HiddenSection(ContentRisk.TITLE"))
        assertTrue(plate.contains("ContentRisk.body(brain.contentRisk, brain.contentRiskRead, hidden)"))
        assertTrue("the read must be skipped while hidden", plate.contains("if (!hidden)"))
    }

    @Test
    fun `the screen it lives on passes the setting and the Show, and draws it first`() {
        // The host is the phone's read-only record screen, which already hides
        // under the same setting: the plate is handed BOTH the flag and the
        // same "Show" the screen uses, so the two cannot disagree.
        assertTrue(host.contains("ContentRiskSection("))
        assertTrue(host.contains("hidden = privateHidden"))
        assertTrue(host.contains("onShow = onShowPrivate"))
        // First, like the desktop's rush strip on every one of its own views.
        val riskAt = host.indexOf("item(key = \"content-risk\")")
        val leadAt = host.indexOf("item(key = \"lead\")")
        assertTrue("the panel was not found on the screen", riskAt > 0)
        assertTrue("the panel must be drawn before the approvals list", riskAt < leadAt)
    }

    // ------------------------------------------------ 3. the empty list ----

    @Test
    fun `an empty list says so instead of drawing a blank block`() {
        val empty = obj("""{"rush":null,"pins":[],"config":{}}""")
        val ready = ContentRisk.body(empty, SectionRead.Read, hidden = false) as ContentRisk.Body.Ready
        assertTrue(ready.pins.isEmpty())
        assertEquals(ContentRisk.NOTHING_PINNED, ContentRisk.pinnedSummary(ready.pins))
        // ...and the plate really draws that line, rather than a heading over
        // nothing.
        assertTrue(plate.contains("ContentRisk.pinnedSummary(body.pins)"))
        assertTrue(plate.contains("ContentRisk.PINNED_HEADING"))
    }

    @Test
    fun `a read that failed says why, and one this PC does not have says that`() {
        assertEquals(
            ContentRisk.Body.Failed("timed out"),
            ContentRisk.body(null, SectionRead.Failed("timed out"), hidden = false),
        )
        assertEquals(ContentRisk.Body.NotHere, ContentRisk.body(null, SectionRead.Absent, hidden = false))
        assertEquals(ContentRisk.Body.Reading, ContentRisk.body(null, SectionRead.Reading, hidden = false))
        // A failed read is not drawn as an empty list: "the check failed" and
        // "nothing is pinned" are different sentences and only one is true.
        assertTrue(ContentRisk.failed("timed out").startsWith("Couldn't read the content risk list"))
        assertTrue(plate.contains("ContentRisk.failed(body.reason)"))
    }

    // ------------------------------------------------ 4. the PC's words ----

    @Test
    fun `every word is the desktop's own`() {
        // The card, its note and its heading, from brain.html and brain.js.
        assertTrue("the desktop card's title moved", brainHtml.contains("<h2>${ContentRisk.TITLE}</h2>"))
        assertTrue("the desktop card's note moved", brainHtml.contains(ContentRisk.NOTE))
        assertTrue("the pinned list's heading moved", brainJs.contains("\"${ContentRisk.PINNED_HEADING}\""))
        // The three latch lines and the empty-list line, from renderContentRisk.
        assertTrue(brainJs.contains("\"${ContentRisk.RUSH_ON}\""))
        assertTrue(brainJs.contains("\"${ContentRisk.RUSH_OFF}\""))
        assertTrue(brainJs.contains("\"${ContentRisk.RUSH_TAIL}\""))
        assertTrue(brainJs.contains("\"${ContentRisk.NOTHING_PINNED}\""))
        // And the desktop's own fields for a row, in its own order: kind, the
        // approval time, the digest.
        assertTrue(brainJs.contains("digest \${String(p.digest).slice(0, 12)}"))
        assertTrue(ContentRisk.pinLine(ContentRisk.Pin("x", "skill", 0L, "0123456789ab", 2))
            .startsWith("skill · approved 2 times · digest 0123456789ab"))
    }

    // --------------------------------------------- 5. read-only, one route --

    @Test
    fun `the panel reads one route and can change nothing at all`() {
        // The plate's ONLY call into the runtime is the one read: no write, no
        // clear, no approval. A control that cleared a latch is exactly what
        // this card's own note promises is not here.
        val calls = Regex("JarvisRuntime\\.(\\w+)").findAll(plate).map { it.groupValues[1] }.toSet()
        assertEquals(setOf("brain", "refreshContentRisk"), calls)
        // ...and that read is the route, held in one place now: the literal
        // path is gone from the runtime, so the two readers cannot drift.
        assertTrue(runtime.contains("api.probe(com.jarvis.client.net.ContentRisk.PATH)"))
        assertFalse(
            "the route's own path literal came back",
            runtime.contains("\"/api/content-risk\""),
        )
    }

    @Test
    fun `the narrow read keeps the last latch through a failure, and stamps no board`() {
        // The same rule refreshBrain applies, written once: a FAILED check keeps
        // the latch it last saw (a latch that vanished because the check failed
        // reads as "nothing is raising the tier"); an ABSENT route clears it.
        val read = runtime.substringAfter("suspend fun refreshContentRisk()").substringBefore("suspend fun memoryAsOf")
        assertTrue(read.contains("is SectionRead.Failed -> prev.contentRisk"))
        assertTrue(read.contains("SectionRead.Read -> now"))
        assertTrue(read.contains("is SectionRead.Failed -> prev.contentRiskAtMs"))
        assertFalse("the narrow read must not stamp the whole board", read.contains("fetchedAtMs ="))
    }
}
