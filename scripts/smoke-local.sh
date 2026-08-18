#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_LOG="$(mktemp)"
FRONTEND_LOG="$(mktemp)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID"
    wait "$FRONTEND_PID" || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID"
    wait "$BACKEND_PID" || true
  fi
  rm -f "$BACKEND_LOG" "$FRONTEND_LOG"
}

trap cleanup EXIT

PYTHONDONTWRITEBYTECODE=1 python3 backend/main.py >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
python3 scripts/wait_for_http.py http://127.0.0.1:8000/api/health 30

(
  cd frontend
  npm run dev -- --host 127.0.0.1 --port 4173 --strictPort >"$FRONTEND_LOG" 2>&1
) &
FRONTEND_PID=$!
python3 scripts/wait_for_http.py http://127.0.0.1:4173/ 30
python3 scripts/wait_for_http.py http://127.0.0.1:4173/api/health 30
