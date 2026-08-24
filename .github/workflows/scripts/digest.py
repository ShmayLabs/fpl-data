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

live = load(f"live_gw{gw}.json") or load(f"live_gw{gw-1}.json")
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
# What the Fellas League actually owns, so differentials can be
