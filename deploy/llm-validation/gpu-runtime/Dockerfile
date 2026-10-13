FROM vllm/vllm-openai:v0.10.2@sha256:607442e407b0fea97f8a132a78b787c121a996dd4de181fa08e8da06e71ec2db
COPY ops/vllm_start.py /app/start.py
COPY ops/gpu_runtime_validation.py /app/gpu_runtime_validation.py
COPY deploy/llm-validation/gpu-runtime/container-run.sh /app/container-run.sh
RUN chmod 0555 /app/container-run.sh
ENV MODEL_PATH=/model SERVED_MODEL_NAME=modelops-qwen3b-qlora HF_HOME=/tmp/hf VLLM_CACHE_ROOT=/tmp/vllm XDG_CACHE_HOME=/tmp/cache SERVING_HOST=0.0.0.0 SERVING_PORT=8000
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=120s CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"
ENTRYPOINT ["/app/container-run.sh"]
