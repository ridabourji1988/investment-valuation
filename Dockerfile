# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- Stage 2: Python backend serving API + built frontend ----
FROM python:3.11-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
# Built frontend goes where app.py expects it: <repo>/web/dist  (i.e. backend/../web/dist)
COPY --from=web /web/dist ./web/dist

WORKDIR /app/backend
EXPOSE 8000
# Railway (and most PaaS) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn valuescope.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
