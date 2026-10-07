# Stage 1: build the React app
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI serves the API at /api and the built UI at /
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY pack/ pack/
COPY --from=web /web/dist frontend/dist

# Layout: /app/backend (cwd), /app/pack, /app/frontend/dist — matches the config.py defaults.
ENV PACK_DIR=/app/pack
WORKDIR /app/backend
EXPOSE 8000
# Render injects $PORT. --proxy-headers + forwarded-allow-ips so uvicorn sees Render's HTTPS
# (needed for the secure session cookie when COOKIE_SECURE=true).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
