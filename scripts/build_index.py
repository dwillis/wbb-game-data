#!/usr/bin/env python3
"""Build a searchable index of game metadata from the raw archive.

The archive keeps each game under the HOME team's directory only:
    {ncaa_id}-{slug}/{season}/{game_id}.json
so the builder resolves the visiting team by name against three sources, in order:
  1. data/teams.json          manifest of all NCAA teams (stats_name / team)
  2. data/learned_names.json  API names/abbrevs -> ncaa_id learned from home teams
  3. data/name_aliases.json   manual aliases for whatever is left

Learned entries map the API's raw team names (e.g. "Missouri St.") and Id
abbreviations (e.g. "MOST") to ncaa_ids; names that map to two different ids
are marked ambiguous (null) and are not used for resolution.

Outputs (written under index/):
  seasons/{season}/games.json       all games in a season
  seasons/{season}/d1|d2|d3.json    per-division shards (by home team's division)
  teams/{ncaa_id}/games.json        one team's all-seasons schedule
  unresolved.json                   visitor names that could not be matched
  meta.json                         counts per season

Usage:
  build_index.py                     full scan of every season
  build_index.py --season 2025-26    rescan one season, merging into existing output
  build_index.py --since <git-ref>   rescan seasons touched since a git ref
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index"
SKIP_DIRS = {"index", "scripts", "data", "site", "reports"}
DIR_RE = re.compile(r"^(\d+)-.+$")
SEASON_RE = re.compile(r"^\d{4}-\d{2}$")
NONWORD = re.compile(r"[^a-z0-9]+")
DIV_SHARD = {"I": "d1", "II": "d2", "III": "d3"}


TOKEN = re.compile(r"[a-z0-9]+")


def norm(name):
    return NONWORD.sub("", (name or "").lower())


def tokens(name):
    return TOKEN.findall((name or "").lower())


class Resolver:
    """Resolves API team names/abbrevs to ncaa_ids; learns from home-team dirs."""

    def __init__(self, manifest):
        self.manifest_by_id = {t["ncaa_id"]: t for t in manifest}
        # high-confidence: unambiguous manifest names
        counts = Counter(norm(t.get("stats_name") or t["team"]) for t in manifest)
        self.static = {}
        for t in manifest:
            n = norm(t.get("stats_name") or t["team"])
            if counts[n] == 1:
                self.static[n] = t["ncaa_id"]
        self.learned, self.ambiguous = self._load_learned()
        self.aliases = self._load_aliases()
        self._fuzzy_src = self._fuzzy_token_index()
        self.new_learned = {}        # key -> set of ids seen this run
        self.resolved_counts = Counter()
        self.unresolved = Counter()

    def _load_learned(self):
        path = ROOT / "data" / "learned_names.json"
        if path.exists():
            d = json.load(open(path))
            return d.get("names", {}), d.get("ambiguous", [])
        return {}, []

    def _load_aliases(self):
        path = ROOT / "data" / "name_aliases.json"
        return {norm(k): v for k, v in json.load(open(path)).items()} if path.exists() else {}

    def learn(self, key, ncaa_id):
        """Record home-team evidence; ambiguous keys become unusable."""
        key = norm(key)
        if not key or key in self.static:
            return
        prev = self.learned.get(key)
        if prev is None:
            self.learned[key] = None if key in self.ambiguous else ncaa_id
        elif prev != ncaa_id:
            self.learned[key] = None
            if key not in self.ambiguous:
                self.ambiguous.append(key)
        self.new_learned.setdefault(key, set()).add(ncaa_id)

    def save_learned(self):
        write_json(ROOT / "data" / "learned_names.json",
                   {"names": self.learned, "ambiguous": sorted(self.ambiguous)})

    def _fuzzy_token_index(self):
        """(tokens, ncaa_id) pairs for prefix-based fuzzy matching."""
        return [(tokens(k), v) for k, v in self.static.items() if v is not None]

    def fuzzy(self, name):
        """'Missouri St.' -> Missouri State via token-prefix match. Unique only."""
        toks = tokens(name)
        if not toks:
            return None
        hits = set()
        for ctoks, cid in self._fuzzy_src:
            if len(ctoks) < len(toks):
                continue
            if all(t in c or c.startswith(t) for t, c in zip(toks, ctoks)):
                hits.add(cid)
        return hits.pop() if len(hits) == 1 else None

    def resolve(self, name, abbrev):
        for key in (norm(name), norm(abbrev)):
            if key in self.static:
                return self.static[key], "manifest"
            v = self.learned.get(key)
            if v is not None:
                return v, "learned"
            if key in self.aliases:
                return self.aliases[key], "alias"
        fuzzy_id = self.fuzzy(norm(name) or "")
        if fuzzy_id is not None:
            return fuzzy_id, "fuzzy"
        return None, "unresolved"


def date_iso(raw):
    """'1/23/2026' -> '2026-01-23'"""
    if not raw:
        return None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw.strip())
    if not m:
        return None
    mm, dd, yy = m.groups()
    return "{}-{:02d}-{:02d}".format(yy, int(mm), int(dd))


def parse_game(path, home_id, manifest_by_id, resolver):
    """Returns (record-or-None, skip_reason).

    The directory only tells us the ncaa_id of the filing team (which is
    normally the payload's HomeTeam, but not always, e.g. a team filing an
    away game). Both sides are therefore resolved from the payload; the
    directory id acts as the tiebreaker for whichever side stays unresolved.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as e:
        return None, "parse_error:{}".format(e.__class__.__name__)
    if not isinstance(data, dict):
        return None, "bad_payload"
    g = data.get("Game") or {}
    if not g:
        return None, "no_game_block"
    home, vis = g.get("HomeTeam") or {}, g.get("VisitingTeam") or {}

    h_name = (home.get("Name") or "").strip()
    v_name = (vis.get("Name") or "").strip()
    h_id = resolver.resolve(h_name, home.get("Id"))[0]
    v_id = resolver.resolve(v_name, vis.get("Id"))[0]
    anchor = home_id if home_id in manifest_by_id else None

    def learn_side(side_name, side_abbrev):
        if anchor is not None:
            resolver.learn(side_name, anchor)
            resolver.learn(side_abbrev, anchor)

    if h_id is None and v_id is None:
        # nothing resolvable; fall back to the filing team for the home side
        h_id = anchor
        learn_side(h_name, home.get("Id"))
    elif h_id is None and v_id != anchor:
        h_id = anchor
        learn_side(h_name, home.get("Id"))
    elif v_id is None and h_id != anchor:
        v_id = anchor
        learn_side(v_name, vis.get("Id"))

    if v_id is None:
        if v_name:
            resolver.unresolved[v_name] += 1
    else:
        resolver.resolved_counts[v_name] += 1

    rec = {
        "id": int(path.stem),
        "s": path.parent.name,
        "d8": date_iso(g.get("Date")),
        "t": g.get("StartTime"),
        "done": bool(g.get("IsComplete")),
        "h": h_id,
        "v": v_id,
        "hs": home.get("Score"),
        "vs": vis.get("Score"),
        "loc": g.get("Location"),
        "at": g.get("Attendance"),
        "src": "{}/{}/{}".format(path.parent.parent.name, path.parent.name, path.name),
    }
    # fall back to raw API names for sides that didn't resolve to a manifest id
    if h_id is None:
        rec["hn"] = h_name
    if v_id is None:
        rec["vn"] = v_name
    hs_p, vs_p = home.get("PeriodScores") or [], vis.get("PeriodScores") or []
    if hs_p or vs_p:
        rec["hp"] = hs_p
        rec["vp"] = vs_p
    return rec, None


def dedupe_records(records):
    """The same real game can appear multiple times: feeds sometimes re-key a
    game (different id, identical content, e.g. 16617 vs 17101 for one WPI
    game), and a game can be filed under either team's folder. Note that
    equal game ids across folders are NOT duplicates — ids are only unique
    per livestats client. Merge records with identical matchup/date/scores
    and venue, keeping the first (the one whose box page / links we ship).
    """
    groups = defaultdict(list)
    for r in records:
        groups[(r["d8"], r["h"], r["v"], r["hs"], r["vs"],
                r.get("loc"), r.get("at"), tuple(r.get("hp") or ()),
                tuple(r.get("vp") or ()))].append(r)
    out, merged = [], 0
    for rs in groups.values():
        if len(rs) > 1:
            merged += len(rs) - 1
        out.append(rs[0])
    out.sort(key=lambda r: (r["d8"] or "", r["id"]))
    return out, merged


def season_divisions(records, manifest_by_id):
    """Split season records into division shards keyed by home team's division."""
    shards = {"d1": [], "d2": [], "d3": [], "x": []}
    for r in records:
        div = manifest_by_id[r["h"]]["division"] if r["h"] in manifest_by_id else None
        shards[DIV_SHARD.get(div, "x")].append(r)
    return shards


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def scan_season(season, manifest_by_id, resolver):
    records = []
    for team_dir in sorted(ROOT.iterdir()):
        if (not team_dir.is_dir() or team_dir.name in SKIP_DIRS
                or team_dir.name.startswith(".")):
            continue
        m = DIR_RE.match(team_dir.name)
        if not m:
            continue
        season_dir = team_dir / season
        if not season_dir.is_dir():
            continue
        home_id = int(m.group(1))
        for fp in sorted(season_dir.glob("*.json")):
            rec, unres = parse_game(fp, home_id, manifest_by_id, resolver)
            if rec is None:
                resolver.unresolved[unres] += 1
            else:
                records.append(rec)
    records.sort(key=lambda r: (r["d8"] or "", r["id"]))
    return records


def merge_team_file(ncaa_id, new_records):
    """Replace a team's records for the seasons being rebuilt, keep the rest."""
    team_file = INDEX / "teams" / str(ncaa_id) / "games.json"
    old = json.load(open(team_file))["games"] if team_file.exists() else []
    rebuilt_seasons = {r["s"] for r in new_records}
    kept = [r for r in old if r["s"] not in rebuilt_seasons]
    records = sorted(kept + new_records, key=lambda r: (r["d8"] or "", r["id"]))
    write_json(team_file, {"team_id": ncaa_id, "games": records})
    return records


def seasons_from_git(ref):
    out = subprocess.run(
        ["git", "diff", "--name-only", ref, "HEAD", "--", "*.json"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    seasons = {p.split("/")[1] for p in out.splitlines() if p.count("/") >= 2}
    if not seasons:
        sys.exit("no .json changes under team/season dirs since " + ref)
    return seasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", action="append", help="rescan only this season (repeatable)")
    ap.add_argument("--since", help="rescan seasons with .json changes since a git ref")
    args = ap.parse_args()

    manifest = json.load(open(ROOT / "data" / "teams.json"))
    manifest_by_id = {t["ncaa_id"]: t for t in manifest}
    resolver = Resolver(manifest)

    if args.since:
        seasons = sorted(seasons_from_git(args.since))
    elif args.season:
        seasons = args.season
    else:
        seasons = sorted({sd.name
                          for td in ROOT.iterdir()
                          if td.is_dir() and td.name not in SKIP_DIRS
                          and not td.name.startswith(".") and DIR_RE.match(td.name)
                          for sd in td.iterdir()
                          if sd.is_dir() and SEASON_RE.match(sd.name)})
    if not seasons:
        sys.exit("no seasons found")
    rebuilt = set(seasons)
    season_meta = {}
    per_team_new = defaultdict(list)
    total = 0

    for season in seasons:
        records = scan_season(season, manifest_by_id, resolver)
        records, merged = dedupe_records(records)
        if merged:
            print("{}: merged {} duplicate filings".format(season, merged), flush=True)
        shards = season_divisions(records, manifest_by_id)
        write_json(INDEX / "seasons" / season / "games.json",
                   {"season": season, "games": records})
        for shard, recs in shards.items():
            if recs:
                write_json(INDEX / "seasons" / season / "{}.json".format(shard),
                           {"season": season, "division": shard, "games": recs})
        for r in records:
            for tid in {r["h"], r["v"]}:
                if tid is not None:
                    per_team_new[tid].append(r)
        season_meta[season] = {
            "games": len(records),
            "d1": len(shards["d1"]), "d2": len(shards["d2"]),
            "d3": len(shards["d3"]), "x": len(shards["x"]),
        }
        total += len(records)
        print("{}: {} games (d1={} d2={} d3={} x={})".format(
            season, len(records), len(shards["d1"]), len(shards["d2"]),
            len(shards["d3"]), len(shards["x"])), flush=True)

    for tid, recs in sorted(per_team_new.items()):
        merge_team_file(tid, [r for r in recs if r["s"] in rebuilt])

    # learnings gained this run persist for future runs
    resolver.save_learned()
    write_json(INDEX / "unresolved.json",
               {"note": "file-level skip reasons and visitor names not matched "
                        "to any manifest/learned/alias entry",
                "names": dict(resolver.unresolved.most_common())})

    meta_file = INDEX / "meta.json"
    meta = json.load(open(meta_file))["seasons"] if meta_file.exists() else {}
    meta.update(season_meta)
    write_json(meta_file, {
        "updated_seasons": seasons,
        "total_games": total,
        "seasons": dict(sorted(meta.items(), reverse=True)),
    })
    if resolver.unresolved:
        top = resolver.unresolved.most_common(5)
        bad = sum(c for n, c in resolver.unresolved.items()
                  if not n.startswith(("no_game_block", "bad_payload", "parse_error")))
        print("unresolved visitor names: {} (top: {})".format(
            bad, ", ".join("{} ({})".format(n, c) for n, c in top)), file=sys.stderr)


if __name__ == "__main__":
    main()
