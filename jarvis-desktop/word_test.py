import io
p = "src/backend_self.rs"
s = io.open(p, encoding="utf-8").read()
old = '''        assert!(sentence.contains("0.2.9"));
        assert!(sentence.contains("0.3.0"));
        assert!(sentence.contains("Install"), "{sentence}");
    }'''
new = '''        assert!(sentence.contains("0.2.9"));
        assert!(sentence.contains("0.3.0"));
        // MEASURED 2026-11-20: this used to say "press Install" and the Updates
        // page has no Install button on that path - the backend half is updated
        // by "Update everything" (the desktop half's own button says Install).
        // The owner read the instruction and could not follow it.
        assert!(sentence.contains("Update everything"), "{sentence}");
        assert!(!sentence.contains("press Install"), "{sentence}");
    }'''
assert old in s
io.open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
print("test updated")
