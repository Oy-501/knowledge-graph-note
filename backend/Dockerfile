# 生产镜像：单进程 uvicorn + SQLite；数据与模型各自挂卷
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 先装 CPU 版 torch，避免把 CUDA 包拉进镜像
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home appuser \
    && mkdir -p /data/uploads /data/exports /models \
    && chown -R appuser:appuser /app /data /models

USER appuser

ENV DB_MODE=sqlite \
    SQLITE_PATH=/data/kg.db \
    UPLOAD_DIR=/data/uploads \
    EXPORT_DIR=/data/exports

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
