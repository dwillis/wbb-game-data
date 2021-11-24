# wbb-game-data

This repository contains individual JSON files of game data from NCAA women's basketball games from the 2014-15 season through the 2020-21 season, although not for all teams listed here. The JSON files are stored in individual team folders prefixed with the NCAA team id of each school. An example of a JSON game file is https://bgsufalcons.com/api/livestats?game_id=10955&detail=full.

These files were collected in April 2021 using [a Python library written for the purpose](https://github.com/dwillis/wbb), which in turn depends on a listing of teams with URLs and NCAA ids (https://github.com/dwillis/wbb/blob/master/ncaa/teams.json). Contributions to the teams JSON file are welcome.

### Caveats

* Some teams do not produce the JSON files or use a different URL structure.
* In some seasons (particularly 2020-21), not all actually played games appear to have corresponding JSON files.

### Contributing

The best way to contribute right now is to add URLs to [the JSON teams file](https://github.com/dwillis/wbb/blob/master/ncaa/teams.json).
