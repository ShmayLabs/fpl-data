"""Render index.html for GitHub Pages from the data the Action just pulled."""
import json, os, html, datetime as dt
from zoneinfo import ZoneInfo
from why import why

UK = ZoneInfo("Europe/London")
D = "data"
POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def load(name):
    try:
        return json.load(open(os.path.join(D, name)))
    except Exception:
        return None


def esc(s):
    return html.escape(str(s if s is not None else ""))


def _find(name):
    for p in (os.path.join("scripts", name), name):
        if os.path.exists(p):
            return p
    raise SystemExit("missing " + name)


boot = load("bootstrap.json")
dg = load("digest.json")
if not boot or not dg:
    raise SystemExit("missing data; nothing to render")

teams = {t["id"]: t["short_name"] for t in boot["teams"]}
els = {e["id"]: e for e in boot["elements"]}
gw = dg["next_gw"]
deadline = dg["next_deadline_utc"]
dl_uk = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00")).astimezone(UK)
squad = dg["squad"]
mine = {s["name"] for s in squad}

xi = sorted([s for s in squad if not s["on_bench"]], key=lambda s: POS_ORDER[s["pos"]])
bench = [s for s in squad if s["on_bench"]]

leagues = dg.get("mini_leagues") or []
fellas = next((l for l in leagues if l["name"] == "Fellas League"), None)
others = [l for l in leagues if l is not fellas]
me_row = next((r for r in (fellas or {}).get("table", [])
               if "Makélélé" in (r["team"] or "")), None)
eh = dg.get("entry_history") or {}


def player_row(s, benched=False):
    mark = ('<span class="armband">C</span>' if s["is_captain"]
            else '<span class="armband vc">V</span>' if s["is_vice"] else "")
    flag = (f'<span class="flag" title="{esc(s["news"] or "Flagged")}">!</span>'
            if s["status"] != "a" or s["news"] else "")
    p = s["gw_points"]
    cls = "pts" + (" good" if p and p >= 6 else " poor" if p is not None and p <= 1 else "")
    mins = f'{s["gw_minutes"]}′' if s["gw_minutes"] is not None else "—"
    return (f'<tr class="{"benched" if benched else ""}">'
            f'<td><span class="poschip">{s["pos"]}</span></td>'
            f'<td class="who"><span class="nm">{esc(s["name"])}{mark}{flag}</span>'
            f'<span class="club">{esc(s["team"])}</span></td>'
            f'<td class="num money">{s["price"]:.1f}</td>'
            f'<td class="num own">{s["owned_by"]:.1f}<span class="pc">%</span></td>'
            f'<td class="num mins">{mins}</td>'
            f'<td class="num {cls}">{p if p is not None else "—"}</td></tr>')


def league_table(lg, limit=11):
    out = []
    for r in lg["table"][:limit]:
        me = "Makélélé" in (r["team"] or "")
        out.append(f'<tr class="{"me" if me else ""}">'
                   f'<td class="num rank">{esc(r["rank"])}</td>'
                   f'<td class="who"><span class="nm">{esc(r["team"])}</span>'
                   f'<span class="club">{esc(r["player"])}</span></td>'
                   f'<td class="num tot">{esc(r["total"])}</td></tr>')
    return "\n".join(out)


gw_stats = {}
for g in range(1, gw + 1):
    live = load(f"live_gw{g}.json")
    for e in (live or {}).get("elements", []):
        st = e.get("stats") or {}
        if st.get("minutes", 0) or st.get("total_points", 0):
            gw_stats.setdefault(e["id"], []).append(st)

radar = []
for eid, hist in gw_stats.items():
    e = els.get(eid)
    if not e or e["web_name"] in mine:
        continue
    if float(e["selected_by_percent"]) >= 12.0 or e["status"] != "a":
        continue
    total = sum(h.get("total_points", 0) for h in hist)
    if total < 8:
        continue
    pos = POS[e["element_type"]]
    radar.append({"name": e["web_name"], "team": teams[e["team"]], "pos": pos,
                  "price": e["now_cost"] / 10,
                  "own": float(e["selected_by_percent"]),
                  "points": total, "why": why(pos, hist)})
radar.sort(key=lambda r: -r["points"])
radar = radar[:10]

radar_rows = "\n".join(
    f'<tr><td class="who"><span class="nm">{esc(r["name"])}</span>'
    f'<span class="club">{esc(r["team"])} · {r["pos"]}</span></td>'
    f'<td class="num money">{r["price"]:.1f}</td>'
    f'<td class="num own">{r["own"]:.1f}<span class="pc">%</span></td>'
    f'<td class="num pts good">{r["points"]}</td></tr>'
    f'<tr class="whyrow"><td colspan="4">{esc(r["why"])}</td></tr>' for r in radar)

my_teams = sorted({s["team"] for s in squad})
fx_rows = []
for t in my_teams:
    fx = (dg.get("fixtures_next_6") or {}).get(t, [])[:6]
    cells = "".join(f'<td class="fx f{f["difficulty"]}"><span class="opp">{esc(f["opp"])}</span>'
                    f'<span class="ha">{f["ha"]}</span></td>' for f in fx)
    cells += '<td class="fx empty"></td>' * (6 - len(fx))
    fx_rows.append(f'<tr><th class="team">{esc(t)}</th>{cells}</tr>')

fx_head = "".join(f"<th>GW{gw + i}</th>" for i in range(6))

CHIPS = [
    ("Wildcard 1", "set one", "GW7-9", "Free rebuild. Held until the fixture picture past the first international break is clear."),
    ("Triple Captain 1", "set one", "GW13-18", "Needs a premium with a soft home fixture and no rotation risk."),
    ("Bench Boost 1", "set one", "GW15-18", "Only pays if the bench starts. Prep from GW7: swap non-players for nailed-on cheap starters."),
    ("Free Hit 1", "set one", "GW18-19", "Held for a blank or congested week. Spent by GW19 regardless."),
    ("Wildcard 2", "set two", "GW28-30", "Second-half reset, aimed at the doubles that decide mini-leagues."),
    ("Free Hit 2", "set two", "on a blank", "The natural answer to a blank gameweek in the cup rounds."),
    ("Bench Boost 2", "set two", "biggest double", "Held for a double gameweek where all 15 play twice."),
    ("Triple Captain 2", "set two", "biggest double", "A premium with two fixtures - the highest-scoring play in the game."),
]
chip_rows = "\n".join(
    f'<tr class="{"setone" if s == "set one" else "settwo"}">'
    f'<td class="who"><span class="nm">{esc(n)}</span><span class="club">{esc(s)}</span></td>'
    f'<td class="num window">{esc(w)}</td><td class="prep">{esc(p)}</td></tr>'
    for n, s, w, p in CHIPS)

css = open(_find("style.css")).read()
now = dt.datetime.now(dt.timezone.utc)
gap = ((fellas["table"][0]["total"] - me_row["total"]) if me_row else 0)

others_html = "\n".join(
    f'<div class="minitable"><h4>{esc(l["name"])}</h4>'
    f'<table class="tbl mini"><tbody>{league_table(l, 5)}</tbody></table></div>'
    for l in others)

tpl = open(_find("template.html")).read()
for k, v in {
    "T0": css,
    "T1": deadline,
    "T2": gw,
    "T3": dl_uk.strftime("%a %-d %b · %H:%M"),
    "T4": dl_uk.strftime("%a %-d %b · %H:%M"),
    "T5": eh.get("total_points", 0),
    "T6": gw - 1,
    "T7": "s" if gw - 1 != 1 else "",
    "T8": format(eh.get("overall_rank") or 0, ","),
    "T9": me_row["rank"] if me_row else "—",
    "T10": len((fellas or {}).get("table", [])),
    "T11": gap,
    "T12": format((eh.get("value") or 1000) / 10, ".1f"),
    "T13": format((eh.get("bank") or 0) / 10, ".1f"),
    "T14": chr(10).join(player_row(s) for s in xi),
    "T15": chr(10).join(player_row(s, True) for s in bench),
    "T16": league_table(fellas) if fellas else "",
    "T17": others_html,
    "T18": fx_head,
    "T19": chr(10).join(fx_rows),
    "T20": radar_rows,
    "T21": chip_rows,
    "T22": now.strftime("%d %b %Y, %H:%M"),
}.items():
    tpl = tpl.replace("%%" + k + "%%", str(v))

open("index.html", "w").write(tpl)
print(f"index.html: {len(tpl)} bytes, gw{gw}, {len(squad)} squad, {len(radar)} radar")
