// Prevents an extra console window from appearing next to the app in Windows
// release builds. Debug builds keep the console so `println!` output from the
// hotkey/tray/capture paths stays visible while developing.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    jarvis_desktop_lib::run();
}
