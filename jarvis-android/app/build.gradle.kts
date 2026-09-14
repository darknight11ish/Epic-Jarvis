import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.jarvis.assistant"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jarvis.assistant"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ""
        }
        release {
            // Shrinking is on, so proguard-rules.pro is actually exercised. It was
            // listed here while isMinifyEnabled was false, which meant the
            // kotlinx-serialization keeps and the OkHttp -dontwarns in it had never
            // once been applied — the release block advertised a shrink it did not
            // do, and the rules would have been validated for the first time on the
            // day someone turned it on.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.animation:animation")
    implementation("androidx.compose.material3:material3")
    // Declared, not inherited. LazyColumn, background and KeyboardOptions are used
    // directly throughout the UI and arrive only as an `api` transitive of
    // material3; that compiles today and stops compiling silently if material3
    // ever narrows what it exposes.
    implementation("androidx.compose.foundation:foundation")

    implementation("androidx.glance:glance:1.1.1")
    implementation("androidx.glance:glance-appwidget:1.1.1")
    implementation("androidx.glance:glance-material3:1.1.1")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    // Same reasoning: JarvisWebSocketManager imports okio.ByteString directly.
    implementation("com.squareup.okio:okio:3.6.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
}
