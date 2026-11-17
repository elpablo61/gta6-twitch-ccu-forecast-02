"""GTA VI launch-day Twitch forecast (gta6-twitch-ccu-forecast-02).

Second iteration on the v1 entry (gta6-twitch-ccu-forecast-01, practice
score 0.206, rank 1,987 of 4,255). Same task: from the Twitch viewer count
of Grand Theft Auto VI at the end of its release day's first hour, forecast
the count in each of hours 2-24 as five quantiles (5%, 25%, 50%, 75%, 95%),
scored by pinball loss on the log scale.

Method (tuned by leave-one-out over the 38 comparables shipped in the kit;
the practice answers are sealed, so nothing here was tuned on them):

  A launch-day curve is anchored on its hour-1 print. Across past launches
  the later hours' log-levels depend strongly on the log hour-1 level
  (correlation about -0.94 at hour 20): a big hour 1 means the world already
  unlocked and the day stays near that level, a tiny hour 1 means the launch
  wave is still coming and the day explodes. Per hour, the forecast blends
  two views of the same pool of past launches:

  1. Local-linear: weighted least squares of log viewers(hour) on
     log viewers(hour 1) across comparables, Gaussian kernel on the log
     hour-1 distance (bandwidth 1.25), Gaussian residual quantiles whose
     spread is smoothed across neighbouring hours. The centre is never
     extrapolated past the biggest comparable in the pool: if the case's
     hour 1 exceeds every past launch, the centre is evaluated at the
     pool's largest log hour-1 (the kernel weights still use the true
     hour 1, so the biggest launches stay the nearest neighbours).
  2. Ratio quantiles: weighted empirical quantiles of log(viewers(hour) /
     viewers(hour 1)) across comparables, anchored on the case's hour-1
     print. The scale kernel's bandwidth follows the hour: 2.0 in hours
     2-6, 1.5 in hours 7-12, 1.0 in hours 13-24. Early on the ratio barely
     depends on scale (correlation near 0 at hour 3), so the kernel pools
     widely; late in the day the scale dependence is strong (about -0.94
     at hour 20), so it pools tightly. This is the one structural change
     from v1, where the ratio part used a single bandwidth of 1.0.
  3. Blend: 55% (1) + 45% (2) in log space, then every quantile's
     log-distance from its median is tightened by a factor of 0.95.

  Comparables that also launched on PC get a lower weight in the
  local-linear part (0.5 in hours 2-5, 0.15 in hours 6-24): their PC
  unlock, hours after the console unlock, adds a second wave a
  console-only launch never has. GTA VI is console only, so the console
  launches in the pool carry the forecast.

Any hour the pool cannot cover falls back to the house persistence
baseline (flat at hour 1, spread 0.15 * sqrt(h - 1) in log space).

Python 3.13, standard library only: no network, no files outside the case,
no clock, no randomness. Two runs on the same case write the same bytes.
"""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]

# Tuned constants (leave-one-out over the kit's comparables).
BW_LL = 1.25           # scale-kernel bandwidth (log units), local-linear part
BW_RQ_EARLY = 2.0      # ratio-quantile bandwidth, hours 2..6
BW_RQ_MID = 1.5        # ratio-quantile bandwidth, hours 7..12
BW_RQ_LATE = 1.0       # ratio-quantile bandwidth, hours 13..24
W_PC_EARLY = 0.5       # weight of PC-launched comparables, hours 2..5
W_PC_LATE = 0.15       # weight of PC-launched comparables, hours 6..24
PC_HOUR_CUT = 5
BLEND_LL = 0.55        # weight of the local-linear part in the log-space blend
SPREAD_TIGHTEN = 0.95  # shrink each quantile's log-distance from the median
MIN_POOL_HOURS = 12    # a comparable needs hour 1 plus this many of hours 2..24
SIGMA_BASE = 0.15      # fallback (house baseline) log-spread per sqrt hour


def parse_ts(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def round2(x):
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def gauss_kernel(d, bw):
    return math.exp(-0.5 * (d / bw) ** 2)


def bw_rq(hour):
    """Ratio-quantile bandwidth for this hour (wider early, tighter late)."""
    if hour <= 6:
        return BW_RQ_EARLY
    if hour <= 12:
        return BW_RQ_MID
    return BW_RQ_LATE


def wquantile(pairs, tau):
    """Weighted empirical quantile of [(value, weight), ...]."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if acc >= tau * total:
            return value
    return pairs[-1][0]


def wls(xs, ys, ws):
    """Weighted least squares y = a + b*x. Returns (a, b)."""
    sw = sum(ws)
    mx = sum(w * x for x, w in zip(xs, ws)) / sw
    my = sum(w * y for y, w in zip(ys, ws)) / sw
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws))
    sxy = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws))
    b = sxy / sxx if sxx > 1e-12 else 0.0
    return my - b * mx, b


def smooth3(values):
    """3-point moving average over a list (hours 2..24 in order)."""
    out = []
    for i in range(len(values)):
        lo = max(0, i - 1)
        hi = min(len(values), i + 2)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def release_day_curve(comp):
    """{hour 1..24: viewers} for the comparable's UTC release day."""
    try:
        day_start = parse_ts(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return {}
    curve = {}
    for point in comp.get("hourly") or []:
        try:
            viewers = point["viewers"]
            at = parse_ts(point["from"])
        except (KeyError, TypeError, ValueError):
            continue
        if viewers is None or viewers <= 0:
            continue
        hour = int((at - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            curve[hour] = viewers
    return curve


def has_pc(comp):
    return "PC" in (comp.get("platforms") or "")


def build_pool(case):
    """Comparables usable as launch-day shapes: a real hour 1 and most of hours 2..24."""
    pool = []
    for comp in sorted(case.get("comparables") or [], key=lambda c: c.get("name", "")):
        curve = release_day_curve(comp)
        if 1 not in curve:
            continue
        if sum(1 for h in range(2, 25) if h in curve) < MIN_POOL_HOURS:
            continue
        pool.append({"curve": curve, "pc": has_pc(comp)})
    return pool


def local_linear_quantiles(pool, p1):
    """Per hour: WLS of log viewers(h) on log viewers(1); Gaussian residual quantiles.

    The centre is evaluated at the log hour-1 level capped at the pool's
    largest log hour-1, so a case bigger than every past launch does not
    ride the fitted line off the end of the data.
    """
    lx = math.log(max(p1, 1))
    cap = max(math.log(entry["curve"][1]) for entry in pool)
    lx_eval = min(lx, cap)
    centers = {}
    sigmas = {}
    for h in range(2, 25):
        xs, ys, ws = [], [], []
        for entry in pool:
            curve = entry["curve"]
            if h in curve and curve[1] > 0:
                xs.append(math.log(curve[1]))
                ys.append(math.log(curve[h]))
                w = max(gauss_kernel(math.log(curve[1]) - lx, BW_LL), 1e-6)
                if entry["pc"]:
                    w *= W_PC_EARLY if h <= PC_HOUR_CUT else W_PC_LATE
                ws.append(w)
        if len(xs) < 5:
            continue
        a, b = wls(xs, ys, ws)
        resid = [y - (a + b * x) for x, y in zip(xs, ys)]
        sw = sum(ws)
        mean_r = sum(w * r for r, w in zip(resid, ws)) / sw
        var = sum(w * (r - mean_r) ** 2 for r, w in zip(resid, ws)) / sw
        centers[h] = a + b * lx_eval
        sigmas[h] = math.sqrt(max(var, 1e-4))
    hours = sorted(centers)
    sig_smooth = smooth3([sigmas[h] for h in hours])
    out = {}
    for h, sg in zip(hours, sig_smooth):
        out[h] = [math.exp(centers[h] + z * sg) for z in Z]
    return out


def ratio_quantiles(pool, p1):
    """Per hour: weighted empirical quantiles of log(viewers(h) / viewers(1))."""
    lx = math.log(max(p1, 1))
    out = {}
    for h in range(2, 25):
        pairs = []
        for entry in pool:
            curve = entry["curve"]
            if h in curve and curve[1] > 0:
                w = max(gauss_kernel(math.log(curve[1]) - lx, bw_rq(h)), 1e-6)
                pairs.append((math.log(curve[h] / curve[1]), w))
        if len(pairs) < 3:
            continue
        out[h] = [max(1.0, p1 * math.exp(wquantile(pairs, tau))) for tau in LEVELS]
    return out


def baseline_quantiles(p1, h):
    """House persistence baseline: flat at hour 1, spread widening in log space."""
    return [max(1.0, p1 * math.exp(z * SIGMA_BASE * math.sqrt(h - 1))) for z in Z]


def tighten_spread(quantiles):
    """Multiply each quantile's log-distance from the median by SPREAD_TIGHTEN."""
    median = quantiles[2]
    log_med = math.log(median)
    return [max(1.0, median * math.exp(SPREAD_TIGHTEN * (math.log(max(q, 1e-9)) - log_med)))
            for q in quantiles]


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    pool = build_pool(case)
    ll = local_linear_quantiles(pool, p1)
    rq = ratio_quantiles(pool, p1)
    rows = []
    # Sort by hour: the case lists hours 2..24 in order, but the output must
    # not depend on the file's row order.
    for row in sorted(case["forecast"], key=lambda r: r["hour"]):
        h = row["hour"]
        if h in ll and h in rq:
            qs = [math.exp(BLEND_LL * math.log(a) + (1 - BLEND_LL) * math.log(b))
                  for a, b in zip(ll[h], rq[h])]
        elif h in ll:
            qs = ll[h]
        elif h in rq:
            qs = rq[h]
        else:
            qs = baseline_quantiles(p1, h)
        qs = tighten_spread(qs)
        # Round to 2 decimals, keep non-decreasing, keep inside (0, 1e9].
        rounded = []
        prev = 0.0
        for q in qs:
            value = round2(min(max(q, 0.01), 1e9))
            if value <= prev:
                value = prev if prev > 0 else value
            rounded.append(value)
            prev = value
        rows.append({"hour": h, "q": rounded})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
