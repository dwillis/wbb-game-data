import os
import re

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SEASON_PATTERN = re.compile(r"^\d{4}-\d{2}$")
SKIP_DIRS = {".git", ".claude", ".github"}


def main():
    teams = 0
    seasons = set()
    game_files = 0

    for entry in os.scandir(REPO_ROOT):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        teams += 1
        for season_entry in os.scandir(entry.path):
            if not season_entry.is_dir() or not SEASON_PATTERN.match(season_entry.name):
                continue
            seasons.add(season_entry.name)
            game_files += sum(
                1 for f in os.scandir(season_entry.path)
                if f.is_file() and f.name.endswith(".json")
            )

    print(f"Teams:      {teams:,}")
    print(f"Seasons:    {len(seasons)}")
    print(f"Game files: {game_files:,}")


if __name__ == "__main__":
    main()
