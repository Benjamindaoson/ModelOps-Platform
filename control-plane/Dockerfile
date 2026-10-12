FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /srv/modelops
COPY pyproject.toml ./
COPY modelops/ ./modelops/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN pip install --no-cache-dir ".[postgres]" \
  && groupadd -r -g 10001 modelops \
  && useradd -r -u 10001 -g modelops -d /srv/modelops modelops
USER 10001
EXPOSE 8080
# Database migrations are a distinct privileged job, not a startup side effect.
CMD ["uvicorn", "modelops.main:app", "--host", "0.0.0.0", "--port", "8080"]
