# Project X — imagen única: construye el frontend y lo sirve desde el backend.
# (Unidad 3: contenerización.) Multi-stage para no arrastrar Node al runtime.

# --- etapa 1: build del frontend (React + Vite) ---
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
COPY shared/ /shared/
RUN npm run build

# --- etapa 2: runtime Python (FastAPI sirve WS + la web construida) ---
FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8787
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY shared/ ./shared/
COPY --from=web /web/dist ./web/dist

EXPOSE 8787
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if b'true' in urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",8787)}/health').read() else 1)"
CMD ["python", "app.py"]
