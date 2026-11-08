#!/usr/bin/env python3
"""Verify every team directory in the archive resolves against data/teams.json.

Reports:
- directories whose ncaa_id is missing from the manifest
- duplicate ncaa_id directories (same team filed twice)
- manifest entries with no directory (teams not yet collected)
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR_RE = re.compile(r"^(\d+)-.+$")


def main() -> None:
    manifest = {t["ncaa_id"]: t for t in json.load(open(ROOT / "data" / "teams.json"))}

    dirs: dict[int, str] = {}
    unmatched_dirs = []
    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        m = DIR_RE.match(p.name)
        if not m:
            unmatched_dirs.append(p.name)
            continue
        ncaa_id = int(m.group(1))
        if ncaa_id in dirs:
            print(f"DUPLICATE ncaa_id {ncaa_id}: {dirs[ncaa_id]} and {p.name}")
        dirs[ncaa_id] = p.name

    missing = sorted(n for n in dirs if n not in manifest)
    not_collected = sorted(k for k in manifest if k not in dirs)

    print(f"directories: {len(dirs)}  manifest entries: {len(manifest)}")
    if unmatched_dirs:
        print(f"\ndirectories not matching 'id-slug' pattern: {unmatched_dirs}")
    if missing:
        print(f"\ndirs missing from manifest ({len(missing)}):")
        for n in missing:
            print(f"  {n}: {dirs[n]}")
    if not_collected:
        print(f"\nmanifest teams with no directory ({len(not_collected)}):")
        for n in not_collected:
            print(f"  {n}: {manifest[n]['team']} ({manifest[n]['division']})")
    if not (missing or not_collected or unmatched_dirs):
        print("OK: all directories resolve to manifest entries")


if __name__ == "__main__":
    main()
