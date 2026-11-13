package com.jarvis.client.localai

import com.jarvis.client.ui.Screen
import com.jarvis.client.ui.screens.MoreMenuWords
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The promises around the engine that no renderer can hold: the switch ships
 * OFF, the label is word for word, the library is never loaded by a class
 * initialiser, the screen adds no network or token path, and R8 keeps the JNI
 * names.
 *
 * These are deliberately source-read pins rather than Compose tests. The app
 * has no Compose test rule (the face runs an endless frame loop, so a
 * ComposeTestRule would never see "idle"), and the behaviour they guard is a
 * property of the wiring - a sentence, a constant, an absent import - which is
 * exactly what a source read can see and a screenshot cannot.
 */
class LocalAiShipsOffTest {

    private val sources: File by lazy {
        var directory: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (directory != null &&
            !File(directory, "jarvis-client/app/src/main/java/com/jarvis/client/localai").isDirectory
        ) {
            directory = directory.parentFile
        }
        requireNotNull(directory) {
            "jarvis-client/app/src/main/java/com/jarvis/client/localai not found above " +
                System.getProperty("user.dir")
        }
        File(directory, "jarvis-client/app/src/main/java/com/jarvis/client/localai")
    }

    private fun source(name: String): String {
        val file = File(sources, name)
        assertTrue("missing source $file", file.isFile)
        return file.readText()
    }

    private fun moduleFile(path: String): String {
        var directory: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (directory != null && !File(directory, "jarvis-client").isDirectory) {
            directory = directory.parentFile
        }
        val root = requireNotNull(directory)
        val file = File(root, "jarvis-client/$path")
        assertTrue("missing file $file", file.isFile)
        return file.readText()
    }

    private class MapFlags : LocalAiFlagStore {
        val values = mutableMapOf<String, Boolean>()
        override fun readBoolean(key: String, fallback: Boolean): Boolean = values[key] ?: fallback
        override fun writeBoolean(key: String, value: Boolean) {
            values[key] = value
        }
    }

    @Test
    fun thePermanentLabelIsTheBriefsSentenceWordForWord() {
        assertEquals(
            "On-device model: runs on this phone, not your PC",
            LocalAiWords.PERMANENT_LABEL,
        )
        assertTrue(source("LocalAiScreen.kt").contains("LocalAiWords.PERMANENT_LABEL"))
    }

    @Test
    fun theDraftCanBeClearedWithoutLeavingTheScreen() {
        // Field test, 2026-11-13: the draft is `rememberSaveable`, so it
        // survives leaving the screen, and there was no way to throw a stale
        // or half-typed question away except killing the app. Clear is wired
        // to the draft's own state, not to the engine.
        assertEquals("Clear", LocalAiWords.CLEAR)
        val screen = source("LocalAiScreen.kt")
        assertTrue(
            "the Clear action must discard the draft:\n$screen",
            screen.contains("onClear = { draft = \"\" }"),
        )
        assertTrue("the composer must draw the Clear action", screen.contains("LocalAiWords.CLEAR"))
    }

    @Test
    fun leavingTheScreenFreesTheModel() {
        // The memory-saving rule that matters: the model is destroyed when the
        // Local AI screen leaves the composition. The five-minute idle window
        // is the rule INSIDE the screen; this is the one on the way out, and
        // `LocalAiControllerTest.closingTheScreenReleasesTheEngine` proves the
        // controller side of it.
        assertTrue(
            "the screen must destroy the engine when it leaves the composition",
            source("LocalAiScreen.kt").contains("onDispose { controller.close() }"),
        )
    }

    @Test
    fun theSwitchIsOffUntilTheOwnerTapsIt() {
        assertFalse(LocalAiSettings.DEFAULT_ENABLED)
        val settings = LocalAiSettings(MapFlags())
        assertFalse(settings.enabled)
        settings.setEnabled(true)
        assertTrue(settings.enabled)
        settings.setEnabled(false)
        assertFalse(settings.enabled)

        // The default state of the screen is the same answer.
        assertFalse(LocalAiState().switchOn)
        assertEquals(EngineState.OFF, LocalAiState().engine)
        // The real store reads Android's boolean with a false fallback.
        val prefs = source("LocalAiSettings.kt")
        assertTrue(prefs.contains("getBoolean(key, fallback)"))
        assertFalse(prefs.contains("getBoolean(key, true)"))
    }

    @Test
    fun theMoreMenuRowOpensTheScreenAndNeedsNoPc() {
        assertEquals(LocalAiWords.TITLE, MoreMenuWords.LOCAL_AI)
        assertEquals(LocalAiWords.MORE_DETAIL, MoreMenuWords.LOCAL_AI_DETAIL)
        assertTrue(
            "the screen must be a real destination",
            Screen.entries.any { it.name == "LOCAL_AI" },
        )
        // Appended last, because the saved back stack restores screens by name;
        // a screen inserted in the middle would restore as another.
        assertEquals(Screen.LOCAL_AI, Screen.values().last())
        assertTrue(moduleFile("app/src/main/java/com/jarvis/client/MainActivity.kt").contains("Screen.LOCAL_AI ->"))
        assertTrue(
            moduleFile("app/src/main/java/com/jarvis/client/MainActivity.kt")
                .contains("onOpenLocalAi = { nav.go(Screen.LOCAL_AI) }"),
        )
        assertTrue(
            moduleFile("app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt")
                .contains("actions.onOpenLocalAi()"),
        )
    }

    @Test
    fun noClassInitialiserLoadsTheNativeLibrary() {
        val native = source("LlamaNative.kt")
        assertFalse(
            "LlamaNative must never load the library; LlamaEngine.create does",
            native.contains("loadLibrary()") || native.contains("System.loadLibrary(\""),
        )
        val engine = source("LlamaEngine.kt")
        val loads = Regex(Regex.escape("System.loadLibrary(")).findAll(engine).count()
        assertEquals("exactly one load, inside create's injected loader", 1, loads)
        assertTrue(engine.contains("private val loadLibrary: () -> Unit = { System.loadLibrary(LIBRARY) }"))
    }

    @Test
    fun r8KeepsEveryJniName() {
        val rules = moduleFile("app/proguard-rules.pro")
        assertTrue(rules.contains("-keep class com.jarvis.client.localai.** { *; }"))
        assertTrue(rules.contains("Java_com_jarvis_client_localai_LlamaNative_nativeCreate"))
        assertTrue(rules.contains("TokenSink"))
    }

    @Test
    fun theImportIsAPickerAndSaysExactlyWhatToTap() {
        val screen = source("LocalAiScreen.kt")
        assertTrue(screen.contains("ActivityResultContracts.OpenDocument()"))
        assertTrue(screen.contains("picker.launch(arrayOf(\"*/*\"))"))
        val help = LocalAiWords.IMPORT_HELP
        assertTrue("the help must name the button", help.contains("Tap Import a model"))
        assertTrue("the help must name the picker", help.contains("file picker"))
        assertTrue("the help must name the confirming tap", help.contains("tap Open"))
    }

    @Test
    fun nothingInTheEnginePathCanReachTheNetworkOrTheToken() {
        val forbidden = listOf("http://", "https://", "OkHttp", "TokenStore", "X-Jarvis-Client", "pairing")
        for (file in sources.listFiles().orEmpty().filter { it.isFile && it.name.endsWith(".kt") }) {
            val text = file.readText()
            for (word in forbidden) {
                assertFalse("${file.name} must contain no $word", text.contains(word))
            }
        }
    }

    @Test
    fun speedIsMeasuredOrSaysNotMeasuredAndNeverInventsANumber() {
        assertEquals("Speed: not measured", LocalAiWords.speedLine(null))
        assertEquals("Speed: not measured", LocalAiWords.speedLine(Double.NaN))
        assertEquals("Speed: not measured", LocalAiWords.speedLine(0.0))
        assertTrue(LocalAiWords.speedLine(7.24).contains("7.2 tokens per second"))
        val stats = EngineStats(promptTokens = 10, generatedTokens = 20, generateMillis = 2_000)
        assertEquals(10.0, stats.tokensPerSecond!!, 0.0001)
        assertEquals(null, EngineStats(10, 0, 2_000).tokensPerSecond)
        assertEquals(null, EngineStats(10, 20, 0).tokensPerSecond)
    }

    @Test
    fun noDownloadIsOfferedAnywhere() {
        val words = source("LocalAiWords.kt")
        assertFalse("the screen must not offer a download button", words.contains("Download"))
        assertTrue(words.contains("Jarvis never downloads a model"))
        assertFalse(source("LocalAiScreen.kt").contains("Download"))
        assertFalse(source("LocalAiController.kt").contains("Download"))
    }

    @Test
    fun theEngineIsOnlyEverCreatedFromLoad() {
        val controller = source("LocalAiController.kt")
        val factoryCalls = Regex(Regex.escape("engineFactory()")).findAll(controller).count()
        assertEquals("one factory call, inside ensureEngine", 1, factoryCalls)
        assertTrue(controller.contains("private fun ensureEngine()"))
        // Turning the screen on must not call it; the only call site is load's
        // ensureEngine, inside the withContext block.
        assertTrue(controller.contains("when (val made = ensureEngine())"))
    }
}
