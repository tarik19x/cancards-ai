# ─── Stage 1: Builder ───────────────────────────────────────────────────────
# Install all Python dependencies.
# This stage is discarded after the build — only the installed packages travel
# to the runtime stage.
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build essentials (some packages need gcc to compile C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements.txt first (Docker layer cache: if requirements.txt
# hasn't changed, this layer is reused and pip install is skipped on rebuild)
COPY requirements.txt .

# Install to a prefix directory (/install) so we can cleanly COPY it to the
# runtime stage without bringing in pip, setuptools, or other build metadata.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── Stage 2: Runtime ───────────────────────────────────────────────────────
# Minimal image that only contains what is needed to run the app.
FROM python:3.12-slim

WORKDIR /app

# Create a non-root user. Running as root inside a container is a security risk.
RUN useradd -m -u 1000 appuser

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy only the application code and data that the running server needs
COPY app/ ./app/
COPY data/ ./data/

# Set correct ownership for the non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Document the port (does not publish it — that is done at run time)
EXPOSE 8000

# Health check: AWS App Runner and ECS both use this to determine if the
# container is healthy. Fail fast (3s timeout) so unhealthy containers are
# replaced quickly.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Production command: one worker (App Runner scales by running more containers,
# not more workers per container).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
