#!/usr/bin/env python3
"""Writes the phone's Galaxy-picture fixture from the desktop's own layout code.

    python3 tools/gen_galaxy_picture_cases.py            # write the fixture
    python3 tools/gen_galaxy_picture_cases.py --check    # compare only (exit 1 on drift)

WHY A GENERATOR, AND WHY IT RUNS NODE. The phone's picture is not a new picture:
it is the desktop's Galaxy (people and things, joined when one saved fact names
both - `galaxy-view.js`) drawn with the desktop's own deterministic flat layout,
`zen-ring` (`galaxy-presets.js`: the best-known name at the centre, the others on
an R=108 halo, growing outward at 24 pitch). Porting that algebra to Kotlin is
only honest if the port can be checked against the original, so this script runs
the REAL desktop modules (node imports the two `jarvis-desktop/src` files, the
same files the desktop tests run) and writes the positions, radii and links they
compute into the phone's test resources. `GalaxyPictureTest.kt` then builds the
same picture from the same entities with the Kotlin port and compares, so a
desktop layout change that the port has not followed fails there.

The desktop's `orderedEntities` caps at 240 names; the phone caps at 48 BEFORE
the links are worked out (a dropped name gets no dot, and a link only ever joins
dots that are drawn - the same rule `buildEntityGraph` states). The node script
below does exactly that, in the same order the app does it.

The three cases:

  * `names`    - the four-name fixture the phone tests already use, so the links
                 and the order can be read by eye;
  * `cap`      - 60 names (cap cuts to 48; 48 = centre + 32 halo + 15 first
                 outward ring), ties on fact count broken by the newest fact id;
  * `thirteen` - one fact naming thirteen names: a list, not a connection, so it
                 joins nothing (`MAX_NAMES_PER_FACT` = 12, both apps).

The file is generated, never edited: the `_comment` says so and `--check` fails
when it drifts from what the desktop code computes today.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract" / "galaxy-picture-cases.json"

KINDS = ["person", "pet", "place", "organisation", "project", "thing", None]


def case_names() -> dict:
    """The four names `PhoneGalaxyTest`/`EntitiesTest` already read."""
    return {
        "name": "names",
        "entities": [
            {"id": "1", "name": "Priya", "kind": "person", "fact_ids": [9, 7, 5, 3]},
            {"id": "2", "name": "Biscuit", "kind": "pet", "fact_ids": [8]},
            {"id": "3", "name": "Garage", "kind": "project", "fact_ids": [5, 3]},
            {"id": "4", "name": "Dan", "kind": "person", "fact_ids": [9, 12, 11, 5]},
        ],
    }


def case_cap() -> dict:
    """60 names of varying weight, with facts shared in groups of ten.

    The fact-count tie-break is exercised on purpose: names 2 and 8 have the
    same number of facts but different `max(fact_ids)`.
    """
    entities = []
    for i in range(1, 61):
        facts = [1000 + i, 500 + (i % 6)]
        for k in range(i % 4):
            facts.append(2000 + i * 10 + k)
        entities.append(
            {
                "id": str(i),
                "name": "Name %02d" % i,
                "kind": KINDS[(i - 1) % len(KINDS)],
                "fact_ids": facts,
            }
        )
    return {"name": "cap", "entities": entities}


def case_thirteen() -> dict:
    """Thirteen names in ONE fact: a list, and the desktop's rule joins nothing."""
    return {
        "name": "thirteen",
        "entities": [
            {"id": str(i), "name": "Many %02d" % i, "kind": "person", "fact_ids": [7000]}
            for i in range(1, 14)
        ],
    }


# The node program: import the desktop's REAL modules and run the phone's
# pipeline (rank, cap, link, lay out) with them. Written to stdin so no shell
# quoting is involved, and printing one JSON object so this script has no
# JavaScript of its own to keep in step.
NODE = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const root = process.cwd();
const view = await import(pathToFileURL(resolve(root, "jarvis-desktop/src/galaxy-view.js")));
const presets = await import(pathToFileURL(resolve(root, "jarvis-desktop/src/galaxy-presets.js")));
const cases = JSON.parse(readFileSync(0, "utf8"));

const MAX = 48;

function degree(nodes, links) {
  const deg = new Map(nodes.map((n) => [n.id, 0]));
  for (const l of links) {
    deg.set(l.source, (deg.get(l.source) || 0) + 1);
    deg.set(l.target, (deg.get(l.target) || 0) + 1);
  }
  return deg;
}

const out = [];
for (const c of cases) {
  // The same shape memory-entities.js hands the desktop: number ids, factIds.
  const entities = c.entities.map((e) => ({
    id: Number(e.id),
    name: e.name,
    kind: e.kind,
    factIds: e.fact_ids.map(Number),
  }));
  // 1. the desktop's cap order, then the phone's own cap - the SAME cut
  //    buildEntityGraph makes, before any link is worked out.
  const ranked = view.orderedEntities(entities);
  const kept = ranked.slice(0, MAX);
  // 2. the desktop's own node/link builder, over the kept names only.
  const graph = view.buildEntityGraph({ entities: kept });
  // 3. the desktop's own deterministic flat layout.
  const layout = presets.layoutZenRing(graph.nodes);
  const deg = degree(graph.nodes, graph.links);
  const nodes = graph.nodes.map((n, i) => {
    const weight = Array.isArray(n.factIds) ? n.factIds.length : 0;
    const d = deg.get(n.id) || 0;
    return {
      id: String(n.entityId),
      x: layout.nodes[i].x,
      y: layout.nodes[i].y,
      r: 3 + Math.min(9, Math.sqrt(weight * 2 + d)),
    };
  });
  const links = graph.links
    .map((l) => ({
      source: String(l.source.replace(/^e:/, "")),
      target: String(l.target.replace(/^e:/, "")),
      shared: l.shared,
    }))
    .sort((x, y) =>
      y.shared - x.shared
      || x.source.localeCompare(y.source)
      || x.target.localeCompare(y.target));
  out.push({
    name: c.name,
    entities: c.entities,
    ordered_ids: nodes.map((n) => n.id),
    nodes,
    links,
    total: c.entities.length,
  });
}
process.stdout.write(JSON.stringify(out, null, 2) + "\n");
"""


def build() -> dict:
    cases = [case_names(), case_cap(), case_thirteen()]
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", NODE],
        input=json.dumps(cases),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit("node could not run the desktop layout modules")
    computed = json.loads(proc.stdout)
    return {
        "_comment": (
            "Made by tools/gen_galaxy_picture_cases.py from the desktop's REAL "
            "jarvis-desktop/src/galaxy-view.js (orderedEntities, buildEntityGraph) "
            "and jarvis-desktop/src/galaxy-presets.js (layoutZenRing). Do not edit by hand."
        ),
        "_contract": (
            "Positions are the desktop's layout units; the phone's fit() scales "
            "them to its canvas. 48 is the phone's cap, applied before the links: "
            "a dropped name gets no dot and no link."
        ),
        "max_nodes": 48,
        "cases": computed,
    }


def main() -> int:
    fixture = build()
    text = json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"
    check = "--check" in sys.argv[1:]
    if check:
        if not OUT.exists():
            print("galaxy-picture fixture is missing: run python3 tools/gen_galaxy_picture_cases.py")
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(
                "galaxy-picture fixture has drifted from the desktop's layout code: "
                "run python3 tools/gen_galaxy_picture_cases.py"
            )
            return 1
        print("galaxy-picture fixture matches the desktop layout code")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("wrote %s (%d cases, %d bytes)" % (OUT.relative_to(ROOT), len(fixture["cases"]), len(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
