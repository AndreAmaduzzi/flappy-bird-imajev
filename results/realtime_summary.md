# Real-time benchmark: 45 games, decide at most every 4 steps, cap 120 s (speed 1) or 60 s (slowed) game time

| config | difficulty | games | pipes_mean | pipes_sd | pipes_median | pipes_max | frames_mean | decisions_mean | latency_mean_ms | latency_p95_ms | unknown_top_pct | oracle_agreement_pct | deaths |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| direct+rt | easy | 5 | 0.0 | 0.0 | 0 | 0 | 116.2 | 19.0 | 86.0 | 90.9 | 31.6 | 37.9 | pipe_top:4 ground:1 |
| perceive_rule+rt | easy | 5 | 0.0 | 0.0 | 0 | 0 | 45.0 | 2.0 | 249.4 | 252.7 | 100.0 | 60.0 | ground:5 |
| perceive_rule+rt0.125 | easy | 5 | 10.4 | 10.5 | 7 | 27 | 1133.0 | 283.0 | 247.4 | 253.6 | 7.6 | 83.6 | pipe_bottom:5 |
| perceive_rule+rt0.25 | easy | 5 | 3.8 | 2.3 | 4 | 6 | 504.4 | 125.4 | 246.8 | 252.5 | 10.4 | 82.9 | pipe_bottom:5 |
| perceive_rule+rt0.5 | easy | 5 | 1.4 | 1.1 | 1 | 3 | 278.0 | 34.2 | 238.6 | 244.7 | 15.2 | 81.3 | pipe_bottom:5 |
| direct+rt | hard | 5 | 0.6 | 0.5 | 1 | 1 | 119.0 | 19.4 | 86.6 | 90.4 | 26.8 | 47.4 | ceiling:3 pipe_top:2 |
| perceive_rule+rt | hard | 5 | 0.0 | 0.0 | 0 | 0 | 37.0 | 2.0 | 248.8 | 253.7 | 100.0 | 40.0 | ground:5 |
| direct+rt | medium | 5 | 0.0 | 0.0 | 0 | 0 | 53.4 | 8.2 | 85.4 | 89.4 | 56.1 | 48.8 | ground:4 pipe_top:1 |
| perceive_rule+rt | medium | 5 | 0.0 | 0.0 | 0 | 0 | 40.0 | 2.0 | 247.9 | 250.5 | 100.0 | 60.0 | ground:5 |

Latency: client-side time per decision (ms). unknown_top_pct: decisions where unknown was the most likely outcome (the agent then waits). oracle_agreement_pct: decisions equal to the oracle's action in the same state. deaths: cause counts (timeout = survived the cap).
