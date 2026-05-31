#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Use .env if exists
if [ -f .env ]; then
    export $(grep -v '^\s*#' .env | grep -v '^\s*$' | xargs)
fi

ACTION="${1:-fetch}"

case "$ACTION" in
    fetch)
        .venv/bin/python3 src/collector.py --influx "$@"
        ;;
    fetch-only)
        .venv/bin/python3 src/collector.py "$@"
        ;;
    power)
        .venv/bin/python3 src/compute_power.py "$@"
        ;;
    reverse)
        .venv/bin/python3 src/reverse_api.py
        ;;
    analyze)
        .venv/bin/python3 src/analyze_capture.py
        ;;
    docker-up)
        docker compose -f infra/docker-compose.yml up -d
        ;;
    docker-down)
        docker compose -f infra/docker-compose.yml down
        ;;
    docker-logs)
        docker compose -f infra/docker-compose.yml logs -f
        ;;
    *)
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  fetch       Fetch data and write to InfluxDB"
        echo "  fetch-only  Fetch data, print to stdout (no Influx)"
        echo "  power       Compute power from raw index data"
        echo "  reverse     Run Playwright reverse-engineering"
        echo "  analyze     Analyze captured API requests"
        echo "  docker-up   Start InfluxDB + Grafana"
        echo "  docker-down Stop stack"
        echo "  docker-logs Follow logs"
        ;;
esac
