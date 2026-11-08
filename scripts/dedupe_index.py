#!/usr/bin/env python3
"""One-time fix-up: de-duplicate the existing index/ in place, without
rescanning the raw archive.

build_index.py now dedupes during its scan (feeds can file the same game
twice under different ids, and a game can appear in either team's folder).
This script applies the same rule to already-built index files and rebuilds
the season shards, per-team schedule files, and meta counts.

Equal game ids across folders are different games (ids are client-local);
the dedupe rule is identical matchup/date/scores/venue/periods.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import (  # noqa: E402
    INDEX, ROOT, SEASON_RE, dedupe_records, season_divisions, write_json)

SKIP = {"index", "scripts", "data", "site", "reports"}


def main():
    manifest_by_id = {t["ncaa_id"]: t for t in
                      json.load(open(ROOT / "data" / "teams.json"))}
    per_team = defaultdict(list)
    season_meta = {}
    for season_dir in sorted((INDEX / "seasons").iterdir()):
        if not SEASON_RE.match(season_dir.name):
            continue
        fp = season_dir / "games.json"
        if not fp.exists():
            continue
        records = json.load(open(fp))["games"]
        records, merged = dedupe_records(records)
        shards = season_divisions(records, manifest_by_id)
        write_json(fp, {"season": season_dir.name, "games": records})
        for shard, recs in shards.items():
            if recs:
                write_json(season_dir / (shard + ".json"),
                           {"season": season_dir.name, "division": shard, "games": recs})
            elif (season_dir / (shard + ".json")).exists():
                (season_dir / (shard + ".json")).unlink()
        for r in records:
            for tid in {r["h"], r["v"]}:
                if tid is not None:
                    per_team[tid].append(r)
        season_meta[season_dir.name] = {
            "games": len(records),
            "d1": len(shards["d1"]), "d2": len(shards["d2"]),
            "d3": len(shards["d3"]), "x": len(shards["x"]),
        }
        print("{}: {} games ({} duplicate filings merged)".format(
            season_dir.name, len(records), merged), flush=True)

    n_teams = 0
    for tid, recs in sorted(per_team.items()):
        recs.sort(key=lambda r: (r["d8"] or "", r["id"]))
        write_json(INDEX / "teams" / str(tid) / "games.json",
                   {"team_id": tid, "games": recs})
        n_teams += 1

    meta_file = INDEX / "meta.json"
    meta = json.load(open(meta_file))
    total = sum(m["games"] for m in season_meta.values())
    meta["total_games"] = total
    meta["seasons"] = dict(sorted(season_meta.items(), reverse=True))
    write_json(meta_file, meta)
    print("rebuilt {} team schedule files; total games across all seasons: {}".format(
        n_teams, total))


if __name__ == "__main__":
    main()
