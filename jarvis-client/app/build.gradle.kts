plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.jarvis.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.jarvis.client"
        // 33, not 30: RuntimeShader/AGSL for the Nucleus face needs 33, and
        // taking 30 would mean a GLES fallback branch carried forever.
        minSdk = 33
        targetSdk = 36
        versionCode = 1
        versionName = "0.1-step0"

        // There was no instrumentation runner, so there was nowhere to put a
        // test that actually starts the app. That is the gap that let a crash
        // in onCreate ship green: the suite compiled the APK and ran unit
        // tests, and never once launched it.
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // The shared debug key, committed at the repository root. Without it AGP mints
    // ~/.android/debug.keystore per machine, and a CI runner is a fresh machine
    // every run - so each build was signed with a different certificate and
    // `adb install -r` over the previous one failed with
    // INSTALL_FAILED_UPDATE_INCOMPATIBLE. The only way through was `adb uninstall`,
    // which wipes the pairing secret, the auth token, the device id and anything
    // still queued offline.
    //
    // Guarded on existence rather than assumed: a checkout of this module alone,
    // without the repository around it, falls back to AGP's generated key and still
    // builds.
    signingConfigs {
        getByName("debug") {
            val shared = rootProject.file("../keystore/debug.keystore")
            if (shared.exists()) {
                storeFile = shared
                storePassword = "android"
                keyAlias = "androiddebugkey"
                keyPassword = "android"
            }
        }
    }

    buildTypes {
        debug { isMinifyEnabled = false }
        release {
            // Minify off and proguardFiles listed anyway advertises a shrink that
            // does not happen. This module has no serialization runtime and no
            // reflective entry points yet, so the rules file is genuinely empty of
            // anything load-bearing; when step 2 adds the SSE client and its models,
            // turn this on rather than adding keeps that nothing verifies.
            isMinifyEnabled = false
        }
    }

    testOptions {
        unitTests {
            // The pattern engine is pure maths over androidx Color, but a stray
            // android.* call in a transitive would otherwise throw "not mocked"
            // rather than returning something the test can assert on.
            isReturnDefaultValues = true
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
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    }
}

dependencies {
    // NOT the 2026.08.00 the brief pins. That BOM resolves Compose 1.12.0,
    // whose every artifact declares minCompileSdk 37, and CheckAarMetadata
    // enforces that as a hard error. §3 also forbids compiling against 37
    // because it is Beta, so the two requirements cannot both be met.
    //
    // Surveying the BOMs by the minCompileSdk in their own AAR metadata:
    // 1.12.x needs 37, everything from 1.11.3 back to 1.9.1 needs 35. Compose
    // never required 36, so 2026.06.00 is the newest BOM usable here.
    //
    // The brief gives a reason for compileSdk 36 and none for this particular
    // BOM, so the BOM is the constraint that yields.
    implementation(platform("androidx.compose:compose-bom:2026.06.00"))

    implementation("androidx.core:core-ktx:1.15.0")
    // 1.12.4, not 1.9.3. androidx.activity is not managed by the Compose BOM, so
    // that pin was real rather than decorative: resolving the graph in CI shows
    // core-ktx and lifecycle floating up to 1.16.0 and 2.9.4 on their own, while
    // activity stayed at a November 2024 release hosting a 2026 Compose runtime
    // under targetSdk 36 — where edge-to-edge enforcement changed and
    // MainActivity calls enableEdgeToEdge(). 1.12.4 is the last patch of the
    // generation contemporaneous with Compose 1.11.3; 1.13.0 is stable but newer
    // than the BOM, and 1.14.x is alpha.
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    // Used directly (LazyColumn, background, KeyboardOptions) rather than relied on
    // as a material3 transitive.
    implementation("androidx.compose.foundation:foundation")

    // The serialization compiler plugin is applied in build.gradle.kts but no
    // runtime was declared, so the first @Serializable anyone wrote would have
    // failed to resolve rather than working. Step 2's event models need it.
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    // The transport. OkHttp rather than Ktor because the SSE stream wants a
    // socket held open for an hour with no read timeout, and chat wants a
    // chunked body cancelled mid-flight to interrupt generation - both are
    // one-liners here.
    // A fingerprint instead of a tap for irreversible and outbound decisions -
    // the one item on the brief's list a browser genuinely cannot do.
    implementation("androidx.biometric:biometric:1.1.0")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okio:okio:3.6.0")

    testImplementation("junit:junit:4.13.2")

    // Deliberately just enough to launch the activity and read its lifecycle
    // state. No Compose test rule: the reactor runs an unbounded
    // withFrameNanos loop, and Compose's test clock treats a running animation
    // as "not idle", so a ComposeTestRule would sit waiting for a face that is
    // never going to stop. ActivityScenario has no such coupling.
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:core-ktx:1.6.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
