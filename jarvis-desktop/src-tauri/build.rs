fn main() {
    // Generates `src-tauri/gen/schemas/*` (the capability schemas referenced by
    // `capabilities/default.json`), embeds the Windows resource/manifest, and
    // makes `tauri::generate_context!()` resolvable at compile time.
    tauri_build::build();
}
