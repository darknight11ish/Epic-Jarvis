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
    implementation("androidx.activity:activity-compose:1.9.3")
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

    testImplementation("junit:junit:4.13.2")
}
