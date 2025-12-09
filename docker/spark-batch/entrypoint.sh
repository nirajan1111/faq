#!/bin/bash
set -e

# Start cron service
service cron start

# Run initial batch job
echo "Running initial batch job..."
python -m src.batch.spark_batch

# Keep container running and tail logs
tail -f /app/logs/batch.log
