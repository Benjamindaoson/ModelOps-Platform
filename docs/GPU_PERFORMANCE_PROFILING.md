# Measured GPU profile and optimization

Actual PyTorch/CUDA trace; Nsight unavailable. Summed overlapping event duration is not wall-clock attribution, bandwidth or occupancy.

|Hot kernel|Summed ms|
|---|---:|
|void cutlass::Kernel2<cutlass_80_tensorop_f16_s16816gemm_relu_f16_256x128_32x3_tn_align8>(cutlass_80_tensorop_f16_s16816|2749.125|
|std::enable_if<!(false), void>::type internal::gemvx::kernel<int, int, __half, __half, __half, float, false, true, true,|2584.085|
|void cutlass::Kernel2<cutlass_80_wmma_tensorop_f16_s161616gemm_f16_16x16_128x2_tn_align8>(cutlass_80_wmma_tensorop_f16_s|2029.494|
|ampere_fp16_s16816gemm_fp16_256x128_ldg8_f2f_stages_32x3_tn|1120.393|
|std::enable_if<!(false), void>::type internal::gemvx::kernel<int, int, __half, __half, __half, float, false, true, true,|946.664|
|void flash::flash_fwd_splitkv_kernel<Flash_fwd_kernel_traits<128, 64, 128, 4, false, false, cutlass::half_t, Flash_kerne|598.060|
|void flash::flash_fwd_splitkv_kernel<Flash_fwd_kernel_traits<128, 64, 128, 4, false, false, cutlass::half_t, Flash_kerne|519.293|
|triton_poi_fused_mul_silu_1|271.324|

The measured trace contains substantial dense GEMM/GEMV work and attention. Repeated long-context prefill was selected for a cache experiment; this is an evidenced workload optimization, not certification that all decode is HBM-bound.

|Repeat|Output text identical|TTFT P50 ratio on/off|TPOT P50 ratio|Throughput ratio|
|---|---|---:|---:|---:|
|0|True|0.1329|0.4870|2.2804|
|1|True|0.0903|0.4874|2.2964|
|2|True|0.0904|0.4866|2.3040|

Same frozen FP16 weights,2048 input/128 output, C16,32 requests x3 repeats. Warmup3. Same context intentionally repeats; no general unique-context speedup claim. All96 request outputs match exactly. Native prefix caching is inherited; experiment coordination and verification are new.

One-factor batch4096 / max-sequences32 / static-memory.60 tests for both engines retain every run. Full latency/memory/power/config results and failures: [profiling_summary.json](evidence/inference-hardening/profiling_summary.json).

Raw trace paths and SHA256:
- /data/ModelOps-Platform/tmp/v1-production-readiness/Evidence/inference-hardening/profiling/profile-fp16/pytorch-2522_13219.1791939108022938581.pt.trace.json.gz — e360071f2430f889a25e487adc59894b0426e8fda2904b8d13210bb4b05fbeac
- /data/ModelOps-Platform/tmp/v1-production-readiness/Evidence/inference-hardening/profiling/profile-fp16/pytorch-2522_13131.async_llm.1791939095541978214.pt.trace.json.gz — a512dd0a8f4271007190d71b31bd3cf67c6941be63d8deed342ea37badd096c1
