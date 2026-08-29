#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
  if python -c "import psycopg2; psycopg2.connect('$DATABASE_URL')" 2>/dev/null; then
    echo "PostgreSQL is ready!"
    break
  fi
  echo "Attempt $i: PostgreSQL not ready, waiting..."
  sleep 3
done

echo "Running database migrations..."
alembic upgrade head || echo "Migration skipped"

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
