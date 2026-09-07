#!/usr/bin/env bash
# Start both the backend and frontend dev servers.
set -e

echo "Starting LifeFlow backend on port 8010..."
cd "$(dirname "$0")/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8010 &
BACKEND_PID=$!

echo "Starting Vite frontend on port 5173..."
cd "$(dirname "$0")"
npm run dev -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8010  (PID $BACKEND_PID)"
echo "Frontend: http://localhost:5173  (PID $FRONTEND_PID)"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait for either to exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
