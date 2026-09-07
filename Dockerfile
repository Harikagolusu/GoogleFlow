# =============================================================================
# GoogleFlow Dockerfile — Cloud Run production
# =============================================================================
# Builds the React frontend and serves it via FastAPI on a single port.
# Environment variables configure all secrets and external services.
# =============================================================================

FROM python:3.11-slim AS base

# -----------------------------------------------------------------------------
# Install system dependencies needed for both frontend and backend
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 1: Build React frontend
# -----------------------------------------------------------------------------
FROM base AS frontend

COPY --from=node:20-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
ENV PATH="/usr/local/lib/node_modules/npm/node_modules/bin:$PATH"

# Copy and build frontend
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Production image
# -----------------------------------------------------------------------------
FROM base

# Install Python dependencies
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source
COPY backend/ /app/backend/

# Copy built frontend from stage 1
COPY --from=frontend /app/dist /app/dist

# Environment variables for production
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV FRONTEND_DIST=/app/dist

# Expose the port Cloud Run expects
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Run uvicorn - bind to 0.0.0.0 for Cloud Run
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
