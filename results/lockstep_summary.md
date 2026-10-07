# Benchmark: 90 games, decide every 4 steps, cap 120 s game time

| config | difficulty | games | pipes_mean | pipes_sd | pipes_median | pipes_max | frames_mean | decisions_mean | latency_mean_ms | latency_p95_ms | unknown_top_pct | oracle_agreement_pct | deaths |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| direct | easy | 5 | 0.0 | 0.0 | 0 | 0 | 110.2 | 28.0 | 83.6 | 88.1 | 39.3 | 34.3 | ceiling:2 pipe_top:2 ground:1 |
| direct+2f | easy | 5 | 0.0 | 0.0 | 0 | 0 | 67.0 | 17.4 | 148.5 | 154.8 | 8.0 | 39.1 | ground:4 pipe_top:1 |
| oracle | easy | 5 | 74.0 | 0.0 | 74 | 74 | 7200.0 | 1800.0 | 2.1 | 2.7 | 0.0 | 100.0 | timeout:5 |
| perceive_rule | easy | 5 | 47.8 | 33.3 | 67 | 74 | 4702.2 | 1175.6 | 249.0 | 255.7 | 4.6 | 86.5 | pipe_bottom:4 timeout:1 |
| perceive_rule+2f | easy | 5 | 16.0 | 15.6 | 12 | 41 | 1676.0 | 419.4 | 435.8 | 442.7 | 2.1 | 81.2 | pipe_bottom:3 pipe_top:2 |
| random | easy | 5 | 0.2 | 0.4 | 0 | 1 | 123.2 | 31.2 | 0.0 | 0.0 | 0.0 | 50.6 | ground:3 ceiling:1 pipe_bottom:1 |
| direct | hard | 5 | 0.0 | 0.0 | 0 | 0 | 89.8 | 23.0 | 85.8 | 88.9 | 31.3 | 34.8 | pipe_top:4 ceiling:1 |
| direct+2f | hard | 5 | 0.0 | 0.0 | 0 | 0 | 37.0 | 10.0 | 145.2 | 155.3 | 12.0 | 26.0 | ground:5 |
| oracle | hard | 5 | 126.0 | 0.0 | 126 | 126 | 7200.0 | 1800.0 | 1.6 | 2.3 | 0.0 | 100.0 | timeout:5 |
| perceive_rule | hard | 5 | 3.4 | 5.1 | 1 | 12 | 299.6 | 75.2 | 247.8 | 254.3 | 8.5 | 75.3 | pipe_top:4 pipe_bottom:1 |
| perceive_rule+2f | hard | 5 | 3.0 | 3.5 | 2 | 8 | 270.2 | 67.8 | 429.5 | 438.8 | 8.8 | 76.1 | pipe_top:4 pipe_bottom:1 |
| random | hard | 5 | 0.0 | 0.0 | 0 | 0 | 87.2 | 22.4 | 0.0 | 0.0 | 0.0 | 50.0 | ground:2 pipe_bottom:2 pipe_top:1 |
| direct | medium | 5 | 0.0 | 0.0 | 0 | 0 | 105.0 | 26.6 | 85.6 | 88.9 | 31.6 | 34.6 | pipe_top:3 ceiling:2 |
| direct+2f | medium | 5 | 0.0 | 0.0 | 0 | 0 | 40.0 | 10.0 | 142.5 | 152.6 | 22.0 | 32.0 | ground:5 |
| oracle | medium | 5 | 99.0 | 0.0 | 99 | 99 | 7200.0 | 1800.0 | 1.8 | 2.3 | 0.0 | 100.0 | timeout:5 |
| perceive_rule | medium | 5 | 5.2 | 6.9 | 3 | 17 | 496.4 | 124.4 | 247.2 | 252.2 | 8.2 | 80.7 | pipe_bottom:3 pipe_top:2 |
| perceive_rule+2f | medium | 5 | 8.8 | 7.0 | 8 | 19 | 759.2 | 190.2 | 432.2 | 440.6 | 3.7 | 77.4 | pipe_top:5 |
| random | medium | 5 | 0.2 | 0.4 | 0 | 1 | 118.0 | 29.8 | 0.0 | 0.0 | 0.0 | 55.7 | ground:2 pipe_bottom:2 pipe_top:1 |

Latency: client-side time per decision (ms). unknown_top_pct: decisions where unknown was the most likely outcome (the agent then waits). oracle_agreement_pct: decisions equal to the oracle's action in the same state. deaths: cause counts (timeout = survived the cap).
