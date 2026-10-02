# M4-L configs

`m4l-<instance>-<method>.yaml` — one job per (instance, method), 10 seeds,
100 iterations, equal construction budget. All 12 jobs together reproduce
`experiments/results/m4l-tsp/` (runs.csv = concatenation of the jobs'
`runs-*.csv`, summary.csv/json = the merge script's output).

Protocol note (stated in every caption): reduced from the original
30 seeds x 200 iterations to 10 seeds x 100 iterations for wall-clock
feasibility on this machine; all four methods share the identical reduced
protocol, nothing is tuned.
