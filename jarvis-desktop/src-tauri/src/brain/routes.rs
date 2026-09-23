//! The Brain's read allowlist, and the trimmer that carries the server's own
//! words back to the UI.
//!
//! Split from the commands next door so the allowlist test — which guards the
//! boundary between "this window may read" and "this window may act" — can be
//! compiled and run without a Tauri app, a window or a network. A security
//! boundary whose test never executes is a comment.

/// The only endpoints the Brain window may read, by the name it asks for.
///
/// A window sends section names; this table turns them into paths. Adding a
/// pane means adding a line here, which is the point — the grant is auditable
/// by reading one array rather than by tracing what a URL parameter can hold.
const READ_ROUTES: &[(&str, &str)] = &[
    ("graph", "/api/graph"),
    ("status", "/api/status"),
    ("models", "/api/models"),
    ("compute", "/api/compute"),
    ("skills", "/api/skills"),
    ("jobs", "/api/jobs"),
    ("undo", "/api/undo"),
    ("ledger", "/api/ledger"),
    ("content_risk", "/api/content-risk"),
    ("watch", "/api/watch"),
    // A GET peek. Marking findings read is a POST on purpose — see
    // [`brain_watch_seen`].
    ("watch_report", "/api/watch/report"),
    ("memory", "/api/memory/status"),
    // `retire_cards=1`: the Brain labels feedback.patch's "stop using this
    // fact?" cards with their own two buttons ("Stop using this fact" /
    // "Keep using it"), so it asks for them. A backend without the patch
    // ignores the parameter.
    ("memory_pending", "/api/memory/pending?retire_cards=1"),
    // Every fact the store holds, retired ones included. A read: the pane
    // shows it, and each change is its own command below.
    ("memory_facts", "/api/memory/facts"),
    ("initiative", "/api/initiative"),
    ("attention", "/api/attention"),
    ("digest", "/api/digest"),
    ("config", "/api/config"),
];

pub(super) fn route_for(section: &str) -> Option<&'static str> {
    READ_ROUTES
        .iter()
        .find(|(name, _)| *name == section)
        .map(|(_, path)| *path)
}

/// The server's message, trimmed to something a toast can hold.
pub(super) fn first_line(body: &str) -> String {
    let text = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string))
        .unwrap_or_else(|| body.trim().to_string());
    if text.is_empty() {
        return String::new();
    }
    let one = text.lines().next().unwrap_or("").trim();
    let clipped: String = one.chars().take(200).collect();
    format!(": {clipped}")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The allowlist is the security boundary, so it is worth asserting rather
    /// than eyeballing: every route is a GET on this backend, and nothing that
    /// changes state is reachable through the read command.
    #[test]
    fn every_read_route_is_read_only() {
        // Paths the API defines as state-changing. If one of these ever appears
        // in READ_ROUTES, a window could trigger it with a read grant.
        const WRITES: &[&str] = &[
            "/api/approve",
            "/api/deny",
            "/api/chat",
            "/api/shutdown",
            "/api/undo/revert",
            "/api/jobs/cancel",
            "/api/holds/cancel",
            "/api/watch/add",
            "/api/watch/remove",
            "/api/watch/seen",
            "/api/skills/decide",
            "/api/models/install",
            "/api/models/switch",
            "/api/models/rollback",
            "/api/attention/mute",
            "/api/attention/unmute",
            "/api/digest/seen",
            "/api/memory/decide",
            "/api/memory/forget",
            "/api/memory/edit",
            "/api/memory/learning",
        ];
        for (section, path) in READ_ROUTES {
            assert!(
                !WRITES.contains(path),
                "`{section}` maps to {path}, which changes state"
            );
            assert!(path.starts_with("/api/"), "{section} -> {path}");
        }
    }

    #[test]
    fn section_names_are_unique_and_resolvable() {
        let mut seen = std::collections::HashSet::new();
        for (section, _) in READ_ROUTES {
            assert!(seen.insert(*section), "`{section}` is listed twice");
            assert!(route_for(section).is_some());
        }
        assert_eq!(route_for("../etc/passwd"), None);
        assert_eq!(route_for("/api/approve"), None);
        assert_eq!(route_for(""), None);
    }

    /// The server's own message has to survive into the error, because "already
    /// gone" and "not found" need different words on screen.
    #[test]
    fn the_servers_message_reaches_the_caller() {
        assert_eq!(
            first_line(r#"{"error":"that hold has already been released"}"#),
            ": that hold has already been released"
        );
        assert_eq!(first_line(""), "");
        assert_eq!(first_line("   "), "");
        // A non-JSON body is still worth showing.
        assert_eq!(first_line("Bad Gateway"), ": Bad Gateway");
        // Only the first line, and not an unbounded amount of it.
        let long = format!("{}\nsecond line", "x".repeat(400));
        let out = first_line(&long);
        assert!(!out.contains("second line"));
        assert!(out.chars().count() <= 202);
    }
}
