# Real Qwen2.5-3B serving benchmark

45 valid points and 5,760 real streamed requests; three repeats at concurrency 1/4/8/16/32 for each FP16 profile. Input budget 256, forced output 64, context bound 2048, same checkpoint and seeds.

| Profile | C | Requests/s | Output tokens/s | TTFT P50/P95/P99 ms | TPOT P50/P95/P99 ms | E2E P95 ms | Peak MiB | Mean GPU % | Mean power W |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| baseline | 1 | 1.394 | 89.21 | 46.48/48.13/48.86 | 10.40/11.50/12.08 | 771.07 | 22841 | 75.91 | 309.02 |
| baseline | 4 | 4.880 | 312.34 | 61.01/66.42/67.86 | 11.99/12.87/13.19 | 855.51 | 22743 | 64.48 | 276.92 |
| baseline | 8 | 9.375 | 600.02 | 28.21/45.38/55.22 | 13.01/13.87/13.94 | 905.05 | 22743 | 49.50 | 254.63 |
| baseline | 16 | 17.670 | 1130.88 | 43.86/81.44/85.15 | 13.52/14.31/14.39 | 959.97 | 22743 | 37.66 | 225.95 |
| baseline | 32 | 31.105 | 1990.70 | 96.89/140.26/146.11 | 14.74/15.21/15.30 | 1053.81 | 22743 | 29.45 | 199.77 |
| batching-token-budget | 1 | 1.390 | 88.97 | 46.31/48.18/48.99 | 10.37/12.01/12.45 | 802.14 | 22669 | 75.50 | 312.85 |
| batching-token-budget | 4 | 5.042 | 322.66 | 27.53/33.10/37.61 | 12.19/12.54/12.62 | 818.37 | 22669 | 63.23 | 280.29 |
| batching-token-budget | 8 | 9.978 | 638.59 | 27.26/45.88/49.89 | 12.14/13.07/13.09 | 854.95 | 22669 | 50.84 | 257.18 |
| batching-token-budget | 16 | 16.712 | 1069.54 | 146.38/184.29/185.45 | 13.10/14.81/14.97 | 1012.85 | 22669 | 39.08 | 227.34 |
| batching-token-budget | 32 | 32.534 | 2082.17 | 74.56/141.77/147.89 | 14.18/14.45/14.52 | 1026.04 | 22669 | 28.17 | 197.91 |
| kv-memory-budget | 1 | 1.391 | 89.04 | 46.15/47.68/48.56 | 10.58/11.70/12.13 | 783.90 | 23895 | 75.55 | 313.81 |
| kv-memory-budget | 4 | 5.016 | 321.03 | 27.63/33.79/38.97 | 12.05/13.08/13.55 | 851.32 | 23895 | 63.38 | 280.53 |
| kv-memory-budget | 8 | 9.770 | 625.26 | 33.64/46.71/52.45 | 12.36/12.92/12.97 | 852.13 | 23895 | 50.30 | 257.81 |
| kv-memory-budget | 16 | 18.083 | 1157.30 | 35.72/80.12/82.13 | 13.20/13.76/13.80 | 928.79 | 23895 | 36.21 | 224.42 |
| kv-memory-budget | 32 | 31.654 | 2025.88 | 84.48/138.69/144.40 | 14.53/15.14/15.21 | 1061.67 | 23895 | 28.43 | 200.38 |

Percentile entries are means of three independently measured trial percentiles, not a pooled 384-request percentile. Synthetic traffic does not establish a business workload SLO or maximum capacity.
vLLM already uses continuous batching; the batching profile changes token budget only. KV tuning raises GPU reservation from 0.90 to 0.95. Any difference is descriptive for this bounded workload.
The already successful first C1 point was reused after a summarizer-path repair. One overlapping validation curl point is retained and excluded; only that point was rerun. Negative quality results and all measurement attempts remain traceable.
Detailed request timings, outputs, CPU-controller logs and GPU power/utilization/memory samples remain in the private cloud evidence directory; file hashes are published in validation.json.
