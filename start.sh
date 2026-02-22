#!/bin/bash

cd /home/runner/workspace

if ! lsof -i :3001 -sTCP:LISTEN > /dev/null 2>&1; then
  cd /home/runner/workspace/backend/management
  npx tsx src/index.ts > /tmp/mgmt.log 2>&1 &
  cd /home/runner/workspace
fi

if ! lsof -i :8001 -sTCP:LISTEN > /dev/null 2>&1; then
  cd /home/runner/workspace/backend/ai-service
  python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 > /tmp/ai.log 2>&1 &
  cd /home/runner/workspace
fi

sleep 2

cd /home/runner/workspace/frontend
exec npx next dev --hostname 0.0.0.0 --port 5000
