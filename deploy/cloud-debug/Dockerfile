FROM python:3.12-slim

RUN groupadd --system --gid 10001 costguard \
    && useradd --system --uid 10001 --gid costguard --home-dir /nonexistent costguard

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY costguard_agent ./costguard_agent
COPY costguard_split ./costguard_split
RUN python -m pip install --no-cache-dir ".[split-server]" \
    && rm -rf /build

WORKDIR /app
COPY deploy/cloud-debug/server.py /app/server.py
COPY deploy/cloud-debug/acceptance.py /app/acceptance.py
RUN mkdir /data && chown costguard:costguard /data
USER 10001:10001

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).read()"]

CMD ["python", "/app/server.py"]
