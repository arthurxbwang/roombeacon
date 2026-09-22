plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "com.roombeacon.shell"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.roombeacon.shell"
        minSdk = 26
        targetSdk = 35
        versionCode = 7
        versionName = "0.6.0"
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        debug { applicationIdSuffix = ".debug"; versionNameSuffix = "-debug" }
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint { warningsAsErrors = true }
}
dependencies { testImplementation("junit:junit:4.13.2") }
