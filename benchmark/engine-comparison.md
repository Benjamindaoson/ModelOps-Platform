# Matched vLLM and SGLang benchmark

Same pinned Qwen2.5-3B model/tokenizer, FP16 and synthetic token-ID prompts. Three repeats x32 requests, three genuine warmups. Cache OFF. Sampling and actual usage lengths checked. Percentiles pool96 actual requests; throughput is mean of three trial rates.

|Engine|Load|C|Output tokens/s|TTFT P50/P95/P99 ms|TPOT P50 ms|E2E P95 ms|Peak MiB|Errors|
|---|---|---:|---:|---|---:|---:|---:|---:|
|sglang|A|1|100.42|31.30/31.93/32.62|9.62|638.01|22925|0|
|sglang|A|4|367.10|75.36/76.78/76.93|9.86|697.78|22969|0|
|sglang|A|8|658.18|133.92/225.28/226.09|10.02|854.41|23113|0|
|sglang|A|16|759.13|225.24/396.59/397.19|17.95|1575.64|23199|0|
|sglang|A|32|1285.21|303.11/514.77/515.17|20.18|1590.85|23199|0|
|sglang|B|1|91.03|144.49/145.20/146.26|9.93|1406.85|23219|0|
|sglang|B|4|277.08|359.11/541.73/543.76|11.75|1849.26|23239|0|
|sglang|B|8|418.49|627.23/1070.16/1080.65|14.34|2453.79|23239|0|
|sglang|B|16|482.79|1199.59/2116.69/2141.55|24.25|4302.57|23239|0|
|sglang|B|32|629.66|2229.74/4151.42/4267.50|33.51|6499.48|23239|0|
|sglang|C|1|102.61|45.48/46.00/46.72|9.67|4993.29|23239|0|
|sglang|C|4|392.06|134.11/135.97/136.46|9.96|5224.75|23239|0|
|sglang|C|8|748.55|231.45/268.22/268.52|10.26|5474.99|23239|0|
|sglang|C|16|897.37|320.08/516.06/518.04|17.19|9287.93|23239|0|
|sglang|C|32|1665.95|568.42/1012.46/1014.21|18.03|9904.40|23239|0|
|vllm|A|1|91.34|23.28/24.32/25.15|10.74|706.94|23103|0|
|vllm|A|4|329.42|74.59/80.55/82.49|11.13|781.92|23103|0|
|vllm|A|8|601.30|134.45/142.59/143.02|11.33|856.99|23103|0|
|vllm|A|16|1016.77|195.75/269.53/269.84|12.65|1022.20|23103|0|
|vllm|A|32|1450.34|343.84/525.65/525.99|16.57|1403.91|23103|0|
|vllm|B|1|84.33|134.17/135.41/136.48|10.89|1522.67|23103|0|
|vllm|B|4|256.26|277.57/531.60/544.99|13.50|2126.22|23103|0|
|vllm|B|8|397.57|402.89/1066.72/1083.82|16.99|3217.84|23103|0|
|vllm|B|16|538.60|418.20/2163.68/2186.12|25.95|5480.14|23105|0|
|vllm|B|32|619.44|2378.89/4453.18/4511.46|31.77|6585.78|23105|0|
|vllm|C|1|92.46|37.68/38.35/39.09|10.76|5554.87|23105|0|
|vllm|C|4|349.10|132.06/138.47/139.25|11.22|5877.58|23105|0|
|vllm|C|8|664.26|165.18/264.36/264.64|11.73|6212.07|23105|0|
|vllm|C|16|1224.78|253.40/519.21/519.49|12.56|6947.41|23105|0|
|vllm|C|32|1905.15|615.43/1039.38/1043.30|15.53|8587.62|23105|0|

Native schedulers/KV/CUDA graphs are upstream capabilities. New adapters provide immutable loading, process ownership, resume-safe measurement and evidence. SGLang0.4.10 Torch2.7.1/cu126 uses Triton attention/PyTorch sampling; vLLM0.10.2 Torch2.8/cu128 uses its recorded defaults. Official tagged C++ source repaired the SGLang wheel omission.

Separate one-factor batch-token/sequence/memory experiments and repeated-context prefix-cache A/B are in profiling_summary.json. No general winner or broad quality claim follows from synthetic throughput.
