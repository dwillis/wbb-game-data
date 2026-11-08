# wbb-game-data

This repository contains individual JSON files of game data from NCAA women's basketball games from the 2006-07 season through the 2024-25 season, although not for all teams listed here. The JSON files are stored in individual team folders prefixed with the NCAA team id of each school. An example of a JSON game file is https://bgsufalcons.com/api/livestats?game_id=10955&detail=full.

These files were collected using [a Python library written for the purpose](https://github.com/dwillis/wbb), which in turn depends on a listing of teams with URLs and NCAA ids (https://github.com/dwillis/wbb/blob/master/ncaa/teams.json). Contributions to the teams JSON file are welcome.

### Caveats

* Not all teams have game data for all seasons.
* Some teams do not produce the JSON files or use a different URL structure.
* In some seasons (particularly 2020-21), not all actually played games appear to have corresponding JSON files.

### Contributing

The best way to contribute right now is to add URLs to [the JSON teams file](https://github.com/dwillis/wbb/blob/master/ncaa/teams.json).

### Structure

* `{ncaa_id}-{team-slug}/{season}/{game_id}.json` — one raw livestats payload per game (schedule + box score + play-by-play). Games are filed under the directory of whichever team's stats feed produced the file — usually but not always the home team, so both teams in a game are read from the payload itself.
* `data/teams.json` — manifest of NCAA teams (name, NCAA id, conference, division), used to resolve every team and shard the index by division.
* `data/learned_names.json` — API team names/abbreviations mapped to NCAA ids, learned automatically from the archive (see below).
* `data/name_aliases.json` — optional manual `name -> ncaa_id` aliases for anything still unresolved.
* `index/` — derived, metadata-only index (schedules, scores, venues; no box scores or play-by-play). Built from the raw files by `scripts/build_index.py`.
* `site/` — the static GitHub Pages site (schedules, division browsing, box-score pages for the current season), built by `scripts/build_site.py` from the index and current-season raw files.

**Organization by division** is a property of the index and site, not the filesystem — raw game files stay where they are, and every view (D-I/D-II/D-III) is derived from `data/teams.json`.

### Scripts

* `scripts/check_teams.py` — verifies every team directory resolves against the manifest, lists duplicates and uncollected teams.
* `scripts/build_index.py` — builds/updates `index/`. Resolves both teams of each game against the manifest, plus names learned from the archive and manual aliases; anything left unresolved is kept name-only and reported in `index/unresolved.json`. Options: `--season 2025-26` (rescan one season), `--since <git-ref>` (rescan seasons touched since a ref — the fast daily-update path).
* `scripts/build_site.py` — builds/updates `site/` (requires the index; parses the current season's raw files for box-score pages and the scoring-leader page).

### Daily update workflow

```sh
# after running the collector for new games:
python3 scripts/build_index.py --since HEAD~1   # or --season 2025-26
python3 scripts/build_site.py
git add index site data && git commit -m "<date> update"
```

Pushing commits that change `site/` triggers the Pages deploy workflow (`.github/workflows/static.yml`), which ships only `site/` — the full archive is never touched by CI.
