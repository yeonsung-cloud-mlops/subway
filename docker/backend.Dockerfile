# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 SQLITE_PATH=/app/var/subway.sqlite3 TZ=Asia/Seoul
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 subway \
    && useradd --uid 10001 --gid subway --no-create-home subway
COPY requirements.txt requirements-lock.txt ./
RUN pip install -r requirements.txt
COPY app ./app
COPY datasets ./datasets
COPY artifacts/model.json artifacts/metrics.json ./artifacts/
COPY scripts ./scripts
RUN mkdir -p /app/var && chown -R subway:subway /app/var /app/artifacts
USER subway
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

FROM runtime AS test
USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install -r requirements-dev.txt
COPY tests ./tests
USER subway
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
