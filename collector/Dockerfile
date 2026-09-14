# Build context must be the repo root (this Dockerfile reaches up to
# watchlist.csv), e.g.: docker build -f collector/Dockerfile .
# Railway/Fly/Render: point the Dockerfile path at collector/Dockerfile with
# the build context set to the repo root.
FROM python:3.12-slim

WORKDIR /app

COPY watchlist.csv ./watchlist.csv
COPY collector/requirements.txt ./collector/requirements.txt
RUN pip install --no-cache-dir -r collector/requirements.txt

COPY collector/ ./collector/

WORKDIR /app/collector
CMD ["python", "-m", "app"]
