#!/bin/bash

cd /home/runner/workspace

if ! lsof -i :3001 -sTCP:LISTEN > /dev/null 2>&1; then
  echo "[START] Starting Management API on port 3001..."
  cd /home/runner/workspace/backend/management
  npx ts-node -r tsconfig-paths/register src/main.ts &
  cd /home/runner/workspace
fi

if ! lsof -i :8001 -sTCP:LISTEN > /dev/null 2>&1; then
  echo "[START] Starting AI Service on port 8001..."
  cd /home/runner/workspace/backend/ai-service
  python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 &
  cd /home/runner/workspace
fi

if ! lsof -i :5001 -sTCP:LISTEN > /dev/null 2>&1; then
  echo "[START] Starting Next.js frontend on port 5001..."
  cd /home/runner/workspace/frontend
  npx next dev --hostname 0.0.0.0 --port 5001 &
  cd /home/runner/workspace
fi

echo "[START] Waiting for services..."
sleep 3

echo "[START] Starting reverse proxy on port 5000..."
exec python3 proxy.py
