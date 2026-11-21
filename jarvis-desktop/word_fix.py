import io
p = "src/backend_self.rs"
s = io.open(p, encoding="utf-8").read()
old = '''            "MISMATCH: the {named}, but this HUD expects {desktop}. Finish the backend \\
             update - Settings, then Updates, and press Install (that updates both halves)."'''
new = '''            "MISMATCH: the {named}, but this HUD expects {desktop}. Finish the backend \\
             update - Settings, then Updates, and press Update everything there (that \\
             updates both halves)."'''
assert old in s, "sentence anchor"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("wording fixed")
