#!/bin/bash

cd /home/runner/workspace
export PATH="/home/runner/workspace/bin:$PATH"

echo "[START] Stopping any existing services..."
for pid in $(ps aux | grep -E "ts-node.*src/main|uvicorn.*8001|next (dev|start).*5001|next-server" | grep -v grep | awk '{print $2}'); do
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

echo "[START] Building and starting Next.js frontend on port 5001..."
cd /home/runner/workspace/frontend
export NEXT_PUBLIC_SITE_URL=https://b31b57a1-419f-4167-a41c-da7c93c04281-00-1fzcly9rvrykj.janeway.replit.dev
if [ ! -d ".next" ] || [ "$(find src -newer .next/BUILD_ID -print -quit 2>/dev/null)" ]; then
  echo "[START] Building Next.js..."
  npx next build
fi
npx next start --hostname 0.0.0.0 --port 5001 &
cd /home/runner/workspace

echo "[START] Waiting for services..."
sleep 3

echo "[START] Starting reverse proxy on port 5000..."
exec python3 proxy.py
