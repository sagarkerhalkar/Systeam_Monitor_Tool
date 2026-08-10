FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/commercial \
    MONITOR_PORT=8443 \
    MONITOR_DATA_ROOT=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10000 appuser \
    && mkdir -p /app /data \
    && chown -R appuser:appuser /app /data

WORKDIR /app
COPY commercial /app/commercial
COPY hackathon/services/monitor/entrypoint.sh /app/entrypoint.sh
RUN chmod 0755 /app/entrypoint.sh

USER 10000:10000
VOLUME ["/data"]
EXPOSE 8443

HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import ssl,urllib.request; c=ssl._create_unverified_context(); urllib.request.urlopen('https://127.0.0.1:8443/api/v1/health/live', context=c, timeout=3).read()"

ENTRYPOINT ["/app/entrypoint.sh"]
