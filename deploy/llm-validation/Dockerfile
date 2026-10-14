FROM vllm/vllm-openai:v0.10.2@sha256:607442e407b0fea97f8a132a78b787c121a996dd4de181fa08e8da06e71ec2db
LABEL org.opencontainers.image.source="https://github.com/Benjamindaoson/ModelOps-Platform" \
      org.opencontainers.image.description="Hash-verified QLoRA merged model serving; weights mounted privately"
COPY ops/vllm_start.py /app/start.py
ENV PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
    MODEL_PATH=/model HOME=/tmp XDG_CACHE_HOME=/tmp/cache HF_HOME=/tmp/hf VLLM_CACHE_ROOT=/tmp/vllm
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=6 \
 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).read()" || exit 1
ENTRYPOINT ["python3","/app/start.py"]
