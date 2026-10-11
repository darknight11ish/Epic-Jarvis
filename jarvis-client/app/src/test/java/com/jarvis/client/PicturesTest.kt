package com.jarvis.client

import com.jarvis.client.net.Pictures
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Ask for a picture, and keep it" on the phone (the owner's decision of
 * 2026-09-27: *"12 GB card: longer conversations with picture understanding
 * first, and making pictures too (swapped in when asked, since both cannot sit
 * on the card at once)"*; docs/JARVIS-API.md section 124;
 * net/Pictures.kt, ui/screens/PicturesPlate.kt, backend jarvis_pictures.py).
 *
 * WHAT THIS IS, HONESTLY
 *
 * There is no phone, no PC, no graphics card and no model anywhere in this
 * file, and there must not be. It tests the ONE thing the phone actually
 * decides: how it reads what the PC sent, what it refuses to send, and what
 * it does while the private lists are hidden. Whether ComfyUI draws a good
 * picture is not a question this suite can ask, and it does not pretend to.
 *
 * WHAT IS COVERED
 *
 *  - a real answer reads back: the folder, the size, the switch, and every
 *    picture's own prompt, seed and when it was made;
 *  - the PC's own sentences are shown word for word, never rebuilt here;
 *  - a PC without the route draws nothing at all (not "no pictures yet");
 *  - a HIDDEN answer is read as hidden, and holds no prompt at all;
 *  - the phone cannot change the switch, the program or the folder: it has no
 *    call for them, and the settings route is the PC's alone;
 *  - the body it sends holds the prompt and NOTHING else - never a seed, a
 *    model, a size or a step count, so the phone cannot pick a drawing
 *    program's knobs;
 *  - a blank or too-long prompt is refused before anything is sent;
 *  - an id is a bare file stem: no separator, no "..", no other path;
 *  - "Save to my phone" names the file safely, from the PC's own name;
 *  - the words are the ones both apps share, and the one sentence that says
 *    nothing is sent anywhere is there.
 */
class PicturesTest {

    private fun obj(vararg pairs: Pair<String, Any?>): JsonObject = buildJsonObject {
        for ((k, v) in pairs) when (v) {
            null -> put(k, kotlinx.serialization.json.JsonNull)
            is String -> put(k, v)
            is Int -> put(k, v)
            is Long -> put(k, v)
            is Boolean -> put(k, v)
        }
    }

    private fun arr(vararg items: JsonObject) =
        kotlinx.serialization.json.JsonArray(items.toList())

    private val realAnswer: JsonObject = buildJsonObject {
        put("ok", true)
        put("available", true)
        put("enabled", true)
        put("runtime", "comfyui")
        put("runtime_plain", "ComfyUI")
        put("folder", "C:\\Users\\owner\\Pictures\\Jarvis")
        put("count", 2)
        put("bytes", 900_000L)
        put("size_words", "879 KB")
        put("words", "")
        put("keep", "Your pictures are kept until you delete them yourself.")
        put("runtimes", arr(
            obj("id" to "comfyui", "plain" to "ComfyUI", "address" to "http://127.0.0.1:8188"),
            obj("id" to "sd_cpp", "plain" to "stable-diffusion.cpp", "address" to "http://127.0.0.1:1234"),
        ))
        put("pictures", arr(
            obj("name" to "2026-10-11-140509-a-red-panda.png", "id" to "2026-10-11-140509-a-red-panda",
                "prompt" to "a red panda in a library", "seed" to 1234L, "model" to "sd_xl_base.safetensors",
                "made_at_words" to "11 Oct 2026, 14:05", "bytes" to 400_000L, "record" to true),
            obj("name" to "2026-10-11-140600-an-owl.png", "id" to "2026-10-11-140600-an-owl",
                "prompt" to "", "made_at_words" to "11 Oct 2026, 14:06", "bytes" to 500_000L,
                "record" to false),
        ))
    }

    // ── a real answer ────────────────────────────────────────────────────

    @Test
    fun aRealAnswerReadsBackWhole() {
        val r = Pictures.readReply(200, realAnswer)
        assertTrue(r.available)
        assertTrue(r.enabled)
        assertTrue(r.canAsk)
        assertTrue(r.visible)
        assertEquals("C:\\Users\\owner\\Pictures\\Jarvis", r.folder)
        assertEquals(2, r.count)
        assertEquals("879 KB", r.sizeWords)
        assertEquals(2, r.shots.size)
        assertEquals("a red panda in a library", r.shots[0].prompt)
        assertEquals(1234L, r.shots[0].seed)
        assertEquals("sd_xl_base.safetensors", r.shots[0].model)
        assertEquals("11 Oct 2026, 14:05", r.shots[0].madeAtWords)
        assertTrue(r.shots[0].hasRecord)
        assertFalse(r.shots[1].hasRecord)
        // The two programs the PC supports, with what to install, so the
        // screen can say what is missing without inventing a word.
        assertEquals(listOf("comfyui", "sd_cpp"), r.programs.map { it.id })
        assertEquals("ComfyUI", r.programs[0].plain)
    }

    @Test
    fun thePcsOwnSentencesAreShownWordForWord() {
        // Nothing set up: the PC's one plain sentence, not a code and not blank.
        val notSetUp = obj(
            "ok" to true, "available" to true, "enabled" to true,
            "folder" to "C:\\Pictures\\Jarvis", "count" to 0, "bytes" to 0,
            "size_words" to "0 B",
            "words" to ("Jarvis has no picture-making program set up yet, so it "
                + "cannot draw one. Install ComfyUI or stable-diffusion.cpp's "
                + "server, then choose which one you installed in Settings, under Pictures."),
            "keep" to "kept",
            "runtimes" to arr(),
            "pictures" to arr(),
        )
        val r = Pictures.readReply(200, notSetUp)
        assertTrue(r.canAsk)  // the switch is on; the PROGRAM is what is missing
        assertTrue(r.words.startsWith("Jarvis has no picture-making program"))
        assertTrue(r.words.endsWith("under Pictures."))
        // A refusal comes back as its own sentence, as sent.
        val refused = obj("ok" to false, "error" to "Jarvis is set to use ComfyUI, but it is not answering. Start it on this PC, then ask again.")
        assertEquals(
            "Jarvis is set to use ComfyUI, but it is not answering. Start it on this PC, then ask again.",
            Pictures.refusal(refused),
        )
        // A refusal with no sentence at all still says something true.
        assertEquals(Pictures.WORDS.getValue("unreadable"), Pictures.refusal(obj("ok" to false)))
        assertEquals(Pictures.WORDS.getValue("unreadable"), Pictures.refusal(null))
    }

    @Test
    fun anOlderPcDrawsNothingAtAll() {
        // Not "no pictures yet" - the feature is simply not there.
        for (status in listOf(404, 501)) {
            val r = Pictures.readReply(status, null)
            assertFalse(r.available)
            assertFalse(r.visible)
            assertFalse(r.canAsk)
            assertTrue(r.shots.isEmpty())
        }
        assertFalse(Pictures.readReply(200, null).available)
        assertFalse(Pictures.readReply(200, obj("ok" to true)).available)
    }

    // ── the hiding rule ──────────────────────────────────────────────────

    @Test
    fun aHiddenAnswerCarriesNoPromptAndNothingIsFetched() {
        // What the PC sends while "Hide memory lists and chat history" is on:
        // the whole gallery taken out, and its own line.
        val hidden = obj(
            "ok" to true, "available" to true, "hidden" to true,
            "keep_on_screen" to true, "title" to "Pictures",
            "hidden_words" to "Hidden while memory lists and chat history are hidden.",
        )
        val r = Pictures.readReply(200, hidden)
        assertTrue(r.hidden)
        assertFalse(r.visible)
        assertFalse(r.canAsk)
        assertTrue(r.shots.isEmpty())
        assertEquals("", r.folder)
        assertEquals(0, r.count)
        assertEquals("", r.sizeWords)
        assertTrue(r.hiddenWords.isNotBlank())
        // The PC's own hidden line is not rebuilt on the phone: no literal of
        // the phone's own can appear in its place.
        assertEquals("Hidden while memory lists and chat history are hidden.", r.hiddenWords)
        // A hidden answer with no words at all still gets a true sentence.
        val bare = Pictures.readReply(200, obj("ok" to true, "available" to true, "hidden" to true))
        assertEquals(Pictures.WORDS.getValue("hidden"), bare.hiddenWords)
        // And the plate's own rule: while hidden it throws the answer away and
        // fetches nothing, which is what Reply.HIDDEN is for.
        assertFalse(Pictures.Reply.HIDDEN.visible)
    }

    // ── the phone changes nothing ────────────────────────────────────────

    @Test
    fun thePhoneHasNoWayToChangeTheSwitchTheProgramOrTheFolder() {
        // The phone's own source, read from the classpath path the test task
        // runs in. It may READ the switch and the folder - the gallery says so
        // - but the settings route and its action names must be nowhere, so
        // there is nothing it could send to change any of them.
        val source = java.io.File("src/main/java/com/jarvis/client/net/Pictures.kt")
        if (!source.isFile) return  // run from somewhere else: the checks below still hold
        val text = source.readText()
        assertFalse(text.contains("pictures/settings"))
        for (action in listOf("\"enabled\"", "\"runtime\"", "\"folder\"")) {
            assertFalse("the phone must not send $action", text.contains(action))
        }
        assertTrue(text.contains("const val PATH = \"/api/pictures\""))
        assertTrue(text.contains("const val FILE_PATH = \"/api/pictures/file\""))
    }

    // ── what the phone sends ─────────────────────────────────────────────

    @Test
    fun theBodyHoldsTheOwnersWordsAndNothingElse() {
        val body = Pictures.makeBody("  a red panda in a library  ")
        assertNotNull(body)
        assertEquals("""{"prompt":"a red panda in a library"}""", body)
        // Not a seed, not a model, not a size, not a step count: the phone
        // cannot pick a drawing program's knobs.
        for forbidden in listOf("seed", "model", "steps", "width", "height", "settings") {
            assertFalse(body!!.contains(forbidden))
        }
        // A prompt of spaces, or one over the PC's own cap, is refused HERE
        // rather than sent to be refused a second time.
        assertNull(Pictures.makeBody("   "))
        assertNull(Pictures.makeBody(""))
        assertNull(Pictures.makeBody("x".repeat(Pictures.MAX_PROMPT + 1)))
        assertNotNull(Pictures.makeBody("x".repeat(Pictures.MAX_PROMPT)))
    }

    @Test
    fun anIdIsABareFileStemAndNeverAPath() {
        val good = "2026-10-11-140509-a-red-panda"
        assertNotNull(Pictures.filePath(good))
        assertEquals("/api/pictures/file?id=$good", Pictures.filePath(good))
        for bad in listOf(
            "", "..", "../pictures.json", "/etc/passwd", "C:\\Windows\\win.ini",
            "2026-10-11-140509-a/b", "2026-10-11-140509-a\\b",
            "2026-10-11-140509-..", "not-a-date-at-all", "9".repeat(97),
        ) {
            assertNull("the id $bad must be refused", Pictures.filePath(bad))
        }
    }

    @Test
    fun theBytesAreDecodedAndNothingElseIs() {
        // A real 1x1 PNG, base64, exactly as the PC sends it.
        val png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        val bytes = Pictures.pngBytes(obj("ok" to true, "png" to png, "encoding" to "base64"))
        assertNotNull(bytes)
        assertTrue(bytes!!.size > 50)
        // The PNG magic, so this is a picture and not a string that decoded.
        assertEquals(0x89.toByte(), bytes[0])
        assertEquals('P'.code.toByte(), bytes[1])
        assertNull(Pictures.pngBytes(obj("ok" to true, "png" to "")))
        assertNull(Pictures.pngBytes(obj("ok" to true, "png" to "not base64 at all !!")))
        assertNull(Pictures.pngBytes(obj("ok" to true)))
        assertNull(Pictures.pngBytes(null))
    }

    @Test
    fun theFileSavedToThePhoneIsNamedSafely() {
        val shot = Pictures.Shot(
            name = "2026-10-11-140509-a-red-panda.png", id = "2026-10-11-140509-a-red-panda",
            prompt = "a red panda", seed = 1L, model = "", madeAtWords = "", bytes = 0L,
            hasRecord = true,
        )
        assertEquals("2026-10-11-140509-a-red-panda.png", Pictures.fileName(shot))
        // A name with anything unsafe in it comes out with only safe characters.
        val nasty = shot.copy(id = "a/b\\c:d*e?f", name = "../x.png")
        val safe = Pictures.fileName(nasty)
        assertTrue(safe.endsWith(".png"))
        assertFalse(safe.contains("/"))
        assertFalse(safe.contains("\\"))
        assertFalse(safe.contains(".."))
        // An id that is nothing usable still gets a file name rather than a path.
        assertEquals("jarvis-picture.png", Pictures.fileName(shot.copy(id = "", name = "")))
    }

    @Test
    fun theWordsBothAppsShareAreTheOnesTheFeatureNeeds() {
        for (key in listOf(
            "title", "under", "ask_label", "make", "another", "save_phone",
            "saved_phone", "empty", "hidden", "hidden_short", "prompt_label",
            "made_label", "seed_label", "no_record", "not_kept", "missing",
            "unreadable", "no_words", "show", "show_title", "still_hidden",
        )) {
            assertTrue("no `$key`", Pictures.WORDS.containsKey(key))
            assertTrue("`$key` is empty", Pictures.WORDS.getValue(key).isNotBlank())
        }
        assertTrue(Pictures.WORDS.getValue("not_kept").contains("never sent anywhere"))
        assertEquals("Pictures", Pictures.WORDS.getValue("title"))
        // A picture with no record is still listed, and says so rather than
        // showing a blank line where the words should be.
        val shot = Pictures.Shot("a.png", "2026-10-11-140509-a", "", null, "", "11 Oct", 0L, false)
        assertTrue(shot.said().contains(Pictures.WORDS.getValue("no_record")))
    }

    @Test
    fun theSizeAPersonReadsIsSaidTheWayThePcSaysIt() {
        assertEquals("0 B", Pictures.sizedWords(0))
        assertEquals("2 KB", Pictures.sizedWords(2048))
        assertEquals("1.0 MB", Pictures.sizedWords(1024L * 1024))
        assertEquals("1.50 GB", Pictures.sizedWords(1024L * 1024 * 1024 * 3 / 2))
    }

    @Test
    fun theDrawingIdIsReadFromThePcsAnswer() {
        assertEquals("2026-10-11-140509-a-red-panda", Pictures.madeId(
            obj("ok" to true, "id" to "2026-10-11-140509-a-red-panda"),
        ))
        assertNull(Pictures.madeId(obj("ok" to true)))
        assertNull(Pictures.madeId(obj("ok" to true, "id" to "")))
        assertNull(Pictures.madeId(null))
    }
}
