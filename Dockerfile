FROM python:3.12-slim as builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
LABEL maintainer="Kyle Johnston" version="1.0.0"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 openssh-client iputils-ping curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -r -s /bin/bash netconfig \
    && mkdir -p /app/instance /app/logs /app/backups \
    && chown -R netconfig:netconfig /app
COPY --from=builder /install /usr/local
COPY --chown=netconfig:netconfig . .
RUN chmod +x /app/entrypoint.sh
USER netconfig
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
