#!/bin/sh
# Container start: bring the database up to date (and add demo data if it's empty), then serve.
set -e
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
