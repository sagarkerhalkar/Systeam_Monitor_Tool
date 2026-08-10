FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8082 \
    DORA_DB=/data/dora.db

WORKDIR /app
COPY hackathon/services/dora_collector/app.py /app/app.py

RUN useradd --create-home --uid 10002 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app

USER 10002:10002
VOLUME ["/data"]
EXPOSE 8082
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/healthz', timeout=2).read()"

ENTRYPOINT ["python", "/app/app.py"]
