"""Hour-by-hour Twitch viewer forecast for Grand Theft Auto VI's launch day.

The case file gives one thing about launch day itself: the Twitch viewer
count for the "Grand Theft Auto VI" category in hour 1 (00:00-01:00 UTC on
19 Nov 2026). Everything else the program knows comes from the comparables:
the release-day hourly curves of past big game launches shipped in the case.

For each hour h = 2..24 the program forecasts five quantiles (5%, 25%, 50%,
75%, 95%) of that hour's concurrent viewers, as a blend of two views of the
same comparables:

1. A local-linear view. Regress log viewers(h) on log viewers(1) across the
   comparables, weighted by a Gaussian kernel in log hour-1 (width 1.25) that
   is centred on this case's own hour-1 print. The centre is capped at the
   largest hour-1 in the pool, so when GTA VI opens bigger than every past
   launch the fit never extrapolates a straight line past the data. The fitted
   value at the centre is the median; the weighted spread of the residuals
   around that fit gives the other quantiles through normal z-scores.

2. A ratio view. Take the weighted empirical quantiles of the ratio
   viewers(h) / viewers(1) across the comparables, with the same kind of
   kernel but a width that narrows as launch day goes on (2.0 early, 1.5 in
   the middle, 1.0 late), then multiply back by this case's hour-1 print.

The two views are averaged 55% / 45% in log space, and the spread of the
result around its median is shrunk by a factor 0.95.

Launches that also shipped on PC are downweighted, because their day-one
curves mix a staggered PC unlock with the console midnight launch: factor
0.5 for hours 2-5, 0.15 from hour 6 on.

Standard library only, deterministic, no network. Reads every <id>.in in the
input directory and writes <id>.out next to it in the output directory:
{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader runs with -P, which leaves this file's directory off sys.path;
# put it back so a helper module shipped beside this file could be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
NORMAL_Q = [-1.645, -0.674, 0.0, 0.674, 1.645]

LOCAL_BW = 1.25            # kernel width for the local-linear view, log units
BLEND_LOCAL = 0.55         # weight of the local-linear view in the log blend
SPREAD_KEEP = 0.95         # shrink factor on the blended quantile spread
# Which view the PC downweight applies to: "ll", "rq" or "both". A PC launch's
# day-one curve mixes a staggered PC unlock with the console midnight launch,
# so its comparables count less -- but only where the downweight helps.
PC_SCOPE = "ll"
# (first hour, last hour, kernel width) for the ratio view's bandwidth.
RATIO_BANDS = ((2, 5, 2.0), (6, 12, 1.5), (13, 24, 1.0))
PERSIST_SIGMA = 0.15       # fallback spread only, if the pool is unusable


def _parse_time(text):
    """An ISO timestamp with a Z suffix, as a datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_curve(comp):
    """A comparable's release-day curve as {hour: viewers} for hours 1..24.

    The comparable's hourly rows span the days around its launch; the release
    day starts at the comparable's day_start. A row belongs to hour h when it
    falls in [day_start + (h-1)h, day_start + h h). Hours with no positive
    viewer count are left out.
    """
    start = _parse_time(comp["day_start"])
    curve = {}
    for row in comp.get("hourly", []):
        viewers = row.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        stamp = row.get("from")
        if stamp is None:
            continue
        hour = int((_parse_time(stamp) - start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24 and hour not in curve:
            curve[hour] = viewers
    return curve


def _pc_factor(comp, hour):
    """Downweight for a launch that also shipped on PC (staggered unlock)."""
    if "PC" not in (comp.get("platforms") or ""):
        return 1.0
    return 0.5 if hour <= 5 else 0.15


def _kernel(distance, width):
    """Gaussian kernel weight for a log-distance from the centre."""
    return math.exp(-0.5 * (distance / width) ** 2)


def _ratio_bandwidth(hour):
    """The ratio view's kernel width for this hour of launch day."""
    for first, last, width in RATIO_BANDS:
        if first <= hour <= last:
            return width
    return RATIO_BANDS[-1][2]


def _local_fit(xs, ys, ws, centre):
    """Weighted straight-line fit of y on (x - centre).

    Returns (fitted value at the centre, weighted residual standard
    deviation), or None when the weights carry nothing.
    """
    total = sum(ws)
    if total <= 0:
        return None
    dxs = [x - centre for x in xs]
    s0 = total
    s1 = sum(w * d for w, d in zip(ws, dxs))
    s2 = sum(w * d * d for w, d in zip(ws, dxs))
    t0 = sum(w * y for w, y in zip(ws, ys))
    t1 = sum(w * d * y for w, d, y in zip(ws, dxs, ys))
    denom = s0 * s2 - s1 * s1
    slope = (s0 * t1 - s1 * t0) / denom if abs(denom) > 1e-12 else 0.0
    value = (t0 - slope * s1) / s0
    var = sum(w * (y - (value + slope * d)) ** 2
              for w, d, y in zip(ws, dxs, ys)) / s0
    return value, math.sqrt(var) if var > 0 else 0.0


def _weighted_quantile(pairs, tau):
    """Smallest value whose cumulative weight reaches tau of the total."""
    ordered = sorted(pairs, key=lambda p: p[0])
    total = sum(w for _, w in ordered)
    if total <= 0:
        return None
    target = tau * total
    running = 0.0
    for value, w in ordered:
        running += w
        if running >= target:
            return value
    return ordered[-1][0]


def _round2(x):
    """x rounded to 2 decimals, halves up; whole numbers come back as ints."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if value == int(value) else value


def _persistence(p1, hour):
    """Fallback forecast: hour 1's print with a widening log spread.

    Only used when the comparable pool cannot support an hour at all; in
    practice the pool always covers it.
    """
    spread = PERSIST_SIGMA * math.sqrt(hour - 1)
    return [_round2(p1 * math.exp(z * spread)) for z in NORMAL_Q]


def _hour_forecast(pool, p1, log_p1, centre, hour):
    """The five quantiles for one hour, blended from the two views."""
    xs, ys, w_local, ratios = [], [], [], []
    ratio_bw = _ratio_bandwidth(hour)
    for comp, curve in pool:
        if hour not in curve:
            continue
        x = math.log(curve[1])
        factor = _pc_factor(comp, hour)
        xs.append(x)
        ys.append(math.log(curve[hour]))
        w_local.append(_kernel(x - centre, LOCAL_BW)
                       * (factor if PC_SCOPE in ("ll", "both") else 1.0))
        ratios.append((curve[hour] / curve[1],
                       _kernel(x - centre, ratio_bw)
                       * (factor if PC_SCOPE in ("rq", "both") else 1.0)))
    fit = _local_fit(xs, ys, w_local, centre) if len(xs) >= 3 else None
    if fit is None or sum(w for _, w in ratios) <= 0:
        return _persistence(p1, hour)
    centre_value, resid_sd = fit
    local_log = [centre_value + z * resid_sd for z in NORMAL_Q]
    ratio_log = []
    for tau in LEVELS:
        r = _weighted_quantile(ratios, tau)
        ratio_log.append(log_p1 + math.log(r if r and r > 0 else 1e-9))
    blended = [BLEND_LOCAL * a + (1.0 - BLEND_LOCAL) * b
               for a, b in zip(local_log, ratio_log)]
    median = blended[2]
    shrunk = [median + SPREAD_KEEP * (v - median) for v in blended]
    out = []
    floor = 0.0
    for v in shrunk:
        q = _round2(math.exp(v))
        q = min(max(q, 0.01), 1e9)
        if q < floor:
            q = floor
        floor = q
        out.append(q)
    return out


def forecast_case(case, name):
    """Forecast one case: {"hours": [{"hour": h, "q": [...]}, ...]}."""
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    log_p1 = math.log(p1)
    pool = []
    for comp in case.get("comparables", []):
        curve = release_day_curve(comp)
        if 1 in curve and curve[1] > 0:
            pool.append((comp, curve))
    if pool:
        # No linear extrapolation past the biggest launch in the pool.
        top = max(math.log(curve[1]) for _, curve in pool)
        centre = min(log_p1, top)
    else:
        centre = log_p1
    rows = []
    for row in case["forecast"]:
        hour = row["hour"]
        if pool:
            q = _hour_forecast(pool, p1, log_p1, centre, hour)
        else:
            q = _persistence(p1, hour)
        rows.append({"hour": hour, "q": q})
    rows.sort(key=lambda r: r["hour"])
    return {"hours": rows}


def main():
    """Forecast every case file in the input directory, in name order."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / (path.stem + ".out")).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
