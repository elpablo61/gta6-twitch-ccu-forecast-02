# gta6-twitch-ccu-forecast-02 — Launch-day curve forecaster, v2

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/elpablo61/gta6-twitch-ccu-forecast-02/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/elpablo61/gta6-twitch-ccu-forecast-02/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A forecaster for the
[make.fun gta6-twitch-ccu-forecast-01 bounty](https://make.fun/bounty/gta6-twitch-ccu-forecast-01): from the Twitch viewer count of Grand Theft Auto VI at the end of its release day's first hour, forecast the count in each of hours 2–24 as five quantiles (5%, 25%, 50%, 75%, 95%), scored by pinball loss on the log scale.

Second iteration on [v1](https://github.com/elpablo61/gta6-twitch-ccu-forecast-01) (practice score 0.206, rank 1,987 of 4,255). The final is the real GTA VI launch day, a fresh case, so this version was not tuned to the practice leaderboard — it was tuned the same honest way as v1, by leave-one-out over the kit's comparables, and only kept because it beats v1 on that validation.

## Method — comparable launch curves, anchored on hour 1

A launch-day curve is anchored on its hour-1 print. Across the past launches bundled in the case, the later hours' log-levels depend strongly on the log hour-1 level (correlation about −0.94 at hour 20): a big hour 1 means the world already unlocked and the day stays near that level; a tiny hour 1 means the launch wave is still coming and the day explodes. Per hour, the forecast blends two views of the same pool of past launches:

1. **Local-linear:** weighted least squares of log viewers(hour) on log viewers(hour 1), Gaussian kernel on the log hour-1 distance (bandwidth 1.25), with Gaussian residual quantiles whose spread is smoothed across neighbouring hours. The centre is never extrapolated past the biggest comparable in the pool: if the case's hour 1 exceeds every past launch, the centre is evaluated at the pool's largest log hour-1 (the kernel weights still use the true hour 1, so the biggest launches stay the nearest neighbours).
2. **Ratio quantiles:** weighted empirical quantiles of log(viewers(hour) / viewers(hour 1)), anchored on the case's hour-1 print. The scale kernel's bandwidth follows the hour: 2.0 in hours 2–6, 1.5 in hours 7–12, 1.0 in hours 13–24. Early on the ratio barely depends on scale (correlation near 0 at hour 3), so the kernel pools widely; late in the day the scale dependence is strong (about −0.94 at hour 20), so it pools tightly.
3. **Blend:** 55% (1) + 45% (2) in log space, then every quantile's log-distance from its median is tightened by a factor of 0.95.

Comparables that also launched on PC get a lower weight in the local-linear part (0.5 in hours 2–5, 0.15 in hours 6–24): their PC unlock, hours after the console unlock, adds a second wave a console-only launch never has. GTA VI is console only, so the console launches in the pool carry the forecast. Any hour the pool cannot cover falls back to the house persistence baseline.

## Validation — leave-one-out over the kit's comparables

The practice answers are sealed, so nothing was tuned on them. The model was tuned by leave-one-out over the 37 past launches in the kit (each one forecast from its own hour 1, scored against its own hours 2–24):

| evaluation set | house baseline | v1 | **this entry (v2)** |
|---|---|---|---|
| all 37 comparables | 0.930 | 0.382 | **0.379** |
| big launches (hour 1 ≥ 20k) | 0.321 | 0.249 | **0.249** |
| console midnight-local family | 0.368 | 0.275 | **0.275** |
| console-only launches | ~0.32 | 0.212 | **0.209** |

(Mean pinball loss on the log scale; lower is better. The house baseline scores about 0.387 on the official practice cases, and v1 scored 0.206 there.)

The gain over v1 is small — v1 was already near a local optimum on this validation, and the differences between the best variants were within noise. What changed, and why it was kept: the per-hour ratio bandwidth (the one structural change), the 55/45 blend, the 0.95 spread tightening, and the no-extrapolation cap on the local-linear centre. Each was kept only because the combination beats v1 on all four validation sets at once.

Rejected on the same leave-one-out: unweighted OLS (0.440), plain ratio-quantiles (0.405), diurnal-profile weighting (0.621 — much worse), a pre-release-buzz second regressor (no gain), dropping PC launches entirely (0.722 — the pool gets too small), a quadratic local regression (0.387–0.399), k-nearest-neighbour median ratios (0.399–0.415), winsorised log-levels (no gain), and re-anchored blends that keep only one part's centre (0.406). The per-hour bias check also showed the v1 blend slightly over-predicts big launches' afternoons and under-predicts small launches' late explosions — the ratio bandwidth schedule is the honest fix for that, not a practice-set fit.

## Files

- `main.py` — the whole forecaster (Python 3.13, standard library only).

No network, no wall clock, no files outside the case, no randomness: the same case always produces the same forecast. Runs in ~0.2 s a case.

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Referral

Built as [@pablo-crypto](https://make.fun/r/vky0ybyt) on make.fun.
