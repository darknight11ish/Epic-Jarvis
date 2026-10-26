package com.jarvis.client

import com.jarvis.client.data.LiveEnd
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.voice.LiveExtras
import com.jarvis.client.voice.LiveRules
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The Jarvis Live extras (the owner's decisions of 2026-09-28): the tile,
 * the headset button, "Live ended - Resume", the Bluetooth headset
 * microphone, "End Live when" on the Security screen, and "Talk about this
 * in Live" - their rules, and (reading the source, like the other contract
 * tests) that the headset button and the tile never approve anything.
 */
class LiveExtrasTest {

    private fun on(minutes: Int, device: String = "phone"): JsonObject = buildJsonObject {
        put("state", "on")
        put("on", true)
        put("device", device)
        put("minutes_left", minutes)
    }

    @Test
    fun `the tile - on here with the minutes left, else where it is`() {
        assertEquals(LiveExtras.Tile(true, "12 min left"), LiveExtras.tile(on(12), connected = true))
        assertEquals(LiveExtras.Tile(false, "On your PC"), LiveExtras.tile(on(5, "desktop"), connected = true))
        assertEquals(LiveExtras.Tile(false, "Off"), LiveExtras.tile(null, connected = true))
        assertEquals(LiveExtras.Tile(false, "Offline"), LiveExtras.tile(null, connected = false))
        // On here, even offline: End must stay reachable (it is never held).
        assertTrue(LiveExtras.tile(on(3), connected = false).on)
    }

    @Test
    fun `the headset button - press stops talking, a hold toggles the mic, once`() {
        val k = LiveExtras.HeadsetKeys()
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 79, 0, 1000, 1000))
        assertEquals(LiveExtras.Press.STOP_TALKING, k.onKey(LiveExtras.UP, 79, 0, 1000, 1150))
        // Held: the key repeats; the long press fires once, the release does nothing.
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 85, 0, 2000, 2000))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 85, 1, 2000, 2300))
        assertEquals(LiveExtras.Press.MIC_TOGGLE, k.onKey(LiveExtras.DOWN, 85, 2, 2000, 2700))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 85, 3, 2000, 2900))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.UP, 85, 0, 2000, 3000))
        // A headset that sends no repeats: a long hold is read on release.
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 79, 0, 5000, 5000))
        assertEquals(LiveExtras.Press.MIC_TOGGLE, k.onKey(LiveExtras.UP, 79, 0, 5000, 5800))
        // Any other key: nothing.
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.DOWN, 87, 0, 6000, 6000))
        assertEquals(LiveExtras.Press.NONE, k.onKey(LiveExtras.UP, 87, 0, 6000, 6100))
        // An up with no down (a stray event): nothing.
        assertEquals(LiveExtras.Press.NONE, LiveExtras.HeadsetKeys().onKey(LiveExtras.UP, 79, 0, 0, 10))
    }

    @Test
    fun `the headset button and the tile never approve anything`() {
        val root = listOf(File("src/main/java"), File("app/src/main/java"),
            File("jarvis-client/app/src/main/java")).first { it.isDirectory }
        val service = File(root, "com/jarvis/client/service/LiveService.kt").readText()
        val cb = service.substring(service.indexOf("private fun onHeadset("))
        val body = cb.substring(0, cb.indexOf("\n    }\n"))
        for (word in listOf("approve", "decide", "deny", "pending", "Approval")) {
            assertFalse("the headset button's code names '$word'", body.contains(word, ignoreCase = true))
        }
        assertTrue(body.contains("stopSpeaking()"))
        assertTrue(body.contains("liveMute("))
        val tile = File(root, "com/jarvis/client/service/LiveTileService.kt").readText()
        for (word in listOf("approve", "decide(", "deny(", "JarvisRuntime.pending")) {
            assertFalse("the tile names '$word'", tile.contains(word, ignoreCase = true))
        }
        assertTrue("the tile ends Live directly (never held)", tile.contains("liveEndNow(\"owner\")"))
        assertTrue("the tile starts Live through the app (after App lock)", tile.contains("ACTION_START_LIVE"))
    }

    @Test
    fun `Live ended - Resume - only after an end here that the PC can resume, for what is left`() {
        val ended = buildJsonObject {
            put("state", "ended")
            put("on", false)
            put("ended_device", "phone")
            put("resumable", true)
            put("ended_ago_s", 60)
            put("limits", buildJsonObject { put("resume_s", 600) })
        }
        assertEquals(540_000L, LiveExtras.resumeFor(ended))
        val obj = { k: String, v: Any ->
            JsonObject(ended.toMutableMap().apply {
                put(k, if (v is Boolean) JsonPrimitive(v) else if (v is Int) JsonPrimitive(v) else JsonPrimitive(v as String))
            })
        }
        assertNull("not resumable (the owner ended it)", LiveExtras.resumeFor(obj("resumable", false)))
        assertNull("ended on the PC", LiveExtras.resumeFor(obj("ended_device", "desktop")))
        assertNull("the 10 minutes are up", LiveExtras.resumeFor(obj("ended_ago_s", 600)))
        assertNull(LiveExtras.resumeFor(on(3)))
        assertEquals(LiveRules.RESUME_S, 600)
    }

    @Test
    fun `the Bluetooth headset's microphone is preferred, and the screen says which`() {
        val phone = LiveExtras.Mic(15, "")
        val sco = LiveExtras.Mic(7, "Buds")
        val le = LiveExtras.Mic(26, "LE Buds")
        assertNull(LiveExtras.pickHeadset(listOf(phone)))
        assertEquals(sco, LiveExtras.pickHeadset(listOf(phone, sco)))
        assertEquals(le, LiveExtras.pickHeadset(listOf(sco, phone, le)))
        assertEquals(LiveExtras.MIC_PHONE, LiveExtras.micWords(null))
        assertEquals("Microphone: your Bluetooth headset (Buds)", LiveExtras.micWords(sco))
        assertEquals(LiveExtras.MIC_FELL_BACK, LiveExtras.micWords(sco, fellBack = true))
    }

    /**
     * The owner's request of 2026-10-26 ("get rid of the long explanation on
     * jarvis live"): the three-sentence headset-button paragraph is not on the
     * Live screen any more. Three checks, because the paragraph can come back
     * three ways:
     *
     * 1. The words, wherever they are moved to - inline, in a constant in
     *    another file, in a rules table. The three removed phrases are looked
     *    for in every Kotlin file under app/src/main/java, after the
     *    `"..." + "..."` seams are flattened. The flattening is needed, not
     *    cosmetic: the removed paragraph was itself three literals joined with
     *    + (63 + 82 + 76 characters), and its own seams fell inside two of the
     *    three phrases, so the raw text held only one of them (measured on the
     *    file the paragraph was removed from).
     * 2. Every `add(...)` in the notes plate is given a quoted note the plate
     *    itself writes, or the microphone line `add(it)`. A note kept in a
     *    constant or a field - or a lookup whose key is quoted,
     *    `SEEN.getValue("x")` - is caught here, whatever its wrapping and
     *    whatever its words.
     * 3. The plate's own literals are short. 112 characters is the honest
     *    boundary: the plate already RENDERS a 110-character note, joined from
     *    two literals at LiveScreen.kt:515-516 (79 + 31), so "no note of 90+"
     *    was measuring something the screen was already doing. The rule is
     *    stated on the source, not on the note, because a note can be joined
     *    from literals or built by a call such as `BargeIn.describe(...)`, and
     *    a text test cannot see the rendered length. What it can see is that
     *    no literal - and no run of literals joined by + - in the plate is 112
     *    characters or longer. The longest single literal in the plate today
     *    is 79 characters of text (81 counting its quotes).
     *
     * The words are deliberately not pinned by their old constant name: the
     * constant is gone, and "never approves anything" legitimately remains in
     * LiveExtras's own KDoc.
     */
    @Test
    fun `the Live screen does not carry the long headset explanation`() {
        val main = listOf(File("src/main/java"), File("app/src/main/java"),
            File("jarvis-client/app/src/main/java")).first { it.isDirectory }
        val screen = File(main, "com/jarvis/client/ui/screens/LiveScreen.kt").readText()

        // 1. The words, wherever they are moved to, however they are wrapped.
        val kotlinSources = main.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .joinToString("\n") { it.readText() }
        val flattened = kotlinSources.replace(SEAM, "")
        for (phrase in listOf(
            "press to stop Jarvis talking",
            "hold to turn the microphone off or on",
            "opens the phone's assistant instead",
        )) {
            assertFalse(
                "the removed headset explanation is back: '$phrase' (found after flattening the " +
                    "\"...\" + \"...\" seams)",
                flattened.contains(phrase),
            )
        }

        // 2. The plate's shape. Its two markers are how it is found: if they
        // move, this test fails and says so - it must never quietly measure the
        // whole file (a KDoc comment then made the old ". " rule fire).
        val plate = notesPlate(screen)

        // 2a. Every add(...) is a quoted note the plate itself writes, or the
        // microphone line. A constant, a field, or a lookup whose *key* is
        // quoted (`SEEN.getValue("x")`) are all caught here, whatever the note
        // says and however it is wrapped.
        val args = addArguments(plate)
        assertTrue(
            "no add(...) calls were found in the notes plate - the plate moved, update this test",
            args.isNotEmpty(),
        )
        for (arg in args) {
            assertTrue(
                "the Live plate adds `${shortForm(arg)}` - not a quoted note the plate writes: a " +
                    "constant, a field, or a lookup whose key is quoted. Write the note as a " +
                    "literal here, or this test cannot measure it.",
                isQuotedNote(arg),
            )
        }

        // 2b. No note of 112+ characters, however it is wrapped.
        val longNotes = LITERAL.findAll(plate.replace(SEAM, ""))
            .filter { it.value.length - 2 >= LONG_NOTE }
            .map { it.value }
            .toList()
        assertTrue(
            "a long note is back in the Live plate (${LONG_NOTE}+ characters): " +
                shortForm(longNotes.firstOrNull() ?: ""),
            longNotes.isEmpty(),
        )

        // 2c. No two-sentence note: neither written with ". " in one literal,
        // nor split across a seam right at the sentence end (".\" + ").
        assertFalse("a two-sentence note is back in the Live plate", plate.contains(". "))
        assertFalse(
            "two sentences are back in one note: a sentence ends exactly at a \" + \" seam, so " +
                "the note the screen shows is two sentences",
            SENTENCE_THEN_SEAM.containsMatchIn(plate),
        )

        // The one short line the owner kept is still required.
        assertTrue("the microphone line is still in the notes", plate.contains("mic?.let { add(it) }"))
    }

    /** The `" + "` seam between two string literals, and any whitespace around the +. */
    private val SEAM = Regex("\"\\s*\\+\\s*\"")

    /** One Kotlin string literal: `\"` and `\\` inside it do not end it (the old regex split those). */
    private val LITERAL = Regex("\"(?:\\\\.|[^\"\\\\\\r\\n])*\"")

    /** A sentence ending inside a literal, immediately followed by a + seam. */
    private val SENTENCE_THEN_SEAM = Regex("[.!?]\"\\s*\\+")

    /** 112: the honest "too long" line, explained on the test above. */
    private val LONG_NOTE = 112

    /** Whitespace collapsed and long text cut short, so an assertion message stays readable. */
    private fun shortForm(s: String): String = s.replace(Regex("\\s+"), " ").trim()
        .let { if (it.length <= 100) it else it.take(100) + "..." }

    /**
     * The notes plate: from `val notes = buildList {` to the
     * `if (notes.isNotEmpty())` that shows it. If either marker has moved, that
     * is a failure that names itself - never a slice that quietly becomes the
     * whole file (an old version of this test did exactly that, then failed on
     * a KDoc comment with a message about a note).
     */
    private fun notesPlate(screen: String): String {
        val open = "val notes = buildList {"
        val close = "if (notes.isNotEmpty()) {"
        val start = screen.indexOf(open)
        assertTrue(
            "the notes plate's opening marker moved - update this test: \"$open\" is not in " +
                "LiveScreen.kt",
            start >= 0,
        )
        val end = screen.indexOf(close, start + open.length)
        assertTrue(
            "the notes plate's closing marker moved - update this test: \"$close\" is not after " +
                "the plate in LiveScreen.kt",
            end > start,
        )
        val plate = screen.substring(start, end)
        assertNotEquals(
            "the notes plate's markers moved - update this test: the slice is the whole file, so " +
                "nothing was measured",
            screen,
            plate,
        )
        assertTrue(
            "the notes plate's slice is the whole file - the markers moved, so nothing was measured",
            plate.length < screen.length,
        )
        return plate
    }

    /**
     * Is this `add(...)` argument a note the plate itself writes? True for the
     * microphone line (`it`) and for an argument that carries a string literal
     * outside every bracket - `"note"`, `"a" + "b"`, or the real plate's
     * `if (...) { "a note" } else { "another" }`.
     *
     * A literal *inside* brackets is a key, not a note: `SEEN.getValue("x")`
     * and `SEEN["x"]` both render a string the plate does not write, so both
     * are false. That is the whole point of the rule - words in a constant
     * cannot be measured by this test, and `arg.contains('"')` alone let a
     * quoted key through.
     */
    private fun isQuotedNote(arg: String): Boolean {
        if (arg == "it") return true
        var depth = 0
        var i = 0
        while (i < arg.length) {
            when (arg[i]) {
                '"' -> {
                    if (depth == 0) return true
                    i++
                    while (i < arg.length) {
                        if (arg[i] == '\\' && i + 1 < arg.length) {
                            i += 2
                            continue
                        }
                        if (arg[i] == '"') break
                        i++
                    }
                }
                '(', '[' -> depth++
                ')', ']' -> depth--
                else -> Unit
            }
            i++
        }
        return false
    }

    /**
     * Every `add(...)` argument in the plate, parentheses and quoted text walked
     * properly: a nested call (`BargeIn.describe(true, ...)`) or a `)` inside a
     * note does not end the argument early, and an escaped quote inside a note
     * is part of that note.
     */
    private fun addArguments(plate: String): List<String> {
        val out = mutableListOf<String>()
        var from = 0
        while (true) {
            val at = plate.indexOf("add(", from)
            if (at < 0) return out
            from = at + 4
            // Only a bare add(...), not some other call that ends in "add(".
            val before = plate.getOrNull(at - 1)
            if (before != null && (before.isLetterOrDigit() || before == '_' || before == '.')) continue
            val arg = StringBuilder()
            var depth = 1
            var inString = false
            var i = at + 4
            while (i < plate.length) {
                val c = plate[i]
                if (inString) {
                    arg.append(c)
                    if (c == '\\' && i + 1 < plate.length) {
                        arg.append(plate[i + 1])
                        i += 2
                        continue
                    }
                    if (c == '"') inString = false
                    i++
                    continue
                }
                if (c == '"') {
                    inString = true
                    arg.append(c)
                } else if (c == '(') {
                    depth++
                    arg.append(c)
                } else if (c == ')') {
                    depth--
                    if (depth == 0) {
                        from = i + 1
                        break
                    }
                    arg.append(c)
                } else {
                    arg.append(c)
                }
                i++
            }
            if (i >= plate.length) from = plate.length
            out += arg.toString().trim().removeSuffix(",").trim()
        }
    }

    @Test
    fun `End Live when - strict by default, the looser choice asks, back is instant`() {
        val base = Security(appLock = true)
        assertEquals(LiveEnd.APP_LOCK, base.liveEnd)
        assertTrue(SecurityRules.loosens(base, base.copy(liveEnd = LiveEnd.SCREEN_LOCK)))
        assertFalse(SecurityRules.loosens(base.copy(liveEnd = LiveEnd.SCREEN_LOCK), base))
        // Strict: App lock's clock ends it; the screen lock alone does not.
        assertEquals("app_lock", SecurityRules.liveEndsNow(base, appLockWouldLock = true, screenLocked = false))
        assertNull(SecurityRules.liveEndsNow(base, appLockWouldLock = false, screenLocked = true))
        // Looser: only the phone's own screen lock.
        val loose = base.copy(liveEnd = LiveEnd.SCREEN_LOCK)
        assertNull(SecurityRules.liveEndsNow(loose, appLockWouldLock = true, screenLocked = false))
        assertEquals("screen_lock", SecurityRules.liveEndsNow(loose, appLockWouldLock = true, screenLocked = true))
        // App lock off: neither ends it, as before the setting.
        assertNull(SecurityRules.liveEndsNow(Security(), appLockWouldLock = true, screenLocked = true))
        assertNull(SecurityRules.liveEndsNow(loose.copy(appLock = false), appLockWouldLock = true, screenLocked = true))
        // Stored and read back; anything unreadable is the strict default.
        val stored = SecurityRules.toStored(loose)
        assertEquals(loose, SecurityRules.fromStored { stored[it] })
        assertEquals(LiveEnd.APP_LOCK, SecurityRules.fromStored { if (it == SecurityRules.KEY_LIVE_END) "nonsense" else null }.liveEnd)
        assertTrue(SecurityRules.summary(loose).contains(SecurityRules.LIVE_END_SUMMARY))
        // Both end reasons are ones the PC takes from an app.
        assertTrue("screen_lock" in LiveRules.END_REASONS && "app_lock" in LiveRules.END_REASONS)
        assertTrue(LiveRules.stopBody("screen_lock").contains("\"why\":\"screen_lock\""))
    }

    @Test
    fun `Solve it here blocks screenshots while it shows`() {
        assertTrue(SecurityRules.blockScreenCapture(Security(), handoffShown = true))
        assertFalse(SecurityRules.blockScreenCapture(Security(), handoffShown = false))
    }

    @Test
    fun `the manifest - a tile, and a second share entry for Live, text only`() {
        val manifest = listOf(File("src/main/AndroidManifest.xml"), File("app/src/main/AndroidManifest.xml"),
            File("jarvis-client/app/src/main/AndroidManifest.xml")).first { it.isFile }.readText()
        val tile = manifest.substring(manifest.indexOf("android:name=\".service.LiveTileService\""))
            .substringBefore("</service>")
        assertTrue(tile.contains("android.permission.BIND_QUICK_SETTINGS_TILE"))
        assertTrue(tile.contains("android.service.quicksettings.action.QS_TILE"))
        val alias = manifest.substring(manifest.indexOf("<activity-alias"))
            .substringBefore("</activity-alias>")
        assertTrue(alias.contains("android:name=\".ShareToLive\""))
        assertTrue(alias.contains("android:targetActivity=\".MainActivity\""))
        assertTrue(alias.contains("android.intent.action.SEND"))
        assertTrue(alias.contains("android:mimeType=\"text/plain\""))
        assertFalse("images are not shared into Live", alias.contains("image/"))
        // No new dangerous permission for any of it. (CAMERA is in the manifest
        // for "Scan the code on your PC" - QR pairing, asked for on a tap - and
        // nothing about Live uses it: the Live camera stays off until the 12 GB
        // card passes the photo test.)
        for (p in listOf("BLUETOOTH_CONNECT", "READ_PHONE_STATE", "BLUETOOTH\"")) {
            assertFalse("the manifest asks for $p", manifest.contains("android.permission.$p"))
        }
    }
}
