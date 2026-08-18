#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cleanup() {
  docker compose down --remove-orphans
}

trap cleanup EXIT

docker compose up --build -d
python3 scripts/wait_for_http.py http://127.0.0.1:8000/api/health 60
python3 scripts/wait_for_http.py http://127.0.0.1:8080/healthz 60
python3 scripts/wait_for_http.py http://127.0.0.1:8080/api/health 60
docker compose ps
