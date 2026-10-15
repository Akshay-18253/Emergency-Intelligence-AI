# ==============================================================================
# Emergency Intelligence AI — Embedded Operations Center (EOC) Container Image
# ==============================================================================
# Architectural Invariant: STRICT ZERO RUNTIME EXTERNAL DEPENDENCIES.
# This container image requires NO pip install steps. It operates 100% on
# the Python Standard Library and self-contained static web assets.
# ==============================================================================

FROM python:3.12-slim

# Container metadata
LABEL maintainer="Emergency Intelligence AI Contributors"
LABEL description="Intelligent navigation and crisis routing engine for emergency medical and disaster response"
LABEL version="0.2.0"

# Python execution hardening
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Set working directory
WORKDIR /app

# Copy application source code, assets, license, and packaging metadata
COPY pyproject.toml LICENSE README.md /app/
COPY src/ /app/src/

# Standard non-root system user for security in containerized environments
RUN useradd -u 10001 -m -s /bin/sh eocuser && \
    chown -R eocuser:eocuser /app

USER eocuser

# Expose default EOC server binding port
EXPOSE 8080

# Built-in healthcheck using Python's standard library urllib (no curl/wget needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

# Default execution entrypoint: run embedded HTTP server
ENTRYPOINT ["python", "-m", "emergency_intelligence.app.server"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
