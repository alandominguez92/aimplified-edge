# AimplifiedEdge — single-image deploy: FastAPI serves the built frontend + API,
# with the C++ EV engine compiled for Linux and the ML models bundled.
# Build context is the aimplified-edge/ directory.

# --- stage 1: build the frontend -------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # -> /fe/dist

# --- stage 2: backend runtime ----------------------------------------------
FROM python:3.13-slim AS runtime

# g++ to compile the C++ engine for Linux (the Windows .exe won't run here)
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

# app code + bundled models/statcast table (see .dockerignore for exclusions)
COPY backend/ /app/

# compile the EV/Kelly engine for Linux (output name is arbitrary on Linux)
RUN g++ -O2 -std=c++17 -o /app/engine/kelly_engine.exe \
        /app/engine/main.cpp /app/engine/kelly.cpp \
    && /app/engine/kelly_engine.exe selftest

# built frontend from stage 1
COPY --from=frontend /fe/dist /app/frontend_dist

ENV PYTHONPATH=/app \
    FRONTEND_DIST=/app/frontend_dist \
    DATA_DIR=/data \
    RUN_SCHEDULER=1 \
    MLB_SEASON=2026 \
    LOKY_MAX_CPU_COUNT=2

EXPOSE 8000
# $PORT is provided by most hosts (Render/Fly); default 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
