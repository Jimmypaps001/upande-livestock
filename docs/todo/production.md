# To do: Livestock Production (Mutara beef)

Mutara's production scope puts livestock forecasting in this app, under a new
**Production** area on the `mutara-beef` line. The crop enterprises (avocado,
fruit & vegetables, aquaculture, apiary) live in `upande_production`; livestock
does not. Another session owns this work.

## Production Forecasting: Livestock

- **Weight gain & output forecasting.** Predict expected weight gain (beef: daily
  gain per bull and per herd/weight band) or other productive output per animal
  or herd group, from historical performance and the herd's feeding programme.
- **Buyer-commitment planning support.** Translate livestock output forecasts
  into supportable volumes for buyer or market commitments (e.g. finished bulls
  and liveweight available per week or month).
- **Herd productivity trend analysis.** Analyse past productivity trends across
  the herd to refine forecasting accuracy over successive cycles.
- **Forecast accuracy reporting (plan vs actual).** Compare forecast livestock
  output against actual recorded outcomes (weighings, exits), and surface the
  gaps to improve future predictions.

## Notes

- Milk is out of scope for Mutara beef (it all goes to calves, none is sold).
  Output means weight and animals ready for exit.
- Build on what `mutara-beef` already has: weighings, weight bands with target
  daily gain, Weighing Overdue, Weight Band Move Due / Ready for Exit, and the
  Bull Performance page.
- Keep the forecast and plan-vs-actual concepts consistent with
  `upande_production` (ISO weeks, `error_pct = (actual - forecast) / forecast`),
  so both read the same in Mutara's dashboards.
