import json, subprocess, sys, os
repo = os.getcwd()
def show(ref):
    return json.loads(subprocess.check_output(["git","show",ref+":features/features.json"], cwd=repo).decode("utf-8"))
base = show("66d114038")          # merge base
ours = show("HEAD")               # branch side (bundle)
main = show("origin/main")        # main side (#1053 gates etc.)
assert isinstance(base,list) and isinstance(ours,list) and isinstance(main,list), (type(base),type(ours),type(main))
by = {r["id"]: r for r in base}; oy = {r["id"]: r for r in ours}; my = {r["id"]: r for r in main}
merged = []
for r in main:
    rid = r["id"]
    if rid not in oy:
        merged.append(r); continue
    o = oy[rid]; b = by.get(rid, {})
    row = dict(r)
    for k, v in o.items():
        if k not in b or b.get(k) != v:
            row[k] = v
    merged.append(row)
for r in ours:
    if r["id"] not in my:
        merged.append(r)
# sanity: same row count as ours and main, unique ids
ids = [r["id"] for r in merged]
assert len(ids) == len(set(ids)), "duplicate ids"
print("merged rows:", len(merged), "ours:", len(ours), "main:", len(main))
print("gate rows preserved:", sum(1 for r in merged if "gate" in r))
print("lesson rows preserved:", sum(1 for r in merged if "lesson_id" in r))
out = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
for p in ["features/features.json","jarvis-desktop/src/features.json","jarvis-client/app/src/main/assets/features.json"]:
    open(p,"w",encoding="utf-8",newline="\n").write(out)
    print("wrote", p, len(out), "bytes")
