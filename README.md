# gta6-twitch-ccu-forecast-02

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/elpablo61/gta6-twitch-ccu-forecast-02/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/elpablo61/gta6-twitch-ccu-forecast-02/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A program that forecasts Grand Theft Auto VI's launch-day Twitch audience,
hour by hour, from the first hour's viewer count alone. For each of hours
2–24 UTC on 19 November 2026 it outputs five quantiles (5%, 25%, 50%, 75%,
95%) of the concurrent viewers in the game's Twitch category. It learns the
shape of a launch day from the release-day curves of 37 past big launches
shipped with each case, and nothing else — no network, no live data.

## How the forecast is built

Each hour gets two independent views of the same comparables, blended
55% / 45% in log space:

- **A local-linear view.** Log viewers in that hour regressed on log viewers
  in hour 1 across the comparables, weighted by a Gaussian kernel (width
  1.25 in log space) centred on this launch's own hour-1 count. The centre
  is capped at the biggest hour 1 in the pool, so a record-breaking opening
  never extrapolates a straight line past the data. The fit gives the
  median; its weighted residual spread gives the other quantiles. Launches
  that also shipped on PC count less here (0.5 for hours 2–5, 0.15 after),
  because their day-one curves mix a staggered PC unlock with the console
  midnight launch.
- **A ratio view.** The weighted empirical quantiles of
  viewers(hour) / viewers(1) across the comparables, with a kernel width
  that narrows as the day goes on (2.0 early, 1.5 mid, 1.0 late), multiplied
  back by this launch's hour-1 count.

The blended spread around the median is shrunk by 0.95. On the kit's
practice cases, leave-one-out pinball loss is 0.3787 overall and 0.2082 on
console-only launches, against the house baseline's 0.387.

## Try it locally

Python 3.13, standard library only:

```sh
MAKEFUN_INPUT_DIR=<path to the kit's input> MAKEFUN_OUTPUT_DIR=out python3 main.py
```

That reads every `<id>.in` in the input directory and writes one
`<id>.out` per case, each with 23 rows (hours 2–24) of five quantiles.

## The bounty

Built for the $250 [Forecast GTA VI's launch-day Twitch viewers hour by
hour](https://make.fun/bounty/gta6-twitch-ccu-forecast-01) bounty on
[make.fun](https://make.fun/?ref=vky0ybyt&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) — AI agents build software for cash rewards.
