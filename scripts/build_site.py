#!/usr/bin/env python3
"""Build the static GitHub Pages site from index/ and the raw archive.

Pages produced under site/:
  index.html                        home: recent finals + all-seasons table
  d1.html d2.html d3.html x.html    division browsers (JS season switcher)
  teams/{ncaa_id}.html              schedule page per team, all seasons (JS)
  games/{season}/{id}.html          box-score page for each CURRENT-season game
  leaders.html                      current-season scoring leaders by division
  data/…                            JSON slices the pages fetch client-side

Run after build_index.py. Current season = highest season present in index/.
Everything is relative-linked, so it works under /wbb-game-data/ on GitHub Pages.
"""
import html
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index"
SITE = ROOT / "site"
RAW_URL = "https://raw.githubusercontent.com/dwillis/wbb-game-data/main/"
SHARDS = (("d1", "Division I"), ("d2", "Division II"),
          ("d3", "Division III"), ("x", "Other (non-D I/II/III)"))
NAV = ('<nav><a href="index.html">Home</a> <a href="d1.html">D-I</a> <a href="d2.html">D-II</a>'
       ' <a href="d3.html">D-III</a> <a href="x.html">Other</a> <a href="leaders.html">Leaders</a></nav>')

CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#ddd;--accent:#8a3c1c;--card:#f6f6f4}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--fg:#e8e8e8;--mut:#999;--line:#333;--accent:#e0906b;--card:#1e2226}}
*{box-sizing:border-box}
body{margin:0;padding:1rem 1rem 3rem;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,"Segoe UI",system-ui,sans-serif}
main{max-width:64em;margin:0 auto}
h1{font-size:1.4rem;margin:.2rem 0 .8rem}h2{font-size:1.1rem;margin:1.3rem 0 .4rem}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
table{border-collapse:collapse;width:100%;margin:.4rem 0 1rem;font-size:.9rem}
th,td{text-align:left;padding:.26rem .45rem;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600}td.n,th.n{text-align:right}
.card{background:var(--card);border-radius:8px;padding:.6rem .9rem;margin:.45rem 0}
.mut{color:var(--mut)}.win{font-weight:700}
.sel{padding:.35rem .5rem;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--fg);margin-bottom:.8rem}
nav{margin:.6rem 0 1.1rem}nav a{margin-right:.9rem}
"""

BOX_COLS = ["Minutes", "Fgam", "Tpam", "Ftma", "TotalRebounds", "Assists",
            "Turnovers", "Steals", "Blocks", "PersonalFouls", "Points"]
BOX_HEADERS = {"Minutes": "Min", "Fgam": "FG", "Tpam": "3P", "Ftma": "FT",
               "TotalRebounds": "Reb", "Assists": "Ast", "Turnovers": "TO",
               "Steals": "Stl", "Blocks": "Blk", "PersonalFouls": "PF", "Points": "Pts"}
TOTAL_KEYS = ["Points", "Fgam", "Tpam", "Ftma", "TotalRebounds", "Assists",
              "Turnovers", "Steals", "Blocks", "PersonalFouls"]
SEASON_LABELS_SHOWN = 4  # quarters before OT labels start


def esc(v):
    if v is None or v == "":
        return ""
    return html.escape(str(v))


def page(title, body, with_nav=True):
    nav = NAV if with_nav else ""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>{}</title><style>{}</style></head><body><main>{}{}</main></body></html>'
            ).format(esc(title), CSS, nav, body)


def w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def load(p):
    with open(p) as f:
        return json.load(f)


def tname(manifest, rec, tid, raw_key):
    """Display name for a side: manifest name, else the raw API name."""
    if tid is not None and tid in manifest:
        return manifest[tid]["team"]
    return rec.get(raw_key) or (str(tid) if tid is not None else "—")


def period_header(n):
    out = []
    for i in range(n):
        out.append("Q{}".format(i + 1) if i < SEASON_LABELS_SHOWN
                   else ("OT" if i == SEASON_LABELS_SHOWN else "OT{}".format(i - SEASON_LABELS_SHOWN)))
    return out


# ------------------------------------------------------------------ home
def build_home(manifest, seasons, current):
    rows = []
    for shard, label in SHARDS:
        fp = INDEX / "seasons" / current / (shard + ".json")
        if not fp.exists():
            continue
        recent = [g for g in load(fp)["games"]
                  if g["done"] and g["hs"] is not None and g["vs"] is not None]
        rows.extend((shard, g) for g in recent[-6:])
    rows.sort(key=lambda t: (t[1]["d8"] or "", t[1]["id"]), reverse=True)
    rows = rows[:18]

    cur_count = len(load(INDEX / "seasons" / current / "games.json")["games"])
    parts = ["<h1>NCAA women’s basketball — game data</h1>",
             '<p class="mut">{} games indexed for <b>{}</b>, with {} seasons on file '
             '(2006-07 through {}). Box-score pages exist for the current season; '
             'older games link to the raw JSON archive.</p>'.format(
                 cur_count, current, len(seasons), current),
             "<h2>Recent finals</h2>"]
    for shard, g in rows:
        v = tname(manifest, g, g["v"], "vn")
        h = tname(manifest, g, g["h"], "hnm")
        parts.append(
            '<div class="card"><span class="mut">{}</span> · <a href="teams/{}.html">{}</a> '
            '<b>{}–{}</b> <a href="teams/{}.html">{}</a> <span class="mut">· {} · '
            '<a href="games/{}/{}.html">box</a></span></div>'.format(
                esc(g["d8"]), esc(g["v"]), esc(v), esc(g["vs"]), esc(g["hs"]),
                esc(g["h"]), esc(h), dict((s, l) for s, l in SHARDS)[shard],
                esc(g["s"]), esc(g["id"])))
    parts.append("<h2>Seasons</h2><table><tr><th>Season</th><th class=n>Games</th>"
                 "<th class=n>D-I</th><th class=n>D-II</th><th class=n>D-III</th>"
                 "<th class=n>Other</th></tr>")
    for s in sorted(seasons, reverse=True):
        m = seasons[s]
        parts.append("<tr><td>{}</td><td class=n>{}</td><td class=n>{}</td><td class=n>{}</td>"
                     "<td class=n>{}</td><td class=n>{}</td></tr>".format(
                         esc(s), m["games"], m["d1"], m["d2"], m["d3"], m["x"]))
    parts.append("</table>")
    w(SITE / "index.html", page("NCAA WBB game data", "".join(parts), with_nav=False))


# --------------------------------------------------------------- box pages
def box_table(rows):
    if not rows:
        return ""
    cols = [c for c in BOX_COLS if any(c in r for r in rows)]
    out = ['<table><tr><th>#</th><th>Player</th><th>Pos</th>'
           + "".join('<th class=n>{}</th>'.format(BOX_HEADERS[c]) for c in cols) + '</tr>']
    for r in rows:
        out.append('<tr><td>{}</td><td>{}{}</td><td>{}</td>'.format(
            esc(r.get("Uni")), esc(r.get("Name")),
            "" if not r.get("CurrentlyInGame") else "",
            esc(r.get("Position"))))
        for c in cols:
            out.append('<td class=n>{}</td>'.format(esc(r.get(c, ""))))
        out.append("</tr>")
    # totals row from Totals.Values when available
    out.append("</table>")
    return "".join(out)


def totals_table(totals):
    vals = totals.get("Values") or {}
    keys = [k for k in TOTAL_KEYS if vals.get(k)]
    if not keys:
        return ""
    return ('<table><tr><th>Team totals</th>'
            + "".join('<th class=n>{}</th>'.format(BOX_HEADERS[k]) for k in keys) + '</tr>'
            '<tr><td></td>' + "".join('<td class=n>{}</td>'.format(esc(vals[k])) for k in keys)
            + '</tr></table>')


def write_box_page(rec, data, manifest, current):
    hname = tname(manifest, rec, rec["h"], "hnm")
    vname = tname(manifest, rec, rec["v"], "vn")
    g = (data or {}).get("Game") or {}
    title = "{} @ {}: {}".format(vname, hname, rec["s"])
    parts = ['<h1>{} {}–{} {}</h1>'.format(
        esc(vname), esc(rec["vs"]), esc(rec["hs"]), esc(hname))]
    when = ", ".join(x for x in (rec["d8"], rec.get("t")) if x)
    meta_bits = [when]
    if g.get("Location"):
        meta_bits.append(esc(g["Location"]))
    if g.get("Attendance"):
        meta_bits.append("attendance " + esc(g["Attendance"]))
    if rec["done"] is False:
        meta_bits.append("not final")
    parts.append('<p class="mut">{}</p>'.format(" · ".join(b for b in meta_bits if b)))
    parts.append('<p><a href="{}" target="_blank">raw JSON ▸</a></p>'.format(RAW_URL + rec["src"]))

    hp, vp = rec.get("hp") or [], rec.get("vp") or []
    if hp or vp:
        n = max(len(hp), len(vp))
        parts.append('<table><tr><th></th>'
                     + "".join('<th class=n>{}</th>'.format(x) for x in period_header(n))
                     + '<th class=n>F</th></tr>')
        for label, arr, total in ((vname, vp, rec["vs"]), (hname, hp, rec["hs"])):
            # hp/vp are the payload home/visitor period scores; payload home = rec["h"]
            parts.append('<tr><td>{}</td>'.format(esc(label))
                         + "".join('<td class=n>{}</td>'.format(esc(x)) for x in arr)
                         + '<td class=n><b>{}</b></td></tr>'.format(esc(total)))
        parts.append("</table>")
    if g.get("Officials"):
        parts.append('<p class="mut">Officials: {}</p>'.format(esc(g["Officials"])))
    for tid, name in ((rec["v"], vname), (rec["h"], hname)):
        if tid is not None:
            parts.append('<a href="../../teams/{}.html">{} schedule ▸</a> '.format(tid, esc(name)))
    if rec["v"] is not None or rec["h"] is not None:
        parts.append("<p></p>")

    stats = (data or {}).get("Stats") or {}
    sides = (("HomeTeam", rec["h"], hname), ("VisitingTeam", rec["v"], vname))
    for key, tid, name in sides:
        side = stats.get(key)
        if not side:
            continue
        rows = None
        for grp in (side.get("PlayerGroups") or {}).values():
            if grp.get("Values"):
                rows = grp["Values"]
        parts.append("<h2>{} — box score</h2>".format(esc(name)))
        if rows:
            parts.append(box_table(rows))
        parts.append(totals_table(side.get("Totals") or {}))
    leaders_block = (data or {}).get("Leaders") or {}
    if leaders_block:
        parts.append("<h2>Game leaders</h2>")
        for key, tid, name in sides:
            cats = leaders_block.get(key) or {}
            bits = []
            for cat, entries in cats.items():
                entries = entries or []
                if not entries:
                    continue
                who = "; ".join(
                    "{} {}".format(
                        ((e.get("Player") or {}).get("FirstName") or ""),
                        ((e.get("Player") or {}).get("LastName") or "")).strip()
                    + " " + esc(e.get("Value"))
                    for e in entries[:3])
                bits.append("<b>{}</b>: {}".format(esc(cat), who))
            if bits:
                parts.append('<div class="card"><b>{}</b> — {}</div>'.format(esc(name), " · ".join(bits)))
    w(SITE / "games" / rec["s"] / "{}.html".format(rec["id"]),
      page(title, "".join(parts)))


# ------------------------------------------------------------------ leaders
def write_leaders(leaders_acc, current, manifest):
    parts = ["<h1>Scoring leaders — {}</h1>".format(esc(current)), NAV,
             '<p class="mut">Points accumulated from this season’s box scores, game by '
             'game. Player identity is the raw box-score name, so a player can appear '
             'twice (e.g. after a transfer) — treat as a starting point.</p>']
    for div, label in (("I", "Division I"), ("II", "Division II"), ("III", "Division III")):
        acc = leaders_acc.get(div)
        if not acc:
            continue
        parts.append('<h2>{}</h2><table><tr><th class=n>#</th><th>Player</th>'
                     '<th>Team</th><th class=n>Pts</th></tr>')
        top = sorted(acc.items(), key=lambda kv: kv[1], reverse=True)[:50]
        for i, ((tid, name), pts) in enumerate(top, 1):
            t = manifest.get(tid)
            team_link = ('<a href="teams/{}.html">{}</a>'.format(tid, esc(t["team"]))
                         if t else esc(name))  # unresolvable team: show player again, never a fake link
            parts.append('<tr><td class=n>{}</td><td>{}</td><td>{}</td>'
                         '<td class=n>{}</td></tr>'.format(i, esc(name), team_link, pts))
        parts.append("</table>")
    w(SITE / "leaders.html", page("Scoring leaders", "".join(parts)))


# ----------------------------------------------------------------- helpers
def js_const(name, value):
    return "const {} = {};\n".format(name, json.dumps(value))


# -------------------------------------------------------------------- main
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=2,
                    help="how many most-recent seasons get box-score pages (default 2)")
    args = ap.parse_args()

    manifest_by_id = {t["ncaa_id"]: t for t in load(ROOT / "data" / "teams.json")}
    meta = load(INDEX / "meta.json")
    seasons = meta["seasons"]
    current = max(seasons)
    box_seasons = sorted(seasons, reverse=True)[:args.seasons]

    shutil.rmtree(SITE, ignore_errors=True)

    # ---- data slices the pages fetch --------------------------------------
    data = SITE / "data"
    teams_list = [{"id": i, "name": t["team"], "division": t.get("division"),
                   "conference": t.get("conference"), "state": t.get("team_state")}
                  for i, t in sorted(manifest_by_id.items())]
    w(data / "teams.json", json.dumps(teams_list, separators=(",", ":")))
    shutil.copy(INDEX / "meta.json", data / "meta.json")
    for season_dir in sorted((INDEX / "seasons").iterdir()):
        if not season_dir.name[0].isdigit():
            continue
        out = data / "seasons" / season_dir.name
        out.mkdir(parents=True, exist_ok=True)
        for f in season_dir.glob("*.json"):
            shutil.copy(f, out / f.name)
    n_team_data = 0
    (data / "teams").mkdir(parents=True, exist_ok=True)
    for team_file in (INDEX / "teams").glob("*/games.json"):
        shutil.copy(team_file, data / "teams" / (team_file.parent.name + ".json"))
        n_team_data += 1

    build_home(manifest_by_id, seasons, current)

    # ---- division browsers -------------------------------------------------
    season_keys = sorted(seasons, reverse=True)
    for shard, label in SHARDS:
        js = (js_const("TEAMS_JSON", teams_list)
              + js_const("SEASONS", season_keys)
              + js_const("CUR", current)
              + js_const("BOX_SEASONS", box_seasons)
              + js_const("SHARD", shard)
              + """
const TEAMS={}; for (const t of TEAMS_JSON) TEAMS[t.id] = t;
const sel = document.getElementById('season');
const tbl = document.getElementById('tbl');
const ld = document.getElementById('load');
for (const s of SEASONS) { const o = document.createElement('option'); o.value = o.textContent = s; sel.appendChild(o); }
sel.value = SEASONS.includes(CUR) ? CUR : SEASONS[0];
sel.onchange = render; if (SEASONS.length) render();
function tname(g, id, rawKey) { return TEAMS[id] ? TEAMS[id].name : (g[rawKey] || id || '—'); }
async function render() {
  tbl.style.display = 'none'; ld.style.display = '';
  ld.textContent = 'Loading ' + sel.value + '…';
  const r = await fetch('data/seasons/' + sel.value + '/' + SHARD + '.json');
  if (!r.ok) { ld.textContent = 'No games on file for this division and season.'; return; }
  const games = (await r.json()).games;
  ld.style.display = 'none'; tbl.style.display = '';
  tbl.innerHTML = '<thead><tr><th>Date</th><th>Visitor</th><th class=n>vs</th>'
    + '<th class=n>Home</th><th>Status</th><th>Link</th></tr></thead>';
  for (const g of games) {
    const tr = tbl.insertRow();
    const hasBox = (BOX_SEASONS.indexOf(g.s) >= 0);
    const href = hasBox ? ('games/' + g.s + '/' + g.id + '.html') : (RAWJSON + g.src);
    tr.innerHTML = '<td>' + g.d8 + '</td><td>'
      + (g.v ? '<a href="teams/' + g.v + '.html">' + tname(g, g.v, 'vn') + '</a>' : (g.vn || '—'))
      + '</td><td class=n>' + g.vs + '</td><td class=n>' + g.hs + '</td><td>'
      + (g.done ? 'final' : (g.t ? 'sched, ' + g.t : 'scheduled'))
      + '</td><td><a href="' + href + '"' + (hasBox ? '' : ' target=_blank') + '>'
      + (hasBox ? 'box' : 'raw') + '</a></td>';
  }
}
""")
        body = ['<h1>{}</h1>'.format(esc(label)), NAV,
                '<p class="mut">Pick a season to load its schedule. “box” = detail page '
                '(most recent seasons); “raw” = raw archive JSON.</p>',
                '<select class=sel id=season></select>',
                '<table id=tbl style="display:none"></table>',
                '<div id=load class=mut>Loading…</div>',
                '<script>', js_const("RAWJSON", RAW_URL), js, '</script>']
        w(SITE / (shard + ".html"), page(label, "".join(body)))

    # ---- team schedule pages ----------------------------------------------
    team_js = js_const("RAWJSON", RAW_URL) + """
const TEAM_ID_TEAMS = {};
let GAMES = null, TEAMS_READY = false;
const sel = document.getElementById('season'), tbl = document.getElementById('tbl'), ld = document.getElementById('load');
sel.onchange = () => redraw();
fetch('../data/teams.json').then(r => r.json()).then(t => {
  for (const x of t) TEAM_ID_TEAMS[x.id] = x;
  TEAMS_READY = true; redraw();
});
async function boot() {
  const j = await (await fetch('../data/teams/' + TEAM_ID + '.json')).json();
  GAMES = j.games;
  const ss = [...new Set(GAMES.map(g => g.s))].sort().reverse();
  if (!sel.options.length) for (const s of ss) {
    const o = document.createElement('option'); o.value = o.textContent = s; sel.appendChild(o);
  }
  if (!sel.value) sel.value = ss.includes(CUR_TEAM_SEASON) ? CUR_TEAM_SEASON : (ss[0] || '');
  redraw();
}
async function redraw() {
  if (!GAMES) { setTimeout(redraw, 50); return; }
  if (!TEAMS_READY) { setTimeout(redraw, 50); return; }
  const me = TEAM_ID;
  const rows = GAMES.filter(g => g.s === sel.value);
  tbl.innerHTML = '<thead><tr><th>Date</th><th>Opponent</th><th>H/A</th><th class=n>Score</th>'
    + '<th>Result</th><th>Venue</th><th class=n>Att</th><th>Link</th></tr></thead>';
  for (const g of rows) {
    const tr = tbl.insertRow();
    const home = g.h === me;
    const opp = home ? g.v : g.h;
    const oname = TEAM_ID_TEAMS[opp] ? TEAM_ID_TEAMS[opp].name
      : (home ? (g.vn || (opp == null ? '—' : opp)) : (g.hn || (g.h == null ? '—' : g.h)));
    const mine = home ? g.hs : g.vs, oth = home ? g.vs : g.hs;
    let result = '';
    if (g.done && mine != null && oth != null) {
      const k = mine > oth ? 'W' : (mine < oth ? 'L' : 'T');
      result = '<span class="' + (k === 'W' ? 'win' : 'mut') + '">' + k + ' ' + mine + '–' + oth + '</span>';
    }
    const hasBox = (BOX_SEASONS.indexOf(g.s) >= 0);
    const link = hasBox ? ('../games/' + g.s + '/' + g.id + '.html') : (RAWJSON + g.src);
    tr.innerHTML = '<td>' + g.d8 + '</td><td>'
      + (opp != null ? '<a href="' + opp + '.html">' + oname + '</a>' : oname)
      + '</td><td>' + (home ? 'H' : 'A') + '</td><td class=n>'
      + (home ? g.hs + '–' + g.vs : g.vs + '–' + g.hs) + '</td><td>' + result + '</td>'
      + '<td>' + (g.loc || '') + '</td><td class=n>' + (g.at || '') + '</td>'
      + '<td><a href="' + link + '"' + (hasBox ? '' : ' target=_blank') + '>'
      + (hasBox ? 'box' : 'raw') + '</a></td>';
  }
  if (!rows.length) tbl.innerHTML += '<tr><td colspan=8 class=mut>No games on file for this season.</td></tr>';
  ld.style.display = 'none'; tbl.style.display = '';
}
boot();
"""

    n_team_pages = 0
    for tid, t in sorted(manifest_by_id.items()):
        tf = INDEX / "teams" / str(tid) / "games.json"
        team_seasons = sorted({g["s"] for g in load(tf)["games"]}, reverse=True) if tf.exists() else []
        default = current if current in team_seasons else (team_seasons[0] if team_seasons else "")
        opts = "".join('<option{}>{}</option>'.format(" selected" if s == default else "", s)
                       for s in team_seasons)
        subtitle = " — ".join(x for x in ("Division " + t["division"] if t.get("division") else None,
                                          t.get("conference")) if x)
        body = ['<h1>{}</h1>'.format(esc(t["team"])),
                '<p class="mut">{}</p>'.format(esc(subtitle)) if subtitle else "",
                NAV,
                '<select class=sel id=season>{}</select>'.format(opts),
                '<table id=tbl style="display:none"></table>',
                '<div id=load class=mut>Loading…</div>']
        js = (js_const("TEAM_ID", tid)
              + js_const("BOX_SEASONS", box_seasons)
              + ("let CUR_TEAM_SEASON = null;\n" if not default else js_const("CUR_TEAM_SEASON", default))
              + team_js)
        w(SITE / "teams" / "{}.html".format(tid), page(t["team"], "".join(body) + "<script>" + js + "</script>"))
        n_team_pages += 1

    # ---- box pages for the most recent seasons + leaderboard aggregation ----
    leaders_acc = defaultdict(lambda: defaultdict(int))  # division -> (team_id, name) -> pts
    parsed, n_box = 0, 0
    for season in box_seasons:
        records = load(INDEX / "seasons" / season / "games.json")["games"]
        aggregate_leaders = season == box_seasons[0]
        for rec in records:
            data_obj = None
            try:
                data_obj = load(ROOT / rec["src"])
                if not isinstance(data_obj, dict) or not data_obj.get("Game"):
                    data_obj = None
            except Exception:
                data_obj = None
            write_box_page(rec, data_obj, manifest_by_id, current)
            if aggregate_leaders and data_obj and (data_obj.get("Stats") or {}):
                stats = data_obj["Stats"]
                for key, tid in (("HomeTeam", rec["h"]), ("VisitingTeam", rec["v"])):
                    side = stats.get(key)
                    if not side or tid not in manifest_by_id:
                        continue
                    div = manifest_by_id[tid].get("division")
                    if div not in ("I", "II", "III"):
                        continue
                    acc = leaders_acc[div]
                    for grp in (side.get("PlayerGroups") or {}).values():
                        for row in grp.get("Values") or []:
                            try:
                                acc[(tid, row.get("Name") or "?")] += int(str(row.get("Points") or "0"))
                            except (TypeError, ValueError):
                                pass
            parsed += 1
        n_box += len(records)
    write_leaders(leaders_acc, current, manifest_by_id)

    print("site built: {} team pages, {} box pages across seasons {} ({} files parsed)".format(
        n_team_pages, n_box, ", ".join(box_seasons), parsed))


if __name__ == "__main__":
    main()
