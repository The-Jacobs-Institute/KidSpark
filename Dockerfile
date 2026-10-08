FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONPATH=/app/backend:/app PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY retrieval/ ./retrieval/
COPY ingestion/ ./ingestion/
COPY shared/ ./shared/
COPY block_catalog/ ./block_catalog/
COPY config/ ./config/
RUN useradd --uid 10001 --create-home kidspark && mkdir -p work runs model_store model_registry && chown -R kidspark:kidspark /app
COPY --from=ui /ui/dist ./ui/dist
USER kidspark
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
