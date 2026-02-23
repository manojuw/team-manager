#!/bin/bash

cd /home/runner/workspace

echo "[START] Stopping any existing services..."
for pid in $(ps aux | grep -E "ts-node.*src/main|uvicorn.*8001|next dev.*5001" | grep -v grep | awk '{print $2}'); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 2

echo "[START] Starting Management API on port 3001..."
cd /home/runner/workspace/backend/management
npx ts-node -r tsconfig-paths/register src/main.ts &
cd /home/runner/workspace

echo "[START] Starting AI Service on port 8001..."
cd /home/runner/workspace/backend/ai-service
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 &
cd /home/runner/workspace

echo "[START] Starting Next.js frontend on port 5001..."
cd /home/runner/workspace/frontend
npx next dev --hostname 0.0.0.0 --port 5001 &
cd /home/runner/workspace

echo "[START] Waiting for services..."
sleep 3

echo "[START] Starting reverse proxy on port 5000..."
exec python3 proxy.py
