"""Render index.html for GitHub Pages. Runs hourly on GitHub's own servers.

Every section is computed from data/*.json. Nothing is hand-written and nothing
needs a Claude session, so the page cannot go stale or half-updated. Judgement
calls (chip strategy, transfer reasoning) deliberately live elsewhere.
"""
import json, os, html, datetime as dt
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
D = "data"
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
DC_THRESHOLD = {"GK": 999, "DEF": 10, "MID": 12, "FWD": 12}


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
played = max(0, gw - 1)
deadline = dg["next_deadline_utc"]
dl_uk = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00")).astimezone(UK)
squad = dg["squad"]
mine = {s["name"] for s in squad}
eh = dg.get("entry_history") or {}

xi = sorted([s for s in squad if not s["on_bench"]], key=lambda s: POS_ORDER[s["pos"]])
bench = [s for s in squad if s["on_bench"]]

leagues = dg.get("mini_leagues") or []
fellas = next((l for l in leagues if l["name"] == "Fellas League"), None)
others = [l for l in leagues if l is not fellas]
me_row = next((r for r in (fellas or {}).get("table", [])
               if "Makélélé" in (r["team"] or "")), None)

hist = {}
for g in range(1, gw + 1):
    for e in (load(f"live_gw{g}.json") or {}).get("elements", []):
        st = e.get("stats") or {}
        if st.get("minutes", 0):
            hist.setdefault(e["id"], []).append(st)


def tot(eid, key):
    return sum(h.get(key, 0) for h in hist.get(eid, []))


def dc_hits(eid, pos):
    t = DC_THRESHOLD.get(pos, 999)
    return sum(1 for h in hist.get(eid, []) if h.get("defensive_contribution", 0) >= t)


def yours(e):
    return ' <span class="yours">yours</span>' if e["web_name"] in mine else ""


def cell(e, extra=""):
    return (f'<td class="who"><span class="nm">{esc(e["web_name"])}</span>'
            f'<span class="club">{esc(teams[e["team"]])} · {POS[e["element_type"]]}'
            f'{extra}</span></td>')


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
    return "\n".join(
        f'<tr class="{"me" if "Makélélé" in (r["team"] or "") else ""}">'
        f'<td class="num rank">{esc(r["rank"])}</td>'
        f'<td class="who"><span class="nm">{esc(r["team"])}</span>'
        f'<span class="club">{esc(r["player"])}</span></td>'
        f'<td class="num tot">{esc(r["total"])}</td></tr>'
        for r in lg["table"][:limit])


# ---- price watch ---------------------------------------------------------
movers = sorted(boot["elements"],
                key=lambda e: -(e["transfers_in_event"] - e["transfers_out_event"]))


def mover_row(e, rising):
    net = e["transfers_in_event"] - e["transfers_out_event"]
    chg = e["cost_change_event"]
    badge = (f'<span class="delta up">+{chg / 10:.1f}</span>' if chg > 0
             else f'<span class="delta down">{chg / 10:.1f}</span>' if chg < 0 else "")
    return (f'<tr>{cell(e, yours(e))}'
            f'<td class="num money">{e["now_cost"] / 10:.1f}{badge}</td>'
            f'<td class="num own">{float(e["selected_by_percent"]):.1f}<span class="pc">%</span></td>'
            f'<td class="num net {"up" if rising else "down"}">'
            f'{"+" if net > 0 else ""}{net:,}</td></tr>')


risers = "\n".join(mover_row(e, True) for e in movers[:6])
fallers = "\n".join(mover_row(e, False) for e in reversed(movers[-6:]))

# ---- league differentials ------------------------------------------------
league_owned = {x["name"] for x in dg.get("league_ownership", [])}
n_rivals = dg.get("rival_count", 0)

diffs = []
for eid, h in hist.items():
    e = els.get(eid)
    if not e or e["web_name"] in mine or e["web_name"] in league_owned:
        continue
    if e["status"] != "a":
        continue
    pts = tot(eid, "total_points")
    if pts < max(6, 3 * played):
        continue
    diffs.append((pts, e, POS[e["element_type"]], len(h)))
diffs.sort(key=lambda x: -x[0])

diff_rows = "\n".join(
    f'<tr>{cell(e)}'
    f'<td class="num money">{e["now_cost"] / 10:.1f}</td>'
    f'<td class="num own">{float(e["selected_by_percent"]):.1f}<span class="pc">%</span></td>'
    f'<td class="num">{apps}</td>'
    f'<td class="num">{tot(e["id"], "goals_scored")}</td>'
    f'<td class="num">{tot(e["id"], "assists")}</td>'
    f'<td class="num">{tot(e["id"], "bonus")}</td>'
    f'<td class="num">{dc_hits(e["id"], pos) or "—"}</td>'
    f'<td class="num pts good">{pts}</td></tr>'
    for pts, e, pos, apps in diffs[:10])

# ---- leaderboards --------------------------------------------------------
qualified = [e for e in boot["elements"] if e["minutes"] >= max(60, 45 * played)]


def board(rows, valfmt):
    return "\n".join(f'<tr>{cell(e, yours(e))}'
                     f'<td class="num money">{e["now_cost"] / 10:.1f}</td>'
                     f'<td class="num pts good">{valfmt(e)}</td></tr>' for e in rows)


top_pts = board(sorted(boot["elements"], key=lambda e: -e["total_points"])[:8],
                lambda e: e["total_points"])
top_p90 = board(sorted(qualified, key=lambda e: -(e["total_points"] / (e["minutes"] / 90)))[:8],
                lambda e: f'{e["total_points"] / (e["minutes"] / 90):.1f}')
top_val = board(sorted(qualified, key=lambda e: -(e["total_points"] / (e["now_cost"] / 10)))[:8],
                lambda e: f'{e["total_points"] / (e["now_cost"] / 10):.1f}')

# ---- xG signals ----------------------------------------------------------
att = [e for e in boot["elements"]
       if e["minutes"] >= max(60, 45 * played) and float(e["expected_goal_involvements"]) > 0.3]


def xg_row(e):
    ga = e["goals_scored"] + e["assists"]
    xgi = float(e["expected_goal_involvements"])
    d = ga - xgi
    return (f'<tr>{cell(e, yours(e))}'
            f'<td class="num money">{e["now_cost"] / 10:.1f}</td>'
            f'<td class="num">{ga}</td><td class="num">{xgi:.2f}</td>'
            f'<td class="num delta {"up" if d > 0 else "down"}">{d:+.2f}</td></tr>')


def xgdiff(e):
    return (e["goals_scored"] + e["assists"]) - float(e["expected_goal_involvements"])


over = "\n".join(xg_row(e) for e in sorted(att, key=lambda e: -xgdiff(e))[:5])
under = "\n".join(xg_row(e) for e in sorted(att, key=xgdiff)[:5])

# ---- rival watch ---------------------------------------------------------
# Only the Fellas League — rival_squads spans all three private leagues and
# their ranks are per-league, so mixing them would produce a nonsense table.
fellas_names = {r["team"] for r in (fellas or {}).get("table", [])}
rivals = sorted([r for r in (dg.get("rival_squads") or [])
                 if r.get("team") in fellas_names],
                key=lambda r: r.get("rank") or 99)
# Take rank from the CURRENT league table, not the snapshot inside
# rival_squads, which can lag and disagree with the table above.
fellas_rank = {r["team"]: r["rank"] for r in (fellas or {}).get("table", [])}
rivals = sorted(rivals, key=lambda r: fellas_rank.get(r.get("team"), 99))

rival_rows = "\n".join(
    f'<tr class="{"me" if "Makélélé" in (r.get("team") or "") else ""}">'
    f'<td class="num rank">{esc(fellas_rank.get(r.get("team"), "—"))}</td>'
    f'<td class="who"><span class="nm">{esc(r.get("team"))}</span>'
    f'<span class="club">{esc(r.get("manager"))}</span></td>'
    f'<td class="num tot">{esc(r.get("total"))}</td>'
    f'<td class="capt">{esc(r.get("captain") or "—")}</td>'
    f'<td class="diffs">{esc(", ".join((r.get("differentials_vs_me") or [])[:6]) or "—")}</td></tr>'
    for r in rivals[:12])

# ---- set pieces ----------------------------------------------------------
sp_rows = []
for tid in sorted(teams, key=lambda t: teams[t]):
    def first(order_key):
        c = [e for e in boot["elements"]
             if e["team"] == tid and e.get(order_key) == 1]
        return esc(c[0]["web_name"]) if c else "—"
    sp_rows.append(f'<tr><th class="team">{esc(teams[tid])}</th>'
                   f'<td>{first("penalties_order")}</td>'
                   f'<td>{first("direct_freekicks_order")}</td>'
                   f'<td>{first("corners_and_indirect_freekicks_order")}</td></tr>')

# ---- fixtures ------------------------------------------------------------
# All 20 clubs, not only the ones we own: the differential, leaderboard and
# price-watch tables are full of players elsewhere, and their fixtures matter
# just as much when judging a transfer. Kindest run first.
my_teams = {s["team"] for s in squad}
allfx = dg.get("fixtures_next_6") or {}


def avg_fdr(t):
    fx = allfx.get(t, [])[:6]
    return sum(f["difficulty"] for f in fx) / len(fx) if fx else 9


fx_rows = []
for t in sorted(allfx, key=lambda t: (avg_fdr(t), t)):
    fx = allfx.get(t, [])[:6]
    cells = "".join(f'<td class="fx f{f["difficulty"]}"><span class="opp">{esc(f["opp"])}</span>'
                    f'<span class="ha">{f["ha"]}</span></td>' for f in fx)
    cells += '<td class="fx empty"></td>' * (6 - len(fx))
    own = ' <span class="dot"></span>' if t in my_teams else ""
    fx_rows.append(f'<tr class="{"ownteam" if t in my_teams else ""}">'
                   f'<th class="team">{esc(t)}{own}</th>{cells}'
                   f'<td class="num avg">{avg_fdr(t):.1f}</td></tr>')
fx_head = "".join(f"<th>GW{gw + i}</th>" for i in range(6)) + '<th class="num">Avg</th>' 

# ---- assemble ------------------------------------------------------------
css = open(_find("style.css")).read()
now = dt.datetime.now(dt.timezone.utc)
gap = ((fellas["table"][0]["total"] - me_row["total"]) if me_row and fellas else 0)
others_html = "\n".join(
    f'<div class="minitable"><h4>{esc(l["name"])}</h4>'
    f'<table class="tbl mini"><tbody>{league_table(l, 5)}</tbody></table></div>'
    for l in others)

tpl = open(_find("template.html")).read()
for k, v in {
    "T0": css, "T1": deadline, "T2": gw,
    "T3": dl_uk.strftime("%a %-d %b · %H:%M"),
    "T5": eh.get("total_points", 0), "T6": played,
    "T7": "" if played == 1 else "s",
    "T8": f'{eh.get("overall_rank") or 0:,}',
    "T9": me_row["rank"] if me_row else "—",
    "T10": len((fellas or {}).get("table", [])), "T11": gap,
    "T12": f'{(eh.get("value") or 1000) / 10:.1f}',
    "T13": f'{(eh.get("bank") or 0) / 10:.1f}',
    "T14": "\n".join(player_row(s) for s in xi),
    "T15": "\n".join(player_row(s, True) for s in bench),
    "T16": league_table(fellas) if fellas else "",
    "T17": others_html, "T18": fx_head, "T19": "\n".join(fx_rows),
    "T20": risers, "T21": fallers, "T22": diff_rows, "T23": n_rivals,
    "T24": top_pts, "T25": top_p90, "T26": top_val,
    "T27": over, "T28": under, "T29": rival_rows,
    "T30": "\n".join(sp_rows),
    "T31": now.strftime("%d %b %Y, %H:%M"),
}.items():
    tpl = tpl.replace("%%" + k + "%%", str(v))

open("index.html", "w").write(tpl)
print(f"index.html: {len(tpl)} bytes | gw{gw} | {len(diffs)} differentials | "
      f"{len(rivals)} rivals | {len(sp_rows)} clubs")
