import pathlib
import subprocess

wt = pathlib.Path(r"C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\.dsh-scratch\wt-secret-wire")
test = wt / "backend" / "test_reconcile_live_backend.py"

# 1. Take main's version of the test file.
subprocess.run(["git", "checkout", "--ours", "--", str(test)], cwd=wt, check=True)
tt = test.read_text(encoding="utf-8")

# 2. Pull our two test functions + helper out of our commit's version.
ours = subprocess.run(
    ["git", "show", "373d2fea4:backend/test_reconcile_live_backend.py"],
    cwd=wt, check=True, capture_output=True, text=True).stdout
start = ours.index("def _secret_handoff_show(")
end = ours.rindex("\ndef main():")
block = ours[start:end].rstrip() + "\n"

# 3. Insert them before the real main().
marker = "\ndef main():"
pos = tt.rindex(marker)
tt = tt[:pos] + "\n" + block + tt[pos:]

# 4. Register the two tests next to the other delta tests.
old_reg = "               t_an_unknown_delta_is_refused_before_writing,\n"
new_reg = (old_reg
           + "               t_the_secret_handoff_delta_is_planned_and_idempotent,\n"
           + "               t_a_missing_or_duplicated_secret_handoff_anchor_is_refused,\n")
assert old_reg in tt, "registration anchor not found in main's test file"
tt = tt.replace(old_reg, new_reg, 1)
test.write_text(tt, encoding="utf-8", newline="\n")
print("test file resolved: main's private-chat tests kept, our two tests re-added")
