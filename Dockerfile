FROM python:3.12-slim
RUN useradd --create-home --uid 10001 monitor
WORKDIR /app
COPY . /app
RUN mkdir -p /app/data && chown -R monitor:monitor /app
USER monitor
EXPOSE 2278
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2278/api/health', timeout=3).read()"
CMD ["python", "-u", "universal_server.py", "--host", "0.0.0.0", "--port", "2278"]
