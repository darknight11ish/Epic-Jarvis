const fs = require("fs");
const src = fs.readFileSync("src/critters-gen.js", "utf8");
for (const id of ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]) {
  const m = src.match(new RegExp(id + ': "((?:[^"\\\\]|\\\\.)*)"'));
  if (!m) { console.log(id, "no match"); continue; }
  const s = m[1].replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  const lines = s.split("\n").filter((l) => /CAM_TARGET|CAM_DIST|BOUND_R/.test(l));
  console.log("== " + id);
  for (const l of lines) console.log("   " + l.trim().slice(0, 160));
}
