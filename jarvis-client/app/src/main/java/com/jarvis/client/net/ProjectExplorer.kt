package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Mobile Project Explorer client parser (inspired by Mobile-Harness repository inspection).
 *
 * Reads project repository maps and file trees from `GET /api/projects/{id}/map`.
 * Read-only under Rule 4: displays file hierarchy, signatures, token counts, and lines.
 */
object ProjectExplorer {

    data class FileEntry(
        val path: String,
        val tokens: Int,
        val lines: Int,
        val classes: List<String>,
        val functions: List<String>,
    )

    data class RepoMap(
        val ok: Boolean,
        val folderName: String,
        val folderPath: String,
        val filesSeen: Int,
        val files: List<FileEntry>,
        val summaryMap: String,
    )

    fun mapPath(projectId: String, question: String = ""): String {
        val q = if (question.isNotBlank()) {
            val encoded = java.net.URLEncoder.encode(question.trim(), "UTF-8").replace("+", "%20")
            "?q=$encoded"
        } else ""
        return "/api/projects/$projectId/map$q"
    }

    fun parseMap(obj: JsonObject): RepoMap {
        val ok = obj["ok"]?.jsonPrimitive?.content?.toBooleanStrictOrNull() ?: false
        val folder = obj["folder"] as? JsonObject
        val folderName = folder?.get("name")?.jsonPrimitive?.content ?: ""
        val folderPath = folder?.get("path")?.jsonPrimitive?.content ?: ""
        val filesSeen = obj["files_seen"]?.jsonPrimitive?.intOrNull ?: 0
        val summaryMap = obj["map"]?.jsonPrimitive?.content ?: ""

        val rawFiles = obj["files"] as? JsonArray ?: JsonArray(emptyList())
        val files = rawFiles.mapNotNull { element ->
            val f = element as? JsonObject ?: return@mapNotNull null
            val path = f["path"]?.jsonPrimitive?.content ?: return@mapNotNull null
            val tokens = f["tokens"]?.jsonPrimitive?.intOrNull ?: 0
            val lines = f["lines"]?.jsonPrimitive?.intOrNull ?: 0
            val classes = (f["classes"] as? JsonArray)?.mapNotNull { (it as? JsonObject)?.get("name")?.jsonPrimitive?.content ?: it.jsonPrimitive.content } ?: emptyList()
            val functions = (f["functions"] as? JsonArray)?.mapNotNull { (it as? JsonObject)?.get("name")?.jsonPrimitive?.content ?: it.jsonPrimitive.content } ?: emptyList()
            FileEntry(path, tokens, lines, classes, functions)
        }

        return RepoMap(
            ok = ok,
            folderName = folderName,
            folderPath = folderPath,
            filesSeen = filesSeen,
            files = files,
            summaryMap = summaryMap,
        )
    }
}
