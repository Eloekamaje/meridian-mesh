#!/usr/bin/env bash
# Démarre le worker d'ingestion pull-first en développement (Postgres + Mongo déjà lancés).
# Usage : scripts/dev-source-worker.sh [--une-passe] [--intervalle 5] [...]
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec .venv/bin/python -m jumeau.source_worker "$@"
