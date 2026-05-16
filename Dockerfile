# ---- 多阶段构建：编译层 ----
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev libssl-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- 运行层 ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo libffi8 fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
WORKDIR /app
COPY . .

RUN mkdir -p /app/data /app/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
  sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3).status==200 else sys.exit(1)" \
  || exit 1

CMD ["python", "run.py"]
