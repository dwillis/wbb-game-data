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
NAV_ITEMS = (("index.html", "Home"), ("d1.html", "D-I"), ("d2.html", "D-II"),
             ("d3.html", "D-III"), ("x.html", "Other"), ("dates.html", "Dates"),
             ("leaders.html", "Leaders"))


def nav(prefix=""):
    return "<nav>" + " ".join('<a href="{}{}">{}</a>'.format(prefix, href, label)
                              for href, label in NAV_ITEMS) + "</nav>"

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
.exh{display:inline-block;font-size:.7rem;line-height:1.3;padding:.1rem .4rem;border-radius:9px;vertical-align:1px;border:1px solid var(--line);color:var(--mut);white-space:nowrap}
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


def is_exhibition(rec, manifest):
    """Cross-division matchup or a side not in the NCAA manifest. The payloads
    carry no exhibition flag (Rules/Context are inconsistent), so this is the
    reliable part of the picture: D1-vs-D2/D3/NAIA games never count. D1-vs-D1
    charity exhibitions are not detectable automatically."""
    divs = []
    for tid in (rec["h"], rec["v"]):
        divs.append(manifest[tid].get("division") if tid in manifest else None)
    known = [d for d in divs if d in ("I", "II", "III")]
    return len(known) < 2 or len(set(known)) > 1


EXHIB_JS = """
function isExh(map, g) {
  const dh = (map[g.h] || {}).division, dv = (map[g.v] || {}).division;
  const ok = [];
  if (dh === 'I' || dh === 'II' || dh === 'III') ok.push(dh);
  if (dv === 'I' || dv === 'II' || dv === 'III') ok.push(dv);
  return ok.length < 2 || ok[0] !== ok[1];
}"""


def page(title, body, nav_html=None):
    n = nav("") if nav_html is None else nav_html
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>{}</title><style>{}</style></head><body><main>{}{}</main></body></html>'
            ).format(esc(title), CSS, n, body)


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
            '<div class="card">{exh}<span class="mut">{date}</span> · <a href="teams/{v}.html">{vname}</a> '
            '<b>{vs}–{hs}</b> <a href="teams/{h}.html">{hname}</a> <span class="mut">· {shard} · '
            '<a href="games/{s}/{id}.html">box</a></span></div>'.format(
                exh='<span class="exh">exhibition</span> ' if is_exhibition(g, manifest) else "",
                date=esc(g["d8"]), v=esc(g["v"]), vname=esc(v), vs=esc(g["vs"]), hs=esc(g["hs"]),
                h=esc(g["h"]), hname=esc(h), shard=dict((s, l) for s, l in SHARDS)[shard],
                s=esc(g["s"]), id=esc(g["id"])))
    parts.append("<h2>Seasons</h2><table><tr><th>Season</th><th class=n>Games</th>"
                 "<th class=n>D-I</th><th class=n>D-II</th><th class=n>D-III</th>"
                 "<th class=n>Other</th></tr>")
    for s in sorted(seasons, reverse=True):
        m = seasons[s]
        parts.append("<tr><td>{}</td><td class=n>{}</td><td class=n>{}</td><td class=n>{}</td>"
                     "<td class=n>{}</td><td class=n>{}</td></tr>".format(
                         esc(s), m["games"], m["d1"], m["d2"], m["d3"], m["x"]))
    parts.append("</table>")
    w(SITE / "index.html", page("NCAA WBB game data", "".join(parts) + nav("")))


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
    if is_exhibition(rec, manifest):
        parts.append('<p><span class="exh">exhibition game</span> <span class="mut">'
                     'cross-division or non-NCAA opponent — typically does not count '
                     'toward team records.</span></p>')
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
      page(title, "".join(parts), nav_html=nav("../../")))


# ------------------------------------------------------------------ leaders
def write_leaders(leaders_acc, current, manifest):
    parts = ["<h1>Scoring leaders — {}</h1>".format(esc(current)), nav(""),
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


# ------------------------------------------------------------------ dates
def build_dates(teams_list, box_seasons, latest):
    """One JSON slice per calendar date with games (all seasons) + one page."""
    by_date = defaultdict(list)
    n_dates = 0
    for season_dir in sorted((INDEX / "seasons").iterdir()):
        fp = season_dir / "games.json"
        if not fp.exists():
            continue
        for rec in load(fp)["games"]:
            if rec.get("d8"):
                by_date[rec["d8"]].append(rec)
        print("  dates: scanned " + season_dir.name, flush=True)
    out = SITE / "data" / "dates"
    summary = []
    for d8 in sorted(by_date):
        games = sorted(by_date[d8], key=lambda r: (r.get("t") or "", r["id"]))
        w(out / (d8 + ".json"), json.dumps({"date": d8, "games": games},
                                           separators=(",", ":")))
        summary.append({"d": d8, "n": len(games)})
        n_dates += 1
    w(SITE / "data" / "dates.json", json.dumps(summary, separators=(",", ":")))

    js = (js_const("DATES_JSON", summary)
          + js_const("BOX_SEASONS", box_seasons)
          + js_const("RAWJSON", RAW_URL)
          + EXHIB_JS
          + """
const TEAMS_JSON_URL = 'data/teams.json';
let TEAMS = {};
const inp = document.getElementById('date'), tbl = document.getElementById('tbl'),
      ld = document.getElementById('load'), cnt = document.getElementById('count');
const POS = {}; DATES_JSON.forEach((d, i) => POS[d.d] = i);
fetch(TEAMS_JSON_URL).then(r => r.json()).then(t => { for (const x of t) TEAMS[x.id] = x; });
inp.value = __LATEST__; inp.onchange = () => render(); render();
function step(delta) {
  const i = POS[inp.value];
  const j = i == null ? DATES_JSON.length - 1 : (i + delta);
  if (j < 0 || j >= DATES_JSON.length) return;
  inp.value = DATES_JSON[j].d; render();
}
function tname(g, id, rawKey) { return TEAMS[id] ? TEAMS[id].name : (g[rawKey] || id || '—'); }
async function render() {
  const d8 = inp.value;
  if (!d8) return;
  tbl.style.display = 'none'; ld.style.display = '';
  ld.textContent = 'Loading ' + d8 + '…';
  const r = await fetch('data/dates/' + d8 + '.json');
  if (!r.ok) { ld.textContent = 'No games on file for this date.'; cnt.textContent = ''; return; }
  const games = (await r.json()).games;
  ld.style.display = 'none'; tbl.style.display = '';
  cnt.textContent = games.length + ' games';
  tbl.innerHTML = '<thead><tr><th>Time</th><th>Visitor</th><th class=n>vs</th>'
    + '<th class=n>Home</th><th>Div</th><th>Status</th><th>Link</th></tr></thead>';
  for (const g of games) {
    const tr = tbl.insertRow();
    const hasBox = (BOX_SEASONS.indexOf(g.s) >= 0);
    const href = hasBox ? ('games/' + g.s + '/' + g.id + '.html') : (RAWJSON + g.src);
    const div = (TEAMS[g.h] && TEAMS[g.h].division) || '?';
    tr.innerHTML = '<td class=mut>' + (g.t || '') + '</td><td>'
      + (g.v ? '<a href="teams/' + g.v + '.html">' + tname(g, g.v, 'vn') + '</a>' : (g.vn || '—'))
      + '</td><td class=n>' + g.vs + '</td><td class=n>' + g.hs + '</td><td class=mut>'
      + div + '</td><td>' + (g.done ? 'final — ' + g.s : 'sched — ' + g.s)
      + (isExh(TEAMS, g) ? ' <span class=exh>exhibition</span>' : '')
      + '</td><td><a href="' + href + '"' + (hasBox ? '' : ' target=_blank') + '>'
      + (hasBox ? 'box' : 'raw') + '</a></td>';
  }
}
""")
    body = ['<h1>Games by date</h1>', nav(""),
            '<p><button onclick="step(-1)">‹ prev</button> '
            '<input type="date" id="date" class="sel"> '
            '<button onclick="step(1)">next ›</button> <span id="count" class="mut"></span></p>',
            '<p class="mut">Steps jump between dates with games on file. Dates use '
            'the game’s local date as published by each school’s feed.</p>',
            '<table id=tbl style="display:none"></table>',
            '<div id=load class=mut>Loading…</div>',
            '<script>', js.replace("__LATEST__", json.dumps(latest)), '</script>']
    w(SITE / "dates.html", page("Games by date", "".join(body)))
    print("dates: {} date pages, {} summary entries".format(n_dates, len(summary)), flush=True)



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
    latest = None
    for s in box_seasons:
        for rec in load(INDEX / "seasons" / s / "games.json")["games"]:
            d8 = rec.get("d8")
            if d8 and (latest is None or d8 > latest):
                latest = d8
    if latest is None:
        latest = "2026-01-01"  # placeholder; pages fall back to the last date with games

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
    build_dates(teams_list, box_seasons, latest=latest)

    # ---- division browsers -------------------------------------------------
    season_keys = sorted(seasons, reverse=True)
    for shard, label in SHARDS:
        js = (js_const("TEAMS_JSON", teams_list)
              + js_const("SEASONS", season_keys)
              + js_const("CUR", current)
              + js_const("BOX_SEASONS", box_seasons)
              + js_const("SHARD", shard)
              + EXHIB_JS
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
      + (isExh(TEAMS, g) ? ' <span class=exh>exhib.</span>' : '')
      + '</td><td><a href="' + href + '"' + (hasBox ? '' : ' target=_blank') + '>'
      + (hasBox ? 'box' : 'raw') + '</a></td>';
  }
}
""")
        body = ['<h1>{}</h1>'.format(esc(label)), nav(""),
                '<p class="mut">Pick a season to load its schedule. “box” = detail page '
                '(most recent seasons); “raw” = raw archive JSON.</p>',
                '<select class=sel id=season></select>',
                '<table id=tbl style="display:none"></table>',
                '<div id=load class=mut>Loading…</div>',
                '<script>', js_const("RAWJSON", RAW_URL), js, '</script>']
        w(SITE / (shard + ".html"), page(label, "".join(body)))

    # ---- team schedule pages ----------------------------------------------
    team_js = js_const("RAWJSON", RAW_URL) + EXHIB_JS + """
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
      + (home ? g.hs + '–' + g.vs : g.vs + '–' + g.hs) + '</td><td>' + result
      + (isExh(TEAM_ID_TEAMS, g) ? ' <span class=exh>exhib.</span>' : '') + '</td>'
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
                nav("../"),
                '<select class=sel id=season>{}</select>'.format(opts),
                '<table id=tbl style="display:none"></table>',
                '<div id=load class=mut>Loading…</div>']
        js = (js_const("TEAM_ID", tid)
              + js_const("BOX_SEASONS", box_seasons)
              + ("let CUR_TEAM_SEASON = null;\n" if not default else js_const("CUR_TEAM_SEASON", default))
              + team_js)
        w(SITE / "teams" / "{}.html".format(tid),
          page(t["team"], "".join(body) + "<script>" + js + "</script>", nav_html=""))
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
