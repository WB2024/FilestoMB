FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CONFIG_HOME=/config \
    MUSIC_ROOT=/music \
    HOST=0.0.0.0 \
    PORT=8000

# Archive extraction from the web UI: 7-Zip for zip/7z, libarchive's bsdtar for
# rar (Debian's 7-Zip can't decompress RAR). fpcalc (Chromaprint) makes AcoustID fingerprints.
RUN apt-get update \
    && apt-get install -y --no-install-recommends 7zip libarchive-tools libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[web]"

# Runs unprivileged. uid 1000 matches the usual owner of the music library
# and of the /config volume (OAuth token + last-browsed directory).
RUN useradd --uid 1000 --create-home filestomb \
    && mkdir -p /config /music \
    && chown filestomb /config
USER filestomb

VOLUME ["/config"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/config', timeout=4)" || exit 1

CMD ["filestomb-web"]
