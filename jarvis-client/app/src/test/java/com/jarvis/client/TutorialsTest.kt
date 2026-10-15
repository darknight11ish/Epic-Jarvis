package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Tutorials
import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Tutorials" and the FAQ on the Brain screen (docs/JARVIS-API.md section 114).
 *
 * The answers below are the shapes `GET /api/tutorials`, `POST
 * /api/tutorials/progress` and `GET /api/faq` really give (backend/
 * jarvis_tutorials.py), written out here rather than generated, because what is
 * being checked is the READING of them: which section a tutorial lands in, where
 * the owner resumes, what a state says in words, and what a bad answer does.
 * backend/test_tutorials.py owns the catalogue's own content and the desktop's
 * suite owns the desktop's half; this is the phone's.
 */
class TutorialsTest {

    private fun json(text: String): JsonObject =
        JarvisJson.parseToJsonElement(text).jsonObject

    private val catalogue = json(
        """
        {"ok": true,
         "sections": [{"id": "pc", "title": "On this PC"},
                      {"id": "phone", "title": "On your phone"}],
         "tutorials": [
           {"id": "intro", "section": "both", "title": "What Jarvis is", "why": "why",
            "minutes": 2, "steps": [{"title": "one", "body": "b", "where": "Brain"},
                                    {"title": "two", "body": "b", "where": "Brain"},
                                    {"title": "three", "body": "b", "where": "Brain"}],
            "state": "not_started", "step": 0, "steps_total": 3, "done": false,
            "resume_at": null, "due": true},
           {"id": "memory", "section": "both", "title": "What Jarvis remembers", "why": "why",
            "minutes": 3, "steps": [{"title": "one", "body": "b", "where": "Brain"},
                                    {"title": "two", "body": "b", "where": "Brain"},
                                    {"title": "three", "body": "b", "where": "Brain"}],
            "state": "in_progress", "step": 2, "steps_total": 3, "done": false,
            "resume_at": 2, "due": false},
           {"id": "pc-at-a-glance", "section": "pc", "title": "The desktop at a glance",
            "why": "why", "minutes": 2, "steps": [{"title": "one", "body": "b", "where": "HUD"}],
            "state": "done", "step": 1, "steps_total": 1, "done": true,
            "resume_at": null, "due": false},
           {"id": "phone-pairing", "section": "phone", "title": "Pairing your phone",
            "why": "why", "minutes": 3, "steps": [{"title": "one", "body": "b", "where": "Brain"}],
            "state": "skipped", "step": 0, "steps_total": 1, "done": false,
            "resume_at": null, "due": false}
          ],
          "counts": {"done": 1, "due": 2, "total": 4}}
        """.trimIndent()
    )

    @Test
    fun `the catalogue is read, with the owner's place in each tutorial`() {
        val read = Tutorials.readOf(ApiResult.Ok(catalogue))
        assertTrue(read is Tutorials.Read.Loaded)
        val loaded = (read as Tutorials.Read.Loaded).catalogue
        assertEquals(listOf("pc", "phone"), loaded.sections)
        assertEquals(4, loaded.tutorials.size)
        val memory = loaded.tutorials.first { it.id == "memory" }
        assertEquals(2, memory.resumeAt)
        assertEquals(3, memory.stepsTotal)
        assertEquals(3, memory.steps.size)
        assertEquals("Brain", memory.steps.first().where)
        assertNull(Tutorials.readLine(read))
    }

    @Test
    fun `a section is its own tutorials plus the shared ones, which is the point`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(
            listOf("intro", "memory", "pc-at-a-glance"),
            loaded.forSection("pc").map { it.id },
        )
        assertEquals(
            listOf("intro", "memory", "phone-pairing"),
            loaded.forSection("phone").map { it.id },
        )
    }

    @Test
    fun `quitting and resuming, the recorded step is the one offered`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(2, loaded.tutorials.first { it.id == "memory" }.startIndex)
        assertEquals(0, loaded.tutorials.first { it.id == "intro" }.startIndex)
        // A resume point past the end is ignored, not trusted.
        assertEquals(0, loaded.tutorials.first { it.id == "memory" }.copy(resumeAt = 99).startIndex)
    }

    @Test
    fun `each state says where the owner is, in the desktop's words`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(Tutorials.NOT_STARTED, loaded.tutorials.first { it.id == "intro" }.stateWords)
        assertEquals("${Tutorials.RESUME} 3", loaded.tutorials.first { it.id == "memory" }.stateWords)
        assertEquals(Tutorials.DONE, loaded.tutorials.first { it.id == "pc-at-a-glance" }.stateWords)
        assertEquals(Tutorials.SKIPPED, loaded.tutorials.first { it.id == "phone-pairing" }.stateWords)
    }

    @Test
    fun `a finished or skipped tutorial is offered again, a fresh one is not`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertTrue(loaded.tutorials.first { it.id == "pc-at-a-glance" }.showsAgain)
        assertTrue(loaded.tutorials.first { it.id == "phone-pairing" }.showsAgain)
        assertFalse(loaded.tutorials.first { it.id == "intro" }.showsAgain)
    }

    @Test
    fun `next stops at the last step and back stops at the first`() {
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        val intro = loaded.tutorials.first { it.id == "intro" }
        assertEquals(1, intro.nextIndex(0))
        assertEquals(2, intro.nextIndex(1))
        assertNull(intro.nextIndex(2))
        assertNull(intro.backIndex(0))
        assertEquals(1, intro.backIndex(2))
        assertEquals("${Tutorials.STEP_OF} 2 ${Tutorials.OF} 3", intro.copy(step = 1).stepWords)
    }

    @Test
    fun `the one number this screen shows counts down, and is never a percentage`() {
        // The PC has computed `counts` since the route was written and NOTHING
        // DREW IT - not this app, not the desktop. The desktop draws the same
        // sentence from the same counts (tests/tutorials.mjs), so the two apps
        // cannot disagree about the number.
        val loaded = (Tutorials.readOf(ApiResult.Ok(catalogue)) as Tutorials.Read.Loaded).catalogue
        assertEquals(Tutorials.Counts(done = 1, due = 2, total = 4), loaded.counts)
        assertEquals("You have met 2 of the 4 lessons here. 2 to go.", loaded.metWords)
        // A skipped lesson counts as MET: `due` is false for one, so it is in
        // the met half. That is the only distinction this line keeps.
        assertEquals("You have met all 4 lessons here.",
            loaded.copy(counts = Tutorials.Counts(done = 3, due = 0, total = 4)).metWords)
        assertEquals("You have met 0 of the 1 lesson here. 1 to go.",
            loaded.copy(counts = Tutorials.Counts(done = 0, due = 1, total = 1)).metWords)
        assertEquals("You have met all 1 lesson here.",
            loaded.copy(counts = Tutorials.Counts(done = 1, due = 0, total = 1)).metWords)
        // A PC too old to send `counts` gets NO line, rather than a made-up one.
        assertEquals("", loaded.copy(counts = null).metWords)
        assertEquals("", loaded.copy(counts = Tutorials.Counts(done = 0, due = 0, total = 0)).metWords)
        // And the sentence is not a shape the design refused.
        val said = loaded.metWords
        assertFalse("the line is a percentage", said.contains("%"))
        assertFalse(
            "the line scores the owner",
            Regex("streak|badge|points|score", RegexOption.IGNORE_CASE).containsMatchIn(said),
        )
    }

    @Test
    fun `a catalogue without counts is still read, and draws no line`() {
        // An older PC: everything else about the screen works, and the line is
        // simply absent.
        val noCounts = json(
            """{"ok": true, "sections": [], "tutorials": [
                 {"id": "intro", "section": "both", "title": "t", "why": "w", "minutes": 1,
                  "steps": [{"title": "one", "body": "b", "where": "Brain"}],
                  "state": "not_started", "step": 0, "steps_total": 1, "done": false,
                  "resume_at": null, "due": true}]}"""
        )
        val loaded = Tutorials.parse(noCounts)
        assertEquals(1, loaded?.tutorials?.size)
        assertNull(loaded?.counts)
        assertEquals("", loaded?.metWords)
    }

    @Test
    fun `an older backend is told to update, in words`() {
        assertEquals(Tutorials.Read.OlderBackend, Tutorials.readOf(ApiResult.Failed(ApiError.NotFound)))
        assertEquals(Tutorials.Read.OlderBackend, Tutorials.readOf(ApiResult.Failed(ApiError.NotAvailable)))
        assertEquals(Tutorials.UPDATE, Tutorials.readLine(Tutorials.Read.OlderBackend))
        // The route saying `available: false` is the same thing.
        assertEquals(
            Tutorials.Read.OlderBackend,
            Tutorials.readOf(ApiResult.Ok(json("""{"available": false, "why": "not yet"}"""))),
        )
    }

    @Test
    fun `an answer that is not the shape this screen reads is answered in words`() {
        assertNull(Tutorials.parse(json("""{"ok": true, "tutorials": []}""")))
        assertNull(Tutorials.parse(json("""{"nope": 1}""")))
        val read = Tutorials.readOf(ApiResult.Ok(json("""{"ok": true, "nope": 1}""")))
        assertTrue(read is Tutorials.Read.Failed)
        assertTrue((read as Tutorials.Read.Failed).reason.startsWith("Your PC answered"))
        assertEquals(read.reason, Tutorials.readLine(read))
    }

    @Test
    fun `the FAQ is read, and searched in the question and the answer`() {
        val faq = json(
            """
            {"ok": true, "count": 2, "questions": [
              {"q": "Does Jarvis send my things anywhere?", "a": "Only the named exceptions.",
               "where": "What asks first"},
              {"q": "How do I make it forget something?", "a": "Erase the words wipes the text.",
               "where": "Brain - Memory"}
            ]}
            """.trimIndent()
        )
        val questions = Tutorials.parseFaq(faq)
        assertEquals(2, questions?.size)
        assertEquals("How do I make it forget something?", Tutorials.search(questions!!, "forget").single().q)
        // A word from the ANSWER works too - half the time that is what is remembered.
        assertEquals("How do I make it forget something?", Tutorials.search(questions, "wipe").single().q)
        assertEquals(2, Tutorials.search(questions, "").size)
        assertTrue(Tutorials.search(questions, "zzz").isEmpty())
        assertNull(Tutorials.parseFaq(json("""{"ok": true}""")))
        assertNull(Tutorials.parseQuestion(json("""{"a": "no question"}""")))
    }

    @Test
    fun `a step writes exactly what the route wants`() {
        val body = Tutorials.progressBody("memory", 2)
        assertEquals("memory", body["id"].toString().trim('"'))
        assertEquals("in_progress", body["state"].toString().trim('"'))
        assertEquals(2, body["step"].toString().toInt())
        val cleared = Tutorials.progressBody("memory", 0, "not_started")
        assertEquals("not_started", cleared["state"].toString().trim('"'))
    }

    @Test
    fun `the labels are the desktop's, word for word`() {
        // jarvis-desktop/tests/tutorials.mjs checks the same words the other way
        // round; backend/test_tutorials.py checks the sections and states.
        assertEquals("Tutorials", Tutorials.HEADING)
        assertEquals("Next", Tutorials.NEXT)
        assertEquals("Back", Tutorials.BACK)
        assertEquals("Skip this one", Tutorials.SKIP)
        assertEquals("Leave it here", Tutorials.QUIT)
        assertEquals("Show this one again", Tutorials.AGAIN)
        assertEquals(listOf("pc", "phone"), Tutorials.SECTIONS.map { it.first })
        assertEquals(listOf("in_progress", "done", "skipped", "not_started"), Tutorials.STATES)
    }

    @Test
    fun `a step points at a real phone control, and only at the phone's own`() {
        val shared = json(
            """
            {"ok": true, "sections": [],
             "tutorials": [
               {"id": "talking", "section": "both", "title": "Talking to it", "why": "why",
                "minutes": 2,
                "steps": [{"title": "The talk button", "body": "b", "where": "Home",
                           "point": {"desktop": "prompt-field", "phone": "talk-button"}},
                          {"title": "PC only", "body": "b", "where": "Settings",
                           "point": {"desktop": "hotkeys", "phone": null}},
                          {"title": "No point at all", "body": "b", "where": "Brain"}],
                "state": "not_started", "step": 0, "steps_total": 3, "done": false,
                "resume_at": null, "due": true}
             ]}
            """.trimIndent()
        )
        val steps = Tutorials.parse(shared)!!.tutorials.single().steps

        // A step meant for the phone carries the PHONE's name, and this app
        // resolves it - which is the only thing "interactive on the phone" can
        // honestly mean before the highlight is drawn.
        assertEquals("talk-button", steps[0].point)
        assertTrue(steps[0].pointsHere)
        assertEquals("The talk button at the bottom of Home", steps[0].target)

        // The step that names a PC control is not a phone step at all: the
        // catalogue sends `null`, so the phone is never told to press a hotkey.
        // That is the failure this whole field exists to prevent.
        assertEquals("", steps[1].point)
        assertFalse(steps[1].pointsHere)
        assertNull(steps[1].target)

        // A step with no point is prose, and says so rather than guessing.
        assertEquals("", steps[2].point)
        assertFalse(steps[2].pointsHere)
    }

    /**
     * THE REAL CATALOGUE, NOT A FIXTURE. This is the check the phone was
     * missing, and the defect it would have caught shipped: the catalogue asks
     * the phone to point at `asks-first` (`intro` step 2) and `CONTROL_POINTS`
     * had no such entry, so that step lost its phone target silently. The test
     * above reads its own inline JSON, so it could never see the drift.
     *
     * The desktop's half has read `backend/jarvis_tutorials.py` all along
     * (jarvis-desktop/tests/tutorials.mjs, "every control the catalogue points
     * at here is one this app declares"). This is the same check, for the
     * phone, against the same file - and it is deliberately aimed at every
     * `"phone": "..."` in the CATALOGUE block rather than at one tutorial.
     */
    @Test
    fun `every control the real catalogue points at on the phone is one this app declares`() {
        val catalogue = catalogueText()
        val named = namesIn(catalogue, "point", "phone")
        assertTrue("the catalogue points at something on the phone", named.isNotEmpty())
        for (name in named.toSet()) {
            assertTrue(
                "net/Tutorials.kt declares the phone control `$name`, which the catalogue points at",
                Tutorials.CONTROL_POINTS.containsKey(name),
            )
        }
        // And the one that was missing, named so a future deletion fails loudly.
        assertTrue(Tutorials.CONTROL_POINTS.containsKey("asks-first"))
    }

    /**
     * `try` is DESIGNED AND NOT BUILT (docs/TUTORIALS-DESIGN.md), and it is
     * checked here anyway for the reason the `point` check exists: a name
     * written into the catalogue that no app declares is drift, and drift
     * written down once is the kind that survives. Nothing observes these yet;
     * [Tutorials.TRY_ACTIONS] is the list, and wiring it up is step 2 of that
     * design.
     */
    @Test
    fun `every action the real catalogue asks the phone to notice is one this app declares`() {
        val named = namesIn(catalogueText(), "try", "phone")
        assertTrue(
            "the lessons added on 2026-10-10 still carry their phone try actions",
            named.isNotEmpty(),
        )
        for (name in named.toSet()) {
            assertTrue(
                "net/Tutorials.kt declares the try action `$name`, which the catalogue asks for",
                Tutorials.TRY_ACTIONS.containsKey(name),
            )
        }
    }

    /**
     * The CATALOGUE literal of the real module, up to its own closing bracket.
     * The module's prose explains `point` and `try` with examples, and an
     * example is not a step - reading the whole file would judge prose.
     */
    private fun catalogueText(): String {
        val py = repoFile("backend/jarvis_tutorials.py").readText()
        val start = py.indexOf("\nCATALOGUE = (")
        assertTrue("the catalogue is where this check expects it", start > 0)
        val end = py.indexOf("\n)\n", start)
        assertTrue("the catalogue has a closing bracket", end > start)
        return py.substring(start, end)
    }

    /**
     * Every name one app is given by the catalogue's `point` (or `try`) maps.
     *
     * Read as the maps themselves and NOT as loose `"phone": "..."` matches: a
     * step may carry both, and their names belong to two different registries.
     * Conflating them is how the desktop's own version of this check went wrong
     * the first time.
     */
    private fun namesIn(catalogue: String, field: String, app: String): List<String> =
        Regex("\"$field\":\\s*\\{[^}]*?\"$app\":\\s*(?:\"([a-z0-9-]+)\"|null)")
            .findAll(catalogue).map { it.groupValues[1] }.filter { it.isNotEmpty() }.toList()

    /** Walks up from Gradle's working folder to the repository root. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    @Test
    fun `no PC-only control is declared on the phone`() {
        // The two registries are allowed to agree where the two apps genuinely
        // mean the same thing - both have an approval card, both have a talk
        // button, and a name is how a shared step points at each app's own.
        //
        // What must never happen is a control only the PC HAS turning up here.
        // That is the failure the owner is asking to avoid: a phone tutorial
        // sending him to a hotkey, a window or the HUD. The desktop's own
        // registry is checked the other way round in
        // jarvis-desktop/tests/tutorials.mjs.
        val pcOnly = listOf(
            "prompt-field",   // the PC's input, and the palette behind it
            "hotkeys",        // a keyboard
            "hud-talk",       // the HUD window
            "faces",          // the Faces window
            "brain-memory",   // Brain's own pages, drawn on the PC
            "brain-tutorials",
            "brain-about",
            "stop-everything", // the PC's stop hotkey
        )
        for (name in pcOnly) {
            assertFalse(
                "the phone must not declare the PC-only control `$name`",
                Tutorials.CONTROL_POINTS.containsKey(name),
            )
        }
        assertTrue(Tutorials.CONTROL_POINTS.isNotEmpty())
    }
}
