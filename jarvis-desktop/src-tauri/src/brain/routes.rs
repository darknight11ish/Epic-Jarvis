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
///
/// NOT `/api/graph` (removed 2026-09-28, privacy finding B1 of
/// docs/RESEARCH-AUDIT-2026-09-28.md section 8.3): the old Galaxy drew it,
/// and its "fact" dots could carry a fact's words while "Windows Hello for
/// memory lists" said every memory list was hidden - `graph` was never on
/// lock/rules.rs's private list. Galaxy is now drawn from
/// `memory_entities`, which is. The test below keeps it out, and keeps every
/// memory list here on the private list.
const READ_ROUTES: &[(&str, &str)] = &[
    ("status", "/api/status"),
    ("models", "/api/models"),
    ("compute", "/api/compute"),
    ("skills", "/api/skills"),
    ("jobs", "/api/jobs"),
    ("undo", "/api/undo"),
    // "Activity" (ease-of-use audit, 2026-09-27, row 11): past approvals,
    // read-only. The SAME route [`crate::stream`]'s own polling reads for
    // the live queue - `{"available", "pending", "history"}` - asked for
    // again here so the Brain window can show the `history` half of it,
    // which that polling loop reads and discards on purpose (it must never
    // let an already-decided row be mistaken for a waiting one). One more
    // GET to an idempotent, already-classified route; nothing here decides
    // anything, so it needs no write command of its own.
    ("gate_history", "/api/pending"),
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
    // `sleep_offer=1`: the Brain shows the daily overnight-tidy card, so it
    // asks for it. The server hands that card out once a day, to the first
    // read that asks - the HUD page does not ask, so it no longer uses the
    // day's card up (memory-pane.patch).
    // `merge_cards=1`: the Brain labels memory-entities.patch's "are these
    // the same?" cards with their own two answers ("Yes, the same" / "No,
    // keep them apart"), so it asks for them. The phone does not: it shows
    // no people-and-things layer (ARCHITECTURE.md section 8).
    (
        "memory_pending",
        "/api/memory/pending?retire_cards=1&sleep_offer=1&merge_cards=1",
    ),
    // Every fact the store holds, retired ones included. A read: the pane
    // shows it, and each change is its own command below.
    ("memory_facts", "/api/memory/facts"),
    // The people and things facts are linked to, and the ids of their
    // facts - the names under each fact and "About <name>"
    // (memory-entities.patch). A read; hidden with the other memory lists
    // (lock/rules.rs PRIVATE_LISTS).
    ("memory_entities", "/api/memory/entities"),
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
            "/api/memory/erase",
            "/api/memory/edit",
            "/api/memory/learning",
            "/api/memory/learning/auto",
            "/api/memory/learning/sensitive",
            // "Always keep in mind": its POST pins a fact. Read through its
            // own command (brain/profile.rs), never through this list.
            "/api/memory/profile",
            // "Between us": its POST tags a fact. Read through its own
            // command (brain/shared.rs), never through this list.
            "/api/memory/shared",
        ];
        for (section, path) in READ_ROUTES {
            assert!(
                !WRITES.contains(path),
                "`{section}` maps to {path}, which changes state"
            );
            assert!(path.starts_with("/api/"), "{section} -> {path}");
        }
    }

    /// Privacy finding B1 (2026-09-28): the Brain cannot read the old graph
    /// at all, and every memory list it CAN read comes back without its
    /// entries while "Windows Hello for memory lists" hides them. A new
    /// memory route added here without a line in lock/rules.rs PRIVATE_LISTS
    /// fails this test instead of quietly showing memory under the lock.
    #[test]
    fn the_graph_is_not_readable_and_every_memory_list_is_private() {
        assert_eq!(route_for("graph"), None);
        assert!(READ_ROUTES
            .iter()
            .all(|(_, p)| !p.starts_with("/api/graph")));
        // The counts ("memory" -> /api/memory/status) are numbers, not memory.
        const NOT_A_LIST: &[&str] = &["/api/memory/status"];
        // Each memory route answers with its OWN list (facts, pending or
        // entities), so each is given only that one - a body carrying all
        // three would make the pending route "leak" facts it never sends.
        // A memory section this test does not know gets all three, and fails
        // unless it is on PRIVATE_LISTS: the point of the test.
        let body_for = |section: &str| match section {
            "memory_facts" => {
                serde_json::json!({"facts": [{"id": 1, "text": "Owner's sister is called Priya"}]})
            }
            "memory_pending" => {
                serde_json::json!({"pending": [{"id": 2, "text": "Owner's sister Priya likes jazz"}]})
            }
            "memory_entities" => serde_json::json!({"entities": [{"id": 3, "name": "Priya"}]}),
            _ => serde_json::json!({
                "facts": [{"id": 1, "text": "Owner's sister is called Priya"}],
                "pending": [{"id": 2, "text": "Owner likes jazz"}],
                "entities": [{"id": 3, "name": "Priya"}],
            }),
        };
        for (section, path) in READ_ROUTES {
            let route = path.split('?').next().unwrap_or(path);
            if !route.starts_with("/api/memory/") || NOT_A_LIST.contains(&route) {
                continue;
            }
            let hidden = crate::lock::redact_private(section, body_for(section));
            assert_eq!(
                hidden["hidden"], true,
                "`{section}` ({path}) is memory but is not on lock/rules.rs PRIVATE_LISTS"
            );
            assert!(!hidden.to_string().contains("Priya"), "{section}: {hidden}");
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
