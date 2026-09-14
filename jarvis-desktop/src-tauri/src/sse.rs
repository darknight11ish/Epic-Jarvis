//! The Server-Sent Events wire format: bytes in, frames out.
//!
//! Split from [`crate::stream`] so it depends on nothing but `serde_json`, and
//! can therefore be built and run on a machine with no Windows toolchain and no
//! GTK — which is the only way the parser gets tested at all before it meets a
//! real backend. `stream.rs` owns the socket; this file owns the grammar.
//!
//! The format is small enough to look trivial and has three details that are
//! not: a line beginning with `:` is a comment and never a field (that is what
//! `: keepalive` is), a field value has exactly *one* optional leading space
//! removed rather than being trimmed, and `data:` may appear more than once in
//! a frame, in which case the values are joined with newlines.

/// One SSE frame under construction.
#[derive(Default)]
pub struct Frame {
    id: Option<u64>,
    name: Option<String>,
    pub(crate) data: Vec<String>,
}

/// A complete SSE event.
pub struct Event {
    pub id: Option<u64>,
    pub name: String,
    pub data: serde_json::Value,
}

impl Frame {
    /// Feeds one line in and returns an event when the frame closes.
    ///
    /// The wire format is line-oriented and tiny, but the two cases that are
    /// easy to get wrong are both here: a line starting with `:` is a comment
    /// (that is what `: keepalive` is) and must not be parsed as a field, and
    /// a field's value has exactly one optional leading space stripped — not
    /// trimmed, because SSE data can legitimately begin with whitespace.
    pub fn feed(&mut self, line: &str) -> Option<Event> {
        if line.is_empty() {
            if self.data.is_empty() && self.name.is_none() {
                // A blank line with nothing before it: the separator after a
                // bare `retry:` line, or a keepalive's terminator.
                return None;
            }
            let name = self.name.take().unwrap_or_else(|| "message".to_string());
            let raw = std::mem::take(&mut self.data).join("\n");
            let id = self.id.take();
            let data = serde_json::from_str(&raw).unwrap_or(serde_json::Value::Null);
            return Some(Event { id, name, data });
        }
        if line.starts_with(':') {
            return None; // keepalive, or any other comment
        }
        let (field, value) = match line.split_once(':') {
            Some((field, value)) => (field, value.strip_prefix(' ').unwrap_or(value)),
            None => (line, ""),
        };
        match field {
            "id" => self.id = value.trim().parse::<u64>().ok(),
            "event" => self.name = Some(value.trim().to_string()),
            "data" => self.data.push(value.to_string()),
            // `retry:` is advice for a browser's EventSource, which reconnects
            // for itself. This loop's backoff is its own; ignoring the field is
            // the same thing every non-browser client does.
            _ => {}
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn drain(lines: &[&str]) -> Vec<(Option<u64>, String, serde_json::Value)> {
        let mut frame = Frame::default();
        let mut out = Vec::new();
        for line in lines {
            if let Some(event) = frame.feed(line) {
                out.push((event.id, event.name, event.data));
            }
        }
        out
    }

    /// The exact bytes `jarvis_events.stream()` writes first, keepalive and all.
    #[test]
    fn parses_the_servers_own_frames() {
        let events = drain(&[
            "retry: 3000",
            "",
            "id: 413",
            "event: hello",
            r#"data: {"resumed_from":412,"stale":false,"latest":413,"retry_ms":3000}"#,
            "",
            "id: 414",
            "event: approval",
            r#"data: {"key":"approvals","value":["a1","a2"],"count":2}"#,
            "",
            ": keepalive",
            "",
        ]);

        assert_eq!(events.len(), 2, "retry and keepalive are not events");
        assert_eq!(events[0].0, Some(413));
        assert_eq!(events[0].1, "hello");
        assert_eq!(events[0].2["stale"], serde_json::json!(false));
        assert_eq!(events[1].0, Some(414));
        assert_eq!(events[1].1, "approval");
        assert_eq!(events[1].2["count"], serde_json::json!(2));
    }

    /// A `data:` value keeps everything after one optional space. Trimming it
    /// would corrupt any payload that legitimately starts with whitespace.
    #[test]
    fn keeps_leading_whitespace_beyond_the_first_space() {
        let events = drain(&["event: note", "data:   padded", ""]);
        assert_eq!(events.len(), 1);
        // Unparseable as JSON, which is Null — the point here is the field
        // parse, so read it back off a frame instead.
        let mut frame = Frame::default();
        frame.feed("data:   padded");
        assert_eq!(frame.data, vec!["  padded".to_string()]);
    }

    /// Multi-line `data:` is joined with newlines, per the SSE spec.
    #[test]
    fn joins_multi_line_data() {
        let mut frame = Frame::default();
        frame.feed("event: chunk");
        frame.feed("data: {\"a\":");
        frame.feed("data: 1}");
        let event = frame.feed("").expect("blank line closes the frame");
        assert_eq!(event.data["a"], serde_json::json!(1));
    }

    /// An event with no `event:` field is `message`, and a keepalive on its own
    /// closes nothing.
    #[test]
    fn defaults_to_message_and_ignores_bare_comments() {
        assert!(drain(&[": keepalive", "", ": keepalive", ""]).is_empty());
        let events = drain(&["data: {}", ""]);
        assert_eq!(events[0].1, "message");
    }
}
