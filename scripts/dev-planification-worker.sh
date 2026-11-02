#!/usr/bin/env bash
# Synchronise les sources de pilotage (travail, people, finance, incidents).
set -euo pipefail
cd "$(dirname "$0")/../backend"
set -a; . ./.env; set +a
exec .venv/bin/python -m meridian.adapters.inbound.worker.planification_worker "$@"
