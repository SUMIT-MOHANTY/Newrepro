# =============================================================================
# Multi-Stage Dockerfile for Django Todo Application
# Supports: Development (SQLite), Testing, Production (PostgreSQL)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# Purpose: Install dependencies and prepare build artifacts
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Development
# Purpose: Hot-reload development with SQLite
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS development

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=app.core.config \
    DEBUG=True

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set working directory
WORKDIR /app

# Copy entrypoint script
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create directories for SQLite and set permissions
RUN mkdir -p /app/data /app/staticfiles && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "main:application", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Stage 3: Production
# Purpose: Optimized production image with PostgreSQL
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=app.core.config \
    DEBUG=False \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user with minimal privileges
RUN groupadd -r appgroup && useradd -r -g appgroup --no-create-home appuser

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appgroup . .

# Copy entrypoint and healthcheck scripts
COPY --chown=appuser:appgroup deploy/entrypoint.sh /entrypoint.sh
COPY --chown=appuser:appgroup deploy/healthcheck.sh /healthcheck.sh
RUN chmod +x /entrypoint.sh /healthcheck.sh

# Create necessary directories with proper permissions
RUN mkdir -p /app/staticfiles /app/data && \
    chown -R appuser:appgroup /app

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /healthcheck.sh

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "main:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
