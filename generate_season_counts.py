import csv
import os
import re

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SEASON_PATTERN = re.compile(r"^\d{4}-\d{2}$")
SKIP_DIRS = {".git", ".claude", ".github"}


def main():
    team_seasons = {}
    all_seasons = set()

    for entry in os.scandir(REPO_ROOT):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        seasons = {}
        for season_entry in os.scandir(entry.path):
            if not season_entry.is_dir() or not SEASON_PATTERN.match(season_entry.name):
                continue
            count = sum(
                1 for f in os.scandir(season_entry.path)
                if f.is_file() and f.name.endswith(".json")
            )
            seasons[season_entry.name] = count
            all_seasons.add(season_entry.name)
        team_seasons[entry.name] = seasons

    sorted_seasons = sorted(all_seasons, reverse=True)
    sorted_teams = sorted(team_seasons.keys())

    output_path = os.path.join(REPO_ROOT, "season_counts.csv")
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["folder"] + sorted_seasons)
        for team in sorted_teams:
            row = [team] + [team_seasons[team].get(s, 0) for s in sorted_seasons]
            writer.writerow(row)

    print(f"Wrote {len(sorted_teams)} teams x {len(sorted_seasons)} seasons to {output_path}")


if __name__ == "__main__":
    main()
