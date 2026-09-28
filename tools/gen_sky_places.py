#!/usr/bin/env python3
"""Write the list of towns Jarvis can find without going online.

"Show the sun and moon behind the animal" needs to know roughly where the
owner is. The owner types a town once on the PC (Settings -> Appearance);
the PC finds it in `backend/jarvis_sky_places.py` - this file's output, a
shipped module holding one long string - and keeps
only its latitude and longitude, rounded to 0.1 degree. Nothing is looked
up online, ever (CLAUDE.md rule 1: location is private).

The towns come from GeoNames (https://www.geonames.org), licensed under
Creative Commons Attribution 4.0 (CC BY 4.0), through the `geonamescache`
Python package (MIT), which carries GeoNames' "cities15000" table: every
place with at least 15,000 people. Kept here:
  * the United States, Canada, the United Kingdom, Ireland, Australia and
    New Zealand: every town of 15,000 or more;
  * everywhere else: every town of 50,000 or more, and every capital.
Each line: name, country code, region (a US state's name; empty elsewhere),
latitude and longitude (2 decimals - the PC rounds them to 1), and the
population (to break ties: "Portland" means the bigger one unless a state
is named).

    pip install geonamescache==3.0.2
    python3 tools/gen_sky_places.py          # rewrite backend/jarvis_sky_places.py
    python3 tools/gen_sky_places.py --check  # exit 1 if it is out of date

The file is committed; the owner's PC never needs geonamescache or a
network to use it. CI does not run this (it needs the package); run it by
hand when the list should change. THIRD-PARTY-NOTICES.txt credits GeoNames.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "jarvis_sky_places.py"
WIDE = {"US", "CA", "GB", "IE", "AU", "NZ"}
HEADER = ('"""jarvis_sky_places.py - the towns "Show the sun and moon behind the animal"\n'
          'can find without going online (jarvis_sky.py reads DATA; nothing else does).\n\n'
          'Data: GeoNames (https://www.geonames.org), licensed under Creative Commons\n'
          'Attribution 4.0 (CC BY 4.0), through geonamescache 3.0.2 (MIT). Made by\n'
          'tools/gen_sky_places.py - do not edit by hand. One town a line: name,\n'
          'country code, region (a US state; empty elsewhere), latitude, longitude,\n'
          'population, separated by tabs.\n"""\n\n'
          'DATA = """\\\n')


def render() -> str:
    import geonamescache
    gc = geonamescache.GeonamesCache()
    countries = gc.get_countries()
    states = {code: s["name"] for code, s in gc.get_us_states().items()}
    capitals = {(c.get("iso"), (c.get("capital") or "").casefold()) for c in countries.values()}
    rows = []
    for c in gc.get_cities().values():
        cc = c["countrycode"]
        pop = int(c.get("population") or 0)
        capital = (cc, c["name"].casefold()) in capitals
        if not (pop >= 50000 or (cc in WIDE and pop >= 15000) or capital):
            continue
        name = " ".join(str(c["name"]).split())
        if not name or "\t" in name or '"' in name or "\\" in name:
            continue
        region = states.get(c.get("admin1code") or "", "") if cc == "US" else ""
        rows.append((name, cc, region, round(float(c["latitude"]), 2), round(float(c["longitude"]), 2), pop))
    rows.sort(key=lambda r: (r[0].casefold(), -r[5], r[1], r[2]))
    body = "".join(f"{n}\t{cc}\t{rg}\t{la:.2f}\t{lo:.2f}\t{p}\n" for n, cc, rg, la, lo, p in rows)
    names = "".join(f"{code}\t{c['name']}\n" for code, c in sorted(countries.items())
                    if '"' not in c["name"] and "\\" not in c["name"])
    us = "".join(f"{code}\t{name}\n" for code, name in sorted(states.items()))
    return (HEADER + body + '"""\n\n# Country codes and names (GeoNames).\nCOUNTRIES = """\\\n' + names
            + '"""\n\n# US states: postal code and name (GeoNames).\nUS_STATES = """\\\n' + us + '"""\n')


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if have != text:
            print(f"{OUT.relative_to(ROOT)} is out of date - run python3 tools/gen_sky_places.py")
            return 1
        print("sky places: up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {text.split('COUNTRIES')[0].count(chr(10)) - 12} towns, {len(text.encode()) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
