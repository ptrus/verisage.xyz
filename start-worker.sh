#!/bin/bash

# Get worker count from environment variable (default: 8).
WORKER_COUNT=${WORKER_COUNT:-8}

echo "Starting Huey consumer with $WORKER_COUNT threaded worker(s)..."

# Start Huey consumer with multiple workers using threaded model.
python3 -m huey.bin.huey_consumer src.workers.huey --workers $WORKER_COUNT --worker-type thread
