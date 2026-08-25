"""Build the one-line 'why he's on the radar' for each player."""

DC_THRESHOLD = {"GK": None, "DEF": 10, "MID": 12, "FWD": 12}


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def join(items):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def why(pos, gws):
    """gws: per-gameweek stat dicts for this player, oldest first."""
    played = [g for g in gws if g.get("minutes", 0) > 0]
    if not played:
        return "No minutes yet this season."

    n = len(played)
    mins = [g["minutes"] for g in played]
    pts = [g["total_points"] for g in played]
    goals = sum(g.get("goals_scored", 0) for g in played)
    assists = sum(g.get("assists", 0) for g in played)
    cs = sum(g.get("clean_sheets", 0) for g in played)
    bonus = sum(g.get("bonus", 0) for g in played)
    saves = sum(g.get("saves", 0) for g in played)
    full = sum(1 for m in mins if m >= 88)

    thresh = DC_THRESHOLD.get(pos)
    dc_hits = (sum(1 for g in played if g.get("defensive_contribution", 0) >= thresh)
               if thresh else 0)
    dc_avg = (sum(g.get("defensive_contribution", 0) for g in played) / n) if thresh else 0

    bits = []

    if n == 1:
        m = mins[0]
        bits.append("90 minutes on his only start" if m >= 88
                    else f"{m} minutes off the bench" if m < 60
                    else f"{m} minutes")
    elif full == n:
        bits.append(f"90 minutes in all {n}")
    elif full >= n - 1:
        bits.append(f"{full} full games from {n}")
    else:
        bits.append(f"{sum(mins)//n} minutes a game across {n}")

    total = sum(pts)
    bits.append(f"averaging {total/n:.1f} points" if n >= 3
                else f"{total} {plural(total, 'point')}")

    src = []
    if goals:
        src.append(f"{goals} {plural(goals, 'goal')}")
    if assists:
        src.append(f"{assists} {plural(assists, 'assist')}")
    if cs and pos in ("GK", "DEF"):
        src.append(f"{cs} clean {plural(cs, 'sheet')}")
    if pos == "GK" and saves >= 4 * n:
        src.append(f"{saves} saves")
    if src:
        bits.append(join(src))
    if bonus:
        bits.append(f"{bonus} bonus")

    line = ", ".join(bits) + "."

    tail = None
    if thresh and dc_hits == n and n >= 2:
        tail = (f"Cleared the {thresh}-action defensive threshold in every game "
                f"— {dc_avg:.0f} a match. That is 2 points a week before he does "
                f"anything at the other end.")
    elif thresh and dc_hits == n == 1:
        role = "defender" if pos == "DEF" else "holding midfielder"
        tail = (f"Cleared the {thresh}-action defensive threshold with {dc_avg:.0f}, "
                f"the {role} profile that scores without needing a clean sheet. "
                f"One game is not a pattern yet.")
    elif thresh and dc_hits and dc_hits < n:
        tail = f"Cleared the defensive threshold in {dc_hits} of {n}."
    elif goals + assists >= n and n >= 2:
        tail = "Involved in a goal in every game he has played."
    elif full == n and n >= 4:
        tail = "Never been substituted — the minutes are not in doubt."

    return line + (" " + tail if tail else "")
