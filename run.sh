#!/usr/bin/env bash
# One command on macOS/Linux: picks a free port (8000, then 8001, ...), builds, runs, prints the URL.
#   ./run.sh                 start
#   HOST_PORT=9000 ./run.sh  force a port
#   ./run.sh reset           wipe the demo database first (re-seeds on start)
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "Docker is not installed or not on PATH: https://docs.docker.com/get-docker/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but not running. Start Docker Desktop and retry."; exit 1; }

port_free() { ! (lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1 || nc -z 127.0.0.1 "$1" >/dev/null 2>&1); }

if [ "${1:-}" = "reset" ]; then
  docker compose down >/dev/null 2>&1 || true
  rm -rf data
  echo "Demo database reset."
fi

if [ -z "${HOST_PORT:-}" ]; then
  for p in 8000 8001 8002 8003 8080 8888; do
    if port_free "$p"; then HOST_PORT=$p; break; fi
  done
fi
[ -n "${HOST_PORT:-}" ] || { echo "No free port found; set one: HOST_PORT=9000 ./run.sh"; exit 1; }
export HOST_PORT

[ "${DRY_RUN:-}" = "1" ] && { echo "would start on http://localhost:$HOST_PORT"; exit 0; }

echo "Starting on http://localhost:$HOST_PORT  (Ctrl-C to stop)"
docker compose up --build
