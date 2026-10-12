FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN pip --no-cache-dir install "huggingface_hub>=0.27,<2" "minio>=7,<8"
WORKDIR /app
COPY loader.py /app/loader.py
RUN groupadd --gid 10001 modelops && useradd --uid 10001 --gid 10001 --create-home modelops
USER 10001
ENTRYPOINT ["python3", "/app/loader.py"]
