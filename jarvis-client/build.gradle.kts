// Versions verified against the registries on 13 Sep 2026, not inferred:
//   AGP 9.4.0            gradle-9.4.0.pom -> 200 on Google Maven
//   Kotlin 2.4.20        current release on Maven Central
//   Compose BOM 2026.08.00  exists; pins androidx.compose.foundation 1.12.0
plugins {
    id("com.android.application") version "9.4.0" apply false
    id("org.jetbrains.kotlin.android") version "2.4.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.4.20" apply false
}
