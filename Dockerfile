FROM python:3.12-slim@sha256:d67a7b66b989ad6b6d6b10d428dcc5e0bfc3e5f88906e67d490c4d3daac57047 AS builder

WORKDIR /app

# Pin versions and timestamps for reproducibility.
ARG SOURCE_DATE_EPOCH=1755248916
ARG DEBIAN_SNAPSHOT=20250815T025533Z
ARG DEBIAN_DIST=trixie
ARG UV_VERSION=0.9.7
# Do not include uv metadata as that includes non-reproducible timestamps.
ARG UV_NO_INSTALLER_METADATA=1
# Disable emitting debug symbols as those can contain randomized local paths.
ARG CFLAGS="-g0"

# Install Debian packages from snapshot for reproducibility.
RUN rm -f /etc/apt/sources.list.d/* && \
    echo "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} ${DEBIAN_DIST} main" > /etc/apt/sources.list && \
    echo "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} ${DEBIAN_DIST}-security main" >> /etc/apt/sources.list && \
    echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/10no-check-valid-until && \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv for Python package management.
RUN pip install uv==${UV_VERSION}

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY static/ ./static/
COPY start-server.sh start-worker.sh ./

RUN find . -exec touch -d @${SOURCE_DATE_EPOCH} "{}" \; && \
    find . -type f -exec chmod 644 "{}" \; && \
    find . -type d -exec chmod 755 "{}" \; && \
    chmod 755 start-server.sh start-worker.sh && \
    chown -R root:root .

RUN uv venv && \
    . .venv/bin/activate && \
    uv sync --locked


FROM python:3.12-slim@sha256:d67a7b66b989ad6b6d6b10d428dcc5e0bfc3e5f88906e67d490c4d3daac57047

WORKDIR /app

ARG SOURCE_DATE_EPOCH

# Set environment variables.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Copy application files from builder stage.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/static /app/static
COPY --from=builder /app/start-server.sh /app/start-worker.sh /app/
COPY --from=builder /app/pyproject.toml /app/

EXPOSE 8000

# No default CMD - use compose.yaml to specify start-server.sh or start-worker.sh.
