# Multi-stage Dockerfile for XMRT-Ecosystem-Redis-LangGraph
# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Copy and install dependencies
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Build application
# Python apps don't typically need a build step
RUN python -m compileall .

# Production stage
FROM python:3.11-slim AS production

WORKDIR /app

# Create non-root user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

# Copy built application from builder stage
COPY --from=builder --chown=appuser:appgroup /app/. ./.

# Copy runtime dependencies
COPY --from=builder /app/requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Set security headers and configurations
ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Start application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
