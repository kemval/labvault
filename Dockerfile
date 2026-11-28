# LabVault production image (roadmap 5.2, ADR 0024; production build, ADR 0026:
# no demo mode, no data simulator): the app, Litestream for
# continuous backup (ADR 0023) and a health check. Runs as a non-root user;
# the database lives on the /data volume. Configuration and secrets come only
# from the environment (deploy/.env.example).
FROM python:3.12-slim-bookworm

ARG LITESTREAM_VERSION=0.5.18
# SHA-256 of the release tarballs (from the release's checksums), per architecture.
ARG LITESTREAM_SHA256_amd64=d3687b9fd0f2e9426bbd3da828429ff3f1dfc5c9b74d54fdf028e4ee510e7dea
ARG LITESTREAM_SHA256_arm64=922a09e6a7ac67f2095571894dc6382e94e1dd4cdd9674883ddf1a8e74ab982d
ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LABVAULT_DB_PATH=/data/labvault.db \
    LABVAULT_BUILD=production \
    PORT=8501

# Litestream, verified against its published checksum before it is installed.
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) arch=x86_64; sum="$LITESTREAM_SHA256_amd64" ;; \
      arm64) arch=arm64;  sum="$LITESTREAM_SHA256_arm64" ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-${arch}.tar.gz"; \
    python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/litestream.tar.gz')" "$url"; \
    echo "$sum  /tmp/litestream.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin litestream; \
    rm /tmp/litestream.tar.gz; \
    litestream version

WORKDIR /app
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

COPY . .
RUN useradd --system --uid 10001 --home-dir /app labvault \
 && mkdir -p /data && chown labvault /data
USER labvault
VOLUME ["/data"]
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "scripts/healthcheck.py"]

ENTRYPOINT ["deploy/start.sh"]
