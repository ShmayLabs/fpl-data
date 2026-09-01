"""Build a small digest.json that Claude reads first.

The full bootstrap is ~1.5MB. This distils it to the few KB that actually
matter: the squad's current status, this week's returns, and the state of
the mini-leagues. Small enough to read instantly, complete enough to answer
most questions without touching the big files.
"""
import json, os, datetime

D = "data"
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def load(name):
    try:
        with open(os.path.join(D, name)) as f:
            return json.load(f)
    except Exception:
        return None


boot = load("bootstrap.json")
if boot is None:
    raise SystemExit("no bootstrap; nothing to digest")

teams = {t["id"]: t["short_name"] for t in boot["teams"]}
els = {e["id"]: e for e in boot["elements"]}

events = boot["events"]
nxt = next((e for e in events if e.get("is_next")), None)
cur = next((e for e in events if e.get("is_current")), None)
gw = (nxt or cur or events[0])["id"]

# ---- squad ---------------------------------------------------------------
picks = None
for g in range(gw, 0, -1):
    picks = load(f"picks_gw{g}.json")
    if picks:
        picks_gw = g
        break

live = next((L for L in (load(f"live_gw{gw}.json"), load(f"live_gw{gw-1}.json"))
             if L and L.get("elements")), None)
live_map = {}
if live:
    for e in live.get("elements", []):
        live_map[e["id"]] = e.get("stats", {})

squad = []
if picks:
    for p in picks.get("picks", []):
        e = els.get(p["element"])
        if not e:
            continue
        st = live_map.get(p["element"], {})
        squad.append({
            "name": e["web_name"],
            "team": teams[e["team"]],
            "pos": POS[e["element_type"]],
            "price": e["now_cost"] / 10,
            "owned_by": float(e["selected_by_percent"]),
            "is_captain": p.get("is_captain", False),
            "is_vice": p.get("is_vice_captain", False),
            "on_bench": p.get("multiplier", 1) == 0,
            "status": e["status"],
            "chance_next": e["chance_of_playing_next_round"],
            "news": (e["news"] or "").strip(),
            "gw_points": st.get("total_points"),
            "gw_minutes": st.get("minutes"),
            "form": e["form"],
            "total_points": e["total_points"],
        })

# ---- anyone flagged ------------------------------------------------------
flagged = [s for s in squad
           if s["status"] != "a" or s["news"]
           or (s["chance_next"] is not None and s["chance_next"] < 100)]

# ---- squad alerts --------------------------------------------------------
# The loud, unmissable block. Anything here changes a squad decision RIGHT NOW.
# It sits at the top of the digest so no analysis can proceed without seeing it.
# Club changes matter because the FPL API lags real transfers by days — a player
# can be sold and still show his old club with status "a".
prev = load("prev_squad_teams.json") or {}
alerts = []
for s in squad:
    e = next((x for x in boot["elements"] if x["web_name"] == s["name"]), None)
    if not e:
        continue
    if s["status"] == "u":
        alerts.append(f'UNAVAILABLE: {s["name"]} ({s["team"]}) — {s["news"] or "no longer selectable"}. '
                      f'{"He is on the bench, so this costs nothing per week — replace him when a free transfer is spare, not urgently." if s["on_bench"] else "HE IS IN THE STARTING XI — replace him this week."}')
    elif s["status"] != "a":
        alerts.append(f'FLAGGED: {s["name"]} ({s["team"]}) — {s["news"] or "doubtful"} ({s["chance_next"]}% chance).')
    elif s["news"]:
        alerts.append(f'NEWS: {s["name"]} ({s["team"]}) — {s["news"]}')
    was = prev.get(s["name"])
    if was and was != s["team"]:
        alerts.append(f'CLUB CHANGE: {s["name"]} moved {was} -> {s["team"]}. Fixtures and minutes both change.')
    if e["cost_change_event"] < 0:
        alerts.append(f'PRICE FALL: {s["name"]} dropped £{abs(e["cost_change_event"]) / 10:.1f}m this gameweek.')
    if s["gw_minutes"] == 0 and s["status"] == "a":
        alerts.append(f'ZERO MINUTES: {s["name"]} ({s["team"]}) played no part in the last gameweek despite being available.')

json.dump({s["name"]: s["team"] for s in squad}, open(os.path.join(D, "prev_squad_teams.json"), "w"))

# ---- leagues -------------------------------------------------------------
leagues = []
lg = load("my_leagues.json") or {}
for lid, v in lg.items():
    st = v.get("standings", {})
    rows = st.get("standings", {}).get("results", [])
    # Skip the global auto-join leagues (Overall, England, Arsenal, ...).
    # FPL marks those league_type "s" (system); private leagues are "x".
    if st.get("league", {}).get("league_type") == "s":
        continue
    leagues.append({
        "id": lid,
        "name": v.get("name"),
        "table": [{"rank": r.get("rank"), "team": r.get("entry_name"),
                   "player": r.get("player_name"), "gw": r.get("event_total"),
                   "total": r.get("total")} for r in rows[:25]],
    })

# ---- upcoming fixtures ---------------------------------------------------
fixtures = load("fixtures.json") or []
upcoming = {}
for f in fixtures:
    ev = f.get("event")
    if ev and gw <= ev <= gw + 5:
        for side, opp, diff in (("team_h", "team_a", "team_h_difficulty"),
                                ("team_a", "team_h", "team_a_difficulty")):
            t = teams[f[side]]
            ha = "H" if side == "team_h" else "A"
            upcoming.setdefault(t, []).append(
                {"gw": ev, "opp": teams[f[opp]], "ha": ha, "difficulty": f[diff]})
for t in upcoming:
    upcoming[t].sort(key=lambda x: x["gw"])

# ---- top performers this gameweek ---------------------------------------
top = []
if live_map:
    scored = [(eid, st.get("total_points", 0)) for eid, st in live_map.items()]
    for eid, pts in sorted(scored, key=lambda x: -x[1])[:25]:
        e = els.get(eid)
        if e and pts > 0:
            top.append({"name": e["web_name"], "team": teams[e["team"]],
                        "pos": POS[e["element_type"]], "price": e["now_cost"] / 10,
                        "points": pts, "owned_by": float(e["selected_by_percent"])})

# ---- rival analysis ------------------------------------------------------
# What the Fellas League actually owns, so differentials can be chosen
# against the people we're playing rather than against the whole game.
rivals_raw = load("rivals.json") or {}
mine = {p["element"] for p in (picks or {}).get("picks", [])}
rival_own, rival_caps, rival_squads = {}, {}, []
n_rivals = 0
for eid, r in rivals_raw.items():
    ids = {p["element"] for p in r.get("picks", [])}
    if not ids:
        continue
    n_rivals += 1
    for i in ids:
        rival_own[i] = rival_own.get(i, 0) + 1
    for p in r.get("picks", []):
        if p.get("is_captain"):
            rival_caps[p["element"]] = rival_caps.get(p["element"], 0) + 1
    rival_squads.append({
        "team": r.get("team"), "manager": r.get("manager"),
        "rank": r.get("rank"), "total": r.get("total"), "chip": r.get("chip"),
        "squad": [els[p["element"]]["web_name"] for p in r.get("picks", [])
                  if p["element"] in els],
        "captain": next((els[p["element"]]["web_name"] for p in r.get("picks", [])
                         if p.get("is_captain") and p["element"] in els), None),
        "differentials_vs_me": [els[i]["web_name"] for i in ids - mine if i in els],
    })


def pct(n):
    return round(100.0 * n / n_rivals, 1) if n_rivals else 0.0


league_ownership = sorted(
    ({"name": els[i]["web_name"], "team": teams[els[i]["team"]],
      "pos": POS[els[i]["element_type"]], "price": els[i]["now_cost"] / 10,
      "owned_in_league_pct": pct(n), "owned_globally_pct": float(els[i]["selected_by_percent"]),
      "i_own": i in mine}
     for i, n in rival_own.items() if i in els),
    key=lambda x: -x["owned_in_league_pct"])

hist = load("my_history.json") or {}
digest = {
    "SQUAD_ALERTS_READ_THIS_FIRST": alerts,
    "generated_utc": datetime.datetime.now(datetime.timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ"),
    "next_gw": gw,
    "next_deadline_utc": (nxt or cur or events[0])["deadline_time"],
    "gw_finished": bool((cur or {}).get("finished")),
    "squad_from_gw": picks_gw if picks else None,
    "entry_history": (picks or {}).get("entry_history"),
    "season_history": hist.get("current", []),
    "squad": squad,
    "flagged_players": flagged,
    "mini_leagues": leagues,
    "fixtures_next_6": upcoming,
    "top_scorers_this_gw": top,
    "rival_count": n_rivals,
    "rival_squads": rival_squads,
    "league_ownership": league_ownership,
    "rival_captains": sorted(
        ({"name": els[i]["web_name"], "picked_by_pct": pct(n)}
         for i, n in rival_caps.items() if i in els),
        key=lambda x: -x["picked_by_pct"]),
}

with open(os.path.join(D, "digest.json"), "w") as f:
    json.dump(digest, f, indent=1)

print(f"digest: gw{gw}, {len(squad)} squad, {len(alerts)} ALERTS, {len(flagged)} flagged, "
      f"{len(leagues)} leagues, {len(top)} top scorers")
