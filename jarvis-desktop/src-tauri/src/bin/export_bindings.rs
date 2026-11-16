//! Writes - or checks - `jarvis-desktop/src/bindings.js`, the ONE generated file
//! the Settings page imports for a Rust command.
//!
//! THE PILOT (2026-11-16): `set_hotkeys` only. The file is generated from the
//! Rust signature, so the page cannot quietly disagree with it about an
//! argument's name. The export itself lives in `jarvis_desktop_lib::hotkeys`
//! (`bindings_js`), because `collect_commands!` resolves the hidden macro that
//! `#[tauri::command]` plants beside the function, and that macro is not visible
//! from another crate.
//!
//! WHY THIS IS A BIN AND NOT A `#[test]`, measured the hard way. A test that so
//! much as names `tauri_specta::Builder::<tauri::Wry>` makes the test harness
//! binary import `TaskDialogIndirect` from `comctl32.dll`. Only the
//! COMMON-CONTROLS V6 assembly exports that function - the plain System32
//! `comctl32.dll` exports no `TaskDialog*` at all - and `tauri-build` embeds the
//! manifest that selects v6 through `cargo:rustc-link-arg-bins`, which reaches
//! BINS ONLY. So a test binary resolved the import against v5 and the loader
//! killed it before `main` with STATUS_ENTRYPOINT_NOT_FOUND (0xC0000139); the
//! whole `cargo test` suite could not run. A bin target gets the manifest, so
//! the exporter lives here. (Giving test targets their own copy of the manifest
//! is not possible from `build.rs`: `rustc-link-arg-tests` needs a `[[test]]`
//! target and this package has none, and the unqualified `rustc-link-arg` is
//! linked into the app's bin twice and fails with "duplicate resource".)
//!
//!   cargo run --bin export_bindings              write the file
//!   cargo run --bin export_bindings -- --check   fail if the committed file is stale
//!
//! Nothing in the app calls this, so none of it is reachable from the shipped
//! binary.
use std::path::{Path, PathBuf};

/// `jarvis-desktop/src/bindings.js`, worked out from `src-tauri/`.
fn destination() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../src/bindings.js")
}

fn main() {
    let check = std::env::args().skip(1).any(|a| a == "--check");
    let want = jarvis_desktop_lib::hotkeys::bindings_js();
    let out = destination();

    if !check {
        std::fs::write(&out, &want).expect("writing the bindings");
        println!("wrote {}", out.display());
        return;
    }

    let got = std::fs::read_to_string(&out).unwrap_or_default();
    if got == want {
        println!("{} is current", out.display());
        return;
    }
    eprintln!(
        "{} is STALE: it does not match what the Rust command exports.\n\
         Run `cargo run --bin export_bindings` from jarvis-desktop/src-tauri, then \n\
         re-run the bindings typecheck (npm run typecheck:bindings in jarvis-desktop).",
        out.display()
    );
    std::process::exit(1);
}
