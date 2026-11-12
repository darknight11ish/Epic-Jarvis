package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ProjectExplorer
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProjectExplorerTest {

    @Test
    fun mapPathConstructsValidEndpoint() {
        assertEquals("/api/projects/my-proj/map", ProjectExplorer.mapPath("my-proj"))
        assertEquals("/api/projects/p123/map?q=test%20query", ProjectExplorer.mapPath("p123", "test query"))
        assertEquals("/api/projects/p123/map", ProjectExplorer.mapPath("p123", "   "))
    }

    @Test
    fun parseMapExtractsRepositoryDetailsAndFiles() {
        val raw = """
            {
              "ok": true,
              "available": true,
              "folder": {
                "name": "epic-jarvis",
                "path": "/workspace/wise-tesla"
              },
              "question": "where is the route registered",
              "budget": 2000,
              "files_seen": 25,
              "map": "summary of the repository",
              "files": [
                {
                  "path": "backend/jarvis_quick.py",
                  "tokens": 420,
                  "lines": 1200,
                  "classes": ["Intent", "Result"],
                  "functions": ["match", "normalize_spoken_command"]
                },
                {
                  "path": "jarvis-client/app/src/main/java/com/jarvis/client/data/Security.kt",
                  "tokens": 150,
                  "lines": 250,
                  "classes": ["Security", "RelockAfter"],
                  "functions": []
                }
              ]
            }
        """.trimIndent()

        val obj = JarvisJson.parseToJsonElement(raw).jsonObject
        val map = ProjectExplorer.parseMap(obj)

        assertTrue(map.ok)
        assertEquals("epic-jarvis", map.folderName)
        assertEquals("/workspace/wise-tesla", map.folderPath)
        assertEquals(25, map.filesSeen)
        assertEquals(2, map.files.size)

        val first = map.files[0]
        assertEquals("backend/jarvis_quick.py", first.path)
        assertEquals(420, first.tokens)
        assertEquals(1200, first.lines)
        assertEquals(listOf("Intent", "Result"), first.classes)
        assertEquals(listOf("match", "normalize_spoken_command"), first.functions)

        val second = map.files[1]
        assertEquals("jarvis-client/app/src/main/java/com/jarvis/client/data/Security.kt", second.path)
        assertEquals(150, second.tokens)
        assertEquals(250, second.lines)
        assertEquals(listOf("Security", "RelockAfter"), second.classes)
        assertTrue(second.functions.isEmpty())
    }

    @Test
    fun parseMapHandlesEmptyOrMalformedJsonSafely() {
        val raw = "{}"
        val obj = JarvisJson.parseToJsonElement(raw).jsonObject
        val map = ProjectExplorer.parseMap(obj)
        assertFalse(map.ok)
        assertEquals("", map.folderName)
        assertEquals(0, map.filesSeen)
        assertTrue(map.files.isEmpty())
    }
}
