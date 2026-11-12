package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ProjectExplorer
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import kotlinx.serialization.json.jsonObject

/**
 * Mobile Project Explorer & Code Review Plate (inspired by Mobile-Harness).
 *
 * Lets developers inspect PC projects, repository maps, files, and tokens
 * directly from Android over the private mesh.
 */
@Composable
fun ProjectExplorerPlate(
    projectId: String = "default",
    onClose: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var targetProject by remember { mutableStateOf(projectId) }
    var filterQuery by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    var repoMap by remember { mutableStateOf<ProjectExplorer.RepoMap?>(null) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var selectedFile by remember { mutableStateOf<ProjectExplorer.FileEntry?>(null) }

    fun fetchMap() {
        val pid = targetProject.trim()
        if (pid.isBlank()) return
        isLoading = true
        errorMessage = null
        selectedFile = null
        scope.launch {
            val path = ProjectExplorer.mapPath(pid)
            when (val res = JarvisRuntime.api.getJson(path)) {
                is ApiResult.Success -> {
                    isLoading = false
                    runCatching {
                        val obj = JarvisJson.parseToJsonElement(res.value).jsonObject
                        repoMap = ProjectExplorer.parseMap(obj)
                    }.onFailure {
                        errorMessage = "Failed to parse repository map: ${it.message}"
                    }
                }
                is ApiResult.Failure -> {
                    isLoading = false
                    errorMessage = "Server error ${res.code}: ${res.error}"
                }
            }
        }
    }

    Section("Project explorer", "Mobile codebase inspector") {
        Plate {
            Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
                // Project input row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TextInput(
                        value = targetProject,
                        onValueChange = { targetProject = it },
                        modifier = Modifier.weight(1f),
                        placeholder = "Project ID (e.g. default)",
                    )
                    Gap(8.dp)
                    Primary(if (isLoading) "Loading..." else "Load Map", enabled = !isLoading, onClick = { fetchMap() })
                    if (onClose != null) {
                        Gap(4.dp)
                        Quiet("Close", onClick = onClose)
                    }
                }

                if (errorMessage != null) {
                    Gap(8.dp)
                    Text(errorMessage.orEmpty(), style = MaterialTheme.typography.bodySmall, color = chrome.badInk)
                }

                val current = repoMap
                if (current != null) {
                    Gap(8.dp)
                    // Summary row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "${current.folderName} (${current.filesSeen} files)",
                            style = MaterialTheme.typography.labelMedium,
                            color = chrome.textHi,
                        )
                        Pill("${current.files.size} mapped", color = chrome.okInk)
                    }

                    Gap(8.dp)
                    // Search Filter
                    TextInput(
                        value = filterQuery,
                        onValueChange = { filterQuery = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = "Filter files (e.g. .kt, .py, api)",
                    )

                    Gap(8.dp)
                    val filtered = current.files.filter {
                        filterQuery.isBlank() || it.path.contains(filterQuery, ignoreCase = true)
                    }

                    // File tree list
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(280.dp)
                            .background(chrome.cardMuted)
                            .padding(4.dp),
                    ) {
                        if (filtered.isEmpty()) {
                            Text("No files matching filter.", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                        } else {
                            LazyColumn(modifier = Modifier.fillMaxWidth()) {
                                items(filtered) { file ->
                                    val isSelected = selectedFile?.path == file.path
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .background(if (isSelected) chrome.cardOver else chrome.cardMuted)
                                            .clickable { selectedFile = file }
                                            .padding(vertical = 4.dp, horizontal = 6.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = file.path,
                                                style = MaterialTheme.typography.bodySmall.copy(fontSize = 12.sp),
                                                color = if (isSelected) chrome.okInk else chrome.textHi,
                                            )
                                            if (file.classes.isNotEmpty() || file.functions.isNotEmpty()) {
                                                val symbols = (file.classes + file.functions).take(3).joinToString(", ")
                                                Text(
                                                    text = symbols,
                                                    style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp),
                                                    color = chrome.textLo,
                                                )
                                            }
                                        }
                                        Text(
                                            text = "${file.lines} lines · ~${file.tokens} tok",
                                            style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp),
                                            color = chrome.textLo,
                                        )
                                    }
                                }
                            }
                        }
                    }

                    // Detail drawer for selected file
                    val active = selectedFile
                    if (active != null) {
                        Gap(8.dp)
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(chrome.cardOver)
                                .padding(8.dp),
                        ) {
                            Text("Selected File Details", style = MaterialTheme.typography.labelMedium, color = chrome.textHi)
                            Text(active.path, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                            Gap(4.dp)
                            if (active.classes.isNotEmpty()) {
                                Text("Classes: ${active.classes.joinToString(", ")}", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                            }
                            if (active.functions.isNotEmpty()) {
                                Text("Functions: ${active.functions.joinToString(", ")}", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                            }
                        }
                    }
                }
            }
        }
    }
}
