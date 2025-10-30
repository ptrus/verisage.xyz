#!/bin/bash

# Get uvicorn worker count from environment variable (default: 8).
UVICORN_WORKERS=${UVICORN_WORKERS:-8}

echo "Starting uvicorn with $UVICORN_WORKERS worker(s)..."

# Start uvicorn web server.
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers $UVICORN_WORKERS
